// Internal endpoints called by GPU workers and operators (CONTRACT sections 5, 9, 9b).

import { requireSharedSecret } from "./auth";
import { loadPricingConfig } from "./config";
import { badRequest, HttpError, json, readJson } from "./http";
import { finalizeJob, outputKeyFor } from "./jobs";
import { settleCents } from "./pricing";
import { isProviderName } from "./providers/types";
import type { Env, JobRow, JobStatus, WorkerState } from "./types";

const ERROR_MAX_CHARS = 2000;
const WORKER_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const PROVIDER_RE = /^[a-z]{1,20}$/;
const WORKER_STATES: readonly WorkerState[] = ["booting", "idle", "busy"];
export const JOB_REPORT_STATUSES = ["running", "succeeded", "failed", "retry"] as const;
export const DEFAULT_RETRY_ERROR = "worker requested retry";
export const DEFAULT_FAILURE_ERROR = "worker reported failure";

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isSafeNonNegInt(v: unknown): v is number {
  return typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
}

function isNonNegFinite(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v) && v >= 0;
}

function optionalNonNegFinite(v: unknown, name: string): number | null {
  if (v === undefined || v === null) return null;
  if (!isNonNegFinite(v)) throw badRequest(`${name} must be a number >= 0`);
  return v;
}

export interface StatusReport {
  status: (typeof JOB_REPORT_STATUSES)[number];
  instanceId: string;
  attempt: number;
  outputKey: string | null;
  outputDurationS: number | null;
  gpuSeconds: number | null;
  wallSeconds: number | null;
  error: string | null;
}

/** Validates the body of POST /internal/jobs/:id/status. Pure. */
export function parseStatusReport(raw: unknown, jobId: string): StatusReport {
  if (!isRecord(raw)) throw badRequest("body must be a JSON object");

  const status = raw.status;
  if (typeof status !== "string" || !(JOB_REPORT_STATUSES as readonly string[]).includes(status)) {
    throw badRequest("status must be running, succeeded, failed or retry");
  }
  const instanceId = raw.instance_id;
  if (typeof instanceId !== "string" || !WORKER_ID_RE.test(instanceId)) {
    throw badRequest("instance_id is required");
  }
  const attempt = raw.attempt === undefined || raw.attempt === null ? 0 : raw.attempt;
  if (!isSafeNonNegInt(attempt) || attempt > 100) throw badRequest("attempt must be a small non-negative integer");

  const gpuSeconds = optionalNonNegFinite(raw.gpu_seconds, "gpu_seconds");
  const wallSeconds = optionalNonNegFinite(raw.wall_seconds, "wall_seconds");

  let error: string | null = null;
  if (typeof raw.error === "string") error = raw.error.slice(0, ERROR_MAX_CHARS);
  else if (raw.error !== undefined && raw.error !== null) throw badRequest("error must be a string or null");

  if (status === "succeeded") {
    if (raw.output_key !== outputKeyFor(jobId)) {
      throw badRequest(`output_key must be ${outputKeyFor(jobId)}`);
    }
    const outputDuration = optionalNonNegFinite(raw.output_duration_s, "output_duration_s");
    if (outputDuration === null) throw badRequest("output_duration_s is required for succeeded");
    return {
      status: "succeeded",
      instanceId,
      attempt,
      outputKey: outputKeyFor(jobId),
      outputDurationS: outputDuration,
      gpuSeconds,
      wallSeconds,
      error: null,
    };
  }

  if (status === "retry") {
    return {
      status: "retry",
      instanceId,
      attempt,
      outputKey: null,
      outputDurationS: null,
      gpuSeconds,
      wallSeconds,
      error: error ?? DEFAULT_RETRY_ERROR,
    };
  }

  return {
    status: status as "running" | "failed",
    instanceId,
    attempt,
    outputKey: null,
    outputDurationS: null,
    gpuSeconds,
    wallSeconds,
    error: status === "failed" ? (error ?? DEFAULT_FAILURE_ERROR) : null,
  };
}

export type Decision = { ok: true; write: boolean } | { ok: false; reason: string };

/**
 * running = claim. Queued jobs are claimed. The current owner repeats harmlessly (no write).
 * Final jobs, unknown jobs and jobs held by another worker are refused.
 */
export function decideClaim(job: { status: JobStatus; worker_id: string | null } | null, workerId: string): Decision {
  if (job === null) return { ok: false, reason: "unknown job" };
  if (job.status === "succeeded" || job.status === "failed") return { ok: false, reason: `job already ${job.status}` };
  if (job.status === "running") {
    if (job.worker_id === workerId) return { ok: true, write: false };
    return { ok: false, reason: "job is claimed by another worker" };
  }
  return { ok: true, write: true };
}

/**
 * retry (v1.3): only the owner of a running job may release it. A repeat of the same release
 * (the job is queued with no owner and the same error) is answered 200 so the worker can ack safely.
 */
export function decideRetry(
  job: { status: JobStatus; worker_id: string | null; error: string | null } | null,
  workerId: string,
  error: string,
): Decision {
  if (job === null) return { ok: false, reason: "unknown job" };
  if (job.status === "succeeded" || job.status === "failed") return { ok: false, reason: `job already ${job.status}` };
  if (job.status === "queued") {
    if (job.worker_id === null && job.error === error) return { ok: true, write: false };
    return { ok: false, reason: "job is not running" };
  }
  if (job.worker_id !== workerId) return { ok: false, reason: "job is claimed by another worker" };
  return { ok: true, write: true };
}

type ClaimRow = Pick<JobRow, "status" | "worker_id" | "error">;

async function readClaimRow(env: Env, jobId: string): Promise<ClaimRow | null> {
  return env.DB.prepare("SELECT status, worker_id, error FROM jobs WHERE id = ?").bind(jobId).first<ClaimRow>();
}

async function handleClaim(env: Env, jobId: string, workerId: string): Promise<Response> {
  const decision = decideClaim(await readClaimRow(env, jobId), workerId);
  if (!decision.ok) return json({ ok: false, reason: decision.reason }, 409);
  if (!decision.write) return json({ ok: true });

  const now = new Date().toISOString();
  const res = await env.DB.prepare(
    `UPDATE jobs SET status = 'running', worker_id = ?, started_at = COALESCE(started_at, ?)
     WHERE id = ? AND status = 'queued'`,
  )
    .bind(workerId, now, jobId)
    .run();
  if (res.meta.changes === 1) return json({ ok: true });

  // Lost a race with another claim: decide again on the new state.
  const again = decideClaim(await readClaimRow(env, jobId), workerId);
  return again.ok ? json({ ok: true }) : json({ ok: false, reason: again.reason }, 409);
}

async function handleRetry(env: Env, jobId: string, workerId: string, error: string): Promise<Response> {
  const decision = decideRetry(await readClaimRow(env, jobId), workerId, error);
  if (!decision.ok) return json({ ok: false, reason: decision.reason }, 409);
  if (!decision.write) return json({ ok: true });

  const res = await env.DB.prepare(
    `UPDATE jobs SET status = 'queued', worker_id = NULL, started_at = NULL, error = ?, attempts = attempts + 1
     WHERE id = ? AND status = 'running' AND worker_id = ?`,
  )
    .bind(error, jobId, workerId)
    .run();
  if (res.meta.changes === 1) return json({ ok: true });

  const again = decideRetry(await readClaimRow(env, jobId), workerId, error);
  return again.ok ? json({ ok: true }) : json({ ok: false, reason: again.reason }, 409);
}

/** POST /internal/jobs/:id/status */
export async function handleJobStatus(request: Request, env: Env, jobId: string): Promise<Response> {
  requireSharedSecret(request, "X-Worker-Secret", env.WORKER_SECRET);
  const report = parseStatusReport(await readJson(request), jobId);

  if (report.status === "running") return handleClaim(env, jobId, report.instanceId);
  if (report.status === "retry") return handleRetry(env, jobId, report.instanceId, report.error ?? DEFAULT_RETRY_ERROR);

  const job = await env.DB.prepare("SELECT * FROM jobs WHERE id = ?").bind(jobId).first<JobRow>();
  if (!job) throw new HttpError(404, "not_found", "job not found");

  // Final states are terminal: late or duplicate reports are ignored.
  if (job.status === "succeeded" || job.status === "failed") {
    return json({ ok: true, ignored: true, status: job.status });
  }

  const now = new Date().toISOString();

  if (report.status === "succeeded") {
    if (report.outputDurationS === null || report.outputKey === null) {
      throw badRequest("output_duration_s and output_key are required for succeeded");
    }
    const { charged } = settleCents(
      job.reserved_cents,
      report.outputDurationS,
      loadPricingConfig(env).pricePerSecond,
    );
    const done = await finalizeJob(env, job, {
      status: "succeeded",
      charged,
      outputKey: report.outputKey,
      error: null,
      gpuSeconds: report.gpuSeconds,
      wallSeconds: report.wallSeconds,
      attempts: report.attempt,
      now,
    });
    return json({ ok: true, status: done ? "succeeded" : "ignored", charged_cents: done ? charged : job.charged_cents });
  }

  const done = await finalizeJob(env, job, {
    status: "failed",
    charged: 0,
    outputKey: null,
    error: report.error,
    gpuSeconds: report.gpuSeconds,
    wallSeconds: report.wallSeconds,
    attempts: report.attempt,
    now,
  });
  return json({ ok: true, status: done ? "failed" : "ignored" });
}

export interface HeartbeatReport {
  instanceId: string;
  provider: string;
  state: WorkerState;
  idleSeconds: number;
  jobsDone: number;
}

/** Validates the body of POST /internal/heartbeat. Pure. */
export function parseHeartbeat(raw: unknown): HeartbeatReport {
  if (!isRecord(raw)) throw badRequest("body must be a JSON object");
  const instanceId = raw.instance_id;
  if (typeof instanceId !== "string" || !WORKER_ID_RE.test(instanceId)) throw badRequest("instance_id is required");
  const provider = raw.provider;
  if (typeof provider !== "string" || !PROVIDER_RE.test(provider) || !isProviderName(provider)) {
    throw badRequest("provider must be vast or salad");
  }
  const state = raw.state;
  if (typeof state !== "string" || !(WORKER_STATES as readonly string[]).includes(state)) {
    throw badRequest("state must be booting, idle or busy");
  }
  const idleSeconds = raw.idle_seconds ?? 0;
  if (!isSafeNonNegInt(idleSeconds)) throw badRequest("idle_seconds must be a non-negative integer");
  const jobsDone = raw.jobs_done ?? 0;
  if (!isSafeNonNegInt(jobsDone)) throw badRequest("jobs_done must be a non-negative integer");
  return { instanceId, provider, state: state as WorkerState, idleSeconds, jobsDone };
}

/**
 * POST /internal/heartbeat. Upserts by worker id. An unknown worker id creates a row with
 * provider_ref NULL. The upsert never overwrites provider or provider_ref (the autoscaler owns them).
 */
export async function handleHeartbeat(request: Request, env: Env): Promise<Response> {
  requireSharedSecret(request, "X-Worker-Secret", env.WORKER_SECRET);
  const hb = parseHeartbeat(await readJson(request));
  const now = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO workers (instance_id, provider, state, created_at, last_heartbeat_at, idle_seconds, jobs_done, provider_ref)
     VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
     ON CONFLICT(instance_id) DO UPDATE SET
       state = excluded.state,
       last_heartbeat_at = excluded.last_heartbeat_at,
       idle_seconds = excluded.idle_seconds,
       jobs_done = excluded.jobs_done`,
  )
    .bind(hb.instanceId, hb.provider, hb.state, now, now, hb.idleSeconds, hb.jobsDone)
    .run();
  return json({ ok: true });
}

export interface CreditsAddReport {
  userId: string;
  cents: number;
}

export function parseCreditsAdd(raw: unknown): CreditsAddReport {
  if (!isRecord(raw)) throw badRequest("body must be a JSON object");
  const userId = raw.user_id;
  if (typeof userId !== "string" || userId.length < 1 || userId.length > 128) throw badRequest("user_id is required");
  const cents = raw.cents;
  if (typeof cents !== "number" || !Number.isSafeInteger(cents) || cents < 1 || cents > 10_000_000) {
    throw badRequest("cents must be an integer from 1 to 10000000");
  }
  return { userId, cents };
}

/** POST /internal/credits/add (X-Admin-Secret). */
export async function handleCreditsAdd(request: Request, env: Env): Promise<Response> {
  requireSharedSecret(request, "X-Admin-Secret", env.ADMIN_SECRET);
  const { userId, cents } = parseCreditsAdd(await readJson(request));
  const res = await env.DB.prepare("UPDATE users SET balance_cents = balance_cents + ? WHERE id = ?")
    .bind(cents, userId)
    .run();
  if (res.meta.changes !== 1) throw new HttpError(404, "not_found", "user not found");
  const row = await env.DB.prepare("SELECT balance_cents FROM users WHERE id = ?")
    .bind(userId)
    .first<{ balance_cents: number }>();
  return json({ user_id: userId, balance_cents: row?.balance_cents ?? null });
}

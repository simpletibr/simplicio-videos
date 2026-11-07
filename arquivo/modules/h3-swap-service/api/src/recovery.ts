// Lost-worker recovery and stale-claim sweep (CONTRACT 9b, addendum: stale claims).
// The pure decisions are first; the D1 and queue effects follow.

import { finalizeJob } from "./jobs";
import type { Env, JobMessage, JobStatus } from "./types";

/** A claim this young is never stale (the claim may still be on its way to the worker). */
export const CLAIM_GRACE_S = 60;

export interface RecoveryJob {
  id: string;
  status: JobStatus;
  worker_id: string | null;
  attempts: number;
}

export interface RecoveryDecision {
  requeue: string[];
  fail: string[];
}

/**
 * attempts counts the runs already consumed. A run that is lost consumes one more, so the job is
 * requeued while attempts + 1 < MAX_ATTEMPTS and failed (full refund) otherwise.
 */
export function decideJob(attempts: number, maxAttempts: number): "requeue" | "fail" {
  return attempts + 1 < maxAttempts ? "requeue" : "fail";
}

/** Running jobs of one lost worker, split into requeue and fail. Pure. */
export function decideRecovery(workerId: string, jobs: readonly RecoveryJob[], maxAttempts: number): RecoveryDecision {
  const requeue: string[] = [];
  const fail: string[] = [];
  for (const j of jobs) {
    if (j.status !== "running" || j.worker_id !== workerId) continue;
    (decideJob(j.attempts, maxAttempts) === "requeue" ? requeue : fail).push(j.id);
  }
  return { requeue, fail };
}

export interface StaleJob {
  id: string;
  status: JobStatus;
  worker_id: string | null;
  /** Start of the current claim (started_at), or null. */
  started_at_ms: number | null;
}

export interface StaleWorker {
  instance_id: string;
  state: "booting" | "idle" | "busy";
  idle_seconds: number;
}

export interface StaleConfig {
  staleClaimS: number; // STALE_CLAIM_S
  claimGraceS: number; // CLAIM_GRACE_S
}

/**
 * Job ids whose claim is stale: running, owned by a worker that is idle for at least STALE_CLAIM_S
 * (per its last heartbeat), or whose worker row no longer exists. A claim younger than the grace
 * period is never stale. Pure.
 */
export function findStaleClaims(
  jobs: readonly StaleJob[],
  workers: readonly StaleWorker[],
  now: number,
  cfg: StaleConfig,
): string[] {
  const byId = new Map(workers.map((w) => [w.instance_id, w] as const));
  const stale: string[] = [];
  for (const j of jobs) {
    if (j.status !== "running" || j.worker_id === null) continue;
    if (j.started_at_ms !== null && now - j.started_at_ms < cfg.claimGraceS * 1000) continue;
    const w = byId.get(j.worker_id);
    if (w === undefined) {
      stale.push(j.id);
    } else if (w.state === "idle" && w.idle_seconds >= cfg.staleClaimS) {
      stale.push(j.id);
    }
  }
  return stale;
}

export interface RecoveryRow {
  id: string;
  user_id: string;
  status: JobStatus;
  worker_id: string | null;
  attempts: number;
  reserved_cents: number;
  started_at: string | null;
  message: string | null;
}

export interface RecoveryResult {
  requeued: string[];
  failed: string[];
}

/** Returns the job to queued with a NEW queue message. False if the row had already moved on. */
async function requeueJob(env: Env, row: RecoveryRow): Promise<boolean> {
  if (row.message === null) throw new Error(`job ${row.id} has no stored queue message`);
  // Change the row first so no worker can claim it while the message is in flight.
  const moved = await env.DB.prepare(
    `UPDATE jobs SET status = 'queued', worker_id = NULL, started_at = NULL, attempts = attempts + 1
     WHERE id = ? AND status = 'running' AND worker_id IS ?`,
  )
    .bind(row.id, row.worker_id)
    .run();
  if (moved.meta.changes !== 1) return false;
  try {
    await env.JOBS_QUEUE.send(JSON.parse(row.message) as JobMessage, { contentType: "json" });
  } catch (err) {
    // Put the job back under its old owner so the next tick retries the whole step.
    await env.DB.prepare(
      `UPDATE jobs SET status = 'running', worker_id = ?, started_at = ?, attempts = attempts - 1
       WHERE id = ? AND status = 'queued' AND worker_id IS NULL`,
    )
      .bind(row.worker_id, row.started_at, row.id)
      .run();
    throw err;
  }
  return true;
}

async function applyDecision(
  env: Env,
  rows: ReadonlyMap<string, RecoveryRow>,
  decision: RecoveryDecision,
  reason: string,
): Promise<RecoveryResult> {
  const failed: string[] = [];
  const requeued: string[] = [];
  for (const id of decision.fail) {
    const row = rows.get(id);
    if (!row) continue;
    const changed = await finalizeJob(env, row, {
      status: "failed",
      charged: 0, // full refund
      outputKey: null,
      error: `${reason}; no attempts left`,
      gpuSeconds: null,
      wallSeconds: null,
      attempts: 0,
      now: new Date().toISOString(),
    });
    if (changed) failed.push(id);
  }
  for (const id of decision.requeue) {
    const row = rows.get(id);
    if (row && (await requeueJob(env, row))) requeued.push(id);
  }
  return { requeued, failed };
}

/** Lost worker: every job it still runs is requeued or failed. Safe to retry on the next tick. */
export async function recoverWorkerJobs(env: Env, workerId: string, maxAttempts: number): Promise<RecoveryResult> {
  const rs = await env.DB.prepare(
    `SELECT id, user_id, status, worker_id, attempts, reserved_cents, started_at, message
     FROM jobs WHERE worker_id = ? AND status = 'running'`,
  )
    .bind(workerId)
    .all<RecoveryRow>();
  const rows = new Map(rs.results.map((r) => [r.id, r] as const));
  const decision = decideRecovery(workerId, rs.results, maxAttempts);
  return applyDecision(env, rows, decision, `worker ${workerId} lost`);
}

/** Stale-claim sweep over all running jobs. */
export async function recoverStaleClaims(
  env: Env,
  now: number,
  cfg: { staleClaimS: number; maxAttempts: number },
  workers: readonly StaleWorker[],
): Promise<RecoveryResult> {
  const rs = await env.DB.prepare(
    `SELECT id, user_id, status, worker_id, attempts, reserved_cents, started_at, message
     FROM jobs WHERE status = 'running'`,
  ).all<RecoveryRow>();
  const rows = new Map(rs.results.map((r) => [r.id, r] as const));
  const stale = findStaleClaims(
    rs.results.map((r) => ({
      id: r.id,
      status: r.status,
      worker_id: r.worker_id,
      started_at_ms: r.started_at === null ? null : Date.parse(r.started_at),
    })),
    workers,
    now,
    { staleClaimS: cfg.staleClaimS, claimGraceS: CLAIM_GRACE_S },
  );
  const decision: RecoveryDecision = { requeue: [], fail: [] };
  for (const id of stale) {
    const row = rows.get(id);
    if (!row) continue;
    (decideJob(row.attempts, cfg.maxAttempts) === "requeue" ? decision.requeue : decision.fail).push(id);
  }
  return applyDecision(env, rows, decision, "stale claim");
}

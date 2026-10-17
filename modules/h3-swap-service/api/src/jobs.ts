// Job endpoints (CONTRACT section 9): create, status, download, and shared settlement.

import { authenticateUser } from "./auth";
import { loadPricingConfig } from "./config";
import { badRequest, HttpError, json } from "./http";
import { reserveCents } from "./pricing";
import type { Env, JobMessage, JobRow } from "./types";

export const FPS = 24 as const;
export const TIER = "768p" as const;
export const MAX_CHARACTERS = 3;
export const MAX_VIDEO_BYTES = 200 * 1024 * 1024;
export const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
export const MIN_DESCRIPTION_CHARS = 3;
export const MAX_DESCRIPTION_CHARS = 200;
export const MAX_PROMPT_EXTRA_CHARS = 500;

const VIDEO_TYPES = new Set(["video/mp4", "video/quicktime"]);
const IMAGE_EXT = new Map<string, string>([
  ["image/png", "png"],
  ["image/jpeg", "jpg"],
  ["image/webp", "webp"],
]);

export const sourceKeyFor = (jobId: string): string => `uploads/${jobId}/source.mp4`;
export const outputKeyFor = (jobId: string): string => `outputs/${jobId}/result.mp4`;

export interface ParsedMeta {
  durationS: number;
  characters: Array<{ replaceDescription: string }>;
  promptExtra: string | null;
  seed: number | null;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isSafeNonNegInt(v: unknown): v is number {
  return typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
}

/** Validates the `meta` JSON part of POST /v1/jobs. Pure. */
export function parseMeta(raw: unknown, maxDurationS: number): ParsedMeta {
  if (!isRecord(raw)) throw badRequest("meta must be a JSON object");

  const durationS = raw.duration_s;
  if (!isSafeNonNegInt(durationS) || durationS < 1 || durationS > maxDurationS) {
    throw badRequest(`duration_s must be an integer from 1 to ${maxDurationS}`);
  }

  const chars = raw.characters;
  if (!Array.isArray(chars) || chars.length < 1 || chars.length > MAX_CHARACTERS) {
    throw badRequest(`characters must be an array of 1 to ${MAX_CHARACTERS} items`);
  }
  const characters = chars.map((c, i) => {
    const rec = isRecord(c) ? c : {};
    const desc = typeof rec.replace_description === "string" ? rec.replace_description.trim() : "";
    const len = Array.from(desc).length;
    if (len < MIN_DESCRIPTION_CHARS || len > MAX_DESCRIPTION_CHARS) {
      throw badRequest(
        `characters[${i}].replace_description must be ${MIN_DESCRIPTION_CHARS} to ${MAX_DESCRIPTION_CHARS} characters`,
      );
    }
    return { replaceDescription: desc };
  });

  let promptExtra: string | null = null;
  if (raw.prompt_extra !== undefined && raw.prompt_extra !== null) {
    if (typeof raw.prompt_extra !== "string") throw badRequest("prompt_extra must be a string or null");
    const trimmed = raw.prompt_extra.trim();
    if (Array.from(trimmed).length > MAX_PROMPT_EXTRA_CHARS) {
      throw badRequest(`prompt_extra must be at most ${MAX_PROMPT_EXTRA_CHARS} characters`);
    }
    promptExtra = trimmed.length > 0 ? trimmed : null;
  }

  let seed: number | null = null;
  if (raw.seed !== undefined && raw.seed !== null) {
    if (!isSafeNonNegInt(raw.seed)) throw badRequest("seed must be a non-negative integer or null");
    seed = raw.seed;
  }

  return { durationS, characters, promptExtra, seed };
}

// Value type of FormData.get() in @cloudflare/workers-types.
type FormValue = File | string | null;

interface ValidFile {
  file: File;
  ext: string;
}

function requireVideo(value: FormValue, field: string): File {
  if (!(value instanceof File)) throw badRequest(`${field} file is required`);
  if (value.size === 0) throw badRequest(`${field} is empty`);
  if (value.size > MAX_VIDEO_BYTES) throw new HttpError(413, "file_too_large", `${field} exceeds 200 MB`);
  if (!VIDEO_TYPES.has(value.type)) {
    throw new HttpError(415, "unsupported_media_type", `${field} must be video/mp4 or video/quicktime`);
  }
  return value;
}

function requireImage(value: FormValue, field: string): ValidFile {
  if (!(value instanceof File)) throw badRequest(`${field} image is required`);
  if (value.size === 0) throw badRequest(`${field} is empty`);
  if (value.size > MAX_IMAGE_BYTES) throw new HttpError(413, "file_too_large", `${field} exceeds 15 MB`);
  const ext = IMAGE_EXT.get(value.type);
  if (!ext) throw new HttpError(415, "unsupported_media_type", `${field} must be image/png, image/jpeg or image/webp`);
  return { file: value, ext };
}

async function reserveCredits(env: Env, userId: string, cents: number): Promise<void> {
  const res = await env.DB.prepare("UPDATE users SET balance_cents = balance_cents - ? WHERE id = ? AND balance_cents >= ?")
    .bind(cents, userId, cents)
    .run();
  if (res.meta.changes !== 1) {
    throw new HttpError(402, "insufficient_credits", "not enough credits for this job");
  }
}

async function creditUser(env: Env, userId: string, cents: number): Promise<void> {
  if (cents <= 0) return;
  await env.DB.prepare("UPDATE users SET balance_cents = balance_cents + ? WHERE id = ?")
    .bind(cents, userId)
    .run();
}

/**
 * Moves a job to a final state and settles credits in one D1 batch (a transaction).
 * The refund runs only if the job row really transitioned to `status` at `now`.
 * Returns false when the job was already final (idempotent no-op).
 */
export async function finalizeJob(
  env: Env,
  job: Pick<JobRow, "id" | "user_id" | "reserved_cents">,
  fields: {
    status: "succeeded" | "failed";
    charged: number;
    outputKey: string | null;
    error: string | null;
    gpuSeconds: number | null;
    wallSeconds: number | null;
    attempts: number;
    now: string;
  },
): Promise<boolean> {
  const refund = job.reserved_cents - fields.charged;
  const [jobRes] = await env.DB.batch([
    env.DB.prepare(
      `UPDATE jobs SET status = ?, output_key = ?, charged_cents = ?, error = ?,
         gpu_seconds = ?, wall_seconds = ?, attempts = MAX(attempts, ?),
         started_at = COALESCE(started_at, ?), finished_at = ?
       WHERE id = ? AND status IN ('queued', 'running')`,
    ).bind(
      fields.status,
      fields.outputKey,
      fields.charged,
      fields.error,
      fields.gpuSeconds,
      fields.wallSeconds,
      fields.attempts,
      fields.now,
      fields.now,
      job.id,
    ),
    env.DB.prepare(
      `UPDATE users SET balance_cents = balance_cents + ?
       WHERE id = ? AND ? > 0
         AND EXISTS (SELECT 1 FROM jobs WHERE id = ? AND status = ? AND finished_at = ?)`,
    ).bind(refund, job.user_id, refund, job.id, fields.status, fields.now),
  ]);
  return jobRes !== undefined && jobRes.meta.changes === 1;
}

function publicJob(row: JobRow): Record<string, unknown> {
  return {
    id: row.id,
    status: row.status,
    duration_s: row.duration_s,
    reserved_cents: row.reserved_cents,
    charged_cents: row.charged_cents,
    attempts: row.attempts,
    error: row.error,
    created_at: row.created_at,
    started_at: row.started_at,
    finished_at: row.finished_at,
    download_available: row.status === "succeeded",
  };
}

/** POST /v1/jobs */
export async function createJob(request: Request, env: Env): Promise<Response> {
  const userId = await authenticateUser(request, env);
  const cfg = loadPricingConfig(env);

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    throw badRequest("body must be multipart/form-data");
  }

  const metaField = form.get("meta");
  if (typeof metaField !== "string") throw badRequest("meta field (JSON) is required");
  let metaRaw: unknown;
  try {
    metaRaw = JSON.parse(metaField);
  } catch {
    throw badRequest("meta must be valid JSON");
  }
  const meta = parseMeta(metaRaw, cfg.maxDurationS);

  for (let i = meta.characters.length + 1; i <= MAX_CHARACTERS; i++) {
    if (form.has(`char${i}`)) throw badRequest(`char${i} sent but only ${meta.characters.length} characters declared`);
  }

  const jobId = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  const sourceKey = sourceKeyFor(jobId);
  const source = requireVideo(form.get("source"), "source");
  const slots = meta.characters.map((c, i) => {
    const field = `char${i + 1}`;
    const img = requireImage(form.get(field), field);
    return {
      key: `uploads/${jobId}/char${i + 1}.${img.ext}`,
      file: img.file,
      description: c.replaceDescription,
    };
  });

  // Built before the insert and stored on the row, so a lost worker's job can be requeued later.
  const message: JobMessage = {
    job_id: jobId,
    user_id: userId,
    created_at: createdAt,
    tier: TIER,
    duration_s: meta.durationS,
    fps: FPS,
    source_key: sourceKey,
    characters: slots.map((s) => ({ image_key: s.key, replace_description: s.description })),
    prompt_extra: meta.promptExtra,
    seed: meta.seed,
  };

  const reserved = reserveCents(meta.durationS, cfg.pricePerSecond);
  await reserveCredits(env, userId, reserved);

  const uploaded: string[] = [];
  try {
    await env.BUCKET.put(sourceKey, source, { httpMetadata: { contentType: source.type } });
    uploaded.push(sourceKey);
    for (const slot of slots) {
      await env.BUCKET.put(slot.key, slot.file, { httpMetadata: { contentType: slot.file.type } });
      uploaded.push(slot.key);
    }
  } catch (err) {
    console.error("upload failed", { jobId, err: String(err) });
    await cleanupObjects(env, uploaded);
    await creditUser(env, userId, reserved).catch((e) => console.error("REFUND FAILED", { jobId, reserved, e: String(e) }));
    throw new HttpError(500, "upload_failed", "could not store uploads");
  }

  try {
    await env.DB.prepare(
      `INSERT INTO jobs (id, user_id, status, duration_s, reserved_cents, charged_cents, source_key,
         output_key, error, attempts, gpu_seconds, wall_seconds, created_at, started_at, finished_at,
         worker_id, message)
       VALUES (?, ?, 'queued', ?, ?, 0, ?, NULL, NULL, 0, NULL, NULL, ?, NULL, NULL, NULL, ?)`,
    )
      .bind(jobId, userId, meta.durationS, reserved, sourceKey, createdAt, JSON.stringify(message))
      .run();
  } catch (err) {
    console.error("job insert failed", { jobId, err: String(err) });
    await cleanupObjects(env, uploaded);
    await creditUser(env, userId, reserved).catch((e) => console.error("REFUND FAILED", { jobId, reserved, e: String(e) }));
    throw new HttpError(500, "db_error", "could not create job");
  }

  try {
    await env.JOBS_QUEUE.send(message, { contentType: "json" });
  } catch (err) {
    console.error("enqueue failed", { jobId, err: String(err) });
    await finalizeJob(
      env,
      { id: jobId, user_id: userId, reserved_cents: reserved },
      {
        status: "failed",
        charged: 0,
        outputKey: null,
        error: "enqueue failed",
        gpuSeconds: null,
        wallSeconds: null,
        attempts: 0,
        now: new Date().toISOString(),
      },
    ).catch((e) => console.error("FINALIZE FAILED", { jobId, e: String(e) }));
    await cleanupObjects(env, uploaded);
    return json({ job_id: jobId, status: "failed", error: "enqueue failed" }, 503);
  }

  return json({ job_id: jobId, status: "queued", reserved_cents: reserved }, 201);
}

async function cleanupObjects(env: Env, keys: string[]): Promise<void> {
  if (keys.length === 0) return;
  await env.BUCKET.delete(keys).catch((e) => console.error("R2 cleanup failed", { keys, e: String(e) }));
}

/** GET /v1/jobs/:id (owner only) */
export async function getJob(request: Request, env: Env, jobId: string): Promise<Response> {
  const userId = await authenticateUser(request, env);
  const row = await env.DB.prepare("SELECT * FROM jobs WHERE id = ? AND user_id = ?")
    .bind(jobId, userId)
    .first<JobRow>();
  if (!row) throw new HttpError(404, "not_found", "job not found");
  return json(publicJob(row));
}

/** GET /v1/jobs/:id/download (owner only, streams result.mp4) */
export async function downloadJob(request: Request, env: Env, jobId: string): Promise<Response> {
  const userId = await authenticateUser(request, env);
  const row = await env.DB.prepare("SELECT id, status, output_key FROM jobs WHERE id = ? AND user_id = ?")
    .bind(jobId, userId)
    .first<Pick<JobRow, "id" | "status" | "output_key">>();
  if (!row) throw new HttpError(404, "not_found", "job not found");
  if (row.status !== "succeeded" || !row.output_key) {
    return json({ error: "not_ready", message: "job has no output yet", status: row.status }, 409);
  }
  const obj = await env.BUCKET.get(row.output_key);
  if (!obj) throw new HttpError(404, "not_found", "output file missing");
  return new Response(obj.body, {
    status: 200,
    headers: {
      "content-type": "video/mp4",
      "content-length": String(obj.size),
      "content-disposition": `attachment; filename="h3-swap-${jobId}.mp4"`,
      "cache-control": "private, no-store",
    },
  });
}

// API-key auth (Bearer, stored as SHA-256 hex) and constant-time shared-secret checks.

import { HttpError, json } from "./http";
import type { Env } from "./types";

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  let out = "";
  for (const b of new Uint8Array(digest)) out += b.toString(16).padStart(2, "0");
  return out;
}

/** Compares without early exit on mismatch or length difference. */
export function timingSafeEqualString(a: string, b: string): boolean {
  const x = new TextEncoder().encode(a);
  const y = new TextEncoder().encode(b);
  const n = Math.max(x.length, y.length);
  let diff = x.length ^ y.length;
  for (let i = 0; i < n; i++) {
    diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  }
  return diff === 0;
}

export function extractBearer(request: Request): string | null {
  const header = request.headers.get("Authorization");
  if (!header) return null;
  const match = /^Bearer\s+(\S+)\s*$/i.exec(header);
  return match?.[1] ?? null;
}

/** Returns the user id for a valid API key, otherwise throws 401. */
export async function authenticateUser(request: Request, env: Env): Promise<string> {
  const key = extractBearer(request);
  if (!key) throw new HttpError(401, "unauthorized", "missing Bearer API key");
  const keyHash = await sha256Hex(key);
  const row = await env.DB.prepare("SELECT user_id FROM api_keys WHERE key_hash = ?")
    .bind(keyHash)
    .first<{ user_id: string }>();
  if (!row) throw new HttpError(401, "unauthorized", "invalid API key");
  return row.user_id;
}

/** Fails closed: an unset secret is a server error, a wrong value is 401. */
export function requireSharedSecret(
  request: Request,
  headerName: "X-Worker-Secret" | "X-Admin-Secret",
  expected: string | undefined,
): void {
  if (!expected) {
    console.error(`secret for ${headerName} is not configured`);
    throw new HttpError(500, "misconfigured", "server is misconfigured");
  }
  const provided = request.headers.get(headerName) ?? "";
  if (!timingSafeEqualString(provided, expected)) {
    throw new HttpError(401, "unauthorized", "bad shared secret");
  }
}

/** GET /v1/me */
export async function getMe(request: Request, env: Env): Promise<Response> {
  const userId = await authenticateUser(request, env);
  const row = await env.DB.prepare("SELECT id, balance_cents FROM users WHERE id = ?")
    .bind(userId)
    .first<{ id: string; balance_cents: number }>();
  if (!row) throw new HttpError(404, "not_found", "user not found");
  return json({ id: row.id, balance_cents: row.balance_cents });
}

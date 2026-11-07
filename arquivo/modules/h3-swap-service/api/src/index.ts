// Worker entry: hand-written router (no framework) plus the cron autoscaler.
// There is deliberately no `queue` handler: the job queue uses an HTTP pull consumer.

import { getMe } from "./auth";
import { runAutoscaler } from "./autoscaler";
import { errorResponse, HttpError, json } from "./http";
import { handleCreditsAdd, handleHeartbeat, handleJobStatus } from "./internal";
import { createJob, downloadJob, getJob } from "./jobs";
import type { Env } from "./types";

const ID = "([A-Za-z0-9-]{1,64})";

interface Route {
  method: "GET" | "POST";
  pattern: RegExp;
  handler: (request: Request, env: Env, match: RegExpExecArray) => Promise<Response>;
}

const routes: Route[] = [
  { method: "POST", pattern: /^\/v1\/jobs$/, handler: (req, env) => createJob(req, env) },
  {
    method: "GET",
    pattern: new RegExp(`^/v1/jobs/${ID}$`),
    handler: (req, env, m) => getJob(req, env, m[1] ?? ""),
  },
  {
    method: "GET",
    pattern: new RegExp(`^/v1/jobs/${ID}/download$`),
    handler: (req, env, m) => downloadJob(req, env, m[1] ?? ""),
  },
  { method: "GET", pattern: /^\/v1\/me$/, handler: (req, env) => getMe(req, env) },
  {
    method: "POST",
    pattern: new RegExp(`^/internal/jobs/${ID}/status$`),
    handler: (req, env, m) => handleJobStatus(req, env, m[1] ?? ""),
  },
  { method: "POST", pattern: /^\/internal\/heartbeat$/, handler: (req, env) => handleHeartbeat(req, env) },
  { method: "POST", pattern: /^\/internal\/credits\/add$/, handler: (req, env) => handleCreditsAdd(req, env) },
];

async function route(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "") || "/";
  const allowed = new Set<string>();

  for (const r of routes) {
    const match = r.pattern.exec(path);
    if (!match) continue;
    if (r.method === request.method) return r.handler(request, env, match);
    allowed.add(r.method);
  }

  if (allowed.size > 0) {
    return json({ error: "method_not_allowed" }, 405, { Allow: [...allowed].join(", ") });
  }
  return json({ error: "not_found" }, 404);
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    try {
      return await route(request, env);
    } catch (err) {
      if (err instanceof HttpError) return errorResponse(err);
      console.error("unhandled error", String(err));
      return json({ error: "internal_error" }, 500);
    }
  },

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runAutoscaler(env));
  },
} satisfies ExportedHandler<Env>;

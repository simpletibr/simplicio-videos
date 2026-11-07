import { describe, expect, it } from "vitest";
import worker from "./index";
import type { Env } from "./types";

// Stub env: these paths reject before any D1, R2 or queue access.
const env = {
  WORKER_SECRET: "worker-secret-value",
  ADMIN_SECRET: "admin-secret-value",
} as unknown as Env;
const ctx = { waitUntil: () => {}, passThroughOnException: () => {} } as unknown as ExecutionContext;

function call(method: string, path: string, init: { headers?: Record<string, string>; body?: string } = {}) {
  return worker.fetch(new Request(`https://api.test${path}`, { method, ...init }), env, ctx);
}

describe("router", () => {
  it("returns 404 for unknown paths", async () => {
    const res = await call("GET", "/nope");
    expect(res.status).toBe(404);
  });

  it("returns 405 with Allow when the path exists under another method", async () => {
    const res = await call("GET", "/v1/jobs");
    expect(res.status).toBe(405);
    expect(res.headers.get("Allow")).toBe("POST");
  });

  it("returns 401 for a missing or wrong worker secret before reading the body", async () => {
    expect((await call("POST", "/internal/heartbeat", { body: "{}" })).status).toBe(401);
    const wrong = await call("POST", "/internal/heartbeat", {
      headers: { "X-Worker-Secret": "nope" },
      body: "{}",
    });
    expect(wrong.status).toBe(401);
  });

  it("returns 400 for invalid JSON from an authorized worker", async () => {
    const res = await call("POST", "/internal/heartbeat", {
      headers: { "X-Worker-Secret": "worker-secret-value" },
      body: "not json",
    });
    expect(res.status).toBe(400);
    expect(((await res.json()) as { error: string }).error).toBe("invalid_json");
  });

  it("rejects a status report for a job with a bad output key before touching the DB", async () => {
    const res = await call("POST", "/internal/jobs/abc-123/status", {
      headers: { "X-Worker-Secret": "worker-secret-value" },
      body: JSON.stringify({ status: "succeeded", instance_id: "1", output_key: "outputs/x/result.mp4", output_duration_s: 3 }),
    });
    expect(res.status).toBe(400);
  });

  it("guards credits/add with the admin secret", async () => {
    const res = await call("POST", "/internal/credits/add", {
      headers: { "X-Admin-Secret": "worker-secret-value" },
      body: JSON.stringify({ user_id: "u", cents: 100 }),
    });
    expect(res.status).toBe(401);
  });

  it("fails closed with 500 when a secret is not configured", async () => {
    const bare = { WORKER_SECRET: "", ADMIN_SECRET: "" } as unknown as Env;
    const res = await worker.fetch(
      new Request("https://api.test/internal/credits/add", {
        method: "POST",
        headers: { "X-Admin-Secret": "" },
        body: "{}",
      }),
      bare,
      ctx,
    );
    expect(res.status).toBe(500);
  });
});

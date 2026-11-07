// Test helpers only: a recording fetch mock and env stubs. Not used by the Worker.

import { vi } from "vitest";
import type { Env } from "./types";

export interface RecordedCall {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

/** Replaces global fetch. Every call is recorded; the handler returns the response. */
export function mockFetch(handler: (call: RecordedCall) => Response): RecordedCall[] {
  const calls: RecordedCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = { ...((init?.headers ?? {}) as Record<string, string>) };
      let body: unknown = undefined;
      if (typeof init?.body === "string") {
        try {
          body = JSON.parse(init.body);
        } catch {
          body = init.body;
        }
      }
      const call: RecordedCall = { url: String(input), method: init?.method ?? "GET", headers, body };
      calls.push(call);
      return handler(call);
    }),
  );
  return calls;
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const SHARED = {
  WORKER_SECRET: "wsecret",
  API_BASE_URL: "https://api.test",
  CF_ACCOUNT_ID: "acct",
  CF_QUEUE_ID: "queue",
  CF_API_TOKEN: "cftok",
  R2_ENDPOINT: "https://r2.test",
  R2_ACCESS_KEY_ID: "akid",
  R2_SECRET_ACCESS_KEY: "rsec",
  R2_BUCKET: "h3-swap",
};

export function vastEnv(over: Record<string, string> = {}): Env {
  return {
    ...SHARED,
    VAST_API_KEY: "vast-key",
    VAST_IMAGE: "ghcr.io/x/h3:runtime",
    VAST_DISK_GB: "150",
    MAX_DPH: "1.0",
    VAST_OFFER_FILTER_JSON: "{}",
    ...over,
  } as unknown as Env;
}

export function saladEnv(over: Record<string, string | undefined> = {}): Env {
  const base: Record<string, string | undefined> = {
    ...SHARED,
    SALAD_API_KEY: "salad-key",
    SALAD_ORG: "org1",
    SALAD_PROJECT: "proj1",
    SALAD_GPU_CLASS_NAME: "RTX 5090",
    SALAD_CPU: "8",
    SALAD_MEMORY_MB: "65536",
    SALAD_IMAGE: "",
    VAST_IMAGE: "ghcr.io/x/h3:runtime",
    ...over,
  };
  return base as unknown as Env;
}

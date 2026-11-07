import { describe, expect, it } from "vitest";
import { decideClaim, decideRetry } from "./internal";

describe("decideClaim (running = claim)", () => {
  it("rejects an unknown job", () => {
    expect(decideClaim(null, "w-1")).toEqual({ ok: false, reason: "unknown job" });
  });

  it("claims a queued job", () => {
    expect(decideClaim({ status: "queued", worker_id: null }, "w-1")).toEqual({ ok: true, write: true });
  });

  it("is idempotent for the worker that already holds the claim", () => {
    expect(decideClaim({ status: "running", worker_id: "w-1" }, "w-1")).toEqual({ ok: true, write: false });
  });

  it("rejects a running job held by another worker", () => {
    const d = decideClaim({ status: "running", worker_id: "w-2" }, "w-1");
    expect(d.ok).toBe(false);
    if (!d.ok) expect(d.reason).toContain("another worker");
  });

  it("always rejects a final job", () => {
    for (const status of ["succeeded", "failed"] as const) {
      const d = decideClaim({ status, worker_id: "w-1" }, "w-1");
      expect(d.ok).toBe(false);
      if (!d.ok) expect(d.reason).toBe(`job already ${status}`);
    }
  });
});

describe("decideRetry (v1.3 release on retry)", () => {
  it("accepts a retry from the owner of the claim and asks for a write", () => {
    expect(decideRetry({ status: "running", worker_id: "w-1", error: null }, "w-1", "boom")).toEqual({
      ok: true,
      write: true,
    });
  });

  it("rejects a retry from any other worker", () => {
    const d = decideRetry({ status: "running", worker_id: "w-2", error: null }, "w-1", "boom");
    expect(d.ok).toBe(false);
    if (!d.ok) expect(d.reason).toContain("another worker");
  });

  it("is idempotent when the same retry is repeated after it already released the job", () => {
    const released = { status: "queued" as const, worker_id: null, error: "boom" };
    expect(decideRetry(released, "w-1", "boom")).toEqual({ ok: true, write: false });
  });

  it("rejects a retry on a queued job whose release was for a different error", () => {
    const d = decideRetry({ status: "queued", worker_id: null, error: "other" }, "w-1", "boom");
    expect(d.ok).toBe(false);
  });

  it("rejects a retry on a final job or an unknown job", () => {
    expect(decideRetry({ status: "succeeded", worker_id: "w-1", error: null }, "w-1", "boom").ok).toBe(false);
    expect(decideRetry({ status: "failed", worker_id: "w-1", error: null }, "w-1", "boom").ok).toBe(false);
    expect(decideRetry(null, "w-1", "boom")).toEqual({ ok: false, reason: "unknown job" });
  });
});

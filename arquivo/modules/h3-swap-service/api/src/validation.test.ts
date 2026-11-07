import { describe, expect, it } from "vitest";
import { parseMeta } from "./jobs";
import { parseCreditsAdd, parseHeartbeat, parseStatusReport } from "./internal";

const JOB = "11111111-2222-4333-8444-555555555555";
const OUT = `outputs/${JOB}/result.mp4`;

function meta(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    duration_s: 10,
    characters: [{ replace_description: "o homem de boné, à esquerda" }],
    ...over,
  };
}

describe("parseMeta", () => {
  it("accepts a valid meta and trims text", () => {
    const m = parseMeta(
      meta({
        characters: [{ replace_description: "  a mulher de vestido  " }, { replace_description: "o cão" }],
        prompt_extra: "  luz de fim de tarde  ",
        seed: 42,
      }),
      30,
    );
    expect(m.durationS).toBe(10);
    expect(m.characters.map((c) => c.replaceDescription)).toEqual(["a mulher de vestido", "o cão"]);
    expect(m.promptExtra).toBe("luz de fim de tarde");
    expect(m.seed).toBe(42);
  });

  it("maps empty prompt_extra and absent seed to null", () => {
    const m = parseMeta(meta({ prompt_extra: "   ", seed: null }), 30);
    expect(m.promptExtra).toBeNull();
    expect(m.seed).toBeNull();
  });

  it("enforces duration 1..MAX_DURATION_S as an integer", () => {
    expect(() => parseMeta(meta({ duration_s: 0 }), 30)).toThrow();
    expect(() => parseMeta(meta({ duration_s: 31 }), 30)).toThrow();
    expect(() => parseMeta(meta({ duration_s: 1.5 }), 30)).toThrow();
    expect(() => parseMeta(meta({ duration_s: "10" }), 30)).toThrow();
    expect(parseMeta(meta({ duration_s: 30 }), 30).durationS).toBe(30);
  });

  it("requires 1 to 3 characters", () => {
    expect(() => parseMeta(meta({ characters: [] }), 30)).toThrow();
    const four = Array.from({ length: 4 }, () => ({ replace_description: "pessoa do meio" }));
    expect(() => parseMeta(meta({ characters: four }), 30)).toThrow();
  });

  it("enforces replace_description length 3..200 after trimming", () => {
    expect(() => parseMeta(meta({ characters: [{ replace_description: "  ab  " }] }), 30)).toThrow();
    expect(() => parseMeta(meta({ characters: [{ replace_description: "x".repeat(201) }] }), 30)).toThrow();
    expect(parseMeta(meta({ characters: [{ replace_description: "x".repeat(200) }] }), 30).characters).toHaveLength(1);
  });

  it("rejects a non-string prompt_extra and invalid seeds", () => {
    expect(() => parseMeta(meta({ prompt_extra: 5 }), 30)).toThrow();
    expect(() => parseMeta(meta({ seed: -1 }), 30)).toThrow();
    expect(() => parseMeta(meta({ seed: 1.5 }), 30)).toThrow();
  });
});

describe("parseStatusReport", () => {
  it("accepts a succeeded report with the contract output key", () => {
    const r = parseStatusReport(
      {
        status: "succeeded",
        instance_id: "123",
        attempt: 1,
        output_key: OUT,
        output_duration_s: 9.83,
        width: 768,
        height: 1382,
        gpu_seconds: 512.4,
        wall_seconds: 540.1,
        error: null,
      },
      JOB,
    );
    expect(r.status).toBe("succeeded");
    expect(r.outputDurationS).toBe(9.83);
    expect(r.outputKey).toBe(OUT);
  });

  it("refuses a succeeded report pointing at another job's output", () => {
    expect(() =>
      parseStatusReport(
        { status: "succeeded", instance_id: "1", output_key: "outputs/other/result.mp4", output_duration_s: 5 },
        JOB,
      ),
    ).toThrow();
  });

  it("requires output_duration_s for succeeded", () => {
    expect(() => parseStatusReport({ status: "succeeded", instance_id: "1", output_key: OUT }, JOB)).toThrow();
  });

  it("defaults the failure message and rejects unknown statuses or missing instance ids", () => {
    const r = parseStatusReport({ status: "failed", instance_id: "7" }, JOB);
    expect(r.error).toBe("worker reported failure");
    expect(() => parseStatusReport({ status: "done", instance_id: "7" }, JOB)).toThrow();
    expect(() => parseStatusReport({ status: "running" }, JOB)).toThrow();
  });
});

describe("retry status (v1.3) and provider names", () => {
  it("parses a retry from the owner with its error", () => {
    const r = parseStatusReport({ status: "retry", instance_id: "w-123e4567e89b", error: "CUDA out of memory" }, JOB);
    expect(r.status).toBe("retry");
    expect(r.instanceId).toBe("w-123e4567e89b");
    expect(r.error).toBe("CUDA out of memory");
    expect(r.outputKey).toBeNull();
  });

  it("uses a default error for a retry without one", () => {
    expect(parseStatusReport({ status: "retry", instance_id: "w-1" }, JOB).error).toBe("worker requested retry");
  });

  it("requires instance_id for a retry", () => {
    expect(() => parseStatusReport({ status: "retry" }, JOB)).toThrow();
  });

  it("accepts salad and rejects an unknown heartbeat provider", () => {
    expect(parseHeartbeat({ instance_id: "w-1", provider: "salad", state: "idle" }).provider).toBe("salad");
    expect(() => parseHeartbeat({ instance_id: "w-1", provider: "local", state: "idle" })).toThrow();
  });
});

describe("parseHeartbeat and parseCreditsAdd", () => {
  it("accepts the worker id format the autoscaler generates", () => {
    const hb = parseHeartbeat({ instance_id: "w-123e4567e89b", provider: "vast", state: "booting" });
    expect(hb.instanceId).toBe("w-123e4567e89b");
  });

  it("accepts a valid heartbeat and rejects an unknown state", () => {
    const hb = parseHeartbeat({ instance_id: "123", provider: "vast", state: "idle", idle_seconds: 30, jobs_done: 2 });
    expect(hb.state).toBe("idle");
    expect(() => parseHeartbeat({ instance_id: "123", provider: "vast", state: "sleeping" })).toThrow();
  });

  it("accepts positive integer top-ups only", () => {
    expect(parseCreditsAdd({ user_id: "u1", cents: 1000 })).toEqual({ userId: "u1", cents: 1000 });
    expect(() => parseCreditsAdd({ user_id: "u1", cents: 0 })).toThrow();
    expect(() => parseCreditsAdd({ user_id: "u1", cents: 10.5 })).toThrow();
    expect(() => parseCreditsAdd({ cents: 10 })).toThrow();
  });
});

import { describe, expect, it } from "vitest";
import {
  decideScaling,
  desiredWorkers,
  pickProvider,
  planScaling,
  type ScalingConfig,
  type WorkerView,
} from "./scaling";

const S = 1000; // ms per second
const NOW = 1_800_000_000_000;

// Defaults from wrangler.toml [vars].
const CFG: ScalingConfig = {
  maxWorkers: 2,
  jobsPerWorker: 4,
  idleDestroyS: 900,
  heartbeatLostS: 1200,
  bootGraceS: 3600,
  bootFailS: 1500,
};
const ORDER = ["vast", "salad"];
const NO_COOLDOWN = new Map<string, number>();

function worker(over: Partial<WorkerView> & { instance_id: string }): WorkerView {
  return {
    provider: "vast",
    provider_ref: "1000",
    state: "idle",
    created_at_ms: NOW - 7200 * S, // old, past boot grace
    last_heartbeat_ms: NOW - 10 * S, // fresh
    idle_seconds: 0,
    ...over,
  };
}

function salad(over: Partial<WorkerView> & { instance_id: string }): WorkerView {
  return worker({ provider: "salad", provider_ref: `h3-swap-${over.instance_id}`, ...over });
}

describe("desiredWorkers", () => {
  it("is zero with no backlog", () => {
    expect(desiredWorkers(0, CFG)).toBe(0);
  });

  it("is ceil(backlog / JOBS_PER_WORKER)", () => {
    expect(desiredWorkers(1, CFG)).toBe(1);
    expect(desiredWorkers(4, CFG)).toBe(1);
    expect(desiredWorkers(5, CFG)).toBe(2);
  });

  it("is capped at MAX_WORKERS", () => {
    expect(desiredWorkers(100, CFG)).toBe(2);
  });
});

describe("decideScaling", () => {
  it("does nothing with no backlog and no workers", () => {
    expect(decideScaling({ backlog: 0, workers: [], now: NOW, config: CFG })).toEqual({
      create: 0,
      destroy: [],
    });
  });

  it("creates workers for backlog, never above MAX_WORKERS", () => {
    expect(decideScaling({ backlog: 1, workers: [], now: NOW, config: CFG })).toEqual({ create: 1, destroy: [] });
    expect(decideScaling({ backlog: 9, workers: [], now: NOW, config: CFG })).toEqual({ create: 2, destroy: [] });
    expect(decideScaling({ backlog: 1000, workers: [], now: NOW, config: CFG })).toEqual({ create: 2, destroy: [] });
  });

  it("counts existing healthy workers against the desired count", () => {
    const busy = [worker({ instance_id: "a", state: "busy" })];
    expect(decideScaling({ backlog: 100, workers: busy, now: NOW, config: CFG })).toEqual({ create: 1, destroy: [] });

    const full = [worker({ instance_id: "a", state: "busy" }), worker({ instance_id: "b", state: "busy" })];
    expect(decideScaling({ backlog: 100, workers: full, now: NOW, config: CFG })).toEqual({ create: 0, destroy: [] });
  });

  it("counts MAX_WORKERS across providers, not per provider", () => {
    const mixed = [worker({ instance_id: "a", state: "busy" }), salad({ instance_id: "b", state: "busy" })];
    expect(decideScaling({ backlog: 100, workers: mixed, now: NOW, config: CFG })).toEqual({ create: 0, destroy: [] });

    const one = [worker({ instance_id: "a", state: "busy" })];
    expect(decideScaling({ backlog: 100, workers: one, now: NOW, config: CFG })).toEqual({ create: 1, destroy: [] });
  });

  it("counts never-heartbeated booting workers toward capacity", () => {
    const booting60 = [worker({ instance_id: "boot1", state: "booting", created_at_ms: NOW - 60 * S, last_heartbeat_ms: null })];
    expect(decideScaling({ backlog: 100, workers: booting60, now: NOW, config: CFG })).toEqual({ create: 1, destroy: [] });

    const two = [
      worker({ instance_id: "boot1", state: "booting", created_at_ms: NOW - 60 * S, last_heartbeat_ms: null }),
      worker({ instance_id: "boot2", state: "booting", created_at_ms: NOW - 30 * S, last_heartbeat_ms: null }),
    ];
    expect(decideScaling({ backlog: 100, workers: two, now: NOW, config: CFG })).toEqual({ create: 0, destroy: [] });
  });

  it("destroys a never-heartbeated booting worker exactly at BOOT_FAIL_S", () => {
    const at = (age: number) => [
      worker({ instance_id: "boot", state: "booting", created_at_ms: NOW - age * S, last_heartbeat_ms: null }),
    ];
    expect(decideScaling({ backlog: 100, workers: at(1499), now: NOW, config: CFG })).toEqual({ create: 1, destroy: [] });
    expect(decideScaling({ backlog: 100, workers: at(1500), now: NOW, config: CFG })).toEqual({
      create: 2,
      destroy: ["boot"],
    });
  });

  it("keeps a booting worker that heartbeated inside BOOT_GRACE_S, even past HEARTBEAT_LOST_S", () => {
    const grace = [
      worker({ instance_id: "slow", state: "booting", created_at_ms: NOW - 1800 * S, last_heartbeat_ms: NOW - 1300 * S }),
    ];
    expect(decideScaling({ backlog: 4, workers: grace, now: NOW, config: CFG })).toEqual({ create: 0, destroy: [] });
  });

  it("destroys a worker that heartbeats but never goes live within BOOT_GRACE_S", () => {
    const stuck = [
      worker({ instance_id: "stuck", state: "booting", created_at_ms: NOW - 3600 * S, last_heartbeat_ms: NOW - 10 * S }),
    ];
    expect(decideScaling({ backlog: 0, workers: stuck, now: NOW, config: CFG })).toEqual({
      create: 0,
      destroy: ["stuck"],
    });
  });

  it("destroys an idle worker only when backlog is 0 and idle >= IDLE_DESTROY_S", () => {
    const idleFor = (s: number) => [worker({ instance_id: "i1", idle_seconds: s })];

    expect(decideScaling({ backlog: 0, workers: idleFor(900), now: NOW, config: CFG })).toEqual({
      create: 0,
      destroy: ["i1"],
    });
    expect(decideScaling({ backlog: 0, workers: idleFor(899), now: NOW, config: CFG })).toEqual({
      create: 0,
      destroy: [],
    });
    // Backlog present: an idle worker over the threshold must be kept.
    expect(decideScaling({ backlog: 1, workers: idleFor(5000), now: NOW, config: CFG })).toEqual({
      create: 0,
      destroy: [],
    });

    const two = [worker({ instance_id: "x", idle_seconds: 1000 }), worker({ instance_id: "y", idle_seconds: 2000 })];
    expect(decideScaling({ backlog: 0, workers: two, now: NOW, config: CFG }).destroy).toEqual(["x", "y"]);
  });

  it("destroys a worker with a lost heartbeat and replaces it when backlog needs it", () => {
    const lost = [worker({ instance_id: "lost", state: "busy", last_heartbeat_ms: NOW - 1200 * S })];
    expect(decideScaling({ backlog: 4, workers: lost, now: NOW, config: CFG })).toEqual({
      create: 1,
      destroy: ["lost"],
    });

    const almostLost = [worker({ instance_id: "ok", state: "busy", last_heartbeat_ms: NOW - 1199 * S })];
    expect(decideScaling({ backlog: 4, workers: almostLost, now: NOW, config: CFG }).destroy).toEqual([]);
  });

  it("keys destroy decisions by worker id even when provider_ref is unknown", () => {
    const adopted = [
      worker({ instance_id: "w-orphan0000001", provider_ref: null, state: "busy", last_heartbeat_ms: NOW - 1300 * S }),
    ];
    expect(decideScaling({ backlog: 0, workers: adopted, now: NOW, config: CFG })).toEqual({
      create: 0,
      destroy: ["w-orphan0000001"],
    });
  });

  it("rejects an invalid config", () => {
    expect(() =>
      decideScaling({ backlog: 1, workers: [], now: NOW, config: { ...CFG, jobsPerWorker: 0 } }),
    ).toThrow(RangeError);
  });
});

describe("pickProvider", () => {
  it("returns the first provider in order that is not cooling down", () => {
    expect(pickProvider(ORDER, NO_COOLDOWN, NOW)).toBe("vast");
  });

  it("skips a provider in cooldown and returns the next one", () => {
    expect(pickProvider(ORDER, new Map([["vast", NOW + 60 * S]]), NOW)).toBe("salad");
  });

  it("returns null when every provider is cooling down", () => {
    const both = new Map([
      ["vast", NOW + 60 * S],
      ["salad", NOW + 60 * S],
    ]);
    expect(pickProvider(ORDER, both, NOW)).toBeNull();
  });

  it("treats an expired cooldown as available", () => {
    expect(pickProvider(ORDER, new Map([["vast", NOW]]), NOW)).toBe("vast");
  });
});

describe("planScaling (provider fallback)", () => {
  it("sends a new worker to the second provider when the first is cooling down", () => {
    const plan = planScaling({
      backlog: 1,
      workers: [],
      now: NOW,
      config: CFG,
      providerOrder: ORDER,
      cooldownUntilMs: new Map([["vast", NOW + 60 * S]]),
      providerCooldownS: 900,
    });
    expect(plan.provider).toBe("salad");
    expect(plan.create).toBe(1);
    expect(plan.destroy).toEqual([]);
  });

  it("creates nothing when every provider is cooling down, but still destroys", () => {
    const plan = planScaling({
      backlog: 100,
      workers: [worker({ instance_id: "lost", state: "busy", last_heartbeat_ms: NOW - 1300 * S })],
      now: NOW,
      config: CFG,
      providerOrder: ORDER,
      cooldownUntilMs: new Map([
        ["vast", NOW + 60 * S],
        ["salad", NOW + 60 * S],
      ]),
      providerCooldownS: 900,
    });
    expect(plan.provider).toBeNull();
    expect(plan.create).toBe(0);
    expect(plan.destroy).toEqual(["lost"]);
    expect(plan.bootFailedProviders).toEqual([]);
  });

  it("destroys a worker that never heartbeats after BOOT_FAIL_S and cools its provider down", () => {
    const plan = planScaling({
      backlog: 100,
      workers: [worker({ instance_id: "v-boot", state: "booting", created_at_ms: NOW - 1600 * S, last_heartbeat_ms: null })],
      now: NOW,
      config: CFG,
      providerOrder: ORDER,
      cooldownUntilMs: NO_COOLDOWN,
      providerCooldownS: 900,
    });
    expect(plan.destroy).toEqual(["v-boot"]);
    expect(plan.bootFailedProviders).toEqual(["vast"]);
    expect(plan.cooldownUntilMs.get("vast")).toBe(NOW + 900 * S);
    // The failed provider is not reused in the same tick.
    expect(plan.provider).toBe("salad");
    expect(plan.create).toBe(2);
  });

  it("a stuck booting worker also cools its provider down", () => {
    const plan = planScaling({
      backlog: 100,
      workers: [salad({ instance_id: "s-stuck", state: "booting", created_at_ms: NOW - 3600 * S, last_heartbeat_ms: NOW - 10 * S })],
      now: NOW,
      config: CFG,
      providerOrder: ORDER,
      cooldownUntilMs: NO_COOLDOWN,
      providerCooldownS: 900,
    });
    expect(plan.destroy).toEqual(["s-stuck"]);
    expect(plan.bootFailedProviders).toEqual(["salad"]);
    expect(plan.provider).toBe("vast");
    expect(plan.create).toBe(2);
  });

  it("a lost heartbeat does not cool its provider down", () => {
    const plan = planScaling({
      backlog: 4,
      workers: [worker({ instance_id: "lost", state: "busy", last_heartbeat_ms: NOW - 1300 * S })],
      now: NOW,
      config: CFG,
      providerOrder: ORDER,
      cooldownUntilMs: NO_COOLDOWN,
      providerCooldownS: 900,
    });
    expect(plan.destroy).toEqual(["lost"]);
    expect(plan.bootFailedProviders).toEqual([]);
    expect(plan.provider).toBe("vast");
  });

  it("MAX_WORKERS still counts workers on other providers when the first provider is cooling down", () => {
    const plan = planScaling({
      backlog: 100,
      workers: [worker({ instance_id: "a", state: "busy" })],
      now: NOW,
      config: CFG,
      providerOrder: ORDER,
      cooldownUntilMs: new Map([["vast", NOW + 60 * S]]),
      providerCooldownS: 900,
    });
    expect(plan.provider).toBe("salad");
    expect(plan.create).toBe(1);
  });
});

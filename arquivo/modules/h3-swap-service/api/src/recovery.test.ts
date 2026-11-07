import { describe, expect, it } from "vitest";
import {
  CLAIM_GRACE_S,
  decideJob,
  decideRecovery,
  findStaleClaims,
  type RecoveryJob,
  type StaleJob,
  type StaleWorker,
} from "./recovery";

const NOW = 1_800_000_000_000;

const jobs: RecoveryJob[] = [
  { id: "j1", status: "running", worker_id: "w-lost", attempts: 0 },
  { id: "j2", status: "running", worker_id: "w-lost", attempts: 1 },
  { id: "j3", status: "running", worker_id: "w-lost", attempts: 2 },
  { id: "j4", status: "running", worker_id: "w-other", attempts: 0 },
  { id: "j5", status: "queued", worker_id: null, attempts: 0 },
  { id: "j6", status: "succeeded", worker_id: "w-lost", attempts: 1 },
];

describe("decideJob", () => {
  it("requeues while another attempt is allowed, counting the lost run", () => {
    expect(decideJob(0, 3)).toBe("requeue");
    expect(decideJob(1, 3)).toBe("requeue");
    expect(decideJob(2, 3)).toBe("fail");
    expect(decideJob(0, 1)).toBe("fail");
  });
});

describe("decideRecovery", () => {
  it("requeues a lost worker's running jobs while another attempt is allowed", () => {
    expect(decideRecovery("w-lost", jobs, 3)).toEqual({ requeue: ["j1", "j2"], fail: ["j3"] });
  });

  it("fails every job when only one attempt is allowed", () => {
    expect(decideRecovery("w-lost", jobs, 1)).toEqual({ requeue: [], fail: ["j1", "j2", "j3"] });
  });

  it("ignores jobs of other workers and jobs that are not running", () => {
    expect(decideRecovery("w-nobody", jobs, 3)).toEqual({ requeue: [], fail: [] });
  });
});

describe("findStaleClaims", () => {
  const CFG = { staleClaimS: 180, claimGraceS: CLAIM_GRACE_S };
  const claimed = (id: string, workerId: string | null, agoS: number): StaleJob => ({
    id,
    status: "running",
    worker_id: workerId,
    started_at_ms: NOW - agoS * 1000,
  });
  const worker = (instance_id: string, state: StaleWorker["state"], idle_seconds = 0): StaleWorker => ({
    instance_id,
    state,
    idle_seconds,
  });

  it("marks a claim stale when its worker has been idle for at least STALE_CLAIM_S", () => {
    expect(findStaleClaims([claimed("j1", "w-a", 600)], [worker("w-a", "idle", 180)], NOW, CFG)).toEqual(["j1"]);
  });

  it("leaves a claim alone while its worker is busy", () => {
    expect(findStaleClaims([claimed("j1", "w-a", 600)], [worker("w-a", "busy", 0)], NOW, CFG)).toEqual([]);
  });

  it("marks a claim stale when its worker row no longer exists", () => {
    expect(findStaleClaims([claimed("j1", "w-gone", 600)], [], NOW, CFG)).toEqual(["j1"]);
  });

  it("leaves an idle worker alone until it has been idle for STALE_CLAIM_S", () => {
    expect(findStaleClaims([claimed("j1", "w-a", 600)], [worker("w-a", "idle", 179)], NOW, CFG)).toEqual([]);
  });

  it("never marks a job claimed in the last 60 s as stale", () => {
    // Missing worker or long idle, but the claim is only 30 s old: protected.
    expect(findStaleClaims([claimed("j1", "w-gone", 30)], [], NOW, CFG)).toEqual([]);
    expect(findStaleClaims([claimed("j1", "w-a", 30)], [worker("w-a", "idle", 9999)], NOW, CFG)).toEqual([]);
    // 61 s old: no longer protected.
    expect(findStaleClaims([claimed("j1", "w-a", 61)], [worker("w-a", "idle", 180)], NOW, CFG)).toEqual(["j1"]);
  });

  it("ignores jobs that are not running and jobs without a worker", () => {
    const queued: StaleJob = { id: "q", status: "queued", worker_id: "w-gone", started_at_ms: null };
    const unowned: StaleJob = { id: "u", status: "running", worker_id: null, started_at_ms: NOW - 600_000 };
    expect(findStaleClaims([queued, unowned], [], NOW, CFG)).toEqual([]);
  });
});

// Pure autoscaling decisions (CONTRACT sections 9 and 9b). No I/O here.

import type { WorkerState } from "./types";

export interface ScalingConfig {
  maxWorkers: number; // MAX_WORKERS (total across providers)
  jobsPerWorker: number; // JOBS_PER_WORKER
  idleDestroyS: number; // IDLE_DESTROY_S
  heartbeatLostS: number; // HEARTBEAT_LOST_S
  bootGraceS: number; // BOOT_GRACE_S: a booting worker that heartbeats may take this long to go live
  bootFailS: number; // BOOT_FAIL_S: a worker that never heartbeats is a boot failure after this
}

export interface WorkerView {
  /** Worker id (workers.instance_id). Decisions are returned under this key. */
  instance_id: string;
  provider: string;
  /** Provider ref (Vast contract id or Salad container name), or null when unknown. */
  provider_ref: string | null;
  state: WorkerState;
  created_at_ms: number;
  last_heartbeat_ms: number | null;
  idle_seconds: number;
}

export interface ScalingInput {
  backlog: number; // jobs in queued|running
  workers: WorkerView[];
  now: number; // ms since epoch
  config: ScalingConfig;
}

export interface ScalingDecision {
  create: number;
  /** Worker ids (workers.instance_id) to destroy. */
  destroy: string[];
}

export type DestroyReason = "boot_fail" | "stuck_boot" | "lost" | "idle";

export interface WorkerVerdict {
  instance_id: string;
  provider: string;
  reason: DestroyReason | null;
}

export interface ScalingPlanInput extends ScalingInput {
  providerOrder: readonly string[];
  /** provider -> cooldown_until in ms since epoch (missing or past means available). */
  cooldownUntilMs: ReadonlyMap<string, number>;
  providerCooldownS: number;
}

export interface ScalingPlan {
  create: number;
  destroy: string[];
  destroyed: WorkerVerdict[];
  /** Providers whose workers failed to boot in this tick. They are cooled down. */
  bootFailedProviders: string[];
  /** Cooldowns after this tick (input plus boot-failure cooldowns). */
  cooldownUntilMs: Map<string, number>;
  /** First provider to try for new workers; null when every provider is cooling down. */
  provider: string | null;
}

function assertValidConfig(c: ScalingConfig): void {
  const ints: Array<[string, number, number]> = [
    ["maxWorkers", c.maxWorkers, 0],
    ["jobsPerWorker", c.jobsPerWorker, 1],
  ];
  for (const [name, value, min] of ints) {
    if (!Number.isInteger(value) || value < min) {
      throw new RangeError(`${name} must be an integer >= ${min} (got ${value})`);
    }
  }
  const secs: Array<[string, number]> = [
    ["idleDestroyS", c.idleDestroyS],
    ["heartbeatLostS", c.heartbeatLostS],
    ["bootGraceS", c.bootGraceS],
    ["bootFailS", c.bootFailS],
  ];
  for (const [name, value] of secs) {
    if (!Number.isFinite(value) || value < 0) {
      throw new RangeError(`${name} must be a finite number >= 0 (got ${value})`);
    }
  }
}

/** desired = min(MAX_WORKERS, ceil(backlog / JOBS_PER_WORKER)). */
export function desiredWorkers(backlog: number, config: ScalingConfig): number {
  assertValidConfig(config);
  if (backlog <= 0) return 0;
  return Math.min(config.maxWorkers, Math.ceil(backlog / config.jobsPerWorker));
}

function reasonFor(w: WorkerView, backlog: number, now: number, cfg: ScalingConfig): DestroyReason | null {
  const ageS = (now - w.created_at_ms) / 1000;

  if (w.state === "booting") {
    // Never heartbeated: a boot failure once BOOT_FAIL_S has passed.
    if (w.last_heartbeat_ms === null) return ageS >= cfg.bootFailS ? "boot_fail" : null;
    // Heartbeats while booting: it may take BOOT_GRACE_S to go live. Lost-heartbeat does not apply inside it.
    return ageS >= cfg.bootGraceS ? "stuck_boot" : null;
  }

  const sinceSeenS = (now - (w.last_heartbeat_ms ?? w.created_at_ms)) / 1000;
  if (sinceSeenS >= cfg.heartbeatLostS) return "lost";
  if (w.state === "idle" && backlog === 0 && w.idle_seconds >= cfg.idleDestroyS) return "idle";
  return null;
}

/** Per-worker verdict: a destroy reason, or null to keep. Pure. */
export function classifyWorkers(input: ScalingInput): WorkerVerdict[] {
  assertValidConfig(input.config);
  if (!Number.isFinite(input.now)) throw new RangeError(`now must be finite (got ${input.now})`);
  return input.workers.map((w) => ({
    instance_id: w.instance_id,
    provider: w.provider,
    reason: reasonFor(w, input.backlog, input.now, input.config),
  }));
}

/**
 * Worker-level decision. Kept workers (any provider) count toward MAX_WORKERS.
 * create = max(0, desired - kept).
 */
export function decideScaling(input: ScalingInput): ScalingDecision {
  const verdicts = classifyWorkers(input);
  const destroy = verdicts.filter((v) => v.reason !== null).map((v) => v.instance_id);
  const kept = verdicts.length - destroy.length;
  const create = Math.max(0, desiredWorkers(input.backlog, input.config) - kept);
  return { create, destroy };
}

/** First provider in order that is not cooling down at `now`, or null. */
export function pickProvider(
  order: readonly string[],
  cooldownUntilMs: ReadonlyMap<string, number>,
  now: number,
): string | null {
  for (const name of order) {
    const until = cooldownUntilMs.get(name);
    if (until === undefined || until <= now) return name;
  }
  return null;
}

/**
 * Full tick plan: destroys, boot-failure cooldowns, the number of workers to create, and the
 * provider to try first. A provider that boot-failed in this tick is excluded from creates in the
 * same tick. If every provider is cooling down, nothing is created (destroys still happen).
 */
export function planScaling(input: ScalingPlanInput): ScalingPlan {
  const verdicts = classifyWorkers(input);
  const destroyed = verdicts.filter((v) => v.reason !== null);
  const destroy = destroyed.map((v) => v.instance_id);

  const bootFailedProviders: string[] = [];
  for (const v of destroyed) {
    if ((v.reason === "boot_fail" || v.reason === "stuck_boot") && !bootFailedProviders.includes(v.provider)) {
      bootFailedProviders.push(v.provider);
    }
  }

  const cooldownUntilMs = new Map(input.cooldownUntilMs);
  for (const p of bootFailedProviders) cooldownUntilMs.set(p, input.now + input.providerCooldownS * 1000);

  const provider = pickProvider(input.providerOrder, cooldownUntilMs, input.now);
  const kept = verdicts.length - destroy.length;
  const create = provider === null ? 0 : Math.max(0, desiredWorkers(input.backlog, input.config) - kept);

  return { create, destroy, destroyed, bootFailedProviders, cooldownUntilMs, provider };
}

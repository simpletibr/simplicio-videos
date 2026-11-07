// Parses string [vars] / secrets from Env into typed config. Throws on invalid values.

import type { Env } from "./types";
import type { ScalingConfig } from "./scaling";
import { isProviderName, PROVIDER_NAMES, type ProviderName } from "./providers/types";

/** Integer from a string var. Empty or missing uses `fallback` when given, otherwise throws. */
export function readInt(raw: string | undefined, name: string, min: number, max: number, fallback?: number): number {
  const s = (raw ?? "").trim();
  if (s === "" && fallback !== undefined) return fallback;
  if (!/^\d+$/.test(s)) throw new Error(`${name} must be a non-negative integer (got ${JSON.stringify(raw)})`);
  const n = Number(s);
  if (n < min || n > max) throw new Error(`${name} must be between ${min} and ${max} (got ${n})`);
  return n;
}

function floatVar(raw: string | undefined, name: string, min: number): number {
  const s = (raw ?? "").trim();
  const n = Number(s);
  if (s === "" || !Number.isFinite(n) || n < min) {
    throw new Error(`${name} must be a number >= ${min} (got ${JSON.stringify(raw)})`);
  }
  return n;
}

export interface PricingConfig {
  pricePerSecond: number;
  maxDurationS: number;
}

export function loadPricingConfig(env: Env): PricingConfig {
  return {
    pricePerSecond: readInt(env.PRICE_CENTS_PER_SECOND, "PRICE_CENTS_PER_SECOND", 1, 100_000),
    maxDurationS: readInt(env.MAX_DURATION_S, "MAX_DURATION_S", 1, 300),
  };
}

export function loadScalingConfig(env: Env): ScalingConfig {
  return {
    maxWorkers: readInt(env.MAX_WORKERS, "MAX_WORKERS", 0, 100),
    jobsPerWorker: readInt(env.JOBS_PER_WORKER, "JOBS_PER_WORKER", 1, 1000),
    idleDestroyS: readInt(env.IDLE_DESTROY_S, "IDLE_DESTROY_S", 0, 86_400),
    heartbeatLostS: readInt(env.HEARTBEAT_LOST_S, "HEARTBEAT_LOST_S", 0, 86_400),
    bootGraceS: readInt(env.BOOT_GRACE_S, "BOOT_GRACE_S", 0, 86_400),
    bootFailS: readInt(env.BOOT_FAIL_S, "BOOT_FAIL_S", 1, 86_400, 1500),
  };
}

/** PROVIDER_ORDER: comma-separated provider names. Default "vast,salad". Trimmed, de-duplicated. */
export function parseProviderOrder(raw: string | undefined): ProviderName[] {
  const s = (raw ?? "").trim();
  const names = s === "" ? ["vast", "salad"] : s.split(",").map((p) => p.trim()).filter((p) => p !== "");
  const out: ProviderName[] = [];
  for (const name of names) {
    if (!isProviderName(name)) {
      throw new Error(`PROVIDER_ORDER has an unknown provider "${name}" (known: ${PROVIDER_NAMES.join(", ")})`);
    }
    if (!out.includes(name)) out.push(name);
  }
  if (out.length === 0) throw new Error("PROVIDER_ORDER must name at least one provider");
  return out;
}

export interface ProviderConfig {
  order: ProviderName[];
  cooldownS: number;
}

export function loadProviderConfig(env: Env): ProviderConfig {
  return {
    order: parseProviderOrder(env.PROVIDER_ORDER),
    cooldownS: readInt(env.PROVIDER_COOLDOWN_S, "PROVIDER_COOLDOWN_S", 0, 86_400, 900),
  };
}

export function loadRecoveryConfig(env: Env): { maxAttempts: number; staleClaimS: number } {
  return {
    maxAttempts: readInt(env.MAX_ATTEMPTS, "MAX_ATTEMPTS", 1, 20, 3),
    staleClaimS: readInt(env.STALE_CLAIM_S, "STALE_CLAIM_S", 1, 86_400, 180),
  };
}

export interface VastConfig {
  image: string;
  diskGb: number;
  maxDph: number;
}

export function loadVastConfig(env: Env): VastConfig {
  const image = (env.VAST_IMAGE ?? "").trim();
  if (image === "") throw new Error("VAST_IMAGE must be set");
  return {
    image,
    diskGb: readInt(env.VAST_DISK_GB, "VAST_DISK_GB", 1, 10_000),
    maxDph: floatVar(env.MAX_DPH, "MAX_DPH", 0),
  };
}

// Provider abstraction (CONTRACT 9b). Each provider is built per cron tick from env, so any
// per-tick caches (for example Salad's GPU class id) live for exactly one invocation.

import type { Env } from "../types";

export type ProviderName = "vast" | "salad";
export const PROVIDER_NAMES: readonly ProviderName[] = ["vast", "salad"];

export function isProviderName(v: string): v is ProviderName {
  return (PROVIDER_NAMES as readonly string[]).includes(v);
}

/** A worker a provider still runs, as seen by the provider (orphan detection). */
export interface ProviderWorker {
  workerId: string;
  providerRef: string;
}

export interface Provider {
  readonly name: ProviderName;
  /** Creates a worker. Returns the provider ref to store. Throws NoCapacityError or another error on failure. */
  create(workerId: string): Promise<string>;
  /** Destroys by provider ref. A missing instance counts as destroyed. */
  destroy(providerRef: string): Promise<void>;
  /** Deterministic provider ref for a worker id, when the provider names workers predictably. */
  refFor?(workerId: string): string;
  /** Workers this provider still runs. Throws when the listing fails. */
  listWorkers?(): Promise<ProviderWorker[]>;
}

export class NoCapacityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NoCapacityError";
  }
}

/** Worker id from a fresh uuid: "w-" + the first 12 hex chars (dashes removed). Pure. */
export function workerIdFromUuid(uuid: string): string {
  const hex = uuid.replace(/-/g, "").toLowerCase();
  if (!/^[0-9a-f]{32}$/.test(hex)) throw new Error("workerIdFromUuid expects a uuid");
  return `w-${hex.slice(0, 12)}`;
}

/** Env pairs forwarded to every worker. INSTANCE_ID is the worker id, PROVIDER is the provider name. */
export function workerEnvPairs(env: Env, workerId: string, provider: ProviderName): Array<[string, string]> {
  return [
    ["INSTANCE_ID", workerId],
    ["PROVIDER", provider],
    ["WORKER_SECRET", env.WORKER_SECRET],
    ["API_BASE_URL", env.API_BASE_URL],
    ["CF_ACCOUNT_ID", env.CF_ACCOUNT_ID],
    ["CF_QUEUE_ID", env.CF_QUEUE_ID],
    ["CF_API_TOKEN", env.CF_API_TOKEN],
    ["R2_ENDPOINT", env.R2_ENDPOINT],
    ["R2_ACCESS_KEY_ID", env.R2_ACCESS_KEY_ID],
    ["R2_SECRET_ACCESS_KEY", env.R2_SECRET_ACCESS_KEY],
    ["R2_BUCKET", env.R2_BUCKET],
  ];
}

/** Throws before any request when a value that must reach the worker is missing. */
export function assertEnvPresent(pairs: ReadonlyArray<readonly [string, string]>): void {
  for (const [key, value] of pairs) {
    if (typeof value !== "string" || value === "") throw new Error(`missing env value for ${key}`);
  }
}

/** Parses a response body as JSON. An empty or non-JSON body becomes {}. */
export function parseBody(text: string): unknown {
  if (text === "") return {};
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

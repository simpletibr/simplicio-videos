// Vast.ai provider (CONTRACT 10). Uses ONLY the endpoints and bodies in CONTRACT section 10.
// Unverified field names and values are marked VERIFY.

import { loadVastConfig } from "../config";
import type { Env } from "../types";
import { NoCapacityError, parseBody, workerEnvPairs, type Provider, type ProviderWorker } from "./types";

export const VAST_API_BASE = "https://console.vast.ai/api/v0";

// Every instance is labelled h3-swap-<worker_id>. Orphan detection matches on this prefix.
export const VAST_LABEL_PREFIX = "h3-swap-";

// VERIFY: runtype value "args" (run the image entrypoint). Not specified in CONTRACT.
export const VAST_RUNTYPE = "args";
// VERIFY: the worker image's ENTRYPOINT starts worker.py, so no onstart script is needed.
export const VAST_ONSTART = "";
const ONSTART_MAX_CHARS = 4048;
const MAX_OFFER_ATTEMPTS = 3;

export class VastApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "VastApiError";
    this.status = status;
  }
}

export interface VastOffer {
  id: string;
  dph_total: number;
}

export interface VastInstance {
  id: string;
  label: string | null;
  actual_status: string | null;
}

// VERIFY: gpu_name spelling. CONTRACT uses "RTX 5090"; Vast may use underscores in some fields.
export const DEFAULT_OFFER_FILTER: Readonly<Record<string, unknown>> = {
  verified: { eq: true },
  rentable: { eq: true },
  gpu_name: { eq: "RTX 5090" },
  num_gpus: { eq: 1 },
  direct_port_count: { gte: 1 },
  order: [["dph_total", "asc"]],
  type: "on-demand",
  limit: 10,
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function instanceLabel(workerId: string): string {
  return `${VAST_LABEL_PREFIX}${workerId}`;
}

/** Worker id encoded in an instance label, or null if the label is not ours. */
export function workerIdFromLabel(label: string | null): string | null {
  if (label === null || !label.startsWith(VAST_LABEL_PREFIX)) return null;
  const id = label.slice(VAST_LABEL_PREFIX.length);
  return id === "" ? null : id;
}

/** Parses VAST_OFFER_FILTER_JSON. Must be a JSON object. */
export function parseOfferFilter(raw: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw.trim() === "" ? "{}" : raw);
  } catch {
    throw new Error("VAST_OFFER_FILTER_JSON is not valid JSON");
  }
  if (!isRecord(parsed)) throw new Error("VAST_OFFER_FILTER_JSON must be a JSON object");
  return parsed;
}

/** Defaults merged (shallow) with VAST_OFFER_FILTER_JSON. Extra keys win. */
export function buildOfferFilter(extraJson: string): Record<string, unknown> {
  return { ...DEFAULT_OFFER_FILTER, ...parseOfferFilter(extraJson) };
}

/** Keeps offers with dph_total <= maxDph, cheapest first. Skips malformed entries. */
export function filterOffers(raw: unknown[], maxDph: number): VastOffer[] {
  const out: VastOffer[] = [];
  for (const o of raw) {
    if (!isRecord(o)) continue;
    const id = o.id;
    const dph = o.dph_total;
    if ((typeof id !== "number" && typeof id !== "string") || typeof dph !== "number" || !Number.isFinite(dph)) {
      continue;
    }
    if (dph > maxDph) continue;
    out.push({ id: String(id), dph_total: dph });
  }
  return out.sort((a, b) => a.dph_total - b.dph_total);
}

const ENV_KEY = /^[A-Za-z_][A-Za-z0-9_]*$/;
const UNSAFE_VALUE = /[\s'"`$\\]/;

/**
 * Builds the Docker-flag env string `-e KEY=value ...` (CONTRACT section 10).
 * Values are not quoted, so they must not contain whitespace or shell-special characters.
 */
export function buildEnvString(vars: ReadonlyArray<readonly [string, string]>): string {
  return vars
    .map(([key, value]) => {
      if (!ENV_KEY.test(key)) throw new Error(`invalid env key: ${key}`);
      if (value === undefined || value === "") throw new Error(`missing env value for ${key}`);
      if (UNSAFE_VALUE.test(value)) {
        throw new Error(`env value for ${key} has whitespace or a shell-special character`);
      }
      return `-e ${key}=${value}`;
    })
    .join(" ");
}

async function vastRequest<T>(env: Env, method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  if (!env.VAST_API_KEY) throw new Error("VAST_API_KEY secret is not set");
  const res = await fetch(`${VAST_API_BASE}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${env.VAST_API_KEY}`,
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new VastApiError(res.status, `Vast ${method} ${path} failed: HTTP ${res.status} ${text.slice(0, 200)}`);
  }
  return parseBody(text) as T;
}

/** POST /bundles/ -> offers under the price cap, cheapest first. */
export async function searchOffers(env: Env, maxDph: number): Promise<VastOffer[]> {
  const filter = buildOfferFilter(env.VAST_OFFER_FILTER_JSON ?? "{}");
  const res = await vastRequest<{ offers?: unknown[] }>(env, "POST", "/bundles/", filter);
  return filterOffers(Array.isArray(res.offers) ? res.offers : [], maxDph);
}

/** PUT /asks/{offer_id}/ -> Vast contract id (new_contract). */
export async function createInstance(
  env: Env,
  offerId: string,
  opts: { image: string; diskGb: number; workerId: string },
): Promise<string> {
  if (VAST_ONSTART.length > ONSTART_MAX_CHARS) throw new Error("onstart exceeds 4048 chars");
  const body = {
    image: opts.image,
    disk: opts.diskGb,
    onstart: VAST_ONSTART,
    env: buildEnvString(workerEnvPairs(env, opts.workerId, "vast")),
    label: instanceLabel(opts.workerId),
    runtype: VAST_RUNTYPE,
  };
  const res = await vastRequest<{ success?: boolean; new_contract?: number | string }>(
    env,
    "PUT",
    `/asks/${encodeURIComponent(offerId)}/`,
    body,
  );
  if (res.success === false || res.new_contract === undefined || res.new_contract === null) {
    throw new Error(`Vast create failed for offer ${offerId}`);
  }
  return String(res.new_contract);
}

/** GET /instances/ */
export async function listInstances(env: Env): Promise<VastInstance[]> {
  const res = await vastRequest<{ instances?: unknown[] }>(env, "GET", "/instances/");
  const list = Array.isArray(res.instances) ? res.instances : [];
  const out: VastInstance[] = [];
  for (const i of list) {
    if (!isRecord(i)) continue;
    const id = i.id;
    if (typeof id !== "number" && typeof id !== "string") continue;
    out.push({
      id: String(id),
      label: typeof i.label === "string" ? i.label : null,
      actual_status: typeof i.actual_status === "string" ? i.actual_status : null,
    });
  }
  return out;
}

/** DELETE /instances/{id}/ */
export async function destroyInstance(env: Env, instanceId: string): Promise<void> {
  await vastRequest<unknown>(env, "DELETE", `/instances/${encodeURIComponent(instanceId)}/`);
}

/** Vast provider bound to env. Create searches offers and rents the cheapest one that succeeds. */
export function createVastProvider(env: Env): Provider {
  return {
    name: "vast",
    async create(workerId: string): Promise<string> {
      const vast = loadVastConfig(env);
      const offers = await searchOffers(env, vast.maxDph);
      if (offers.length === 0) throw new NoCapacityError("vast: no offer under MAX_DPH");
      let lastError: unknown = new NoCapacityError("vast: every offer failed");
      for (const offer of offers.slice(0, MAX_OFFER_ATTEMPTS)) {
        try {
          return await createInstance(env, offer.id, { image: vast.image, diskGb: vast.diskGb, workerId });
        } catch (err) {
          lastError = err;
        }
      }
      throw lastError;
    },
    async destroy(providerRef: string): Promise<void> {
      try {
        await destroyInstance(env, providerRef);
      } catch (err) {
        if (err instanceof VastApiError && err.status === 404) return;
        throw err;
      }
    },
    async listWorkers(): Promise<ProviderWorker[]> {
      const instances = await listInstances(env);
      const out: ProviderWorker[] = [];
      for (const inst of instances) {
        const workerId = workerIdFromLabel(inst.label);
        if (workerId !== null) out.push({ workerId, providerRef: inst.id });
      }
      return out;
    },
  };
}

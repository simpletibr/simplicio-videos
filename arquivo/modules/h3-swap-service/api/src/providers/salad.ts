// Salad provider (CONTRACT 10b). Base https://api.salad.com/api/public, header Salad-Api-Key.
// Unverified items are marked VERIFY.

import { readInt } from "../config";
import type { Env } from "../types";
import { assertEnvPresent, parseBody, workerEnvPairs, type Provider, type ProviderWorker } from "./types";

export const SALAD_API_BASE = "https://api.salad.com/api/public";
export const SALAD_NAME_PREFIX = "h3-swap-";
const DEFAULT_GPU_CLASS = "RTX 5090";
const DEFAULT_CPU = 8;
const DEFAULT_MEMORY_MB = 65536;

export class SaladApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "SaladApiError";
    this.status = status;
  }
}

export interface SaladConfig {
  org: string;
  project: string;
  gpuClassName: string;
  cpu: number;
  memoryMb: number;
  priority: string | null;
  image: string;
}

/** Container name: h3-swap-<worker_id>. Deterministic, so destroy needs no lookup. */
export function containerName(workerId: string): string {
  return `${SALAD_NAME_PREFIX}${workerId}`;
}

/** Worker id from a container name, or null if the name is not ours. */
export function workerIdFromContainerName(name: string): string | null {
  if (!name.startsWith(SALAD_NAME_PREFIX)) return null;
  const id = name.slice(SALAD_NAME_PREFIX.length);
  return id === "" ? null : id;
}

/** Salad names: 2 to 63 chars, lowercase letters, digits and hyphens, starting with a letter. */
export function assertContainerName(name: string): void {
  if (!/^[a-z][a-z0-9-]{1,62}$/.test(name)) throw new Error(`invalid Salad container name: ${name}`);
}

export function loadSaladConfig(env: Env): SaladConfig {
  const org = (env.SALAD_ORG ?? "").trim();
  if (org === "") throw new Error("SALAD_ORG must be set");
  const project = (env.SALAD_PROJECT ?? "").trim();
  if (project === "") throw new Error("SALAD_PROJECT must be set");
  const image = (env.SALAD_IMAGE ?? "").trim() || (env.VAST_IMAGE ?? "").trim();
  if (image === "") throw new Error("SALAD_IMAGE (or VAST_IMAGE) must be set");
  return {
    org,
    project,
    gpuClassName: (env.SALAD_GPU_CLASS_NAME ?? "").trim() || DEFAULT_GPU_CLASS,
    // VERIFY: cpu and memory defaults (CONTRACT: 8 and 65536 MB, unverified).
    cpu: readInt(env.SALAD_CPU, "SALAD_CPU", 1, 128, DEFAULT_CPU),
    memoryMb: readInt(env.SALAD_MEMORY_MB, "SALAD_MEMORY_MB", 1024, 1_048_576, DEFAULT_MEMORY_MB),
    priority: (env.SALAD_PRIORITY ?? "").trim() || null,
    image,
  };
}

/** Body for POST .../containers (CONTRACT 10b). environment_variables is an object. Pure. */
export function buildCreateBody(
  cfg: SaladConfig,
  name: string,
  gpuClassId: string,
  envPairs: ReadonlyArray<readonly [string, string]>,
): Record<string, unknown> {
  const container: Record<string, unknown> = {
    image: cfg.image,
    resources: { cpu: cfg.cpu, memory: cfg.memoryMb, gpu_classes: [gpuClassId] },
    environment_variables: Object.fromEntries(envPairs),
  };
  // Salad docs (create-container-group, read 2026-10-17): `priority` lives INSIDE `container`
  // (high|medium|low|batch). Sent only when SALAD_PRIORITY is set; the default is not documented.
  if (cfg.priority !== null) container.priority = cfg.priority;
  return {
    name,
    display_name: name,
    container,
    autostart_policy: true,
    restart_policy: "on_failure",
    replicas: 1,
  };
}

async function saladRequest<T>(env: Env, method: "GET" | "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  const key = env.SALAD_API_KEY;
  if (!key) throw new Error("SALAD_API_KEY secret is not set");
  const res = await fetch(`${SALAD_API_BASE}${path}`, {
    method,
    headers: {
      "Salad-Api-Key": key,
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new SaladApiError(res.status, `Salad ${method} ${path} failed: HTTP ${res.status} ${text.slice(0, 200)}`);
  }
  return parseBody(text) as T;
}

function enc(s: string): string {
  return encodeURIComponent(s);
}

/** Salad provider bound to env. The GPU class id is cached for this instance (one per cron tick). */
export function createSaladProvider(env: Env): Provider {
  let gpuClassId: string | null = null;

  const containersPath = (cfg: SaladConfig): string =>
    `/organizations/${enc(cfg.org)}/projects/${enc(cfg.project)}/containers`;

  const resolveGpuClass = async (cfg: SaladConfig): Promise<string> => {
    if (gpuClassId !== null) return gpuClassId;
    const res = await saladRequest<{ items?: unknown[] }>(env, "GET", `/organizations/${enc(cfg.org)}/gpu-classes`);
    const items = Array.isArray(res.items) ? res.items : [];
    for (const item of items) {
      if (typeof item !== "object" || item === null) continue;
      const rec = item as Record<string, unknown>;
      if (rec.name === cfg.gpuClassName && typeof rec.id === "string") {
        gpuClassId = rec.id;
        return rec.id;
      }
    }
    throw new Error(`Salad GPU class "${cfg.gpuClassName}" not found in organization`);
  };

  return {
    name: "salad",

    refFor(workerId: string): string {
      return containerName(workerId);
    },

    async create(workerId: string): Promise<string> {
      const cfg = loadSaladConfig(env);
      const name = containerName(workerId);
      assertContainerName(name);
      const pairs = workerEnvPairs(env, workerId, "salad");
      assertEnvPresent(pairs);
      const classId = await resolveGpuClass(cfg);
      await saladRequest(env, "POST", containersPath(cfg), buildCreateBody(cfg, name, classId, pairs));
      return name;
    },

    async destroy(providerRef: string): Promise<void> {
      const cfg = loadSaladConfig(env);
      try {
        await saladRequest(env, "DELETE", `${containersPath(cfg)}/${enc(providerRef)}`);
      } catch (err) {
        if (err instanceof SaladApiError && err.status === 404) return;
        throw err;
      }
    },

    // Best-effort (endpoint UNVERIFIED): a failure logs and returns no workers, so no orphan is destroyed on it.
    async listWorkers(): Promise<ProviderWorker[]> {
      try {
        const cfg = loadSaladConfig(env);
        const res = await saladRequest<{ items?: unknown[] }>(env, "GET", containersPath(cfg));
        const out: ProviderWorker[] = [];
        for (const item of Array.isArray(res.items) ? res.items : []) {
          if (typeof item !== "object" || item === null) continue;
          const name = (item as Record<string, unknown>).name;
          if (typeof name !== "string") continue;
          const workerId = workerIdFromContainerName(name);
          if (workerId !== null) out.push({ workerId, providerRef: name });
        }
        return out;
      } catch (err) {
        console.error(JSON.stringify({ event: "salad_list_failed", error: String(err) }));
        return [];
      }
    },
  };
}

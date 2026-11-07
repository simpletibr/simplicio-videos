import type { Env } from "../types";
import { createSaladProvider } from "./salad";
import type { Provider, ProviderName } from "./types";
import { createVastProvider } from "./vast";

/** Builds every provider bound to this env. Call once per cron tick. */
export function buildProviders(env: Env): Record<ProviderName, Provider> {
  return { vast: createVastProvider(env), salad: createSaladProvider(env) };
}

export * from "./types";

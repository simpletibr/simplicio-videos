// Cron autoscaler (CONTRACT sections 9 and 9b). Reads D1 and the providers, decides with pure logic
// (scaling.ts, recovery.ts), then acts through the providers.
//
// Order within a tick matters:
//  1. List every provider first. A worker row is always written before its instance is created,
//     so a listed instance either has a row read in step 2 or is a real orphan.
//  2. Read D1 (backlog, workers, provider cooldowns).
//  3. Plan (pure).
//  4. Destroy orphans. 5. Record boot-failure cooldowns.
//  6. Release workers: destroy the instance, requeue its jobs, then delete the row.
//     A failed step keeps the row, so the next tick retries it.
//  7. Stale-claim sweep. 8. Create, falling back to the next provider on error.

import { loadProviderConfig, loadRecoveryConfig, loadScalingConfig } from "./config";
import { recoverStaleClaims, recoverWorkerJobs, type RecoveryResult } from "./recovery";
import { pickProvider, planScaling, type WorkerView } from "./scaling";
import { buildProviders, isProviderName, PROVIDER_NAMES, workerIdFromUuid, type Provider, type ProviderWorker } from "./providers";
import type { Env, WorkerRow } from "./types";

export interface AutoscaleReport {
  backlog: number;
  known: number;
  created: string[]; // worker ids
  destroyed: string[]; // worker ids whose row was removed
  recovered: string[]; // job ids requeued
  failedJobs: string[]; // job ids failed (no attempts left)
  orphans: string[]; // provider refs destroyed because no D1 row tracks them
  cooldowns: string[]; // providers put into cooldown
  errors: string[];
}

function emptyReport(): AutoscaleReport {
  return { backlog: 0, known: 0, created: [], destroyed: [], recovered: [], failedJobs: [], orphans: [], cooldowns: [], errors: [] };
}

export function toWorkerView(row: WorkerRow): WorkerView {
  const created = Date.parse(row.created_at);
  const seen = row.last_heartbeat_at === null ? NaN : Date.parse(row.last_heartbeat_at);
  return {
    instance_id: row.instance_id,
    provider: row.provider,
    provider_ref: row.provider_ref,
    state: row.state,
    // An unparsable created_at is treated as ancient so the row gets cleaned up.
    created_at_ms: Number.isNaN(created) ? 0 : created,
    last_heartbeat_ms: Number.isNaN(seen) ? null : seen,
    idle_seconds: row.idle_seconds,
  };
}

async function readCooldowns(env: Env): Promise<Map<string, number>> {
  const rs = await env.DB.prepare("SELECT provider, cooldown_until FROM provider_state").all<{
    provider: string;
    cooldown_until: string | null;
  }>();
  const out = new Map<string, number>();
  for (const r of rs.results) {
    if (r.cooldown_until === null) continue;
    const until = Date.parse(r.cooldown_until);
    if (!Number.isNaN(until)) out.set(r.provider, until);
  }
  return out;
}

async function setCooldown(env: Env, provider: string, untilMs: number, lastError: string, report: AutoscaleReport): Promise<void> {
  try {
    await env.DB.prepare(
      `INSERT INTO provider_state (provider, cooldown_until, last_error) VALUES (?, ?, ?)
       ON CONFLICT(provider) DO UPDATE SET cooldown_until = excluded.cooldown_until, last_error = excluded.last_error`,
    )
      .bind(provider, new Date(untilMs).toISOString(), lastError.slice(0, 500))
      .run();
    report.cooldowns.push(provider);
  } catch (err) {
    report.errors.push(`cooldown ${provider}: ${String(err)}`);
  }
}

async function dropRow(env: Env, workerId: string, report: AutoscaleReport): Promise<void> {
  await env.DB.prepare("DELETE FROM workers WHERE instance_id = ?")
    .bind(workerId)
    .run()
    .catch((e) => report.errors.push(`delete row ${workerId}: ${String(e)}`));
}

/**
 * Releases one worker: destroy its instance, requeue or fail its jobs, then delete its row.
 * Each step is retry-safe, so a throw keeps the row for the next tick.
 */
async function releaseWorker(
  env: Env,
  row: WorkerRow,
  providers: Record<string, Provider>,
  listed: ReadonlyMap<string, ProviderWorker[] | null>,
  maxAttempts: number,
): Promise<RecoveryResult> {
  const provider = providers[row.provider];
  if (!provider) throw new Error(`unknown provider ${row.provider} on worker ${row.instance_id}`);
  const ref = row.provider_ref ?? provider.refFor?.(row.instance_id) ?? null;
  if (ref !== null) {
    await provider.destroy(ref);
  } else {
    // No stored ref (the create call never stored one): destroy by listing the provider's workers.
    const list = listed.get(provider.name);
    if (!list) throw new Error(`no provider_ref for ${row.instance_id} and no listing; retry later`);
    for (const w of list) {
      if (w.workerId === row.instance_id) await provider.destroy(w.providerRef);
    }
  }
  const recovered = await recoverWorkerJobs(env, row.instance_id, maxAttempts);
  await env.DB.prepare("DELETE FROM workers WHERE instance_id = ?").bind(row.instance_id).run();
  return recovered;
}

/** Runs one autoscaler tick. Never throws; problems go into the report and logs. */
export async function runAutoscaler(env: Env, now: number = Date.now()): Promise<AutoscaleReport> {
  const report = emptyReport();
  const nowIso = new Date(now).toISOString();

  try {
    const scaling = loadScalingConfig(env);
    const providerCfg = loadProviderConfig(env);
    const recovery = loadRecoveryConfig(env);
    const providers = buildProviders(env) as Record<string, Provider>;

    // 1. Listings first.
    const listed = new Map<string, ProviderWorker[] | null>();
    for (const name of PROVIDER_NAMES) {
      const p = providers[name];
      try {
        listed.set(name, p?.listWorkers ? await p.listWorkers() : []);
      } catch (err) {
        listed.set(name, null);
        report.errors.push(`list ${name}: ${String(err)}`);
      }
    }

    // 2. D1 snapshot.
    const backlogRow = await env.DB.prepare("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued', 'running')").first<{
      n: number;
    }>();
    report.backlog = backlogRow?.n ?? 0;
    const rows = (await env.DB.prepare("SELECT * FROM workers").all<WorkerRow>()).results;
    report.known = rows.length;
    const rowsById = new Map(rows.map((r) => [r.instance_id, r] as const));
    const cooldown = await readCooldowns(env);

    // 3. Plan.
    const plan = planScaling({
      backlog: report.backlog,
      workers: rows.map(toWorkerView),
      now,
      config: scaling,
      providerOrder: providerCfg.order,
      cooldownUntilMs: cooldown,
      providerCooldownS: providerCfg.cooldownS,
    });

    // 4. Orphans: listed workers with no row.
    for (const name of PROVIDER_NAMES) {
      const list = listed.get(name);
      if (!list) continue;
      for (const w of list) {
        if (rowsById.has(w.workerId)) continue;
        try {
          await providers[name]?.destroy(w.providerRef);
          report.orphans.push(w.providerRef);
        } catch (err) {
          report.errors.push(`orphan ${w.providerRef}: ${String(err)}`);
        }
      }
    }

    // 5. Boot-failure cooldowns.
    for (const p of plan.bootFailedProviders) {
      await setCooldown(env, p, plan.cooldownUntilMs.get(p) ?? now, "boot failure: worker never came up", report);
    }

    // 6. Releases.
    for (const workerId of plan.destroy) {
      const row = rowsById.get(workerId);
      if (!row) continue;
      try {
        const rec = await releaseWorker(env, row, providers, listed, recovery.maxAttempts);
        report.destroyed.push(workerId);
        report.recovered.push(...rec.requeued);
        report.failedJobs.push(...rec.failed);
      } catch (err) {
        report.errors.push(`release ${workerId}: ${String(err)}`);
      }
    }

    // 7. Stale claims: running jobs whose worker is idle for STALE_CLAIM_S or gone.
    try {
      const workerStates = rows.map((r) => ({ instance_id: r.instance_id, state: r.state, idle_seconds: r.idle_seconds }));
      const rec = await recoverStaleClaims(env, now, { staleClaimS: recovery.staleClaimS, maxAttempts: recovery.maxAttempts }, workerStates);
      report.recovered.push(...rec.requeued);
      report.failedJobs.push(...rec.failed);
    } catch (err) {
      report.errors.push(`stale claims: ${String(err)}`);
    }

    // 8. Creates. On a create error the provider cools down and the next one is tried in this tick.
    if (plan.create > 0) {
      const local = new Map(plan.cooldownUntilMs);
      let made = 0;
      while (made < plan.create) {
        const picked = pickProvider(providerCfg.order, local, now);
        if (picked === null || !isProviderName(picked)) {
          report.errors.push(`no provider available: wanted ${plan.create}, created ${made}`);
          break;
        }
        const workerId = workerIdFromUuid(crypto.randomUUID());
        try {
          await env.DB.prepare(
            `INSERT INTO workers (instance_id, provider, provider_ref, state, created_at, last_heartbeat_at, idle_seconds, jobs_done)
             VALUES (?, ?, NULL, 'booting', ?, NULL, 0, 0)`,
          )
            .bind(workerId, picked, nowIso)
            .run();
        } catch (err) {
          report.errors.push(`record ${workerId}: ${String(err)}`);
          break;
        }

        let ref: string;
        try {
          ref = await providers[picked]!.create(workerId);
        } catch (err) {
          report.errors.push(`create via ${picked}: ${String(err)}`);
          const until = now + providerCfg.cooldownS * 1000;
          local.set(picked, until);
          await setCooldown(env, picked, until, String(err), report);
          await dropRow(env, workerId, report);
          continue;
        }

        try {
          await env.DB.prepare("UPDATE workers SET provider_ref = ? WHERE instance_id = ?").bind(ref, workerId).run();
        } catch (err) {
          // The row is dropped even if this destroy fails. The orphan sweep then finds the instance.
          report.errors.push(`store provider_ref for ${workerId}: ${String(err)}`);
          await providers[picked]!.destroy(ref).catch((e) => report.errors.push(`destroy ${ref}: ${String(e)}`));
          await dropRow(env, workerId, report);
          continue;
        }

        made += 1;
        report.created.push(workerId);
      }
    }
  } catch (err) {
    report.errors.push(String(err));
  }

  console.log(JSON.stringify({ event: "autoscale", at: nowIso, ...report }));
  return report;
}

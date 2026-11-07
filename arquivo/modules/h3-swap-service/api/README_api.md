# h3-swap-api (control plane)

One Cloudflare Worker (`src/index.ts`) with a hand-written router. It serves the client API,
receives claims, status and heartbeats from GPU workers, produces jobs on the `h3-jobs` queue, and
runs the autoscaler on a cron every minute. Workers run on two providers with fallback: Vast.ai
first, Salad second (`PROVIDER_ORDER`). Storage is D1 (state), R2 (uploads and outputs) and Queues.

Nothing here has been deployed or called against Cloudflare, Vast or Salad. See section 6.

## 1. Setup

Run everything from `api/`.

```bash
cd api
npm install
```

1. **D1 database.** Create it, paste the printed `database_id` into `wrangler.toml` (replace
   `TODO_FILL`), and apply the schema:
   ```bash
   npx wrangler d1 create h3-swap
   npx wrangler d1 execute h3-swap --remote --file=schema.sql
   ```
   Use `--local` for local dev. An older database needs the `ALTER TABLE` and `CREATE` lines in the
   header of `schema.sql`, run once.
2. **R2 bucket.** `npx wrangler r2 bucket create h3-swap`
3. **Queue and HTTP pull consumer.** The producer binding is in `wrangler.toml`. The consumer is NOT
   declared in code, because the GPU workers pull over HTTP:
   ```bash
   npx wrangler queues create h3-jobs
   npx wrangler queues consumer http add h3-jobs
   ```
   Get `CF_QUEUE_ID` from `npx wrangler queues list` or the dashboard. The API token needs
   `Queues: Edit` (queues_read + queues_write).
4. **Secrets.** Each is prompted for by `wrangler secret put`. Never commit values.
   ```bash
   npx wrangler secret put VAST_API_KEY
   npx wrangler secret put SALAD_API_KEY        # Salad-Api-Key header
   npx wrangler secret put WORKER_SECRET        # shared with workers (X-Worker-Secret)
   npx wrangler secret put ADMIN_SECRET         # /internal/credits/add (X-Admin-Secret)
   npx wrangler secret put CF_ACCOUNT_ID
   npx wrangler secret put CF_QUEUE_ID
   npx wrangler secret put CF_API_TOKEN
   npx wrangler secret put R2_ENDPOINT          # https://<ACCOUNT_ID>.r2.cloudflarestorage.com
   npx wrangler secret put R2_ACCESS_KEY_ID
   npx wrangler secret put R2_SECRET_ACCESS_KEY
   npx wrangler secret put R2_BUCKET            # h3-swap
   npx wrangler secret put API_BASE_URL         # public URL of this Worker, no trailing slash
   ```
   Use hex or URL-safe values (for example `openssl rand -hex 32`). Vast env values must not contain
   whitespace, quotes, backticks, `$` or backslashes (they go in as unquoted Docker `-e` flags).
   Salad env goes in as a JSON object, so it has no such restriction.
5. **Vast setup.** Set `VAST_IMAGE` (and `VAST_DISK_GB`, `MAX_DPH`, `VAST_OFFER_FILTER_JSON`) in
   `[vars]`. Vast instances are created with `runtype: "args"`.
6. **Salad setup.** Set in `[vars]`: `SALAD_ORG`, `SALAD_PROJECT`, `SALAD_GPU_CLASS_NAME` (default
   `RTX 5090`), `SALAD_CPU` (default 8), `SALAD_MEMORY_MB` (default 65536). `SALAD_PRIORITY` is
   optional and sent only when set. `SALAD_IMAGE` falls back to `VAST_IMAGE` when empty. Use the
   `runtime` image target for Salad (instances are interruptible and their disk is ephemeral).
7. **Tune `[vars]`** (price, caps, provider order, boot and stale timeouts). `PRICE_CENTS_PER_SECOND`
   is in BRL centavos (16 = R$ 0,16/s).
8. **Deploy and check.**
   ```bash
   npm run typecheck && npm test
   npx wrangler deploy --dry-run   # bundles without deploying
   npm run deploy
   ```

## 2. Environment

| Name | Default | Meaning |
|---|---|---|
| `MAX_WORKERS` | 2 | Total workers across providers |
| `JOBS_PER_WORKER` | 4 | Desired workers = ceil(backlog / this), capped at MAX_WORKERS |
| `IDLE_DESTROY_S` | 900 | Release an idle worker when backlog is 0 |
| `HEARTBEAT_LOST_S` | 1200 | Release a worker with no heartbeat for this long |
| `BOOT_GRACE_S` | 3600 | A booting worker that heartbeats may take this long to go live |
| `BOOT_FAIL_S` | 1500 | A worker that never heartbeats is a boot failure after this (provider cooldown) |
| `PROVIDER_ORDER` | `vast,salad` | Order of providers to try for new workers |
| `PROVIDER_COOLDOWN_S` | 900 | A provider that failed to create or boot is skipped for this long |
| `MAX_ATTEMPTS` | 3 | Total runs allowed per job (see section 4) |
| `STALE_CLAIM_S` | 180 | A claim whose worker has been idle this long (per last heartbeat) is requeued |
| `PRICE_CENTS_PER_SECOND`, `MAX_DURATION_S` | 16, 30 | Pricing and clip length |

## 3. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/v1/jobs` | `Authorization: Bearer <api key>` | Create a job (multipart) |
| GET | `/v1/jobs/{id}` | Bearer, owner only | Job status |
| GET | `/v1/jobs/{id}/download` | Bearer, owner only | Stream `result.mp4` (409 until succeeded) |
| GET | `/v1/me` | Bearer | Balance in cents |
| POST | `/internal/jobs/{id}/status` | `X-Worker-Secret` | Worker callback, see below |
| POST | `/internal/heartbeat` | `X-Worker-Secret` | Heartbeat; `instance_id` is the worker id |
| POST | `/internal/credits/add` | `X-Admin-Secret` | Manual top-up `{user_id, cents}` |
| (cron, every minute) | | | Autoscaler, provider fallback, recovery |

`POST /internal/jobs/{id}/status` takes `status` with one of these values:

| `status` | Effect | Answers |
|---|---|---|
| `running` | Claim. Queued job, or the current owner repeating. Sets `worker_id`. | `200 {"ok":true}`, or `409 {"ok":false,"reason"}` if final, unknown, or held by another worker |
| `retry` | Owner releases a failed try. Sets `queued`, clears `worker_id`, stores `error`, `attempts+1`. No refund. | `200 {"ok":true}`, or `409` for another worker, a final job, or unknown. A repeat of the same release answers 200. |
| `succeeded` | Settles: charges `ceil(output_duration_s) * price`, refunds the rest | `200`; repeat on a final job is `200 {"ignored":true}` |
| `failed` | Full refund | `200`; repeat on a final job is `200 {"ignored":true}` |

Errors are JSON: `{"error": "<code>", "message": "..."}`. Codes include `unauthorized` (401),
`insufficient_credits` (402), `not_found` (404), `not_ready` (409), `file_too_large` (413),
`unsupported_media_type` (415), `invalid_request` (400) and `invalid_json` (400).

Examples (replace the placeholders):

```bash
API=https://api.example.com
KEY=<raw api key>

# Balance
curl -sS "$API/v1/me" -H "Authorization: Bearer $KEY"

# Create a job: source video, 1 character image, meta JSON
curl -sS "$API/v1/jobs" -H "Authorization: Bearer $KEY" \
  -F 'meta={"duration_s":10,"characters":[{"replace_description":"o homem de boné, à esquerda"}],"prompt_extra":null,"seed":null};type=application/json' \
  -F 'source=@clip.mp4;type=video/mp4' \
  -F 'char1=@person.png;type=image/png'
# -> {"job_id":"...","status":"queued","reserved_cents":160}

# Poll status, download when "succeeded"
curl -sS "$API/v1/jobs/<job_id>" -H "Authorization: Bearer $KEY"
curl -sS -o result.mp4 "$API/v1/jobs/<job_id>/download" -H "Authorization: Bearer $KEY"

# Worker claim (what a worker sends before doing GPU work)
curl -sS -X POST "$API/internal/jobs/<job_id>/status" -H "X-Worker-Secret: $WORKER_SECRET" \
  -H "content-type: application/json" -d '{"status":"running","instance_id":"w-123e4567e89b"}'

# Admin top-up (R$ 50,00)
curl -sS -X POST "$API/internal/credits/add" \
  -H "X-Admin-Secret: $ADMIN_SECRET" -H "content-type: application/json" \
  -d '{"user_id":"user-001","cents":5000}'
```

Limits: `duration_s` 1..`MAX_DURATION_S` (30). 1 to 3 characters. `replace_description` 3..200 characters
after trimming. `prompt_extra` at most 500 characters (an API choice, not in CONTRACT). Video is
`video/mp4` or `video/quicktime`, at most 200 MiB. Images are `image/png`, `image/jpeg` or
`image/webp`, at most 15 MiB.

## 4. Behaviour

- **Credits.** Create reserves `duration_s * PRICE_CENTS_PER_SECOND` with a conditional
  `UPDATE ... WHERE balance_cents >= ?`. `succeeded` settles (charge capped at the reservation, rest
  refunded). `failed` refunds everything. `retry` never touches credits. Settlement and refund are one
  D1 batch.
- **Attempts.** `attempts` counts consumed runs. A claim does not change it. A `retry` adds one, and so
  does a requeue after a lost worker or a stale claim. A job is requeued while `attempts + 1 < MAX_ATTEMPTS`
  and failed (full refund, error "...; no attempts left") otherwise. So MAX_ATTEMPTS = 3 means at most 3 runs.
- **Requeue.** A requeue sets `queued`, clears `worker_id` and `started_at`, adds one to `attempts`,
  then sends a NEW queue message built from the message stored on the job row. If the send fails, the
  row goes back to its old owner so the next tick retries. An old message may reappear later; the
  claim answers 409 and the worker acks it.
- **Lost worker.** Released (lost heartbeat, idle, or boot failure): the instance is destroyed first,
  then every job with `status='running'` and that `worker_id` is requeued or failed, then the row is
  deleted. A failed step keeps the row for the next tick.
- **Stale claims.** Each tick, a running job is requeued when its worker row is gone, or its worker is
  `idle` with `idle_seconds >= STALE_CLAIM_S`. A claim younger than 60 s is never stale. This covers a
  claim stored while the worker saw a 5xx.
- **Scaling** (`scaling.ts`, pure). `desired = min(MAX_WORKERS, ceil(backlog / JOBS_PER_WORKER))`.
  Kept workers from all providers count toward MAX_WORKERS. A booting worker with no heartbeat counts as
  capacity until `BOOT_FAIL_S`, then it is a boot failure. A booting worker that heartbeats counts until
  `BOOT_GRACE_S`, and lost-heartbeat does not apply inside that window. Lost heartbeat, idle release and
  boot failure are the destroy reasons. Instances are never stopped or restarted.
- **Provider fallback.** `pickProvider` takes the first provider in `PROVIDER_ORDER` not cooling down.
  A create error, or a boot failure, cools that provider down for `PROVIDER_COOLDOWN_S`. The same tick
  then tries the next provider. If every provider is cooling down, nothing is created, but releases still
  happen.
- **Identity.** Each worker gets `w-<12 hex>` from a fresh uuid before the create call. That id is
  `workers.instance_id`, is passed to the worker as `INSTANCE_ID`, and is the Vast label suffix
  (`h3-swap-<id>`) or Salad container name (`h3-swap-<id>`). `workers.provider_ref` is the Vast contract
  id or Salad container name, used for destroy.
- **Create order.** Insert the row (`booting`, `provider_ref` NULL), create the instance, store
  `provider_ref`. A failed create drops the row. A failed store destroys the instance and drops the row.
  A create that succeeded without a stored ref is caught by the orphan sweep.
- **Orphans.** Each tick lists every provider first, then reads D1. A listed worker with no row is
  destroyed. Vast lists instances by the `h3-swap-` label. Salad lists containers by the same name prefix
  (best-effort: on failure it logs and returns nothing, so nothing is destroyed on that basis).
- **Heartbeats.** Upserted by worker id. An unknown id creates a row with `provider_ref` NULL. The upsert
  never overwrites `provider` or `provider_ref`. `provider` must be `vast` or `salad`.
- **Logs.** Each tick logs one JSON line, `event: "autoscale"`, with `backlog`, `created`, `destroyed`,
  `recovered`, `failedJobs`, `orphans`, `cooldowns` and `errors`. Watch it with `npx wrangler tail`.

## 5. Providers

Vast (CONTRACT 10): search `POST /bundles/` with the default filter (`RTX 5090`, x1, on-demand, verified,
rentable) merged with `VAST_OFFER_FILTER_JSON`, keep offers with `dph_total <= MAX_DPH`, rent the cheapest
that succeeds (at most 3 attempts) with `PUT /asks/{id}/`. Destroy with `DELETE /instances/{id}/`, where a
404 counts as destroyed. Orphans come from `GET /instances/` filtered by label.

Salad (CONTRACT 10b): base `https://api.salad.com/api/public`, header `Salad-Api-Key`. GPU class: `GET
/organizations/{org}/gpu-classes`, matched by name, cached for one cron tick. Create: `POST
/organizations/{org}/projects/{project}/containers` with `name` `h3-swap-<worker_id>`, `autostart_policy:
true`, `restart_policy: "on_failure"`, `replicas: 1`, and `container.environment_variables` as an object.
Destroy: `DELETE .../containers/{name}`, where a 404 counts as destroyed. The name is deterministic, so no
lookup is needed. Orphans: `GET .../containers` (best-effort).

## 6. VERIFY (not checked against real services)

Verified here: `npm run typecheck` is clean, `npm test` passes (112 tests in 9 files), and
`wrangler deploy --dry-run` bundles the Worker with the expected bindings and no queue consumer.

UNVERIFIED, and must be checked before relying on it:

1. **Deploy and bindings.** `database_id` is still `TODO_FILL`. Nothing was deployed.
2. **Queue HTTP pull consumer.** Confirm `wrangler queues consumer http add h3-jobs` works on the account, and that `CF_QUEUE_ID` is the right value.
3. **Vast REST.** Still to confirm: `runtype: "args"` (not in CONTRACT), `onstart: ""` (assumes the image ENTRYPOINT starts the worker), offer fields `id` and `dph_total`, `gpu_name` spelling (`RTX 5090` vs `RTX_5090`), whether `dph_total` is USD per hour, that `PUT /asks/{id}/` accepts `label`, that `DELETE` on a missing instance returns 404, and that the `-e` env string reaches the container intact.
4. **Vast instance list returns labels.** Orphan detection depends on each item of `GET /instances/` carrying `label`. If labels are missing, no Vast orphans are found, which is safe but leaves them alive.
5. **Salad (CONTRACT 10b items).**
   - An `RTX 5090` GPU class exists in the org. If not, every Salad create fails and Salad cools down.
   - The gpu-classes list is not paginated.
   - Create returns 201 and the container's `name` is the provider ref.
   - Whether `autostart_policy: true` starts the container without an explicit `POST .../start` (not called).
   - Cpu and memory defaults (8, 65536 MB) and the position of the `priority` field (UNVERIFIED).
   - Private-registry auth (not sent; the image must be public or added later).
   - The list-containers endpoint, used for orphan detection (best-effort).
   - Delete of a running container returns 202, and whether a container must be stopped first.
   - The RTX 5090 price (US$0.50/h is third-party and not confirmed).
   - Interruptible instances and ephemeral disk: a worker can vanish at any time (covered by lost-worker recovery).
6. **GPU worker side.** It must read `INSTANCE_ID` and report it as `instance_id`, send `status: "running"` as its claim (handle 409 by acking and skipping), send `status: "retry"` before asking the queue to retry, and set `PROVIDER` from its env. A wrong id leaves the real row without heartbeats.
7. **Stale-claim threshold.** `STALE_CLAIM_S` (180) must be longer than a worker's normal poll-and-claim gap, and idle workers must heartbeat often enough for `idle_seconds` to be fresh.
8. **Large uploads.** A 200 MiB multipart body goes through `request.formData()`. Confirm the Workers request-size limit and memory on the plan in use.
9. **Content types.** Types are client-declared and not sniffed. `video/quicktime` is stored under the `source.mp4` key. Confirm the worker and ComfyUI decode it.
10. **Boot and orphan cost.** A worker that never heartbeats costs up to `BOOT_FAIL_S` (1500 s) before it is released. An orphan that is not listed costs until the next listing.
11. **Cron.** Confirm the `* * * * *` trigger fires after deploy.
12. **Refund guard.** Settlement refunds only when the job row moved to that final state at that timestamp. Two settlements in the same millisecond could double-refund. Unlikely, not proven.
13. **Requeue crash window.** If the process dies after a requeue update and before the send, the job is `queued` with no message. Recovery does not revisit `queued` jobs. This is a known gap.

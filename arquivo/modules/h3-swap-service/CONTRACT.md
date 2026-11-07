# h3-swap-service — CONTRACT v1

Character-swap video service on the open MiniMax H3 + akatz-ai Character-Swap LoRA,
ComfyUI (headless) on rented GPUs (Vast.ai first, Salad later), Cloudflare for the control plane.

```
client -> API Worker (CF) -> R2 (uploads) + Queue + D1
                                  ^ cron autoscaler (CF Worker) -> Vast REST (create/destroy)
GPU box (Docker): worker.py -- pulls Queue over HTTP --> ComfyUI :8188 -> R2 (outputs)
                           \-- status callback + heartbeat --> API Worker
```

## 1. Layout and ownership (ONE owner per file, never edit another squad's files)

| Path | Owner |
|---|---|
| `CONTRACT.md`, `README.md`, `.env.example`, `.gitignore` | lead |
| `docker/**` | squad A |
| `worker/**` | squad B |
| `api/**` | squad C |
| `bench/**` | squad D (may import read-only from `worker/`) |

## 2. Constants

- `PRICE_CENTS_PER_SECOND = 16` (BRL centavos, i.e. R$ 0,16/s). Configurable by env, default 16.
- `MAX_DURATION_S = 30`, `FPS = 24`, native tier label `"768p"` (H3 native canvas is 768 px short edge).
- H3 frame grid: valid frame counts are `17k + 5`. Per-clip ceiling is 362 frames (~15 s).
  Videos longer than 15 s are produced in chunks by the Continuum workflow.

## 3. R2 key layout (bucket from `R2_BUCKET`)

```
uploads/{job_id}/source.mp4
uploads/{job_id}/char1.png|jpg|webp   (also char2, char3; 1..3 characters)
outputs/{job_id}/result.mp4
models/{dest}                         e.g. models/diffusion_models/<file>.safetensors
config/workflow_api.json              user-exported ComfyUI workflow (API format); boot copies to /app/workflow_api.json
config/workflow_map.json              node map; boot copies to /app/workflow_map.json
```
Workflow files live in R2 (not in the image) so a workflow change never needs an image rebuild.

`dest` is the path relative to `ComfyUI/models/` (diffusion_models, text_encoders, vae, loras).

## 4. Queue message (Cloudflare Queue `h3-jobs`, content type `json`)

```json
{
  "job_id": "uuid-v4",
  "user_id": "string",
  "created_at": "2026-10-17T20:00:00Z",
  "tier": "768p",
  "duration_s": 10,
  "fps": 24,
  "source_key": "uploads/<job_id>/source.mp4",
  "characters": [
    {"image_key": "uploads/<job_id>/char1.png",
     "replace_description": "o homem de boné, à esquerda"}
  ],
  "prompt_extra": null,
  "seed": null
}
```
Rules: 1..3 characters; `duration_s` is 1..30 (int); `replace_description` is 3..200 chars (never a name).
Pull-consumer bodies arrive base64-encoded (json content type): the worker MUST base64-decode then JSON-parse.

Cloudflare HTTP pull consumer (verified in CF docs):
- pull: `POST https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/queues/{CF_QUEUE_ID}/messages/pull`
  body `{"visibility_timeout_ms": N, "batch_size": 1}`; response `result.messages[]` with
  `body, id, timestamp_ms, attempts, metadata, lease_id`, plus `result.message_backlog_count`.
- ack/retry: `POST .../messages/ack` body `{"acks":[{"lease_id":"..."}],"retries":[{"lease_id":"...","delay_seconds":60}]}`.
- auth: `Authorization: Bearer $CF_API_TOKEN` (permissions queues_read + queues_write).
- short polling: empty result means sleep and poll again. Unacked messages reappear after visibility timeout.

## 5. Status callback and heartbeat (worker -> API Worker)

Header on both: `X-Worker-Secret: $WORKER_SECRET`.

`POST {API_BASE_URL}/internal/jobs/{job_id}/status`
```json
{"status": "running|succeeded|failed", "instance_id": "123",
 "attempt": 1, "output_key": "outputs/<job_id>/result.mp4",
 "output_duration_s": 9.83, "width": 768, "height": 1382,
 "gpu_seconds": 512.4, "wall_seconds": 540.1, "error": null}
```
`POST {API_BASE_URL}/internal/heartbeat`
```json
{"instance_id": "123", "provider": "vast", "state": "booting|idle|busy",
 "idle_seconds": 0, "jobs_done": 0}
```
**Claim semantics (v1.2):** the `running` status call is the claim. The API answers `200 {"ok":true}` when the
job may run (state `queued`, or `running` by this same worker_id) and records `jobs.worker_id`;
it answers `409 {"ok":false,"reason":"..."}` when the job is already final, or `running` under another
worker, or unknown. On 409 the worker acks the queue message, deletes any downloaded files and skips the job
(no failed status, no GPU work). This makes duplicate queue deliveries harmless.

**Release on retry (v1.3):** status value `"retry"` is a fifth callback value (`running|succeeded|failed|retry`).
When a worker fails a job but attempts remain, it POSTs `status:"retry"` (with `error`) BEFORE asking the
queue to retry. The API accepts it only from the worker that owns the claim (`jobs.worker_id` = body
`instance_id`), sets `status='queued'`, clears `jobs.worker_id`, stores `error`, and increments `attempts`;
it answers 200. From any other worker, or for a final job, it answers 409 and the worker just acks.
Without this step the retry pulled by another worker would hit 409 forever and the job would stay `running`.

Settlement: API reserves `duration_s * PRICE_CENTS_PER_SECOND` at job creation; on `succeeded` it
charges `ceil(output_duration_s) * PRICE_CENTS_PER_SECOND` (never more than reserved) and refunds the
rest; on `failed` it refunds everything.

## 6. Worker environment variables

`CF_ACCOUNT_ID, CF_QUEUE_ID, CF_API_TOKEN, R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
R2_BUCKET, API_BASE_URL, WORKER_SECRET, INSTANCE_ID (default "local"), PROVIDER (default "vast"),
COMFY_URL (default http://127.0.0.1:8188), COMFY_INPUT_DIR (default /opt/ComfyUI/input),
WORKFLOW_TEMPLATE (default /app/workflow_api.json), WORKFLOW_MAP (default /app/workflow_map.json),
VISIBILITY_TIMEOUT_MS (default 2700000), POLL_INTERVAL_S (default 5), JOB_TIMEOUT_S (default 2400),
HEARTBEAT_INTERVAL_S (default 30), MAX_ATTEMPTS (default 3)`

**Instance id (v1.1):** the autoscaler generates `worker_id` (`w-<12 hex>`) BEFORE creating the Vast
instance and injects it as env `INSTANCE_ID` plus label `h3-swap-<worker_id>`. The worker sends this
value as `instance_id` in heartbeat/status. `workers.instance_id` = worker_id; the Vast contract id is
stored in the extra column `workers.vast_id` and is used only for destroy. We do not depend on any Vast
container-id env var (unverified).

## 7. ComfyUI integration (workflow is exported by the user, not authored here)

The user exports their working swap workflow from ComfyUI as **API format** into
`workflow_api.json`, and writes `workflow_map.json` telling the worker which node input to set:

```json
{
  "inputs": {
    "source_video":     {"node": "12", "field": "video"},
    "character_images": [{"node": "20", "field": "image"},
                         {"node": "21", "field": "image"},
                         {"node": "22", "field": "image"}],
    "prompt":           {"node": "30", "field": "text"},
    "seed":             {"node": "40", "field": "seed"},
    "length_frames":    {"node": "41", "field": "length"},
    "chunk_count":      {"node": "42", "field": "chunks"}
  },
  "output": {"node": "90", "kind": "videos"}
}
```
- `length_frames` and `chunk_count` are optional keys. Unused character slots (fewer than 3 characters)
  are simply not set; the map may list fewer than 3 slots.
- Values for `source_video` / `character_images` are file names relative to ComfyUI's input dir
  (the worker copies downloaded files there, naming them `{job_id}_source.mp4`, `{job_id}_char{n}.<ext>`).
- `output.kind` is the key inside `history[prompt_id].outputs[node]` that lists produced files
  (`videos`, `gifs` or `images`); each item has `filename`, `subfolder`, `type`.
- Prompt text (function `build_prompt(characters, prompt_extra)` in `worker/workflow.py`):
  for each character i (1-based):
  `Replace {replace_description} in <Video 1> with the person from <Picture {i}>.`
  joined by a space, then ` Keep the original motion, camera, background and audio.`,
  then ` {prompt_extra}` when present.
- `frames_for_duration(seconds, fps=24)`: smallest `17k+5` that is `>= seconds*fps`, capped at 362 per clip.
  `chunk_count(seconds) = ceil(seconds / 15)`.

## 8. D1 tables (owner: squad C, `api/schema.sql`)

`users(id TEXT PK, email TEXT, balance_cents INTEGER, created_at TEXT)`,
`api_keys(key_hash TEXT PK, user_id TEXT, created_at TEXT)`,
`jobs(id TEXT PK, user_id TEXT, status TEXT, duration_s INTEGER, reserved_cents INTEGER,
charged_cents INTEGER, source_key TEXT, output_key TEXT, error TEXT, attempts INTEGER,
gpu_seconds REAL, wall_seconds REAL, created_at TEXT, started_at TEXT, finished_at TEXT)`,
`workers(instance_id TEXT PK, provider TEXT, state TEXT, created_at TEXT,
last_heartbeat_at TEXT, idle_seconds INTEGER, jobs_done INTEGER)`.
Job statuses: `queued, running, succeeded, failed`.
v1.2 additions (additive): `jobs.worker_id TEXT` (set on claim), `workers.provider_ref TEXT` (Vast contract id,
or Salad container-group name; replaces the earlier `vast_id`), and
`provider_state(provider TEXT PK, cooldown_until TEXT, last_error TEXT)`.

## 9. API Worker endpoints (owner: squad C)

- `POST /v1/jobs` (Bearer API key; multipart: `source` video, `char1..char3` images, `meta` JSON with
  `duration_s`, `characters[].replace_description`, optional `prompt_extra`, `seed`).
  Validates, reserves credits, stores uploads in R2, inserts job, enqueues message (section 4).
- `GET /v1/jobs/{id}` status; `GET /v1/jobs/{id}/download` streams `result.mp4` (owner only).
- `GET /v1/me` balance in cents.
- `POST /internal/jobs/{id}/status`, `POST /internal/heartbeat` (X-Worker-Secret).
- `POST /internal/credits/add` (X-Admin-Secret; body `{user_id, cents}`) for manual top-ups.
- Cron (every minute) = autoscaler: backlog = count of jobs in `queued|running`; desired workers
  `min(MAX_WORKERS, ceil(backlog / JOBS_PER_WORKER))`; create Vast instances when below desired
  (workers booted in the last `BOOT_GRACE_S` count); destroy workers idle `>= IDLE_DESTROY_S` while backlog is 0;
  destroy workers with no heartbeat for `HEARTBEAT_LOST_S`. Never stop/start Vast instances:
  stopped instances may lose their GPU, always destroy and recreate.

### 9b. Providers with fallback (v1.2)

Provider interface (TypeScript, `api/src/providers/`): `create(workerId, env) -> providerRef`,
`destroy(providerRef)`, optional `listWorkerIds() -> string[]` for orphan detection.
Implementations: `vast`, `salad`. Env `PROVIDER_ORDER` (default `"vast,salad"`): the autoscaler tries providers
in order, skipping any in cooldown. When `create` throws or finds no offer, that provider goes into cooldown
`PROVIDER_COOLDOWN_S` (default 900) and the next provider is tried. A worker that never sends a heartbeat within
`BOOT_FAIL_S` (default 1500) is destroyed and its provider put in cooldown too. The order is configuration only:
flip to `"salad,vast"` if `bench/` proves Salad is cheaper at equal quality. Total workers across providers
never exceed `MAX_WORKERS`. The autoscaler injects `PROVIDER=<name>` and `INSTANCE_ID=<worker_id>` into each worker.

Lost-worker recovery: when a worker is destroyed for lost heartbeat or boot failure, every job with
`status='running' AND worker_id=<that worker>` goes back to `queued` and a NEW queue message is sent for it
(only if `attempts < MAX_ATTEMPTS`, else `failed` with full refund). The old message may reappear later; the claim
(409) makes that harmless.

## 10. Vast REST (verified in Vast docs; base `https://console.vast.ai/api/v0`, `Authorization: Bearer $VAST_API_KEY`)

- search: `POST /bundles/` JSON filters e.g. `{"verified":{"eq":true},"rentable":{"eq":true},"gpu_name":{"eq":"RTX 5090"},"num_gpus":{"eq":1},"direct_port_count":{"gte":1},"order":[["dph_total","asc"]],"type":"on-demand","limit":10}` -> `offers[]` with `id`.
- create: `PUT /asks/{offer_id}/` body `{"image","disk","onstart","env","label","runtype"}` -> `new_contract` = instance id.
  `env` is a Docker-flag STRING like `-e KEY=value -e KEY2=value2`. `onstart` is limited to 4048 chars.
- list: `GET /instances/` -> `instances[]`; one: `GET /instances/{id}/` -> `actual_status`.
- destroy: `DELETE /instances/{id}/`.
- "loading" status (image download) is not billed; models baked in the image pull for free on Vast.
- Offer field names beyond the ones above (e.g. RAM, download speed filters) are NOT verified:
  keep extra filters in env `VAST_OFFER_FILTER_JSON` and mark them `VERIFY` in docs.

## 10b. Salad REST (read in Salad docs 2026-10-17; base `https://api.salad.com/api/public`, header `Salad-Api-Key: $SALAD_API_KEY`)

- list GPU classes: `GET /organizations/{org}/gpu-classes` -> `items[]` `{id (uuid), name, prices[{priority,price}], ...}`;
  resolve the class id by `name` (env `SALAD_GPU_CLASS_NAME`, default `"RTX 5090"`; whether that class exists is UNVERIFIED).
- create: `POST /organizations/{org}/projects/{project}/containers` body
  `{"name","display_name","container":{"image","resources":{"cpu","memory"(MB),"gpu_classes":[uuid]},"environment_variables":{K:V}},
  "autostart_policy":true,"restart_policy":"on_failure","replicas":1}` -> 201. Name: 2-63 chars, lowercase letters/digits/hyphens,
  starts with a letter. Required fields: autostart_policy, container.image, container.resources.cpu/memory, name, replicas, restart_policy.
- get: `GET .../containers/{name}` (status in `current_state.status`, values UNVERIFIED).
- start: `POST .../containers/{name}/start` -> 202. delete: `DELETE .../containers/{name}` -> 202.
- Salad group name is deterministic: `h3-swap-<worker_id>` (worker_id is `w-<12 hex>`), so destroy needs no lookup.
- Env: `SALAD_API_KEY` (secret), `SALAD_ORG`, `SALAD_PROJECT`, `SALAD_GPU_CLASS_NAME`, `SALAD_CPU` (default 8), `SALAD_MEMORY_MB`
  (default 65536), `SALAD_PRIORITY` (optional; sent only if set). cpu/memory defaults and the `priority` request field are UNVERIFIED.
- UNVERIFIED: private-registry auth field (assume a public image or add it later), list-containers endpoint for orphan detection
  (implement best-effort, tolerate failure), RTX 5090 price (US$0.50/h is a third-party figure).
- Salad instances are interruptible and local disk is ephemeral: always use the `runtime` image target there and
  assume the instance can vanish at any time (covered by lost-worker recovery).

## 11. Hard rules for all squads

- No secrets in code or in committed files. Only `.env.example` placeholders.
- Do not invent model file names: if unsure write `TODO_VERIFY` and say so in docs.
- Type hints (Python 3.11) / strict TypeScript. Small modules, pure functions where possible.
- Tests first for logic (pytest). Run them and report the real output. Say UNVERIFIED for anything not run.
- Do not claim performance numbers. Cost/time numbers come only from `bench/` at run time.

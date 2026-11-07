# worker (GPU box)

One process per GPU box. It pulls one job at a time from the Cloudflare Queue `h3-jobs`,
claims the job with the API, downloads the inputs from R2, runs the user's ComfyUI API workflow,
uploads `outputs/{job_id}/result.mp4` to R2 and reports status and heartbeats to the API Worker.

Run it with `python -m worker` from the directory that contains the `worker/` package
(`/app` in the image). Dependencies: `pip install -r worker/requirements.txt`. `ffprobe`
must be on `PATH`. Configuration comes only from environment variables (CONTRACT section 6,
placeholders in `.env.example`).

## Modules

| Module | Role |
|---|---|
| `config.py` | `Config.from_env()`; secrets are excluded from `repr` |
| `queue_client.py` | Cloudflare HTTP pull consumer: pull, ack, retry |
| `job.py` | Validates a message body against CONTRACT section 4 |
| `workflow.py` | Prompt text, 17k+5 frame grid, chunk count, template patching (never mutates inputs) |
| `r2.py` | boto3 S3 client, `region_name="auto"`: download, upload, exists |
| `comfy_client.py` | ComfyUI `/prompt`, `/history/{id}`, `/view`, `/system_stats` |
| `media.py` | `ffprobe` wrapper returning duration, size, fps and audio presence |
| `callbacks.py` | Status POSTs (returns the API's answer), heartbeat POSTs, worker state, heartbeat thread |
| `runner.py` | `process_message` (one job end to end), `run_loop`, `run_forever` |

## Per-message flow (`runner.process_message`)

1. Validate the body. Invalid: post `failed`, ack, no retry.
2. **Claim:** post `running`. The answer decides what happens next (see Claim below).
3. Download the source and characters into `COMFY_INPUT_DIR` as `{job_id}_source.mp4` and `{job_id}_char{n}.<ext>`.
4. Load `WORKFLOW_TEMPLATE` and `WORKFLOW_MAP`, build the prompt, patch a copy of the template.
5. Queue the prompt, wait for the output node, download the file to a temp path, `ffprobe` it, upload to R2.
6. Post `succeeded` with the output facts, then ack.
7. Any transient failure: if `attempts < MAX_ATTEMPTS`, release and retry (see Release on retry below). Otherwise post `failed` and ack.
8. Input and temp files are removed in a `finally` block.

`run_loop` waits for `GET /system_stats` (state `booting`), then pulls one message at a time
(`idle` and `busy`). A heartbeat thread posts every `HEARTBEAT_INTERVAL_S`. On SIGTERM or
SIGINT no new pull starts; a message already pulled is finished.

## Claim (CONTRACT section 5, claim semantics v1.2)

The `running` status call is the claim. It is made before any R2 download.

| API answer to `running` | Worker action | Outcome |
|---|---|---|
| `200 {"ok":true}` | proceed to download and run | continues |
| `409 {"ok":false,"reason":...}` | ack the queue message; no download, no ComfyUI work, no further status | `skipped` (not done, not failed, not retried) |
| `5xx` or network error | retry path (60 s delay while attempts remain) | `retry` or `failed` |
| other `4xx` | retry path, same as above | `retry` or `failed` |

A `409` means the job is already final, is `running` under another worker_id, or is unknown.
This makes duplicate queue deliveries harmless.

409 on a final status is also `skipped`: the message is acked and nothing else is posted.
Any other 4xx on a final status is logged and acked (retrying a deterministic refusal would only burn GPU time).
5xx and network errors on a final status follow the transient path.

## Release on retry (CONTRACT section 5, v1.3)

When a transient failure happens and attempts remain, the worker releases the claim before it re-queues:

1. POST status `retry` with `error` (and `instance_id`, `attempt`). This happens first.
2. If the answer is `409`, the job is no longer ours. The worker acks the message and does not re-queue (outcome `skipped`).
3. If the POST fails with a network error, `5xx` or another `4xx`, the worker logs it and queues the retry anyway (best effort).
4. Otherwise (`200`), `queue.retry` with a 60 s delay.

The API clears `worker_id`, sets the job back to `queued`, and increments its attempt count. Any worker can then claim it.

The release is sent only when this worker holds the claim (the `running` call answered 200). If the claim itself failed
(network, 5xx or other 4xx), the worker never owned the job. It queues the retry without a release. A `409` to a
non-owner would not mean "not ours", and acking it would strand a queued job.

## Identity: INSTANCE_ID and PROVIDER

The autoscaler injects both (CONTRACT sections 6 and 9b). `INSTANCE_ID` is the `worker_id`
(`w-<12 hex>`). The API uses it as the claim owner, so it must be unique per box. The local
defaults (`local`, `vast`) are for development only: two boxes sharing `local` would pass each
other's claims. Nothing else in the worker depends on how these values are set.

## Limits (v1)

- **Retry after a claim is covered by release (v1.3).** A retry pulled by another worker can claim the job, because the release cleared the owner.
- **Claim answered with a 5xx but recorded by the API (edge, not handled).** If the API stores a claim and then answers 5xx,
  the job stays `running` under this worker without a release. A retry pulled by another worker gets `409` and is skipped,
  and the job waits for lost-worker recovery. The release cannot cover this case, because the worker cannot tell
  whether the claim was stored.
- **Lease length.** The pull API cannot extend a lease. `VISIBILITY_TIMEOUT_MS` must exceed the
  longest job including downloads and upload. Otherwise the message is redelivered and the job runs again
  (the claim answers 409 if the earlier run already holds it under the same worker, or 200 if it is the same worker).
- **No checkpoints.** A retry restarts the whole job.
- **At-least-once.** A crash after the upload but before the ack re-runs the job and overwrites the result key.
- **`gpu_seconds` is a proxy.** It is the wall time of the ComfyUI run (queueing and inference inside ComfyUI), not measured GPU time.
- **Undecodable bodies.** A body that is not valid base64 JSON cannot be acked by the worker. The pull raises, and the message returns after its lease expires until the queue's retry or dead-letter settings take over.
- **Failed final callback.** If the `failed` status POST fails with 5xx or a network error, the message is left unacked and returns after its lease expires.
- **ComfyUI disk.** Outputs stay in ComfyUI's output directory; the worker only reads them via `/view`. Long-lived boxes need a cleanup policy.
- **Output selection.** Only the first item of `outputs[output_node][kind]` is used.

## Environment variables

Required: `CF_ACCOUNT_ID`, `CF_QUEUE_ID`, `CF_API_TOKEN`, `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `API_BASE_URL`, `WORKER_SECRET`. Empty values count as unset.

Injected by the autoscaler: `INSTANCE_ID` (`local`), `PROVIDER` (`vast`).

Optional (default): `COMFY_URL` (`http://127.0.0.1:8188`),
`COMFY_INPUT_DIR` (`/opt/ComfyUI/input`), `WORKFLOW_TEMPLATE` (`/app/workflow_api.json`),
`WORKFLOW_MAP` (`/app/workflow_map.json`), `VISIBILITY_TIMEOUT_MS` (`2700000`),
`POLL_INTERVAL_S` (`5`), `JOB_TIMEOUT_S` (`2400`), `HEARTBEAT_INTERVAL_S` (`30`), `MAX_ATTEMPTS` (`3`).

`POLL_INTERVAL_S` is the queue and readiness poll. ComfyUI history is polled every 2 s.

## Tests

From the repo root: `python -m pytest worker/tests -q` (needs pytest, requests, boto3).
The tests use fakes and mocks only. They do not contact ComfyUI, R2, Cloudflare or a GPU.

## VERIFY (not checked against the real systems)

- Cloudflare pull response fields (`messages[].attempts` starting value, `lease_id`, base64 body), against live docs.
- ComfyUI `/history/{id}` shape: `status.status_str`, `status.completed`, `outputs[node][kind]`.
- ComfyUI `/prompt` error shape: `error.message` and `node_errors`.
- `/system_stats` as the readiness probe.
- The user-exported `workflow_api.json` and `workflow_map.json`: node ids and field names must match the export. Neither file is in this repo.
- R2 through boto3: the 404 code from `head_object`, and whether recent boto3 default checksums work with R2. If uploads fail, check the request checksum settings.
- Whether `ffprobe` is in the image and reports `duration` and `avg_frame_rate` for the H3 output.
- The meaning of `length` and `chunks` in the user's workflow nodes (the 17k+5 grid and the 15 s chunks are contract values).
- Whether `VISIBILITY_TIMEOUT_MS` exceeds the real worst-case job time.
- The API's exact 409 `reason` text, and that the `retry` status clears `worker_id` and increments attempts as CONTRACT v1.3 says.

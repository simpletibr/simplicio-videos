# docker/ — worker image (squad A)

Status: **UNVERIFIED**. The Dockerfile has not been built (no Docker daemon here), and the
entrypoint has not run against a real GPU or ComfyUI. What was run:
- `python -m pytest docker/tests -q`: 64 tests (planner, retries, waiver rules, CLI exit codes,
  entrypoint guard functions). Results are in the final report.
- `entrypoint.sh` in a scratch copy with fake ComfyUI and worker processes: SIGTERM forwarding,
  worker exit-status propagation, ComfyUI crash, port-in-use, bad `MODELS_MODE`, and the GPU
  warning (fake `nvidia-smi`).

## Files

| File | What it does |
|---|---|
| `Dockerfile` | Multi-stage image: `base` (apt, venv, torch cu130, boto3), `comfy` (ComfyUI + 3 custom nodes), `app` (worker/, entrypoint, fetcher), then the final targets `baked` and `runtime`. |
| `entrypoint.sh` | PID 1. Checks the GPU, warns on `PROVIDER=salad` + `MODELS_MODE=baked`, fetches from R2, checks the workflow files, starts ComfyUI on 127.0.0.1:8188, waits for `/system_stats`, runs `python -m worker`. Forwards SIGTERM and stops ComfyUI on exit. Sourcing it defines the functions without running them (used by the tests). |
| `fetch_models.py` | Reads `models.manifest.json` and downloads from R2 (4 parallel workers, 3 attempts, `.part` then rename, optional sha256). Pure planner: `plan_downloads()`. |
| `models.manifest.json` | 7 model entries (5 required, 2 `TODO_VERIFY` optional) and 2 workflow config entries (required, always re-fetched). |
| `build.sh` | Wrapper for `docker build` (target, tag, push, BuildKit secrets for `baked`). Usage: `docker/build.sh --help`. |
| `tests/test_fetch_models.py` | pytest suite for the planner, retries, verification, waiver, `dest_root`, scopes, and `main()`. |
| `tests/test_entrypoint.py` | pytest suite for the entrypoint guard functions (Salad warning, workflow check). |
| `README_docker.md` | This file. |

## Targets

- **`runtime`** (default, last stage). No model weights in the image. `entrypoint.sh` runs
  `fetch_models.py --scope all` at boot: weights plus workflow config.
- **`baked`**. Weights are fetched at build time by `fetch_models.py --scope models`, inside a
  `RUN --mount=type=secret` step. The secrets `r2_endpoint`, `r2_bucket`, `r2_access_key_id` and
  `r2_secret_access_key` are mounted at `/run/secrets/` for that one step. They are not in an `ARG`,
  an `ENV`, or a layer. The image sets `MODELS_MODE=baked`. At boot the entrypoint runs
  `--scope config`, so the workflow files are still fetched every time.

Build commands are in `build.sh` and in the Dockerfile header. Build from the repo root.

## Workflow config from R2

The worker reads `WORKFLOW_TEMPLATE` (default `/app/workflow_api.json`) and `WORKFLOW_MAP`
(default `/app/workflow_map.json`). The manifest has two entries for them:

| R2 key | Written to | Behaviour |
|---|---|---|
| `config/workflow_api.json` | `/app/workflow_api.json` | required, `always_download`: fetched at **every** boot, even when a file exists |
| `config/workflow_map.json` | `/app/workflow_map.json` | same |

Both entries use `dest_root: "/app"`. A `dest_root` overrides `--models-dir` as the target
directory. An entry with `dest_root` must use the `config/` key prefix. Workflow changes therefore
need no image rebuild.

**`WORKFLOW_OPTIONAL=1`** makes a file that is missing in R2 (HTTP 404) a warning instead of a
failure. The container keeps running, and the entrypoint prints a loud banner saying the worker
will fail every job. Any other failure (network, auth) is still fatal. A missing always-download
file also has any stale local copy removed, so an old workflow is never served. Without the env flag,
a missing workflow file is fatal and the container exits 1.

## Vast and Salad

- **Vast.ai**: the image pull during the "loading" phase is not billed (CONTRACT section 10), so
  `baked` moves the weight download into that unbilled window. `runtime` downloads about 36 GB
  from R2 at boot. That transfer is billed as instance time and egress.
- **Salad**: see the dedicated section below.

### Salad (CONTRACT section 10b)

- **Use the `runtime` target.** A Salad image is capped at 35 GB compressed. The baked image
  with weights is far larger, so `PROVIDER=salad` with `MODELS_MODE=baked` prints a WARNING. It
  does not fail, but the push or pull will probably fail first.
- **Ephemeral disk, and the instance can vanish at any time.** Nothing written to the local disk
  survives a restart. The autoscaler's lost-worker recovery re-queues the job.
- **Env vars arrive from the container group.** The autoscaler sets `PROVIDER`, `INSTANCE_ID`,
  the R2 variables and the others through the container's `environment_variables`. Nothing is
  read from a file.
- **Models and config are fetched from R2 at every start.** Each start downloads about 36 GB of
  weights plus the two workflow files. R2 charges no egress fee (Cloudflare's published R2 pricing;
  VERIFY current terms), so the cost is the boot time, not a transfer fee.
- The Salad container disk size is not in the contract. VERIFY that the 120 GB guidance below
  fits the container's disk setting.

## Disk sizing

Give the instance at least **120 GB** of disk. The breakdown:
about 36 GB of models, the CUDA base image and torch cu130 (several GB), ComfyUI and its
dependencies, and room for job inputs and outputs under `/opt/ComfyUI/input` and `/output`.
In `runtime` mode the models live in the container's writable layer, so size the disk for them too.

## Runtime environment

| Variable | Default | Used by |
|---|---|---|
| `MODELS_MODE` | `runtime` | entrypoint: `runtime` fetches weights and config, `baked` fetches config only |
| `PROVIDER` | `vast` | entrypoint: `salad` with `baked` prints a WARNING. The worker reads it too. |
| `WORKFLOW_OPTIONAL` | unset | fetcher and entrypoint: `1` makes a missing workflow file a warning |
| `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | none | fetcher (always needed: config is fetched at every boot) |
| `COMFY_DIR` | `/opt/ComfyUI` | entrypoint |
| `COMFY_LOG` | `/var/log/comfyui.log` | entrypoint (ComfyUI stdout and stderr) |
| `COMFY_READY_TIMEOUT_S` | `600` | entrypoint: how long to wait for `/system_stats` |
| `WORKFLOW_TEMPLATE`, `WORKFLOW_MAP` | `/app/workflow_api.json`, `/app/workflow_map.json` | entrypoint check, and the worker |
| worker variables | see CONTRACT section 6 | `python -m worker` |

Exit codes of `fetch_models.py`: 0 when there is no fatal failure (optional failures and waived
missing workflow files only warn), 1 when a required file failed, 2 for a bad manifest or missing
R2 variables. When everything in scope is already present and nothing is always-download, it exits
0 without creating an S3 client. The workflow entries are always in scope at boot, so the
R2 variables are always needed at boot.

## Proposed root `.dockerignore`

Docker reads `.dockerignore` only from the **build context root**, which is the repo root here.
`docker/.dockerignore` would be ignored, so this file is not created. To use it, copy the content
below to `/.dockerignore` (the repo root) yourself:

```
.git
**/.git
.env
.env.*
!.env.example
**/__pycache__
**/*.pyc
**/.pytest_cache
**/tests
.venv
node_modules
.wrangler
dist
*.log
api
bench
docs
```

`**/tests` also excludes `docker/tests` and `worker/tests`, which the image does not need.
The Dockerfile copies only `worker/`, `docker/entrypoint.sh`, `docker/fetch_models.py` and
`docker/models.manifest.json`.

## Process model (deviation from the brief)

The brief said `exec python -m worker`. This version starts the worker as a child and waits for it
instead. The reason: with `exec`, the shell is gone, so nothing is left to stop ComfyUI on SIGTERM
and it is orphaned. The shell stays as PID 1, forwards TERM to the worker, waits for the worker to
exit, and stops ComfyUI (TERM, then KILL after 30 s). The worker's exit status becomes the
container's exit status.

The worker entry point is `python -m worker` (`worker/__main__.py`). `worker/runner.py` has no
`main`, so it is not a valid entry point.

## VERIFY list

Everything below is unconfirmed. Check each item before relying on the image.

1. `nvidia/cuda:13.0.0-runtime-ubuntu24.04` exists on Docker Hub.
2. The PyTorch index `https://download.pytorch.org/whl/cu130` has torch, torchvision and torchaudio
   builds that match the ComfyUI master requirements. The image pins whatever pip resolves; there is
   no explicit torch version yet.
3. Ubuntu 24.04 `python3` is 3.12. The code is written for 3.11 (tested on 3.11.17 and 3.13 here).
   If an exact 3.11 is required, switch to `uv` or deadsnakes.
4. `comfyui-h3-continuum`: confirm the default branch and whether it has `requirements.txt`.
   The `main` and `master` refs are placeholders. Pin commit SHAs for production builds. The same
   applies to rgthree-comfy and ComfyUI-KJNodes.
5. Model file names. Only the 5 known names are used. The two `TODO_VERIFY_*` entries
   (`diffusion_models/TODO_VERIFY_ref2va_base.safetensors`, `loras/TODO_VERIFY_turbo_lora.safetensors`)
   must be checked on huggingface.co/Comfy-Org/MiniMax-H3. Until then they stay optional and their
   R2 keys probably 404.
6. R2 keys `models/<dest>` for the 5 known files exist in the bucket. Sizes and sha256 values are
   `null`, so there is no integrity check yet. Fill them in after upload.
7. R2 keys `config/workflow_api.json` and `config/workflow_map.json` exist in the bucket. Without them
   the container exits 1, or with `WORKFLOW_OPTIONAL=1` it runs and fails every job.
8. `nvidia-smi --query-gpu=compute_cap` works on the Vast and Salad hosts. If it does not, the
   entrypoint prints a warning and continues.
9. The boto3 range `>=1.34,<2` is not pinned to a tested version.
10. BuildKit features used: `# syntax=docker/dockerfile:1.7`, `COPY --chmod`, and secret mounts.
    Check the builder version that will run the build.
11. ComfyUI is started without `--disable-auto-launch`, exactly as the brief specified. Headless
    Linux should not try to open a browser. Confirm this on the target image.
12. A SIGTERM during the (long) runtime model fetch is handled late. Bash runs the trap only after
    the foreground `fetch_models.py` exits, so Docker's stop grace period (10 s by default) may
    expire first and SIGKILL the container. Model fetches are safe to restart.
13. Salad: R2 egress is free (Cloudflare's published R2 pricing, VERIFY current terms); the
    container disk size setting; boot time for a 36 GB download; the private-registry auth (the
    image must be pullable).
14. `docker build` has not been run. Results are UNVERIFIED.

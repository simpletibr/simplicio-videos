#!/usr/bin/env bash
# Container entrypoint for the h3-swap worker.
#
#   1. Print GPU name, VRAM and system RAM (informational; warns only below
#      16 GiB VRAM or 48 GiB system RAM). Never fails the boot.
#   2. Warn when PROVIDER=salad runs with MODELS_MODE=baked (never fails).
#   3. Fetch from R2: weights and config in runtime mode, only config in baked mode.
#      Workflow config (config/workflow_*.json) is re-fetched at every boot.
#      Optional alternatives are fetched only when FETCH_OPTIONAL is set.
#   4. Check the workflow files exist (loud warning when WORKFLOW_OPTIONAL=1).
#   5. Start ComfyUI headless on 127.0.0.1:8188, logging to COMFY_LOG.
#   6. Wait until /system_stats answers, then run `python -m worker` in the foreground.
#
# Signals: SIGTERM/SIGINT are forwarded to the worker, and ComfyUI is stopped on
# the way out. The worker is a child, not exec'd, so the shell stays as PID 1 and
# can stop ComfyUI; an exec would leave ComfyUI orphaned.
#
# Sourcing this file defines the functions without running anything (used by tests).
set -euo pipefail

readonly COMFY_DIR="${COMFY_DIR:-/opt/ComfyUI}"
readonly COMFY_HOST="127.0.0.1"
readonly COMFY_PORT="8188"
readonly COMFY_URL="http://${COMFY_HOST}:${COMFY_PORT}"
readonly COMFY_LOG="${COMFY_LOG:-/var/log/comfyui.log}"
readonly READY_TIMEOUT_S="${COMFY_READY_TIMEOUT_S:-600}"
readonly MODELS_MODE="${MODELS_MODE:-runtime}"
readonly MANIFEST="/app/models.manifest.json"
readonly MODELS_DIR="${COMFY_DIR}/models"
# FETCH_MODELS_PY is a test seam; the image always uses the default.
readonly FETCHER="${FETCH_MODELS_PY:-/app/fetch_models.py}"

COMFY_PID=""
WORKER_PID=""

log() {
  printf '[entrypoint] %s\n' "$*"
}

warn_banner() {
  cat >&2 <<EOF
================================================================================
$*
================================================================================
EOF
}

# Informational GPU and RAM report. Only prints; it never fails the boot.
# Thresholds are the guide values (16 GiB VRAM, 48 GiB system RAM) with 5% tolerance,
# because nvidia-smi and /proc/meminfo report slightly less than the nominal size.
check_gpu() {
  local smi="${NVIDIA_SMI:-nvidia-smi}"
  local meminfo="${MEMINFO_PATH:-/proc/meminfo}"
  local ram_kb ram_gib low_ram=0 low_vram=0 gpu_lines="" line name vram_mib vram_gib

  ram_kb="$(awk '/^MemTotal:/ { print $2 }' "${meminfo}" 2>/dev/null || true)"
  if [[ -n "${ram_kb}" ]]; then
    ram_gib="$(awk -v k="${ram_kb}" 'BEGIN { printf "%.1f", k / 1048576 }')"
    log "system RAM: ${ram_gib} GiB"
    if awk -v k="${ram_kb}" 'BEGIN { exit !(k + 0 < 48 * 1048576 * 0.95) }'; then
      low_ram=1
    fi
  else
    log "system RAM: unknown (${meminfo} not readable)"
  fi

  if ! command -v "${smi}" >/dev/null 2>&1; then
    log "GPU: nvidia-smi not found; no GPU is visible to this container"
  else
    gpu_lines="$("${smi}" --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null || true)"
    if [[ -z "${gpu_lines//[[:space:]]/}" ]]; then
      log "GPU: nvidia-smi reported no GPU"
    fi
  fi

  while IFS= read -r line; do
    [[ -n "${line//[[:space:]]/}" ]] || continue
    name="$(printf '%s' "${line%,*}" | sed 's/^ *//; s/ *$//')"
    vram_mib="${line##*,}"
    vram_mib="${vram_mib//[[:space:]]/}"
    vram_gib="$(awk -v m="${vram_mib}" 'BEGIN { printf "%.1f", m / 1024 }')"
    log "GPU: ${name}, VRAM ${vram_gib} GiB"
    if awk -v m="${vram_mib}" 'BEGIN { exit !(m + 0 < 16 * 1024 * 0.95) }'; then
      low_vram=1
    fi
  done <<< "${gpu_lines}"

  if (( low_vram || low_ram )); then
    warn_banner "WARNING: GPU VRAM or system RAM is below the guide (16 GiB VRAM, 48 GiB system RAM).
Offload needs system RAM; speed and VRAM at 768p are unmeasured.
Nothing was blocked: the container keeps booting."
  fi
  return 0
}

check_provider_mode() {
  if [[ "${PROVIDER:-vast}" == "salad" && "${MODELS_MODE}" == "baked" ]]; then
    warn_banner "WARNING: PROVIDER=salad with MODELS_MODE=baked.
Salad caps images at 35 GB compressed and a baked image is far larger, so the
push or pull will likely fail. Use the runtime image target on Salad.
Continuing anyway (this warning does not stop the container)."
  fi
  return 0
}

fetch_models() {
  local -a args=(--manifest "${MANIFEST}" --models-dir "${MODELS_DIR}")
  if [[ -n "${FETCH_OPTIONAL:-}" ]]; then
    args+=(--include-optional "${FETCH_OPTIONAL}")
    log "FETCH_OPTIONAL=${FETCH_OPTIONAL}: optional alternatives will be fetched if present in R2"
  fi
  if [[ "${MODELS_MODE}" == "baked" ]]; then
    # Weights were baked at build time. Workflow config is still fetched every boot.
    log "MODELS_MODE=baked: weights come from the image; fetching config/ from R2"
    python "${FETCHER}" "${args[@]}" --scope config
    return 0
  fi
  log "fetching models and config from R2 into ${MODELS_DIR}"
  python "${FETCHER}" "${args[@]}" --scope all
}

check_workflow_files() {
  local -a files=("${WORKFLOW_TEMPLATE:-/app/workflow_api.json}" "${WORKFLOW_MAP:-/app/workflow_map.json}")
  local -a missing=()
  local f
  for f in "${files[@]}"; do
    [[ -s "${f}" ]] || missing+=("${f}")
  done

  if (( ${#missing[@]} == 0 )); then
    log "workflow files present: ${files[*]}"
    return 0
  fi

  if [[ "${WORKFLOW_OPTIONAL:-0}" == "1" ]]; then
    warn_banner "WARNING: workflow file(s) missing: ${missing[*]}
WORKFLOW_OPTIONAL=1, so the container keeps running without them.
THE WORKER WILL FAIL EVERY JOB until config/workflow_api.json and
config/workflow_map.json exist in R2 and the container restarts."
    return 0
  fi

  log "ERROR: workflow file(s) missing: ${missing[*]}"
  return 1
}

start_comfy() {
  # Any listener on the port would make the readiness check pass for the wrong process.
  if (exec 3<>"/dev/tcp/${COMFY_HOST}/${COMFY_PORT}") 2>/dev/null; then
    log "ERROR: ${COMFY_HOST}:${COMFY_PORT} is already in use before ComfyUI starts"
    return 1
  fi
  mkdir -p "$(dirname "${COMFY_LOG}")"
  log "starting ComfyUI on ${COMFY_URL} (log: ${COMFY_LOG})"
  # The subshell execs python, so $! is the ComfyUI PID itself.
  (cd "${COMFY_DIR}" && exec python main.py --listen "${COMFY_HOST}" --port "${COMFY_PORT}") \
    >"${COMFY_LOG}" 2>&1 &
  COMFY_PID=$!
}

wait_for_comfy() {
  local deadline=$((SECONDS + READY_TIMEOUT_S))
  while true; do
    # Check liveness first, so a dead ComfyUI is never mistaken for a ready one.
    if ! kill -0 "${COMFY_PID}" 2>/dev/null; then
      log "ERROR: ComfyUI exited before it became ready; last log lines:"
      tail -n 80 "${COMFY_LOG}" >&2 || true
      return 1
    fi
    if curl -fsS --max-time 5 "${COMFY_URL}/system_stats" >/dev/null 2>&1; then
      break
    fi
    if (( SECONDS >= deadline )); then
      log "ERROR: ComfyUI not ready after ${READY_TIMEOUT_S}s; last log lines:"
      tail -n 80 "${COMFY_LOG}" >&2 || true
      return 1
    fi
    sleep 2
  done
  log "ComfyUI is ready"
}

stop_comfy() {
  if [[ -z "${COMFY_PID}" ]] || ! kill -0 "${COMFY_PID}" 2>/dev/null; then
    return 0
  fi
  log "stopping ComfyUI (pid ${COMFY_PID})"
  kill -TERM "${COMFY_PID}" 2>/dev/null || true
  local i
  for i in $(seq 1 30); do
    kill -0 "${COMFY_PID}" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "${COMFY_PID}" 2>/dev/null; then
    log "ComfyUI did not exit within 30 s; sending SIGKILL"
    kill -KILL "${COMFY_PID}" 2>/dev/null || true
  fi
  wait "${COMFY_PID}" 2>/dev/null || true
  COMFY_PID=""
}

on_term() {
  log "received termination signal"
  if [[ -n "${WORKER_PID}" ]]; then
    # The wait loop in main returns once the worker has exited.
    kill -TERM "${WORKER_PID}" 2>/dev/null || true
  else
    stop_comfy
    exit 143
  fi
}

main() {
  case "${MODELS_MODE}" in
    runtime|baked) ;;
    *) log "ERROR: MODELS_MODE must be 'runtime' or 'baked', got '${MODELS_MODE}'"; exit 2 ;;
  esac

  trap on_term TERM INT
  trap stop_comfy EXIT

  check_gpu
  check_provider_mode
  fetch_models
  check_workflow_files
  start_comfy
  wait_for_comfy

  log "starting worker"
  cd /app
  python -m worker &
  WORKER_PID=$!

  # wait returns early when a trapped signal arrives while the worker still runs;
  # loop until the worker is really gone. Capture the status with && / || so that
  # $? is the worker's status, not the status of an if-compound.
  local rc=0
  while true; do
    wait "${WORKER_PID}" && rc=0 || rc=$?
    if ! kill -0 "${WORKER_PID}" 2>/dev/null; then
      break
    fi
  done
  log "worker exited with status ${rc}"
  exit "${rc}"
}

# Run only when executed directly, not when sourced by the tests.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi

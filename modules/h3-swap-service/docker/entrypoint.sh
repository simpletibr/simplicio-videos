#!/usr/bin/env bash
# Container entrypoint for the h3-swap worker.
#
#   1. Warn when the GPU is below compute capability 12.0 (NVFP4 needs Blackwell).
#   2. Warn when PROVIDER=salad runs with MODELS_MODE=baked (never fails).
#   3. Fetch from R2: all of it in runtime mode, only workflow config in baked mode.
#      Workflow config (config/workflow_*.json) is re-fetched at every boot.
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

check_gpu() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    log "WARNING: nvidia-smi not found; no GPU is visible to this container"
    return 0
  fi
  local caps
  caps="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null || true)"
  if [[ -z "${caps}" ]]; then
    log "WARNING: could not read compute capability from nvidia-smi"
    return 0
  fi
  log "GPU compute capability: $(printf '%s' "${caps}" | tr '\n' ' ')"

  local cap
  while IFS= read -r cap; do
    cap="${cap//[[:space:]]/}"
    if awk -v c="${cap}" 'BEGIN { exit !(c + 0 < 12.0) }'; then
      warn_banner "WARNING: GPU compute capability ${cap} is below 12.0.
The NVFP4 text encoder (qwen3vl_32b_minimax_h3_nvfp4_awq) needs Blackwell
(RTX 50xx / RTX PRO 6000). Expect load or inference failures on this GPU."
    fi
  done <<< "${caps}"
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
  if [[ "${MODELS_MODE}" == "baked" ]]; then
    # Weights were baked at build time. Workflow config is still fetched every boot.
    log "MODELS_MODE=baked: weights come from the image; fetching config/ from R2"
    python /app/fetch_models.py --manifest "${MANIFEST}" --models-dir "${MODELS_DIR}" --scope config
    return 0
  fi
  log "fetching models and config from R2 into ${MODELS_DIR}"
  python /app/fetch_models.py --manifest "${MANIFEST}" --models-dir "${MODELS_DIR}" --scope all
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

"""Queue consumer: runs one swap job at a time through ComfyUI (CONTRACT sections 4-7)."""

from __future__ import annotations

import json
import logging
import os
import signal
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from worker import media
from worker.callbacks import CallbackError, HeartbeatThread, StatusPoster, StatusResult, WorkerState
from worker.comfy_client import ComfyClient, ComfyError
from worker.config import Config
from worker.job import InvalidJob, Job, is_valid_job_id, parse_job
from worker.queue_client import QueueClient, QueueError, QueueMessage
from worker.r2 import R2
from worker.workflow import (
    WorkflowError,
    apply_workflow,
    build_prompt,
    chunk_count,
    frames_for_duration,
    output_spec,
)

log = logging.getLogger("worker.runner")

RETRY_DELAY_S = 60
MAX_ERROR_CHARS = 2000
RESULT_CONTENT_TYPE = "video/mp4"


class QueueLike(Protocol):
    def pull(self, batch_size: int = 1, visibility_timeout_ms: int = 2700000) -> list[QueueMessage]: ...

    def ack(self, lease_ids: list[str]) -> None: ...

    def retry(self, lease_id: str, delay_seconds: int = 60) -> None: ...


class StorageLike(Protocol):
    def download(self, key: str, dest_path: str) -> None: ...

    def upload(self, src_path: str, key: str, content_type: str | None = None) -> None: ...


class ComfyLike(Protocol):
    def ready(self) -> bool: ...

    def queue_prompt(self, workflow: dict[str, Any]) -> str: ...

    def wait_for_outputs(self, prompt_id: str, output_node: str, kind: str, poll_s: float = 2.0) -> list[dict[str, Any]]: ...

    def download_output(self, item: dict[str, Any]) -> bytes: ...


class PosterLike(Protocol):
    def post_status(self, job_id: str, payload: dict[str, Any]) -> StatusResult: ...

    def post_heartbeat(self, payload: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class JobResult:
    job_id: str | None
    # "succeeded" | "failed" | "retry" | "skipped" (API answered 409: not ours to run or settle)
    outcome: str
    output_key: str | None = None
    error: str | None = None


@dataclass
class Deps:
    """Everything process_message touches. Tests pass fakes for each part."""

    config: Config
    queue: QueueLike
    r2: StorageLike
    comfy: ComfyLike
    poster: PosterLike
    state: WorkerState = field(default_factory=WorkerState)
    clock: Callable[[], float] = time.monotonic
    probe: Callable[[str], dict[str, Any]] = media.probe


@dataclass(frozen=True)
class _Produced:
    output_key: str
    info: dict[str, Any]
    gpu_seconds: float


def process_message(msg: QueueMessage, deps: Deps) -> JobResult:
    """Handle one queue message: validate, claim, download, run, upload, settle, ack.

    Outcomes:
      "succeeded" - output uploaded and settled, message acked.
      "failed"    - final failure reported, message acked.
      "retry"     - re-queued with a 60 s delay; nothing final reported.
      "skipped"   - the API answered 409 (claim or settlement refused): message acked,
                    no further status, no R2 or ComfyUI work. Not counted as done or failed.
    """
    started = deps.clock()
    raw_job_id = msg.body.get("job_id")

    try:
        job = parse_job(msg.body)
    except InvalidJob as exc:
        error = _describe(exc)
        job_id = raw_job_id if is_valid_job_id(raw_job_id) else None
        if job_id is not None:
            _report_final(deps, job_id, _payload("failed", deps, msg, error=error, wall_seconds=deps.clock() - started))
        deps.queue.ack([msg.lease_id])
        log.warning("rejected invalid job message %s: %s", msg.id, error)
        return JobResult(job_id=job_id, outcome="failed", error=error)

    job_id = job.job_id

    # Claim before any R2 download, so a job the API will refuse costs no egress or time.
    try:
        claim = deps.poster.post_status(job_id, _payload("running", deps, msg))
    except CallbackError as exc:
        return _retry_or_fail(job_id, msg, deps, started, _describe(exc), owned=False)
    if claim.status_code == 409:
        return _skip(job_id, msg, deps, f"claim refused: {claim.reason or 'HTTP 409'}")
    if not claim.ok:
        return _retry_or_fail(
            job_id, msg, deps, started, f"claim refused: HTTP {claim.status_code}", owned=False
        )

    cleanup: list[str] = []
    try:
        produced = _produce(job, deps, cleanup)
        settled = _report_final(
            deps,
            job_id,
            _payload(
                "succeeded",
                deps,
                msg,
                output_key=produced.output_key,
                output_duration_s=float(produced.info["duration_s"]),
                width=int(produced.info["width"]),
                height=int(produced.info["height"]),
                gpu_seconds=produced.gpu_seconds,
                wall_seconds=deps.clock() - started,
            ),
        )
    except Exception as exc:
        return _retry_or_fail(job_id, msg, deps, started, _describe(exc), owned=True)
    finally:
        _remove_files(cleanup)

    if settled.status_code == 409:
        return _skip(job_id, msg, deps, f"settlement refused: {settled.reason or 'HTTP 409'}")
    deps.queue.ack([msg.lease_id])
    log.info("job %s succeeded in %.1fs", job_id, deps.clock() - started)
    return JobResult(job_id=job_id, outcome="succeeded", output_key=produced.output_key)


def _skip(job_id: str, msg: QueueMessage, deps: Deps, reason: str) -> JobResult:
    deps.queue.ack([msg.lease_id])
    log.info("job %s skipped: %s", job_id, reason)
    return JobResult(job_id=job_id, outcome="skipped", error=reason)


def _release(job_id: str, msg: QueueMessage, deps: Deps, error: str) -> StatusResult | None:
    """POST status "retry" so the API clears the claim (CONTRACT section 5, v1.3).

    Returns the API's answer, or None when there was no usable answer (network error,
    5xx or other 4xx). The caller queues the retry in that case anyway.
    """
    try:
        result = deps.poster.post_status(job_id, _payload("retry", deps, msg, error=error))
    except CallbackError as exc:
        log.warning("release of job %s failed, queueing the retry anyway: %s", job_id, exc)
        return None
    if not result.ok and result.status_code != 409:
        log.warning("API answered HTTP %d to release of job %s, queueing the retry anyway", result.status_code, job_id)
        return None
    return result


def _retry_or_fail(
    job_id: str, msg: QueueMessage, deps: Deps, started: float, error: str, *, owned: bool
) -> JobResult:
    """Transient-failure policy: retry while attempts remain, else report failed and ack.

    `owned` is True once this worker holds the claim. Only the claim owner may release it,
    so the release POST is sent only then. Without a claim, a 409 would not mean "not ours"
    and acking would strand a queued job.
    """
    if msg.attempts < deps.config.max_attempts:
        log.warning("job %s attempt %d failed, retrying in %ds: %s", job_id, msg.attempts, RETRY_DELAY_S, error)
        if owned:
            released = _release(job_id, msg, deps, error)
            if released is not None and released.status_code == 409:
                return _skip(job_id, msg, deps, f"release refused: {released.reason or 'HTTP 409'}")
        deps.queue.retry(msg.lease_id, delay_seconds=RETRY_DELAY_S)
        return JobResult(job_id=job_id, outcome="retry", error=error)
    log.error("job %s failed after %d attempts: %s", job_id, msg.attempts, error)
    final = _report_final(deps, job_id, _payload("failed", deps, msg, error=error, wall_seconds=deps.clock() - started))
    if final.status_code == 409:
        return _skip(job_id, msg, deps, f"failure report refused: {final.reason or 'HTTP 409'}")
    deps.queue.ack([msg.lease_id])
    return JobResult(job_id=job_id, outcome="failed", error=error)


def _report_final(deps: Deps, job_id: str, payload: dict[str, Any]) -> StatusResult:
    """Post a final status. A 4xx answer is logged; transient errors propagate to the caller."""
    result = deps.poster.post_status(job_id, payload)
    if not result.ok:
        log.warning(
            "API answered HTTP %d to %s status for job %s: %s",
            result.status_code,
            payload["status"],
            job_id,
            result.reason,
        )
    return result


def _produce(job: Job, deps: Deps, cleanup: list[str]) -> _Produced:
    cfg = deps.config
    source_name = f"{job.job_id}_source.mp4"
    source_path = os.path.join(cfg.comfy_input_dir, source_name)
    cleanup.append(source_path)
    deps.r2.download(job.source_key, source_path)

    image_names: list[str] = []
    for index, character in enumerate(job.characters, start=1):
        name = f"{job.job_id}_char{index}{character.image_ext}"
        path = os.path.join(cfg.comfy_input_dir, name)
        cleanup.append(path)
        deps.r2.download(character.image_key, path)
        image_names.append(name)

    template = _load_json_object(cfg.workflow_template)
    mapping = _load_json_object(cfg.workflow_map)
    node, kind = output_spec(mapping)
    workflow = apply_workflow(
        template,
        mapping,
        source_video=source_name,
        character_images=image_names,
        prompt=build_prompt(
            [{"replace_description": c.replace_description} for c in job.characters],
            job.prompt_extra,
        ),
        seed=job.seed,
        length_frames=frames_for_duration(job.duration_s, job.fps),
        chunk_count=chunk_count(job.duration_s),
    )

    started = deps.clock()
    prompt_id = deps.comfy.queue_prompt(workflow)
    items = deps.comfy.wait_for_outputs(prompt_id, node, kind)
    # Proxy only: wall time of the ComfyUI run, not measured GPU time.
    gpu_seconds = deps.clock() - started
    if not items:
        raise ComfyError(f"ComfyUI produced no '{kind}' output")

    data = deps.comfy.download_output(items[0])
    fd, out_path = tempfile.mkstemp(prefix=f"{job.job_id}_", suffix=".mp4")
    cleanup.append(out_path)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)

    info = deps.probe(out_path)
    output_key = f"outputs/{job.job_id}/result.mp4"
    deps.r2.upload(out_path, output_key, content_type=RESULT_CONTENT_TYPE)
    return _Produced(output_key=output_key, info=info, gpu_seconds=gpu_seconds)


def _payload(status: str, deps: Deps, msg: QueueMessage, **fields: Any) -> dict[str, Any]:
    """Status callback body in the CONTRACT section 5 shape; unset fields are null."""
    payload: dict[str, Any] = {
        "status": status,
        "instance_id": deps.config.instance_id,
        "attempt": msg.attempts,
        "output_key": None,
        "output_duration_s": None,
        "width": None,
        "height": None,
        "gpu_seconds": None,
        "wall_seconds": None,
        "error": None,
    }
    payload.update(fields)
    return payload


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]


def _load_json_object(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise WorkflowError(f"{path} must contain a JSON object")
    return data


def _remove_files(paths: list[str]) -> None:
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("could not remove %s: %s", path, exc)


def run_loop(deps: Deps, stop: threading.Event) -> None:
    """Wait for ComfyUI, then pull and process one message at a time until `stop` is set.

    A stop request never interrupts a message already pulled; no new pull starts after it.
    """
    cfg = deps.config
    while not stop.is_set() and not deps.comfy.ready():
        log.info("waiting for ComfyUI at %s", cfg.comfy_url)
        stop.wait(cfg.poll_interval_s)
    if stop.is_set():
        return
    deps.state.mark_idle()
    log.info("worker %s ready", cfg.instance_id)

    while not stop.is_set():
        try:
            messages = deps.queue.pull(batch_size=1, visibility_timeout_ms=cfg.visibility_timeout_ms)
        except QueueError as exc:
            log.warning("queue pull failed: %s", exc)
            stop.wait(cfg.poll_interval_s)
            continue
        except Exception:
            log.exception("unexpected error while pulling from the queue")
            stop.wait(cfg.poll_interval_s)
            continue
        if not messages:
            stop.wait(cfg.poll_interval_s)
            continue
        _handle(messages[0], deps)
    log.info("stop requested, exiting")


def _handle(msg: QueueMessage, deps: Deps) -> None:
    deps.state.mark_busy()
    finished = False
    try:
        result = process_message(msg, deps)
        finished = result.outcome in ("succeeded", "failed")
    except Exception:
        log.exception("unhandled error on message %s; left unacked for redelivery", msg.id)
    finally:
        deps.state.mark_idle(job_done=finished)


def install_signal_handlers(stop: threading.Event) -> None:
    def request_stop(signum: int, _frame: object) -> None:
        log.info("signal %s received: finishing the current job, then exiting", signum)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, request_stop)
        except ValueError:
            log.debug("cannot install handler for signal %s outside the main thread", sig)


def build_deps(config: Config) -> Deps:
    return Deps(
        config=config,
        queue=QueueClient(config.cf_account_id, config.cf_queue_id, config.cf_api_token),
        r2=R2(config.r2_endpoint, config.r2_access_key_id, config.r2_secret_access_key, config.r2_bucket),
        comfy=ComfyClient(config.comfy_url, timeout_s=config.job_timeout_s),
        poster=StatusPoster(config.api_base_url, config.worker_secret),
    )


def run_forever(config: Config) -> None:
    stop = threading.Event()
    install_signal_handlers(stop)
    deps = build_deps(config)
    heartbeat = HeartbeatThread(
        deps.poster, deps.state, config.instance_id, config.provider, config.heartbeat_interval_s, stop
    )
    heartbeat.start()
    log.info("worker %s starting (provider=%s)", config.instance_id, config.provider)
    try:
        run_loop(deps, stop)
    finally:
        stop.set()
        heartbeat.join(timeout=5)

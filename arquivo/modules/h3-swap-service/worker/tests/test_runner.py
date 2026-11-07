from __future__ import annotations

import itertools
import json
import os
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import boto3
import pytest

from worker import runner
from worker.callbacks import CallbackError, StatusPoster, StatusResult, WorkerState
from worker.comfy_client import ComfyClient, ComfyError
from worker.config import Config
from worker.media import MediaError
from worker.queue_client import QueueClient, QueueError, QueueMessage
from worker.r2 import R2, R2Error
from worker.runner import Deps, build_deps, process_message, run_loop
from worker.tests.fixtures import JOB_ID, MAP, TEMPLATE, valid_body

SOURCE_KEY = f"uploads/{JOB_ID}/source.mp4"
CHAR1_KEY = f"uploads/{JOB_ID}/char1.png"
RESULT_KEY = f"outputs/{JOB_ID}/result.mp4"
PROBE_INFO: dict[str, Any] = {"duration_s": 9.83, "width": 768, "height": 1382, "fps": 24.0, "has_audio": True}


class FakeQueue:
    """Scripted pull results: a list (returned), an exception (raised) or a callable (called)."""

    def __init__(self, pulls: list[Any] | None = None) -> None:
        self.pull_script = list(pulls or [])
        self.pull_calls = 0
        self.acks: list[list[str]] = []
        self.retries: list[tuple[str, int]] = []
        self.events: list[tuple[str, str]] = []

    def pull(self, batch_size: int = 1, visibility_timeout_ms: int = 2700000) -> list[QueueMessage]:
        self.pull_calls += 1
        step = self.pull_script.pop(0) if self.pull_script else []
        if isinstance(step, BaseException):
            raise step
        if callable(step):
            return step()
        return step

    def ack(self, lease_ids: list[str]) -> None:
        self.acks.append(list(lease_ids))
        self.events.append(("queue", "ack"))

    def retry(self, lease_id: str, delay_seconds: int = 60) -> None:
        self.retries.append((lease_id, delay_seconds))
        self.events.append(("queue", "retry"))


class FakeR2:
    def __init__(self, objects: dict[str, bytes], fail_upload: bool = False) -> None:
        self.objects = dict(objects)
        self.fail_upload = fail_upload
        self.downloads: list[tuple[str, str]] = []
        self.uploads: list[tuple[str, str | None, bytes]] = []
        self.events: list[tuple[str, str]] = []

    def download(self, key: str, dest_path: str) -> None:
        self.downloads.append((key, dest_path))
        self.events.append(("download", key))
        if key not in self.objects:
            raise R2Error(f"missing {key}")
        with open(dest_path, "wb") as handle:
            handle.write(self.objects[key])

    def upload(self, src_path: str, key: str, content_type: str | None = None) -> None:
        if self.fail_upload:
            raise R2Error("upload refused")
        with open(src_path, "rb") as handle:
            self.uploads.append((key, content_type, handle.read()))


class FakeComfy:
    def __init__(self, error: BaseException | None = None, ready_script: list[bool] | None = None) -> None:
        self.error = error
        self.ready_script = list(ready_script or [])
        self.ready_calls = 0
        self.workflows: list[dict[str, Any]] = []
        self.waited: tuple[str, str, str] | None = None

    def ready(self) -> bool:
        self.ready_calls += 1
        return self.ready_script.pop(0) if self.ready_script else True

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        self.workflows.append(workflow)
        return "pid-1"

    def wait_for_outputs(self, prompt_id: str, output_node: str, kind: str, poll_s: float = 2.0) -> list[dict[str, Any]]:
        self.waited = (prompt_id, output_node, kind)
        if self.error is not None:
            raise self.error
        return [{"filename": "out_00001.mp4", "subfolder": "", "type": "output"}]

    def download_output(self, item: dict[str, Any]) -> bytes:
        return b"MP4-OUT"


class FakePoster:
    """Records every status call in order.

    `errors` raise CallbackError (transient: 5xx or network). `refusals` answer with
    ok=False and the given HTTP code (409 or other 4xx).
    """

    def __init__(self, errors: dict[str, BaseException] | None = None, refusals: dict[str, int] | None = None) -> None:
        self.errors: dict[str, BaseException] = dict(errors or {})
        self.refusals: dict[str, int] = dict(refusals or {})
        self.statuses: list[tuple[str, dict[str, Any]]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.events: list[tuple[str, str]] = []

    def post_status(self, job_id: str, payload: dict[str, Any]) -> StatusResult:
        status = payload["status"]
        self.events.append(("status", status))
        self.statuses.append((job_id, payload))
        if status in self.errors:
            raise self.errors[status]
        if status in self.refusals:
            return StatusResult(ok=False, status_code=self.refusals[status], reason=f"refused {status}")
        return StatusResult(ok=True, status_code=200, reason=None)

    def post_heartbeat(self, payload: dict[str, Any]) -> None:
        self.heartbeats.append(payload)

    def sequence(self) -> list[str]:
        return [payload["status"] for _, payload in self.statuses]


class FakeProbe:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.paths: list[str] = []
        self.existed: list[bool] = []

    def __call__(self, path: str) -> dict[str, Any]:
        self.paths.append(path)
        self.existed.append(os.path.exists(path))
        if self.error is not None:
            raise self.error
        return dict(PROBE_INFO)


@dataclass
class Harness:
    deps: Deps
    queue: FakeQueue
    r2: FakeR2
    comfy: FakeComfy
    poster: FakePoster
    probe: FakeProbe
    input_dir: Path
    events: list[tuple[str, str]]


def _ticking_clock() -> Callable[[], float]:
    ticks = itertools.count()

    def clock() -> float:
        return float(next(ticks))

    return clock


def make_harness(
    tmp_path: Path,
    *,
    max_attempts: int = 3,
    objects: dict[str, bytes] | None = None,
    queue: FakeQueue | None = None,
    comfy: FakeComfy | None = None,
    poster: FakePoster | None = None,
    probe: FakeProbe | None = None,
    r2: FakeR2 | None = None,
) -> Harness:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    template_path = tmp_path / "workflow_api.json"
    template_path.write_text(json.dumps(TEMPLATE), encoding="utf-8")
    map_path = tmp_path / "workflow_map.json"
    map_path.write_text(json.dumps(MAP), encoding="utf-8")
    config = Config(
        cf_account_id="acct",
        cf_queue_id="queue",
        cf_api_token="token",
        r2_endpoint="https://r2.example.com",
        r2_access_key_id="ak",
        r2_secret_access_key="sk",
        r2_bucket="bucket",
        api_base_url="https://api.example.com",
        worker_secret="ws",
        instance_id="inst-7",
        comfy_input_dir=str(input_dir),
        workflow_template=str(template_path),
        workflow_map=str(map_path),
        max_attempts=max_attempts,
        poll_interval_s=0.001,
    )
    clock = _ticking_clock()
    fake_r2 = r2 or FakeR2(objects if objects is not None else {SOURCE_KEY: b"SRC", CHAR1_KEY: b"IMG1"})
    fake_comfy = comfy or FakeComfy()
    fake_poster = poster or FakePoster()
    fake_queue = queue or FakeQueue()
    fake_probe = probe or FakeProbe()
    events: list[tuple[str, str]] = []
    fake_r2.events = events
    fake_poster.events = events
    fake_queue.events = events
    deps = Deps(
        config=config,
        queue=fake_queue,
        r2=fake_r2,
        comfy=fake_comfy,
        poster=fake_poster,
        state=WorkerState(clock=clock),
        clock=clock,
        probe=fake_probe,
    )
    return Harness(
        deps=deps,
        queue=fake_queue,
        r2=fake_r2,
        comfy=fake_comfy,
        poster=fake_poster,
        probe=fake_probe,
        input_dir=input_dir,
        events=events,
    )


def make_message(body: dict[str, Any] | None = None, attempts: int = 1, lease: str = "lease-1") -> QueueMessage:
    return QueueMessage(
        id="msg-1",
        lease_id=lease,
        attempts=attempts,
        body=valid_body() if body is None else body,
    )


def _set_and_return(stop: threading.Event, value: Any) -> Any:
    stop.set()
    return value


def test_success_downloads_inputs_runs_comfy_uploads_result_and_acks(tmp_path: Path) -> None:
    h = make_harness(tmp_path)
    result = process_message(make_message(), h.deps)

    assert result.outcome == "succeeded"
    assert result.output_key == RESULT_KEY
    assert h.r2.downloads == [
        (SOURCE_KEY, str(h.input_dir / f"{JOB_ID}_source.mp4")),
        (CHAR1_KEY, str(h.input_dir / f"{JOB_ID}_char1.png")),
    ]

    workflow = h.comfy.workflows[0]
    assert workflow["12"]["inputs"]["video"] == f"{JOB_ID}_source.mp4"
    assert workflow["20"]["inputs"]["image"] == f"{JOB_ID}_char1.png"
    assert workflow["21"]["inputs"]["image"] == "ph2.png"
    assert workflow["30"]["inputs"]["text"].startswith(
        "Replace o homem de boné, à esquerda in <Video 1> with the person from <Picture 1>."
    )
    assert workflow["41"]["inputs"]["length"] == 243
    assert workflow["42"]["inputs"]["chunks"] == 1
    assert isinstance(workflow["40"]["inputs"]["seed"], int)
    assert h.comfy.waited == ("pid-1", "90", "videos")

    assert h.r2.uploads == [(RESULT_KEY, "video/mp4", b"MP4-OUT")]
    assert h.poster.sequence() == ["running", "succeeded"]
    assert all(job_id == JOB_ID for job_id, _ in h.poster.statuses)
    final = h.poster.statuses[-1][1]
    assert final["instance_id"] == "inst-7"
    assert final["attempt"] == 1
    assert final["output_key"] == RESULT_KEY
    assert final["output_duration_s"] == 9.83
    assert final["width"] == 768
    assert final["height"] == 1382
    assert final["error"] is None
    assert final["gpu_seconds"] > 0
    assert final["wall_seconds"] >= final["gpu_seconds"]

    assert h.queue.acks == [["lease-1"]]
    assert h.queue.retries == []
    assert os.listdir(h.input_dir) == []
    assert h.probe.existed == [True]
    assert not os.path.exists(h.probe.paths[0])


def test_two_characters_fill_two_slots_and_keep_extension(tmp_path: Path) -> None:
    char2_key = f"uploads/{JOB_ID}/char2.webp"
    objects = {SOURCE_KEY: b"SRC", CHAR1_KEY: b"A", char2_key: b"B"}
    body = valid_body(
        characters=[
            {"image_key": CHAR1_KEY, "replace_description": "the man in red"},
            {"image_key": char2_key, "replace_description": "the woman on the left"},
        ]
    )
    h = make_harness(tmp_path, objects=objects)
    result = process_message(make_message(body), h.deps)

    assert result.outcome == "succeeded"
    workflow = h.comfy.workflows[0]
    assert workflow["20"]["inputs"]["image"] == f"{JOB_ID}_char1.png"
    assert workflow["21"]["inputs"]["image"] == f"{JOB_ID}_char2.webp"
    assert workflow["22"]["inputs"]["image"] == "ph3.png"
    assert "<Picture 2>" in workflow["30"]["inputs"]["text"]
    assert (char2_key, str(h.input_dir / f"{JOB_ID}_char2.webp")) in h.r2.downloads


def test_invalid_body_fails_immediately_without_retry(tmp_path: Path) -> None:
    h = make_harness(tmp_path)
    result = process_message(make_message(valid_body(duration_s=0), attempts=1), h.deps)

    assert result.outcome == "failed"
    assert h.r2.downloads == []
    assert h.queue.retries == []
    assert h.queue.acks == [["lease-1"]]
    assert h.poster.sequence() == ["failed"]
    assert "duration_s" in h.poster.statuses[0][1]["error"]


def test_invalid_body_without_usable_job_id_is_acked_silently(tmp_path: Path) -> None:
    body = valid_body()
    del body["job_id"]
    h = make_harness(tmp_path)
    result = process_message(make_message(body), h.deps)

    assert result.outcome == "failed"
    assert result.job_id is None
    assert h.poster.statuses == []
    assert h.queue.acks == [["lease-1"]]


@pytest.mark.parametrize("attempts", [1, 2])
def test_comfy_failure_requeues_with_60s_delay_while_attempts_remain(tmp_path: Path, attempts: int) -> None:
    h = make_harness(tmp_path, comfy=FakeComfy(error=ComfyError("boom")))
    result = process_message(make_message(attempts=attempts), h.deps)

    assert result.outcome == "retry"
    assert h.queue.retries == [("lease-1", 60)]
    assert h.queue.acks == []
    assert h.poster.sequence() == ["running", "retry"]
    assert os.listdir(h.input_dir) == []


def test_final_attempt_failure_posts_failed_status_and_acks(tmp_path: Path) -> None:
    h = make_harness(tmp_path, comfy=FakeComfy(error=ComfyError("boom")))
    result = process_message(make_message(attempts=3), h.deps)

    assert result.outcome == "failed"
    assert result.error is not None and "boom" in result.error
    assert h.poster.sequence() == ["running", "failed"]
    final = h.poster.statuses[-1][1]
    assert final["attempt"] == 3
    assert "ComfyError" in final["error"] and "boom" in final["error"]
    assert h.queue.acks == [["lease-1"]]
    assert h.queue.retries == []
    assert os.listdir(h.input_dir) == []


def test_missing_source_object_is_retried(tmp_path: Path) -> None:
    h = make_harness(tmp_path, objects={CHAR1_KEY: b"IMG1"})
    result = process_message(make_message(attempts=1), h.deps)
    assert result.outcome == "retry"
    assert h.queue.retries == [("lease-1", 60)]
    assert os.listdir(h.input_dir) == []


def test_probe_failure_is_retried(tmp_path: Path) -> None:
    h = make_harness(tmp_path, probe=FakeProbe(error=MediaError("bad mp4")))
    result = process_message(make_message(attempts=1), h.deps)
    assert result.outcome == "retry"
    assert "bad mp4" in (result.error or "")


def test_temp_output_is_removed_when_upload_fails(tmp_path: Path) -> None:
    h = make_harness(tmp_path, r2=FakeR2({SOURCE_KEY: b"SRC", CHAR1_KEY: b"IMG1"}, fail_upload=True))
    result = process_message(make_message(attempts=1), h.deps)
    assert result.outcome == "retry"
    assert len(h.probe.paths) == 1
    assert not os.path.exists(h.probe.paths[0])
    assert os.listdir(h.input_dir) == []


# Claim semantics (CONTRACT section 5, v1.2): the `running` status call is the claim.


def test_claim_is_posted_before_any_r2_download(tmp_path: Path) -> None:
    h = make_harness(tmp_path)
    process_message(make_message(), h.deps)
    assert h.events[0] == ("status", "running")
    assert h.events.index(("download", SOURCE_KEY)) > h.events.index(("status", "running"))


def test_claim_200_proceeds_to_download_run_and_settle(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster())
    result = process_message(make_message(), h.deps)

    assert result.outcome == "succeeded"
    assert h.poster.statuses[0][1]["status"] == "running"
    assert h.r2.downloads != []
    assert len(h.comfy.workflows) == 1
    assert h.poster.sequence() == ["running", "succeeded"]


def test_claim_409_skips_without_touching_r2_or_comfy(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster(refusals={"running": 409}))
    result = process_message(make_message(), h.deps)

    assert result.outcome == "skipped"
    assert h.r2.downloads == []
    assert h.r2.uploads == []
    assert h.comfy.workflows == []
    assert h.comfy.waited is None
    assert h.probe.paths == []
    assert h.poster.sequence() == ["running"]
    assert h.queue.acks == [["lease-1"]]
    assert h.queue.retries == []
    assert os.listdir(h.input_dir) == []


@pytest.mark.parametrize("attempts", [1, 3])
def test_claim_409_is_skipped_not_failed_at_any_attempt(tmp_path: Path, attempts: int) -> None:
    h = make_harness(tmp_path, poster=FakePoster(refusals={"running": 409}))
    result = process_message(make_message(attempts=attempts), h.deps)
    assert result.outcome == "skipped"
    assert h.poster.sequence() == ["running"]
    assert h.queue.acks == [["lease-1"]]


@pytest.mark.parametrize("attempts", [1, 2])
@pytest.mark.parametrize(
    "error",
    [CallbackError("POST status returned HTTP 500"), CallbackError("POST status failed: connection reset")],
)
def test_claim_transient_failure_goes_to_retry_path(tmp_path: Path, attempts: int, error: CallbackError) -> None:
    h = make_harness(tmp_path, poster=FakePoster(errors={"running": error}))
    result = process_message(make_message(attempts=attempts), h.deps)

    assert result.outcome == "retry"
    assert h.queue.retries == [("lease-1", 60)]
    assert h.queue.acks == []
    assert h.poster.sequence() == ["running"]
    assert h.r2.downloads == []
    assert h.comfy.workflows == []


def test_claim_transient_failure_on_final_attempt_posts_failed_and_acks(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster(errors={"running": CallbackError("POST status returned HTTP 500")}))
    result = process_message(make_message(attempts=3), h.deps)

    assert result.outcome == "failed"
    assert h.poster.sequence() == ["running", "failed"]
    assert "CallbackError" in h.poster.statuses[-1][1]["error"]
    assert h.queue.acks == [["lease-1"]]
    assert h.queue.retries == []
    assert h.r2.downloads == []


def test_claim_refused_with_other_4xx_goes_to_retry_path(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster(refusals={"running": 401}))
    result = process_message(make_message(attempts=1), h.deps)

    assert result.outcome == "retry"
    assert h.queue.retries == [("lease-1", 60)]
    assert h.r2.downloads == []


def test_succeeded_status_refused_with_409_is_skipped_and_acked(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster(refusals={"succeeded": 409}))
    result = process_message(make_message(), h.deps)

    assert result.outcome == "skipped"
    assert h.poster.sequence() == ["running", "succeeded"]
    assert h.queue.acks == [["lease-1"]]
    assert h.queue.retries == []


def test_succeeded_status_refused_with_400_is_acked_not_retried(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster(refusals={"succeeded": 400}))
    result = process_message(make_message(), h.deps)

    assert result.outcome == "succeeded"
    assert h.queue.acks == [["lease-1"]]
    assert h.queue.retries == []


def test_succeeded_status_transient_failure_retries_while_attempts_remain(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster(errors={"succeeded": CallbackError("POST status returned HTTP 500")}))
    result = process_message(make_message(attempts=1), h.deps)
    assert result.outcome == "retry"
    assert h.queue.retries == [("lease-1", 60)]
    assert h.queue.acks == []


def test_failed_status_refused_with_409_on_final_attempt_is_skipped(tmp_path: Path) -> None:
    h = make_harness(
        tmp_path,
        comfy=FakeComfy(error=ComfyError("boom")),
        poster=FakePoster(refusals={"failed": 409}),
    )
    result = process_message(make_message(attempts=3), h.deps)
    assert result.outcome == "skipped"
    assert h.queue.acks == [["lease-1"]]


def test_failed_callback_on_final_attempt_propagates_without_ack(tmp_path: Path) -> None:
    h = make_harness(
        tmp_path,
        comfy=FakeComfy(error=ComfyError("boom")),
        poster=FakePoster(errors={"failed": CallbackError("POST status returned HTTP 500")}),
    )
    with pytest.raises(CallbackError):
        process_message(make_message(attempts=3), h.deps)
    assert h.queue.acks == []
    assert h.queue.retries == []
    assert os.listdir(h.input_dir) == []


# Release on retry (CONTRACT section 5, v1.3): the retry status is posted before the queue retry.


def test_retry_status_is_posted_before_queue_retry(tmp_path: Path) -> None:
    h = make_harness(tmp_path, comfy=FakeComfy(error=ComfyError("boom")))
    result = process_message(make_message(attempts=1), h.deps)

    assert result.outcome == "retry"
    assert h.poster.sequence() == ["running", "retry"]
    assert h.events.index(("status", "retry")) < h.events.index(("queue", "retry"))
    release = h.poster.statuses[-1][1]
    assert release["instance_id"] == "inst-7"
    assert release["attempt"] == 1
    assert "boom" in release["error"]
    assert h.queue.retries == [("lease-1", 60)]
    assert h.queue.acks == []


def test_retry_status_409_acks_and_does_not_requeue(tmp_path: Path) -> None:
    h = make_harness(
        tmp_path,
        comfy=FakeComfy(error=ComfyError("boom")),
        poster=FakePoster(refusals={"retry": 409}),
    )
    result = process_message(make_message(attempts=1), h.deps)

    assert result.outcome == "skipped"
    assert h.poster.sequence() == ["running", "retry"]
    assert h.queue.retries == []
    assert h.queue.acks == [["lease-1"]]
    assert ("queue", "retry") not in h.events


@pytest.mark.parametrize(
    "errors, refusals",
    [
        ({"retry": CallbackError("POST status returned HTTP 500")}, {}),
        ({"retry": CallbackError("POST status failed: connection reset")}, {}),
        ({}, {"retry": 401}),
    ],
)
def test_retry_status_network_5xx_or_other_4xx_still_requeues(
    tmp_path: Path, errors: dict[str, BaseException], refusals: dict[str, int]
) -> None:
    h = make_harness(
        tmp_path,
        comfy=FakeComfy(error=ComfyError("boom")),
        poster=FakePoster(errors=errors, refusals=refusals),
    )
    result = process_message(make_message(attempts=1), h.deps)

    assert result.outcome == "retry"
    assert h.queue.retries == [("lease-1", 60)]
    assert h.queue.acks == []
    assert h.events.index(("status", "retry")) < h.events.index(("queue", "retry"))


def test_claim_transient_failure_sends_no_release_because_job_is_not_owned(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster(errors={"running": CallbackError("POST status returned HTTP 500")}))
    result = process_message(make_message(attempts=1), h.deps)

    assert result.outcome == "retry"
    assert h.poster.sequence() == ["running"]
    assert h.queue.retries == [("lease-1", 60)]


def test_succeeded_status_transient_failure_releases_then_requeues(tmp_path: Path) -> None:
    h = make_harness(tmp_path, poster=FakePoster(errors={"succeeded": CallbackError("POST status returned HTTP 500")}))
    result = process_message(make_message(attempts=1), h.deps)
    assert result.outcome == "retry"
    assert h.poster.sequence() == ["running", "succeeded", "retry"]
    assert h.events.index(("status", "retry")) < h.events.index(("queue", "retry"))


# run_loop


def test_run_loop_does_not_pull_once_stop_is_requested(tmp_path: Path) -> None:
    h = make_harness(tmp_path)
    stop = threading.Event()
    stop.set()
    run_loop(h.deps, stop)
    assert h.queue.pull_calls == 0


def test_run_loop_finishes_in_flight_message_then_exits(tmp_path: Path) -> None:
    stop = threading.Event()
    queue = FakeQueue([lambda: _set_and_return(stop, [make_message()])])
    h = make_harness(tmp_path, queue=queue)
    run_loop(h.deps, stop)

    assert h.queue.pull_calls == 1
    assert h.queue.acks == [["lease-1"]]
    snap = h.deps.state.snapshot()
    assert snap.state == "idle"
    assert snap.jobs_done == 1


def test_run_loop_keeps_looping_after_a_skipped_job_and_does_not_count_it(tmp_path: Path) -> None:
    stop = threading.Event()
    queue = FakeQueue([lambda: [make_message()], lambda: _set_and_return(stop, [])])
    h = make_harness(tmp_path, queue=queue, poster=FakePoster(refusals={"running": 409}))
    run_loop(h.deps, stop)

    assert queue.pull_calls == 2
    assert queue.acks == [["lease-1"]]
    assert h.comfy.workflows == []
    snap = h.deps.state.snapshot()
    assert snap.state == "idle"
    assert snap.jobs_done == 0


def test_run_loop_survives_queue_errors_and_empty_pulls(tmp_path: Path) -> None:
    stop = threading.Event()
    queue = FakeQueue([QueueError("queue down"), [], lambda: _set_and_return(stop, [])])
    h = make_harness(tmp_path, queue=queue)
    run_loop(h.deps, stop)
    assert h.queue.pull_calls == 3
    assert h.queue.acks == []


def test_run_loop_waits_for_comfy_before_pulling(tmp_path: Path) -> None:
    stop = threading.Event()
    queue = FakeQueue([lambda: _set_and_return(stop, [])])
    comfy = FakeComfy(ready_script=[False, False, True])
    h = make_harness(tmp_path, queue=queue, comfy=comfy)
    run_loop(h.deps, stop)
    assert comfy.ready_calls == 3
    assert queue.pull_calls == 1


def test_install_signal_handlers_sets_stop_on_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: dict[int, Callable[[int, object], None]] = {}
    monkeypatch.setattr(runner.signal, "signal", lambda sig, handler: registered.__setitem__(sig, handler))
    stop = threading.Event()
    runner.install_signal_handlers(stop)
    assert signal.SIGTERM in registered
    registered[signal.SIGTERM](signal.SIGTERM, None)
    assert stop.is_set()


def test_build_deps_wires_clients_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(boto3, "client", MagicMock(name="boto3.client"))
    config = make_harness(tmp_path).deps.config
    deps = build_deps(config)
    assert deps.config is config
    assert isinstance(deps.queue, QueueClient)
    assert isinstance(deps.r2, R2)
    assert isinstance(deps.comfy, ComfyClient)
    assert isinstance(deps.poster, StatusPoster)

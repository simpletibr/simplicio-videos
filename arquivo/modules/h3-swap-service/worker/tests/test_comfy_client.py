from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from worker import comfy_client
from worker.comfy_client import ComfyClient, ComfyError

BASE = "http://gpu.test:8188"
OUTPUT_ITEM = {"filename": "out_00001.mp4", "subfolder": "", "type": "output"}


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = "" if payload is None else str(payload)

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time(monkeypatch: pytest.MonkeyPatch) -> FakeTime:
    fake = FakeTime()
    monkeypatch.setattr(comfy_client.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(comfy_client.time, "sleep", fake.sleep)
    return fake


def _session(**returns: Any) -> MagicMock:
    session = MagicMock(spec=requests.Session)
    for name, value in returns.items():
        getattr(session, name).return_value = value
    return session


def _completed_history(outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "pid-1": {
            "outputs": outputs,
            "status": {"completed": True, "status_str": "success", "messages": []},
        }
    }


def test_queue_prompt_posts_workflow_and_returns_prompt_id() -> None:
    session = _session(post=FakeResponse(200, {"prompt_id": "pid-1", "number": 3, "node_errors": {}}))
    workflow = {"12": {"class_type": "LoadVideo", "inputs": {"video": "a.mp4"}}}
    assert ComfyClient(BASE, session=session).queue_prompt(workflow) == "pid-1"
    args, kwargs = session.post.call_args
    assert args[0] == f"{BASE}/prompt"
    assert kwargs["json"]["prompt"] == workflow
    uuid.UUID(kwargs["json"]["client_id"])


def test_queue_prompt_strips_trailing_slash_from_base_url() -> None:
    session = _session(post=FakeResponse(200, {"prompt_id": "pid-1"}))
    ComfyClient(BASE + "/", session=session).queue_prompt({})
    assert session.post.call_args.args[0] == f"{BASE}/prompt"


def test_queue_prompt_raises_on_node_errors_in_success_response() -> None:
    payload = {
        "prompt_id": "pid-1",
        "node_errors": {"90": {"errors": [{"message": "Value not in list", "details": "codec"}]}},
    }
    session = _session(post=FakeResponse(200, payload))
    with pytest.raises(ComfyError, match="Value not in list") as info:
        ComfyClient(BASE, session=session).queue_prompt({})
    assert "90" in str(info.value)


def test_queue_prompt_rejected_with_400_reports_error_and_node_errors() -> None:
    payload = {
        "error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
        "node_errors": {"90": {"errors": [{"message": "Required input is missing", "details": "seed"}]}},
    }
    session = _session(post=FakeResponse(400, payload))
    with pytest.raises(ComfyError) as info:
        ComfyClient(BASE, session=session).queue_prompt({})
    assert "Prompt outputs failed validation" in str(info.value)
    assert "Required input is missing" in str(info.value)


def test_queue_prompt_without_prompt_id_raises() -> None:
    session = _session(post=FakeResponse(200, {"node_errors": {}}))
    with pytest.raises(ComfyError):
        ComfyClient(BASE, session=session).queue_prompt({})


def test_queue_prompt_connection_error_raises_comfy_error() -> None:
    session = MagicMock(spec=requests.Session)
    session.post.side_effect = requests.ConnectionError("refused")
    with pytest.raises(ComfyError):
        ComfyClient(BASE, session=session).queue_prompt({})


def test_queue_prompt_server_error_without_json_raises() -> None:
    session = _session(post=FakeResponse(500, None))
    with pytest.raises(ComfyError, match="500"):
        ComfyClient(BASE, session=session).queue_prompt({})


def test_wait_for_outputs_polls_until_completed(fake_time: FakeTime) -> None:
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = [
        FakeResponse(200, {}),
        FakeResponse(
            200,
            {"pid-1": {"outputs": {}, "status": {"completed": False, "status_str": "running"}}},
        ),
        FakeResponse(200, _completed_history({"90": {"videos": [OUTPUT_ITEM]}})),
    ]
    items = ComfyClient(BASE, session=session).wait_for_outputs("pid-1", "90", "videos", poll_s=2.0)
    assert items == [OUTPUT_ITEM]
    assert fake_time.sleeps == [2.0, 2.0]
    assert session.get.call_args_list[0].args[0] == f"{BASE}/history/pid-1"


def test_wait_for_outputs_raises_on_execution_error(fake_time: FakeTime) -> None:
    history = {
        "pid-1": {
            "outputs": {},
            "status": {
                "completed": True,
                "status_str": "error",
                "messages": [["execution_error", {"exception_message": "CUDA out of memory"}]],
            },
        }
    }
    session = _session(get=FakeResponse(200, history))
    with pytest.raises(ComfyError, match="CUDA out of memory"):
        ComfyClient(BASE, session=session).wait_for_outputs("pid-1", "90", "videos")


def test_wait_for_outputs_times_out(fake_time: FakeTime) -> None:
    session = _session(get=FakeResponse(200, {}))
    client = ComfyClient(BASE, timeout_s=10, session=session)
    with pytest.raises(ComfyError, match="timed out"):
        client.wait_for_outputs("pid-1", "90", "videos", poll_s=2.0)
    assert fake_time.now >= 10


def test_wait_for_outputs_missing_output_node_raises(fake_time: FakeTime) -> None:
    session = _session(get=FakeResponse(200, _completed_history({"5": {"videos": [OUTPUT_ITEM]}})))
    with pytest.raises(ComfyError):
        ComfyClient(BASE, session=session).wait_for_outputs("pid-1", "90", "videos")


def test_wait_for_outputs_missing_kind_raises(fake_time: FakeTime) -> None:
    session = _session(get=FakeResponse(200, _completed_history({"90": {"images": [OUTPUT_ITEM]}})))
    with pytest.raises(ComfyError):
        ComfyClient(BASE, session=session).wait_for_outputs("pid-1", "90", "videos")


def test_wait_for_outputs_http_error_raises(fake_time: FakeTime) -> None:
    session = _session(get=FakeResponse(500, None))
    with pytest.raises(ComfyError):
        ComfyClient(BASE, session=session).wait_for_outputs("pid-1", "90", "videos")


def test_download_output_returns_bytes_with_query_parameters() -> None:
    session = _session(get=FakeResponse(200, None, content=b"MP4BYTES"))
    item = {"filename": "out_00001.mp4", "subfolder": "vid", "type": "output"}
    assert ComfyClient(BASE, session=session).download_output(item) == b"MP4BYTES"
    args, kwargs = session.get.call_args
    assert args[0] == f"{BASE}/view"
    assert kwargs["params"] == {"filename": "out_00001.mp4", "subfolder": "vid", "type": "output"}


def test_download_output_requires_filename() -> None:
    session = _session(get=FakeResponse(200, None, content=b""))
    with pytest.raises(ComfyError):
        ComfyClient(BASE, session=session).download_output({"subfolder": "", "type": "output"})


def test_download_output_http_error_raises() -> None:
    session = _session(get=FakeResponse(404, None))
    with pytest.raises(ComfyError):
        ComfyClient(BASE, session=session).download_output(OUTPUT_ITEM)


def test_ready_true_when_system_stats_answers() -> None:
    session = _session(get=FakeResponse(200, {"system": {}}))
    assert ComfyClient(BASE, session=session).ready() is True
    assert session.get.call_args.args[0] == f"{BASE}/system_stats"


def test_ready_false_when_connection_refused() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("refused")
    assert ComfyClient(BASE, session=session).ready() is False


def test_ready_false_on_error_status() -> None:
    session = _session(get=FakeResponse(503, None))
    assert ComfyClient(BASE, session=session).ready() is False

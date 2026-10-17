from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from worker.callbacks import CallbackError, HeartbeatThread, StatusPoster, StatusResult, WorkerState


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload


def _poster(response: Any) -> tuple[StatusPoster, MagicMock]:
    session = MagicMock(spec=requests.Session)
    session.post.return_value = response
    return StatusPoster("https://api.example.com/", "SECRET-WS", session=session), session


def test_post_status_200_is_ok_and_targets_status_endpoint() -> None:
    poster, session = _poster(FakeResponse(200, {"ok": True}))
    result = poster.post_status("job-1", {"status": "running"})
    assert result == StatusResult(ok=True, status_code=200, reason=None)
    args, kwargs = session.post.call_args
    assert args[0] == "https://api.example.com/internal/jobs/job-1/status"
    assert kwargs["json"] == {"status": "running"}
    assert kwargs["headers"]["X-Worker-Secret"] == "SECRET-WS"


def test_post_status_409_is_a_refusal_carrying_the_reason_not_an_exception() -> None:
    poster, _ = _poster(FakeResponse(409, {"ok": False, "reason": "running under w-222"}))
    result = poster.post_status("job-1", {"status": "running"})
    assert result == StatusResult(ok=False, status_code=409, reason="running under w-222")


def test_post_status_409_without_json_body_has_no_reason() -> None:
    poster, _ = _poster(FakeResponse(409, None))
    assert poster.post_status("job-1", {"status": "running"}) == StatusResult(
        ok=False, status_code=409, reason=None
    )


def test_post_status_other_4xx_is_a_refusal_not_an_exception() -> None:
    poster, _ = _poster(FakeResponse(401, None))
    assert poster.post_status("job-1", {"status": "running"}) == StatusResult(
        ok=False, status_code=401, reason=None
    )


def test_post_status_truncates_long_reason() -> None:
    poster, _ = _poster(FakeResponse(409, {"ok": False, "reason": "x" * 500}))
    result = poster.post_status("job-1", {"status": "running"})
    assert result.reason is not None and len(result.reason) == 200


def test_post_status_5xx_raises_callback_error_without_leaking_secret() -> None:
    poster, _ = _poster(FakeResponse(500, None))
    with pytest.raises(CallbackError) as info:
        poster.post_status("job-1", {"status": "running"})
    assert "SECRET-WS" not in str(info.value)


def test_post_status_network_error_raises_callback_error() -> None:
    poster, session = _poster(None)
    session.post.side_effect = requests.ConnectionError("reset")
    with pytest.raises(CallbackError):
        poster.post_status("job-1", {"status": "running"})


def test_post_heartbeat_targets_heartbeat_endpoint() -> None:
    poster, session = _poster(FakeResponse(200, {"ok": True}))
    poster.post_heartbeat({"state": "idle"})
    assert session.post.call_args.args[0] == "https://api.example.com/internal/heartbeat"


def test_post_heartbeat_error_status_raises() -> None:
    poster, _ = _poster(FakeResponse(500, None))
    with pytest.raises(CallbackError):
        poster.post_heartbeat({"state": "idle"})


def test_worker_state_tracks_idle_seconds_and_jobs_done() -> None:
    now = {"t": 100.0}
    state = WorkerState(clock=lambda: now["t"])

    snap = state.snapshot()
    assert (snap.state, snap.idle_seconds, snap.jobs_done) == ("booting", 0, 0)

    state.mark_idle()
    now["t"] = 130.0
    snap = state.snapshot()
    assert (snap.state, snap.idle_seconds, snap.jobs_done) == ("idle", 30, 0)

    state.mark_busy()
    now["t"] = 200.0
    snap = state.snapshot()
    assert (snap.state, snap.idle_seconds) == ("busy", 0)

    state.mark_idle(job_done=True)
    assert state.snapshot().jobs_done == 1
    now["t"] = 205.0
    snap = state.snapshot()
    assert (snap.state, snap.idle_seconds, snap.jobs_done) == ("idle", 5, 1)


def test_heartbeat_payload_matches_contract_and_failures_are_swallowed() -> None:
    poster = MagicMock()
    poster.post_heartbeat.side_effect = CallbackError("api down")
    state = WorkerState(clock=lambda: 0.0)
    state.mark_idle()
    beat = HeartbeatThread(poster, state, "inst-1", "vast", 30, threading.Event())
    assert beat.beat_once() is False
    poster.post_heartbeat.assert_called_once_with(
        {"instance_id": "inst-1", "provider": "vast", "state": "idle", "idle_seconds": 0, "jobs_done": 0}
    )


def test_heartbeat_survives_unexpected_poster_error() -> None:
    poster = MagicMock()
    poster.post_heartbeat.side_effect = RuntimeError("boom")
    beat = HeartbeatThread(poster, WorkerState(clock=lambda: 0.0), "inst-1", "vast", 30, threading.Event())
    assert beat.beat_once() is False


def test_heartbeat_run_beats_once_then_returns_when_stop_already_set() -> None:
    stop = threading.Event()
    stop.set()
    poster = MagicMock()
    state = WorkerState(clock=lambda: 0.0)
    HeartbeatThread(poster, state, "inst-1", "vast", 30, stop).run()
    poster.post_heartbeat.assert_called_once()
    assert poster.post_heartbeat.call_args.args[0]["state"] == "booting"

"""Status and heartbeat callbacks to the API Worker (CONTRACT section 5), plus worker state.

The `running` status call is the claim (claim semantics v1.2): 200 means the job may run,
409 means it is already final, owned by another worker, or unknown.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger("worker.callbacks")
_HTTP_TIMEOUT_S = 15
_REASON_MAX_CHARS = 200


class CallbackError(RuntimeError):
    """Transient failure: the API Worker was unreachable or answered 5xx."""


@dataclass(frozen=True)
class StatusResult:
    """The API's answer to a status POST that was not a 5xx or a network failure."""

    ok: bool
    status_code: int
    reason: str | None = None


class StatusPoster:
    def __init__(self, api_base_url: str, worker_secret: str, session: requests.Session | None = None) -> None:
        self._base = api_base_url.rstrip("/")
        self._headers = {"X-Worker-Secret": worker_secret, "Content-Type": "application/json"}
        self._session = session if session is not None else requests.Session()

    def post_status(self, job_id: str, payload: dict[str, Any]) -> StatusResult:
        """POST a status. 2xx is ok; any other 4xx is a refusal (409 = not ours to run or settle).

        Raises CallbackError on 5xx or a network failure, which callers treat as transient.
        """
        status_code, body = self._send(f"/internal/jobs/{job_id}/status", payload)
        if status_code >= 500:
            raise CallbackError(f"status POST for job {job_id} returned HTTP {status_code}")
        ok = 200 <= status_code < 300
        return StatusResult(ok=ok, status_code=status_code, reason=None if ok else _reason(body))

    def post_heartbeat(self, payload: dict[str, Any]) -> None:
        status_code, _ = self._send("/internal/heartbeat", payload)
        if status_code >= 400:
            raise CallbackError(f"heartbeat returned HTTP {status_code}")

    def _send(self, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
        try:
            response = self._session.post(
                f"{self._base}{path}", json=payload, headers=self._headers, timeout=_HTTP_TIMEOUT_S
            )
        except requests.RequestException as exc:
            raise CallbackError(f"POST {path} failed: {exc}") from exc
        return response.status_code, _json_or_none(response)


def _json_or_none(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _reason(body: Any) -> str | None:
    if isinstance(body, dict) and isinstance(body.get("reason"), str):
        return str(body["reason"])[:_REASON_MAX_CHARS]
    return None


@dataclass(frozen=True)
class StateSnapshot:
    state: str
    idle_seconds: int
    jobs_done: int


class WorkerState:
    """Thread-safe booting -> idle <-> busy state shared by the loop and the heartbeat thread."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._state = "booting"
        self._idle_since: float | None = None
        self._jobs_done = 0

    def mark_idle(self, job_done: bool = False) -> None:
        with self._lock:
            if job_done:
                self._jobs_done += 1
            self._state = "idle"
            self._idle_since = self._clock()

    def mark_busy(self) -> None:
        with self._lock:
            self._state = "busy"
            self._idle_since = None

    def snapshot(self) -> StateSnapshot:
        with self._lock:
            idle_seconds = 0
            if self._state == "idle" and self._idle_since is not None:
                idle_seconds = max(0, int(self._clock() - self._idle_since))
            return StateSnapshot(state=self._state, idle_seconds=idle_seconds, jobs_done=self._jobs_done)


class HeartbeatThread(threading.Thread):
    def __init__(
        self,
        poster: Any,
        state: WorkerState,
        instance_id: str,
        provider: str,
        interval_s: float,
        stop: threading.Event,
    ) -> None:
        super().__init__(name="heartbeat", daemon=True)
        self._poster = poster
        self._state = state
        self._instance_id = instance_id
        self._provider = provider
        self._interval_s = interval_s
        self._stop = stop

    def beat_once(self) -> bool:
        snap = self._state.snapshot()
        payload = {
            "instance_id": self._instance_id,
            "provider": self._provider,
            "state": snap.state,
            "idle_seconds": snap.idle_seconds,
            "jobs_done": snap.jobs_done,
        }
        try:
            self._poster.post_heartbeat(payload)
        except Exception as exc:  # the heartbeat thread must never die
            log.warning("heartbeat failed: %s", exc)
            return False
        return True

    def run(self) -> None:
        while True:
            self.beat_once()
            if self._stop.wait(self._interval_s):
                return

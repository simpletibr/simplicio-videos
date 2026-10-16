"""Adapter `fake`: no network, no key, no cost. For tests, the benchmark and for exercising the orchestration.

It "generates" by returning the bytes of the chunk it received (an identity swap), and it does not keep audio, so the
original audio remount is exercised. Class attributes tune its behaviour; `reset()` restores the defaults.

Simulated latency (real time, so concurrency is observable): `submit_delay_s` (upload), `generation_s` /
`generation_by_index` (how long a job stays `running`), `fetch_delay_s` (download). `max_in_flight` is the most chunks
that were submitted and not yet fetched at once. The same knobs exist as environment variables for runs in a child
process (`simplicio-video jobs`): SIMPLICIO_FAKE_SUBMIT_S, SIMPLICIO_FAKE_GENERATION_S, SIMPLICIO_FAKE_FETCH_S,
SIMPLICIO_FAKE_STUCK=1 (never finishes) and SIMPLICIO_FAKE_FAIL=1 (submit fails for good).
"""
from __future__ import annotations

import os
import threading
import time

from .base import Adapter, Capabilities, PriceRow, ProviderError, Status


def _env_float(name: str) -> float:
    try:
        return float(os.environ.get(name, "") or 0)
    except ValueError:
        return 0.0


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


class FakeAdapter(Adapter):
    name = "fake"
    env_var = ""
    version = "1"
    verified = True
    model = "fake-swap-1"
    capabilities = Capabilities(resolutions=("720p", "1080p"), max_input_s=10.0, max_output_s=10.0, max_ref_images=3,
                                keeps_audio=False, bills_input=False)
    prices = (
        PriceRow("fake-swap-1", "720p", 0.05, "https://example.invalid/fake-prices", "2026-10-15", "alta",
                 note="preço de teste"),
        PriceRow("fake-swap-1", "1080p", 0.10, "https://example.invalid/fake-prices", "2026-10-15", "alta",
                 note="preço de teste"),
    )
    notes = "adaptador de teste: sem rede, sem chave"

    submits: list = []
    submit_calls: list = []
    stuck = False
    polls_before_done = 1
    fail_submits = 0
    fail_retryable = True
    fail_index: int | None = None
    fail_poll_index: int | None = None
    submit_delay_s = 0.0
    generation_s = 0.0
    generation_by_index: dict = {}
    fetch_delay_s = 0.0
    in_flight = 0
    max_in_flight = 0
    _jobs: dict = {}
    _polls: dict = {}
    _started: dict = {}
    _lock = threading.Lock()

    @classmethod
    def reset(cls):
        cls.submits = []
        cls.submit_calls = []
        cls.stuck = False
        cls.polls_before_done = 1
        cls.fail_submits = 0
        cls.fail_retryable = True
        cls.fail_index = None
        cls.fail_poll_index = None
        cls.submit_delay_s = 0.0
        cls.generation_s = 0.0
        cls.generation_by_index = {}
        cls.fetch_delay_s = 0.0
        cls.in_flight = 0
        cls.max_in_flight = 0
        cls._jobs = {}
        cls._polls = {}
        cls._started = {}

    @classmethod
    def _generation(cls, index: int) -> float:
        if index in cls.generation_by_index:
            return float(cls.generation_by_index[index])
        return cls.generation_s or _env_float("SIMPLICIO_FAKE_GENERATION_S")

    def submit(self, job):
        cls = type(self)
        delay = cls.submit_delay_s or _env_float("SIMPLICIO_FAKE_SUBMIT_S")
        if delay:
            time.sleep(delay)
        with cls._lock:
            cls.submit_calls.append(job)
            if _env_flag("SIMPLICIO_FAKE_FAIL"):
                raise ProviderError("fake: falha simulada", retryable=False)
            if cls.fail_index is not None and job.index == cls.fail_index:
                raise ProviderError(f"fake: falha simulada no pedaço {job.index}", retryable=cls.fail_retryable)
            if cls.fail_submits > 0:
                cls.fail_submits -= 1
                raise ProviderError("fake: falha simulada", retryable=cls.fail_retryable)
            hid = f"fake-{len(cls.submits)}"
            cls.submits.append(job)
            cls._jobs[hid] = job
            cls._polls[hid] = 0
            cls._started[hid] = time.monotonic()
            cls.in_flight += 1
            cls.max_in_flight = max(cls.max_in_flight, cls.in_flight)
        return {"id": hid}

    def poll(self, handle):
        cls = type(self)
        if cls.stuck or _env_flag("SIMPLICIO_FAKE_STUCK"):
            return Status("running")
        with cls._lock:
            cls._polls[handle["id"]] += 1
            polls = cls._polls[handle["id"]]
            index = cls._jobs[handle["id"]].index
            gen = cls._generation(index)
            ready = (time.monotonic() - cls._started[handle["id"]] >= gen) if gen > 0 else polls > cls.polls_before_done
        if not ready:
            return Status("running")
        if cls.fail_poll_index is not None and index == cls.fail_poll_index:
            return Status("failed", f"falha simulada no pedaço {index}")
        return Status("done")

    def fetch(self, handle):
        cls = type(self)
        delay = cls.fetch_delay_s or _env_float("SIMPLICIO_FAKE_FETCH_S")
        if delay:
            time.sleep(delay)
        try:
            return cls._jobs[handle["id"]].video.read_bytes()
        finally:
            with cls._lock:
                cls.in_flight -= 1

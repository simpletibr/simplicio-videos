"""Adapter `fake`: no network, no key, no cost. For tests and for exercising the orchestration.

It "generates" by returning the bytes of the chunk it received (an identity swap), and it does not keep audio, so the
original audio remount is exercised. Class attributes tune its behaviour; `reset()` restores the defaults.
"""
from __future__ import annotations

from .base import Adapter, Capabilities, PriceRow, ProviderError, Status


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
    _jobs: dict = {}
    _polls: dict = {}

    @classmethod
    def reset(cls):
        cls.submits = []
        cls.submit_calls = []
        cls.stuck = False
        cls.polls_before_done = 1
        cls.fail_submits = 0
        cls.fail_retryable = True
        cls._jobs = {}
        cls._polls = {}

    def submit(self, job):
        cls = type(self)
        cls.submit_calls.append(job)
        if cls.fail_submits > 0:
            cls.fail_submits -= 1
            raise ProviderError("fake: falha simulada", retryable=cls.fail_retryable)
        hid = f"fake-{len(cls.submits)}"
        cls.submits.append(job)
        cls._jobs[hid] = job
        cls._polls[hid] = 0
        return {"id": hid}

    def poll(self, handle):
        cls = type(self)
        if cls.stuck:
            return Status("running")
        cls._polls[handle["id"]] += 1
        return Status("done" if cls._polls[handle["id"]] > cls.polls_before_done else "running")

    def fetch(self, handle):
        return type(self)._jobs[handle["id"]].video.read_bytes()

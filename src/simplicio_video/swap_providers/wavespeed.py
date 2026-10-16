"""Adapter `wavespeed` (UNVERIFIED): WaveSpeedAI, model wavespeed-ai/wan-2.2/animate with mode=replace.

Written from the public documentation (https://wavespeed.ai/docs): POST api.wavespeed.ai/api/v3/{model} with
`Authorization: Bearer <WAVESPEED_API_KEY>` returns data.id and data.urls.get; GET /api/v3/predictions/{id}/result
returns data.status (created, processing, completed, failed) and data.outputs[]. UNVERIFIED: the input field names
(video, image, mode, resolution), data URIs as input, the output list and the limits. It bills the input duration
(3 to 120 s).
"""
from __future__ import annotations

from .base import Capabilities, PriceRow, ProviderError, Status
from ._unverified import UnverifiedAdapter

MODEL = "wavespeed-ai/wan-2.2/animate"
PAGE = "https://wavespeed.ai/models/wavespeed-ai/wan-2.2/animate"
BASE = "https://api.wavespeed.ai/api/v3"


class WaveSpeedAdapter(UnverifiedAdapter):
    name = "wavespeed"
    env_var = "WAVESPEED_API_KEY"
    version = "1-unverified"
    model = MODEL
    capabilities = Capabilities(resolutions=("720p",), max_input_s=120.0, max_output_s=120.0, max_ref_images=1,
                                keeps_audio=False, bills_input=True, min_input_s=3.0, max_concurrency=2)  # UNVERIFIED: conservative until checked against the real API
    prices = (PriceRow(MODEL, "720p", 0.08, PAGE, "2026-10-15", "media",
                       note="mode=replace; cobra a duração de entrada, de 3 a 120 s"),)
    notes = "UNVERIFIED: campos de entrada e saída não conferidos na API real."
    states = {"CREATED": "queued", "PROCESSING": "running", "COMPLETED": "done", "FAILED": "failed"}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key()}"}

    def submit(self, job) -> dict:
        video, image = self._inputs(job)
        body = {"video": video, "image": image, "mode": "replace", "resolution": job.resolution}  # UNVERIFIED
        data = self._json(self._call("POST", f"{BASE}/{MODEL}", self._headers(), body, timeout=300)).get("data") or {}
        if not data.get("id"):
            raise ProviderError("wavespeed: a resposta não trouxe data.id", retryable=False)
        return {"id": data["id"]}

    def _result(self, handle) -> dict:
        return self._json(self._call("GET", f"{BASE}/predictions/{handle['id']}/result", self._headers())).get("data") or {}

    def poll(self, handle) -> Status:
        data = self._result(handle)
        state = self._state(data.get("status"))
        return Status(state, data.get("error") if state == "failed" else None)

    def fetch(self, handle) -> bytes:
        outs = self._result(handle).get("outputs") or []
        if not outs:
            raise ProviderError("wavespeed: a saída não tem outputs (UNVERIFIED)", retryable=False)
        return self._download(outs[0])

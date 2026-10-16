"""Adapter `kie` (UNVERIFIED): Kie.ai, model wan/2-2-animate-replace.

Written from the public documentation (https://docs.kie.ai): POST api.kie.ai/api/v1/jobs/createTask with
`Authorization: Bearer <KIE_API_KEY>` and {model, input} returns data.taskId; GET /api/v1/jobs/recordInfo?taskId=
returns data.state (waiting, queuing, generating, success, fail) and data.resultJson (a JSON string with resultUrls).
UNVERIFIED: this model's input fields (video_url, image_url, resolution), data URIs as input and the limits.
"""
from __future__ import annotations

import json

from .base import Capabilities, PriceRow, ProviderError, Status
from ._unverified import UnverifiedAdapter

MODEL = "wan/2-2-animate-replace"
BASE = "https://api.kie.ai/api/v1/jobs"


class KieAdapter(UnverifiedAdapter):
    name = "kie"
    env_var = "KIE_API_KEY"
    version = "1-unverified"
    model = MODEL
    capabilities = Capabilities(resolutions=("720p",), max_input_s=10.0, max_output_s=10.0, max_ref_images=1,
                                keeps_audio=False, bills_input=False)
    prices = (PriceRow(MODEL, "720p", 0.0625, "https://kie.ai/pricing", "2026-10-15", "baixa"),)
    notes = "UNVERIFIED: campos de entrada e saída não conferidos na API real."
    states = {"WAITING": "queued", "QUEUING": "queued", "GENERATING": "running", "SUCCESS": "done", "FAIL": "failed"}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key()}"}

    def submit(self, job) -> dict:
        video, image = self._inputs(job)
        body = {"model": MODEL, "input": {"video_url": video, "image_url": image, "resolution": job.resolution}}  # UNVERIFIED
        data = self._json(self._call("POST", f"{BASE}/createTask", self._headers(), body, timeout=300)).get("data") or {}
        if not data.get("taskId"):
            raise ProviderError("kie: a resposta não trouxe data.taskId", retryable=False)
        return {"id": data["taskId"]}

    def _info(self, handle) -> dict:
        return self._json(self._call("GET", f"{BASE}/recordInfo?taskId={handle['id']}", self._headers())).get("data") or {}

    def poll(self, handle) -> Status:
        data = self._info(handle)
        state = self._state(data.get("state"))
        return Status(state, data.get("failMsg") if state == "failed" else None)

    def fetch(self, handle) -> bytes:
        try:
            urls = json.loads(self._info(handle).get("resultJson") or "{}").get("resultUrls") or []
        except ValueError:
            urls = []
        if not urls:
            raise ProviderError("kie: a saída não tem resultUrls (UNVERIFIED)", retryable=False)
        return self._download(urls[0])

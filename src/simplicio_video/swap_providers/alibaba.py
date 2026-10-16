"""Adapter `alibaba` (UNVERIFIED): Alibaba Cloud Model Studio (DashScope, Singapore), model wan2.2-animate-mix.

Written from the public documentation (https://www.alibabacloud.com/help/en/model-studio): POST
dashscope-intl.aliyuncs.com/api/v1/services/aigc/image2video/video-synthesis/ with `Authorization: Bearer
<DASHSCOPE_API_KEY>` and `X-DashScope-Async: enable` returns output.task_id; GET /api/v1/tasks/{id} returns
output.task_status (PENDING, RUNNING, SUCCEEDED, FAILED) and output.results.video_url. UNVERIFIED: the input fields
(image_url, video_url), parameters, data URIs as input (this API usually expects public URLs) and the limits.
"""
from __future__ import annotations

from .base import Capabilities, PriceRow, ProviderError, Status
from ._unverified import UnverifiedAdapter

MODEL = "wan2.2-animate-mix"
BASE = "https://dashscope-intl.aliyuncs.com/api/v1"


class AlibabaAdapter(UnverifiedAdapter):
    name = "alibaba"
    env_var = "DASHSCOPE_API_KEY"
    version = "1-unverified"
    model = MODEL
    capabilities = Capabilities(resolutions=("720p",), max_input_s=30.0, max_output_s=30.0, max_ref_images=1,
                                keeps_audio=False, bills_input=False, min_input_s=2.0)
    prices = (PriceRow(MODEL, "720p", 0.18, "https://www.alibabacloud.com/help/en/model-studio/model-pricing",
                       "2026-10-15", "media", note="região Singapura"),)
    notes = "UNVERIFIED: campos de entrada e saída não conferidos na API real; a API costuma pedir URL pública."
    states = {"PENDING": "queued", "RUNNING": "running", "SUCCEEDED": "done", "FAILED": "failed", "CANCELED": "failed",
              "UNKNOWN": "failed"}

    def _headers(self, async_: bool = False) -> dict:
        h = {"Authorization": f"Bearer {self.api_key()}"}
        if async_:
            h["X-DashScope-Async"] = "enable"
        return h

    def submit(self, job) -> dict:
        video, image = self._inputs(job)
        body = {"model": MODEL, "input": {"image_url": image, "video_url": video}, "parameters": {}}  # UNVERIFIED
        url = f"{BASE}/services/aigc/image2video/video-synthesis/"
        data = (self._json(self._call("POST", url, self._headers(True), body, timeout=300)).get("output")) or {}
        if not data.get("task_id"):
            raise ProviderError("alibaba: a resposta não trouxe output.task_id", retryable=False)
        return {"id": data["task_id"]}

    def _task(self, handle) -> dict:
        return self._json(self._call("GET", f"{BASE}/tasks/{handle['id']}", self._headers())).get("output") or {}

    def poll(self, handle) -> Status:
        out = self._task(handle)
        state = self._state(out.get("task_status"))
        return Status(state, out.get("message") if state == "failed" else None)

    def fetch(self, handle) -> bytes:
        url = (self._task(handle).get("results") or {}).get("video_url")
        if not url:
            raise ProviderError("alibaba: a saída não tem results.video_url (UNVERIFIED)", retryable=False)
        return self._download(url)

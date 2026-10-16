"""Adapter `fal` (UNVERIFIED): fal queue API, model fal-ai/wan/v2.2-14b/animate/replace.

Written from the public queue documentation (https://docs.fal.ai/model-endpoints/queue): POST queue.fal.run/{model} with
`Authorization: Key <FAL_KEY>` returns request_id, status_url and response_url; the status is IN_QUEUE, IN_PROGRESS or
COMPLETED. UNVERIFIED: the input field names of this model (video_url, image_url), the output field (video.url), data
URIs as input and the limits below. fal bills by frames at 16 fps: a 24 fps source can cost 1,5x.
"""
from __future__ import annotations

from .base import Capabilities, PriceRow, ProviderError, Status
from ._unverified import UnverifiedAdapter

MODEL = "fal-ai/wan/v2.2-14b/animate/replace"
PAGE = "https://fal.ai/models/fal-ai/wan/v2.2-14b/animate/replace"


class FalAdapter(UnverifiedAdapter):
    name = "fal"
    env_var = "FAL_KEY"
    version = "1-unverified"
    model = MODEL
    capabilities = Capabilities(resolutions=("720p",), max_input_s=10.0, max_output_s=10.0, max_ref_images=1,
                                keeps_audio=False, bills_input=False)
    prices = (PriceRow(MODEL, "720p", 0.08, PAGE, "2026-10-15", "media",
                       note="fal cobra por quadros a 16 fps: com fonte a 24 fps pode custar 1,5x"),)
    notes = "UNVERIFIED: campos de entrada e saída não conferidos na API real."
    states = {"IN_QUEUE": "queued", "IN_PROGRESS": "running", "COMPLETED": "done"}

    def fps_factor(self, job) -> float:
        return max(1.0, job.fps / 16.0)

    def _headers(self) -> dict:
        return {"Authorization": f"Key {self.api_key()}"}

    def submit(self, job) -> dict:
        video, image = self._inputs(job)
        body = {"video_url": video, "image_url": image}  # UNVERIFIED field names
        data = self._json(self._call("POST", f"https://queue.fal.run/{MODEL}", self._headers(), body, timeout=300))
        if not data.get("request_id"):
            raise ProviderError("fal: a resposta não trouxe request_id", retryable=False)
        return {"id": data["request_id"], "status_url": data.get("status_url"), "response_url": data.get("response_url")}

    def poll(self, handle) -> Status:
        data = self._json(self._call("GET", handle["status_url"], self._headers()))
        state = self._state(data.get("status"))
        return Status(state, data.get("error") if state == "failed" else None)

    def fetch(self, handle) -> bytes:
        data = self._json(self._call("GET", handle["response_url"], self._headers()))
        url = (data.get("video") or {}).get("url")  # UNVERIFIED output field
        if not url:
            raise ProviderError("fal: a saída não tem video.url (UNVERIFIED)", retryable=False)
        return self._download(url)

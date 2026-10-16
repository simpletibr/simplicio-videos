"""Adapter `gemini`: Gemini Omni video editing through the Interactions API.

Verified against https://ai.google.dev/gemini-api/docs/omni (read 2026-10-15):
  POST {base}/interactions, header `x-goog-api-key`, body {model, input[], response_format{type,resolution}, background}.
  input items: {"type":"video"|"image","data":<base64>,"mime_type":...} (or "uri" from the Files API) and {"type":"text"}.
  The reference image is cited in the prompt as <IMAGE_REF_0>.
  `background: true` returns at once {"id","status":"in_progress"}; the result comes from GET {base}/interactions/{id}.
  Without `background` the request stays open and hangs: this adapter never uses that mode.
  Completed: steps[] with a `model_output` step whose content[] has {"type":"video","mime_type","data"|"uri"}.
  A later GET returns the video inline in `data`; `uri` is only guaranteed in the creation response.
Not documented in what was read (code marked UNVERIFIED below): the status names besides in_progress/completed, the
`usage` field names (used only for the measured cost), and the limit of reference images (kept at 3, conservative).
Inputs go inline in base64 (clips are at most 10 s); the Files API upload is not used.
"""
from __future__ import annotations

import base64
import os
import re
from urllib.parse import urlparse

from .base import Adapter, Capabilities, PriceRow, ProviderError, Status, SwapError, b64_file, mime_of

BASE = "https://generativelanguage.googleapis.com/v1beta"
PRICING = "https://ai.google.dev/gemini-api/docs/pricing"
OUT_USD_PER_TOKEN = 17.5e-6  # US$ 17,50 per 1M output tokens (5.792 tokens per second of video)
IN_USD_PER_TOKEN = 1.5e-6    # US$ 1,50 per 1M input tokens
FREE_PLAN_MSG = (
    "gemini: o plano grátis não tem cota para o modelo gemini-omni-1.1-flash (Rate limit exceeded ... limit: 0). "
    "Use uma chave de um projeto com faturamento ativo no Google AI Studio / Google Cloud. Não adianta tentar de novo."
)
QUOTA_MSG = (
    "gemini: cota excedida (You exceeded your current quota). Confira o plano e o faturamento do projeto no Google AI Studio / "
    "Google Cloud. Não adianta tentar de novo agora."
)
FAILED_STATES = ("failed", "cancelled", "canceled", "expired", "incomplete")  # UNVERIFIED: only completed/in_progress are documented


class GeminiAdapter(Adapter):
    name = "gemini"
    env_var = "GEMINI_API_KEY"
    version = "1"
    verified = True
    model = "gemini-omni-1.1-flash"
    capabilities = Capabilities(resolutions=("720p", "1080p"), max_input_s=10.0, max_output_s=10.0, max_ref_images=3,
                                keeps_audio=False, bills_input=True, min_input_s=3.0)
    prices = (
        PriceRow("gemini-omni-1.1-flash", "720p", 0.101, PRICING, "2026-10-15", "alta", usd_per_s_in=0.0087,
                 note="saída 5.792 tokens/s a US$ 17,50 por 1M; entrada US$ 1,50 por 1M (cerca de US$ 0,0087 por segundo)"),
        PriceRow("gemini-omni-1.1-flash", "1080p", 0.152, PRICING, "2026-10-15", "baixa", usd_per_s_in=0.0087,
                 note="valor de terceiros; o Google só publica o 720p"),
    )
    notes = ("Entrada editável até 10 s, saída de 3 a 10 s a 24 fps. Plano grátis não tem cota (limit: 0): precisa de projeto "
             "com faturamento. O áudio do resultado não é tratado como preservado: o original é remontado.")

    def __init__(self):
        self._usage: dict = {}

    def _base(self) -> str:
        base = os.environ.get("SIMPLICIO_GEMINI_BASE", "").strip().rstrip("/") or BASE
        u = urlparse(base)
        if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")):
            raise SwapError("SIMPLICIO_GEMINI_BASE precisa ser https (http só em localhost): a chave não vai em texto claro")
        return base

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.api_key()}

    def _check(self, res):
        data = res.json()
        if res.status >= 400 or (isinstance(data, dict) and "error" in data and "steps" not in data and "status" not in data):
            err = data.get("error") if isinstance(data, dict) else None
            msg = (err.get("message") if isinstance(err, dict) else str(err or "")) or ""
            low = (msg or res.body[:400].decode("utf8", "replace")).lower()
            if res.status == 429 and re.search(r"limit:\s*0\b", low):  # free plan: no quota at all, whatever the wording
                raise ProviderError(FREE_PLAN_MSG, retryable=False)
            if res.status == 429 and "quota" in low:  # an exhausted quota does not come back by waiting seconds
                raise ProviderError(QUOTA_MSG, retryable=False)
            raise self._error(res)
        if not isinstance(data, dict):
            raise ProviderError("gemini: resposta que não é JSON", retryable=True, network=True)
        return data

    def build_body(self, job) -> dict:
        items = [{"type": "video", "data": b64_file(job.video), "mime_type": mime_of(job.video)}]
        for ref in job.refs:
            items.append({"type": "image", "data": b64_file(ref), "mime_type": mime_of(ref)})
        items.append({"type": "text", "text": job.prompt})
        return {"model": self.model, "input": items, "response_format": {"type": "video", "resolution": job.resolution},
                "background": True}  # never the synchronous mode: it hangs

    def submit(self, job) -> dict:
        res = self._call("POST", f"{self._base()}/interactions", self._headers(), self.build_body(job), timeout=300)
        data = self._check(res)
        if not data.get("id"):
            raise ProviderError("gemini: a resposta não trouxe o id da interação", retryable=False)
        return {"id": data["id"]}

    def _get(self, handle) -> dict:
        return self._check(self._call("GET", f"{self._base()}/interactions/{handle['id']}", self._headers()))

    def poll(self, handle) -> Status:
        data = self._get(handle)
        status = str(data.get("status", "")).lower()
        err = data.get("error")
        if status == "completed":
            return Status("done")
        if status in FAILED_STATES or err:
            msg = (err.get("message") if isinstance(err, dict) else err) or f"estado {status}"
            return Status("failed", str(msg))
        return Status("running")

    def fetch(self, handle) -> bytes:
        data = self._get(handle)
        usage = data.get("usage")
        if isinstance(usage, dict):
            self._usage[handle["id"]] = usage
        video = None
        for step in reversed(data.get("steps") or []):
            if step.get("type") != "model_output":
                continue
            for item in step.get("content") or []:
                if item.get("type") == "video":
                    video = item
                    break
            if video:
                break
        if not video:
            raise ProviderError("gemini: a interação terminou sem vídeo na saída (steps[].content[] type=video)", retryable=False)
        if video.get("data"):
            try:
                return base64.b64decode(video["data"])
            except ValueError:
                raise ProviderError("gemini: base64 do vídeo inválido", retryable=False) from None
        uri = video.get("uri")
        if uri:
            u = urlparse(uri)
            host = u.hostname or ""
            google = u.scheme == "https" and (host == "googleapis.com" or host.endswith(".googleapis.com"))
            headers = self._headers() if google else {}  # the key goes only to Google, over TLS
            res = self._call("GET", uri, headers)
            if res.status >= 400:
                raise self._error(res)
            return res.body
        raise ProviderError("gemini: o vídeo da saída não tem data nem uri", retryable=False)

    def measured_usd(self, handle) -> float | None:
        u = self._usage.get(handle["id"])
        if not u:
            return None
        out = u.get("total_output_tokens", u.get("output_tokens"))  # UNVERIFIED field names
        inp = u.get("total_input_tokens", u.get("input_tokens")) or 0
        if not isinstance(out, (int, float)) or not isinstance(inp, (int, float)):
            return None
        return out * OUT_USD_PER_TOKEN + inp * IN_USD_PER_TOKEN

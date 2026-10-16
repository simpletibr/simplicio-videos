"""Adapter interface shared by every swap provider.

An adapter knows one provider: its name, the environment variable that holds the key (never an argument, file, log or
manifest), what it can do (`Capabilities`), a price table (`PriceRow`, each row with source_url, read_on and
confidence) and four calls: `estimate`, `submit`, `poll`, `fetch`. The orchestration (swap.py) is the same for all.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from . import http

# Reference exchange rate, kept apart from the USD prices so R$ can be shown next to US$.
FX = {"brl_per_usd": 5.0521, "source": "PTAX de 2026-10-15 (Banco Central do Brasil)"}
PRICES_READ_ON = "2026-10-15"
UNVERIFIED = "UNVERIFIED"


class SwapError(Exception):
    pass


class ProviderError(SwapError):
    """A provider failure. `retryable` says whether trying the same call again can help."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class Capabilities:
    resolutions: tuple
    max_input_s: float
    max_output_s: float
    max_ref_images: int
    keeps_audio: bool
    bills_input: bool
    min_input_s: float = 0.0


@dataclass(frozen=True)
class PriceRow:
    model: str
    resolution: str
    usd_per_s_out: float
    source_url: str
    read_on: str
    confidence: str  # alta | media | baixa
    usd_per_s_in: float = 0.0
    note: str = ""


@dataclass
class Estimate:
    usd: float
    model: str
    resolution: str
    source_url: str
    read_on: str
    confidence: str
    detail: str = ""
    note: str = ""

    def as_dict(self) -> dict:
        return {"usd": round(self.usd, 6), "brl": round(self.usd * FX["brl_per_usd"], 4), "model": self.model,
                "resolution": self.resolution, "source_url": self.source_url, "read_on": self.read_on,
                "confidence": self.confidence, "detail": self.detail, "note": self.note,
                "fx_brl_per_usd": FX["brl_per_usd"]}


@dataclass
class Status:
    state: str  # queued | running | done | failed
    error: str | None = None


@dataclass
class Job:
    """One piece of work. For `estimate` it is the whole video; for `submit` it is one chunk (max_input_s at most)."""
    video: Path
    refs: list
    prompt: str = ""
    resolution: str = "720p"
    duration_s: float = 0.0
    fps: float = 24.0
    width: int = 0
    height: int = 0
    has_audio: bool = True
    index: int = 0


MIMES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".png": "image/png",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def mime_of(path: Path) -> str:
    return MIMES.get(Path(path).suffix.lower(), "application/octet-stream")


def b64_file(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def data_uri(path: Path) -> str:
    return f"data:{mime_of(path)};base64,{b64_file(path)}"


class Adapter:
    name = ""
    env_var = ""
    version = "1"
    verified = False
    model = ""
    capabilities: Capabilities
    prices: tuple = ()
    notes = ""

    # -- key and HTTP -------------------------------------------------------------------------------------------
    def api_key(self) -> str:
        key = os.environ.get(self.env_var, "").strip() if self.env_var else ""
        if self.env_var and not key:
            raise SwapError(f"{self.env_var} não definida: a chave do provedor {self.name} só entra por variável de ambiente")
        return key

    def _call(self, method: str, url: str, headers: dict | None = None, body: dict | None = None, timeout: float = 120):
        try:
            return http.request(method, url, headers=headers, json_body=body, timeout=timeout)
        except http.NetworkError as e:
            raise ProviderError(f"{self.name}: {e}", retryable=True) from None

    def _error(self, res: http.Response) -> ProviderError:
        """A non-2xx response as a ProviderError (5xx and 429 are transient, other 4xx are not)."""
        data = res.json()
        msg = ""
        if isinstance(data, dict):
            err = data.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or data.get("message") or data.get("msg") or ""
        msg = str(msg or res.body[:200].decode("utf8", "replace"))
        quota = res.status == 429 and "quota" in msg.lower()  # an exhausted quota does not come back in seconds
        return ProviderError(f"{self.name}: HTTP {res.status}: {msg}", retryable=(res.status == 429 and not quota) or res.status >= 500)

    # -- price ----------------------------------------------------------------------------------------------------
    def price_row(self, resolution: str) -> PriceRow:
        for r in self.prices:
            if r.resolution == resolution:
                return r
        ok = ", ".join(self.capabilities.resolutions)
        raise SwapError(f"{self.name}: resolução {resolution} sem preço/suporte (use: {ok})")

    def fps_factor(self, job: Job) -> float:
        return 1.0

    def estimate(self, job: Job) -> Estimate:
        row = self.price_row(job.resolution)
        secs = max(job.duration_s, self.capabilities.min_input_s)
        factor = self.fps_factor(job)
        usd_out = secs * row.usd_per_s_out * factor
        usd_in = secs * row.usd_per_s_in
        detail = f"{secs:.1f} s x US$ {row.usd_per_s_out}/s de saída"
        if factor != 1.0:
            detail += f" x {factor:g} (quadros)"
        if row.usd_per_s_in:
            detail += f" + {secs:.1f} s x US$ {row.usd_per_s_in}/s de entrada"
        return Estimate(usd_out + usd_in, row.model, row.resolution, row.source_url, row.read_on, row.confidence,
                        detail=detail, note=row.note)

    # -- the four calls -----------------------------------------------------------------------------------------
    def submit(self, job: Job) -> dict:
        raise NotImplementedError

    def poll(self, handle: dict) -> Status:
        raise NotImplementedError

    def fetch(self, handle: dict) -> bytes:
        raise NotImplementedError

    def measured_usd(self, handle: dict) -> float | None:
        return None

    def describe(self) -> dict:
        c = self.capabilities
        return {"name": self.name, "model": self.model, "env_var": self.env_var or None, "verified": self.verified,
                "status": "verificado" if self.verified else UNVERIFIED, "adapter_version": self.version,
                "capabilities": {"resolutions": list(c.resolutions), "max_input_s": c.max_input_s,
                                 "min_input_s": c.min_input_s, "max_output_s": c.max_output_s,
                                 "max_ref_images": c.max_ref_images, "keeps_audio": c.keeps_audio,
                                 "bills_input": c.bills_input},
                "prices": [{"model": r.model, "resolution": r.resolution, "usd_per_s_out": r.usd_per_s_out,
                            "usd_per_s_in": r.usd_per_s_in, "brl_per_s_out": round(r.usd_per_s_out * FX["brl_per_usd"], 4),
                            "source_url": r.source_url, "read_on": r.read_on, "confidence": r.confidence,
                            "note": r.note} for r in self.prices],
                "notes": self.notes}

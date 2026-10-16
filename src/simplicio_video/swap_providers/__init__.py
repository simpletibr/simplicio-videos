"""Swap providers: one adapter per provider behind the same interface (see base.py). Add a provider by writing an
adapter module and listing it in REGISTRY; the orchestration in swap.py does not change."""
from __future__ import annotations

from .alibaba import AlibabaAdapter
from .base import (FX, UNVERIFIED, Adapter, Capabilities, Estimate, Job, PriceRow, ProviderError, Status,  # noqa: F401
                   SwapError)
from .fake import FakeAdapter
from .fal import FalAdapter
from .gemini import GeminiAdapter
from .kie import KieAdapter
from .wavespeed import WaveSpeedAdapter

REGISTRY = {c.name: c for c in (GeminiAdapter, FalAdapter, WaveSpeedAdapter, KieAdapter, AlibabaAdapter, FakeAdapter)}


def names() -> list[str]:
    return list(REGISTRY)


def get(name: str) -> Adapter:
    try:
        return REGISTRY[name]()
    except KeyError:
        raise SwapError(f"provedor desconhecido: {name} (use `simplicio-video swap providers`)") from None

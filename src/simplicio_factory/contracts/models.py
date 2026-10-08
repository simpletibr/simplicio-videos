"""Dataclasses do kernel: Item (estado), Event (log), Brand e Draft (entrada do estágio), RenderResult.

Rotas de produção (#82, épico #81): `Item.production` escolhe o grafo de transições (`deterministic` ou
`ai_assisted`); `Item.review` é a revisão humana (`null | pending | approved | changes_requested`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

STATES = (
    "idea",
    "drafted",
    "quoted",
    "approved",
    "generating",
    "generated",
    "rendering",
    "rendered",
    "failed",
)
ROUTES = ("deterministic", "ai_assisted")
REVIEW_VALUES = ("pending", "approved", "changes_requested")
DEFAULT_ROUTE = "deterministic"


def default_production() -> dict:
    return {"route": DEFAULT_ROUTE, "steps": []}


@dataclass
class Brand:
    name: str
    colors: dict
    logo: Optional[str]
    facts: dict


@dataclass
class Draft:
    item_id: str
    idea: str
    facts: dict
    claims: list
    platform: str
    duration_s: int


@dataclass
class Item:
    """Estado de um item. Só `transition()` muda `state`."""

    id: str
    brand: str
    state: str = "idea"
    failed_from: Optional[str] = None
    production: dict = field(default_factory=default_production)
    review: Optional[str] = None

    def __post_init__(self) -> None:
        route = (self.production or {}).get("route", DEFAULT_ROUTE)
        if route not in ROUTES:
            raise ValueError(f"rota de produção inválida: {route!r}")
        if self.review is not None and self.review not in REVIEW_VALUES:
            raise ValueError(f"review inválido: {self.review!r}")


@dataclass
class Event:
    seq: int
    kind: str
    item_id: str
    data: dict


@dataclass
class RenderResult:
    mp4_path: str
    content_hash: str

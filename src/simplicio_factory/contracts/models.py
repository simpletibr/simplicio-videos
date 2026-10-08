"""Dataclasses do kernel: Item (estado), Event (log), Brand e Draft (entrada do estágio), RenderResult."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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

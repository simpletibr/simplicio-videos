"""Interface do kernel: Protocols (Store, Renderer, Stage, StageContract) e dataclasses Brand e Draft.

Interface exata (decisão da #33): `Brand(name, colors: dict, logo: str | None, facts: dict)` e
`Draft(item_id, idea, facts: dict, claims: list, platform: str, duration_s: int)`.
"""

from __future__ import annotations

import abc
import dataclasses
import inspect
import typing
from typing import Optional

import pytest

from tests.factory._fixtures import contracts


def _is_protocol_or_abc(obj) -> bool:
    if getattr(obj, "_is_protocol", False):
        return True
    return inspect.isclass(obj) and (issubclass(obj, abc.ABC) or inspect.isabstract(obj))


@pytest.mark.parametrize("name", ["Store", "Renderer", "Stage", "StageContract"])
def test_kernel_protocol_exists_as_protocol_or_abstract_base(name):
    obj = getattr(contracts(), name)
    assert _is_protocol_or_abc(obj), f"{name} precisa ser typing.Protocol ou classe base abstrata"


def _hint_matches(hint, expected) -> bool:
    if expected is Optional[str]:
        return hint == Optional[str]
    return (typing.get_origin(hint) or hint) is expected


def _field_names(cls) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


def test_brand_is_dataclass_with_exact_fields():
    brand_cls = contracts().Brand
    assert dataclasses.is_dataclass(brand_cls)
    assert _field_names(brand_cls) == ["name", "colors", "logo", "facts"]
    hints = typing.get_type_hints(brand_cls)
    assert _hint_matches(hints["name"], str)
    assert _hint_matches(hints["colors"], dict)
    assert _hint_matches(hints["logo"], Optional[str])
    assert _hint_matches(hints["facts"], dict)


def test_brand_accepts_logo_none():
    brand = contracts().Brand(name="Acme", colors={"primary": "#112233"}, logo=None, facts={"founded": 2010})
    assert brand.name == "Acme"
    assert brand.logo is None
    assert brand.facts == {"founded": 2010}


def test_draft_is_dataclass_with_exact_fields():
    draft_cls = contracts().Draft
    assert dataclasses.is_dataclass(draft_cls)
    assert _field_names(draft_cls) == ["item_id", "idea", "facts", "claims", "platform", "duration_s"]
    hints = typing.get_type_hints(draft_cls)
    assert _hint_matches(hints["item_id"], str)
    assert _hint_matches(hints["idea"], str)
    assert _hint_matches(hints["facts"], dict)
    assert _hint_matches(hints["claims"], list)
    assert _hint_matches(hints["platform"], str)
    assert _hint_matches(hints["duration_s"], int)


def test_draft_accepts_minimal_values():
    draft = contracts().Draft(
        item_id="itm_01HZTEST0000000000000001",
        idea="Promo de inverno",
        facts={},
        claims=[],
        platform="instagram-reels",
        duration_s=15,
    )
    assert draft.duration_s == 15
    assert draft.claims == []

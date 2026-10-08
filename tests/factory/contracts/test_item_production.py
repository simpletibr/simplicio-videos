"""Campos `production` e `review` do item (#82, épico #81): schema commitado, padrões, validação e persistência.

O schema lido é o commitado (schemas/factory/item.schema.json); a igualdade com o gerado já é coberta por
test_item_schema.py. Em cada teste de rejeição, o caso válido é conferido antes, para que o teste não passe
só porque o campo desconhecido é rejeitado pelo `additionalProperties: false`.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from tests.factory._fixtures import ai_production, contracts, json_store, make_item, make_routed_item

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schemas" / "factory" / "item.schema.json"

BASE_ITEM = {
    "schema": "simplicio.factory-item/v1",
    "id": "itm_01HZTEST0000000000000001",
    "brand": "acme",
    "state": "idea",
}


def _errors(item: dict) -> list:
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    return list(validator.iter_errors(item))


def _with(**fields) -> dict:
    return {**BASE_ITEM, **fields}


def test_item_without_production_or_review_is_still_valid():
    assert _errors(BASE_ITEM) == []


@pytest.mark.parametrize(
    "production",
    [
        pytest.param({"route": "deterministic"}, id="deterministic"),
        pytest.param({"route": "ai_assisted", "steps": [{"kind": "ai_media", "provider": "provedor-teste"}]}, id="ai_assisted"),
    ],
)
def test_production_with_known_route_is_accepted(production):
    assert _errors(_with(production=production)) == []


def test_production_with_unknown_route_is_rejected():
    assert _errors(_with(production={"route": "deterministic"})) == []

    assert _errors(_with(production={"route": "bogus"})), "route fora de {deterministic, ai_assisted} deveria ser rejeitada"


@pytest.mark.parametrize("review", [None, "pending", "approved", "changes_requested"])
def test_review_accepts_null_and_the_three_values(review):
    assert _errors(_with(review=review)) == []


@pytest.mark.parametrize("review", ["bogus", "APPROVED", ""])
def test_review_rejects_invalid_values(review):
    assert _errors(_with(review="approved")) == []

    assert _errors(_with(review=review)), f"review {review!r} deveria ser rejeitado"


@pytest.mark.parametrize("state", ["quoted", "approved", "generating", "generated"])
def test_schema_accepts_ai_assisted_states(state):
    assert _errors(_with(state=state, production=ai_production())) == []


def test_schema_accepts_failed_from_generating():
    item = _with(state="failed", failed_from="generating", production=ai_production())

    assert _errors(item) == []


def test_schema_still_rejects_unknown_state():
    assert _errors(BASE_ITEM) == []

    assert _errors(_with(state="bogus")), "state fora do conjunto deveria ser rejeitado"


def test_item_review_defaults_to_none():
    assert make_item().review is None


def test_item_rejects_invalid_review_value_at_construction():
    with pytest.raises(ValueError):
        contracts().Item(id="itm_01HZTEST0000000000000001", brand="acme", state="idea", review="bogus")


def test_item_rejects_unknown_route_at_construction():
    with pytest.raises(ValueError):
        contracts().Item(
            id="itm_01HZTEST0000000000000001",
            brand="acme",
            state="idea",
            production={"route": "bogus"},
        )


def test_production_and_review_survive_json_store_round_trip(tmp_path):
    store = json_store(tmp_path)
    item = make_routed_item(state="drafted", production=ai_production(), review="pending")
    store.save_item(item)

    loaded = store.get_item(item.id)

    assert getattr(loaded, "production", None) == ai_production()
    assert getattr(loaded, "review", None) == "pending"


def test_reloaded_ai_assisted_item_keeps_its_route_in_transitions(tmp_path):
    store = json_store(tmp_path)
    store.save_item(make_routed_item(state="drafted", production=ai_production()))
    loaded = store.get_item("itm_01HZTEST0000000000000001")

    contracts().transition(loaded, "quoted", store)

    assert loaded.state == "quoted"
    assert store.read()[-1].data["route"] == "ai_assisted"

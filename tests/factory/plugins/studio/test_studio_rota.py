"""studio.json grava a rota real do item (#95, épico #81).

Antes da #95, `_gravar_estado` gravava sempre `{"route": "deterministic", "steps": []}`. Agora grava o `production`
do item: a rota e os passos (por exemplo o ai_media de `generate quote`). Item determinístico segue igual.
"""

from __future__ import annotations

import json

from tests.factory._fixtures import ai_production, make_routed_item
from tests.factory.plugins.studio._studio import (
    BRAND_ID,
    ITEM_ID,
    json_store,
    make_item,
    make_stage,
    stub_renderer,
)

PASSO_IA = {
    "kind": "ai_media",
    "provider": "real-oficial",
    "estimate_ref": "est_teste_01",
    "credits": 120,
    "confirmed_by": "Wesley",
    "confirmed_at": "2026-10-08T10:00:00Z",
}


def _estado_do_item(tmp_path):
    return json.loads((tmp_path / "items" / ITEM_ID / "studio.json").read_text(encoding="utf-8"))


def test_item_ai_assisted_grava_rota_e_passos_no_studio_json(tmp_path):
    store = json_store(tmp_path / "factory")
    # A rota ai_assisted não tem drafted -> rendering: o item chega a `generated` (como no fluxo da #90).
    item = make_routed_item(
        state="generated",
        production=ai_production(steps=[dict(PASSO_IA)]),
        item_id=ITEM_ID,
        brand=BRAND_ID,
    )
    store.save_item(item)

    make_stage(tmp_path, renderer=stub_renderer(tmp_path)).run(item, store)

    assert store.get_item(ITEM_ID).state == "rendered"
    assert _estado_do_item(tmp_path)["production"] == {"route": "ai_assisted", "steps": [PASSO_IA]}
    transicoes = [(e.data["from"], e.data["to"], e.data["route"]) for e in store.read() if e.kind == "item.state_changed"]
    assert transicoes == [("generated", "rendering", "ai_assisted"), ("rendering", "rendered", "ai_assisted")]


def test_item_deterministico_grava_rota_padrao_sem_passos(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)

    make_stage(tmp_path).run(item, store)

    assert _estado_do_item(tmp_path)["production"] == {"route": "deterministic", "steps": []}

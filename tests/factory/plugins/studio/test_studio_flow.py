"""Fluxo idea -> drafted -> rendering -> rendered com StubRenderer, em menos de 2 s (#16).

Mudanças de estado passam por transition(). O item.json guarda content_hash e production (spec, item.json).
"""

from __future__ import annotations

import json
import re
import time

import pytest

from tests.factory.plugins.studio._studio import (
    claims_module,
    draft_with,
    hashing_module,
    json_store,
    make_item,
    load_draft,
    make_stage,
    stage_module,
    stub_renderer,
)


def test_fluxo_idea_ate_rendered_com_stub_em_menos_de_2_s(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)
    renderer = stub_renderer(tmp_path)
    stage = make_stage(tmp_path, renderer=renderer)

    started = time.perf_counter()
    stage.run(item, store)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"fluxo levou {elapsed:.2f} s"
    assert store.get_item(item.id).state == "rendered"
    changes = [(e.data["from"], e.data["to"]) for e in store.read() if e.kind == "item.state_changed"]
    assert changes == [("idea", "drafted"), ("drafted", "rendering"), ("rendering", "rendered")]
    assert len(renderer.calls) == 1


def test_mudancas_de_estado_passam_por_transition(tmp_path, monkeypatch):
    stage_mod = stage_module()
    real_transition = stage_mod.transition
    seen = []

    def spy(item, to, store):
        seen.append((item.state, to))
        return real_transition(item, to, store)

    monkeypatch.setattr(stage_mod, "transition", spy)
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)

    make_stage(tmp_path).run(item, store)

    assert seen == [("idea", "drafted"), ("drafted", "rendering"), ("rendering", "rendered")]


def test_falha_no_render_vai_para_failed_a_partir_de_rendering(tmp_path):
    class BoomRenderer:
        def render(self, contract_path, preview):
            raise RuntimeError("render quebrou")

    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)
    stage = make_stage(tmp_path, renderer=BoomRenderer())

    with pytest.raises(RuntimeError, match="render quebrou"):
        stage.run(item, store)

    saved = store.get_item(item.id)
    assert saved.state == "failed"
    assert saved.failed_from == "rendering"


def test_claim_invalido_nao_chega_a_renderizar(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)
    renderer = stub_renderer(tmp_path)
    stage = make_stage(tmp_path, renderer=renderer, draft=draft_with(idea="Clareamento por R$ 99."))

    with pytest.raises(claims_module().ClaimError):
        stage.run(item, store)

    assert renderer.calls == []
    assert store.get_item(item.id).state != "rendered"


def test_item_json_guarda_content_hash_e_production(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)
    stage = make_stage(tmp_path)

    stage.run(item, store)

    # Estado do estúdio fica em <pasta-do-item>/studio.json (decisão fixada da #16); o item.json do kernel não muda de schema.
    saved = json.loads((tmp_path / "items" / item.id / "studio.json").read_text(encoding="utf-8"))
    assert saved["production"] == {"route": "deterministic", "steps": []}
    assert re.fullmatch(r"[0-9a-f]{64}", saved["content_hash"])
    contract = tmp_path / "items" / item.id / "contract.yaml"
    assert saved["content_hash"] == hashing_module().content_hash(contract, load_draft())

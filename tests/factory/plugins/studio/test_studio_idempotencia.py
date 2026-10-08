"""Idempotência por (item_id, stage) (#16): rodar o estágio de novo não duplica eventos nem re-renderiza."""

from __future__ import annotations

from tests.factory.plugins.studio._studio import json_store, make_item, make_stage, stub_renderer


def test_segunda_execucao_nao_duplica_eventos_nem_renderiza(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)
    renderer = stub_renderer(tmp_path)
    stage = make_stage(tmp_path, renderer=renderer)
    stage.run(item, store)
    events_before = [(e.seq, e.kind, e.data) for e in store.read()]
    item_bytes_before = (tmp_path / "factory" / "items" / f"{item.id}.json").read_bytes()

    stage.run(store.get_item(item.id), store)

    assert [(e.seq, e.kind, e.data) for e in store.read()] == events_before
    assert len(renderer.calls) == 1
    assert (tmp_path / "factory" / "items" / f"{item.id}.json").read_bytes() == item_bytes_before
    assert store.get_item(item.id).state == "rendered"


def test_item_ja_rendered_nao_e_renderizado_de_novo(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)
    make_stage(tmp_path).run(item, store)
    renderer = stub_renderer(tmp_path)

    make_stage(tmp_path, renderer=renderer).run(store.get_item(item.id), store)

    assert renderer.calls == []

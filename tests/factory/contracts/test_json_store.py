"""JsonStore (#33): arquivo JSON por item em SIMPLICIO_FACTORY_HOME, sobrevive a um novo processo (nova instância)."""

from __future__ import annotations

import importlib
from pathlib import Path

from tests.factory._fixtures import contracts, json_store, make_item

ROOT = Path(__file__).resolve().parents[3]


def _json_class():
    return importlib.import_module("simplicio_factory.contracts.json_store").JsonStore


def test_item_and_events_survive_a_new_store_instance(tmp_path):
    root = tmp_path / "factory"
    first = json_store(root)
    item = make_item()
    first.save_item(item)
    contracts().transition(item, "drafted", first)

    second = json_store(root)

    assert second.get_item(item.id) == item
    events = second.read()
    assert [e.kind for e in events] == ["item.state_changed"]


def test_one_json_file_per_item_under_root(tmp_path):
    root = tmp_path / "factory"
    store = json_store(root)
    item = make_item()

    store.save_item(item)

    files = [p for p in root.rglob("*.json") if item.id in p.read_text(encoding="utf-8")]
    assert len(files) == 1


def test_root_comes_from_simplicio_factory_home_env(tmp_path, monkeypatch):
    home = tmp_path / "home-da-fabrica"
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))
    store = _json_class()()
    item = make_item()

    store.save_item(item)

    assert any(item.id in p.read_text(encoding="utf-8") for p in home.rglob("*.json"))


def test_factory_home_default_is_gitignored():
    lines = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert ".simplicio-factory/" in lines

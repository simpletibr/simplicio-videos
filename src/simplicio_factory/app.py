"""Composição do kernel: escolhe o Store padrão (JsonStore em SIMPLICIO_FACTORY_HOME)."""

from __future__ import annotations

from simplicio_factory.contracts.json_store import JsonStore


def default_store() -> JsonStore:
    return JsonStore()

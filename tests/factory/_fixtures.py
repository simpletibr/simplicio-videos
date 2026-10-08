"""Helpers compartilhados pelos testes do kernel (#33).

Não há `tests/factory/conftest.py`: um segundo conftest.py em `tests/` deu conflito de nome no pytest (#43).
Os testes importam estes helpers explicitamente: `from tests.factory._fixtures import make_item`.
Os imports de `simplicio_factory` ficam dentro das funções, para que um módulo ausente falhe no teste
(e não na coleta, que interrompe a suíte inteira).
"""

from __future__ import annotations

import importlib

VALID_STATES = ("idea", "drafted", "rendering", "rendered", "failed")

# Única lista de transições válidas do MVP (decisão da #33 em m0a-decisions.md).
VALID_TRANSITIONS = (
    ("idea", "drafted"),
    ("drafted", "rendering"),
    ("rendering", "rendered"),
    ("rendering", "failed"),
)


def contracts():
    return importlib.import_module("simplicio_factory.contracts")


def kit_module():
    return importlib.import_module("simplicio_factory.testkit")


def make_item(state: str = "idea", item_id: str = "itm_01HZTEST0000000000000001", brand: str = "acme"):
    """Item mínimo: `Item(id, brand, state, failed_from=None)`."""
    return contracts().Item(id=item_id, brand=brand, state=state)


def memory_store():
    return kit_module().MemoryStore()


def json_store(root):
    return importlib.import_module("simplicio_factory.contracts.json_store").JsonStore(root)

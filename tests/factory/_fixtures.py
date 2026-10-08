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


# Rotas de produção (#82, épico #81): grafos completos de cada rota. O grafo `deterministic` é o de VALID_TRANSITIONS.
ROUTES = ("deterministic", "ai_assisted")
ALL_STATES = (
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
DETERMINISTIC_TRANSITIONS = frozenset(VALID_TRANSITIONS)
AI_ASSISTED_TRANSITIONS = frozenset(
    {
        ("idea", "drafted"),
        ("drafted", "quoted"),
        ("quoted", "drafted"),
        ("quoted", "approved"),
        ("approved", "generating"),
        ("generating", "generated"),
        ("generating", "failed"),
        ("generated", "rendering"),
        ("rendering", "rendered"),
        ("rendering", "failed"),
    }
)
ROUTE_TRANSITIONS = {"deterministic": DETERMINISTIC_TRANSITIONS, "ai_assisted": AI_ASSISTED_TRANSITIONS}
AI_MEDIA_STEP = {"kind": "ai_media", "provider": "provedor-teste"}


def ai_production(steps=None):
    """`production` de um item ai_assisted. Sem `steps`, traz um passo ai_media com provider não vazio."""
    return {"route": "ai_assisted", "steps": [dict(AI_MEDIA_STEP)] if steps is None else steps}


def make_routed_item(state: str = "idea", production=None, review=None, item_id: str = "itm_01HZTEST0000000000000001", brand: str = "acme"):
    """Item com `production` e `review` atribuídos após a construção, para que a falha caia na transição
    (InvalidTransition) e não num TypeError do construtor. `production=None` = item sem `production` (compatibilidade)."""
    item = make_item(state=state, item_id=item_id, brand=brand)
    if production is not None:
        item.production = production
    if review is not None:
        item.review = review
    return item


def transitions_module():
    return importlib.import_module("simplicio_factory.contracts.transitions")


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

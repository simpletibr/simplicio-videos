"""transition(item, to, store): a única forma de mudar o estado de um item (#33; rotas em #82, épico #81).

Cada rota tem o seu grafo. `deterministic` (MVP, #33): idea->drafted, drafted->rendering, rendering->rendered,
rendering->failed. `ai_assisted`: o fluxo com geração por IA (quoted, approved, generating, generated).
`drafted->quoted` exige um passo `ai_media` com `provider` não vazio em `item.production["steps"]`.
Qualquer outra transição levanta InvalidTransition, sem mudar o item e sem evento.
"""

from __future__ import annotations

from simplicio_factory.contracts.errors import InvalidTransition
from simplicio_factory.contracts.models import DEFAULT_ROUTE, ROUTES, Event, Item
from simplicio_factory.contracts.protocols import Store

DETERMINISTIC_TRANSITIONS = frozenset(
    {
        ("idea", "drafted"),
        ("drafted", "rendering"),
        ("rendering", "rendered"),
        ("rendering", "failed"),
    }
)

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

ROUTE_TRANSITIONS = {
    "deterministic": DETERMINISTIC_TRANSITIONS,
    "ai_assisted": AI_ASSISTED_TRANSITIONS,
}

# Grafo da rota determinística (compatibilidade com os testes e importações da #33).
VALID_TRANSITIONS = DETERMINISTIC_TRANSITIONS

EVENT_STATE_CHANGED = "item.state_changed"
AI_MEDIA_KIND = "ai_media"


def transitions_for(route: str) -> frozenset:
    """Conjunto de transições (src, dst) válidas na rota dada."""
    if route not in ROUTES:
        raise ValueError(f"rota de produção inválida: {route!r}")
    return ROUTE_TRANSITIONS[route]


def _route_of(item: Item) -> str:
    return (item.production or {}).get("route", DEFAULT_ROUTE)


def _has_ai_media_step(item: Item) -> bool:
    for step in (item.production or {}).get("steps") or []:
        if not isinstance(step, dict) or step.get("kind") != AI_MEDIA_KIND:
            continue
        provider = step.get("provider")
        if isinstance(provider, str) and provider.strip():
            return True
    return False


def transition(item: Item, to: str, store: Store) -> Event:
    src = item.state
    route = _route_of(item)
    if (src, to) not in transitions_for(route):
        raise InvalidTransition(f"transição inválida na rota {route}: {src} -> {to}")
    if route == "ai_assisted" and (src, to) == ("drafted", "quoted") and not _has_ai_media_step(item):
        raise InvalidTransition("drafted -> quoted exige um passo ai_media com provider na rota ai_assisted")
    item.state = to
    if to == "failed":
        item.failed_from = src
    store.save_item(item)
    return store.append_event(EVENT_STATE_CHANGED, item.id, {"from": src, "to": to, "route": route})

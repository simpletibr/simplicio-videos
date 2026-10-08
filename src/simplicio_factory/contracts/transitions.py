"""transition(item, to, store): a única forma de mudar o estado de um item (#33).

Grafo do MVP: idea->drafted, drafted->rendering, rendering->rendered, rendering->failed.
Qualquer outra transição (inclusive failed->drafted) levanta InvalidTransition, sem mudar o item e sem evento.
"""

from __future__ import annotations

from simplicio_factory.contracts.errors import InvalidTransition
from simplicio_factory.contracts.models import Event, Item
from simplicio_factory.contracts.protocols import Store

VALID_TRANSITIONS = frozenset(
    {
        ("idea", "drafted"),
        ("drafted", "rendering"),
        ("rendering", "rendered"),
        ("rendering", "failed"),
    }
)

EVENT_STATE_CHANGED = "item.state_changed"


def transition(item: Item, to: str, store: Store) -> Event:
    src = item.state
    if (src, to) not in VALID_TRANSITIONS:
        raise InvalidTransition(f"transição inválida: {src} -> {to}")
    item.state = to
    if to == "failed":
        item.failed_from = src
    store.save_item(item)
    return store.append_event(EVENT_STATE_CHANGED, item.id, {"from": src, "to": to})

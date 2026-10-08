"""transition(item, to, store): a única forma de mudar o estado de um item (#33, decisão do MVP).

Valid: idea->drafted, drafted->rendering, rendering->rendered, rendering->failed. Qualquer outra transição
levanta InvalidTransition, não muda o estado e não emite evento. Cada transição válida emite um evento
`item.state_changed` no store.
"""

from __future__ import annotations

import pytest

from tests.factory._fixtures import VALID_STATES, VALID_TRANSITIONS, contracts, make_item, memory_store

EXTRA_TARGETS = ("discarded", "in_review", "bogus")  # estados da spec ou inexistentes: nunca válidos no MVP
INVALID_TRANSITIONS = [
    (src, dst)
    for src in VALID_STATES
    for dst in (*VALID_STATES, *EXTRA_TARGETS)
    if (src, dst) not in VALID_TRANSITIONS
]


@pytest.mark.parametrize(("src", "dst"), VALID_TRANSITIONS, ids=lambda t: t)
def test_valid_transition_changes_state_and_emits_one_event(src, dst):
    store = memory_store()
    item = make_item(state=src)
    before = len(store.read())

    contracts().transition(item, dst, store)

    assert item.state == dst
    events = store.read()
    assert len(events) == before + 1
    assert events[-1].kind == "item.state_changed"
    assert events[-1].item_id == item.id


def test_entering_failed_records_failed_from():
    store = memory_store()
    item = make_item(state="rendering")

    contracts().transition(item, "failed", store)

    assert item.state == "failed"
    assert item.failed_from == "rendering"


@pytest.mark.parametrize(("src", "dst"), INVALID_TRANSITIONS, ids=lambda t: t)
def test_other_transitions_raise_invalid_transition(src, dst):
    """A spec admite failed->drafted (retry) e outras; o MVP só aceita as quatro transições válidas."""
    store = memory_store()
    item = make_item(state=src)

    with pytest.raises(contracts().InvalidTransition):
        contracts().transition(item, dst, store)

    assert item.state == src
    assert store.read() == []

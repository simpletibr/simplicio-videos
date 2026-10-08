"""Grafo por rota de produção (#82, épico #81): `deterministic` (inalterado) e `ai_assisted`.

`transition(item, to, store)` usa o grafo da rota do item; `transitions_for(route)` devolve o conjunto da rota.
Os imports do kernel ficam dentro das funções (via tests.factory._fixtures), então um símbolo ausente falha
no teste (AttributeError/AssertionError) e não na coleta.
"""

from __future__ import annotations

import pytest

from tests.factory._fixtures import (
    AI_ASSISTED_TRANSITIONS,
    AI_MEDIA_STEP,
    ALL_STATES,
    DETERMINISTIC_TRANSITIONS,
    ROUTE_TRANSITIONS,
    ROUTES,
    ai_production,
    contracts,
    make_routed_item,
    memory_store,
    transitions_module,
)


def _invalid_pairs():
    for route in ROUTES:
        for src in ALL_STATES:
            for dst in ALL_STATES:
                if (src, dst) not in ROUTE_TRANSITIONS[route]:
                    yield pytest.param(route, src, dst, id=f"{route}:{src}->{dst}")


def _item_in(route: str, state: str):
    if route == "ai_assisted":
        return make_routed_item(state=state, production=ai_production())
    return make_routed_item(state=state, production={"route": "deterministic"})


@pytest.mark.parametrize("route", ROUTES)
def test_transitions_for_returns_exactly_the_route_graph(route):
    assert transitions_module().transitions_for(route) == ROUTE_TRANSITIONS[route]


@pytest.mark.parametrize(("src", "dst"), sorted(DETERMINISTIC_TRANSITIONS))
def test_deterministic_valid_transition_emits_event_with_route(src, dst):
    store = memory_store()
    item = _item_in("deterministic", src)

    contracts().transition(item, dst, store)

    assert item.state == dst
    events = store.read()
    assert len(events) == 1
    assert events[0].kind == "item.state_changed"
    assert events[0].item_id == item.id
    assert events[0].data["from"] == src
    assert events[0].data["to"] == dst
    assert events[0].data["route"] == "deterministic"


@pytest.mark.parametrize(("src", "dst"), sorted(AI_ASSISTED_TRANSITIONS))
def test_ai_assisted_valid_transition_changes_state_and_emits_event_with_route(src, dst):
    store = memory_store()
    item = _item_in("ai_assisted", src)

    contracts().transition(item, dst, store)

    assert item.state == dst
    events = store.read()
    assert len(events) == 1
    assert events[0].kind == "item.state_changed"
    assert events[0].item_id == item.id
    assert events[0].data["from"] == src
    assert events[0].data["to"] == dst
    assert events[0].data["route"] == "ai_assisted"


@pytest.mark.parametrize(("route", "src", "dst"), _invalid_pairs())
def test_transition_outside_route_graph_raises_and_changes_nothing(route, src, dst):
    store = memory_store()
    item = _item_in(route, src)

    with pytest.raises(contracts().InvalidTransition):
        contracts().transition(item, dst, store)

    assert item.state == src
    assert store.read() == []


@pytest.mark.parametrize("dst", ["quoted", "approved", "generating", "generated"])
def test_deterministic_item_rejects_ai_only_states(dst):
    store = memory_store()
    item = _item_in("deterministic", "drafted")

    with pytest.raises(contracts().InvalidTransition):
        contracts().transition(item, dst, store)

    assert item.state == "drafted"
    assert store.read() == []


def test_ai_assisted_item_rejects_drafted_to_rendering():
    store = memory_store()
    item = _item_in("ai_assisted", "drafted")

    with pytest.raises(contracts().InvalidTransition):
        contracts().transition(item, "rendering", store)

    assert item.state == "drafted"
    assert store.read() == []


def test_ai_assisted_failure_from_generating_records_failed_from():
    store = memory_store()
    item = _item_in("ai_assisted", "generating")

    contracts().transition(item, "failed", store)

    assert item.state == "failed"
    assert item.failed_from == "generating"


@pytest.mark.parametrize(
    "production",
    [
        pytest.param({"route": "ai_assisted"}, id="sem-steps"),
        pytest.param({"route": "ai_assisted", "steps": []}, id="steps-vazio"),
        pytest.param({"route": "ai_assisted", "steps": [{"kind": "script"}]}, id="sem-ai_media"),
        pytest.param({"route": "ai_assisted", "steps": [{"kind": "ai_media"}]}, id="ai_media-sem-provider"),
        pytest.param({"route": "ai_assisted", "steps": [{"kind": "ai_media", "provider": ""}]}, id="provider-vazio"),
        pytest.param({"route": "ai_assisted", "steps": [{"kind": "ai_media", "provider": "   "}]}, id="provider-espaco"),
        pytest.param({"route": "ai_assisted", "steps": [{"kind": "ai_media", "provider": None}]}, id="provider-none"),
    ],
)
def test_drafted_to_quoted_requires_ai_media_step_with_provider(production):
    store = memory_store()
    item = make_routed_item(state="drafted", production=production)

    with pytest.raises(contracts().InvalidTransition, match="ai_media"):
        contracts().transition(item, "quoted", store)

    assert item.state == "drafted"
    assert store.read() == []


def test_drafted_to_quoted_accepts_ai_media_step_among_other_steps():
    store = memory_store()
    item = make_routed_item(
        state="drafted",
        production={"route": "ai_assisted", "steps": [{"kind": "script"}, dict(AI_MEDIA_STEP)]},
    )

    contracts().transition(item, "quoted", store)

    assert item.state == "quoted"


@pytest.mark.parametrize("review", [None, "pending", "approved", "changes_requested"])
def test_review_value_does_not_change_either_graph(review):
    store = memory_store()
    deterministic = make_routed_item(state="drafted", production={"route": "deterministic"}, review=review)
    ai_assisted = make_routed_item(state="drafted", production=ai_production(), review=review)

    with pytest.raises(contracts().InvalidTransition):
        contracts().transition(deterministic, "quoted", store)
    assert deterministic.state == "drafted"
    assert deterministic.review == review

    contracts().transition(ai_assisted, "quoted", store)
    assert ai_assisted.state == "quoted"
    assert ai_assisted.review == review


@pytest.mark.parametrize("production", [None, {"steps": []}, {"route": "deterministic"}], ids=["sem-production", "sem-route", "route-explicita"])
def test_item_without_ai_route_follows_deterministic_graph(production):
    store = memory_store()
    item = make_routed_item(state="drafted", production=production)

    contracts().transition(item, "rendering", store)

    assert item.state == "rendering"
    assert store.read()[-1].data["route"] == "deterministic"

    other = make_routed_item(state="drafted", production=production)
    with pytest.raises(contracts().InvalidTransition):
        contracts().transition(other, "quoted", memory_store())
    assert other.state == "drafted"


def test_failed_item_has_no_outgoing_transition_in_either_route():
    for route in ROUTES:
        store = memory_store()
        item = _item_in(route, "failed")
        for dst in ALL_STATES:
            with pytest.raises(contracts().InvalidTransition):
                contracts().transition(item, dst, store)
        assert item.state == "failed"
        assert store.read() == []

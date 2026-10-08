"""Orçamento de mídia (#85): media_credits do workspace, teto diário e as recusas de aprovação."""

from __future__ import annotations

import argparse
from datetime import date

import pytest
import yaml

from tests.factory.plugins.media._fixtures import ITEM_ID, budget_module, escreve_policy


def test_teto_diario_padrao_e_mil_creditos():
    assert budget_module().DEFAULT_DAILY_CAP == 1000


def test_media_credits_sem_workspace_e_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", str(tmp_path / "ws-inexistente"))

    assert budget_module().media_credits() == 0


def test_media_credits_sem_a_chave_e_zero(monkeypatch, tmp_path):
    ws = tmp_path / "ws"
    escreve_policy(ws, media_credits=None)
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", str(ws))

    assert budget_module().media_credits() == 0


def test_media_credits_le_budgets_media_credits_do_policy(monkeypatch, tmp_path):
    ws = tmp_path / "ws"
    escreve_policy(ws, media_credits=750)
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", str(ws))

    assert budget_module().media_credits() == 750


def test_chave_gravada_pelo_setup_e_lida_pelo_media(monkeypatch, tmp_path):
    from simplicio_video.commands import setup

    ws = tmp_path / "ws"
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", str(ws))
    codigo = setup.run(
        argparse.Namespace(
            yes=True, theme=None, lang=None, force=False, realoficial=False
        )
    )

    assert codigo == 0
    dados = yaml.safe_load((ws / "policy.yaml").read_text(encoding="utf-8"))
    assert dados["budgets"]["media_credits"] == 0
    assert budget_module().media_credits() == 0


def test_orcamento_zero_recusa_qualquer_aprovacao():
    with pytest.raises(budget_module().BudgetError, match="orçamento"):
        budget_module().verifica_aprovacao(
            credits=10, media=0, daily_cap=1000, gasto_hoje=0
        )


def test_recusa_credits_acima_de_media_credits():
    with pytest.raises(budget_module().BudgetError, match="media_credits"):
        budget_module().verifica_aprovacao(
            credits=600, media=500, daily_cap=1000, gasto_hoje=0
        )


def test_recusa_credits_acima_do_teto_diario():
    with pytest.raises(budget_module().BudgetError, match="teto diário"):
        budget_module().verifica_aprovacao(
            credits=1001, media=5000, daily_cap=1000, gasto_hoje=0
        )


def test_recusa_quando_o_gasto_do_dia_mais_o_novo_passa_do_teto():
    with pytest.raises(budget_module().BudgetError, match="teto diário"):
        budget_module().verifica_aprovacao(
            credits=500, media=5000, daily_cap=1000, gasto_hoje=600
        )


def test_aceita_exatamente_no_teto_diario():
    budget_module().verifica_aprovacao(
        credits=400, media=5000, daily_cap=1000, gasto_hoje=600
    )


def test_teto_diario_padrao_vale_quando_nao_informado():
    with pytest.raises(budget_module().BudgetError, match="teto diário"):
        budget_module().verifica_aprovacao(credits=1001, media=5000)


def test_gasto_do_dia_soma_so_aprovados_do_dia_em_brt(tmp_path):
    from simplicio_factory.contracts.json_store import JsonStore

    store = JsonStore(tmp_path / "home")
    store.append_event(
        "spend.approved", ITEM_ID, {"credits": 300, "at": "2026-10-08T10:00:00-03:00"}
    )
    store.append_event(
        "spend.approved", ITEM_ID, {"credits": 50, "at": "2026-10-08T13:00:00+00:00"}
    )
    store.append_event(
        "spend.approved", ITEM_ID, {"credits": 200, "at": "2026-10-07T23:00:00-03:00"}
    )
    store.append_event(
        "spend.approved", ITEM_ID, {"credits": 100, "at": "2026-10-08T02:00:00+00:00"}
    )
    store.append_event(
        "spend.quoted", ITEM_ID, {"credits": 999, "at": "2026-10-08T10:00:00-03:00"}
    )
    store.append_event(
        "item.state_changed", ITEM_ID, {"from": "quoted", "to": "approved"}
    )

    assert budget_module().gasto_do_dia(store.read(), date(2026, 10, 8)) == 350
    assert budget_module().gasto_do_dia(store.read(), date(2026, 10, 9)) == 0

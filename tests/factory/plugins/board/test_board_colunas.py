"""Colunas do quadro (#86, épico #81): derivadas de state e review, nunca guardadas; uma linha por estado e rota."""

from __future__ import annotations

import pytest

from tests.factory.plugins.board._fixtures import (
    CHAVES_DE_COLUNA,
    TITULOS_DE_COLUNA,
    ler_item_cru,
    model_module,
    cartao_em,
    home_de,
    salvar_item,
    service_module,
)

# (estado, review, coluna esperada) com um item por estado, para cada rota.
TABELA_DETERMINISTICA = [
    ("idea", None, "ideia"),
    ("drafted", None, "roteiro"),
    ("rendering", None, "gerando"),
    ("rendered", None, "revisao"),
    ("rendered", "pending", "revisao"),
    ("rendered", "changes_requested", "revisao"),
    ("rendered", "approved", "pronto"),
    ("failed", None, "falhou"),
]

TABELA_AI_ASSISTED = [
    ("idea", None, "ideia"),
    ("drafted", None, "roteiro"),
    ("quoted", None, "orcamento"),
    ("approved", None, "aprovado"),
    ("generating", None, "gerando"),
    ("generated", None, "gerando"),
    ("rendering", None, "gerando"),
    ("rendered", None, "revisao"),
    ("rendered", "approved", "pronto"),
    ("failed", None, "falhou"),
]


@pytest.mark.parametrize("state,review,esperada", TABELA_DETERMINISTICA + TABELA_AI_ASSISTED)
def test_coluna_de_segue_a_tabela(state, review, esperada):
    assert model_module().coluna_de(state, review) == esperada


@pytest.mark.parametrize("route", ["deterministic", "ai_assisted"])
def test_listar_poe_cada_item_na_coluna_da_tabela_da_sua_rota(tmp_path, route):
    tabela = TABELA_DETERMINISTICA if route == "deterministic" else TABELA_AI_ASSISTED
    home = home_de(tmp_path)
    esperadas = {}
    for n, (state, review, coluna) in enumerate(tabela):
        item_id = f"itm_COL{route[:3]}{n:03d}"
        salvar_item(home, state, route=route, review=review, item_id=item_id)
        esperadas[item_id] = coluna

    quadro = service_module().listar(home)

    for item_id, coluna in esperadas.items():
        achada, cartao = cartao_em(quadro, item_id)
        assert achada == coluna, f"{item_id} deveria estar em {coluna}, está em {achada}"
        assert cartao["route"] == route


def test_quadro_tem_as_oito_colunas_na_ordem_do_pedido(tmp_path):
    quadro = service_module().listar(home_de(tmp_path))

    assert [c["id"] for c in quadro["columns"]] == list(CHAVES_DE_COLUNA)
    assert [c["title"] for c in quadro["columns"]] == list(TITULOS_DE_COLUNA)
    assert all(c["cards"] == [] for c in quadro["columns"])


def test_colunas_da_rota_determinista_so_passam_pelas_etapas_previstas():
    colunas = model_module().colunas_da_rota("deterministic")

    # Ideia, Roteiro, Gerando (rendering), Revisão e Pronto; Falhou é o caminho de erro do render.
    assert colunas == frozenset({"ideia", "roteiro", "gerando", "revisao", "pronto", "falhou"})
    assert "orcamento" not in colunas
    assert "aprovado" not in colunas


def test_colunas_da_rota_ai_assisted_incluem_orcamento_e_aprovado():
    colunas = model_module().colunas_da_rota("ai_assisted")

    assert colunas == frozenset(CHAVES_DE_COLUNA)


def test_colunas_nao_sao_guardadas_no_item(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered", review="approved")
    antes = ler_item_cru(home)

    service_module().listar(home)

    depois = ler_item_cru(home)
    assert depois == antes
    assert set(depois) <= {"schema", "id", "brand", "state", "failed_from", "production", "review"}

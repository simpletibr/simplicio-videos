"""Revisão humana do quadro (#86, épico #81): `review approve` leva Revisão -> Pronto; `changes` mantém em Revisão."""

from __future__ import annotations

import json

import pytest

from tests.factory.plugins.board._fixtures import (
    ITEM_ID,
    cartao_em,
    fixed_clock,
    home_de,
    ler_item_cru,
    run_cli,
    salvar_item,
    service_module,
)


def _ultimo_comentario(home):
    linhas = service_module().caminho_comentarios(home, ITEM_ID).read_text(encoding="utf-8").splitlines()
    return json.loads(linhas[-1])


def test_approve_leva_revisao_para_pronto(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    svc = service_module()
    assert cartao_em(svc.listar(home), ITEM_ID)[0] == "revisao"

    svc.revisar(home, ITEM_ID, "approve", "Ana", relogio=fixed_clock())

    assert ler_item_cru(home)["review"] == "approved"
    assert cartao_em(svc.listar(home), ITEM_ID)[0] == "pronto"
    ultimo = _ultimo_comentario(home)
    assert ultimo["kind"] == "review"
    assert ultimo["by"] == "Ana"
    assert ultimo["text"].strip(), "a revisão sem --note também grava um texto na linha"


def test_changes_mantem_em_revisao_e_grava_a_nota(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    svc = service_module()

    svc.revisar(home, ITEM_ID, "changes", "Bruno", note="trocar a cor do logo", relogio=fixed_clock())

    assert ler_item_cru(home)["review"] == "changes_requested"
    assert cartao_em(svc.listar(home), ITEM_ID)[0] == "revisao"
    ultimo = _ultimo_comentario(home)
    assert ultimo["kind"] == "review"
    assert ultimo["text"] == "trocar a cor do logo"


def test_changes_depois_approve_chega_a_pronto(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    svc = service_module()

    svc.revisar(home, ITEM_ID, "changes", "Ana", note="refazer o final", relogio=fixed_clock())
    svc.revisar(home, ITEM_ID, "approve", "Ana", relogio=fixed_clock())

    assert cartao_em(svc.listar(home), ITEM_ID)[0] == "pronto"


def test_review_so_vale_para_item_renderizado(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "drafted")
    antes = ler_item_cru(home)
    svc = service_module()

    with pytest.raises(svc.BoardError):
        svc.revisar(home, ITEM_ID, "approve", "Ana", relogio=fixed_clock())

    assert ler_item_cru(home) == antes
    assert not svc.caminho_comentarios(home, ITEM_ID).exists()


def test_decisao_invalida_e_recusada_pela_cli(tmp_path, monkeypatch):
    home = home_de(tmp_path)
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))
    salvar_item(home, "rendered")
    antes = ler_item_cru(home)

    code, _, _ = run_cli(["review", ITEM_ID, "talvez", "--by", "Ana"])

    assert code == 2
    assert ler_item_cru(home) == antes


def test_review_pela_cli_aprova_e_muda_a_coluna(tmp_path, monkeypatch):
    home = home_de(tmp_path)
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))
    salvar_item(home, "rendered")

    code, _, _ = run_cli(["review", ITEM_ID, "approve", "--by", "Ana", "--note", "pode publicar"])

    assert code == 0
    assert ler_item_cru(home)["review"] == "approved"
    assert _ultimo_comentario(home)["text"] == "pode publicar"
    assert cartao_em(service_module().listar(home), ITEM_ID)[0] == "pronto"

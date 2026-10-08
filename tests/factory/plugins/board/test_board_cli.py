"""CLI do quadro (#86, épico #81): `board list [--json]`, help com exemplo, manifesto e `plugin list`."""

from __future__ import annotations

import json

from tests.factory.plugins.board._fixtures import (
    CHAVES_DE_COLUNA,
    ITEM_ID,
    MANIFEST_PATH,
    TITULOS_DE_COLUNA,
    carregar_validador,
    cli_module,
    fixed_clock,
    home_de,
    run_cli,
    salvar_item,
    service_module,
)


def test_board_help_mostra_exemplo():
    code, out, _ = run_cli(["--help"])

    assert code == 0
    assert "Exemplo" in out
    assert "simplicio-video board" in out


def test_cada_subcomando_tem_help_com_exemplo():
    for sub in ("list", "comment", "review"):
        code, out, _ = run_cli([sub, "--help"])

        assert code == 0, sub
        assert f"simplicio-video board {sub}" in out, sub


def test_list_sem_itens_mostra_todas_as_colunas(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home_de(tmp_path)))

    code, out, _ = run_cli(["list"])

    assert code == 0
    for titulo in TITULOS_DE_COLUNA:
        assert titulo in out


def test_list_json_valida_contra_o_schema(tmp_path, monkeypatch):
    home = home_de(tmp_path)
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))
    salvar_item(home, "rendered", review="approved")
    salvar_item(home, "drafted", item_id="itm_01HZBOARD00000000000002")

    code, out, _ = run_cli(["list", "--json"])

    assert code == 0
    quadro = json.loads(out)
    assert quadro["schema"] == "simplicio.board/v1"
    assert [c["id"] for c in quadro["columns"]] == list(CHAVES_DE_COLUNA)
    assert list(carregar_validador().iter_errors(quadro)) == []


def test_list_json_e_deterministico(tmp_path, monkeypatch):
    home = home_de(tmp_path)
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))
    salvar_item(home, "rendered")
    service_module().comentar(home, ITEM_ID, "um comentário", "Ana", relogio=fixed_clock())

    primeiro = run_cli(["list", "--json"])[1]
    segundo = run_cli(["list", "--json"])[1]

    assert primeiro == segundo


def test_list_json_sem_itens_valida_contra_o_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home_de(tmp_path)))

    code, out, _ = run_cli(["list", "--json"])

    assert code == 0
    assert list(carregar_validador().iter_errors(json.loads(out))) == []


def test_subcomando_desconhecido_sai_com_2(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home_de(tmp_path)))

    code, _, _ = run_cli(["fazer-coisas"])

    assert code == 2


def test_plugin_list_mostra_o_board(capsys):
    from simplicio_video import cli

    code = cli.main(["plugin", "list"])

    assert code == 0
    assert "board" in capsys.readouterr().out


def test_manifesto_do_board_aponta_para_o_handler():
    manifesto = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifesto["id"] == "board"
    assert [c["name"] for c in manifesto["commands"]] == ["board"]
    assert manifesto["commands"][0]["handler"] == "simplicio_factory.plugins.board.cli:board_cmd"
    assert callable(cli_module().board_cmd)

"""Catálogo de ângulos de anúncio: 50 ângulos em 5 grupos, consultados por `list angles` (CLI) e `video.list` (MCP)."""
from __future__ import annotations

import json
import re

import pytest

from simplicio_video import catalog, cli, mcp_server, paths

GRUPOS = {"problema": 10, "prova": 10, "desejo": 10, "decisao": 10, "estrategia": 10}
CAMPOS = {"id", "nome", "grupo", "gatilho", "quando_usar", "gancho_exemplo", "cuidado"}
MARCADORES = {"produto", "beneficio", "problema", "publico", "setor", "cidade", "nome_cliente", "numero"}


@pytest.fixture
def dados():
    return json.loads((paths.data_dir() / "angles" / "angles.json").read_text(encoding="utf8"))


def test_arquivo_de_angulos_tem_schema_e_50_entradas(dados):
    assert dados["schema"] == "simplicio.ad-angles/v1"
    assert len(dados["angulos"]) == 50


def test_ids_sao_unicos_e_os_grupos_tem_10_cada(dados):
    ids = [a["id"] for a in dados["angulos"]]
    assert len(ids) == len(set(ids))
    for grupo, n in GRUPOS.items():
        assert sum(a["grupo"] == grupo for a in dados["angulos"]) == n, grupo


def test_cada_angulo_tem_exatamente_os_campos_e_nenhum_vazio(dados):
    for a in dados["angulos"]:
        assert set(a) == CAMPOS, a.get("id")
        assert all(isinstance(a[c], str) and a[c].strip() for c in CAMPOS), a["id"]


def test_ganchos_nao_tem_fato_inventado(dados):
    # Só fatos reais: nenhum número, preço, percentual ou prazo escrito no gancho; fatos entram por marcador.
    for a in dados["angulos"]:
        gancho = a["gancho_exemplo"]
        assert not re.search(r"\d", gancho), a["id"]
        assert "%" not in gancho and "R$" not in gancho, a["id"]
        assert set(re.findall(r"\{(\w+)\}", gancho)) <= MARCADORES, a["id"]
        assert 8 <= len(gancho.split()) <= 20, a["id"]


def test_nao_ha_emoji_nem_texto_de_outra_marca(dados):
    texto = json.dumps(dados, ensure_ascii=False)
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", texto)


def test_catalog_angles_lista_todos_e_filtra_por_grupo():
    d = paths.data_dir()
    todos = catalog.angles(d)
    assert len(todos) == 50
    assert {a["grupo"] for a in catalog.angles(d, grupo="prova")} == {"prova"}
    assert len(catalog.angles(d, grupo="prova")) == 10


def test_cli_list_angles_json(capsys):
    assert cli.main(["list", "angles", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 50 and rows[0]["id"]


def test_cli_list_angles_filtra_por_grupo(capsys):
    assert cli.main(["list", "angles", "--grupo", "decisao", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 10 and {r["grupo"] for r in rows} == {"decisao"}


def test_cli_list_angles_texto_mostra_id_e_grupo(capsys):
    assert cli.main(["list", "angles"]) == 0
    out = capsys.readouterr().out
    assert "agitacao-dor" in out and "problema" in out


def test_cli_grupo_so_vale_com_angles(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["list", "templates", "--grupo", "prova"])
    assert e.value.code == 2
    assert "--grupo" in capsys.readouterr().err


def test_cli_grupo_desconhecido_e_erro_de_uso(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["list", "angles", "--grupo", "inventado"])
    assert e.value.code == 2


def test_mcp_video_list_serve_angles():
    r = mcp_server.video_list("angles")
    assert r["ok"] is True and len(r["items"]) == 50


def test_mcp_video_list_filtra_angles_por_grupo():
    r = mcp_server.video_list("angles", grupo="estrategia")
    assert r["ok"] is True and len(r["items"]) == 10

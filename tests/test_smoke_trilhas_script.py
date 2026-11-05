"""Testes do `scripts/smoke_trilhas.py` (o smoke só de leitura das trilhas externas e do núcleo).

Dois níveis. As funções de formatação e de decisão rodam offline, sem CLI nem rede, e entram no `make check`.
O script de verdade roda contra o que está instalado nesta máquina: é o teste `integration`, fora do `make check`.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from simplicio_video import mcp_server, tools

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_trilhas.py"

AJUDA_OPENCUT = """usage: simplicio-video opencut [-h] ...

Clona e sobe o OpenCut.

positional arguments:
  args        clone [dir] | dev | where

options:
  -h, --help  show this help message and exit
"""

AJUDA_INSTAGRAM = """usage: simplicio-video instagram [-h] ...

positional arguments:
  args        clone [dir] | where [--skills] | status | skills | run FERRAMENTA
              [--forcar] [--bruto] [-- argumentos]

options:
  -h, --help  show this help message and exit
"""

AJUDA_CLONE = """usage: simplicio-video clone [-h] ...

positional arguments:
  args        argumentos repassados ao CLI do Hypit AI

options:
  -h, --help  show this help message and exit
"""


@pytest.fixture(scope="module")
def smoke():
    assert SCRIPT.is_file(), "scripts/smoke_trilhas.py does not exist"
    spec = importlib.util.spec_from_file_location("smoke_trilhas_sob_teste", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # dataclasses look the module up by name while the script is executed
    try:
        spec.loader.exec_module(modulo)
        yield modulo
    finally:
        sys.modules.pop(spec.name, None)


def _resultados_falsos(smoke):
    return [
        smoke.Resultado("opencut", "cli where", smoke.OK, "/root/.simplicio-video/tools/opencut",
                        via="cli", comando="simplicio-video opencut where", segundos=0.4),
        smoke.Resultado("voicestudio", "mcp video_voicestudio", smoke.SKIP, "não instalado", via="mcp"),
        smoke.Resultado("tinyfish", "cli status", smoke.FAIL, "rc 1: " + "detalhe longo " * 20, via="cli"),
    ]


def test_tabela_tem_cabecalho_uma_linha_por_checagem_e_detalhe_curto(smoke):
    linhas = smoke.formatar_tabela(_resultados_falsos(smoke)).splitlines()
    cabecalho = [c.strip() for c in linhas[0].split("|")]
    assert cabecalho[:3] == ["trilha", "checagem", "estado"]
    assert "detalhe" in linhas[0]
    assert len(linhas) == 2 + 3  # cabeçalho, separador e as três checagens
    assert any("FAIL" in linha for linha in linhas)
    assert any("não instalado" in linha for linha in linhas)
    assert all(linha.endswith("...") for linha in linhas[2:] if "detalhe longo" in linha)


def test_json_tem_schema_contagem_e_ok_so_sem_fail(smoke):
    dados = smoke.formatar_json(_resultados_falsos(smoke), 1.25)
    assert dados["schema"] == "simplicio.smoke-trilhas/v1"
    assert dados["resumo"] == {"OK": 1, "FAIL": 1, "SKIP": 1}
    assert dados["ok"] is False
    assert [c["status"] for c in dados["checagens"]] == ["OK", "SKIP", "FAIL"]
    assert dados["checagens"][0]["comando"] == "simplicio-video opencut where"
    json.dumps(dados)  # serializável como está


def test_codigo_de_saida_so_reprova_com_fail(smoke):
    sem_fail = [r for r in _resultados_falsos(smoke) if r.estado != smoke.FAIL]
    assert smoke.codigo_de_saida(sem_fail) == 0
    assert smoke.codigo_de_saida(_resultados_falsos(smoke)) == 1


def test_subcomandos_saem_da_linha_args_do_help(smoke):
    assert smoke.subcomandos(AJUDA_OPENCUT) == {"clone", "dev", "where"}
    assert smoke.subcomandos(AJUDA_INSTAGRAM) == {"clone", "where", "status", "skills", "run"}
    assert smoke.subcomandos(AJUDA_CLONE) == set()  # texto livre: o help não lista subcomandos


def test_trilha_nao_instalada_so_roda_a_ajuda(smoke, monkeypatch):
    chamadas = []

    def cli_falso(argv):
        chamadas.append(list(argv))
        return smoke.Saida(0, AJUDA_OPENCUT, "")

    def mcp_proibido(funcao, kwargs):
        pytest.fail(f"a chamada MCP {funcao} não pode rodar com a trilha não instalada")

    monkeypatch.setattr(smoke, "_rodar_cli", cli_falso)
    monkeypatch.setattr(smoke, "_chamar_mcp", mcp_proibido)
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: False)

    res = smoke.checar_trilha("opencut")

    assert chamadas == [["opencut", "--help"]]  # nenhum `where` nem `status` roda sem o checkout
    assert {r.checagem: r.estado for r in res} == {
        "cli --help": "OK", "cli where": "SKIP", "cli status": "SKIP", "mcp video_opencut": "SKIP"}
    assert all(r.detalhe == "não instalado" for r in res if r.estado == "SKIP" and r.via == "cli" and "where" in r.checagem)


def test_where_quebrado_em_trilha_instalada_reprova(smoke, monkeypatch):
    def cli_falso(argv):
        if argv[1:] == ["where"]:
            return smoke.Saida(1, "", "boom")
        return smoke.Saida(0, AJUDA_OPENCUT, "")

    monkeypatch.setattr(smoke, "_rodar_cli", cli_falso)
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: ({"ok": True, "log": "/x"}, ""))
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: True)

    por_checagem = {r.checagem: r for r in smoke.checar_trilha("opencut")}

    assert por_checagem["cli where"].estado == smoke.FAIL
    assert por_checagem["cli where"].detalhe == "rc 1: boom"
    assert por_checagem["mcp video_opencut"].estado == smoke.OK
    assert smoke.codigo_de_saida(list(por_checagem.values())) == 1


def test_status_sem_json_le_o_texto(smoke, monkeypatch):
    def cli_falso(argv):
        if argv[-1] == "--json":
            return smoke.Saida(1, "", "moneyprinter: status não recebe argumentos; argumento a mais: --json")
        return smoke.Saida(0, "checkout: /x\n", "")

    monkeypatch.setattr(smoke, "_rodar_cli", cli_falso)
    r = smoke._checar_sub_cli("moneyprinter", "moneyprinter", "status", {"status"}, True, False)
    assert (r.estado, r.detalhe) == (smoke.OK, "texto (sem --json)")


def test_app_fechado_nao_reprova(smoke, monkeypatch):
    monkeypatch.setattr(smoke, "_rodar_cli", lambda argv: smoke.Saida(
        1, "", "voicestudio: não consegui falar com o VoiceStudio em http://127.0.0.1:3900/mcp/"))
    r = smoke._checar_sub_cli("voicestudio", "voicestudio", "status", {"status"}, True, False)
    assert r.estado == smoke.SKIP
    assert smoke.codigo_de_saida([r]) == 0


def test_chamadas_mcp_do_smoke_so_leem(smoke):
    permitidos = ("--help", "where", "status", ["fetch"])  # `fetch` sem URL é recusado antes de qualquer download
    for trilha, chamada in smoke.MCP_LEITURA.items():
        assert trilha in tools.TOOLS, trilha
        assert all(valor in permitidos for valor in chamada.kwargs.values()), (trilha, chamada.kwargs)
        assert hasattr(mcp_server, chamada.funcao), (trilha, chamada.funcao)


def test_toda_trilha_do_registro_tem_roteiro_no_smoke(smoke):
    assert set(tools.TOOLS) <= set(smoke.MCP_LEITURA)


@pytest.mark.integration
def test_smoke_trilhas_nesta_maquina_sem_fail():
    r = subprocess.run([sys.executable, str(SCRIPT), "--json"], capture_output=True, text=True, encoding="utf-8",
                       timeout=600, cwd=ROOT)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-2000:])
    dados = json.loads(r.stdout)
    assert dados["schema"] == "simplicio.smoke-trilhas/v1"
    assert [c for c in dados["checagens"] if c["status"] == "FAIL"] == []
    trilhas = {c["trilha"] for c in dados["checagens"]}
    assert set(tools.TOOLS) <= trilhas
    assert {"doctor --json", "status --json", "list templates", "validate", "mcp tools/list"} <= {
        c["checagem"] for c in dados["checagens"] if c["trilha"] == "core"}

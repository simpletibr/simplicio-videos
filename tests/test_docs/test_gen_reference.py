"""scripts/gen_reference.py --out DIR: writes docs/reference/*.md from the code, deterministically and completely.

Contract under test: the five files below appear in DIR; two runs (and a run from another cwd) give identical bytes;
every subcommand of simplicio_video.cli.build_parser() and each of its long options appear in cli.md; every MCP
tool of mcp_server.TOOLS appears in mcp-tools.md; every *.schema.json under src/simplicio_video/data/ appears in
schemas.md; every env var the package reads appears in config.md; events.md says it is empty.
"""
from __future__ import annotations

import argparse
import re

import pytest

from _docs import ROOT, run_script

REFERENCE_FILES = {"cli.md", "mcp-tools.md", "schemas.md", "events.md", "config.md"}
PKG = ROOT / "src" / "simplicio_video"
ENV_READ = re.compile(
    r"""(?:environ(?:\.get)?|getenv)\(\s*["']([A-Z][A-Z0-9_]+)["']|environ\[\s*["']([A-Z][A-Z0-9_]+)["']\]"""
)


def _gen(out):
    result = run_script("gen_reference.py", "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    return out


@pytest.fixture(scope="module")
def gerado(tmp_path_factory):
    """Uma geração só para o módulo: os testes que só leem a saída não pagam o gerador de novo (são ~3 s cada)."""
    return _gen(tmp_path_factory.mktemp("gerado") / "ref")


def _read(out, name):
    return (out / name).read_text(encoding="utf-8")


def _subcommands():
    from simplicio_video.cli import build_parser

    parser = build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action.choices


def test_gera_os_cinco_arquivos(gerado):
    assert {p.name for p in gerado.iterdir()} == REFERENCE_FILES


def test_duas_execucoes_geram_bytes_iguais(gerado, tmp_path):
    # Duas execuções: a do módulo (`gerado`) e uma de outro cwd, que é também uma segunda execução independente.
    other_cwd = tmp_path / "de-outro-cwd"
    other_cwd.mkdir()
    run_script("gen_reference.py", "--out", str(tmp_path / "c"), cwd=other_cwd)
    for name in sorted(REFERENCE_FILES):
        assert (gerado / name).read_bytes() == (tmp_path / "c" / name).read_bytes(), f"{name} muda entre execuções ou depende do cwd"


def test_cli_md_tem_todo_subcomando_e_toda_opcao_longa(gerado):
    text = _read(gerado, "cli.md")
    subcommands = _subcommands()
    assert subcommands, "build_parser() não tem subcomandos"
    for name, sub in subcommands.items():
        assert f"simplicio-video {name}" in text, f"subcomando {name!r} ausente de cli.md"
        for opt in sub._option_string_actions:
            if opt.startswith("--") and opt != "--help":
                assert opt in text, f"opção {name} {opt} ausente de cli.md (o help real não entrou)"


def test_mcp_tools_md_tem_toda_tool(gerado):
    from simplicio_video.mcp_server import TOOLS

    text = _read(gerado, "mcp-tools.md")
    for name, _fn, _desc in TOOLS:
        assert name in text, f"tool MCP {name!r} ausente de mcp-tools.md"


def test_schemas_md_tem_todo_schema_do_pacote(gerado):
    text = _read(gerado, "schemas.md")
    schemas = sorted((PKG / "data").rglob("*.schema.json"))
    assert schemas, "não achei schemas em src/simplicio_video/data/"
    for path in schemas:
        assert path.name in text, f"{path.name} ausente de schemas.md"


def test_config_md_tem_toda_variavel_lida_pelo_codigo(gerado):
    read = set()
    for path in PKG.rglob("*.py"):
        for match in ENV_READ.finditer(path.read_text(encoding="utf-8")):
            read.add(match.group(1) or match.group(2))
    read.discard("PATH")  # variável do sistema, não do produto
    assert "GEMINI_API_KEY" in read and "SIMPLICIO_OFFLINE" in read, "o scan não achou variáveis conhecidas"
    text = _read(gerado, "config.md")
    missing = sorted(name for name in read if name not in text)
    assert not missing, f"variáveis lidas pelo código ausentes de config.md: {missing}"


def test_eventos_vazio_com_aviso(gerado):
    assert "ainda não há eventos" in _read(gerado, "events.md").lower()


def test_cli_md_nao_depende_da_versao_do_python(gerado):
    """O argparse do 3.12 e o do 3.13 calculam a coluna de ajuda dos subcomandos de formas diferentes; o gerador fixa uma só.
    O cli.md gerado por qualquer Python suportado tem de ser igual ao commitado."""
    assert _read(gerado, "cli.md") == (ROOT / "docs" / "reference" / "cli.md").read_text(encoding="utf-8")

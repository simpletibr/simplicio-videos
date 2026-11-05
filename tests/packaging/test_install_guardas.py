"""Guardas do `install` contra as opções de remoção (review rev177, F1). argparse aceita abreviação de opção longa, e
`--uninstall` rodava antes de `--check`: `install --check --uninst` removia a skill e o recibo. Agora o parser não aceita
abreviação, `--check` e `--verify` não combinam com `--uninstall` (eles não escrevem; o uninstall remove), e o MCP recusa a
abreviação e a forma `--opt=valor` antes de rodar qualquer coisa. Testes em processo, com HOME e PATH selados (`caixa`)."""
from __future__ import annotations

import pytest

import _caixa
from _comum import executa, fotografia, make_bundle
from simplicio_video import distribution, mcp_server
from simplicio_video.cli import main

caixa = _caixa.caixa


@pytest.fixture
def falso(caixa, monkeypatch, tmp_path):
    """Um pacote mínimo no lugar das skills de verdade, e uma pasta de projeto que existe (como em test_cli_install.py)."""
    pacote = make_bundle(tmp_path / "bundle")
    monkeypatch.setattr(distribution, "bundle_root", lambda: pacote, raising=False)
    alvo = tmp_path / "proj"
    alvo.mkdir()
    caixa.bundle, caixa.alvo = pacote, alvo
    return caixa


def _instalado(falso, capsys) -> dict:
    """Instala no projeto e devolve a fotografia da pasta: o que as guardas precisam preservar."""
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0, err
    antes = fotografia(falso.alvo)
    assert any(caminho.endswith("SKILL.md") for caminho in antes), antes
    return antes


# --- o parser (CLI) ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [["--uninst"], ["--unins"], ["--global", "--prune-proj"], ["--global", "--prune-project"]])
def test_o_parser_recusa_abreviacao_das_opcoes_de_remocao_e_nao_remove_nada(falso, capsys, argv):
    antes = _instalado(falso, capsys)
    rc, out, err = executa(["install", *argv, "--target", str(falso.alvo)], capsys, main)
    assert rc == 2, (argv, rc, out, err)
    assert fotografia(falso.alvo) == antes


@pytest.mark.parametrize("flag", ["--check", "--verify"])
def test_check_e_verify_nao_combinam_com_uninstall_e_nao_removem_nada(falso, capsys, flag):
    antes = _instalado(falso, capsys)
    rc, out, err = executa(["install", flag, "--uninstall", "--target", str(falso.alvo)], capsys, main)
    assert rc == 2, (rc, out, err)
    assert fotografia(falso.alvo) == antes


# --- o MCP ----------------------------------------------------------------------------------------------------------------

def test_mcp_check_com_abreviacao_de_uninstall_nao_remove_a_skill(falso, capsys):
    antes = _instalado(falso, capsys)
    r = mcp_server.video_install(args=f"--check --uninst --target {falso.alvo}")
    assert r["ok"] is False, r
    assert fotografia(falso.alvo) == antes

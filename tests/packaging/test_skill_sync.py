"""`simplicio_video.skill_sync`: the table of the folders where each host keeps its skills (ported from simplicio-loop, 2034e2d).

`install --global` writes the skills into every one of these folders, with the ownership rules of the review of PR #117 (tests in
`test_install_seguranca.py` and `test_cli_install.py`): create what is missing, update only our own unedited copy, never overwrite a
file that was already there or that the user edited, never delete an extra file. The module itself holds only the table and the names
of the skills; it imports nothing from the package, so the installer (which runs under a system Python without PyYAML) can use it.
"""
from __future__ import annotations

import ast

import pytest

import _caixa
from _caixa import SISTEMAS, skill_sync
from _comum import ROOT

simula_so = _caixa.simula_so

# host -> where it keeps its skills under the home: the table of simplicio-loop (skill_sync.py), the same on all three systems
RAIZES_DO_LOOP = {
    "claude": ".claude/skills", "cursor": ".cursor/skills", "codex": ".codex/skills", "grok": ".grok/skills",
    "agents": ".agents/skills", "copilot": ".copilot/skills", "vscode": ".vscode/simplicio-skills",
    "opencode": ".config/opencode/skills", "amp": ".config/amp/skills", "kiro": ".kiro/steering",
    "simplicio_agent": ".simplicio-loop/skills",  # the folder the loop defines for that host
}


def test_as_skills_sao_as_do_simplicio_video():
    assert skill_sync.SKILLS == ("simplicio-video", "simplicio-video-social")


def test_a_tabela_de_hosts_e_a_do_loop():
    assert skill_sync.HOST_SKILL_ROOTS == RAIZES_DO_LOOP and len(skill_sync.HOST_SKILL_ROOTS) == 11


@pytest.mark.parametrize("so", SISTEMAS)
def test_as_pastas_sao_relativas_ao_home_e_com_barra_nos_tres_sistemas(simula_so, so):
    simula_so(so)
    for raiz in skill_sync.HOST_SKILL_ROOTS.values():
        assert not raiz.startswith("/") and "\\" not in raiz and ".." not in raiz.split("/")


def test_o_instalador_usa_a_mesma_tabela_e_este_modulo_nao_importa_nada_do_pacote():
    from _caixa import installer
    assert tuple(installer.GLOBAL_ROOTS) == tuple(skill_sync.HOST_SKILL_ROOTS.values())
    arvore = ast.parse((ROOT / "src" / "simplicio_video" / "skill_sync.py").read_text(encoding="utf-8"))
    relativos = [no for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.level > 0]
    assert relativos == [], "skill_sync.py is the registry: the installer imports it, never the other way round"

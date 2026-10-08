"""Contrato de `simplicio-video setup` (issue #43): cria o workspace (docs/factory/contracts.md, "Workspace layout").

Com --yes o wizard aceita os padrões, sem rede e sem login do Real Oficial. O workspace fica em
$SIMPLICIO_WORKSPACE (tmp_path). Nada pode ser escrito em ~.
"""
from __future__ import annotations

import yaml

from _comum import executa, exige_registrado
from simplicio_video.cli import main


def _le(ws, nome):
    return yaml.safe_load((ws / nome).read_text(encoding="utf8"))


def test_setup_cria_workspace_com_tema_idioma_l1_e_tokens_zero(casa, capsys):
    exige_registrado("setup", capsys, main)
    rc, out, err = executa(["setup", "--yes", "--theme", "br", "--lang", "pt-BR"], capsys, main)
    assert rc == 0, out + err

    wsp = _le(casa.workspace, "workspace.yaml")
    assert wsp["schema"] == "simplicio.workspace/v1"
    assert wsp["language"] == "pt-BR"
    assert wsp["settings"]["theme"] == "br"
    assert wsp["settings"]["ui_language"] == "pt-BR"

    pol = _le(casa.workspace, "policy.yaml")
    assert pol["schema"] == "simplicio.policy/v1"
    assert pol["autonomy"]["default"] == "L1"
    for limite in ("llm_tokens", "llm_usd", "media_credits"):
        assert pol["budgets"][limite] == 0, f"orçamento {limite} precisa começar em zero"


def test_setup_sem_escolhas_usa_autonomia_l1_e_zero_tokens(casa, capsys):
    exige_registrado("setup", capsys, main)
    rc, out, err = executa(["setup", "--yes"], capsys, main)
    assert rc == 0, out + err
    pol = _le(casa.workspace, "policy.yaml")
    assert pol["autonomy"]["default"] == "L1"
    assert pol["budgets"]["llm_tokens"] == 0


def test_setup_nao_escreve_fora_do_workspace(casa, capsys):
    exige_registrado("setup", capsys, main)
    rc, out, err = executa(["setup", "--yes"], capsys, main)
    assert rc == 0, out + err
    assert list(casa.home.iterdir()) == [], "setup escreveu no HOME"


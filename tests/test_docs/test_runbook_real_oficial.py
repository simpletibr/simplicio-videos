"""Runbook de geração por IA com o Real Oficial (#87, épico #81) cruzado com docs/realoficial.md.

Contrato: todo `ro_*` citado no runbook existe na lista de tools de docs/realoficial.md; cada passo numerado (`## N.`)
cita a ferramenta ou o comando certo, na ordem do fluxo; e o runbook não manda colar o link de mídia em lugar nenhum
que saia do chat.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "how-to" / "gerar-video-real-oficial.md"
REALOFICIAL = ROOT / "docs" / "realoficial.md"
RO = re.compile(r"\bro_[a-z0-9_]*[a-z0-9]\b")
PASSOS = {
    1: "ro_whoami",
    2: "ro_list_media_models",
    3: "ro_estimate_video",
    4: "generate quote",
    5: "generate approve",
    6: "ro_confirm_spend",
    7: "ro_list_media",
    8: "media_url",
    9: "media attach",
}


def _secao(texto: str, numero: int) -> str:
    """Texto do passo `## N.` até o próximo `## `."""
    cabecalho = re.search(rf"^## {numero}\. ", texto, flags=re.MULTILINE)
    assert cabecalho, (
        f"o runbook não tem o passo {numero} (cabeçalho '## {numero}. ...')"
    )
    resto = texto[cabecalho.end() :]
    proximo = re.search(r"^## ", resto, flags=re.MULTILINE)
    return resto[: proximo.start()] if proximo else resto


def test_runbook_existe():
    assert RUNBOOK.is_file(), f"falta {RUNBOOK.relative_to(ROOT)}"


def test_todo_ro_citado_no_runbook_existe_em_realoficial_md():
    runbook = set(RO.findall(RUNBOOK.read_text(encoding="utf-8")))
    lista = set(RO.findall(REALOFICIAL.read_text(encoding="utf-8")))

    assert runbook, "o runbook não cita nenhum ro_*"
    assert runbook - lista == set(), (
        f"ro_* do runbook que não estão em docs/realoficial.md: {sorted(runbook - lista)}"
    )


def test_cada_passo_numerado_cita_a_ferramenta_certa():
    texto = RUNBOOK.read_text(encoding="utf-8")

    for numero, marcador in PASSOS.items():
        assert marcador in _secao(texto, numero), f"passo {numero} sem {marcador!r}"


def test_passos_aparecem_em_ordem():
    texto = RUNBOOK.read_text(encoding="utf-8")
    cabecalhos = [
        int(n) for n in re.findall(r"^## (\d+)\. ", texto, flags=re.MULTILINE)
    ]

    assert cabecalhos == sorted(PASSOS), (
        f"passos fora de ordem ou faltando: {cabecalhos}"
    )


def test_runbook_nao_manda_colar_o_link_de_midia_fora_do_download():
    texto = RUNBOOK.read_text(encoding="utf-8")
    passo_download = _secao(texto, 8)

    assert "PESSOAL" in passo_download or "pessoal" in passo_download
    assert "expira" in passo_download
    assert "legenda" in texto and "commit" in texto

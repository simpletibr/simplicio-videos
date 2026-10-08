"""Licença e documentos legais do motor (#70): AGPL-3.0-or-later.

Contrato que a fase 2 precisa cumprir (estes testes leem arquivos do repo; nada de rede nem sockets):

- LICENSE: texto integral da GNU AGPL v3 (cabeçalho nas primeiras linhas, "END OF TERMS AND CONDITIONS").
- pyproject.toml: [project] license = { text = "AGPL-3.0-or-later" }.
- NOTICE: aviso do produto (simplicio-video) com a licença.
- docs/legal/README.md: índice que linka licenca.md, terceiros.md e historico.md.
- docs/legal/licenca.md: por que AGPL e como contribuir (seções "## Por que" e "## Contribuição").
- docs/legal/terceiros.md: fontes OFL, GSAP em templates, link para ../licenses.md.
- docs/legal/historico.md: limpeza da coleta e a regra de não reescrever o histórico.
- docs/licenses.md (gerado pelo scan de #46): linha do produto com AGPL-3.0-or-later.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LICENSE_ID = "AGPL-3.0-or-later"


def _ler(rel: str) -> str:
    """Lê um arquivo do repo. Ausente falha com a razão certa (o arquivo ainda não existe)."""
    path = ROOT / rel
    if not path.is_file():
        pytest.fail(f"{rel} não existe: a fase 2 (#70) cria este arquivo", pytrace=False)
    return path.read_text(encoding="utf-8")


def _linhas(text: str) -> list[str]:
    return [linha.strip() for linha in text.splitlines()]


def _tem_secao(text: str, titulo: str) -> bool:
    return titulo in _linhas(text)


def _linka(text: str, alvo: str) -> bool:
    """True se há um link markdown para `alvo` (com ou sem ./ e com âncora opcional)."""
    padrao = r"\]\(\s*(?:\./)?" + re.escape(alvo) + r"(?:#[^)\s]*)?\s*\)"
    return re.search(padrao, text) is not None


# --------------------------------------------------------------------------- LICENSE
def test_license_tem_cabecalho_da_agpl3():
    text = _ler("LICENSE")
    topo = "\n".join(text.splitlines()[:10])
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in topo, "LICENSE não começa com o cabeçalho da GNU AGPL"
    assert "Version 3, 19 November 2007" in topo, "LICENSE não traz 'Version 3, 19 November 2007' no topo"


def test_license_termina_com_end_of_terms_and_conditions():
    text = _ler("LICENSE")
    assert "END OF TERMS AND CONDITIONS" in text, "LICENSE não contém o texto integral (falta END OF TERMS AND CONDITIONS)"


# --------------------------------------------------------------------------- pyproject.toml
def test_pyproject_declara_agpl_em_project_license():
    data = tomllib.loads(_ler("pyproject.toml"))
    licenca = data.get("project", {}).get("license")
    assert isinstance(licenca, dict), "pyproject.toml: [project] license deve ser uma tabela com o campo text"
    assert LICENSE_ID in licenca.get("text", ""), (
        f"pyproject.toml: project.license.text deveria conter {LICENSE_ID!r}, mas é {licenca.get('text')!r}"
    )


# --------------------------------------------------------------------------- NOTICE
def test_notice_existe_e_nomeia_produto_e_licenca():
    text = _ler("NOTICE")
    assert "simplicio-video" in text, "NOTICE não nomeia o produto simplicio-video"
    assert LICENSE_ID in text, f"NOTICE não cita a licença {LICENSE_ID}"


# --------------------------------------------------------------------------- docs/legal
def test_docs_legal_readme_linka_os_tres_documentos():
    text = _ler("docs/legal/README.md")
    for alvo in ("licenca.md", "terceiros.md", "historico.md"):
        assert _linka(text, alvo), f"docs/legal/README.md não linka {alvo} (esperado um link markdown)"


def test_docs_legal_licenca_explica_agpl_e_contribuicao():
    text = _ler("docs/legal/licenca.md")
    assert LICENSE_ID in text, f"docs/legal/licenca.md não cita {LICENSE_ID}"
    for secao in ("## Por que", "## Contribuição"):
        assert _tem_secao(text, secao), f"docs/legal/licenca.md não tem a seção {secao!r}"


def test_docs_legal_terceiros_cobre_ofl_gsap_e_linka_licenses():
    text = _ler("docs/legal/terceiros.md")
    assert "OFL" in text, "docs/legal/terceiros.md não cita as fontes sob OFL"
    assert "GSAP" in text, "docs/legal/terceiros.md não cita o uso confirmado do GSAP em templates"
    assert _linka(text, "../licenses.md"), "docs/legal/terceiros.md não linka ../licenses.md"


def test_docs_legal_historico_registra_coleta_e_regra_de_nao_reescrever():
    text = _ler("docs/legal/historico.md")
    assert "coleta" in text, "docs/legal/historico.md não registra a coleta"
    assert "não reescrever o histórico sem autorização" in text, (
        "docs/legal/historico.md não traz a regra 'não reescrever o histórico sem autorização'"
    )


# --------------------------------------------------------------------------- docs/licenses.md (#46)
def test_docs_licenses_md_traz_o_produto_como_agpl():
    linhas = _ler("docs/licenses.md").splitlines()
    padrao = re.compile(r"^\|\s*simplicio-video\s*\|[^|]*\|\s*" + re.escape(LICENSE_ID) + r"\s*\|")
    assert any(padrao.match(linha.strip()) for linha in linhas), (
        f"docs/licenses.md: a linha do produto simplicio-video deveria ter a licença {LICENSE_ID} "
        "(regere com o scan de #46 depois de mudar o pyproject)"
    )

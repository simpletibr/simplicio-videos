"""Contrato dos docs do pacote de operação (issue #43): arquivos existem, ADR-0017 tem as seções, exemplos batem com o código.

Confere: os três arquivos (how-to/install.md, host/packaging.md, ADR-0017) existem; o ADR tem Contexto, Decisão e
Consequências; todo `--with` dos blocos de código usa um extra que existe no pyproject.toml; todo subcomando
`simplicio-video X` citado nos docs está registrado no CLI; links relativos dos três arquivos apontam para arquivos
que existem. Só lê arquivos do repo; sem rede.
"""
from __future__ import annotations

import re

import pytest

from _comum import ROOT, exige_registrado
from simplicio_video.cli import main

tomllib = pytest.importorskip("tomllib")

INSTALL_MD = ROOT / "docs" / "how-to" / "install.md"
PACKAGING_MD = ROOT / "docs" / "host" / "packaging.md"
ADR = ROOT / "docs" / "decisoes" / "ADR-0017-instalacao-atualizacao.md"
DOCS = [INSTALL_MD, PACKAGING_MD, ADR]
SECOES_ADR = ("## Contexto", "## Decisão", "## Consequências")
BLOCO = re.compile(r"```(?:bash|sh)\n(.*?)```", re.S)


def _extras_do_pyproject() -> set[str]:
    dados = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))
    return set(dados["project"].get("optional-dependencies", {}))


def _blocos_de_codigo(caminho) -> list[str]:
    return BLOCO.findall(caminho.read_text(encoding="utf8"))


@pytest.mark.parametrize("caminho", DOCS, ids=lambda p: p.name)
def test_arquivo_do_pacote_existe(caminho):
    assert caminho.is_file(), f"{caminho.relative_to(ROOT)} não existe"


def test_adr_0017_tem_contexto_decisao_e_consequencias():
    texto = ADR.read_text(encoding="utf8")
    for secao in SECOES_ADR:
        assert re.search(rf"^{re.escape(secao)}\s*$", texto, re.M), f"ADR-0017 sem a seção {secao!r}"


def test_exemplos_de_with_usam_extras_que_existem():
    existentes = _extras_do_pyproject()
    assert existentes, "pyproject.toml sem optional-dependencies"
    usados = set()
    for bloco in _blocos_de_codigo(INSTALL_MD):
        for lista in re.findall(r"--with[ =]([A-Za-z0-9_,.-]+)", bloco):
            usados.update(lista.split(","))
    assert usados, "install.md não tem nenhum exemplo com --with"
    inexistentes = usados - existentes
    assert not inexistentes, f"install.md cita extras que não existem no pyproject: {sorted(inexistentes)}"


def test_subcomandos_citados_nos_docs_estao_registrados(capsys):
    citados = set()
    for caminho in (INSTALL_MD, PACKAGING_MD):
        for bloco in _blocos_de_codigo(caminho):
            citados.update(re.findall(r"simplicio-video\s+([a-z]+)", bloco))
    assert citados, "os docs não citam nenhum subcomando"
    for nome in sorted(citados):
        exige_registrado(nome, capsys, main)


@pytest.mark.parametrize("caminho", DOCS, ids=lambda p: p.name)
def test_links_relativos_apontam_para_arquivos_existentes(caminho):
    texto = caminho.read_text(encoding="utf8")
    faltando = []
    for alvo in re.findall(r"\]\(([^)\s]+)\)", texto):
        if alvo.startswith(("http://", "https://", "#", "mailto:")):
            continue
        arquivo = alvo.split("#", 1)[0]
        if not (caminho.parent / arquivo).resolve().exists():
            faltando.append(alvo)
    assert not faltando, f"{caminho.name} tem links quebrados: {faltando}"

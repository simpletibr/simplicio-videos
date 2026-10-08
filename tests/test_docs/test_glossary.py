"""docs/glossary.md exists and defines the minimum terms of the engine and of the factory.

A term counts as defined when it opens a heading or a list item (`## Contrato`, `- **Contrato** — ...`).
"""
from __future__ import annotations

import re

import pytest

from _docs import ROOT

GLOSSARY = ROOT / "docs" / "glossary.md"
TERMS = [
    "contrato",
    "render",
    "marca",
    "motion",
    "template",
    "voz",
    "manifesto",
    "ferramenta",
    "ADR",
    "stage",
    "station",
    "character",
    "plugin",
    "Runtime plugin",
]


def _defines(text, term):
    pattern = re.compile(rf"(?im)^(?:#{{1,6}}\s+|[-*]\s+)\**{re.escape(term)}\**(?=\s|$|[:(—–-])")
    return pattern.search(text) is not None


def test_glossario_existe():
    assert GLOSSARY.exists(), "docs/glossary.md não existe (entra na fase 2)"


@pytest.mark.parametrize("term", TERMS)
def test_termo_minimo_tem_definicao(term):
    assert GLOSSARY.exists(), "docs/glossary.md não existe (entra na fase 2)"
    text = GLOSSARY.read_text(encoding="utf-8")
    assert _defines(text, term), f"termo {term!r} sem definição (título ou item de lista) no glossário"

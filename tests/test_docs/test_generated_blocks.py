"""The host map in README.md and AGENTS.md is generated from the front matter of docs/host/*.md, between
`<!-- BEGIN GENERATED: host -->` and `<!-- END GENERATED -->` markers.

Contract under test: each file has exactly one `host` block. The set of (title, path) links inside the block equals
the set built from the front matter of the pages in docs/host/ (README.md excluded).
"""
from __future__ import annotations

import re

import pytest

from _docs import HOST_DIR, ROOT, doc_pages, front_matter

SECTIONS = {"host": HOST_DIR}
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
END = "<!-- END GENERATED -->"


def _block(text, section):
    begin = f"<!-- BEGIN GENERATED: {section} -->"
    assert text.count(begin) == 1, f"marcador {begin!r} ausente ou repetido"
    assert text.count(END) >= 1, f"marcador {END!r} ausente"
    start = text.index(begin) + len(begin)
    return text[start:text.index(END, start)]


def _expected(directory):
    entries = set()
    for page in doc_pages(directory):
        meta = front_matter(page)
        assert meta and "title" in meta, f"{page.relative_to(ROOT)} sem front matter com title"
        entries.add((meta["title"], page.relative_to(ROOT).as_posix()))
    return entries


def _found(block):
    entries = set()
    for title, target in LINK.findall(block):
        path = target.split("#")[0]
        if path.startswith("docs/host/") and not path.endswith("README.md"):
            entries.add((title, path))
    return entries


def test_host_tem_as_tres_paginas_existentes_no_front_matter():
    assert len(_expected(HOST_DIR)) >= 3, "o mapa de docs/host/ ficaria vazio: o teste não provaria nada"


@pytest.mark.parametrize("doc", ["README.md", "AGENTS.md"])
@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_bloco_gerado_bate_com_o_front_matter(doc, section):
    text = (ROOT / doc).read_text(encoding="utf-8")
    block = _block(text, section)
    expected = _expected(SECTIONS[section])
    found = _found(block)
    assert found == expected, (
        f"{doc} [{section}]: faltando={sorted(expected - found)} sobrando={sorted(found - expected)}"
    )

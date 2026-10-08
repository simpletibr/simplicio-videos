"""Every docs/host/*.md page has front matter with the five keys: title, summary, commands, issue, last_verified.

`commands` may be a YAML list (possibly empty) or a comma-separated string, because the three pages that exist
today (gate, packaging, licenses) already use the string form and belong to other issues (#31, #43, #46).
"""
from __future__ import annotations

import pytest

from _docs import FRONT_MATTER_KEYS, HOST_DIR, doc_pages, front_matter

EXISTING = ["gate.md", "packaging.md", "licenses.md"]


def test_paginas_existentes_estao_cobertas():
    names = {p.name for p in doc_pages(HOST_DIR)}
    assert set(EXISTING) <= names, f"docs/host/ sem {set(EXISTING) - names}"


@pytest.mark.parametrize("page", doc_pages(HOST_DIR), ids=lambda p: p.name)
def test_front_matter_tem_as_cinco_chaves(page):
    meta = front_matter(page)
    assert meta is not None, f"{page.name} sem front matter"
    missing = [key for key in FRONT_MATTER_KEYS if key not in meta]
    assert not missing, f"{page.name} sem as chaves {missing}"
    assert isinstance(meta["commands"], (list, str)), f"{page.name}: commands precisa ser lista ou texto"

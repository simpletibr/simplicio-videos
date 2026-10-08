"""scripts/check_docs.py --root DIR (offline): links, anchors, front matter, orphans, TODO and mermaid fences.

Contract under test: the checker scans every .md under DIR, prints each problem with its file path, and exits 1
when there is any problem and 0 when there is none. Pages under docs/host/ and docs/plugins/ (except README.md)
need the five front matter keys. Every problem is planted in a copy of a valid mini tree under tmp_path. The valid
tree must pass (positive control), so the negative cases fail because of the planted problem and not because the
checker rejects everything.
"""
from __future__ import annotations

import pytest

from _docs import run_script

FM = (
    "---\n"
    "title: Gate\n"
    "summary: Resumo curto da página.\n"
    "commands: []\n"
    "issue: 31\n"
    "last_verified: 2026-10-08\n"
    "---\n\n"
)

VALID = {
    "README.md": "# Projeto\n\nVeja [os docs](docs/README.md).\n",
    "docs/README.md": "# Docs\n\n- [Guia](guia.md)\n- [Host](host/gate.md)\n",
    "docs/guia.md": (
        "# Guia\n\n## Como rodar\n\n"
        "Volte ao [topo](#guia). Site externo, sem buscar: [exemplo](https://example.com/nao-buscar).\n\n"
        "```mermaid\ngraph TD\n  A-->B\n```\n"
    ),
    "docs/host/gate.md": FM + "# Gate\n\nVeja o [guia](../guia.md#como-rodar).\n",
}


def _tree(tmp_path, overrides=None):
    files = {**VALID, **(overrides or {})}
    root = tmp_path / "vault"
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _check(root):
    return run_script("check_docs.py", "--root", str(root))


def _assert_pega(result, *names):
    out = result.stdout + result.stderr
    assert result.returncode == 1, f"esperava saída 1 (problema achado), veio {result.returncode}:\n{out}"
    for name in names:
        assert name in out, f"a saída não nomeia {name!r}:\n{out}"


def test_arvore_valida_passa(tmp_path):
    result = _check(_tree(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr


def test_link_relativo_quebrado_e_pego(tmp_path):
    root = _tree(tmp_path, {"docs/guia.md": VALID["docs/guia.md"] + "\nVeja [sumido](nao-existe.md).\n"})
    _assert_pega(_check(root), "guia.md", "nao-existe.md")


def test_ancora_inexistente_e_pega(tmp_path):
    root = _tree(tmp_path, {"docs/README.md": VALID["docs/README.md"] + "\nVeja [seção](guia.md#nao-existe).\n"})
    _assert_pega(_check(root), "README.md", "nao-existe")


def test_pagina_orfa_e_pega(tmp_path):
    root = _tree(tmp_path, {"docs/perdido.md": "# Perdido\n\nNenhum índice aponta para cá.\n"})
    _assert_pega(_check(root), "perdido.md")


@pytest.mark.parametrize(
    "overrides, page, key",
    [
        ({"docs/host/gate.md": "# Gate\n\nSem front matter nenhum.\n"}, "gate.md", None),
        (
            {"docs/host/gate.md": FM.replace("last_verified: 2026-10-08\n", "") + "# Gate\n\nSem last_verified.\n"},
            "gate.md",
            "last_verified",
        ),
        (
            {
                "docs/README.md": VALID["docs/README.md"] + "- [Plugin](plugins/exemplo.md)\n",
                "docs/plugins/exemplo.md": FM.replace("issue: 31\n", "") + "# Exemplo\n",
            },
            "exemplo.md",
            "issue",
        ),
    ],
    ids=["sem-front-matter-host", "host-sem-last_verified", "plugin-sem-issue"],
)
def test_front_matter_ausente_e_pego(tmp_path, overrides, page, key):
    result = _check(_tree(tmp_path, overrides))
    names = (page,) if key is None else (page, key)
    _assert_pega(result, *names)


def test_todo_e_pego(tmp_path):
    root = _tree(tmp_path, {"docs/guia.md": VALID["docs/guia.md"] + "\nTODO: escrever o passo 2.\n"})
    _assert_pega(_check(root), "guia.md", "TODO")


def test_fence_mermaid_sem_fechamento_e_pega(tmp_path):
    unclosed = "# Guia\n\n## Como rodar\n\n```mermaid\ngraph TD\n  A-->B\n"
    root = _tree(tmp_path, {"docs/guia.md": unclosed})
    _assert_pega(_check(root), "guia.md", "mermaid")

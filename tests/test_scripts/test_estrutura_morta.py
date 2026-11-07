"""The dead structure of the repository is gone, and stays gone (U15).

The `web/` workspace ("chega com a #34") was announced in the Makefile, in both `dev_install` scripts, in `licenses.py` and in three
host docs, and never existed. A promise in the gate that nothing keeps is read as a feature: `make check-web` printed "nada para
checar ainda" and exited 0, `dev_install` printed "web/ chega com a #34" on every run.
"""
from __future__ import annotations

import re

import pytest
from helpers import ROOT

ARQUIVOS_DO_GATE = ["Makefile", "scripts/dev_install.sh", "scripts/dev_install.ps1", "scripts/licenses.py", "scripts/check.sh",
                    "docs/host/gate.md", "docs/host/licenses.md", "docs/host/packaging.md"]
# What announced the workspace: its folder, its issue, its Make target and variable.
RASTROS = re.compile(r"\bweb[\\/]|#34\b|check-web|CHECKS_WEB|npm --prefix web")


@pytest.mark.parametrize("rel", ARQUIVOS_DO_GATE)
def test_nothing_in_the_gate_or_its_docs_announces_the_web_workspace(rel):
    achados = [f"{n}: {ln.strip()[:110]}" for n, ln in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1) if RASTROS.search(ln)]
    assert not achados, f"{rel} still talks about a web/ workspace that never existed:\n  " + "\n  ".join(achados)


def test_dev_install_has_no_step_for_web_in_the_plan_or_in_the_run():
    sh = (ROOT / "scripts" / "dev_install.sh").read_text(encoding="utf-8")
    ps = (ROOT / "scripts" / "dev_install.ps1").read_text(encoding="utf-8")
    for texto in (sh, ps):
        assert not re.search(r"\bweb\b", texto, re.IGNORECASE), "no web step: it never had a folder to build"
    # the plan is numbered without a hole: the web line was step 6 and doctor was 7
    assert "  6. rodar " in sh and "  7. imprimir os próximos passos" in sh
    assert "  6. rodar " in ps and "  7. imprimir os próximos passos" in ps


def test_licenses_does_not_print_a_line_about_a_web_scan_that_has_nothing_to_scan():
    texto = (ROOT / "scripts" / "licenses.py").read_text(encoding="utf-8")
    assert "workspace web" not in texto and "nada a escanear" not in texto


def test_the_docs_that_cite_the_gate_cite_the_skills_mirror_script():
    """`make regen` also rewrites the `skills/` mirror and the `.gitignore` block (PR #216): both docs say who does it."""
    for rel in ("CONTRIBUTING.md", "docs/host/gate.md"):
        texto = (ROOT / rel).read_text(encoding="utf-8")
        assert "scripts/sync_skills.py" in texto, f"{rel} does not mention scripts/sync_skills.py"
        assert "skills/" in texto


def test_no_doc_or_template_points_to_the_old_place_of_the_ownership_map():
    """The map moved to scripts/ownership.yaml: what still names `docs/factory/ownership.yaml` is a dead link or a wrong path."""
    for rel in ("CONTRIBUTING.md", "docs/host/gate.md", ".github/PULL_REQUEST_TEMPLATE.md", "docs/decisoes/ADR-0005-gate-sem-ci.md",
                "scripts/check_ownership.py"):
        texto = (ROOT / rel).read_text(encoding="utf-8")
        assert "factory/ownership.yaml" not in texto, rel

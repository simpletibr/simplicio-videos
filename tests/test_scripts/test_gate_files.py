"""The gate deliverables exist and have the shape the issue asks for (Makefile, hooks, templates, docs)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys

import pytest
from gitfixture import ROOT, Repo, clean_env, tool

try:  # py>=3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py3.10 (pytest pulls tomli in)
    import tomli as tomllib

MARKERS = {"unit", "contract", "e2e", "integration", "render", "ui", "slow"}


def pyproject():
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def makefile():
    path = ROOT / "Makefile"
    assert path.exists(), "Makefile is missing"
    return path


def make(*args, cwd=ROOT, env=None):
    assert shutil.which("make"), "make is required for the gate"
    return subprocess.run(["make", "--no-print-directory", *args], cwd=cwd, capture_output=True, text=True, env=env or clean_env())


# ------------------------------------------------------------------ Makefile

def test_makefile_declares_the_extension_points():
    text = makefile().read_text()
    for var in ("CHECKS", "REGEN", "CHECKS_WEB"):
        assert re.search(rf"^{var}\s*[:?]?=", text, re.M), f"{var} is not defined"
    assert re.search(r"^-include\s+mk/\*\.mk\s*$", text, re.M)


@pytest.mark.parametrize("target", ["setup", "check", "check-full", "check-web", "hooks", "regen"])
def test_makefile_targets_exist(target):
    r = make("-n", target)
    assert r.returncode == 0, r.stderr


def test_check_runs_the_local_gate_and_check_full_adds_the_slow_tests():
    check = make("-n", "check").stdout
    assert "scripts/check.sh" in check
    full = make("-n", "check-full").stdout
    assert "scripts/check.sh" in full  # check-full = check + the rest
    assert "pytest" in full and "not render" not in full.split("scripts/check.sh", 1)[1]


def test_check_web_succeeds_without_a_web_workspace_and_says_why():
    r = make("check-web")
    assert r.returncode == 0, r.stderr
    assert "#34" in r.stdout


def test_regen_with_nothing_to_regenerate_succeeds():
    r = make("regen")
    assert r.returncode == 0, r.stderr


def test_tracks_extend_the_gate_through_mk_files(tmp_path):
    shutil.copy(makefile(), tmp_path / "Makefile")
    (tmp_path / "mk").mkdir()
    (tmp_path / "mk" / "demo.mk").write_text(
        "CHECKS += demo-check\nREGEN += demo-regen\nCHECKS_WEB += demo-web\n"
        "demo-check: ; @echo DEMO_CHECK_RAN\ndemo-regen: ; @echo DEMO_REGEN_RAN\ndemo-web: ; @echo DEMO_WEB_RAN\n"
    )
    assert "DEMO_CHECK_RAN" in make("-n", "check", cwd=tmp_path).stdout
    assert "DEMO_REGEN_RAN" in make("-n", "regen", cwd=tmp_path).stdout
    web = make("check-web", cwd=tmp_path)
    assert web.returncode == 0 and "DEMO_WEB_RAN" in web.stdout and "#34" not in web.stdout


def test_make_hooks_points_git_at_the_versioned_hooks(tmp_path):
    repo = Repo(tmp_path / "r")
    shutil.copy(makefile(), repo.path / "Makefile")
    r = make("hooks", cwd=repo.path)
    assert r.returncode == 0, r.stderr
    assert repo.git("config", "core.hooksPath") == ".githooks"


# ------------------------------------------------------------------ hooks and shell scripts

def test_pre_push_hook_runs_the_gate():
    hook = ROOT / ".githooks" / "pre-push"
    assert hook.exists(), ".githooks/pre-push is missing"
    assert hook.stat().st_mode & 0o111, "pre-push must be executable"
    assert "make check" in hook.read_text()


@pytest.mark.parametrize("rel", ["scripts/check.sh", "scripts/land.sh", ".githooks/pre-push"])
def test_shell_scripts_parse_and_are_executable(rel):
    p = ROOT / rel
    assert p.exists(), f"{rel} is missing"
    assert p.stat().st_mode & 0o111, f"{rel} must be executable"
    r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("rel", ["scripts/check.sh", "scripts/land.sh", ".githooks/pre-push"])
def test_shell_scripts_are_shellcheck_clean(rel):
    sc = tool("shellcheck")
    if not sc:
        pytest.skip("shellcheck not installed (pip install shellcheck-py)")
    assert (ROOT / rel).exists(), f"{rel} is missing"
    r = subprocess.run([sc, "--shell=bash", str(ROOT / rel)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("script", ["check_ownership.py", "check_tdd.py"])
def test_python_gate_scripts_have_help_with_examples(script):
    p = ROOT / "scripts" / script
    assert p.exists(), f"scripts/{script} is missing"
    r = subprocess.run([sys.executable, str(p), "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "--base" in r.stdout and "Exemplos" in r.stdout


# ------------------------------------------------------------------ pyproject

def test_markers_are_registered():
    names = {m.split(":")[0].split("(")[0].strip() for m in pyproject()["tool"]["pytest"]["ini_options"]["markers"]}
    assert MARKERS <= names


def test_unit_tests_run_with_the_socket_guard_by_default():
    assert "--disable-socket" in pyproject()["tool"]["pytest"]["ini_options"]["addopts"]


def test_test_extra_carries_the_gate_tools():
    names = {re.split(r"[<>=!~\[ ]", dep, maxsplit=1)[0].lower() for dep in pyproject()["project"]["optional-dependencies"]["test"]}
    assert {"pytest", "pytest-socket", "ruff"} <= names


def test_clone_and_montage_are_no_longer_console_scripts():
    scripts = pyproject()["project"]["scripts"]
    assert set(scripts) == {"simplicio-video", "simplicio-video-mcp"}


def test_ruff_is_scoped_to_the_engine_and_scripts():
    ruff = pyproject()["tool"]["ruff"]
    assert set(ruff["include"]) == {"src/simplicio_video/**/*.py", "scripts/**/*.py"}


def test_ruff_is_clean_on_the_gated_paths():
    exe = tool("ruff")
    assert exe, "ruff is part of the test extra"
    r = subprocess.run([exe, "check", "--no-cache", "."], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]


# ------------------------------------------------------------------ templates and docs

def test_pr_template_has_the_required_sections():
    text = (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
    for needle in ("Closes #", "check_ownership", "commit vermelho", "critério de aceitação", "Docs e help", "tokens", "Risco", "Revisão"):
        assert needle in text, needle


def test_issue_template_follows_the_factory_issue_format():
    folder = ROOT / ".github" / "ISSUE_TEMPLATE"
    templates = [p for p in folder.glob("*.md")]
    assert templates, ".github/ISSUE_TEMPLATE/*.md is missing"
    text = "\n".join(p.read_text() for p in templates)
    for heading in ("## Goal", "## Scope", "## Owns (only these paths)", "## Interfaces", "## Tests first", "## Acceptance criteria",
                    "## Docs and help", "## Risks and open questions", "## Definition of done"):
        assert heading in text, heading


def test_there_are_no_workflow_files():
    gh = ROOT / ".github"
    assert gh.is_dir()
    assert not (gh / "workflows").exists(), "GitHub Actions are not allowed (org policy)"
    assert not [p for p in gh.rglob("*") if p.suffix in {".yml", ".yaml"} and "ISSUE_TEMPLATE" not in p.parts]


def test_contributing_points_at_the_gate():
    text = (ROOT / "CONTRIBUTING.md").read_text()
    for needle in ("make setup", "make check", "scripts/land.sh", "docs/host/gate.md"):
        assert needle in text, needle


def test_gate_doc_has_the_promised_sections():
    text = (ROOT / "docs" / "host" / "gate.md").read_text()
    for heading in ("Como rodar", "O que é verificado", "Regra de TDD", "Pouso (land.sh)", "Solução de problemas"):
        assert re.search(rf"^#+ .*{re.escape(heading)}", text, re.M), heading


def test_adr_0005_records_the_gate_without_ci_and_the_subprocess_offline_rule():
    adrs = list((ROOT / "docs" / "decisoes").glob("ADR-0005-*.md"))
    assert len(adrs) == 1, "exactly one ADR-0005-*.md"
    text = adrs[0].read_text()
    for needle in ("GitHub Actions", "SIMPLICIO_OFFLINE", "subprocess", "pytest-socket"):
        assert needle in text, needle

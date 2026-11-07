"""scripts/ownership.yaml, the real map of who owns what (U15).

It used to live in `docs/factory/` (the spec of a factory that was never built) and 219 of its 432 `owns` patterns matched no file
in the repository, while `generated` listed files that are not generated (`plugin.json`, `web/**`, `schemas/factory/**`). Now:

* the map sits next to the script that reads it;
* every `owns` pattern matches a file; the ones that do not (work not started, files that were never made) are in the explicit
  `backlog` block, per issue, and are not enforced; an issue that starts moves them to `owns` in its own entry;
* `generated` names only whole files that `make regen` writes.
"""
from __future__ import annotations

import importlib.util
import subprocess

import pytest
from gitfixture import OWNERSHIP_REL, ROOT, SCRIPTS, Repo

OWNERSHIP = ROOT / OWNERSHIP_REL
# whole files, rewritten by `make regen`: gen_reference.py (docs/reference), licenses.py --write (docs/licenses.md) and
# sync_skills.py (the skills/ mirror). The README/AGENTS blocks, plugin.json and the .gitignore block are generated INSIDE a
# hand-edited file, so they are not here: whoever owns the file owns the rest of it.
GENERATED = {"docs/reference/**", "docs/licenses.md", "skills/**"}


def _checker():
    spec = importlib.util.spec_from_file_location("check_ownership", SCRIPTS / "check_ownership.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


co = _checker()


@pytest.fixture(scope="module")
def arquivos() -> list[str]:
    """The files of the repository: tracked, plus new ones that git does not ignore (what a branch can touch)."""
    r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        pytest.skip(f"not a git checkout: {r.stderr.strip()}")
    return [p for p in r.stdout.split("\0") if p]


@pytest.fixture(scope="module")
def mapa() -> dict:
    assert OWNERSHIP.is_file(), f"{OWNERSHIP_REL} does not exist"
    return co.load_ownership(OWNERSHIP.read_text(encoding="utf-8"), OWNERSHIP_REL)


def _casa(padrao: str, arquivos: list[str]) -> bool:
    rx, _secao = co.split_owns(padrao)
    return any(rx.match(a) for a in arquivos)


def test_the_map_lives_next_to_its_script_and_not_in_the_spec_of_the_factory(mapa):
    assert OWNERSHIP_REL == "scripts/ownership.yaml" == co.OWNERSHIP_REL
    assert not (ROOT / "docs" / "factory" / "ownership.yaml").exists()


def test_every_owns_pattern_matches_a_file_or_is_in_the_backlog(mapa, arquivos):
    mortos = [f"#{n}: {p}" for n, e in mapa["issues"].items() for p in e.get("owns") or [] if not _casa(p, arquivos)]
    assert not mortos, ("a pattern of `owns` that matches no file is a promise nobody can check: move it to the `backlog` block of "
                        "its issue, or fix the pattern:\n  " + "\n  ".join(mortos))


def test_the_backlog_is_per_issue_and_not_enforced(mapa):
    backlog = mapa.get("backlog")
    assert isinstance(backlog, dict) and backlog, "the patterns that were pruned from `owns` went somewhere: the `backlog` block"
    for n, padroes in backlog.items():
        assert n in mapa["issues"], f"backlog of #{n}, an issue that has no entry"
        assert isinstance(padroes, list) and padroes and all(isinstance(p, str) for p in padroes), n
        assert len(set(padroes)) == len(padroes), f"#{n}: a pattern twice in the backlog"
        owns = set(mapa["issues"][n].get("owns") or [])
        assert not owns & set(padroes), f"#{n}: {sorted(owns & set(padroes))} is in `owns` and in `backlog`"


def test_generated_names_only_whole_files_that_make_regen_writes(mapa, arquivos):
    assert set(mapa["generated"]) == GENERATED
    for padrao in GENERATED:
        rx = co.glob_to_regex(padrao)
        assert any(rx.match(a) for a in arquivos), f"`generated` lists {padrao}, which matches no file"
    # each one has a generator that writes it
    assert "docs/reference" in (ROOT / "mk" / "docs.mk").read_text(encoding="utf-8")
    assert "sync_skills.py" in (ROOT / "mk" / "docs.mk").read_text(encoding="utf-8")
    assert "docs/licenses.md" in (ROOT / "scripts" / "licenses.py").read_text(encoding="utf-8")


def test_the_map_has_no_trace_of_the_web_workspace_that_never_existed(mapa):
    texto = OWNERSHIP.read_text(encoding="utf-8")
    assert "web/" not in texto and "schemas/factory" not in texto


def test_the_script_works_with_the_real_map_for_every_issue(mapa, tmp_path, monkeypatch, capsys):
    """`check_ownership.py <n>` on a clean branch: 0 for an issue with `owns`, 2 and a reason for the others (backlog, nothing live)."""
    repo = Repo(tmp_path / "repo")
    repo.seed_main(OWNERSHIP.read_text(encoding="utf-8"))
    repo.branch("feat/31-gate")
    monkeypatch.chdir(repo.path)
    resultado = {}
    for n, e in mapa["issues"].items():
        capsys.readouterr()
        resultado[n] = (co.main([str(n), "--base", "main"]), capsys.readouterr().err)
    for n, e in mapa["issues"].items():
        rc, err = resultado[n]
        if e.get("status") == "backlog":
            assert rc == 2 and "backlog" in err, (n, rc, err)
        elif e.get("owns"):
            assert rc == 0, (n, rc, err)
        else:  # every pattern of the issue was pruned: it says where they are
            assert rc == 2 and "backlog" in err and "owns" in err, (n, rc, err)

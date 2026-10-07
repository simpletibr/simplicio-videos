"""scripts/check_ownership.py <issue> [--base REF]: a branch may only touch the paths its issue owns."""
from __future__ import annotations

import pytest
from gitfixture import OWNERSHIP, Repo, run_script


@pytest.fixture
def repo(tmp_path):
    r = Repo(tmp_path / "repo")
    r.seed_main()
    r.branch("feat/31-gate")
    return r


def check(repo, issue="31", *extra):
    return run_script("check_ownership.py", issue, "--base", "main", *extra, cwd=repo.path)


def test_owned_files_pass(repo):
    repo.commit_files("feat: gate", {"Makefile": "all:\n", "scripts/check_tdd.py": "#\n", "docs/decisoes/ADR-0005-gate.md": "# adr\n"})
    r = check(repo)
    assert r.returncode == 0, r.stdout + r.stderr


def test_file_outside_the_owned_set_fails_and_is_named(repo):
    repo.commit_files("feat: gate", {"Makefile": "all:\n", "src/simplicio_video/cli.py": "# not mine\n"})
    r = check(repo)
    assert r.returncode == 1
    out = r.stdout + r.stderr
    assert "src/simplicio_video/cli.py" in out
    assert "FALHA" in out and "Makefile" not in out.split("FALHA", 1)[1]  # only the offender is listed


def test_double_star_matches_any_depth_and_single_star_does_not_cross_directories(repo):
    repo.commit_files("feat: hooks", {".githooks/pre-push": "#!/bin/sh\n", ".githooks/deep/er/hook": "#!/bin/sh\n"})
    assert check(repo).returncode == 0
    repo.commit_files("feat: nested", {"scripts/sub/check_x.py": "#\n"})  # scripts/check_*.py is one level only
    r = check(repo)
    assert r.returncode == 1 and "scripts/sub/check_x.py" in r.stdout + r.stderr


def test_generated_files_are_allowed_for_any_issue(repo):
    repo.commit_files("chore: regen", {"plugin.json": "{}\n", "schemas/factory/x.json": "{}\n"})
    assert check(repo).returncode == 0
    assert check(repo, "32").returncode == 0  # generated is global, not per issue


def test_generated_glob_does_not_cover_other_directories(repo):
    repo.commit_files("chore: regen", {"schemas/other/x.json": "{}\n"})
    assert check(repo).returncode == 1


def test_shared_file_with_a_section_is_allowed_and_the_section_is_reported(repo):
    repo.commit_files("chore: pytest cfg", {"pyproject.toml": "[tool.pytest]\n"})
    r = check(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pyproject.toml" in r.stdout and "tool.pytest" in r.stdout  # the reviewer verifies the section


def test_shared_file_is_not_allowed_for_an_issue_that_does_not_list_it(repo):
    repo.commit_files("chore: pytest cfg", {"pyproject.toml": "[tool.pytest]\n"})
    assert check(repo, "32").returncode == 1


def test_backlog_issue_cannot_be_started(repo):
    repo.commit_files("feat: x", {"Makefile": "all:\n"})
    r = check(repo, "50")
    assert r.returncode == 2
    assert "backlog" in r.stdout + r.stderr


def test_unknown_issue_is_a_usage_error(repo):
    r = check(repo, "999")
    assert r.returncode == 2
    assert "999" in r.stdout + r.stderr


def test_unknown_base_is_a_usage_error(repo):
    r = run_script("check_ownership.py", "31", "--base", "origin/nope", cwd=repo.path)
    assert r.returncode == 2
    assert "origin/nope" in r.stdout + r.stderr


def test_default_base_is_origin_main(repo):
    r = run_script("check_ownership.py", "31", cwd=repo.path)  # there is no origin here
    assert r.returncode == 2 and "origin/main" in r.stdout + r.stderr


def test_uncommitted_and_untracked_changes_count_too(repo):
    repo.write("Makefile", "dirty\n")
    repo.git("add", "Makefile")
    repo.write("stray.txt", "untracked\n")
    r = check(repo)
    assert r.returncode == 1 and "stray.txt" in r.stdout + r.stderr


def test_renames_check_both_sides(repo):
    repo.git("checkout", "-q", "main")
    repo.commit_files("chore: base file", {"src/old.py": "x = 1\n"})
    repo.git("checkout", "-q", "feat/31-gate")
    repo.git("rebase", "-q", "main")
    repo.git("mv", "src/old.py", "Makefile.moved")
    repo.git("commit", "-q", "-m", "refactor: move")
    r = check(repo)
    assert r.returncode == 1 and "src/old.py" in r.stdout + r.stderr


def test_empty_branch_passes(repo):
    r = check(repo)
    assert r.returncode == 0


def test_ownership_file_edit_is_allowed_only_for_the_issues_own_entry(repo):
    other = OWNERSHIP.replace('"src/simplicio_video/registry.py"', '"src/simplicio_video/registry.py"\n      - "src/simplicio_video/extra.py"')
    repo.commit_files("docs: touch 32", {"docs/factory/ownership.yaml": other})
    r = check(repo)
    assert r.returncode == 1 and "ownership.yaml" in r.stdout + r.stderr


def test_ownership_file_edit_of_the_issues_own_entry_is_allowed(repo):
    mine = OWNERSHIP.replace('"Makefile"', '"Makefile"\n      - "mk/gate.mk"')
    repo.commit_files("docs: own entry", {"docs/factory/ownership.yaml": mine})
    r = check(repo)
    assert r.returncode == 0, r.stdout + r.stderr

"""scripts/check_tdd.py [--base REF]: tests come first.

Rules under test: the first commit of the branch touches only tests, fixtures and docs; every change
under src/ comes with a change under tests/; the `tdd-exempt` label waives both.
"""
from __future__ import annotations

import pytest
from gitfixture import Repo, clean_env, run_script


@pytest.fixture
def repo(tmp_path):
    r = Repo(tmp_path / "repo")
    r.seed_main()
    r.branch("feat/31-gate")
    return r


def check(repo, *extra, env=None):
    return run_script("check_tdd.py", "--base", "main", *extra, cwd=repo.path, env=env)


def test_empty_branch_passes(repo):
    assert check(repo).returncode == 0


def test_tests_first_then_src_passes(repo):
    repo.commit_files("test: red", {"tests/test_mod.py": "def test_x(): assert False\n"})
    repo.commit_files("feat: green", {"src/simplicio_video/mod.py": "X = 1\n", "tests/test_mod.py": "def test_x(): assert True\n"})
    r = check(repo)
    assert r.returncode == 0, r.stdout + r.stderr


def test_first_commit_with_docs_and_fixtures_passes(repo):
    repo.commit_files("test: red", {"tests/fixtures/mini/a.yaml": "a: 1\n", "docs/notes.md": "# n\n", "tests/test_a.py": "def test_a(): pass\n"})
    assert check(repo).returncode == 0


def test_src_in_the_first_commit_fails(repo):
    repo.commit_files("feat: impl first", {"src/simplicio_video/mod.py": "X = 1\n", "tests/test_mod.py": "def test_x(): pass\n"})
    r = check(repo)
    assert r.returncode == 1
    assert "src/simplicio_video/mod.py" in r.stdout + r.stderr


def test_non_test_file_in_the_first_commit_fails(repo):
    repo.commit_files("chore: gate", {"Makefile": "all:\n", "tests/test_a.py": "def test_a(): pass\n"})
    r = check(repo)
    assert r.returncode == 1 and "Makefile" in r.stdout + r.stderr


def test_src_without_any_test_change_fails(repo):
    repo.commit_files("docs: first", {"docs/a.md": "# a\n"})
    repo.commit_files("feat: impl", {"src/simplicio_video/mod.py": "X = 1\n"})
    r = check(repo)
    assert r.returncode == 1
    assert "tests/" in r.stdout + r.stderr


def test_docs_only_branch_passes(repo):
    repo.commit_files("docs: only", {"docs/a.md": "# a\n"})
    assert check(repo).returncode == 0


def test_exempt_label_by_argument(repo):
    repo.commit_files("feat: impl first", {"src/simplicio_video/mod.py": "X = 1\n"})
    r = check(repo, "--labels", "size:M,tdd-exempt")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tdd-exempt" in r.stdout


def test_exempt_label_by_environment(repo):
    repo.commit_files("feat: impl first", {"src/simplicio_video/mod.py": "X = 1\n"})
    r = check(repo, env=clean_env(PR_LABELS="mvp tdd-exempt kind:host"))
    assert r.returncode == 0, r.stdout + r.stderr


def test_other_labels_do_not_exempt(repo):
    repo.commit_files("feat: impl first", {"src/simplicio_video/mod.py": "X = 1\n"})
    assert check(repo, "--labels", "reviewed,size:M").returncode == 1


def test_unknown_base_is_a_usage_error(repo):
    r = run_script("check_tdd.py", "--base", "origin/nope", cwd=repo.path)
    assert r.returncode == 2 and "origin/nope" in r.stdout + r.stderr


def test_default_base_is_origin_main(repo):
    r = run_script("check_tdd.py", cwd=repo.path)
    assert r.returncode == 2 and "origin/main" in r.stdout + r.stderr


def test_only_the_oldest_commit_of_the_branch_is_the_first(repo):
    repo.commit_files("test: red", {"tests/test_a.py": "def test_a(): pass\n"})
    repo.commit_files("chore: later non-test commit", {"Makefile": "all:\n"})  # allowed: not the first commit
    assert check(repo).returncode == 0

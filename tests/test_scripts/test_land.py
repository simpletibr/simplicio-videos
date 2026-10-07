"""scripts/land.sh <pr>: serialized landing without CI. Never talks to GitHub here: `gh` is a fake on PATH.

Contract with `gh` (what land.sh may call):
  gh pr view <pr> --json <one field> --jq <expr>   with field in state | labels | body | headRefName
  gh pr checkout <pr>
  gh pr merge <pr> --squash --delete-branch [...]
The fake answers the `view` calls from files in $FAKE_GH_DIR (already filtered, one value per line) and
appends every call to $FAKE_GH_LOG, so the tests can prove that read-only runs never mutate.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from gitfixture import OWNERSHIP, ROOT, Repo, clean_env

LAND = ROOT / "scripts" / "land.sh"

FAKE_GH = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_GH_LOG"
if [ "$1 $2" = "pr view" ]; then
  field=""
  prev=""
  for a in "$@"; do
    if [ "$prev" = "--json" ]; then field="$a"; fi
    prev="$a"
  done
  cat "$FAKE_GH_DIR/$field" 2>/dev/null
elif [ "$1 $2" = "pr checkout" ]; then
  if [ -f "$FAKE_GH_DIR/checkout_branch" ]; then git checkout -q "$(cat "$FAKE_GH_DIR/checkout_branch")"; fi
fi
exit 0
"""


class Sandbox:
    def __init__(self, tmp_path: Path, labels="reviewed\nsize:M\n", state="OPEN\n", body="Closes #31\n", head="feat/31-gate\n"):
        self.dir = tmp_path / "gh"
        self.dir.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.log = tmp_path / "gh.log"
        self.log.write_text("")
        self.lock = tmp_path / "lock"
        self.repo = Repo(tmp_path / "cwd-repo")  # land.sh must never touch the real repo in these tests
        self.repo.seed_main()
        for name, value in (("labels", labels), ("state", state), ("body", body), ("headRefName", head)):
            (self.dir / name).write_text(value)

    def env(self, **extra):
        return clean_env(
            PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            FAKE_GH_DIR=str(self.dir),
            FAKE_GH_LOG=str(self.log),
            LAND_LOCK_DIR=str(self.lock),
            PYTHON=sys.executable,
            **extra,
        )

    def calls(self):
        return self.log.read_text().splitlines()

    def mutating(self):
        return [c for c in self.calls() if c.startswith(("pr checkout", "pr merge"))]


def land(sb, *args, cwd=None):
    assert LAND.exists(), "scripts/land.sh does not exist yet (red-first: the gate is not implemented)"
    return subprocess.run(["bash", str(LAND), *args], cwd=cwd or sb.repo.path, capture_output=True, text=True, env=sb.env(), timeout=120)


@pytest.fixture
def sb(tmp_path):
    return Sandbox(tmp_path)


# ------------------------------------------------------------------ usage and dry-run

def test_help_documents_the_flags_with_examples(sb):
    r = land(sb, "--help")
    assert r.returncode == 0, r.stderr
    for needle in ("--dry-run", "Exemplos", "land.sh 123", "reviewed"):
        assert needle in r.stdout, needle


def test_missing_or_bad_pr_number_is_a_usage_error(sb):
    assert land(sb).returncode == 2
    assert land(sb, "abc").returncode == 2
    assert sb.calls() == []


def test_dry_run_prints_the_plan_in_order_and_mutates_nothing(sb):
    r = land(sb, "7", "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    plan = [
        "gh pr checkout 7",
        "git rebase origin/main",
        "make check",
        "check_ownership.py 31",
        "check_tdd.py",
        "gh pr merge 7 --squash --delete-branch",
    ]
    positions = [r.stdout.find(step) for step in plan]
    assert all(p >= 0 for p in positions), (plan, r.stdout)
    assert positions == sorted(positions), r.stdout
    assert sb.mutating() == []
    assert not sb.lock.exists()


def test_dry_run_still_requires_the_reviewed_label(tmp_path):
    sb = Sandbox(tmp_path, labels="size:M\n")
    r = land(sb, "7", "--dry-run")
    assert r.returncode == 1
    assert "reviewed" in r.stdout + r.stderr
    assert sb.mutating() == []


def test_refuses_a_pr_that_is_not_open(tmp_path):
    sb = Sandbox(tmp_path, state="MERGED\n")
    r = land(sb, "7", "--dry-run")
    assert r.returncode == 1 and "MERGED" in r.stdout + r.stderr


def test_issue_comes_from_the_flag_or_from_closes_in_the_body(tmp_path):
    sb = Sandbox(tmp_path, body="no keyword here\n")
    assert land(sb, "7", "--dry-run").returncode == 1  # cannot tell which issue to check
    r = land(sb, "7", "--dry-run", "--issue", "32")
    assert r.returncode == 0 and "check_ownership.py 32" in r.stdout


# ------------------------------------------------------------------ lock

def test_a_live_lock_refuses_the_second_landing(sb):
    sb.lock.mkdir()
    (sb.lock / "pid").write_text(f"{os.getpid()}\n")  # this pytest process is alive
    for args in (("7", "--dry-run"), ("7",)):
        r = land(sb, *args)
        assert r.returncode == 1, args
        assert "lock" in (r.stdout + r.stderr).lower()
    assert sb.mutating() == []
    assert sb.lock.exists()  # a refused run must not steal the lock


# ------------------------------------------------------------------ real landing against a local origin

LAND_OWNERSHIP = OWNERSHIP.replace('  31:\n    track: gate\n    owns:\n', '  31:\n    track: gate\n    owns:\n      - "src/**"\n      - "tests/**"\n')


@pytest.fixture
def world(tmp_path):
    """origin (bare) + a clone with a `feat/31-gate` branch that is tests-first and inside the owned paths."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    work = Repo(tmp_path / "work")
    work.seed_main(LAND_OWNERSHIP)
    work.commit_files("chore: gate", {"Makefile": "check:\n\t@echo gate-ran\n"})
    work.git("remote", "add", "origin", str(origin))
    work.git("push", "-q", "origin", "main")
    work.branch("feat/31-gate")
    work.commit_files("test: red", {"tests/test_mod.py": "def test_x(): pass\n"})
    work.commit_files("feat: green", {"src/mod.py": "X = 1\n", "tests/test_mod.py": "def test_x(): assert True\n"})
    work.git("push", "-q", "origin", "feat/31-gate")
    work.git("checkout", "-q", "main")
    sandbox = Sandbox(tmp_path)
    (sandbox.dir / "checkout_branch").write_text("feat/31-gate\n")
    return work, sandbox


def test_green_landing_rebases_runs_the_gate_and_squash_merges(world):
    work, sb = world
    work.commit_files("docs: main moved on", {"README.md": "moved\n"})  # origin/main is ahead of the branch
    work.git("push", "-q", "origin", "main")
    work.git("reset", "-q", "--hard", "HEAD~1")  # local main is stale: land.sh must fetch
    r = land(sb, "7", cwd=work.path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gate-ran" in r.stdout  # `make check` ran in the checked-out branch
    assert any(c.startswith("pr merge 7") and "--squash" in c and "--delete-branch" in c for c in sb.calls())
    ahead = subprocess.run(["git", "merge-base", "--is-ancestor", "origin/main", "feat/31-gate"], cwd=work.path)
    assert ahead.returncode == 0, "the branch must be rebased on origin/main before the gate"
    pushed = work.git("ls-remote", "origin", "feat/31-gate").split()[0]
    assert pushed == work.git("rev-parse", "feat/31-gate"), "the tested head is what gets merged"
    assert not sb.lock.exists(), "the lock is released"


def test_red_gate_refuses_to_merge(world):
    work, sb = world
    work.commit_files("chore: red gate", {"Makefile": "check:\n\t@echo red; exit 1\n"})
    work.git("push", "-q", "origin", "main")
    r = land(sb, "7", cwd=work.path)
    assert r.returncode != 0
    assert not [c for c in sb.calls() if c.startswith("pr merge")]
    assert not sb.lock.exists(), "the lock is released even on failure"


def test_ownership_violation_refuses_to_merge(world):
    work, sb = world
    work.git("checkout", "-q", "feat/31-gate")
    work.commit_files("feat: stray", {"Makefile.extra": "oops\n"})
    work.git("push", "-q", "origin", "feat/31-gate")
    work.git("checkout", "-q", "main")
    r = land(sb, "7", cwd=work.path)
    assert r.returncode != 0
    assert "Makefile.extra" in r.stdout + r.stderr
    assert not [c for c in sb.calls() if c.startswith("pr merge")]


def test_tdd_violation_refuses_to_merge_unless_exempt(world):
    work, sb = world
    work.git("checkout", "-q", "-b", "feat/32-impl-first", "main")
    work.commit_files("feat: impl first", {"src/other.py": "Y = 1\n"})
    work.git("push", "-q", "origin", "feat/32-impl-first")
    work.git("checkout", "-q", "main")
    (sb.dir / "checkout_branch").write_text("feat/32-impl-first\n")
    (sb.dir / "headRefName").write_text("feat/32-impl-first\n")
    r = land(sb, "8", "--issue", "31", cwd=work.path)
    assert r.returncode != 0 and "src/other.py" in r.stdout + r.stderr
    assert not [c for c in sb.calls() if c.startswith("pr merge")]
    (sb.dir / "labels").write_text("reviewed\ntdd-exempt\n")
    work.git("checkout", "-q", "main")
    ok = land(sb, "8", "--issue", "31", cwd=work.path)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert any(c.startswith("pr merge 8") for c in sb.calls())


def test_a_stale_lock_from_a_dead_process_is_reclaimed(world):
    work, sb = world
    sb.lock.mkdir()
    gone = subprocess.Popen(["true"])
    gone.wait()
    (sb.lock / "pid").write_text(f"{gone.pid}\n")  # a pid that just exited
    r = land(sb, "7", cwd=work.path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not sb.lock.exists()

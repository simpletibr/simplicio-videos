"""Helpers for the gate script tests: throwaway git repos and the repo's own tool paths."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

OWNERSHIP = """\
schema: simplicio.ownership/v1

generated:
  - "plugin.json"
  - "schemas/factory/*.json"

issues:
  31:
    track: gate
    owns:
      - "Makefile"
      - ".githooks/**"
      - "scripts/check_*.py"
      - "docs/decisoes/ADR-0005-*.md"
      - "pyproject.toml#tool.pytest,tool.ruff"
  32:
    track: host
    owns:
      - "src/simplicio_video/registry.py"
  50: {track: later, status: backlog}
"""


def tool(name: str) -> str | None:
    """A CLI installed next to the running interpreter (venv/bin) or on PATH."""
    beside = Path(sys.executable).parent / name
    if beside.exists():
        return str(beside)
    return shutil.which(name)


def clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PR_", "TDD_", "ISSUE", "BASE"))}
    env.update(extra)
    return env


class Repo:
    """A tiny git repo with a `main` branch; every call is hermetic (no global git config)."""

    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str, check: bool = True) -> str:
        r = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True, env=clean_env(GIT_CONFIG_GLOBAL="/dev/null"))
        if check and r.returncode:
            raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
        return r.stdout.strip()

    def write(self, rel: str, text: str = "x\n") -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit_files(self, message: str, files: dict[str, str]) -> str:
        for rel, text in files.items():
            self.write(rel, text)
        self.git("add", "--", *files)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def seed_main(self, ownership: str = OWNERSHIP) -> str:
        sha = self.commit_files("chore: base", {"docs/factory/ownership.yaml": ownership, "README.md": "base\n"})
        return sha

    def branch(self, name: str) -> None:
        self.git("checkout", "-q", "-b", name)


def run_script(script: str, *args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run one of the repo's scripts/*.py against a throwaway repo (cwd)."""
    path = SCRIPTS / script
    assert path.exists(), f"scripts/{script} does not exist yet (red-first: the gate is not implemented)"
    return subprocess.run([sys.executable, str(path), *args], cwd=cwd, capture_output=True, text=True, env=env or clean_env())

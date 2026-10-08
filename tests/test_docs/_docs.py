"""Helpers for the docs system tests (#44). Fixtures live in tmp_path; nothing here opens a socket."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
HOST_DIR = ROOT / "docs" / "host"
PLUGINS_DIR = ROOT / "docs" / "plugins"
FRONT_MATTER_KEYS = ("title", "summary", "commands", "issue", "last_verified")


def run_script(name: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Runs scripts/<name> with the interpreter that runs the tests (the venv)."""
    script = SCRIPTS / name
    assert script.exists(), f"scripts/{name} ainda não existe (entra na fase 2)"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or ROOT),
        timeout=120,
    )


def front_matter(path: Path) -> dict | None:
    """The YAML block between the first two `---` lines, or None when the page has none."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return None
    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else None


def doc_pages(directory: Path) -> list[Path]:
    """The index README of a folder is not a page: it has no front matter of its own."""
    return sorted(p for p in directory.glob("*.md") if p.name != "README.md")

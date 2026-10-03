"""Clone track: Video cloning pipeline using Hypit AI (https://github.com/hypit-ai/hypit).

Invokes Hypit AI agent capabilities to clone videos into complete workflows.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class CloneError(Exception):
    pass


HYPIT_REPO = "https://github.com/hypit-ai/hypit"


def find_hypit_bin() -> list[str]:
    """Find local hypit executable or fallback to npx hypit."""
    hypit = shutil.which("hypit")
    if hypit:
        return [hypit]
    npx = shutil.which("npx")
    if npx:
        return [npx, "hypit"]
    raise CloneError("Nem `hypit` nem `npx` foram encontrados no PATH. Instale o Hypit AI (https://github.com/hypit-ai/hypit).")


def run_hypit(args: list[str], cwd: Path | None = None) -> int:
    """Execute hypit CLI with passed arguments."""
    cmd = find_hypit_bin() + args
    return subprocess.call(cmd, cwd=cwd)

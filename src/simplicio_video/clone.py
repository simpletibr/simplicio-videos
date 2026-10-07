"""Clone track: Video cloning pipeline using Hypit AI (https://github.com/hypit-ai/hypit).

Invokes Hypit AI agent capabilities to clone videos into complete workflows.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import tools


class CloneError(Exception):
    pass


HYPIT_REPO = "https://github.com/hypit-ai/hypit"


def find_hypit_bin() -> list[str]:
    """A local `hypit` binary, else npx at the pinned version (tools.TOOLS['hypit'])."""
    try:
        return tools.npm_command("hypit")
    except tools.ToolError:
        raise CloneError("Nem `hypit` nem `npx` foram encontrados no PATH. Instale o Hypit AI (https://github.com/hypit-ai/hypit).") from None


def run_hypit(args: list[str], cwd: Path | None = None) -> int:
    """Execute hypit CLI with passed arguments."""
    cmd = find_hypit_bin() + args
    return subprocess.call(cmd, cwd=cwd)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        return run_hypit(args)
    except CloneError as e:
        print(f"clone: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())


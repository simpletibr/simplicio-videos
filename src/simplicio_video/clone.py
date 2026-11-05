"""Clone track: Video cloning pipeline using Hypit AI (https://github.com/hypit-ai/hypit).

Invokes Hypit AI agent capabilities to clone videos into complete workflows.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from . import tools
from .childio import run_child


class CloneError(Exception):
    pass


HYPIT_REPO = "https://github.com/hypit-ai/hypit"


def find_hypit_bin() -> list[str]:
    """A local `hypit` binary, else npx at the pinned version (tools.TOOLS['hypit'])."""
    try:
        return tools.npm_command("hypit")
    except tools.ToolError:
        raise CloneError("Nem `hypit` nem `npx` foram encontrados no PATH. Instale o Hypit AI (https://github.com/hypit-ai/hypit).") from None


def status() -> dict:
    """Is Hypit runnable? Local checks only (PATH, `node --version`); nothing is downloaded or run."""
    t = tools.get("hypit")
    binary, npx, node = shutil.which(t.name), shutil.which("npx"), tools.node_version()
    node_ok = node is not None and node[:2] >= tools.NODE_MIN
    source = tools.install_source(t)
    return {"ok": source is not None, "track": t.name, "package": t.source, "pinned": tools.pinned_ref(t), "source": source,
            "binary": binary, "npx": npx,
            "node": {"path": shutil.which("node"), "version": ".".join(map(str, node)) if node else None, "ok": node_ok,
                     "minimum": ".".join(map(str, tools.NODE_MIN))}}


def run_status(args: list[str]) -> int:
    r = status()
    if "--json" in args:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        n = r["node"]
        print(f"hypit {r['pinned']} ({r['package']}): {'pronto, via ' + r['source'] if r['ok'] else 'indisponível'}")
        print(f"  binário hypit: {r['binary'] or '-'}\n  npx: {r['npx'] or '-'}")
        print(f"  node: {n['version'] or 'ausente'} (mínimo {n['minimum']}): {'ok' if n['ok'] else 'insuficiente'}")
    return 0 if r["ok"] else 1


def run_hypit(args: list[str], cwd: Path | None = None) -> int:
    """Execute hypit CLI with passed arguments. `status` without a Build id is the engine's own check (Hypit's needs one)."""
    if args[:1] == ["status"] and all(a == "--json" for a in args[1:]):
        return run_status(args)
    cmd = find_hypit_bin() + args
    return run_child(cmd, cwd=cwd)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        return run_hypit(args)
    except CloneError as e:
        print(f"clone: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())


"""Montage track: Agentic video production platform using OpenMontage (https://github.com/calesthio/OpenMontage).

Invokes OpenMontage production capabilities (backlot, pipelines, tools).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import tools


class MontageError(Exception):
    pass


OPENMONTAGE_REPO = tools.get("openmontage").source


def find_openmontage_dir() -> Path | None:
    """The pinned OpenMontage checkout ($OPENMONTAGE_DIR or $SIMPLICIO_TOOLS_DIR/openmontage), or None."""
    return tools.find("openmontage")


def clone_openmontage(target_dir: Path | None = None) -> Path:
    """Install OpenMontage at its pinned commit (target_dir overrides the location)."""
    if target_dir is not None:
        os.environ["OPENMONTAGE_DIR"] = str(Path(target_dir).expanduser())
    try:
        return Path(tools.install("openmontage"))
    except tools.ToolError as e:
        raise MontageError(str(e)) from None


def ensure_openmontage_dir(target_dir: Path | None = None) -> Path:
    """Find or install OpenMontage."""
    d = find_openmontage_dir()
    if d is not None:
        return d
    return clone_openmontage(target_dir)


def run_montage(args: list[str], cwd: Path | None = None) -> int:
    """Execute OpenMontage with arguments."""
    if args and args[0] in ("clone", "--clone"):
        target = Path(args[1]) if len(args) > 1 else None
        clone_openmontage(target)
        return 0

    om_dir = find_openmontage_dir()
    if om_dir is None:
        if not args or args[0] in ("-h", "--help", "help"):
            print(
                f"OpenMontage ({OPENMONTAGE_REPO})\n\n"
                "OpenMontage não foi encontrado localmente.\n"
                "Para clonar e inicializar, execute:\n"
                "  simplicio-video montage clone [diretório]\n"
                "  ou defina OPENMONTAGE_DIR apontando para o checkout.\n"
            )
            return 0
        om_dir = ensure_openmontage_dir()

    workdir = cwd or om_dir
    py = sys.executable

    first = args[0] if args else "open"
    if first == "open":
        cmd = [py, "-m", "backlot", "open"] + args[1:]
    elif first == "serve":
        cmd = [py, "-m", "backlot", "serve"] + args[1:]
    elif first == "demo":
        cmd = [py, "render_demo.py"] + args[1:]
    elif first in ("doctor", "hyperframes-doctor"):
        cmd = [
            py, "-c",
            "from tools.video.hyperframes_compose import HyperFramesCompose; "
            "r=HyperFramesCompose().execute({'operation':'doctor'}); "
            "import json; print(json.dumps(r.data, indent=2)); "
            "print('OK' if r.success else f'FAIL: {r.error}')"
        ]
    elif first == "preflight":
        cmd = [
            py, "-c",
            "from tools.tool_registry import registry; import json; "
            "registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"
        ]
    else:
        if args and args[0].endswith(".py"):
            cmd = [py] + args
        elif args and args[0] in ("-m", "-c"):
            cmd = [py] + args
        elif args:
            cmd = [py, "-m"] + args
        else:
            cmd = [py, "-m", "backlot", "open"]

    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{om_dir}:{existing_pp}" if existing_pp else str(om_dir)

    return subprocess.call(cmd, cwd=workdir, env=env)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        return run_montage(args)
    except MontageError as e:
        print(f"montage: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

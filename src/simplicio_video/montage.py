"""Montage track: Agentic video production platform using OpenMontage (https://github.com/calesthio/OpenMontage).

Invokes OpenMontage production capabilities (backlot, pipelines, tools).
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

from . import tools


class MontageError(Exception):
    pass


OPENMONTAGE_REPO = tools.get("openmontage").source


def _offline() -> bool:
    return os.environ.get("SIMPLICIO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


def default_openmontage_dir() -> Path:
    """Where the pinned checkout lives. First hit wins:
    $OPENMONTAGE_DIR, $SIMPLICIO_OPENMONTAGE_DIR, $SIMPLICIO_TOOLS_DIR/openmontage,
    $SIMPLICIO_VIDEO_DATA/tools/openmontage, ~/.simplicio-video/tools/openmontage."""
    name = tools.get("openmontage").name
    explicit = os.environ.get("OPENMONTAGE_DIR") or os.environ.get("SIMPLICIO_OPENMONTAGE_DIR")
    if explicit:
        return Path(explicit).expanduser()
    if os.environ.get("SIMPLICIO_TOOLS_DIR"):
        return tools.tools_dir() / name
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(data).expanduser() if data else Path.home() / ".simplicio-video"
    return base / "tools" / name


def find_openmontage_dir() -> Path | None:
    """The pinned OpenMontage checkout (see default_openmontage_dir), or None when not installed."""
    d = default_openmontage_dir()
    return d.resolve() if d.is_dir() and (d / tools.get("openmontage").marker).exists() else None


@contextlib.contextmanager
def _checkout_at(target: Path):
    """Point tools.install at `target` for the duration of the block, then restore the environment."""
    previous = os.environ.get("OPENMONTAGE_DIR")
    os.environ["OPENMONTAGE_DIR"] = str(target)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("OPENMONTAGE_DIR", None)
        else:
            os.environ["OPENMONTAGE_DIR"] = previous


def clone_openmontage(target_dir: Path | None = None) -> Path:
    """Install OpenMontage at its pinned commit (target_dir overrides the location). Never in offline mode."""
    if _offline():
        raise MontageError(
            "modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o OpenMontage. "
            "Instale fora do modo offline com `simplicio-video montage clone` ou aponte OPENMONTAGE_DIR para um checkout."
        )
    target = Path(target_dir).expanduser() if target_dir is not None else default_openmontage_dir()
    try:
        with _checkout_at(target):
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
                f"Local padrão: {default_openmontage_dir()} ($SIMPLICIO_VIDEO_DATA/tools/openmontage).\n"
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

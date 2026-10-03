"""Montage track: Agentic video production platform using OpenMontage (https://github.com/calesthio/OpenMontage).

Invokes OpenMontage production capabilities (backlot, pipelines, tools).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths


class MontageError(Exception):
    pass


OPENMONTAGE_REPO = "https://github.com/calesthio/OpenMontage"


def find_openmontage_dir() -> Path | None:
    """Locate OpenMontage checkout directory from env or known locations."""
    env_dir = os.environ.get("OPENMONTAGE_DIR") or os.environ.get("SIMPLICIO_OPENMONTAGE_DIR")
    if env_dir:
        p = Path(env_dir).expanduser().resolve()
        if p.is_dir():
            return p

    candidates = [
        Path("/projetos/ai/OpenMontage"),
        Path("/projetos/ai/openmontage"),
        paths.home() / "tools" / "openmontage",
        Path.home() / ".openmontage",
        Path.cwd() / "OpenMontage",
    ]
    for c in candidates:
        if c.is_dir() and (c / "backlot").is_dir():
            return c
        if c.is_dir() and (c / ".git").is_dir():
            return c
    return None


def clone_openmontage(target_dir: Path | None = None) -> Path:
    """Clone OpenMontage repository into target directory."""
    git_bin = shutil.which("git")
    if not git_bin:
        raise MontageError("Git não encontrado no PATH para clonar o OpenMontage.")

    dst = target_dir or Path("/projetos/ai/OpenMontage")
    dst = dst.expanduser().resolve()
    if dst.is_dir() and (dst / "backlot").is_dir():
        return dst

    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [git_bin, "clone", "--depth", "1", OPENMONTAGE_REPO, str(dst)]
    print(f"Clonando OpenMontage em {dst}...")
    res = subprocess.call(cmd)
    if res != 0 or not dst.is_dir():
        raise MontageError(f"Falha ao clonar OpenMontage de {OPENMONTAGE_REPO} para {dst}.")
    return dst


def ensure_openmontage_dir(target_dir: Path | None = None) -> Path:
    """Find or auto-clone OpenMontage."""
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

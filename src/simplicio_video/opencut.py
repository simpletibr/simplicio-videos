"""OpenCut track: open-source video editor (https://github.com/OpenCut-app/OpenCut, MIT) for manual finishing.

The rewrite in OpenCut-app/OpenCut has no headless/MCP yet, so the track uses the classic editor
(https://github.com/OpenCut-app/opencut-classic). The deterministic render stays in `render`; OpenCut is the
human-in-the-loop editor for touching up an MP4 the CLI produced.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import paths

OPENCUT_REPO = "https://github.com/OpenCut-app/opencut-classic"


class OpenCutError(Exception):
    pass


def find_opencut_dir() -> Path | None:
    env_dir = os.environ.get("OPENCUT_DIR") or os.environ.get("SIMPLICIO_OPENCUT_DIR")
    candidates = [Path(env_dir).expanduser()] if env_dir else []
    candidates += [paths.home() / "tools" / "opencut", Path.home() / ".opencut", Path.cwd() / "opencut"]
    for c in candidates:
        if c.is_dir() and (c / "package.json").is_file():
            return c.resolve()
    return None


def clone_opencut(target: Path | None = None) -> Path:
    git = shutil.which("git")
    if not git:
        raise OpenCutError("git não encontrado no PATH.")
    dst = (target or paths.home() / "tools" / "opencut").expanduser().resolve()
    if (dst / "package.json").is_file():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    if subprocess.call([git, "clone", "--depth", "1", OPENCUT_REPO, str(dst)]) != 0:
        raise OpenCutError(f"falha ao clonar {OPENCUT_REPO}")
    return dst


def run_opencut(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(f"OpenCut ({OPENCUT_REPO})\n  simplicio-video opencut clone [dir]   # clona o editor\n"
              "  simplicio-video opencut dev           # bun install + bun dev:web (localhost:3000; Docker opcional p/ db)\n"
              "  simplicio-video opencut where         # imprime o checkout (OPENCUT_DIR)")
        return 0
    if first == "clone":
        print(clone_opencut(Path(args[1]) if len(args) > 1 else None))
        return 0
    d = find_opencut_dir()
    if d is None:
        raise OpenCutError("OpenCut não encontrado: rode `simplicio-video opencut clone` ou defina OPENCUT_DIR.")
    if first == "where":
        print(d)
        return 0
    if first == "dev":
        bun = shutil.which("bun")
        if not bun:
            raise OpenCutError("bun não encontrado (https://bun.sh).")
        if subprocess.call([bun, "install"], cwd=d) != 0:
            return 1
        return subprocess.call([bun, "dev:web", *args[1:]], cwd=d)
    raise OpenCutError(f"subcomando desconhecido: {first} (clone|dev|where)")

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

from . import tools

OPENCUT_REPO = tools.get("opencut").source


class OpenCutError(Exception):
    pass


def find_opencut_dir() -> Path | None:
    return tools.find("opencut")


def clone_opencut(target: Path | None = None) -> Path:
    if target is not None:
        os.environ["OPENCUT_DIR"] = str(Path(target).expanduser())
    try:
        return Path(tools.install("opencut"))
    except tools.ToolError as e:
        raise OpenCutError(str(e)) from None


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

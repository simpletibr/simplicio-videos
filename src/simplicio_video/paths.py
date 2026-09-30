"""Locate the plugin home (repo root with templates/, motion/, schema/)."""
from __future__ import annotations

import json
import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
ENGINE_DIR = PKG_DIR / "engine"


def _is_home(p: Path) -> bool:
    pj = p / "plugin.json"
    if not (pj.is_file() and (p / "schema" / "contract.schema.json").is_file()):
        return False
    try:
        return json.loads(pj.read_text(encoding="utf8")).get("name") == "videos"
    except (OSError, ValueError):
        return False


def home(start: Path | None = None) -> Path:
    """SIMPLICIO_VIDEO_HOME, else walk up from `start`/cwd, else the source checkout (editable install)."""
    env = os.environ.get("SIMPLICIO_VIDEO_HOME")
    if env:
        return Path(env).resolve()
    for base in [start, Path.cwd(), PKG_DIR]:
        if base is None:
            continue
        for p in [base.resolve(), *base.resolve().parents]:
            if _is_home(p):
                return p
    raise SystemExit("simplicio-video: plugin home not found (set SIMPLICIO_VIDEO_HOME to the simplicio-videos checkout)")


def schema_path(h: Path | None = None) -> Path:
    return (h or home()) / "schema" / "contract.schema.json"


def tts_python() -> str:
    """Python with kokoro-onnx/soundfile for the local provider."""
    return os.environ.get("SIMPLICIO_TTS_PY", str(Path.home() / ".local/share/simplicio-tts/cbvenv/bin/python"))


def node_env() -> dict:
    env = dict(os.environ)
    extra = Path.home() / ".local/node22/bin"
    if extra.is_dir():
        env["PATH"] = f"{extra}{os.pathsep}{env.get('PATH', '')}"
    return env

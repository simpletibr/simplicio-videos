"""Locate the plugin home (checkout root with plugin.json) and the engine data (schema/, schemas/, templates/, motion/).

Os dados vivem dentro do pacote (`src/simplicio_video/data/`, issue #74): um `pip install` numa pasta limpa basta
para `list`, `validate` e `render`. SIMPLICIO_VIDEO_HOME (checkout) continua valendo e troca os dados para os do checkout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
ENGINE_DIR = PKG_DIR / "engine"


def _is_home(p: Path) -> bool:
    pj = p / "plugin.json"
    if not pj.is_file():
        return False
    try:
        return json.loads(pj.read_text(encoding="utf8")).get("name") == "videos"
    except (OSError, ValueError):
        return False


def home(start: Path | None = None) -> Path:
    """SIMPLICIO_VIDEO_HOME, else walk up from `start`/cwd to the checkout, else the package itself (wheel install)."""
    env = os.environ.get("SIMPLICIO_VIDEO_HOME")
    if env:
        return Path(env).resolve()
    for base in [start, Path.cwd(), PKG_DIR]:
        if base is None:
            continue
        for p in [base.resolve(), *base.resolve().parents]:
            if _is_home(p):
                return p
    return DATA_DIR


def data_dir() -> Path:
    """Dados do motor: os do pacote, ou os do checkout apontado por SIMPLICIO_VIDEO_HOME."""
    env = os.environ.get("SIMPLICIO_VIDEO_HOME")
    if env:
        return Path(env).resolve() / "src" / "simplicio_video" / "data"
    return DATA_DIR


def schema_path(d: Path | None = None) -> Path:
    return (d or data_dir()) / "schema" / "contract.schema.json"


def tts_python() -> str:
    """Python with kokoro-onnx/soundfile for the local provider."""
    return os.environ.get("SIMPLICIO_TTS_PY", str(Path.home() / ".local/share/simplicio-tts/cbvenv/bin/python"))


def node_env() -> dict:
    env = dict(os.environ)
    extra = Path.home() / ".local/node22/bin"
    if extra.is_dir():
        env["PATH"] = f"{extra}{os.pathsep}{env.get('PATH', '')}"
    ff = env.get("SIMPLICIO_FFMPEG_DIR")  # pinned ffmpeg toolchain (ADR-0003): HyperFrames + master.sh + build.mjs use it
    if ff:
        env["PATH"] = f"{ff}{os.pathsep}{env['PATH']}"
        env.setdefault("HYPERFRAMES_FFMPEG_PATH", str(Path(ff) / "ffmpeg"))
        env.setdefault("HYPERFRAMES_FFPROBE_PATH", str(Path(ff) / "ffprobe"))
    return env

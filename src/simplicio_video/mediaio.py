"""One way to find ffmpeg/ffprobe and one ffprobe call for the duration and the metadata of a media file.

Standard library only. The callers of today (render, voice, qc, trilha, media, download, shorts, swap, openverse_sheet) move
here one by one (U06); this module only adds the interface.

The errors are the RAW ones of `subprocess`, `float` and `json`, never wrapped: `FileNotFoundError` (no ffprobe),
`subprocess.CalledProcessError` (ffprobe could not read the file), `subprocess.TimeoutExpired` (only with `timeout`) and
`ValueError` (the output is not a number / not JSON). Each caller keeps turning them into its own error, with its own text.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def ffmpeg_bin(name: str = "ffmpeg") -> str:
    """The program `name` (`ffmpeg` or `ffprobe`) of the locked toolchain, or just `name` for the PATH.

    `SIMPLICIO_FFMPEG_DIR` (ADR-0003: the same ffmpeg build in every backend gives the same bytes) wins when that folder
    really holds `name`; a folder without it, a missing folder or an empty variable fall back to `name`. Read at CALL time.
    (paths.node_env does the equivalent for the child processes of the render: it puts that folder first in PATH.)
    """
    d = os.environ.get("SIMPLICIO_FFMPEG_DIR")
    if d and os.path.exists(os.path.join(d, name)):
        return str(Path(d) / name)
    return name


def _ffprobe(args: list[str], path: Path | str, timeout: float | None) -> str:
    return subprocess.run([ffmpeg_bin("ffprobe"), "-v", "error", *args, str(path)], check=True, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=timeout).stdout


def duration_s(path: Path | str, *, timeout: float | None = None) -> float:
    """Duration in seconds of `path`, from `format=duration` (raw errors: see the module docstring)."""
    return float(_ffprobe(["-show_entries", "format=duration", "-of", "csv=p=0"], path, timeout).strip())


def probe(path: Path | str, *, timeout: float | None = None) -> dict:
    """The raw JSON of `ffprobe -show_format -show_streams` for `path` (nothing converted; raw errors)."""
    return json.loads(_ffprobe(["-print_format", "json", "-show_format", "-show_streams"], path, timeout))

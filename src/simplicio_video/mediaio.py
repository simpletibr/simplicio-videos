"""One way to find ffmpeg/ffprobe and one ffprobe call for the duration and the metadata of a media file.

Standard library and `fsutil` only. The callers of today (render, voice, qc, trilha, media, download, shorts, swap, openverse_sheet)
run their ffprobe here (U06); social keeps its own call (its boundary test allows no environment access and no import but paths and
fsutil). The callers do NOT agree on the program: the ones that always ran the one on the PATH pass `ffprobe=PATH_FFPROBE`, the ones
that ran the locked one (SIMPLICIO_FFMPEG_DIR) pass what their own `_bin` found, and `ffprobe=None` is the resolution of
`ffmpeg_bin`. Moving a caller here never changes which program it runs.

The errors of `duration_s`, `probe` and `run_ffprobe` are the RAW ones of `subprocess`, `float` and `json`, never wrapped:
`FileNotFoundError` (no ffprobe), `subprocess.CalledProcessError` (ffprobe could not read the file; only with `check=True`),
`subprocess.TimeoutExpired` (only with `timeout`) and `ValueError` (the output is not a number / not JSON). Each caller keeps turning
them into its own error, with its own text. `probe_summary` raises the error class the caller hands in.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .fsutil import sha256_file

PATH_FFPROBE = "ffprobe"  # the bare name: the child finds it through its own PATH, SIMPLICIO_FFMPEG_DIR is never read
DURATION_ARGS = ("-show_entries", "format=duration", "-of", "csv=p=0")
PROBE_ARGS = ("-print_format", "json", "-show_format", "-show_streams")


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


def ffprobe_cmd(args: Sequence[str], target: Path | str, *, ffprobe: str | None = None) -> list[str]:
    """`[ffprobe, "-v", "error", *args, target]`; `ffprobe` is the program to run, None is `ffmpeg_bin(PATH_FFPROBE)`."""
    return [ffmpeg_bin(PATH_FFPROBE) if ffprobe is None else ffprobe, "-v", "error", *args, str(target)]


def run_ffprobe(args: Sequence[str], target: Path | str, *, ffprobe: str | None = None, env: Mapping[str, str] | None = None,
                timeout: float | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run `ffprobe -v error *args target` with stdin on /dev/null and stdout/stderr captured as text.

    With `check=False` the caller reads `returncode`, `stdout` and `stderr` itself. `env` is the environment of the child, and a bare
    program name is looked up in the PATH of THAT environment (as `subprocess` does).
    """
    # a tuple, as voice.sh always passed it: str(CalledProcessError) prints the argv
    return subprocess.run(tuple(ffprobe_cmd(args, target, ffprobe=ffprobe)), check=check, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout, env=env)


def duration_s(path: Path | str, *, timeout: float | None = None, ffprobe: str | None = None, env: Mapping[str, str] | None = None,
               check: bool = True) -> float:
    """Duration in seconds of `path`, from `format=duration` (raw errors: see the module docstring).

    With `check=False` an ffprobe that fails is not an error by itself: its (empty) output is what `float` refuses."""
    return float(run_ffprobe(DURATION_ARGS, path, ffprobe=ffprobe, env=env, timeout=timeout, check=check).stdout.strip())


def probe(path: Path | str, *, timeout: float | None = None, ffprobe: str | None = None, env: Mapping[str, str] | None = None) -> dict:
    """The raw JSON of `ffprobe -show_format -show_streams` for `path` (nothing converted; raw errors)."""
    return json.loads(run_ffprobe(PROBE_ARGS, path, ffprobe=ffprobe, env=env, timeout=timeout).stdout)


def fps(raw) -> float:
    """Frames per second from an ffprobe rate (`30000/1001`, `25`), rounded to 3 places; 0.0 when it is not a number.

    A zero denominator (`0/0`, what ffprobe prints for a stream without a frame rate) raises ZeroDivisionError: only ValueError
    and TypeError were ever caught."""
    if not raw or "/" not in str(raw):
        try:
            return round(float(raw), 3)
        except (TypeError, ValueError):
            return 0.0
    num, _, den = str(raw).partition("/")
    try:
        return round(float(num) / float(den or 1), 3)
    except ValueError:
        return 0.0


def probe_summary(path: Path, *, ffprobe: str, fail: Callable[[str], Exception]) -> dict:
    """The facts of the first video stream of `path`, plus its size and sha256: `path`, `duration`, `width`, `height`, `fps`,
    `has_audio`, `size_bytes`, `sha256`.

    `ffprobe` is the program to run and `fail(message)` builds the error of the caller (`ShortsError`, `MediaError`): ffprobe with a
    bad exit code (the message is its stderr, or `ffprobe falhou em <path>`) and a file without a video stream. A reply that is not
    JSON is a raw ValueError, and no reply at all counts as no streams."""
    r = run_ffprobe(PROBE_ARGS, path, ffprobe=ffprobe, check=False)
    if r.returncode != 0:
        raise fail(r.stderr.strip() or f"ffprobe falhou em {path}")
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise fail(f"sem trilha de vídeo: {path}")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = data.get("format", {}).get("duration") or video.get("duration") or 0
    try:
        duration_f = float(duration)
    except (TypeError, ValueError):
        duration_f = 0.0
    return {
        "path": str(path),
        "duration": round(duration_f, 3),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "has_audio": audio is not None,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }

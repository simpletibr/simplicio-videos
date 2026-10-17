"""ffprobe wrapper returning the output facts the API needs (CONTRACT section 5)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

FFPROBE = "ffprobe"
PROBE_TIMEOUT_S = 60


class MediaError(RuntimeError):
    """ffprobe could not run, or the file has no usable video stream."""


def probe(path: str) -> dict[str, Any]:
    args = [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False, timeout=PROBE_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaError(f"ffprobe could not run on {path}: {exc}") from exc

    if proc.returncode != 0:
        raise MediaError(f"ffprobe failed on {path} (exit {proc.returncode}): {proc.stderr.strip()}")

    try:
        data = json.loads(proc.stdout)
    except ValueError as exc:
        raise MediaError(f"ffprobe returned invalid JSON for {path}") from exc
    if not isinstance(data, dict):
        raise MediaError(f"ffprobe returned an unexpected payload for {path}")

    streams: list[dict[str, Any]] = [s for s in (data.get("streams") or []) if isinstance(s, dict)]
    raw_format = data.get("format")
    fmt: dict[str, Any] = raw_format if isinstance(raw_format, dict) else {}
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError(f"no video stream in {path}")

    duration = _as_float(fmt.get("duration")) or _as_float(video.get("duration"))
    if duration is None or duration <= 0:
        raise MediaError(f"could not determine the duration of {path}")

    width = _as_int(video.get("width"))
    height = _as_int(video.get("height"))
    if width is None or height is None:
        raise MediaError(f"could not determine the frame size of {path}")

    fps = _parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate"))
    return {
        "duration_s": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_rate(value: Any) -> float:
    """Parse an ffprobe rate such as '30000/1001'. Returns 0.0 when unknown."""
    if not isinstance(value, str) or "/" not in value:
        return 0.0
    numerator_text, denominator_text = value.split("/", 1)
    try:
        numerator = float(numerator_text)
        denominator = float(denominator_text)
    except ValueError:
        return 0.0
    return numerator / denominator if denominator else 0.0

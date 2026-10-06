"""Voice cloning / local-engine providers: voxcpm, openvoice, voicestudio.

Each writes one raw WAV take to `dst`; voice.py then runs the same trim/chain/48 kHz processing as every provider and
never time-stretches. Engines stay out of this package: VoxCPM and OpenVoice run through their own CLI/env, and
VoiceStudio (AGPL-3.0) is only reached over its local OpenAI-compatible HTTP API, never vendored or imported.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from . import paths


class CloneVoiceError(SystemExit):
    pass


def voxcpm(S: dict, text: str, dst: Path, ref: Path | None) -> None:
    """VoxCPM2 (Apache-2.0): voice design from `control`, or cloning from a reference clip (+ transcript = ultimate cloning)."""
    exe = os.environ.get("VOXCPM_BIN") or shutil.which("voxcpm")
    if not exe:
        raise CloneVoiceError("provider=voxcpm: `voxcpm` CLI not found. pip install voxcpm (Python 3.10-3.12, PyTorch >= 2.5) or set VOXCPM_BIN.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if ref:
        cmd = [exe, "clone", "--text", text, "--reference-audio", str(ref), "--output", str(dst)]
        if S.get("reference_text"):
            cmd += ["--prompt-audio", str(ref), "--prompt-text", S["reference_text"]]
        if S.get("control"):
            cmd += ["--control", S["control"]]
    else:
        cmd = [exe, "design", "--text", text, "--output", str(dst)]
        if S.get("control"):
            cmd += ["--control", S["control"]]
    cmd += ["--seed", str(S["seed"])]
    subprocess.run(cmd, check=True)


def openvoice(S: dict, text: str, dst: Path, ref: Path | None, base_take) -> None:
    """OpenVoice V2 (MIT): Kokoro base take -> tone-color conversion to the reference speaker. `base_take(text, path)` makes the base."""
    if ref is None:
        raise CloneVoiceError("provider=openvoice: set voz.providers.openvoice.reference_audio (a clean 10-30 s clip of an authorized speaker)")
    py = os.environ.get("OPENVOICE_PY")
    ckpt = os.environ.get("OPENVOICE_CHECKPOINTS") or str(Path.home() / ".local/share/simplicio-tts/openvoice/checkpoints_v2")
    if not py or not Path(py).exists():
        raise CloneVoiceError("provider=openvoice: set OPENVOICE_PY to a Python with OpenVoice installed (see voices/openvoice.md)")
    if not (Path(ckpt) / "converter" / "checkpoint.pth").is_file():
        raise CloneVoiceError(f"provider=openvoice: checkpoints_v2 not found at {ckpt} (set OPENVOICE_CHECKPOINTS)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "base.wav"
        base_take(text, base)
        subprocess.run([py, str(paths.ENGINE_DIR / "openvoice_convert.py"), ckpt, str(base), str(ref), str(dst)], check=True)


def voicestudio_url() -> str:
    return os.environ.get("VOICESTUDIO_URL", "http://localhost:3900").rstrip("/")


def voicestudio(S: dict, text: str, dst: Path) -> None:
    """VoiceStudio local API (OpenAI-compatible POST /v1/audio/speech). `voice` = a voice-profile id (your clone)."""
    body = {"model": S["model"], "voice": S["voice"], "input": text, "response_format": "wav"}
    headers = {"Content-Type": "application/json"}
    if os.environ.get("VOICESTUDIO_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["VOICESTUDIO_API_KEY"]
    req = urllib.request.Request(voicestudio_url() + "/v1/audio/speech", data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise CloneVoiceError(f"provider=voicestudio: HTTP {e.code}: {e.read().decode('utf8', 'replace')[:500]}") from None
    except urllib.error.URLError as e:
        raise CloneVoiceError(f"provider=voicestudio: backend not reachable at {voicestudio_url()} ({e.reason}). Start VoiceStudio or set VOICESTUDIO_URL.") from None
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)

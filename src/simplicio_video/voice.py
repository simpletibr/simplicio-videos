"""`simplicio-video voice`: render/cache the narration lines of a contract and write timing.lock.json.

Same processing as the legacy scripts/voice.py (so takes are bit-identical): source -> 48 kHz mono ->
silence trim -> contract ffmpeg chain -> pcm_s16le -bitexact. Never time-stretches: a take longer than
its max_s is an error. Cache key = provider + resolved settings + chain + text-to-say (+ source file hash).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from . import paths
from .contract import Contract, r4

DEFAULT_CHAIN = ("highpass=f=85,equalizer=f=320:t=q:w=1.1:g=-2.5,equalizer=f=3400:t=q:w=1.3:g=2.5,"
                 "equalizer=f=9000:t=q:w=1:g=1.5,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=140:makeup=2:knee=4,"
                 "aecho=1.0:1.0:19|31|47:0.09|0.06|0.04")
FILE_PATTERNS = ["line-{n:02d}.wav", "{id}.wav", "line-{n:02d}.mp3", "line-{n:02d}.m4a"]
TRIM = ("silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.06,areverse,"
        "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.10,areverse")
PROVIDERS = {
    "file": "WAV/MP3 per line generated elsewhere (Gemini in Google AI Studio). Default dir assets/audio/vo/external, line-01.wav ...",
    "local": "Provisional local TTS: Kokoro-82M (Apache-2.0) via kokoro-onnx; needs SIMPLICIO_TTS_PY with kokoro_onnx + models in ~/.local/share/simplicio-tts",
    "gemini": "Gemini TTS API (needs GEMINI_API_KEY); also saves the raw take to the file dir so provider=file reproduces it",
    "elevenlabs": "stub in v0.2 (generate elsewhere, then use provider=file)",
    "xai": "stub in v0.2 (generate elsewhere, then use provider=file)",
}


class VoiceError(SystemExit):
    pass


def sh(*a: str) -> str:
    return subprocess.run(a, check=True, capture_output=True, text=True).stdout


def duration(p: Path) -> float:
    return float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)).strip())


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def settings_for(c: Contract, prov: str) -> dict:
    v = c.data["voz"]
    P = (v.get("providers") or {}).get(prov, {})
    if prov == "file":
        return {"dir": P.get("dir", "assets/audio/vo/external"), "padroes": P.get("padroes", FILE_PATTERNS)}
    if prov == "local":
        voice = P.get("voice") or (v.get("voice") if v["provider"] == "local" else None) or "pf_dora"
        return {"engine": P.get("engine", "kokoro"), "voice": voice, "speed": P.get("speed", 1.0), "lang": P.get("lang", "pt-br")}
    if prov == "gemini":
        voice = P.get("voice") or (v.get("voice") if v["provider"] == "gemini" else None) or "Sulafat"
        return {"model": P.get("model", "gemini-3.8-flash-tts"), "voice": voice, "estilo": P.get("estilo") or v.get("estilo", "")}
    return dict(P)


# ---------------- providers (write a raw take to dst) ----------------
def _file_source(c: Contract, S: dict, idx: int, line: dict) -> Path:
    d = c.rel(S["dir"])
    for pat in S["padroes"]:
        f = d / pat.format(n=idx + 1, id=line["id"])
        if f.is_file():
            return f
    raise VoiceError(f"provider=file: missing external take for {line['id']} (expected {S['dir']}/line-{idx + 1:02d}.wav)")


def _local(S: dict, text: str, dst: Path) -> None:
    code = ("import sys,soundfile as sf\nfrom kokoro_onnx import Kokoro\nfrom pathlib import Path\n"
            "d=Path(sys.argv[1]); k=Kokoro(str(d/'kokoro-v1.0.onnx'),str(d/'voices-v1.0.bin'))\n"
            "a,sr=k.create(sys.argv[2],voice=sys.argv[3],speed=float(sys.argv[4]),lang=sys.argv[5]); sf.write(sys.argv[6],a,sr)\n")
    tts_dir = os.environ.get("KOKORO_DIR", str(Path.home() / ".local/share/simplicio-tts"))
    py = paths.tts_python()
    if not Path(py).exists():
        raise VoiceError(f"provider=local: python with kokoro_onnx not found at {py} (set SIMPLICIO_TTS_PY)")
    subprocess.run([py, "-c", code, tts_dir, text, S["voice"], str(S["speed"]), S["lang"], str(dst)], check=True)


def _gemini(S: dict, text: str, dst: Path) -> None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise VoiceError("provider=gemini: GEMINI_API_KEY not set. Export it (aistudio.google.com -> Get API key) or generate the "
                         "lines in Google AI Studio and use --provider file (assets/audio/vo/external/line-NN.wav).")
    body = {"model": S["model"],
            "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                       "annotations": [{"type": "speech_metadata", "style": S["estilo"]}]}]}],
            "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": S["voice"]}]}}
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions", data=json.dumps(body).encode(),
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        res = json.loads(r.read())
    audio = [c for st in res.get("steps", []) if st.get("type") == "model_output" for c in st.get("content", []) if c.get("type") == "audio"]
    if not audio:
        raise VoiceError("provider=gemini: no audio in response")
    pcm = base64.b64decode(audio[-1]["data"])
    if pcm[:4] != b"RIFF":  # raw 16-bit mono 24 kHz
        import struct
        pcm = b"RIFF" + struct.pack("<I4s4sIHHIIHH4sI", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1, 24000, 48000, 2, 16, b"data", len(pcm)) + pcm
    dst.write_bytes(pcm)


def run(c: Contract, provider: str | None = None, force: bool = False, only: list[str] | None = None, log=print) -> dict:
    v = c.data["voz"]
    prov = provider or v["provider"]
    if prov in ("elevenlabs", "xai"):
        raise VoiceError(f"provider={prov}: stub in simplicio-video v0.2 - generate the takes elsewhere, drop them in the file dir and use --provider file")
    if prov not in PROVIDERS:
        raise VoiceError(f"unknown provider {prov}")
    S = settings_for(c, prov)
    chain = v.get("processamento", DEFAULT_CHAIN)
    cache = c.rel(v.get("cache_dir", "assets/audio/voz"))
    cache.mkdir(parents=True, exist_ok=True)
    lines = c.lines()
    lock_lines, over = {}, []
    for idx, line in enumerate(lines):
        say = line.get("say", line["texto"])
        src = _file_source(c, S, idx, line) if prov == "file" else None
        ident = [prov, S, chain, say] + ([sha256_file(src)] if src else [])
        h = hashlib.sha256(json.dumps(ident, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
        final = cache / f"{line['id']}-{h}.wav"
        if final.is_file() and not force and not (only and line["id"] in only):
            status = "cached"
        else:
            with tempfile.TemporaryDirectory() as td:
                raw, cut = Path(td) / "raw.wav", Path(td) / "cut.wav"
                if prov == "file":
                    sh("ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "48000", str(raw))
                elif prov == "local":
                    _local(S, say, raw)
                else:  # gemini: keep the raw take next to the AI Studio files so provider=file reproduces it
                    fdir = c.rel(settings_for(c, "file")["dir"])
                    fdir.mkdir(parents=True, exist_ok=True)
                    keep = fdir / f"line-{idx + 1:02d}.wav"
                    _gemini(S, say, keep)
                    sh("ffmpeg", "-y", "-v", "error", "-i", str(keep), "-ac", "1", "-ar", "48000", str(raw))
                sh("ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", TRIM, str(cut))
                sh("ffmpeg", "-y", "-v", "error", "-i", str(cut), "-af", chain + ",aresample=48000", "-ac", "1",
                   "-c:a", "pcm_s16le", "-bitexact", str(final))
            for o in cache.glob(f"{line['id']}-*.wav"):
                if o != final:
                    o.unlink()
            status = "rendered"
        dur = round(duration(final), 3)
        rel = os.path.relpath(final, c.dir)
        lock_lines[line["id"]] = {"file": rel, "sha256": sha256_file(final), "dur_s": dur, "t": line["t"], "max_s": line["max_s"],
                                  "scene": line["scene"], "text": line["texto"], "say": say,
                                  "source": os.path.relpath(src, c.dir) if src else None,
                                  "fits": dur <= line["max_s"] + 1e-6, "slack_s": r4(line["max_s"] - dur)}
        log(f"{line['id']} {status:8s} {dur:.2f}s / {line['max_s']}s  {line['texto']}")
        if dur > line["max_s"] + 1e-6:
            over.append(f"{line['id']}: {dur:.3f}s > max_s {line['max_s']}s")
    lock = {"schema": "simplicio.timing-lock/v1", "provider": prov, "settings": S, "processing": chain,
            "cache_dir": v.get("cache_dir", "assets/audio/voz"), "lines": lock_lines}
    (c.dir / "timing.lock.json").write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    log(f"voice: {prov} -> {os.path.relpath(c.dir / 'timing.lock.json')}")
    if over:
        raise VoiceError("lines longer than their slot (no time-stretch by design) - shorten text or widen max_s/scene:\n  " + "\n  ".join(over))
    return lock

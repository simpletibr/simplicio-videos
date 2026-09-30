"""`simplicio-video voice`: render/cache the narration lines of a contract and write timing.lock.json.

Same processing as the legacy scripts/voice.py (so takes are bit-identical): source -> 48 kHz mono ->
silence trim -> contract ffmpeg chain -> pcm_s16le -bitexact. Never time-stretches: a take longer than
its max_s is an error (after one retry with the tighter silence trim TRIM_TIGHT). Cache key = provider + resolved settings + chain + text-to-say (+ source file hash).
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

from . import paths, words as wordsmod
from .contract import Contract, r4

DEFAULT_CHAIN = ("highpass=f=85,equalizer=f=320:t=q:w=1.1:g=-2.5,equalizer=f=3400:t=q:w=1.3:g=2.5,"
                 "equalizer=f=9000:t=q:w=1:g=1.5,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=140:makeup=2:knee=4,"
                 "aecho=1.0:1.0:19|31|47:0.09|0.06|0.04")
FILE_PATTERNS = ["line-{n:02d}.wav", "{id}.wav", "line-{n:02d}.mp3", "line-{n:02d}.m4a"]
TRIM = ("silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.06,areverse,"
        "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.10,areverse")
# Fallback only when a take is longer than its slot: Gemini/AI Studio takes carry a -55..-45 dB noise/breath
# lead-in (0.2 s+) that TRIM keeps. Trimming at -42/-45 dB (40 ms pre-roll, 80 ms tail) removes only that
# air, never speech, and never time-stretches. Takes that already fit keep TRIM (bit-identical to before).
TRIM_TIGHT = ("silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.04,areverse,"
              "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
GEMINI_MODEL = "gemini-3.8-flash-tts"   # cheaper: gemini-3.8-flash-lite-tts (same schema)
GEMINI_SR = 24000
PROVIDERS = {
    "file": "WAV/MP3 per line generated elsewhere (Gemini in Google AI Studio). Default dir assets/audio/vo/external, line-01.wav ...",
    "local": "Provisional local TTS: Kokoro-82M (Apache-2.0) via kokoro-onnx; needs SIMPLICIO_TTS_PY with kokoro_onnx + models in ~/.local/share/simplicio-tts",
    "gemini": "Gemini TTS API (GEMINI_API_KEY from aistudio.google.com/apikey; free tier ok): model/voice/estilo from the contract, WAV 24 kHz kept in the file dir so provider=file reproduces it",
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
        S = {"model": P.get("model", GEMINI_MODEL), "voice": voice, "estilo": P.get("estilo") or v.get("estilo", "")}
        if P.get("api", "interactions") != "interactions":  # keep the default cache key identical to v0.2
            S["api"] = P["api"]
        return S
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


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
# SIMPLICIO_GEMINI_BASE: only for dry runs against a local mock (scripts/mock_gemini_tts.py); never a real key there.
GEMINI_RETRY = (429, 500, 502, 503, 504)


def gemini_base() -> str:
    return os.environ.get("SIMPLICIO_GEMINI_BASE", "").rstrip("/") or GEMINI_BASE


def gemini_request(S: dict, text: str) -> tuple[str, dict]:
    """(url, JSON body) for one single-speaker line. Style goes in speech_metadata (3.8 TTS reads `text` verbatim).

    api=interactions (default, recommended by Google): POST /v1beta/interactions, voice in generation_config.speech_config.
    api=generate_content (still fully supported): POST /v1beta/models/<model>:generateContent with
    responseModalities=[AUDIO] + speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName and part-level speech_metadata.
    Docs: https://ai.google.dev/gemini-api/docs/speech-generation
    """
    meta = {"style": S["estilo"]} if S.get("estilo") else {}
    if S.get("api", "interactions") == "generate_content":
        part = {"text": text, **({"speech_metadata": meta} if meta else {})}
        body = {"contents": [{"role": "user", "parts": [part]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": S["voice"]}}}}}
        return f"{gemini_base()}/models/{S['model']}:generateContent", body
    content = {"type": "text", "text": text}
    if meta:
        content["annotations"] = [{"type": "speech_metadata", **meta}]
    body = {"model": S["model"], "input": [{"type": "user_input", "content": [content]}],
            "response_format": {"type": "audio", "mime_type": "audio/wav", "sample_rate": GEMINI_SR},
            "generation_config": {"speech_config": [{"voice": S["voice"]}]}}
    return f"{gemini_base()}/interactions", body


def gemini_audio(res: dict) -> tuple[bytes, str]:
    """Extract (bytes, mime) of the last audio block from an Interactions or generateContent response."""
    for st in reversed(res.get("steps") or []):  # Interactions: steps[].content[] {type: audio, data, mime_type}
        if st.get("type") == "model_output":
            for c in reversed(st.get("content") or []):
                if c.get("type") == "audio" and c.get("data"):
                    return base64.b64decode(c["data"]), c.get("mime_type", "audio/wav")
    oa = res.get("output_audio") or {}
    if oa.get("data"):
        return base64.b64decode(oa["data"]), oa.get("mime_type", "audio/wav")
    for cand in res.get("candidates") or []:  # generateContent: candidates[].content.parts[].inlineData
        for part in reversed((cand.get("content") or {}).get("parts") or []):
            d = part.get("inlineData") or part.get("inline_data")
            if d and d.get("data"):
                return base64.b64decode(d["data"]), d.get("mimeType") or d.get("mime_type") or "audio/L16;rate=24000"
    raise VoiceError(f"provider=gemini: no audio in response (keys: {sorted(res)})")


def to_wav(data: bytes, mime: str = "") -> bytes:
    """Unary 3.8 TTS already returns WAV (RIFF); older models / generateContent return raw 16-bit mono PCM (24 kHz)."""
    if data[:4] == b"RIFF":
        return data
    import re
    import struct
    m = re.search(r"rate=(\d+)", mime or "")
    sr = int(m.group(1)) if m else GEMINI_SR
    return b"RIFF" + struct.pack("<I4s4sIHHIIHH4sI", 36 + len(data), b"WAVE", b"fmt ", 16, 1, 1, sr, sr * 2, 2, 16,
                                 b"data", len(data)) + data


def _gemini(S: dict, text: str, dst: Path, retries: int = 4) -> dict:
    """Generate one line with the Gemini TTS API and write a WAV (24 kHz mono 16-bit) to dst. Returns request info."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise VoiceError("provider=gemini: GEMINI_API_KEY not set. Create a key at https://aistudio.google.com/apikey (free tier "
                         "works; Google AI Pro does NOT include API quota), export it, or generate the lines in Google AI "
                         "Studio and use --provider file (assets/audio/vo/external/line-NN.wav).")
    import time
    import urllib.error
    url, body = gemini_request(S, text)
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                res = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf8", "replace")[:800] if hasattr(e, "read") else ""
            if e.code in GEMINI_RETRY and attempt < retries:
                wait = float((e.headers or {}).get("Retry-After") or 2 ** (attempt + 1))
                time.sleep(min(wait, 60))
                continue
            hint = " (free-tier rate limit/quota: wait, or enable billing on the AI Studio project)" if e.code == 429 else ""
            raise VoiceError(f"provider=gemini: HTTP {e.code} from {url}{hint}\n{detail}") from None
    audio, mime = gemini_audio(res)
    wav = to_wav(audio, mime)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(wav)
    return {"api": S.get("api", "interactions"), "model": S["model"], "voice": S["voice"], "mime": mime, "chars": len(text),
            "usage": res.get("usage") or res.get("usageMetadata")}


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
    prev_path = c.dir / "timing.lock.json"
    prev = json.loads(prev_path.read_text(encoding="utf8")).get("lines", {}) if prev_path.is_file() else {}
    lang = (v.get("idioma") or "pt-BR").split("-")[0]
    fdir = c.rel(settings_for(c, "file")["dir"])
    tts_chars = 0
    for idx, line in enumerate(lines):
        gen = None
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
                    keep = fdir / f"line-{idx + 1:02d}.wav"
                    gen = _gemini(S, say, keep)
                    tts_chars += len(say)
                    sh("ffmpeg", "-y", "-v", "error", "-i", str(keep), "-ac", "1", "-ar", "48000", str(raw))
                sh("ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", TRIM, str(cut))
                sh("ffmpeg", "-y", "-v", "error", "-i", str(cut), "-af", chain + ",aresample=48000", "-ac", "1",
                   "-c:a", "pcm_s16le", "-bitexact", str(final))
            for o in cache.glob(f"{line['id']}-*.wav"):
                if o != final:
                    o.unlink()
            status = "rendered"
        dur = round(duration(final), 3)
        trim = "normal"
        take = src if prov == "file" else (fdir / f"line-{idx + 1:02d}.wav" if prov == "gemini" else None)
        if dur > line["max_s"] + 1e-6 and take is not None and take.is_file():
            ht = hashlib.sha256(json.dumps(ident + ["trim-tight"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
            tight = cache / f"{line['id']}-{ht}.wav"
            if not tight.is_file() or force or (only and line["id"] in only):
                with tempfile.TemporaryDirectory() as td:
                    raw, cut = Path(td) / "raw.wav", Path(td) / "cut.wav"
                    sh("ffmpeg", "-y", "-v", "error", "-i", str(take), "-ac", "1", "-ar", "48000", str(raw))
                    sh("ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", TRIM_TIGHT, str(cut))
                    sh("ffmpeg", "-y", "-v", "error", "-i", str(cut), "-af", chain + ",aresample=48000", "-ac", "1",
                       "-c:a", "pcm_s16le", "-bitexact", str(tight))
            dur_t = round(duration(tight), 3)
            if dur_t < dur:
                final, dur, trim = tight, dur_t, "tight"
                status += "+tight"
        rel = os.path.relpath(final, c.dir)
        digest = sha256_file(final)
        # word timings (kinetic typography): reuse the lock when the take and the text did not change
        old = prev.get(line["id"], {})
        if old.get("sha256") == digest and old.get("words") and [w["w"] for w in old["words"]] == line["texto"].split():
            wl, wsrc = old["words"], old.get("words_source", "lock")
        else:
            wl, wsrc = wordsmod.align(final, line["texto"], dur, lang)
        lock_lines[line["id"]] = {"file": rel, "sha256": digest, "dur_s": dur, "t": line["t"], "max_s": line["max_s"],
                                  "scene": line["scene"], "text": line["texto"], "say": say,
                                  "source": os.path.relpath(src, c.dir) if src else (
                                      os.path.relpath(fdir / f"line-{idx + 1:02d}.wav", c.dir) if prov == "gemini" else None),
                                  "fits": dur <= line["max_s"] + 1e-6, "slack_s": r4(line["max_s"] - dur),
                                  "words": wl, "words_source": wsrc}
        if trim != "normal":
            lock_lines[line["id"]]["trim"] = trim
        if prov == "gemini":
            lock_lines[line["id"]]["tts"] = gen or (old.get("tts") if old.get("sha256") == digest else None)
        log(f"{line['id']} {status:8s} {dur:.2f}s / {line['max_s']}s  {line['texto']}")
        if dur > line["max_s"] + 1e-6:
            over.append(f"{line['id']}: {dur:.3f}s > max_s {line['max_s']}s")
    lock = {"schema": "simplicio.timing-lock/v1", "provider": prov, "settings": S, "processing": chain,
            "cache_dir": v.get("cache_dir", "assets/audio/voz"), "lines": lock_lines}
    if prov in ("gemini", "elevenlabs", "xai"):  # metering for credits (ADR-0002): only lines synthesized in this run
        lock["usage"] = {"tts_chars_this_run": tts_chars}
    (c.dir / "timing.lock.json").write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    log(f"voice: {prov} -> {os.path.relpath(c.dir / 'timing.lock.json')}")
    if over:
        raise VoiceError("lines longer than their slot (no time-stretch by design) - shorten text or widen max_s/scene:\n  " + "\n  ".join(over))
    return lock

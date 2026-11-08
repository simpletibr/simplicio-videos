"""`simplicio-video voice`: render/cache the narration lines of a contract and write timing.lock.json.

Same processing as the legacy scripts/voice.py of the per-video projects (no longer in this repository; so takes are bit-identical): source -> 48 kHz mono ->
silence trim -> contract ffmpeg chain -> pcm_s16le -bitexact. Never time-stretches: a take longer than
its max_s is an error (after one retry with the tighter silence trim TRIM_TIGHT). Cache key = provider + resolved settings + chain + text-to-say (+ source file hash).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from . import aio, childio, hostos, mediaio, paths, rede, voice_clone, voz_catalogo, words as wordsmod
from .contract import Contract, r4
from .fsutil import sha256_file

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
AUDIO8_MODEL = "Edge0/Audio8-TTS-Realistic-0.6b"  # Apache-2.0; the 0.1B checkpoint has its own license, so it is not the default
GEMINI_SR = 24000
# The providers are described by `REGISTRO` (below the provider functions); PROVIDERS, NETWORK_PROVIDERS and GENERATIVE are derived from it.
# Lines are generated concurrently only for providers that WAIT on the network; local providers burn CPU, so they stay
# serial (asyncio does not speed up CPU work). The ffmpeg processing of every line stays serial as well.
DEFAULT_CONCURRENCY = 4


def effective_concurrency(prov: str, requested: int | None = None) -> int:
    """How many lines may be generated at once: 1 for local providers, else the request (default DEFAULT_CONCURRENCY)."""
    return aio.clamp(requested, DEFAULT_CONCURRENCY) if prov in NETWORK_PROVIDERS else 1


class VoiceError(SystemExit):
    pass


def sh(*a: str) -> str:
    return subprocess.run(a, check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True).stdout


def duration(p: Path) -> float:
    return mediaio.duration_s(p, ffprobe=mediaio.PATH_FFPROBE)


def _bloco(v: dict, prov: str) -> dict:
    """The `voz.providers.<prov>` block of the contract (empty when it is not there)."""
    return (v.get("providers") or {}).get(prov, {})


def _settings_file(v: dict) -> dict:
    P = _bloco(v, "file")
    return {"dir": P.get("dir", "assets/audio/vo/external"), "padroes": P.get("padroes", FILE_PATTERNS)}


def _settings_local(v: dict) -> dict:
    P = _bloco(v, "local")
    voice = P.get("voice") or (v.get("voice") if v["provider"] == "local" else None) or "pf_dora"
    return {"engine": P.get("engine", "kokoro"), "voice": voice, "speed": P.get("speed", 1.0), "lang": P.get("lang", "pt-br")}


def _settings_gemini(v: dict) -> dict:
    P = _bloco(v, "gemini")
    voice = P.get("voice") or (v.get("voice") if v["provider"] == "gemini" else None) or "Sulafat"
    S = {"model": P.get("model", GEMINI_MODEL), "voice": voice, "estilo": P.get("estilo") or v.get("estilo", "")}
    if P.get("api", "interactions") != "interactions":  # keep the default cache key identical to v0.2
        S["api"] = P["api"]
    return S


def _settings_voxcpm(v: dict) -> dict:
    P = _bloco(v, "voxcpm")
    return {"control": P.get("control", ""), "reference_audio": P.get("reference_audio", ""), "reference_text": P.get("reference_text", ""),
            "seed": P.get("seed", 42)}


def _settings_audio8(v: dict) -> dict:
    P = _bloco(v, "audio8")
    return {"model": P.get("model", AUDIO8_MODEL), "reference_audio": P.get("reference_audio", ""),
            "reference_text": P.get("reference_text", ""), "device": P.get("device", "")}


def _settings_openvoice(v: dict) -> dict:
    return {"reference_audio": _bloco(v, "openvoice").get("reference_audio", ""), "base": _settings_local(v)}


def _settings_voicestudio(v: dict) -> dict:
    P = _bloco(v, "voicestudio")
    return {"model": P.get("model", "omnivoice"), "voice": P.get("voice") or (v.get("voice") if v["provider"] == "voicestudio" else None) or "default"}


def _settings_bloco(prov: str) -> Callable[[dict], dict]:
    """The settings of a provider with no fields of its own (the stubs): its block of the contract, as it is."""
    return lambda v: dict(_bloco(v, prov))


def settings_for(c: Contract, prov: str) -> dict:
    p = REGISTRO.get(prov)
    v = c.data["voz"]
    return p.settings(v) if p else dict(_bloco(v, prov))


def keep_path(fdir: Path, prov: str, idx: int) -> Path:
    return (fdir if prov == "gemini" else fdir / prov) / f"line-{idx + 1:02d}.wav"


def _stub(prov: str) -> VoiceError:
    return VoiceError(f"provider={prov}: stub in simplicio-video v0.2 - generate the takes elsewhere, drop them in the file dir and use --provider file")


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
    tts_dir = os.environ.get("KOKORO_DIR", str(hostos.home_dir() / ".local/share/simplicio-tts"))
    py = paths.tts_python()
    if not Path(py).exists():
        raise VoiceError(f"provider=local: python with kokoro_onnx not found at {py} (set SIMPLICIO_TTS_PY)")
    childio.check_child([py, "-c", code, tts_dir, text, S["voice"], str(S["speed"]), S["lang"], str(dst)])


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
# SIMPLICIO_GEMINI_BASE: only for dry runs against a local mock (tests/tools/mock_gemini.py); never a real key there.
GEMINI_RETRY = (429, 500, 502, 503, 504)
# The key goes to this base in the `x-goog-api-key` header, so the base is https, or http to this machine. It is the rule of the swap adapter
# (swap_providers/gemini.py, `GeminiAdapter._base`) with the same words; tests/test_voice_gemini_base.py fails if the two copies drift apart.
GEMINI_PLAIN_HTTP_HOSTS = ("localhost", "127.0.0.1", "::1")
GEMINI_BASE_REFUSAL = "SIMPLICIO_GEMINI_BASE precisa ser https (http só em localhost): a chave não vai em texto claro"


def gemini_base() -> str:
    """The base URL of the Gemini API: SIMPLICIO_GEMINI_BASE or the official one, without the trailing slash.

    Refused (VoiceError) unless it is https, or http to localhost, 127.0.0.1 or ::1: the key would travel in clear."""
    base = os.environ.get("SIMPLICIO_GEMINI_BASE", "").rstrip("/") or GEMINI_BASE
    u = urlparse(base.strip())  # the adapter judges the text without the spaces around it
    if u.scheme != "https" and not (u.scheme == "http" and u.hostname in GEMINI_PLAIN_HTTP_HOSTS):
        raise VoiceError(f"provider=gemini: {GEMINI_BASE_REFUSAL}")
    return base


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
            with rede.urlopen_seguro(req, timeout=180) as r:  # urlopen, but a redirect to another host does not take the key along
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


# ---------------- the registry: what a provider IS (voz_catalogo) and what it DOES (settings, gerar) ----------------
@dataclass(frozen=True)
class Provider:
    """One voice provider.

    `settings(voz)` resolves its settings from the `voz` block of the contract: the order of its keys is the order of `settings` in
    timing.lock.json and the dict is part of the cache key. `gerar(c, S, text, dst, ref)` writes the raw take of one line to `dst`
    (`ref` is the reference audio, or None) and returns the request info the lock keeps (only gemini has some). `file` and the stubs
    never generate: `gerar` says so.
    """
    nome: str
    descricao: str
    rede: bool
    guarda_bruto: bool
    settings: Callable[[dict], dict]
    gerar: Callable[..., dict | None]


# `gerar` looks the function up by name when it is CALLED (tests replace `voice._gemini`, `voice._local` and `voice_clone.*`)
def _gerar_gemini(c: Contract, S: dict, text: str, dst: Path, ref: Path | None) -> dict:
    return _gemini(S, text, dst)


def _gerar_local(c: Contract, S: dict, text: str, dst: Path, ref: Path | None) -> None:
    _local(S, text, dst)


def _gerar_voxcpm(c: Contract, S: dict, text: str, dst: Path, ref: Path | None) -> None:
    voice_clone.voxcpm(S, text, dst, ref)


def _gerar_audio8(c: Contract, S: dict, text: str, dst: Path, ref: Path | None) -> None:
    voice_clone.audio8(S, text, dst, ref)


def _gerar_openvoice(c: Contract, S: dict, text: str, dst: Path, ref: Path | None) -> None:
    voice_clone.openvoice(S, text, dst, ref, lambda t, p: _local(S["base"], t, p))


def _gerar_voicestudio(c: Contract, S: dict, text: str, dst: Path, ref: Path | None) -> None:
    voice_clone.voicestudio(S, text, dst)


def _gerar_file(c: Contract, S: dict, text: str, dst: Path, ref: Path | None) -> None:
    raise VoiceError(f"provider=file: nothing to generate, the takes are the files in {S['dir']}")


def _gerar_stub(prov: str) -> Callable[..., None]:
    def gerar(c: Contract, S: dict, text: str, dst: Path, ref: Path | None) -> None:
        raise _stub(prov)
    return gerar


_COMPORTAMENTO: dict[str, tuple[Callable[[dict], dict], Callable[..., dict | None]]] = {
    "file": (_settings_file, _gerar_file),
    "local": (_settings_local, _gerar_local),
    "gemini": (_settings_gemini, _gerar_gemini),
    "voxcpm": (_settings_voxcpm, _gerar_voxcpm),
    "openvoice": (_settings_openvoice, _gerar_openvoice),
    "voicestudio": (_settings_voicestudio, _gerar_voicestudio),
    "audio8": (_settings_audio8, _gerar_audio8),
    "elevenlabs": (_settings_bloco("elevenlabs"), _gerar_stub("elevenlabs")),
    "xai": (_settings_bloco("xai"), _gerar_stub("xai")),
}
REGISTRO: dict[str, Provider] = {f.nome: Provider(f.nome, f.descricao, f.rede, f.guarda_bruto, *_COMPORTAMENTO[f.nome])
                                 for f in voz_catalogo.FICHAS}
PROVIDERS = {nome: p.descricao for nome, p in REGISTRO.items()}
NETWORK_PROVIDERS = tuple(nome for nome, p in REGISTRO.items() if p.rede)
# generative providers keep the raw take; gemini keeps the historical dir, the others a per-provider subdir (keep_path)
GENERATIVE = tuple(nome for nome, p in REGISTRO.items() if p.guarda_bruto)


def _normaliza(take: Path, raw: Path) -> None:
    """Any take -> 48 kHz mono WAV. The local provider skips this: it writes its take straight to `raw`."""
    sh("ffmpeg", "-y", "-v", "error", "-i", str(take), "-ac", "1", "-ar", "48000", str(raw))


def _cadeia(raw: Path, dst: Path, chain: str, trim: str) -> None:
    """The ONE ffmpeg chain of a take: silence trim (TRIM, or TRIM_TIGHT in the retry), then the contract chain at 48 kHz mono as
    pcm_s16le -bitexact. It is the determinism of contract -> MP4: the bytes of `dst` depend on `raw`, `chain` and `trim`, not on who calls."""
    cut = raw.with_name("cut.wav")
    sh("ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", trim, str(cut))
    sh("ffmpeg", "-y", "-v", "error", "-i", str(cut), "-af", chain + ",aresample=48000", "-ac", "1",
       "-c:a", "pcm_s16le", "-bitexact", str(dst))


def _digest(ident: list) -> str:
    return hashlib.sha256(json.dumps(ident, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def _is_cached(final: Path, force: bool, only: list[str] | None, line_id: str) -> bool:
    return final.is_file() and not force and not (only and line_id in only)


def _line_ident(c: Contract, prov: str, S: dict, chain: str, line: dict, idx: int) -> list:
    """The cache identity of one line. ONE function for the prefetch and for the real loop, so they cannot drift apart."""
    say = line.get("say", line["texto"])
    src = _file_source(c, S, idx, line) if prov == "file" else None
    ref = c.rel(S["reference_audio"]) if S.get("reference_audio") else None
    if ref is not None and not ref.is_file():
        raise VoiceError(f"provider={prov}: reference_audio not found: {S['reference_audio']}")
    return [prov, S, chain, say] + ([sha256_file(src)] if src else []) + ([sha256_file(ref)] if ref else [])


async def _generate_all(c: Contract, prov: str, S: dict, jobs: list[tuple[int, str, Path]], concurrency: int) -> tuple[dict, dict]:
    """Generate the raw takes of `jobs` [(index, text, dst)] with at most `concurrency` requests in flight.
    Returns (done, errors) by line index. After the first failure no new request starts, but the ones already in flight
    are awaited and kept: the provider charged them, so the next round must not pay for them again."""
    sem = asyncio.Semaphore(concurrency)
    out: dict = {}
    errors: dict = {}

    async def one(idx: int, text: str, dst: Path) -> None:
        async with sem:
            if errors:
                return  # a line failed: do not start (and pay for) more
            try:
                out[idx] = await aio.athread(REGISTRO[prov].gerar, c, S, text, dst, None)
            except (Exception, SystemExit) as e:  # noqa: BLE001 (VoiceError is a SystemExit: keep it per line, not first-come)
                errors[idx] = e

    tasks = [asyncio.create_task(one(*j)) for j in jobs]  # in line order
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return out, errors


def _prefetch(c: Contract, prov: str, S: dict, chain: str, cache: Path, fdir: Path, lines: list[dict], force: bool,
              only: list[str] | None, concurrency: int) -> tuple[dict, dict]:
    """Phase 1 (network providers only): generate every raw take that is not cached, concurrently. Phase 2 (the loop in
    `run`) then processes the lines in order exactly as the serial mode does, so outputs and timing.lock.json are identical.
    Returns (takes, errors) by line index."""
    todo = []
    for idx, line in enumerate(lines):
        say = line.get("say", line["texto"])
        final = cache / f"{line['id']}-{_digest(_line_ident(c, prov, S, chain, line, idx))}.wav"
        if not _is_cached(final, force, only, line["id"]):
            todo.append((idx, say, keep_path(fdir, prov, idx)))
    if concurrency < 2 or len(todo) < 2:
        return {}, {}
    return aio.run_sync(_generate_all(c, prov, S, todo, concurrency))


def run(c: Contract, provider: str | None = None, force: bool = False, only: list[str] | None = None, log=print,
        concurrency: int | None = None) -> dict:
    v = c.data["voz"]
    prov = provider or v["provider"]
    if prov in ("elevenlabs", "xai"):
        raise _stub(prov)
    if prov not in PROVIDERS:
        raise VoiceError(f"unknown provider {prov}")
    p = REGISTRO[prov]
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
    workers = effective_concurrency(prov, concurrency)
    pre, perr = _prefetch(c, prov, S, chain, cache, fdir, lines, force, only, workers) if workers > 1 else ({}, {})
    first_error = perr[min(perr)] if perr else None  # the lowest line index, like the serial mode would have hit first
    for idx, line in enumerate(lines):
        gen = None
        say = line.get("say", line["texto"])
        src = _file_source(c, S, idx, line) if prov == "file" else None
        ref = c.rel(S["reference_audio"]) if S.get("reference_audio") else None
        ident = _line_ident(c, prov, S, chain, line, idx)
        h = _digest(ident)
        final = cache / f"{line['id']}-{h}.wav"
        if _is_cached(final, force, only, line["id"]):
            status = "cached"
        elif first_error is not None and idx not in pre:
            continue  # phase 1 failed: finalize into the cache every line that WAS generated (and paid), skip the rest
        else:
            with tempfile.TemporaryDirectory() as td:
                raw = Path(td) / "raw.wav"
                if prov == "file":
                    _normaliza(src, raw)
                elif not p.guarda_bruto:  # local: synthesised straight into the raw take
                    p.gerar(c, S, say, raw, ref)
                else:  # generative: keep the raw take (gemini next to the AI Studio files) so the run is reproducible
                    keep = keep_path(fdir, prov, idx)
                    gen = pre[idx] if idx in pre else p.gerar(c, S, say, keep, ref)
                    tts_chars += len(say)
                    _normaliza(keep, raw)
                _cadeia(raw, final, chain, TRIM)
            for o in cache.glob(f"{line['id']}-*.wav"):
                if o != final:
                    o.unlink()
            status = "rendered"
        dur = round(duration(final), 3)
        trim = "normal"
        take = src if prov == "file" else (keep_path(fdir, prov, idx) if p.guarda_bruto else None)
        if dur > line["max_s"] + 1e-6 and take is not None and take.is_file():
            ht = _digest(ident + ["trim-tight"])
            tight = cache / f"{line['id']}-{ht}.wav"
            if not tight.is_file() or force or (only and line["id"] in only):
                with tempfile.TemporaryDirectory() as td:
                    raw = Path(td) / "raw.wav"
                    _normaliza(take, raw)
                    _cadeia(raw, tight, chain, TRIM_TIGHT)
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
                                      os.path.relpath(keep_path(fdir, prov, idx), c.dir) if p.guarda_bruto else None),
                                  "fits": dur <= line["max_s"] + 1e-6, "slack_s": r4(line["max_s"] - dur),
                                  "words": wl, "words_source": wsrc}
        if trim != "normal":
            lock_lines[line["id"]]["trim"] = trim
        if prov == "gemini":
            lock_lines[line["id"]]["tts"] = gen or (old.get("tts") if old.get("sha256") == digest else None)
        log(f"{line['id']} {status:8s} {dur:.2f}s / {line['max_s']}s  {line['texto']}")
        if dur > line["max_s"] + 1e-6:
            over.append(f"{line['id']}: {dur:.3f}s > max_s {line['max_s']}s")
    if first_error is not None:  # every generated line is in the cache now: the next round only pays for what is missing
        raise first_error
    lock = {"schema": "simplicio.timing-lock/v1", "provider": prov, "settings": S, "processing": chain,
            "cache_dir": v.get("cache_dir", "assets/audio/voz"), "lines": lock_lines}
    if prov in ("gemini", "elevenlabs", "xai"):  # metering for credits (ADR-0002): only lines synthesized in this run
        lock["usage"] = {"tts_chars_this_run": tts_chars}
    (c.dir / "timing.lock.json").write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    log(f"voice: {prov} -> {os.path.relpath(c.dir / 'timing.lock.json')}")
    if over:
        raise VoiceError("lines longer than their slot (no time-stretch by design) - shorten text or widen max_s/scene:\n  " + "\n  ".join(over))
    return lock

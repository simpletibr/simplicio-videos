#!/usr/bin/env python3
"""Render the voice-over lines from spec.json -> assets/audio/vo/ (cached, committed).

Deterministic by construction:
  * each line's file name embeds a hash of everything that shapes it (provider settings, text-to-say,
    seeds, processing chain); same spec => cache hit => no TTS call;
  * stochastic models (Chatterbox) run with fixed seeds; with `select: asr` we render every seed and keep
    the take whose speech-to-text matches the script best (ties -> shortest). CPU inference is not guaranteed
    bit-exact across runs, so the committed WAVs (cache) are the source of truth for reproducible renders.
Providers (spec.voice.provider, or env VOICE_PROVIDER):
  chatterbox  local, MIT (Resemble AI Chatterbox Multilingual V3, language_id=pt). Voice timbre comes from a
              reference clip that we SYNTHESIZE with Kokoro (Apache-2.0) - no real person's voice is cloned.
  kokoro      local, Apache-2.0 (hexgrad/Kokoro-82M) via kokoro-onnx (MIT).
  elevenlabs  cloud, needs ELEVENLABS_API_KEY + voice_id. Paid plan required for commercial use.
  file        externally generated WAV/MP3 per line (e.g. Gemini TTS from Google AI Studio) dropped in
              assets/audio/vo/external/line-01.wav ... line-09.wav (or <id>.wav); trimmed + processed like the rest.
  xai         cloud, xAI/Grok TTS (POST /v1/tts, language pt-BR), needs XAI_API_KEY. US$15 / 1M chars (Sep 2026).
No time-stretching: a line longer than its slot is an error (shorten the text or widen the slot).
Processing (ffmpeg, spec.voice.processing): trim silence -> EQ -> gentle compression -> subtle room -> 48 kHz mono.
"""
import difflib, hashlib, json, os, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = json.loads((ROOT / "spec.json").read_text(encoding="utf8"))
V = spec["voice"]
prov = os.environ.get("VOICE_PROVIDER", V["provider"])
P = V["providers"][prov]
OUT = ROOT / "assets/audio/vo"
OUT.mkdir(parents=True, exist_ok=True)
TTS_DIR = Path(os.environ.get("KOKORO_DIR", Path.home() / ".local/share/simplicio-tts"))
force = "--force" in sys.argv
only = [a for a in sys.argv[1:] if not a.startswith("--")]

def sh(*a):
    return subprocess.run(a, check=True, capture_output=True, text=True).stdout

def duration(path):
    return float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)).strip())

# ---------------- providers ----------------
_k = None
def kokoro(text, dst, voice, speed=1.0, lang="pt-br"):
    global _k
    import soundfile as sf
    from kokoro_onnx import Kokoro
    if _k is None:
        _k = Kokoro(str(TTS_DIR / "kokoro-v1.0.onnx"), str(TTS_DIR / "voices-v1.0.bin"))
    a, sr = _k.create(text, voice=voice, speed=speed, lang=lang)
    sf.write(dst, a, sr)

_cb = None
def chatterbox(text, dst, seed):
    global _cb
    import torch, torchaudio as ta
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    if _cb is None:
        _cb = ChatterboxMultilingualTTS.from_pretrained(device="cpu", t3_model=P.get("t3_model", "v3"))
    ref = OUT / "ref" / f"{P['reference']['voice']}.wav"
    if not ref.exists():  # synthetic reference voice (Kokoro, Apache-2.0)
        ref.parent.mkdir(exist_ok=True)
        kokoro(P["reference"]["text"], str(ref), P["reference"]["voice"], 1.0)
    torch.manual_seed(seed)
    w = _cb.generate(text, language_id="pt", audio_prompt_path=str(ref), exaggeration=P["exaggeration"],
                     cfg_weight=P["cfg_weight"], temperature=P["temperature"])
    ta.save(dst, w, _cb.sr)

def elevenlabs(text, dst):
    key = os.environ.get(P.get("env", "ELEVENLABS_API_KEY"))
    if not key:
        sys.exit("ELEVENLABS_API_KEY not set (provider=elevenlabs). Export it or switch spec.voice.provider.")
    if P["voice_id"].startswith("<"):
        sys.exit("Set spec.voice.providers.elevenlabs.voice_id to a real ElevenLabs voice id.")
    body = json.dumps({"text": text, "model_id": P["model"], "voice_settings": {
        "stability": P["stability"], "similarity_boost": P["similarity_boost"], "style": P["style"]}}).encode()
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{P['voice_id']}?output_format=mp3_44100_128",
        data=body, headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    mp3 = dst.replace(".wav", ".mp3")
    with urllib.request.urlopen(req, timeout=120) as r, open(mp3, "wb") as f:
        f.write(r.read())
    sh("ffmpeg", "-y", "-v", "error", "-i", mp3, dst)

def xai(text, dst):
    """xAI (Grok) Text to Speech: POST https://api.x.ai/v1/tts (docs.x.ai > Voice > Text to Speech)."""
    key = os.environ.get(P.get("env", "XAI_API_KEY"))
    if not key:
        sys.exit("XAI_API_KEY not set (provider=xai). Export it or switch spec.voice.provider.")
    body = json.dumps({"text": text, "voice_id": P["voice_id"], "language": P.get("language", "pt-BR")}).encode()
    req = urllib.request.Request("https://api.x.ai/v1/tts", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    mp3 = dst.replace(".wav", ".mp3")
    with urllib.request.urlopen(req, timeout=120) as r, open(mp3, "wb") as f:
        f.write(r.read())  # default output: MP3 24 kHz
    sh("ffmpeg", "-y", "-v", "error", "-i", mp3, dst)

def external_path(line_idx, line):
    """provider=file: externally generated narration (e.g. Gemini TTS / AI Studio), one file per line.
    Looks for <dir>/<pattern> with {n} = 1-based line number (zero-padded) and {id} = line id."""
    d = ROOT / P.get("dir", "assets/audio/vo/external")
    for pat in P.get("patterns", ["line-{n:02d}.wav", "{id}.wav", "line-{n:02d}.mp3", "line-{n:02d}.m4a"]):
        f = d / pat.format(n=line_idx + 1, id=line["id"])
        if f.exists():
            return f
    sys.exit(f"provider=file: missing external VO for {line['id']} (expected e.g. {d.relative_to(ROOT)}/line-{line_idx + 1:02d}.wav)")

def external(src, dst):
    sh("ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "48000", dst)

# ---------------- take selection (speech-to-text) ----------------
_asr = None
def asr_score(path, text):
    global _asr
    import soundfile as sf
    from faster_whisper import WhisperModel
    if _asr is None:
        _asr = WhisperModel(V.get("asr_model", "small"), device="cpu", compute_type="int8")
    tmp = path + ".16k.wav"
    sh("ffmpeg", "-y", "-v", "error", "-i", path, "-ar", "16000", "-ac", "1", tmp)
    a, _ = sf.read(tmp, dtype="float32")
    segs, _ = _asr.transcribe(a, language="pt", beam_size=5)
    hyp = "".join(s.text for s in segs).strip()
    norm = lambda s: re.sub(r"[^\w ]", "", s.lower()).split()
    return difflib.SequenceMatcher(None, norm(text), norm(hyp)).ratio(), hyp

def trim(src, dst):
    t = "silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.06,areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.10,areverse"
    sh("ffmpeg", "-y", "-v", "error", "-i", src, "-af", t, dst)

# ---------------- main ----------------
chain = V["processing"]["ffmpeg"]
old = json.loads((OUT / "manifest.json").read_text())["lines"] if (OUT / "manifest.json").exists() else {}
settings = {k: v for k, v in P.items() if k not in ("env",)}
manifest = {"provider": prov, "settings": settings, "processing": chain, "lines": {}}
for li, line in enumerate(V["lines"]):
    say = line.get("say", line["text"])
    src_ext = external_path(li, line) if prov == "file" else None
    ext_sha = hashlib.sha256(src_ext.read_bytes()).hexdigest() if src_ext else None  # new file dropped in => re-process
    ident = json.dumps([prov, settings, chain, say, V.get("select")] + ([ext_sha] if ext_sha else []), ensure_ascii=False, sort_keys=True)
    h = hashlib.sha256(ident.encode()).hexdigest()[:12]
    final = OUT / f"{line['id']}-{h}.wav"
    info = old.get(line["id"], {}) if final.exists() else {}
    if final.exists() and not force and not (only and line["id"] in only):
        status = "cached"
    else:
        with tempfile.TemporaryDirectory() as td:
            takes = []
            seeds = P.get("seeds", [0]) if prov == "chatterbox" else [0]
            for seed in seeds:
                raw, cut = f"{td}/raw{seed}.wav", f"{td}/cut{seed}.wav"
                if prov == "chatterbox": chatterbox(say, raw, seed)
                elif prov == "kokoro": kokoro(say, raw, P["voice"], P.get("speed", 1.0), P.get("lang", "pt-br"))
                elif prov == "xai": xai(say, raw)
                elif prov == "file": external(src_ext, raw)
                else: elevenlabs(say, raw)
                trim(raw, cut)
                d = duration(cut)
                score, hyp = asr_score(cut, line["text"]) if V.get("select") == "asr" else (1.0, "")
                takes.append({"seed": seed, "dur": d, "score": score, "hyp": hyp, "path": cut})
                print(f"   {line['id']} seed {seed}: {d:.2f}s asr={score:.2f} {hyp}", flush=True)
            best = sorted(takes, key=lambda t: (-round(t["score"], 2), t["dur"]))[0]  # best ASR match, then shortest
            sh("ffmpeg", "-y", "-v", "error", "-i", best["path"], "-af", chain + ",aresample=48000", "-ac", "1", "-c:a", "pcm_s16le", "-bitexact", str(final))
        for o in OUT.glob(f"{line['id']}-*.wav"):
            if o != final: o.unlink()
        info = {"seed": best["seed"], "asr_score": round(best["score"], 3), "asr_text": best["hyp"]}
        status = "rendered"
    manifest["lines"][line["id"]] = {"file": str(final.relative_to(ROOT)), "t": line["t"], "dur_s": round(duration(final), 3),
        "max_s": line["max_s"], "text": line["text"], "say": say, **{k: info.get(k) for k in ("seed", "asr_score", "asr_text")}}
    m = manifest["lines"][line["id"]]
    print(f"{line['id']} {status:8s} {m['dur_s']:.2f}s/{line['max_s']}s  {line['text']}", flush=True)
over = [f"{k}: {m['dur_s']:.2f}s > slot {m['max_s']}s" for k, m in manifest["lines"].items() if m["dur_s"] > m["max_s"]]
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
print(f"voice: {prov} -> {OUT.relative_to(ROOT)}/manifest.json")
if over:
    sys.exit("lines longer than their slot (no time-stretch by design) - shorten text or move/widen slots:\n  " + "\n  ".join(over))

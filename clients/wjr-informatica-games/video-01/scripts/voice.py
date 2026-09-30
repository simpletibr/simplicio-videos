#!/usr/bin/env python3
"""Render the voice-over lines from spec.json -> assets/audio/vo/ (cached, committed).

Deterministic by construction: each line's file name embeds a hash of
(provider, model, voice, speed, lang, text-to-say, max_s). Same spec => same cache hit => no TTS call.
Providers:
  kokoro      local, Apache-2.0 weights (hexgrad/Kokoro-82M) via kokoro-onnx (MIT). Needs the venv from
              scripts/setup-tts.sh (or SIMPLICIO_TTS_PY / KOKORO_DIR env vars).
  elevenlabs  cloud, needs ELEVENLABS_API_KEY (+ a voice_id in spec.json). Paid/ToS apply.
Post-processing (provider-agnostic, ffmpeg): trim leading/trailing silence, speed up with atempo if the
line is longer than its slot (max 1.3x), resample to 48 kHz mono s16.
"""
import hashlib, json, os, subprocess, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = json.loads((ROOT / "spec.json").read_text(encoding="utf8"))
V = spec["voice"]
prov = os.environ.get("VOICE_PROVIDER", V["provider"])
P = V["providers"][prov]
OUT = ROOT / "assets/audio/vo"
OUT.mkdir(parents=True, exist_ok=True)
force = "--force" in sys.argv

def sh(*a, **k):
    return subprocess.run(a, check=True, capture_output=True, text=True, **k).stdout

def duration(path):
    return float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)).strip())

_kokoro = None
def tts_kokoro(text, dst):
    global _kokoro
    import soundfile as sf
    from kokoro_onnx import Kokoro
    if _kokoro is None:
        d = Path(os.environ.get("KOKORO_DIR", Path.home() / ".local/share/simplicio-tts"))
        _kokoro = Kokoro(str(d / "kokoro-v1.0.onnx"), str(d / "voices-v1.0.bin"))
    audio, sr = _kokoro.create(text, voice=P["voice"], speed=P["speed"], lang=P["lang"])
    sf.write(dst, audio, sr)

def tts_elevenlabs(text, dst):
    key = os.environ.get(P.get("env", "ELEVENLABS_API_KEY"))
    if not key:
        sys.exit("ELEVENLABS_API_KEY not set (provider=elevenlabs). Export it or switch spec.voice.provider to 'kokoro'.")
    if P["voice_id"].startswith("<"):
        sys.exit("Set spec.voice.providers.elevenlabs.voice_id to a real ElevenLabs voice id.")
    body = json.dumps({"text": text, "model_id": P["model"], "voice_settings": {
        "stability": P["stability"], "similarity_boost": P["similarity_boost"], "style": P["style"]}}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{P['voice_id']}?output_format=mp3_44100_128",
        data=body, headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    mp3 = dst.replace(".wav", ".mp3")
    with urllib.request.urlopen(req, timeout=120) as r, open(mp3, "wb") as f:
        f.write(r.read())
    sh("ffmpeg", "-y", "-v", "error", "-i", mp3, dst)

TTS = {"kokoro": tts_kokoro, "elevenlabs": tts_elevenlabs}[prov]
old_lines = json.loads((OUT / "manifest.json").read_text())["lines"] if (OUT / "manifest.json").exists() else {}
manifest = {"provider": prov, "model": P.get("model"), "voice": P.get("voice") or P.get("voice_id"), "lines": {}}
for line in V["lines"]:
    say = line.get("say", line["text"])
    ident = json.dumps([prov, P.get("model"), P.get("voice") or P.get("voice_id"), P.get("speed"), P.get("lang"), say, line["max_s"]], ensure_ascii=False)
    h = hashlib.sha256(ident.encode()).hexdigest()[:12]
    final = OUT / f"{line['id']}-{h}.wav"
    if final.exists() and not force:
        status = "cached"
    else:
        with tempfile.TemporaryDirectory() as td:
            raw, trimmed = f"{td}/raw.wav", f"{td}/trim.wav"
            TTS(say, raw)
            trim = "silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.06,areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.08,areverse"
            sh("ffmpeg", "-y", "-v", "error", "-i", raw, "-af", trim, trimmed)
            d = duration(trimmed)
            tempo = max(1.0, d / line["max_s"])
            if tempo > 1.3:
                sys.exit(f"{line['id']}: {d:.2f}s does not fit {line['max_s']}s even at 1.3x - shorten the text or widen the slot")
            af = (f"atempo={tempo:.4f}," if tempo > 1.0 else "") + "aresample=48000"
            sh("ffmpeg", "-y", "-v", "error", "-i", trimmed, "-af", af, "-ac", "1", "-c:a", "pcm_s16le", "-bitexact", str(final))
        for old in OUT.glob(f"{line['id']}-*.wav"):  # drop stale takes of this line
            if old != final:
                old.unlink()
        status = "rendered"
    manifest["lines"][line["id"]] = {"file": str(final.relative_to(ROOT)), "t": line["t"], "dur_s": round(duration(final), 3), "text": line["text"],
        "say": line.get("say", line["text"]), "atempo": round(tempo, 4) if status == "rendered" else old_lines.get(line["id"], {}).get("atempo")}
    print(f"{line['id']} {status:8s} {manifest['lines'][line['id']]['dur_s']:.2f}s/{line['max_s']}s  {line['text']}")
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
print(f"voice: {prov} / {manifest['voice']} -> {OUT.relative_to(ROOT)}/manifest.json")

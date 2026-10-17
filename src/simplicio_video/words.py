"""Word timings of a processed narration take (for word-by-word kinetic typography synced to the voice).

`simplicio-video voice` stores them in timing.lock.json -> lines.<id>.words = [{"w", "t", "end"}] (seconds from
the start of the processed take). Render only reads the lock, so the video stays deterministic.

Source of truth: faster-whisper word timestamps (python from SIMPLICIO_STT_PY, default the simplicio-tts venv),
mapped onto the contract text (`texto`, not `say`) through a character timeline, so a recognition like
"clinica sorizo" still yields the times of "Clínica Sorriso". Without faster-whisper the words are spread
over the take proportionally to their letters (words_source = "proporcional").
"""
from __future__ import annotations

import json
import os
import subprocess
import unicodedata
from pathlib import Path

from . import paths

STT_CODE = r"""
import json, subprocess, sys
import numpy as np
from faster_whisper import WhisperModel
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", sys.argv[1], "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                     capture_output=True, check=True).stdout
a = np.frombuffer(pcm, dtype=np.float32)
m = WhisperModel(sys.argv[2], device="cpu", compute_type="int8")
segs, _ = m.transcribe(a, language=sys.argv[3], word_timestamps=True, beam_size=5, vad_filter=False, temperature=0.0)
print(json.dumps([{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)} for s in segs for w in (s.words or [])]))
"""
MODEL = "small"


def stt_python() -> str:
    return os.environ.get("SIMPLICIO_STT_PY", paths.tts_python())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if ch.isalnum())


def stt_words(wav: Path, lang: str = "pt") -> list[dict] | None:
    py = stt_python()
    if not Path(py).exists():
        return None
    p = subprocess.run([py, "-c", STT_CODE, str(wav), MODEL, lang], capture_output=True, text=True)
    if p.returncode != 0:
        return None
    try:
        return [w for w in json.loads(p.stdout.strip().splitlines()[-1]) if _norm(w["w"])]
    except (ValueError, IndexError, KeyError):
        return None


def map_words(text: str, dur: float, rec: list[dict] | None) -> list[dict]:
    """Map the display words of `text` onto a timeline: recognised words (char timeline) or proportional."""
    words = text.split()
    lens = [max(1, len(_norm(w))) for w in words]
    total = sum(lens)
    if rec:
        # char timeline of the recognition: each char gets a time inside its word
        times: list[float] = []
        for w in rec:
            n = max(1, len(_norm(w["w"])))
            times += [w["start"] + (w["end"] - w["start"]) * j / n for j in range(n)]
        times.append(rec[-1]["end"])
        at = lambda frac: times[min(len(times) - 1, int(round(frac * (len(times) - 1))))]
    else:
        at = lambda frac: frac * dur
    out, acc = [], 0
    for w, n in zip(words, lens):
        t0, t1 = at(acc / total), at((acc + n) / total)
        out.append({"w": w, "t": round(t0, 3), "end": round(max(t1, t0 + 0.05), 3)})
        acc += n
    return out


def align(wav: Path, text: str, dur: float, lang: str = "pt") -> tuple[list[dict], str]:
    rec = stt_words(wav, lang)
    return map_words(text, dur, rec), (f"faster-whisper {MODEL}" if rec else "proporcional")

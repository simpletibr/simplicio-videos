#!/usr/bin/env python3
"""Transcribe a video/audio file locally with faster-whisper and write a
Scribe-shaped JSON (the format video-use's helpers expect), so the video-use
pipeline (pack_transcripts.py, render.py --build-subtitles) runs without an
ElevenLabs key.

Output shape (subset of ElevenLabs Scribe v1):
  {"language_code": "pt", "text": "...", "words": [
     {"type": "word", "text": "Seu", "start": 0.05, "end": 0.21, "speaker_id": "speaker_0"},
     {"type": "spacing", "text": " ", "start": 0.21, "end": 0.26, "speaker_id": "speaker_0"}, ...]}

Limits vs Scribe: no diarization (single speaker_0), no audio events.
Script alignment (--script spec.json): when the narration text is known (our own
TTS lines in spec.json -> voice.lines[{text, t, max_s}]), the ASR words inside each
line window are replaced by the script words. Same word count -> keep ASR timings
1:1; otherwise the window [first.start, last.end] is split by character length.
Word spans are clamped to [t, t + max_s] (the onset is known). Fixes ASR slips like
"Se o console" / "Whole Effect" and ASR timestamp drift between runs.
Optional --fixes JSON {"wrong": "right"} for single-word corrections without a script.

Usage: transcribe_local.py <media> -o <out.json> [--model small] [--lang pt] [--script spec.json] [--fixes fixes.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def align_to_script(words: list[dict], lines: list[dict]) -> list[dict]:
    """Replace ASR tokens with script tokens line by line (see module doc)."""
    asr = [w for w in words if w["type"] == "word"]
    out_words: list[dict] = []
    used: set[int] = set()
    # each ASR word belongs to the last line that starts before its midpoint
    starts = [float(ln["t"]) - 0.1 for ln in lines]
    owner: dict[int, list[int]] = {}
    for i, w in enumerate(asr):
        mid = (w["start"] + w["end"]) / 2
        k = max((j for j, t0 in enumerate(starts) if t0 <= mid), default=None)
        if k is not None and mid <= float(lines[k]["t"]) + float(lines[k]["max_s"]) + 0.3:
            owner.setdefault(k, []).append(i)
    for k, ln in enumerate(lines):
        idx = owner.get(k, [])
        tokens = ln["text"].split()
        if not idx:
            continue
        used.update(idx)
        group = [asr[i] for i in idx]
        if len(group) == len(tokens):
            spans = [(g["start"], g["end"]) for g in group]
        else:
            a, b = group[0]["start"], group[-1]["end"]
            total = sum(len(t) for t in tokens)
            spans, cur = [], a
            for t in tokens:
                nxt = cur + (b - a) * len(t) / total
                spans.append((round(cur, 3), round(nxt, 3)))
                cur = nxt
        # the line onset is known exactly (voice.py places each line at t), so clamp
        # ASR drift: nothing of this line starts before t or ends after t + max_s
        t_on, t_off = float(ln["t"]), float(ln["t"]) + float(ln["max_s"])
        spans = [(round(min(max(a0, t_on), t_off), 3), round(min(max(a1, t_on), t_off), 3)) for a0, a1 in spans]
        for t, (s0, s1) in zip(tokens, spans):
            out_words.append({"type": "word", "text": t, "start": s0, "end": s1, "speaker_id": "speaker_0"})
    # keep ASR words outside any script window (e.g. off-script speech)
    out_words += [w for i, w in enumerate(asr) if i not in used]
    out_words.sort(key=lambda w: w["start"])
    rebuilt: list[dict] = []
    prev_end = None
    for w in out_words:
        if prev_end is not None and w["start"] > prev_end:
            rebuilt.append({"type": "spacing", "text": " ", "start": prev_end, "end": w["start"], "speaker_id": "speaker_0"})
        rebuilt.append(w)
        prev_end = w["end"]
    return rebuilt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("media", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--lang", default="pt")
    ap.add_argument("--fixes", type=Path, default=None)
    ap.add_argument("--script", type=Path, default=None, help="spec.json with voice.lines")
    args = ap.parse_args()

    from faster_whisper import WhisperModel  # heavy import, keep local
    import soundfile as sf

    fixes = json.loads(args.fixes.read_text()) if args.fixes else {}

    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a16.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(args.media), "-vn",
                        "-ac", "1", "-ar", "16000", str(wav)], check=True)
        audio, _ = sf.read(str(wav), dtype="float32")

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(audio, language=args.lang, beam_size=5,
                                       word_timestamps=True, vad_filter=False,
                                       condition_on_previous_text=False)
    words: list[dict] = []
    prev_end = None
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            core = text.strip(".,!?;:")
            if core in fixes:
                text = text.replace(core, fixes[core])
            start, end = round(float(w.start), 3), round(float(w.end), 3)
            if prev_end is not None and start > prev_end:
                words.append({"type": "spacing", "text": " ", "start": prev_end,
                              "end": start, "speaker_id": "speaker_0"})
            words.append({"type": "word", "text": text, "start": start, "end": end,
                          "speaker_id": "speaker_0"})
            prev_end = end

    if args.script:
        words = align_to_script(words, json.loads(args.script.read_text())["voice"]["lines"])

    out = {
        "language_code": args.lang,
        "text": " ".join(w["text"] for w in words if w["type"] == "word"),
        "words": words,
        "_generator": f"faster-whisper {args.model} (int8, cpu) via tools/video-use/transcribe_local.py",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(1 for w in words if w["type"] == "word")
    print(f"{n} words -> {args.output}")


if __name__ == "__main__":
    main()

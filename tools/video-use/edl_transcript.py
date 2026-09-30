#!/usr/bin/env python3
"""Map source transcripts (edit/transcripts/<source>.json, Scribe shape) onto the
output timeline of an EDL, so timeline_view.py --transcript shows the words that
are actually in the cut (not the source words at the same timestamp).

Usage: edl_transcript.py edit/edl.json -o edit/verify/output.words.json
"""
import argparse
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("edl", type=Path)
ap.add_argument("-o", "--output", type=Path, required=True)
a = ap.parse_args()
edl = json.loads(a.edl.read_text())
tdir = a.edl.parent / "transcripts"
out, offset = [], 0.0
for r in edl["ranges"]:
    s0, s1 = float(r["start"]), float(r["end"])
    src = json.loads((tdir / f"{r['source']}.json").read_text())
    for w in src["words"]:
        if w.get("type") != "word" or w["end"] <= s0 or w["start"] >= s1:
            continue
        out.append({**w, "start": round(max(w["start"], s0) - s0 + offset, 3),
                    "end": round(min(w["end"], s1) - s0 + offset, 3)})
    offset += s1 - s0
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps({"words": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{len(out)} words on output timeline -> {a.output}")

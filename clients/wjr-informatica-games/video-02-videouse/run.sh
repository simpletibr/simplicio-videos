#!/usr/bin/env bash
# video-02 — cutdown 11,5 s do video-01 montado com video-use (ferramenta opcional: tools/video-use/).
# Passos: fonte = variante do video-01 pelo spec (source.variables.json: sem o contador "0N / 03", que não faz
# sentido no corte) → transcrição local (formato Scribe, alinhada ao roteiro, em cache) → pack_transcripts
# → overlay HyperFrames (MOV alpha) → render.py do EDL → master (−14 LUFS / −1,5 dBTP) → SRT lateral
# → timeline_view (autoavaliação) → preview.
set -euo pipefail
cd "$(dirname "$0")"
HERE="$PWD"; V1="$HERE/../video-01"; TOOLS="$HERE/../../../tools/video-use"
export PATH="$HOME/.local/node22/bin:$PATH"
PY="${SIMPLICIO_TTS_PY:-$HOME/.local/share/simplicio-tts/cbvenv/bin/python}"
H="$(bash "$TOOLS/setup.sh" --quiet)"
mkdir -p out
SRC=out/source.mp4

# 1. source: video-01 rendered with the override variables (re-render only if its inputs changed)
if [ ! -f "$SRC" ] || [ "$V1/index.html" -nt "$SRC" ] || [ "$V1/spec.json" -nt "$SRC" ] || [ source.variables.json -nt "$SRC" ]; then
  (cd "$V1" && node scripts/build.mjs >/dev/null)
  node -e 'const f=require("fs");const [a,b,o]=process.argv.slice(1);f.writeFileSync(o,JSON.stringify({...JSON.parse(f.readFileSync(a)),...JSON.parse(f.readFileSync(b))},null,2))' \
    "$V1/build/variables.json" source.variables.json out/source.variables.json
  (cd "$V1" && npx --yes hyperframes@0.8.97 render --quality delivery --strict-variables \
    --variables-file "$HERE/out/source.variables.json" --output "$HERE/out/source.raw.mp4")
  bash "$V1/scripts/master.sh" "$HERE/out/source.raw.mp4" "$HERE/$SRC"
fi

# 2. transcript (cached per source, video-use hard rule 9; audio = video-01 mix, so key it to the script)
TR=edit/transcripts/video-01.json
if [ ! -f "$TR" ] || [ "$V1/spec.json" -nt "$TR" ] || [ -n "${FORCE_TRANSCRIBE:-}" ]; then
  "$PY" "$TOOLS/transcribe_local.py" "$SRC" -o "$TR" --script "$V1/spec.json"
fi
"$PY" "$H/pack_transcripts.py" --edit-dir edit

# 3. overlay (HyperFrames → MOV ProRes 4444 with alpha; WebM loses alpha in render.py)
(cd overlay && npx --yes hyperframes@0.8.97 lint && npx --yes hyperframes@0.8.97 render --format mov --output ../out/overlay.mov .)

# 4. EDL → video (video-use render.py; loudness by our master)
"$PY" "$H/render.py" edit/edl.json -o out/video-02.raw.mp4 --no-loudnorm --no-subtitles --fps 30
bash "$V1/scripts/master.sh" "$HERE/out/video-02.raw.mp4" "$HERE/out/video-02.mp4"

# 5. sidecar captions (video-use build_master_srt; not burned: the composition already has kinetic text)
(cd "$H" && "$PY" -c "import json,sys; from pathlib import Path; import render as r; e=Path(sys.argv[1]); r.build_master_srt(json.loads((e/'edl.json').read_text()), e, Path(sys.argv[2]))" "$HERE/edit" "$HERE/edit/master.srt")

# 6. self-evaluation (video-use timeline_view) at the cut and at both ends
"$PY" "$TOOLS/edl_transcript.py" edit/edl.json -o edit/verify/video-02.words.json
"$PY" "$H/timeline_view.py" out/video-02.mp4 2.5 5.5 -o edit/verify/corte-4s.png --transcript edit/verify/video-02.words.json
"$PY" "$H/timeline_view.py" out/video-02.mp4 0 2 -o edit/verify/inicio.png --transcript edit/verify/video-02.words.json
"$PY" "$H/timeline_view.py" out/video-02.mp4 9.45 11.45 -o edit/verify/fim.png --transcript edit/verify/video-02.words.json  # last frame < duration

# 7. preview + contact sheet + loudness
ffmpeg -v error -y -i out/video-02.mp4 -vf scale=720:1280:flags=lanczos -c:v libx264 -preset slow -crf 25 -maxrate 3M -bufsize 6M -pix_fmt yuv420p -c:a copy -movflags +faststart preview/video-02-preview-720p.mp4
ffmpeg -v error -y -i out/video-02.mp4 -vf "fps=1,scale=270:480,tile=6x2" -frames:v 1 preview/contact-sheet.png
ffmpeg -hide_banner -nostats -i out/video-02.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -A14 Summary

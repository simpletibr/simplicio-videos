#!/usr/bin/env bash
# video-02 — cutdown 11,5 s do video-01 montado com video-use (browser-use/video-use, MIT).
# Pré-requisito: clients/wjr-informatica-games/video-01/out/video-01.mp4 (rode `npm run render` no video-01).
# Passos: clona video-use fixado → transcrição local (faster-whisper → JSON formato Scribe, alinhado ao roteiro)
# → pack_transcripts (takes_packed.md) → overlay HyperFrames (MOV alpha) → render.py do EDL
# → master (−14 LUFS / −1,5 dBTP, mesmo script do video-01) → SRT lateral → timeline_view (autoavaliação) → preview.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/node22/bin:$PATH"
VU_REF=b877063835e6ea6e457124da7e28a0ae26691dc3
VU_DIR="${VIDEO_USE_DIR:-$HOME/.cache/simplicio/video-use}"
PY="${SIMPLICIO_TTS_PY:-$HOME/.local/share/simplicio-tts/cbvenv/bin/python}"
SRC=../video-01/out/video-01.mp4
[ -f "$SRC" ] || { echo "falta $SRC — rode 'npm run render' em ../video-01"; exit 1; }

# 1. video-use, fixed commit (not vendored)
if [ ! -d "$VU_DIR/.git" ]; then git clone -q https://github.com/browser-use/video-use "$VU_DIR"; fi
git -C "$VU_DIR" cat-file -e "$VU_REF^{commit}" 2>/dev/null || git -C "$VU_DIR" fetch -q origin
git -C "$VU_DIR" -c advice.detachedHead=false checkout -q "$VU_REF"
H="$VU_DIR/helpers"

# 2. transcript (local, no ElevenLabs key) + pack
# cached per source (video-use hard rule 9): re-transcribe only if the source or the script changed
TR=edit/transcripts/video-01.json
if [ ! -f "$TR" ] || [ "$SRC" -nt "$TR" ] || [ ../video-01/spec.json -nt "$TR" ] || [ -n "${FORCE_TRANSCRIBE:-}" ]; then
  "$PY" scripts/fw_to_scribe.py "$SRC" -o "$TR" --script ../video-01/spec.json
fi
"$PY" "$H/pack_transcripts.py" --edit-dir edit

# 3. overlay (HyperFrames → MOV ProRes 4444 with alpha; WebM loses alpha in render.py, see README)
mkdir -p out
(cd overlay && npx --yes hyperframes@0.8.97 lint && npx --yes hyperframes@0.8.97 render --format mov --output ../out/overlay.mov .)

# 4. EDL → video (video-use render.py; loudness done by our master)
"$PY" "$H/render.py" edit/edl.json -o out/video-02.raw.mp4 --no-loudnorm --no-subtitles --fps 30
bash ../video-01/scripts/master.sh "$PWD/out/video-02.raw.mp4" "$PWD/out/video-02.mp4"

# 5. sidecar captions (video-use build_master_srt, not burned: the composition already has kinetic text)
(cd "$H" && "$PY" -c "import json,sys; from pathlib import Path; import render as r; e=Path(sys.argv[1]); r.build_master_srt(json.loads((e/'edl.json').read_text()), e, Path(sys.argv[2]))" "$OLDPWD/edit" "$OLDPWD/edit/master.srt")

# 6. self-evaluation (video-use timeline_view) at the cut and at both ends
"$PY" scripts/edl_transcript.py edit/edl.json -o edit/verify/video-02.words.json
"$PY" "$H/timeline_view.py" out/video-02.mp4 2.5 5.5 -o edit/verify/corte-4s.png --transcript edit/verify/video-02.words.json
"$PY" "$H/timeline_view.py" out/video-02.mp4 0 2 -o edit/verify/inicio.png --transcript edit/verify/video-02.words.json
"$PY" "$H/timeline_view.py" out/video-02.mp4 9.45 11.45 -o edit/verify/fim.png --transcript edit/verify/video-02.words.json  # last frame < duration

# 7. preview + contact sheet + loudness
ffmpeg -v error -y -i out/video-02.mp4 -vf scale=720:1280:flags=lanczos -c:v libx264 -preset slow -crf 25 -maxrate 3M -bufsize 6M -pix_fmt yuv420p -c:a copy -movflags +faststart preview/video-02-preview-720p.mp4
ffmpeg -v error -y -i out/video-02.mp4 -vf "fps=1,scale=270:480,tile=6x2" -frames:v 1 preview/contact-sheet.png
ffmpeg -hide_banner -nostats -i out/video-02.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -A14 Summary

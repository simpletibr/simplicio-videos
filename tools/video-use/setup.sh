#!/usr/bin/env bash
# Optional tool: browser-use/video-use (MIT), pinned. Clones outside the repo (never vendored),
# checks the deps our flow needs and prints the helpers dir on the last line of stdout.
# usage: bash tools/video-use/setup.sh [--quiet]
#   env: VIDEO_USE_DIR (default ~/.cache/simplicio/video-use)
#        SIMPLICIO_TTS_PY (python with numpy + Pillow [+ faster-whisper for local transcription])
set -euo pipefail
VU_REPO=https://github.com/browser-use/video-use
VU_REF=b877063835e6ea6e457124da7e28a0ae26691dc3   # 2026-09-23; bump deliberately, re-run the WJR video-02 example
VU_DIR="${VIDEO_USE_DIR:-$HOME/.cache/simplicio/video-use}"
PY="${SIMPLICIO_TTS_PY:-$HOME/.local/share/simplicio-tts/cbvenv/bin/python}"
QUIET="${1:-}"
log() { [ "$QUIET" = "--quiet" ] || echo "$@" >&2; }

command -v ffmpeg >/dev/null || { echo "ffmpeg ausente (docs/setup.md)" >&2; exit 1; }
FILTERS="$(ffmpeg -hide_banner -filters 2>/dev/null || true)"
grep -qE "[[:space:]]subtitles[[:space:]]" <<<"$FILTERS" || log "aviso: ffmpeg sem libass — legendas queimadas não funcionam (SRT lateral ainda funciona)"
[ -x "$PY" ] || { echo "python não encontrado em $PY (defina SIMPLICIO_TTS_PY)" >&2; exit 1; }
"$PY" -c "import numpy, PIL" 2>/dev/null || { echo "faltam numpy/Pillow em $PY" >&2; exit 1; }
"$PY" -c "import faster_whisper" 2>/dev/null || log "aviso: faster-whisper ausente — transcrição local indisponível (use Scribe com ELEVENLABS_API_KEY)"

if [ ! -d "$VU_DIR/.git" ]; then mkdir -p "$(dirname "$VU_DIR")"; git clone -q "$VU_REPO" "$VU_DIR"; fi
git -C "$VU_DIR" cat-file -e "$VU_REF^{commit}" 2>/dev/null || git -C "$VU_DIR" fetch -q origin
git -C "$VU_DIR" -c advice.detachedHead=false checkout -q "$VU_REF"
log "video-use @ ${VU_REF:0:7} em $VU_DIR"
echo "$VU_DIR/helpers"

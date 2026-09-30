#!/usr/bin/env bash
# One-time local TTS setup in ~/.local/share/simplicio-tts (~1.6 GB venv + ~2 GB HF cache on first run).
#   cbvenv/  Chatterbox Multilingual V3 (ResembleAI, MIT) + Kokoro-82M (Apache-2.0, reference voice + fallback)
#            + faster-whisper (MIT, ASR take selection). CPU-only torch.
# Chatterbox weights (ResembleAI/chatterbox on Hugging Face) download on the first `npm run voice`.
set -euo pipefail
D="${KOKORO_DIR:-$HOME/.local/share/simplicio-tts}"
mkdir -p "$D" && cd "$D"
command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 1; }
[[ -x cbvenv/bin/python ]] || uv venv --python 3.13 cbvenv
PY=cbvenv/bin/python
uv pip install --python "$PY" -q "torch==2.6.0" "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cpu
# PyPI chatterbox-tts 0.1.7 lacks the V3 multilingual T3 (t3_model="v3"); pin the git commit we validated.
uv pip install --python "$PY" -q "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox@5de7a54aa4e5e2baadb0182dde554908b48b85c2" \
  "kokoro-onnx==0.6.1" "faster-whisper==1.2.1" soundfile --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
REL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[[ -f kokoro-v1.0.onnx ]] || curl -fL -o kokoro-v1.0.onnx "$REL/kokoro-v1.0.onnx"
[[ -f voices-v1.0.bin  ]] || curl -fL -o voices-v1.0.bin  "$REL/voices-v1.0.bin"
sha256sum -c <<SUM
7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5  kokoro-v1.0.onnx
bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d  voices-v1.0.bin
SUM
"$PY" -c "import torch, chatterbox.mtl_tts, kokoro_onnx, faster_whisper; print('torch', torch.__version__)"
echo "OK: TTS ready in $D (python: $D/$PY) - npm run voice uses it by default (override with SIMPLICIO_TTS_PY)"

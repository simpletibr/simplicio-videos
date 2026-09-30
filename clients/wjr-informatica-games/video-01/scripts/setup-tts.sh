#!/usr/bin/env bash
# One-time local TTS setup (Kokoro-82M, Apache-2.0) in ~/.local/share/simplicio-tts (~360 MB).
set -euo pipefail
D="${KOKORO_DIR:-$HOME/.local/share/simplicio-tts}"
mkdir -p "$D" && cd "$D"
[[ -x venv/bin/python ]] || python3 -m venv venv
venv/bin/pip install -q "kokoro-onnx==0.6.1" soundfile
REL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[[ -f kokoro-v1.0.onnx ]] || curl -fL -o kokoro-v1.0.onnx "$REL/kokoro-v1.0.onnx"
[[ -f voices-v1.0.bin  ]] || curl -fL -o voices-v1.0.bin  "$REL/voices-v1.0.bin"
sha256sum -c <<SUM
7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5  kokoro-v1.0.onnx
bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d  voices-v1.0.bin
SUM
echo "OK: Kokoro ready in $D (python: $D/venv/bin/python)"

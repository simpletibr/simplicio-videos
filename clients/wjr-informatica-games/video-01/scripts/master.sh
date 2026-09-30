#!/usr/bin/env bash
# Final audio master on the rendered MP4: 2-pass loudnorm to the spec target, video stream copied untouched.
# HyperFrames' mixer applies a constant gain to the pre-mixed WAV (measured: -1 dB without video plates,
# -6 dB with the 5 <video> plates present, same waveform otherwise), so we measure the real container.
# usage: scripts/master.sh <in.mp4> <out.mp4>
set -euo pipefail
cd "$(dirname "$0")/.."
IN="$1"; OUT="$2"
I=$(node -p 'require("./spec.json").audio.master.target_lufs'); TP=$(node -p 'require("./spec.json").audio.master.true_peak_db')
TPE="$TP" # loudnorm target; a brickwall limiter at -2.5 dBFS below absorbs AAC overshoot
M=$(ffmpeg -hide_banner -nostats -i "$IN" -af "loudnorm=I=$I:TP=$TPE:LRA=11:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p')
get() { echo "$M" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>console.log(JSON.parse(s)[process.argv[1]]))' "$1"; }
AF="loudnorm=I=$I:TP=$TPE:LRA=11:measured_I=$(get input_i):measured_TP=$(get input_tp):measured_LRA=$(get input_lra):measured_thresh=$(get input_thresh):offset=$(get target_offset):linear=true"
ffmpeg -y -hide_banner -loglevel error -i "$IN" -map 0:v:0 -map 0:a:0 -c:v copy -af "$AF,alimiter=limit=0.75:attack=1:release=40:level=false" -ar 48000 -c:a aac -b:a 192k -movflags +faststart "$OUT"
echo "master: $OUT (input $(get input_i) LUFS -> target $I LUFS, TP $TP dBTP)"

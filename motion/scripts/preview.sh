#!/usr/bin/env bash
# Lint + snapshot motion patterns through the real mount path: a throwaway HyperFrames project gets
# compositions/<id>.html (the block) + an index.html host that mounts it with data-composition-src and the
# block defaults (motion/assets linked in). `hyperframes lint` must pass; one frame at
# pattern.json -> preview_at is saved as patterns/<id>/preview.png (360x640).
# Usage: bash motion/scripts/preview.sh            # all patterns with status "pronto"
#        bash motion/scripts/preview.sh <id> [...] # only these
set -euo pipefail
HF="npx --yes hyperframes@0.8.97"
MOTION="$(cd "$(dirname "$0")/.." && pwd)"
ids=("$@")
if [ ${#ids[@]} -eq 0 ]; then
  mapfile -t ids < <(for d in "$MOTION"/patterns/*/; do [ -f "$d/block.html" ] && basename "$d"; done)
fi
fail=0
for id in "${ids[@]}"; do
  dir="$MOTION/patterns/$id"
  [ -f "$dir/block.html" ] || { echo "skip $id (no block.html)"; continue; }
  at=$(node -e "console.log(require('$dir/pattern.json').preview_at ?? 1)")
  dur=$(node -e "console.log(require('$dir/pattern.json').duration_s)")
  tmp=$(mktemp -d)
  mkdir -p "$tmp/compositions" && cp "$dir/block.html" "$tmp/compositions/$id.html"
  cat > "$tmp/index.html" <<HTML
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>html, body { margin: 0; width: 1080px; height: 1920px; overflow: hidden; background: #080808; }</style>
  </head>
  <body>
    <div id="main" data-composition-id="main" data-start="0" data-duration="$dur" data-width="1080" data-height="1920">
      <div id="block" class="clip" data-composition-id="$id" data-composition-src="compositions/$id.html" data-start="0" data-duration="$dur" data-track-index="0"></div>
    </div>
    <script>
      const tl = gsap.timeline({ paused: true });
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
HTML
  ln -s "$MOTION/assets" "$tmp/assets"
  printf '{"paths":{"blocks":"compositions","components":"compositions/components","assets":"assets"}}\n' > "$tmp/hyperframes.json"
  printf '{"id":"motion-%s","name":"%s"}\n' "$id" "$id" > "$tmp/meta.json"
  if ! (cd "$tmp" && $HF lint >"$tmp/lint.log" 2>&1); then echo "LINT FAIL $id"; cat "$tmp/lint.log"; fail=1; rm -rf "$tmp"; continue; fi
  (cd "$tmp" && $HF snapshot --at "$at" --no-end -o "$tmp/snap" >"$tmp/snap.log" 2>&1) || { echo "SNAPSHOT FAIL $id"; tail -20 "$tmp/snap.log"; fail=1; rm -rf "$tmp"; continue; }
  png=$(ls "$tmp"/snap/*.png | head -1)
  ffmpeg -v error -y -i "$png" -vf scale=360:640:flags=lanczos "$dir/preview.png"
  echo "ok $id @ ${at}s -> patterns/$id/preview.png"
  rm -rf "$tmp"
done
exit $fail

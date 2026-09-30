#!/usr/bin/env bash
# Downloads the PUBLIC images from the client's website into assets/client/ (gitignored)
# so internal drafts look closer to the real brand. These are NOT final assets:
# the client must send the high-res logo and real photos + confirm usage rights.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/client
BASE="https://www.wjrinformaticagames.com.br/assets"
curl -fsSL -o assets/client/logo.png          "$BASE/logo.png"
curl -fsSL -o assets/client/photo-hero.png    "$BASE/hero-consoles.png"
curl -fsSL -o assets/client/photo-bench.png   "$BASE/repair-workbench.png"
echo "OK: assets/client/ populated from the public site (drafts only)."

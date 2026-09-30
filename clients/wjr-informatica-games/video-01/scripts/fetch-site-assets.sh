#!/usr/bin/env bash
# Populates assets/client/ (gitignored) with the client's PUBLIC site images for internal drafts.
# Source of truth is ../coleta/site/imagens/ (snapshot taken 2026-09-30); falls back to downloading
# from the live site only if the snapshot is missing. NOT final assets: the client must send
# the high-res logo and real photos + confirm usage rights (see ../coleta/pendencias.md).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/client
SNAP="../coleta/site/imagens"
BASE="https://www.wjrinformaticagames.com.br/assets"
get() { # $1 = file in snapshot/site, $2 = local name
  if [[ -f "$SNAP/$1" ]]; then cp "$SNAP/$1" "assets/client/$2"; else curl -fsSL -o "assets/client/$2" "$BASE/$1"; fi
}
get logo.png             logo.png
get hero-consoles.png    photo-hero.png
get repair-workbench.png photo-bench.png
echo "OK: assets/client/ populated (from coleta/ snapshot when available; drafts only)."

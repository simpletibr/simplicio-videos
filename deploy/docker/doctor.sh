#!/usr/bin/env sh
# Roda `simplicio-video doctor` dentro da imagem local (issue #43). Passe argumentos extras, ex.: --json.
# Uso: deploy/docker/doctor.sh [--json]
set -eu
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ"
# O exit code é o do doctor: 1 também quando uma trilha externa opcional está quebrada (a linha trilhas; o
# `doctor trilhas` mostra a correção). Não muda aqui: quem chama decide se isso reprova.
exec docker compose run --rm simplicio doctor "$@"

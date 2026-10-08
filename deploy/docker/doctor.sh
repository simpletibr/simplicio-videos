#!/usr/bin/env sh
# Roda `simplicio-video doctor` dentro da imagem local (issue #43). Passe argumentos extras, ex.: --json.
# Uso: deploy/docker/doctor.sh [--json]
set -eu
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ"
exec docker compose run --rm simplicio doctor "$@"

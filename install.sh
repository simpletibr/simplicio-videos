#!/usr/bin/env bash
# install.sh: invólucro fino. O ambiente do checkout é scripts/dev_install.sh (o mesmo nome que o simplicio-loop usa), com as mesmas
# opções: ./install.sh --dry-run | --with EXTRAS | --python 3.12. Para copiar a skill para o agente use `simplicio-video install`.
# No Windows: install.ps1 (e scripts/dev_install.ps1).
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$RAIZ/scripts/dev_install.sh" "$@"

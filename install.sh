#!/usr/bin/env bash
# install.sh: instalação do simplicio-video (issue #43). Um comando, sem privilégio de root, idempotente.
#
# Uso:
#   ./install.sh [--with server,publish] [--python 3.12] [--dry-run]
#
# Faz, nesta ordem: checa Node 22 ou superior, ffmpeg com libass e 5 GB livres (sem instalar nada no sistema);
# garante o uv (se faltar, oferece instalar e só baixa com sua confirmação); cria o .venv com o Python pedido e
# instala os extras pelo comando `simplicio-video install`; constrói web/ se ele existir; roda `simplicio-video
# doctor` e imprime os próximos passos. Rodar de novo não muda nada que já está certo.
#
# --dry-run lista o plano e não cria nem altera nada. --with aceita extras separados por vírgula.

set -euo pipefail

MIN_NODE=22
MIN_DISCO_GB=5
PY="3.12"
EXTRAS=""
DRY=0
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

uso() {
  cat <<'AJUDA'
uso: ./install.sh [--with EXTRAS] [--python VERSÃO] [--dry-run]

  --with EXTRAS     extras do pacote separados por vírgula, ex.: server,publish
  --python VERSÃO   Python do .venv (padrão: 3.12; os extras do CrewAI exigem menos de 3.14)
  --dry-run         lista o plano e sai; não cria nem altera nada
  -h, --help        mostra esta ajuda

exemplos:
  ./install.sh --dry-run
  ./install.sh
  ./install.sh --with server,publish --python 3.12

Requisitos: Node 22 ou superior, ffmpeg com libass, 5 GB livres. Sem sudo.
Depois: .venv/bin/simplicio-video setup  e  .venv/bin/simplicio-video doctor
AJUDA
}

falha() {
  printf 'install.sh: %s\n' "$*" >&2
  exit 1
}

versao_node() {
  if command -v node >/dev/null 2>&1; then
    node --version 2>/dev/null | sed -e 's/^v//' -e 's/\..*//'
  else
    echo 0
  fi
}

ffmpeg_com_libass() {
  local saida
  command -v ffmpeg >/dev/null 2>&1 || return 1
  saida="$(ffmpeg -hide_banner -version 2>/dev/null || true)"
  case "$saida" in
    *--enable-libass*) return 0 ;;
  esac
  return 1
}

disco_livre_gb() {
  local kb
  kb="$(df -Pk "$RAIZ" | awk 'NR==2 {print $4}')"
  echo $((kb / 1024 / 1024))
}

node_ok() {
  local maior
  maior="$(versao_node)"
  [[ "$maior" =~ ^[0-9]+$ ]] && [ "$maior" -ge "$MIN_NODE" ]
}

garante_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  if [ ! -t 0 ]; then
    falha "uv não encontrado. Instale em https://docs.astral.sh/uv/ e rode de novo (ou rode num terminal para instalar daqui)."
  fi
  printf 'uv não encontrado. Instalar agora com o script oficial (https://astral.sh/uv/install.sh)? [s/N] '
  local resp=""
  read -r resp || resp=""
  case "$resp" in
    s|S|sim|SIM|y|Y) ;;
    *) falha "uv é necessário. Instale e rode de novo." ;;
  esac
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || falha "o uv não apareceu no PATH depois da instalação."
}

plano() {
  local sub_extras="sem extras"
  local comando_install="simplicio-video install --python $PY"
  if [ -n "$EXTRAS" ]; then
    sub_extras="extras: $EXTRAS"
    comando_install="$comando_install --with $EXTRAS"
  fi
  local status_node status_ffmpeg status_uv disco
  if node_ok; then status_node="ok (node $(node --version 2>/dev/null || echo ?))"; else status_node="falta: precisa de Node $MIN_NODE ou superior"; fi
  if ffmpeg_com_libass; then status_ffmpeg="ok"; else status_ffmpeg="falta: ffmpeg com libass"; fi
  if command -v uv >/dev/null 2>&1; then status_uv="ok"; else status_uv="ausente: ofereceria instalar com a sua confirmação"; fi
  disco="$(disco_livre_gb)"

  printf 'install.sh --dry-run: nada será criado nem alterado. Plano:\n'
  printf '  1. checar Node %s ou superior ........ %s\n' "$MIN_NODE" "$status_node"
  printf '  2. checar ffmpeg com libass .......... %s\n' "$status_ffmpeg"
  printf '  3. checar %s GB livres (em %s) ..... hoje: %s GB\n' "$MIN_DISCO_GB" "$RAIZ" "$disco"
  printf '  4. garantir o uv ...................... %s\n' "$status_uv"
  printf '  5. criar .venv com Python %s e instalar o pacote (%s): %s\n' "$PY" "$sub_extras" "$comando_install"
  if [ -f "$RAIZ/web/package.json" ]; then
    printf '  6. construir web/ (npm --prefix web ci && npm --prefix web run build)\n'
  else
    printf '  6. web/ ainda não existe: registrar "web/ chega com a #34" e seguir\n'
  fi
  printf '  7. rodar .venv/bin/simplicio-video doctor\n'
  printf '  8. imprimir os próximos passos (setup e doctor)\n'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --with)
      [ $# -ge 2 ] || falha "--with pede os extras, ex.: --with server,publish"
      EXTRAS="$2"
      shift 2
      ;;
    --with=*)
      EXTRAS="${1#--with=}"
      shift
      ;;
    --python)
      [ $# -ge 2 ] || falha "--python pede a versão, ex.: --python 3.12"
      PY="$2"
      shift 2
      ;;
    --python=*)
      PY="${1#--python=}"
      shift
      ;;
    --dry-run)
      DRY=1
      shift
      ;;
    -h|--help)
      uso
      exit 0
      ;;
    *)
      falha "opção desconhecida: $1 (veja ./install.sh --help)"
      ;;
  esac
done

[[ "$PY" =~ ^3\.[0-9]+$ ]] || falha "versão de Python inválida: $PY (use algo como 3.12)"
if [ -n "$EXTRAS" ] && ! [[ "$EXTRAS" =~ ^[a-z][a-z0-9-]*(,[a-z][a-z0-9-]*)*$ ]]; then
  falha "extras inválidos: $EXTRAS (use nomes separados por vírgula, ex.: server,publish)"
fi

if [ "$DRY" -eq 1 ]; then
  plano
  exit 0
fi

cd "$RAIZ"

if ! node_ok; then
  falha "Node $MIN_NODE ou superior é necessário (hoje: $(node --version 2>/dev/null || echo ausente)). Instale com 'nvm install $MIN_NODE' e rode de novo."
fi
if ! ffmpeg_com_libass; then
  falha "ffmpeg com libass é necessário. macOS: 'brew install ffmpeg'; Debian/Ubuntu: 'apt install ffmpeg'. Rode de novo depois."
fi
if [ "$(disco_livre_gb)" -lt "$MIN_DISCO_GB" ]; then
  falha "são necessários ${MIN_DISCO_GB} GB livres em $RAIZ (hoje: $(disco_livre_gb) GB)."
fi

garante_uv

echo "> instalando o ambiente (simplicio-video install --python $PY${EXTRAS:+ --with $EXTRAS})"
install_args=(install --python "$PY")
if [ -n "$EXTRAS" ]; then
  install_args+=(--with "$EXTRAS")
fi
SIMPLICIO_VIDEO_HOME="$RAIZ" PYTHONPATH="$RAIZ/src" python3 -m simplicio_video "${install_args[@]}"

if [ -f web/package.json ]; then
  echo "> construindo web/"
  npm --prefix web ci
  npm --prefix web run build
else
  echo "web/ chega com a #34: nada a construir."
fi

echo "> checando o ambiente (simplicio-video doctor)"
if ! .venv/bin/simplicio-video doctor; then
  echo "install.sh: o doctor apontou falhas acima. Corrija a correção indicada e rode .venv/bin/simplicio-video doctor."
  exit 1
fi

cat <<'PROXIMOS'

instalação pronta. Próximos passos:
  .venv/bin/simplicio-video setup      primeira execução: workspace, tema, idioma (use --yes para os padrões)
  .venv/bin/simplicio-video doctor     checagem do ambiente (--json para máquinas)
  .venv/bin/simplicio-video --help     todos os comandos
Atualizar depois: .venv/bin/simplicio-video update --check
PROXIMOS

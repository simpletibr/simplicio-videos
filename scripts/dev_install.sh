#!/usr/bin/env bash
# dev_install.sh: o ambiente de desenvolvimento do simplicio-video no checkout (Linux e macOS; no Windows, dev_install.ps1).
#
# É o equivalente do `scripts/dev_install.sh` do simplicio-loop (`bash scripts/dev_install.sh`) e o que o `simplicio-video install`
# fazia antes do ADR-0020. Agora o `simplicio-video install` copia a skill para o host do agente (como o `install` do loop) e o
# ambiente do checkout mora aqui. Um comando, sem privilégio de root, idempotente. Não usa o python do sistema: o uv traz o Python.
#
# Uso:
#   bash scripts/dev_install.sh [--with EXTRAS] [--python 3.12] [--dry-run]     (./install.sh faz o mesmo)
#
# Faz, nesta ordem: checa Node 22 ou superior, ffmpeg com libass e 5 GB livres (sem instalar nada no sistema); garante o uv (se
# faltar, oferece instalar e só baixa com sua confirmação); cria o .venv com o Python pedido e instala o pacote editável com os
# extras (uv pip install -e); constrói web/ se ele existir; roda `simplicio-video doctor` e imprime os próximos passos. Rodar de
# novo não muda nada que já está certo. Um .venv com outro Python é um conflito: o script diz o que apagar e não troca sozinho.
#
# --dry-run lista o plano e não cria nem altera nada. --with aceita extras separados por vírgula.

set -euo pipefail

MIN_NODE=22
MIN_DISCO_GB=5
PY="3.12"
EXTRAS=""
DRY=0
UV=""
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) VENV_PY=".venv/Scripts/python.exe"; SV=".venv/Scripts/simplicio-video.exe" ;;
  *) VENV_PY=".venv/bin/python"; SV=".venv/bin/simplicio-video" ;;
esac

uso() {
  cat <<'AJUDA'
uso: bash scripts/dev_install.sh [--with EXTRAS] [--python VERSÃO] [--dry-run]     (./install.sh faz o mesmo)

  --with EXTRAS     extras do pacote separados por vírgula, ex.: local-tts,mcp
  --python VERSÃO   Python do .venv (padrão: 3.12; os extras do CrewAI exigem menos de 3.14)
  --dry-run         lista o plano e sai; não cria nem altera nada
  -h, --help        mostra esta ajuda

exemplos:
  bash scripts/dev_install.sh --dry-run
  bash scripts/dev_install.sh
  bash scripts/dev_install.sh --with local-tts --python 3.12

Requisitos: Node 22 ou superior, ffmpeg com libass, 5 GB livres. Sem sudo. No Windows: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1
Este script cria o ambiente do checkout. Para copiar a skill para o agente (o `install` do simplicio-loop), use depois:
  .venv/bin/simplicio-video install            (o projeto)       .venv/bin/simplicio-video install --global     (o home)
Depois: .venv/bin/simplicio-video setup  e  .venv/bin/simplicio-video doctor
AJUDA
}

falha() {
  printf 'dev_install.sh: %s\n' "$*" >&2
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

# O uv no PATH e, se não estiver, onde o instalador dele costuma deixá-lo (~/.local/bin, ~/.cargo/bin, Homebrew).
acha_uv() {
  local candidato
  if command -v uv >/dev/null 2>&1; then
    UV="$(command -v uv)"
    return 0
  fi
  for candidato in "${HOME:-/nao-existe}/.local/bin/uv" "${HOME:-/nao-existe}/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -x "$candidato" ]; then
      UV="$candidato"
      return 0
    fi
  done
  return 1
}

garante_uv() {
  acha_uv && return 0
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
  acha_uv || falha "o uv não apareceu no PATH depois da instalação."
}

versao_do_venv() {
  [ -f .venv/pyvenv.cfg ] || return 0
  sed -n -E 's/^version(_info)?[[:space:]]*=[[:space:]]*([0-9]+\.[0-9]+).*/\2/p' .venv/pyvenv.cfg | head -n 1
}

alvo_do_pacote() {
  if [ -n "$EXTRAS" ]; then
    printf '.[%s]' "$EXTRAS"
  else
    printf '.'
  fi
}

plano() {
  local sub_extras="sem extras"
  if [ -n "$EXTRAS" ]; then
    sub_extras="extras: $EXTRAS"
  fi
  local status_node status_ffmpeg status_uv disco
  if node_ok; then status_node="ok (node $(node --version 2>/dev/null || echo ?))"; else status_node="falta: precisa de Node $MIN_NODE ou superior"; fi
  if ffmpeg_com_libass; then status_ffmpeg="ok"; else status_ffmpeg="falta: ffmpeg com libass"; fi
  if acha_uv; then status_uv="ok"; else status_uv="ausente: ofereceria instalar com a sua confirmação"; fi
  disco="$(disco_livre_gb)"

  printf 'dev_install.sh --dry-run: nada será criado nem alterado. Plano:\n'
  printf '  1. checar Node %s ou superior ........ %s\n' "$MIN_NODE" "$status_node"
  printf '  2. checar ffmpeg com libass .......... %s\n' "$status_ffmpeg"
  printf '  3. checar %s GB livres (em %s) ..... hoje: %s GB\n' "$MIN_DISCO_GB" "$RAIZ" "$disco"
  printf '  4. garantir o uv ...................... %s\n' "$status_uv"
  printf '  5. criar .venv com Python %s e instalar o pacote (%s):\n' "$PY" "$sub_extras"
  printf '       uv venv --python %s .venv\n' "$PY"
  printf '       uv pip install --python %s -e "%s"\n' "$VENV_PY" "$(alvo_do_pacote)"
  if [ -f "$RAIZ/web/package.json" ]; then
    printf '  6. construir web/ (npm --prefix web ci && npm --prefix web run build)\n'
  else
    printf '  6. web/ ainda não existe: registrar "web/ chega com a #34" e seguir\n'
  fi
  printf '  7. rodar %s doctor\n' "$SV"
  printf '  8. imprimir os próximos passos (install, setup e doctor)\n'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --with)
      [ $# -ge 2 ] || falha "--with pede os extras, ex.: --with local-tts,mcp"
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
      falha "opção desconhecida: $1 (veja bash scripts/dev_install.sh --help)"
      ;;
  esac
done

[[ "$PY" =~ ^3\.[0-9]+$ ]] || falha "versão de Python inválida: $PY (use algo como 3.12)"
if [ -n "$EXTRAS" ] && ! [[ "$EXTRAS" =~ ^[a-z][a-z0-9-]*(,[a-z][a-z0-9-]*)*$ ]]; then
  falha "extras inválidos: $EXTRAS (use nomes separados por vírgula, ex.: local-tts,mcp)"
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

if [ -d .venv ]; then
  atual="$(versao_do_venv)"
  if [ "$atual" != "$PY" ]; then
    falha "conflito: .venv usa Python ${atual:-desconhecido} e o pedido é $PY: apague .venv (rm -rf .venv) e rode de novo."
  fi
else
  echo "> criando o .venv com Python $PY"
  "$UV" venv --python "$PY" .venv
fi

echo "> instalando o pacote em modo editável ($(alvo_do_pacote))"
"$UV" pip install --python "$VENV_PY" -e "$(alvo_do_pacote)"

if [ -f web/package.json ]; then
  echo "> construindo web/"
  npm --prefix web ci
  npm --prefix web run build
else
  echo "web/ chega com a #34: nada a construir."
fi

echo "> checando o ambiente (simplicio-video doctor)"
if ! "$SV" doctor; then
  echo "dev_install.sh: o doctor apontou falhas acima. Corrija a correção indicada e rode $SV doctor."
  exit 1
fi

cat <<PROXIMOS

instalação pronta. Próximos passos:
  $SV install     copia a skill para o agente deste projeto (--global: para o home; --check mostra o plano)
  $SV setup       primeira execução: workspace, tema, idioma (use --yes para os padrões)
  $SV doctor      checagem do ambiente (--json para máquinas)
  $SV --help      todos os comandos
Atualizar depois: git pull e bash scripts/dev_install.sh (o simplicio-video update de um checkout só diz isso)
PROXIMOS

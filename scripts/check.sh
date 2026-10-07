#!/usr/bin/env bash
# Gate local offline do simplicio-videos (make check). Veja docs/host/gate.md.
#
# Roda, nesta ordem: ruff, shellcheck, testes sem os marcados slow/render/integration/ui (sockets
# bloqueados, SIMPLICIO_OFFLINE=1) e, quando há uma issue e uma base, ownership e ordem do TDD.
#
# Variáveis:
#   ISSUE            número da issue (padrão: tirado do nome do branch, ex.: feat/31-gate)
#   BASE             ref de comparação (padrão: origin/main, se existir)
#   PR_LABELS        labels do PR (tdd-exempt dispensa a checagem de TDD)
#   PYTHON           interpretador (padrão: .venv/bin/python, senão python3)
#   CHECK_BUDGET_S   orçamento em segundos; passar disso só avisa (padrão: 60)
#
# Exemplos:
#   make check
#   ISSUE=31 BASE=origin/main scripts/check.sh
#   scripts/check.sh --help
set -euo pipefail

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '2,/^set -e/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
  exit 0
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."
start=$SECONDS

if [ -n "${PYTHON:-}" ]; then
  py="$PYTHON"
elif [ -x .venv/bin/python ]; then
  py=.venv/bin/python
else
  py=python3
fi

step() { printf '\n==> %s\n' "$*"; }
fail() { printf 'check: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- ruff
step "ruff (src/simplicio_video, scripts e os .py alterados)"
"$py" -m ruff check .

base="${BASE:-}"
if [ -z "$base" ] && git rev-parse --verify --quiet 'origin/main^{commit}' >/dev/null; then
  base=origin/main
fi
if [ -n "$base" ] && mb="$(git merge-base "$base" HEAD 2>/dev/null)"; then
  changed=()
  while IFS= read -r -d '' f; do
    [ -f "$f" ] && changed+=("$f")
  done < <(git diff --name-only --diff-filter=d -z "$mb" -- '*.py'; git ls-files --others --exclude-standard -z -- '*.py')
  if [ "${#changed[@]}" -gt 0 ]; then
    "$py" -m ruff check --no-cache "${changed[@]}"
  fi
fi

# ---------------------------------------------------------------- shellcheck
step "shellcheck"
sc="$(command -v shellcheck || true)"
[ -z "$sc" ] && [ -x "$(dirname "$py")/shellcheck" ] && sc="$(dirname "$py")/shellcheck"
if [ -n "$sc" ]; then
  shopt -s nullglob
  "$sc" --shell=bash scripts/*.sh .githooks/*
else
  echo "shellcheck não encontrado (pip install shellcheck-py): pulando"
fi

# ---------------------------------------------------------------- testes
step "testes (sem slow, render, integration, ui; sockets bloqueados)"
SIMPLICIO_OFFLINE=1 "$py" -m pytest -q -p no:cacheprovider -m "not slow and not render and not integration and not ui"

# ---------------------------------------------------------------- ownership e TDD
issue="${ISSUE:-}"
if [ -z "$issue" ]; then
  branch="$(git symbolic-ref --short -q HEAD || true)"
  if [[ "$branch" =~ ^[a-z]+/(issue-)?([0-9]+)([^0-9]|$) ]]; then
    issue="${BASH_REMATCH[2]}"
  fi
fi
if [ -n "$issue" ] && [ -n "$base" ]; then
  step "ownership da issue #$issue contra $base"
  "$py" scripts/check_ownership.py "$issue" --base "$base" || fail "ownership violado"
  step "ordem do TDD contra $base"
  "$py" scripts/check_tdd.py --base "$base" || fail "TDD violado"
else
  step "ownership e TDD"
  echo "pulando: sem issue (ISSUE=N ou branch feat/N-slug) ou sem base (BASE=ref ou origin/main)"
fi

elapsed=$((SECONDS - start))
budget="${CHECK_BUDGET_S:-60}"
printf '\ncheck: ok em %ss\n' "$elapsed"
if [ "$elapsed" -gt "$budget" ]; then
  printf 'check: aviso: passou do orçamento de %ss; mova o teste lento para slow\n' "$budget" >&2
fi

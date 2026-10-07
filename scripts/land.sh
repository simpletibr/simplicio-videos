#!/usr/bin/env bash
# Pouso de um PR sem CI: um de cada vez, com o gate rodando na máquina. Veja docs/host/gate.md.
#
# Uso: scripts/land.sh <pr> [--issue N] [--base REF] [--dry-run]
#
# Passos (o primeiro que falhar para tudo e nada é mesclado):
#   1. pega o lock (um pouso por vez; o lock fica em .git/simplicio-land.lock)
#   2. confere pelo gh: PR aberto, label `reviewed`, issue (--issue ou "Closes #N" no corpo)
#   3. gh pr checkout, git fetch e git rebase na base (padrão origin/main)
#   4. make check, check_ownership.py <issue> e check_tdd.py (label tdd-exempt dispensa o TDD)
#   5. empurra o branch rebaseado (force-with-lease) se mudou e faz o squash-merge apagando o branch,
#      só se o head do PR for o commit que passou no gate
#
# Opções:
#   --issue N    issue dona do PR (padrão: "Closes #N" no corpo do PR)
#   --base REF   base do rebase e das checagens (padrão: origin/main)
#   --dry-run    só mostra o plano; consulta o gh em leitura e não muda nada (nem o lock)
#   -h, --help   esta ajuda
#
# Variáveis: GH (padrão gh), PYTHON (padrão .venv/bin/python, senão python3), LAND_LOCK_DIR.
# Só PRs de branches do próprio repositório (não de forks).
#
# Exemplos:
#   scripts/land.sh 123 --dry-run
#   scripts/land.sh 123
#   scripts/land.sh 123 --issue 31
set -euo pipefail

die() { local code="$1"; shift; printf 'land: %s\n' "$*" >&2; exit "$code"; }

usage() {
  sed -n '2,/^set -e/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

dry=0
issue=""
base="origin/main"
pr=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) dry=1 ;;
    --issue) [ $# -ge 2 ] || die 2 "--issue pede um número"; issue="$2"; shift ;;
    --base) [ $# -ge 2 ] || die 2 "--base pede uma ref"; base="$2"; shift ;;
    -*) die 2 "opção desconhecida: $1 (veja --help)" ;;
    *) [ -z "$pr" ] || die 2 "mais de um PR: $pr e $1"; pr="$1" ;;
  esac
  shift
done
[[ "$pr" =~ ^[0-9]+$ ]] || die 2 "informe o número do PR (veja --help)"
[ -z "$issue" ] || [[ "$issue" =~ ^[0-9]+$ ]] || die 2 "--issue pede um número, recebi: $issue"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gh_bin="${GH:-gh}"
if [ -n "${PYTHON:-}" ]; then
  py="$PYTHON"
elif [ -x "$script_dir/../.venv/bin/python" ]; then
  py="$script_dir/../.venv/bin/python"
else
  py=python3
fi

root="$(git rev-parse --show-toplevel)" || die 2 "rode dentro de um clone do repositório"
cd "$root"
remote="${base%%/*}"
base_branch="${base#*/}"

# ---------------------------------------------------------------- lock
lock_dir="${LAND_LOCK_DIR:-$(cd "$(git rev-parse --git-common-dir)" && pwd)/simplicio-land.lock}"

lock_holder() { cat "$lock_dir/pid" 2>/dev/null || true; }

lock_is_live() {
  local pid
  pid="$(lock_holder)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

release_lock() {
  rm -f "$lock_dir/pid"
  rmdir "$lock_dir" 2>/dev/null || true
}

if [ "$dry" = 1 ]; then
  if [ -d "$lock_dir" ] && lock_is_live; then
    die 1 "lock ocupado: outro pouso em andamento (pid $(lock_holder))"
  fi
else
  if ! mkdir "$lock_dir" 2>/dev/null; then
    if lock_is_live; then
      die 1 "lock ocupado: outro pouso em andamento (pid $(lock_holder))"
    fi
    echo "land: lock velho (processo $(lock_holder) não existe mais), reaproveitando"
    release_lock
    mkdir "$lock_dir" 2>/dev/null || die 1 "lock ocupado: não consegui pegar $lock_dir"
  fi
  echo "$$" > "$lock_dir/pid"
  trap release_lock EXIT
fi

# ---------------------------------------------------------------- o que o gh diz do PR (só leitura)
pr_field() { "$gh_bin" pr view "$pr" --json "$1" --jq "$2"; }

state="$(pr_field state '.state')"
[ "$state" = "OPEN" ] || die 1 "o PR #$pr não está aberto (estado: ${state:-desconhecido})"

labels="$(pr_field labels '.labels[].name')"
grep -qx 'reviewed' <<<"$labels" || die 1 "o PR #$pr não tem o label reviewed: peça a revisão independente antes de pousar"
pr_labels="$(tr '\n' ',' <<<"$labels")"
pr_labels="${pr_labels%,}"

if [ -z "$issue" ]; then
  body="$(pr_field body '.body')"
  if [[ "$body" =~ ([Cc]loses|[Ff]ixes|[Rr]esolves)[[:space:]]+#([0-9]+) ]]; then
    issue="${BASH_REMATCH[2]}"
  else
    die 1 "não achei a issue do PR #$pr: use --issue N ou escreva 'Closes #N' no corpo"
  fi
fi
head_ref="$(pr_field headRefName '.headRefName')"
[ -n "$head_ref" ] || die 1 "o gh não devolveu o branch do PR #$pr"

# ---------------------------------------------------------------- execução (ou plano)
run() {
  if [ "$dry" = 1 ]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi
  printf '+ %s\n' "$*"
  "$@"
}

if [ "$dry" = 0 ]; then
  [ -z "$(git status --porcelain --untracked-files=no)" ] || die 1 "a árvore de trabalho tem alterações; commite ou guarde antes de pousar"
  original="$(git symbolic-ref --short -q HEAD || git rev-parse HEAD)"
  restore() { git checkout -q "$original" 2>/dev/null || true; release_lock; }
  trap restore EXIT
fi

echo "land: PR #$pr (issue #$issue, branch $head_ref) -> $base"

run "$gh_bin" pr checkout "$pr"
run git fetch "$remote" "$base_branch"
if ! run git rebase "$base"; then
  git rebase --abort 2>/dev/null || true
  die 1 "o rebase em $base deu conflito: resolva no branch e rode de novo"
fi
run make check
run "$py" "$script_dir/check_ownership.py" "$issue" --base "$base"
run "$py" "$script_dir/check_tdd.py" --base "$base" --labels "$pr_labels"

if [ "$dry" = 1 ]; then
  echo "[dry-run] git push --force-with-lease $remote HEAD:refs/heads/$head_ref   (só se o rebase mudou o head)"
  echo "[dry-run] $gh_bin pr merge $pr --squash --delete-branch --match-head-commit <head que passou no gate>"
  echo "land: dry-run ok, nada foi alterado"
  exit 0
fi

head_sha="$(git rev-parse HEAD)"
remote_sha="$(git ls-remote "$remote" "refs/heads/$head_ref" | cut -f1)"
if [ "$head_sha" != "$remote_sha" ]; then
  run git push --force-with-lease "$remote" "HEAD:refs/heads/$head_ref"
fi
run "$gh_bin" pr merge "$pr" --squash --delete-branch --match-head-commit "$head_sha"
echo "land: PR #$pr mesclado"

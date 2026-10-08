"""`simplicio-video update [--check] [--force]` (issue #43): atualiza o checkout com segurança.

Sequência: recusa árvore suja (alterações rastreadas não commitadas) -> git fetch -> mostra os commits novos e o
diff do CHANGELOG -> (--check para aqui) -> git pull --ff-only -> simplicio-video install -> build de web/ ->
simplicio-video doctor. Imprime o commit anterior e como voltar. Nunca descarta alterações: --force só deixa seguir
com árvore suja, e o git ainda recusa o pull se ele tocar nesses arquivos. A rede é só o git fetch/pull do remoto.

Exemplos:
  simplicio-video update --check
  simplicio-video update
  simplicio-video update --force
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

from .. import paths

# web/ chega com a #34. Enquanto não existe, o passo só registra isso e segue.
WEB_CMD = ('if [ -f web/package.json ]; then npm --prefix web ci && npm --prefix web run build; '
           'else echo "web/ chega com a #34: nada a construir"; fi')


def _git(checkout, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True)


def run(a) -> int:
    checkout = paths.home()
    if _git(checkout, "rev-parse", "--is-inside-work-tree").returncode != 0:
        print(f"update: {checkout} não é um repositório git. O update usa git pull --ff-only.", file=sys.stderr)
        return 1

    sujo = _git(checkout, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if sujo and not a.force:
        print("update recusado: a árvore está suja (alterações não commitadas em arquivos rastreados):",
              file=sys.stderr)
        print(textwrap.indent(sujo, "  "), file=sys.stderr)
        print("Faça commit ou stash dessas mudanças, ou rode `simplicio-video update --force` "
              "(o git ainda recusa se o pull tocar nesses arquivos).", file=sys.stderr)
        return 1
    if sujo:
        print("aviso: árvore suja; seguindo porque --force foi passado.")

    antigo = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    fetch = _git(checkout, "fetch", "--quiet")
    if fetch.returncode != 0:
        print(f"update: git fetch falhou: {fetch.stderr.strip()}", file=sys.stderr)
        return 1
    if _git(checkout, "rev-parse", "--verify", "-q", "@{u}").returncode != 0:
        print("update: a branch atual não tem upstream. Configure com `git branch --set-upstream-to`.",
              file=sys.stderr)
        return 1
    upstream = _git(checkout, "rev-parse", "--abbrev-ref", "@{u}").stdout.strip()
    novos = _git(checkout, "log", "--oneline", "HEAD..@{u}").stdout.strip()
    if not novos:
        print(f"já está atualizado com {upstream} ({antigo[:7]}): nada a fazer.")
        return 0

    print(f"commits novos em {upstream}:")
    print(textwrap.indent(novos, "  "))
    diff = _git(checkout, "diff", "HEAD", "@{u}", "--", "CHANGELOG.md").stdout.rstrip()
    print("CHANGELOG.md (diff):")
    print(diff or "  (sem mudanças no CHANGELOG neste intervalo)")
    if a.check:
        print("--check: nada foi alterado. Rode `simplicio-video update` para aplicar.")
        return 0

    pull = _git(checkout, "pull", "--ff-only", "--quiet")
    if pull.returncode != 0:
        print("update: o pull não é fast-forward (há commits locais). Nada foi alterado; veja git status e git log.",
              file=sys.stderr)
        print(pull.stderr.strip(), file=sys.stderr)
        return 1
    novo = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    print(f"atualizado: {antigo[:7]} -> {novo[:7]}")
    print("para voltar à versão anterior (rollback):")
    print(f"  git -C {checkout} reset --keep {antigo}")
    print("  depois: simplicio-video install && simplicio-video doctor")

    py = sys.executable
    passos = [
        ("instalar dependências (simplicio-video install)", [py, "-m", "simplicio_video", "install"]),
        ("reconstruir web/", ["sh", "-c", WEB_CMD]),
    ]
    for titulo, argv in passos:
        print(f"> {titulo}")
        r = subprocess.run(argv, cwd=str(checkout))
        if r.returncode != 0:
            print(f"update: falhou em '{titulo}' (rc {r.returncode}). Para voltar: "
                  f"git -C {checkout} reset --keep {antigo}", file=sys.stderr)
            return r.returncode
    print("> checar o ambiente (simplicio-video doctor)")
    return subprocess.run([py, "-m", "simplicio_video", "doctor"], cwd=str(checkout)).returncode

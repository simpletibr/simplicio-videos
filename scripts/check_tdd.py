#!/usr/bin/env python3
"""Confere a ordem do TDD numa branch: os testes vêm primeiro.

Regras (sobre os commits desde o merge-base com --base):
  1. o primeiro commit da branch só toca testes, fixtures e docs (tests/, docs/, pastas fixtures/);
  2. toda mudança em src/ vem com mudança em tests/ na mesma branch.
O label `tdd-exempt` (de --labels ou da variável PR_LABELS) dispensa as duas regras; registre o
motivo no corpo do PR.

Saída: 0 = ok, 1 = regra violada, 2 = erro de uso (base desconhecida).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

EXEMPT = "tdd-exempt"

EPILOG = """\
Exemplos:
  scripts/check_tdd.py                                # contra origin/main
  scripts/check_tdd.py --base 6856ba5                 # contra um commit
  scripts/check_tdd.py --labels reviewed,tdd-exempt   # PR com o label de dispensa
  PR_LABELS="mvp tdd-exempt" scripts/check_tdd.py     # o mesmo, por variável de ambiente
"""


class UsageError(Exception):
    pass


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode:
        raise UsageError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def is_test_side(path: str) -> bool:
    if path.startswith(("tests/", "docs/")):
        return True
    return not path.startswith("src/") and "fixtures" in path.split("/")


def labels_from(arg: str) -> set[str]:
    return {x for x in re.split(r"[,\s]+", f"{arg},{os.environ.get('PR_LABELS', '')}") if x}


def run(base: str, labels: set[str]) -> int:
    if git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}", check=False).strip() == "":
        raise UsageError(f"base desconhecida: {base} (faça `git fetch` ou passe --base)")
    if EXEMPT in labels:
        print(f"ok: label {EXEMPT} presente, checagem de TDD dispensada (o motivo vai no corpo do PR)")
        return 0

    mb = git("merge-base", base, "HEAD").strip()
    commits = git("rev-list", "--reverse", "--no-merges", f"{mb}..HEAD").split()
    if not commits:
        print(f"ok: nenhum commit novo em relação a {base}")
        return 0

    problems: list[str] = []
    first = commits[0]
    first_files = [p for p in git("diff-tree", "--root", "--no-commit-id", "--name-only", "--no-renames", "-r", first).split("\n") if p]
    bad = [p for p in first_files if not is_test_side(p)]
    if bad:
        subject = git("log", "-1", "--format=%s", first).strip()
        problems.append(
            f"FALHA: o primeiro commit da branch ({first[:7]} \"{subject}\") deve tocar só testes, fixtures e docs; "
            f"tocou: {', '.join(bad)}"
        )

    changed = [p for p in git("diff", "--name-only", "--no-renames", mb, "HEAD").split("\n") if p]
    src = [p for p in changed if p.startswith("src/")]
    if src and not any(p.startswith("tests/") for p in changed):
        problems.append(f"FALHA: mudanças em src/ ({', '.join(src)}) sem nenhuma mudança em tests/ na branch")

    if problems:
        print("\n".join(problems))
        print(f"Escreva os testes primeiro e commite-os sozinhos; para PR só de docs ou refactor puro use o label {EXEMPT} com o motivo.")
        return 1
    print(f"ok: {len(commits)} commit(s); o primeiro toca só testes/fixtures/docs e src/ vem com testes")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="check_tdd.py",
        description=__doc__,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--base", default="origin/main", help="ref de comparação (padrão: origin/main)")
    ap.add_argument("--labels", default="", help=f"labels do PR, separados por vírgula ou espaço ({EXEMPT} dispensa a checagem)")
    args = ap.parse_args(argv)
    try:
        return run(args.base, labels_from(args.labels))
    except UsageError as e:
        print(f"check_tdd: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

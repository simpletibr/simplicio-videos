#!/usr/bin/env python3
"""Confere que uma branch só altera os paths que a issue possui (docs/factory/ownership.yaml).

Compara os arquivos alterados desde o merge-base com --base (commits, alterações não commitadas e
arquivos novos fora do .gitignore) com `owns` da issue mais a lista global `generated`.

Sintaxe das entradas de `owns`:
  glob            `**` casa qualquer profundidade, `*` não atravessa `/`.
  path#secao,...  arquivo compartilhado: a issue só pode mexer nas seções listadas. O script libera o
                  arquivo e avisa; o revisor confere a seção.
Uma issue com `status: backlog` ainda não pode começar. O arquivo ownership.yaml em si só pode mudar
na entrada da própria issue.

Saída: 0 = tudo dentro do escopo, 1 = arquivo fora do escopo, 2 = erro de uso (issue inexistente ou
em backlog, base desconhecida, ownership.yaml ilegível).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

import yaml

OWNERSHIP_REL = "docs/factory/ownership.yaml"

EPILOG = """\
Exemplos:
  scripts/check_ownership.py 31                       # contra origin/main
  scripts/check_ownership.py 31 --base 6856ba5        # contra um commit
  scripts/check_ownership.py 32 --base main           # contra um branch local
"""


class UsageError(Exception):
    pass


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode:
        raise UsageError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def split_owns(entry: str) -> tuple[re.Pattern[str], str]:
    path, _, sections = entry.partition("#")
    return glob_to_regex(path), sections


def merge_base(base: str) -> str:
    if git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}", check=False).strip() == "":
        raise UsageError(f"base desconhecida: {base} (faça `git fetch` ou passe --base)")
    return git("merge-base", base, "HEAD").strip()


def changed_files(mb: str) -> list[str]:
    tracked = git("diff", "--name-only", "--no-renames", "-z", mb).split("\0")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return sorted({p for p in tracked + untracked if p})


def load_ownership(text: str, where: str) -> dict:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise UsageError(f"{where}: YAML inválido: {e}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("issues"), dict):
        raise UsageError(f"{where}: faltou a chave `issues`")
    return doc


def without_issue(doc: dict, issue: int) -> dict:
    copy = {k: v for k, v in doc.items() if k != "issues"}
    copy["issues"] = {k: v for k, v in doc["issues"].items() if k != issue}
    return copy


def ownership_edit_is_own_entry(mb: str, issue: int, current: dict) -> bool:
    """True when the only change to ownership.yaml is inside the entry of `issue`."""
    before = git("show", f"{mb}:{OWNERSHIP_REL}", check=False)
    if not before:
        return False
    try:
        return without_issue(load_ownership(before, f"{mb}:{OWNERSHIP_REL}"), issue) == without_issue(current, issue)
    except UsageError:
        return False


def run(issue: int, base: str) -> int:
    root = git("rev-parse", "--show-toplevel").strip()
    try:
        with open(f"{root}/{OWNERSHIP_REL}", encoding="utf-8") as f:
            doc = load_ownership(f.read(), OWNERSHIP_REL)
    except OSError as e:
        raise UsageError(f"não consegui ler {OWNERSHIP_REL}: {e}") from None

    entry = doc["issues"].get(issue)
    if entry is None:
        raise UsageError(f"a issue #{issue} não tem entrada em {OWNERSHIP_REL}")
    if entry.get("status") == "backlog":
        raise UsageError(f"a issue #{issue} está em backlog: elabore (owns e critérios) e vire para `status: ready` antes de começar")
    owns = entry.get("owns")
    if not owns:
        raise UsageError(f"a issue #{issue} não lista `owns` em {OWNERSHIP_REL}")

    owned = [split_owns(e) for e in owns]
    generated = [glob_to_regex(g) for g in doc.get("generated") or []]
    mb = merge_base(base)
    files = changed_files(mb)

    offenders: list[str] = []
    notes: list[str] = []
    for path in files:
        hit = next(((rx, sec) for rx, sec in owned if rx.match(path)), None)
        if hit:
            if hit[1]:
                notes.append(f"  nota: {path} é compartilhado; a issue #{issue} só pode mexer em: {hit[1]} (o revisor confere a seção)")
        elif any(rx.match(path) for rx in generated):
            notes.append(f"  gerado: {path} (não edite à mão; use `make regen`)")
        elif path == OWNERSHIP_REL and ownership_edit_is_own_entry(mb, issue, doc):
            notes.append(f"  nota: {path} mudou só na entrada da issue #{issue}")
        else:
            offenders.append(path)

    if offenders:
        for path in offenders:
            print(f"FALHA: {path} não pertence à issue #{issue}")
        print(f"{len(offenders)} arquivo(s) fora do escopo. Comente na issue dona do arquivo ou abra um PR pequeno de ajuste.")
        return 1
    print(f"ok: {len(files)} arquivo(s) alterado(s) em relação a {base}, todos dentro do escopo da issue #{issue}")
    for line in notes:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="check_ownership.py",
        description=__doc__,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("issue", type=int, help="número da issue (chave em docs/factory/ownership.yaml)")
    ap.add_argument("--base", default="origin/main", help="ref de comparação (padrão: origin/main)")
    args = ap.parse_args(argv)
    try:
        return run(args.issue, args.base)
    except UsageError as e:
        print(f"check_ownership: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

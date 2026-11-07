#!/usr/bin/env python3
"""Generates the `skills/` mirror and the `GENERATED skills` block of .gitignore from the skills that ship in the package (U02).

The source of truth is `src/simplicio_video/data/skills/` (what the wheel carries and what `install` copies into the agent host).
`skills/` at the repo root is only a mirror for the Runtime plugin and for the readers of the repo, so nobody edits it by hand:

  1. `skills/` becomes a byte-for-byte copy of `src/simplicio_video/data/skills/` (files, executable bit; files that left the
     package and folders the package does not carry are removed from the mirror);
  2. the lines between `# BEGIN GENERATED skills` and `# END GENERATED skills` in .gitignore list one
     `.claude/skills/<name>/` per name in `simplicio_video.skill_sync.SKILLS`, the folders `install` creates in the repo root.
     Everything outside the block is left alone, and the block must already exist.

Usage:
  scripts/sync_skills.py            rewrites what is stale (a file that is already right is not touched)
  scripts/sync_skills.py --check    writes nothing; prints the diff and exits 1 when the mirror or the block is stale

`make docs` (so `make check`) runs `--check`; `make regen` runs it without the flag.
Exit codes: 0 = in sync (or regenerated), 1 = `--check` found a difference, 2 = structure error (a skill folder that
`skill_sync.SKILLS` does not list or the other way round, a missing source, a missing or duplicated block in .gitignore).

Examples:
  scripts/sync_skills.py --check
  scripts/sync_skills.py
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "simplicio_video" / "data" / "skills"
MIRROR = ROOT / "skills"
SKILL_SYNC = ROOT / "src" / "simplicio_video" / "skill_sync.py"
GITIGNORE = ROOT / ".gitignore"

BEGIN = "# BEGIN GENERATED skills"
END = "# END GENERATED skills"
GITIGNORE_NOTE = ("# as skills que `simplicio-video install` copia para a raiz deste repositório "
                  "(a fonte é src/simplicio_video/data/skills/; bloco gerado por scripts/sync_skills.py, não edite: `make regen`)")
HOW_TO_FIX = "Rode `make regen` (scripts/sync_skills.py) e inclua o resultado no commit."
DIFF_LINES = 30


class StructureError(Exception):
    pass


def skill_names() -> tuple[str, ...]:
    """`skill_sync.SKILLS`, loaded by path: the module imports nothing from the package, so no install is needed."""
    spec = importlib.util.spec_from_file_location("_simplicio_skill_sync", SKILL_SYNC)
    if spec is None or spec.loader is None:
        raise StructureError(f"não consegui carregar {SKILL_SYNC.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.SKILLS)


def read_tree(base: Path) -> dict[str, tuple]:
    """Relative posix path -> ("file", bytes, executable) or ("link", target). Empty folders do not count (git has none)."""
    found: dict[str, tuple] = {}
    for folder, dirs, files in os.walk(base):
        here = Path(folder)
        for name in list(dirs):
            path = here / name
            if path.is_symlink():
                found[path.relative_to(base).as_posix()] = ("link", os.readlink(path))
                dirs.remove(name)
        for name in files:
            path = here / name
            rel = path.relative_to(base).as_posix()
            if path.is_symlink():
                found[rel] = ("link", os.readlink(path))
            else:
                found[rel] = ("file", path.read_bytes(), bool(path.stat().st_mode & 0o100))
    return found


def check_structure(source: dict[str, tuple], names: tuple[str, ...]) -> None:
    if not source:
        raise StructureError(f"{SOURCE.relative_to(ROOT)} está vazio ou não existe")
    folders = {rel.split("/", 1)[0] for rel in source}
    extra, missing = sorted(folders - set(names)), sorted(set(names) - folders)
    if extra or missing:
        raise StructureError(
            f"skill_sync.SKILLS e {SOURCE.relative_to(ROOT)} divergem: "
            f"no pacote e fora de SKILLS: {extra or '-'}; em SKILLS e fora do pacote: {missing or '-'}")
    loose = sorted(rel for rel in source if "/" not in rel)
    if loose:
        raise StructureError(f"arquivo solto em {SOURCE.relative_to(ROOT)} (só pastas de skill): {loose}")


def gitignore_block(names: tuple[str, ...]) -> list[str]:
    return [BEGIN, GITIGNORE_NOTE, *(f".claude/skills/{name}/" for name in names), END]


def split_gitignore(text: str) -> tuple[list[str], list[str], list[str]]:
    """(lines before the block, the block itself, lines after it); keeps the line endings of everything outside the block."""
    lines = text.splitlines(keepends=True)
    begins = [i for i, line in enumerate(lines) if line.strip() == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise StructureError(
            f".gitignore precisa de um (e só um) bloco '{BEGIN}' ... '{END}' (achei {len(begins)} início(s) e {len(ends)} fim(ns)); "
            "crie as duas linhas no lugar onde o bloco deve ficar e rode `make regen`")
    return lines[:begins[0]], lines[begins[0]:ends[0] + 1], lines[ends[0] + 1:]


def show(old: str, new: str, label: str) -> list[str]:
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"{label} (atual)", f"{label} (esperado)", lineterm="", n=1))
    return [f"      {line}" for line in diff[:DIFF_LINES]] + ([f"      ... (+{len(diff) - DIFF_LINES} linhas)"] if len(diff) > DIFF_LINES else [])


def text_of(entry: tuple) -> str | None:
    if entry[0] != "file":
        return None
    try:
        return entry[1].decode("utf-8")
    except UnicodeDecodeError:
        return None


def mirror_changes(source: dict[str, tuple], mirror: dict[str, tuple]) -> tuple[list[str], list[str]]:
    """(lines to print, paths that differ), where each path is relative to the mirror root."""
    report, paths = [], []
    for rel in sorted(source.keys() | mirror.keys()):
        want, have = source.get(rel), mirror.get(rel)
        if want == have:
            continue
        paths.append(rel)
        shown = f"skills/{rel}"
        if have is None:
            report.append(f"  falta   {shown}")
        elif want is None:
            report.append(f"  sobra   {shown}")
        else:
            report.append(f"  difere  {shown}")
            old, new = text_of(have), text_of(want)
            if old is not None and new is not None:
                report.extend(show(old, new, shown))
    return report, paths


def write_mirror(source: dict[str, tuple], mirror: dict[str, tuple], paths: list[str]) -> None:
    for rel in paths:
        target = MIRROR / rel
        if rel not in source:
            target.unlink()
            continue
        if rel in mirror:
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        entry = source[rel]
        if entry[0] == "link":
            os.symlink(entry[1], target)
        else:
            target.write_bytes(entry[1])
            target.chmod(0o755 if entry[2] else 0o644)
    for folder, _dirs, _files in os.walk(MIRROR, topdown=False):  # folders the package no longer has
        if Path(folder) != MIRROR and not os.listdir(folder):
            os.rmdir(folder)


def run(check: bool) -> int:
    names = skill_names()
    source = read_tree(SOURCE) if SOURCE.is_dir() else {}
    check_structure(source, names)
    mirror = read_tree(MIRROR) if MIRROR.is_dir() else {}
    report, paths = mirror_changes(source, mirror)

    current = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.is_file() else ""
    before, block, after = split_gitignore(current)
    wanted = gitignore_block(names)
    stale_block = [line.rstrip("\r\n") for line in block] != wanted
    if stale_block:
        report.append("  difere  .gitignore (bloco GENERATED skills)")
        report.extend(show("\n".join(line.rstrip("\r\n") for line in block), "\n".join(wanted), ".gitignore"))

    if not report:
        print(f"sync_skills: em dia ({len(names)} skills, {len(source)} arquivos em skills/, bloco do .gitignore)")
        return 0
    if check:
        print("sync_skills: o espelho skills/ ou o bloco do .gitignore está desatualizado (a fonte é src/simplicio_video/data/skills/):",
              file=sys.stderr)
        print("\n".join(report), file=sys.stderr)
        print(HOW_TO_FIX, file=sys.stderr)
        return 1

    write_mirror(source, mirror, paths)
    if stale_block:
        GITIGNORE.write_text("".join(before) + "\n".join(wanted) + "\n" + "".join(after), encoding="utf-8")
    print("sync_skills: regerado:")
    print("\n".join(line for line in report if not line.startswith("      ")))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera o espelho skills/ e o bloco GENERATED skills do .gitignore a partir de src/simplicio_video/data/skills/.",
        epilog="Exemplos:\n  scripts/sync_skills.py --check\n  scripts/sync_skills.py", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="não escreve; imprime o diff e sai 1 se algo estiver desatualizado")
    args = parser.parse_args(argv)
    try:
        return run(args.check)
    except StructureError as e:
        print(f"sync_skills: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

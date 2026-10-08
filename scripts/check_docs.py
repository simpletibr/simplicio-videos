#!/usr/bin/env python3
"""Offline documentation check (#44): relative links, anchors, front matter, orphans, TODO and mermaid fences.

Usage:
  scripts/check_docs.py [--root DIR]

Scope: the .md files tracked by git (`git ls-files`) under DIR. Outside a git checkout (the tests use temporary
trees), every .md under DIR is checked. Nothing here uses the network: http(s) and mailto links are skipped.

Exit status: 1 when there is at least one problem (each printed with its file path), 0 when there is none.

Examples:
  scripts/check_docs.py
  scripts/check_docs.py --root /tmp/arvore-de-teste
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]

# The imported factory spec (docs/factory/, from PR #51, closed without merge) is excluded from every check: it is
# reference text whose links point to pages that do not exist in this repo. tests/test_docs proves the behaviour on
# temporary trees, so this exclusion does not hide any check from the tests.
SPEC_PREFIXES = ("docs/factory/",)
# Pages under these folders need front matter (the folder README.md is an index and is exempt).
FRONT_MATTER_DIRS = ("docs/host/", "docs/plugins/")
FRONT_MATTER_KEYS = ("title", "summary", "commands", "issue", "last_verified")
# Orphan check: only the documentation tree. Folder READMEs are indexes, so they are exempt too.
ORPHAN_DIR = "docs/"
SKIP_DIRS = {".git", ".venv", "node_modules", "build", "__pycache__"}
MERMAID_TYPES = {
    "graph", "flowchart", "sequenceDiagram", "classDiagram", "stateDiagram", "stateDiagram-v2", "erDiagram",
    "journey", "gantt", "pie", "mindmap", "timeline", "gitGraph", "quadrantChart", "requirementDiagram",
    "sankey-beta", "xychart-beta", "block-beta", "C4Context",
}

FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})\s*([^\s`~]*)")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE = re.compile(r"`[^`]*`")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")
TODO = re.compile(r"\bTODO\b")
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def list_pages(root: Path) -> list[str]:
    """Relative posix paths of the Markdown files in scope: git-tracked when DIR is a checkout, else every .md."""
    top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve():
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.md"], capture_output=True, text=True, check=True
        ).stdout
        return sorted(p for p in out.split("\0") if p)
    pages = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root)
        if not SKIP_DIRS & set(rel.parts):
            pages.append(rel.as_posix())
    return sorted(pages)


def parse(text: str):
    """Splits a page into prose lines and fenced blocks. Returns (prose, fences, unclosed) with line numbers."""
    prose: list[tuple[int, str]] = []
    fences: list[tuple[int, str, list[str]]] = []
    current = None  # (marker, info, start line, body)
    for number, line in enumerate(text.splitlines(), 1):
        if current is not None:
            marker, info, start, body = current
            if re.fullmatch(rf"\s*{re.escape(marker[0])}{{{len(marker)},}}\s*", line):
                fences.append((start, info, body))
                current = None
            else:
                body.append(line)
            continue
        opened = FENCE_OPEN.match(line)
        if opened:
            current = (opened.group(1), opened.group(2).lower(), number, [])
            continue
        prose.append((number, line))
    unclosed = (current[2], current[1]) if current is not None else None
    return prose, fences, unclosed


def slugify(title: str) -> str:
    """GitHub-style anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    text = title.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors_of(prose: list[tuple[int, str]]) -> set[str]:
    seen: dict[str, int] = {}
    result: set[str] = set()
    for _, line in prose:
        match = HEADING.match(line)
        if not match:
            continue
        base = slugify(match.group(1))
        count = seen.get(base, 0)
        result.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return result


def check_front_matter(rel: str, text: str) -> list[str]:
    match = FRONT_MATTER.match(text)
    if not match:
        return [f"{rel}: sem front matter (faltam {', '.join(FRONT_MATTER_KEYS)})"]
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return [f"{rel}: front matter com YAML inválido ({exc.__class__.__name__})"]
    if not isinstance(meta, dict):
        return [f"{rel}: front matter não é um mapa"]
    problems = [f"{rel}: front matter sem a chave {key}" for key in FRONT_MATTER_KEYS if key not in meta]
    if "commands" in meta and not isinstance(meta["commands"], (list, str)):
        problems.append(f"{rel}: front matter commands precisa ser lista ou texto")
    return problems


def check_mermaid(rel: str, fences, unclosed) -> list[str]:
    problems = []
    for start, info, body in fences:
        if info != "mermaid":
            continue
        first = next((line.strip() for line in body if line.strip() and not line.strip().startswith("%%")), "")
        kind = first.split()[0] if first else ""
        if kind not in MERMAID_TYPES:
            problems.append(f"{rel}:{start}: bloco mermaid com tipo desconhecido ({kind or 'vazio'})")
    if unclosed is not None:
        start, info = unclosed
        label = "mermaid" if info == "mermaid" else "de código"
        problems.append(f"{rel}:{start}: fence {label} sem fechamento")
    return problems


def check_page(rel: str, text: str, pages: set[str], cache: dict, root: Path):
    """Returns (problems, inbound) for one page. inbound is the set of resolved targets it links to."""
    problems: list[str] = []
    inbound: set[str] = set()
    prose, fences, unclosed = parse(text)
    own_anchors = anchors_of(prose)

    for number, line in prose:
        scan_line = INLINE_CODE.sub("", line)
        for match in LINK.finditer(scan_line):
            target = match.group(1)
            if EXTERNAL.match(target):
                continue
            path, _, anchor = unquote(target).partition("#")
            if path:
                resolved = os.path.normpath(os.path.join(os.path.dirname(rel), path)).replace(os.sep, "/")
                if resolved.startswith(".."):
                    problems.append(f"{rel}:{number}: link quebrado (sai do repositório): {target}")
                    continue
                if not (root / resolved).exists():
                    problems.append(f"{rel}:{number}: link quebrado: {target}")
                    continue
                if resolved in pages and resolved != rel:
                    inbound.add(resolved)
            else:
                resolved = rel
            if anchor and resolved.endswith(".md"):
                if resolved == rel:
                    available = own_anchors
                else:
                    if resolved not in cache:
                        cache[resolved] = anchors_of(parse((root / resolved).read_text(encoding="utf-8"))[0])
                    available = cache[resolved]
                if anchor not in available:
                    problems.append(f"{rel}:{number}: âncora inexistente: {target}")

        if TODO.search(scan_line):
            problems.append(f"{rel}:{number}: marcador TODO em texto (feche ou tire do texto)")

    problems += check_mermaid(rel, fences, unclosed)
    if rel.startswith(FRONT_MATTER_DIRS) and not rel.endswith("/README.md"):
        problems += check_front_matter(rel, text)
    return problems, inbound


def run(root: Path) -> int:
    pages = [p for p in list_pages(root) if not p.startswith(SPEC_PREFIXES)]
    page_set = set(pages)
    problems: list[str] = []
    inbound: dict[str, set[str]] = {p: set() for p in pages}
    cache: dict[str, set[str]] = {}
    for rel in pages:
        text = (root / rel).read_text(encoding="utf-8")
        found, links = check_page(rel, text, page_set, cache, root)
        problems += found
        for target in links:
            inbound[target].add(rel)

    for rel in pages:
        if rel.startswith(ORPHAN_DIR) and rel.rsplit("/", 1)[-1] != "README.md" and not inbound[rel]:
            problems.append(f"{rel}: página órfã (nenhuma outra página aponta para ela)")

    for problem in problems:
        print(problem)
    if problems:
        print(f"docs: {len(problems)} problema(s) em {len(pages)} páginas")
        return 1
    print(f"docs: ok ({len(pages)} páginas)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Checagem offline da documentação: links, âncoras, front matter, órfãos, TODO e mermaid.",
        epilog="exemplos:\n  scripts/check_docs.py\n  scripts/check_docs.py --root /tmp/arvore-de-teste",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="pasta a checar (padrão: a raiz do repositório)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"docs: {root} não é uma pasta", file=sys.stderr)
        return 2
    return run(root)


if __name__ == "__main__":
    sys.exit(main())

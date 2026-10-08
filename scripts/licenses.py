#!/usr/bin/env python3
"""Confere as licenças das dependências instaladas (#46).

Lê as distribuições instaladas com importlib.metadata e classifica a licença de cada uma. A ordem de
leitura é License-Expression (PEP 639), License e, por último, os classifiers `License ::`. A licença
precisa estar na allowlist (MIT, Apache-2.0, BSD, ISC, PSF-2.0, MPL-2.0, no nível de arquivo). Fora da
allowlist, o pacote reprova, a menos que docs/licenses-exceptions.yaml o cubra com justificativa e uso.
Em OR basta uma opção permitida; em AND todas precisam ser permitidas.

O próprio simplicio-video é o produto, não dependência: fica fora do scan, mas aparece na tabela.
Não usa rede nem sockets.

Modos:
  --check            scan e docs/licenses.md atualizado (padrão; `make licenses` roda este e --imports)
  --write            regera docs/licenses.md (`make licenses-write`)
  --imports DIR...   reprova arquivos .py que importam pacote negado ou programa AGPL conhecido (ast)

Saída: 0 = ok, 1 = reprovado, 2 = erro de uso. Veja docs/host/licenses.md.
"""
from __future__ import annotations

import argparse
import ast
import importlib.metadata
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS = ROOT / "docs" / "licenses-exceptions.yaml"
DOC = ROOT / "docs" / "licenses.md"

PRODUCT = "simplicio-video"
ALLOWED = ("MIT", "Apache-2.0", "BSD", "ISC", "PSF-2.0", "MPL-2.0")
EXCEPTION_FIELDS = ("package", "license", "justificativa", "uso")
# Programas AGPL que só existem como processo ou serviço externo (docs/factory/monetization.md).
FORBIDDEN_PROGRAMS = {"openmontage", "voicestudio", "postiz"}

STATUS_LABEL = {"allowed": "permitida", "exception": "exceção", "denied": "negada", "product": "produto"}

# Ordem importa: AGPL e LGPL antes de GPL, MIT-0 antes de MIT.
_RULES = [
    (r"AGPL|AFFERO", "AGPL-3.0"),
    (r"LGPL|LESSER GENERAL", "LGPL"),
    (r"\bGPL|GENERAL PUBLIC", "GPL"),
    (r"MIT-0", "MIT-0"),
    (r"\bMIT\b", "MIT"),
    (r"APACHE", "Apache-2.0"),
    (r"\bBSD", "BSD"),
    (r"\bISC\b", "ISC"),
    (r"\bPSF\b|PYTHON SOFTWARE FOUNDATION", "PSF-2.0"),
    (r"MPL[- ]?2|MOZILLA PUBLIC LICENSE 2", "MPL-2.0"),
    (r"MPL|MOZILLA", "MPL-1.x"),
    (r"PROPRIETARY", "Proprietary"),
]


@dataclass
class Entry:
    name: str
    version: str
    license: str
    status: str  # allowed | exception | denied | product
    used_by: str
    modules: tuple[str, ...] = ()
    reason: str = ""


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _class_of(term: str) -> str:
    up = term.upper()
    for pattern, cls in _RULES:
        if re.search(pattern, up):
            return cls
    return "UNKNOWN"


def evaluate(expr: str) -> bool:
    """True se a expressão de licença pode ser usada sob a allowlist."""
    text = expr.replace("(", " ").replace(")", " ").strip()
    if not text:
        return False
    options = re.split(r"\s+OR\s+", text, flags=re.IGNORECASE)
    return any(
        all(_class_of(term) in ALLOWED for term in re.split(r"\s+AND\s+", opt.strip(), flags=re.IGNORECASE))
        for opt in options
    )


def _field(md, key: str) -> str:
    value = md.get(key)
    return value.strip() if isinstance(value, str) else ""


def declared_license(md) -> str:
    expr = _field(md, "License-Expression")
    if expr:
        return expr
    lic = _field(md, "License")
    if lic and "\n" not in lic and len(lic) <= 80 and lic.upper() != "UNKNOWN":
        return lic
    classifiers = [c.split("::")[-1].strip() for c in (md.get_all("Classifier") or []) if c.startswith("License ::")]
    return " OR ".join(classifiers) if classifiers else "UNKNOWN"


def load_exceptions(path: Path) -> dict[str, dict]:
    """Mapa nome normalizado -> entrada. Arquivo ausente ou vazio vale como lista vazia."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{_rel(path)}: esperava uma lista de entradas {{package, license, justificativa, uso}}")
    out: dict[str, dict] = {}
    for item in data:
        if "package" in item:
            out[norm(str(item["package"]))] = item
    return out


def _modules(dist, name: str) -> tuple[str, ...]:
    top = dist.read_text("top_level.txt") or ""
    mods = tuple(line.strip() for line in top.splitlines() if line.strip())
    return mods or (norm(name).replace("-", "_"),)


def _parents(dists) -> dict[str, list[str]]:
    """Quem exige cada distribuição (Requires-Dist), com [extra] quando a exigência é de um extra."""
    parents: dict[str, list[str]] = {}
    for dist in dists:
        md = dist.metadata
        parent = md.get("Name") or getattr(dist, "name", "") or "?"
        for req in md.get_all("Requires-Dist") or []:
            m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", req)
            if not m:
                continue
            extra = re.search(r"extra\s*==\s*[\"']([^\"']+)", req)
            label = f"{parent}[{extra.group(1)}]" if extra else parent
            parents.setdefault(norm(m.group(1)), []).append(label)
    return parents


def scan(exceptions_path: Path = EXCEPTIONS) -> list[Entry]:
    exc = load_exceptions(exceptions_path)
    dists = list(importlib.metadata.distributions())
    parents = _parents(dists)

    entries: list[Entry] = []
    seen: set[tuple[str, str]] = set()
    product_seen = False
    for dist in dists:
        md = dist.metadata
        name = md.get("Name") or getattr(dist, "name", "") or "?"
        version = str(dist.version)
        lic = declared_license(md)

        if norm(name) == PRODUCT:
            if not product_seen:
                product_seen = True
                entries.append(Entry(name, version, lic, "product", "produto (este repo)"))
            continue
        if (norm(name), version) in seen:
            continue
        seen.add((norm(name), version))

        users = sorted(set(parents.get(norm(name), [])))
        used_by = ", ".join(users) if users else "—"
        status, reason = "allowed", ""
        if lic == "UNKNOWN" or not evaluate(lic):
            status, reason = "denied", f"licença {lic} fora da allowlist"
        item = exc.get(norm(name))
        if item is not None:
            missing = [f for f in EXCEPTION_FIELDS if not str(item.get(f) or "").strip()]
            if missing:
                status, reason = "denied", f"exceção sem {', '.join(missing)}"
            elif str(item["license"]).strip().lower() != lic.strip().lower():
                status = "denied"
                reason = f"exceção declara {item['license']}, metadado declara {lic}"
            else:
                status, reason = "exception", ""
        entries.append(Entry(name, version, lic, status, used_by, _modules(dist, name), reason))

    return sorted(entries, key=lambda e: norm(e.name))


def denied(entries: list[Entry]) -> list[Entry]:
    return [e for e in entries if e.status == "denied"]


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def render_table(entries: list[Entry]) -> str:
    lines = [
        "# Licenças das dependências",
        "",
        "<!-- Gerado por scripts/licenses.py --write (make licenses-write). Não edite à mão. -->",
        "",
        "Scan das distribuições instaladas (`importlib.metadata`). Allowlist: MIT, Apache-2.0, BSD, ISC, "
        "PSF-2.0, MPL-2.0 (nível de arquivo). Exceções com justificativa: `docs/licenses-exceptions.yaml`. "
        "Regras e como atualizar: `docs/host/licenses.md`.",
        "",
        "| Pacote | Versão | Licença | Status | Onde é usado |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(entries, key=lambda e: norm(e.name)):
        lines.append(
            f"| {_cell(e.name)} | {_cell(e.version)} | {_cell(e.license)} | "
            f"{STATUS_LABEL[e.status]} | {_cell(e.used_by)} |"
        )
    lines.append("")
    return "\n".join(lines)


def check_generated(path: Path, entries: list[Entry]) -> list[str]:
    if not path.exists():
        return [f"{_rel(path)}: ausente (rode make licenses-write)"]
    if path.read_text(encoding="utf-8") != render_table(entries):
        return [f"{_rel(path)}: desatualizado (rode make licenses-write)"]
    return []


def imported_roots(path: Path) -> list[tuple[str, int]]:
    """Primeiro nome de cada import estático ou dinâmico (import_module/__import__ com string literal)."""
    found: list[tuple[str, int]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name.split(".")[0], node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.module.split(".")[0], node.lineno))
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"import_module", "__import__"} and isinstance(node.args[0].value, str):
                found.append((node.args[0].value.split(".")[0], node.lineno))
    return found


def import_violations(files: list[Path], entries: list[Entry]) -> list[str]:
    blocked: dict[str, str] = {}
    for e in denied(entries):
        for mod in e.modules:
            blocked.setdefault(mod.lower(), f"{e.name} {e.license}")
    for prog in FORBIDDEN_PROGRAMS:
        blocked.setdefault(prog, "programa AGPL externo")

    out: list[str] = []
    for path in files:
        try:
            roots = imported_roots(path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            out.append(f"{_rel(path)}: não foi possível ler ({exc})")
            continue
        for root, lineno in roots:
            if root.lower() in blocked:
                out.append(
                    f"{_rel(path)}:{lineno} importa {root} ({blocked[root.lower()]}): "
                    "licença incompatível no import graph"
                )
    return out


EPILOG = """\
Exemplos:
  scripts/licenses.py                          # --check: scan e docs/licenses.md em dia (o que o gate roda)
  scripts/licenses.py --write                  # regera docs/licenses.md (também: make licenses-write)
  scripts/licenses.py --imports src scripts    # reprova import de pacote AGPL/GPL negado
  scripts/licenses.py --help
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Confere licenças das dependências instaladas contra a allowlist e as exceções (#46).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="scan e docs/licenses.md atualizado (padrão)")
    mode.add_argument("--write", action="store_true", help="regera docs/licenses.md")
    mode.add_argument("--imports", nargs="+", metavar="DIR", help="reprova .py que importem pacote negado")
    args = parser.parse_args(argv)

    try:
        entries = scan(EXCEPTIONS)
    except ValueError as exc:
        print(f"licenses: {exc}", file=sys.stderr)
        return 2

    bad = denied(entries)
    if args.write:
        DOC.write_text(render_table(entries), encoding="utf-8")
        print(f"licenses: {_rel(DOC)} gerado ({len(entries)} linhas)")
        for e in bad:
            print(f"licenses: negada: {e.name} {e.version}: {e.reason}", file=sys.stderr)
        return 1 if bad else 0

    if args.imports:
        files: list[Path] = []
        for d in args.imports:
            base = Path(d)
            if not base.is_dir():
                print(f"licenses: não é diretório: {d}", file=sys.stderr)
                return 2
            files += sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
        problems = import_violations(files, entries)
        for line in problems:
            print(f"licenses: {line}", file=sys.stderr)
        if problems:
            return 1
        print(f"licenses: imports ok ({len(files)} arquivos .py)")
        return 0

    problems = [f"negada: {e.name} {e.version}: {e.reason}" for e in bad]
    problems += check_generated(DOC, entries)
    counts = {s: sum(1 for e in entries if e.status == s) for s in STATUS_LABEL}
    print(
        f"licenses: {len(entries)} distribuições: {counts['allowed']} permitidas, "
        f"{counts['exception']} exceção, {counts['denied']} negada, {counts['product']} produto"
    )
    print("licenses: web/ ainda não existe (workspace web chega com a #34): nada a escanear")
    for line in problems:
        print(f"licenses: {line}", file=sys.stderr)
    if problems:
        return 1
    print("licenses: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

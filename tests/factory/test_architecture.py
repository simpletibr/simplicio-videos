"""Arquitetura do kernel (#33): simplicio_factory não depende de operação.

Regra: nenhum módulo de `src/simplicio_factory` importa `simplicio_video.publish`, `venda`, `prospect` ou `ugc`.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "src" / "simplicio_factory"
FORBIDDEN = {"publish", "venda", "prospect", "ugc"}


def _absolute_imports(path: Path):
    """Yield (module, imported_names) for every absolute import in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, []
        elif isinstance(node, ast.ImportFrom) and not node.level:
            yield node.module or "", [alias.name for alias in node.names]


def test_kernel_package_exists():
    assert (PKG / "app.py").is_file(), "src/simplicio_factory/app.py ausente: o kernel (#33) ainda não existe"


def _kernel_files() -> list[Path]:
    files = sorted(PKG.rglob("*.py"))
    assert files, "nenhum módulo em src/simplicio_factory: a regra de arquitetura não teria o que verificar"
    return files


def test_kernel_modules_are_scanned():
    _kernel_files()


def test_kernel_does_not_import_operation_modules():
    violations = []
    for path in _kernel_files():
        for module, names in _absolute_imports(path):
            parts = module.split(".")
            if parts[0] == "simplicio_video" and FORBIDDEN & set(parts[1:]):
                violations.append(f"{path.relative_to(ROOT)}: import {module}")
            if module == "simplicio_video" and FORBIDDEN & set(names):
                violations.append(f"{path.relative_to(ROOT)}: from simplicio_video import {', '.join(names)}")
    assert not violations, "simplicio_factory importa operação (publish/venda/prospect/ugc):\n" + "\n".join(violations)

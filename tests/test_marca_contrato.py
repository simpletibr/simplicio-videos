"""Issue #76: the watermark and the end credit are contract input (`marca`), not constants of the render.

Neutral default (no brand in the engine): with no `marca.dagua` the watermark is "Prévia" and there is no end credit
(`marca.credito` = null). The sales modules (prospect/venda) fill the operator's brand from their own configuration.

- (a) a contract without the brand fields gets the neutral default in the composition (spec.json `marca`);
- (b) a contract with `marca.dagua` / `marca.credito` has them reflected in the composition (spec.json `marca`);
- (c) the render code (render.py, compiler.py, engine/) contains no person or company name hardcoded;
- (d) an invalid brand field is rejected by `validate` (the field exists in the schema, the constraint is what fails).

No render, no ffmpeg, no sockets: only the composition spec is built.
"""
import re
from pathlib import Path

import pytest
import yaml

from conftest import ROOT
from simplicio_video import compiler
from simplicio_video import contract as ct

SRC = ROOT / "src" / "simplicio_video"
RENDER_CODE = [SRC / "render.py", SRC / "compiler.py"] + sorted(p for p in (SRC / "engine").rglob("*")
                                                              if p.is_file() and "__pycache__" not in p.parts)
# Hardcoded names that must leave the render code (the operator's brand, the client names, the company).
FORBIDDEN = re.compile(r"wesley|wjr|lothus|simpleti", re.I)

DEFAULT_MARCA = {"dagua": "Prévia", "credito": None}
BRAND = {"dagua": "Marca Teste", "credito": {"texto": "Feito por Teste"}}


def _edit(path, fn):
    d = yaml.safe_load(path.read_text())
    fn(d)
    path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))


def _spec(path):
    return compiler.build_spec(ct.load(path), None)


# (a) no brand in the contract -> neutral default in the composition

def test_contract_without_brand_fields_gets_neutral_default(mini):
    _edit(mini, lambda d: [d["marca"].pop(k, None) for k in ("dagua", "credito")])
    assert _spec(mini).get("marca") == DEFAULT_MARCA


# (b) brand defined in the contract -> reflected in the composition

def test_contract_with_brand_is_reflected_in_composition(mini):
    _edit(mini, lambda d: d["marca"].update(BRAND))
    assert ct.validate(ct.load(mini)).ok
    assert _spec(mini).get("marca") == BRAND


def test_brand_without_credit_keeps_credit_null(mini):
    _edit(mini, lambda d: d["marca"].update(dagua="Marca Teste"))
    assert _spec(mini).get("marca") == {"dagua": "Marca Teste", "credito": None}


# (c) the render code has no hardcoded person or company name

@pytest.mark.parametrize("path", RENDER_CODE, ids=lambda p: str(p.relative_to(SRC)))
def test_render_code_has_no_hardcoded_name(path: Path):
    hits = [i + 1 for i, line in enumerate(path.read_text(encoding="utf8", errors="ignore").splitlines())
            if FORBIDDEN.search(line)]
    assert hits == [], f"{path.relative_to(ROOT)}: nome de pessoa/empresa hardcoded nas linhas {hits}"


# (d) invalid brand field -> validate rejects it, pointing at the field

def test_valid_brand_fields_pass_schema(mini):
    _edit(mini, lambda d: d["marca"].update(BRAND))
    rep = ct.validate(ct.load(mini))
    assert rep.ok, rep.errors


@pytest.mark.parametrize("campo, valor, local", [
    ("dagua", "", "marca/dagua"),
    ("dagua", "x" * 61, "marca/dagua"),
    ("dagua", 123, "marca/dagua"),
    ("credito", "Feito por Teste", "marca/credito"),
    ("credito", {"texto": 42}, "marca/credito/texto"),
])
def test_invalid_brand_field_is_rejected_by_validate(mini, campo, valor, local):
    _edit(mini, lambda d: d["marca"].update({campo: valor}))
    rep = ct.validate(ct.load(mini))
    assert not rep.ok
    assert any(e.startswith(f"schema: {local}:") for e in rep.errors), rep.errors

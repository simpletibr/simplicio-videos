"""Issue #76: the watermark and the end credit are contract input (`marca`), not constants of the render.

Neutral default (no brand in the engine): with no `marca.dagua` the watermark is "Prévia" and there is no end credit
(`marca.credito` = null). The sales modules (prospect/venda) fill the operator's brand from their own configuration.

- (a) a contract without the brand fields gets the neutral default in the composition (spec.json `marca`);
- (b) a contract with `marca.dagua` / `marca.credito` has them reflected in the composition (spec.json `marca`);
- (c) the render code (render.py, compiler.py, engine/) contains no person or company name hardcoded;
- (d) an invalid brand field is rejected by `validate` (the field exists in the schema, the constraint is what fails).

No render, no ffmpeg, no sockets: only the composition spec is built.
"""
import json
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


# (e) the preview reads the brand from spec.json (watermark text and end card); no credit = no end card.
# Covered at the ffmpeg argument level (filter graph + texts) and by a real encode of a 2 s synthetic clip.

def _preview_src(tmp_path):
    import subprocess
    src = tmp_path / "draft.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30", "-f", "lavfi",
                    "-i", "sine=frequency=440", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(src)], check=True)
    return src


def _duration(path):
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def test_preview_filter_without_credit_has_no_end_card(tmp_path):
    from simplicio_video import render
    fc = render.preview_filter(2.0, render.preview_font(ROOT), tmp_path, marca=DEFAULT_MARCA)
    assert "concat=n=1:v=1:a=1" in fc and "concat=n=2" not in fc and "anullsrc" not in fc
    assert (tmp_path / "wm.txt").read_text().count("Prévia") == 3 and not (tmp_path / "end1.txt").exists()


def test_preview_filter_takes_watermark_and_credit_from_marca(tmp_path):
    from simplicio_video import render
    render.preview_filter(2.0, render.preview_font(ROOT), tmp_path, marca=BRAND, chrome={"badge": "PRÉVIA · Teste"})
    assert (tmp_path / "wm.txt").read_text().count("Marca Teste") == 3
    assert (tmp_path / "end1.txt").read_text() == "Feito por Teste"
    assert (tmp_path / "badge.txt").read_text() == "PRÉVIA · Teste"
    assert not (tmp_path / "end2.txt").exists()  # no end_url in the chrome -> no second end-card line


def test_make_preview_encodes_with_and_without_end_card(tmp_path):
    from simplicio_video import render
    src = _preview_src(tmp_path)
    no_card = render.make_preview(src, tmp_path / "sem.mp4", ROOT, log=lambda *a: None, marca=DEFAULT_MARCA)
    with_card = render.make_preview(src, tmp_path / "com.mp4", ROOT, log=lambda *a: None, marca=BRAND)
    assert abs(no_card["duration_s"] - 2.0) < 0.2 and no_card["watermark"] == "Prévia"
    assert abs(with_card["duration_s"] - (2.0 + render.PREVIEW["end_card_s"])) < 0.2 and with_card["watermark"] == "Marca Teste"


def test_render_preview_reads_marca_from_spec_json(mini, tmp_path, monkeypatch):
    from simplicio_video import render
    _edit(mini, lambda d: d["marca"].update(BRAND))
    c = ct.load(mini)
    wd = tmp_path / "wd"
    wd.mkdir()
    (wd / "spec.json").write_text(json.dumps(_spec(mini)), encoding="utf8")
    seen = {}

    def fake_render_local(c, out=None, workdir=None, log=print, **kw):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"draft")
        return {"inputs_sha256": "0" * 64, "files": {}, "timings_s": {}}

    def fake_make_preview(src, dst, home, log=print, marca=None, chrome=None):
        seen.update(marca=marca, chrome=chrome)
        return {"path": str(dst), "sha256": "0" * 64, "duration_s": 1.0, "bytes": 1, "watermark": marca["dagua"], "logo": None}

    monkeypatch.setattr(render, "render_local", fake_render_local)
    monkeypatch.setattr(render, "make_preview", fake_make_preview)
    man = render.render_preview(c, out=tmp_path / "p.mp4", workdir=wd, log=lambda *a: None, chrome={"badge": "B"})
    assert seen == {"marca": BRAND, "chrome": {"badge": "B"}} and man["spec"]["marca"] == BRAND

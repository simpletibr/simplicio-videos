import pytest
import yaml

from conftest import ROOT, WJR, contract_with_coleta_placeholders
from simplicio_video import contract as ct
from simplicio_video.compiler import compile_project, render_template


def test_placeholders(mini):
    c = ct.load(mini)
    out = render_template("{{t:a}}|{{t:b+0.25}}|{{t:b-0.1}}|{{dur:b}}|{{end:a}}|{{duracao}}|{{cuts}}|{{width}}x{{height}}@{{fps}}|{{vars:<x>}}", c, {})
    assert out == "0|0.75|0.4|0.5|0.5|1|[0, 0.5, 1]|180x320@30|{{vars:<x>}}"


def _client_strings_replaced_by_the_template():
    """(real client string, generic placeholder) pairs: the packaged template (it ships to PyPI) carries placeholders,
    while the legacy video-01 project in clients/ keeps the real WJR data. The values come from the WJR contract."""
    d = yaml.safe_load(WJR.read_text(encoding="utf8"))
    cta = next(s["textos"] for s in d["cenas"] if "whatsapp" in s.get("textos", {}))
    return [
        (cta["whatsapp"], "(00) 00000-0000"),
        (cta["address"], "Rua Exemplo, 123 · Cidade"),
        (cta["instagram"], "@suaempresa"),
        ('alt="WJR Infogames"', 'alt="Logo"'),
        ("Assistência técnica em Guarulhos", "Assistência técnica na sua cidade"),
        ('WJR Infogames — video-01 "showreel"', 'Assistência técnica / games — "showreel"'),
    ]


@pytest.mark.skipif(not WJR.exists(), reason="clients/ fica fora do git: sem o contrato WJR não há o que comparar")
def test_wjr_compiles_to_the_legacy_composition(tmp_path):
    """The contract port must produce the hand-authored video-01 index.html byte for byte, except for the client
    strings that the template replaced with generic placeholders (each one must still exist in the legacy file)."""
    c = ct.load(contract_with_coleta_placeholders(WJR, tmp_path / "client"))
    compile_project(c, tmp_path / "wd", ct.load_lock(c))
    legacy = (ROOT / "clients/wjr-informatica-games/video-01/index.html").read_bytes().decode("utf8")
    for real, generic in _client_strings_replaced_by_the_template():
        assert real in legacy, f"the legacy video-01 no longer has {real!r}: update the pairs"
        legacy = legacy.replace(real, generic)
    assert (tmp_path / "wd" / "index.html").read_bytes().decode("utf8") == legacy


def test_beat_and_words_placeholders(mini):
    c = ct.load(mini)
    lock = {"lines": {"vo1": {"words": [{"w": "tom", "t": 0.0, "end": 0.1}, {"w": "de", "t": 0.1, "end": 0.15},
                                         {"w": "teste", "t": 0.15, "end": 0.3}]}}}
    out = render_template("{{bpm}}|{{beat}}|{{words:vo1}}|{{words:vo1+0.1}}", c, {}, lock)
    assert out == "120|0.5|0.05|0.15|0.2|0.15|0.25|0.3"


def test_param_placeholders_resolve_with_numeric_cast(mini):
    from simplicio_video.compiler import resolve_params
    c = ct.load(mini)
    lock = {"lines": {"vo1": {"words": [{"w": "tom", "t": 0.0, "end": 0.1}, {"w": "de", "t": 0.2, "end": 0.3}, {"w": "teste", "t": 0.3, "end": 0.4}]}}}
    res = resolve_params({"k": {"bpm": "{{bpm}}", "d": "{{dur:b}}", "times": "{{words:vo1}}", "txt": "fica {{bpm}}", "n": 3}}, c, lock)
    assert res["k"] == {"bpm": 120, "d": 0.5, "times": "0.05|0.25|0.35", "txt": "fica 120", "n": 3}

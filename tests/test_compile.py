from conftest import ROOT, WJR
from simplicio_video import contract as ct
from simplicio_video.compiler import compile_project, render_template


def test_placeholders(mini):
    c = ct.load(mini)
    out = render_template("{{t:a}}|{{t:b+0.25}}|{{t:b-0.1}}|{{dur:b}}|{{end:a}}|{{duracao}}|{{cuts}}|{{width}}x{{height}}@{{fps}}|{{vars:<x>}}", c, {})
    assert out == "0|0.75|0.4|0.5|0.5|1|[0, 0.5, 1]|180x320@30|{{vars:<x>}}"


def test_wjr_compiles_to_the_legacy_composition(tmp_path):
    """The contract port must produce byte-identical index.html to the hand-authored video-01."""
    c = ct.load(WJR)
    compile_project(c, tmp_path / "wd", ct.load_lock(c))
    legacy = (ROOT / "clients/wjr-informatica-games/video-01/index.html").read_bytes()
    assert (tmp_path / "wd" / "index.html").read_bytes() == legacy


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

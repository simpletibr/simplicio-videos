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

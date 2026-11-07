"""T6 review fixes: argparse abbreviations of --output, a closed filter set for grade over MCP, stale paths."""
import json
from pathlib import Path

import pytest

from simplicio_video import edit, mcp_server
from helpers import ROOT

PKG_TOOL = ROOT / "src" / "simplicio_video" / "data" / "tools" / "video-use"


@pytest.fixture
def calls(monkeypatch):
    got = []
    monkeypatch.setattr(edit, "helpers_dir", lambda: Path("/h"))
    monkeypatch.setattr(edit, "_run", lambda cmd: got.append(cmd) or 0)
    return got


# --- argparse prefix abbreviations of --output; the last value wins, so every value is checked ---

@pytest.mark.parametrize("args", [
    "render edl.json -o /abs/x.mp4 --ou rel.mp4",
    "render edl.json -o /abs/x.mp4 --outpu=rel.mp4",
    "transcribe f.mp4 -o /abs/x.json --o rel.json",
    "grade f.mp4 -o /abs/g.mp4 --outp rel.mp4",
    "grade f.mp4 -o /abs/g.mp4 -o=rel.mp4",
    "verify v.mp4 1 2 -o /abs/p.png --output rel.png",
])
def test_mcp_edit_checks_every_output_value_including_abbreviations(args, monkeypatch):
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, **k: pytest.fail("must refuse before running"))
    r = mcp_server.video_edit(args)
    assert r["ok"] is False and "absolut" in r["error"]


def test_mcp_edit_accepts_glued_and_abbreviated_absolute_outputs(monkeypatch):
    got = []
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, **k: got.append(argv) or {"ok": True, "rc": 0})
    assert mcp_server.video_edit("grade f.mp4 -o/abs/g.mp4")["ok"]
    assert mcp_server.video_edit("grade f.mp4 --outp /abs/g.mp4")["ok"]
    assert mcp_server.video_edit("grade f.mp4 --o=/abs/g.mp4")["ok"]
    assert len(got) == 3


@pytest.mark.parametrize("forma", [["--o", "g.mp4"], ["--ou", "g.mp4"], ["--outp", "g.mp4"], ["--outpu=g.mp4"], ["-o=g.mp4"]])
def test_grade_in_the_terminal_accepts_every_output_spelling(forma, calls):
    assert edit.run_edit(["grade", "in.mp4", *forma]) == 0
    assert calls


def test_output_values_is_the_single_parser():
    assert edit._output_values(["a", "-o", "/x", "--ou", "y", "--outpu=z", "-ow", "-o=q"]) == ["/x", "y", "z", "w", "q"]
    assert edit._output_values(["a", "--", "-o", "x"]) == []
    assert edit._output_values(["a", "--preset", "p"]) == []
    assert edit._tem_saida(["x.mp4", "--outp", "y"]) is True and edit._tem_saida(["x.mp4"]) is False


# --- MCP: grade --filter is a closed set of colour filters ---

@pytest.mark.parametrize("filt", [
    "eq=contrast=1.05:saturation=0.95",
    "curves=master=0/0 0.25/0.23 0.75/0.77 1/1,eq=contrast=1.1",  # sem aspas: o ffmpeg aceita o espaço, e aspas agora são recusadas
    "colorbalance=rs=0.02:bs=-0.03;hue=s=0.9",
    "lutrgb=r=val*1.02,vibrance=intensity=0.2",
])
def test_mcp_grade_filter_allows_colour_filters(filt, monkeypatch):
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, **k: {"ok": True, "rc": 0})
    assert mcp_server.video_edit(["grade", "/a.mp4", "-o", "/b.mp4", "--filter", filt])["ok"]


@pytest.mark.parametrize("filt", [
    "movie=/etc/passwd",
    "eq=contrast=1.1,amovie=x.wav",
    "sendcmd=f=cmds.txt",
    "zmq",
    "curves=psfile=/etc/passwd",
    "curves=preset=/tmp/x",
    "lut3d=file=x.cube",
    "eq=contrast=1.1,subtitles=/etc/passwd",
    "hue=filename=x",
    "lutrgb=stats_file=/tmp/x",
    "eq=result=/tmp/x",
    # ffmpeg drops the backslash and the quotes before it matches the option names: psfile in all three
    r"curves=ps\file=/etc/hostname",
    "curves='psfile'=/etc/hostname",
    'curves="psfile"=/etc/hostname',
])
@pytest.mark.parametrize("forma", ["--filter", "--filt", "--filter="])
def test_mcp_grade_filter_refuses_anything_else_and_names_the_terminal(filt, forma, monkeypatch):
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, **k: pytest.fail("must refuse before running"))
    tail = [forma + filt] if forma.endswith("=") else [forma, filt]
    r = mcp_server.video_edit(["grade", "/a.mp4", "-o", "/b.mp4", *tail])
    assert r["ok"] is False and "terminal" in r["error"]


def test_terminal_grade_filter_is_unrestricted(calls):
    assert edit.run_edit(["grade", "in.mp4", "-o", "o.mp4", "--filter", "lut3d=file=x.cube"]) == 0


# --- stale paths ---

def test_no_stale_tools_video_use_path():
    pj = (ROOT / "plugin.json").read_text(encoding="utf8")
    assert "tools/video-use" not in pj.replace("data/tools/video-use", "")
    d = next(c for c in json.loads(pj)["commands"] if c.get("verb") == "video.edit")["description"]
    assert "grade" in d and "absolute" in d and "terminal" in d
    assert "tools/video-use" not in (PKG_TOOL / "README.md").read_text(encoding="utf8").splitlines()[0]
    assert "(tools/video-use)" not in (ROOT / "docs" / "receita-video-cliente.md").read_text(encoding="utf8")

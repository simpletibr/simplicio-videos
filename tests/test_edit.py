"""edit track (T6): video-use helpers ship inside the package, `edit grade`, and the MCP rules for video.edit."""
from pathlib import Path

import pytest

from simplicio_video import edit, mcp_server, paths

ROOT = Path(__file__).resolve().parents[1]
PKG_TOOL = ROOT / "src" / "simplicio_video" / "data" / "tools" / "video-use"


# --- the tool files live in package data (so a wheel ships them) ---

def test_video_use_files_are_package_data():
    for n in ("setup.sh", "transcribe_local.py", "edl_transcript.py", "README.md"):
        assert (PKG_TOOL / n).is_file(), n
    assert not (ROOT / "tools" / "video-use" / "setup.sh").exists()


def test_tool_dir_is_the_package_data_even_when_home_is_somewhere_else(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(tmp_path))  # a "home" with no tools/ at all
    assert edit.tool_dir() == paths.DATA_DIR / "tools" / "video-use"
    assert (edit.tool_dir() / "setup.sh").is_file()


def test_helpers_dir_runs_the_packaged_setup(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(tmp_path))
    seen = []

    class R:
        returncode, stdout, stderr = 0, "log\n/x/helpers\n", ""
    monkeypatch.setattr(edit.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or R())
    assert edit.helpers_dir() == Path("/x/helpers")
    assert seen[0][1] == str(PKG_TOOL / "setup.sh")


def test_pyproject_packages_the_tool_files():
    t = (ROOT / "pyproject.toml").read_text(encoding="utf8")
    assert '"data/**/*"' in t  # covers data/tools/video-use/*


# --- edit grade ---

@pytest.fixture
def calls(monkeypatch):
    got = []
    monkeypatch.setattr(edit, "helpers_dir", lambda: Path("/h"))
    monkeypatch.setattr(edit, "_run", lambda cmd: got.append(cmd) or 0)
    return got


def test_grade_auto_is_the_default(calls):
    assert edit.run_edit(["grade", "in.mp4", "-o", "out.mp4"]) == 0
    assert calls[0][1:] == ["/h/grade.py", "in.mp4", "-o", "out.mp4"]


def test_grade_preset_filter_and_analyze_pass_through(calls):
    assert edit.run_edit(["grade", "in.mp4", "-o", "o.mp4", "--preset", "warm_cinematic"]) == 0
    assert "--preset" in calls[-1] and "warm_cinematic" in calls[-1]
    assert edit.run_edit(["grade", "--analyze", "in.mp4"]) == 0
    assert calls[-1][1:] == ["/h/grade.py", "--analyze", "in.mp4"]
    assert edit.run_edit(["grade", "--list-presets"]) == 0
    assert edit.run_edit(["grade", "in.mp4", "--output=o.mp4", "--filter", "eq=contrast=1.05"]) == 0


def test_grade_needs_an_output_unless_it_only_reads(calls):
    with pytest.raises(edit.EditError, match="-o"):
        edit.run_edit(["grade", "in.mp4"])
    with pytest.raises(edit.EditError, match="FONTE"):
        edit.run_edit(["grade", "-o", "o.mp4"])
    assert not calls


def test_grade_help_has_presets_analyze_and_examples_without_setup(capsys, monkeypatch):
    monkeypatch.setattr(edit, "helpers_dir", lambda: (_ for _ in ()).throw(AssertionError("setup must not run for --help")))
    assert edit.run_edit(["grade", "--help"]) == 0
    out = capsys.readouterr().out
    for s in ("auto", "warm_cinematic", "neutral_punch", "subtle", "--analyze", "--filter", "simplicio-video edit grade"):
        assert s in out, s


def test_edit_help_grade_is_reachable_through_the_cli(capsys):
    from conftest import run_cli
    r = run_cli("edit", "help", "grade")
    assert r.returncode == 0 and "--analyze" in r.stdout and "simplicio-video edit grade" in r.stdout, r.stderr


def test_edit_help_lists_grade(capsys):
    edit.run_edit(["--help"])
    assert "grade" in capsys.readouterr().out


def test_edit_transcribe_batch_in_the_terminal_passes_through(calls):
    assert edit.run_edit(["transcribe-batch", "/videos"]) == 0
    assert calls[0][1:] == ["/h/transcribe_batch.py", "/videos"]


# --- MCP video.edit ---

@pytest.mark.parametrize("args", [
    "transcribe a.mp4 -o rel.json",
    "render edl.json -o out.mp4",
    "verify v.mp4 1 2 --out p.png",
    "grade a.mp4 --output=out.mp4",
    "grade a.mp4 -oout.mp4",
])
def test_mcp_edit_refuses_relative_outputs(args, monkeypatch):
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, **k: pytest.fail("must refuse before running"))
    r = mcp_server.video_edit(args)
    assert r["ok"] is False and "absolut" in r["error"]


@pytest.mark.parametrize("args", ["transcribe a.mp4", "render edl.json", "grade a.mp4"])
def test_mcp_edit_requires_an_output(args, monkeypatch):
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, **k: pytest.fail("must refuse before running"))
    r = mcp_server.video_edit(args)
    assert r["ok"] is False and "-o" in r["error"]


@pytest.mark.parametrize("name", ["transcribe-batch", "transcribe_batch"])
def test_mcp_edit_batch_transcription_is_terminal_only(name, monkeypatch):
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, **k: pytest.fail("must refuse before running"))
    r = mcp_server.video_edit(f"{name} /videos")
    assert r["ok"] is False and "terminal" in r["error"] and "ElevenLabs" in r["error"]


def test_mcp_edit_absolute_outputs_and_read_only_forms_run(monkeypatch):
    got = []
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, **k: got.append(argv) or {"ok": True, "rc": 0})
    assert mcp_server.video_edit("render /w/edl.json -o /w/out.mp4")["ok"]
    assert mcp_server.video_edit("grade --analyze /w/a.mp4")["ok"]
    assert mcp_server.video_edit("grade --list-presets")["ok"]
    assert mcp_server.video_edit("setup")["ok"] and mcp_server.video_edit("pack /w/edit")["ok"]
    assert mcp_server.video_edit("grade --help")["ok"]
    assert len(got) == 6


def test_mcp_edit_description_states_the_rules():
    d = mcp_server.DESC_video_edit
    assert "grade" in d and "absolute" in d and "terminal" in d and "transcribe-batch" in d

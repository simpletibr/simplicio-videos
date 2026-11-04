"""rea-video track: a pinned checkout installed in a venv of its own, and every command passed through to it.
Nothing here touches the network: clone, pip and the upstream command are stubbed."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

from simplicio_video import cli, mcp_server, rea_video, tools

SHA40 = re.compile(r"^[0-9a-f]{40}$")
REF = "36e02ddf1ffc287bd760d816c132027598f2e4c0"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "dados"))
    for var in ("REA_VIDEO_DIR", "REA_VIDEO_DATA_DIR", "REA_VIDEO_HOME", "REA_VIDEO_MODELS", "REA_VLM_API_KEY",
                "VIDEO_ANALYSIS_API_KEY", "GEMINI3_API_KEY", "SIMPLICIO_OFFLINE", "SIMPLICIO_REA_VIDEO_REF"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    d = tmp_path / "rea-video"
    (d / ".git").mkdir(parents=True)  # a real checkout has .git: the commit check reads it
    (d / "rea_video").mkdir(parents=True)
    (d / "rea_video" / "cli.py").write_text("def main():\n    return 0\n", encoding="utf8")
    monkeypatch.setenv("REA_VIDEO_DIR", str(d))
    return d


def _data(tmp_path) -> Path:
    return (tmp_path / "dados" / "rea-video-data").resolve()


def _rea_video_bin(tmp_path) -> Path:
    """The upstream command inside the venv of the track (a stand-in file: the subprocess is stubbed)."""
    exe = _data(tmp_path) / "venv" / "bin" / "rea-video"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("#!/bin/sh\n", encoding="utf8")
    return exe


class _Calls:
    """Stands in for subprocess.call: records argv and kwargs, returns `rc`."""

    def __init__(self, rc: int = 0):
        self.rc = rc
        self.calls: list[tuple[list, dict]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return self.rc


def _no_call(*args, **kwargs):
    pytest.fail("não devia chamar o rea-video nem o pip neste caso")


# ---- registry -----------------------------------------------------------------------------------------------------

def test_rea_video_is_pinned_to_a_full_commit_with_its_license_caveat():
    t = tools.get("rea_video")
    assert t.kind == "git" and t.source == "https://github.com/JuneYaooo/rea-video"  # upstream: the pin exists there too
    assert t.ref == REF and SHA40.match(t.ref)
    assert t.license.startswith("MIT") and "LICENSE" in t.license  # declared in pyproject.toml, no LICENSE file at the pin
    assert t.marker == "rea_video/cli.py"
    assert tools.COMMANDS["rea_video"] == "rea-video"


def test_listing_shows_the_track_and_its_command():
    rows = {r["name"]: r for r in tools.listing()}
    assert rows["rea_video"]["command"] == "simplicio-video rea-video"
    assert rows["rea_video"]["version"] == REF
    assert rows["rea_video"]["installed"] is False


# ---- where / status -----------------------------------------------------------------------------------------------

def test_where_prints_the_checkout(checkout, capsys):
    assert cli.main(["rea-video", "where"]) == 0
    assert capsys.readouterr().out.strip() == str(checkout.resolve())


def test_where_without_a_checkout_says_how_to_clone(capsys):
    assert cli.main(["rea-video", "where"]) == 1
    assert "rea-video clone" in capsys.readouterr().err


def test_status_without_an_install_says_what_is_missing(capsys):
    assert cli.main(["rea-video", "status"]) == 0
    out = capsys.readouterr().out
    assert f"commit fixado: {REF}" in out
    assert "não encontrado" in out and "não existe" in out
    assert "ocr: sem venv" in out
    assert "REA_VLM_API_KEY: não definida" in out


def test_status_compares_the_checkout_commit_with_the_pin(checkout, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "a" * 40)
    assert cli.main(["rea-video", "status"]) == 0
    out = capsys.readouterr().out
    assert str(checkout.resolve()) in out and "diferente do fixado" in out


def test_status_reports_the_vlm_key_as_set_without_printing_it(monkeypatch, capsys):
    monkeypatch.setenv("REA_VLM_API_KEY", "segredo-de-teste-123")
    assert cli.main(["rea-video", "status"]) == 0
    out = capsys.readouterr().out
    assert "REA_VLM_API_KEY: definida" in out
    assert "segredo-de-teste-123" not in out


# ---- clone --------------------------------------------------------------------------------------------------------

def test_clone_installs_the_pin_in_the_default_folder(monkeypatch):
    seen = {}

    def fake_install(name):
        seen["name"] = name
        return str(tools.checkout_dir(tools.get("rea_video")))

    monkeypatch.setattr(tools, "install", fake_install)
    assert rea_video.clone_rea_video() == tools.checkout_dir(tools.get("rea_video"))
    assert seen["name"] == "rea_video"


def test_clone_with_a_folder_uses_it_and_restores_the_environment(tmp_path, monkeypatch):
    seen = {}

    def fake_install(name):
        seen["env"] = os.environ.get("REA_VIDEO_DIR")
        return seen["env"]

    monkeypatch.setattr(tools, "install", fake_install)
    target = tmp_path / "meu-rea"
    assert rea_video.clone_rea_video(target) == target
    assert seen["env"] == str(target)
    assert "REA_VIDEO_DIR" not in os.environ


def test_clone_refuses_offline_mode(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    monkeypatch.setattr(tools, "install", _no_call)
    with pytest.raises(rea_video.ReaVideoError, match="offline"):
        rea_video.clone_rea_video()


def test_clone_takes_at_most_one_folder(monkeypatch, capsys):
    monkeypatch.setattr(tools, "install", _no_call)
    assert cli.main(["rea-video", "clone", "a", "b"]) == 1
    assert "no máximo uma pasta" in capsys.readouterr().err


# ---- setup --------------------------------------------------------------------------------------------------------

def test_setup_builds_a_venv_and_installs_the_checkout_with_the_ocr_extra(checkout, tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: REF)
    venv = _data(tmp_path) / "venv"
    calls: list[list] = []

    def fake_call(argv, **kwargs):
        calls.append(list(argv))
        if argv[1:3] == ["-m", "venv"]:
            (venv / "bin").mkdir(parents=True, exist_ok=True)
            (venv / "bin" / "python").write_text("", encoding="utf8")
        if argv[1:4] == ["-m", "pip", "install"]:
            (venv / "bin" / "rea-video").write_text("", encoding="utf8")
        return 0

    monkeypatch.setattr(rea_video.subprocess, "call", fake_call)
    assert cli.main(["rea-video", "setup"]) == 0
    assert calls[0] == [sys.executable, "-m", "venv", str(venv)]
    assert calls[1][0] == str(venv / "bin" / "python")
    assert calls[1][1:4] == ["-m", "pip", "install"]
    assert calls[1][-1] == f"{checkout.resolve()}[ocr]"


def test_setup_falls_back_to_the_core_when_the_ocr_extra_does_not_install(checkout, tmp_path, monkeypatch, capsys):
    """rapidocr-onnxruntime has no release for every Python: without the extra the analysis still works (the upstream
    says so and runs with OCR off), so setup installs the core and warns, instead of failing."""
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: REF)
    venv = _data(tmp_path) / "venv"
    calls: list[list] = []

    def fake_call(argv, **kwargs):
        calls.append(list(argv))
        if argv[1:3] == ["-m", "venv"]:
            (venv / "bin").mkdir(parents=True, exist_ok=True)
            (venv / "bin" / "python").write_text("", encoding="utf8")
            return 0
        if argv[1:4] == ["-m", "pip", "install"]:
            if argv[-1].endswith("[ocr]"):
                return 1  # no release of the extra for this Python
            (venv / "bin" / "rea-video").write_text("", encoding="utf8")
        return 0

    monkeypatch.setattr(rea_video.subprocess, "call", fake_call)
    assert cli.main(["rea-video", "setup"]) == 0
    pip_calls = [c for c in calls if c[1:4] == ["-m", "pip", "install"]]
    assert pip_calls[0][-1].endswith("[ocr]") and pip_calls[-1][-1] == str(checkout.resolve())  # the core, no extra
    err = capsys.readouterr().err
    assert "aviso" in err and "Sem OCR" in err


def test_setup_builds_the_venv_with_rea_video_python_when_it_is_set(checkout, tmp_path, monkeypatch):
    """The OCR extra needs a Python that its wheel supports (3.11 here), so the venv's interpreter is a choice."""
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: REF)
    monkeypatch.setenv("REA_VIDEO_PYTHON", "/opt/py311/bin/python3.11")
    venv = _data(tmp_path) / "venv"
    calls: list[list] = []

    def fake_call(argv, **kwargs):
        calls.append(list(argv))
        if argv[1:3] == ["-m", "venv"]:
            (venv / "bin").mkdir(parents=True, exist_ok=True)
            (venv / "bin" / "python").write_text("", encoding="utf8")
        if argv[1:4] == ["-m", "pip", "install"]:
            (venv / "bin" / "rea-video").write_text("", encoding="utf8")
        return 0

    monkeypatch.setattr(rea_video.subprocess, "call", fake_call)
    assert cli.main(["rea-video", "setup"]) == 0
    assert calls[0] == ["/opt/py311/bin/python3.11", "-m", "venv", str(venv)]


def test_status_warns_about_a_dotenv_in_the_working_folder(tmp_path, monkeypatch, capsys):
    """The upstream reads a .env from the folder the user runs it in, with its endpoints and keys: say so."""
    work = tmp_path / "outro-projeto"
    work.mkdir()
    (work / ".env").write_text("REA_VLM_API_KEY=nao-real\n", encoding="utf8")
    monkeypatch.chdir(work)
    assert cli.main(["rea-video", "status"]) == 0
    out = capsys.readouterr().out
    assert "aviso" in out and ".env" in out


def test_status_has_no_dotenv_warning_without_a_dotenv(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["rea-video", "status"]) == 0
    assert "aviso" not in capsys.readouterr().out


def test_setup_fails_when_even_the_core_does_not_install(checkout, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: REF)

    def fake_call(argv, **kwargs):
        if argv[1:3] == ["-m", "venv"]:
            (_data(tmp_path) / "venv" / "bin").mkdir(parents=True, exist_ok=True)
            (_data(tmp_path) / "venv" / "bin" / "python").write_text("", encoding="utf8")
            return 0
        return 1  # every pip install fails, the extra and the core alike

    monkeypatch.setattr(rea_video.subprocess, "call", fake_call)
    assert cli.main(["rea-video", "setup"]) == 1
    assert "não consegui instalar" in capsys.readouterr().err


def test_setup_warns_when_the_checkout_is_not_the_pin(checkout, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "b" * 40)
    monkeypatch.setattr(rea_video.subprocess, "call", lambda argv, **k: 0)
    cli.main(["rea-video", "setup"])  # the outcome is not the point here: the warning is
    err = capsys.readouterr().err
    assert "aviso" in err and REF[:12] in err


def test_setup_refuses_offline_mode(checkout, monkeypatch, capsys):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    monkeypatch.setattr(rea_video.subprocess, "call", _no_call)
    assert cli.main(["rea-video", "setup"]) == 1
    assert "offline" in capsys.readouterr().err


def test_setup_needs_a_checkout_first(monkeypatch, capsys):
    monkeypatch.setattr(rea_video.subprocess, "call", _no_call)
    assert cli.main(["rea-video", "setup"]) == 1
    assert "rea-video clone" in capsys.readouterr().err


def test_setup_takes_no_arguments(checkout, monkeypatch, capsys):
    monkeypatch.setattr(rea_video.subprocess, "call", _no_call)
    assert cli.main(["rea-video", "setup", "extra"]) == 1
    assert "não recebe argumentos" in capsys.readouterr().err


# ---- passthrough --------------------------------------------------------------------------------------------------

def test_any_other_word_goes_to_rea_video_unchanged(tmp_path, monkeypatch, capsys):
    exe = _rea_video_bin(tmp_path)
    calls = _Calls(rc=0)
    monkeypatch.setattr(rea_video.subprocess, "call", calls)
    args = ["decompose", "ref.mp4", "-o", "out/ref", "--no-ocr", "--ocr-lang", "ja"]
    assert cli.main(["rea-video", *args]) == 0
    argv, kwargs = calls.calls[0]
    assert argv == [str(exe), *args]
    assert kwargs.get("cwd") is None  # runs where the user called it, so relative paths keep their meaning
    assert capsys.readouterr().out == ""  # nothing of ours around the upstream output


def test_leading_upstream_flags_reach_rea_video_not_setup(tmp_path, monkeypatch):
    exe = _rea_video_bin(tmp_path)
    calls = _Calls()
    monkeypatch.setattr(rea_video.subprocess, "call", calls)
    assert cli.main(["rea-video", "--env-file", "x.env", "decompose", "a.mp4"]) == 0
    assert calls.calls[0][0] == [str(exe), "--env-file", "x.env", "decompose", "a.mp4"]


def test_status_names_each_vlm_key_without_printing_values(monkeypatch, capsys):
    monkeypatch.setenv("VIDEO_ANALYSIS_API_KEY", "segredo-outro-456")
    assert cli.main(["rea-video", "status"]) == 0
    out = capsys.readouterr().out
    assert "VIDEO_ANALYSIS_API_KEY: definida" in out and "GEMINI3_API_KEY: não definida" in out
    assert "segredo-outro-456" not in out


def test_the_upstream_exit_code_is_returned(tmp_path, monkeypatch):
    _rea_video_bin(tmp_path)
    monkeypatch.setattr(rea_video.subprocess, "call", _Calls(rc=3))
    assert cli.main(["rea-video", "summary", "breakdown.json"]) == 3


def test_help_after_an_upstream_command_is_the_upstream_help(tmp_path, monkeypatch, capsys):
    exe = _rea_video_bin(tmp_path)
    calls = _Calls()
    monkeypatch.setattr(rea_video.subprocess, "call", calls)
    assert cli.main(["rea-video", "decompose", "--help"]) == 0
    assert calls.calls[0][0] == [str(exe), "decompose", "--help"]
    assert "simplicio-video rea-video" not in capsys.readouterr().out


def test_passthrough_needs_only_the_venv_not_the_checkout(tmp_path, monkeypatch):
    exe = _rea_video_bin(tmp_path)
    calls = _Calls()
    monkeypatch.setattr(rea_video.subprocess, "call", calls)
    assert cli.main(["rea-video", "memory"]) == 0
    assert calls.calls[0][0] == [str(exe), "memory"]


def test_running_before_setup_says_to_run_setup(monkeypatch, capsys):
    monkeypatch.setattr(rea_video.subprocess, "call", _no_call)
    assert cli.main(["rea-video", "decompose", "ref.mp4"]) == 1
    err = capsys.readouterr().err
    assert "rea-video: " in err and "setup" in err


def test_state_and_models_default_to_the_data_folder_and_respect_overrides(tmp_path, monkeypatch):
    _rea_video_bin(tmp_path)
    calls = _Calls()
    monkeypatch.setattr(rea_video.subprocess, "call", calls)
    assert cli.main(["rea-video", "memory"]) == 0
    env = calls.calls[0][1]["env"]
    assert env["REA_VIDEO_HOME"] == str(_data(tmp_path) / "home")
    assert env["REA_VIDEO_MODELS"] == str(_data(tmp_path) / "models")
    monkeypatch.setenv("REA_VIDEO_HOME", str(tmp_path / "meu"))
    assert cli.main(["rea-video", "memory"]) == 0
    assert calls.calls[1][1]["env"]["REA_VIDEO_HOME"] == str(tmp_path / "meu")


@pytest.mark.parametrize("args,goes", [
    ([], False), (["--help"], False), (["-h"], False), (["help"], False), (["where"], False),
    (["status"], False), (["setup"], False), (["clone"], False),
    (["decompose"], True), (["decompose", "--help"], True), (["review", "out/ref"], True),
    (["--env-file", ".env", "decompose"], True), (["-v", "prefs"], True),  # upstream global flags come first
])
def test_repassa_decides_what_goes_to_rea_video(args, goes):
    assert rea_video.repassa(args) is goes


# ---- help and dispatch --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [["rea-video"], ["rea-video", "help"]])
def test_wrapper_help_names_the_commands_and_the_limits(argv, capsys, monkeypatch):
    monkeypatch.setattr(rea_video.subprocess, "call", _no_call)
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    for word in ("clone", "setup", "where", "status", "decompose", "REA_VLM_BASE_URL", "ffmpeg", "67 MB",
                 "SIMPLICIO_OFFLINE", "REA_VIDEO_HOME", "REA_VIDEO_MODELS"):
        assert word in out, word


def test_cli_dispatches_to_the_track(monkeypatch):
    recorded = []
    monkeypatch.setattr(rea_video, "run_rea_video", lambda args: recorded.append(args) or 0)
    assert cli.main(["rea-video", "decompose", "x.mp4"]) == 0
    assert recorded == [["decompose", "x.mp4"]]


def test_cli_error_exits_1_with_the_track_prefix(monkeypatch, capsys):
    def boom(args):
        raise rea_video.ReaVideoError("falha teste")

    monkeypatch.setattr(rea_video, "run_rea_video", boom)
    assert cli.main(["rea-video", "where"]) == 1
    assert "rea-video: falha teste" in capsys.readouterr().err


# ---- MCP ----------------------------------------------------------------------------------------------------------

def test_mcp_exposes_the_track_under_the_cli_name():
    assert "video.rea-video" in {name for name, _, _ in mcp_server.TOOLS}


def test_mcp_reads_and_refuses_setup_and_the_analysis(checkout, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: REF)
    assert mcp_server.video_rea_video("where")["ok"] is True
    assert mcp_server.video_rea_video("status")["ok"] is True
    assert mcp_server.video_rea_video("clone /tmp/x")["ok"] is False  # the default folder only, over MCP
    assert mcp_server.video_rea_video("where extra")["ok"] is False
    for refused in ("setup", "decompose ref.mp4 -o out/ref", "remake-run jobs.json"):
        r = mcp_server.video_rea_video(refused)
        assert r["ok"] is False and "terminal" in r["error"], refused


def test_module_never_imports_the_upstream_package_nor_uses_a_machine_path():
    src = Path(rea_video.__file__).read_text(encoding="utf8")
    assert "import rea_video" not in src and "from rea_video" not in src
    assert "/home/" not in src and "/Users/" not in src

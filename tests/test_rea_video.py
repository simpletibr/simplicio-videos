"""rea-video track: a pinned checkout installed in a venv of its own, and every command passed through to it.
Nothing here touches the network: clone, pip and the upstream command are stubbed."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from _orfao import SINAIS, espera, espera_pid, mata_o_que_sobrou, roda_motor, vivo

from simplicio_video import cli, mcp_server, rea_video, tools
from helpers import isolate_tools

SHA40 = re.compile(r"^[0-9a-f]{40}$")
REF = "36e02ddf1ffc287bd760d816c132027598f2e4c0"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate_tools(monkeypatch, tmp_path, data="dados",
                  drop=("REA_VIDEO_DIR", "REA_VIDEO_DATA_DIR", "REA_VIDEO_HOME", "REA_VIDEO_MODELS", "REA_VLM_API_KEY",
                        "VIDEO_ANALYSIS_API_KEY", "GEMINI3_API_KEY", "SIMPLICIO_OFFLINE", "SIMPLICIO_REA_VIDEO_REF"))


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

    def fake_install(name, *, dir=None):
        seen["dir"] = dir
        seen["env"] = os.environ.get("REA_VIDEO_DIR")
        return str(dir)

    monkeypatch.setattr(tools, "install", fake_install)
    target = tmp_path / "meu-rea"
    assert rea_video.clone_rea_video(target) == target
    assert seen["dir"] == target  # the folder goes to tools.install as `dir=`
    assert seen["env"] is None  # and the variable is not even set while it runs (it used to be, and put back)
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
    for refused in ("setup", "remake-run jobs.json"):
        r = mcp_server.video_rea_video(refused)
        assert r["ok"] is False and "terminal" in r["error"], refused


def test_module_never_imports_the_upstream_package_nor_uses_a_machine_path():
    src = Path(rea_video.__file__).read_text(encoding="utf8")
    assert "import rea_video" not in src and "from rea_video" not in src
    assert "/home/" not in src and "/Users/" not in src


# ---- MCP: the open commands, a closed list of flags, a private cwd (T5) ---------------------------------------------

class _Exec:
    """Stands in for rea_video._mcp_exec (the one place the MCP path starts the upstream): records (argv, cwd, env)."""

    def __init__(self, rc: int = 0, out: str = "ok"):
        self.rc, self.out, self.calls, self.cwd_seen = rc, out, [], []

    def __call__(self, argv, cwd, env):
        self.calls.append((list(argv), Path(cwd), dict(env)))
        self.cwd_seen.append((Path(cwd).is_dir(), sorted(p.name for p in Path(cwd).iterdir())))
        return self.rc, self.out


@pytest.fixture
def fake(tmp_path, monkeypatch):
    _rea_video_bin(tmp_path)
    ex = _Exec()
    monkeypatch.setattr(rea_video, "_mcp_exec", ex)
    return ex


@pytest.fixture
def media(tmp_path):
    video = tmp_path / "ref.mp4"
    video.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    bd = out / "breakdown.json"
    bd.write_text("{}", encoding="utf8")
    ans = out / "answers.json"
    ans.write_text("{}", encoding="utf8")
    return {"video": str(video), "out": str(out), "bd": str(bd), "ans": str(ans), "dir": tmp_path}


def _mcp(arg_list):
    return mcp_server.video_rea_video(arg_list)


def test_mcp_open_commands_reach_the_upstream_with_exactly_the_given_flags(fake, media):
    v, o, bd, ans = media["video"], str(media["dir"] / "t.jpg"), media["bd"], media["ans"]
    cases = [
        (["summary", bd], ["summary", bd]),
        (["probe", v, "--tags"], ["probe", v, "--tags"]),
        (["tiles", v, "-o", o, "--start", "1", "--end", "3.5", "--every", "0.5", "--cols", "4", "--cell", "200", "--max", "10"],
         ["tiles", v, "-o", o, "--start", "1", "--end", "3.5", "--every", "0.5", "--cols", "4", "--cell", "200", "--max", "10"]),
        (["tiles", v, f"--out={o}"], ["tiles", v, "--out", o]),
        (["review", media["out"], "--force"], ["review", media["out"], "--force"]),
        (["apply-review", media["out"], ans, "--by", "claude"], ["apply-review", media["out"], ans, "--by", "claude"]),
        (["remake-plan", bd, "--capsule-root", str(media["dir"]), "--engine", "seedance2.0", "--mode", "image_to_video",
          "--labels", "ai_video,cg_3d"],
         ["remake-plan", bd, "--capsule-root", str(media["dir"]), "--engine", "seedance2.0", "--mode", "image_to_video",
          "--labels", "ai_video,cg_3d"]),
    ]
    for given, want in cases:
        fake.calls.clear()
        r = _mcp(given)
        assert r["ok"] is True, (given, r)
        assert len(fake.calls) == 1 and fake.calls[0][0][1:] == want, given
        assert Path(fake.calls[0][0][0]).name == "rea-video"


def test_mcp_accepts_a_quoted_string_with_a_path_that_has_spaces(fake, tmp_path):
    d = tmp_path / "meu video"
    d.mkdir()
    f = d / "a.mp4"
    f.write_bytes(b"x")
    assert _mcp(f'probe "{f}"')["ok"] is True
    assert fake.calls[0][0][2] == str(f)


def test_mcp_children_run_in_a_private_empty_cwd_not_the_callers(fake, media, monkeypatch, tmp_path):
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / ".env").write_text("REA_VLM_API_KEY=sk-should-never-be-read\n", encoding="utf8")
    monkeypatch.chdir(caller)
    assert _mcp(["summary", media["bd"]])["ok"] is True
    cwd = fake.calls[0][1]
    assert cwd != caller and not (cwd / ".env").exists()
    assert fake.cwd_seen[0] == (True, [])  # existed and was empty while the child ran
    assert not cwd.exists()  # and is gone afterwards


def test_mcp_exec_uses_stdin_devnull_and_the_private_cwd(tmp_path):
    code = "import os,sys;print(os.getcwd(), repr(sys.stdin.read()), os.environ.get('A'))"
    rc, out = rea_video._mcp_exec([sys.executable, "-c", code], tmp_path, {"A": "1"})
    assert rc == 0 and out.split() == [str(tmp_path), "''", "1"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX signals")
@pytest.mark.parametrize("quando", ["popen", "espera"])
@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_does_not_orphan_the_upstream_nor_leave_the_private_folder(tmp_path, nome, quando):
    """No SIGTERM/SIGHUP handler existed (the default action ends the engine on the spot: the upstream, in its own session, and the
    `rea-video-cwd-*` folder stay) and the kill was armed only after Popen returned (a signal in that gap left an orphan)."""
    pidfile = tmp_path / "pid"
    exe = tmp_path / "rea-video"
    exe.write_text(f"#!/bin/sh\necho $$ > {pidfile}\nexec sleep 120\n")
    exe.chmod(0o755)
    tmpd = tmp_path / "tmpd"
    corpo = ("from pathlib import Path\nfrom simplicio_video import rea_video\n"
             f"rea_video._rea_video_exe = lambda: Path({str(exe)!r})\n"
             "rea_video.mcp_command = lambda args: ['summary', '/x']\n"
             "sys.exit(rea_video.mcp_run(['summary', '/x'])[0])\n")
    try:
        res = roda_motor(tmp_path, corpo, pidfile, nome, quando, so_se=str(exe), tmpd=tmpd)
        assert espera(lambda: not vivo(espera_pid(pidfile)), 8), f"the upstream outlived the engine (rc {res.returncode})\n{res.stderr[-400:]}"
        assert not list(tmpd.glob("rea-video-cwd-*")), "the private folder was left behind"
        assert res.returncode in (128 + getattr(signal, nome), -getattr(signal, nome), 1), res.returncode
    finally:
        mata_o_que_sobrou(pidfile)


@pytest.mark.slow
def test_mcp_exec_timeout_kills_the_whole_process_group(tmp_path, monkeypatch):
    monkeypatch.setattr(rea_video, "MCP_TIMEOUT", 1)
    code = ("import subprocess,sys,time;"
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print(p.pid,flush=True);time.sleep(60)")
    rc, out = rea_video._mcp_exec([sys.executable, "-c", code], tmp_path, {})
    assert rc == 124
    pid = int(out.split()[0])
    import time
    for _ in range(50):  # the grandchild must be gone (or at most a zombie waiting for its reaper)
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
            state = "gone"
        if state in ("gone", "Z"):
            break
        time.sleep(0.1)
    assert state in ("gone", "Z"), state


def test_mcp_children_never_see_the_vlm_settings_of_the_caller(fake, media, monkeypatch):
    for k in ("REA_VLM_API_KEY", "REA_VLM_BASE_URL", "VIDEO_ANALYSIS_API_KEY", "VIDEO_ANALYSIS_BASE_URL", "GEMINI3_API_KEY"):
        monkeypatch.setenv(k, "segredo-" + k)
    monkeypatch.setenv("REA_VIDEO_HOME", "/h")
    assert _mcp(["summary", media["bd"]])["ok"] is True
    env = fake.calls[0][2]
    assert not [k for k in env if k.startswith(("REA_VLM_", "VIDEO_ANALYSIS_", "GEMINI3_"))]
    assert env["REA_VIDEO_HOME"] == "/h" and "REA_VIDEO_MODELS" in env  # state and models stay where the user has them


@pytest.mark.parametrize("given", [
    ["setup"], ["remake-run", "/x/jobs.json"], ["remake-run", "/x/jobs.json", "--dry-run"], ["capsule-draft", "/x/b.json"],
    ["prefs"], ["prefs", "vlm", "on"], ["correct", "/x"], ["memory"], ["eval", "/x/l.yaml"],
])
def test_mcp_terminal_only_commands_are_refused(fake, given):
    r = _mcp(given)
    assert r["ok"] is False and "terminal" in r["error"], given
    assert fake.calls == []


@pytest.mark.parametrize("extra", [["--vlm"], ["--env-file", "/x/.env"], ["--env-file=/x/.env"], ["--vl"], ["--no-such"]])
def test_mcp_refuses_vlm_env_file_and_unknown_flags_on_every_open_command(fake, media, extra):
    base = {"summary": [media["bd"]], "probe": [media["video"]], "review": [media["out"]],
            "apply-review": [media["out"]], "remake-plan": [media["bd"]],
            "tiles": [media["video"], "-o", str(media["dir"] / "t.jpg")], "stems": [media["video"], "-o", media["out"]],
            "decompose": [media["video"], "-o", media["out"]]}
    for cmd, pos in base.items():
        r = _mcp([cmd, *pos, *extra])
        assert r["ok"] is False and "terminal" in r["error"], (cmd, extra, r)
    assert fake.calls == []


def test_mcp_refuses_global_upstream_flags_before_the_command(fake, media):
    for given in (["--env-file", "/x/.env", "summary", media["bd"]], ["-v", "summary", media["bd"]]):
        r = _mcp(given)
        assert r["ok"] is False and "terminal" in r["error"]
    assert fake.calls == []


def test_mcp_paths_must_be_absolute_and_exist(fake, media, tmp_path):
    for given in (["summary", "breakdown.json"], ["probe", "~/a.mp4"], ["review", "out/ref"],
                  ["tiles", media["video"], "-o", "t.jpg"], ["tiles", media["video"]],  # -o is required, and absolute
                  ["stems", media["video"]], ["stems", media["video"], "-o", "out/stems"],
                  ["remake-plan", media["bd"], "--capsule-root", "capsule"],
                  ["summary", str(tmp_path / "nao-existe.json")], ["probe", str(tmp_path / "nao-existe.mp4")]):
        r = _mcp(given)
        assert r["ok"] is False and r["error"], given
    assert fake.calls == []


def test_mcp_flag_values_are_checked(fake, media):
    v = media["video"]
    o = str(media["dir"] / "t.jpg")
    for given in (["tiles", v, "-o", o, "--cols", "x"], ["tiles", v, "-o", o, "--start"], ["tiles", v, "-o", o, "--max", "-1"],
                  ["remake-plan", media["bd"], "--mode", "anything"], ["review", media["out"], "--force", "--force"],
                  ["summary", media["bd"], media["bd"]], ["summary"], ["tiles", v, "-o", o, "--every", "--vlm"],
                  ["apply-review", media["out"], media["ans"], "extra"]):
        r = _mcp(given)
        assert r["ok"] is False and r["error"], given
    assert fake.calls == []


def test_mcp_reports_the_upstream_exit_code_and_output(fake, media):
    fake.rc, fake.out = 3, "boom"
    r = _mcp(["summary", media["bd"]])
    assert r["ok"] is False and r["result"] == 3 and "boom" in r["log"]


def test_mcp_without_the_venv_says_to_run_setup(media, monkeypatch):
    monkeypatch.setattr(rea_video, "_mcp_exec", lambda *a: pytest.fail("não devia rodar"))
    r = _mcp(["summary", media["bd"]])
    assert r["ok"] is False and "setup" in r["error"]


def test_mcp_where_status_clone_still_work_as_before(checkout, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: REF)
    assert _mcp(["where"])["ok"] is True and _mcp("status")["ok"] is True
    assert _mcp(["clone", "/tmp/x"])["ok"] is False


# ---- MCP: decompose as a background job ----------------------------------------------------------------------------

@pytest.fixture
def stub_spawn(monkeypatch):
    from simplicio_video import jobs
    calls = []
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: calls.append(jid) or os.getpid())
    return calls


def test_jobs_has_the_rea_video_kind():
    from simplicio_video import jobs
    assert "rea-video" in jobs.KINDS


def test_mcp_decompose_submits_a_job_and_always_says_no_vlm(fake, media, stub_spawn):
    from simplicio_video import jobs
    out = str(media["dir"] / "dec")
    r = _mcp(["decompose", media["video"], "-o", out, "--no-stems", "--no-ocr", "--workers", "2", "--ocr-lang", "ja"])
    assert r["ok"] is True and r["job"]["kind"] == "rea-video" and r["job"]["state"] == "queued", r
    assert fake.calls == [] and stub_spawn == [r["job"]["id"]]  # submitted, not run inline
    st = jobs.status(r["job"]["id"])
    args = st["params"]["args"]
    assert args[0] == "decompose" and "--no-vlm" in args and "--vlm" not in args and "-o" in args
    assert Path(st["cwd"]) != Path.cwd() and Path(st["cwd"]).is_dir()  # the runner starts the child in a private folder
    assert jobs.build_argv("rea-video", st["params"])[0] == "rea-video"


@pytest.mark.parametrize("extra", [["--vlm"], ["--env-file", "/x/.env"], ["--env-file=/x/.env"]])
def test_mcp_decompose_refuses_vlm_and_env_file(fake, media, stub_spawn, extra):
    r = _mcp(["decompose", media["video"], "-o", str(media["dir"] / "dec"), *extra])
    assert r["ok"] is False and "terminal" in r["error"] and stub_spawn == []


def test_mcp_decompose_needs_an_absolute_out(fake, media, stub_spawn):
    for given in (["decompose", media["video"]], ["decompose", media["video"], "-o", "out/ref"]):
        assert _mcp(given)["ok"] is False
    assert stub_spawn == []


def test_jobs_submit_validates_the_same_way_whatever_the_origin(media, stub_spawn):
    from simplicio_video import jobs
    for origin in ("mcp", "terminal"):
        with pytest.raises(jobs.JobError, match="terminal"):
            jobs.submit("rea-video", {"args": ["decompose", media["video"], "-o", media["out"], "--vlm"]}, origin=origin)
        with pytest.raises(jobs.JobError):
            jobs.submit("rea-video", {"args": ["summary", media["bd"]]}, origin=origin)  # only decompose is a job
        with pytest.raises(jobs.JobError):
            jobs.submit("rea-video", {"args": ["decompose", media["video"], "-o", media["out"]], "x": 1}, origin=origin)
    assert stub_spawn == []


def test_rea_video_job_result_summarises_the_breakdown(tmp_path):
    from simplicio_video import jobs
    out = tmp_path / "dec"
    out.mkdir()
    (out / "breakdown.json").write_text(json.dumps({"summary": {"verdict": "ai", "shots": 4, "confidence": 0.8, "vlm": "off"}}),
                                        encoding="utf8")
    (out / "report.html").write_text("<html>", encoding="utf8")
    params = {"args": ["decompose", "/v.mp4", "-o", str(out), "--no-vlm"]}
    res = jobs.KINDS["rea-video"]["result"](params, None)
    assert res["out"] == str(out) and res["breakdown"] == str(out / "breakdown.json")
    assert res["report"] == str(out / "report.html") and res["verdict"] == "ai" and res["shots"] == 4
    assert len(res["breakdown_sha256"]) == 64
    (out / "breakdown.json").unlink()
    assert jobs.KINDS["rea-video"]["result"](params, None) is None


def test_mcp_description_names_what_is_open_and_what_stays_in_the_terminal():
    d = mcp_server.DESC_video_rea_video
    for word in ("summary", "probe", "tiles", "stems", "review", "apply-review", "remake-plan", "decompose", "job", "terminal"):
        assert word in d, word
    assert "--vlm" in d


# ---- review round 1: output paths cannot clobber, stems is a job, job hygiene ---------------------------------------

@pytest.fixture(autouse=True)
def _private_tmp(tmp_path, monkeypatch):
    t = tmp_path / "systmp"
    t.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(t))
    return t


def test_mcp_tiles_never_overwrites_an_existing_file_or_a_symlink(fake, media):
    v, d = media["video"], media["dir"]
    victim = d / "victim.png"
    victim.write_text("keep", encoding="utf8")
    link = d / "link.jpg"
    link.symlink_to(d / "alvo.txt")
    real = d / "real"
    real.mkdir()
    (d / "viaLink").symlink_to(real)
    (d / "t_2.jpg").write_text("keep", encoding="utf8")  # a derived name (t_1.jpg, t_2.jpg ...) that already exists
    for target in (victim, link, d / "viaLink" / "x.jpg", d / "real" / ".." / "x.jpg", d / "t.jpg", d / "sem-pai" / "x.jpg"):
        r = _mcp(["tiles", v, "-o", str(target)])
        assert r["ok"] is False and r["error"], target
    assert fake.calls == [] and victim.read_text() == "keep"
    assert _mcp(["tiles", v, "-o", str(d / "novo.jpg")])["ok"] is True


def test_mcp_output_folders_must_be_new_or_empty_and_not_symlinks(fake, media, stub_spawn):
    v, d = media["video"], media["dir"]
    empty = d / "vazia"
    empty.mkdir()
    (d / "alvo").mkdir()
    (d / "lnk").symlink_to(d / "alvo")
    for cmd in ("decompose", "stems"):
        for bad in (media["out"], str(d / "lnk"), str(d / "real" / ".." / "x")):  # non-empty, symlink, '..'
            r = _mcp([cmd, v, "-o", bad])
            assert r["ok"] is False and r["error"], (cmd, bad)
    assert stub_spawn == []
    assert _mcp(["decompose", v, "-o", str(empty)])["ok"] is True
    assert _mcp(["stems", v, "-o", str(d / "nova")])["ok"] is True


def test_mcp_review_and_apply_review_need_a_real_analysis_folder(fake, media):
    d = media["dir"]
    vazio = d / "vazio"
    vazio.mkdir()
    (d / "lnk").symlink_to(media["out"])
    ruim = d / "ruim"
    ruim.mkdir()
    (ruim / "breakdown.json").write_text("{}", encoding="utf8")
    (ruim / "review_answers.json").symlink_to(d / "alvo.txt")
    for cmd in ("review", "apply-review"):
        for bad in (vazio, d / "lnk", ruim, d):
            r = _mcp([cmd, str(bad)])
            assert r["ok"] is False and r["error"], (cmd, bad)
        assert _mcp([cmd, media["out"]])["ok"] is True


def test_mcp_remake_plan_writes_only_beside_a_real_breakdown(fake, media):
    d = media["dir"]
    solto = d / "outro.json"
    solto.write_text("{}", encoding="utf8")
    out2 = d / "out2"
    out2.mkdir()
    (out2 / "breakdown.json").write_text("{}", encoding="utf8")
    (out2 / "remake").symlink_to(d / "alvo")
    for bad in (str(solto), str(out2 / "breakdown.json")):
        assert _mcp(["remake-plan", bad])["ok"] is False
    assert _mcp(["remake-plan", media["bd"]])["ok"] is True


def test_mcp_tiles_every_must_be_positive(fake, media):
    o = str(media["dir"] / "t.jpg")
    for bad in ("0", "0.0"):
        assert _mcp(["tiles", media["video"], "-o", o, "--every", bad])["ok"] is False
    assert fake.calls == []


def test_mcp_stems_is_a_job_and_summary_is_not(fake, media, stub_spawn):
    from simplicio_video import jobs
    r = _mcp(["stems", media["video"], "-o", str(media["dir"] / "st")])
    assert r["ok"] is True and r["job"]["kind"] == "rea-video" and fake.calls == [] and len(stub_spawn) == 1
    assert jobs.status(r["job"]["id"])["params"]["args"][0] == "stems"
    with pytest.raises(jobs.JobError):
        jobs.submit("rea-video", {"args": ["summary", media["bd"]]}, origin="mcp")


def test_stems_job_result_lists_the_stems(tmp_path):
    from simplicio_video import jobs
    st = tmp_path / "st" / "stems"
    st.mkdir(parents=True)
    for n in ("original", "vocals", "music"):
        (st / f"{n}.wav").write_bytes(b"x")
    res = jobs.KINDS["rea-video"]["result"]({"args": ["stems", "/v.mp4", "-o", str(tmp_path / "st")]}, None)
    assert res["original"] == str(st / "original.wav") and res["vocals"] == str(st / "vocals.wav")
    assert res["music"] == str(st / "music.wav")


def test_job_private_cwd_is_under_the_temp_dir_and_removed_when_the_job_ends(fake, media, stub_spawn, _private_tmp):
    from simplicio_video import jobs
    out = media["dir"] / "dec2"
    r = _mcp(["decompose", media["video"], "-o", str(out)])
    st = jobs.status(r["job"]["id"])
    cwd = Path(st["cwd"])
    assert cwd.parent == _private_tmp and cwd.is_dir()
    (out).mkdir()
    (out / "breakdown.json").write_text(json.dumps({"summary": {}}), encoding="utf8")
    assert jobs.KINDS["rea-video"]["result"](st["params"], None) is not None
    assert not cwd.exists()


def test_stale_private_cwds_are_swept_on_the_next_submit(fake, media, stub_spawn, _private_tmp):
    old = _private_tmp / "rea-video-job-velho"
    old.mkdir()
    os.utime(old, (1, 1))
    busy = _private_tmp / "rea-video-job-cheio"
    busy.mkdir()
    (busy / "x").write_text("a", encoding="utf8")
    os.utime(busy, (1, 1))
    assert _mcp(["decompose", media["video"], "-o", str(media["dir"] / "dec3")])["ok"] is True
    assert not old.exists() and busy.exists()


def test_the_runner_revalidates_the_stored_args_before_exec(media):
    from simplicio_video import jobs
    good = {"args": ["decompose", media["video"], "-o", str(media["dir"] / "d"), "--no-vlm"]}
    assert jobs.build_argv("rea-video", good)[0] == "rea-video"
    for bad in (["decompose", media["video"], "-o", str(media["dir"] / "d"), "--vlm"],
                ["decompose", media["video"], "-o", str(media["dir"] / "d"), "--env-file", "/x"], ["setup"]):
        with pytest.raises(Exception, match="terminal|tarefa"):
            jobs.build_argv("rea-video", {"args": bad})


def test_no_vlm_runs_do_not_hand_the_vlm_settings_to_the_upstream(tmp_path, monkeypatch):
    _rea_video_bin(tmp_path)
    for k in ("REA_VLM_API_KEY", "REA_VLM_BASE_URL", "VIDEO_ANALYSIS_API_KEY", "GEMINI3_API_KEY"):
        monkeypatch.setenv(k, "segredo")
    calls = _Calls()
    monkeypatch.setattr(subprocess, "call", calls)
    assert rea_video.run_rea_video(["decompose", "/v.mp4", "-o", "/o", "--no-vlm"]) == 0
    assert not [k for k in calls.calls[0][1]["env"] if k.startswith(("REA_VLM_", "VIDEO_ANALYSIS_", "GEMINI3_"))]
    assert rea_video.run_rea_video(["stems", "/v.mp4", "-o", "/o"]) == 0
    assert "REA_VLM_API_KEY" not in calls.calls[1][1]["env"]
    # a terminal decompose without --no-vlm keeps them: the person may want the vision model (prefs, --vlm)
    assert rea_video.run_rea_video(["decompose", "/v.mp4", "--vlm"]) == 0
    assert calls.calls[2][1]["env"]["REA_VLM_API_KEY"] == "segredo"


def test_docs_say_what_mcp_can_submit():
    root = Path(__file__).resolve().parents[1]
    assert "stems" in mcp_server.DESC_video_rea_video and "job" in mcp_server.DESC_video_rea_video
    assert "rea-video" in mcp_server.DESC_video_jobs
    from simplicio_video import jobs
    assert "rea-video" in jobs.HELP_DESC and "stems" in jobs.HELP_DESC
    agents = (root / "AGENTS.md").read_text(encoding="utf8")
    assert "só os de leitura" not in agents

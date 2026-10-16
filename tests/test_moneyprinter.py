from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from simplicio_video import cli, mcp_server, moneyprinter, tools

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
FAKE_KEY = "FAKEKEY-do-not-print-0123456789"
FAKE_KEY_2 = "FAKEKEY-in-a-list-9876543210"

EXAMPLE = """\
[app]
api_key = ""
pexels_api_keys = []
openai_api_key = ""
openai_model_name = ""
"""

CONFIG_WITH_KEYS = f"""\
listen_host = "0.0.0.0"
listen_port = 8080

[app]
api_key = ""
hide_config = false
pexels_api_keys = [
  "{FAKE_KEY_2}",  # a comment with a "quote" inside
]
pixabay_api_keys = []
openai_api_key = "{FAKE_KEY}"   # inline comment
openai_model_name = "gpt-fake"
anthropic_api_key = ''

[azure]
speech_key = ""
"""


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    # Isolate the home and the tools dir: a real checkout under ~/.simplicio-video must never be found by a test.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.delenv("MONEYPRINTER_DIR", raising=False)
    monkeypatch.delenv("MONEYPRINTER_DATA_DIR", raising=False)
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))


@pytest.fixture
def checkout(monkeypatch, tmp_path):
    """A stand-in MoneyPrinterTurbo checkout (config.example.toml is the marker): the tests never clone anything."""
    d = tmp_path / "moneyprinter"
    d.mkdir()
    (d / "config.example.toml").write_text(EXAMPLE)
    monkeypatch.setenv("MONEYPRINTER_DIR", str(d))
    return d


@pytest.fixture
def venv():
    """The isolated venv `setup` would have made (only the interpreter path matters to the fakes)."""
    py = moneyprinter.venv_python()
    py.parent.mkdir(parents=True)
    py.write_text("")
    return py


@pytest.fixture
def calls(monkeypatch):
    """Records every subprocess.call (venv, pip) as (cmd, cwd). A step exits 0 unless a test sets fail[index]."""
    recorded: list[tuple[list[str], Path | None]] = []
    fail: dict[int, int] = {}

    def fake(cmd, cwd=None, env=None):
        recorded.append((list(cmd), cwd))
        return fail.get(len(recorded) - 1, 0)

    monkeypatch.setattr("subprocess.call", fake)
    return recorded, fail


@pytest.fixture
def server(monkeypatch):
    """Fakes the long-running server processes. Records how each is started and which signal reaches each group.
    state.interrupt: the next sleep in the supervision loop raises KeyboardInterrupt (Ctrl+C on this process).
    state.exit_codes: None = every process exits 0 once the loop has slept once; a dict = only those processes
    (index -> exit code) exit, the others keep running."""
    state = SimpleNamespace(started=[], signals=[], interrupt=False, ignore_sigint=False, term_handler=None,
                            exit_codes=None, slept=0)

    class Proc:
        def __init__(self, cmd, cwd=None, env=None, start_new_session=False):
            self.cmd, self.cwd, self.env, self.start_new_session = cmd, cwd, env, start_new_session
            self.pid = 4242 + len(state.started)
            self.index = len(state.started)
            self.returncode = None
            state.started.append(self)

        def wait(self, timeout=None):
            if timeout is not None and state.ignore_sigint and any(sig == signal.SIGINT for _, sig in state.signals):
                raise subprocess.TimeoutExpired(self.cmd, timeout)
            self.returncode = 0 if self.returncode is None else self.returncode
            return self.returncode

        def poll(self):
            if self.returncode is None and state.slept:
                if state.exit_codes is None:
                    self.returncode = 0
                elif self.index in state.exit_codes:
                    self.returncode = state.exit_codes[self.index]
            return self.returncode

    def fake_sleep(seconds):
        state.term_handler = signal.getsignal(signal.SIGTERM)
        if state.interrupt:
            state.interrupt = False
            raise KeyboardInterrupt
        state.slept += 1

    monkeypatch.setattr("subprocess.Popen", Proc)
    monkeypatch.setattr(moneyprinter.time, "sleep", fake_sleep)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: state.signals.append((pgid, sig)))
    return state


def _alive(pid: int) -> bool:
    """Linux: a zombie counts as gone, since it no longer runs and no longer holds the port."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != "Z"


# ---- pin, folders, help -------------------------------------------------------------------------------------

def test_moneyprinter_is_pinned_to_a_full_commit_under_mit():
    t = tools.get("moneyprinter")
    assert t.kind == "git"
    assert t.source == "https://github.com/harry0703/MoneyPrinterTurbo"
    assert t.ref == "4b7b9657647bdb149715354269eec7e4dbad4a7a"
    assert SHA40.match(t.ref)
    assert t.license == "MIT"
    assert t.marker == "config.example.toml"
    # the note says what the service terms are about, without inventing their content
    assert "Pexels" in t.note and "LLM" in t.note


def test_find_dir_uses_the_env_override(checkout):
    assert moneyprinter.find_moneyprinter_dir() == checkout.resolve()


def test_find_dir_is_none_without_a_checkout(monkeypatch, tmp_path):
    monkeypatch.setenv("MONEYPRINTER_DIR", str(tmp_path / "vazio"))
    assert moneyprinter.find_moneyprinter_dir() is None


def test_data_dir_defaults_outside_the_checkout(tmp_path):
    assert moneyprinter.data_dir() == (tmp_path / "data" / "moneyprinter-data").resolve()


def test_data_dir_is_absolute_because_the_server_runs_inside_the_checkout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MONEYPRINTER_DATA_DIR", "dados/relativos")
    assert moneyprinter.data_dir().is_absolute()
    assert moneyprinter.data_dir() == (tmp_path / "dados" / "relativos").resolve()


def test_help_needs_no_checkout(calls, capsys):
    recorded, _ = calls
    assert moneyprinter.run_moneyprinter(["--help"]) == 0
    out = capsys.readouterr().out
    for word in ("clone", "setup", "serve", "where", "status", "--lan", "0.0.0.0", "8501", "8080",
                 "MONEYPRINTER_DIR", "MONEYPRINTER_DATA_DIR", "Python 3.11", "ffmpeg", "config.toml"):
        assert word in out, word
    assert recorded == []


@pytest.mark.parametrize("args", [["where"], ["setup"], ["serve"], ["status"]])
def test_commands_without_a_checkout_point_to_clone(args):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="moneyprinter clone"):
        moneyprinter.run_moneyprinter(args)


def test_unknown_subcommand_is_an_error(checkout):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="clone\\|setup\\|serve\\|where\\|status"):
        moneyprinter.run_moneyprinter(["nope"])


# ---- clone / where --------------------------------------------------------------------------------------------

def test_clone_installs_at_the_pinned_commit(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    assert moneyprinter.clone_moneyprinter() == tmp_path / "moneyprinter"
    assert calls[0][0] == "clone" and calls[0][-1] == str(tmp_path / "moneyprinter")
    assert calls[-1] == ("checkout", "--quiet", "--detach", tools.get("moneyprinter").ref)


def test_clone_never_runs_when_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path))
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    with pytest.raises(moneyprinter.MoneyPrinterError, match="offline"):
        moneyprinter.clone_moneyprinter()
    assert calls == []


def test_clone_to_an_explicit_dir_does_not_leak_into_the_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "")
    other = tmp_path / "meu"
    assert moneyprinter.clone_moneyprinter(other) == other
    assert "MONEYPRINTER_DIR" not in os.environ


def test_where_prints_the_checkout(checkout, capsys):
    assert moneyprinter.run_moneyprinter(["where"]) == 0
    assert capsys.readouterr().out.strip() == str(checkout.resolve())


# ---- setup ----------------------------------------------------------------------------------------------------

def test_setup_makes_an_isolated_venv_and_installs_the_requirements(checkout, calls, tmp_path):
    recorded, _ = calls
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    venv_dir = (tmp_path / "data" / "moneyprinter-data" / "venv").resolve()
    py = moneyprinter.venv_python()
    assert py.is_relative_to(venv_dir) and checkout.resolve() not in py.parents
    assert recorded[0][0][1:] == ["-m", "venv", str(venv_dir)]
    assert recorded[1][0] == [str(py), "-m", "pip", "install", "-r", "requirements.txt"]
    assert recorded[1][1] == checkout.resolve()


def test_setup_reuses_an_existing_venv(checkout, venv, calls):
    recorded, _ = calls
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    assert [cmd[1:4] for cmd, _ in recorded] == [["-m", "pip", "install"]]


def test_setup_needs_python_3_11_or_newer(checkout, calls, monkeypatch):
    recorded, _ = calls
    monkeypatch.setattr(moneyprinter, "MIN_PYTHON", (99, 0))
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(moneyprinter.MoneyPrinterError, match="3.11"):
        moneyprinter.run_moneyprinter(["setup"])
    assert recorded == []


@pytest.mark.parametrize("step", [0, 1])
def test_setup_stops_at_the_first_failing_step(checkout, calls, step):
    recorded, fail = calls
    fail[step] = 2
    assert moneyprinter.run_moneyprinter(["setup"]) == 1
    assert len(recorded) == step + 1


def test_setup_copies_the_example_config_without_filling_any_key(checkout, calls):
    assert not (checkout / "config.toml").exists()
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    assert (checkout / "config.toml").read_text() == EXAMPLE


def test_setup_never_overwrites_an_existing_config(checkout, calls, capsys):
    (checkout / "config.toml").write_text(CONFIG_WITH_KEYS)
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    assert (checkout / "config.toml").read_text() == CONFIG_WITH_KEYS
    out = capsys.readouterr()
    assert "já existe" in out.out


def test_setup_sends_the_storage_to_the_data_dir_and_keeps_an_existing_one(checkout, calls, tmp_path):
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    link = checkout / "storage"
    assert link.is_symlink()
    assert link.resolve() == (tmp_path / "data" / "moneyprinter-data" / "storage").resolve()
    assert link.resolve().is_dir()


def test_setup_leaves_a_real_storage_folder_alone(checkout, calls):
    (checkout / "storage").mkdir()
    (checkout / "storage" / "x.txt").write_text("meu")
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    assert not (checkout / "storage").is_symlink()
    assert (checkout / "storage" / "x.txt").read_text() == "meu"


def test_setup_reports_what_is_missing(checkout, calls, monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    out = capsys.readouterr().out
    assert "ffmpeg: não encontrado" in out
    assert "ImageMagick" in out
    assert "nenhuma chave preenchida" in out


def test_setup_says_ffmpeg_is_found(checkout, calls, monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else None)
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    assert "ffmpeg: encontrado" in capsys.readouterr().out


# ---- keys: only yes or no, never the value -----------------------------------------------------------------------

def test_config_report_marks_filled_keys_without_their_values(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG_WITH_KEYS)
    rep = moneyprinter.config_report(cfg)
    assert rep["exists"] is True
    assert rep["keys"]["app.openai_api_key"] is True
    assert rep["keys"]["app.pexels_api_keys"] is True       # multi-line list
    assert rep["keys"]["app.pixabay_api_keys"] is False     # empty list
    assert rep["keys"]["app.api_key"] is False
    assert rep["keys"]["app.anthropic_api_key"] is False    # single-quoted empty string
    assert rep["keys"]["azure.speech_key"] is False
    assert not any("model_name" in k or "listen" in k or "hide_config" in k for k in rep["keys"])
    assert FAKE_KEY not in json.dumps(rep) and FAKE_KEY_2 not in json.dumps(rep)


def test_config_report_without_a_file(tmp_path):
    assert moneyprinter.config_report(tmp_path / "nao-existe.toml") == {"exists": False, "keys": {}}


def test_status_prints_yes_or_no_and_never_a_key(checkout, capsys):
    (checkout / "config.toml").write_text(CONFIG_WITH_KEYS)
    assert moneyprinter.run_moneyprinter(["status"]) == 0
    out = capsys.readouterr()
    assert "config.toml: existe" in out.out
    assert "app.openai_api_key: sim" in out.out and "app.pexels_api_keys: sim" in out.out
    assert "app.anthropic_api_key" not in out.out.replace("vazias", "")  # empty ones are only counted
    for stream in (out.out, out.err):
        assert FAKE_KEY not in stream and FAKE_KEY_2 not in stream


def test_status_without_config(checkout, capsys):
    assert moneyprinter.run_moneyprinter(["status"]) == 0
    assert "config.toml: não existe" in capsys.readouterr().out


def test_no_command_leaks_a_key_to_stdout_or_stderr(checkout, venv, calls, server, capsys):
    (checkout / "config.toml").write_text(CONFIG_WITH_KEYS)
    for args in (["where"], ["status"], ["setup"], ["serve"], ["serve", "--api", "--lan"], ["--help"]):
        server.started.clear()
        moneyprinter.run_moneyprinter(args)
    out = capsys.readouterr()
    for stream in (out.out, out.err):
        assert FAKE_KEY not in stream and FAKE_KEY_2 not in stream
    for p in server.started:  # nor does it hand a key to the server through the command line or the environment
        assert FAKE_KEY not in " ".join(p.cmd)
        assert FAKE_KEY not in json.dumps({k: v for k, v in p.env.items() if k != "PATH"}, default=str)


# ---- serve --------------------------------------------------------------------------------------------------------

def test_serve_without_a_venv_points_to_setup(checkout, server):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="moneyprinter setup"):
        moneyprinter.run_moneyprinter(["serve"])
    assert server.started == []


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.10", "::"])
def test_serve_refuses_a_non_loopback_host_without_lan(checkout, venv, server, host):
    with pytest.raises(moneyprinter.MoneyPrinterError) as e:
        moneyprinter.run_moneyprinter(["serve", "--host", host])
    assert "--lan" in str(e.value)
    assert server.started == []


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_serve_accepts_a_loopback_host_without_lan(checkout, venv, server, host):
    assert moneyprinter.run_moneyprinter(["serve", "--host", host]) == 0
    assert f"--server.address={host}" in server.started[0].cmd


def test_serve_by_default_starts_only_the_webui_on_loopback(checkout, venv, server):
    # upstream's own default for the API is 0.0.0.0 (config listen_host): here the host is always forced by argument
    assert moneyprinter.run_moneyprinter(["serve"]) == 0
    assert len(server.started) == 1
    p = server.started[0]
    assert p.cmd[:5] == [str(venv), "-m", "streamlit", "run", str(checkout.resolve() / "webui" / "Main.py")]
    assert "--server.address=127.0.0.1" in p.cmd and "--server.port=8501" in p.cmd
    assert "--server.headless=true" in p.cmd and "--browser.gatherUsageStats=False" in p.cmd
    assert p.cwd == checkout.resolve()
    assert p.env["PYTHONPATH"].split(os.pathsep)[0] == str(checkout.resolve())
    assert p.start_new_session is True  # its own group, so a stop reaches every process it started


def test_serve_api_forces_the_host_by_argument_not_by_config(checkout, venv, server):
    (checkout / "config.toml").write_text('listen_host = "0.0.0.0"\n')
    assert moneyprinter.run_moneyprinter(["serve", "--api"]) == 0
    assert [p.cmd for p in server.started] == [
        [str(venv), "-m", "uvicorn", "app.asgi:app", "--host", "127.0.0.1", "--port", "8080", "--log-level", "warning"]]
    assert (checkout / "config.toml").read_text() == 'listen_host = "0.0.0.0"\n'  # the user's file is not edited


def test_serve_webui_and_api_run_in_separate_groups(checkout, venv, server):
    assert moneyprinter.run_moneyprinter(["serve", "--webui", "--api"]) == 0
    assert len(server.started) == 2
    assert all(p.start_new_session for p in server.started)
    assert {p.pid for p in server.started} == {4242, 4243}


def test_serve_lan_listens_on_every_interface_and_says_so(checkout, venv, server, capsys):
    assert moneyprinter.run_moneyprinter(["serve", "--api", "--webui", "--lan"]) == 0
    web, api = server.started
    assert "--server.address=0.0.0.0" in web.cmd
    assert api.cmd[api.cmd.index("--host") + 1] == "0.0.0.0"
    out = capsys.readouterr().out
    assert "todas as interfaces" in out and "sem login" in out


def test_serve_lan_with_an_explicit_host(checkout, venv, server):
    assert moneyprinter.run_moneyprinter(["serve", "--lan", "--host", "192.168.0.10"]) == 0
    assert "--server.address=192.168.0.10" in server.started[0].cmd


def test_serve_rejects_unknown_arguments_before_starting_anything(checkout, venv, server):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--port"):
        moneyprinter.run_moneyprinter(["serve", "--port", "9000"])
    assert server.started == []


def test_serve_ctrl_c_stops_every_group_without_a_traceback(checkout, venv, server, capsys):
    server.interrupt = True
    assert moneyprinter.run_moneyprinter(["serve", "--webui", "--api"]) == 0
    # SIGINT first, then the SIGKILL sweep of each group, for both processes
    assert server.signals == [(4242, signal.SIGINT), (4242, signal.SIGKILL),
                              (4243, signal.SIGINT), (4243, signal.SIGKILL)]
    assert "Traceback" not in capsys.readouterr().err


def test_serve_escalates_to_sigkill_when_a_server_ignores_sigint(checkout, venv, server):
    server.interrupt = True
    server.ignore_sigint = True
    assert moneyprinter.run_moneyprinter(["serve"]) == 0
    assert server.signals == [(4242, signal.SIGINT), (4242, signal.SIGKILL), (4242, signal.SIGKILL)]


def test_serve_when_one_server_dies_the_other_group_is_stopped_too(checkout, venv, server):
    server.exit_codes = {0: 3}  # the WebUI exits with 3 while the API keeps running
    assert moneyprinter.run_moneyprinter(["serve", "--webui", "--api"]) == 3
    assert server.signals == [(4243, signal.SIGINT), (4243, signal.SIGKILL)]


def test_serve_sigterm_is_handled_like_ctrl_c_and_restored_afterwards(checkout, venv, server):
    before = signal.getsignal(signal.SIGTERM)
    assert moneyprinter.run_moneyprinter(["serve"]) == 0
    handler = server.term_handler
    assert callable(handler) and handler is not before
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGTERM, None)
    assert signal.getsignal(signal.SIGTERM) is before


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="o teste lê /proc (Linux)")
def test_stop_group_kills_grandchildren_too(tmp_path):
    # Real processes, no network: the server starts a helper, and stopping the group must kill the helper as well.
    pidfile = tmp_path / "helper.pid"
    script = (
        "import subprocess, sys, time\n"
        "h = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
        f"open({str(pidfile)!r}, 'w').write(str(h.pid))\n"
        "time.sleep(600)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", script], start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 20
        while not (pidfile.exists() and pidfile.read_text().strip()) and time.time() < deadline:
            time.sleep(0.05)
        helper = int(pidfile.read_text())
        assert _alive(helper)
        moneyprinter._stop_group(proc)
        assert proc.poll() is not None
        deadline = time.time() + 5
        while _alive(helper) and time.time() < deadline:
            time.sleep(0.05)
        assert not _alive(helper)
    finally:
        if proc.poll() is None:
            proc.kill()


# ---- CLI, MCP, plugin ---------------------------------------------------------------------------------------------

def test_cli_dispatch_moneyprinter(monkeypatch):
    recorded = []
    monkeypatch.setattr(moneyprinter, "run_moneyprinter", lambda args: recorded.append(args) or 0)
    assert cli.main(["moneyprinter", "where"]) == 0
    assert recorded == [["where"]]


def test_cli_moneyprinter_error_exits_1(monkeypatch, capsys):
    def boom(args):
        raise moneyprinter.MoneyPrinterError("falha teste")

    monkeypatch.setattr(moneyprinter, "run_moneyprinter", boom)
    assert cli.main(["moneyprinter", "serve"]) == 1
    assert "moneyprinter: falha teste" in capsys.readouterr().err


def test_mcp_exposes_video_moneyprinter():
    assert "video.moneyprinter" in [name for name, fn, desc in mcp_server.TOOLS]


def test_mcp_where_returns_the_checkout(checkout):
    r = mcp_server.video_moneyprinter("where")
    assert r["ok"] is True
    assert str(checkout.resolve()) in r["log"]


@pytest.mark.parametrize("args", ["serve", "serve --lan", "serve --api", "setup", "status", "", "--help"])
def test_mcp_refuses_everything_but_where_and_clone(checkout, venv, calls, server, args):
    # an agent does not install packages, start servers or pick folders: serve and setup are terminal-only
    recorded, _ = calls
    r = mcp_server.video_moneyprinter(args)
    assert r["ok"] is False
    assert "terminal" in r["error"]
    assert recorded == [] and server.started == []
    assert not (checkout / "config.toml").exists()


def test_mcp_clone_uses_the_default_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    r = mcp_server.video_moneyprinter("clone")
    assert r["ok"] is True
    assert calls[0][-1] == str(tmp_path / "moneyprinter")


def test_mcp_clone_into_a_chosen_dir_is_refused(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    r = mcp_server.video_moneyprinter(f"clone {tmp_path / 'em-outro-lugar'}")
    assert r["ok"] is False
    assert calls == []


def _verbs(node):
    if isinstance(node, dict):
        if isinstance(node.get("verb"), str):
            yield node["verb"]
        for v in node.values():
            yield from _verbs(v)
    elif isinstance(node, list):
        for v in node:
            yield from _verbs(v)


def test_plugin_json_declares_the_verb_and_the_tool():
    data = json.loads((ROOT / "plugin.json").read_text())
    assert "video.moneyprinter" in data["mcp"]["tools"]
    assert "video.moneyprinter" in set(_verbs(data))


def test_status_lists_moneyprinter_with_its_pin():
    from simplicio_video import status
    assert "moneyprinter" in status.ENGINE_TOOLS


def test_moneyprinter_source_has_no_machine_specific_path():
    src = Path(moneyprinter.__file__).read_text()
    assert not re.search(r"""["'](/projetos|/home/|/Users/|[A-Za-z]:\\)""", src)

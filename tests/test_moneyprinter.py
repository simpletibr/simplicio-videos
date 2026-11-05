from __future__ import annotations

import errno
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


class _FakeListener:
    """Stands in for the socket generate reserves: sockets are blocked in unit tests."""

    def __init__(self, port):
        self.port = port

    def fileno(self):
        return 99

    def getsockname(self):
        return ("127.0.0.1", self.port)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _no_git_and_no_real_sockets(monkeypatch):
    """generate asks git for the checkout's HEAD and reserves a loopback port: unit tests do neither for real."""
    def not_a_checkout(*a, cwd=None):
        raise tools.ToolError("not a repository")
    monkeypatch.setattr(tools, "_git", not_a_checkout)
    monkeypatch.setattr(moneyprinter, "_listen_socket", lambda port: _FakeListener(port or 45678), raising=False)


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

    def not_a_checkout(*a, cwd=None):  # the stand-in checkout is not a repository: the pin check has nothing to compare
        raise tools.ToolError("not a repository")

    monkeypatch.setattr("subprocess.call", fake)
    monkeypatch.setattr(tools, "_git", not_a_checkout)
    return recorded, fail


@pytest.fixture
def server(monkeypatch):
    """Fakes the long-running server processes. Records how each is started and which signal reaches each group.
    state.interrupt: the next sleep in the supervision loop raises KeyboardInterrupt (Ctrl+C on this process).
    state.exit_codes: None = every process exits 0 once the loop has slept once; a dict = only those processes
    (index -> exit code) exit, the others keep running."""
    state = SimpleNamespace(started=[], signals=[], interrupt=False, ignore_sigint=False, term_handler=None,
                            hup_handler=None, exit_codes=None, slept=0, stop_handlers=[], wait_interrupts=0)

    class Proc:
        def __init__(self, cmd, cwd=None, env=None, start_new_session=False, **kwargs):
            self.cmd, self.cwd, self.env, self.start_new_session = cmd, cwd, env, start_new_session
            self.kwargs = kwargs
            self.pid = 4242 + len(state.started)
            self.index = len(state.started)
            self.returncode = None
            state.started.append(self)

        def wait(self, timeout=None):
            if timeout is not None:
                state.stop_handlers.append(tuple(signal.getsignal(n) for n in _STOP_SIGNALS))
                if state.wait_interrupts:
                    state.wait_interrupts -= 1
                    raise KeyboardInterrupt  # a second signal arrives while the group is being stopped
            if timeout is not None and state.ignore_sigint and any(sig == signal.SIGINT for _, sig in state.signals):
                raise subprocess.TimeoutExpired(self.cmd, timeout)
            self.returncode = 0 if self.returncode is None else self.returncode
            return self.returncode

        def poll(self):
            if self.returncode is None and state.slept:
                if state.exit_codes is None:
                    pass
                elif self.index in state.exit_codes:
                    self.returncode = state.exit_codes[self.index]
            return self.returncode

    def fake_sleep(seconds):
        state.term_handler = signal.getsignal(signal.SIGTERM)
        if hasattr(signal, "SIGHUP"):
            state.hup_handler = signal.getsignal(signal.SIGHUP)
        if state.interrupt or (state.exit_codes is None and state.slept):
            state.interrupt = False
            raise KeyboardInterrupt
        state.slept += 1

    monkeypatch.setattr("subprocess.Popen", Proc)
    monkeypatch.setattr(moneyprinter.time, "sleep", fake_sleep)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: state.signals.append((pgid, sig)))
    return state


_STOP_SIGNALS = tuple(getattr(signal, n) for n in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, n))


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
    with pytest.raises(moneyprinter.MoneyPrinterError, match="clone\\|setup\\|serve\\|generate\\|run\\|where\\|status"):
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
    started = []
    for args in (["where"], ["status"], ["setup"], ["serve"], ["serve", "--api", "--lan"], ["--help"]):
        server.started.clear()
        moneyprinter.run_moneyprinter(args)
        started += server.started
    assert len(started) == 2  # the WebUI, then the API: the checks below must have something to check
    out = capsys.readouterr()
    for stream in (out.out, out.err):
        assert FAKE_KEY not in stream and FAKE_KEY_2 not in stream
    for p in started:  # nor does it hand a key to the server through the command line or the environment
        assert FAKE_KEY not in " ".join(p.cmd) and FAKE_KEY_2 not in " ".join(p.cmd)
        env_text = json.dumps(p.env, default=str)  # the whole environment, PATH included
        assert FAKE_KEY not in env_text and FAKE_KEY_2 not in env_text


# ---- config_report: valid TOML forms (M1) -------------------------------------------------------------------------

@pytest.mark.parametrize("text, name, filled", [
    ('app.openai_api_key = "S3CRET"\n', "app.openai_api_key", True),        # dotted key
    ('[app]\n"openai_api_key" = "S3CRET"\n', "app.openai_api_key", True),   # quoted key
    ('llm = { api_key = "S3CRET" }\n', "llm.api_key", True),                # inline table
    ('[app]\nOPENAI_API_KEY = "S3CRET"\nApiKey = "S3CRET"\n', "app.OPENAI_API_KEY", True),
    ('[aws]\naccess_key_id = "S3CRET"\n', "aws.access_key_id", True),
    ('[app]\napi_key = """"""\n', "app.api_key", False),                   # empty multi-line string
    ('[app]\napi_key = " "\n', "app.api_key", False),                      # blank is not filled
    ('[app]\nkeys_x = 1\npexels_api_keys = ["", " "]\n', "app.pexels_api_keys", False),
    ('[[providers]]\napi_key = "S3CRET"\n', "providers.api_key", True),    # array of tables: right name
    ('[app.sub]\nsecret = "S3CRET"\n', "app.sub.secret", True),
])
def test_config_report_reads_every_valid_toml_form(tmp_path, text, name, filled):
    f = tmp_path / "c.toml"
    f.write_text(text)
    rep = moneyprinter.config_report(f)
    assert rep["keys"].get(name) is filled, rep
    assert "S3CRET" not in json.dumps(rep)


def test_config_report_does_not_invent_a_name_from_inside_a_value(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[app]\nnote = """\nleak_token = x\n"""\napi_key = "S3CRET"\n')
    assert moneyprinter.config_report(f)["keys"] == {"app.api_key": True}


def test_config_report_unclosed_list_does_not_swallow_the_next_keys(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[app]\npexels_api_keys = ["x"\nopenai_api_key = "S3CRET"\n')  # invalid TOML: line fallback
    keys = moneyprinter.config_report(f)["keys"]
    assert keys.get("app.openai_api_key") is True


# ---- config.toml is private (M2) ----------------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="modo POSIX")
def test_setup_creates_the_config_readable_only_by_the_owner(checkout, calls):
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    assert (checkout / "config.toml").stat().st_mode & 0o777 == 0o600


# ---- setup checks the pin (M5) and turns file errors into clear ones (M6, M7) --------------------------------------

def test_setup_warns_when_the_checkout_is_not_at_the_pinned_commit(checkout, calls, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "a" * 40)
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    err = capsys.readouterr().err
    assert "commit fixado" in err and tools.get("moneyprinter").ref[:12] in err


def test_setup_is_quiet_when_the_checkout_is_at_the_pin(checkout, calls, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: tools.pinned_ref(tools.get("moneyprinter")))
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    assert "commit fixado" not in capsys.readouterr().err


def test_setup_without_the_example_config_is_a_clear_error(checkout, calls):
    (checkout / "config.example.toml").unlink()
    (checkout / "config.example.toml").mkdir()  # still there for the checkout lookup, but not a readable file
    with pytest.raises(moneyprinter.MoneyPrinterError, match="config"):
        moneyprinter.run_moneyprinter(["setup"])


def test_setup_with_a_file_where_the_data_dir_should_be_is_a_clear_error(checkout, calls, tmp_path):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "moneyprinter-data").write_text("")
    with pytest.raises(moneyprinter.MoneyPrinterError):
        moneyprinter.run_moneyprinter(["setup"])


def test_serve_with_a_missing_interpreter_is_a_clear_error(checkout, venv, server, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr("subprocess.Popen", boom)
    with pytest.raises(moneyprinter.MoneyPrinterError, match="não consegui iniciar"):
        moneyprinter.run_moneyprinter(["serve"])


@pytest.mark.parametrize("args", [["clone", "a", "b"], ["where", "x"], ["status", "x"]])
def test_extra_arguments_are_an_error_not_ignored(checkout, args):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="argumento"):
        moneyprinter.run_moneyprinter(args)


def test_setup_with_an_existing_venv_does_not_need_python_3_11(checkout, venv, calls, monkeypatch):
    monkeypatch.setattr(moneyprinter, "MIN_PYTHON", (99, 0))
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert moneyprinter.run_moneyprinter(["setup"]) == 0


def test_cli_help_of_moneyprinter_lists_host():
    assert "serve [--webui] [--api] [--lan] [--host H]" in (ROOT / "src" / "simplicio_video" / "cli.py").read_text()


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
    # the one that exited is swept too (a helper it left behind), the other is stopped
    assert server.signals == [(4242, signal.SIGKILL), (4243, signal.SIGINT), (4243, signal.SIGKILL)]


def test_serve_sigterm_is_handled_like_ctrl_c_and_restored_afterwards(checkout, venv, server):
    before = signal.getsignal(signal.SIGTERM)
    assert moneyprinter.run_moneyprinter(["serve"]) == 0
    handler = server.term_handler
    assert callable(handler) and handler is not before
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGTERM, None)
    assert signal.getsignal(signal.SIGTERM) is before


def test_serve_a_second_signal_during_the_stop_does_not_leave_a_server_running(checkout, venv, server):
    # Ctrl+C twice (or SIGTERM then Ctrl+C): the first stop wait is cut short, yet both groups must be stopped
    server.interrupt = True
    server.wait_interrupts = 1
    assert moneyprinter.run_moneyprinter(["serve", "--webui", "--api"]) == 0
    stopped = {pgid for pgid, sig in server.signals if sig == signal.SIGKILL}
    assert stopped == {4242, 4243}
    assert (4243, signal.SIGINT) in server.signals


def test_serve_ignores_further_signals_while_stopping_and_restores_the_handlers(checkout, venv, server):
    before = [signal.getsignal(n) for n in _STOP_SIGNALS]
    server.interrupt = True
    assert moneyprinter.run_moneyprinter(["serve", "--webui", "--api"]) == 0
    assert server.stop_handlers and all(h == (signal.SIG_IGN,) * len(_STOP_SIGNALS) for h in server.stop_handlers)
    assert [signal.getsignal(n) for n in _STOP_SIGNALS] == before


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="sem SIGHUP nesta plataforma")
def test_serve_sighup_stops_the_servers_like_ctrl_c_and_is_restored(checkout, venv, server):
    before = signal.getsignal(signal.SIGHUP)
    assert moneyprinter.run_moneyprinter(["serve"]) == 0
    handler = server.hup_handler
    assert callable(handler) and handler is not before  # the default action would end the parent and orphan the servers
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGHUP, None)
    assert signal.getsignal(signal.SIGHUP) is before


def test_serve_names_the_server_that_exited_by_itself_and_never_returns_0(checkout, venv, server, capsys):
    server.exit_codes = {1: 0}  # the API ends by itself with 0 (e.g. port taken and handled): not a requested stop
    assert moneyprinter.run_moneyprinter(["serve", "--webui", "--api"]) == 1
    err = capsys.readouterr().err
    assert "API" in err and "saiu" in err and "parando" in err


def test_serve_a_server_killed_by_a_signal_returns_a_positive_code(checkout, venv, server, capsys):
    server.exit_codes = {0: -9}
    assert moneyprinter.run_moneyprinter(["serve", "--webui", "--api"]) == 9 + 128
    assert "WebUI" in capsys.readouterr().err


# Upstream at the pinned commit (app/asgi.py): CORS is closed by default (CORS_ALLOWED_ORIGINS empty = same origin
# only), so a page in the browser cannot read the API. With app.api_key empty the API still has no login at all, for
# any other program on this computer, a DNS-rebinding page, or (with --lan) the network.

def test_serve_api_without_an_api_key_warns_clearly_and_still_starts(checkout, venv, server, capsys):
    (checkout / "config.toml").write_text(CONFIG_WITH_KEYS)  # app.api_key = ""
    assert moneyprinter.run_moneyprinter(["serve", "--api"]) == 0
    err = capsys.readouterr().err
    assert "app.api_key" in err and "sem chave" in err and "LLM" in err
    assert len(server.started) == 1


def test_serve_api_without_a_config_file_warns_too(checkout, venv, server, capsys):
    assert moneyprinter.run_moneyprinter(["serve", "--api"]) == 0
    assert "app.api_key" in capsys.readouterr().err


def test_serve_api_with_an_api_key_does_not_warn_and_never_prints_it(checkout, venv, server, capsys):
    (checkout / "config.toml").write_text(f'[app]\napi_key = "{FAKE_KEY}"\n')
    assert moneyprinter.run_moneyprinter(["serve", "--api"]) == 0
    out = capsys.readouterr()
    assert "sem chave" not in out.err
    assert FAKE_KEY not in out.out and FAKE_KEY not in out.err


def test_serve_webui_only_does_not_warn_about_the_api_key(checkout, venv, server, capsys):
    assert moneyprinter.run_moneyprinter(["serve"]) == 0
    assert "app.api_key" not in capsys.readouterr().err


def test_serve_api_refuses_open_cors_without_an_api_key(checkout, venv, server, monkeypatch):
    # the combination upstream itself flags: any web page could then call the API with the user's paid keys
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:8501, *")
    with pytest.raises(moneyprinter.MoneyPrinterError, match="CORS_ALLOWED_ORIGINS"):
        moneyprinter.run_moneyprinter(["serve", "--api"])
    assert server.started == []


def test_serve_api_accepts_open_cors_when_the_api_key_is_filled(checkout, venv, server, monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    (checkout / "config.toml").write_text(f'[app]\napi_key = "{FAKE_KEY}"\n')
    assert moneyprinter.run_moneyprinter(["serve", "--api"]) == 0


def test_help_says_the_api_has_no_login_without_an_api_key():
    text = moneyprinter.USAGE
    assert "app.api_key" in text and "CORS_ALLOWED_ORIGINS" in text


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


@pytest.mark.parametrize("args", ["serve", "serve --lan", "serve --api", "setup", "", "--help"])
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


# ---- #144: porta da API configurável e o comando generate (roda por trás e traz o MP4) ---------------------------

def test_serve_api_port_is_configurable_and_defaults_to_8080(checkout, venv, server, capsys):
    assert moneyprinter.run_moneyprinter(["serve", "--api", "--api-port", "9090"]) == 0
    cmd = server.started[0].cmd
    assert cmd[cmd.index("--port") + 1] == "9090"
    assert "http://127.0.0.1:9090/docs" in capsys.readouterr().out
    server.started.clear()
    assert moneyprinter.run_moneyprinter(["serve", "--api"]) == 0
    cmd = server.started[0].cmd
    assert cmd[cmd.index("--port") + 1] == "8080"


@pytest.mark.parametrize("value", ["abc", "0", "1023", "70000", "80.5"])
def test_serve_api_port_must_be_an_unprivileged_port_number(checkout, venv, server, value):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="entre 1024 e 65535"):
        moneyprinter.run_moneyprinter(["serve", "--api", "--api-port", value])
    assert server.started == []


def test_help_lists_generate_and_the_api_port():
    assert "generate" in moneyprinter.USAGE and "--api-port" in moneyprinter.USAGE


def test_generate_request_is_local_only_and_carries_no_key():
    body = moneyprinter.build_video_request(
        script="Olá, este é um teste.", voice="pt-BR-FranciscaNeural-Female", aspect="9:16",
        materials=["clip.mp4"], subject="teste")
    assert body["video_source"] == "local"
    assert body["video_materials"] == [{"provider": "local", "url": "clip.mp4"}]
    assert body["video_script"] == "Olá, este é um teste."
    assert body["voice_name"] == "pt-BR-FranciscaNeural-Female"
    assert body["video_aspect"] == "9:16"
    assert body["subtitle_enabled"] is False
    assert not any("key" in name.lower() for name in body)


def test_write_result_copies_the_video_and_records_its_hash(tmp_path):
    import hashlib
    src = tmp_path / "src" / "final-1.mp4"
    src.parent.mkdir()
    src.write_bytes(b"video bytes")
    out = tmp_path / "out"
    meta = moneyprinter.write_result(out, task_id="t1", video=src, request={"voice": "x"}, materials=[], elapsed=1.5)
    assert (out / "moneyprinter-t1.mp4").read_bytes() == b"video bytes"
    assert meta["sha256"] == hashlib.sha256(b"video bytes").hexdigest()
    assert meta["bytes"] == len(b"video bytes")
    manifest = json.loads((out / "moneyprinter-t1.json").read_text())
    assert manifest["schema"] == "simplicio.moneyprinter-result/v1"
    assert manifest["sha256"] == meta["sha256"]
    assert manifest["pinned_commit"] == "4b7b9657647bdb149715354269eec7e4dbad4a7a"


def test_wait_for_task_returns_when_complete_and_fails_loudly_on_failure():
    replies = iter([
        (200, {"data": {"task_id": "t1", "state": 0, "progress": 10}}),
        (200, {"data": {"task_id": "t1", "state": 1, "progress": 100, "videos": ["/tasks/t1/final-1.mp4"]}}),
    ])
    got = moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: next(replies),
                                     sleep=lambda s: None, max_polls=5)
    assert got["videos"] == ["/tasks/t1/final-1.mp4"]
    failing = lambda url: (200, {"data": {"task_id": "t1", "state": -1, "error": "boom", "failed_stage": "audio"}})
    with pytest.raises(moneyprinter.MoneyPrinterError, match="boom"):
        moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=failing, sleep=lambda s: None, max_polls=5)
    waiting = lambda url: (200, {"data": {"task_id": "t1", "state": 0, "progress": 1}})
    with pytest.raises(moneyprinter.MoneyPrinterError, match="tempo"):
        moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=waiting, sleep=lambda s: None, max_polls=3)


@pytest.mark.parametrize("args", [
    ["generate", "--out", "x"],
    ["generate", "--script", "s.txt", "--out", "x"],
    ["generate", "--script", "s.txt", "--material", "c.mp4"],
])
def test_generate_needs_script_material_and_out(checkout, venv, server, args):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--script, --material e --out"):
        moneyprinter.run_moneyprinter(args)
    assert server.started == []


def test_generate_without_a_venv_points_to_setup(checkout, server, tmp_path):
    script = tmp_path / "r.txt"
    script.write_text("x")
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    with pytest.raises(moneyprinter.MoneyPrinterError, match="ambiente não preparado"):
        moneyprinter.run_moneyprinter(["generate", "--script", str(script), "--material", str(clip),
                                       "--out", str(tmp_path / "o")])
    assert server.started == []


def test_generate_with_a_missing_material_fails_before_starting_the_api(checkout, venv, server, tmp_path):
    script = tmp_path / "r.txt"
    script.write_text("x")
    with pytest.raises(moneyprinter.MoneyPrinterError, match="material não encontrado"):
        moneyprinter.run_moneyprinter(["generate", "--script", str(script), "--material", str(tmp_path / "nope.mp4"),
                                       "--out", str(tmp_path / "o")])
    assert server.started == []


def _generate_fakes(monkeypatch, state_reply, sent):
    monkeypatch.setattr(moneyprinter, "_request", _api_request(final_state=state_reply, sent=sent))


def test_generate_runs_the_api_behind_the_scenes_and_brings_the_mp4_back(
        checkout, venv, server, monkeypatch, tmp_path, capsys):
    import hashlib
    script = tmp_path / "roteiro.txt"
    script.write_text("Olá, este é um teste de voz.")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"material")
    out = tmp_path / "out"
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video bytes")
    sent = {}
    _generate_fakes(monkeypatch, {"task_id": "t1", "state": 1, "progress": 100, "videos": ["/tasks/t1/final-1.mp4"]}, sent)
    rc = moneyprinter.run_moneyprinter(["generate", "--script", str(script), "--material", str(clip),
                                        "--out", str(out), "--api-port", "45678", "--json"])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["task_id"] == "t1"
    assert result["sha256"] == hashlib.sha256(b"video bytes").hexdigest()
    assert (out / "moneyprinter-t1.mp4").read_bytes() == b"video bytes"
    assert sent["body"]["video_materials"] == [{"provider": "local", "url": "stored-clip.mp4"}]
    assert sent["body"]["video_script"] == "Olá, este é um teste de voz."
    cmd = server.started[0].cmd
    assert cmd[cmd.index("--fd") + 1] == "99" and server.started[0].kwargs["pass_fds"] == (99,)
    assert "--port" not in cmd and "--host" not in cmd  # the socket is the address: no second bind
    assert server.signals  # the API group is stopped at the end, never left running


def test_generate_stops_the_api_when_the_task_fails(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script = tmp_path / "roteiro.txt"
    script.write_text("x")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"material")
    _generate_fakes(monkeypatch, {"task_id": "t1", "state": -1, "error": "no valid local video materials were found",
                                  "failed_stage": "materials"}, {})
    rc = moneyprinter.run_moneyprinter(["generate", "--script", str(script), "--material", str(clip),
                                        "--out", str(tmp_path / "o"), "--api-port", "45678"])
    assert rc == 1
    assert "no valid local video materials were found" in capsys.readouterr().err
    assert server.signals
    assert not (tmp_path / "o" / "moneyprinter-t1.mp4").exists()


# ---- revisão independente do PR #145: bloqueantes e pontos a corrigir ----------------------------------------------

def _generate_inputs(tmp_path):
    script = tmp_path / "roteiro.txt"
    script.write_text("Olá, este é um teste.")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"material bytes")
    return script, clip


def _generate_argv(script, clip, out, port="45678", *extra):
    return ["generate", "--script", str(script), "--material", str(clip), "--out", str(out), "--api-port", port, *extra]


def _api_request(final_state=None, posted=None, material_status=200, on_task=None, port_busy=False, sent=None):
    """Fake da API: /openapi.json de MoneyPrinterTurbo, upload, POST e tarefa concluída (ou o estado dado)."""
    state = final_state or {"task_id": "t1", "state": 1, "progress": 100, "videos": ["/tasks/t1/final-1.mp4"]}
    calls = {"openapi": 0}

    def fake(method, url, body=None, headers=None, timeout=30):
        if posted is not None:
            posted.append((method, url, body))
        if sent is not None:
            sent.setdefault("seen", []).append((url, (headers or {}).get("x-api-key")))
        if url.endswith("/openapi.json"):
            calls["openapi"] += 1
            if port_busy or calls["openapi"] > 1:  # free until our own API starts answering
                return 200, {"info": {"title": "MoneyPrinterTurbo"}}
            return 0, None
        if url.endswith("/api/v1/video_materials"):
            if on_task:
                on_task("upload", body)
            return material_status, ({"status": 200, "data": {"file": "stored-clip.mp4"}} if material_status == 200 else None)
        if url.endswith("/api/v1/videos"):
            if sent is not None:
                sent["body"] = json.loads(body)
                sent["headers"] = headers
            return 200, {"status": 200, "data": {"task_id": "t1"}}
        if url.endswith("/api/v1/tasks/t1"):
            if on_task:
                on_task("task", None)
            return 200, {"status": 200, "data": state}
        raise AssertionError(f"unexpected request: {method} {url}")
    return fake


def test_generate_refuses_a_port_someone_else_holds(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    posted = []

    def busy(port):
        raise OSError(errno.EADDRINUSE, "Address already in use")
    monkeypatch.setattr(moneyprinter, "_listen_socket", busy)
    monkeypatch.setattr(moneyprinter, "_request", _api_request(posted=posted))
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o"))
    assert rc == 1
    assert server.started == []  # no API started, nothing requested from that port
    assert posted == []
    assert "já está em uso" in capsys.readouterr().err


def test_generate_reports_a_child_that_dies_while_waiting(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    server.exit_codes = {0: 3}  # the API process exits with 3 once the loop has slept
    monkeypatch.setattr(moneyprinter, "_request", lambda method, url, body=None, headers=None, timeout=30: (0, None))
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "saiu com código 3" in err and "veja a saída acima" in err
    assert server.signals  # the group is always stopped (no leftover process)


def test_loopback_requests_ignore_the_proxy_environment(monkeypatch):
    import urllib.request
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("http_proxy", "http://proxy.invalid:3128")
    # the default opener has a ProxyHandler that reads HTTP_PROXY; ours must not have any
    assert not any(isinstance(h, urllib.request.ProxyHandler) for h in moneyprinter._OPENER.handlers)


@pytest.mark.parametrize("uri", [
    "/tasks/../secret.txt", "/tasks/%2e%2e/secret.txt", "/tasks/%2E%2E%2Fsecret.txt", "/etc/passwd",
    "/tasks//etc/passwd", "http://example.com/tasks/t1/final-1.mp4", "/tasks/", "/TASKS/t1/final-1.mp4",
    "/tasks/t1/\x00final.mp4",
])
def test_task_file_refuses_anything_outside_storage_tasks(tmp_path, uri):
    with pytest.raises(moneyprinter.MoneyPrinterError):
        moneyprinter._task_file(tmp_path, uri)


def test_task_file_accepts_the_output_of_a_task(tmp_path):
    assert moneyprinter._task_file(tmp_path, "/tasks/t1/final-1.mp4") == \
        (tmp_path / "storage" / "tasks" / "t1" / "final-1.mp4").resolve()


def test_task_file_refuses_a_symlink_that_leaves_the_task_folder(tmp_path):
    tasks = tmp_path / "storage" / "tasks"
    tasks.mkdir(parents=True)
    (tmp_path / "secret.txt").write_text("x")
    (tasks / "t1").symlink_to(tmp_path)
    with pytest.raises(moneyprinter.MoneyPrinterError):
        moneyprinter._task_file(tmp_path, "/tasks/t1/secret.txt")


def test_generate_checks_the_output_folder_before_paying_for_the_task(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    blocker = tmp_path / "um-arquivo"
    blocker.write_text("x")
    posted = []
    monkeypatch.setattr(moneyprinter, "_request", _api_request(posted=posted))
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, blocker))
    assert rc == 1
    assert server.started == [] and posted == []
    assert "pasta de saída" in capsys.readouterr().err


def test_generate_stops_the_api_when_an_upload_fails(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    monkeypatch.setattr(moneyprinter, "_request", _api_request(material_status=500))
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o"))
    assert rc == 1
    assert "falhou (HTTP 500)" in capsys.readouterr().err
    assert server.signals


def test_generate_applies_the_same_api_key_guard_as_serve(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o"))
    assert rc == 1
    assert "CORS_ALLOWED_ORIGINS" in capsys.readouterr().err
    assert server.started == []


def test_generate_never_prints_or_records_a_key_from_the_config(checkout, venv, server, monkeypatch, tmp_path, capsys):
    (checkout / "config.toml").write_text(CONFIG_WITH_KEYS)
    script, clip = _generate_inputs(tmp_path)
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video")
    monkeypatch.setattr(moneyprinter, "_request", _api_request())
    out = tmp_path / "o"
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, out, "45678", "--json"))
    captured = capsys.readouterr()
    assert rc == 0
    assert FAKE_KEY not in captured.out + captured.err and FAKE_KEY_2 not in captured.out + captured.err
    recorded = (out / "moneyprinter-t1.json").read_text()
    assert FAKE_KEY not in recorded and FAKE_KEY_2 not in recorded


def test_material_hash_is_the_one_of_the_bytes_that_were_sent(checkout, venv, server, monkeypatch, tmp_path, capsys):
    import hashlib
    script, clip = _generate_inputs(tmp_path)
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video")
    uploads = []

    def on_task(stage, body):
        if stage == "upload":
            uploads.append(body)
        else:  # the file changes after the upload and before the manifest is written
            clip.write_bytes(b"changed after upload")

    monkeypatch.setattr(moneyprinter, "_request", _api_request(on_task=on_task))
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678", "--json"))
    assert rc == 0
    meta = json.loads(capsys.readouterr().out)
    assert b"material bytes" in uploads[0]
    assert meta["materials"][0]["sha256"] == hashlib.sha256(b"material bytes").hexdigest()


def test_manifest_records_the_checkout_head_that_actually_ran(tmp_path):
    src = tmp_path / "f.mp4"
    src.write_bytes(b"x")
    moneyprinter.write_result(tmp_path / "o", task_id="t1", video=src, request={}, materials=[], elapsed=0,
                              checkout_head="abc123")
    assert json.loads((tmp_path / "o" / "moneyprinter-t1.json").read_text())["checkout_head"] == "abc123"


def test_manifest_records_the_voice_the_request_used(tmp_path):
    src = tmp_path / "f.mp4"
    src.write_bytes(b"x")
    meta = moneyprinter.write_result(tmp_path / "o", task_id="t1", video=src, request={"voice_name": "voz-x"},
                                     materials=[], elapsed=0)
    assert meta["voice"] == "voz-x"


@pytest.mark.parametrize("args", [
    ["serve", "--api-port", "9090"],  # the port means nothing without the API: refuse instead of ignoring it
    ["serve", "--webui", "--api", "--api-port", "8501"],  # collides with the WebUI port
])
def test_serve_api_port_is_refused_when_it_cannot_apply(checkout, venv, server, args):
    with pytest.raises(moneyprinter.MoneyPrinterError):
        moneyprinter.run_moneyprinter(args)
    assert server.started == []


def test_api_port_with_thousands_of_digits_is_a_clean_error():
    with pytest.raises(moneyprinter.MoneyPrinterError, match="entre 1024 e 65535"):
        moneyprinter._port("9" * 5000)


def test_wait_for_task_stops_at_an_unknown_task():
    sleeps = []
    with pytest.raises(moneyprinter.MoneyPrinterError, match="não encontrada"):
        moneyprinter.wait_for_task("http://127.0.0.1:1", "t9", get=lambda url: (404, {"message": "task not found"}),
                                   sleep=sleeps.append, max_polls=900)
    assert sleeps == []


def test_generate_reads_the_mp4_where_the_checkout_writes_it(checkout, venv, server, monkeypatch, tmp_path, capsys):
    # MONEYPRINTER_DATA_DIR now points elsewhere: the upstream still writes into checkout/storage (linked by setup)
    monkeypatch.setenv("MONEYPRINTER_DATA_DIR", str(tmp_path / "outra-pasta"))
    py = moneyprinter.venv_python()
    py.parent.mkdir(parents=True)
    py.write_text("")
    script, clip = _generate_inputs(tmp_path)
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video")
    monkeypatch.setattr(moneyprinter, "_request", _api_request())
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678", "--json"))
    assert rc == 0
    assert (tmp_path / "o" / "moneyprinter-t1.mp4").read_bytes() == b"video"


def test_the_api_log_goes_to_stderr_so_the_json_stdout_stays_clean(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video")
    monkeypatch.setattr(moneyprinter, "_request", _api_request())
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678", "--json"))
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["task_id"] == "t1"  # stdout is only the JSON object
    assert server.started[0].kwargs.get("stdout") == 2  # the server's own output goes to stderr (fd 2)


def test_a_non_http_service_on_the_port_is_a_clean_error_not_a_traceback(monkeypatch):
    import http.client

    class Broken:
        def open(self, req, timeout=None):
            raise http.client.BadStatusLine("RESP")
    monkeypatch.setattr(moneyprinter, "_OPENER", Broken())
    assert moneyprinter._request("GET", "http://127.0.0.1:1/openapi.json") == (0, None)


@pytest.mark.parametrize("value", ["\uff18\uff10\uff18\uff10", "08080 ", "+8080"])
def test_api_port_accepts_only_ascii_digits(value):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="entre 1024 e 65535"):
        moneyprinter._port(value)


def test_generate_sends_the_api_key_from_config_to_loopback_only_and_never_prints_it(
        checkout, venv, server, monkeypatch, tmp_path, capsys):
    (checkout / "config.toml").write_text(f'[app]\napi_key = "{FAKE_KEY}"\n')
    script, clip = _generate_inputs(tmp_path)
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video")
    sent = {}
    monkeypatch.setattr(moneyprinter, "_request", _api_request(sent=sent))
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678", "--json"))
    captured = capsys.readouterr()
    assert rc == 0
    assert sent["headers"]["x-api-key"] == FAKE_KEY  # the API requires it once app.api_key is filled
    assert FAKE_KEY not in captured.out + captured.err
    assert FAKE_KEY not in (tmp_path / "o" / "moneyprinter-t1.json").read_text()


def test_checkout_head_is_not_read_from_a_parent_repository(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "deadbeef")
    assert moneyprinter._checkout_head(tmp_path) is None  # no .git here: never ask git (it would find the parent's)
    assert calls == []


def test_every_call_to_the_api_carries_the_key_when_app_api_key_is_filled(
        checkout, venv, server, monkeypatch, tmp_path, capsys):
    (checkout / "config.toml").write_text(f'[app]\napi_key = "{FAKE_KEY}"\n')
    script, clip = _generate_inputs(tmp_path)
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video")
    sent = {}
    monkeypatch.setattr(moneyprinter, "_request", _api_request(sent=sent))
    assert moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678")) == 0
    urls = [u for u, _ in sent["seen"]]
    assert any(u.endswith("/openapi.json") for u in urls) and any(u.endswith("/api/v1/tasks/t1") for u in urls)
    assert all(key == FAKE_KEY for _, key in sent["seen"]), sent["seen"]  # readiness, upload, POST and polling
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out + captured.err


def test_an_unreadable_config_with_a_key_is_an_error_not_a_silent_missing_key(
        checkout, venv, server, monkeypatch, tmp_path, capsys):
    (checkout / "config.toml").write_text(f'[app]\napi_key = "{FAKE_KEY}"\n[quebrado\n')
    script, clip = _generate_inputs(tmp_path)
    monkeypatch.setattr(moneyprinter, "_request", _api_request())
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678"))
    err = capsys.readouterr().err
    assert rc == 1 and "config.toml" in err
    assert FAKE_KEY not in err and server.started == []


def test_api_key_refuses_control_and_non_latin1_characters_without_echoing_them(tmp_path):
    (tmp_path / "config.toml").write_text('[app]\napi_key = """SEGREDO-1\nSEGREDO-2"""\n')
    with pytest.raises(moneyprinter.MoneyPrinterError) as multiline:
        moneyprinter._api_key(tmp_path)
    assert "SEGREDO" not in str(multiline.value)
    (tmp_path / "config.toml").write_text('[app]\napi_key = "chave-\u20ac-SEGREDO"\n')
    with pytest.raises(moneyprinter.MoneyPrinterError) as not_latin1:
        moneyprinter._api_key(tmp_path)
    assert "SEGREDO" not in str(not_latin1.value)


def test_api_key_of_an_invalid_config_is_an_error_only_when_a_key_is_there(tmp_path):
    (tmp_path / "config.toml").write_text(f'[app]\napi_key = "{FAKE_KEY}"\n[quebrado\n')
    with pytest.raises(moneyprinter.MoneyPrinterError) as e:
        moneyprinter._api_key(tmp_path)
    assert FAKE_KEY not in str(e.value)
    (tmp_path / "config.toml").write_text("[quebrado\n")
    assert moneyprinter._api_key(tmp_path) is None


def test_an_http_error_whose_body_cannot_be_read_still_returns_its_status(monkeypatch):
    import http.client
    import urllib.error

    class Body:
        def read(self, *a):
            raise http.client.IncompleteRead(b"")

        def close(self):
            pass

    class Opener:
        def open(self, req, timeout=None):
            raise urllib.error.HTTPError("http://127.0.0.1:1/x", 500, "boom", {}, Body())
    monkeypatch.setattr(moneyprinter, "_OPENER", Opener())
    assert moneyprinter._request("GET", "http://127.0.0.1:1/x") == (500, None)


def test_loopback_requests_do_not_follow_redirects():
    assert any(isinstance(h, moneyprinter._NoRedirect) for h in moneyprinter._OPENER.handlers)
    assert moneyprinter._NoRedirect().redirect_request(None, None, 302, "Found", {}, "http://evil.example/") is None


def test_a_busy_default_port_says_so_without_printing_none(checkout, venv, server, monkeypatch, tmp_path, capsys):
    def busy(port):
        raise OSError(errno.EADDRINUSE, "Address already in use")
    monkeypatch.setattr(moneyprinter, "_listen_socket", busy)
    script, clip = _generate_inputs(tmp_path)
    rc = moneyprinter.run_moneyprinter(["generate", "--script", str(script), "--material", str(clip),
                                        "--out", str(tmp_path / "o")])
    err = capsys.readouterr().err
    assert rc == 1 and "já está em uso" in err and "None" not in err


def test_without_api_port_the_api_uses_the_port_the_socket_got(checkout, venv, server, monkeypatch, tmp_path):
    monkeypatch.setattr(moneyprinter, "_listen_socket", lambda port: _FakeListener(54321))
    script, clip = _generate_inputs(tmp_path)
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video")
    sent = {}
    monkeypatch.setattr(moneyprinter, "_request", _api_request(sent=sent))
    rc = moneyprinter.run_moneyprinter(["generate", "--script", str(script), "--material", str(clip),
                                        "--out", str(tmp_path / "o")])
    assert rc == 0
    assert all(u.startswith("http://127.0.0.1:54321/") for u, _ in sent["seen"])


def test_a_failed_start_closes_the_reserved_socket(checkout, venv, monkeypatch, tmp_path, capsys):
    closed = []

    class Listener(_FakeListener):
        def close(self):
            closed.append(self.port)
    monkeypatch.setattr(moneyprinter, "_listen_socket", lambda port: Listener(port or 45678))

    def cannot_exec(*a, **k):
        raise OSError("no exec")
    monkeypatch.setattr(subprocess, "Popen", cannot_exec)
    script, clip = _generate_inputs(tmp_path)
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678"))
    assert rc == 1 and closed == [45678]
    assert "não consegui iniciar a API" in capsys.readouterr().err


def test_wait_for_task_stops_on_an_unexpected_status_and_keeps_a_dropped_connection_polling():
    sleeps = []
    with pytest.raises(moneyprinter.MoneyPrinterError, match="HTTP 400"):
        moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: (400, None),
                                   sleep=sleeps.append, max_polls=900)
    assert sleeps == []
    replies = iter([(0, None), (200, {"data": {"task_id": "t1", "state": 1, "videos": ["/tasks/t1/f.mp4"]}})])
    got = moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: next(replies),
                                     sleep=sleeps.append, max_polls=5)
    assert got["videos"] == ["/tasks/t1/f.mp4"] and len(sleeps) == 1


def test_generate_needs_python_311_to_read_the_key_it_must_send(checkout, venv, server, monkeypatch, tmp_path):
    monkeypatch.setattr(moneyprinter, "_can_read_toml", lambda: False)
    script, clip = _generate_inputs(tmp_path)
    with pytest.raises(moneyprinter.MoneyPrinterError, match="3.11"):
        moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678"))
    assert server.started == []


def test_api_key_must_be_text(tmp_path):
    (tmp_path / "config.toml").write_text("[app]\napi_key = 12345\n")
    with pytest.raises(moneyprinter.MoneyPrinterError, match="texto"):
        moneyprinter._api_key(tmp_path)


def test_an_unreadable_config_is_a_clean_error(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text('[app]\napi_key = "x"\n')

    def denied(self, *a, **k):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(moneyprinter.Path, "read_text", denied)
    with pytest.raises(moneyprinter.MoneyPrinterError, match="não consegui ler"):
        moneyprinter._api_key(tmp_path)


def test_an_invalid_config_that_names_the_key_never_echoes_it(tmp_path):
    (tmp_path / "config.toml").write_text('[app\napp.api_key = "SEGREDO-X"\n')
    with pytest.raises(moneyprinter.MoneyPrinterError) as e:
        moneyprinter._api_key(tmp_path)
    assert "SEGREDO" not in str(e.value)


def test_without_a_key_no_call_carries_the_header(checkout, venv, server, monkeypatch, tmp_path):
    (checkout / "config.toml").write_text('[app]\napi_key = ""\n')
    script, clip = _generate_inputs(tmp_path)
    final = checkout / "storage" / "tasks" / "t1" / "final-1.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"video")
    sent = {}
    monkeypatch.setattr(moneyprinter, "_request", _api_request(sent=sent))
    assert moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678")) == 0
    assert sent["seen"] and all(key is None for _, key in sent["seen"]), sent["seen"]


def test_a_redirect_from_loopback_is_not_followed_on_the_wire(monkeypatch):
    import io
    import urllib.request
    import urllib.response
    seen = []
    handler = next(h for h in moneyprinter._OPENER.handlers if type(h) is urllib.request.HTTPHandler)

    import email.message

    class Found(io.BytesIO):  # the status line and headers of a 302 to another host, as the transport would hand them over
        code = 302
        msg = "Found"

        def __init__(self, url):
            super().__init__(b"")
            self.url = url
            self.headers = email.message.Message()
            self.headers["Location"] = "http://evil.example/"

        def info(self):
            return self.headers

    def transport(req):  # the wire: a 302 to another host, and nothing else
        seen.append((req.full_url, req.get_header("X-api-key")))
        return Found(req.full_url)
    monkeypatch.setattr(handler, "http_open", transport)
    status, body = moneyprinter._request("GET", "http://127.0.0.1:1/api/v1/tasks/t1", headers={"x-api-key": "k"})
    assert (status, body) == (302, None)
    assert seen == [("http://127.0.0.1:1/api/v1/tasks/t1", "k")]  # one request, to loopback, never to evil.example


def test_wait_for_task_retries_transient_errors_a_few_times_then_gives_up():
    sleeps = []
    replies = iter([(503, None)] * 5 + [(200, {"data": {"task_id": "t1", "state": 1, "videos": ["/tasks/t1/f.mp4"]}})])
    got = moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: next(replies),
                                     sleep=sleeps.append, max_polls=50)
    assert got["videos"] == ["/tasks/t1/f.mp4"] and len(sleeps) == 5
    with pytest.raises(moneyprinter.MoneyPrinterError, match="tentativas"):
        moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: (503, None),
                                   sleep=lambda s: None, max_polls=50)


def test_wait_for_task_refuses_an_unexpected_client_error_at_once():
    sleeps = []
    with pytest.raises(moneyprinter.MoneyPrinterError, match="HTTP 401"):
        moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: (401, None),
                                   sleep=sleeps.append, max_polls=50)
    assert sleeps == []


def test_wait_for_task_refuses_a_200_without_task_data():
    with pytest.raises(moneyprinter.MoneyPrinterError, match="sem dados"):
        moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: (200, None),
                                   sleep=lambda s: None, max_polls=50)


def test_a_deeply_nested_config_is_not_a_recursion_traceback(tmp_path):
    (tmp_path / "config.toml").write_text("x = " + "[" * 3000 + "]" * 3000 + "\n")
    assert moneyprinter._api_key(tmp_path) is None


def test_an_app_table_that_is_not_a_table_with_a_key_is_an_error(tmp_path):
    (tmp_path / "config.toml").write_text('[[app]]\napi_key = "SEGREDO-Y"\n')
    with pytest.raises(moneyprinter.MoneyPrinterError) as e:
        moneyprinter._api_key(tmp_path)
    assert "tabela" in str(e.value) and "SEGREDO" not in str(e.value)


def test_a_non_text_key_does_not_echo_its_value(tmp_path):
    (tmp_path / "config.toml").write_text("[app]\napi_key = 12345678\n")
    with pytest.raises(moneyprinter.MoneyPrinterError) as e:
        moneyprinter._api_key(tmp_path)
    assert "12345678" not in str(e.value)


def test_an_upload_reply_without_a_file_name_is_an_error(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    calls = {"openapi": 0}

    def fake(method, url, body=None, headers=None, timeout=30):
        if url.endswith("/openapi.json"):
            calls["openapi"] += 1
            return (200, {"info": {"title": "MoneyPrinterTurbo"}}) if calls["openapi"] > 1 else (0, None)
        if url.endswith("/api/v1/video_materials"):
            return 200, {"status": 200, "data": "file-x"}  # a string where the data object should be
        raise AssertionError(url)
    monkeypatch.setattr(moneyprinter, "_request", fake)
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678"))
    assert rc == 1 and "resposta sem nome de arquivo" in capsys.readouterr().err


def test_a_task_whose_videos_are_not_a_list_is_an_error(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    monkeypatch.setattr(moneyprinter, "_request", _api_request(final_state={"task_id": "t1", "state": 1,
                                                                             "videos": {"a": 1}}))
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678"))
    assert rc == 1 and "sem vídeo" in capsys.readouterr().err


@pytest.mark.parametrize("status", [0, 429, 500, 502, 503, 599])
def test_transient_statuses_are_retried_up_to_the_limit(status):
    sleeps = []
    replies = iter([(status, None)] * 5 + [(200, {"data": {"task_id": "t1", "state": 1, "videos": ["/tasks/t1/f.mp4"]}})])
    got = moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: next(replies),
                                     sleep=sleeps.append, max_polls=50)
    assert got["videos"] == ["/tasks/t1/f.mp4"] and len(sleeps) == 5


def test_six_transient_errors_in_a_row_stop_even_if_a_later_reply_is_fine():
    replies = iter([(503, None)] * 6 + [(200, {"data": {"task_id": "t1", "state": 1, "videos": ["/tasks/t1/f.mp4"]}})])
    with pytest.raises(moneyprinter.MoneyPrinterError, match="tentativas"):
        moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: next(replies),
                                   sleep=lambda s: None, max_polls=50)


def test_a_good_reply_resets_the_count_of_transient_errors():
    working = {"data": {"task_id": "t1", "state": 0, "progress": 10}}
    done = {"data": {"task_id": "t1", "state": 1, "videos": ["/tasks/t1/f.mp4"]}}
    replies = iter([(503, None)] * 4 + [(200, working)] + [(503, None)] * 5 + [(200, done)])
    got = moneyprinter.wait_for_task("http://127.0.0.1:1", "t1", get=lambda url: next(replies),
                                     sleep=lambda s: None, max_polls=50)
    assert got["videos"] == ["/tasks/t1/f.mp4"]


def test_a_task_whose_video_entry_is_not_text_is_a_clean_error(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    monkeypatch.setattr(moneyprinter, "_request", _api_request(final_state={"task_id": "t1", "state": 1,
                                                                             "videos": [None]}))
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678"))
    err = capsys.readouterr().err
    assert rc == 1 and "saída inválida" in err and "Traceback" not in err


def test_an_upload_reply_with_a_non_text_file_name_says_what_is_wrong(checkout, venv, server, monkeypatch, tmp_path, capsys):
    script, clip = _generate_inputs(tmp_path)
    calls = {"openapi": 0}

    def fake(method, url, body=None, headers=None, timeout=30):
        if url.endswith("/openapi.json"):
            calls["openapi"] += 1
            return (200, {"info": {"title": "MoneyPrinterTurbo"}}) if calls["openapi"] > 1 else (0, None)
        if url.endswith("/api/v1/video_materials"):
            return 200, {"status": 200, "data": {"file": False}}
        raise AssertionError(url)
    monkeypatch.setattr(moneyprinter, "_request", fake)
    rc = moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o", "45678"))
    err = capsys.readouterr().err
    assert rc == 1 and "resposta sem nome de arquivo" in err and "HTTP 200" not in err


# ---- T4: `run` (flags do cli.py do upstream), MCP em segundo plano, progresso do setup -------------------------------

EDGE = "pt-BR-FranciscaNeural-Female"


def _task_stdout(checkout, task_id="t1", videos=("final-1.mp4",), extra=None):
    paths = []
    for name in videos:
        f = checkout / "storage" / "tasks" / task_id / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(f"video {task_id} {name}".encode())
        paths.append(str(f))
    return json.dumps({"task_id": task_id, "result": {"state": 1, "videos": paths, **(extra or {})}})


@pytest.fixture
def spawn(monkeypatch, checkout, venv):
    """Fakes the one place `run` starts the upstream cli.py: records (argv, cwd, env) and answers (rc, stdout)."""
    st = SimpleNamespace(calls=[], rc=0, stdout=None)

    def fake(argv, cwd, env):
        st.calls.append((list(argv), cwd, env))
        out = st.stdout if st.stdout is not None else _task_stdout(checkout)
        return st.rc, out

    monkeypatch.setattr(moneyprinter, "_spawn_cli", fake, raising=False)
    return st


def _run(tmp_path, *upstream, before=()):
    return moneyprinter.run_moneyprinter(["run", "--out", str(tmp_path / "out"), *before, "--", *upstream])


def _local(tmp_path, name="clip.mp4"):
    clip = tmp_path / name
    clip.write_bytes(b"clip")
    return clip


def _free(tmp_path, *extra):
    return ["--video-script", "Olá, mundo.", "--video-source", "local", "--video-materials", str(_local(tmp_path)),
            "--voice-name", EDGE, *extra]


def test_run_passes_the_flags_to_the_upstream_cli_in_the_checkout_and_brings_the_video_back(
        checkout, spawn, tmp_path, capsys):
    import hashlib
    rc = _run(tmp_path, *_free(tmp_path, "--stop-at", "video", "--no-subtitle-enabled"), before=("--json",))
    assert rc == 0
    argv, cwd, _ = spawn.calls[0]
    assert argv[0] == str(moneyprinter.venv_python()) and argv[1] == "cli.py"
    assert Path(cwd) == checkout
    assert "--video-script=Olá, mundo." in argv and "--no-subtitle-enabled" in argv and "--stop-at=video" in argv
    out = json.loads(capsys.readouterr().out)
    assert out["total"] == 1 and out["failed"] == 0
    video = out["tasks"][0]["videos"][0]
    assert video["sha256"] == hashlib.sha256(b"video t1 final-1.mp4").hexdigest()
    assert (tmp_path / "out" / video["video"]).read_bytes() == b"video t1 final-1.mp4"
    assert (tmp_path / "out" / "moneyprinter-t1.json").is_file()


def test_run_makes_relative_paths_absolute_against_the_callers_folder(checkout, spawn, tmp_path, monkeypatch):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "a.mp4").write_bytes(b"a")
    (tmp_path / "w" / "b.mp4").write_bytes(b"b")
    monkeypatch.chdir(tmp_path / "w")
    rc = moneyprinter.run_moneyprinter(["run", "--out", str(tmp_path / "out"), "--", "--video-script", "x",
                                        "--video-source", "local", "--video-materials", "a.mp4,b.mp4",
                                        "--voice-name", EDGE])
    assert rc == 0
    flag = next(a for a in spawn.calls[0][0] if a.startswith("--video-materials="))
    assert flag == f"--video-materials={tmp_path / 'w' / 'a.mp4'},{tmp_path / 'w' / 'b.mp4'}"


@pytest.mark.parametrize("bad", [["--video-script", "x", "--bogus"], ["--video-script", "x", "positional"],
                                 ["--help"], ["-h"], ["--video-script", "x", "--upload-post"],
                                 ["--video-script", "x", "--social-metadata"], ["--video-script"]])
def test_run_refuses_anything_outside_the_closed_flag_list(checkout, spawn, tmp_path, bad):
    with pytest.raises(moneyprinter.MoneyPrinterError):
        _run(tmp_path, *bad)
    assert spawn.calls == []


def test_run_needs_the_double_dash_and_something_after_it(checkout, spawn, tmp_path):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--"):
        moneyprinter.run_moneyprinter(["run", "--out", str(tmp_path / "o"), "--video-script", "x"])
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--"):
        moneyprinter.run_moneyprinter(["run", "--out", str(tmp_path / "o"), "--"])
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--out"):
        moneyprinter.run_moneyprinter(["run", "--", "--video-script", "x"])
    assert spawn.calls == []


def test_run_accepts_the_flag_equals_value_form(checkout, spawn, tmp_path):
    assert _run(tmp_path, "--video-script=-dash start", "--video-source=local",
                f"--video-materials={_local(tmp_path)}", f"--voice-name={EDGE}") == 0
    assert "--video-script=-dash start" in spawn.calls[0][0]


@pytest.mark.parametrize("flag", ["--confirm-wavespeed-charge", "--confirm-seedance-charge", "--confirm-ofox-charge",
                                  "--confirm-metaso-minimax-charge", "--confirm-muapi-charge"])
def test_run_confirm_charge_flags_need_the_engine_yes(checkout, spawn, tmp_path, flag):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, *_free(tmp_path, flag))
    assert spawn.calls == []
    assert _run(tmp_path, *_free(tmp_path, flag), before=("--yes",)) == 0


@pytest.mark.parametrize("source,flag", [("wavespeed", "--confirm-wavespeed-charge"),
                                         ("volcengine_seedance", "--confirm-seedance-charge"),
                                         ("ofox", "--confirm-ofox-charge"),
                                         ("metaso_minimax", "--confirm-metaso-minimax-charge"),
                                         ("muapi", "--confirm-muapi-charge"), ("openai_image", None)])
def test_run_paid_material_sources_need_yes_and_their_own_charge_confirmation(checkout, spawn, tmp_path, source, flag):
    base = ["--video-script", "x", "--video-source", source, "--voice-name", EDGE, "--video-terms", "a,b"]
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, *base, *([flag] if flag else []))
    if flag:
        with pytest.raises(moneyprinter.MoneyPrinterError, match=flag):
            _run(tmp_path, *base, before=("--yes",))
    assert spawn.calls == []
    assert _run(tmp_path, *base, *([flag] if flag else []), before=("--yes",)) == 0


def test_run_script_by_llm_needs_yes(checkout, spawn, tmp_path):
    args = ["--video-subject", "tema", "--video-source", "local", "--video-materials", str(_local(tmp_path)),
            "--voice-name", EDGE]
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, *args)
    assert spawn.calls == []
    assert _run(tmp_path, *args, before=("--yes",)) == 0


@pytest.mark.parametrize("extra", [["--voice-name", "gemini:Kore"], ["--voice-name", "elevenlabs:abc"],
                                   ["--voice-name", "azure-voice-V2"], ["--bgm-type", "sonilo"],
                                   ["--bgm-type", "elevenlabs"], ["--sonilo-bgm-prompt", "calm"],
                                   ["--video-music-prompt", "calm", "--bgm-type", "sonilo"]])
def test_run_paid_voice_or_ai_music_needs_yes(checkout, spawn, tmp_path, extra):
    args = ["--video-script", "x", "--video-source", "local", "--video-materials", str(_local(tmp_path)), *extra]
    if "--voice-name" not in extra:
        args += ["--voice-name", EDGE]
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, *args)
    assert spawn.calls == []


@pytest.mark.parametrize("voice", [EDGE, "no-voice", "en-US-AriaNeural", "zh-CN-XiaoxiaoNeural-Female"])
def test_run_edge_and_silent_voices_are_free(checkout, spawn, tmp_path, voice):
    args = ["--video-script", "x", "--video-source", "local", "--video-materials", str(_local(tmp_path)),
            "--voice-name", voice]
    assert _run(tmp_path, *args) == 0


def test_run_free_online_source_with_terms_given_needs_no_yes_but_without_terms_it_does(checkout, spawn, tmp_path):
    base = ["--video-script", "x", "--video-source", "pexels", "--voice-name", EDGE]
    assert _run(tmp_path, *base, "--video-terms", "mar,praia") == 0
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):  # the terms would come from an LLM
        _run(tmp_path, *base)


def test_run_stops_before_cross_posting_when_the_config_publishes(checkout, spawn, tmp_path):
    (checkout / "config.toml").write_text("[app]\nupload_post_enabled = true\nupload_post_auto_upload = true\n")
    with pytest.raises(moneyprinter.MoneyPrinterError, match="publica"):
        _run(tmp_path, *_free(tmp_path))
    assert spawn.calls == []
    (checkout / "config.toml").write_text("[app]\nupload_post_enabled = false\nupload_post_auto_upload = false\n")
    assert _run(tmp_path, *_free(tmp_path)) == 0


def test_run_earlier_stage_prints_the_upstream_result_and_copies_nothing(checkout, spawn, tmp_path, capsys):
    spawn.stdout = json.dumps({"task_id": "t9", "result": {"script": "Olá"}})
    assert _run(tmp_path, "--video-script", "Olá", "--stop-at", "script", before=("--json",)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["tasks"][0]["result"] == {"script": "Olá"} and out["tasks"][0]["videos"] == []
    assert not list((tmp_path / "out").glob("*.mp4"))


def test_run_a_failed_task_returns_1_and_copies_nothing(checkout, spawn, tmp_path):
    spawn.rc = 1
    spawn.stdout = ""
    assert _run(tmp_path, *_free(tmp_path)) == 1
    assert not list((tmp_path / "out").glob("*.mp4"))


def test_run_passes_the_upstream_exit_code_2_through(checkout, spawn, tmp_path):
    spawn.rc = 2
    spawn.stdout = ""
    assert _run(tmp_path, *_free(tmp_path)) == 2


def test_run_never_reads_a_video_outside_storage_tasks(checkout, spawn, tmp_path, capsys):
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"x")
    spawn.stdout = json.dumps({"task_id": "t1", "result": {"state": 1, "videos": [str(outside)]}})
    assert _run(tmp_path, *_free(tmp_path)) == 1
    assert "fora da pasta de tarefas" in capsys.readouterr().err
    assert not list((tmp_path / "out").glob("*.mp4"))


def test_run_several_videos_get_distinct_names(checkout, spawn, tmp_path, capsys):
    spawn.stdout = _task_stdout(checkout, videos=("final-1.mp4", "final-2.mp4"))
    assert _run(tmp_path, *_free(tmp_path, "--video-count", "2"), before=("--json",)) == 0
    names = [v["video"] for v in json.loads(capsys.readouterr().out)["tasks"][0]["videos"]]
    assert len(set(names)) == 2 and all((tmp_path / "out" / n).is_file() for n in names)


def test_run_batch_file_copies_every_task_and_counts_failures(checkout, spawn, tmp_path, capsys):
    manifest = tmp_path / "tasks.jsonl"
    manifest.write_text(json.dumps({"video_script": "a", "video_source": "local"}) + "\n")
    a = _task_stdout(checkout, "ta")
    summary = {"total": 2, "succeeded": 1, "failed": 1, "tasks": [
        {"index": 1, "task_id": "ta", "status": "succeeded", "result": json.loads(a)["result"], "failed_stage": None,
         "error": None},
        {"index": 2, "task_id": "tb", "status": "failed", "result": None, "failed_stage": "audio", "error": "boom"}]}
    spawn.stdout = json.dumps(summary)
    spawn.rc = 1
    rc = _run(tmp_path, "--batch-file", str(manifest), "--voice-name", EDGE, before=("--json",))
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert (out["total"], out["succeeded"], out["failed"]) == (2, 1, 1)
    assert out["tasks"][0]["videos"][0]["sha256"] and out["tasks"][1]["error"] == "boom"
    assert (tmp_path / "out" / "moneyprinter-ta.mp4").is_file()


def test_run_batch_file_with_a_task_that_needs_an_llm_or_paid_source_needs_yes(checkout, spawn, tmp_path):
    m = tmp_path / "m.json"
    for entry in ({"video_subject": "tema"}, {"video_script": "a", "video_source": "wavespeed"},
                  {"video_script": "a", "video_source": "local", "voice_name": "gemini:Kore"},
                  {"video_script": "a", "video_source": "local", "bgm_type": "sonilo"}):
        m.write_text(json.dumps([entry]))
        with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
            _run(tmp_path, "--batch-file", str(m), "--video-source", "local", "--voice-name", EDGE)
    assert spawn.calls == []
    m.write_text(json.dumps([{"video_script": "a"}, {"video_script": "b"}]))
    assert _run(tmp_path, "--batch-file", str(m), "--video-source", "local", "--voice-name", EDGE) == 0


def test_run_batch_file_must_exist(checkout, spawn, tmp_path):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="manifesto"):
        _run(tmp_path, "--batch-file", str(tmp_path / "nao-existe.json"), "--voice-name", EDGE)


def test_run_without_a_venv_points_to_setup(checkout, spawn, tmp_path):
    moneyprinter.venv_python().unlink()
    with pytest.raises(moneyprinter.MoneyPrinterError, match="setup"):
        _run(tmp_path, *_free(tmp_path))


def test_the_module_never_calls_the_publishing_endpoints():
    src = (ROOT / "src" / "simplicio_video" / "moneyprinter.py").read_text(encoding="utf-8")
    assert "social-metadata" not in src and "cross_post_video" not in src and "/api/v1/social" not in src


def test_help_documents_run_with_examples_and_the_yes_rule():
    u = moneyprinter.USAGE
    assert "moneyprinter run" in u and "--yes" in u and "--out" in u and "--video-script" in u


# ---- MCP: generate e run só como tarefa em segundo plano -----------------------------------------------------------

@pytest.fixture
def jobs_env(monkeypatch):
    from simplicio_video import jobs
    spawned = []
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: spawned.append(jid) or os.getpid())
    return jobs, spawned


def _mcp_run(tmp_path, *upstream, out=None):
    import shlex
    out = out if out is not None else str(tmp_path / "out")
    return mcp_server.video_moneyprinter("run --out " + shlex.quote(out) + " -- "
                                         + " ".join(shlex.quote(u) for u in upstream))


def test_mcp_run_with_a_script_local_material_and_edge_voice_becomes_a_moneyprinter_job(checkout, tmp_path, jobs_env):
    jobs, spawned = jobs_env
    r = _mcp_run(tmp_path, *_free(tmp_path))
    assert r["ok"] is True, r
    st = jobs.read_state(r["job"]["id"])
    assert st["kind"] == "moneyprinter" and st["origin"] == "mcp" and st["spends"] is False
    assert spawned == [st["id"]]
    argv = jobs.build_argv("moneyprinter", st["params"])
    assert argv[:3] == ["moneyprinter", "run", "--out"] and argv[3] == str(tmp_path / "out")
    assert "--json" in argv and "--yes" not in argv and argv[argv.index("--json") + 1] == "--"
    assert "--video-script=Olá, mundo." in argv and "--video-source=local" in argv


def test_mcp_generate_with_a_script_file_becomes_a_job_with_subtitles_off(checkout, tmp_path, jobs_env):
    jobs, _ = jobs_env
    script = tmp_path / "roteiro.txt"
    script.write_text("Texto do roteiro.")
    clip = _local(tmp_path)
    r = mcp_server.video_moneyprinter(f"generate --script {script} --material {clip} --out {tmp_path / 'out'}")
    assert r["ok"] is True, r
    argv = jobs.build_argv("moneyprinter", jobs.read_state(r["job"]["id"])["params"])
    assert "--video-script=Texto do roteiro." in argv and f"--video-materials={clip}" in argv
    assert f"--voice-name={moneyprinter.DEFAULT_VOICE}" in argv and "--no-subtitle-enabled" in argv


@pytest.mark.parametrize("upstream", [
    ["--video-subject", "tema"],                                    # script by LLM
    ["--video-script", " "],
    ["--video-script", "x", "--video-source", "pexels", "--video-terms", "a"],
    ["--video-script", "x", "--video-source", "wavespeed", "--confirm-wavespeed-charge"],
    ["--video-script", "x", "--voice-name", "gemini:Kore"],
    ["--video-script", "x", "--bgm-type", "sonilo"],
    ["--video-script", "x", "--batch-file", "/tmp/m.json"],
    ["--video-script", "x", "--task-id", "00000000-0000-0000-0000-000000000000"],
    ["--video-script", "x", "--stop-at", "script"],
    ["--video-script", "x", "--paragraph-number", "2"],
    ["--video-script", "x", "--video-script-prompt", "p"],
    ["--video-script", "x", "--custom-system-prompt", "p"],
    ["--video-script", "x", "--bogus"],
])
def test_mcp_run_refuses_everything_else_naming_the_terminal(checkout, tmp_path, jobs_env, upstream):
    jobs, spawned = jobs_env
    clip = _local(tmp_path)
    full = list(upstream)
    if "--video-source" not in full:
        full += ["--video-source", "local"]
    if "--video-materials" not in full:
        full += ["--video-materials", str(clip)]
    if "--voice-name" not in full:
        full += ["--voice-name", EDGE]
    r = _mcp_run(tmp_path, *full)
    assert r["ok"] is False and "terminal" in r["error"]
    assert spawned == [] and jobs.list_jobs() == []


@pytest.mark.parametrize("what", ["relative-out", "relative-material", "missing-material", "no-voice-flag", "no-material"])
def test_mcp_run_needs_absolute_paths_existing_material_and_an_explicit_voice(checkout, tmp_path, jobs_env, what):
    _, spawned = jobs_env
    clip = _local(tmp_path)
    args = ["--video-script", "x", "--video-source", "local", "--video-materials", str(clip), "--voice-name", EDGE]
    out = str(tmp_path / "out")
    if what == "relative-out":
        out = "out"
    elif what == "relative-material":
        args[args.index("--video-materials") + 1] = "clip.mp4"
    elif what == "missing-material":
        args[args.index("--video-materials") + 1] = str(tmp_path / "nao.mp4")
    elif what == "no-voice-flag":
        del args[-2:]
    elif what == "no-material":
        i = args.index("--video-materials")
        del args[i:i + 2]
    r = _mcp_run(tmp_path, *args, out=out)
    assert r["ok"] is False and r["error"]
    assert spawned == []


def test_mcp_generate_refuses_relative_paths_and_a_missing_script(checkout, tmp_path, jobs_env):
    _, spawned = jobs_env
    clip = _local(tmp_path)
    for cmd in (f"generate --script roteiro.txt --material {clip} --out {tmp_path / 'o'}",
                f"generate --script {tmp_path / 'nao.txt'} --material {clip} --out {tmp_path / 'o'}",
                f"generate --script {tmp_path / 'nao.txt'} --material {clip} --out o"):
        assert mcp_server.video_moneyprinter(cmd)["ok"] is False
    assert spawned == []


def test_mcp_generate_refuses_a_paid_voice_with_terminal_in_the_error(checkout, tmp_path, jobs_env):
    script = tmp_path / "r.txt"
    script.write_text("x")
    r = mcp_server.video_moneyprinter(
        f"generate --script {script} --material {_local(tmp_path)} --out {tmp_path / 'o'} --voice gemini:Kore")
    assert r["ok"] is False and "terminal" in r["error"]


def test_mcp_still_refuses_setup_serve_and_batch(checkout, venv, tmp_path, jobs_env):
    for a in ("setup", "serve", "serve --lan", f"run --out {tmp_path / 'o'} -- --batch-file {tmp_path / 'm.json'}"):
        r = mcp_server.video_moneyprinter(a)
        assert r["ok"] is False and "terminal" in r["error"], a


def test_the_moneyprinter_job_kind_revalidates_what_it_is_given(checkout, tmp_path, jobs_env):
    jobs, spawned = jobs_env
    bad = {"out": str(tmp_path / "o"), "upstream": ["--video-subject=tema", "--video-source=local"]}
    with pytest.raises(jobs.JobError, match="terminal"):
        jobs.submit("moneyprinter", bad, origin="mcp")
    with pytest.raises(jobs.JobError):
        jobs.submit("moneyprinter", {"out": str(tmp_path / "o"), "upstream": [], "yes": True}, origin="mcp")
    assert spawned == []


def test_the_moneyprinter_job_never_carries_the_engine_yes(checkout, tmp_path, jobs_env):
    jobs, _ = jobs_env
    r = _mcp_run(tmp_path, *_free(tmp_path))
    argv = jobs.build_argv("moneyprinter", jobs.read_state(r["job"]["id"])["params"])
    assert "--yes" not in argv and not any(a.startswith("--confirm-") for a in argv)


def test_the_moneyprinter_job_result_is_the_list_of_videos_with_their_hashes(tmp_path):
    from simplicio_video import jobs
    last = {"total": 1, "succeeded": 1, "failed": 0, "tasks": [
        {"task_id": "t1", "status": "succeeded", "error": None,
         "videos": [{"video": "moneyprinter-t1.mp4", "sha256": "ab" * 32, "bytes": 3}]}]}
    res = jobs.KINDS["moneyprinter"]["result"]({"out": str(tmp_path)}, last)
    assert res["videos"] == [{"path": str(tmp_path / "moneyprinter-t1.mp4"), "sha256": "ab" * 32, "bytes": 3}]
    assert jobs.KINDS["moneyprinter"]["result"]({"out": str(tmp_path)}, None) is None


def test_mcp_description_mentions_generate_run_and_the_terminal_only_rest():
    d = mcp_server.DESC_video_moneyprinter
    assert "generate" in d and "run" in d and "terminal" in d and "script" in d and "background" in d


# ---- setup mostra o progresso por etapa ------------------------------------------------------------------------------

def test_setup_prints_progress_per_step_with_the_time_each_took(checkout, calls, capsys):
    assert moneyprinter.run_moneyprinter(["setup"]) == 0
    out = capsys.readouterr().out
    steps = re.findall(r"^\[(\d+)/(\d+)\] (.+)$", out, flags=re.M)
    assert steps and all(total == steps[0][1] for _, total, _ in steps)
    assert [int(i) for i, _, _ in steps] == list(range(1, len(steps) + 1))
    assert int(steps[0][1]) == len(steps)
    assert "pip install" in out and "venv" in out
    assert len(re.findall(r"^\s*ok \(\d+s\)$", out, flags=re.M)) >= 2


def test_setup_progress_line_comes_before_the_step_runs_and_a_failure_is_named(checkout, monkeypatch, capsys):
    seen = []

    def fake(cmd, cwd=None, env=None):
        seen.append(capsys.readouterr().out)  # what was printed before this step started
        return 5 if "pip" in cmd else 0
    monkeypatch.setattr("subprocess.call", fake)
    assert moneyprinter.run_moneyprinter(["setup"]) == 1
    assert "[1/" in seen[0] and "[2/" in seen[1]
    assert re.search(r"falhou \(código 5, \d+s\)", capsys.readouterr().out)


def test_spawn_cli_relays_the_upstream_log_lines_live_and_returns_only_the_json_document(tmp_path, capsys):
    # the upstream cli.py logs to STDOUT (loguru sink sys.stdout) and prints its result there too: the log must reach the
    # user (stderr) while it runs, and only the JSON line comes back as the result
    code = ("import sys; print('2026-11-05 | INFO | start task', flush=True); "
            "print('{\"task_id\": \"t1\", \"result\": {}}', flush=True); print('2026 | INFO | after', flush=True)")
    rc, out = moneyprinter._spawn_cli([sys.executable, "-c", code], tmp_path, dict(os.environ))
    assert rc == 0 and json.loads(out) == {"task_id": "t1", "result": {}}
    err = capsys.readouterr().err
    assert "start task" in err and "after" in err and "task_id" not in err


def test_spawn_cli_returns_the_exit_code(tmp_path):
    rc, out = moneyprinter._spawn_cli([sys.executable, "-c", "import sys; print('x'); sys.exit(3)"], tmp_path,
                                      dict(os.environ))
    assert rc == 3 and out == ""


# ---- revisão do PR #165 ----------------------------------------------------------------------------------------------

PUBLISHING_CONFIGS = {
    "string-true": '[app]\nupload_post_auto_upload = "true"\n',
    "string-true-literal": "[app]\nupload_post_auto_upload = 'true'\n",
    "string-false-is-truthy": '[app]\nupload_post_auto_upload = "false"\n',
    "int-one": "[app]\nupload_post_auto_upload = 1\n",
    "string-yes": '[app]\nupload_post_auto_upload = "yes"\n',
    "quoted-key": '[app]\n"upload_post_auto_upload" = true\n',
    "literal-quoted-key": "[app]\n'upload_post_auto_upload' = true\n",
    "dotted-key": "app.upload_post_auto_upload = true\n",
    "inline-table": "app = { upload_post_auto_upload = true }\n",
    "with-comment": "[app]\nupload_post_auto_upload=true # sim\n",
    "non-empty-list": '[app]\nupload_post_auto_upload = ["x"]\n',
    "invalid-toml": "[app\nupload_post_auto_upload = true\n",
}


@pytest.mark.parametrize("name", sorted(PUBLISHING_CONFIGS))
def test_run_refuses_every_form_of_a_truthy_auto_upload(checkout, spawn, tmp_path, name):
    (checkout / "config.toml").write_text(PUBLISHING_CONFIGS[name])
    with pytest.raises(moneyprinter.MoneyPrinterError, match="publica|config.toml"):
        _run(tmp_path, *_free(tmp_path))
    assert spawn.calls == []


@pytest.mark.parametrize("text", ['[app]\nupload_post_auto_upload = false\n', "[app]\nupload_post_auto_upload = 0\n",
                                  '[app]\nupload_post_auto_upload = ""\n', "[app]\nx = 1\n", "upload_post_auto_upload = true\n"])
def test_run_allows_a_falsy_or_absent_auto_upload(checkout, spawn, tmp_path, text):
    (checkout / "config.toml").write_text(text)  # the last one is top level: upstream reads only [app]
    assert _run(tmp_path, *_free(tmp_path)) == 0


def test_generate_and_serve_apply_the_publishing_gate_too(checkout, venv, server, monkeypatch, tmp_path):
    (checkout / "config.toml").write_text('[app]\nupload_post_auto_upload = "true"\n')
    script, clip = _generate_inputs(tmp_path)
    monkeypatch.setattr(moneyprinter, "_request", _api_request())
    with pytest.raises(moneyprinter.MoneyPrinterError, match="publica"):
        moneyprinter.run_moneyprinter(_generate_argv(script, clip, tmp_path / "o"))
    for args in (["serve", "--api"], ["serve", "--webui"], ["serve"]):
        with pytest.raises(moneyprinter.MoneyPrinterError, match="publica"):
            moneyprinter.run_moneyprinter(args)
    assert server.started == []


def _ui(checkout, body):
    (checkout / "config.toml").write_text("[ui]\n" + body)


def _novoice(tmp_path, *extra):
    return ["--video-script", "x", "--video-source", "local", "--video-materials", str(_local(tmp_path)), *extra]


def test_run_without_a_voice_resolves_the_one_from_config_and_classifies_it(checkout, spawn, tmp_path):
    _ui(checkout, 'voice_name = "gemini:Kore"\n')
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, *_novoice(tmp_path))
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, *_novoice(tmp_path, "--voice-name", ""))
    assert spawn.calls == []
    assert _run(tmp_path, *_novoice(tmp_path), before=("--yes",)) == 0


@pytest.mark.parametrize("body", ['voice_name = "gemini:Kore"\nvoice_mode = "none"\n',
                                  'voice_name = "gemini:Kore"\nvoice_mode = "upload"\n',
                                  'voice_name = "pt-BR-FranciscaNeural-Female"\n', ""])
def test_run_without_a_voice_is_free_when_config_says_none_upload_edge_or_nothing(checkout, spawn, tmp_path, body):
    _ui(checkout, body)
    assert _run(tmp_path, *_novoice(tmp_path)) == 0


def test_run_an_explicit_voice_wins_over_the_config(checkout, spawn, tmp_path):
    _ui(checkout, 'voice_name = "gemini:Kore"\n')
    assert _run(tmp_path, *_novoice(tmp_path, "--voice-name", EDGE)) == 0


@pytest.mark.parametrize("voice", ["", " ", "x"])
def test_mcp_needs_a_non_empty_explicit_free_voice(checkout, tmp_path, jobs_env, voice):
    _, spawned = jobs_env
    r = _mcp_run(tmp_path, "--video-script", "x", "--video-source", "local", "--video-materials", str(_local(tmp_path)),
                 "--voice-name", voice)
    assert r["ok"] is False and spawned == []
    script = tmp_path / "r.txt"
    script.write_text("x")
    r = mcp_server.video_moneyprinter(["generate", "--script", str(script), "--material", str(_local(tmp_path)), "--out",
                                       str(tmp_path / "o"), "--voice", voice])
    assert r["ok"] is False and spawned == []


@pytest.mark.parametrize("bgm", ["ELEVENLABS", " Sonilo", "SoNiLo ", "elevenlabs"])
def test_run_classifies_the_bgm_type_the_way_upstream_normalizes_it(checkout, spawn, tmp_path, bgm):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, *_free(tmp_path, "--bgm-type", bgm))
    assert spawn.calls == []


def test_batch_entry_bgm_type_is_normalized_too(checkout, spawn, tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps([{"video_script": "a", "bgm_type": " ELEVENLABS"}]))
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, "--batch-file", str(m), "--video-source", "local", "--voice-name", EDGE)


@pytest.mark.parametrize("terms", [" , ", ",", "，", " "])
def test_terms_that_split_to_nothing_mean_llm_terms(checkout, spawn, tmp_path, terms):
    with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
        _run(tmp_path, "--video-script", "x", "--video-source", "pexels", "--video-terms", terms, "--voice-name", EDGE)
    assert spawn.calls == []
    assert _run(tmp_path, "--video-script", "x", "--video-source", "pexels", "--video-terms", "mar， praia",
                "--voice-name", EDGE) == 0


def test_batch_entry_terms_that_are_empty_mean_llm_terms(checkout, spawn, tmp_path):
    m = tmp_path / "m.json"
    for terms in ([], [" "], " , "):
        m.write_text(json.dumps([{"video_script": "a", "video_source": "pexels", "video_terms": terms}]))
        with pytest.raises(moneyprinter.MoneyPrinterError, match="--yes"):
            _run(tmp_path, "--batch-file", str(m), "--voice-name", EDGE)


def test_batch_manifest_is_capped_before_it_is_read(checkout, spawn, tmp_path):
    big = tmp_path / "big.jsonl"
    big.write_text(("x" * 1024 * 1024) + "\n")
    with pytest.raises(moneyprinter.MoneyPrinterError, match="1 MiB|MiB"):
        _run(tmp_path, "--batch-file", str(big), "--voice-name", EDGE)
    many = tmp_path / "many.json"
    many.write_text(json.dumps([{"video_script": "a", "video_source": "local"}] * 101))
    with pytest.raises(moneyprinter.MoneyPrinterError, match="100"):
        _run(tmp_path, "--batch-file", str(many), "--voice-name", EDGE)
    assert spawn.calls == []


def test_stopping_run_takes_the_upstream_process_group_down_within_the_grace(tmp_path):
    fake = tmp_path / "fake_cli.py"
    fake.write_text("import os, signal, sys, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\n"
                    "open(sys.argv[1], 'w').write(str(os.getpid()))\nprint('log line', flush=True)\ntime.sleep(25)\n")
    pidfile = tmp_path / "pid"
    driver = tmp_path / "driver.py"
    driver.write_text("import os, sys\nfrom pathlib import Path\nfrom simplicio_video import moneyprinter as m\n"
                      "m._spawn_cli([sys.executable, sys.argv[1], sys.argv[2]], Path('.'), dict(os.environ))\n")
    env = {**os.environ, "SIMPLICIO_JOBS_GRACE_S": "2"}
    p = subprocess.Popen([sys.executable, str(driver), str(fake), str(pidfile)], env=env, cwd=tmp_path)
    try:
        deadline = time.monotonic() + 15
        while not (pidfile.exists() and pidfile.read_text()) and time.monotonic() < deadline:
            time.sleep(0.05)
        child = int(pidfile.read_text())
        assert _alive(child)
        t0 = time.monotonic()
        p.send_signal(signal.SIGINT)
        p.send_signal(signal.SIGINT)  # a second Ctrl+C must not abort the stop
        p.wait(timeout=10)
        while _alive(child) and time.monotonic() - t0 < 3.5:
            time.sleep(0.05)
        assert not _alive(child), "the upstream cli.py outlived the stop"
        assert time.monotonic() - t0 <= 3.1  # grace (2 s) + 1
    finally:
        p.kill()
        if pidfile.exists() and pidfile.read_text():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

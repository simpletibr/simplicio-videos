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

from simplicio_video import cli, mcp_server, tools, toonflow

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(autouse=True)
def _no_toonflow_overrides(monkeypatch, tmp_path):
    # Isolate the home and the tools dir: a real checkout under ~/.simplicio-video must never be found by a test.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.delenv("TOONFLOW_DIR", raising=False)
    monkeypatch.delenv("TOONFLOW_DATA_DIR", raising=False)
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))


@pytest.fixture
def checkout(monkeypatch, tmp_path):
    """A stand-in Toonflow checkout (package.json is the marker): the run tests never clone anything."""
    d = tmp_path / "toonflow"
    d.mkdir()
    (d / "package.json").write_text("{}")
    monkeypatch.setenv("TOONFLOW_DIR", str(d))
    return d


@pytest.fixture
def bun(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/bun" if cmd == "bun" else None)
    return "/usr/bin/bun"


@pytest.fixture
def calls(monkeypatch):
    """Records every install/build subprocess.call as (cmd, cwd, TOONFLOW_DATA_DIR). A step exits 0 unless a
    test sets fail[(args)]."""
    recorded: list[tuple[list[str], Path | None, str | None]] = []
    fail: dict[tuple[str, ...], int] = {}

    def fake(cmd, cwd=None, env=None):
        recorded.append((list(cmd), cwd, (env or {}).get("TOONFLOW_DATA_DIR")))
        return fail.get(tuple(cmd[1:3]), 0)

    monkeypatch.setattr("subprocess.call", fake)
    return recorded, fail


@pytest.fixture
def server(monkeypatch):
    """Fakes the long-running server process. Records how it is started and which signal reaches its group.
    state.interrupt: the next blocking wait() raises KeyboardInterrupt (Ctrl+C on this process).
    state.ignore_sigint: the server ignores SIGINT, so the stop must escalate to SIGKILL."""
    state = SimpleNamespace(started=[], signals=[], interrupt=False, ignore_sigint=False, term_handler=None)

    class Proc:
        pid = 4242

        def __init__(self, cmd, cwd=None, env=None, start_new_session=False):
            self.cmd, self.cwd, self.env, self.start_new_session = cmd, cwd, env, start_new_session
            self.returncode = None
            state.started.append(self)

        def wait(self, timeout=None):
            if timeout is None:
                state.term_handler = signal.getsignal(signal.SIGTERM)
                if state.interrupt:
                    state.interrupt = False  # one Ctrl+C: the wait after SIGKILL must return normally
                    raise KeyboardInterrupt
            elif state.ignore_sigint and any(sig == signal.SIGINT for _, sig in state.signals):
                raise subprocess.TimeoutExpired(self.cmd, timeout)
            self.returncode = 0
            return 0

        def poll(self):
            return self.returncode

    monkeypatch.setattr("subprocess.Popen", Proc)
    monkeypatch.setattr(toonflow.os, "killpg", lambda pgid, sig: state.signals.append((pgid, sig)))
    return state


def _alive(pid: int) -> bool:
    """Linux: a zombie counts as gone, since it no longer runs and no longer holds the port."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != "Z"


def test_toonflow_is_pinned_to_a_full_commit_under_mit():
    t = tools.get("toonflow")
    assert t.kind == "git"
    assert t.source == "https://github.com/HBAI-Ltd/Toonflow-app"
    assert SHA40.match(t.ref), t.ref
    assert t.license == "MIT"
    assert t.marker == "package.json"


def test_find_toonflow_dir_uses_the_env_override(checkout):
    assert toonflow.find_toonflow_dir() == checkout.resolve()


def test_find_toonflow_dir_is_none_without_a_checkout(monkeypatch, tmp_path):
    monkeypatch.setenv("TOONFLOW_DIR", str(tmp_path / "vazio"))
    assert toonflow.find_toonflow_dir() is None


def test_help_needs_no_checkout(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("subprocess.call", lambda *a, **k: calls.append(a) or 0)
    assert toonflow.run_toonflow(["--help"]) == 0
    out = capsys.readouterr().out
    assert "clone" in out and "serve" in out and "where" in out
    assert "--lan" in out and "0.0.0.0" in out
    assert calls == []


@pytest.mark.parametrize("args", [["where"], ["serve", "--lan"]])
def test_commands_without_a_checkout_point_to_clone(args):
    with pytest.raises(toonflow.ToonflowError, match="toonflow clone"):
        toonflow.run_toonflow(args)


def test_unknown_subcommand_is_an_error(checkout):
    with pytest.raises(toonflow.ToonflowError, match="clone\\|serve\\|where"):
        toonflow.run_toonflow(["nope"])


def test_clone_installs_at_the_pinned_commit(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path))
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    assert toonflow.clone_toonflow() == tmp_path / "toonflow"
    assert calls[0][0] == "clone" and calls[0][-1] == str(tmp_path / "toonflow")
    assert calls[-1] == ("checkout", "--quiet", "--detach", tools.get("toonflow").ref)


def test_clone_never_runs_when_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path))
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    with pytest.raises(toonflow.ToonflowError, match="offline"):
        toonflow.clone_toonflow()
    assert calls == []


def test_clone_to_an_explicit_dir_does_not_leak_into_the_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "")
    other = tmp_path / "meu"
    assert toonflow.clone_toonflow(other) == other
    assert "TOONFLOW_DIR" not in os.environ


def test_where_prints_the_checkout(checkout, capsys):
    assert toonflow.run_toonflow(["where"]) == 0
    assert capsys.readouterr().out.strip() == str(checkout.resolve())


def test_serve_without_lan_refuses_because_the_server_is_open_on_every_interface(checkout, bun, calls, server):
    recorded, _ = calls
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.run_toonflow(["serve"])
    assert "--lan" in str(e.value) and "0.0.0.0" in str(e.value)
    assert recorded == [] and server.started == []


def test_serve_installs_builds_then_runs_the_built_server_directly(checkout, bun, calls, server):
    # `bun build/server/index.js` is the command upstream's Dockerfile runs. No `bun run` wrappers: each wrapper is
    # one more process that a stop could leave behind holding port 3000.
    recorded, _ = calls
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    assert [cmd for cmd, _, _ in recorded] == [
        [bun, "install", "--frozen-lockfile"],
        [bun, "run", "build:server"],
    ]
    assert [p.cmd for p in server.started] == [[bun, "build/server/index.js"]]
    assert server.started[0].cwd == checkout.resolve()
    assert server.started[0].start_new_session is True  # its own group, so a stop reaches every process it started


def test_serve_keeps_the_data_outside_the_checkout(checkout, bun, calls, server, tmp_path):
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    data = (tmp_path / "data" / "toonflow-data").resolve()
    assert server.started[0].env["TOONFLOW_DATA_DIR"] == str(data)
    assert (data / "workspaces" / "myProject").is_dir()
    assert checkout.resolve() not in data.parents


def test_serve_respects_a_data_dir_the_user_set(checkout, bun, calls, server, monkeypatch, tmp_path):
    mine = (tmp_path / "meu-toonflow").resolve()
    monkeypatch.setenv("TOONFLOW_DATA_DIR", str(mine))
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    assert server.started[0].env["TOONFLOW_DATA_DIR"] == str(mine)
    assert (mine / "workspaces" / "myProject").is_dir()


def test_data_dir_is_absolute_because_the_server_runs_inside_the_checkout(monkeypatch, tmp_path):
    # A relative TOONFLOW_DATA_DIR would be read from the checkout by the server but created from the caller's cwd.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOONFLOW_DATA_DIR", "dados/relativos")
    assert toonflow.data_dir().is_absolute()
    assert toonflow.data_dir() == (tmp_path / "dados" / "relativos").resolve()


@pytest.mark.parametrize("step", [("install", "--frozen-lockfile"), ("run", "build:server")])
def test_serve_stops_at_the_first_failing_step(checkout, bun, calls, server, step):
    recorded, fail = calls
    fail[step] = 3
    assert toonflow.run_toonflow(["serve", "--lan"]) == 1
    assert recorded[-1][0][1:3] == list(step)
    assert server.started == []


def test_serve_ctrl_c_stops_the_whole_server_group_without_a_traceback(checkout, bun, calls, server, capsys):
    server.interrupt = True
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    assert (4242, signal.SIGINT) in server.signals
    assert (4242, signal.SIGKILL) not in server.signals
    assert "Traceback" not in capsys.readouterr().err


def test_serve_escalates_to_sigkill_when_the_server_ignores_sigint(checkout, bun, calls, server):
    server.interrupt = True
    server.ignore_sigint = True
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    assert server.signals == [(4242, signal.SIGINT), (4242, signal.SIGKILL)]


def test_serve_sigterm_is_handled_like_ctrl_c_and_restored_afterwards(checkout, bun, calls, server):
    before = signal.getsignal(signal.SIGTERM)
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    handler = server.term_handler  # what SIGTERM would run while the server was up
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
        f"h = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
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
        toonflow._stop_group(proc)
        assert proc.poll() is not None
        assert not _alive(helper)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_serve_ctrl_c_during_install_is_an_interruption_not_a_traceback(checkout, bun, monkeypatch, capsys):
    def interrupted(cmd, cwd=None, env=None):
        raise KeyboardInterrupt

    monkeypatch.setattr("subprocess.call", interrupted)
    assert toonflow.run_toonflow(["serve", "--lan"]) == 130
    assert "Traceback" not in capsys.readouterr().err


def test_serve_refuses_extra_args_because_the_port_is_fixed(checkout, bun, calls, server):
    recorded, _ = calls
    with pytest.raises(toonflow.ToonflowError, match="aceita só --lan"):
        toonflow.run_toonflow(["serve", "--lan", "--port", "5174"])
    assert recorded == [] and server.started == []


def test_serve_without_bun_says_where_to_get_it(checkout, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(toonflow.ToonflowError, match="bun"):
        toonflow.run_toonflow(["serve", "--lan"])


def test_cli_dispatch_toonflow(monkeypatch):
    recorded = []
    monkeypatch.setattr(toonflow, "run_toonflow", lambda args: recorded.append(args) or 0)
    assert cli.main(["toonflow", "where"]) == 0
    assert recorded == [["where"]]


def test_cli_toonflow_error_exits_1(monkeypatch, capsys):
    def boom(args):
        raise toonflow.ToonflowError("falha teste")

    monkeypatch.setattr(toonflow, "run_toonflow", boom)
    assert cli.main(["toonflow", "serve"]) == 1
    assert "toonflow: falha teste" in capsys.readouterr().err


def test_mcp_exposes_video_toonflow():
    names = [name for name, fn, desc in mcp_server.TOOLS]
    assert "video.toonflow" in names


def test_mcp_where_returns_the_checkout(checkout):
    r = mcp_server.video_toonflow("where")
    assert r["ok"] is True
    assert str(checkout.resolve()) in r["log"]


@pytest.mark.parametrize("args", ["serve", "serve --lan"])
def test_mcp_refuses_serve_because_it_blocks_the_server(checkout, args):
    r = mcp_server.video_toonflow(args)
    assert r["ok"] is False
    assert "terminal" in r["error"]


def test_mcp_clone_uses_the_default_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    r = mcp_server.video_toonflow("clone")
    assert r["ok"] is True
    assert calls[0][-1] == str(tmp_path / "toonflow")


def test_mcp_clone_into_a_chosen_dir_is_refused(monkeypatch, tmp_path):
    # An agent must not pick where a git checkout is written: that is a terminal-only choice.
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    r = mcp_server.video_toonflow(f"clone {tmp_path / 'em-outro-lugar'}")
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
    assert "video.toonflow" in data["mcp"]["tools"]
    assert "video.toonflow" in set(_verbs(data))


def test_toonflow_source_has_no_machine_specific_path():
    src = Path(toonflow.__file__).read_text()
    assert not re.search(r"""["'](/projetos|/home/|/Users/|[A-Za-z]:\\)""", src)

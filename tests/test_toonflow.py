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
from _orfao import SINAIS, espera, espera_pid, mata_o_que_sobrou, sinaliza_no_popen, sinais_padrao, vivo  # noqa: F401

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
    state = SimpleNamespace(started=[], signals=[], interrupt=False, ignore_sigint=False, term_handler=None, hup_handler=None)

    class Proc:
        pid = 4242

        def __init__(self, cmd, cwd=None, env=None, start_new_session=False):
            self.cmd, self.cwd, self.env, self.start_new_session = cmd, cwd, env, start_new_session
            self.returncode = None
            state.started.append(self)

        def wait(self, timeout=None):
            if timeout is None:
                state.term_handler = signal.getsignal(signal.SIGTERM)
                state.hup_handler = signal.getsignal(signal.SIGHUP)
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
    # SIGINT first, then the sweep of the group (SIGKILL) that catches anything the server left behind
    assert server.signals == [(4242, signal.SIGINT), (4242, signal.SIGKILL)]
    assert "Traceback" not in capsys.readouterr().err


def test_serve_escalates_to_sigkill_when_the_server_ignores_sigint(checkout, bun, calls, server):
    server.interrupt = True
    server.ignore_sigint = True
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    assert server.signals == [(4242, signal.SIGINT), (4242, signal.SIGKILL), (4242, signal.SIGKILL)]


def test_serve_sigterm_is_handled_like_ctrl_c_and_restored_afterwards(checkout, bun, calls, server):
    before = signal.getsignal(signal.SIGTERM)
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    handler = server.term_handler  # what SIGTERM would run while the server was up
    assert callable(handler) and handler is not before
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGTERM, None)
    assert signal.getsignal(signal.SIGTERM) is before


def test_serve_sighup_para_o_servidor_como_ctrl_c_e_restaura_depois(checkout, bun, calls, server):
    # ssh caiu ou o terminal fechou: o SIGHUP tem de parar o servidor, não matar só o processo de frente e deixá-lo escutando
    before = signal.getsignal(signal.SIGHUP)
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    handler = server.hup_handler
    assert callable(handler) and handler is not before
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGHUP, None)
    assert signal.getsignal(signal.SIGHUP) is before


@pytest.mark.skipif(os.name != "posix", reason="POSIX signals")
@pytest.mark.usefixtures("sinais_padrao")
@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_inside_popen_does_not_leave_the_server_running(checkout, calls, monkeypatch, tmp_path, nome):
    """The handler (KeyboardInterrupt) ran inside Popen, before `proc` existed and outside the try: the server was never stopped
    and kept listening on 0.0.0.0:3000 with nobody to stop it. Now it is stopped like Ctrl+C: `serve` ends with 0."""
    pidfile = tmp_path / "pid"
    fake_bun = tmp_path / "bun"
    fake_bun.write_text(f"#!/bin/sh\necho $$ > {pidfile}\nexec sleep 120\n")
    fake_bun.chmod(0o755)
    monkeypatch.setattr("shutil.which", lambda cmd: str(fake_bun) if cmd == "bun" else None)
    sinaliza_no_popen(monkeypatch, pidfile, getattr(signal, nome), so_se=str(fake_bun))
    try:
        try:
            rc = toonflow.run_toonflow(["serve", "--lan"])
        except KeyboardInterrupt:
            rc = "KeyboardInterrupt escaped"
        assert espera(lambda: not vivo(espera_pid(pidfile)), 8), "the server outlived the engine"
        assert rc == 0, rc
    finally:
        mata_o_que_sobrou(pidfile)


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
        deadline = time.time() + 5  # the kernel finishes the kill asynchronously: give it a moment, not a fixed sleep
        while _alive(helper) and time.time() < deadline:
            time.sleep(0.05)
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


# --- T3: status, mcp, serve --docker, MCP verbs -------------------------------------------------------------------------

PIN = tools.get("toonflow").ref


@pytest.fixture
def built(checkout, monkeypatch):
    """The stand-in checkout with the two build products, HEAD at the pin, and a bun that reports 1.3.14."""
    (checkout / "build" / "server").mkdir(parents=True)
    (checkout / "build" / "mcp").mkdir(parents=True)
    (checkout / "build" / "server" / "index.js").write_text("//")
    (checkout / "build" / "mcp" / "stdio.js").write_text("//")
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: PIN)
    monkeypatch.setattr(toonflow, "_bun_version", lambda bun: "1.3.14")
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd in ("bun", "node") else None)
    return checkout


def _runtime(port=10588, mode=0o600, token="T" * 40):
    d = toonflow.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"mcpRuntime{port}.json"
    f.write_text(json.dumps({"pid": 1, "url": f"http://127.0.0.1:{port}/mcp", "token": token}))
    f.chmod(mode)
    return f


def test_status_reports_checkout_pin_bun_build_and_no_runtime(built):
    s = toonflow.status()
    assert s["checkout"] == str(built.resolve())
    assert s["pin"] == PIN and s["head"] == PIN and s["pin_match"] is True
    assert s["bun"] == {"found": True, "path": "/usr/bin/bun", "version": "1.3.14"}
    assert s["build"] == {"server": True, "mcp_stdio": True}
    assert s["mcp_runtime"] == []


def test_status_flags_a_head_that_is_not_the_pin_and_a_missing_build(checkout, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "0" * 40)
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    s = toonflow.status()
    assert s["pin_match"] is False
    assert s["bun"]["found"] is False and s["bun"]["version"] is None
    assert s["build"] == {"server": False, "mcp_stdio": False}


def test_status_without_a_checkout_does_not_raise(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    s = toonflow.status()
    assert s["checkout"] is None and s["pin_match"] is None and s["build"] == {"server": False, "mcp_stdio": False}


def test_status_lists_runtime_files_with_mode_and_never_the_token(built):
    _runtime(10588, 0o600)
    _runtime(3002, 0o644)
    s = toonflow.status()
    by_port = {r["port"]: r for r in s["mcp_runtime"]}
    assert by_port[10588]["mode"] == "0600" and by_port[10588]["ok"] is True
    assert by_port[3002]["mode"] == "0644" and by_port[3002]["ok"] is False
    assert "T" * 40 not in json.dumps(s)


def test_cli_status_json_is_parseable_and_has_no_token(built, capsys):
    _runtime()
    assert toonflow.run_toonflow(["status", "--json"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["pin"] == PIN
    assert "T" * 40 not in out


def test_cli_status_text_is_human(built, capsys):
    assert toonflow.run_toonflow(["status"]) == 0
    out = capsys.readouterr().out
    assert PIN in out and "1.3.14" in out


def test_mcp_prints_the_stdio_block_with_absolute_paths_and_no_token(built, capsys):
    f = _runtime()
    assert toonflow.run_toonflow(["mcp", "--json"]) == 0
    out = capsys.readouterr().out
    cfg = json.loads(out)["mcpServers"]["toonflow"]
    assert cfg["command"] == "/usr/bin/node"
    assert cfg["args"] == [str((built / "build" / "mcp" / "stdio.js").resolve()), "--runtime", str(f.resolve())]
    assert "T" * 40 not in out


def test_mcp_falls_back_to_bun_when_node_is_missing(built, monkeypatch):
    _runtime()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/bun" if cmd == "bun" else None)
    assert toonflow.mcp_config()["mcpServers"]["toonflow"]["command"] == "/usr/bin/bun"


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o666, 0o700])
def test_mcp_refuses_a_runtime_file_that_is_not_0600_and_says_how_to_fix(built, mode):
    f = _runtime(mode=mode)
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.mcp_config()
    assert "chmod 600" in str(e.value) and str(f.resolve()) in str(e.value)
    assert "T" * 40 not in str(e.value)


def test_mcp_without_a_runtime_file_says_to_enable_mcp_in_settings(built):
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.mcp_config()
    assert "MCP" in str(e.value) and "mcpRuntime" in str(e.value)


def test_mcp_without_the_stdio_build_says_to_build(checkout, monkeypatch):
    _runtime()
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.mcp_config()
    assert "build:server" in str(e.value)


def test_mcp_asks_for_a_port_when_there_are_several(built):
    _runtime(10588)
    f2 = _runtime(3002)
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.mcp_config()
    assert "--port" in str(e.value)
    assert toonflow.mcp_config(3002)["mcpServers"]["toonflow"]["args"][-1] == str(f2.resolve())


def test_cli_mcp_port_flag(built, capsys):
    _runtime(10588)
    _runtime(3002)
    assert toonflow.run_toonflow(["mcp", "--port", "3002", "--json"]) == 0
    assert "mcpRuntime3002.json" in capsys.readouterr().out


def test_serve_docker_runs_the_upstream_compose_in_the_checkout(checkout, monkeypatch, calls):
    recorded, _ = calls
    monkeypatch.setattr(toonflow, "_compose_cmd", lambda: ["/usr/bin/docker", "compose"])
    assert toonflow.run_toonflow(["serve", "--docker"]) == 0
    cmd, cwd, _data = recorded[-1]
    assert cmd == ["/usr/bin/docker", "compose", "-f", str(checkout.resolve() / "compose.yaml"), "up", "--build"] and cwd == checkout.resolve()


def test_serve_docker_without_docker_is_a_clean_error(checkout, monkeypatch, calls):
    recorded, _ = calls
    monkeypatch.setattr(toonflow, "_compose_cmd", lambda: None)
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.run_toonflow(["serve", "--docker"])
    assert "docker" in str(e.value).lower() and recorded == []


def test_serve_docker_needs_no_lan_and_does_not_use_bun(checkout, monkeypatch, calls):
    recorded, _ = calls
    monkeypatch.setattr(toonflow, "_compose_cmd", lambda: ["docker", "compose"])
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert toonflow.run_toonflow(["serve", "--docker"]) == 0
    assert all("bun" not in c[0] for c, _, _ in recorded)


def test_serve_docker_ctrl_c_is_not_a_traceback(checkout, monkeypatch):
    monkeypatch.setattr(toonflow, "_compose_cmd", lambda: ["docker", "compose"])

    def boom(cmd, cwd=None, env=None):
        raise KeyboardInterrupt

    monkeypatch.setattr("subprocess.call", boom)
    assert toonflow.run_toonflow(["serve", "--docker"]) == 0


@pytest.mark.parametrize("args", [["--docker", "--lan"], ["--docker", "--local"]])
def test_serve_docker_does_not_mix_with_other_modes(checkout, monkeypatch, args):
    monkeypatch.setattr(toonflow, "_compose_cmd", lambda: ["docker", "compose"])
    with pytest.raises(toonflow.ToonflowError):
        toonflow.run_toonflow(["serve", *args])


def test_serve_local_is_refused_because_upstream_has_no_host_setting(checkout, bun, calls, server):
    # apps/server/src/index.ts at the pin: `app.listen(3000, cb)`, port a constant, no HOST: it cannot bind 127.0.0.1.
    recorded, _ = calls
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.run_toonflow(["serve", "--local"])
    assert "--docker" in str(e.value) and recorded == [] and server.started == []


def test_serve_lan_is_unchanged(checkout, bun, calls, server):
    assert toonflow.run_toonflow(["serve", "--lan"]) == 0
    assert server.started[0].cmd == ["/usr/bin/bun", "build/server/index.js"]


def test_usage_documents_the_new_verbs(capsys):
    toonflow.run_toonflow(["help"])
    out = capsys.readouterr().out
    assert "status" in out and "mcp" in out and "--docker" in out


@pytest.mark.parametrize("args", ["status", "status --json", "mcp", "mcp --json"])
def test_mcp_server_allows_status_and_mcp(built, args):
    _runtime()
    r = mcp_server.video_toonflow(args)
    assert r["ok"] is True, r
    assert "T" * 40 not in json.dumps(r)
    assert ("mcpServers" in r["log"]) == args.startswith("mcp")


def test_mcp_server_mcp_reports_the_fix_when_the_runtime_is_open(built):
    _runtime(mode=0o644)
    r = mcp_server.video_toonflow("mcp")
    assert r["ok"] is False and "chmod 600" in r["error"]


@pytest.mark.parametrize("args", ["serve --docker", "serve --local", "serve --lan"])
def test_mcp_server_still_refuses_every_serve_variant(checkout, args):
    r = mcp_server.video_toonflow(args)
    assert r["ok"] is False and "terminal" in r["error"]


def test_mcp_server_description_lists_the_allowed_verbs():
    d = mcp_server.DESC_video_toonflow
    assert "status" in d and "mcp" in d and "terminal" in d


# --- T3 review fixes -----------------------------------------------------------------------------------------------------

def test_mcp_refuses_a_symlinked_runtime_file_and_never_shows_the_target(built, tmp_path):
    secret = tmp_path / "fake_id_rsa"
    secret.write_text("PRIVATE-KEY-CONTENTS")
    secret.chmod(0o600)
    d = toonflow.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    link = d / "mcpRuntime10588.json"
    link.symlink_to(secret)
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.mcp_config()
    assert "link simbólico" in str(e.value) and str(link) in str(e.value)
    assert "PRIVATE-KEY" not in str(e.value) and "fake_id_rsa" not in str(e.value)
    row = toonflow.status()["mcp_runtime"][0]
    assert row["ok"] is False and row["path"] == str(link)


def test_mcp_refuses_a_runtime_entry_that_is_not_a_regular_file(built):
    d = toonflow.data_dir()
    (d / "mcpRuntime10588.json").mkdir(parents=True)
    with pytest.raises(toonflow.ToonflowError):
        toonflow.mcp_config()


@pytest.mark.parametrize("port", ["²", "٣", "0", "65536", "123456", "-1", "x"])
def test_mcp_port_flag_rejects_bad_ports_with_a_toonflow_error(built, port):
    _runtime()
    with pytest.raises(toonflow.ToonflowError):
        toonflow.run_toonflow(["mcp", "--port", port])


def test_runtime_name_only_accepts_ascii_digits(built):
    d = toonflow.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "mcpRuntime٣.json").write_text("{}")
    assert toonflow.status()["mcp_runtime"] == []


def test_mcp_refuses_a_runtime_file_of_another_owner_and_says_chown_not_chmod(built, monkeypatch):
    f = _runtime()
    monkeypatch.setattr(os, "getuid", lambda: f.stat().st_uid + 1)
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.mcp_config()
    msg = str(e.value)
    assert "dono" in msg and "chown" in msg and "chmod 600" not in msg
    assert toonflow.status()["mcp_runtime"][0]["ok"] is False


def test_serve_docker_pins_the_checkout_compose_file_and_drops_compose_env(checkout, monkeypatch):
    seen = {}
    monkeypatch.setattr(toonflow, "_compose_cmd", lambda: ["docker", "compose"])
    monkeypatch.setenv("COMPOSE_FILE", "/tmp/evil.yaml")
    monkeypatch.setenv("COMPOSE_PROFILES", "x")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "x")

    def fake(cmd, cwd=None, env=None):
        seen.update(cmd=list(cmd), cwd=cwd, env=env)
        return 0

    monkeypatch.setattr("subprocess.call", fake)
    assert toonflow.run_toonflow(["serve", "--docker"]) == 0
    assert seen["cmd"] == ["docker", "compose", "-f", str(checkout.resolve() / "compose.yaml"), "up", "--build"]
    assert seen["env"] is not None
    assert not [k for k in seen["env"] if k.startswith("COMPOSE_")]


def test_usage_and_mcp_error_say_docker_and_mcp_do_not_work_together(built, capsys):
    toonflow.run_toonflow(["help"])
    usage = capsys.readouterr().out
    assert "--docker" in usage and "toonflow mcp" in usage and "volume" in usage
    with pytest.raises(toonflow.ToonflowError) as e:
        toonflow.mcp_config()
    assert "--docker" in str(e.value)


@pytest.mark.parametrize("args", ["", "help", "bogus", "clone /x", "clone a b", "where extra", "serve", "status --evil"])
def test_mcp_server_uses_an_allow_list(checkout, args):
    r = mcp_server.video_toonflow(args)
    assert r["ok"] is False


@pytest.mark.parametrize("args", ["where", "status", "status --json", "mcp --json"])
def test_mcp_server_allow_list_lets_the_read_verbs_through(built, args):
    _runtime()
    assert mcp_server.video_toonflow(args)["ok"] is True

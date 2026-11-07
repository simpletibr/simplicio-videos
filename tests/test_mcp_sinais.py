"""The real MCP server (stdio), a tool that runs a child in a worker thread, and a SIGTERM to the server: the child must die with it."""
from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import time

import pytest
from _orfao import POSIX, SINAIS, espera, limpa, sinais_ignorados, vivo

pytestmark = pytest.mark.skipif(not POSIX, reason="POSIX signals")
pytest.importorskip("mcp")


@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_to_the_mcp_server_kills_the_child_of_a_running_tool(nome, tmp_path):
    from conftest import ROOT, offline_env

    bindir, home, pidfile = tmp_path / "bin", tmp_path / "home", tmp_path / "child.pid"
    bindir.mkdir(), home.mkdir()
    falso = bindir / "tinyfish"  # video.busca runs this from a worker thread of the server (guarded_child, own session)
    falso.write_text(f"#!/bin/bash\necho $$ > {pidfile}\nexec sleep 120\n")
    falso.chmod(falso.stat().st_mode | stat.S_IEXEC)
    env = offline_env(HOME=str(home), PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}", TINYFISH_API_KEY="x")
    env.pop("SIMPLICIO_OFFLINE", None)  # busca refuses to call the binary offline; this one is a script of ours and never touches the network
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])
    servidor = subprocess.Popen([sys.executable, "-m", "simplicio_video.mcp_server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=open(tmp_path / "server.err", "w"), env=env, cwd=tmp_path)

    def manda(obj):
        servidor.stdin.write((json.dumps(obj) + "\n").encode())
        servidor.stdin.flush()

    try:
        manda({"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        assert b'"id":1' in servidor.stdout.readline()
        manda({"jsonrpc": "2.0", "method": "notifications/initialized"})
        manda({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
               "params": {"name": "video.busca", "arguments": {"acao": "consulta", "consulta": "teste de busca"}}})
        assert espera(lambda: pidfile.exists() and pidfile.read_text().strip(), 30), "the tool never started its child"
        pid = int(pidfile.read_text())
        os.kill(servidor.pid, getattr(signal, nome))
        assert servidor.wait(20) == 128 + getattr(signal, nome)
        assert espera(lambda: not vivo(pid), 10), "the child of the running tool outlived the MCP server"
    finally:
        servidor.kill()
        servidor.wait()
        limpa(None, pidfile)


def test_a_burst_of_stop_signals_to_real_mcp_servers_never_hangs_or_leaks_a_child(tmp_path):
    """The real server (a tool running a child in a worker thread), 8 at a time, bursts of 1-4 signals 0-10 ms apart: every server
    exits with 128+n and no child survives."""
    import random

    from conftest import ROOT, offline_env

    rng = random.Random(20261107)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    ok = (128 + signal.SIGTERM, 128 + signal.SIGHUP, 128 + signal.SIGINT)
    env = None
    servidores = []
    try:
        for i in range(8):
            d = tmp_path / f"s{i}"
            d.mkdir()
            pidfile = d / "child.pid"
            falso = bindir / f"tinyfish{i}"
            falso.write_text(f"#!/bin/bash\necho $$ > {pidfile}\nexec sleep 120\n")
            falso.chmod(falso.stat().st_mode | stat.S_IEXEC)
            (d / "bin").mkdir()
            (d / "bin" / "tinyfish").symlink_to(falso)
            env = offline_env(HOME=str(d), PATH=f"{d / 'bin'}{os.pathsep}{os.environ['PATH']}", TINYFISH_API_KEY="x")
            env.pop("SIMPLICIO_OFFLINE", None)
            env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])
            p = subprocess.Popen([sys.executable, "-m", "simplicio_video.mcp_server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=open(d / "server.err", "w"), env=env, cwd=d)
            servidores.append((d, pidfile, p))
        for d, pidfile, p in servidores:
            for obj in ({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},):
                p.stdin.write((json.dumps(obj) + "\n").encode())
                p.stdin.flush()
            assert b'"id":1' in p.stdout.readline()
            for obj in ({"jsonrpc": "2.0", "method": "notifications/initialized"},
                        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": "video.busca", "arguments": {"acao": "consulta", "consulta": "teste de busca"}}}):
                p.stdin.write((json.dumps(obj) + "\n").encode())
                p.stdin.flush()
        pids = []
        for d, pidfile, p in servidores:
            assert espera(lambda pf=pidfile: pf.exists() and pf.read_text().strip(), 30), "the tool never started its child"
            pids.append(int(pidfile.read_text()))
            for _ in range(rng.randint(1, 4)):
                os.kill(p.pid, rng.choice((signal.SIGTERM, signal.SIGHUP, signal.SIGINT)))
                time.sleep(rng.choice((0, 0.001, 0.005, 0.01)))
        for d, pidfile, p in servidores:
            assert p.wait(20) in ok, (d / "server.err").read_text()[-600:]
        assert espera(lambda: not any(vivo(x) for x in pids), 10), "a child outlived its MCP server"
    finally:
        for d, pidfile, p in servidores:
            p.kill()
            p.wait()
            limpa(None, pidfile)


@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_to_the_mcp_server_kills_the_child_of_a_running_tool_even_when_pytest_ignores_hup_and_int(nome, tmp_path):
    """`nohup make check` / `make check &`: pytest starts with SIGHUP and SIGINT ignored. The server the test launches must still
    start with them at their defaults, as it does from a shell (the engine keeps an ignored signal ignored, on purpose)."""
    with sinais_ignorados("SIGHUP", "SIGINT"):
        test_a_stop_signal_to_the_mcp_server_kills_the_child_of_a_running_tool(nome, tmp_path)


def test_a_burst_of_stop_signals_to_real_mcp_servers_never_hangs_or_leaks_a_child_even_when_pytest_ignores_hup_and_int(tmp_path):
    with sinais_ignorados("SIGHUP", "SIGINT"):
        test_a_burst_of_stop_signals_to_real_mcp_servers_never_hangs_or_leaks_a_child(tmp_path)

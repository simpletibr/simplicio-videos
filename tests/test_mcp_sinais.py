"""The real MCP server (stdio), a tool that runs a child in a worker thread, and a SIGTERM to the server: the child must die with it."""
from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys

import pytest
from _orfao import POSIX, SINAIS, espera, limpa, vivo

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

"""Review fixes for the montage registry: the upstream child never inherits the MCP stdio, status probes that touch the network
are skipped offline/under MCP, the MCP surface is bounded, and `open` diagnoses honestly. Offline, fake checkout and fake venv."""
from __future__ import annotations

import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from simplicio_video import mcp_server, montage, tools

FAKE_REGISTRY = '''\
import os, subprocess, sys


class Status:
    def __init__(self, value):
        self.value = value


class FakeTool:
    def __init__(self, name, runtime, tier):
        self.name, self.runtime, self.tier = name, runtime, tier

    def get_status(self):
        subprocess.run(["npm", "view", "hyperframes", "version"], capture_output=True)  # a probe that shells out
        return Status("available")

    def get_info(self):
        return {"name": self.name, "runtime": self.runtime, "tier": self.tier, "capability": "c", "provider": "p",
                "status": self.get_status().value, "stability": "production"}

    def dry_run(self, inputs):
        return {"tool": self.name, "stdin": sys.stdin.read(), "status": self.get_status().value, "inputs": inputs,
                "npm_offline": os.environ.get("npm_config_offline")}


class Registry:
    def __init__(self):
        self._tools = {}

    def discover(self, package_name="tools"):
        os.system("echo NOISE-FROM-A-GRANDCHILD")  # C-level stdout of a grandchild
        for t in (FakeTool("a", "api", "core"), FakeTool("b", "local", "core"), FakeTool("c", "local", "extra")):
            self._tools[t.name] = t

    def list_all(self):
        return list(self._tools)

    def get(self, name):
        return self._tools.get(name)

    def support_envelope(self):
        return {n: t.get_info() for n, t in self._tools.items()}


registry = Registry()
'''

FAKE_BACKLOT = '''\
import os, sys, time
mode = os.environ.get("FAKE_SERVE", "missing")
if sys.argv[1:2] == ["open"]:
    print("backlot: server did not come up in time \\u2014 continuing without the board")
elif mode == "missing":
    import fastapi_ausente_xyz
elif mode == "inuse":
    sys.stderr.write("OSError: [Errno 98] error while attempting to bind on address: address already in use\\n")
    sys.exit(1)
else:
    open(os.environ["FAKE_PID_FILE"], "w").write(str(os.getpid()))
    time.sleep(120)
'''

PROBE_LOG_PY = '#!/bin/sh\nreadlink /proc/self/fd/0 >> "{log}"\nexec "{py}" "$@"\n'


def _exe(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path, monkeypatch):
    om = tmp_path / "om"
    (om / "backlot").mkdir(parents=True)
    (om / "backlot" / "__init__.py").write_text("", encoding="utf8")
    (om / "backlot" / "__main__.py").write_text(FAKE_BACKLOT, encoding="utf8")
    (om / "requirements.txt").write_text("pyyaml\n", encoding="utf8")
    (om / "pipeline_defs").mkdir()
    (om / "tools").mkdir()
    (om / "tools" / "__init__.py").write_text("", encoding="utf8")
    (om / "tools" / "tool_registry.py").write_text(FAKE_REGISTRY, encoding="utf8")
    monkeypatch.setenv("OPENMONTAGE_DIR", str(om))
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", str(tmp_path / "omdata"))
    _exe(montage.venv_python(), f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    shim = tmp_path / "shim"
    log = tmp_path / "npm.log"
    _exe(shim / "npm", f'#!/bin/sh\necho "$@" >> "{log}"\n')
    monkeypatch.setenv("PATH", f"{shim}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    monkeypatch.delenv("SIMPLICIO_MCP", raising=False)
    return om, log


def run(capsys, *argv):
    code = montage.main(list(argv))
    c = capsys.readouterr()
    return code, c.out, c.err


def calls(log: Path) -> int:
    return len(log.read_text().splitlines()) if log.exists() else 0


# ---- F1: the child never inherits fd 0 ----------------------------------------------------------------------------

def test_child_gets_eof_not_the_parents_stdin(env, monkeypatch, capsys):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    r, w = os.pipe()
    os.write(w, b"JSON-RPC-FRAME-THE-CHILD-MUST-NOT-READ")
    os.close(w)
    saved = os.dup(0)
    os.dup2(r, 0)
    try:
        code, out, _ = run(capsys, "estimate", "a", "--input", "{}", "--json")
    finally:
        os.dup2(saved, 0)
        os.close(saved)
        os.close(r)
    assert code == 0 and json.loads(out)["stdin"] == ""


@pytest.mark.skipif(not Path("/proc/self/fd/0").exists(), reason="needs /proc")
def test_status_probe_runs_in_the_venv_python_with_devnull_stdin(env, tmp_path, capsys):
    om, _ = env
    log = tmp_path / "probe.log"
    _exe(montage.venv_python(), PROBE_LOG_PY.format(log=log, py=sys.executable))
    monkey = pytest.MonkeyPatch()
    monkey.setattr(tools, "_git", lambda *a, **k: "0" * 40)
    try:
        code, out, _ = run(capsys, "status", "--json")
    finally:
        monkey.undo()
    assert code == 0 and json.loads(out)["missing_modules"] == []
    assert log.read_text().strip() == "/dev/null"  # the probe ran through the venv python, and its stdin is /dev/null


# ---- F2: no network probes offline or under MCP --------------------------------------------------------------------

@pytest.mark.parametrize("flag", ["SIMPLICIO_OFFLINE", "SIMPLICIO_MCP"])
def test_status_probes_are_skipped_offline_and_under_mcp(env, monkeypatch, capsys, flag):
    _, log = env
    monkeypatch.setenv(flag, "1")
    for argv in (["tools", "list", "--json"], ["envelope", "--json", "--full"], ["tools", "info", "a", "--json"]):
        code, out, _ = run(capsys, *argv)
        assert code == 0 and "unknown (probe skipped)" in out, argv
    code, out, _ = run(capsys, "estimate", "a", "--input", "{}", "--json")
    assert json.loads(out)["npm_offline"] == "true" and json.loads(out)["status"] == "unknown (probe skipped)"
    assert calls(log) == 0


def test_terminal_keeps_the_live_probes(env, capsys):
    _, log = env
    code, out, _ = run(capsys, "tools", "list", "--json")
    assert code == 0 and "unknown" not in out and calls(log) == 3
    assert json.loads(run(capsys, "estimate", "a", "--input", "{}", "--json")[1])["npm_offline"] is None


# ---- F6: grandchild stdout cannot corrupt the JSON ------------------------------------------------------------------

def test_grandchild_stdout_does_not_corrupt_the_json(env, capsys):
    code, out, err = run(capsys, "tools", "list", "--json")
    assert code == 0 and len(json.loads(out)["tools"]) == 3
    assert "NOISE-FROM-A-GRANDCHILD" not in out


# ---- F4: envelope is a summary over MCP ----------------------------------------------------------------------------

def test_envelope_is_a_summary_over_mcp_unless_full(env, monkeypatch, capsys):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    d = json.loads(run(capsys, "envelope", "--json")[1])
    assert "envelope" not in d and d["summary"]["count"] == 3
    assert d["summary"]["by_runtime"] == {"api": 1, "local": 2} and d["summary"]["by_tier"] == {"core": 2, "extra": 1}
    assert d["summary"]["tools"] == ["a", "b", "c"] and "--full" in d["note"]
    assert set(json.loads(run(capsys, "envelope", "--json", "--full")[1])["envelope"]) == {"a", "b", "c"}


def test_envelope_is_full_in_the_terminal(env, capsys):
    assert set(json.loads(run(capsys, "envelope", "--json")[1])["envelope"]) == {"a", "b", "c"}


# ---- F5: relative paths in estimate input over MCP -----------------------------------------------------------------

@pytest.mark.parametrize("value", ["clips/a.mp4", "../x.mp4", "./a.mp4", "~/a.mp4"])
def test_mcp_estimate_rejects_relative_paths(env, monkeypatch, capsys, value):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    code, _, err = run(capsys, "estimate", "a", "--input", json.dumps({"clips": [value]}))
    assert code == 1 and "absolut" in err


def test_mcp_estimate_accepts_absolute_paths_urls_and_prose(env, monkeypatch, capsys):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    body = {"clips": ["/abs/a.mp4"], "u": "https://x.y/z", "prompt": "um gato e/ou um cão"}
    assert run(capsys, "estimate", "a", "--input", json.dumps(body))[0] == 0


def test_terminal_estimate_allows_relative_paths(env, capsys):
    assert run(capsys, "estimate", "a", "--input", '{"clips": ["rel/a.mp4"]}')[0] == 0


# ---- F3: structured input through MCP --------------------------------------------------------------------------------

def test_mcp_input_object_survives_spaces_and_quotes(env, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    r = mcp_server.video_montage("estimate a --json", input={"prompt": "um gato \"preto\"", "n": 2})
    assert r["ok"] is True and r["result"]["inputs"] == {"prompt": "um gato \"preto\"", "n": 2}


def test_mcp_input_only_with_estimate(env):
    r = mcp_server.video_montage("status --json", input={"a": 1})
    assert r["ok"] is False and "estimate" in r["error"]


def test_mcp_description_states_the_limits():
    d = mcp_server.DESC_video_montage
    for word in ("probe", "--full", "absolute", "input"):
        assert word in d


# ---- F7: the `open` diagnosis ---------------------------------------------------------------------------------------

def test_open_diagnosis_kills_a_server_that_stays_up(env, monkeypatch, tmp_path, capsys):
    pid_file = tmp_path / "serve.pid"
    monkeypatch.setenv("FAKE_SERVE", "sleep")
    monkeypatch.setenv("FAKE_PID_FILE", str(pid_file))
    monkeypatch.setattr(montage, "_OPEN_DIAG_TIMEOUT", 1.5)
    code, out, err = run(capsys, "open")
    assert code == 0 and "did not come up" in out
    assert "subiu" in err and "não subiu" not in err
    pid = int(pid_file.read_text())
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("the foreground diagnostic server was left running")


def test_open_diagnosis_address_in_use_means_it_came_up_late(env, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_SERVE", "inuse")
    code, _, err = run(capsys, "open")
    assert code == 0 and "já em uso" in err and "não subiu" not in err


# ---- F8: a relative data dir ------------------------------------------------------------------------------------------

def test_relative_data_dir_becomes_absolute_and_warns_once(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", "rel-data")
    monkeypatch.setattr(montage, "_WARNED_RELATIVE", set(), raising=False)
    d = montage.data_dir()
    assert d == (tmp_path / "rel-data").resolve() and d.is_absolute()
    montage.data_dir()
    err = capsys.readouterr().err
    assert err.count("OPENMONTAGE_DATA_DIR") == 1 and "relativ" in err

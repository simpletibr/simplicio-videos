"""montage setup/status, the OpenMontage venv, `open` diagnostics and the MCP surface. Offline: a fake checkout in tmp_path,
a fake venv python (a shell wrapper around the test interpreter) and recorded setup steps; no pip, no npm, no network."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys

import pytest

from simplicio_video import cli, mcp_server, montage, tools

REQS = "pyyaml>=6.0\nnonexistent-dist-xyz>=1  # never installed\n"

FAKE_BACKLOT = '''\
import sys
if sys.argv[1:2] == ["open"]:
    print("backlot: server did not come up in time \\u2014 continuing without the board")
elif sys.argv[1:2] == ["serve"]:
    import fastapi_ausente_xyz
'''


def _fake_python(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def om(tmp_path, monkeypatch):
    d = tmp_path / "om"
    (d / "backlot").mkdir(parents=True)
    (d / "backlot" / "__init__.py").write_text("", encoding="utf8")
    (d / "backlot" / "__main__.py").write_text(FAKE_BACKLOT, encoding="utf8")
    (d / "requirements.txt").write_text(REQS, encoding="utf8")
    (d / "pipeline_defs").mkdir()
    (d / "remotion-composer").mkdir()
    monkeypatch.setenv("OPENMONTAGE_DIR", str(d))
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", str(tmp_path / "omdata"))
    return d


@pytest.fixture
def venv(om):
    _fake_python(montage.venv_python())
    return montage.venv_python()


def run(capsys, *argv):
    code = montage.main(list(argv))
    c = capsys.readouterr()
    return code, c.out, c.err


# ---- the venv is the interpreter for every upstream command -------------------------------------------------------

def test_data_dir_follows_env_then_simplicio_data(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", str(tmp_path / "x"))
    assert montage.data_dir() == (tmp_path / "x").resolve()
    monkeypatch.delenv("OPENMONTAGE_DATA_DIR")
    assert montage.data_dir().name == "openmontage-data"
    assert str(montage.data_dir()).startswith(os.path.realpath(os.environ["SIMPLICIO_VIDEO_DATA"]))  # hermetic temp dir


def test_upstream_python_without_venv_says_run_setup(om):
    with pytest.raises(montage.MontageError, match="montage setup"):
        montage.upstream_python()


@pytest.mark.parametrize("argv", [["doctor"], ["preflight"], ["open"], ["serve"], ["demo", "--list"], ["tools", "list"],
                                  ["tools", "info", "x"], ["envelope"], ["estimate", "x"], ["rodar.py"]])
def test_every_upstream_command_without_venv_is_a_clean_error(om, capsys, argv):
    code, out, err = run(capsys, *argv)
    assert code == 1
    assert "montage setup" in err and "Traceback" not in err


def test_pipelines_and_status_need_no_venv(om, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, **k: "0" * 40)
    assert run(capsys, "pipelines", "list")[0] == 0
    assert run(capsys, "status", "--json")[0] == 0


@pytest.mark.parametrize("argv,expect", [
    (["doctor"], ["-c"]), (["preflight"], ["-c"]), (["open", "p1"], ["-m", "backlot", "open", "p1"]),
    (["serve", "--port", "1"], ["-m", "backlot", "serve", "--port", "1"]), (["demo", "--list"], ["render_demo.py", "--list"]),
])
def test_commands_use_the_venv_python_and_pythonpath(om, venv, monkeypatch, argv, expect):
    seen = []
    monkeypatch.setattr(montage, "run_child", lambda cmd, **kw: seen.append((cmd, kw)) or 0)
    monkeypatch.setattr(montage, "_run_open", lambda cmd, **kw: seen.append((cmd, kw)) or 0, raising=False)
    assert montage.run_montage(argv) == 0
    cmd, kw = seen[0]
    assert cmd[0] == str(venv)
    assert cmd[1:1 + len(expect)] == expect
    assert kw["cwd"] == om.resolve()
    assert kw["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(om.resolve())


def test_pythonpath_is_joined_with_os_pathsep(om, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "a")
    monkeypatch.setattr(os, "pathsep", ";")
    assert montage._upstream_env(om)["PYTHONPATH"] == f"{om};a"


# ---- setup --------------------------------------------------------------------------------------------------------

@pytest.fixture
def steps(monkeypatch):
    """Record the setup steps; the venv-creation step leaves a fake venv python behind."""
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)  # the hermetic fixture sets it; setup itself refuses offline
    rec = []

    def fake(cmd, cwd=None):
        rec.append((list(cmd), cwd))
        if "venv" in cmd and cmd[1:3] == ["-m", "venv"]:
            _fake_python(montage.venv_python())
        return 0
    monkeypatch.setattr(montage, "_run_step", fake)
    return rec


def test_setup_creates_venv_installs_requirements_and_prints_progress(om, steps, capsys):
    code, out, err = run(capsys, "setup")
    assert code == 0
    assert len(steps) == 2
    assert steps[0][0][1:3] == ["-m", "venv"] and steps[0][0][3] == str(montage.data_dir() / "venv")
    assert steps[1][0] == [str(montage.venv_python()), "-m", "pip", "install", "-r", str(om.resolve() / "requirements.txt")]
    assert steps[1][1] == om.resolve()
    assert re.search(r"\[1/2\].*venv", out) and re.search(r"\[2/2\].*requirements", out)  # a line before each step
    assert "montage tools list" in out  # what to do next


def test_setup_keeps_an_existing_venv(om, venv, steps, capsys):
    code, out, _ = run(capsys, "setup")
    assert code == 0 and len(steps) == 1 and "-r" in steps[0][0] and "[1/1]" in out


def test_setup_remotion_and_piper(om, venv, steps, monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda n: f"/fake/{n}" if n == "npm" else None)
    code, out, _ = run(capsys, "setup", "--remotion", "--piper")
    assert code == 0 and len(steps) == 3
    assert steps[1] == (["/fake/npm", "install"], om.resolve() / "remotion-composer")
    assert steps[2][0] == [str(venv), "-m", "pip", "install", "piper-tts"]
    assert "[3/3]" in out


def test_setup_remotion_without_npm_is_a_clean_error_and_runs_nothing(om, venv, steps, monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    code, _, err = run(capsys, "setup", "--remotion")
    assert code == 1 and "npm" in err and "Traceback" not in err and steps == []


def test_setup_failing_step_stops_and_names_the_step(om, venv, monkeypatch, capsys):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    calls = []
    monkeypatch.setattr(montage, "_run_step", lambda cmd, cwd=None: calls.append(cmd) or 3)
    monkeypatch.setattr(shutil, "which", lambda n: "/fake/npm")
    code, _, err = run(capsys, "setup", "--remotion", "--piper")
    assert code == 1 and len(calls) == 1
    assert "1/3" in err and "3" in err and "Traceback" not in err


def test_setup_refuses_offline(om, steps, monkeypatch, capsys):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    code, _, err = run(capsys, "setup")
    assert code == 1 and "offline" in err and steps == []


def test_setup_without_checkout_offline_points_at_clone(tmp_path, monkeypatch, steps, capsys):
    monkeypatch.setenv("OPENMONTAGE_DIR", str(tmp_path / "ausente"))
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", str(tmp_path / "omdata"))
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    code, _, err = run(capsys, "setup")
    assert code == 1 and "clone" in err and steps == []


def test_setup_help_has_examples(om, capsys):
    with pytest.raises(SystemExit) as e:
        montage.main(["setup", "--help"])
    out = capsys.readouterr().out
    assert e.value.code == 0 and "--remotion" in out and "--piper" in out and "exemplos" in out


# ---- status -------------------------------------------------------------------------------------------------------

def test_status_without_venv(om, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, **k: tools.pinned_ref(tools.get("openmontage")))
    code, out, _ = run(capsys, "status", "--json")
    d = json.loads(out)
    assert code == 0 and d["ok"] is True
    assert d["checkout"]["found"] is True and d["checkout"]["pin_match"] is True
    assert d["venv"]["present"] is False and d["missing_modules"] is None
    assert d["remotion"] is False and d["piper"] is False


def test_status_pin_mismatch_and_missing_modules(om, venv, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, **k: "0" * 40)
    (om / "remotion-composer" / "node_modules").mkdir()
    d = json.loads(run(capsys, "status", "--json")[1])
    assert d["checkout"]["pin_match"] is False
    assert d["venv"]["present"] is True and d["venv"]["python"] == str(venv)
    assert d["missing_modules"] == ["nonexistent-dist-xyz"]  # pyyaml is installed, the invented one is not
    assert d["remotion"] is True


def test_status_without_checkout(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENMONTAGE_DIR", str(tmp_path / "ausente"))
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", str(tmp_path / "omdata"))
    code, out, _ = run(capsys, "status", "--json")
    d = json.loads(out)
    assert code == 0 and d["checkout"]["found"] is False and d["checkout"]["pin_match"] is None


# ---- open: the real reason when backlot does not come up ----------------------------------------------------------

def test_open_surfaces_why_backlot_did_not_come_up(om, venv, capsys):
    code, out, err = run(capsys, "open")
    assert code == 0  # open stays non-fatal, like the upstream
    assert "did not come up" in out
    assert "ModuleNotFoundError" in err and "fastapi_ausente_xyz" in err
    assert "montage setup" in err


# ---- MCP ----------------------------------------------------------------------------------------------------------

def test_mcp_allows_the_read_only_registry(om, venv, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, **k: "0" * 40)
    (om / "pipeline_defs" / "alpha.yaml").write_text("name: alpha\n", encoding="utf8")
    r = mcp_server.video_montage("pipelines list --json")
    assert r["ok"] is True and r["result"]["pipelines"][0]["name"] == "alpha"
    r = mcp_server.video_montage("status --json")
    assert r["ok"] is True and r["result"]["venv"]["present"] is True
    (om / "tools").mkdir()
    (om / "tools" / "__init__.py").write_text("", encoding="utf8")
    (om / "tools" / "tool_registry.py").write_text(
        "class R:\n    def discover(self): pass\n    def support_envelope(self): return {'t': {'name': 't', 'runtime': 'api'}}\n"
        "    def get(self, n): return None\n    def list_all(self): return ['t']\nregistry = R()\n", encoding="utf8")
    r = mcp_server.video_montage("tools list --runtime api --json")
    assert r["ok"] is True and r["result"]["tools"][0]["name"] == "t"
    assert mcp_server.video_montage("envelope --json")["ok"] is True


@pytest.mark.parametrize("args", ["setup", "setup --piper", "serve", "open", "", "demo --list", "clone /tmp/x", "-c print(1)"])
def test_mcp_refuses_what_installs_or_never_ends(args):
    r = mcp_server.video_montage(args)
    assert r["ok"] is False and "terminal" in r["error"], args


def test_mcp_description_lists_the_registry_commands():
    d = mcp_server.DESC_video_montage
    for word in ("pipelines", "tools", "envelope", "estimate", "status", "setup"):
        assert word in d


# ---- help: the engine's own help, never the passthrough (`montage help` ran `python -m help`) ----------------------

def _proibido(*args, **kwargs):
    raise AssertionError("o help não deve clonar nem instalar nada")


HELP_FORMS = [
    (["help"], "simplicio-video montage setup"),
    (["-h"], "simplicio-video montage setup"),
    (["help", "open"], "simplicio-video montage setup"),  # no help of its own here: the usage
    (["help", "setup"], "usage: simplicio-video montage setup"),
    (["help", "tools", "info"], "usage: simplicio-video montage tools info"),
    (["help", "run-tool"], "usage: simplicio-video montage run-tool"),
]


def test_cli_montage_help_with_checkout_and_venv_prints_usage(om, venv, capsys):
    assert cli.main(["montage", "help"]) == 0
    c = capsys.readouterr()
    assert "No module named" not in c.err and "simplicio-video montage setup" in c.out


@pytest.mark.parametrize("argv,marca", HELP_FORMS)
def test_help_never_reaches_the_upstream(om, venv, monkeypatch, capsys, argv, marca):
    ran = []
    monkeypatch.setattr(montage, "run_child", lambda cmd, **kw: ran.append(cmd) or 0)
    monkeypatch.setattr(montage, "_run_open", lambda cmd, **kw: ran.append(cmd) or 0, raising=False)
    code, out, err = run(capsys, *argv)
    assert (code, ran) == (0, []), argv
    assert marca in out and "Traceback" not in err


@pytest.mark.parametrize("sub", ["setup", "status", "tools", "run-tool"])
def test_help_sub_prints_the_subcommands_own_help(om, capsys, sub):
    assert montage.main(["help", sub]) == 0
    da_ajuda = capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        montage.main([sub, "--help"])
    assert e.value.code == 0
    assert da_ajuda and capsys.readouterr().out == da_ajuda


def test_help_without_checkout_prints_usage_and_clones_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENMONTAGE_DIR", str(tmp_path / "sem-checkout"))
    monkeypatch.setattr(montage, "clone_openmontage", _proibido)
    monkeypatch.setattr(montage, "ensure_openmontage_dir", _proibido)
    code, out, err = run(capsys, "help")
    assert code == 0 and "simplicio-video montage setup" in out and "montage clone" in out and "Traceback" not in err


def test_usage_names_every_registry_command():
    for cmd in montage.REGISTRY_COMMANDS:
        assert cmd in montage.USAGE, cmd


def test_mcp_help_is_read_only_and_prints_the_usage(om, venv, monkeypatch):
    ran = []
    monkeypatch.setattr(montage, "run_child", lambda cmd, **kw: ran.append(cmd) or 0)
    monkeypatch.setattr(montage, "clone_openmontage", _proibido)
    r = mcp_server.video_montage("help")
    assert r["ok"] is True and ran == [] and "simplicio-video montage setup" in r["log"]
    r = mcp_server.video_montage("help setup")
    assert r["ok"] is True and ran == [] and "usage: simplicio-video montage setup" in r["log"]

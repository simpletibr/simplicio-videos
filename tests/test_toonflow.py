from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from simplicio_video import cli, mcp_server, tools, toonflow

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(autouse=True)
def _no_toonflow_overrides(monkeypatch, tmp_path):
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
    """Records every subprocess.call as (cmd, cwd, TOONFLOW_DATA_DIR). A step exits 0 unless a test sets fail[(args)]."""
    recorded: list[tuple[list[str], Path | None, str | None]] = []
    fail: dict[tuple[str, ...], int] = {}

    def fake(cmd, cwd=None, env=None):
        recorded.append((list(cmd), cwd, (env or {}).get("TOONFLOW_DATA_DIR")))
        return fail.get(tuple(cmd[1:3]), 0)

    monkeypatch.setattr("subprocess.call", fake)
    return recorded, fail


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
    assert "localhost" in out
    assert calls == []


@pytest.mark.parametrize("args", [["where"], ["serve"]])
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


def test_serve_installs_builds_then_starts_the_server_inside_the_checkout(checkout, bun, calls):
    recorded, _ = calls
    assert toonflow.run_toonflow(["serve"]) == 0
    assert [cmd for cmd, _, _ in recorded] == [
        [bun, "install", "--frozen-lockfile"],
        [bun, "run", "build:server"],
        [bun, "run", "start:server"],
    ]
    assert all(cwd == checkout.resolve() for _, cwd, _ in recorded)


def test_serve_keeps_the_data_outside_the_checkout(checkout, bun, calls, tmp_path):
    recorded, _ = calls
    assert toonflow.run_toonflow(["serve"]) == 0
    data = (tmp_path / "data" / "toonflow-data").resolve()
    assert recorded[-1][2] == str(data)
    assert (data / "workspaces" / "myProject").is_dir()
    assert checkout.resolve() not in data.parents


def test_serve_respects_a_data_dir_the_user_set(checkout, bun, calls, monkeypatch, tmp_path):
    mine = (tmp_path / "meu-toonflow").resolve()
    monkeypatch.setenv("TOONFLOW_DATA_DIR", str(mine))
    recorded, _ = calls
    assert toonflow.run_toonflow(["serve"]) == 0
    assert recorded[-1][2] == str(mine)
    assert (mine / "workspaces" / "myProject").is_dir()


def test_data_dir_is_absolute_because_the_server_runs_inside_the_checkout(monkeypatch, tmp_path):
    # A relative TOONFLOW_DATA_DIR would be read from the checkout by the server but created from the caller's cwd.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOONFLOW_DATA_DIR", "dados/relativos")
    assert toonflow.data_dir().is_absolute()
    assert toonflow.data_dir() == (tmp_path / "dados" / "relativos").resolve()


@pytest.mark.parametrize("step", [("install", "--frozen-lockfile"), ("run", "build:server")])
def test_serve_stops_at_the_first_failing_step(checkout, bun, calls, step):
    recorded, fail = calls
    fail[step] = 3
    assert toonflow.run_toonflow(["serve"]) == 1
    assert recorded[-1][0][1:3] == list(step)
    assert not any("start:server" in cmd for cmd, _, _ in recorded)


def test_serve_ctrl_c_stops_the_server_without_a_traceback(checkout, bun, monkeypatch, capsys):
    def interrupted(cmd, cwd=None, env=None):
        if cmd[1:3] == ["run", "start:server"]:
            raise KeyboardInterrupt
        return 0

    monkeypatch.setattr("subprocess.call", interrupted)
    assert toonflow.run_toonflow(["serve"]) == 0
    assert "Traceback" not in capsys.readouterr().err


def test_serve_refuses_extra_args_because_the_port_is_fixed(checkout, bun, calls):
    recorded, _ = calls
    with pytest.raises(toonflow.ToonflowError, match="não recebe argumentos"):
        toonflow.run_toonflow(["serve", "--port", "5174"])
    assert recorded == []


def test_serve_without_bun_says_where_to_get_it(checkout, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(toonflow.ToonflowError, match="bun"):
        toonflow.run_toonflow(["serve"])


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


def test_mcp_refuses_serve_because_it_blocks_the_server(checkout):
    r = mcp_server.video_toonflow("serve")
    assert r["ok"] is False
    assert "terminal" in r["error"]


def test_mcp_capture_does_not_pass_log_to_functions_that_do_not_take_it():
    # Regression: _capture always passed log=, so every wrapper of a plain run_* function failed with TypeError.
    r = mcp_server._capture(lambda args: 0, ["x"])
    assert r["ok"] is True and r["result"] == 0


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

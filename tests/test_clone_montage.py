from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from simplicio_video import cli, clone, mcp_server, montage


def test_clone_find_hypit_bin_fallback(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/npx" if cmd == "npx" else None)
    bin_cmd = clone.find_hypit_bin()
    assert bin_cmd == ["/usr/bin/npx", "--yes", "@hypit/hypit"]


def test_clone_find_hypit_bin_local(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/hypit" if cmd == "hypit" else None)
    bin_cmd = clone.find_hypit_bin()
    assert bin_cmd == ["/usr/local/bin/hypit"]


def test_clone_find_hypit_bin_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(clone.CloneError, match="Nem `hypit` nem `npx` foram encontrados"):
        clone.find_hypit_bin()


def test_clone_run_hypit_invokes_subprocess(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/hypit" if cmd == "hypit" else None)
    recorded = []
    monkeypatch.setattr("subprocess.call", lambda cmd, cwd=None: recorded.append((cmd, cwd)) or 0)
    ret = clone.run_hypit(["video.mp4"])
    assert ret == 0
    assert recorded == [(["/usr/local/bin/hypit", "video.mp4"], None)]


def test_clone_main_error_handling(monkeypatch, capsys):
    monkeypatch.setattr(clone, "run_hypit", lambda args: (_ for _ in ()).throw(clone.CloneError("falha teste")))
    ret = clone.main([])
    assert ret == 1
    assert "clone: falha teste" in capsys.readouterr().err


def test_montage_find_openmontage_dir_env(monkeypatch, tmp_path):
    d = tmp_path / "custom_openmontage"
    d.mkdir()
    monkeypatch.setenv("OPENMONTAGE_DIR", str(d))
    found = montage.find_openmontage_dir()
    assert found == d.resolve()


def test_montage_find_openmontage_dir_default():
    found = montage.find_openmontage_dir()
    assert found is not None
    assert (found / "backlot").is_dir() or (found / ".git").is_dir()


def test_montage_run_demo_list(monkeypatch):
    recorded = []
    monkeypatch.setattr("subprocess.call", lambda cmd, cwd=None, env=None: recorded.append((cmd, cwd)) or 0)
    ret = montage.run_montage(["demo", "--list"])
    assert ret == 0
    assert len(recorded) == 1
    cmd, cwd = recorded[0]
    assert cmd[1] == "render_demo.py"
    assert cmd[2] == "--list"


def test_montage_run_open_subcommand(monkeypatch):
    recorded = []
    monkeypatch.setattr("subprocess.call", lambda cmd, cwd=None, env=None: recorded.append((cmd, cwd)) or 0)
    ret = montage.run_montage(["open", "proj-123"])
    assert ret == 0
    assert len(recorded) == 1
    cmd, cwd = recorded[0]
    assert cmd[1:4] == ["-m", "backlot", "open"]
    assert cmd[4] == "proj-123"


def test_cli_dispatch_clone(monkeypatch):
    recorded = []
    monkeypatch.setattr(clone, "run_hypit", lambda args: recorded.append(args) or 0)
    ret = cli.main(["clone", "--test", "arg"])
    assert ret == 0
    assert recorded == [["--test", "arg"]]


def test_cli_dispatch_montage(monkeypatch):
    recorded = []
    monkeypatch.setattr(montage, "run_montage", lambda args: recorded.append(args) or 0)
    ret = cli.main(["montage", "demo", "--list"])
    assert ret == 0
    assert recorded == [["demo", "--list"]]


def test_mcp_tools_include_clone_and_montage():
    tool_names = [name for name, fn, desc in mcp_server.TOOLS]
    assert "video.clone" in tool_names
    assert "video.montage" in tool_names


def test_realoficial_config_is_mcp_remote(capsys):
    from simplicio_video import realoficial
    assert realoficial.run_realoficial(["config"]) == 0
    cfg = __import__("json").loads(capsys.readouterr().out)
    assert cfg["mcpServers"]["realoficial"]["args"] == ["-y", "mcp-remote", "https://api.realoficial.com.br/mcp"]


def test_opencut_dispatch_and_missing(monkeypatch):
    from simplicio_video import opencut
    monkeypatch.setattr(opencut, "find_opencut_dir", lambda: None)
    assert cli.main(["opencut", "dev"]) == 1

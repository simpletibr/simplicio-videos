"""match-cut track: pinned skill checkout that the engine only downloads and points at. Nothing here touches the network."""
from __future__ import annotations

import re

import pytest

from simplicio_video import cli, matchcut, mcp_server, tools

SHA40 = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.delenv("MATCHCUT_DIR", raising=False)
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    d = tmp_path / "matchcut"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: match-cut\n---\n", encoding="utf8")
    monkeypatch.setenv("MATCHCUT_DIR", str(d))
    return d


def test_matchcut_is_pinned_to_a_full_commit_under_mit():
    t = tools.get("matchcut")
    assert t.kind == "git" and t.source == "https://github.com/Sac-Y/match-cut"
    assert t.ref == "b51c98f5c795b046ceb1c69396368dbabd88d5d9" and SHA40.match(t.ref)
    assert t.license == "MIT" and t.marker == "SKILL.md"
    assert "Renoise" in t.note
    assert tools.COMMANDS["matchcut"] == "matchcut"


def test_where_prints_the_skill_path(checkout, capsys):
    assert cli.main(["matchcut", "where"]) == 0
    assert capsys.readouterr().out.strip() == str(checkout.resolve() / "SKILL.md")


def test_where_without_a_checkout_says_how_to_clone(capsys):
    assert cli.main(["matchcut", "where"]) == 1
    assert "matchcut clone" in capsys.readouterr().err


def test_status_without_a_checkout(capsys):
    assert cli.main(["matchcut", "status"]) == 0
    out = capsys.readouterr().out
    assert tools.get("matchcut").ref in out and "instalado: não" in out


def test_status_with_a_checkout_shows_the_skill_file(checkout, capsys, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: tools.get("matchcut").ref)
    assert cli.main(["matchcut", "status"]) == 0
    out = capsys.readouterr().out
    assert "instalado: sim" in out and str(checkout.resolve() / "SKILL.md") in out and "diferente" not in out


def test_unknown_subcommand_is_an_error():
    with pytest.raises(matchcut.MatchcutError, match="clone|where|status"):
        matchcut.run_matchcut(["serve"])


def test_help_says_it_only_downloads_and_needs_renoise(capsys):
    assert matchcut.run_matchcut(["--help"]) == 0
    out = capsys.readouterr().out
    for word in ("clone", "where", "status", "Renoise", "créditos", "MATCHCUT_DIR", "não roda o skill"):
        assert word in out


def test_clone_refuses_offline_mode(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(matchcut.MatchcutError, match="offline"):
        matchcut.clone_matchcut()


def test_mcp_tool_reads_and_refuses_the_rest(checkout, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: tools.get("matchcut").ref)
    assert mcp_server.video_matchcut("where")["ok"] is True
    assert mcp_server.video_matchcut("status")["ok"] is True
    assert mcp_server.video_matchcut("clone /tmp/x")["ok"] is False
    assert mcp_server.video_matchcut("where extra")["ok"] is False
    assert mcp_server.video_matchcut("run")["ok"] is False

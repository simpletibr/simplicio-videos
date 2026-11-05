"""Hypit (`clone`) over MCP: a closed allowlist, the `--help` passthrough and `clone status`. Offline: Hypit is never run."""
import json

import pytest

from simplicio_video import clone, mcp_server
from simplicio_video.cli import main


@pytest.fixture
def chamadas(monkeypatch):
    rec = []
    monkeypatch.setattr(clone, "run_hypit", lambda args: rec.append(list(args)) or 0)
    return rec


ALLOWED = ["help", "help build", "version", "doctor", "check x.md", "plan x.md --json", "pricing x.md", "status b-1", "builds --limit 5",
           "history out", "activity", "inspect b-1", "logs b-1 --lines 20", "paths", "get b-1 --output v --to /tmp/out/v.mp4",
           "media probe /tmp/a.mp4 --json", "media frames /tmp/a.mp4", "media tile /tmp/a.mp4", "media tiles /tmp/a.mp4",
           "media boundaries /tmp/a.mp4", "media cut /tmp/a.mp4", "vocabulary", "--help", "-h", "doctor --help"]


@pytest.mark.parametrize("args", ALLOWED)
def test_mcp_allows_the_read_only_and_local_commands(chamadas, args):
    r = mcp_server.video_clone(args)
    assert r["ok"] is True, r
    assert chamadas == [args.split()]


REFUSED = ["build x.md", "build x.md --follow", "studio", "auth", "auth login", "runtime up", "runtime down", "packages install x",
           "capture install-browser", "capture run", "media fetch https://example.com/v", "media prepare-fetch", "media",
           "transcribe a.wav", "measure a.wav", "cancel b-1", "programs", "result b-1", "_worker", "snapshot", "novo-comando", "",
           "--json build x.md", "get b-1 --output v", "get b-1 --output v --to rel/out.mp4", "get b-1 --output v --to ../out.mp4",
           "media nova"]


@pytest.mark.parametrize("args", REFUSED)
def test_mcp_refuses_everything_else_with_a_terminal_error(chamadas, args):
    r = mcp_server.video_clone(args)
    assert r["ok"] is False, r
    assert "terminal" in r["error"]
    assert chamadas == []


def test_media_fetch_points_to_the_gated_command(chamadas):
    r = mcp_server.video_clone("media fetch https://example.com/v")
    assert "simplicio-video media fetch --autorizo" in r["error"]
    assert "simplicio-video media fetch --autorizo" in mcp_server.video_clone("media prepare-fetch")["error"]


def test_the_reason_is_named(chamadas):
    assert "studio" in mcp_server.video_clone("studio")["error"]
    assert "build" in mcp_server.video_clone("build x.md")["error"]


def test_list_args_are_checked_too(chamadas):
    assert mcp_server.video_clone(["build", "x.md"])["ok"] is False
    assert mcp_server.video_clone(["get", "b", "--output", "v", "--to", "/tmp/a space/v.mp4"])["ok"] is True


def test_description_states_the_allowlist():
    d = mcp_server.DESC_video_clone
    assert "terminal" in d and "build" in d and "studio" in d and "media fetch" in d and "doctor" in d


def test_help_after_clone_goes_to_hypit(chamadas):
    for a in (["--help"], ["-h"], ["build", "--help"], ["help", "build"]):
        assert main(["clone", *a]) == 0
        assert chamadas[-1] == a


def test_engine_help_is_still_reachable(chamadas, capsys):
    with pytest.raises(SystemExit) as e:  # argparse prints the help and exits
        main(["clone", "--engine-help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert chamadas == [] and "argumentos repassados ao CLI do Hypit" in out


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    for v in ("HYPIT_DIR", "SIMPLICIO_HYPIT_REF", "SIMPLICIO_HYPIT_DIR"):
        monkeypatch.delenv(v, raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    return bin_dir


def _fake(bin_dir, nome, saida):
    p = bin_dir / nome
    p.write_text(f"#!/bin/sh\necho '{saida}'\n")
    p.chmod(0o755)


def _json(argv, capsys):
    rc = main(argv)
    return rc, json.loads(capsys.readouterr().out)


def test_clone_status_ready_with_npx_and_node(ambiente, capsys):
    _fake(ambiente, "npx", "10.0.0")
    _fake(ambiente, "node", "v22.15.0")
    rc, r = _json(["clone", "status", "--json"], capsys)
    assert rc == 0 and r["ok"] is True
    assert r["pinned"] == "0.2.17" and r["package"] == "@hypit/hypit"
    assert r["source"] == "npx" and r["binary"] is None and r["npx"].endswith("/npx")
    assert r["node"]["version"] == "22.15.0" and r["node"]["ok"] is True and r["node"]["minimum"] == "22.15"


def test_clone_status_old_node(ambiente, capsys):
    _fake(ambiente, "npx", "10.0.0")
    _fake(ambiente, "node", "v22.14.9")
    rc, r = _json(["clone", "status", "--json"], capsys)
    assert rc == 1 and r["ok"] is False and r["node"]["ok"] is False and r["source"] is None


def test_clone_status_nothing_installed(ambiente, capsys):
    rc, r = _json(["clone", "status", "--json"], capsys)
    assert rc == 1 and r["ok"] is False and r["npx"] is None and r["node"]["version"] is None


def test_clone_status_prefers_the_local_binary(ambiente, capsys):
    _fake(ambiente, "hypit", "0.2.17")
    _fake(ambiente, "node", "v22.15.0")
    rc, r = _json(["clone", "status", "--json"], capsys)
    assert rc == 0 and r["source"] == "path" and r["binary"].endswith("/hypit")


def test_clone_status_with_a_build_id_is_hypits(chamadas):
    assert main(["clone", "status", "b-1"]) == 0
    assert chamadas == [["status", "b-1"]]


def test_clone_status_text(ambiente, capsys):
    _fake(ambiente, "npx", "10.0.0")
    _fake(ambiente, "node", "v22.15.0")
    assert main(["clone", "status"]) == 0
    out = capsys.readouterr().out
    assert "0.2.17" in out and "npx" in out and "22.15" in out


def test_status_and_tools_see_hypit_through_npx(ambiente, capsys):
    _fake(ambiente, "npx", "10.0.0")
    _fake(ambiente, "node", "v22.15.0")
    _, rep = _json(["status", "--json"], capsys)
    by = {t["name"]: t for t in rep["tools"]}
    assert by["hypit"]["installed"] is True and by["hypit"]["source"] == "npx"
    assert by["tinyfish"]["installed"] is False  # busca only uses a binary on PATH, never npx
    assert main(["tools", "--json"]) == 0
    rows = {r["name"]: r for r in json.loads(capsys.readouterr().out)}
    assert rows["hypit"]["installed"] is True and rows["hypit"]["source"] == "npx"
    assert rows["tinyfish"]["installed"] is False


def test_status_does_not_count_npx_when_node_is_old(ambiente, capsys):
    _fake(ambiente, "npx", "10.0.0")
    _fake(ambiente, "node", "v20.0.0")
    _, rep = _json(["status", "--json"], capsys)
    assert {t["name"]: t for t in rep["tools"]}["hypit"]["installed"] is False

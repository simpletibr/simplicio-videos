from __future__ import annotations

import json
import re
import socket
import stat
from pathlib import Path

import pytest

from simplicio_video import cli, mcp_server, opencut, tools

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = """# Environment variables example
NODE_ENV=development
NEXT_PUBLIC_SITE_URL=http://localhost:3000
NEXT_PUBLIC_MARBLE_API_URL=https://api.marblecms.com
DATABASE_URL="postgresql://opencut:opencut@localhost:5432/opencut"
BETTER_AUTH_SECRET=your_better_auth_secret
UPSTASH_REDIS_REST_URL=http://localhost:8079
UPSTASH_REDIS_REST_TOKEN=example_token
MARBLE_WORKSPACE_KEY=your_workspace_key_here
FREESOUND_CLIENT_ID=your_client_id_here
FREESOUND_API_KEY=your_api_key_here
"""
REQUIRED = ("NEXT_PUBLIC_MARBLE_API_URL", "DATABASE_URL", "BETTER_AUTH_SECRET", "UPSTASH_REDIS_REST_URL",
            "UPSTASH_REDIS_REST_TOKEN", "MARBLE_WORKSPACE_KEY", "FREESOUND_CLIENT_ID", "FREESOUND_API_KEY")


@pytest.fixture(autouse=True)
def _isolado(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.delenv("OPENCUT_DIR", raising=False)
    monkeypatch.delenv("SIMPLICIO_OPENCUT_REF", raising=False)


@pytest.fixture
def checkout(monkeypatch, tmp_path):
    d = tmp_path / "opencut"
    (d / "apps" / "web").mkdir(parents=True)
    (d / "package.json").write_text("{}")
    (d / "apps" / "web" / ".env.example").write_text(EXAMPLE)
    monkeypatch.setenv("OPENCUT_DIR", str(d))
    return d


@pytest.fixture
def bun(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/bun" if cmd == "bun" else None)


@pytest.fixture
def calls(monkeypatch):
    recorded: list[tuple[list[str], Path | None]] = []
    monkeypatch.setattr("subprocess.call", lambda cmd, cwd=None, **k: recorded.append((list(cmd), cwd)) or 0)
    return recorded


def _env(d: Path) -> dict[str, str]:
    out = {}
    for line in (d / "apps" / "web" / ".env.local").read_text().splitlines():
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            out[k] = v.strip('"')
    return out


# --- dev: .env.local ---------------------------------------------------------------------------------------------

def test_dev_creates_env_local_from_the_example_with_a_random_secret(checkout, bun, calls, capsys):
    assert opencut.run_opencut(["dev"]) == 0
    env = _env(checkout)
    assert all(env.get(k) for k in REQUIRED)
    assert env["DATABASE_URL"].startswith("postgresql://")
    assert re.fullmatch(r"[0-9a-f]{64}", env["BETTER_AUTH_SECRET"])
    cap = capsys.readouterr()
    assert env["BETTER_AUTH_SECRET"] not in cap.out + cap.err


def test_dev_env_local_is_private_and_secret_differs_per_checkout(checkout, bun, calls):
    opencut.run_opencut(["dev"])
    path = checkout / "apps" / "web" / ".env.local"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    first = _env(checkout)["BETTER_AUTH_SECRET"]
    path.unlink()
    opencut.run_opencut(["dev"])
    assert _env(checkout)["BETTER_AUTH_SECRET"] != first


def test_dev_never_overwrites_an_existing_env_local(checkout, bun, calls):
    path = checkout / "apps" / "web" / ".env.local"
    path.write_text("DATABASE_URL=postgresql://meu/banco\n")
    assert opencut.run_opencut(["dev"]) == 0
    assert path.read_text() == "DATABASE_URL=postgresql://meu/banco\n"


def test_dev_without_env_example_still_writes_every_required_key(checkout, bun, calls):
    (checkout / "apps" / "web" / ".env.example").unlink()
    opencut.run_opencut(["dev"])
    assert all(_env(checkout).get(k) for k in REQUIRED)


def test_dev_completes_keys_the_example_lacks(checkout, bun, calls):
    (checkout / "apps" / "web" / ".env.example").write_text("NODE_ENV=development\n")
    opencut.run_opencut(["dev"])
    assert all(_env(checkout).get(k) for k in REQUIRED)


# --- dev: bind ---------------------------------------------------------------------------------------------------

def _dev_cmd(calls):
    return [c for c, _ in calls if c[1:2] != ["install"]][-1]


def test_dev_runs_next_dev_from_apps_web_because_turbo_rejects_hostname(checkout, bun, calls):
    opencut.run_opencut(["dev"])
    cmd, cwd = calls[-1]
    assert cmd[:3] == ["/usr/bin/bun", "run", "dev"] and cwd == checkout / "apps" / "web"


def test_dev_binds_to_loopback_by_default(checkout, bun, calls):
    opencut.run_opencut(["dev"])
    cmd = _dev_cmd(calls)
    assert cmd[-2:] == ["--hostname", "127.0.0.1"]
    assert "0.0.0.0" not in cmd


def test_dev_installs_before_running(checkout, bun, calls):
    opencut.run_opencut(["dev"])
    assert calls[0][0] == ["/usr/bin/bun", "install"] and calls[0][1] == checkout


def test_dev_lan_binds_every_interface_and_says_so(checkout, bun, calls, capsys):
    opencut.run_opencut(["dev", "--lan"])
    assert _dev_cmd(calls)[-2:] == ["--hostname", "0.0.0.0"]
    cap = capsys.readouterr()
    assert "0.0.0.0" in cap.out + cap.err


def test_dev_does_not_forward_unknown_flags(checkout, bun, calls):
    with pytest.raises(opencut.OpenCutError, match="--lan"):
        opencut.run_opencut(["dev", "--hostname", "0.0.0.0"])
    assert calls == []


def test_dev_without_bun_says_where_to_get_it(checkout, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(opencut.OpenCutError, match="bun"):
        opencut.run_opencut(["dev"])


def test_dev_prints_the_address_without_secrets(checkout, bun, calls, capsys):
    opencut.run_opencut(["dev"])
    out = capsys.readouterr().out
    assert "127.0.0.1:3000" in out and ".env.local" in out
    assert _env(checkout)["BETTER_AUTH_SECRET"] not in out


def test_help_documents_services_and_lan(capsys):
    assert opencut.run_opencut(["--help"]) == 0
    out = capsys.readouterr().out
    for word in ("--lan", "127.0.0.1", ".env.local", "status", "Postgres", "Redis", "opencut-classic"):
        assert word in out, word


# --- status ------------------------------------------------------------------------------------------------------

def _status(capsys, *args):
    rc = opencut.run_opencut(["status", *args])
    return rc, capsys.readouterr().out


def test_status_without_checkout_reports_it_and_exits_0(capsys, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setattr(opencut, "_port_free", lambda port, host="127.0.0.1": True)
    rc, out = _status(capsys, "--json")
    data = json.loads(out)
    assert rc == 0
    assert data["checkout"] is None and data["pin_match"] is False and data["bun"] is False
    assert data["env_local"] is False and data["node_modules"] is False


def test_status_json_reports_the_fields(checkout, bun, monkeypatch, capsys):
    pin = tools.pinned_ref(tools.get("opencut"))
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: pin)
    (checkout / "node_modules").mkdir()
    (checkout / "apps" / "web" / ".env.local").write_text("BETTER_AUTH_SECRET=segredo-xyz\n")
    monkeypatch.setattr(opencut, "_port_free", lambda port, host="127.0.0.1": True)
    rc, out = _status(capsys, "--json")
    data = json.loads(out)
    assert rc == 0
    assert data["checkout"] == str(checkout.resolve())
    assert data["pin"] == pin and data["head"] == pin and data["pin_match"] is True
    assert data["bun"] is True and data["node_modules"] is True and data["env_local"] is True
    assert data["port"] == 3000 and data["port_free"] is True
    assert "segredo-xyz" not in out


def test_status_detects_a_pin_mismatch_and_a_busy_port(checkout, bun, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "0" * 40)
    monkeypatch.setattr(opencut, "_port_free", lambda port, host="127.0.0.1": False)
    _, out = _status(capsys, "--json")
    data = json.loads(out)
    assert data["pin_match"] is False and data["head"] == "0" * 40
    assert data["port_free"] is False and data["env_local"] is False and data["node_modules"] is False


def test_status_text_never_prints_env_values(checkout, bun, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "0" * 40)
    monkeypatch.setattr(opencut, "_port_free", lambda port, host="127.0.0.1": True)
    (checkout / "apps" / "web" / ".env.local").write_text(
        "BETTER_AUTH_SECRET=segredo-xyz\nDATABASE_URL=postgresql://u:senha@h/d\n")
    _, out = _status(capsys)
    assert ".env.local" in out and "segredo-xyz" not in out and "senha" not in out


def test_status_rejects_unknown_flags(checkout):
    with pytest.raises(opencut.OpenCutError):
        opencut.run_opencut(["status", "--xml"])


@pytest.mark.parametrize("rc,free", [(0, False), (111, True)])
def test_port_free_connects_to_loopback_only(monkeypatch, rc, free):
    seen = []

    class FakeSocket:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, t): pass
        def connect_ex(self, addr):
            seen.append(addr)
            return rc

    monkeypatch.setattr(socket, "socket", FakeSocket)
    assert opencut._port_free(3000) is free
    assert seen == [("127.0.0.1", 3000)]


# --- MCP / CLI ---------------------------------------------------------------------------------------------------

def test_cli_opencut_error_exits_1(monkeypatch, capsys):
    def boom(args):
        raise opencut.OpenCutError("falhou")
    monkeypatch.setattr(opencut, "run_opencut", boom)
    assert cli.main(["opencut", "dev"]) == 1
    assert "falhou" in capsys.readouterr().err


def test_mcp_description_links_the_classic_repo_matching_the_pin():
    desc = mcp_server.DESC_video_opencut
    assert tools.get("opencut").source in desc
    assert "OpenCut-app/OpenCut)" not in desc and "OpenCut-app/OpenCut " not in desc
    assert "status" in desc and "terminal" in desc


def test_mcp_snapshot_uses_the_same_description():
    snap = json.loads((ROOT / "tests" / "data" / "mcp_tools_list.snapshot.json").read_text())
    entry = next(t for t in snap["tools"] if t["name"] == "video.opencut")
    assert entry["description"] == mcp_server.DESC_video_opencut


@pytest.mark.parametrize("args", ["dev", "dev --lan", "clone /tmp/x"])
def test_mcp_refuses_dev_and_clone_into_a_dir(args):
    r = mcp_server.video_opencut(args)
    assert r["ok"] is False and "terminal" in r["error"]


@pytest.mark.parametrize("args", ["status --json", "status", "where", "--help"])
def test_mcp_allows_status_where_and_help(checkout, bun, monkeypatch, args):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "0" * 40)
    monkeypatch.setattr(opencut, "_port_free", lambda port, host="127.0.0.1": True)
    r = mcp_server.video_opencut(args)
    assert r["ok"] is True, r


def test_mcp_status_json_is_parsed(checkout, bun, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "0" * 40)
    monkeypatch.setattr(opencut, "_port_free", lambda port, host="127.0.0.1": True)
    r = mcp_server.video_opencut("status --json")
    assert r["result"]["checkout"] == str(checkout.resolve())

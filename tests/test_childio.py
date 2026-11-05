"""childio.run_child: under the MCP stdio server a child must never touch fds 0/1 (JSON-RPC stream)."""
import ast
import contextlib
import io
import os
import sys
from pathlib import Path

import pytest

from simplicio_video import childio

SRC = Path(__file__).resolve().parents[1] / "src" / "simplicio_video"
CHILD = "import sys; print('child-out'); print('child-err', file=sys.stderr); sys.stdin.read(); sys.exit(7)"


def _run(env_mcp: bool, monkeypatch):
    if env_mcp:
        monkeypatch.setenv("SIMPLICIO_MCP", "1")
    else:
        monkeypatch.delenv("SIMPLICIO_MCP", raising=False)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = childio.run_child([sys.executable, "-c", CHILD])
    return rc, out.getvalue(), err.getvalue()


def test_mcp_mode_never_touches_fd1_and_does_not_read_stdin(capfd, monkeypatch):
    rc, out, err = _run(True, monkeypatch)
    cap = capfd.readouterr()
    assert cap.out == "" and cap.err == ""  # nothing reached the real fds
    assert rc == 7  # stdin was /dev/null: read() returned at once
    assert "child-out" in out and "child-err" in err  # re-emitted through Python's streams, which _cli captures


def test_mcp_mode_forwards_cwd_and_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = childio.run_child([sys.executable, "-c", "import os; print(os.getcwd(), os.environ['XV'])"],
                               cwd=tmp_path, env={**os.environ, "XV": "ok"})
    assert rc == 0 and out.getvalue().split() == [str(tmp_path.resolve()), "ok"]


def test_terminal_mode_inherits_the_terminal(capfd, monkeypatch):
    monkeypatch.delenv("SIMPLICIO_MCP", raising=False)
    rc = childio.run_child([sys.executable, "-c", "import sys; print('child-out'); sys.exit(3)"])
    assert rc == 3
    assert capfd.readouterr().out == "child-out\n"  # straight to fd 1, as subprocess.call


def test_main_sets_the_mcp_flag(monkeypatch):
    from simplicio_video import mcp_server

    class Stub:
        def run(self, transport):
            seen.append((transport, os.environ.get("SIMPLICIO_MCP")))
    seen = []
    monkeypatch.setenv("SIMPLICIO_MCP", "0")  # restored on teardown, so the flag does not leak into other tests
    monkeypatch.setattr(mcp_server, "build_server", lambda: Stub())
    mcp_server.main()
    assert seen == [("stdio", "1")]


# ---- lint: no bare child process in any module reachable from the MCP server ----
def _imports(rel: str) -> set[str]:
    """Package-internal modules `rel` imports (at module level or inside functions), as paths relative to SRC."""
    tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
    pkg = list(Path(rel).parent.parts)
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level:
            base = pkg[:len(pkg) - (n.level - 1)]
            mod = n.module.split(".") if n.module else []
            if mod:
                out.add("/".join(base + mod))
            out.update("/".join(base + mod + [a.name]) for a in n.names)
    return out


def _reachable() -> list[str]:
    seen, todo = set(), ["mcp_server.py"]
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        for m in _imports(rel):
            todo += [c for c in (m + ".py", m + "/__init__.py") if (SRC / c).exists()]
    return sorted(seen - {"childio.py"})


# Computed from mcp_server's imports (mcp_server runs cli.main, so the whole CLI is in): a new module is covered at once.
SCAN = _reachable()
# (module, function) -> why a bare call is safe. Everything else must pass stdin= and capture stdout/stderr, or use run_child.
ALLOW = {
    ("rea_video.py", "_setup"): "setup is terminal-only: video.rea-video accepts where|status|clone",
    ("rea_video.py", "_run_upstream"): "analysis commands are terminal-only: video.rea-video refuses them",
    ("rea_video.py", "_ocr_state"): "the probe is `python -c` that prints nothing and never reads stdin",
    ("toonflow.py", "_serve"): "serve never ends and is refused by video.toonflow",
    ("moneyprinter.py", "_setup"): "setup/serve are terminal-only (video.moneyprinter refuses them)",
    ("moneyprinter.py", "_serve"): "serve never ends and is refused by video.moneyprinter",
    ("opencut.py", "run_opencut"): "dev never ends and is refused by video.opencut",
    ("commands/install.py", "_run_setup"): "interactive setup runs only with a TTY (_tty guard); MCP refuses it",
    ("commands/update.py", "_run"): "installing an update is terminal-only; MCP only does --check/--dry-run",
}
SUBPROCESS_FUNCS = {"call", "run", "Popen", "check_call", "check_output"}


def _bare_calls(rel: str):
    tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
    found = []

    def visit(node, fn):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
        if isinstance(node, ast.ImportFrom) and node.module in ("subprocess", "os") and node.level == 0:
            found.append((rel, fn, node.lineno))  # `from subprocess import run` would hide the call from this lint
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner, attr = node.func.value.id, node.func.attr
            kws = {k.arg for k in node.keywords}
            is_sub = (owner == "subprocess" and attr in SUBPROCESS_FUNCS) or (
                owner == "asyncio" and attr in ("create_subprocess_exec", "create_subprocess_shell"))
            if owner == "os" and attr in ("system", "popen", "spawnv", "spawnvp", "execv", "execvp"):
                found.append((rel, fn, node.lineno))
            elif is_sub:
                captured = "capture_output" in kws or {"stdout", "stderr"} <= kws or (attr == "check_output" and "stderr" in kws)
                if None in kws or not (captured and ({"stdin", "input"} & kws)):
                    found.append((rel, fn, node.lineno))
        for ch in ast.iter_child_nodes(node):
            visit(ch, fn)
    visit(tree, None)
    return found


def test_scan_follows_mcp_server_imports():
    assert {"voice.py", "voice_clone.py", "cli.py", "media.py", "render.py", "commands/doctor.py"} <= set(SCAN)
    # mcp_server imports voice lazily inside a tool function: the walk must see function-level imports too
    assert "voice.py" in {m + ".py" for m in _imports("mcp_server.py")}


@pytest.mark.parametrize("rel", SCAN)
def test_no_bare_subprocess_in_mcp_reachable_modules(rel):
    bad = [(r, fn, ln) for r, fn, ln in _bare_calls(rel) if (r, fn) not in ALLOW]
    assert not bad, f"use childio.run_child (or stdin=subprocess.DEVNULL plus captured stdout/stderr): {bad}"


def test_allowlist_has_no_stale_entries():
    live = {(r, fn) for rel in SCAN for r, fn, _ in _bare_calls(rel)}
    assert set(ALLOW) <= live, f"stale allowlist entries: {set(ALLOW) - live}"

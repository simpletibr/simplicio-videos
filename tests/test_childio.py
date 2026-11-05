"""childio.run_child: under the MCP stdio server a child must never touch fds 0/1 (JSON-RPC stream)."""
import ast
import contextlib
import io
import os
import sys
import threading
import time
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
# engine/remote_render.py is not imported: it is the script a remote (Colab/Kaggle) session runs, but it keeps the same rule.
SCAN = _reachable() + ["engine/remote_render.py"]
# (module, function) -> why a bare call is safe. Everything else must pass stdin= and capture stdout/stderr, or use run_child.
ALLOW = {
    ("rea_video.py", "_setup"): "setup is terminal-only: video.rea-video accepts where|status|clone",
    ("rea_video.py", "_run_upstream"): "analysis commands are terminal-only: video.rea-video refuses them",
    ("rea_video.py", "_ocr_state"): "the probe is `python -c` that prints nothing and never reads stdin",
    ("toonflow.py", "_serve"): "serve never ends and is refused by video.toonflow",
    ("toonflow.py", "_run_server"): "only called by _serve (refused by video.toonflow); the server keeps the terminal",
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
                if not (captured and ({"stdin", "input"} & kws)):
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


def test_mcp_mode_does_not_wait_for_grandchildren(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    t0 = time.monotonic()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        rc = childio.run_child(["sh", "-c", "(sleep 4 &); echo done"])
    assert rc == 0 and out.getvalue().strip() == "done"
    assert time.monotonic() - t0 < 2.5  # a pipe would hold run() until the background sleep ended


def test_mcp_mode_decodes_as_utf8_with_replacement(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    code = "import sys; sys.stdout.buffer.write('ação'.encode() + b'\\xff')"
    with contextlib.redirect_stdout(io.StringIO()) as out:
        childio.run_child([sys.executable, "-c", code])
    assert out.getvalue() == "ação�"


def test_check_child_raises_on_failure(monkeypatch):
    import subprocess
    monkeypatch.delenv("SIMPLICIO_MCP", raising=False)
    childio.check_child([sys.executable, "-c", "pass"])
    with pytest.raises(subprocess.CalledProcessError) as e:
        childio.check_child([sys.executable, "-c", "import sys; sys.exit(5)"])
    assert e.value.returncode == 5


FIXTURE = Path(__file__).parent / "fixtures" / "mini"


def _voice_under_mcp(tmp_path, monkeypatch, provider):
    import shutil
    from simplicio_video import mcp_server
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    d = tmp_path / "mini"
    shutil.copytree(FIXTURE, d)
    return mcp_server.video_voice(str(d / "contract.yaml"), provider=provider, force=True)


def test_video_voice_file_provider_keeps_fd1_clean(tmp_path, monkeypatch, capfd):
    r = _voice_under_mcp(tmp_path, monkeypatch, "file")
    cap = capfd.readouterr()
    assert r["ok"], r
    assert cap.out == ""


def test_video_voice_local_provider_child_output_stays_off_fd1(tmp_path, monkeypatch, capfd):
    """The kokoro child (voice.py _local) printed straight to fd 1 before; a fake interpreter stands in for it."""
    fake = tmp_path / "fakepy"
    fake.write_text('#!/bin/sh\necho NOISE-ON-STDOUT\necho NOISE-ON-STDERR >&2\n'
                    f'exec cp {FIXTURE}/vo/line-01.wav "$(eval echo \\${{$#}})"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("SIMPLICIO_TTS_PY", str(fake))
    r = _voice_under_mcp(tmp_path, monkeypatch, "local")
    cap = capfd.readouterr()
    assert r["ok"], r
    assert cap.out == ""  # fd 2 is not the JSON-RPC stream: the stderr noise may land there
    assert "NOISE-ON-STDOUT" in r["log"]


def test_mcp_capture_is_safe_under_concurrent_tool_calls():
    """mcp 2.x runs sync tools in worker threads: redirect_stdout is process-wide, so calls must not interleave."""
    from simplicio_video import mcp_server
    before = sys.stdout

    def fn(tag, log):
        for _ in range(3):
            print(tag)
            time.sleep(0.01)
        return tag

    results = {}

    def work(i):
        results[i] = mcp_server._capture(fn, f"T{i}")

    ts = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sys.stdout is before
    for i, r in results.items():
        assert r["ok"] and r["log"].split() == [f"T{i}"] * 3, r

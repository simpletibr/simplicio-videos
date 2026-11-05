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
        elif isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] == "simplicio_video":
            mod = n.module.split(".")[1:]  # absolute form: from simplicio_video.x import y
            if mod:
                out.add("/".join(mod))
            out.update("/".join(mod + [a.name]) for a in n.names)
        elif isinstance(n, ast.Import):
            out.update("/".join(a.name.split(".")[1:]) for a in n.names
                       if a.name.split(".")[0] == "simplicio_video" and "." in a.name)
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
SPAWNERS = {  # module -> functions that start a child (run/call/Popen style: judged by their keywords)
    "subprocess": {"call", "run", "Popen", "check_call", "check_output"},
    "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
}
ALWAYS_BAD = {  # no way to pass stdin/capture, or they replace the process / fork it
    "subprocess": {"getoutput", "getstatusoutput"},
    "pty": {"spawn", "fork"},
    "os": {"system", "popen", "fork", "forkpty", "posix_spawn", "posix_spawnp"},
}
TRACKED = set(SPAWNERS) | set(ALWAYS_BAD)


def _kw_on(node, name):
    """The keyword `name` is given a value other than a literal None/False."""
    for k in node.keywords:
        if k.arg == name:
            return not (isinstance(k.value, ast.Constant) and k.value.value in (None, False))
    return False


def _bad_name(mod, attr):
    return attr in ALWAYS_BAD.get(mod, ()) or (mod == "os" and attr.startswith(("exec", "spawn")))


def _bare_calls_src(src: str, rel: str = "<src>"):
    tree = ast.parse(src)
    found = []
    alias = {m: m for m in TRACKED}  # local name -> module, grown by `import x as y` and `y = x`
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            alias.update({(a.asname or a.name): a.name for a in n.names if a.name in TRACKED})
        elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Name) and alias.get(n.value.id):
            alias.update({t.id: alias[n.value.id] for t in n.targets if isinstance(t, ast.Name)})

    def visit(node, fn, called=False):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in TRACKED:
            found.append((rel, fn, node.lineno))  # `from subprocess import run [as r]` would hide the call from this lint
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in alias:
                mod, attr = alias[f.value.id], f.attr
                if _bad_name(mod, attr):
                    found.append((rel, fn, node.lineno))
                elif attr in SPAWNERS.get(mod, ()):
                    captured = _kw_on(node, "capture_output") or (_kw_on(node, "stdout") and _kw_on(node, "stderr")) or (
                        attr == "check_output" and _kw_on(node, "stderr"))
                    if not (captured and (_kw_on(node, "stdin") or _kw_on(node, "input"))):
                        found.append((rel, fn, node.lineno))
            for ch in ast.iter_child_nodes(node):
                visit(ch, fn, called=ch is node.func)
            return
        if (isinstance(node, ast.Attribute) and not called and isinstance(node.value, ast.Name) and node.value.id in alias
                and (_bad_name(alias[node.value.id], node.attr) or node.attr in SPAWNERS.get(alias[node.value.id], ()))):
            found.append((rel, fn, node.lineno))  # `x = subprocess.run` / passing it around: unchecked later
        if isinstance(node, ast.arg):
            return  # annotations (`proc: subprocess.Popen`) are not uses
        if isinstance(node, ast.AnnAssign):
            kids = [node.target] + ([node.value] if node.value else [])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kids = [c for c in ast.iter_child_nodes(node) if c is not node.returns]
        else:
            kids = list(ast.iter_child_nodes(node))
        for ch in kids:
            visit(ch, fn)
    visit(tree, None)
    return found


def _bare_calls(rel: str):
    return _bare_calls_src((SRC / rel).read_text(encoding="utf-8"), rel)


@pytest.mark.parametrize("src,bad", [
    ("import subprocess\nsubprocess.run(c)", True),
    ("import subprocess\nsubprocess.run(c, stdin=subprocess.DEVNULL, capture_output=True)", False),
    ("import subprocess\nsubprocess.run(c, stdin=None, capture_output=True)", True),
    ("import subprocess\nsubprocess.run(c, stdin=subprocess.DEVNULL, capture_output=False)", True),
    ("import subprocess\nsubprocess.run(c, stdin=subprocess.DEVNULL, stdout=a, stderr=None)", True),
    ("import subprocess\nsubprocess.run(c, stdin=subprocess.DEVNULL, stdout=a, stderr=b)", False),
    ("import subprocess as sp\nsp.run(c)", True),
    ("import subprocess\nsp = subprocess\nsp.run(c)", True),
    ("import subprocess\nr = subprocess.run\nr(c)", True),
    ("from subprocess import run\nrun(c)", True),
    ("from subprocess import run as r\nr(c)", True),
    ("import subprocess\nsubprocess.getoutput('x')", True),
    ("import subprocess\nsubprocess.getstatusoutput('x')", True),
    ("import os\nos.execvp('x', [])", True),
    ("import os\nos.posix_spawn('x', [], {})", True),
    ("import os\nos.fork()", True),
    ("import os\nos.spawnlp(0, 'x')", True),
    ("import pty\npty.spawn(['x'])", True),
    ("import asyncio\nasyncio.create_subprocess_exec(*c)", True),
    ("import asyncio\nasyncio.create_subprocess_exec(*c, stdin=d, stdout=a, stderr=b)", False),
    ("import os\nos.getcwd()", False),
])
def test_lint_catches_the_bypasses(src, bad):
    assert bool(_bare_calls_src(src)) is bad


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


# ---- per-call sinks instead of a global lock ----
def test_slow_captured_call_does_not_delay_another_tool(monkeypatch):
    from simplicio_video import mcp_server
    started = threading.Event()

    def slow(log):
        started.set()
        time.sleep(2.0)
        return "slow"

    t = threading.Thread(target=lambda: mcp_server._capture(slow))
    t.start()
    assert started.wait(5)
    t0 = time.monotonic()
    r = mcp_server._cli(["status", "--json"])
    waited = time.monotonic() - t0
    t.join()
    assert r["rc"] == 0 and waited < 1.0, waited


def test_nested_captures_restore_the_outer_sink():
    from simplicio_video import mcp_server

    def inner(log):
        print("inner")

    def outer(log):
        print("before")
        mcp_server._capture(inner)
        print("after")

    r = mcp_server._capture(outer)
    assert r["log"].split() == ["before", "after"]


def test_aio_threads_of_a_tool_write_to_that_tools_sink(capfd):
    from simplicio_video import aio, mcp_server

    async def co():
        await aio.athread(print, "from-athread")

    def tool(log):
        aio.run_sync(co())  # voice.run goes through this: loop in a helper thread, calls in daemon threads

    r = mcp_server._capture(tool)
    assert "from-athread" in r["log"]
    assert capfd.readouterr().out == ""


def test_unrelated_threads_never_write_to_fd1_while_a_tool_runs(capfd):
    from simplicio_video import mcp_server
    go, done = threading.Event(), threading.Event()

    def orphan():
        go.wait(5)
        print("orphan-output")
        done.set()

    threading.Thread(target=orphan, daemon=True).start()

    def tool(log):
        go.set()
        done.wait(5)

    mcp_server._capture(tool)
    cap = capfd.readouterr()
    assert cap.out == "" and "orphan-output" in cap.err  # documented: a thread with no sink falls back to stderr


def test_failing_child_reason_reaches_the_tool_result(monkeypatch):
    from simplicio_video import mcp_server
    monkeypatch.setenv("SIMPLICIO_MCP", "1")

    def tool(log):
        childio.check_child([sys.executable, "-c", "import sys; print('kokoro exploded', file=sys.stderr); sys.exit(3)"])

    r = mcp_server._capture(tool)
    assert not r["ok"] and "kokoro exploded" in r["log"] and "kokoro exploded" in r["error"]


def test_timeout_writes_the_partial_output_then_raises(monkeypatch):
    import subprocess
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(subprocess.TimeoutExpired):
        childio.run_child([sys.executable, "-u", "-c", "import time; print('partial'); time.sleep(30)"], timeout=1)
    assert "partial" in out.getvalue()


def test_input_is_refused_not_dropped(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    with pytest.raises(TypeError):
        childio.run_child([sys.executable, "-c", "pass"], input="x")

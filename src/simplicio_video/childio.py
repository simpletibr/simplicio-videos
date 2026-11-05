"""Start a child process without letting it touch the MCP stdio channel, and capture tool output per call.

Under the MCP stdio server (`SIMPLICIO_MCP=1`) fds 0/1 are the JSON-RPC stream: a child that inherits them can write into
it or swallow client input. There the child gets stdin=/dev/null and its stdout/stderr are captured and re-emitted through
Python's sys.stdout/sys.stderr, which `capture()` routes to the calling tool's own buffers. In a terminal run_child is
exactly subprocess.call.

`capture()` replaces the process-wide `contextlib.redirect_stdout` (mcp 2.x runs sync tools in worker threads, so a global
redirect mixed their logs, and a lock around it made every tool wait behind a render). While at least one capture is open,
sys.stdout/sys.stderr are small proxies that write to the sink of the *current context* (a ContextVar). aio's helper
threads copy that context, so their output lands in the tool that spawned them. A thread with no sink at all (one nobody
spawned through aio) falls back to the REAL STDERR, never to fd 1."""
from __future__ import annotations

import contextlib
import contextvars
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Sequence
from typing import Any

ENV_FLAG = "SIMPLICIO_MCP"

_OUT: contextvars.ContextVar[Any] = contextvars.ContextVar("simplicio_out", default=None)
_ERR: contextvars.ContextVar[Any] = contextvars.ContextVar("simplicio_err", default=None)
_mu = threading.Lock()
_open = 0
_saved: tuple[Any, Any] | None = None


class _Proxy:
    def __init__(self, var: contextvars.ContextVar, real: Any, fallback: Any) -> None:
        self._var, self._real, self._fallback = var, real, fallback

    def _target(self) -> Any:
        sink = self._var.get()
        return sink if sink is not None else self._fallback

    def write(self, s: str) -> int:
        return self._target().write(s)

    def flush(self) -> None:
        with contextlib.suppress(Exception):
            self._target().flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target(), name)


@contextlib.contextmanager
def capture(out: Any, err: Any = None):
    """Send what this context (and the threads that copy it) prints to `out` / `err` instead of the real streams.
    Calls nest: the previous sinks come back on exit. `err=None` keeps stderr on its current sink."""
    global _open, _saved
    with _mu:
        if _open == 0:
            _saved = (sys.stdout, sys.stderr)
            real_err = sys.stderr
            sys.stdout = _Proxy(_OUT, sys.stdout, real_err)  # fd 1 is the protocol: an orphan thread goes to stderr
            sys.stderr = _Proxy(_ERR, real_err, real_err)
        _open += 1
    t_out = _OUT.set(out)
    t_err = _ERR.set(err) if err is not None else None
    try:
        yield
    finally:
        _OUT.reset(t_out)
        if t_err is not None:
            _ERR.reset(t_err)
        with _mu:
            _open -= 1
            if _open == 0 and _saved is not None:
                if isinstance(sys.stdout, _Proxy):
                    sys.stdout = _saved[0]
                if isinstance(sys.stderr, _Proxy):
                    sys.stderr = _saved[1]
                _saved = None


def under_mcp() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


class ChildError(subprocess.CalledProcessError):
    """CalledProcessError whose message carries the tail of the child's stderr (the reason it failed)."""

    def __str__(self) -> str:
        tail = (self.stderr or "").strip()[-500:]
        base = super().__str__()
        return f"{base}: {tail}" if tail else base


def _run_captured(argv: Sequence[Any], kw: dict[str, Any]) -> tuple[int, str, str]:
    if "input" in kw:
        raise TypeError("run_child: input= is not supported (the child's stdin is /dev/null under MCP)")
    for k in ("stdin", "stdout", "stderr", "capture_output"):
        kw.pop(k, None)
    # Temp files, not pipes: a pipe would keep run() waiting for any grandchild that inherited it (`(sleep 4 &)`).
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        def emit() -> tuple[str, str]:
            texts = []
            for f, sink in ((out, sys.stdout), (err, sys.stderr)):
                f.seek(0)
                text = f.read().decode("utf-8", errors="replace")  # explicit: the locale codec (cp1252) would garble it
                if text:
                    sink.write(text)
                texts.append(text)
            return texts[0], texts[1]

        try:
            rc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, **kw).returncode
        except BaseException:  # TimeoutExpired, KeyboardInterrupt: what the child printed so far is still worth showing
            emit()
            raise
        o, e = emit()
    return rc, o, e


def run_child(argv: Sequence[Any], **kw: Any) -> int:
    """Run `argv` to completion and return its exit code. Extra keywords (cwd, env, timeout) go to subprocess."""
    if not under_mcp():
        return subprocess.call(argv, **kw)
    return _run_captured(argv, kw)[0]


def check_child(argv: Sequence[Any], **kw: Any) -> None:
    """`subprocess.run(argv, check=True)` through run_child: raises CalledProcessError on a non-zero exit (under MCP it
    carries the stderr, so the reason reaches the tool result)."""
    if not under_mcp():
        rc, err = run_child(argv, **kw), None  # a terminal: plain subprocess.call
    else:
        rc, _, err = _run_captured(argv, kw)
    if rc != 0:
        raise ChildError(rc, list(argv), stderr=err)

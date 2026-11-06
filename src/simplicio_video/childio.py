"""Start a child process without letting it touch the MCP stdio channel, and capture tool output per call.

Under the MCP stdio server (`SIMPLICIO_MCP=1`) fds 0/1 are the JSON-RPC stream: a child that inherits them can write into
it or swallow client input. There the child gets stdin=/dev/null and its stdout/stderr are captured and re-emitted through
Python's sys.stdout/sys.stderr, which `capture()` routes to the calling tool's own buffers. In a terminal run_child is
exactly subprocess.call.

`capture()` replaces the process-wide `contextlib.redirect_stdout` (mcp 2.x runs sync tools in worker threads, so a global
redirect mixed their logs, and a lock around it made every tool wait behind a render). While at least one capture is open,
sys.stdout/sys.stderr are small proxies that write to the sink of the *current context* (a ContextVar). aio's helper
threads copy that context, so their output lands in the tool that spawned them. A thread with no sink at all (one nobody
spawned through aio) falls back to the REAL STDERR, never to fd 1. That holds only while a capture is open: a daemon
writer that outlives its tool call (aio's late takes) writes to whatever sys.stdout is after the last capture closed, i.e.
the real stream. Nothing in the engine may use contextlib.redirect_std* (a test enforces it): it would swap the proxy.

A long-lived child must also not outlive the engine because of a stop signal. `guarded_child` (a Popen whose kill is armed before
the fork returns: SIGTERM, SIGHUP and Ctrl+C that land in the gap are held until the child exists, then it is killed and the stop
is raised), `start_child` (the same for servers a caller stops in its own `finally`) and `kill_group` (SIGKILL of the child's group,
refusing pid <= 1, our own group and a child that already exited) are that API; the rules and the tests are in docs/host/gate.md."""
from __future__ import annotations

import contextlib
import contextvars
import os
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator, Sequence
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


# ---- a child that cannot be orphaned by a stop signal ----

def stop_exception(signum: int) -> BaseException:
    """What a stop signal turns into: Ctrl+C is KeyboardInterrupt, SIGTERM/SIGHUP end the engine with the shell's 128+n."""
    return KeyboardInterrupt() if signum == signal.SIGINT else SystemExit(128 + signum)


def stop_as_interrupt(signum: int) -> BaseException:
    """For engines whose servers stop on Ctrl+C: every stop signal is a KeyboardInterrupt (what their own handler does)."""
    return KeyboardInterrupt()


def kill_group(proc: subprocess.Popen, group: bool = True) -> None:
    """SIGKILL the child's whole process group (`group`: it was started with start_new_session) or just the child, then reap it.
    It signals nothing that may not be the child: a pid <= 1 (killpg(0) is OUR group, killpg(1) is init's), our own pid or
    process group, and a child that has already exited (its pid may belong to somebody else by now). `group` on a child that
    leads no group of its own (no start_new_session: killpg would name no group, or ours) kills just the child."""
    pid = proc.pid
    if pid <= 1 or pid == os.getpid() or (hasattr(os, "getpgrp") and pid == os.getpgrp()):
        return
    if proc.poll() is not None:  # exited and reaped: nothing left to kill, and the pid is no longer ours
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        if group and hasattr(os, "killpg") and os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
        else:  # no group of its own (or Windows): only the child itself
            proc.kill()
    with contextlib.suppress(Exception):
        proc.wait(5)


class _Guard:
    """Signal state of one guarded start: signals that land before the Popen has returned are only noted (raising there would
    leave the child with no owner), and from then on they end the engine. Ignored signals stay ignored; Ctrl+C is taken over
    only while Python's default handler is in place; off the main thread no handler can be set, and nothing is changed."""

    def __init__(self, stop: Callable[[int], BaseException]) -> None:
        self.stop, self.proc, self.pending, self.stopping, self.previous = stop, None, [], False, {}

    def handle(self, signum, frame) -> None:
        if self.proc is None or self.stopping:  # no child yet (or already stopping it): note it, act when the child exists
            self.pending.append(signum)
            return
        self.stopping = True  # here, not in the `except`: a second signal can land between this raise and the first line there
        raise self.stop(signum)

    def install(self) -> None:
        for name in ("SIGTERM", "SIGHUP", "SIGINT"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            current = signal.getsignal(sig)
            if current == signal.SIG_IGN or (sig == signal.SIGINT and current is not signal.default_int_handler):
                continue
            try:
                self.previous[sig] = signal.signal(sig, self.handle)
            except (ValueError, OSError):  # not the main thread
                continue

    def restore(self) -> None:
        """Every handler goes back, one signal at a time: a signal delivered while this runs can raise (from the handler just put
        back, or from ours still in place), and that must not cut the loop short. The first such exception is raised at the end."""
        first: BaseException | None = None
        for sig, old in self.previous.items():
            for _ in range(3):  # a raise from our own handler, before the swap, is retried: the swap itself must happen
                try:
                    with contextlib.suppress(ValueError, OSError):
                        if signal.getsignal(sig) == self.handle:  # a stop routine that set SIG_IGN keeps it: it restores in its own time
                            signal.signal(sig, old if old is not None else signal.SIG_DFL)
                    break
                except BaseException as e:  # noqa: BLE001 - a stop signal turned into an exception by a handler
                    first = first or e
        if first is not None:
            raise first


@contextlib.contextmanager
def guarded_child(argv: Sequence[Any], *, stop: Callable[[int], BaseException] | None = None,
                  kill: Callable[[subprocess.Popen], None] | None = None, **kw: Any) -> Iterator[subprocess.Popen]:
    """`subprocess.Popen(argv, **kw)` whose child dies with the engine. SIGTERM, SIGHUP and Ctrl+C are caught from before the
    fork until the block ends: one that lands while Popen is starting the child is held until the child exists, then the child
    is killed (`kill`, default: its whole group when `start_new_session` was given, else itself) and the stop is raised
    (`stop(signum)`: KeyboardInterrupt for Ctrl+C, SystemExit(128+n) otherwise); one that lands later raises it from
    wherever the engine is waiting, and the child is killed on the way out of the block, like any other exception. The
    previous handlers come back when the block ends, also when Popen raises (FileNotFoundError and the like: no child, the
    error passes through unchanged unless a stop signal came in, which wins). A normal exit leaves the child to the caller.
    Wrap the block in an ExitStack to tell a spawn error from an error of the body."""
    guard = _Guard(stop or stop_exception)
    killer = kill or (lambda p: kill_group(p, bool(kw.get("start_new_session"))))
    guard.install()
    try:
        try:
            guard.proc = subprocess.Popen(argv, **kw)
        except BaseException:
            if guard.pending:
                raise guard.stop(guard.pending[0]) from None
            raise
        if guard.pending:  # it came in during the fork: the child exists now, so it is ended like any other
            raise guard.stop(guard.pending[0])
        yield guard.proc
    except BaseException:
        guard.stopping = True  # (handle() already set it for a signal; this covers the other exceptions) the kill is not cut short
        if guard.proc is not None:
            killer(guard.proc)
        raise
    finally:
        guard.restore()


def start_child(argv: Sequence[Any], *, track: list | None = None, **kw: Any) -> subprocess.Popen:
    """guarded_child for a child whose owner is a list the caller cleans up (servers stopped in a `finally`): `track` gets the
    child before any stop signal can be acted on, so the caller's own cleanup stops it. The child is not killed on a stop
    that comes after this returns; that is the caller's cleanup."""
    with guarded_child(argv, **kw) as proc:
        if track is not None:
            track.append(proc)
    return proc

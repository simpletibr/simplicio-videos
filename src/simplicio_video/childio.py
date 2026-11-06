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
refusing pid <= 1 and our own pid and group; the group of a leader that already exited is still swept, its grandchildren outlive it)
are that API; the rules and the tests are in docs/host/gate.md.
Worker threads cannot take signals, so every guarded child is also in a process-wide registry (`live_children`, `kill_live`), and the
MCP server's entry point calls `install_exit_guard()` once from its main thread to kill them on SIGTERM/SIGHUP/Ctrl+C (its handler
must never block: see docs/host/gate.md)."""
from __future__ import annotations

import contextlib
import contextvars
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
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
    """SIGKILL the child's whole process group (`group`: the caller started it with start_new_session, so pgid == pid) or just the
    child, then reap it. It signals nothing that may not be the child: a pid <= 1 (killpg(0) is OUR group, killpg(1) is init's), our
    own pid or process group. A child that has already exited and been reaped is left alone, except that its GROUP is still swept
    when `group` says it led one: grandchildren outlive their leader, and Linux does not reuse a pid while a process group with
    that id exists (a group that is gone is ESRCH). `group` on a child that leads no group of its own (no start_new_session:
    killpg would name no group, or ours) kills just the child."""
    pid = proc.pid
    if pid <= 1 or pid == os.getpid() or (hasattr(os, "getpgrp") and pid == os.getpgrp()):
        return
    exited = proc.poll() is not None  # exited and reaped: the pid is no longer ours (reuse), only its group may remain
    sweep = group and hasattr(os, "killpg")
    if exited and not sweep:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        if sweep and (exited or os.getpgid(pid) == pid):  # a live child must really lead the group; a reaped one is declared by the caller
            os.killpg(pid, signal.SIGKILL)
        elif not exited:  # no group of its own (or Windows): only the child itself
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


# ---- the children that are under a guard right now (for a stop signal that no guard can take: a worker thread) ----

_live: dict[int, tuple[subprocess.Popen, Callable[[subprocess.Popen], None]]] = {}  # pid -> (child, its killer)
_live_mu = threading.RLock()  # writers only (worker threads, short sections); the exit handler never takes it
_spawning = 0  # guarded_child calls that are between "about to fork" and "registered"
_exit_code = 0
GUARD_INSTALLED, GUARD_ALREADY, GUARD_NOT_MAIN, GUARD_NOTHING = "installed", "already-installed", "not-main-thread", "nothing-to-install"


class _Flag:
    """A boolean the exit handler can set from any point of any thread: no lock, no Condition (threading.Event.set takes a lock a
    nested signal handler on the same thread would wait for forever)."""
    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = False

    def set(self) -> None:
        self.value = True

    def clear(self) -> None:
        self.value = False

    def is_set(self) -> bool:
        return self.value


_exiting = _Flag()


def live_children() -> list[subprocess.Popen]:
    """The children that are under a guarded_child block right now (started, block not ended). A normal exit of a block hands
    its child to the caller and removes it; start_child's child is never in here after it returns."""
    return [p for p, _ in list(_live.values())]  # list() is one atomic step under the GIL: safe from a signal handler too


def kill_live() -> None:
    """Kill every child that is under a guard, each with the killer its guarded_child was given."""
    for proc, killer in list(_live.values()):
        with contextlib.suppress(Exception):
            killer(proc)


def _track(proc: subprocess.Popen, killer: Callable[[subprocess.Popen], None]) -> None:
    with _live_mu:
        _live[proc.pid] = (proc, killer)


def _untrack(proc: subprocess.Popen) -> None:
    with _live_mu:
        if _live.get(proc.pid, (None,))[0] is proc:
            del _live[proc.pid]


@contextlib.contextmanager
def _starting() -> Iterator[None]:
    """Counts a start (fork until registered) so the exit handler can wait for it. Dekker-style with the handler, no lock shared
    with it: the start counts itself FIRST and looks at the exit flag AFTER; the handler sets the flag FIRST and reads the count
    AFTER. So either this start sees the flag and forks nothing, or the handler sees the start and waits for it."""
    global _spawning
    with _live_mu:
        _spawning += 1
    try:
        if _exiting.is_set():  # the engine is ending (e.g. a tool that goes on to its next program after the sweep killed the last)
            raise SystemExit(_exit_code)
        yield
    finally:
        with _live_mu:
            _spawning -= 1


_exit_wait_s = 3.0
_exit_leave: Callable[[int], Any] = os._exit


def _exit_handler(signum, frame) -> None:
    """The stop-signal handler of install_exit_guard. Nothing here may block on anything another thread, or this very thread
    further up the stack, can hold: no lock, no Event/Condition, no stream flush. A second signal that lands inside it just runs it
    again (the first signal's exit code wins)."""
    global _exit_code
    if not _exiting.is_set():
        _exit_code = 128 + signum
        _exiting.set()
    limite = time.monotonic() + _exit_wait_s
    while True:
        quiet = _spawning == 0  # read BEFORE the kill: nobody was between fork and registration, so kill_live sees every child
        kill_live()
        if quiet or time.monotonic() >= limite:
            break
        time.sleep(0.01)
    _exit_leave(_exit_code)


_exit_prev: dict[int, Any] = {}  # signal -> handler that was there before install_exit_guard
_exit_pipe: list[int] = []  # [read fd, write fd] of the wakeup pipe, while installed


def _watch_signals(rfd: int) -> None:
    """Runs on a daemon thread. CPython runs a Python signal handler only on the main thread, and the OS may hand the signal to a
    worker thread (it does when the main thread already has one pending, as in a burst): the C handler then records it and the
    main thread, asleep in a syscall, would not run the Python handler until it wakes. The C handler also writes the signal number
    to the wakeup fd, whatever thread caught it: this thread reads it and runs the same handler, so the exit never waits for the
    main thread. It acts only on a signal whose handler is still ours (after uninstall_exit_guard a stray byte does nothing)."""
    while True:
        try:
            data = os.read(rfd, 64)
        except OSError:
            return
        if not data:
            return
        for signum in data:
            if signal.getsignal(signum) is _exit_handler:
                _exit_handler(signum, None)


def install_exit_guard(wait_s: float = 3.0, leave: Callable[[int], Any] = os._exit) -> str:
    """For a process whose work runs in worker threads, where no guarded_child can take a signal (the MCP server): from the MAIN
    thread, SIGTERM, SIGHUP and Ctrl+C kill every child that is under a guard (also one a worker is still forking; one that would
    start after is never forked) and end the process with the shell's 128+n through `leave` (os._exit: a worker thread cannot be
    unwound, and waiting for one would be waiting for a render). Ignored signals stay ignored, a handler the engine set itself
    stays. The CLI never calls this: its guarded_child blocks take the signals themselves. Returns what it did: GUARD_INSTALLED,
    GUARD_ALREADY (it was installed by an earlier call; nothing changed), GUARD_NOT_MAIN (called off the main thread: nothing is
    installed) or GUARD_NOTHING (every stop signal is ignored or handled by the engine itself)."""
    global _exit_wait_s, _exit_leave
    names = [n for n in ("SIGTERM", "SIGHUP", "SIGINT") if hasattr(signal, n)]
    if any(signal.getsignal(getattr(signal, n)) is _exit_handler for n in names):
        return GUARD_ALREADY
    if threading.current_thread() is not threading.main_thread():
        return GUARD_NOT_MAIN
    _exit_wait_s, _exit_leave = wait_s, leave
    installed = False
    for name in names:
        sig = getattr(signal, name)
        current = signal.getsignal(sig)
        if current == signal.SIG_IGN or (sig == signal.SIGINT and current is not signal.default_int_handler) or (
                sig != signal.SIGINT and current != signal.SIG_DFL):
            continue
        try:
            _exit_prev[sig] = signal.signal(sig, _exit_handler)
            installed = True
        except (ValueError, OSError):
            return GUARD_INSTALLED if installed else GUARD_NOT_MAIN
    if installed and not _exit_pipe:
        try:
            rfd, wfd = os.pipe()
            os.set_blocking(wfd, False)  # a full pipe drops the byte: the Python handler still runs
            signal.set_wakeup_fd(wfd, warn_on_full_buffer=False)
            _exit_pipe.extend((rfd, wfd))
            threading.Thread(target=_watch_signals, args=(rfd,), daemon=True, name="exit-guard").start()
        except (ValueError, OSError):  # no wakeup fd: the handlers alone are what there was before
            pass
    return GUARD_INSTALLED if installed else GUARD_NOTHING


def uninstall_exit_guard() -> None:
    """Gives back the handlers install_exit_guard replaced (the ones that are still ours) and the wakeup fd. For tests; the MCP
    server installs once and never removes it."""
    for sig, old in list(_exit_prev.items()):
        with contextlib.suppress(ValueError, OSError):
            if signal.getsignal(sig) is _exit_handler:
                signal.signal(sig, old if old is not None else signal.SIG_DFL)
    _exit_prev.clear()
    if _exit_pipe:
        with contextlib.suppress(ValueError, OSError):
            signal.set_wakeup_fd(-1)
        rfd, wfd = _exit_pipe[:]
        _exit_pipe.clear()
        for fd in (wfd, rfd):  # closing the write end ends the watcher's read
            with contextlib.suppress(OSError):
                os.close(fd)


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
            with _starting():
                guard.proc = subprocess.Popen(argv, **kw)
                _track(guard.proc, killer)
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
        try:
            if guard.proc is not None:
                _untrack(guard.proc)
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

"""Shared pieces for the "a stop signal must not orphan the child" tests (childio.guarded_child and the modules that use it).

The gap is the time between the fork and the return of Popen. It cannot be hit by timing, so the tests make it deterministic:
`sinaliza_no_popen` swaps subprocess.Popen for a subclass that, once the child is really running (it wrote its pid), signals the
engine from inside __init__, exactly where a signal would land. The child is a sleeper that is always killed in the cleanup, so
a test that fails (the orphan lives) leaves nothing behind."""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

POSIX = os.name == "posix"
SINAIS = [n for n in ("SIGTERM", "SIGHUP", "SIGINT") if hasattr(signal, n)]

SLEEPER_CODE = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(120)"


def sleeper(pidfile: Path) -> list[str]:
    """argv of a child that writes its pid to `pidfile`, then sleeps (it is the orphan the tests look for)."""
    return [sys.executable, "-c", SLEEPER_CODE, str(pidfile)]


def vivo(pid: int) -> bool:
    """Is the process alive (a zombie that nobody reaped counts as dead)?"""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def espera(condicao, segundos: float = 20.0) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(0.05)
    return bool(condicao())


def pid_de(pidfile: Path) -> int | None:
    try:
        texto = pidfile.read_text().strip()
    except OSError:
        return None
    return int(texto) if texto else None


def espera_pid(pidfile: Path) -> int:
    assert espera(lambda: pid_de(pidfile) is not None), "the child never started"
    return pid_de(pidfile)


def mata_o_que_sobrou(pidfile: Path) -> None:
    """Cleanup of every test: whatever the sleeper still is, it dies here."""
    pid = pid_de(pidfile)
    if pid is not None and vivo(pid):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL) if os.getpgid(pid) == pid else os.kill(pid, signal.SIGKILL)


def limpa(proc, pidfile: Path) -> None:
    """mata_o_que_sobrou plus the direct child itself: it dies even when it never got to write its pid (a test that fails early)."""
    if proc is not None:
        with contextlib.suppress(Exception):
            proc.kill()
            proc.wait(5)
    mata_o_que_sobrou(pidfile)


def sinaliza_no_popen(monkeypatch, pidfile: Path, sinal: int, *, so_se: str | None = None) -> list:
    """Patch subprocess.Popen so that, after the child has started and written `pidfile`, the engine gets `sinal` while Popen is
    still running (its handler, if any, runs inside Popen, before the child is handed back). Only a Popen whose argv contains
    `so_se` (default: the pidfile path) is hooked. Returns the list of the Popen objects that were hooked."""
    real = subprocess.Popen
    marca = so_se or str(pidfile)
    ganchos: list = []

    class PopenQueSinaliza(real):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            argv = args[0] if args else kwargs.get("args")
            if marca in " ".join(map(str, argv if not isinstance(argv, (str, bytes)) else [argv])):
                ganchos.append(self)
                espera_pid(pidfile)
                os.kill(os.getpid(), sinal)  # the engine's handler runs here, before Popen gives the child back

    monkeypatch.setattr(subprocess, "Popen", PopenQueSinaliza)
    return ganchos


def estado_dos_sinais() -> dict:
    return {n: signal.getsignal(getattr(signal, n)) for n in SINAIS}


@contextlib.contextmanager
def sinais_ignorados(*nomes: str):
    """The pytest process as `nohup pytest` or `pytest &` start it: the named signals at SIG_IGN, restored on exit. Whatever the
    test launches inherits them (the exec keeps an ignored signal ignored), unless it is launched through `lanca_como_shell`."""
    antes = estado_dos_sinais()
    try:
        for n in nomes:
            signal.signal(getattr(signal, n), signal.SIG_IGN)
        yield
    finally:
        for n, h in antes.items():
            signal.signal(getattr(signal, n), h)


# Runs in the wrapper process before the exec: SIGHUP, SIGINT and SIGTERM back to SIG_DFL (a shell starts every command that way), then
# the command takes the place of the wrapper (same pid). Python, exec'd with SIGINT at SIG_DFL, installs default_int_handler for it,
# which is what childio's _Guard.install requires. No preexec_fn: it is not safe in a process with threads (pytest, xdist).
# SIGPIPE and SIGXFSZ go back to SIG_DFL too: the wrapper is itself a Python process, and Python starts with both at SIG_IGN (Popen's
# restore_signals only restores them for the wrapper's exec, and the wrapper's interpreter ignores them again), so without this a child
# that is not Python (`sleep`, `head`) kept them ignored (SigIgn=0x1001000 in /proc) where a shell gives them at their defaults.
# `argv[1]` is the write end of a close-on-exec pipe: when the exec fails (no such command, not executable) the wrapper writes the errno
# there and exits, and the caller raises the same OSError Popen would have raised (a clean exec closes the pipe: EOF, nothing written).
_COMO_SHELL = """\
import os, signal, sys
[signal.signal(getattr(signal, n), signal.SIG_DFL) for n in ('SIGHUP', 'SIGINT', 'SIGTERM', 'SIGPIPE', 'SIGXFSZ') if hasattr(signal, n)]
canal = int(sys.argv[1])
os.set_inheritable(canal, False)
try:
    os.execvp(sys.argv[2], sys.argv[2:])
except OSError as e:
    os.write(canal, str(e.errno).encode())
    os._exit(127)
"""


def lanca_como_shell(argv: list[str], **popen_kw) -> subprocess.Popen:
    """subprocess.Popen(argv, **popen_kw) with SIGHUP, SIGINT, SIGTERM, SIGPIPE and SIGXFSZ in the state a shell gives a command, whatever
    the pytest process has (`nohup make check` and `make check &` leave HUP and INT at SIG_IGN, and an ignored signal survives the exec: the
    engine keeps it ignored on purpose, so a test signal sent to such a child does nothing). The single launcher for every test that
    starts the engine or the MCP server and signals it. `restore_signals=True` does not do this: it restores SIGPIPE and SIGXFSZ only for
    the wrapper, which is a Python process that ignores them again.

    Like Popen it returns once the command has taken the place of the wrapper (the pid is the command's, with its final signal state), and
    it raises what Popen raises when the command cannot run: FileNotFoundError for a missing command, PermissionError for a file that is
    not executable (same errno and filename). The lookup uses the `env` and `cwd` given, as Popen does."""
    leitura, escrita = os.pipe()
    try:
        pass_fds = (*popen_kw.pop("pass_fds", ()), escrita)
        proc = subprocess.Popen([sys.executable, "-c", _COMO_SHELL, str(escrita), *map(os.fspath, argv)], pass_fds=pass_fds, **popen_kw)
    except BaseException:
        os.close(leitura)
        raise
    finally:
        os.close(escrita)
    try:
        with os.fdopen(leitura, "rb") as canal:
            errno_do_exec = canal.read()  # EOF: the exec happened (or the wrapper died before it)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    if errno_do_exec:
        numero = int(errno_do_exec)
        with proc:  # reaps the wrapper and closes the pipes Popen made
            pass
        raise OSError(numero, os.strerror(numero), os.fsdecode(os.fspath(argv[0])))
    return proc


@pytest.fixture
def sinais_padrao():
    """The engine as a shell starts it: the stop signals at their defaults (pytest may run under nohup, which ignores SIGHUP, and
    the engine keeps ignored signals ignored on purpose). Use with @pytest.mark.usefixtures("sinais_padrao")."""
    antes = estado_dos_sinais()
    for n in SINAIS:
        signal.signal(getattr(signal, n), signal.default_int_handler if n == "SIGINT" else signal.SIG_DFL)
    yield
    for n, h in antes.items():
        signal.signal(getattr(signal, n), h)


def parada_esperada(nome: str):
    """(exception class, exit code) a stop signal must turn into."""
    return (KeyboardInterrupt, None) if nome == "SIGINT" else (SystemExit, 128 + getattr(signal, nome))


# ---- an engine in its own process: for the modules that never had a stop-signal handler (the default action ends the engine) ----

PRELUDIO = r"""
import json, os, signal, subprocess, sys, threading, time
cfg = json.loads(os.environ["ORFAO_CFG"])
_sinal = getattr(signal, cfg["sinal"])

def _pid():
    for _ in range(600):
        try:
            t = open(cfg["pidfile"]).read().strip()
        except OSError:
            t = ""
        if t:
            return int(t)
        time.sleep(0.05)
    raise SystemExit("the child never started")

if cfg["quando"] == "popen":  # the signal lands INSIDE Popen, with the child already running: the gap
    _real = subprocess.Popen
    class _P(_real):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            argv = a[0] if a else k.get("args")
            if cfg["so_se"] in " ".join(map(str, argv)):
                _pid()
                os.kill(os.getpid(), _sinal)
    subprocess.Popen = _P
else:  # the signal lands while the engine waits for the child
    threading.Thread(target=lambda: (_pid(), os.kill(os.getpid(), _sinal)), daemon=True).start()
"""


def roda_motor(tmp_path: Path, corpo: str, pidfile: Path, sinal: str, quando: str, *, so_se: str | None = None, tmpd: Path | None = None,
               extra_env: dict | None = None, timeout: float = 90) -> subprocess.CompletedProcess:
    """Run `corpo` (Python source that calls the module under test) in a separate engine process. `quando` is "popen" (the signal
    lands inside Popen, once the child that wrote `pidfile` runs) or "espera" (while the engine waits for the child). The caller
    asserts on the exit code, the child (pid in `pidfile`) and the private folders under `tmpd`."""
    from conftest import ROOT, offline_env

    cfg = {"pidfile": str(pidfile), "sinal": sinal, "quando": quando, "so_se": so_se or str(pidfile)}
    env = offline_env(ORFAO_CFG=__import__("json").dumps(cfg), **(extra_env or {}))
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])
    if tmpd is not None:
        tmpd.mkdir(exist_ok=True)
        env["TMPDIR"] = str(tmpd)
    # Files, not pipes: an orphan that inherited a pipe would keep the read open and hang the test instead of failing it.
    with open(tmp_path / "motor.out", "w+") as out, open(tmp_path / "motor.err", "w+") as err:
        # as a shell starts the engine (pytest may run under nohup, which ignores SIGHUP and SIGINT): the three stop signals at their defaults
        proc = lanca_como_shell([sys.executable, "-c", PRELUDIO + corpo], env=env, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                cwd=tmp_path)
        try:
            rc = proc.wait(timeout)
        except BaseException:  # what subprocess.run does: do not leave the engine behind
            proc.kill()
            proc.wait()
            raise
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess([], rc, out.read(), err.read())

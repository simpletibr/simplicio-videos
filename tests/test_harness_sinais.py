"""The harness that starts the engine (or the MCP server) under test hands it the stop signals the way a shell does.

`nohup make check` and `make check &` start pytest with SIGHUP and SIGINT at SIG_IGN, and a child inherits an ignored signal. The
engine keeps an ignored signal ignored on purpose (childio.install_exit_guard, _Guard.install), so a test that signals a child that
inherited SIG_IGN does nothing and the test waits for nothing. `_orfao.lanca_como_shell` is the one launcher that gives the child
SIGHUP, SIGINT and SIGTERM in the state a shell gives them (SIG_DFL; Python then installs default_int_handler for SIGINT), whatever
the pytest process ignores. These tests make pytest ignore the signals themselves, so they hold under a plain `make check` too."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from _orfao import POSIX, espera, roda_motor, sinais_ignorados

pytestmark = pytest.mark.skipif(not POSIX, reason="POSIX signals")

# Prints, as JSON, the state in which the process that runs it found SIGHUP, SIGINT and SIGTERM.
PROBE = """
import json, signal

def nome(h):
    if h is signal.SIG_DFL:
        return "SIG_DFL"
    if h is signal.SIG_IGN:
        return "SIG_IGN"
    return "default_int_handler" if h is signal.default_int_handler else repr(h)

print(json.dumps({n: nome(signal.getsignal(getattr(signal, n))) for n in ("SIGHUP", "SIGINT", "SIGTERM")}))
"""

COMO_UM_SHELL = {"SIGHUP": "SIG_DFL", "SIGINT": "default_int_handler", "SIGTERM": "SIG_DFL"}

IGNORADOS = [(), ("SIGHUP",), ("SIGINT",), ("SIGHUP", "SIGINT")]
IDS = ["nenhum", "so-HUP", "so-INT", "HUP-e-INT"]


def test_a_plain_popen_hands_down_the_signals_the_pytest_process_ignores():
    """The premise (it holds for every launcher but `lanca_como_shell`): SIG_IGN survives the exec, so the child never gets the
    default action the stop-signal tests rely on."""
    with sinais_ignorados("SIGHUP", "SIGINT"):
        r = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == {"SIGHUP": "SIG_IGN", "SIGINT": "SIG_IGN", "SIGTERM": "SIG_DFL"}


@pytest.mark.parametrize("ignorados", IGNORADOS, ids=IDS)
def test_a_child_started_as_a_shell_sees_the_stop_signals_at_their_defaults(ignorados):
    from _orfao import lanca_como_shell

    with sinais_ignorados(*ignorados):
        proc = lanca_como_shell([sys.executable, "-c", PROBE], stdout=subprocess.PIPE, text=True)
        saida, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0
    assert json.loads(saida) == COMO_UM_SHELL


@pytest.mark.parametrize("ignorados", IGNORADOS, ids=IDS)
def test_the_engine_process_of_roda_motor_sees_the_stop_signals_at_their_defaults(ignorados, tmp_path):
    """roda_motor runs the module under test in an engine process of its own: it must find the three signals as a shell leaves them
    (SIGINT included: the engine of the rea_video SIGINT cases never saw its Ctrl+C)."""
    with sinais_ignorados(*ignorados):
        r = roda_motor(tmp_path, PROBE, tmp_path / "filho.pid", "SIGTERM", "espera")
    assert r.returncode == 0, r.stderr[-600:]
    assert json.loads(r.stdout) == COMO_UM_SHELL


def test_lanca_como_shell_keeps_the_pid_of_the_process_it_returns():
    """The wrapper execs the command (no extra process in between): the pid that tests signal is the pid of the command itself."""
    from _orfao import lanca_como_shell

    proc = lanca_como_shell([sys.executable, "-c", "import os; print(os.getpid())"], stdout=subprocess.PIPE, text=True)
    saida, _ = proc.communicate(timeout=60)
    assert int(saida) == proc.pid


def test_lanca_como_shell_passes_argv_and_the_popen_keywords_through(tmp_path):
    from _orfao import lanca_como_shell

    codigo = "import os, sys; print(os.getcwd()); print(os.environ['LANCA_X']); print(*sys.argv[1:], sep='|'); sys.exit(7)"
    env = {**os.environ, "LANCA_X": "valor ç"}
    proc = lanca_como_shell([sys.executable, "-c", codigo, "a b", "c'd\"e", "ção"], cwd=tmp_path, env=env, stdout=subprocess.PIPE,
                            text=True, encoding="utf-8")
    saida, _ = proc.communicate(timeout=60)
    assert isinstance(proc, subprocess.Popen)
    assert proc.returncode == 7
    assert saida.splitlines() == [str(tmp_path.resolve()), "valor ç", "a b|c'd\"e|ção"]


def test_lanca_como_shell_resolves_a_bare_command_name_like_popen_does(tmp_path):
    from _orfao import lanca_como_shell

    if not shutil.which("echo"):
        pytest.skip("no echo on PATH")
    proc = lanca_como_shell(["echo", "oi"], stdout=subprocess.PIPE, text=True)
    saida, _ = proc.communicate(timeout=60)
    assert (proc.returncode, saida) == (0, "oi\n")


def test_lanca_como_shell_does_not_use_preexec_fn(monkeypatch):
    """preexec_fn is not safe in a process with threads (pytest and xdist have them; Python 3.12+ warns): the wrapper does it."""
    from _orfao import lanca_como_shell

    vistos: list[dict] = []
    real = subprocess.Popen

    class Anota(real):
        def __init__(self, *args, **kwargs):
            vistos.append(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", Anota)
    proc = lanca_como_shell([sys.executable, "-c", "pass"])
    proc.wait(60)
    assert len(vistos) == 1
    assert vistos[0].get("preexec_fn") is None


@pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="needs /proc")
@pytest.mark.skipif(not shutil.which("sleep"), reason="no sleep on PATH")
def test_a_child_that_is_not_python_has_none_of_the_stop_signals_ignored():
    """Not only Python: the ignored-signals mask (SigIgn in /proc) of a plain `sleep` has SIGHUP, SIGINT and SIGTERM clear."""
    from _orfao import lanca_como_shell

    with sinais_ignorados("SIGHUP", "SIGINT"):
        proc = lanca_como_shell(["sleep", "60"])
    try:
        comm = Path(f"/proc/{proc.pid}/comm")
        assert espera(lambda: comm.exists() and comm.read_text().strip() == "sleep", 20), "the wrapper never exec'd the command"
        linha = next(x for x in Path(f"/proc/{proc.pid}/status").read_text().splitlines() if x.startswith("SigIgn:"))
        mascara = int(linha.split()[1], 16)
        for numero in (1, 2, 15):  # SIGHUP, SIGINT, SIGTERM (bit n-1)
            assert not mascara & (1 << (numero - 1)), f"signal {numero} is ignored: {linha}"
    finally:
        proc.kill()
        proc.wait(10)


def _mascara_de_sigign_de_um_sleep() -> tuple[int, str]:
    """Launch a plain `sleep` through the helper, with pytest ignoring HUP and INT as under `nohup`, and read its SigIgn from /proc."""
    from _orfao import lanca_como_shell

    with sinais_ignorados("SIGHUP", "SIGINT"):
        proc = lanca_como_shell(["sleep", "60"])
    try:
        comm = Path(f"/proc/{proc.pid}/comm")
        assert espera(lambda: comm.exists() and comm.read_text().strip() == "sleep", 20), "the wrapper never exec'd the command"
        linha = next(x for x in Path(f"/proc/{proc.pid}/status").read_text().splitlines() if x.startswith("SigIgn:"))
        return int(linha.split()[1], 16), linha
    finally:
        proc.kill()
        proc.wait(10)


@pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="needs /proc")
@pytest.mark.skipif(not shutil.which("sleep"), reason="no sleep on PATH")
def test_a_child_that_is_not_python_has_sigpipe_and_sigxfsz_at_their_defaults():
    """The wrapper is a Python process, and Python starts with SIGPIPE and SIGXFSZ at SIG_IGN (SigIgn=0x1001000): the exec keeps them
    ignored, so a plain `sleep | head` child would never die of a broken pipe. A shell gives a command both at their defaults."""
    mascara, linha = _mascara_de_sigign_de_um_sleep()
    for nome in ("SIGPIPE", "SIGXFSZ"):
        assert not mascara & (1 << (int(getattr(signal, nome)) - 1)), f"{nome} is ignored in the child: {linha}"


@pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="needs /proc")
@pytest.mark.skipif(not shutil.which("sleep"), reason="no sleep on PATH")
def test_lanca_como_shell_returns_only_after_the_command_took_the_place_of_the_wrapper():
    """Like Popen, which returns once the exec happened: the process a test signals is already the command, with its final
    signal state, and not still the wrapper that is starting Python."""
    from _orfao import lanca_como_shell

    proc = lanca_como_shell(["sleep", "60"])
    try:
        assert Path(f"/proc/{proc.pid}/comm").read_text().strip() == "sleep"
    finally:
        proc.kill()
        proc.wait(10)


def _recusa_do_popen(argv):
    with pytest.raises(OSError) as esperado:
        subprocess.Popen(argv)
    return esperado.value


@pytest.mark.parametrize("caso", ["nome-solto", "caminho-que-nao-existe", "sem-permissao-de-execucao"])
def test_lanca_como_shell_refuses_a_command_that_cannot_run_the_way_popen_does(caso, tmp_path):
    """Popen raises FileNotFoundError (or PermissionError) in the caller. Through the wrapper the failure used to be an execvp
    traceback in the wrapper's stderr and a plain rc=1 from a process that had already been returned."""
    from _orfao import lanca_como_shell

    if caso == "nome-solto":
        alvo = "comando-que-nao-existe-simplicio"
    elif caso == "caminho-que-nao-existe":
        alvo = str(tmp_path / "nada" / "ai")
    else:
        alvo = str(tmp_path / "sem-x")
        Path(alvo).write_text("#!/bin/sh\nexit 0\n")
        os.chmod(alvo, 0o644)
    esperado = _recusa_do_popen([alvo])
    with open(tmp_path / "wrapper.err", "w+") as err:
        with pytest.raises(type(esperado)) as obtido:
            lanca_como_shell([alvo], stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL)
        err.seek(0)
        sobra = err.read()
    assert (obtido.value.errno, obtido.value.filename) == (esperado.errno, alvo)
    assert sobra == "", "the wrapper's own traceback must not reach the test's stderr"


def test_lanca_como_shell_still_resolves_the_command_with_the_path_of_the_env_it_was_given(tmp_path):
    """The lookup happens in the wrapper, after the env and cwd of Popen apply: same rule as Popen([name], env=env)."""
    from _orfao import lanca_como_shell

    pasta = tmp_path / "bin"
    pasta.mkdir()
    comando = pasta / "so-neste-path"
    comando.write_text("#!/bin/sh\necho achei\n")
    comando.chmod(0o755)
    env = {**os.environ, "PATH": f"{pasta}{os.pathsep}{os.environ['PATH']}"}
    proc = lanca_como_shell(["so-neste-path"], env=env, stdout=subprocess.PIPE, text=True)
    saida, _ = proc.communicate(timeout=60)
    assert (proc.returncode, saida) == (0, "achei\n")

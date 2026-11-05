"""childio.guarded_child / start_child: a child started through them cannot outlive the engine because of a stop signal,
including the one that lands between the fork and the return of Popen (the engine then had no reference to kill)."""
from __future__ import annotations

import signal
import subprocess
import sys
import threading

import pytest
from _orfao import POSIX, SINAIS, espera, espera_pid, mata_o_que_sobrou, pid_de, sinaliza_no_popen, sleeper, vivo

from simplicio_video import childio

pytestmark = pytest.mark.skipif(not POSIX, reason="POSIX signals")


@pytest.fixture
def sinais_padrao():
    """The engine as a shell starts it: the stop signals at their defaults (pytest may run under nohup, which ignores SIGHUP)."""
    antes = {n: signal.getsignal(getattr(signal, n)) for n in SINAIS}
    for n in SINAIS:
        signal.signal(getattr(signal, n), signal.default_int_handler if n == "SIGINT" else signal.SIG_DFL)
    yield
    for n, h in antes.items():
        signal.signal(getattr(signal, n), h)


def estado() -> dict:
    return {n: signal.getsignal(getattr(signal, n)) for n in SINAIS}


def esperado(nome: str):
    sinal = getattr(signal, nome)
    return KeyboardInterrupt if nome == "SIGINT" else SystemExit, (None if nome == "SIGINT" else 128 + sinal)


@pytest.mark.parametrize("nome", SINAIS)
def test_a_signal_inside_popen_kills_the_child_and_raises_the_stop(nome, monkeypatch, tmp_path, sinais_padrao):
    """The engine gets the signal while Popen is still starting the child: the child is killed (its whole group) and the engine
    exits the usual way (128+n; Ctrl+C is a KeyboardInterrupt). Without the guard the exception came out of Popen: no reference."""
    pidfile = tmp_path / "pid"
    ganchos = sinaliza_no_popen(monkeypatch, pidfile, getattr(signal, nome))
    antes = estado()
    exc, codigo = esperado(nome)
    try:
        with pytest.raises(exc) as saida:
            with childio.guarded_child(sleeper(pidfile), start_new_session=True):
                pytest.fail("the block must not run: the stop signal came in before the child was handed back")
        if codigo is not None:
            assert saida.value.code == codigo
        (popen,) = ganchos
        assert popen.returncode == -signal.SIGKILL  # killed and reaped by the guard
        assert espera(lambda: not vivo(espera_pid(pidfile)), 10), "the child outlived the engine"
        assert estado() == antes  # the previous handlers are back
    finally:
        mata_o_que_sobrou(pidfile)


@pytest.mark.parametrize("nome", SINAIS)
def test_a_signal_while_the_engine_waits_kills_the_child_on_the_way_out(nome, tmp_path, sinais_padrao):
    pidfile = tmp_path / "pid"
    antes = estado()
    exc, codigo = esperado(nome)
    try:
        with pytest.raises(exc) as saida:
            with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
                espera_pid(pidfile)
                signal.raise_signal(getattr(signal, nome))  # lands in the body, where a render or a server would be waited for
                proc.wait(30)
        if codigo is not None:
            assert saida.value.code == codigo
        assert proc.returncode == -signal.SIGKILL
        assert not vivo(pid_de(pidfile))
        assert estado() == antes
    finally:
        mata_o_que_sobrou(pidfile)


def test_a_normal_exit_leaves_the_child_to_the_caller_and_gives_the_handlers_back(tmp_path, sinais_padrao):
    pidfile = tmp_path / "pid"
    antes = estado()
    try:
        with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
            espera_pid(pidfile)
            assert estado() != antes  # armed while the block runs
        assert proc.poll() is None and vivo(pid_de(pidfile))
        assert estado() == antes
    finally:
        mata_o_que_sobrou(pidfile)


def test_an_error_of_the_body_kills_the_child_and_passes_through(tmp_path, sinais_padrao):
    pidfile = tmp_path / "pid"
    try:
        with pytest.raises(ZeroDivisionError):
            with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
                espera_pid(pidfile)
                1 / 0
        assert proc.returncode == -signal.SIGKILL
    finally:
        mata_o_que_sobrou(pidfile)


def test_popen_failing_restores_the_handlers_and_the_error_is_unchanged(sinais_padrao):
    antes = estado()
    with pytest.raises(FileNotFoundError):
        with childio.guarded_child(["/nao/existe/mesmo"]):
            pytest.fail("no child")
    assert estado() == antes


@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_that_lands_in_a_failing_popen_wins_over_the_spawn_error(nome, monkeypatch, sinais_padrao):
    """There is no child to kill, but the engine was told to stop: it stops (the module's `except OSError` must not turn it into
    a spawn error and carry on)."""
    import os

    real = subprocess.Popen

    class PopenQueFalha(real):
        def __init__(self, *args, **kwargs):
            os.kill(os.getpid(), getattr(signal, nome))  # inside Popen, before it fails
            raise FileNotFoundError("sem o programa")

    monkeypatch.setattr(subprocess, "Popen", PopenQueFalha)
    antes = estado()
    exc, _ = esperado(nome)
    with pytest.raises(exc):
        with childio.guarded_child(["x"]):
            pytest.fail("no child")
    assert estado() == antes


def test_sighup_ignored_by_the_parent_stays_ignored(tmp_path):
    """nohup semantics, as instagram.py has always had them: an ignored SIGHUP is never taken over (and so never ends the engine)."""
    pidfile = tmp_path / "pid"
    antes = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
            espera_pid(pidfile)
            assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
            signal.raise_signal(signal.SIGHUP)  # ignored: nothing happens
            assert proc.poll() is None
        assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
    finally:
        signal.signal(signal.SIGHUP, antes)
        mata_o_que_sobrou(pidfile)


def test_ctrl_c_is_taken_over_only_while_python_default_handler_is_in_place(tmp_path, sinais_padrao):
    """An engine with its own SIGINT handler keeps it: the guard does not replace what it does not understand."""
    def meu(signum, frame):
        pass

    signal.signal(signal.SIGINT, meu)
    pidfile = tmp_path / "pid"
    try:
        with childio.guarded_child(sleeper(pidfile), start_new_session=True):
            assert signal.getsignal(signal.SIGINT) is meu
            assert signal.getsignal(signal.SIGTERM) != signal.SIG_DFL
        assert signal.getsignal(signal.SIGINT) is meu
    finally:
        mata_o_que_sobrou(pidfile)


def test_off_the_main_thread_it_degrades_to_a_plain_popen_and_still_kills_on_error(tmp_path):
    """signal.signal raises ValueError off the main thread: nothing is armed, nothing crashes, the body error still kills the child."""
    pidfile = tmp_path / "pid"
    resultado: dict = {}

    def trabalho():
        try:
            with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
                resultado["armado"] = signal.getsignal(signal.SIGTERM)
                espera_pid(pidfile)
                1 / 0
        except ZeroDivisionError:
            resultado["proc"] = proc
        except BaseException as e:  # noqa: BLE001 - the test reports whatever came out
            resultado["erro"] = repr(e)

    antes = estado()
    hilo = threading.Thread(target=trabalho)
    hilo.start()
    hilo.join(30)
    try:
        assert "erro" not in resultado, resultado
        assert resultado["armado"] == antes["SIGTERM"]  # untouched
        assert resultado["proc"].returncode == -signal.SIGKILL
        assert estado() == antes
    finally:
        mata_o_que_sobrou(pidfile)


def test_a_custom_stop_and_a_custom_kill_are_used(monkeypatch, tmp_path, sinais_padrao):
    """toonflow/moneyprinter stop on Ctrl+C semantics (KeyboardInterrupt for every signal) and stop their server gracefully."""
    pidfile = tmp_path / "pid"
    ganchos = sinaliza_no_popen(monkeypatch, pidfile, signal.SIGTERM)
    parados = []

    def mata(proc):
        parados.append(proc.pid)
        childio.kill_group(proc)

    try:
        with pytest.raises(KeyboardInterrupt):
            with childio.guarded_child(sleeper(pidfile), start_new_session=True, stop=childio.stop_as_interrupt, kill=mata):
                pytest.fail("the block must not run")
        assert parados == [ganchos[0].pid]
    finally:
        mata_o_que_sobrou(pidfile)


def test_a_child_without_its_own_group_is_killed_alone_not_with_the_engine_group(tmp_path, sinais_padrao):
    """No start_new_session: killpg on it would be the engine's own group. Only the child itself is killed."""
    pidfile = tmp_path / "pid"
    try:
        with pytest.raises(ZeroDivisionError):
            with childio.guarded_child(sleeper(pidfile)) as proc:
                espera_pid(pidfile)
                1 / 0
        assert proc.returncode == -signal.SIGKILL
    finally:
        mata_o_que_sobrou(pidfile)


def test_kill_group_takes_the_grandchildren_with_it(tmp_path):
    neto = tmp_path / "neto"
    codigo = ("import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1]]); time.sleep(120)")
    proc = subprocess.Popen([sys.executable, "-c", codigo, str(neto), "import os,sys,time; open(sys.argv[1],'w').write(str(os.getpid())); time.sleep(120)"],
                            start_new_session=True)
    try:
        pid = espera_pid(neto)
        childio.kill_group(proc)
        assert espera(lambda: not vivo(pid), 10), "the grandchild survived the group kill"
    finally:
        mata_o_que_sobrou(neto)
        proc.kill()


def test_start_child_tracks_the_child_before_any_stop_can_be_acted_on(monkeypatch, tmp_path, sinais_padrao):
    """The server list of moneyprinter: the child is in `track` when the stop arrives, so the caller's own cleanup stops it."""
    pidfile = tmp_path / "pid"
    sinaliza_no_popen(monkeypatch, pidfile, signal.SIGTERM)
    procs: list = []
    try:
        with pytest.raises(SystemExit):
            childio.start_child(sleeper(pidfile), track=procs, start_new_session=True)
        assert len(procs) <= 1 and not vivo(pid_de(pidfile))  # killed by the guard; tracked if the signal came after the append
    finally:
        mata_o_que_sobrou(pidfile)


def test_start_child_returns_the_running_child_and_hands_the_handlers_back(tmp_path, sinais_padrao):
    pidfile = tmp_path / "pid"
    antes = estado()
    procs: list = []
    try:
        proc = childio.start_child(sleeper(pidfile), track=procs, start_new_session=True)
        assert procs == [proc] and proc.poll() is None
        assert estado() == antes
    finally:
        mata_o_que_sobrou(pidfile)


def test_the_mcp_lint_counts_guarded_child_and_start_child_as_spawners():
    """test_childio's bare-subprocess lint must not be bypassed by going through the helper without stdin/stdout."""
    import test_childio as lint

    assert lint._bare_calls_src("from . import childio\nchildio.guarded_child(argv)")
    assert lint._bare_calls_src("from . import childio\nchildio.start_child(argv, track=procs)")
    assert lint._bare_calls_src("from .childio import guarded_child\nguarded_child(argv)")
    assert not lint._bare_calls_src("from . import childio\nchildio.guarded_child(argv, stdin=d, stdout=a, stderr=b)")
    assert not lint._bare_calls_src("from . import childio\nchildio.kill_group(proc)")
    assert not lint._bare_calls_src("from . import childio\nchildio.run_child(argv)")

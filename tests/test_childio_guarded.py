"""childio.guarded_child / start_child: a child started through them cannot outlive the engine because of a stop signal,
including the one that lands between the fork and the return of Popen (the engine then had no reference to kill)."""
from __future__ import annotations

import os
import random
import signal
import subprocess
import sys
import threading
import time

import pytest
from _orfao import (POSIX, SINAIS, espera, espera_pid, estado_dos_sinais, limpa, mata_o_que_sobrou, parada_esperada, pid_de,  # noqa: F401
                    sinais_padrao, sinaliza_no_popen, sleeper, vivo)

from simplicio_video import childio

pytestmark = [pytest.mark.skipif(not POSIX, reason="POSIX signals"), pytest.mark.usefixtures("sinais_padrao")]


@pytest.mark.parametrize("nome", SINAIS)
def test_a_signal_inside_popen_kills_the_child_and_raises_the_stop(nome, monkeypatch, tmp_path):
    """The engine gets the signal while Popen is still starting the child: the child is killed (its whole group) and the engine
    exits the usual way (128+n; Ctrl+C is a KeyboardInterrupt). Without the guard the exception came out of Popen: no reference."""
    pidfile = tmp_path / "pid"
    ganchos = sinaliza_no_popen(monkeypatch, pidfile, getattr(signal, nome))
    antes = estado_dos_sinais()
    exc, codigo = parada_esperada(nome)
    try:
        with pytest.raises(exc) as saida:
            with childio.guarded_child(sleeper(pidfile), start_new_session=True):
                pytest.fail("the block must not run: the stop signal came in before the child was handed back")
        if codigo is not None:
            assert saida.value.code == codigo
        (popen,) = ganchos
        assert popen.returncode == -signal.SIGKILL  # killed and reaped by the guard
        assert espera(lambda: not vivo(espera_pid(pidfile)), 10), "the child outlived the engine"
        assert estado_dos_sinais() == antes  # the previous handlers are back
    finally:
        mata_o_que_sobrou(pidfile)


@pytest.mark.parametrize("nome", SINAIS)
def test_a_signal_while_the_engine_waits_kills_the_child_on_the_way_out(nome, tmp_path):
    pidfile = tmp_path / "pid"
    antes = estado_dos_sinais()
    exc, codigo = parada_esperada(nome)
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
        assert estado_dos_sinais() == antes
    finally:
        mata_o_que_sobrou(pidfile)


def test_a_normal_exit_leaves_the_child_to_the_caller_and_gives_the_handlers_back(tmp_path):
    pidfile = tmp_path / "pid"
    antes = estado_dos_sinais()
    try:
        with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
            espera_pid(pidfile)
            assert estado_dos_sinais() != antes  # armed while the block runs
        assert proc.poll() is None and vivo(pid_de(pidfile))
        assert estado_dos_sinais() == antes
    finally:
        mata_o_que_sobrou(pidfile)


def test_an_error_of_the_body_kills_the_child_and_passes_through(tmp_path):
    pidfile = tmp_path / "pid"
    try:
        with pytest.raises(ZeroDivisionError):
            with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
                espera_pid(pidfile)
                1 / 0
        assert proc.returncode == -signal.SIGKILL
    finally:
        mata_o_que_sobrou(pidfile)


def test_popen_failing_restores_the_handlers_and_the_error_is_unchanged():
    antes = estado_dos_sinais()
    with pytest.raises(FileNotFoundError):
        with childio.guarded_child(["/nao/existe/mesmo"]):
            pytest.fail("no child")
    assert estado_dos_sinais() == antes


@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_that_lands_in_a_failing_popen_wins_over_the_spawn_error(nome, monkeypatch):
    """There is no child to kill, but the engine was told to stop: it stops (the module's `except OSError` must not turn it into
    a spawn error and carry on)."""
    import os

    real = subprocess.Popen

    class PopenQueFalha(real):
        def __init__(self, *args, **kwargs):
            os.kill(os.getpid(), getattr(signal, nome))  # inside Popen, before it fails
            raise FileNotFoundError("sem o programa")

    monkeypatch.setattr(subprocess, "Popen", PopenQueFalha)
    antes = estado_dos_sinais()
    exc, _ = parada_esperada(nome)
    with pytest.raises(exc):
        with childio.guarded_child(["x"]):
            pytest.fail("no child")
    assert estado_dos_sinais() == antes


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


def test_ctrl_c_is_taken_over_only_while_python_default_handler_is_in_place(tmp_path):
    """An engine with its own SIGINT handler keeps it: the guard does not replace what it does not understand."""
    def meu(signum, frame):
        pass

    signal.signal(signal.SIGINT, meu)
    pidfile = tmp_path / "pid"
    proc = None
    try:
        with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
            espera_pid(pidfile)  # ready before anything can fail: the cleanup below needs the pid
            assert signal.getsignal(signal.SIGINT) is meu
            assert signal.getsignal(signal.SIGTERM) != signal.SIG_DFL
        assert signal.getsignal(signal.SIGINT) is meu
    finally:
        limpa(proc, pidfile)


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

    antes = estado_dos_sinais()
    hilo = threading.Thread(target=trabalho)
    hilo.start()
    hilo.join(30)
    try:
        assert "erro" not in resultado, resultado
        assert resultado["armado"] == antes["SIGTERM"]  # untouched
        assert resultado["proc"].returncode == -signal.SIGKILL
        assert estado_dos_sinais() == antes
    finally:
        mata_o_que_sobrou(pidfile)


def test_a_custom_stop_and_a_custom_kill_are_used(monkeypatch, tmp_path):
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


def test_a_child_without_its_own_group_is_killed_alone_not_with_the_engine_group(tmp_path):
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


def test_start_child_tracks_the_child_before_any_stop_can_be_acted_on(monkeypatch, tmp_path):
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


def test_start_child_returns_the_running_child_and_hands_the_handlers_back(tmp_path):
    pidfile = tmp_path / "pid"
    antes = estado_dos_sinais()
    procs: list = []
    proc = None
    try:
        proc = childio.start_child(sleeper(pidfile), track=procs, start_new_session=True)
        espera_pid(pidfile)  # ready before the assertions: a failing one must still find a pid to clean up
        assert procs == [proc] and proc.poll() is None
        assert estado_dos_sinais() == antes
    finally:
        limpa(proc, pidfile)


def test_the_mcp_lint_counts_guarded_child_and_start_child_as_spawners():
    """test_childio's bare-subprocess lint must not be bypassed by going through the helper without stdin/stdout."""
    import test_childio as lint

    assert lint._bare_calls_src("from . import childio\nchildio.guarded_child(argv)")
    assert lint._bare_calls_src("from . import childio\nchildio.start_child(argv, track=procs)")
    assert lint._bare_calls_src("from .childio import guarded_child\nguarded_child(argv)")
    assert not lint._bare_calls_src("from . import childio\nchildio.guarded_child(argv, stdin=d, stdout=a, stderr=b)")
    assert not lint._bare_calls_src("from . import childio\nchildio.kill_group(proc)")
    assert not lint._bare_calls_src("from . import childio\nchildio.run_child(argv)")


# ---- a second stop signal while the first one is being handled ----

def _segundo_sinal_na_primeira_linha_do_except(gen_frame, sinal: int) -> dict:
    """Trace `gen_frame` (the suspended generator of guarded_child): once the body's exception has been thrown into it, the next
    line it runs is the first of its `except` clause. Fire `sinal` right there, exactly where a second signal does damage: after
    the first handler raised, before the kill. Returns a dict that records whether it fired."""
    estado = {"viu_a_excecao": False, "disparou": False}

    def local(frame, evento, arg):
        if evento == "exception":
            estado["viu_a_excecao"] = True
        elif evento == "line" and estado["viu_a_excecao"] and not estado["disparou"]:
            estado["disparou"] = True
            signal.raise_signal(sinal)  # the Python handler runs here, before the line does
        return local

    gen_frame.f_trace = local
    gen_frame.f_trace_lines = True
    sys.settrace(lambda *a: None)  # tracing must be on for the frame's own trace function to be called
    return estado


@pytest.mark.parametrize("segundo", ["SIGHUP", "SIGTERM", "SIGINT"])
def test_a_second_stop_signal_while_the_child_is_being_killed_does_not_cut_the_kill_short(segundo, tmp_path):
    """Deterministic: SIGTERM raises the stop out of the body; a second signal lands on the very next line of guarded_child,
    before the child is killed. The kill must still happen and the first stop is what comes out (the second one is only noted)."""
    pidfile = tmp_path / "pid"
    cm = childio.guarded_child(sleeper(pidfile), start_new_session=True)
    antes = estado_dos_sinais()
    estado = None
    try:
        with pytest.raises((SystemExit, KeyboardInterrupt)) as saida:  # a second stop that escapes must fail the test, not end pytest
            with cm as proc:
                espera_pid(pidfile)
                estado = _segundo_sinal_na_primeira_linha_do_except(cm.gen.gi_frame, getattr(signal, segundo))
                signal.raise_signal(signal.SIGTERM)  # the first stop: raised from the handler, out of the body
                pytest.fail("the first stop must leave the block")
        sys.settrace(None)
        assert estado["disparou"], "the second signal was never fired: the test did not exercise the window"
        assert isinstance(saida.value, SystemExit) and saida.value.code == 128 + signal.SIGTERM, repr(saida.value)
        assert proc.returncode == -signal.SIGKILL, "the second signal cut the kill short: the child is an orphan"
        assert not vivo(pid_de(pidfile))
        assert estado_dos_sinais() == antes
    finally:
        sys.settrace(None)
        limpa(locals().get("proc"), pidfile)


def test_smoke_a_storm_of_stop_signals_never_orphans_the_child(tmp_path):
    """SMOKE test, not a discriminator (it passes on the code without the fix: the window is a few bytecodes wide and a storm cannot
    aim at it; the settrace tests above are the ones that fail without it). Randomized (seeded), short: a burst of SIGTERM/SIGHUP from another thread lands anywhere in a guarded start, wait and kill.
    Whatever the interleaving, the engine ends with the first stop's exit code and the child is dead and reaped."""
    rng = random.Random(20261106)
    sobra_de_sinais: list = []

    def sobra(signum, frame):  # outside the guard: a late signal must not end the test run
        sobra_de_sinais.append(signum)

    signal.signal(signal.SIGTERM, sobra)
    signal.signal(signal.SIGHUP, sobra)
    argv = [sys.executable, "-c", "import time; time.sleep(120)"]
    for _ in range(25):
        rajada = [rng.choice((signal.SIGTERM, signal.SIGHUP)) for _ in range(rng.randint(2, 8))]
        folgas = [rng.choice((0, 0, 0.0001, 0.0005, 0.002)) for _ in rajada]
        vistos: list = []

        def mata(p, vistos=vistos):
            vistos.append(p)
            childio.kill_group(p)

        def dispara(rajada=rajada, folgas=folgas):
            limite = time.monotonic() + 5
            while signal.getsignal(signal.SIGINT) is signal.default_int_handler and time.monotonic() < limite:  # armed: SIGINT is the last one it takes
                time.sleep(0.0001)
            for sinal, folga in zip(rajada, folgas):
                if folga:
                    time.sleep(folga)
                signal.pthread_kill(principal, sinal)  # to the main thread: a signal taken by this one would not interrupt its sleep

        principal = threading.get_ident()
        hilo = threading.Thread(target=dispara)
        hilo.start()
        try:
            with pytest.raises(SystemExit) as saida:
                with childio.guarded_child(argv, start_new_session=True, kill=mata):
                    time.sleep(10)  # a stop signal ends this
            assert saida.value.code in (128 + signal.SIGTERM, 128 + signal.SIGHUP)
            assert len(vistos) == 1, "the stop came out without the child being killed"
            assert vistos[0].returncode == -signal.SIGKILL and not vivo(vistos[0].pid), "the child outlived the engine"
        finally:
            hilo.join(10)
            for p in vistos:
                limpa(p, tmp_path / "nenhum")
    # No wall-clock ceiling on purpose (same as the burst test of test_childio_registry.py, PR #203): under host load the 25 rounds took
    # 10.1 s against the old 4.5 s limit (wave-0 review, load > 5) with every child dead and reaped, so the clock measured the machine.
    # What matters is asserted in each round: exit code 128+n, the child killed exactly once, dead and reaped. A hang stays bounded: the
    # body sleeps at most 10 s and the signalling thread is joined with a 10 s timeout.


# ---- kill_group refuses what it must not signal ----

class _Falso:
    """A stand-in for a Popen: records what would be signalled."""

    def __init__(self, pid, returncode=None, poll_rc=None):
        self.pid, self.returncode, self._poll_rc, self.chamadas = pid, returncode, poll_rc, []

    def poll(self):
        if self.returncode is None and self._poll_rc is not None:
            self.returncode = self._poll_rc
        return self.returncode

    def kill(self):
        self.chamadas.append("kill")

    def wait(self, timeout=None):
        self.chamadas.append("wait")


@pytest.fixture
def sinais_enviados(monkeypatch):
    enviados: list = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: enviados.append(("killpg", pgid, sig)))
    monkeypatch.setattr(os, "kill", lambda pid, sig: enviados.append(("kill", pid, sig)))
    return enviados


@pytest.mark.parametrize("pid", [1, 0, -1, -1234])
def test_kill_group_refuses_pid_one_and_below(pid, sinais_enviados):
    """killpg(1) is init's group; killpg(0) is OUR group; killpg(-n) is a different call altogether."""
    falso = _Falso(pid)
    childio.kill_group(falso, group=True)
    childio.kill_group(falso, group=False)
    assert sinais_enviados == [] and "kill" not in falso.chamadas


@pytest.mark.parametrize("quem", ["pgid", "pid"])
def test_kill_group_refuses_our_own_group_and_our_own_pid(quem, sinais_enviados):
    falso = _Falso(os.getpgrp() if quem == "pgid" else os.getpid())
    childio.kill_group(falso, group=True)
    childio.kill_group(falso, group=False)
    assert sinais_enviados == [] and "kill" not in falso.chamadas


def test_kill_group_alone_does_not_signal_a_child_that_has_exited_and_been_reaped(sinais_enviados):
    """Without a group of its own there is nothing left to kill, and the pid may belong to somebody else by now (reuse)."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(30)
    childio.kill_group(proc, group=False)
    assert sinais_enviados == []


def test_kill_group_still_sweeps_the_group_of_a_leader_that_has_exited_and_been_reaped(sinais_enviados, monkeypatch):
    """The caller says it started the child with start_new_session: the group (pgid == pid) can outlive its leader (grandchildren), and
    Linux does not reuse a pid while a group with that id exists, so the group is still swept."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    proc.wait(30)
    childio.kill_group(proc, group=True)
    assert sinais_enviados == [("killpg", proc.pid, signal.SIGKILL)]


def test_kill_group_alone_skips_a_child_that_poll_says_has_exited(sinais_enviados):
    falso = _Falso(os.getpid() + 100000, returncode=None, poll_rc=0)  # returncode not set yet, poll() reaps it
    childio.kill_group(falso, group=False)
    assert sinais_enviados == [] and "kill" not in falso.chamadas


def test_kill_group_sweeps_the_group_of_a_leader_that_poll_says_has_exited(sinais_enviados):
    falso = _Falso(os.getpid() + 100000, returncode=None, poll_rc=0)
    childio.kill_group(falso, group=True)
    assert sinais_enviados == [("killpg", falso.pid, signal.SIGKILL)]


NETO_CODE = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(120)"
# a leader that starts a grandchild (same group) and exits at once
LIDER_CODE = "import subprocess, sys; subprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1]])"


def test_kill_group_takes_the_grandchildren_of_a_leader_that_already_exited(tmp_path):
    neto = tmp_path / "neto"
    proc = subprocess.Popen([sys.executable, "-c", LIDER_CODE, str(neto), NETO_CODE], start_new_session=True)
    try:
        pid = espera_pid(neto)
        proc.wait(30)  # the leader is gone and reaped; the grandchild lives in its group
        assert vivo(pid)
        childio.kill_group(proc, group=True)
        assert espera(lambda: not vivo(pid), 10), "the grandchild of a reaped leader survived the group kill"
    finally:
        limpa(None, neto)


def test_the_default_killer_sweeps_the_group_when_the_body_fails_after_the_leader_exited(tmp_path):
    """The shape of instagram._executa and busca._rodar: the script exits (reaped), then the body raises (output too big)."""
    neto = tmp_path / "neto"
    try:
        with pytest.raises(ZeroDivisionError):
            with childio.guarded_child([sys.executable, "-c", LIDER_CODE, str(neto), NETO_CODE], start_new_session=True) as proc:
                espera_pid(neto)
                proc.wait(30)
                1 / 0
        assert espera(lambda: not vivo(pid_de(neto)), 10), "the background process of the script outlived the failing call"
    finally:
        limpa(None, neto)


def test_kill_group_true_on_a_child_that_leads_no_group_kills_only_the_child(tmp_path):
    """No start_new_session: killpg(child pid) names no group (a silent no-op that left the child running), and the engine's own
    group must never be the target. The child itself is killed."""
    pidfile = tmp_path / "pid"
    proc = subprocess.Popen(sleeper(pidfile))
    try:
        espera_pid(pidfile)
        assert os.getpgid(proc.pid) == os.getpgrp()  # it shares our group
        childio.kill_group(proc, group=True)
        assert proc.returncode == -signal.SIGKILL and not vivo(proc.pid)
        assert os.getpgrp()  # and we are still here
    finally:
        limpa(proc, pidfile)


def test_kill_group_still_kills_the_group_of_a_live_group_leader(tmp_path):
    pidfile = tmp_path / "pid"
    proc = subprocess.Popen(sleeper(pidfile), start_new_session=True)
    try:
        espera_pid(pidfile)
        childio.kill_group(proc, group=True)
        assert proc.returncode == -signal.SIGKILL and not vivo(proc.pid)
    finally:
        limpa(proc, pidfile)


# ---- restore is signal-safe ----

def test_restore_gives_every_handler_back_even_when_a_restored_one_raises(monkeypatch, tmp_path):
    """The previous SIGTERM handler raises when it fires (moneyprinter's `_on_term`). A SIGTERM that is delivered the moment it is put
    back must not leave SIGHUP and SIGINT with the guard's handler for the rest of the process."""
    def on_term(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, on_term)
    antes = estado_dos_sinais()
    real = signal.signal
    disparou: list = []

    def signal_que_entrega(sig, handler):
        anterior = real(sig, handler)
        if sig == signal.SIGTERM and handler is on_term and not disparou:  # the restore of SIGTERM: a SIGTERM lands now
            disparou.append(True)
            signal.raise_signal(signal.SIGTERM)
        return anterior

    pidfile = tmp_path / "pid"
    proc = None
    try:
        with pytest.raises(SystemExit):
            with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
                espera_pid(pidfile)
                monkeypatch.setattr(signal, "signal", signal_que_entrega)
        monkeypatch.undo()
        assert disparou, "the test did not exercise the restore"
        assert estado_dos_sinais() == antes, "a handler of the guard was left installed"
    finally:
        monkeypatch.undo()
        for n, h in antes.items():
            real(getattr(signal, n), h)
        limpa(proc, pidfile)

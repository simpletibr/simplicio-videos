"""childio's process-wide registry of live guarded children, and the exit guard the MCP server installs once from its main thread.

The MCP server runs its sync tools in worker threads, where guarded_child cannot take signals (signal.signal is main-thread only):
a SIGTERM to the server used to end it at once with the children still running. The registry lets the main thread kill them."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from _orfao import POSIX, SINAIS, espera, espera_pid, limpa, pid_de, sinais_padrao, sleeper, vivo  # noqa: F401

from simplicio_video import childio

pytestmark = pytest.mark.skipif(not POSIX, reason="POSIX signals")


def test_the_child_is_registered_while_the_block_runs_and_forgotten_when_it_ends(tmp_path):
    pidfile = tmp_path / "pid"
    proc = None
    try:
        with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
            espera_pid(pidfile)
            assert proc in childio.live_children()
        assert proc not in childio.live_children()  # a normal exit hands the child to the caller
        assert proc.poll() is None
    finally:
        limpa(proc, pidfile)


def test_the_child_is_forgotten_when_the_block_fails(tmp_path):
    pidfile = tmp_path / "pid"
    seen = []
    with pytest.raises(ZeroDivisionError):
        with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
            seen.append(proc)
            1 / 0
    assert seen[0] not in childio.live_children() and seen[0].returncode == -signal.SIGKILL
    limpa(seen[0], pidfile)


def test_kill_live_kills_every_registered_child_with_its_own_killer(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    ga, gb = None, None
    parados = []
    try:
        with childio.guarded_child(sleeper(a), start_new_session=True) as ga, \
                childio.guarded_child(sleeper(b), kill=lambda p: (parados.append(p.pid), childio.kill_group(p, False))) as gb:
            espera_pid(a), espera_pid(b)
            assert {ga, gb} <= set(childio.live_children())
            childio.kill_live()
            assert ga.returncode == -signal.SIGKILL and gb.returncode == -signal.SIGKILL
            assert parados == [gb.pid]  # the child's own killer, not a guess
    finally:
        limpa(ga, a)
        limpa(gb, b)


def test_a_child_is_not_even_forked_once_the_engine_is_ending(monkeypatch, tmp_path):
    """A tool call that begins after the exit guard has done its sweep: the sweep could not see its child, so none is started and the
    exit is raised in its place."""
    forks = []
    real = subprocess.Popen

    class Popen(real):
        def __init__(self, *a, **k):
            forks.append(a)
            super().__init__(*a, **k)

    monkeypatch.setattr(subprocess, "Popen", Popen)
    monkeypatch.setattr(childio, "_exit_code", 128 + signal.SIGTERM)
    childio._exiting.set()
    try:
        with pytest.raises(SystemExit) as saida:
            with childio.guarded_child(sleeper(tmp_path / "pid"), start_new_session=True):
                pytest.fail("the engine is ending: no block may run")
        assert saida.value.code == 128 + signal.SIGTERM
        assert forks == [] and childio.live_children() == []
    finally:
        childio._exiting.clear()


# ---- the exit guard, in an engine process of its own (worker threads, main thread waiting, like the MCP server) ----

HARNESS = textwrap.dedent('''
    import json, os, signal, subprocess, sys, threading, time
    from simplicio_video import childio
    for _n in ("SIGTERM", "SIGHUP", "SIGINT"):  # as a shell starts the engine: a launcher's ignored signal (nohup, a background job) is not inherited
        signal.signal(getattr(signal, _n), signal.default_int_handler if _n == "SIGINT" else signal.SIG_DFL)
    cfg = json.loads(os.environ["HARNESS_CFG"])
    if cfg.get("ignore_sighup"):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    if cfg.get("gap"):  # a signal that lands inside Popen, in a worker thread, with the child already running
        _real = subprocess.Popen
        _main = threading.get_ident()
        class _P(_real):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                if cfg["gap"] in " ".join(map(str, a[0])):
                    for _ in range(600):
                        if os.path.exists(cfg["gap"]) and open(cfg["gap"]).read().strip():
                            break
                        time.sleep(0.05)
                    signal.pthread_kill(_main, signal.SIGTERM)
                    time.sleep(0.3)  # still inside Popen while the main thread handles the signal
        subprocess.Popen = _P
    if cfg.get("respawn"):  # a worker that starts the next child as soon as the previous one dies, Popen slow to hand it back
        _real2 = subprocess.Popen
        _n = [0]
        class _Q(_real2):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                if "time.sleep(120)" in " ".join(map(str, a[0])):
                    n, _n[0] = _n[0], _n[0] + 1
                    open(cfg["respawn"] + "." + str(n), "w").write(str(self.pid))  # the fork happened: this child exists
                    if n >= 1:
                        time.sleep(0.3)  # the engine's handler must not leave while this is going on
        subprocess.Popen = _Q
    childio.install_exit_guard()

    def work_respawn(pidfile, group):
        while True:
            with childio.guarded_child([sys.executable, "-c",
                    "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(120)", pidfile],
                    start_new_session=True) as proc:
                proc.wait()

    def work(pidfile, group):
        with childio.guarded_child([sys.executable, "-c",
                "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(120)", pidfile],
                start_new_session=group) as proc:
            proc.wait()

    for i, group in enumerate(cfg["groups"]):
        threading.Thread(target=work_respawn if cfg.get("respawn") else work, args=(cfg["pidfiles"][i], group), daemon=True).start()
    if cfg.get("to_worker"):  # the OS hands the signal to a worker thread (it does in a burst); the main thread sleeps in a syscall
        def _poke():
            for _p in cfg["pidfiles"]:
                for _ in range(600):
                    if os.path.exists(_p) and open(_p).read().strip():
                        break
                    time.sleep(0.05)
            signal.pthread_kill(threading.get_ident(), signal.SIGTERM)
            time.sleep(60)
        threading.Thread(target=_poke, daemon=True).start()
    if cfg.get("nested"):  # SIGTERM, and a second signal lands inside the flag's set (inside Event.set's lock, when it is an Event) in the first handler
        for _p in cfg["pidfiles"]:
            for _ in range(600):
                if os.path.exists(_p) and open(_p).read().strip():
                    break
                time.sleep(0.05)
        _fired = []
        def _local(frame, event, arg):
            if event == "line" and not _fired:
                _fired.append(1)
                signal.raise_signal(signal.SIGHUP)
            return None
        def _global(frame, event, arg):
            # inside the lock of Event.set (its notify_all) on code that uses an Event; on our own flag's set otherwise
            name, fname = frame.f_code.co_name, frame.f_code.co_filename
            if event == "call" and not _fired and (name == "notify_all" or (name == "set" and fname.endswith("childio.py"))):
                return _local
            return None
        sys.settrace(_global)
        signal.raise_signal(signal.SIGTERM)
        time.sleep(60)
    print("ready", flush=True)
    time.sleep(60)
    print("the engine was not stopped", flush=True)
    sys.exit(3)
''')


def _roda_harness(tmp_path: Path, cfg: dict) -> subprocess.Popen:
    import json

    from conftest import ROOT, offline_env

    env = offline_env(HARNESS_CFG=json.dumps(cfg))
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])
    with open(tmp_path / "h.out", "w") as out, open(tmp_path / "h.err", "w") as err:
        return subprocess.Popen([sys.executable, "-c", HARNESS], env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=tmp_path)


@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_to_the_engine_kills_the_children_of_worker_threads_and_exits_128_plus_n(nome, tmp_path):
    pidfiles = [tmp_path / "p0", tmp_path / "p1"]
    motor = _roda_harness(tmp_path, {"groups": [True, False], "pidfiles": [str(p) for p in pidfiles]})
    try:
        pids = [espera_pid(p) for p in pidfiles]
        os.kill(motor.pid, getattr(signal, nome))
        assert motor.wait(15) == 128 + getattr(signal, nome), (tmp_path / "h.err").read_text()
        assert espera(lambda: not any(vivo(p) for p in pids), 10), "a child outlived the engine"
    finally:
        motor.kill()
        motor.wait()
        for p in pidfiles:
            limpa(None, p)


def test_a_signal_inside_popen_of_a_worker_thread_still_ends_with_the_child_dead(tmp_path):
    """The child exists, the worker is still inside Popen (it is not registered yet) when the main thread gets SIGTERM."""
    pidfile = tmp_path / "p0"
    motor = _roda_harness(tmp_path, {"groups": [True], "pidfiles": [str(pidfile)], "gap": str(pidfile)})
    try:
        pid = espera_pid(pidfile)
        assert motor.wait(15) == 128 + signal.SIGTERM, (tmp_path / "h.err").read_text()
        assert espera(lambda: not vivo(pid), 10), "the child that was being started outlived the engine"
    finally:
        motor.kill()
        motor.wait()
        limpa(None, pidfile)


def test_a_worker_that_starts_the_next_child_when_the_killed_one_dies_does_not_leave_an_orphan(tmp_path):
    """The sweep kills child 1; the worker, woken by that, starts child 2 (a tool that runs several programs in a row). The engine
    must not leave while that start is going on, or must stop it before the fork: no child may outlive it."""
    pidfile, marcas = tmp_path / "p0", tmp_path / "forked"
    motor = _roda_harness(tmp_path, {"groups": [True], "pidfiles": [str(pidfile)], "respawn": str(marcas)})
    try:
        espera_pid(pidfile)
        os.kill(motor.pid, signal.SIGTERM)
        assert motor.wait(15) == 128 + signal.SIGTERM, (tmp_path / "h.err").read_text()
        pids = [int(m.read_text()) for m in sorted(tmp_path.glob("forked.*")) if m.read_text().strip()]
        assert pids, "the harness never forked a child"
        assert espera(lambda: not any(vivo(p) for p in pids), 10), f"a child that was started while the engine was ending outlived it: {pids}"
    finally:
        motor.kill()
        motor.wait()
        for m in tmp_path.glob("forked.*"):
            limpa(None, m)
        limpa(None, pidfile)


def test_an_ignored_sighup_stays_ignored_by_the_exit_guard(tmp_path):
    pidfile = tmp_path / "p0"
    motor = _roda_harness(tmp_path, {"groups": [True], "pidfiles": [str(pidfile)], "ignore_sighup": True})
    try:
        pid = espera_pid(pidfile)
        os.kill(motor.pid, signal.SIGHUP)
        time.sleep(0.5)
        assert motor.poll() is None and vivo(pid)  # nohup semantics, as the guard has always had them
    finally:
        motor.kill()
        motor.wait()
        limpa(None, pidfile)


def test_nothing_changes_for_the_cli_without_the_exit_guard(tmp_path):
    """install_exit_guard is the MCP entry point's call: without it a guarded child in the main thread behaves as before."""
    antes = {n: signal.getsignal(getattr(signal, n)) for n in SINAIS}
    pidfile = tmp_path / "pid"
    proc = None
    try:
        with childio.guarded_child(sleeper(pidfile), start_new_session=True) as proc:
            espera_pid(pidfile)
        assert {n: signal.getsignal(getattr(signal, n)) for n in SINAIS} == antes
    finally:
        limpa(proc, pidfile)
        assert pid_de(pidfile) is None or not vivo(pid_de(pidfile))


def test_a_second_stop_signal_inside_the_first_handler_does_not_deadlock_it(tmp_path):
    """The handler used a threading.Event: a signal landing inside Event.set re-entered the same non-reentrant lock on the main
    thread, and the engine never exited (children leaked, even later SIGTERMs hung). Nothing in the handler may block."""
    pidfile = tmp_path / "p0"
    motor = _roda_harness(tmp_path, {"groups": [True], "pidfiles": [str(pidfile)], "nested": True})
    try:
        pid = espera_pid(pidfile)
        assert motor.wait(15) in (128 + signal.SIGTERM, 128 + signal.SIGHUP), (tmp_path / "h.err").read_text()
        assert espera(lambda: not vivo(pid), 10), "a child outlived the engine"
    finally:
        motor.kill()
        motor.wait()
        limpa(None, pidfile)


def test_a_stop_signal_taken_by_a_worker_thread_still_ends_the_engine(tmp_path):
    """CPython runs Python signal handlers on the main thread only; with the main thread asleep in a syscall a signal caught by a
    worker thread would wait for it to wake up (a minute here). The wakeup-fd watcher runs the handler at once."""
    pidfile = tmp_path / "p0"
    motor = _roda_harness(tmp_path, {"groups": [True], "pidfiles": [str(pidfile)], "to_worker": True})
    try:
        pid = espera_pid(pidfile)
        assert motor.wait(15) == 128 + signal.SIGTERM, (tmp_path / "h.err").read_text()
        assert espera(lambda: not vivo(pid), 10), "a child outlived the engine"
    finally:
        motor.kill()
        motor.wait()
        limpa(None, pidfile)


def test_a_burst_of_stop_signals_always_ends_the_engine_and_its_children(tmp_path):
    """Seeded bursts of 1-4 signals 0-10 ms apart at 120 engines (12 at a time): none hangs, every child is dead."""
    import random

    rng = random.Random(20261107)
    ok = (128 + signal.SIGTERM, 128 + signal.SIGHUP, 128 + signal.SIGINT)
    for lote in range(10):
        motores = []
        for i in range(12):
            d = tmp_path / f"b{lote}_{i}"
            d.mkdir()
            motores.append((d, _roda_harness(d, {"groups": [True], "pidfiles": [str(d / "p0")]})))
        pids = {}
        try:
            for d, m in motores:
                pids[d] = espera_pid(d / "p0")
                for _ in range(rng.randint(1, 4)):
                    os.kill(m.pid, rng.choice((signal.SIGTERM, signal.SIGHUP, signal.SIGINT)))
                    time.sleep(rng.choice((0, 0.001, 0.005, 0.01)))
            for d, m in motores:
                assert m.wait(15) in ok, (d / "h.err").read_text()
            assert espera(lambda: not any(vivo(p) for p in pids.values()), 10), "a child outlived its engine"
        finally:
            for d, m in motores:
                m.kill()
                m.wait()
                limpa(None, d / "p0")


@pytest.mark.usefixtures("sinais_padrao")
def test_install_exit_guard_says_what_it_did(monkeypatch):
    import threading

    try:
        assert childio.install_exit_guard() == childio.GUARD_INSTALLED
        assert childio.install_exit_guard() == childio.GUARD_ALREADY
        out: list = []
        t = threading.Thread(target=lambda: out.append(childio.install_exit_guard()))
        t.start()
        t.join()
        assert out == [childio.GUARD_ALREADY]  # installed already: that is what is true, wherever it is asked from
    finally:
        childio.uninstall_exit_guard()
    assert {n: signal.getsignal(getattr(signal, n)) for n in SINAIS} == {n: (signal.default_int_handler if n == "SIGINT" else signal.SIG_DFL)
                                                                         for n in SINAIS}  # the previous handlers are back
    for n in SINAIS:  # a process that ignores / handles everything itself: nothing to take over
        signal.signal(getattr(signal, n), signal.SIG_IGN if n != "SIGINT" else (lambda *a: None))
    assert childio.install_exit_guard() == childio.GUARD_NOTHING


@pytest.mark.usefixtures("sinais_padrao")
def test_install_exit_guard_off_the_main_thread_installs_nothing():
    import threading

    out: list = []
    t = threading.Thread(target=lambda: out.append(childio.install_exit_guard()))
    t.start()
    t.join()
    assert out == [childio.GUARD_NOT_MAIN]

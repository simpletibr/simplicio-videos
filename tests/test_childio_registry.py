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
from _orfao import POSIX, SINAIS, espera, espera_pid, limpa, pid_de, sleeper, vivo

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


def test_a_child_started_while_the_engine_is_already_ending_is_killed_by_its_own_guard(monkeypatch, tmp_path):
    """A tool call that begins after the exit guard has done its sweep: the child is registered too late for kill_live, so the guard
    that started it ends it and raises the exit."""
    pidfile = tmp_path / "pid"
    vistos = []
    monkeypatch.setattr(childio, "_exit_code", 128 + signal.SIGTERM)
    childio._exiting.set()
    try:
        with pytest.raises(SystemExit) as saida:
            with childio.guarded_child(sleeper(pidfile), start_new_session=True, kill=lambda p: (vistos.append(p), childio.kill_group(p))):
                pytest.fail("the engine is ending: no block may run")
        assert saida.value.code == 128 + signal.SIGTERM
        assert len(vistos) == 1 and vistos[0].returncode == -signal.SIGKILL and vistos[0] not in childio.live_children()
    finally:
        childio._exiting.clear()
        limpa(vistos[0] if vistos else None, pidfile)


# ---- the exit guard, in an engine process of its own (worker threads, main thread waiting, like the MCP server) ----

HARNESS = textwrap.dedent('''
    import json, os, signal, subprocess, sys, threading, time
    from simplicio_video import childio
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
    print("ready", flush=True)
    time.sleep(60)
    print("the engine was not stopped", flush=True)
    sys.exit(3)
''')


def _roda_harness(tmp_path: Path, cfg: dict) -> subprocess.Popen:
    from conftest import ROOT, offline_env

    import json
    env = offline_env(HARNESS_CFG=json.dumps(cfg))
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])
    return subprocess.Popen([sys.executable, "-c", HARNESS], env=env, stdin=subprocess.DEVNULL, stdout=open(tmp_path / "h.out", "w"),
                            stderr=open(tmp_path / "h.err", "w"), cwd=tmp_path)


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

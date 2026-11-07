"""`hostos.run_limitado` and the stop signals: the child it starts must die with the engine, also under the MCP exit guard.

The MCP server runs its tools in worker threads and calls `childio.install_exit_guard()` from its main thread: SIGTERM, SIGHUP and
Ctrl+C then kill every child that is in childio's registry and leave through `os._exit`, which skips `atexit`. `run_limitado` used to
keep a second registry (`_VIVOS`) that only an `atexit` hook knew, so the server ended with 143/129/130 and the `git ls-remote` of
`video.doctor --online` (also `video.tools` and `video.status`) kept running. These tests start the engine in a process of its own
(`lanca_como_shell`: the stop signals at their defaults, whatever pytest ignores) and look at the child that is left.

Also pinned here, so the move onto `childio.guarded_child` changes none of it: what `run_limitado` returns, raises and kills, and the
Windows branch (`CREATE_NEW_PROCESS_GROUP` and `taskkill /T`, UNVERIFIED on a real Windows: only its wiring is checked, with a fake Popen)."""
from __future__ import annotations

import ast
import contextlib
import json
import os
import signal
import stat
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from _orfao import POSIX, SINAIS, espera, espera_pid, estado_dos_sinais, lanca_como_shell, vivo

from simplicio_video import childio, hostos
from helpers import SRC

POSIX_ONLY = pytest.mark.skipif(not POSIX, reason="POSIX signals and sh")
COMO_SH = 'echo $$ > "$1"; exec sleep 60'  # the pid of the child (it becomes `sleep`) goes to the file in $1


def dorme(pidfile: Path) -> list[str]:
    return ["sh", "-c", COMO_SH, "sh", str(pidfile)]


def pids_de(pidfile: Path) -> list[int]:
    try:
        return [int(x) for x in pidfile.read_text().split()]
    except (OSError, ValueError):
        return []


def mata_todos(pidfile: Path) -> None:
    """Cleanup of every test: whatever a child left running dies here (each pid led a session of its own)."""
    for pid in pids_de(pidfile):
        if vivo(pid):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, signal.SIGKILL) if os.getpgid(pid) == pid else os.kill(pid, signal.SIGKILL)


def motor(tmp_path: Path, corpo: str, *args: str, **extra_env: str) -> subprocess.Popen:
    """Python source `corpo` as an engine process of its own, started as a shell starts it (stop signals at their defaults)."""
    from helpers import ROOT, offline_env

    env = offline_env(**extra_env)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])
    # files, not pipes: an orphan that inherited a pipe would keep the read open and hang the test instead of failing it
    return lanca_como_shell([sys.executable, "-c", corpo, *args], env=env, stdin=subprocess.DEVNULL,
                            stdout=open(tmp_path / "motor.out", "w"), stderr=open(tmp_path / "motor.err", "w"), cwd=tmp_path)


def acaba(proc: subprocess.Popen) -> None:
    proc.kill()
    proc.wait()


# ---- the defect: a stop signal to a process under the exit guard (the MCP server) leaves the child of run_limitado alive ----

SERVIDOR = textwrap.dedent('''
    import sys, threading, time
    from simplicio_video import childio, hostos
    childio.install_exit_guard()  # what mcp_server.main() does, from the main thread
    pidfile = sys.argv[1]

    def ferramenta():  # a tool: the sync tools of the MCP server run in worker threads
        hostos.run_limitado(["sh", "-c", 'echo $$ > "$1"; exec sleep 60', "sh", pidfile], timeout=120)

    threading.Thread(target=ferramenta, daemon=True).start()
    time.sleep(60)
''')


@POSIX_ONLY
@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_to_a_process_under_the_exit_guard_kills_the_child_of_run_limitado(nome, tmp_path):
    pidfile = tmp_path / "filho.pid"
    servidor = motor(tmp_path, SERVIDOR, str(pidfile))
    try:
        pid = espera_pid(pidfile)
        os.kill(servidor.pid, getattr(signal, nome))
        assert servidor.wait(20) == 128 + getattr(signal, nome), (tmp_path / "motor.err").read_text()
        assert espera(lambda: not vivo(pid), 10), "the child of run_limitado outlived the server"
    finally:
        acaba(servidor)
        mata_todos(pidfile)


@POSIX_ONLY
@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_to_the_real_mcp_server_kills_the_git_read_of_video_doctor_trilhas_online(nome, tmp_path):
    """The real server (stdio) and a tool that reads the upstream of each track with `git ls-remote` (run_limitado) in worker
    threads: the server ends with 128+n and no `git` of the reads is left. (`trilhas` is the table of the tracks alone: the other
    checks of `doctor --online` touch sockets, which offline_env blocks.)"""
    pytest.importorskip("mcp")
    from conftest import ROOT, offline_env

    bindir, home, pidfile = tmp_path / "bin", tmp_path / "home", tmp_path / "git.pids"
    bindir.mkdir(), home.mkdir()
    falso = bindir / "git"  # the read of the upstream (ls-remote) hangs, one line per such git; any other git call fails at once
    falso.write_text(f'#!/bin/bash\ncase " $* " in *" ls-remote "*) echo $$ >> {pidfile}; exec sleep 120;; esac\n'
                     'echo "fatal: not a repository" >&2\nexit 128\n')
    falso.chmod(falso.stat().st_mode | stat.S_IEXEC)
    env = offline_env(HOME=str(home), PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}", SIMPLICIO_VIDEO_DATA=str(tmp_path / "data"))
    env.pop("SIMPLICIO_OFFLINE", None)  # --online reads the upstream; the sitecustomize of offline_env still blocks every socket
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])
    servidor = lanca_como_shell([sys.executable, "-m", "simplicio_video.mcp_server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=open(tmp_path / "server.err", "w"), env=env, cwd=tmp_path)

    def manda(obj):
        servidor.stdin.write((json.dumps(obj) + "\n").encode())
        servidor.stdin.flush()

    try:
        manda({"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        assert b'"id":1' in servidor.stdout.readline()
        manda({"jsonrpc": "2.0", "method": "notifications/initialized"})
        manda({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "video.doctor", "arguments": {"args": "trilhas --online"}}})
        assert espera(lambda: pids_de(pidfile), 30), "the tool never started its git"
        os.kill(servidor.pid, getattr(signal, nome))
        assert servidor.wait(20) == 128 + getattr(signal, nome), (tmp_path / "server.err").read_text()[-600:]
        pids = pids_de(pidfile)
        assert espera(lambda: not any(vivo(p) for p in pids), 10), f"a git read outlived the MCP server: {[p for p in pids if vivo(p)]}"
    finally:
        acaba(servidor)
        mata_todos(pidfile)


# ---- the same defect in-process: the child is in childio's registry, so the exit guard can reach it ----

@POSIX_ONLY
def test_the_child_of_run_limitado_is_in_childios_registry_while_it_runs_and_out_of_it_after(tmp_path):
    pidfile = tmp_path / "filho.pid"
    feito = []
    fio = threading.Thread(target=lambda: feito.append(hostos.run_limitado(dorme(pidfile), timeout=60)), daemon=True)
    fio.start()
    try:
        pid = espera_pid(pidfile)
        assert pid in [p.pid for p in childio.live_children()]
        childio.kill_live()  # what the exit guard does on a stop signal
        fio.join(10)
        assert not fio.is_alive() and feito and feito[0].returncode == -signal.SIGKILL
        assert pid not in [p.pid for p in childio.live_children()]
    finally:
        mata_todos(pidfile)


@POSIX_ONLY
def test_the_child_of_run_limitado_leaves_the_registry_when_it_times_out_or_cannot_start(tmp_path):
    pidfile = tmp_path / "filho.pid"
    antes = childio.live_children()
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            hostos.run_limitado(dorme(pidfile), timeout=0.5)
        with pytest.raises(FileNotFoundError):
            hostos.run_limitado([str(tmp_path / "nao-existe")], timeout=5)
        assert childio.live_children() == antes
    finally:
        mata_todos(pidfile)


# ---- the CLI: no exit guard, run_limitado in the main thread ----

CLI = textwrap.dedent('''
    import sys
    from simplicio_video import hostos
    hostos.run_limitado(["sh", "-c", 'echo $$ > "$1"; exec sleep 60', "sh", sys.argv[1]], timeout=120)
''')


@POSIX_ONLY
@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_to_the_cli_while_run_limitado_waits_leaves_no_child(nome, tmp_path):
    """Ctrl+C, SIGTERM (an agent's timeout) and SIGHUP (the terminal closed) reach the engine in the main thread: the child that
    lives in a session of its own dies with it. The engine ends by the signal or with the shell's 128+n."""
    pidfile = tmp_path / "filho.pid"
    cli = motor(tmp_path, CLI, str(pidfile))
    try:
        pid = espera_pid(pidfile)
        os.kill(cli.pid, getattr(signal, nome))
        assert cli.wait(20) in (-getattr(signal, nome), 128 + getattr(signal, nome)), (tmp_path / "motor.err").read_text()
        assert espera(lambda: not vivo(pid), 10), "the child outlived the CLI"
    finally:
        acaba(cli)
        mata_todos(pidfile)


SAI = textwrap.dedent('''
    import os, sys, threading, time
    from simplicio_video import hostos
    pidfile = sys.argv[1]
    threading.Thread(target=lambda: hostos.run_limitado(["sh", "-c", 'echo $$ > "$1"; exec sleep 60', "sh", pidfile], timeout=120),
                     daemon=True).start()
    while not (os.path.exists(pidfile) and open(pidfile).read().strip()):
        time.sleep(0.05)
''')  # the main thread ends while a daemon thread is still waiting for the read (the budget of `doctor --online` is over)


@POSIX_ONLY
def test_the_process_ending_in_the_middle_of_a_read_takes_the_child_with_it(tmp_path):
    pidfile = tmp_path / "filho.pid"
    saida = motor(tmp_path, SAI, str(pidfile))
    try:
        assert saida.wait(30) == 0, (tmp_path / "motor.err").read_text()
        pid = espera_pid(pidfile)
        assert espera(lambda: not vivo(pid), 10), "the child of an interrupted read outlived the process"
    finally:
        acaba(saida)
        mata_todos(pidfile)


# ---- what run_limitado returns, raises and kills: unchanged ----

@POSIX_ONLY
def test_it_returns_the_exit_code_the_text_and_the_argv_like_subprocess_run(tmp_path):
    argv = ["sh", "-c", "echo oi; echo erro >&2; exit 7"]
    r = hostos.run_limitado(argv, timeout=10)
    assert isinstance(r, subprocess.CompletedProcess)
    assert (r.args, r.returncode, r.stdout, r.stderr) == (argv, 7, "oi\n", "erro\n")
    assert r.args is not argv  # a copy: the caller's list is not shared
    assert hostos.run_limitado([Path("/bin/sh"), "-c", "echo $0"], timeout=10).stdout == "/bin/sh\n"  # every item goes through str()


@POSIX_ONLY
def test_a_child_killed_by_a_signal_has_the_negative_return_code():
    assert hostos.run_limitado(["sh", "-c", "kill -9 $$"], timeout=10).returncode == -signal.SIGKILL


@POSIX_ONLY
def test_stdin_is_closed_and_the_output_has_no_cap_of_its_own():
    assert hostos.run_limitado(["sh", "-c", "cat; echo fim"], timeout=10).stdout == "fim\n"  # cat would wait on a terminal
    grande = hostos.run_limitado(["sh", "-c", "head -c 1000000 /dev/zero | tr '\\0' x"], timeout=20)
    assert grande.returncode == 0 and len(grande.stdout) == 1_000_000


@POSIX_ONLY
def test_the_environment_is_exactly_the_one_given_or_the_inherited_one(monkeypatch, tmp_path):
    monkeypatch.setenv("SV_HERDADA", "pai")
    assert hostos.run_limitado(["sh", "-c", 'echo "${SV_HERDADA-sem}"'], timeout=10).stdout == "pai\n"
    dado = hostos.run_limitado(["sh", "-c", 'echo "$A:${SV_HERDADA-sem}"'], timeout=10, env={"A": "1", "PATH": os.environ["PATH"]})
    assert dado.stdout == "1:sem\n"
    onde = hostos.run_limitado(["sh", "-c", "pwd -P"], timeout=10, cwd=tmp_path)  # a Path is accepted
    assert onde.stdout.strip() == os.path.realpath(tmp_path)


@POSIX_ONLY
def test_the_text_is_utf8_and_a_bad_byte_becomes_the_replacement_character():
    assert hostos.run_limitado(["sh", "-c", "printf '\\303\\247\\377'"], timeout=10).stdout == "ç�"


@POSIX_ONLY
def test_a_program_that_cannot_start_raises_oserror_with_nothing_left_behind(tmp_path):
    antes = estado_dos_sinais()
    with pytest.raises(FileNotFoundError):
        hostos.run_limitado([str(tmp_path / "nao-existe")], timeout=5)
    (tmp_path / "sem-x").write_text("#!/bin/sh\n")  # no execute bit
    with pytest.raises(PermissionError):
        hostos.run_limitado([str(tmp_path / "sem-x")], timeout=5)
    assert estado_dos_sinais() == antes


@POSIX_ONLY
def test_a_timeout_raises_timeoutexpired_and_kills_the_whole_tree(tmp_path):
    """subprocess.run would kill only the child: its own session (the group) is what is killed, the grandchild with it."""
    pidfile = tmp_path / "arvore.pids"
    argv = ["sh", "-c", 'echo $$ > "$1"; sleep 60 & echo $! >> "$1"; wait', "sh", str(pidfile)]
    antes = estado_dos_sinais()
    inicio = time.monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired) as erro:
            hostos.run_limitado(argv, timeout=0.5)
        assert time.monotonic() - inicio < 5
        assert erro.value.cmd == argv and erro.value.timeout == 0.5
        assert erro.value.__cause__ is None and erro.value.__suppress_context__  # `from None`: the caller sees only the timeout
        pids = pids_de(pidfile)
        assert len(pids) == 2 and espera(lambda: not any(vivo(p) for p in pids), 10), [p for p in pids if vivo(p)]
        assert estado_dos_sinais() == antes
    finally:
        mata_todos(pidfile)


@POSIX_ONLY
def test_ctrl_c_on_the_main_thread_kills_the_tree_and_ends_the_engine_by_sigint(tmp_path):
    pidfile = tmp_path / "filho.pid"
    cli = motor(tmp_path, CLI, str(pidfile))
    try:
        pid = espera_pid(pidfile)
        os.kill(cli.pid, signal.SIGINT)
        assert cli.wait(20) == -signal.SIGINT  # an unhandled KeyboardInterrupt: Python dies by the signal, as the shell reports it
        assert espera(lambda: not vivo(pid), 10)
    finally:
        acaba(cli)
        mata_todos(pidfile)


# ---- the Windows branch (UNVERIFIED on a real Windows): CREATE_NEW_PROCESS_GROUP and taskkill /T, wired as before ----

def test_the_windows_branch_starts_a_process_group_and_ends_the_tree_with_taskkill_once(monkeypatch):
    chamadas = {"taskkill": [], "popen": []}

    class Filho:
        pid, returncode = 4242, None

        def __init__(self, argv, **kw):
            chamadas["popen"].append((argv, kw))
            self.esperas = 0

        def communicate(self, timeout=None):
            self.esperas += 1
            if self.esperas == 1:
                raise subprocess.TimeoutExpired("x", timeout)
            return "", ""

        def poll(self):
            return None

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    def falso_run(argv, **kw):
        chamadas["taskkill"].append(argv)

    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)  # exists only on Windows
    monkeypatch.setattr(subprocess, "Popen", Filho)
    monkeypatch.setattr(subprocess, "run", falso_run)
    with pytest.raises(subprocess.TimeoutExpired) as erro:
        hostos.run_limitado(["git", "ls-remote"], timeout=3)
    assert erro.value.cmd == ["git", "ls-remote"] and erro.value.timeout == 3
    (argv, kw), = chamadas["popen"]
    assert argv == ["git", "ls-remote"] and kw["creationflags"] == 512 and "start_new_session" not in kw
    assert kw["stdin"] is subprocess.DEVNULL and kw["stdout"] == subprocess.PIPE and kw["stderr"] == subprocess.PIPE
    assert chamadas["taskkill"] == [["taskkill", "/T", "/F", "/PID", "4242"]]


# ---- one place stops a group: childio.kill_group; one registry of live children: childio's ----

@pytest.mark.parametrize("modulo", ["hostos", "busca", "instagram", "matchcut"])
def test_stopping_a_group_is_not_reimplemented_with_killpg_here(modulo):
    arvore = ast.parse((SRC / f"{modulo}.py").read_text(encoding="utf-8"))
    copias = [n.name for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == "_matar"]
    usos = [n.lineno for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and n.attr == "killpg"]
    assert usos == [] and copias == [], "use childio.kill_group"


def test_the_names_a_test_replaces_in_instagram_and_matchcut_are_childios_kill_group():
    from simplicio_video import instagram, matchcut

    assert instagram._matar is childio.kill_group and matchcut._matar is childio.kill_group


def test_hostos_keeps_no_registry_of_live_children_of_its_own():
    assert not hasattr(hostos, "_VIVOS") and not hasattr(hostos, "_mata_os_vivos")

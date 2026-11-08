"""U22f: the child of `simplicio-video instagram run` gets its kernel limits from a wrapper that runs INSIDE the child and then execs the
script, not from a fork hook of the engine.

Why. A fork hook (`preexec_fn`) runs Python code between fork and exec. The Python documentation says it is not safe in a process with
threads (the child can deadlock before it ever reaches exec), and the MCP server runs every tool in a worker thread. matchcut already put
its limits through a wrapper; instagram now does too, with the limits it always had (RLIMIT_CPU 35 s soft / 40 s hard, no core dump)
plus one it did not have: RLIMIT_AS, 4 GiB of address space. Measured on the six real scripts of the pinned commit with the largest input
the engine accepts (1 MiB): the peak address space is 115 MiB, and 128 MiB is the smallest limit under which every run still ends the same.

What is proved here, with a real child process (a probe script that prints what the process it runs in really is, standing in for the
upstream script: `run_tool` is the path the CLI and the MCP take, only the checkout check is skipped, and tests/test_instagram.py covers
that): the limits are set in the child and never in the engine; the script is still the process the engine started (same pid, leader of
its own session, so the group kill still reaches it) in the same isolated mode; a limit the kernel refuses does not stop the script;
the engine passes no fork hook from any thread; where there is no `resource` module (Windows) the script runs directly, as it always did.
"""
from __future__ import annotations

import ast
import contextlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from helpers import SRC, isolate_tools
from simplicio_video import instagram, matchcut

try:
    import resource
except ImportError:  # pragma: no cover (Windows)
    resource = None

POSIX = pytest.mark.skipif(resource is None or os.name != "posix", reason="POSIX rlimit")
LINUX = pytest.mark.skipif(sys.platform != "linux", reason="the exact RLIMIT_AS values are frozen on Linux (macOS does not enforce it)")
MIB = 1024 ** 2
QUATRO_GIB = 4 * 1024 ** 3
NOMES = ("RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_CORE")
# what a child may see: the closed list of the engine plus the two names Python itself may add (locale coercion, macOS launcher)
ENV_PERMITIDO = {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONIOENCODING", "TMP", "TEMP", "SYSTEMROOT", "LC_CTYPE", "__PYVENV_LAUNCHER__"}

# What the child runs in place of an upstream script: it prints the facts about its own process (or allocates, when asked to).
SONDA = r'''
import json, os, sys
try:
    import resource
except ImportError:
    resource = None
alvo = " ".join(sys.argv[1:])
if "TRIGGER:ALLOC:" in alvo:
    mib = int(alvo.split("TRIGGER:ALLOC:", 1)[1].split()[0])
    try:
        buf = bytearray(mib * 1024 * 1024)
    except MemoryError:
        print("MemoryError")
    else:
        print("alloc-ok", len(buf))
    sys.exit(0)
limites = {} if resource is None else {n: list(resource.getrlimit(getattr(resource, n))) for n in ("RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_CORE")}
print(json.dumps({"rlimit": limites, "pid": os.getpid(), "pgrp": os.getpgrp(), "sid": os.getsid(0), "argv": sys.argv,
                  "executable": sys.executable, "env": sorted(os.environ), "stdin": sys.stdin.read(),
                  "flags": {"isolated": sys.flags.isolated, "utf8": sys.flags.utf8_mode, "nobytecode": sys.flags.dont_write_bytecode}}))
'''


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    (tmp_path / "home").mkdir()
    (tmp_path / "work").mkdir()
    isolate_tools(monkeypatch, tmp_path, drop=("INSTAGRAM_DIR", "SIMPLICIO_INSTAGRAM_DIR", "SIMPLICIO_INSTAGRAM_REF"))
    monkeypatch.chdir(tmp_path / "work")


@pytest.fixture
def sonda(tmp_path, monkeypatch) -> Path:
    """`run_tool` runs the probe where it would run the upstream script (the checkout and its sha256 are checked by test_instagram.py)."""
    script = tmp_path / "sonda" / "probe.py"
    script.parent.mkdir()
    script.write_text(SONDA, encoding="utf8")
    monkeypatch.setattr(instagram, "_prepara", lambda f, destino: (script, []))
    return script


@pytest.fixture
def popens(monkeypatch) -> list:
    """Every subprocess.Popen the engine makes (arguments and keywords), then the real one runs."""
    chamadas: list = []
    real = subprocess.Popen

    def espia(argv, *a, **k):
        chamadas.append(SimpleNamespace(argv=list(argv), kwargs=k))
        return real(argv, *a, **k)

    monkeypatch.setattr(subprocess, "Popen", espia)
    return chamadas


def roda(texto: str = "x") -> dict:
    """One `hookscore --hook TEXTO` through the real path of the CLI and the MCP; what the probe printed, as a dict."""
    res = instagram.run_tool("hookscore", ["--hook", texto])
    assert res["codigo_saida"] == 0, res["stderr"]
    return json.loads(res["stdout"])


def limites_do_pai() -> dict:
    return {n: list(resource.getrlimit(getattr(resource, n))) for n in NOMES}


def pula_se_o_pai_ja_limita() -> None:
    """The exact values below hold when the engine's own hard limits are not already lower (a lower hard limit is inherited and wins)."""
    infinito = resource.RLIM_INFINITY
    cpu, memoria = resource.getrlimit(resource.RLIMIT_CPU)[1], resource.getrlimit(resource.RLIMIT_AS)[1]
    if cpu != infinito and cpu < 40:
        pytest.skip("o pai já tem um limite de CPU menor que 40 s")
    if memoria != infinito and memoria < QUATRO_GIB:
        pytest.skip("o pai já tem um limite de memória menor que 4 GiB")


# ---------------------------------------------------------------------------------------------------------- the limits are the child's

@POSIX
@LINUX
def test_the_child_has_the_cpu_the_memory_and_the_core_limits_when_the_script_starts(sonda):
    pula_se_o_pai_ja_limita()
    assert roda()["rlimit"] == {"RLIMIT_CPU": [35, 40], "RLIMIT_AS": [QUATRO_GIB, QUATRO_GIB], "RLIMIT_CORE": [0, 0]}


@POSIX
@LINUX
def test_the_limits_follow_the_constants_of_the_module_read_when_the_script_is_run(sonda, monkeypatch):
    pula_se_o_pai_ja_limita()
    monkeypatch.setattr(instagram, "TIMEOUT_S", 12.5)
    monkeypatch.setattr(instagram, "CPU_FOLGA_S", 3)
    monkeypatch.setattr(instagram, "MAX_MEM_BYTES", 512 * MIB)
    assert roda()["rlimit"] == {"RLIMIT_CPU": [15, 20], "RLIMIT_AS": [512 * MIB, 512 * MIB], "RLIMIT_CORE": [0, 0]}  # int(12.5) + 3, hard +5
    monkeypatch.setattr(instagram, "CPU_FOLGA_S", -100)  # never below one second of CPU: zero would mean no limit
    assert roda()["rlimit"]["RLIMIT_CPU"] == [1, 6]


@POSIX
@LINUX
def test_a_memory_limit_of_zero_leaves_the_memory_alone(sonda, monkeypatch):
    pula_se_o_pai_ja_limita()
    monkeypatch.setattr(instagram, "MAX_MEM_BYTES", 0)
    visto = roda()["rlimit"]
    assert visto["RLIMIT_AS"] == limites_do_pai()["RLIMIT_AS"] and visto["RLIMIT_CPU"] == [35, 40] and visto["RLIMIT_CORE"] == [0, 0]


@POSIX
@LINUX
def test_the_limits_are_the_childs_never_the_engines(sonda):
    antes = limites_do_pai()
    roda()
    assert limites_do_pai() == antes


@POSIX
@LINUX
def test_a_script_that_allocates_past_the_memory_limit_gets_a_memory_error_and_one_under_it_does_not(sonda, monkeypatch):
    monkeypatch.setattr(instagram, "MAX_MEM_BYTES", 256 * MIB)  # nothing is really touched: the allocation is refused (or not) by the kernel
    mais = instagram.run_tool("hookscore", ["--hook", "TRIGGER:ALLOC:512"])
    menos = instagram.run_tool("hookscore", ["--hook", "TRIGGER:ALLOC:16"])
    assert (mais["codigo_saida"], mais["stdout"].strip()) == (0, "MemoryError")
    assert (menos["codigo_saida"], menos["stdout"].strip()) == (0, "alloc-ok 16777216")


# ---------------------------------------------------------------------------------------------------------- the script is the same process as before

@POSIX
def test_the_script_is_the_process_the_engine_started_and_leads_its_own_group(sonda, monkeypatch):
    """The wrapper replaces itself (exec): the pid, the session and the group are the ones the engine holds, so the group kill
    (`kill_group`, on a timeout, a stop signal or the output cap) still reaches the script and what it started."""
    pids: list = []
    real = instagram.childio.guarded_child

    @contextlib.contextmanager
    def espia(argv, **kw):
        with real(argv, **kw) as proc:
            pids.append(proc.pid)
            yield proc

    monkeypatch.setattr(instagram.childio, "guarded_child", espia)
    visto = roda()
    assert pids == [visto["pid"]] and visto["pgrp"] == visto["pid"] == visto["sid"]


@POSIX
def test_the_script_runs_in_isolated_mode_with_its_own_arguments_and_the_engines_interpreter(sonda):
    visto = roda()
    assert visto["flags"] == {"isolated": 1, "utf8": 1, "nobytecode": 1}
    assert visto["argv"] == [str(sonda), "--hook=x"] and visto["executable"] == sys.executable  # the limits are not in what the script receives
    assert set(visto["env"]) <= ENV_PERMITIDO, set(visto["env"]) - ENV_PERMITIDO  # the wrapper adds nothing to the closed environment


@POSIX
def test_over_the_mcp_the_text_reaches_the_script_through_the_wrapper_with_the_limits_set(sonda):
    res = instagram.run_tool("hookscore", [], texto="oi\nmundo", canal="mcp")
    assert res["codigo_saida"] == 0, res["stderr"]
    visto = json.loads(res["stdout"])
    assert visto["stdin"] == "oi\nmundo" and visto["argv"] == [str(sonda), "-"]
    assert visto["rlimit"]["RLIMIT_CPU"] == [35, 40] and visto["rlimit"]["RLIMIT_CORE"] == [0, 0]  # the memory one is asserted above: same wrapper


@POSIX
def test_the_wrapper_never_imports_from_the_users_folder(sonda, tmp_path):
    """In the terminal the child runs in the folder the user is in: a `resource.py` there must not take the place of the module the wrapper
    imports (isolated mode keeps the working directory out of sys.path), or the limits would silently not be set."""
    (tmp_path / "work" / "resource.py").write_text("open('HIJACKED', 'w').write('x')\n", encoding="utf8")
    visto = roda()
    assert not (tmp_path / "work" / "HIJACKED").exists()
    assert visto["rlimit"]["RLIMIT_CPU"] == [35, 40] and visto["rlimit"]["RLIMIT_CORE"] == [0, 0]


@POSIX
def test_the_engine_starts_the_child_through_the_wrapper_and_without_a_fork_hook(sonda, popens):
    roda()
    (chamada,) = popens
    assert chamada.argv[:6] == [sys.executable, "-I", "-B", "-X", "utf8", "-c"] and chamada.argv[-2:] == [str(sonda), "--hook=x"]
    assert chamada.kwargs.get("preexec_fn") is None and chamada.kwargs["start_new_session"] is True
    assert chamada.kwargs["env"] == instagram._ambiente() and "shell" not in chamada.kwargs


@POSIX
@LINUX
def test_tools_started_from_several_threads_never_get_a_fork_hook_and_each_child_gets_its_limits(sonda, popens):
    pula_se_o_pai_ja_limita()
    fundo = threading.Event()
    parados = [threading.Thread(target=fundo.wait, daemon=True) for _ in range(4)]  # what the MCP server's own threads are, to the engine
    for t in parados:
        t.start()
    assert threading.active_count() >= 1 + len(parados)
    feitos: list = []
    erros: list = []

    def trabalha(i: int) -> None:
        try:
            res = instagram.run_tool("hookscore", ["--hook", f"x{i}"])
            feitos.append((i, res["codigo_saida"], json.loads(res["stdout"])["rlimit"]))
        except BaseException as e:  # the thread must report, not die quietly
            erros.append(e)

    trabalhadores = [threading.Thread(target=trabalha, args=(i,)) for i in range(6)]
    try:
        for t in trabalhadores:
            t.start()
        for t in trabalhadores:
            t.join(60)
    finally:
        fundo.set()
    assert not erros, erros
    assert sorted(i for i, _, _ in feitos) == list(range(6)) and all(rc == 0 for _, rc, _ in feitos)
    assert len(popens) == 6 and all(c.kwargs.get("preexec_fn") is None for c in popens)
    assert all(rl == {"RLIMIT_CPU": [35, 40], "RLIMIT_AS": [QUATRO_GIB, QUATRO_GIB], "RLIMIT_CORE": [0, 0]} for _, _, rl in feitos)


# ---------------------------------------------------------------------------------------------------------- what the kernel may refuse, and Windows

CODIGO_DO_PAI_COM_LIMITE_MENOR = r'''
import json, pathlib, resource, sys
sys.path.insert(0, sys.argv[1])
resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))  # the engine itself runs under a hard limit lower than the 4 GiB it asks for
from simplicio_video import instagram
instagram._prepara = lambda f, destino: (pathlib.Path(sys.argv[2]), [])
res = instagram.run_tool("hookscore", ["--hook", "x"])
print(json.dumps({"codigo_saida": res["codigo_saida"], "stdout": res["stdout"], "stderr": res["stderr"]}))
'''


@POSIX
@LINUX
def test_a_limit_the_kernel_refuses_is_skipped_and_the_script_still_runs_with_the_others(sonda):
    """setrlimit raises ValueError when the new hard limit is above the one inherited: that limit stays as it was, the others are set,
    and the script runs. (A wrapper that did not catch it would end with a traceback and the script would never run.)"""
    r = subprocess.run([sys.executable, "-c", CODIGO_DO_PAI_COM_LIMITE_MENOR, str(SRC.parent), str(sonda)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)
    assert res["codigo_saida"] == 0, res["stderr"]
    assert json.loads(res["stdout"])["rlimit"] == {"RLIMIT_CPU": [35, 40], "RLIMIT_AS": [2 << 30, 2 << 30], "RLIMIT_CORE": [0, 0]}


@POSIX
def test_without_the_resource_module_the_script_runs_directly_as_it_always_did(sonda, popens, monkeypatch):
    """Windows has no rlimit (UNVERIFIED there: simulated by taking the module away): no wrapper, no limits, no fork hook, and exec
    must not be used (on Windows it would start a new process and let the one the engine waits for exit at once)."""
    monkeypatch.setattr(instagram, "resource", None)
    visto = roda()
    (chamada,) = popens
    assert chamada.argv == [sys.executable, "-I", "-B", "-X", "utf8", str(sonda), "--hook=x"]
    assert chamada.kwargs.get("preexec_fn") is None and chamada.kwargs["start_new_session"] is True
    assert visto["rlimit"] == limites_do_pai()  # nothing was set: the child has what the engine has
    assert visto["pid"] == visto["pgrp"]


# ---------------------------------------------------------------------------------------------------------- one mechanism, no fork hook anywhere

def test_no_module_of_the_engine_starts_a_child_with_a_fork_hook():
    assert "preexec_fn" not in (SRC / "instagram.py").read_text(encoding="utf8")  # not even in a comment: the ficha greps for it
    achados = []
    for arquivo in sorted(SRC.rglob("*.py")):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf8"))):
            if ((isinstance(no, ast.keyword) and no.arg == "preexec_fn") or (isinstance(no, ast.Constant) and no.value == "preexec_fn")
                    or (isinstance(no, ast.Attribute) and no.attr == "preexec_fn") or (isinstance(no, ast.Name) and no.id == "preexec_fn")):
                achados.append(f"{arquivo.relative_to(SRC)}:{no.lineno}")
    assert achados == []


@POSIX
@LINUX
def test_the_instagram_and_the_matchcut_wrappers_set_the_same_memory_and_core_limits_and_the_same_flags(tmp_path):
    """Until one wrapper lives in `terceiros` (it takes terceiros.py and matchcut.py, which U22f does not own: see the PR), the two
    copies must not drift apart on what they share: RLIMIT_AS, RLIMIT_CORE and the flags of the interpreter that runs the script."""
    sonda = ("import json, resource, sys; print(json.dumps({n: list(resource.getrlimit(getattr(resource, n))) for n in "
             "('RLIMIT_AS', 'RLIMIT_CORE')} | {'flags': [sys.flags.isolated, sys.flags.utf8_mode, sys.flags.dont_write_bytecode]}))")
    base = [sys.executable, "-I", "-B", "-X", "utf8", "-c"]
    for memoria in (3 * 1024 ** 3, 0):
        mc = subprocess.run([*base, matchcut._WRAPPER, str(memoria), "-c", sonda], capture_output=True, text=True, check=True, cwd=tmp_path)
        ig = subprocess.run([*base, instagram._WRAPPER, "35", str(memoria), "-c", sonda], capture_output=True, text=True, check=True, cwd=tmp_path)
        assert json.loads(ig.stdout) == json.loads(mc.stdout), memoria

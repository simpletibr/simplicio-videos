"""What the scripts of `scripts/` share, frozen BEFORE `scripts/_lib.py` takes it (U18).

Measured with `ast` on the five scripts, the only code that is IDENTICAL in more than one of them is: `REPO` (smoke_so, smoke_trilhas,
e2e_real), `UsageError` + `git()` (check_tdd, check_ownership) and the kill of a child's process group (`_matar_arvore` of
smoke_trilhas and `_matar_grupo` of e2e_real). The names the ficha listed (`Resultado`, `Passo`, `Saida`, `_executar`, `_resumo`)
repeat the NAME, not the code: their fields and bodies differ, so they stay where they are.

These tests pin what a caller sees (the value of `REPO`, what `git()` returns and raises, what the kill does and does not raise) and the
`--help` of every script. They are green before the extraction and must stay green after it.
"""
import ast
import hashlib
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from helpers import ROOT, SCRIPTS

CINCO = ("smoke_so", "smoke_trilhas", "e2e_real", "check_tdd", "check_ownership")


def _carrega(nome: str):
    """The script, loaded by path as the other tests do (the folder `scripts/` is NOT on sys.path)."""
    spec = importlib.util.spec_from_file_location(f"lib_scripts_{nome}", SCRIPTS / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look the module up by name while the script is executed
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return mod


@pytest.fixture(scope="module")
def mods():
    carregados = {n: _carrega(n) for n in CINCO}
    yield carregados
    for n in CINCO:
        sys.modules.pop(f"lib_scripts_{n}", None)


# ---------------------------------------------------------------- --help, byte for byte
HELP_SHA256 = {  # sha256 of the stdout of `python scripts/<x>.py --help` with COLUMNS=100, frozen on Python 3.13 (argparse wraps by version)
    "smoke_so": "0872cbc4b1dbe19b280604c1e1494ab70421c844b9fa74ca0e2287df5232b9e0",
    "smoke_trilhas": "08373c43febe46455396f92f2a55a0d15ae27da5fced7946fe016194ffc3e72d",
    "e2e_real": "849f713885bf7e635d11e702652d652622ef61cf3daae862d0871e55d38b0dd1",
    "check_tdd": "2c4f4eb7b1a8be06481536e3de9eb12095c7d162c92e10f9968f2658fe95fe12",
    "check_ownership": "dc2aa473103ed28d942da4e592fe1d232e0a47b752a4150662544460e3640e79",
}


def _help(nome: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "COLUMNS": "100", "NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, str(SCRIPTS / f"{nome}.py"), "--help"], capture_output=True, text=True, env=env, timeout=120)


@pytest.mark.parametrize("nome", CINCO)
def test_help_runs_as_a_file_and_prints_the_usage(nome):
    r = _help(nome)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("usage: "), r.stdout[:200]
    assert nome in r.stdout.splitlines()[0] or f"scripts/{nome}.py" in r.stdout


@pytest.mark.parametrize("nome", CINCO)
def test_help_is_frozen_byte_for_byte(nome):
    if sys.version_info[:2] != (3, 13):
        pytest.skip("the help hashes were frozen on Python 3.13 (argparse wraps the usage differently by version)")
    r = _help(nome)
    assert hashlib.sha256(r.stdout.encode()).hexdigest() == HELP_SHA256[nome], r.stdout
    assert r.stderr == ""


# ---------------------------------------------------------------- REPO
@pytest.mark.parametrize("nome", ["smoke_so", "smoke_trilhas", "e2e_real"])
def test_repo_is_the_root_of_the_checkout(mods, nome):
    assert isinstance(mods[nome].REPO, Path) and mods[nome].REPO == ROOT
    assert (mods[nome].REPO / "pyproject.toml").is_file()


def test_e2e_src_hangs_from_repo(mods):
    assert mods["e2e_real"].SRC == ROOT / "src"


# ---------------------------------------------------------------- UsageError and git()
@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("nome", ["check_tdd", "check_ownership"])
def test_usage_error_is_a_plain_exception(mods, nome):
    erro = mods[nome].UsageError
    assert issubclass(erro, Exception) and erro.__mro__[1] is Exception and not issubclass(erro, SystemExit)
    assert str(erro("x")) == "x"


@pytest.mark.parametrize("nome", ["check_tdd", "check_ownership"])
def test_git_returns_the_stdout(mods, repo, nome):
    assert mods[nome].git("rev-parse", "--is-inside-work-tree") == "true\n"
    assert mods[nome].git("status", "--porcelain") == ""
    (repo / "a.txt").write_text("x")
    assert mods[nome].git("status", "--porcelain") == "?? a.txt\n"


@pytest.mark.parametrize("nome", ["check_tdd", "check_ownership"])
def test_git_failure_raises_usage_error_with_the_command_and_the_stderr(mods, repo, nome):
    with pytest.raises(mods[nome].UsageError) as ei:
        mods[nome].git("rev-parse", "--verify", "nao-existe")
    assert str(ei.value).startswith("git rev-parse --verify nao-existe: ") and "fatal" in str(ei.value)
    assert not str(ei.value).endswith(("\n", " "))  # the stderr is stripped


@pytest.mark.parametrize("nome", ["check_tdd", "check_ownership"])
def test_git_check_false_returns_the_stdout_of_a_failed_command(mods, repo, nome):
    assert mods[nome].git("rev-parse", "--verify", "--quiet", "nao-existe", check=False) == ""


@pytest.mark.parametrize("nome", ["check_tdd", "check_ownership"])
def test_a_failed_git_ends_the_script_with_2_and_names_it_on_stderr(mods, tmp_path, monkeypatch, capsys, nome):
    monkeypatch.chdir(tmp_path)  # not a repository: the first git call fails
    argv = ["--base", "origin/nope"] if nome == "check_tdd" else ["31", "--base", "origin/nope"]
    assert mods[nome].main(argv) == 2
    visto = capsys.readouterr()
    assert visto.err.startswith(f"{nome}: ") and visto.err.endswith("\n") and visto.out == ""


# ---------------------------------------------------------------- the kill of a process group
def _vivo(pid: int) -> bool:
    """Alive and not a zombie (a container without a reaper keeps the dead ones as `Z`)."""
    try:
        estado = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return False
    return estado != "Z"


MATAR = [("smoke_trilhas", "_matar_arvore"), ("e2e_real", "_matar_grupo")]
posix = pytest.mark.skipif(os.name != "posix" or not Path("/proc/self/stat").exists(), reason="process groups and /proc")


@posix
@pytest.mark.parametrize("nome,funcao", MATAR)
def test_the_kill_takes_the_whole_group_down(mods, tmp_path, nome, funcao):
    pidfile = tmp_path / "neto.pid"
    codigo = ("import pathlib, subprocess, sys, time\n"
              "n = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
              f"pathlib.Path({str(pidfile)!r}).write_text(str(n.pid))\n"
              "time.sleep(60)\n")
    proc = subprocess.Popen([sys.executable, "-c", codigo], start_new_session=True)
    try:
        fim = time.monotonic() + 10
        while not pidfile.exists() and time.monotonic() < fim:
            time.sleep(0.02)
        neto = int(pidfile.read_text())
        assert getattr(mods[nome], funcao)(proc) is None
        assert proc.wait(timeout=10) == -signal.SIGKILL
        fim = time.monotonic() + 10
        while _vivo(neto) and time.monotonic() < fim:
            time.sleep(0.02)
        assert not _vivo(neto), "the grandchild lives in the group of the child: it dies with it"
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


@posix
@pytest.mark.parametrize("nome,funcao", MATAR)
def test_the_kill_of_a_group_that_already_ended_is_silent(mods, nome, funcao):
    proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    proc.wait()
    assert getattr(mods[nome], funcao)(proc) is None  # killpg on a dead group: OSError, swallowed


@pytest.mark.parametrize("nome,funcao", MATAR)
def test_without_posix_the_kill_is_the_kill_of_the_child_alone(mods, monkeypatch, nome, funcao):
    visto = []

    class Filho:
        pid = 4242

        def kill(self):
            visto.append("kill")

    monkeypatch.setattr(os, "killpg", lambda *a: visto.append(("killpg", *a)))
    with monkeypatch.context() as m:
        m.setattr(os, "name", "nt")
        assert getattr(mods[nome], funcao)(Filho()) is None
    assert visto == ["kill"]


@pytest.mark.parametrize("nome,funcao", MATAR)
def test_the_kill_swallows_only_oserror(mods, monkeypatch, nome, funcao):
    class Filho:
        pid = 4242

    monkeypatch.setattr(os, "killpg", lambda *a: (_ for _ in ()).throw(PermissionError("not yours")))
    assert getattr(mods[nome], funcao)(Filho()) is None
    monkeypatch.setattr(os, "killpg", lambda *a: (_ for _ in ()).throw(ValueError("not an OSError")))
    with pytest.raises(ValueError):
        getattr(mods[nome], funcao)(Filho())


# ---------------------------------------------------------------- the package never imports a script helper
def test_nothing_in_src_imports_a_script_helper():
    achados = []
    for f in (ROOT / "src" / "simplicio_video").rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            nomes = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""] if isinstance(n, ast.ImportFrom) else []
            achados += [f"{f.relative_to(ROOT)}: {x}" for x in nomes if x.split(".")[0] in {"_lib", "scripts"}]
    assert achados == []


# ================================================================ scripts/_lib.py (what U18 adds)
USAM_LIB = ("check_tdd", "check_ownership", "smoke_trilhas", "e2e_real")


def _lib(mods):
    assert "_lib" in sys.modules, "a script that imports _lib puts its own folder on sys.path first, so the tests that load it by path work"
    assert Path(sys.modules["_lib"].__file__).resolve() == SCRIPTS / "_lib.py"
    return sys.modules["_lib"]


def _importados(caminho: Path) -> set[str]:
    achados = set()
    for n in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            achados |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0:
            achados.add((n.module or "").split(".")[0])
    return achados


def test_lib_uses_only_the_standard_library():
    fora = sorted(m for m in _importados(SCRIPTS / "_lib.py") if m not in sys.stdlib_module_names and m != "__future__")
    assert fora == []


def test_exactly_the_scripts_that_share_something_import_it():
    importam = sorted(n for n in CINCO if "_lib" in _importados(SCRIPTS / f"{n}.py"))
    assert importam == sorted(USAM_LIB)  # smoke_so keeps its own REPO: its test pins "only the standard library at the top"


def test_the_shared_names_are_the_ones_of_lib(mods):
    lib = _lib(mods)
    assert mods["check_tdd"].git is mods["check_ownership"].git is lib.git
    assert mods["check_tdd"].UsageError is mods["check_ownership"].UsageError is lib.UsageError
    assert mods["smoke_trilhas"]._matar_arvore is mods["e2e_real"]._matar_grupo is lib.matar_grupo
    assert mods["smoke_trilhas"].REPO is mods["e2e_real"].REPO is lib.REPO


def test_no_script_defines_again_what_lib_has():
    redefinidos = []
    for f in sorted(SCRIPTS.glob("*.py")):
        if f.name == "_lib.py":
            continue
        for n in ast.parse(f.read_text(encoding="utf-8")).body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in {"git", "UsageError", "_matar_arvore", "_matar_grupo", "matar_grupo"}:
                redefinidos.append(f"{f.name}:{n.name}")
    assert redefinidos == []


@pytest.mark.parametrize("nome", USAM_LIB)
def test_the_script_runs_as_a_file_from_any_folder(nome, tmp_path):
    env = {**os.environ, "COLUMNS": "100", "NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, str(SCRIPTS / f"{nome}.py"), "--help"], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)
    assert r.returncode == 0 and r.stderr == "" and r.stdout == _help(nome).stdout


@pytest.mark.parametrize("nome", USAM_LIB)
def test_the_script_loaded_by_path_in_a_fresh_process_finds_lib(nome, tmp_path):
    """Nothing but the script's own bootstrap puts `scripts/` on sys.path: the earlier tests of this module already did it in this process."""
    codigo = ("import importlib.util, sys\n"
              "assert not any(p.endswith('scripts') for p in sys.path), sys.path\n"
              f"spec = importlib.util.spec_from_file_location('carregado', {str(SCRIPTS / f'{nome}.py')!r})\n"
              "mod = importlib.util.module_from_spec(spec); sys.modules['carregado'] = mod; spec.loader.exec_module(mod)\n"
              "import _lib\n"
              f"assert _lib.__file__ == {str(SCRIPTS / '_lib.py')!r}, _lib.__file__\n")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, cwd=tmp_path, timeout=120,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert r.returncode == 0, r.stderr

"""Fixture `caixa` and helpers for the update, doctor and install tests (direct owner request, PRs #108-#112 style).

`caixa` is a sealed box: HOME, USERPROFILE and PATH point at folders under tmp_path, and a tripwire on subprocess.Popen
refuses to start any program called `simplicio` that does not live under tmp_path. The machine that develops this repo has
a REAL Runtime in ~/.simplicio/bin: with this box a test can never find it, and if a bug computed its real path anyway, the
tripwire fails the test instead of running it. Nothing here reads or writes the shared login file (~/.simplicio/login.json):
the video CLI does not use it any more, and the tests never create it.

The fake Runtime is a Python script (not a shell script) with a tiny launcher, so the same tests run on Linux, macOS
and Windows. Tests that need POSIX file semantics (modes, symlinks, FIFOs, flock) use `posix_real`.

Own module name (not conftest.py): a tests/packaging/conftest.py would shadow the root `conftest` of tests/.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

# Credentials of OTHER programs that must never reach a child process, an output or a log.
LEAKY_ENV = {
    "GH_TOKEN": "fake-gh-1", "GITHUB_TOKEN": "fake-gh-2", "SIMPLICIO_LOGIN_TOKEN": "fake-lt-3",
    "OPENROUTER_API_KEY": "fake-or-4", "ANTHROPIC_API_KEY": "fake-an-5", "AWS_SECRET_ACCESS_KEY": "fake-aws-6",
    "GEMINI_API_KEY": "fake-gem-7",
}
CLEARED_ENV = ("SIMPLICIO_AUTH_FILE", "SIMPLICIO_247_LOGIN", "BROWSER", "PIP_BREAK_SYSTEM_PACKAGES", "SIMPLICIO_VIDEO_HOME",
               *LEAKY_ENV)

# Decided at import time, BEFORE any test simulates another system: the machine that really runs the suite.
REAL_WINDOWS = os.name == "nt"
REAL_PATH = os.environ.get("PATH", "")  # the PATH before `caixa` seals it: only used to find the real git
posix_real = pytest.mark.skipif(REAL_WINDOWS, reason="needs real POSIX files (modes, symlinks, FIFOs, flock)")
SISTEMAS = ["linux", "darwin", "win32"]


def so_incompativel(so: str) -> bool:
    """True when a test that RUNS fake programs under a simulated `so` cannot work on this real machine.

    A real Windows has only .cmd launchers: it can run the win32 case, not the linux/darwin ones."""
    return REAL_WINDOWS and so != "win32"


class _Lazy:
    """A module that is imported on first use, so a missing module fails the TEST (red for the right reason)."""

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_name", name)

    def _real(self):
        try:
            return importlib.import_module(object.__getattribute__(self, "_name"))
        except ImportError as exc:
            pytest.fail(f"module {object.__getattribute__(self, '_name')} does not exist yet: {exc}", pytrace=False)

    @property
    def __dict__(self):  # pytest >= 9.2 monkeypatch reads the old value from target.__dict__: it must be the real module's
        return self._real().__dict__

    def __getattr__(self, item):
        if item.startswith("__") or item == "pytestmark":  # pytest probes every module-level name while collecting
            raise AttributeError(item)
        return getattr(self._real(), item)

    def __setattr__(self, key, value):
        setattr(self._real(), key, value)

    def __delattr__(self, key):
        delattr(self._real(), key)


hostos = _Lazy("simplicio_video.hostos")
distribution = _Lazy("simplicio_video.distribution")
update_cmd = _Lazy("simplicio_video.commands.update")
doctor_cmd = _Lazy("simplicio_video.commands.doctor")
install_cmd = _Lazy("simplicio_video.commands.install")
installer = _Lazy("simplicio_video.installer")
skill_sync = _Lazy("simplicio_video.skill_sync")


def nega_acesso(monkeypatch, *pastas: Path) -> None:
    """Simulate folders this user cannot search: a PATH folder with mode 0000, or a 0700 folder that another user owns.

    Anything STRICTLY inside them raises PermissionError (stat, lstat, open, os.open, scandir, listdir, mkdir, unlink) and
    `os.access` says no; the folder itself can still be stat'ed (that only needs its parent) but not listed. A real chmod
    would do nothing here: root, who runs this suite in some environments, ignores modes. Only this process is affected
    (a child process, like the fake Runtime, still sees the real files).
    """
    bases = [os.path.abspath(str(p)) for p in pastas]

    def texto(caminho) -> str | None:
        try:
            valor = os.fspath(caminho)
        except TypeError:  # a file descriptor
            return None
        return os.path.abspath(os.fsdecode(valor))

    def dentro(caminho) -> bool:
        alvo = texto(caminho)
        return alvo is not None and any(alvo.startswith(base + os.sep) for base in bases)

    def dentro_ou_igual(caminho) -> bool:
        alvo = texto(caminho)
        return alvo is not None and (dentro(caminho) or alvo in bases)

    def nega(nome: str, ate_a_propria_pasta: bool = False):
        real = getattr(os, nome)

        def wrapper(caminho, *a, **kw):
            if (dentro_ou_igual if ate_a_propria_pasta else dentro)(caminho):
                raise PermissionError(13, "Permission denied", os.fspath(caminho))
            return real(caminho, *a, **kw)

        monkeypatch.setattr(os, nome, wrapper)

    for nome in ("stat", "lstat", "open", "mkdir", "unlink", "remove"):
        nega(nome)
    for nome in ("scandir", "listdir"):
        nega(nome, ate_a_propria_pasta=True)
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda caminho, *a, **kw: False if dentro(caminho) else real_access(caminho, *a, **kw))
    import builtins
    import io

    for modulo in (builtins, io):
        real_open = modulo.open

        def abre(arquivo, *a, _real=real_open, **kw):
            if not isinstance(arquivo, int) and dentro(arquivo):
                raise PermissionError(13, "Permission denied", os.fspath(arquivo))
            return _real(arquivo, *a, **kw)

        monkeypatch.setattr(modulo, "open", abre)


def roda(argv: list[str], capsys, main=None) -> tuple[int, str, str]:
    """main(argv) in process: (rc, stdout, stderr). Any exception that is not a SystemExit FAILS the test: that is a traceback."""
    if main is None:
        from simplicio_video.cli import main
    try:
        rc = main(argv)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    except Exception as e:  # noqa: BLE001 - the whole point: nothing may escape a command
        pytest.fail(f"`simplicio-video {' '.join(argv)}` raised {type(e).__name__}: {str(e)[:200]}", pytrace=False)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def roda_com_prazo(funcao, prazo: float = 3.0, destravar=None):
    """funcao() in a thread: its result, or its exception, or a test FAILURE if it is still running after `prazo` seconds.

    For code that could block forever on a FIFO. `destravar` is called when the deadline passes, to free the stuck thread (and
    let the test process exit): for a FIFO, open it for writing without blocking."""
    resultado: dict = {}

    def alvo():
        try:
            resultado["valor"] = funcao()
        except BaseException as exc:  # noqa: BLE001 - handed back to the caller below
            resultado["erro"] = exc

    fio = threading.Thread(target=alvo, daemon=True)
    fio.start()
    fio.join(prazo)
    if fio.is_alive():
        if destravar is not None:
            destravar()
        fio.join(2)
        pytest.fail(f"still blocked after {prazo} s: a FIFO (or another file that never ends) was opened and read", pytrace=False)
    if "erro" in resultado:
        raise resultado["erro"]
    return resultado.get("valor")


def solta_fifo(caminho) -> None:
    """Frees a thread that is blocked opening the FIFO `caminho` for reading."""
    try:
        os.close(os.open(caminho, os.O_WRONLY | os.O_NONBLOCK))
    except OSError:
        pass


def assert_no_secret(*channels: str) -> None:
    for text in channels:
        for secret in LEAKY_ENV.values():
            assert secret not in text, f"{secret!r} leaked"


_FAKE_RUNTIME_PY = r'''
import json, os, sys

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "fake_simplicio.json"), encoding="utf-8") as handle:
    version = json.load(handle)["version"]
if sys.argv[1:2] == ["--version"]:
    print("simplicio " + version)
    print("executable: " + sys.argv[0])
    print("component: runtime-kernel " + version)
    sys.exit(0)
sys.exit(2)
'''


def write_fake_runtime(directory: Path, *, version: str = "3.10.0", launcher_name: str = "simplicio") -> Path:
    """A `simplicio` for tests: it answers `--version` and nothing else.

    The launcher uses the absolute path of this interpreter, so the child needs nothing on PATH.
    `launcher_name` only matters on POSIX (on real Windows the launcher is always simplicio.cmd)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "fake_simplicio.py").write_text(_FAKE_RUNTIME_PY, encoding="utf-8")
    (directory / "fake_simplicio.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    script = str(directory / "fake_simplicio.py")
    if REAL_WINDOWS:
        launcher = directory / "simplicio.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return launcher
    launcher = directory / launcher_name  # a simulated-Windows test on POSIX asks for `simplicio.exe`
    launcher.write_text(f"#!/bin/sh\nexec '{sys.executable}' '{script}' \"$@\"\n", encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


_FAKE_TOOL_PY = r"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
name = os.path.basename(__file__)[len("fake_"):-len(".py")]
with open(os.path.join(here, name + ".argv"), "a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\n")
with open(os.path.join(here, name + ".out"), encoding="utf-8") as handle:
    sys.stdout.write(handle.read())
with open(os.path.join(here, name + ".rc"), encoding="utf-8") as handle:
    sys.exit(int(handle.read()))
"""


def write_fake_tool(directory: Path, nome: str, saida: str, *, rc: int = 0, ext: str | None = None) -> Path:
    """A fake `node`, `ffmpeg`, `npm`... : prints `saida`, exits with `rc`, appends its arguments to `<nome>.argv`.

    On Windows the launcher is a .cmd (or `ext`), elsewhere an executable script; `ext` forces the file name for the
    simulated-Windows tests (`node.exe`, `npm.cmd`) on a POSIX host, where it is a shell script named that way."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"fake_{nome}.py").write_text(_FAKE_TOOL_PY, encoding="utf-8")
    (directory / f"{nome}.out").write_text(saida, encoding="utf-8")
    (directory / f"{nome}.rc").write_text(str(rc), encoding="utf-8")
    script = str(directory / f"fake_{nome}.py")
    if REAL_WINDOWS:
        launcher = directory / f"{nome}.cmd"  # a real Windows cannot run a script named .exe: `ext` is ignored here
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return launcher
    launcher = directory / f"{nome}{ext or ''}"
    launcher.write_text(f"#!/bin/sh\nexec '{sys.executable}' '{script}' \"$@\"\n", encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


_FAKE_UV_PY = r"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(here, "uv.argv"), "a", encoding="utf-8") as handle:
    handle.write("\t".join(args) + "\n")
print("uv fake: " + " ".join(args))
if args[:1] == ["venv"]:
    venv = os.path.abspath(args[-1])
    os.makedirs(venv, exist_ok=True)
    version = args[args.index("--python") + 1] if "--python" in args else "3.12"
    with open(os.path.join(venv, "pyvenv.cfg"), "w", encoding="utf-8") as handle:
        handle.write("home = /fake\nversion_info = " + version + ".4\n")
    os.makedirs(os.path.join(venv, "bin"), exist_ok=True)  # the CLI the dev install runs `doctor` with at the end
    stub = os.path.join(venv, "bin", "simplicio-video")
    with open(stub, "w", encoding="utf-8") as handle:
        handle.write('#!/bin/sh\necho "$@" >> "$(dirname "$0")/../doctor.log"\n'
                     'exit $(cat "$(dirname "$0")/../doctor.rc" 2>/dev/null || echo 0)\n')
    os.chmod(stub, 0o755)
sys.exit(0)
"""


def write_fake_uv(directory: Path, launcher_name: str = "uv") -> Path:
    """A `uv` that records every call (tab separated) in `uv.argv`; `uv venv` creates a .venv with a pyvenv.cfg.

    `launcher_name` only matters on POSIX (a simulated-Windows test asks for `uv.exe`)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "fake_uv.py").write_text(_FAKE_UV_PY, encoding="utf-8")
    script = str(directory / "fake_uv.py")
    if REAL_WINDOWS:
        launcher = directory / "uv.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return launcher
    launcher = directory / launcher_name
    launcher.write_text(f"#!/bin/sh\nexec '{sys.executable}' '{script}' \"$@\"\n", encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


def write_git_launcher(directory: Path) -> Path:
    """A `git` on the sealed PATH that runs the REAL git, so the update tests can use real repositories under tmp_path.

    Only git is let through: the sealed PATH still has no `simplicio`, no gh, no node."""
    real = shutil.which("git", path=REAL_PATH)
    if real is None:
        pytest.skip("git is not installed on this machine")
    directory.mkdir(parents=True, exist_ok=True)
    if REAL_WINDOWS:
        launcher = directory / "git.cmd"
        launcher.write_text(f'@"{real}" %*\r\n', encoding="utf-8")
        return launcher
    launcher = directory / "git"
    launcher.write_text(f"#!/bin/sh\nexec '{real}' \"$@\"\n", encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


def chamadas_do_uv(directory: Path) -> list[list[str]]:
    arq = directory / "uv.argv"
    return [linha.split("\t") for linha in arq.read_text(encoding="utf-8").splitlines()] if arq.exists() else []


def _guard_runtime(monkeypatch, root: Path) -> None:
    """Tripwire: nothing named `simplicio` may be started unless it is a file under `root` (the tmp folder of the test)."""
    real_init = subprocess.Popen.__init__
    base = root.resolve()

    def guarded(self, args, *a, **kw):
        argv = list(args) if isinstance(args, (list, tuple)) else [str(args)]
        first = str(argv[0]) if argv else ""
        name = Path(first).name.lower()
        stem = name[:-4] if name.endswith((".exe", ".cmd", ".bat")) else name
        if stem == "simplicio":
            inside = (os.sep in first or "/" in first) and base in Path(first).resolve().parents
            if not inside:
                raise AssertionError(f"the test tried to start a Runtime outside tmp_path: {first!r}")
        return real_init(self, args, *a, **kw)

    monkeypatch.setattr(subprocess.Popen, "__init__", guarded)


@pytest.fixture
def caixa(tmp_path, monkeypatch):
    """HOME, USERPROFILE and PATH sealed under tmp_path; env of other programs cleared; real Runtime unreachable."""
    home = tmp_path / "home"
    home.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", str(tmp_path / "workspace"))
    for name in CLEARED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _guard_runtime(monkeypatch, tmp_path)
    # Sockets are blocked in the tests: the doctor's port check is replaced by a function that says "free" (as in `saude`).
    monkeypatch.setattr(doctor_cmd, "porta_livre", lambda porta, *a, **kw: True)
    box = SimpleNamespace(home=home, bin=bindir, tmp=tmp_path, data=tmp_path / "data", workspace=tmp_path / "workspace")
    box.runtime = lambda **kw: write_fake_runtime(bindir, **kw)
    return box


@pytest.fixture
def simula_so(monkeypatch):
    """simula_so("win32"): the code under test sees that system (sys.platform and platform.system), nothing else changes.

    os.name stays real on purpose: pathlib picks WindowsPath or PosixPath from it, and a fake `nt` on Linux breaks every Path()."""
    import platform

    def troca(nome: str) -> str:
        assert nome in SISTEMAS
        monkeypatch.setattr(sys, "platform", nome)
        monkeypatch.setattr(platform, "system", lambda: {"linux": "Linux", "darwin": "Darwin", "win32": "Windows"}[nome])
        return nome

    return troca


def saida_cp1252(*textos: str) -> None:
    """The Windows console of many installs is cp1252: an output it cannot encode would crash there."""
    for texto in textos:
        try:
            texto.encode("cp1252")
        except UnicodeEncodeError as exc:
            pytest.fail(f"output not encodable in cp1252: {exc}")




GB = 1024**3
SENTINELA = "segredo-sentinela-nao-pode-aparecer-na-saida"
FFMPEG_COM_LIBASS = (
    "ffmpeg version 7.0.2 Copyright (c) 2000-2024 the FFmpeg developers\n"
    "configuration: --enable-gpl --enable-version3 --enable-libass --enable-libx264\n"
)
FFMPEG_SEM_LIBASS = (
    "ffmpeg version 7.0.2 Copyright (c) 2000-2024 the FFmpeg developers\n"
    "configuration: --enable-gpl --enable-version3 --enable-libx264\n"
)


@pytest.fixture
def saude(caixa, monkeypatch):
    """A healthy environment: ffmpeg with libass, node 22, 50 GB free, GEMINI_API_KEY set, workspace created."""
    st = SimpleNamespace(livre_gb=50.0, medidos=[], caixa=caixa)
    write_fake_tool(caixa.bin, "node", "v22.11.0\n")
    write_fake_tool(caixa.bin, "ffmpeg", FFMPEG_COM_LIBASS)

    def disk_usage(caminho):
        st.medidos.append(str(caminho))
        return SimpleNamespace(total=100 * GB, used=int((100 - st.livre_gb) * GB), free=int(st.livre_gb * GB))

    monkeypatch.setattr(shutil, "disk_usage", disk_usage)
    # Sockets are blocked in the tests: the port check is replaced by a function that says "free".
    monkeypatch.setattr(doctor_cmd, "porta_livre", lambda porta, *a, **kw: True)
    monkeypatch.setattr(distribution, "kind", lambda **kw: "source")
    monkeypatch.setattr(doctor_cmd, "python_version", lambda: (3, 12, 4))  # the suite runs on any Python
    monkeypatch.setenv("GEMINI_API_KEY", SENTINELA)
    caixa.workspace.mkdir(parents=True)
    (caixa.workspace / "workspace.yaml").write_text(yaml.safe_dump(
        {"schema": "simplicio.workspace/v1", "workspace": "factory/v1", "language": "pt-BR",
         "settings": {"theme": "br", "ui_language": "pt-BR"}}), encoding="utf8")
    (caixa.workspace / "policy.yaml").write_text(yaml.safe_dump(
        {"schema": "simplicio.policy/v1", "autonomy": {"default": "L1"},
         "budgets": {"llm_tokens": 0, "llm_usd": 0, "media_credits": 0}}), encoding="utf8")
    return st



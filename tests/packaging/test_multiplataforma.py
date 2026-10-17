"""Linux, macOS and Windows: no hidden POSIX assumption in the install, update, doctor and login code.

This suite runs on Linux in the gate and simulates the three systems (`simula_so`: sys.platform and platform.system; os.name
stays real, because pathlib breaks with a fake `nt`). The path logic is checked with PureWindowsPath and PurePosixPath, the
Windows lock with a fake msvcrt (see test_auth_store.py), and tests that need real POSIX files are marked `posix_real`, so
the SAME suite also runs on a real Windows or macOS machine without failing for nothing.

What is NOT proven here: that Windows and macOS really behave like these simulations. That is `scripts/smoke_so.py`, which
someone has to run on those systems (docs/how-to/testar-em-windows-e-macos.md). Until then they are UNVERIFIED.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

import _caixa
from _caixa import SISTEMAS, hostos, saida_cp1252
from _comum import executa, exige_registrado
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
simula_so = _caixa.simula_so


@pytest.mark.parametrize("so,esperado", [("linux", "linux"), ("darwin", "darwin"), ("win32", "win32")])
def test_o_sistema_vem_de_sys_platform_lido_na_hora(simula_so, so, esperado):
    simula_so(so)
    assert hostos.system() == esperado
    assert hostos.is_windows() == (so == "win32") and hostos.is_macos() == (so == "darwin")


def test_cygwin_e_posix(monkeypatch):
    monkeypatch.setattr("sys.platform", "cygwin")
    assert hostos.system() == "linux" and not hostos.is_windows()


@pytest.mark.parametrize("so,sufixo", [("linux", ""), ("darwin", ""), ("win32", ".exe")])
def test_nome_do_executavel(simula_so, so, sufixo):
    simula_so(so)
    assert hostos.exe_name("simplicio") == "simplicio" + sufixo


# --- where Homebrew puts the tools -------------------------------------------------------------------------------------


def test_o_homebrew_so_entra_no_macos(simula_so):
    simula_so("darwin")
    assert hostos.extra_tool_dirs() == ["/opt/homebrew/bin", "/usr/local/bin"]
    for so in ("linux", "win32"):
        simula_so(so)
        assert hostos.extra_tool_dirs() == []


@pytest.mark.parametrize("ferramenta,so,trecho", [
    ("ffmpeg", "linux", "apt install ffmpeg"),
    ("ffmpeg", "darwin", "brew install ffmpeg"),
    ("ffmpeg", "win32", "winget install Gyan.FFmpeg"),
    ("node", "darwin", "nvm install 22"),
    ("node", "linux", "nvm install 22"),
])
def test_a_dica_de_instalacao_e_a_do_sistema(ferramenta, so, trecho):
    assert trecho in hostos.hint(ferramenta, so)


def test_a_dica_do_node_no_windows_nao_manda_usar_nvm_do_posix():
    dica = hostos.hint("node", "win32")
    assert "22" in dica and "nvm install 22" not in dica


# --- finding a program: PATH, PATHEXT, never the current directory ---------------------------------------------------------


def _exe(pasta: Path, nome: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / nome
    arq.write_text("x")
    arq.chmod(0o755)
    return arq


def test_which_acha_no_path_e_so_arquivo_executavel(tmp_path, simula_so):
    simula_so("linux")
    pronto = _exe(tmp_path / "a", "ferramenta")
    sem_x = tmp_path / "b" / "outra"
    sem_x.parent.mkdir()
    sem_x.write_text("x")
    sem_x.chmod(0o644)
    caminho = os.pathsep.join([str(tmp_path / "b"), str(tmp_path / "a")])
    assert hostos.which("ferramenta", caminho) == pronto
    if not os.access(sem_x, os.X_OK):  # a real Windows has no exec bit: every file passes
        assert hostos.which("outra", caminho) is None


@pytest.mark.parametrize("so", SISTEMAS)
def test_which_ignora_entrada_vazia_ponto_e_o_diretorio_atual(tmp_path, monkeypatch, simula_so, so):
    simula_so(so)
    cwd = tmp_path / "cwd"
    for nome in ("alvo", "alvo.exe", "alvo.cmd"):
        _exe(cwd, nome)
    monkeypatch.chdir(cwd)
    assert hostos.which("alvo", os.pathsep.join(["", ".", str(tmp_path / "vazio")])) is None
    assert hostos.which("alvo", "") is None and hostos.which("alvo", None) is None


def test_which_no_windows_tenta_as_extensoes_do_pathext(tmp_path, simula_so, monkeypatch):
    simula_so("win32")
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.CMD")
    cmd = _exe(tmp_path / "bin", "ferramenta.cmd")
    assert hostos.which("ferramenta", str(tmp_path / "bin")) == cmd
    assert hostos.which("ferramenta.cmd", str(tmp_path / "bin")) == cmd
    exe = _exe(tmp_path / "bin2", "ferramenta.exe")
    assert hostos.which("ferramenta", str(tmp_path / "bin2")) == exe


def test_which_no_windows_nao_acha_um_arquivo_sem_extensao(tmp_path, simula_so):
    simula_so("win32")
    _exe(tmp_path / "bin", "ferramenta")
    assert hostos.which("ferramenta", str(tmp_path / "bin")) is None, "a file without extension does not run on Windows"


def test_which_no_posix_nao_acrescenta_extensao(tmp_path, simula_so):
    simula_so("linux")
    _exe(tmp_path / "bin", "ferramenta.exe")
    assert hostos.which("ferramenta", str(tmp_path / "bin")) is None


def test_find_tool_olha_o_path_e_depois_os_diretorios_extras(tmp_path, simula_so, monkeypatch):
    simula_so("darwin")
    extra = tmp_path / "opt" / "homebrew" / "bin"
    achado = _exe(extra, "ferramenta")
    monkeypatch.setattr(hostos, "EXTRA_TOOL_DIRS", {"darwin": [str(extra)]})
    assert hostos.find_tool("ferramenta", {"PATH": str(tmp_path / "vazio")}) == str(achado)
    no_path = _exe(tmp_path / "bin", "ferramenta")
    assert hostos.find_tool("ferramenta", {"PATH": str(tmp_path / "bin")}) == str(no_path)
    simula_so("linux")
    assert hostos.find_tool("ferramenta", {"PATH": str(tmp_path / "vazio")}) is None


# --- the output must survive a Windows console --------------------------------------------------------------------------


@pytest.mark.parametrize("so", SISTEMAS)
@pytest.mark.parametrize("argv", [["auth", "status"], ["login"], ["logout"], ["logout", "--yes"], ["doctor", "login"],
                                  ["install", "--dry-run"]])
def test_a_saida_dos_comandos_cabe_no_cp1252(caixa, capsys, simula_so, monkeypatch, so, argv):
    simula_so(so)
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(caixa.tmp))
    exige_registrado(argv[0], capsys, main)
    if argv[0] == "install":
        argv = [*argv, "--target", str(caixa.tmp / "alvo")]
    rc, out, err = executa(argv, capsys, main)
    assert out.strip(), f"{argv} printed nothing"
    saida_cp1252(out, err)


@pytest.mark.parametrize("so", SISTEMAS)
def test_os_comandos_nao_tem_traceback_em_nenhum_sistema(caixa, capsys, simula_so, monkeypatch, so):
    simula_so(so)
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(caixa.tmp))
    for argv in (["auth", "status", "--json"], ["login", "--json"], ["logout", "--json"], ["doctor", "login", "--json"],
                 ["install", "--check", "--json"]):
        exige_registrado(argv[0], capsys, main)
        if argv[0] == "install":
            argv = [*argv, "--target", str(caixa.tmp / "alvo")]
        rc, out, err = executa(argv, capsys, main)
        assert "Traceback" not in out + err, (argv, err)
        json.loads(out)  # one JSON document, whatever the system


# --- PATHEXT comes from the environment that was passed in --------------------------------------------------------------------


def test_pathext_vem_do_ambiente_passado_e_nao_do_os_environ_global(tmp_path, simula_so, monkeypatch):
    simula_so("win32")
    monkeypatch.setenv("PATHEXT", ".CMD")  # the process's own: it must not decide what an injected environment can run
    pasta = tmp_path / "bin"
    foo = _exe(pasta, "ferramenta.foo")
    cmd = _exe(pasta, "outra.cmd")
    env = {"PATH": str(pasta), "PATHEXT": ".FOO;.EXE"}
    assert hostos.which("ferramenta", str(pasta), env) == foo
    assert hostos.which("outra", str(pasta), env) is None, ".CMD is not in the PATHEXT that was passed in"
    assert hostos.find_tool("ferramenta", env) == str(foo) and hostos.find_tool("outra", env) is None
    # an environment WITHOUT PATHEXT gets the default list, not the process's one
    monkeypatch.setenv("PATHEXT", ".FOO")
    assert hostos.which("outra", str(pasta), {"PATH": str(pasta)}) == cmd
    assert hostos.which("ferramenta", str(pasta), {"PATH": str(pasta)}) is None


def test_o_runtime_e_achado_com_o_pathext_do_ambiente_passado(tmp_path, simula_so, monkeypatch):
    simula_so("win32")
    monkeypatch.setenv("PATHEXT", ".EXE")
    pasta = tmp_path / "bin"
    foo = _exe(pasta, "simplicio.foo")
    env = {"HOME": str(tmp_path / "home"), "PATH": str(pasta), "PATHEXT": ".FOO"}
    assert _caixa.auth.runtime_binary(env) == foo
    assert _caixa.auth.runtime_binary({**env, "PATHEXT": ".EXE"}) is None


# --- Windows: every text read and every text subprocess names its encoding ------------------------------------------------------


FONTES_DE_OPERACAO = ["auth.py", "hostos.py", "distribution.py", "paths.py", "installer.py", "skill_sync.py", "commands/install.py",
                      "commands/update.py", "commands/doctor.py", "commands/login.py", "commands/setup.py"]
CHAMADAS_DE_SUBPROCESSO = {"run", "call", "check_output", "check_call", "Popen"}


def _quem_chama(chamada: ast.Call) -> tuple[str | None, str, bool]:
    """(the name it is called on, the function name, whether it is an attribute call). `x.y.open()` is called on None."""
    f = chamada.func
    if isinstance(f, ast.Attribute):
        return (f.value.id if isinstance(f.value, ast.Name) else None), f.attr, True
    return None, f.id if isinstance(f, ast.Name) else "", False


def _e_binario(chamada: ast.Call, dono: str | None, atributo: bool) -> bool:
    """The mode is the 2nd argument of open(file, mode), io.open and os.fdopen(fd, mode), but the 1st of `path.open(mode)`."""
    posicao = 0 if (atributo and chamada.func.attr == "open" and dono != "io") else 1
    modo = chamada.args[posicao] if len(chamada.args) > posicao else next((k.value for k in chamada.keywords if k.arg == "mode"), None)
    return isinstance(modo, ast.Constant) and isinstance(modo.value, str) and "b" in modo.value


# `.open()` that is not a file: os.open (a descriptor) and the urllib opener of update.py
NAO_ABRE_ARQUIVO = {"os", "_OPENER"}


def problemas_de_encoding(codigo: str, onde: str) -> list[str]:
    problemas = []
    for chamada in (n for n in ast.walk(ast.parse(codigo)) if isinstance(n, ast.Call)):
        dono, nome, atributo = _quem_chama(chamada)
        kw = {k.arg: k.value for k in chamada.keywords}
        local = f"{onde}:{chamada.lineno}"
        if nome == "read_text" and not chamada.args and "encoding" not in kw:
            problemas.append(f"{local} read_text() without encoding")
        if nome == "write_text" and len(chamada.args) < 2 and "encoding" not in kw:
            problemas.append(f"{local} write_text() without encoding")
        # builtin open(), io.open() and EVERY `x.open()` (a Path, `self.p.open`...) except os.open and the urllib opener
        abre_arquivo = (nome == "open" and (not atributo or dono not in NAO_ABRE_ARQUIVO)) or nome == "fdopen"
        if abre_arquivo and not _e_binario(chamada, dono, atributo) and "encoding" not in kw:
            problemas.append(f"{local} {nome}() in text mode without encoding")
        if dono == "subprocess" and nome in CHAMADAS_DE_SUBPROCESSO:
            texto = any(isinstance(kw.get(k), ast.Constant) and kw[k].value is True for k in ("text", "universal_newlines"))
            if texto and not ("encoding" in kw and "errors" in kw):
                problemas.append(f"{local} subprocess.{nome}(text=True) without encoding= and errors=")
    return problemas


def test_toda_leitura_de_texto_e_todo_subprocesso_de_texto_tem_encoding_explicito():
    """The Windows default is the console codec (cp1252): the `Í` of the CHANGELOG (bytes C3 8D) or an accent in git's output
    would raise UnicodeDecodeError there, while UTF-8 on Linux hides it. So: `encoding=` on every text open and read_text and
    write_text, and `encoding="utf-8", errors="replace"` on every subprocess that is read as text."""
    from _comum import ROOT
    fontes = [ROOT / "src" / "simplicio_video" / nome for nome in FONTES_DE_OPERACAO] + [ROOT / "scripts" / "smoke_so.py"]
    problemas = [p for arquivo in fontes for p in problemas_de_encoding(arquivo.read_text(encoding="utf-8"), arquivo.name)]
    assert problemas == [], "\n".join(problemas)


@pytest.mark.parametrize("codigo", [
    "def f(path):\n    return path.open()\n",
    "def f(path):\n    with path.open('r') as h:\n        return h.read()\n",
    "def f(self):\n    return self.p.open()\n",
    "def f(p):\n    return (p / 'x').open('w')\n",
    "def f():\n    return open('x')\n",
    "def f():\n    return io.open('x')\n",
    "def f(fd):\n    return os.fdopen(fd)\n",
    "def f(p):\n    return p.read_text()\n",
    "def f(p):\n    return p.write_text('x')\n",
    "def f():\n    return subprocess.run(['x'], text=True)\n",
    "def f():\n    return subprocess.run(['x'], text=True, encoding='utf-8')\n",
    "def f():\n    return subprocess.check_output(['x'], universal_newlines=True)\n",
])
def test_o_verificador_de_encoding_pega_cada_forma_de_leitura_de_texto_sem_encoding(codigo):
    """The check must catch each form (a mutation `path.open()` without encoding passed once): a mutant of the check itself."""
    assert problemas_de_encoding(codigo, "x.py"), codigo


@pytest.mark.parametrize("codigo", [
    "def f(path):\n    return path.open(encoding='utf-8')\n",
    "def f(path):\n    return path.open('rb')\n",
    "def f(path):\n    return path.open(mode='wb')\n",
    "def f():\n    return open('x', 'rb')\n",
    "def f():\n    return open('x', encoding='utf-8')\n",
    "def f(p, flags):\n    return os.open(p, flags)\n",
    "def f(url):\n    return _OPENER.open(url, timeout=1)\n",
    "def f(fd):\n    return os.fdopen(fd, 'w', encoding='utf-8')\n",
    "def f(p):\n    return p.read_text(encoding='utf-8')\n",
    "def f():\n    return subprocess.run(['x'], capture_output=True)\n",
    "def f():\n    return subprocess.run(['x'], text=True, encoding='utf-8', errors='replace')\n",
])
def test_o_verificador_de_encoding_nao_acusa_o_que_esta_certo_nem_o_que_nao_e_arquivo(codigo):
    assert problemas_de_encoding(codigo, "x.py") == [], codigo


# --- the folders of every host, the same relative to the home on the three systems -------------------------------------------------


@pytest.mark.parametrize("so", SISTEMAS)
def test_as_pastas_de_cada_host_ficam_sob_o_home_em_todo_sistema(caixa, simula_so, so):
    """The loop keeps one table of host skill folders under the home (skill_sync.HOST_SKILL_ROOTS) and uses it on Linux, macOS and
    Windows alike: pathlib joins them with the right separator. They are never anchored anywhere else (no APPDATA, no /Library)."""
    simula_so(so)
    tabela = _caixa.skill_sync.HOST_SKILL_ROOTS
    assert len(tabela) == 11
    for host, relativo in tabela.items():
        assert not PurePosixPath(relativo).is_absolute() and ".." not in PurePosixPath(relativo).parts, host
        assert not PureWindowsPath(relativo).drive and not PureWindowsPath(relativo).root, host
        assert "\\" not in relativo, f"{host}: the table uses `/`, pathlib converts it"
    raiz = PureWindowsPath(r"C:\Users\Maria Souza")
    assert str(raiz.joinpath(*PurePosixPath(tabela["codex"]).parts)) == r"C:\Users\Maria Souza\.codex\skills"
    assert str(raiz.joinpath(*PurePosixPath(tabela["opencode"]).parts)) == r"C:\Users\Maria Souza\.config\opencode\skills"

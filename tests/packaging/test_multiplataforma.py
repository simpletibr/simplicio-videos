"""Linux, macOS and Windows: no hidden POSIX assumption in the install, update, doctor and login code.

This suite runs on Linux in the gate and simulates the three systems (`simula_so`: sys.platform and platform.system; os.name
stays real, because pathlib breaks with a fake `nt`). The path logic is checked with PureWindowsPath and PurePosixPath, the
Windows lock with a fake msvcrt (see test_auth_store.py), and tests that need real POSIX files are marked `posix_real`, so
the SAME suite also runs on a real Windows or macOS machine without failing for nothing.

What is NOT proven here: that Windows and macOS really behave like these simulations. That is `scripts/smoke_so.py`, which
someone has to run on those systems (docs/how-to/testar-em-windows-e-macos.md). Until then they are UNVERIFIED.
"""
from __future__ import annotations

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


# --- the python of the venv --------------------------------------------------------------------------------------------


def test_python_do_venv_no_windows_usa_scripts_e_exe():
    venv = PureWindowsPath(r"C:\Users\Maria Souza\proj\.venv")
    assert str(hostos.venv_python(venv, "win32")) == r"C:\Users\Maria Souza\proj\.venv\Scripts\python.exe"


@pytest.mark.parametrize("so", ["linux", "darwin"])
def test_python_do_venv_no_posix_usa_bin_python(so):
    venv = PurePosixPath("/home/maria/proj/.venv")
    assert str(hostos.venv_python(venv, so)) == "/home/maria/proj/.venv/bin/python"


def test_python_do_venv_sem_sistema_explicito_usa_o_atual(simula_so):
    simula_so("win32")
    assert hostos.venv_python(Path("x") / ".venv").parts[-2:] == ("Scripts", "python.exe")
    simula_so("linux")
    assert hostos.venv_python(Path("x") / ".venv").parts[-2:] == ("bin", "python")


# --- where uv, node and ffmpeg live -------------------------------------------------------------------------------------


def test_uv_no_linux_usa_local_bin_e_cargo_bin_e_nada_de_homebrew():
    casa = PurePosixPath("/home/maria")
    assert [str(p) for p in hostos.uv_candidates(casa, {}, "linux")] == ["/home/maria/.local/bin/uv", "/home/maria/.cargo/bin/uv"]


def test_uv_no_macos_inclui_os_dois_prefixos_do_homebrew():
    casa = PurePosixPath("/Users/maria")
    achados = [str(p) for p in hostos.uv_candidates(casa, {}, "darwin")]
    assert achados[:2] == ["/Users/maria/.local/bin/uv", "/Users/maria/.cargo/bin/uv"]
    assert "/opt/homebrew/bin/uv" in achados and "/usr/local/bin/uv" in achados


def test_uv_no_windows_e_uv_exe_em_local_bin_e_cargo_bin_do_userprofile():
    casa = PureWindowsPath(r"C:\Users\Maria")
    achados = [str(p) for p in hostos.uv_candidates(casa, {}, "win32")]
    assert achados == [r"C:\Users\Maria\.local\bin\uv.exe", r"C:\Users\Maria\.cargo\bin\uv.exe"]


def test_o_homebrew_so_entra_no_macos(simula_so):
    simula_so("darwin")
    assert hostos.extra_tool_dirs() == ["/opt/homebrew/bin", "/usr/local/bin"]
    for so in ("linux", "win32"):
        simula_so(so)
        assert hostos.extra_tool_dirs() == []


@pytest.mark.parametrize("ferramenta,so,trecho", [
    ("uv", "linux", "curl -LsSf https://astral.sh/uv/install.sh | sh"),
    ("uv", "darwin", "brew install uv"),
    ("uv", "win32", "irm https://astral.sh/uv/install.ps1 | iex"),
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


def test_find_uv_acha_o_do_home_quando_nao_esta_no_path(caixa, simula_so):
    simula_so("linux")
    achado = _exe(caixa.home / ".cargo" / "bin", "uv")
    assert hostos.find_uv({"HOME": str(caixa.home), "PATH": ""}) == str(achado)
    assert hostos.find_uv({"HOME": str(caixa.tmp / "outro"), "PATH": ""}) is None


# --- the output must survive a Windows console --------------------------------------------------------------------------


@pytest.mark.parametrize("so", SISTEMAS)
@pytest.mark.parametrize("argv", [["auth", "status"], ["login"], ["logout"], ["logout", "--yes"], ["doctor", "login"],
                                  ["install", "--dry-run"]])
def test_a_saida_dos_comandos_cabe_no_cp1252(caixa, capsys, simula_so, monkeypatch, so, argv):
    simula_so(so)
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(caixa.tmp))
    exige_registrado(argv[0], capsys, main)
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
        rc, out, err = executa(argv, capsys, main)
        assert "Traceback" not in out + err, (argv, err)
        json.loads(out)  # one JSON document, whatever the system

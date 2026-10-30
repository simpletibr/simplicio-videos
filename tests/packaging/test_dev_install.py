"""Contract of `scripts/dev_install.sh` (Linux, macOS) and `scripts/dev_install.ps1` (Windows), and of the two thin wrappers
`./install.sh` and `./install.ps1` at the root.

Breaking change (direct owner request: "faz igual ao simplicio-loop"): the `.venv` of the checkout used to be `simplicio-video
install` (and `./install.sh` called it). Now `simplicio-video install` copies the skill into the agent host, like the loop, and
the development environment is `scripts/dev_install.sh`, exactly as the loop has one (`bash scripts/dev_install.sh`). It keeps what
the old install did: Node 22 or newer, ffmpeg with libass and 5 GB free (nothing installed in the system), `uv` (offered, only
with a yes), the `.venv` with the Python asked for (3.12), the package editable with the extras, the `web/` build when `web/`
exists, `doctor` at the end and the next steps. No sudo. It does not use the system python at all (so a python3 without PyYAML,
macOS with the Xcode tools, is no problem: bug B1 of the PR #116).

The shell script runs here for real, on fakes (`uv`, `node`, `ffmpeg`, `npm`) in a sealed PATH and HOME. The PowerShell script
can NOT run here (no PowerShell on Linux): it is checked statically and stays UNVERIFIED until someone runs it on Windows.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import _caixa
from _caixa import FFMPEG_COM_LIBASS, FFMPEG_SEM_LIBASS, chamadas_do_uv, posix_real, write_fake_tool, write_fake_uv
from _comum import ROOT, instantanea

caixa = _caixa.caixa

DEV_SH = ROOT / "scripts" / "dev_install.sh"
DEV_PS1 = ROOT / "scripts" / "dev_install.ps1"
WRAP_SH = ROOT / "install.sh"
WRAP_PS1 = ROOT / "install.ps1"
SISTEMA = "/usr/bin:/bin"  # bash, df, sed, awk and dirname live here; the fakes come first


@pytest.fixture
def copia(caixa):
    """A checkout in tmp_path with the scripts, the real pyproject.toml and plugin.json, and the sealed box around it."""
    repo = caixa.tmp / "checkout"
    (repo / "scripts").mkdir(parents=True)
    for origem, destino in ((DEV_SH, "scripts/dev_install.sh"), (DEV_PS1, "scripts/dev_install.ps1"), (WRAP_SH, "install.sh"),
                            (WRAP_PS1, "install.ps1")):
        if origem.is_file():
            shutil.copy2(origem, repo / destino)
    for nome in ("pyproject.toml", "plugin.json"):
        shutil.copy2(ROOT / nome, repo / nome)
    caixa.repo = repo
    return caixa


def roda(copia, *argv, script="scripts/dev_install.sh", path=None, entrada=None, extra_env=None):
    """`bash <script> ...` in the copy with HOME and PATH sealed (fakes first, then only the system tools)."""
    env = {"HOME": str(copia.home), "PATH": path or f"{copia.bin}:{SISTEMA}", "LANG": "C.UTF-8", **(extra_env or {})}
    return subprocess.run(["bash", script, *argv], cwd=copia.repo, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", input=entrada if entrada is not None else "", timeout=120)


def texto(feito):
    return feito.stdout + feito.stderr


def ferramentas_ok(copia):
    write_fake_tool(copia.bin, "node", "v22.11.0\n")
    write_fake_tool(copia.bin, "ffmpeg", FFMPEG_COM_LIBASS)
    return write_fake_uv(copia.bin)


def disco_suficiente(pasta):
    if shutil.disk_usage(pasta).free < 6 * 1024**3:
        pytest.skip("less than 5 GB free in the temporary folder: the script would refuse, as it should")


# --- the files ------------------------------------------------------------------------------------------------------------


def test_os_scripts_existem_e_os_de_shell_sao_executaveis():
    for arquivo in (DEV_SH, WRAP_SH):
        assert arquivo.is_file(), f"{arquivo.relative_to(ROOT)} não existe"
        assert os.access(arquivo, os.X_OK), f"{arquivo.relative_to(ROOT)} precisa ser executável"
    for arquivo in (DEV_PS1, WRAP_PS1):
        assert arquivo.is_file(), f"{arquivo.relative_to(ROOT)} não existe"


def test_gitattributes_fixa_o_fim_de_linha_dos_scripts_de_shell():
    """A Windows checkout with autocrlf would turn `#!/usr/bin/env bash\\r` into a script bash cannot run."""
    atributos = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\.sh\s+text\s+eol=lf\s*$", atributos, re.M)


@pytest.mark.parametrize("arquivo", [DEV_SH, WRAP_SH])
def test_shell_sem_sudo_e_com_sintaxe_bash_e_shellcheck(arquivo):
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if linha.lstrip().startswith("#"):
            continue
        assert not re.search(r"(^|[\s;&|(])sudo\s", linha), f"{arquivo.name} não pode usar sudo: {linha!r}"
    assert subprocess.run(["bash", "-n", str(arquivo)], capture_output=True, text=True).returncode == 0
    sc = shutil.which("shellcheck", path=str(Path(sys.executable).parent))
    if sc is None:
        pytest.skip("shellcheck não está no .venv (pacote shellcheck-py do extra test)")
    feito = subprocess.run([sc, "--shell=bash", str(arquivo)], capture_output=True, text=True)
    assert feito.returncode == 0, feito.stdout + feito.stderr


def test_o_gate_do_shellcheck_cobre_o_dev_install():
    """scripts/check.sh lints scripts/*.sh: the new script is in that folder, so it is gated without an edit."""
    assert DEV_SH.parent.name == "scripts" and DEV_SH.suffix == ".sh"


# --- the thin wrapper ---------------------------------------------------------------------------------------------------------


def test_install_sh_da_raiz_e_um_involucro_fino_que_chama_o_dev_install():
    linhas = [l for l in WRAP_SH.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]
    assert len(linhas) <= 12, "the wrapper must stay thin: the logic lives in scripts/dev_install.sh"
    corpo = "\n".join(linhas)
    assert "dev_install.sh" in corpo and "exec" in corpo and '"$@"' in corpo
    for logica in ("uv venv", "uv pip", "ffmpeg", "node --version", "df "):
        assert logica not in corpo, f"the wrapper has logic of the dev install: {logica!r}"


def test_o_involucro_passa_os_argumentos_e_funciona_de_outra_pasta(copia, tmp_path):
    feito = subprocess.run(["bash", str(copia.repo / "install.sh"), "--dry-run", "--python", "3.12", "--with", "mcp"],
                           cwd=tmp_path, env={"HOME": str(copia.home), "PATH": f"{copia.bin}:{SISTEMA}"}, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60)
    assert feito.returncode == 0, texto(feito)
    assert "mcp" in feito.stdout and "3.12" in feito.stdout and str(copia.repo) in feito.stdout


def test_o_involucro_e_o_script_dao_o_mesmo_plano(copia):
    a = roda(copia, "--dry-run", script="install.sh")
    b = roda(copia, "--dry-run")
    assert a.returncode == b.returncode == 0
    normaliza = lambda t: re.sub(r"(install|dev_install)\.sh", "SCRIPT", t)  # noqa: E731
    assert normaliza(a.stdout) == normaliza(b.stdout)


def test_o_help_do_involucro_e_o_do_dev_install(copia):
    feito = roda(copia, "--help", script="install.sh")
    assert feito.returncode == 0 and "--with" in feito.stdout and "--python" in feito.stdout and "--dry-run" in feito.stdout
    assert "simplicio-video install" in feito.stdout, "it points to the command that installs the skills in the agent"


# --- --dry-run -------------------------------------------------------------------------------------------------------------


def test_dry_run_lista_o_plano_completo(copia):
    feito = roda(copia, "--dry-run")
    saida, baixa = texto(feito), texto(feito).lower()
    assert feito.returncode == 0, saida
    assert "dry" in baixa, "o plano deveria dizer que é dry-run"
    for trecho in ("3.12", ".venv", "doctor", "web", "ffmpeg", "libass", "22"):
        assert trecho in baixa, f"plano sem '{trecho}':\n{saida}"
    assert re.search(r"\buv\b", baixa) and re.search(r"node\b", baixa) and re.search(r"5\s*GB", saida, re.IGNORECASE)


def test_dry_run_aceita_extras_e_python_e_mostra_o_alvo_do_uv(copia):
    feito = roda(copia, "--dry-run", "--with", "local-tts,mcp", "--python", "3.12")
    assert feito.returncode == 0, texto(feito)
    assert "local-tts" in feito.stdout and "mcp" in feito.stdout and ".[local-tts,mcp]" in feito.stdout


def test_dry_run_nao_cria_nada_e_nao_chama_o_uv(copia):
    write_fake_uv(copia.bin)
    antes = instantanea(copia.repo)
    feito = roda(copia, "--dry-run")
    assert feito.returncode == 0, texto(feito)
    assert instantanea(copia.repo) == antes and not (copia.repo / ".venv").exists()
    assert list(copia.home.iterdir()) == [] and chamadas_do_uv(copia.bin) == []


# --- the real run, on fakes ----------------------------------------------------------------------------------------------------


@posix_real
def test_instala_cria_o_venv_instala_editavel_roda_o_doctor_e_diz_os_proximos_passos(copia):
    ferramentas_ok(copia)
    disco_suficiente(copia.tmp)
    feito = roda(copia)
    assert feito.returncode == 0, texto(feito)
    chamadas = chamadas_do_uv(copia.bin)
    assert chamadas[0] == ["venv", "--python", "3.12", ".venv"]
    assert chamadas[1][:2] == ["pip", "install"] and chamadas[1][-2:] == ["-e", "."]
    assert Path(chamadas[1][chamadas[1].index("--python") + 1]).parts[-3:] == (".venv", "bin", "python")
    assert (copia.repo / ".venv" / "doctor.log").read_text(encoding="utf-8").strip() == "doctor"
    assert "simplicio-video install" in feito.stdout, "the next step names the command that installs the skills in the agent"
    assert "simplicio-video setup" in feito.stdout and "doctor" in feito.stdout
    assert list(copia.home.iterdir()) == [], "the dev install writes nothing outside the checkout"


@posix_real
def test_with_instala_os_extras_e_python_pede_a_versao(copia):
    ferramentas_ok(copia)
    disco_suficiente(copia.tmp)
    feito = roda(copia, "--with", "local-tts,mcp", "--python", "3.13")
    assert feito.returncode == 0, texto(feito)
    chamadas = chamadas_do_uv(copia.bin)
    assert chamadas[0] == ["venv", "--python", "3.13", ".venv"] and chamadas[1][-1] == ".[local-tts,mcp]"


@posix_real
def test_rodar_de_novo_nao_recria_o_venv_e_continua_certo(copia):
    ferramentas_ok(copia)
    disco_suficiente(copia.tmp)
    assert roda(copia).returncode == 0
    assert roda(copia).returncode == 0
    verbos = [c[0] for c in chamadas_do_uv(copia.bin)]
    assert verbos == ["venv", "pip", "pip"], "the .venv is created once; the editable install is repeated (it is idempotent)"


@posix_real
def test_venv_com_outro_python_e_um_conflito_que_nao_chama_o_uv(copia):
    ferramentas_ok(copia)
    disco_suficiente(copia.tmp)
    (copia.repo / ".venv").mkdir()
    (copia.repo / ".venv" / "pyvenv.cfg").write_text("home = /x\nversion_info = 3.11.9\n", encoding="utf-8")
    feito = roda(copia)
    assert feito.returncode == 1 and "3.11" in texto(feito) and "rm -rf .venv" in texto(feito)
    assert chamadas_do_uv(copia.bin) == []


@posix_real
def test_sem_uv_e_sem_terminal_falha_com_a_instrucao(copia):
    write_fake_tool(copia.bin, "node", "v22.11.0\n")
    write_fake_tool(copia.bin, "ffmpeg", FFMPEG_COM_LIBASS)
    if shutil.which("uv", path=SISTEMA):
        pytest.skip("a real uv in /usr/bin")
    disco_suficiente(copia.tmp)
    feito = roda(copia, extra_env={"SIMPLICIO_UV_SYSTEM_DIRS": ""})  # a real uv in /usr/local/bin or Homebrew must not be found
    assert feito.returncode == 1 and "uv não encontrado" in texto(feito) and "docs.astral.sh/uv" in texto(feito)
    assert not (copia.repo / ".venv").exists()


@posix_real
@pytest.mark.parametrize("onde", [".local/bin", ".cargo/bin"])
def test_uv_fora_do_path_e_achado_nas_pastas_de_sempre_do_home(copia, onde):
    """What `hostos.find_uv` did before this PR: the installer of uv drops it in ~/.local/bin (or ~/.cargo/bin)."""
    write_fake_tool(copia.bin, "node", "v22.11.0\n")
    write_fake_tool(copia.bin, "ffmpeg", FFMPEG_COM_LIBASS)
    write_fake_uv(copia.home / onde)
    disco_suficiente(copia.tmp)
    feito = roda(copia)
    assert feito.returncode == 0, texto(feito)
    assert chamadas_do_uv(copia.home / onde)[0][:1] == ["venv"]


@posix_real
def test_o_uv_do_path_vence_o_do_home(copia):
    ferramentas_ok(copia)
    write_fake_uv(copia.home / ".local" / "bin")
    disco_suficiente(copia.tmp)
    assert roda(copia).returncode == 0
    assert chamadas_do_uv(copia.bin) and not chamadas_do_uv(copia.home / ".local" / "bin")


@posix_real
def test_node_antigo_para_antes_de_qualquer_coisa(copia):
    ferramentas_ok(copia)
    write_fake_tool(copia.bin, "node", "v18.19.0\n")
    feito = roda(copia)
    assert feito.returncode == 1 and "Node 22" in texto(feito) and chamadas_do_uv(copia.bin) == []


@posix_real
def test_ffmpeg_sem_libass_para_antes_de_qualquer_coisa(copia):
    ferramentas_ok(copia)
    write_fake_tool(copia.bin, "ffmpeg", FFMPEG_SEM_LIBASS)
    feito = roda(copia)
    assert feito.returncode == 1 and "libass" in texto(feito) and chamadas_do_uv(copia.bin) == []


@posix_real
def test_doctor_que_reprova_faz_o_script_sair_1_e_diz_o_que_fazer(copia):
    ferramentas_ok(copia)
    disco_suficiente(copia.tmp)
    (copia.repo / ".venv").mkdir()
    (copia.repo / ".venv" / "pyvenv.cfg").write_text("version_info = 3.12.4\n", encoding="utf-8")
    (copia.repo / ".venv" / "bin").mkdir()
    stub = copia.repo / ".venv" / "bin" / "simplicio-video"
    stub.write_text('#!/bin/sh\nexit 1\n', encoding="utf-8")
    stub.chmod(0o755)
    feito = roda(copia)
    assert feito.returncode == 1 and "doctor" in texto(feito)


@posix_real
def test_com_web_o_script_roda_npm_ci_e_o_build(copia):
    ferramentas_ok(copia)
    npm = write_fake_tool(copia.bin, "npm", "")
    disco_suficiente(copia.tmp)
    (copia.repo / "web").mkdir()
    (copia.repo / "web" / "package.json").write_text("{}\n", encoding="utf-8")
    feito = roda(copia)
    assert feito.returncode == 0, texto(feito)
    chamadas = (npm.parent / "npm.argv").read_text(encoding="utf-8").splitlines()
    assert chamadas == ["--prefix web ci", "--prefix web run build"]


@posix_real
@pytest.mark.parametrize("argv,trecho", [(["--python", "tres-doze"], "versão de Python inválida"),
                                         (["--with", "Ruim!"], "extras inválidos"), (["--with"], "--with pede os extras"),
                                         (["--python"], "--python pede a versão"), (["--nada"], "opção desconhecida")])
def test_argumento_invalido_sai_1_antes_de_qualquer_coisa(copia, argv, trecho):
    ferramentas_ok(copia)
    feito = roda(copia, *argv)
    assert feito.returncode == 1 and trecho in texto(feito) and chamadas_do_uv(copia.bin) == []
    assert not (copia.repo / ".venv").exists()


@posix_real
def test_nao_usa_o_python_do_sistema_para_nada(copia):
    """Bug B1 of the PR #116: the old `./install.sh` ran `python3 -m simplicio_video` with the SYSTEM python, which has no PyYAML.
    The dev install must not need a python3 on PATH at all (uv brings the Python)."""
    ferramentas_ok(copia)
    disco_suficiente(copia.tmp)
    # a PATH with the fakes and the shell tools, but NO python anywhere
    pasta = copia.tmp / "sem-python"
    pasta.mkdir()
    for nome in ("bash", "sh", "df", "awk", "sed", "dirname", "cat", "grep", "tr", "head", "uname", "env", "mkdir", "rm"):
        achado = shutil.which(nome, path=SISTEMA)
        if achado:
            (pasta / nome).symlink_to(achado)
    feito = roda(copia, path=f"{copia.bin}:{pasta}")
    assert feito.returncode == 0, texto(feito)


def test_o_script_nao_menciona_o_python_do_sistema_nem_o_modulo_do_cli():
    codigo = "\n".join(l for l in DEV_SH.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
    assert "python3" not in codigo and "-m simplicio_video" not in codigo and "PYTHONPATH" not in codigo


# --- PowerShell (UNVERIFIED: it cannot run here) ---------------------------------------------------------------------------------


def _ps1(arquivo):
    return arquivo.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("arquivo", [DEV_PS1, WRAP_PS1])
def test_ps1_ou_e_ascii_ou_tem_bom_utf8(arquivo):
    """Windows PowerShell 5.1 reads a file without a BOM as the ANSI code page: the accents would come out wrong."""
    bruto = arquivo.read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf") or all(b < 128 for b in bruto), f"{arquivo.name}: UTF-8 com acento precisa de BOM"


def test_dev_install_ps1_tem_as_mesmas_opcoes_e_os_mesmos_passos_do_sh():
    codigo = _ps1(DEV_PS1)
    assert "UNVERIFIED" in codigo, "the header must say that nobody ran it on a real Windows yet"
    assert re.search(r"\[CmdletBinding\(\)\]", codigo) and re.search(r"param\s*\(", codigo)
    for parametro in ("$With", "$Python", "$DryRun"):
        assert parametro in codigo, parametro
    assert '$ErrorActionPreference = "Stop"' in codigo or "$ErrorActionPreference = 'Stop'" in codigo
    for passo in ("uv venv --python", "pip install", ".venv", "Scripts", "python.exe", "doctor", "libass", "22", "5"):
        assert passo in codigo, f"dev_install.ps1 sem {passo!r}"
    assert "Invoke-WebRequest" not in codigo, "nothing is downloaded behind the user's back"


def test_dev_install_ps1_so_instala_o_uv_com_a_confirmacao_e_sem_admin():
    codigo = _ps1(DEV_PS1)
    assert "Read-Host" in codigo, "uv is only installed after a yes"
    for proibido in ("Start-Process -Verb RunAs", "RunAs", "Set-ExecutionPolicy", "gsudo", "choco ", "winget install"):
        # `winget install Gyan.FFmpeg` appears as a HINT for ffmpeg, never as a command the script runs
        if proibido == "winget install":
            assert not re.search(r"^\s*(&\s*)?winget\s+install", codigo, re.M)
        else:
            assert proibido not in codigo, f"the script must not need administrator rights: {proibido}"
    iex = [l for l in codigo.splitlines() if re.search(r"\biex\b|Invoke-Expression", l)]
    assert all(l.lstrip().startswith("#") or "install.ps1" in l or "Read-Host" in l or "uv" in l for l in iex)


def test_dev_install_ps1_nao_usa_o_python_do_sistema():
    codigo = "\n".join(l for l in _ps1(DEV_PS1).splitlines() if not l.lstrip().startswith("#"))
    assert "python3" not in codigo and "-m simplicio_video" not in codigo


def test_install_ps1_e_um_involucro_fino():
    linhas = [l for l in _ps1(WRAP_PS1).splitlines() if l.strip() and not l.lstrip().startswith("#")]
    assert len(linhas) <= 12, "the wrapper must stay thin"
    corpo = "\n".join(linhas)
    assert "dev_install.ps1" in corpo and "@args" in corpo or "$args" in corpo
    for logica in ("uv venv", "libass", "pip install"):
        assert logica not in corpo
    assert "powershell" in corpo.lower() or "& " in corpo


# --- the places that used to call the .venv install -----------------------------------------------------------------------------


def test_nenhum_consumidor_chama_mais_o_install_do_venv():
    """`simplicio-video install --python/--with` and `.venv/simplicio-install.json` are gone: nobody may still use them."""
    donos = [ROOT / "Dockerfile", ROOT / "compose.yaml", ROOT / "deploy" / "docker" / "doctor.sh", ROOT / "install.sh",
             ROOT / "scripts" / "check.sh", ROOT / "Makefile"]
    donos += sorted((ROOT / "src" / "simplicio_video").rglob("*.py"))
    for arquivo in donos:
        if not arquivo.is_file():
            continue
        corpo = arquivo.read_text(encoding="utf-8")
        assert "simplicio-install.json" not in corpo, f"{arquivo.relative_to(ROOT)} cita o registro antigo do .venv"
        if arquivo.name in ("Dockerfile", "compose.yaml", "doctor.sh"):
            assert "dev_install" not in re.sub(r"(?m)^\s*#.*$", "", corpo), f"{arquivo.name}: the image installs by pip, not by the dev install"
        assert not re.search(r"simplicio-video install[^\n]*--(python|with)\b", corpo), f"{arquivo.relative_to(ROOT)}: install --python/--with"
        assert not re.search(r"[\"']simplicio_video[\"'],\s*[\"']install[\"']\s*\]", corpo), f"{arquivo.relative_to(ROOT)} roda o install do venv"


def test_dev_install_ps1_aceita_o_with_como_lista_do_powershell_e_como_texto_com_virgula():
    """`-With local-tts,mcp` typed in PowerShell is an ARRAY: a plain [string] would join it with a space and refuse it (review of #117)."""
    codigo = _ps1(DEV_PS1)
    assert "[string[]]$With" in codigo and '-join ","' in codigo
    assert "$WithTexto" in codigo and "$With -ne" not in codigo.replace("$WithTexto", ""), "every test of the extras reads the joined text"


def test_os_usos_do_powershell_nos_scripts_levam_o_bypass_so_do_processo():
    """The client Windows policy is Restricted: `powershell -File x.ps1` stops with "running scripts is disabled" (review of #117)."""
    usos = []
    for arquivo in (DEV_PS1, WRAP_PS1, DEV_SH, WRAP_SH):
        usos += [(arquivo.name, l.strip()) for l in arquivo.read_text(encoding="utf-8-sig").splitlines()
                 if re.search(r"powershell[^\n]*(dev_install|install)\.ps1", l, re.I) and "astral.sh" not in l]  # not uv's own installer
    assert usos, "the scripts say how to run the PowerShell one"
    for nome, linha in usos:
        assert "-NoProfile -ExecutionPolicy Bypass -File" in linha, f"{nome}: {linha}"

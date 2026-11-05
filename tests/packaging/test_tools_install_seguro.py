"""tools.install() and npm_command() check the ref they pass to git or npx before any argument is built (an override such as
`--force` would be read as an option of the program, and a checkout with it discards local edits). And without a home there is
nowhere to put the checkout: the clone refuses cleanly, with no folder made in the working directory.

The unit tests use a fake git that records its arguments (the hermetic suite refuses real git); the integration test is the one
with real git and a local edit.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import _caixa
from _caixa import write_git_launcher
from simplicio_video import hostos, montage, tools, tools_lock, tools_update

saude = _caixa.saude
caixa = _caixa.caixa
REAL_GIT = tools._git  # the hermetic fixture swaps tools._git for a refusal in every test: the integration test puts this one back

SEM_CASA = ("HOME", "USERPROFILE", "SIMPLICIO_TOOLS_DIR", "SIMPLICIO_VIDEO_DATA", "SIMPLICIO_OFFLINE")  # the data folder is a home too
VALORES_GIT = ["--force", "--upload-pack=touch X", "abc1234;rm -rf ~", "main"]
VALORES_NPM = ["0.2.17;rm -rf ~", "--force", "0.2"]


def _sem_casa(monkeypatch):
    for nome in SEM_CASA:
        monkeypatch.delenv(nome, raising=False)

    def sem(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(sem))


@pytest.mark.parametrize("valor", VALORES_GIT)
def test_ref_de_git_invalida_nao_chega_a_nenhum_argv(monkeypatch, tmp_path, valor):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_OPENMONTAGE_REF", valor)
    chamadas = []

    def gravador(*args, cwd=None):
        chamadas.append(args)
        return ""

    monkeypatch.setattr(tools, "_git", gravador)
    with pytest.raises(tools.ToolError) as erro:
        tools.install("openmontage")
    assert chamadas == [], chamadas
    assert valor not in str(erro.value)


@pytest.mark.parametrize("valor", VALORES_NPM)
def test_versao_de_npm_invalida_nao_roda_o_npx(monkeypatch, tmp_path, valor):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_HYPIT_REF", valor)
    # no local hypit (a binary on PATH wins in npm_command, before any check): npx is the way the ref is used
    monkeypatch.setattr(tools.shutil, "which", lambda nome, **kw: None if nome == "hypit" else f"/falso/{nome}")
    chamadas = []

    def gravador(argv, **kw):
        chamadas.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(tools.subprocess, "run", gravador)
    with pytest.raises(tools.ToolError) as erro:
        tools.install("hypit")
    assert chamadas == [], chamadas
    assert valor not in str(erro.value)
    with pytest.raises(tools.ToolError):
        tools.npm_command("hypit")


def test_sem_home_o_install_recusa_e_nao_cria_pasta_no_cwd(monkeypatch, tmp_path):
    _sem_casa(monkeypatch)
    monkeypatch.chdir(tmp_path)
    antes = os.getcwd()
    with pytest.raises(tools.ToolError) as erro:
        tools.install("opencut")
    assert "HOME" in str(erro.value)
    assert os.getcwd() == antes and not (tmp_path / "~").exists()


def test_sem_home_o_montage_clone_recusa_com_mensagem_e_sem_pasta(monkeypatch, tmp_path):
    _sem_casa(monkeypatch)
    monkeypatch.chdir(tmp_path)
    antes = os.getcwd()
    with pytest.raises(montage.MontageError) as erro:
        montage.clone_openmontage()
    assert "HOME" in str(erro.value)
    assert os.getcwd() == antes and not (tmp_path / "~").exists()


def _tils(cwd: Path) -> list:
    return sorted(p.name for p in cwd.iterdir() if p.name.startswith("~"))


def test_sem_HOME_nenhuma_til_no_cwd_install_lock_e_update(monkeypatch, tmp_path):
    """No HOME and no passwd entry: Path("~") is relative, and a mkdir on it makes a folder literally named `~` in the cwd. Neither
    install('video-use'), nor the lock, nor an `update` may make one: each refuses (or records the failure) and creates nothing."""
    _sem_casa(monkeypatch)
    monkeypatch.delenv("VIDEO_USE_DIR", raising=False)
    monkeypatch.setattr(tools, "_git", lambda *args, **kwargs: "")  # a git that "works": only the folder it is given is in question
    monkeypatch.chdir(tmp_path)
    with pytest.raises(tools.ToolError) as erro:
        tools.install("video-use")
    assert "HOME" in str(erro.value)
    assert _tils(tmp_path) == [], _tils(tmp_path)
    with pytest.raises(hostos.SemCasa):
        tools_lock.write_lock(tools_lock.empty())
    assert _tils(tmp_path) == [], _tils(tmp_path)
    assert tools_lock.read_lock() == tools_lock.empty()  # nothing to read is no lock, not a traceback
    chamadas = []

    def roda(argv, cwd=None):
        chamadas.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "a" * 40 + "\tHEAD\n", "")

    io = tools_update.Io(network=True, run=roda, fetch_json=lambda url: {}, now=lambda: 1_800_000_000)
    for modo in ("pin", "follow"):
        linhas, falhas = tools_update.apply_all(tools_lock.empty(), modo, io)  # must not raise
        assert falhas > 0 and any("HOME" in linha for linha in linhas), linhas
        assert _tils(tmp_path) == [], (modo, _tils(tmp_path))
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_home_absoluta_le_o_ambiente_como_o_resto(monkeypatch, tmp_path):
    """USERPROFILE (Windows) or HOME: hostos.home_absoluta() must read os.environ like home_dir(os.environ) does, so the tools folder and
    the video-use checkout agree. Path.home() alone (what home_dir() does without an environment) answers another folder here."""
    for nome in ("HOME", "SIMPLICIO_TOOLS_DIR", "VIDEO_USE_DIR", "SIMPLICIO_VIDEO_DATA"):
        monkeypatch.delenv(nome, raising=False)
    perfil = tmp_path / "perfil"
    outro = tmp_path / "outro-home"
    monkeypatch.setenv("USERPROFILE", str(perfil))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: outro))
    assert hostos.home_absoluta() == perfil
    assert tools.tools_dir() == perfil / ".simplicio-video" / "tools"
    assert tools_update.checkout_for(tools.get("video-use")) == perfil / ".cache" / "simplicio" / "video-use"
    assert tools_lock.default_data_dir() == perfil / ".simplicio-video"


def test_override_de_pip_nao_aparece_na_mensagem(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_YT-DLP_REF", "2099.1.1")
    with pytest.raises(tools.ToolError) as erro:
        tools.install("yt-dlp")
    assert "2099.1.1" not in str(erro.value)


@pytest.mark.skipif(os.name == "nt", reason="bash")
def test_setup_sh_sem_HOME_diz_o_que_definir_e_nao_cria_nada(tmp_path):
    """`set -u` made the script die with `HOME: unbound variable`: a message that names the fix, and nothing created."""
    setup = Path(tools.__file__).parent / "data" / "tools" / "video-use" / "setup.sh"
    bash = shutil.which("bash")
    assert bash
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    r = subprocess.run([bash, str(setup), "--quiet"], cwd=cwd, env={"PATH": os.environ["PATH"]}, capture_output=True, text=True, timeout=30)
    assert r.returncode != 0
    assert "unbound" not in r.stderr and "defina HOME" in r.stderr, r.stderr
    assert list(cwd.iterdir()) == [] and list(tmp_path.iterdir()) == [cwd]


@pytest.mark.integration
def test_integracao_edicao_local_sobrevive_a_um_ref_hostil(saude, monkeypatch):
    """A local edit of a tracked file survives an override that is an option (`--force` would discard it), and an override that is
    the commit in use (no change at all)."""
    e = saude.caixa
    write_git_launcher(e.bin)
    monkeypatch.setattr(tools, "_git", REAL_GIT)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(e.tmp / "tools"))
    for nome in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(nome, "teste")
    for nome in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(nome, "teste@invalido.example")
    real = shutil.which("git", path=_caixa.REAL_PATH)

    def git(pasta, *args):
        return subprocess.run([real, *args], cwd=pasta, check=True, capture_output=True, text=True).stdout.strip()

    origem = e.tmp / "origem"
    origem.mkdir()
    (origem / "package.json").write_text("{}\n", encoding="utf-8")
    git(origem, "init", "-q")
    git(origem, "add", "-A")
    git(origem, "commit", "-q", "-m", "origem")
    destino = e.tmp / "tools" / "opencut"
    git(e.tmp, "clone", "-q", str(origem), str(destino))
    editado = "editado a mão, sem commit\n"
    (destino / "package.json").write_text(editado, encoding="utf-8")

    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", "--force")
    with pytest.raises(tools.ToolError):
        tools.install("opencut")
    assert (destino / "package.json").read_text(encoding="utf-8") == editado

    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", git(destino, "rev-parse", "HEAD"))
    tools.install("opencut")
    assert (destino / "package.json").read_text(encoding="utf-8") == editado

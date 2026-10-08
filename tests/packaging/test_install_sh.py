"""Contrato do install.sh (issue #43).

`./install.sh --dry-run` lista o plano (uv, Python 3.12, .venv, extras, Node 22, ffmpeg com libass, web, doctor,
5 GB livres) e não cria nada. Os testes rodam o script numa cópia em tmp_path (com pyproject.toml e plugin.json),
com HOME temporário: nenhum .venv real nem ~ é tocado. Sem sudo. Sintaxe com `bash -n` e shellcheck (do .venv).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from _comum import ROOT, instantanea

SCRIPT = ROOT / "install.sh"


@pytest.fixture
def copia(tmp_path, monkeypatch):
    """Cópia do install.sh e dos arquivos que ele lê, num checkout temporário."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    if SCRIPT.is_file():
        shutil.copy2(SCRIPT, repo / "install.sh")
    for nome in ("pyproject.toml", "plugin.json"):
        shutil.copy2(ROOT / nome, repo / nome)
    monkeypatch.setenv("HOME", str(home))
    return SimpleNamespace(repo=repo, home=home)


def _dry_run(copia, *extra):
    env = {**os.environ, "HOME": str(copia.home)}
    return subprocess.run(["bash", "install.sh", "--dry-run", *extra], cwd=copia.repo, env=env,
                          capture_output=True, text=True, timeout=120)


def test_install_sh_existe_e_e_executavel():
    assert SCRIPT.is_file(), "install.sh não existe na raiz do repo"
    assert os.access(SCRIPT, os.X_OK), "install.sh precisa ser executável (./install.sh)"


def test_dry_run_lista_o_plano_completo(copia):
    assert SCRIPT.is_file(), "install.sh não existe"
    r = _dry_run(copia)
    texto = r.stdout + r.stderr
    low = texto.lower()
    assert r.returncode == 0, texto
    assert "dry" in low, "o plano deveria dizer que é dry-run"
    for trecho in ("3.12", ".venv", "doctor", "web", "ffmpeg", "libass", "22"):
        assert trecho in low, f"plano sem '{trecho}':\n{texto}"
    assert re.search(r"\buv\b", low), f"plano sem uv:\n{texto}"
    assert re.search(r"node\b", low), f"plano sem Node:\n{texto}"
    assert re.search(r"5\s*GB", texto, re.IGNORECASE), f"plano sem o mínimo de 5 GB livres:\n{texto}"


def test_dry_run_aceita_extras_e_python(copia):
    assert SCRIPT.is_file(), "install.sh não existe"
    r = _dry_run(copia, "--with", "server,publish", "--python", "3.12")
    texto = r.stdout + r.stderr
    assert r.returncode == 0, texto
    assert "server" in texto and "publish" in texto, f"extras pedidos não aparecem no plano:\n{texto}"
    assert "3.12" in texto


def test_dry_run_nao_cria_nada(copia):
    assert SCRIPT.is_file(), "install.sh não existe"
    antes = instantanea(copia.repo)
    r = _dry_run(copia)
    assert r.returncode == 0, r.stdout + r.stderr
    assert instantanea(copia.repo) == antes, "--dry-run alterou o checkout"
    assert not (copia.repo / ".venv").exists(), "--dry-run não pode criar .venv"
    assert list(copia.home.iterdir()) == [], "--dry-run não pode escrever no HOME"


def test_install_sh_sem_sudo():
    assert SCRIPT.is_file(), "install.sh não existe"
    for linha in SCRIPT.read_text(encoding="utf8").splitlines():
        if linha.lstrip().startswith("#"):
            continue
        assert not re.search(r"(^|[\s;&|(])sudo\s", linha), f"install.sh não pode usar sudo: {linha!r}"


def test_install_sh_sintaxe_bash():
    assert SCRIPT.is_file(), "install.sh não existe"
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_install_sh_shellcheck():
    assert SCRIPT.is_file(), "install.sh não existe"
    sc = shutil.which("shellcheck", path=str(Path(sys.executable).parent))
    if sc is None:
        pytest.skip("shellcheck não está no .venv (pacote shellcheck-py do extra test)")
    r = subprocess.run([sc, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

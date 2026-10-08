"""Contrato de `simplicio-video install` (issue #43): o instalador idempotente que o install.sh chama.

`install --check` reporta o que mudaria e não cria nada. Testes em processo (main()), com o checkout em tmp_path
(SIMPLICIO_VIDEO_HOME), nunca o .venv real. A idempotência de uma instalação de verdade precisa de uv e rede e fica
de fora desta suíte (ver relatório da issue).
"""
from __future__ import annotations

import shutil

import pytest

from _casa import casa  # noqa: F401 (fixture: HOME e workspace isolados)
from _comum import ROOT, executa, exige_registrado, instantanea
from simplicio_video.cli import main


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """Um checkout mínimo (pyproject.toml e plugin.json reais), sem .venv, apontado por SIMPLICIO_VIDEO_HOME."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    for nome in ("pyproject.toml", "plugin.json"):
        shutil.copy2(ROOT / nome, repo / nome)
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(repo))
    return repo


def test_install_check_reporta_o_que_mudaria_sem_criar_nada(checkout, casa, capsys):  # noqa: F811
    exige_registrado("install", capsys, main)
    antes = instantanea(checkout)
    rc, out, err = executa(["install", "--check"], capsys, main)
    assert rc in (0, 1), f"rc inesperado {rc}: {err}{out}"
    texto = out + err
    assert ".venv" in texto, f"--check não diz que o .venv seria criado:\n{texto}"
    assert instantanea(checkout) == antes, "install --check alterou o checkout"
    assert not (checkout / ".venv").exists(), "install --check não pode criar .venv"
    assert list(casa.home.iterdir()) == [], "install --check não pode escrever no HOME"


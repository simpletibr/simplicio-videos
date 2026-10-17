"""An installed package (pip) has no checkout: `install` and `update` must never create or touch anything in site-packages.

`paths.home()` falls back to the package data folder (`.../site-packages/simplicio_video/data`) when no checkout is found.
Here the installed package is simulated: no .git or plugin.json above the module, no editable install, the distribution
metadata present, and `paths.home()` pointing at a folder under tmp_path that the test watches.

Contract: `install` works the same for a pip package and for a checkout (it copies the skill to `--target`, or to the home with
`--global`, never into site-packages) and its `--check` answers 0 or 10; `update` takes the pip branch (PyPI), never runs git and
reinstalls the skills afterwards (`install --global`); `status` and `doctor` never present site-packages as a checkout.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

import _caixa
from _caixa import distribution, doctor_cmd, saida_cp1252, update_cmd
from _comum import erros_de_schema, executa, instantanea
from simplicio_video import paths
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa


@pytest.fixture
def pacote(caixa, monkeypatch):
    """The installed package: nothing above it is a checkout, and `paths.home()` is the (watched) data folder."""
    site = caixa.tmp / "site-packages" / "simplicio_video" / "data"
    site.mkdir(parents=True)
    monkeypatch.setattr(paths, "home", lambda start=None: site)
    monkeypatch.setattr(paths, "DATA_DIR", site)
    monkeypatch.setattr(distribution, "in_checkout", lambda: False)
    monkeypatch.setattr(distribution, "is_editable", lambda: False)
    monkeypatch.setattr(distribution, "_installed", lambda: object())
    caixa.site = site
    caixa.arvore = caixa.tmp / "site-packages"
    return caixa


def test_o_pacote_simulado_e_da_distribuicao_pip(pacote):
    assert distribution.kind() == distribution.PIP == "pip"
    assert distribution.kind(editable=True) == distribution.SOURCE
    assert distribution.kind(checkout=True) == distribution.SOURCE


def test_sem_metadados_de_instalacao_nem_checkout_e_source(monkeypatch):
    """Run straight from a tree that pip never installed (PYTHONPATH=src): it is a source run, not pip."""
    monkeypatch.setattr(distribution, "_installed", lambda: None)
    assert distribution.kind(editable=False, checkout=False) == distribution.SOURCE


def test_um_checkout_exige_git_e_plugin_json_na_raiz(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    assert distribution.checkout_marker(tmp_path) is False, "a .git alone (e.g. a stray one in lib/) is not a checkout"
    (tmp_path / "plugin.json").write_text('{"name": "videos"}\n')
    assert distribution.checkout_marker(tmp_path) is True
    (tmp_path / ".git").rmdir()
    assert distribution.checkout_marker(tmp_path) is False


@pytest.mark.parametrize("opcoes", [["--check"], ["--dry-run"], ["--check", "--dry-run"]])
def test_install_check_e_dry_run_do_pacote_instalado_nao_tocam_no_site_packages(pacote, capsys, opcoes, tmp_path):
    alvo = tmp_path / "proj"
    alvo.mkdir()
    antes = instantanea(pacote.arvore)
    rc, out, err = executa(["install", *opcoes, "--target", str(alvo)], capsys, main)
    assert rc == (10 if "--check" in opcoes else 0), out + err
    assert "checkout:" not in out + err and str(pacote.site) not in out + err and "site-packages" not in out + err
    assert instantanea(pacote.arvore) == antes, "nothing may be created in site-packages"
    assert instantanea(alvo) == [] and list(pacote.home.iterdir()) == []
    saida_cp1252(out, err)


def test_install_de_pacote_instalado_copia_as_skills_para_o_alvo_e_nada_para_o_site_packages(pacote, capsys, tmp_path):
    alvo = tmp_path / "proj"
    alvo.mkdir()
    antes = instantanea(pacote.arvore)
    rc, out, err = executa(["install", "--target", str(alvo)], capsys, main)
    assert rc == 0, out + err
    assert (alvo / ".claude" / "skills" / "simplicio-video" / "SKILL.md").is_file()
    assert instantanea(pacote.arvore) == antes and not (pacote.site / ".venv").exists()
    assert executa(["install", "--check", "--target", str(alvo)], capsys, main)[0] == 0


def test_install_global_de_pacote_instalado_vai_para_o_home_e_nao_para_o_site_packages(pacote, capsys):
    antes = instantanea(pacote.arvore)
    rc, out, err = executa(["install", "--global"], capsys, main)
    assert rc == 0, out + err
    assert (pacote.home / ".claude" / "skills" / "simplicio-video" / "SKILL.md").is_file()
    assert instantanea(pacote.arvore) == antes


def test_install_json_de_pacote_instalado_fecha_com_o_schema(pacote, capsys, tmp_path):
    rc, out, err = executa(["install", "--check", "--json", "--target", str(tmp_path)], capsys, main)
    doc = json.loads(out)
    assert rc == 10 and erros_de_schema("install-plan", doc) == [] and doc["host"] == "claude"


def test_update_de_pacote_instalado_usa_o_ramo_pip_e_nunca_roda_git(pacote, capsys, monkeypatch):
    chamadas = []
    antes = instantanea(pacote.arvore)
    monkeypatch.setattr(update_cmd, "_git", lambda *a, **k: pytest.fail("git is not part of the pip update"))
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: "v99.0.0")
    monkeypatch.setattr(update_cmd, "_run", lambda argv, cwd=None: chamadas.append((list(argv), cwd)) or 0)
    monkeypatch.setattr(update_cmd, "is_pep668_environment", lambda **kw: (False, None))
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0, out + err
    assert chamadas == [([sys.executable, "-m", "pip", "install", "--upgrade", "simplicio-video==99.0.0"], None),
                        ([sys.executable, "-m", "simplicio_video", "install", "--global"], None)]
    assert instantanea(pacote.arvore) == antes


def test_update_check_de_pacote_instalado_grava_kind_pip_sem_commits_behind(pacote, capsys, monkeypatch):
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: "v99.0.0")
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10, out + err
    registro = json.loads((pacote.data / "update-check.json").read_text())
    assert registro["kind"] == "pip" and registro["update_available"] is True and "commits_behind" not in registro
    assert not (pacote.site / "update-check.json").exists()


def test_status_nao_mostra_o_site_packages_como_checkout(pacote, capsys):
    rc, out, err = executa(["status"], capsys, main)
    assert rc == 0 and str(pacote.site) not in out + err and "site-packages" not in out + err
    rc, out, err = executa(["status", "--json"], capsys, main)
    assert rc == 0 and str(pacote.site) not in out + err and "site-packages" not in out + err


def test_doctor_nao_mostra_o_site_packages_como_checkout(pacote, capsys, monkeypatch):
    monkeypatch.setattr(doctor_cmd, "porta_livre", lambda porta, *a, **kw: True)
    rc, out, err = executa(["doctor", "--json"], capsys, main)
    assert "site-packages" not in out + err and os.fspath(pacote.site) not in out + err
    doc = json.loads(out)
    distribuicao = next(c for c in doc["checks"] if c["name"] == "distribution")
    assert distribuicao["detail"]["kind"] == "pip" and "checkout" not in distribuicao["summary"].replace("sem checkout", "")

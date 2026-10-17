"""An installed package (pip) has no checkout: `install` and `update` must never create or touch anything in site-packages.

`paths.home()` falls back to the package data folder (`.../site-packages/simplicio_video/data`) when no checkout is found,
so a naive `install` would create a `.venv` inside site-packages and a naive `install --check` would print that folder as
"checkout". Here the installed package is simulated: no .git or plugin.json above the module, no editable install, the
distribution metadata present, and `paths.home()` pointing at a folder under tmp_path that the test watches.

Contract: `install --check` and `--dry-run` say the package was installed by pip and exit 0; a real `install` exits 2;
`update` takes the pip branch (PyPI) and never runs git; `status` and `doctor` never present site-packages as a checkout.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

import _caixa
from _caixa import chamadas_do_uv, distribution, doctor_cmd, saida_cp1252, update_cmd, write_fake_uv
from _comum import executa, instantanea
from simplicio_video import paths
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa

MENSAGEM = "instalado por pip: não há .venv a criar; use pip install --upgrade simplicio-video"


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
    write_fake_uv(caixa.bin)
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
def test_install_check_e_dry_run_dizem_que_foi_o_pip_e_saem_0(pacote, capsys, opcoes):
    antes = instantanea(pacote.arvore)
    rc, out, err = executa(["install", *opcoes], capsys, main)
    assert rc == 0, out + err
    assert MENSAGEM in out + err
    assert "checkout:" not in out + err and str(pacote.site) not in out + err
    assert instantanea(pacote.arvore) == antes, "nothing may be created in site-packages"
    assert chamadas_do_uv(pacote.bin) == [], "uv must not start"
    saida_cp1252(out, err)


def test_install_real_sai_2_e_nao_cria_nada_no_site_packages(pacote, capsys):
    antes = instantanea(pacote.arvore)
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 2
    assert MENSAGEM in err, "the refusal goes to stderr"
    assert instantanea(pacote.arvore) == antes and not (pacote.site / ".venv").exists()
    assert chamadas_do_uv(pacote.bin) == []
    assert list(pacote.home.iterdir()) == []


def test_install_json_de_pacote_instalado_e_valido_e_diz_pip(pacote, capsys):
    rc, out, err = executa(["install", "--check", "--json"], capsys, main)
    doc = json.loads(out)
    assert rc == 0 and doc["distribution"] == "pip" and doc["up_to_date"] is True
    assert doc["pending"] == [] and doc["conflict"] is None and doc["extras"] == []
    assert doc["python"] == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert MENSAGEM in err and MENSAGEM not in out, "stdout stays one JSON document"


def test_install_real_com_json_tambem_sai_2_sem_documento(pacote, capsys):
    rc, out, err = executa(["install", "--json"], capsys, main)
    assert rc == 2 and out == "" and MENSAGEM in err


def test_update_de_pacote_instalado_usa_o_ramo_pip_e_nunca_roda_git(pacote, capsys, monkeypatch):
    chamadas = []
    antes = instantanea(pacote.arvore)
    monkeypatch.setattr(update_cmd, "_git", lambda *a, **k: pytest.fail("git is not part of the pip update"))
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: "v99.0.0")
    monkeypatch.setattr(update_cmd, "_run", lambda argv, cwd=None: chamadas.append((list(argv), cwd)) or 0)
    monkeypatch.setattr(update_cmd, "is_pep668_environment", lambda **kw: (False, None))
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0, out + err
    assert chamadas == [([sys.executable, "-m", "pip", "install", "--upgrade", "simplicio-video==99.0.0"], None)]
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

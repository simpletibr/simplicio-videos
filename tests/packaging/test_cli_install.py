"""Contract of `simplicio-video install [--check] [--dry-run] [--json] [--python X] [--with EXTRAS]`.

`install` is the checkout environment: `<checkout>/.venv` created with uv and the package installed in editable mode (it does
NOT copy skills into an agent host, unlike the loop's install). The loop's exit codes: `--check` exits 0 when up to date and
10 when something is pending (it was 1: breaking change); `--dry-run` writes nothing and exits 0. `--json` prints one
`simplicio.video-install/v1` document on stdout (everything else goes to stderr).

Tests run in process (main()) with the checkout in tmp_path (SIMPLICIO_VIDEO_HOME), a FAKE `uv` on a sealed PATH and a sealed
HOME: never the real .venv, ~ or the network.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

import _caixa
from _caixa import (chamadas_do_uv, distribution, hostos, saida_cp1252, so_incompativel,
                    write_fake_uv)
from _comum import ROOT, executa, exige_registrado, instantanea
from simplicio_video import __version__
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
simula_so = _caixa.simula_so


@pytest.fixture
def checkout(caixa, monkeypatch):
    """A minimal checkout (the real pyproject.toml and plugin.json), no .venv, pointed at by SIMPLICIO_VIDEO_HOME."""
    repo = caixa.tmp / "checkout"
    repo.mkdir()
    for nome in ("pyproject.toml", "plugin.json"):
        shutil.copy2(ROOT / nome, repo / nome)
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(repo))
    monkeypatch.setattr(distribution, "kind", lambda **kw: "source")
    return repo


def _json(capsys, *argv):
    rc, out, err = executa(["install", "--json", *argv], capsys, main)
    try:
        doc = json.loads(out)
    except ValueError:
        pytest.fail(f"install --json did not print a single JSON document (rc {rc}).\nstdout={out!r}\nstderr={err!r}")
    return rc, doc, err


# --- --check ---------------------------------------------------------------------------------------------------------


def test_check_com_mudanca_pendente_sai_10_sem_criar_nada(checkout, caixa, capsys):
    exige_registrado("install", capsys, main)
    antes = instantanea(checkout)
    rc, out, err = executa(["install", "--check"], capsys, main)
    assert rc == 10, f"--check with pending changes exits 10 (was 1): {rc}\n{out}{err}"
    assert ".venv" in out + err, f"--check does not say the .venv would be created:\n{out}{err}"
    assert instantanea(checkout) == antes, "install --check changed the checkout"
    assert not (checkout / ".venv").exists()
    assert list(caixa.home.iterdir()) == [], "install --check must not write to HOME"
    saida_cp1252(out, err)


def test_check_em_dia_sai_0(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    assert executa(["install"], capsys, main)[0] == 0
    rc, out, err = executa(["install", "--check"], capsys, main)
    assert rc == 0, out + err
    assert "nada a mudar" in out


def test_check_com_conflito_de_python_sai_10_e_diz_o_que_fazer(checkout, caixa, capsys):
    (checkout / ".venv").mkdir()
    (checkout / ".venv" / "pyvenv.cfg").write_text("home = /x\nversion_info = 3.11.9\n")
    rc, out, err = executa(["install", "--check"], capsys, main)
    assert rc == 10 and "conflito" in out and "3.11" in out and "rm -rf .venv" in out


def test_check_de_pyproject_alterado_volta_a_ficar_pendente(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    executa(["install"], capsys, main)
    with open(checkout / "pyproject.toml", "a", encoding="utf8") as f:
        f.write("\n# mudou\n")
    rc, out, err = executa(["install", "--check"], capsys, main)
    assert rc == 10 and "uv pip install" in out


# --- --dry-run -------------------------------------------------------------------------------------------------------


def test_dry_run_sai_0_nao_cria_nada_e_nao_chama_o_uv(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    antes = instantanea(checkout)
    rc, out, err = executa(["install", "--dry-run"], capsys, main)
    assert rc == 0, out + err
    assert "dry-run" in out and ".venv" in out and "uv venv --python 3.12" in out
    assert instantanea(checkout) == antes and list(caixa.home.iterdir()) == []
    assert chamadas_do_uv(caixa.bin) == [], "--dry-run must not start uv"


def test_dry_run_com_conflito_ainda_sai_0_e_mostra_o_conflito(checkout, caixa, capsys):
    (checkout / ".venv").mkdir()
    (checkout / ".venv" / "pyvenv.cfg").write_text("version_info = 3.11.9\n")
    rc, out, err = executa(["install", "--dry-run"], capsys, main)
    assert rc == 0 and "conflito" in out


def test_dry_run_com_extras_mostra_o_alvo_do_uv(checkout, capsys):
    rc, out, err = executa(["install", "--dry-run", "--python", "3.12", "--with", "local-tts,mcp"], capsys, main)
    assert rc == 0 and "-e .[local-tts,mcp]" in out


# --- --json ----------------------------------------------------------------------------------------------------------


def test_json_do_check_tem_o_contrato(checkout, capsys):
    rc, doc, err = _json(capsys, "--check")
    assert rc == 10
    assert doc["schema"] == "simplicio.video-install/v1" and doc["version"] == __version__
    assert doc["up_to_date"] is False and doc["conflict"] is None and doc["python"] == "3.12" and doc["extras"] == []
    assert doc["distribution"] == "source"
    assert len(doc["pending"]) == 2 and "uv venv" in doc["pending"][0] and "uv pip install" in doc["pending"][1]
    assert set(doc) == {"schema", "version", "up_to_date", "pending", "conflict", "python", "extras", "distribution"}


def test_json_do_dry_run_sai_0_e_nao_cria_nada(checkout, capsys):
    antes = instantanea(checkout)
    rc, doc, err = _json(capsys, "--dry-run", "--with", "local-tts")
    assert rc == 0 and doc["extras"] == ["local-tts"] and doc["up_to_date"] is False
    assert instantanea(checkout) == antes


def test_json_com_conflito_traz_o_texto(checkout, capsys):
    (checkout / ".venv").mkdir()
    (checkout / ".venv" / "pyvenv.cfg").write_text("version_info = 3.11.9\n")
    rc, doc, err = _json(capsys, "--check")
    assert rc == 10 and "3.11" in doc["conflict"]


def test_json_da_instalacao_real_so_tem_o_documento_no_stdout(checkout, caixa, capfd):
    write_fake_uv(caixa.bin)
    rc = main(["install", "--json"])
    out, err = capfd.readouterr()
    doc = json.loads(out)  # the output of uv ("uv fake: ...") went to stderr
    assert rc == 0 and doc["up_to_date"] is True and doc["pending"] == [] and "uv fake" in err and "uv fake" not in out


# --- the real install (fake uv) ---------------------------------------------------------------------------------------


def test_instala_cria_o_venv_instala_editavel_e_grava_o_registro(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 0, out + err
    chamadas = chamadas_do_uv(caixa.bin)
    assert chamadas[0] == ["venv", "--python", "3.12", ".venv"]
    assert chamadas[1][:2] == ["pip", "install"] and chamadas[1][-2:] == ["-e", "."]
    registro = json.loads((checkout / ".venv" / "simplicio-install.json").read_text())
    assert registro == {"python": "3.12", "extras": [],
                        "pyproject_sha256": hashlib.sha256((checkout / "pyproject.toml").read_bytes()).hexdigest()}
    assert "simplicio-video doctor" in out and "simplicio-video setup" in out, "the next steps are printed"
    assert list(caixa.home.iterdir()) == []


def test_sem_workspace_a_dica_do_setup_e_com_workspace_nao(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    caixa.workspace.mkdir(parents=True)
    (caixa.workspace / "workspace.yaml").write_text("schema: simplicio.workspace/v1\n")
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 0 and "simplicio-video doctor" in out and "simplicio-video setup" not in out


def test_a_segunda_instalacao_nao_chama_o_uv(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    executa(["install"], capsys, main)
    n = len(chamadas_do_uv(caixa.bin))
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 0 and len(chamadas_do_uv(caixa.bin)) == n and "nada a mudar" in out


def test_with_instala_os_extras_e_a_proxima_vez_reaproveita(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    rc, out, err = executa(["install", "--with", "local-tts,mcp"], capsys, main)
    assert rc == 0 and chamadas_do_uv(caixa.bin)[1][-1] == ".[local-tts,mcp]"
    registro = json.loads((checkout / ".venv" / "simplicio-install.json").read_text())
    assert registro["extras"] == ["local-tts", "mcp"]
    rc, out, err = executa(["install", "--check"], capsys, main)
    assert rc == 0, "without --with the extras of the last install are kept"


@pytest.mark.parametrize("so,partes", [("linux", (".venv", "bin", "python")), ("darwin", (".venv", "bin", "python")),
                                       ("win32", (".venv", "Scripts", "python.exe"))])
def test_o_python_do_venv_depende_do_sistema(checkout, caixa, capsys, simula_so, so, partes):
    if so_incompativel(so):
        pytest.skip("a real Windows only has .cmd launchers")
    simula_so(so)
    write_fake_uv(caixa.bin, hostos.exe_name("uv"))
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 0, out + err
    instalar = chamadas_do_uv(caixa.bin)[1]
    assert Path(instalar[instalar.index("--python") + 1]).parts[-3:] == partes


def test_conflito_na_instalacao_real_sai_1_e_nao_chama_o_uv(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    (checkout / ".venv").mkdir()
    (checkout / ".venv" / "pyvenv.cfg").write_text("version_info = 3.11.9\n")
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 1 and "conflito" in out + err and chamadas_do_uv(caixa.bin) == []


def test_uv_que_falha_sai_1_sem_gravar_o_registro(checkout, caixa, capsys):
    uv = write_fake_uv(caixa.bin)
    if uv.suffix == ".cmd":
        pytest.skip("this check rewrites the POSIX launcher")
    uv.write_text("#!/bin/sh\nexit 4\n")
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 1 and "comando falhou" in out + err
    assert not (checkout / ".venv" / "simplicio-install.json").exists()


@pytest.mark.parametrize("argv", [["--with", "Ruim Extra"], ["--python", "tres-doze"], ["--with", "ok,Ruim!"]])
def test_argumentos_invalidos_saem_com_2(checkout, capsys, argv):
    rc, out, err = executa(["install", "--check", *argv], capsys, main)
    assert rc == 2 and instantanea(checkout) == sorted(["plugin.json", "pyproject.toml"])


# --- finding uv ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("so,trecho", [("linux", "curl -LsSf https://astral.sh/uv/install.sh | sh"),
                                       ("darwin", "brew install uv"),
                                       ("win32", "irm https://astral.sh/uv/install.ps1 | iex")])
def test_sem_uv_sai_1_com_a_dica_do_sistema(checkout, caixa, capsys, simula_so, so, trecho):
    simula_so(so)
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 1 and trecho in out + err and "https://docs.astral.sh/uv/" in out + err
    assert not (checkout / ".venv").exists()
    saida_cp1252(out, err)


@pytest.mark.parametrize("so", ["linux", "darwin"])
def test_uv_fora_do_path_e_achado_em_local_bin_do_home(checkout, caixa, capsys, simula_so, so):
    if so_incompativel(so):
        pytest.skip("a real Windows only has .cmd launchers")
    simula_so(so)
    write_fake_uv(caixa.home / ".local" / "bin")
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 0, out + err
    assert chamadas_do_uv(caixa.home / ".local" / "bin")[0][:1] == ["venv"]


def test_o_uv_do_path_vence_o_do_home(checkout, caixa, capsys):
    write_fake_uv(caixa.bin)
    write_fake_uv(caixa.home / ".local" / "bin")
    executa(["install"], capsys, main)
    assert chamadas_do_uv(caixa.bin) and not chamadas_do_uv(caixa.home / ".local" / "bin")
    assert sys.version_info >= (3, 10)

"""Contract of `simplicio-video doctor [all|login] [--json] [--online]`: the loop's `simplicio.doctor/v1`.

JSON (stdout with --json):
  {"schema": "simplicio.doctor/v1", "status": "ok|warn|fail" (the worst), "version": str,
   "checks": [{"name": str, "status": "ok|warn|fail", "summary": str, "fix": str|null, "detail": {...}}, ...]}
Sections, in order: login, update, distribution, runtime, python, node, ffmpeg, ffmpeg-libass, disk, ports, GEMINI_API_KEY,
setup. Exit 1 only when a check is `fail`. A missing login, a missing workspace and a missing GEMINI_API_KEY are `warn`.
No token is ever printed.

Environment (fixture `saude`): HOME, PATH and the workspace are sealed under tmp_path (see _caixa.py); `node` and `ffmpeg`
are fake programs on that PATH (so the same tests run on Windows too), the disk and the ports are injected. A real
ffmpeg, node, Runtime or login file is never touched.
"""
from __future__ import annotations

import json
import os

import pytest

import _caixa
from _caixa import (FFMPEG_COM_LIBASS, FFMPEG_SEM_LIBASS, LEAKY_ENV, SENTINELA, assert_no_secret,
                    distribution, doctor_cmd, hostos, login_doc, posix_real, put_login, saida_cp1252,
                    so_incompativel, update_cmd, write_fake_tool)
from _comum import executa, exige_registrado, instantanea
from simplicio_video import __version__
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
saude = _caixa.saude
simula_so = _caixa.simula_so

GB = 1024**3
SECOES = ["login", "update", "distribution", "runtime", "python", "node", "ffmpeg", "ffmpeg-libass", "disk", "ports",
          "GEMINI_API_KEY", "setup"]


def _tira(saude, nome):
    """Remove a fake tool (its launcher and its side files) from the sealed PATH."""
    for f in saude.caixa.bin.glob(f"*{nome}*"):
        f.unlink()


def _json(capsys, *extra):
    exige_registrado("doctor", capsys, main)
    rc, out, err = executa(["doctor", "--json", *extra], capsys, main)
    try:
        rel = json.loads(out)
    except ValueError:
        pytest.fail(f"doctor --json did not print JSON (rc {rc}).\nstdout={out!r}\nstderr={err!r}")
    return rc, rel, out, err


def _linha(rel, nome):
    achadas = [c for c in rel["checks"] if c["name"] == nome]
    assert len(achadas) == 1, f"expected exactly one check {nome!r}: {[c['name'] for c in rel['checks']]}"
    return achadas[0]


# --- the contract ----------------------------------------------------------------------------------------------------


def test_json_tem_o_contrato_do_loop(saude, capsys):
    rc, rel, out, err = _json(capsys)
    assert rel["schema"] == "simplicio.doctor/v1" and rel["version"] == __version__
    assert rel["status"] in ("ok", "warn", "fail")
    assert "ok" not in rel, "the old `ok` flag is gone (breaking change): use `status`"
    for c in rel["checks"]:
        assert set(c) == {"name", "status", "summary", "fix", "detail"}, c
        assert c["status"] in ("ok", "warn", "fail") and isinstance(c["summary"], str) and c["summary"]
        assert isinstance(c["detail"], dict), "detail is an object now (was a string)"
        assert c["fix"] is None or isinstance(c["fix"], str)
    saida_cp1252(out, err)


def test_as_secoes_vem_na_ordem_do_contrato(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    assert [c["name"] for c in rel["checks"]] == SECOES
    assert list(doctor_cmd.SECTIONS) == SECOES and doctor_cmd.SCHEMA == "simplicio.doctor/v1"


def test_o_status_geral_e_o_pior_dos_checks(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    ordem = {"ok": 0, "warn": 1, "fail": 2}
    assert rel["status"] == max((c["status"] for c in rel["checks"]), key=ordem.get)


def test_ambiente_saudavel_so_tem_o_aviso_do_login_ausente(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    assert rc == 0 and rel["status"] == "warn"
    assert [c["name"] for c in rel["checks"] if c["status"] == "warn"] == ["login"]
    assert [c for c in rel["checks"] if c["status"] == "fail"] == []


def test_com_login_valido_o_ambiente_saudavel_fica_ok(saude, capsys):
    put_login(saude.caixa.login)
    rc, rel, out, err = _json(capsys)
    assert rc == 0 and rel["status"] == "ok", [c for c in rel["checks"] if c["status"] != "ok"]
    assert_no_secret(out, err)


# --- fail ------------------------------------------------------------------------------------------------------------


def test_sem_ffmpeg_sai_com_1_e_a_correcao(saude, capsys):
    _tira(saude, "ffmpeg")
    rc, rel, _, _ = _json(capsys)
    assert rc == 1 and rel["status"] == "fail"
    c = _linha(rel, "ffmpeg")
    assert c["status"] == "fail" and "ffmpeg" in c["fix"].lower()


def test_ffmpeg_sem_libass_falha_com_a_correcao(saude, capsys):
    write_fake_tool(saude.caixa.bin, "ffmpeg", FFMPEG_SEM_LIBASS)
    rc, rel, _, _ = _json(capsys)
    assert rc == 1
    c = _linha(rel, "ffmpeg-libass")
    assert c["status"] == "fail" and "libass" in c["fix"].lower()
    assert _linha(rel, "ffmpeg")["status"] == "ok"


@pytest.mark.parametrize("versao,estado", [((3, 12, 4), "ok"), ((3, 11, 9), "fail"), ((3, 14, 0), "warn")])
def test_a_linha_do_python(saude, capsys, monkeypatch, versao, estado):
    monkeypatch.setattr(doctor_cmd, "python_version", lambda: versao)
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "python")
    assert c["status"] == estado and ".".join(map(str, versao)) in c["summary"]
    if estado != "ok":
        assert "3.12" in c["fix"]
    assert (rc == 1) == (estado == "fail")


def test_node_com_versao_errada_falha_e_cita_o_node_22(saude, capsys):
    write_fake_tool(saude.caixa.bin, "node", "v20.18.0\n")
    rc, rel, _, _ = _json(capsys)
    assert rc == 1
    c = _linha(rel, "node")
    assert c["status"] == "fail" and "22" in c["fix"]


def test_pouco_disco_falha_com_a_correcao(saude, capsys):
    saude.livre_gb = 1.0
    rc, rel, _, _ = _json(capsys)
    assert rc == 1
    c = _linha(rel, "disk")
    assert c["status"] == "fail" and c["fix"] and c["detail"]["free_bytes"] < 5 * GB


def test_o_disco_e_medido_com_shutil_e_nao_com_statvfs(saude, capsys, monkeypatch):
    """os.statvfs does not exist on Windows: the check must work without it."""
    def proibido(*a, **k):
        raise AssertionError("os.statvfs does not exist on Windows")

    monkeypatch.setattr(os, "statvfs", proibido, raising=False)
    rc, rel, _, _ = _json(capsys)
    assert _linha(rel, "disk")["status"] == "ok" and saude.medidos


@posix_real
def test_login_com_permissao_frouxa_e_falha_e_diz_o_chmod(saude, capsys):
    put_login(saude.caixa.login, mode=0o644)
    rc, rel, out, err = _json(capsys)
    assert rc == 1 and rel["status"] == "fail"
    c = _linha(rel, "login")
    assert c["status"] == "fail" and c["fix"] == f"chmod 600 {saude.caixa.login}"
    assert c["detail"]["reason_code"] == "login_permissions"
    assert_no_secret(out, err)


def test_setup_com_workspace_invalido_falha_e_manda_regravar(saude, capsys):
    (saude.caixa.workspace / "workspace.yaml").write_text("schema: errado\n", encoding="utf8")
    rc, rel, _, _ = _json(capsys)
    assert rc == 1
    c = _linha(rel, "setup")
    assert c["status"] == "fail" and "setup --force" in c["fix"]


def test_setup_com_policy_ilegivel_falha(saude, capsys):
    (saude.caixa.workspace / "policy.yaml").write_text(": : not yaml [", encoding="utf8")
    rc, rel, _, _ = _json(capsys)
    assert rc == 1 and _linha(rel, "setup")["status"] == "fail"


# --- warn ------------------------------------------------------------------------------------------------------------


def test_login_ausente_e_aviso_nunca_falha(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "login")
    assert rc == 0 and c["status"] == "warn" and c["fix"] == "simplicio-video login"
    assert c["detail"]["reason_code"] == "login_missing" and c["detail"]["schema"] == "simplicio.auth-status/v1"


def test_login_expirado_e_aviso(saude, capsys):
    put_login(saude.caixa.login, login_doc(access_expires_at=1, refresh_token="", refresh_token_expires_at=0))
    rc, rel, _, _ = _json(capsys)
    assert rc == 0 and _linha(rel, "login")["status"] == "warn"


def test_workspace_ausente_e_aviso_e_manda_rodar_o_setup(saude, capsys):
    (saude.caixa.workspace / "workspace.yaml").unlink()
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "setup")
    assert rc == 0, "a missing workspace is a warning now (it was a failure): nothing in the engine reads it"
    assert c["status"] == "warn" and "simplicio-video setup" in c["fix"]


def test_credencial_ausente_e_aviso_e_nao_falha(saude, capsys, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    rc, rel, out, err = _json(capsys)
    c = _linha(rel, "GEMINI_API_KEY")
    assert rc == 0 and c["status"] == "warn" and "GEMINI_API_KEY" in c["fix"]
    assert SENTINELA not in out + err


def test_credencial_presente_nunca_mostra_o_valor(saude, capsys):
    rc, out, err = executa(["doctor"], capsys, main)
    assert SENTINELA not in out + err, "doctor (text) printed the credential"
    rc, rel, out, err = _json(capsys)
    assert SENTINELA not in out + err, "doctor --json printed the credential"
    c = _linha(rel, "GEMINI_API_KEY")
    assert c["status"] == "ok" and "oculto" in c["summary"]


def test_portas_ocupadas_sao_aviso(saude, capsys, monkeypatch):
    monkeypatch.setattr(doctor_cmd, "porta_livre", lambda porta, *a, **kw: porta != 3000)
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "ports")
    assert rc == 0 and c["status"] == "warn" and "3000" in c["summary"]


def test_o_runtime_e_sempre_ok_com_ou_sem_ele(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "runtime")
    assert c["status"] == "ok" and c["detail"]["found"] is False and "opcional" in c["summary"]
    saude.caixa.runtime()
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "runtime")
    assert c["status"] == "ok" and c["detail"]["found"] is True and c["detail"]["version"] == "3.10.0"


def test_a_linha_distribution_diz_como_foi_instalado(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "distribution")
    assert c["status"] == "ok" and c["detail"]["kind"] == "source" and __version__ in c["detail"]["version"]


# --- update: offline by default, the cache of the last `update --check` ----------------------------------------------


def test_update_sem_cache_e_ok_e_diz_como_checar(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "update")
    assert c["status"] == "ok" and "update --check" in c["summary"]


def test_update_le_o_cache_sem_rede_e_avisa_quando_ha_versao_nova(saude, capsys, monkeypatch):
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: pytest.fail("offline doctor must not ask GitHub"))
    update_cmd.write_check({"installed": "0.4.0", "latest": "99.0.0", "update_available": True, "kind": "source"})
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "update")
    assert rc == 0 and c["status"] == "warn" and "99.0.0" in c["summary"] and c["fix"] == "simplicio-video update"
    assert c["detail"]["update_available"] is True


def test_update_com_cache_em_dia_e_ok(saude, capsys):
    update_cmd.write_check({"installed": __version__, "latest": __version__, "update_available": False, "kind": "source"})
    rc, rel, _, _ = _json(capsys)
    assert _linha(rel, "update")["status"] == "ok"


def test_online_pergunta_ao_github_e_regrava_o_cache(saude, capsys, monkeypatch):
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: "v99.1.0")
    rc, rel, _, _ = _json(capsys, "--online")
    c = _linha(rel, "update")
    assert rc == 0 and c["status"] == "warn" and "99.1.0" in c["summary"]
    cache = json.loads((saude.caixa.data / "update-check.json").read_text())
    assert cache["latest"] == "99.1.0" and cache["update_available"] is True and cache["kind"] == "pip"


def test_online_sem_rede_vira_aviso_e_nao_grava_cache(saude, capsys, monkeypatch):
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")

    def sem_rede():
        raise OSError("rede fora")

    monkeypatch.setattr(update_cmd, "fetch_latest_tag", sem_rede)
    rc, rel, _, _ = _json(capsys, "--online")
    c = _linha(rel, "update")
    assert rc == 0 and c["status"] == "warn" and "rede fora" in c["summary"]
    assert not (saude.caixa.data / "update-check.json").exists()


def test_sem_online_o_doctor_nao_escreve_nada(saude, capsys):
    antes = instantanea(saude.caixa.tmp)
    _json(capsys)
    depois = instantanea(saude.caixa.tmp)
    assert depois == antes, "doctor (offline) must not write anything"


# --- doctor all, doctor login ----------------------------------------------------------------------------------------


def test_doctor_login_roda_so_a_linha_do_login(saude, capsys):
    exige_registrado("doctor", capsys, main)
    rc, out, err = executa(["doctor", "login", "--json"], capsys, main)
    rel = json.loads(out)
    assert [c["name"] for c in rel["checks"]] == ["login"] and rc == 0 and rel["status"] == "warn"


def test_doctor_all_e_igual_a_doctor_sem_subcomando(saude, capsys):
    _, a, _, _ = _json(capsys)
    rc, out, err = executa(["doctor", "all", "--json"], capsys, main)
    b = json.loads(out)
    assert [c["name"] for c in a["checks"]] == [c["name"] for c in b["checks"]]


def test_collect_aceita_so_e_devolve_o_documento(saude):
    rel = doctor_cmd.collect(only="login")
    assert rel["schema"] == "simplicio.doctor/v1" and [c["name"] for c in rel["checks"]] == ["login"]
    assert rel["status"] == "warn" and rel["version"] == __version__


# --- text layout ------------------------------------------------------------------------------------------------------


def test_texto_tem_o_layout_do_loop_com_resumo_em_portugues(saude, capsys):
    exige_registrado("doctor", capsys, main)
    rc, out, err = executa(["doctor"], capsys, main)
    linhas = out.splitlines()
    assert linhas[0] == "simplicio-video doctor: warn"
    assert any(l.startswith("  ok    python") for l in linhas), out
    assert any(l.startswith("  warn  login") for l in linhas), out
    assert "        fix: simplicio-video login" in linhas
    saida_cp1252(out, err)


def test_texto_sem_ffmpeg_sai_com_1_e_mostra_a_correcao(saude, capsys):
    _tira(saude, "ffmpeg")
    rc, out, err = executa(["doctor"], capsys, main)
    assert rc == 1 and "fail" in out.splitlines()[0] and "ffmpeg" in out.lower() and "fix:" in out


def test_nenhum_modo_imprime_token_nem_email_com_um_login_presente(saude, capsys, monkeypatch):
    for nome, valor in LEAKY_ENV.items():
        monkeypatch.setenv(nome, valor)
    put_login(saude.caixa.login)
    saude.caixa.runtime()
    rc, out, err = executa(["doctor"], capsys, main)
    assert_no_secret(out, err)
    rc, rel, out, err = _json(capsys)
    assert_no_secret(out, err)
    assert "w***@example.org" in _linha(rel, "login")["summary"]


# --- macOS, Windows and an installed package -------------------------------------------------------------------------


def test_no_macos_o_ffmpeg_e_o_node_do_homebrew_sao_achados_fora_do_path(saude, capsys, simula_so, monkeypatch):
    """GUI and ssh sessions on macOS often lack /opt/homebrew/bin on PATH; the doctor looks there too."""
    if so_incompativel("darwin"):
        pytest.skip("a real Windows only has .cmd launchers")
    simula_so("darwin")
    brew = saude.caixa.tmp / "opt" / "homebrew" / "bin"
    write_fake_tool(brew, "node", "v22.11.0\n")
    write_fake_tool(brew, "ffmpeg", FFMPEG_COM_LIBASS)
    _tira(saude, "node")
    _tira(saude, "ffmpeg")
    monkeypatch.setattr(hostos, "EXTRA_TOOL_DIRS", {"darwin": [str(brew)]}, raising=True)
    rc, rel, _, _ = _json(capsys)
    assert _linha(rel, "node")["status"] == "ok" and _linha(rel, "ffmpeg")["status"] == "ok"
    assert str(brew) in _linha(rel, "ffmpeg")["summary"] or str(brew) in json.dumps(_linha(rel, "ffmpeg")["detail"])


def test_no_linux_o_homebrew_nao_entra_na_busca(simula_so):
    simula_so("linux")
    assert hostos.extra_tool_dirs() == []
    simula_so("win32")
    assert hostos.extra_tool_dirs() == []
    simula_so("darwin")
    assert hostos.extra_tool_dirs() == ["/opt/homebrew/bin", "/usr/local/bin"]


@pytest.mark.parametrize("so,trecho", [("darwin", "brew install ffmpeg"), ("linux", "apt install ffmpeg"),
                                         ("win32", "winget install Gyan.FFmpeg")])
def test_a_correcao_do_ffmpeg_e_a_do_sistema(saude, capsys, simula_so, so, trecho):
    simula_so(so)
    _tira(saude, "ffmpeg")
    rc, rel, _, _ = _json(capsys)
    c = _linha(rel, "ffmpeg")
    assert c["status"] == "fail" and trecho in c["fix"]


def test_no_windows_o_node_e_achado_como_exe(saude, capsys, simula_so):
    simula_so("win32")
    _tira(saude, "node")
    write_fake_tool(saude.caixa.bin, "node", "v22.11.0\n", ext=".exe")
    rc, rel, _, _ = _json(capsys)
    assert _linha(rel, "node")["status"] == "ok"


def test_num_pacote_instalado_o_disco_e_medido_na_pasta_de_dados_e_nao_no_site_packages(saude, capsys, monkeypatch):
    site = saude.caixa.tmp / "site-packages" / "simplicio_video" / "data"
    site.mkdir(parents=True)
    from simplicio_video import paths
    monkeypatch.setattr(paths, "home", lambda start=None: site)
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    rc, rel, out, err = _json(capsys)
    assert _linha(rel, "distribution")["detail"]["kind"] == "pip"
    assert str(site) not in out + err, "an installed package must not show site-packages as a checkout"
    assert all(not m.startswith(str(site)) for m in saude.medidos)

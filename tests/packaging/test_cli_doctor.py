"""Contract of `simplicio-video doctor [all] [--json] [--online]`: the loop's `simplicio.doctor/v1`.

JSON (stdout with --json):
  {"schema": "simplicio.doctor/v1", "status": "ok|warn|fail" (the worst), "version": str,
   "checks": [{"name": str, "status": "ok|warn|fail", "summary": str, "fix": str|null, "detail": {...}}, ...]}
Sections, in order: update, distribution, runtime, python, node, ffmpeg, ffmpeg-libass, disk, ports, GEMINI_API_KEY,
setup. Exit 1 only when a check is `fail`. A missing workspace and a missing GEMINI_API_KEY are `warn`.
No token is ever printed.

Environment (fixture `saude`): HOME, PATH and the workspace are sealed under tmp_path (see _caixa.py); `node` and `ffmpeg`
are fake programs on that PATH (so the same tests run on Windows too), the disk and the ports are injected. A real
ffmpeg, node or Runtime is never touched.
"""
from __future__ import annotations

import json
import os

import pytest

import _caixa
from _caixa import (FFMPEG_COM_LIBASS, FFMPEG_SEM_LIBASS, SENTINELA, distribution, doctor_cmd, hostos, posix_real, saida_cp1252,
                    so_incompativel, update_cmd, write_fake_tool)
from _comum import erros_de_schema, executa, exige_registrado, instantanea
from simplicio_video import __version__
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
saude = _caixa.saude
simula_so = _caixa.simula_so

GB = 1024**3
SECOES = ["update", "distribution", "runtime", "python", "node", "ffmpeg", "ffmpeg-libass", "disk", "ports",
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


def test_ambiente_saudavel_fica_ok_sem_nenhum_aviso(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    assert rc == 0 and rel["status"] == "ok"
    assert [c["name"] for c in rel["checks"] if c["status"] != "ok"] == []


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
    antes = instantanea(saude.caixa.home)
    _json(capsys)
    assert instantanea(saude.caixa.home) == antes, "doctor (offline) must not write to HOME"
    assert not saude.caixa.data.exists(), "doctor (offline) must not write the update cache"


# --- doctor all ----------------------------------------------------------------------------------------


def test_doctor_all_e_igual_a_doctor_sem_subcomando(saude, capsys):
    _, a, _, _ = _json(capsys)
    rc, out, err = executa(["doctor", "all", "--json"], capsys, main)
    b = json.loads(out)
    assert [c["name"] for c in a["checks"]] == [c["name"] for c in b["checks"]]


def test_collect_aceita_so_e_devolve_o_documento(saude):
    rel = doctor_cmd.collect(only="update")
    assert rel["schema"] == "simplicio.doctor/v1" and [c["name"] for c in rel["checks"]] == ["update"]
    assert rel["status"] == "ok" and rel["version"] == __version__


# --- text layout ------------------------------------------------------------------------------------------------------


def test_texto_tem_o_layout_do_loop_com_resumo_em_portugues(saude, capsys):
    exige_registrado("doctor", capsys, main)
    rc, out, err = executa(["doctor"], capsys, main)
    linhas = out.splitlines()
    assert linhas[0] == "simplicio-video doctor: ok"
    assert any(l.startswith("  ok    python") for l in linhas), out
    assert any(l.startswith("  ok    update") for l in linhas), out
    saida_cp1252(out, err)


def test_texto_sem_ffmpeg_sai_com_1_e_mostra_a_correcao(saude, capsys):
    _tira(saude, "ffmpeg")
    rc, out, err = executa(["doctor"], capsys, main)
    assert rc == 1 and "fail" in out.splitlines()[0] and "ffmpeg" in out.lower() and "fix:" in out


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


# --- a corrupt or hostile update-check.json must not take the doctor down; only the schema's keys are copied -----------------


def _cache(**sobre) -> str:
    """The text of an update-check.json: the values are raw JSON fragments, None leaves the key out."""
    base = {"installed": '"0.4.0"', "latest": '"99.0.0"', "update_available": "true", "kind": '"source"',
            "checked_at": "1700000000"}
    base.update(sobre)
    return "{" + ", ".join(f'"{nome}": {valor}' for nome, valor in base.items() if valor is not None) + "}"


def _escreve_cache(saude, bruto: str) -> None:
    saude.caixa.data.mkdir(parents=True, exist_ok=True)
    (saude.caixa.data / "update-check.json").write_text(bruto, encoding="utf-8")


CACHES_INVALIDOS = {
    "checked_at_texto": _cache(checked_at='"yesterday"'),
    "checked_at_enorme": _cache(checked_at="1e20"),
    "checked_at_infinito": _cache(checked_at="1e999"),
    "checked_at_lista": _cache(checked_at="[1]"),
    "checked_at_booleano": _cache(checked_at="true"),
    "checked_at_negativo": _cache(checked_at="-5"),
    "checked_at_nulo": _cache(checked_at="null"),
    "checked_at_ausente": _cache(checked_at=None),
    "checked_at_depois_do_ano_9999": _cache(checked_at="253402300800"),
    "checked_at_decimal": _cache(checked_at="1.5"),
    "checked_at_texto_gigante": _cache(checked_at='"' + "9" * 5000 + '"'),
    "latest_com_escape_ansi": _cache(latest='"\\u001b[31m99.0.0"'),
    "latest_numero": _cache(latest="99"),
    "latest_lista": _cache(latest='["99.0.0"]'),
    "latest_sem_versao": _cache(latest='"latest"'),
    "latest_nulo": _cache(latest="null"),
    "latest_ausente": _cache(latest=None),
    "latest_com_argumento_do_pip": _cache(latest='"99.0.0 --index-url=http://evil.invalid"'),
    "nao_e_objeto": "[1]", "texto": '"x"', "vazio": "", "nao_e_json": "not json", "aninhado": "[" * 100_000,
}


@pytest.mark.parametrize("nome", sorted(CACHES_INVALIDOS))
def test_cache_do_update_invalido_e_aviso_com_a_dica_e_nunca_excecao(saude, nome):
    _escreve_cache(saude, CACHES_INVALIDOS[nome])
    linha = doctor_cmd.collect(only="update")["checks"][0]
    assert linha["name"] == "update" and linha["status"] == "warn", linha
    assert linha["fix"] == "simplicio-video update --check" and "inválid" in linha["summary"]
    assert linha["detail"] == {}, "nothing of a corrupt file is copied into the document"
    for lixo in ("\x1b", "--index-url", "evil", "yesterday"):
        assert lixo not in linha["summary"], f"{lixo!r} of the corrupt file reached the summary"


@pytest.mark.parametrize("nome", ["checked_at_texto", "checked_at_enorme", "checked_at_lista", "latest_com_escape_ansi", "aninhado"])
def test_o_doctor_inteiro_sobrevive_ao_cache_invalido_em_texto_e_em_json(saude, capsys, nome):
    _escreve_cache(saude, CACHES_INVALIDOS[nome])
    rc, rel, out, err = _json(capsys)
    assert rc == 0 and len(rel["checks"]) == 11, "the eleven checks must not be lost to one corrupt cache"
    assert _linha(rel, "update")["status"] == "warn" and erros_de_schema("doctor", rel) == []
    rc, out, err = executa(["doctor"], capsys, main)
    assert rc == 0 and "Traceback" not in out + err and "\x1b" not in out + err and "warn  update" in out


def test_o_detail_do_update_so_tem_as_chaves_do_schema_e_nao_repete_segredo(saude, capsys):
    """A cache with an `access_token` key used to be copied whole: the document broke its own schema and repeated the value."""
    _escreve_cache(saude, _cache(commits_behind="3", access_token='"fake-secret-tok-1"', refresh_token='"fake-secret-tok-2"',
                                 zzz='{"fundo": [1, 2]}'))
    rc, rel, out, err = _json(capsys)
    detail = _linha(rel, "update")["detail"]
    assert set(detail) <= {"installed", "latest", "update_available", "kind", "commits_behind", "checked_at"}, detail
    assert detail["latest"] == "99.0.0" and detail["commits_behind"] == 3 and detail["checked_at"] == 1700000000
    assert "fake-secret-tok" not in out + err and erros_de_schema("doctor", rel) == []


def test_o_resumo_do_update_usa_a_versao_normalizada_e_nao_o_texto_do_arquivo(saude):
    _escreve_cache(saude, _cache(latest='" v99.0.0\\n"'))
    linha = doctor_cmd.collect(only="update")["checks"][0]
    assert linha["status"] == "warn" and "-> 99.0.0 " in linha["summary"] and "\n" not in linha["summary"]
    assert linha["detail"]["latest"] == "99.0.0"


def test_cache_valido_ate_o_ano_9999_aparece_com_a_data(saude):
    _escreve_cache(saude, _cache(checked_at="253402300799"))
    linha = doctor_cmd.collect(only="update")["checks"][0]
    assert linha["status"] == "warn" and "9999-12-31T23:59:59Z" in linha["summary"]


@posix_real
def test_node_e_ffmpeg_com_saida_que_nao_e_utf8_nao_derrubam_o_doctor(saude, capsys):
    """On Windows the output of a program is decoded with the console codec; here a byte UTF-8 cannot read (0xCD, Latin-1 `Í`)."""
    for nome, saida in (("node", "v22.11.0 \\315\\n"),
                        ("ffmpeg", "ffmpeg version 7.0.2 \\315 Copyright\\nconfiguration: --enable-libass\\n")):
        alvo = saude.caixa.bin / nome
        alvo.write_bytes(f"#!/bin/sh\nprintf '{saida}'\n".encode())
        alvo.chmod(0o755)
    rc, rel, out, err = _json(capsys)
    assert rc == 0 and "Traceback" not in out + err
    assert [_linha(rel, n)["status"] for n in ("node", "ffmpeg", "ffmpeg-libass")] == ["ok", "ok", "ok"]


@pytest.mark.parametrize("instalada", ["0.5.0.dev1", "0.5.0rc1", "0.5.0a2", "0.5.0b1"])
def test_instalada_de_desenvolvimento_ou_pre_release_tem_atualizacao_frente_a_release_final(saude, instalada):
    """PEP 440: `0.5.0rc1` is OLDER than `0.5.0` (it used to read as "em dia")."""
    _escreve_cache(saude, _cache(latest='"0.5.0"', update_available="false"))
    linha = doctor_cmd.collect(only="update", installed=instalada)["checks"][0]
    assert linha["status"] == "warn" and "atualização disponível" in linha["summary"], linha
    assert linha["detail"]["update_available"] is True and linha["detail"]["latest"] == "0.5.0"


@pytest.mark.parametrize("instalada", ["0.5.0", "0.5.0+local", "0.5.0.post1", "0.6.0rc1"])
def test_instalada_final_local_post_ou_mais_nova_esta_em_dia_no_doctor(saude, instalada):
    _escreve_cache(saude, _cache(latest='"0.5.0"', update_available="true"))
    linha = doctor_cmd.collect(only="update", installed=instalada)["checks"][0]
    assert linha["status"] == "ok" and linha["detail"]["update_available"] is False, linha

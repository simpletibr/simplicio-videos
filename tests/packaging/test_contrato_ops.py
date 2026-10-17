"""The JSON contracts of the operations commands: six packaged schemas, and every `--json` output validates against them.

Schemas live in src/simplicio_video/data/schemas/cli/ (Draft 2020-12, like the five that already exist):
  doctor.schema.json         simplicio.doctor/v1        (the loop's id)
  login.schema.json          simplicio.login/v1         (the loop's id)
  logout.schema.json         simplicio.logout/v1        (the loop's id)
  auth-status.schema.json    simplicio.auth-status/v1   (the loop's id; forbids access_token and refresh_token)
  update-check.schema.json   the state file `update-check.json` (installed, latest, update_available, kind, checked_at)
  install-result.schema.json simplicio.video-install/v1 (the video's own: `install` here is the .venv, not the host skills)
Everything is FAKE: tokens, e-mail, Runtime. HOME and PATH are sealed (see _caixa.py).
"""
from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

import _caixa
from _caixa import (FAKE_ACCESS, FAKE_REFRESH, distribution, login_cmd, login_doc, posix_real, put_login,
                    update_cmd)
from _comum import ROOT, executa
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
saude = _caixa.saude
simula_so = _caixa.simula_so

SCHEMAS = ROOT / "src" / "simplicio_video" / "data" / "schemas" / "cli"
IDS_DO_LOOP = {
    "doctor": "simplicio.doctor/v1", "login": "simplicio.login/v1", "logout": "simplicio.logout/v1",
    "auth-status": "simplicio.auth-status/v1",
}
NOVOS = ["doctor", "login", "logout", "auth-status", "update-check", "install-result"]
# What `auth.describe()` of simplicio-loop (2034e2d, auth.py:438-465) can put in an auth-status document.
CHAVES_DO_AUTH_STATUS_DO_LOOP = {
    "schema", "logged_in", "reason_code", "fix", "detail", "path", "runtime_path", "shared_with_runtime", "runtime",
    "email", "access_expires_at", "access_expired", "refresh_expires_at", "refresh_expired", "has_refresh_token",
    "entitlement",
}


def schema(nome: str) -> dict:
    return json.loads((SCHEMAS / f"{nome}.schema.json").read_text(encoding="utf8"))


def erros(nome: str, dados) -> list[str]:
    return [e.message for e in Draft202012Validator(schema(nome)).iter_errors(dados)]


def valida(nome: str, dados) -> None:
    assert erros(nome, dados) == [], f"{nome}: {json.dumps(dados, ensure_ascii=False)[:300]}"


# --- the files -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", NOVOS)
def test_o_schema_existe_e_e_draft_2020_12_valido(nome):
    dados = schema(nome)
    Draft202012Validator.check_schema(dados)
    assert dados["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert dados["type"] == "object" and dados.get("description"), "every schema describes itself"


@pytest.mark.parametrize("nome,ident", sorted(IDS_DO_LOOP.items()))
def test_o_id_e_o_mesmo_do_loop(nome, ident):
    assert schema(nome)["$id"] == ident
    assert schema(nome)["properties"]["schema"] == {"const": ident}


def test_os_ids_do_install_e_o_estado():
    assert schema("install-result")["$id"] == "simplicio.video-install/v1"
    assert schema("install-result")["properties"]["schema"] == {"const": "simplicio.video-install/v1"}
    assert "$id" not in schema("update-check"), "a state file without a `schema` key has no $id (the loop's has none either)"


@pytest.mark.parametrize("nome", NOVOS)
def test_nenhum_schema_aceita_chave_desconhecida(nome):
    assert schema(nome)["additionalProperties"] is False


def test_as_chaves_do_auth_status_sao_as_do_loop():
    assert set(schema("auth-status")["properties"]) == CHAVES_DO_AUTH_STATUS_DO_LOOP


def test_o_login_estende_o_auth_status_com_as_chaves_do_loop():
    props = set(schema("login")["properties"])
    assert CHAVES_DO_AUTH_STATUS_DO_LOOP <= props
    assert props - CHAVES_DO_AUTH_STATUS_DO_LOOP == {"status", "runtime_exit_code", "sign_in_url", "user_code", "install",
                                                    "install_doc"}
    assert set(schema("login")["properties"]["status"]["enum"]) == {"VERIFIED", "NOT_VERIFIED", "UNVERIFIED", "REFUSED"}


def test_o_logout_tem_as_chaves_e_os_status_do_loop():
    assert set(schema("logout")["properties"]) == {"schema", "status", "path", "runtime_path", "also_logs_out_runtime",
                                                  "reason_code", "detail"}
    assert set(schema("logout")["properties"]["status"]["enum"]) == {"REFUSED", "FAILED", "LOGGED_OUT", "NO_LOGIN"}


# --- a token can never be in these documents --------------------------------------------------------------------------


BASE_AUTH = {"schema": "simplicio.auth-status/v1", "logged_in": False, "reason_code": "login_missing",
             "fix": "simplicio-video login", "path": "/h/.simplicio/login.json", "runtime_path": "/h/.simplicio/login.json",
             "shared_with_runtime": True, "runtime": {"found": False, "path": None, "version": None}}


@pytest.mark.parametrize("nome", ["auth-status", "login", "logout", "doctor"])
@pytest.mark.parametrize("chave", ["access_token", "refresh_token", "id_token", "token"])
def test_o_schema_proibe_chave_de_token_em_qualquer_lugar(nome, chave):
    base = {"auth-status": BASE_AUTH,
            "login": {**BASE_AUTH, "schema": "simplicio.login/v1", "status": "UNVERIFIED"},
            "logout": {"schema": "simplicio.logout/v1", "status": "NO_LOGIN", "path": "p", "runtime_path": "p",
                       "also_logs_out_runtime": True},
            "doctor": {"schema": "simplicio.doctor/v1", "status": "ok", "version": "1", "checks": []}}[nome]
    valida(nome, base)
    assert erros(nome, {**base, chave: FAKE_ACCESS}), f"{nome} accepted a `{chave}` key"


def test_o_schema_do_auth_status_diz_no_proprio_texto_que_proibe_os_dois_tokens():
    texto = json.dumps(schema("auth-status"))
    assert "access_token" in texto and "refresh_token" in texto
    assert schema("auth-status")["propertyNames"] == {"not": {"enum": ["access_token", "refresh_token"]}}
    assert schema("login")["propertyNames"] == {"not": {"enum": ["access_token", "refresh_token"]}}


def test_o_runtime_do_auth_status_nao_aceita_token_dentro_dele():
    sujo = {**BASE_AUTH, "runtime": {"found": True, "path": "/x", "version": "3.10.0", "access_token": FAKE_ACCESS}}
    assert erros("auth-status", sujo)


# --- documents that must be refused ----------------------------------------------------------------------------------


def test_o_doctor_antigo_nao_e_mais_valido():
    antigo = {"ok": True, "checks": [{"name": "python", "status": "ok", "detail": "Python 3.12", "fix": None}]}
    assert erros("doctor", antigo)


def test_o_doctor_exige_detail_objeto_e_status_conhecido():
    base = {"schema": "simplicio.doctor/v1", "status": "ok", "version": "0.4.0",
            "checks": [{"name": "python", "status": "ok", "summary": "Python 3.12", "fix": None, "detail": {}}]}
    valida("doctor", base)
    base["checks"][0]["detail"] = "texto"
    assert erros("doctor", base)
    base["checks"][0]["detail"] = {}
    base["checks"][0]["status"] = "aviso"
    assert erros("doctor", base)
    base["checks"][0]["status"] = "ok"
    base["status"] = "mal"
    assert erros("doctor", base)


def test_o_estado_so_aceita_commits_behind_no_source():
    base = {"installed": "0.4.0", "latest": "0.5.0", "update_available": True, "kind": "pip", "checked_at": 1}
    valida("update-check", base)
    assert erros("update-check", {**base, "commits_behind": 2}), "commits_behind only exists for kind=source"
    valida("update-check", {**base, "kind": "source", "commits_behind": 2})
    assert erros("update-check", {**base, "kind": "binary"}), "there is no binary distribution"


def test_o_resultado_do_install_exige_as_chaves_e_o_python_no_formato():
    base = {"schema": "simplicio.video-install/v1", "version": "0.4.0", "up_to_date": False, "pending": ["x"],
            "conflict": None, "python": "3.12", "extras": [], "distribution": "source"}
    valida("install-result", base)
    assert erros("install-result", {**base, "python": "tres"})
    assert erros("install-result", {**base, "distribution": "binary"})
    assert erros("install-result", {k: v for k, v in base.items() if k != "pending"})


def test_o_logout_aceita_o_motivo_not_a_login_file_e_o_detalhe_na_recusa():
    base = {"schema": "simplicio.logout/v1", "status": "REFUSED", "path": "p", "runtime_path": "p", "also_logs_out_runtime": True,
            "reason_code": "not_a_login_file", "detail": "p não tem a forma de um login; nada foi apagado"}
    valida("logout", base)
    assert erros("logout", {**base, "reason_code": "qualquer_coisa"})


def test_o_resultado_do_install_com_erro_traz_error_e_so_o_que_se_sabe():
    """An error document (a bad --python, no uv, a conflicting .venv...): `error` plus whatever the install already knew."""
    minimo = {"schema": "simplicio.video-install/v1", "version": "0.4.0", "distribution": "source", "error": "extra inválido"}
    valida("install-result", minimo)
    valida("install-result", {**minimo, "python": "3.12", "extras": [], "pending": ["x"], "conflict": None, "up_to_date": False})
    assert erros("install-result", {k: v for k, v in minimo.items() if k != "error"}), "no error and no plan: not a document"
    assert erros("install-result", {**minimo, "error": ""}) and erros("install-result", {**minimo, "error": 3})
    assert erros("install-result", {**minimo, "python": "tres"}), "what is there still has to fit"
    assert erros("install-result", {**minimo, "up_to_date": True}), "an error is never up to date"


# --- the real outputs validate ---------------------------------------------------------------------------------------


def _doc(capsys, *argv):
    rc, out, err = executa(list(argv), capsys, main)
    return rc, json.loads(out), out + err


def test_auth_status_real_valida(caixa, capsys):
    rc, doc, texto = _doc(capsys, "auth", "status", "--json")
    valida("auth-status", doc)
    put_login(caixa.login)
    caixa.runtime()
    rc, doc, texto = _doc(capsys, "auth", "status", "--json")
    valida("auth-status", doc)
    assert doc["logged_in"] is True and FAKE_ACCESS not in texto and FAKE_REFRESH not in texto
    put_login(caixa.login, login_doc(access_expires_at=1, refresh_token="", refresh_token_expires_at=0))
    valida("auth-status", _doc(capsys, "auth", "status", "--json")[1])


@posix_real
def test_auth_status_de_permissao_frouxa_valida(caixa, capsys):
    put_login(caixa.login, mode=0o644)
    rc, doc, _ = _doc(capsys, "auth", "status", "--json")
    valida("auth-status", doc)
    assert doc["reason_code"] == "login_permissions"


def test_login_real_valida_em_todos_os_status(caixa, capfd, simula_so):
    # UNVERIFIED: no Runtime on the sealed PATH
    assert login_cmd.login(as_json=True) == 1
    doc = json.loads(capfd.readouterr().out)
    valida("login", doc)
    assert doc["status"] == "UNVERIFIED"
    # VERIFIED and NOT_VERIFIED: the fake Runtime
    caixa.runtime()
    assert login_cmd.login(as_json=True) == 0
    doc = json.loads(capfd.readouterr().out)
    valida("login", doc)
    assert doc["status"] == "VERIFIED"
    caixa.login.unlink()
    caixa.runtime(writes=False, exit_code=7)
    assert login_cmd.login(as_json=True) == 1
    doc = json.loads(capfd.readouterr().out)
    valida("login", doc)
    assert doc["status"] == "NOT_VERIFIED"
    # REFUSED: --no-browser on Windows
    simula_so("win32")
    caixa.runtime(launcher_name="simplicio.exe")
    assert login_cmd.login(as_json=True, no_browser=True) == 2
    doc = json.loads(capfd.readouterr().out)
    valida("login", doc)
    assert doc["status"] == "REFUSED"


def test_logout_real_valida_em_todos_os_status(caixa, capsys):
    put_login(caixa.login)
    for argv, status in ((["logout", "--json"], "REFUSED"), (["logout", "--yes", "--json"], "LOGGED_OUT"),
                         (["logout", "--yes", "--json"], "NO_LOGIN")):
        rc, doc, _ = _doc(capsys, *argv)
        valida("logout", doc)
        assert doc["status"] == status
    caixa.login.mkdir(parents=True)  # not a login file: refused (exit 2), not a failure
    rc, doc, _ = _doc(capsys, "logout", "--yes", "--json")
    valida("logout", doc)
    assert doc["status"] == "REFUSED" and doc["reason_code"] == "not_a_login_file" and rc == 2


def test_doctor_real_valida_saudavel_e_doente(saude, capsys):
    rc, doc, _ = _doc(capsys, "doctor", "--json")
    valida("doctor", doc)
    for f in saude.caixa.bin.glob("*ffmpeg*"):
        f.unlink()
    put_login(saude.caixa.login)
    rc, doc, _ = _doc(capsys, "doctor", "--json")
    valida("doctor", doc)
    assert doc["status"] == "fail"
    rc, doc, _ = _doc(capsys, "doctor", "login", "--json")
    valida("doctor", doc)


def test_install_real_valida_check_dry_run_e_pacote_instalado(caixa, capsys, monkeypatch):
    repo = caixa.tmp / "checkout"
    repo.mkdir()
    for nome in ("pyproject.toml", "plugin.json"):
        (repo / nome).write_text((ROOT / nome).read_text(encoding="utf8"), encoding="utf8")
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(repo))
    monkeypatch.setattr(distribution, "kind", lambda **kw: "source")
    for opcao in ("--check", "--dry-run"):
        rc, doc, _ = _doc(capsys, "install", opcao, "--json")
        valida("install-result", doc)
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    rc, doc, _ = _doc(capsys, "install", "--check", "--json")
    valida("install-result", doc)
    assert doc["distribution"] == "pip"


def test_o_estado_gravado_pelo_update_valida(caixa, capsys, monkeypatch):
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: "v99.0.0")
    assert executa(["update", "--check"], capsys, main)[0] == 10
    valida("update-check", json.loads((caixa.data / "update-check.json").read_text()))

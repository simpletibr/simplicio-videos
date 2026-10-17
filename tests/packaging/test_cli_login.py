"""`simplicio-video login | logout | auth status`: a mirror of the simplicio-loop commands (2034e2d), same JSON, same codes.

The video CLI never signs in by itself: `login` runs the Runtime (`simplicio login google`) and then reads the shared file
`~/.simplicio/login.json` (or SIMPLICIO_AUTH_FILE). It stores no credential, unlocks nothing and charges nothing.
A fake Runtime stands in for `simplicio` (see _caixa.py); HOME, USERPROFILE and PATH are under tmp_path, and a tripwire
refuses to start any Runtime outside tmp_path. Every token and e-mail is FAKE.
"""
from __future__ import annotations

import json
import os
import stat


import _caixa
from _caixa import (LEAKY_ENV, MASKED, SECRETS, assert_no_secret, login_cmd, login_doc, posix_real, put_login,
                    saida_cp1252)
from _comum import executa, exige_registrado
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa

INSTALL_SH = "curl -fsSL https://raw.githubusercontent.com/simpletibr/simplicio/master/install.sh | sh"
INSTALL_PS1 = "irm https://raw.githubusercontent.com/simpletibr/simplicio/master/install.ps1 | iex"
INSTALL_DOC = "https://github.com/simpletibr/simplicio-runtime/blob/main/INSTALL.md"


def saida(capfd):
    return capfd.readouterr()


# --- login -----------------------------------------------------------------------------------------------------------


def test_login_delega_ao_runtime_e_confere_o_arquivo_compartilhado(caixa, capfd):
    caixa.runtime()
    rc = login_cmd.login()
    out, err = saida(capfd)
    assert rc == 0
    assert caixa.log.read_text().startswith("argv: login google\n"), "the Runtime must get exactly `login google`"
    assert caixa.login.is_file()
    for esperado in ("verificado", MASKED, "3.10.0", str(caixa.login)):
        assert esperado in out, esperado
    assert "https://example.invalid/device" in out  # the Runtime talks to the terminal untouched
    assert_no_secret(out, err)
    saida_cp1252(out, err)


@posix_real
def test_o_arquivo_que_o_runtime_gravou_e_privado(caixa, capfd):
    caixa.runtime()
    assert login_cmd.login() == 0
    assert stat.S_IMODE(caixa.login.stat().st_mode) == 0o600


def test_login_json_mantem_o_stdout_um_unico_documento(caixa, capfd):
    caixa.runtime()
    rc = login_cmd.login(as_json=True)
    out, err = saida(capfd)
    doc = json.loads(out)
    assert rc == 0 and doc["schema"] == "simplicio.login/v1" and doc["status"] == "VERIFIED" and doc["logged_in"] is True
    assert doc["email"] == MASKED and doc["runtime"]["version"] == "3.10.0" and doc["runtime_exit_code"] == 0
    assert "https://example.invalid/device" in err  # the Runtime output went to stderr
    assert "access_token" not in doc and "refresh_token" not in doc
    assert_no_secret(out, err)


def test_login_respeita_simplicio_auth_file_e_o_runtime_grava_la(caixa, capfd, monkeypatch):
    custom = caixa.tmp / "servico" / "login.json"
    custom.parent.mkdir()
    custom.parent.chmod(0o700)
    monkeypatch.setenv("SIMPLICIO_AUTH_FILE", str(custom))
    caixa.runtime()
    assert login_cmd.login(as_json=True) == 0
    doc = json.loads(saida(capfd)[0])
    assert custom.is_file() and not caixa.login.is_file()
    assert f"auth_file: {custom}" in caixa.log.read_text()
    assert doc["path"] == str(custom) and doc["shared_with_runtime"] is True


def test_o_filho_recebe_ambiente_minimo_sem_credenciais_de_outros_programas(caixa, capfd, monkeypatch):
    for nome, valor in LEAKY_ENV.items():
        monkeypatch.setenv(nome, valor)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.invalid:3128")
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    caixa.runtime()
    assert login_cmd.login() == 0
    visto = json.loads(caixa.envlog.read_text())
    for nome, valor in LEAKY_ENV.items():
        assert nome not in visto and valor not in json.dumps(visto), nome
    for preciso in ("PATH", "HOME", "USERPROFILE", "HTTPS_PROXY", "LC_ALL", "SYSTEMROOT"):  # what a sign-in really needs
        assert preciso in visto, preciso
    assert visto["HTTPS_PROXY"] == "http://proxy.example.invalid:3128"


def test_o_filho_nao_recebe_variaveis_desconhecidas(caixa, capfd, monkeypatch):
    monkeypatch.setenv("MINHA_VARIAVEL_QUALQUER", "x")
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(caixa.data))
    caixa.runtime()
    assert login_cmd.login() == 0
    visto = json.loads(caixa.envlog.read_text())
    assert "MINHA_VARIAVEL_QUALQUER" not in visto and "SIMPLICIO_VIDEO_DATA" not in visto


def test_login_nao_mexe_no_ambiente_quando_nao_ha_arquivo_customizado(caixa, capfd):
    caixa.runtime()
    login_cmd.login()
    assert "auth_file: \n" in caixa.log.read_text()


@posix_real
def test_no_browser_pede_ao_runtime_para_nao_abrir_um(caixa, capfd):
    caixa.runtime()
    login_cmd.login(no_browser=True)
    assert "browser: true" in caixa.log.read_text()
    capfd.readouterr()
    login_cmd.login()
    assert "browser: true\n" not in caixa.log.read_text().split("argv: login google")[-1]


def test_login_do_runtime_que_falha_nao_e_verificado(caixa, capfd):
    caixa.runtime(writes=False, exit_code=7)
    rc = login_cmd.login(as_json=True)
    doc = json.loads(saida(capfd)[0])
    assert rc == 1 and doc["status"] == "NOT_VERIFIED" and doc["reason_code"] == "runtime_login_failed"
    assert doc["runtime_exit_code"] == 7 and doc["logged_in"] is False and doc["fix"] == "simplicio-video login"


def test_runtime_que_diz_ok_mas_nao_gravou_login_nao_e_verificado(caixa, capfd):
    caixa.runtime(writes=False)
    rc = login_cmd.login(as_json=True)
    doc = json.loads(saida(capfd)[0])
    assert rc == 1 and doc["status"] == "NOT_VERIFIED" and doc["reason_code"] == "login_missing"


@posix_real
def test_login_que_o_grupo_pode_ler_nao_e_verificado(caixa, capfd):
    caixa.runtime(file_mode=0o644)
    rc = login_cmd.login(as_json=True)
    doc = json.loads(saida(capfd)[0])
    assert rc == 1 and doc["reason_code"] == "login_permissions" and "chmod 600" in doc["fix"]


def test_sem_runtime_o_login_proprio_e_unverified_e_diz_como_instalar(caixa, capfd):
    rc = login_cmd.login()
    out, err = saida(capfd)
    assert rc == 1
    assert "UNVERIFIED" in out and "Runtime" in out
    assert INSTALL_SH in out and INSTALL_PS1 in out and INSTALL_DOC in out
    assert "simplicio-video login" in out
    assert not caixa.login.exists() and not caixa.login.parent.exists()  # nothing was created
    saida_cp1252(out, err)
    capfd.readouterr()
    rc = login_cmd.login(as_json=True)
    doc = json.loads(saida(capfd)[0])
    assert rc == 1 and doc["status"] == "UNVERIFIED" and doc["reason_code"] == "standalone_login_unverified"
    assert doc["runtime"]["found"] is False and doc["install"]["macOS / Linux"] == INSTALL_SH
    assert doc["install"]["Windows (PowerShell)"] == INSTALL_PS1 and doc["install_doc"] == INSTALL_DOC
    assert "runtime_exit_code" not in doc


def test_sem_runtime_um_login_que_ja_existe_continua_sendo_informado(caixa, capfd):
    put_login(caixa.login)
    assert login_cmd.login() == 1
    out, err = saida(capfd)
    assert "UNVERIFIED" in out and "já existe um login utilizável" in out and "auth status" in out
    assert_no_secret(out, err)
    assert login_cmd.login(as_json=True) == 1
    assert json.loads(saida(capfd)[0])["logged_in"] is True


def test_o_login_nao_recebe_token_por_argumento(caixa, capfd):
    caixa.runtime()
    login_cmd.login(as_json=True)
    argvs = [linha for linha in caixa.log.read_text().splitlines() if linha.startswith("argv:")]
    assert argvs == ["argv: login google"]


# --- logout ----------------------------------------------------------------------------------------------------------


def test_logout_sem_yes_nao_apaga_nada_e_avisa_do_runtime(caixa, capfd):
    put_login(caixa.login)
    rc = login_cmd.logout()
    out, err = saida(capfd)
    assert rc == 2 and caixa.login.exists()
    assert "Runtime" in out + err and "--yes" in out + err and str(caixa.login) in out + err
    assert_no_secret(out, err)


def test_logout_sem_yes_json_e_refused(caixa, capfd):
    put_login(caixa.login)
    assert login_cmd.logout(as_json=True) == 2
    doc = json.loads(saida(capfd)[0])
    assert doc["schema"] == "simplicio.logout/v1" and doc["status"] == "REFUSED"
    assert doc["reason_code"] == "confirmation_required" and doc["also_logs_out_runtime"] is True
    assert doc["path"] == str(caixa.login) and caixa.login.exists()


def test_logout_com_yes_remove_o_arquivo_compartilhado(caixa, capfd):
    put_login(caixa.login)
    rc = login_cmd.logout(yes=True)
    out, err = saida(capfd)
    assert rc == 0 and not caixa.login.exists()
    assert "Runtime" in out and "não é revogado" in out
    assert_no_secret(out, err)
    saida_cp1252(out, err)
    rc = login_cmd.logout(yes=True, as_json=True)
    doc = json.loads(saida(capfd)[0])
    assert rc == 0 and doc["status"] == "NO_LOGIN"


def test_logout_json_com_yes(caixa, capfd):
    put_login(caixa.login)
    assert login_cmd.logout(yes=True, as_json=True) == 0
    doc = json.loads(saida(capfd)[0])
    assert doc["status"] == "LOGGED_OUT" and not caixa.login.exists() and doc["also_logs_out_runtime"] is True


def test_logout_sem_login_nao_cria_arquivo_nem_pasta(caixa, capfd):
    assert login_cmd.logout(yes=True, as_json=True) == 0
    assert json.loads(saida(capfd)[0])["status"] == "NO_LOGIN"
    assert not caixa.login.parent.exists(), "NO_LOGIN must write nothing (no lock file either)"


def test_logout_de_algo_que_nao_e_arquivo_de_login_e_erro_e_nao_traceback(caixa, capfd):
    caixa.login.mkdir(parents=True)
    assert login_cmd.logout(yes=True, as_json=True) == 1
    out, err = saida(capfd)
    doc = json.loads(out)
    assert doc["status"] == "FAILED" and doc["reason_code"] == "login_invalid" and "detail" in doc
    assert "Traceback" not in out + err and caixa.login.is_dir()


# --- auth status -----------------------------------------------------------------------------------------------------


def test_status_mostra_conta_expiracao_direitos_e_runtime_sem_nenhum_segredo(caixa, capfd):
    put_login(caixa.login)
    caixa.runtime()
    rc = login_cmd.status()
    out, err = saida(capfd)
    assert rc == 0
    for esperado in (MASKED, "pro", "3.10.0", str(caixa.login), "expira"):
        assert esperado in out, esperado
    assert_no_secret(out, err)
    saida_cp1252(out, err)


def test_status_json_nao_tem_segredo_e_traz_as_chaves_documentadas(caixa, capfd):
    put_login(caixa.login)
    caixa.runtime()
    rc = login_cmd.status(as_json=True)
    out, err = saida(capfd)
    doc = json.loads(out)
    assert rc == 0 and doc["schema"] == "simplicio.auth-status/v1"
    assert doc["logged_in"] is True and doc["reason_code"] == "ok" and doc["email"] == MASKED
    assert doc["access_expired"] is False and doc["entitlement"]["tier"] == "pro"
    assert doc["path"] == str(caixa.login) and doc["shared_with_runtime"] is True
    assert doc["runtime"]["found"] is True and doc["runtime"]["version"] == "3.10.0"
    assert "access_token" not in doc and "refresh_token" not in doc
    assert_no_secret(out, err)


def test_status_de_login_ausente(caixa, capfd):
    rc = login_cmd.status(as_json=True)
    doc = json.loads(saida(capfd)[0])
    assert rc == 1 and doc["logged_in"] is False and doc["reason_code"] == "login_missing"
    assert doc["fix"] == "simplicio-video login"
    rc = login_cmd.status()
    out, _ = saida(capfd)
    assert rc == 1 and "não logado" in out and "simplicio-video login" in out


@posix_real
def test_status_recusa_arquivo_que_outros_leem_e_diz_a_correcao(caixa, capfd):
    put_login(caixa.login, mode=0o644)
    rc = login_cmd.status(as_json=True)
    out, err = saida(capfd)
    doc = json.loads(out)
    assert rc == 1 and doc["reason_code"] == "login_permissions" and doc["fix"] == f"chmod 600 {caixa.login}"
    assert_no_secret(out, err)


def test_status_de_login_expirado(caixa, capfd):
    put_login(caixa.login, login_doc(access_expires_at=1, refresh_token="", refresh_token_expires_at=0))
    rc = login_cmd.status(as_json=True)
    doc = json.loads(saida(capfd)[0])
    assert rc == 1 and doc["reason_code"] == "login_expired" and doc["access_expired"] is True
    put_login(caixa.login, login_doc(access_expires_at=1))  # a living refresh token still makes it usable
    assert login_cmd.status(as_json=True) == 0
    assert json.loads(saida(capfd)[0])["logged_in"] is True


def test_nenhum_modo_imprime_segredo_com_um_login_presente(caixa, capfd, monkeypatch):
    for nome, valor in LEAKY_ENV.items():
        monkeypatch.setenv(nome, valor)
    put_login(caixa.login)
    caixa.runtime()
    for chamada in (lambda: login_cmd.status(), lambda: login_cmd.status(as_json=True), lambda: login_cmd.login(),
                    lambda: login_cmd.login(as_json=True), lambda: login_cmd.logout(), lambda: login_cmd.logout(as_json=True)):
        chamada()
        out, err = saida(capfd)
        assert_no_secret(out, err)
        for segredo in SECRETS:
            assert segredo not in out + err


# --- the command line ------------------------------------------------------------------------------------------------


def test_os_comandos_estao_ligados_no_cli(caixa, capsys):
    for nome in ("login", "logout", "auth"):
        exige_registrado(nome, capsys, main)
    rc, out, _ = executa(["auth", "status", "--json"], capsys, main)
    assert rc == 1 and json.loads(out)["reason_code"] == "login_missing"
    rc, out, err = executa(["logout"], capsys, main)
    assert rc == 2
    rc, out, _ = executa(["logout", "--yes", "--json"], capsys, main)
    assert rc == 0 and json.loads(out)["status"] == "NO_LOGIN"
    rc, out, _ = executa(["login", "--json"], capsys, main)  # no Runtime on the sealed PATH: nothing is started
    assert rc == 1 and json.loads(out)["status"] == "UNVERIFIED"


def test_auth_status_nao_tem_online_porque_o_motor_nao_consome_o_token(caixa, capsys):
    rc, out, err = executa(["auth", "status", "--online"], capsys, main)
    assert rc == 2 and "--online" in err


def test_auth_sem_acao_e_erro_de_uso(caixa, capsys):
    rc, out, err = executa(["auth"], capsys, main)
    assert rc == 2


def test_o_login_nao_entra_no_plugin_nem_no_mcp():
    """The login is a terminal command like `openverse get`: no plugin verb and no MCP tool."""
    from _comum import ROOT
    plugin = (ROOT / "plugin.json").read_text(encoding="utf-8")
    assert "video.login" not in plugin and "video.logout" not in plugin and "video.auth" not in plugin
    mcp = (ROOT / "src" / "simplicio_video" / "mcp_server.py").read_text(encoding="utf-8")
    assert "video.login" not in mcp and "video.auth" not in mcp
    assert "login.json" not in mcp


def test_nenhum_modulo_do_motor_depende_do_login():
    """Nothing in the engine reads the login: only `auth`, the login/doctor commands and hostos know the file."""
    from _comum import ROOT
    quem_le = []
    for arq in (ROOT / "src" / "simplicio_video").rglob("*.py"):
        texto = arq.read_text(encoding="utf-8")
        if "login.json" in texto or "SIMPLICIO_AUTH_FILE" in texto:
            quem_le.append(arq.relative_to(ROOT / "src" / "simplicio_video").as_posix())
    assert sorted(quem_le) == sorted(x for x in quem_le if x in {"auth.py", "commands/login.py", "commands/doctor.py"}), quem_le
    assert os.path.basename(__file__)  # keep `os` used on every host

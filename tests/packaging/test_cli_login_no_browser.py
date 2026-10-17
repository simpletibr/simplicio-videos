"""`simplicio-video login --no-browser`: a Runtime that opens the browser and ignores BROWSER must not open it.

Ported from simplicio-loop tests/test_auth_cli_no_browser.py (2034e2d). The opener stand-ins are POSIX shell scripts, so
those tests run on Linux and macOS only (`posix_real`); the Windows refusal (`no_browser_unsupported`, exit 2) and the
macOS `open` stand-in are exercised here with a simulated system. No real Runtime and no real browser is ever started.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from pathlib import Path

import pytest

import _caixa
from _caixa import login_cmd, posix_real, saida_cp1252

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
simula_so = _caixa.simula_so

# the code is percent-encoded so that it does not appear verbatim in the address
URL = "https://example.test/simplicio/login?user_code=ABCD%2D1234"
CODE = "ABCD-1234"


@pytest.fixture
def sandbox(caixa, monkeypatch):
    """A fake `xdg-open` that records its use, and a Runtime found at /bin/true (the tests inject `run`)."""
    real_bin = caixa.tmp / "real-bin"
    real_bin.mkdir()
    called = caixa.tmp / "xdg-open-called"
    opener = real_bin / "xdg-open"
    opener.write_text(f'#!/bin/sh\necho "$@" > "{called}"\n')
    opener.chmod(0o755)
    monkeypatch.setattr(login_cmd.auth, "runtime_binary", lambda *a, **k: Path("/bin/true"))
    env = {"PATH": f"{real_bin}{os.pathsep}{os.environ['PATH']}", "HOME": str(caixa.home)}
    return env, called


def _runtime_que_abre_o_navegador(command, env, stdout):
    """Imitates Runtime 3.10.0: calls xdg-open and ignores BROWSER."""
    subprocess.call(["xdg-open", URL], env=env)
    return 0


def _nunca(command, env, stdout):
    raise AssertionError("the Runtime must not run")


# --- Windows: the refusal --------------------------------------------------------------------------------------------


def test_no_windows_no_browser_recusa_com_exit_2_e_o_motivo(caixa, simula_so, capsys):
    simula_so("win32")
    caixa.runtime(launcher_name="simplicio.exe")
    code = login_cmd.login(as_json=True, no_browser=True, run=_nunca)
    out = capsys.readouterr().out
    doc = json.loads(out)
    assert code == 2 and doc["status"] == "REFUSED" and doc["reason_code"] == "no_browser_unsupported"
    assert "Runtime" in doc["detail"] and "simplicio-video login" in doc["detail"]
    assert doc["schema"] == "simplicio.login/v1"
    saida_cp1252(out)


def test_no_windows_a_recusa_em_texto_nomeia_o_runtime_e_nao_roda_nada(caixa, simula_so, capsys):
    simula_so("win32")
    caixa.runtime(launcher_name="simplicio.exe")
    code = login_cmd.login(no_browser=True, run=_nunca)
    out = capsys.readouterr().out
    assert code == 2 and out.startswith("login: --no-browser não é suportado") and "Simplicio Runtime" in out
    assert not caixa.log.exists(), "the Runtime was started"


@pytest.mark.parametrize("so", ["linux", "darwin"])
def test_so_o_windows_recusa_no_browser(sandbox, simula_so, so):
    simula_so(so)
    assert login_cmd._can_block_browser() is True
    simula_so("win32")
    assert login_cmd._can_block_browser() is False


def test_no_browser_que_nao_pode_ser_atendido_recusa_com_exit_2(sandbox, monkeypatch, capsys):
    env, called = sandbox
    monkeypatch.setattr(login_cmd, "_can_block_browser", lambda: False)
    code = login_cmd.login(as_json=True, no_browser=True, environ=env, run=_nunca)
    doc = json.loads(capsys.readouterr().out)
    assert code == 2 and doc["reason_code"] == "no_browser_unsupported" and "Runtime" in doc["detail"]
    assert not called.exists()


def test_sem_a_opcao_o_login_roda_no_windows_simulado_sem_shim(caixa, simula_so, capsys):
    """Without --no-browser nothing about the system is special: the Runtime is run by its own absolute path."""
    simula_so("win32")
    caixa.runtime(launcher_name="simplicio.exe")
    seen = {}

    def run(command, env, stdout):
        seen["command"] = command
        seen["env"] = env
        return 0

    login_cmd.login(as_json=True, run=run)
    assert seen["command"][0].endswith("simplicio.exe") and seen["command"][1:] == ["login", "google"]
    assert "BROWSER" not in seen["env"]


# --- POSIX: the stand-ins ---------------------------------------------------------------------------------------------

posix = posix_real


@posix
def test_sem_a_opcao_o_runtime_falso_abre_o_navegador(sandbox):
    env, called = sandbox
    login_cmd.login(as_json=True, environ=env, run=_runtime_que_abre_o_navegador)
    assert called.exists()


@posix
def test_no_browser_nao_chama_o_opener_e_informa_url_e_codigo_em_json(sandbox, capsys):
    env, called = sandbox
    login_cmd.login(as_json=True, no_browser=True, environ=env, run=_runtime_que_abre_o_navegador)
    doc = json.loads(capsys.readouterr().out)
    assert not called.exists()
    assert doc["sign_in_url"] == URL and doc["user_code"] == CODE


@posix
def test_no_browser_informa_url_e_codigo_em_texto(sandbox, capsys):
    env, called = sandbox
    login_cmd.login(no_browser=True, environ=env, run=_runtime_que_abre_o_navegador)
    out = capsys.readouterr().out
    assert not called.exists()
    assert f"Abra este endereço no navegador para entrar: {URL}" in out
    assert f"Código: {CODE}" in out.splitlines()
    saida_cp1252(out)


def _pasta_dos_substitutos(env):
    return Path(env["PATH"].split(os.pathsep)[0])


def _login_json(env, run, capsys):
    code = login_cmd.login(as_json=True, no_browser=True, environ=env, run=run)
    return code, json.loads(capsys.readouterr().out)


def _chamando(*listas):
    """A Runtime that runs the stand-ins by their absolute path, with the given argument lists."""
    def run(command, env, stdout):
        for argv in listas:
            subprocess.call([str(_pasta_dos_substitutos(env) / argv[0]), *argv[1:]], env=env)
        return 0
    return run


@posix
@pytest.mark.parametrize("so", ["linux", "darwin"])
def test_os_substitutos_cobrem_xdg_open_e_no_macos_o_open(sandbox, simula_so, capsys, so):
    simula_so(so)
    env, _ = sandbox
    vistos = {}

    def run(command, child, stdout):
        vistos["nomes"] = sorted(p.name for p in _pasta_dos_substitutos(child).iterdir())
        subprocess.call([str(_pasta_dos_substitutos(child) / "open"), URL], env=child)
        return 0

    _, doc = _login_json(env, run, capsys)
    assert {"xdg-open", "open", "gio"} <= set(vistos["nomes"])
    assert doc["sign_in_url"] == URL, "the `open` stand-in (macOS) must record the address"


@posix
@pytest.mark.parametrize("path", [None, ""])
def test_path_ausente_ou_vazio_nao_deixa_entrada_vazia_nem_roda_nada_do_cwd(caixa, monkeypatch, capsys, path):
    monkeypatch.setattr(login_cmd.auth, "runtime_binary", lambda *a, **k: Path("/bin/true"))
    plantado = caixa.tmp / "cwd"
    plantado.mkdir()
    rodou = caixa.tmp / "planted-ran"
    (plantado / "dirname").write_text(f'#!/bin/sh\necho x > "{rodou}"\n')
    (plantado / "dirname").chmod(0o755)
    env = {"HOME": str(caixa.home)}
    if path is not None:
        env["PATH"] = path
    visto = {}

    def run(command, child, stdout):
        visto["path"] = child["PATH"]
        subprocess.call([str(_pasta_dos_substitutos(child) / "xdg-open"), URL], env=child, cwd=plantado)
        return 0

    _, doc = _login_json(env, run, capsys)
    assert "" not in visto["path"].split(os.pathsep)
    assert not rodou.exists()
    assert doc["sign_in_url"] == URL


@posix
def test_um_path_nao_vazio_e_mantido_depois_dos_substitutos(sandbox, capsys):
    env, _ = sandbox
    visto = {}

    def run(command, child, stdout):
        visto["path"] = child["PATH"]
        return 0

    _login_json(env, run, capsys)
    assert visto["path"].split(os.pathsep)[1:] == env["PATH"].split(os.pathsep)


@posix
@pytest.mark.parametrize("url", ["http://[::1/login?user_code=A", "https://[::1/x"])
def test_endereco_malformado_nao_e_login_nem_quebra(sandbox, capsys, url):
    env, _ = sandbox
    _, doc = _login_json(env, _chamando(["xdg-open", url]), capsys)
    assert "sign_in_url" not in doc and "user_code" not in doc
    assert doc["runtime_exit_code"] == 0 and "status" in doc


@posix
def test_bytes_invalidos_no_arquivo_do_endereco_nao_quebram(sandbox, capsys):
    env, _ = sandbox

    def run(command, child, stdout):
        (_pasta_dos_substitutos(child) / "sign-in-url").write_bytes(b"\xff\xfe")
        return 0

    _, doc = _login_json(env, run, capsys)
    assert "sign_in_url" not in doc and doc["runtime_exit_code"] == 0


def _espiao(visto, interno):
    def run(command, child, stdout):
        visto["dir"] = _pasta_dos_substitutos(child)
        assert visto["dir"].is_dir()
        return interno(command, child, stdout)
    return run


@posix
def test_a_pasta_temporaria_some_depois_do_sucesso(sandbox, capsys):
    env, _ = sandbox
    visto = {}
    _login_json(env, _espiao(visto, _runtime_que_abre_o_navegador), capsys)
    assert not visto["dir"].exists()


@posix
def test_a_pasta_temporaria_some_quando_o_runtime_levanta_excecao(sandbox):
    env, _ = sandbox
    visto = {}

    def explode(command, child, stdout):
        (_pasta_dos_substitutos(child) / "sign-in-url").write_text(URL)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        login_cmd.login(as_json=True, no_browser=True, environ=env, run=_espiao(visto, explode))
    assert not visto["dir"].exists()


def _sentinela(signum, frame):
    raise AssertionError("the sentinel handler must not be called")


@pytest.fixture
def sentinelas():
    """Handlers of our own, so that one leaked by another test cannot hide a missing restore."""
    salvos = {s: signal.signal(s, _sentinela) for s in (signal.SIGTERM, signal.SIGHUP)} if hasattr(signal, "SIGHUP") else {}
    yield
    for s, handler in salvos.items():
        signal.signal(s, handler)


@posix
def test_os_handlers_voltam_depois_do_sucesso(sandbox, sentinelas):
    env, _ = sandbox
    login_cmd.login(as_json=True, no_browser=True, environ=env, run=_runtime_que_abre_o_navegador)
    assert signal.getsignal(signal.SIGTERM) is _sentinela and signal.getsignal(signal.SIGHUP) is _sentinela


@posix
@pytest.mark.parametrize("nome", ["SIGTERM", "SIGHUP"])
def test_sinal_de_termino_apaga_a_pasta_e_devolve_os_handlers(sandbox, sentinelas, nome):
    env, _ = sandbox
    sig = getattr(signal, nome)
    antes = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    visto = {}

    def morto(command, child, stdout):
        (_pasta_dos_substitutos(child) / "sign-in-url").write_text(URL)
        os.kill(os.getpid(), sig)
        raise AssertionError("the signal must interrupt the login")

    with pytest.raises(BaseException) as erro:
        login_cmd.login(as_json=True, no_browser=True, environ=env, run=_espiao(visto, morto))
    assert not isinstance(erro.value, AssertionError)
    assert not visto["dir"].exists()
    assert {s: signal.getsignal(s) for s in antes} == antes


@posix
@pytest.mark.parametrize(("nome", "codigo"), [("SIGTERM", 143), ("SIGHUP", 129)])
def test_sinal_de_termino_encerra_com_128_mais_o_numero(sandbox, sentinelas, nome, codigo):
    env, _ = sandbox
    sig = getattr(signal, nome)

    def morto(command, child, stdout):
        os.kill(os.getpid(), sig)
        raise AssertionError("the signal must interrupt the login")

    with pytest.raises(SystemExit) as erro:
        login_cmd.login(as_json=True, no_browser=True, environ=env, run=morto)
    assert erro.value.code == codigo


@posix
def test_sem_a_opcao_os_handlers_nao_sao_tocados(sandbox):
    env, _ = sandbox
    visto = {}

    def run(command, child, stdout):
        visto["term"] = signal.getsignal(signal.SIGTERM)
        return 0

    antes = signal.getsignal(signal.SIGTERM)
    login_cmd.login(as_json=True, environ=env, run=run)
    assert visto["term"] == antes


@posix
def test_no_browser_funciona_fora_da_thread_principal(sandbox, capsys):
    env, _ = sandbox
    resultado = {}

    def trabalha():
        try:
            resultado["code"] = login_cmd.login(as_json=True, no_browser=True, environ=env,
                                                run=_runtime_que_abre_o_navegador)
        except BaseException as exc:  # noqa: BLE001 - the test reports whatever happened
            resultado["erro"] = exc

    thread = threading.Thread(target=trabalha)
    thread.start()
    thread.join()
    assert "erro" not in resultado
    assert json.loads(capsys.readouterr().out)["sign_in_url"] == URL


@posix
def test_chamadas_sem_endereco_sao_ignoradas_e_o_primeiro_endereco_vence(sandbox, capsys):
    env, _ = sandbox
    run = _chamando(["gio", "mount", "-l"], ["xdg-open", URL], ["gio", "trash", "x"], ["xdg-open", "https://other.test/a"])
    _, doc = _login_json(env, run, capsys)
    assert doc["sign_in_url"] == URL


@posix
def test_chamada_sem_endereco_nao_deixa_login(sandbox, capsys):
    env, _ = sandbox
    _, doc = _login_json(env, _chamando(["gio", "mount", "-l"], ["xdg-open", "file:///etc/passwd"]), capsys)
    assert "sign_in_url" not in doc


@posix
@pytest.mark.parametrize("url", [
    "https://example.test/\x1b]0;pwned\x07",
    "https://example.test/\x1b[2J",
    "https://example.test/a\nFAKE LINE",
    "https://example.test/a b",
    "https://example.test/café",
    "ftp://example.test/a",
])
def test_endereco_que_nao_e_http_ascii_imprimivel_nao_e_endereco(sandbox, capsys, url):
    env, _ = sandbox

    def run(command, child, stdout):  # the stand-in refuses it, and so does the reader of the file
        subprocess.call([str(_pasta_dos_substitutos(child) / "xdg-open"), url], env=child, stderr=subprocess.DEVNULL)
        (_pasta_dos_substitutos(child) / "sign-in-url").write_text(url + "\n", encoding="utf-8")
        return 0

    login_cmd.login(no_browser=True, environ=env, run=run)
    out = capsys.readouterr().out
    assert "\x1b" not in out and "FAKE LINE" not in out and "Abra este endereço" not in out and "Código:" not in out


@posix
def test_o_proprio_substituto_nao_imprime_nada_cru_no_terminal(sandbox, caixa):
    env, _ = sandbox
    err = caixa.tmp / "err"

    def run(command, child, stdout):
        with open(err, "wb") as handle:
            subprocess.call([str(_pasta_dos_substitutos(child) / "xdg-open"), "https://example.test/\x1b[2J"],
                            env=child, stderr=handle)
        return 0

    login_cmd.login(as_json=True, no_browser=True, environ=env, run=run)
    assert b"\x1b" not in err.read_bytes()


@posix
def test_codigo_com_sequencia_de_escape_nao_e_impresso(sandbox, capsys):
    env, _ = sandbox
    url = "https://example.test/login?user_code=%1B%5B2J%0AFAKE"
    login_cmd.login(no_browser=True, environ=env, run=_chamando(["xdg-open", url]))
    out = capsys.readouterr().out
    assert "\x1b" not in out and "FAKE" not in out.replace(url, "")
    assert "Código:" not in out


def _chama_o_opener_pelo_caminho_absoluto_se_ha_display(opener):
    """A Runtime that bypasses PATH: it runs the system opener by its absolute path when a display or session bus is set."""
    def run(command, env, stdout):
        if any(nome in env for nome in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS")):
            subprocess.call([str(opener), URL], env=env)
        return 0
    return run


@posix
def test_no_browser_tira_display_e_barramento_de_sessao_do_ambiente_do_runtime(sandbox, capsys):
    env, _ = sandbox
    env.update(DISPLAY=":0", WAYLAND_DISPLAY="wayland-0", DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/0/bus")
    visto = {}

    def run(command, child, stdout):
        visto.update(child)
        return 0

    _login_json(env, run, capsys)
    assert not {"DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"} & visto.keys()


@posix
def test_no_browser_para_um_opener_chamado_pelo_caminho_absoluto_que_le_o_display(sandbox, capsys):
    env, called = sandbox
    env.update(DISPLAY=":0", DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/0/bus")
    opener = called.parent / "real-bin" / "xdg-open"
    _login_json(env, _chama_o_opener_pelo_caminho_absoluto_se_ha_display(opener), capsys)
    assert not called.exists()


@posix
def test_sem_a_opcao_display_e_barramento_ainda_chegam_ao_runtime(sandbox):
    env, _ = sandbox
    env.update(DISPLAY=":0", DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/0/bus")
    visto = {}

    def run(command, child, stdout):
        visto.update(child)
        return 0

    login_cmd.login(as_json=True, environ=env, run=run)
    assert visto["DISPLAY"] == ":0" and visto["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/0/bus"


@posix
def test_no_browser_poe_browser_true_para_o_runtime(sandbox, capsys):
    env, _ = sandbox
    visto = {}

    def run(command, child, stdout):
        visto["browser"] = child.get("BROWSER")
        return 0

    _login_json(env, run, capsys)
    assert visto["browser"] == "true"


@posix
def test_a_recusa_nomeia_a_versao_do_runtime(caixa, monkeypatch, capsys):
    caixa.runtime()
    monkeypatch.setattr(login_cmd, "_can_block_browser", lambda: False)
    code = login_cmd.login(as_json=True, no_browser=True, run=_nunca)
    doc = json.loads(capsys.readouterr().out)
    assert code == 2 and "3.10.0" in doc["detail"]


@posix
def test_no_browser_que_nao_instala_os_substitutos_recusa_com_motivo_e_versao(caixa, monkeypatch, capsys):
    caixa.runtime()

    def sem_espaco(*a, **k):
        raise OSError("no space left on device")

    monkeypatch.setattr(login_cmd.tempfile, "mkdtemp", sem_espaco)
    code = login_cmd.login(as_json=True, no_browser=True, run=_nunca)
    doc = json.loads(capsys.readouterr().out)
    assert code == 2 and doc["status"] == "REFUSED" and doc["reason_code"] == "no_browser_unsupported"
    assert "no space left on device" in doc["detail"] and "3.10.0" in doc["detail"]

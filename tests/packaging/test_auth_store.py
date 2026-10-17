"""The login file shared with the Simplicio Runtime (read only here): where it is, how it is checked, the lock.

Ported from simplicio-loop tests/test_auth_store.py (2034e2d), only for the functions the video CLI keeps: no write,
no refresh, no apply_tokens (decision: the video CLI never stores a credential). Every token is FAKE and every path is
under tmp_path. Tests that need real POSIX files use `posix_real`, so the SAME suite also runs on a real Windows or
macOS machine; the Windows code paths are exercised here with a simulated system and a fake msvcrt.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import _caixa
from _caixa import (FAKE_ACCESS, MASKED, REAL_WINDOWS, SISTEMAS, assert_no_secret, auth, hostos, login_doc,
                    posix_real, put_login, saida_cp1252, write_fake_runtime)
from _comum import ROOT

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
simula_so = _caixa.simula_so


def env_de(home: Path, **extra) -> dict:
    return {"HOME": str(home), "USERPROFILE": str(home), **extra}


@pytest.fixture(autouse=True)
def umask_normal():
    """The reader refuses a folder that group or others can write: assume the usual umask, not a group one."""
    antigo = os.umask(0o022)
    yield
    os.umask(antigo)


@pytest.fixture
def arq(tmp_path):
    return tmp_path / "home" / ".simplicio" / "login.json"


# --- where the file is -----------------------------------------------------------------------------------------------


def test_caminho_padrao_e_o_arquivo_do_runtime(tmp_path):
    esperado = tmp_path / ".simplicio" / "login.json"
    assert auth.runtime_login_path(env_de(tmp_path)) == esperado
    assert auth.login_path(env_de(tmp_path)) == esperado


def test_simplicio_auth_file_vence_e_branco_e_ignorado(tmp_path):
    assert auth.login_path(env_de(tmp_path, SIMPLICIO_AUTH_FILE=str(tmp_path / "rt.json"))) == tmp_path / "rt.json"
    assert auth.login_path(env_de(tmp_path, SIMPLICIO_AUTH_FILE="  ")) == tmp_path / ".simplicio" / "login.json"


def test_o_login_do_watcher_247_do_loop_nao_existe_aqui(tmp_path):
    """SIMPLICIO_247_LOGIN belongs to the loop's 24/7 watcher; the video CLI reads only the Runtime's file."""
    env = env_de(tmp_path, SIMPLICIO_247_LOGIN=str(tmp_path / "watcher.json"))
    assert auth.login_path(env) == tmp_path / ".simplicio" / "login.json"


def test_o_arquivo_de_trava_e_o_irmao_do_runtime(tmp_path):
    # the Runtime locks `login.lock` (the extension of the login file replaced): the same file or no exclusion at all
    assert auth.lock_path(tmp_path / "login.json") == tmp_path / "login.lock"
    assert auth.lock_path(tmp_path / "custom") == tmp_path / "custom.lock"


def test_o_modulo_nao_grava_credencial():
    """Decision: login is a mirror of the loop. No write, no refresh, no token application in this CLI."""
    for nome in ("write_login", "apply_tokens", "refresh_if_due", "watcher_path"):
        assert not hasattr(auth, nome), f"auth.{nome} would let the video CLI store or renew a credential"


@pytest.mark.parametrize("so", SISTEMAS)
def test_home_com_espaco_e_acento(tmp_path, simula_so, so):
    simula_so(so)
    casa = tmp_path / "Meu Usuário"
    casa.mkdir()
    assert auth.login_path(env_de(casa)) == casa / ".simplicio" / "login.json"
    saida_cp1252(str(auth.login_path(env_de(casa))))


def test_o_home_do_windows_prefere_userprofile_e_o_posix_prefere_home(tmp_path, simula_so):
    outro = tmp_path / "outro"
    simula_so("win32")
    assert hostos.home_dir({"HOME": str(outro), "USERPROFILE": str(tmp_path)}) == tmp_path
    simula_so("linux")
    assert hostos.home_dir({"HOME": str(tmp_path), "USERPROFILE": str(outro)}) == tmp_path
    simula_so("darwin")
    assert hostos.home_dir({"HOME": str(tmp_path)}) == tmp_path


def test_sem_home_no_ambiente_usa_path_home(caixa):
    assert hostos.home_dir({}) == caixa.home
    assert hostos.home_dir(None) == caixa.home


# --- read: validation ------------------------------------------------------------------------------------------------


def test_leitura_de_arquivo_ausente(arq):
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_missing"
    assert "simplicio-video login" in str(err.value)


@pytest.mark.parametrize("bruto", ["", "not json", "[1, 2]", '"text"'])
def test_conteudo_invalido_nao_e_login(arq, bruto):
    arq.parent.mkdir(parents=True)
    arq.write_text(bruto)
    arq.chmod(0o600)
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_invalid"


@posix_real
@pytest.mark.parametrize("modo", [0o644, 0o640, 0o604, 0o666])
def test_recusa_arquivo_que_o_grupo_ou_outros_leem(arq, modo):
    put_login(arq, mode=modo)
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_permissions"
    assert str(arq) in str(err.value) and f"chmod 600 {arq}" in str(err.value)
    assert err.value.fix == f"chmod 600 {arq}"
    assert FAKE_ACCESS not in str(err.value)


@posix_real
def test_recusa_link_simbolico(tmp_path, arq):
    real = put_login(tmp_path / "real.json")
    arq.parent.mkdir(parents=True)
    arq.symlink_to(real)
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_symlink"


@posix_real
def test_link_quebrado_e_recusado_e_o_alvo_nao_e_criado(tmp_path, arq):
    arq.parent.mkdir(parents=True)
    arq.parent.chmod(0o700)
    alvo = tmp_path / "nowhere.json"
    arq.symlink_to(alvo)
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_symlink"
    assert not alvo.exists()


def test_le_o_conteudo_de_um_arquivo_privado(arq):
    put_login(arq)
    assert auth.read_login(arq)["access_token"] == FAKE_ACCESS


def test_diretorio_nao_e_arquivo_de_login_e_nao_gera_traceback(arq):
    arq.mkdir(parents=True)
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_invalid"


@posix_real
def test_fifo_nao_trava_a_leitura(arq):
    arq.parent.mkdir(parents=True)
    arq.parent.chmod(0o700)
    os.mkfifo(arq, 0o600)
    inicio = time.monotonic()
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_invalid" and time.monotonic() - inicio < 2


@posix_real
@pytest.mark.parametrize("modo", [0o777, 0o775, 0o770, 0o707, 0o722])  # 0775 is what umask 002 gives mkdir
def test_pasta_que_grupo_ou_outros_gravam_e_recusada(arq, modo):
    put_login(arq)
    arq.parent.chmod(modo)
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_permissions" and f"chmod 700 {arq.parent}" in str(err.value)
    assert err.value.fix == f"chmod 700 {arq.parent}"  # the fix names the folder, not the file
    env = env_de(arq.parent.parent, SIMPLICIO_AUTH_FILE=str(arq))
    assert auth.describe(env)["fix"] == f"chmod 700 {arq.parent}"
    with pytest.raises(auth.LoginError):
        with auth.file_lock(arq, wait_s=0.1):
            pass


@posix_real
def test_pasta_sticky_nossa_e_aceita(arq):
    put_login(arq)
    arq.parent.chmod(0o1777)
    assert auth.read_login(arq)["access_token"] == FAKE_ACCESS
    arq.parent.chmod(0o755)
    assert auth.read_login(arq)["access_token"] == FAKE_ACCESS


@posix_real
def test_arquivo_de_outro_usuario_e_recusado(arq, monkeypatch):
    put_login(arq)
    monkeypatch.setattr(os, "geteuid", lambda: os.stat(arq).st_uid + 1)
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_permissions" and "outro usuário" in str(err.value)


# --- Windows: no mode bits, but links and reparse points stay refused -------------------------------------------------


def test_no_windows_o_modo_posix_nao_vale_e_nao_e_checado(arq, simula_so):
    """On Windows chmod does not mean anything: the 0o077 and folder checks are skipped (ACLs are NOT verified)."""
    simula_so("win32")
    put_login(arq, mode=0o644)
    arq.parent.chmod(0o777)
    assert auth.read_login(arq)["access_token"] == FAKE_ACCESS


@posix_real
@pytest.mark.parametrize("so", ["linux", "darwin"])
def test_no_linux_e_no_macos_o_mesmo_arquivo_e_recusado(arq, simula_so, so):
    simula_so(so)
    put_login(arq, mode=0o644)
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_permissions"


@pytest.mark.parametrize("tag", ["IO_REPARSE_TAG_SYMLINK", "IO_REPARSE_TAG_MOUNT_POINT"])
def test_ponto_de_reparse_do_windows_conta_como_link(arq, monkeypatch, tag):
    """A junction or a symlink on Windows is a reparse point: refused like a POSIX symlink (simulated lstat)."""
    put_login(arq)
    real = os.lstat

    def lstat(caminho, *a, **kw):
        info = real(caminho, *a, **kw)
        if str(caminho) == str(arq):
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                                   st_reparse_tag=getattr(stat, tag))
        return info

    monkeypatch.setattr(os, "lstat", lstat)
    assert auth.is_link(arq) is True
    with pytest.raises(auth.LoginError) as err:
        auth.read_login(arq)
    assert err.value.reason_code == "login_symlink"


def test_reparse_de_nuvem_nao_e_link(arq, monkeypatch):
    """A cloud placeholder (OneDrive) is a reparse point too, but not a link: it must not be refused as one."""
    put_login(arq)
    real = os.lstat

    def lstat(caminho, *a, **kw):
        info = real(caminho, *a, **kw)
        if str(caminho) == str(arq):
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                                   st_reparse_tag=0x9000001A)
        return info

    monkeypatch.setattr(os, "lstat", lstat)
    assert auth.is_link(arq) is False


# --- the lock --------------------------------------------------------------------------------------------------------


@posix_real
@pytest.mark.parametrize("modo", [0o644, 0o660, 0o666, 0o604])
def test_trava_existente_que_outros_abrem_e_recusada(tmp_path, modo):
    caminho = tmp_path / "login.json"
    trava = auth.lock_path(caminho)
    trava.write_text("")
    trava.chmod(modo)
    with pytest.raises(auth.LoginError) as err:
        with auth.file_lock(caminho, wait_s=0.1):
            pytest.fail("the lock must not be taken on a file others can open")
    assert err.value.reason_code == "login_permissions" and "chmod 600" in str(err.value)


@posix_real
def test_trava_de_outro_usuario_e_recusada_salvo_root(tmp_path, monkeypatch):
    caminho = tmp_path / "login.json"
    trava = auth.lock_path(caminho)
    trava.write_text("")
    trava.chmod(0o600)
    monkeypatch.setattr(os, "geteuid", lambda: os.stat(trava).st_uid + 1)  # a different, non-root user
    with pytest.raises(auth.LoginError) as err:
        with auth.file_lock(caminho, wait_s=0.1):
            pytest.fail("not our lock file")
    assert err.value.reason_code == "login_permissions" and "outro usuário" in str(err.value)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with auth.file_lock(caminho, wait_s=0.1):  # root may use a service user's lock
        pass


def test_a_trava_e_solta_ao_sair_e_depois_de_erro(tmp_path):
    caminho = tmp_path / "login.json"
    with auth.file_lock(caminho):
        pass
    with pytest.raises(RuntimeError):
        with auth.file_lock(caminho):
            raise RuntimeError("boom")
    with auth.file_lock(caminho, wait_s=0.2):  # taken again at once
        pass


@posix_real
def test_arquivo_de_trava_velho_nao_bloqueia(tmp_path):
    """The kernel drops a flock when its owner dies; the file a dead process leaves behind is not a lock."""
    caminho = tmp_path / "login.json"
    velho = auth.lock_path(caminho)
    velho.write_text("pid 424242 died here\n")
    velho.chmod(0o600)
    inicio = time.monotonic()
    with auth.file_lock(caminho, wait_s=2):
        pass
    assert time.monotonic() - inicio < 1.5


SEGURA = textwrap.dedent("""
    import sys, time
    from simplicio_video import auth
    with auth.file_lock(sys.argv[1], wait_s=5):
        print("held", flush=True)
        time.sleep(float(sys.argv[2]))
""")


@posix_real
def test_trava_segurada_por_outro_processo_bloqueia_e_depois_estoura(tmp_path):
    caminho = tmp_path / "login.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    dono = subprocess.Popen([sys.executable, "-c", SEGURA, str(caminho), "3"], stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert dono.stdout.readline().strip() == "held"
        with pytest.raises(auth.LoginError) as err:
            with auth.file_lock(caminho, wait_s=0.3):
                pytest.fail("the lock was not held by the other process")
        assert err.value.reason_code == "login_lock_timeout"
    finally:
        dono.kill()
        dono.wait()
    with auth.file_lock(caminho, wait_s=2):  # the dead holder no longer holds it
        pass


@posix_real
def test_trava_que_e_link_simbolico_e_recusada(tmp_path):
    caminho = tmp_path / "login.json"
    alvo = tmp_path / "elsewhere"
    alvo.write_text("")
    auth.lock_path(caminho).symlink_to(alvo)
    with pytest.raises(auth.LoginError) as err:
        with auth.file_lock(caminho, wait_s=0.2):
            pass
    assert err.value.reason_code == "login_symlink"


class _MsvcrtFalso:
    LK_NBLCK = 2
    LK_UNLCK = 0
    chamadas: list = []

    @classmethod
    def locking(cls, fd, modo, n):
        cls.chamadas.append((modo, n))


def test_trava_no_windows_usa_msvcrt_com_um_byte(tmp_path, monkeypatch, simula_so):
    simula_so("win32")
    _MsvcrtFalso.chamadas = []
    monkeypatch.setattr(auth, "fcntl", None)
    monkeypatch.setattr(auth, "msvcrt", _MsvcrtFalso)
    with auth.file_lock(tmp_path / "login.json", wait_s=1):
        assert _MsvcrtFalso.chamadas == [(_MsvcrtFalso.LK_NBLCK, 1)]
    assert _MsvcrtFalso.chamadas == [(_MsvcrtFalso.LK_NBLCK, 1), (_MsvcrtFalso.LK_UNLCK, 1)]


def test_trava_no_windows_tenta_de_novo_enquanto_ocupada(tmp_path, monkeypatch, simula_so):
    simula_so("win32")
    chamadas = []

    class Ocupada:
        LK_NBLCK = 2
        LK_UNLCK = 0

        @staticmethod
        def locking(fd, modo, n):
            chamadas.append(modo)
            if modo == 2 and chamadas.count(2) < 3:
                raise OSError(13, "busy")

    monkeypatch.setattr(auth, "fcntl", None)
    monkeypatch.setattr(auth, "msvcrt", Ocupada)
    with auth.file_lock(tmp_path / "login.json", wait_s=2):
        pass
    assert chamadas.count(2) == 3


def test_trava_no_windows_estoura_com_login_lock_timeout(tmp_path, monkeypatch, simula_so):
    simula_so("win32")

    class Sempre:
        LK_NBLCK = 2
        LK_UNLCK = 0

        @staticmethod
        def locking(fd, modo, n):
            raise OSError(13, "busy")

    monkeypatch.setattr(auth, "fcntl", None)
    monkeypatch.setattr(auth, "msvcrt", Sempre)
    with pytest.raises(auth.LoginError) as err:
        with auth.file_lock(tmp_path / "login.json", wait_s=0.2):
            pass
    assert err.value.reason_code == "login_lock_timeout"


def test_no_posix_a_trava_usa_fcntl_e_no_windows_msvcrt():
    """Exactly one backend per system: fcntl where it exists, msvcrt where it does not."""
    assert (auth.fcntl is None) == (auth.msvcrt is not None)
    assert (auth.fcntl is None) == REAL_WINDOWS


# --- logout ----------------------------------------------------------------------------------------------------------


def test_clear_apaga_o_arquivo_sob_a_trava(arq):
    put_login(arq)
    assert auth.clear_login(arq) is True
    assert not arq.exists()
    assert auth.clear_login(arq) is False


def test_clear_de_arquivo_ausente_nao_cria_nada(arq):
    assert auth.clear_login(arq) is False
    assert not arq.parent.exists()


@posix_real
def test_clear_remove_o_link_mas_nunca_o_alvo(tmp_path, arq):
    real = put_login(tmp_path / "real.json")
    arq.parent.mkdir(parents=True)
    arq.symlink_to(real)
    assert auth.clear_login(arq) is True
    assert real.exists() and not arq.is_symlink()


def test_clear_de_diretorio_e_recusado_sem_traceback(arq):
    arq.mkdir(parents=True)
    with pytest.raises(auth.LoginError) as err:
        auth.clear_login(arq)
    assert err.value.reason_code == "login_invalid" and arq.is_dir()


# --- what the file says (never a token) ------------------------------------------------------------------------------


@pytest.mark.parametrize("email,mascarado", [
    ("wesley@gmail.com", "w***@gmail.com"), ("a@b.co", "a***@b.co"), ("sem-arroba", ""), ("", ""), ("x@y", ""),
])
def test_mask_email(email, mascarado):
    assert auth.mask_email(email) == mascarado


def test_summary_nao_tem_segredo_e_mascara_o_email():
    fatos = auth.summary(login_doc(), now=time.time())
    assert fatos["email"] == MASKED
    assert fatos["has_refresh_token"] is True and fatos["access_expired"] is False
    assert fatos["entitlement"]["tier"] == "pro"
    assert_no_secret(json.dumps(fatos))


def test_summary_de_login_sem_validacao_em_cache():
    fatos = auth.summary({"access_token": "x", "access_expires_at": 0}, now=1000)
    assert fatos["email"] == "" and fatos["entitlement"] is None and fatos["access_expired"] is True
    assert fatos["has_refresh_token"] is False


def test_describe_de_login_valido(caixa):
    caixa.runtime()
    put_login(caixa.login)
    doc = auth.describe(env_de(caixa.home, PATH=str(caixa.bin)))
    assert doc["schema"] == "simplicio.auth-status/v1"
    assert doc["logged_in"] is True and doc["reason_code"] == "ok" and doc["fix"] is None
    assert doc["email"] == MASKED and doc["path"] == str(caixa.login) and doc["shared_with_runtime"] is True
    assert doc["runtime"]["found"] is True and doc["runtime"]["version"] == "3.10.0"
    assert "access_token" not in doc and "refresh_token" not in doc
    assert_no_secret(json.dumps(doc))


def test_describe_de_login_ausente_diz_o_comando(caixa):
    doc = auth.describe(env_de(caixa.home, PATH=str(caixa.bin)))
    assert doc["logged_in"] is False and doc["reason_code"] == "login_missing"
    assert doc["fix"] == "simplicio-video login"
    assert doc["runtime"] == {"found": False, "path": None, "version": None}
    assert not caixa.login.parent.exists()  # reading creates nothing


def test_describe_de_login_expirado(caixa):
    put_login(caixa.login, login_doc(access_expires_at=1, refresh_token="", refresh_token_expires_at=0))
    doc = auth.describe(env_de(caixa.home, PATH=str(caixa.bin)))
    assert doc["logged_in"] is False and doc["reason_code"] == "login_expired" and doc["access_expired"] is True
    # an expired access token with a living refresh token is still a usable login
    put_login(caixa.login, login_doc(access_expires_at=1))
    assert auth.describe(env_de(caixa.home, PATH=str(caixa.bin)))["logged_in"] is True
    # ... until the refresh token itself has expired
    put_login(caixa.login, login_doc(access_expires_at=1, refresh_token_expires_at=2))
    assert auth.describe(env_de(caixa.home, PATH=str(caixa.bin)))["reason_code"] == "login_expired"


@posix_real
def test_describe_de_permissao_frouxa_traz_detail_e_fix(caixa):
    put_login(caixa.login, mode=0o644)
    doc = auth.describe(env_de(caixa.home, PATH=str(caixa.bin)))
    assert doc["reason_code"] == "login_permissions" and doc["fix"] == f"chmod 600 {caixa.login}"
    assert "detail" in doc and FAKE_ACCESS not in json.dumps(doc)


def test_describe_so_aponta_outro_arquivo_quando_ha_simplicio_auth_file(caixa):
    outro = put_login(caixa.tmp / "servico" / "login.json")
    doc = auth.describe(env_de(caixa.home, PATH=str(caixa.bin), SIMPLICIO_AUTH_FILE=str(outro)))
    # SIMPLICIO_AUTH_FILE is the very name the Runtime reads, so it is the Runtime's file too
    assert doc["path"] == str(outro) and doc["runtime_path"] == str(outro) and doc["shared_with_runtime"] is True


# --- the Runtime -----------------------------------------------------------------------------------------------------


def test_runtime_e_achado_no_path_primeiro_e_depois_na_pasta_bin(tmp_path):
    no_path = write_fake_runtime(tmp_path / "bin")
    gerenciado = write_fake_runtime(tmp_path / "home" / ".simplicio" / "bin")
    env = env_de(tmp_path / "home", PATH=str(tmp_path / "bin"))
    assert auth.runtime_binary(env) == no_path
    assert auth.runtime_binary(env_de(tmp_path / "home", PATH=str(tmp_path / "vazio"))) == gerenciado
    assert auth.runtime_binary(env_de(tmp_path / "sem-home", PATH=str(tmp_path / "vazio"))) is None


def test_runtime_sem_path_no_ambiente_nao_olha_o_path_de_verdade(tmp_path, monkeypatch):
    """An injected environment without PATH must not fall back to the real PATH of the process."""
    real = write_fake_runtime(tmp_path / "realbin")
    monkeypatch.setenv("PATH", str(real.parent))
    assert auth.runtime_binary(env_de(tmp_path / "sem-home")) is None


@pytest.mark.parametrize("nome", ["simplicio.exe", "simplicio.cmd"])
def test_no_windows_o_runtime_e_achado_como_exe_ou_cmd(tmp_path, simula_so, nome):
    simula_so("win32")
    pasta = tmp_path / "bin"
    pasta.mkdir()
    alvo = pasta / nome
    alvo.write_text("@echo off\r\n")
    alvo.chmod(0o755)
    assert auth.runtime_binary(env_de(tmp_path / "home", PATH=str(pasta))) == alvo


def test_no_windows_o_runtime_gerenciado_e_o_exe_em_simplicio_bin(tmp_path, simula_so):
    simula_so("win32")
    pasta = tmp_path / "home" / ".simplicio" / "bin"
    pasta.mkdir(parents=True)
    exe = pasta / "simplicio.exe"
    exe.write_text("x")
    exe.chmod(0o755)
    assert auth.runtime_binary(env_de(tmp_path / "home", PATH=str(tmp_path / "vazio"))) == exe
    assert hostos.exe_name("simplicio") == "simplicio.exe"


@pytest.mark.parametrize("so", ["linux", "darwin"])
def test_no_posix_o_runtime_se_chama_simplicio(simula_so, so):
    simula_so(so)
    assert hostos.exe_name("simplicio") == "simplicio"


@pytest.mark.parametrize("so", SISTEMAS)
def test_o_diretorio_atual_nunca_entra_na_busca_do_runtime(tmp_path, monkeypatch, simula_so, so):
    """shutil.which looks in the current directory first on Windows: a planted simplicio.exe would be run by `login`."""
    simula_so(so)
    plantado = tmp_path / "cwd"
    plantado.mkdir()
    for nome in ("simplicio", "simplicio.exe", "simplicio.cmd"):
        (plantado / nome).write_text("planted")
        (plantado / nome).chmod(0o755)
    monkeypatch.chdir(plantado)
    env = env_de(tmp_path / "home", PATH=str(tmp_path / "vazio") + os.pathsep + "." + os.pathsep)
    assert auth.runtime_binary(env) is None
    assert hostos.which("simplicio", "") is None


def test_versao_do_runtime_vem_da_saida_de_version(tmp_path):
    binario = write_fake_runtime(tmp_path / "bin")
    assert auth.runtime_version(binario) == "3.10.0"
    assert auth.runtime_version(tmp_path / "missing") is None


@posix_real
def test_runtime_que_nao_responde_nao_tem_versao(tmp_path):
    quebrado = tmp_path / "bin2" / "simplicio"
    quebrado.parent.mkdir()
    quebrado.write_text("#!/bin/sh\nexit 3\n")
    quebrado.chmod(0o755)
    assert auth.runtime_version(quebrado) is None

"""The exclusive file lock the installer holds (`lockfile.file_lock`): the wait, the timeout, a dead owner, a symlink, Windows.

Ported from the lock cases of the removed login module (test_auth_store.py), without the login checks: the installer takes the
lock non-strict, so a lock file that others can open is fine here. Every path is under tmp_path; nothing touches ~/.simplicio.
The Windows code path runs with a fake msvcrt, so the SAME suite runs on any system.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import pytest

from _caixa import REAL_WINDOWS, posix_real
from _comum import ROOT

from simplicio_video import lockfile


SEGURA = textwrap.dedent("""
    import sys, time
    from simplicio_video import lockfile
    with lockfile.file_lock(sys.argv[1], wait_s=5):
        print("held", flush=True)
        time.sleep(float(sys.argv[2]))
""")


def test_o_lock_fica_no_sidecar_do_arquivo(tmp_path):
    assert lockfile.lock_path(tmp_path / "install.json") == tmp_path / "install.lock"


def test_a_trava_e_solta_ao_sair_e_depois_de_erro(tmp_path):
    caminho = tmp_path / "install.json"
    with lockfile.file_lock(caminho, wait_s=1):
        pass
    with pytest.raises(RuntimeError):
        with lockfile.file_lock(caminho, wait_s=1):
            raise RuntimeError("boom")
    with lockfile.file_lock(caminho, wait_s=0.2):  # taken again at once
        pass


def test_a_trava_nao_apaga_o_arquivo_de_trava(tmp_path):
    """The caller decides what happens to the lock file: releasing the lock leaves it in place."""
    caminho = tmp_path / "install.json"
    with lockfile.file_lock(caminho, wait_s=1):
        pass
    assert lockfile.lock_path(caminho).exists()


@posix_real
def test_arquivo_de_trava_velho_nao_bloqueia(tmp_path):
    """The kernel drops a flock when its owner dies; the file a dead process leaves behind is not a lock."""
    caminho = tmp_path / "install.json"
    velho = lockfile.lock_path(caminho)
    velho.write_text("pid 424242 died here\n")
    velho.chmod(0o600)
    inicio = time.monotonic()
    with lockfile.file_lock(caminho, wait_s=2):
        pass
    assert time.monotonic() - inicio < 1.5


@posix_real
def test_trava_segurada_por_outro_processo_bloqueia_e_depois_estoura(tmp_path):
    caminho = tmp_path / "install.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    dono = subprocess.Popen([sys.executable, "-c", SEGURA, str(caminho), "3"], stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert dono.stdout.readline().strip() == "held"
        with pytest.raises(lockfile.LockError) as err:
            with lockfile.file_lock(caminho, wait_s=0.3):
                pytest.fail("the lock was not held by the other process")
        assert err.value.reason_code == "lock_timeout"
        assert "outro programa segura" in str(err.value) and "tente de novo" in str(err.value)
    finally:
        dono.kill()
        dono.wait()
    with lockfile.file_lock(caminho, wait_s=2):  # the dead holder no longer holds it
        pass


@posix_real
def test_trava_que_e_link_simbolico_e_recusada(tmp_path):
    caminho = tmp_path / "install.json"
    alvo = tmp_path / "elsewhere"
    alvo.write_text("")
    lockfile.lock_path(caminho).symlink_to(alvo)
    with pytest.raises(lockfile.LockError) as err:
        with lockfile.file_lock(caminho, wait_s=0.2):
            pass
    assert err.value.reason_code == "lock_symlink"
    assert alvo.read_text() == ""  # neither the link nor its target is touched


def test_pasta_que_nao_pode_ser_criada_vira_erro_de_trava(tmp_path):
    bloqueada = tmp_path / "arquivo"
    bloqueada.write_text("")  # a file where the lock's folder should be
    with pytest.raises(lockfile.LockError) as err:
        with lockfile.file_lock(bloqueada / "sub" / "install.json", wait_s=0.1):
            pass
    assert err.value.reason_code == "lock_invalid" and "criar a pasta" in str(err.value)


class _MsvcrtFalso:
    LK_NBLCK = 2
    LK_UNLCK = 0
    chamadas: list = []

    @classmethod
    def locking(cls, fd, modo, n):
        cls.chamadas.append((modo, n))


def test_trava_no_windows_usa_msvcrt_com_um_byte(tmp_path, monkeypatch):
    _MsvcrtFalso.chamadas = []
    monkeypatch.setattr(lockfile, "fcntl", None)
    monkeypatch.setattr(lockfile, "msvcrt", _MsvcrtFalso)
    with lockfile.file_lock(tmp_path / "install.json", wait_s=1):
        assert _MsvcrtFalso.chamadas == [(_MsvcrtFalso.LK_NBLCK, 1)]
    assert _MsvcrtFalso.chamadas == [(_MsvcrtFalso.LK_NBLCK, 1), (_MsvcrtFalso.LK_UNLCK, 1)]


def test_trava_no_windows_tenta_de_novo_enquanto_ocupada(tmp_path, monkeypatch):
    chamadas = []

    class Ocupada:
        LK_NBLCK = 2
        LK_UNLCK = 0

        @staticmethod
        def locking(fd, modo, n):
            chamadas.append(modo)
            if modo == 2 and chamadas.count(2) < 3:
                raise OSError(13, "busy")

    monkeypatch.setattr(lockfile, "fcntl", None)
    monkeypatch.setattr(lockfile, "msvcrt", Ocupada)
    with lockfile.file_lock(tmp_path / "install.json", wait_s=2):
        pass
    assert chamadas.count(2) == 3


def test_trava_no_windows_estoura_com_lock_timeout(tmp_path, monkeypatch):
    class Sempre:
        LK_NBLCK = 2
        LK_UNLCK = 0

        @staticmethod
        def locking(fd, modo, n):
            raise OSError(13, "busy")

    monkeypatch.setattr(lockfile, "fcntl", None)
    monkeypatch.setattr(lockfile, "msvcrt", Sempre)
    with pytest.raises(lockfile.LockError) as err:
        with lockfile.file_lock(tmp_path / "install.json", wait_s=0.2):
            pass
    assert err.value.reason_code == "lock_timeout"


def test_no_posix_a_trava_usa_fcntl_e_no_windows_msvcrt():
    """Exactly one backend per system: fcntl where it exists, msvcrt where it does not."""
    assert (lockfile.fcntl is None) == (lockfile.msvcrt is not None)
    assert (lockfile.fcntl is None) == REAL_WINDOWS


def test_a_trava_nao_depende_de_login():
    """The lock module knows nothing of the shared login: no login name, no login code, no login file."""
    texto = open(lockfile.__file__, encoding="utf8").read().lower()
    assert "login" not in texto and "auth" not in texto
    assert not hasattr(lockfile, "LoginError")

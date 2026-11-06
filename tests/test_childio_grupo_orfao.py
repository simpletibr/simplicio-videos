"""A script that leaves a background process and exits, and then the call fails (output too big): the guard's default killer must still
sweep the script's group. The leader is already reaped by then (instagram._executa and busca._rodar wait for it before they read)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from _orfao import POSIX, espera, espera_pid, limpa, vivo

pytestmark = pytest.mark.skipif(not POSIX, reason="POSIX process groups")

SLEEP = shutil.which("sleep") or "/bin/sleep"


def _script(tmp_path: Path, pidfile: Path, nome: str) -> Path:
    exe = tmp_path / nome
    exe.write_text(f"#!/bin/sh\n{SLEEP} 120 &\necho $! > {pidfile}\nhead -c 5000 /dev/zero\n")
    exe.chmod(0o755)
    return exe


def test_instagram_executa_kills_the_background_process_of_a_script_with_oversized_output(tmp_path, monkeypatch):
    from simplicio_video import instagram

    pidfile = tmp_path / "pid"
    monkeypatch.setattr(instagram, "MAX_OUTPUT_BYTES", 1000)
    try:
        with pytest.raises(instagram.InstagramError, match="limite"):
            instagram._executa([str(_script(tmp_path, pidfile, "script.sh"))], None, str(tmp_path))
        assert espera(lambda: not vivo(espera_pid(pidfile)), 10), "the background process of the script outlived the call"
    finally:
        limpa(None, pidfile)


def test_busca_rodar_kills_the_background_process_of_a_binary_with_oversized_output(tmp_path):
    from simplicio_video import busca

    pidfile = tmp_path / "pid"
    try:
        with pytest.raises(busca.BuscaError, match="limite"):
            busca._rodar(str(_script(tmp_path, pidfile, "tinyfish")), ["search", "q"], 60, 1000)
        assert espera(lambda: not vivo(espera_pid(pidfile)), 10), "the background process of the binary outlived the call"
    finally:
        limpa(None, pidfile)

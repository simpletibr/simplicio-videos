"""Cada comando de operação tem --help com exemplos (issue #43, critério de aceitação de help)."""
import pytest

from _comum import executa
from simplicio_video.cli import main


@pytest.mark.parametrize("comando", ["install", "update", "doctor", "setup"])
def test_comando_de_operacao_tem_help_com_exemplos(comando, capsys):
    rc, out, err = executa([comando, "--help"], capsys, main)
    assert rc == 0, f"{comando} --help falhou: {err}"
    assert "exemplos" in out.lower(), f"{comando} --help sem exemplos"

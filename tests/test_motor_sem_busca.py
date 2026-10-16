"""Revisão do PR #112, achado 12: o motor (render, contrato, compilador, pipeline) não depende do módulo `busca`.

No molde de test_motor_sem_vendas: o módulo é bloqueado no import (`sys.modules[nome] = None` faz o import falhar como se
o arquivo não existisse) e o CLI continua importando, montando o parser e rodando. Os subprocessos herdam o guard de socket.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from conftest import ROOT, offline_env

RUNNER = """\
import sys
for nome in {bloqueados!r}:
    sys.modules["simplicio_video." + nome] = None
from simplicio_video import cli
sys.exit(cli.main(sys.argv[1:]))
"""


def _roda(args, tmp_path, codigo=RUNNER.format(bloqueados=["busca"])):
    env = offline_env(SIMPLICIO_VIDEO_HOME=str(ROOT), SIMPLICIO_VIDEO_DATA=str(tmp_path / "data"))
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])  # always this checkout's code, whatever pip installed
    return subprocess.run([sys.executable, "-c", codigo, *args], capture_output=True, text=True, cwd=tmp_path, env=env)


@pytest.mark.parametrize("args,esperado", [
    (["validate", "{contrato}"], "OK: contrato válido"),
    (["render", "--help"], "usage: simplicio-video render"),
    (["list", "templates"], "alimentacao"),
    (["busca", "--help"], "Pesquisa e leitura de páginas na internet"),  # the help text lives apart from the module that calls the binary
])
def test_motor_importa_e_roda_sem_o_modulo_busca(args, esperado, mini, tmp_path):
    args = [str(mini) if a == "{contrato}" else a for a in args]
    r = _roda(args, tmp_path)
    assert r.returncode == 0, f"rc={r.returncode}\nstderr:\n{r.stderr}"
    assert "Traceback" not in r.stderr
    assert esperado in r.stdout, r.stdout


def test_montar_o_parser_e_importar_o_motor_nao_carrega_a_busca(tmp_path):
    codigo = ("import sys\n"
              "from simplicio_video import cli, compiler, contract, pipeline, render\n"
              "cli.build_parser()\n"
              "assert 'simplicio_video.busca' not in sys.modules, 'busca foi importada ao montar o parser'\n"
              "print('ok')\n")
    r = _roda([], tmp_path, codigo=codigo)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr

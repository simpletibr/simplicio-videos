"""Issue #77: o CLI do motor não carrega os módulos de venda (prospect, venda, ugc, realoficial, publish).

Os arquivos desses módulos continuam no repo até depois da campanha de 12/10. Aqui se prova só que o motor
importa, registra e roda sem eles. Os subprocessos herdam o guard de socket (conftest.offline_env).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

import pytest

from conftest import ROOT, offline_env, run_cli

# Subcomandos de venda: não podem aparecer no argparse do motor nem no --help dele.
VENDAS = ("prospect", "batch", "venda", "ugc", "realoficial", "publish")
# Módulos que o motor não pode importar (a batch é alias de prospect, então não entra aqui).
MODULOS_VENDAS = ("prospect", "venda", "ugc", "realoficial", "publish")
# Subcomandos do motor que ficam; o --help de cada um não pode citar os de venda.
MOTOR = ("init", "validate", "voice", "render", "run", "list", "mcp", "clone", "montage", "edit", "opencut", "toonflow")

# Roda o CLI com os módulos de venda bloqueados: `sys.modules[nome] = None` faz o import falhar como se o arquivo
# não existisse. Depois de importar o CLI, executa cli.main() com os argumentos recebidos.
RUNNER = """\
import sys
for nome in {bloqueados!r}:
    sys.modules["simplicio_video." + nome] = None
from simplicio_video import cli
sys.exit(cli.main(sys.argv[1:]))
"""


def _subparsers(ap: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))


def test_cli_nao_registra_subcomandos_de_venda():
    from simplicio_video import cli

    registrados = set(_subparsers(cli.build_parser()).choices)
    assert not registrados & set(VENDAS), f"subcomandos de venda ainda registrados no motor: {sorted(registrados & set(VENDAS))}"


@pytest.mark.parametrize("nome", VENDAS)
def test_argparse_rejeita_subcomando_de_venda(nome, capsys):
    from simplicio_video import cli

    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args([nome])
    assert e.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize("args,esperado", [
    (["validate", "{contrato}"], "OK: contrato válido"),
    (["render", "--help"], "usage: simplicio-video render"),
    (["list", "templates"], "alimentacao"),
])
def test_motor_importa_e_roda_sem_modulos_de_venda(args, esperado, mini, tmp_path):
    args = [str(mini) if a == "{contrato}" else a for a in args]
    env = offline_env(SIMPLICIO_VIDEO_HOME=str(ROOT), SIMPLICIO_VIDEO_DATA=str(tmp_path / "data"))
    r = subprocess.run([sys.executable, "-c", RUNNER.format(bloqueados=list(MODULOS_VENDAS)), *args],
                       capture_output=True, text=True, cwd=tmp_path, env=env)
    assert r.returncode == 0, f"rc={r.returncode}\nstderr:\n{r.stderr}"
    assert "Traceback" not in r.stderr
    assert esperado in r.stdout, r.stdout


def test_help_principal_nao_lista_subcomandos_de_venda():
    r = run_cli("--help")
    assert r.returncode == 0, r.stderr
    for nome in VENDAS:
        assert not re.search(rf"^  {nome}\s", r.stdout, re.M), f"linha de subcomando {nome!r} no --help principal"
        assert f"simplicio-video {nome}" not in r.stdout, f"exemplo com {nome!r} no --help principal"


@pytest.mark.parametrize("sub", MOTOR)
def test_help_do_subcomando_motor_nao_cita_venda(sub):
    r = run_cli(sub, "--help")
    assert r.returncode == 0, r.stderr
    for nome in VENDAS:
        assert f"simplicio-video {nome}" not in r.stdout, f"{sub} --help cita {nome!r}"


def test_modulos_de_venda_continuam_no_repo():
    # A issue só corta o import no CLI: os arquivos saem do repo depois de 12/10, não agora.
    for nome in MODULOS_VENDAS:
        assert (ROOT / "src" / "simplicio_video" / f"{nome}.py").is_file(), f"{nome}.py não pode ser apagado pela #77"

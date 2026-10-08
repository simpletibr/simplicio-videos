"""CLI do host de plugins (#32): `plugin list`, despacho de comando de plugin e --help.

Fase 1 (vermelho): `plugin list` e o despacho ainda não existem; os testes de exit 2 e de --help dos subcomandos
atuais são guardas de regressão e já passam.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from simplicio_video import cli
from _host_fixtures import escreve_manifesto, handler_fake, manifesto, plugin_root  # noqa: F401 (fixtures do host de plugins)

SUBCOMANDOS_ATUAIS = ["init", "validate", "voice", "render", "run", "clone", "montage", "edit", "opencut", "mcp",
                      "status", "list", "install", "update", "doctor", "setup"]


def run_cli(*args):
    """Roda `python -m simplicio_video` em subprocesso (help e exit code reais, sem rede)."""
    env = os.environ.copy()
    env["SIMPLICIO_OFFLINE"] = "1"
    return subprocess.run([sys.executable, "-m", "simplicio_video", *map(str, args)],
                          capture_output=True, text=True, env=env)


def test_plugin_list_imprime_o_id_do_plugin(plugin_root, capsys):  # noqa: F811 (fixture importada, redefinida como parâmetro)
    code = cli.main(["plugin", "list"])
    assert code == 0
    assert "fake" in capsys.readouterr().out


def test_comando_de_plugin_chama_handler_com_argumentos_restantes(plugin_root, handler_fake):  # noqa: F811 (fixture importada, redefinida como parâmetro)
    code = cli.main(["fakecmd", "arg"])
    assert code == handler_fake
    assert sys.modules["pluginfake_hosttest"].CHAMADAS == [["arg"]]


def test_comando_desconhecido_sai_com_codigo_2():
    r = run_cli("comando-que-nao-existe")
    assert r.returncode == 2


def test_help_de_nivel_superior_mantem_todos_os_subcomandos_atuais():
    r = run_cli("--help")
    assert r.returncode == 0, r.stderr
    for s in SUBCOMANDOS_ATUAIS:
        assert re.search(rf"^    {s}\s", r.stdout, re.M), f"--help perdeu o subcomando {s!r}"


def test_help_de_nivel_superior_lista_plugin():
    r = run_cli("--help")
    assert r.returncode == 0, r.stderr
    assert re.search(r"^    plugin\s", r.stdout, re.M), "--help de nível superior não lista 'plugin'"


def test_plugin_list_tem_help_com_exemplo():
    r = run_cli("plugin", "list", "--help")
    assert r.returncode == 0, r.stderr
    assert "exemplos:" in r.stdout and "simplicio-video plugin list" in r.stdout

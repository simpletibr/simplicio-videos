"""Issue #77: o CLI do motor não carrega os módulos de venda (prospect, venda, ugc, realoficial, publish).

Aqui se prova que o motor importa, registra e roda sem eles. Os mortos (prospect, venda, ugc) saíram do pacote
do PyPI; `publish` e `realoficial` ficam porque ainda têm dependente. Os subprocessos herdam o guard de socket (conftest.offline_env).
"""
from __future__ import annotations

import argparse
import ast
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
MOTOR = ("init", "validate", "voice", "render", "run", "list", "mcp", "clone", "montage", "edit", "opencut", "toonflow", "moneyprinter")

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


# Módulos de venda mortos: nada no CLI, no MCP nem no motor os importa (só os testes exclusivos deles os importavam),
# então saíram do pacote que vai para o PyPI, com os dados que só eles liam (`layout` só o `prospect` importava).
# `publish` e `realoficial` ficam: `publish` ainda é exercitado por tests/test_contrato_sem_drive.py e
# `commands/setup.py` importa REALOFICIAL_MCP_URL.
MODULOS_MORTOS = ("prospect", "venda", "ugc", "layout")
MODULOS_QUE_FICAM = ("publish", "realoficial")
SRC = ROOT / "src" / "simplicio_video"


def test_modulos_de_venda_mortos_nao_estao_no_pacote():
    for nome in MODULOS_MORTOS:
        assert not (SRC / f"{nome}.py").exists(), f"{nome}.py é código morto: não vai para o PyPI"
    templates = SRC / "data" / "templates"
    assert not (templates / "prospect-roteamento.json").exists()
    assert not sorted(templates.glob("*/contract.base.yaml")), "contrato-base do prospect (marca d'água e @ do dono) no pacote"
    assert not sorted(templates.glob("*/setores.json")), "regras de setor do prospect no pacote"


def test_modulos_de_venda_com_dependente_continuam_no_repo():
    for nome in MODULOS_QUE_FICAM:
        assert (SRC / f"{nome}.py").is_file(), f"{nome}.py ainda tem dependente (setup.py / test_contrato_sem_drive.py)"


# A varredura de antes era uma regex de linha: não pegava `from . import (\n venda,\n)` nem `importlib.import_module("...")`.
_REGEX_ANTIGA = re.compile(r"^\s*(?:from\s+\.(?:prospect|venda|ugc)\b|from\s+\.\s+import\s+[^\n#]*\b(?:prospect|venda|ugc)\b|"
                           r"(?:from|import)\s+simplicio_video(?:\.|\s+import\s+[^\n#]*\b)(?:prospect|venda|ugc)\b)", re.M)


def _nome_morto(nome: str | None) -> bool:
    partes = [p for p in (nome or "").split(".") if p]
    if partes[:1] == ["simplicio_video"]:
        partes = partes[1:]
    return bool(partes) and partes[0] in MODULOS_MORTOS


def _importa_modulo_morto(codigo: str) -> list[str]:
    """Imports de módulo morto no código, pela árvore sintática (qualquer formatação) e as chamadas de import dinâmico.

    Um import dinâmico com nome que não é texto literal não dá para conferir: também é achado (o pacote não usa nenhum)."""
    achados = []
    for no in ast.walk(ast.parse(codigo)):
        if isinstance(no, ast.Import):
            achados += [f"import {a.name}" for a in no.names if a.name.startswith("simplicio_video.") and _nome_morto(a.name)]
        elif isinstance(no, ast.ImportFrom):
            if no.level == 0 and (no.module or "").split(".")[0] != "simplicio_video":
                continue
            if _nome_morto(no.module):  # from .venda import x, from simplicio_video.venda import x
                achados.append(f"from {'.' * no.level}{no.module} import ...")
            if no.module in (None, "simplicio_video"):  # from . import venda, from simplicio_video import venda
                achados += [f"from {'.' * no.level}{no.module or ''} import {a.name}" for a in no.names if _nome_morto(a.name)]
        elif isinstance(no, ast.Call):
            f = no.func
            nome = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if nome in ("import_module", "__import__"):
                arg = no.args[0] if no.args else None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if _nome_morto(arg.value):
                        achados.append(f"{nome}({arg.value!r})")
                else:
                    achados.append(f"{nome}(...) com nome que não é literal")
    return achados


@pytest.mark.parametrize("exemplo", [
    "from . import venda",
    "from .prospect import x",
    "from . import cli, ugc",
    "from . import layout",
    "import simplicio_video.ugc",
    "from simplicio_video import prospect as P",
    "from simplicio_video.layout import x",
    "def _lazy():\n    from . import (\n        venda,\n    )\n    return venda",
    "def _lazy():\n    from . import (\n        cli,\n        prospect as p,\n    )",
    "import importlib\nm = importlib.import_module('simplicio_video.prospect')",
    "m = __import__('simplicio_video.venda', fromlist=['x'])",
    "from importlib import import_module\nm = import_module('.ugc', 'simplicio_video')",
    "from importlib import import_module\nm = import_module(f'simplicio_video.{nome}')",
])
def test_a_varredura_de_imports_pega_as_formas_de_burla(exemplo):
    assert _importa_modulo_morto(exemplo), f"a varredura não pega {exemplo!r}"


@pytest.mark.parametrize("exemplo", [
    "from . import (\n    cli,\n    publish,\n)\nfrom .realoficial import X",
    "import importlib\nm = importlib.import_module('simplicio_video.publish')",
    "from simplicio_video import cli, paths",
    "# from . import venda\nx = 'from . import venda'",
])
def test_a_varredura_de_imports_nao_acusa_o_que_fica(exemplo):
    assert _importa_modulo_morto(exemplo) == []


@pytest.mark.parametrize("exemplo", [
    "def _lazy():\n    from . import (\n        venda,\n    )\n    return venda",
    "import importlib\nm = importlib.import_module('simplicio_video.prospect')",
    "from . import layout",
])
def test_a_regex_antiga_deixava_passar_estes(exemplo):
    assert not _REGEX_ANTIGA.search(exemplo)


def test_nada_no_pacote_importa_os_modulos_mortos():
    achados = [f"{p.relative_to(SRC)}: {a}" for p in sorted(SRC.rglob("*.py")) for a in _importa_modulo_morto(p.read_text(encoding="utf8"))]
    assert not achados, achados

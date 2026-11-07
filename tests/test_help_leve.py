"""U10b: `simplicio-video --help` is light. It prints a screen of short lines, so it must not import the tracks.

Before this change `import simplicio_video.cli` imported `mcp_server` (the `mcp` line of the main help is made from its list of
tools: 19 modules), and `build_parser()` imported `swap` with its six adapters, `jobs`, `social`, `openverse` and `busca_ajuda`
only to read the long description and the examples of ONE of the commands (a `--help` loaded 37 modules of the package). Now:

* the description and the examples that live in a heavy module go into the page of that command only
  (`build_parser(only="swap")`); the main help, and the help of every other command, do not need them. `build_parser()` without
  `only` is still the parser with everything (it is what `scripts/gen_reference.py` and `docs/reference/cli.md` are made from);
* `MAIN_DESC` is computed when the main help is asked for, and its list of tools still comes from `mcp_server.TOOLS`, in its
  order, without importing it.

Three kinds of test:

* CHARACTERIZATION (green before and after): the help the CLI prints for every command, the main help, and the error of an unknown
  command are exactly the text of the parser that has everything. They are compared in-process, with the same Python, so the layout
  that argparse changes from one version to the next is not a source of noise. The same screens were also compared byte by byte
  with origin/main in a subprocess for every command (`--help`, `-h`, `--json <cmd> --help`, `<cmd> --help --json`, a bad option);
* STRUCTURE (red before): `only` exists and decides what a page carries, and the CLI asks for the page it prints;
* WEIGHT (red before): in a clean interpreter, `import simplicio_video.cli`, `--help` and the help of each command that
  the parser alone prints import at most 12 modules of the package, and none of the heavy ones.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import offline_env
from simplicio_video import cli, mcp_server

LIMITE = 12  # modules of the package that `--help` may import (it was 37)

# the commands whose long help is in a module of its own: that module is imported only for the page that asks for it
PESADOS = {"swap": "swap", "jobs": "jobs", "social": "social", "openverse": "openverse", "busca": "busca_ajuda"}
# never imported by the main help (nor by the help of a command that does not need them)
PROIBIDOS = ("mcp_server", "swap", "jobs", "social", "openverse", "busca_ajuda", "busca", "tools", "tools_lock", "edit", "media",
             "montage", "rea_video", "video_to_skill", "voicestudio", "toonflow", "trilha_base", "download", "childio")


def _sub(ap: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))


COMPLETO = cli.build_parser()  # the parser with everything: what `docs/reference/cli.md` is made from
NOMES = list(_sub(COMPLETO).choices)


def _roda(argv: list[str]) -> tuple[int | str | None, str, str]:
    """`cli.main(argv)` in-process: (return code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(argv)
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def _pagina(nome: str) -> list[str]:
    """The words that make the CLI print the page of the PARSER for command `nome` (`clone --help` is Hypit's own help)."""
    return [nome, "--engine-help"] if nome == "clone" else [nome, "--help"]


# ------------------------------------------------------------------------------------------------ characterization (green)

@pytest.fixture(autouse=True)
def _caixa(tmp_path, monkeypatch):
    """An empty HOME and data folder, no network: a help screen must not depend on, or touch, the machine."""
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")


def test_the_parser_with_everything_has_the_long_help_of_the_five_heavy_commands():
    from simplicio_video import busca_ajuda, jobs, openverse, social, swap
    escolhas = _sub(COMPLETO).choices
    for nome, modulo in {"swap": swap, "jobs": jobs, "social": social, "openverse": openverse, "busca": busca_ajuda}.items():
        assert escolhas[nome].description == modulo.HELP_DESC, nome
        assert escolhas[nome].epilog == modulo.HELP_EPILOG, nome


def test_every_command_is_on_the_parser_with_its_short_line():
    ajudas = {a.dest: a.help for a in _sub(COMPLETO)._get_subactions()}
    assert set(ajudas) == set(NOMES)
    assert all(ajudas.values()), "every command shows a short line on the main help"


@pytest.mark.parametrize("nome", NOMES)
def test_the_help_of_each_command_is_the_page_of_the_parser_with_everything(nome):
    rc, out, err = _roda(_pagina(nome))
    assert (rc, err) == (0, "")
    assert out == _sub(COMPLETO).choices[nome].format_help()


# `--json <cmd>` is refused (exit 2) where the command has no `--json` of its own to receive it: `instagram`, `moneyprinter`, ... take
# it after some verbs only, and `clone --help` is Hypit's (the page is `--engine-help`, which the parser does not have)
@pytest.mark.parametrize("nome", [n for n in NOMES if n not in cli._JSON_SO_EM and n != "clone"])
def test_the_global_json_before_a_command_does_not_change_its_help(nome):
    rc, out, err = _roda(["--json", *_pagina(nome)])
    assert (rc, err) == (0, "")
    assert out == _sub(COMPLETO).choices[nome].format_help()


@pytest.mark.parametrize("argv", [["--help"], ["-h"], [], ["--json"], ["--json", "--help"]])
def test_the_main_help_is_the_page_of_the_parser_with_everything(argv):
    rc, out, err = _roda(argv)
    assert (rc, err) == (0, "")
    assert out == COMPLETO.format_help()


def test_an_unknown_command_is_refused_with_the_whole_list_of_commands():
    rc, out, err = _roda(["comando-que-nao-existe"])
    assert (rc, out) == (2, "")
    esperado = io.StringIO()
    with contextlib.redirect_stderr(esperado), pytest.raises(SystemExit) as e:
        COMPLETO.parse_args(["comando-que-nao-existe"])
    assert e.value.code == 2
    assert err == esperado.getvalue()
    assert all(nome in err for nome in NOMES), "the error of argparse lists every command that exists"


def test_a_bad_option_is_refused_the_same_way():
    rc, out, err = _roda(["--opcao-que-nao-existe"])
    esperado = io.StringIO()
    with contextlib.redirect_stderr(esperado), pytest.raises(SystemExit):
        COMPLETO.parse_args(["--opcao-que-nao-existe"])
    assert (rc, out, err) == (2, "", esperado.getvalue())


# ------------------------------------------------------------------------------------------------ structure (red before)

@pytest.mark.parametrize("only", ["", "init", "swap", "busca"])
def test_the_main_help_and_the_list_of_commands_do_not_depend_on_only(only):
    ap = cli.build_parser(only=only)
    assert list(_sub(ap).choices) == NOMES
    assert ap.format_help() == COMPLETO.format_help()
    assert [(a.dest, a.help) for a in _sub(ap)._get_subactions()] == [(a.dest, a.help) for a in _sub(COMPLETO)._get_subactions()]


@pytest.mark.parametrize("nome", sorted(PESADOS))
def test_only_brings_the_long_help_of_that_command_and_of_no_other(nome):
    ap = cli.build_parser(only=nome)
    escolhas, completo = _sub(ap).choices, _sub(COMPLETO).choices
    assert escolhas[nome].format_help() == completo[nome].format_help()
    assert escolhas[nome].description and escolhas[nome].epilog
    for outro in set(PESADOS) - {nome}:
        assert escolhas[outro].description is None and escolhas[outro].epilog is None, outro
        assert escolhas[outro].format_help() != completo[outro].format_help()


@pytest.mark.parametrize("only", ["", "init", "validate", "voice", "qc", "doctor"])
def test_a_command_with_its_help_in_cli_py_is_the_same_whatever_only_is(only):
    ap = cli.build_parser(only=only)
    for nome in set(NOMES) - set(PESADOS):
        assert _sub(ap).choices[nome].format_help() == _sub(COMPLETO).choices[nome].format_help(), nome


def test_without_only_the_parser_has_everything():
    assert cli.build_parser(only=None).format_help() == COMPLETO.format_help()
    for nome in PESADOS:
        assert _sub(cli.build_parser(only=None)).choices[nome].format_help() == _sub(COMPLETO).choices[nome].format_help()


@pytest.mark.parametrize("argv,only", [
    (["--help"], ""), (["-h"], ""), ([], ""), (["--version"], ""), (["comando-que-nao-existe"], ""),
    (["swap", "--help"], "swap"), (["--json", "busca", "--help"], "busca"), (["jobs", "-h"], "jobs"), (["init", "-h"], "init"),
    (["list", "templates"], ""), (["--vers"], ""), (["--hel"], ""), (["--h"], ""), (["--json", "--hel", "swap"], ""),
    # an option comes first and argparse decides which page prints (`--version swap --help` prints the page of swap): everything, as before
    (["--version", "swap", "--help"], None), (["--vers", "swap", "-h"], None), (["--js", "swap", "-h"], None),
    (["--", "jobs", "--help"], None), (["--json", "--version", "social", "--help"], None), (["--version", "--json", "busca", "-h"], None),
    (["--version", "swap", "--hel"], None), (["--vers", "openverse", "--h"], None)])
def test_the_cli_asks_for_the_page_it_prints(monkeypatch, argv, only):
    """The page of a command is built only when that command's `--help` is the thing asked for; any other run asks for none. When an
    option stands before the command, which page prints is argparse's call (it takes `--hel`, `--vers` and `--js` too): all of them."""
    pedidos: list = []
    construir = cli.build_parser

    def espia(only=None):
        pedidos.append(only)
        return construir(only=only)

    monkeypatch.setattr(cli, "build_parser", espia)
    _roda(argv)
    assert pedidos == [only]


def test_running_a_heavy_command_does_not_build_its_long_help(monkeypatch):
    """`swap providers` runs the module; the text of its page is for `swap --help` only."""
    vistos: list = []
    construir = cli.build_parser

    def espia(only=None):
        vistos.append(only)
        return construir(only=only)

    monkeypatch.setattr(cli, "build_parser", espia)
    monkeypatch.setattr(cli, "_despacha", lambda c, args: 0)
    for nome in PESADOS:
        vistos.clear()
        assert cli.main([nome, "providers"]) == 0
        assert vistos == [""], (nome, vistos)  # nothing heavy asked for


# `-h` and the abbreviations of `--help` that argparse accepts; the options that may come before the command (abbreviated too)
FLAGS_DE_AJUDA = ["--help", "-h", "--hel", "--he", "--h"]
PREFIXOS = [[], ["--json"], ["--version"], ["--"], ["--vers"], ["--js"], ["--json", "--version"], ["--json", "--json"]]


def _roda_ate_o_fim(argv: list[str]) -> tuple:
    """`cli.main(argv)` in-process; a crash is its type and message (a traceback has line numbers that move with every edit)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(argv)
        except SystemExit as e:
            rc = e.code
        except Exception as e:  # noqa: BLE001 - what is compared is what happens, crash included
            rc = f"{type(e).__name__}: {e}"
    return rc, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("prefixo", PREFIXOS, ids=lambda p: " ".join(p) or "sem-prefixo")
@pytest.mark.parametrize("nome", [*sorted(PESADOS), "init", "qc", "doctor", "voice", "list", "opencut", "status"])
def test_the_help_prints_what_the_parser_with_everything_prints_whatever_the_order_of_the_words(monkeypatch, prefixo, nome):
    """The oracle: what origin/main did (it always built the parser with everything). The long help of swap, jobs, social, openverse
    and busca must come out whole wherever argparse prints it, `--version swap --help` and `-- jobs --help` included."""
    construir = cli.build_parser
    for flag in FLAGS_DE_AJUDA:
        argv = [*prefixo, nome, flag]
        real = _roda_ate_o_fim(argv)
        with monkeypatch.context() as m:
            m.setattr(cli, "build_parser", lambda only=None: construir(only=None))
            esperado = _roda_ate_o_fim(argv)
        assert real == esperado, argv


@pytest.mark.parametrize("argv", [["--version", "swap", "--help"], ["--vers", "swap", "-h"], ["--js", "swap", "-h"], ["--json", "--version", "busca", "-h"],
                                  ["--json", "--version", "social", "--help"], ["--", "jobs", "--help"]])
def test_the_long_help_is_whole_when_an_option_comes_before_the_command(argv):
    """The four ways the first version of this change lost the description and the examples of the page (60 of 60 in the matrix)."""
    nome = next(w for w in argv if w in PESADOS)
    rc, out, _ = _roda_ate_o_fim(argv)
    assert rc == 0
    assert out == _sub(COMPLETO).choices[nome].format_help()
    assert _sub(COMPLETO).choices[nome].description in out and _sub(COMPLETO).choices[nome].epilog in out


# ------------------------------------------------------------------------------------------------ weight (red before)

# What a clean interpreter has imported from the package after `<corpo>`. Same count as `scripts/equiv.sh` (help_modules.txt).
SONDA = """\
import contextlib, io, json, sys
from simplicio_video import cli
{corpo}
print(json.dumps(sorted(m for m in sys.modules if m.startswith("simplicio_video"))))
"""


def _modulos(tmp_path: Path, corpo: str) -> list[str]:
    env = offline_env(HOME=str(tmp_path / "home"), SIMPLICIO_VIDEO_DATA=str(tmp_path / "data"), NO_COLOR="1")
    r = subprocess.run([sys.executable, "-c", SONDA.format(corpo=corpo)], capture_output=True, text=True, cwd=tmp_path, env=env,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.splitlines()[-1])


def _ajuda(argv: list[str]) -> str:
    return (f"with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):\n"
            f"    try:\n        cli.main({argv!r})\n    except SystemExit:\n        pass\n")


def _confere(modulos: list[str], quem: str) -> None:
    assert len(modulos) <= LIMITE, f"{quem} imports {len(modulos)} modules of the package (limit {LIMITE}): {modulos}"
    presentes = [m for m in modulos if m.removeprefix("simplicio_video.") in PROIBIDOS]
    assert not presentes, f"{quem} imported what only a command needs: {presentes}"


def test_importing_the_cli_does_not_import_the_tracks(tmp_path):
    _confere(_modulos(tmp_path, ""), "`import simplicio_video.cli`")


def test_the_main_help_imports_at_most_twelve_modules(tmp_path):
    _confere(_modulos(tmp_path, _ajuda(["--help"])), "`--help`")


@pytest.mark.parametrize("nome", [n for n in NOMES if n not in PESADOS and n != "clone"
                                  and (n not in cli.COMANDOS or cli.COMANDOS[n].ajuda == "argparse")])
def test_the_help_of_a_command_the_parser_prints_imports_at_most_twelve_modules(tmp_path, nome):
    _confere(_modulos(tmp_path, _ajuda([nome, "--help"])), f"`{nome} --help`")


# what each heavy help brings with it: `jobs` imports `swap`, the others stand alone
CARREGA = {"swap": {"swap"}, "jobs": {"jobs", "swap"}, "social": {"social"}, "openverse": {"openverse"}, "busca": {"busca_ajuda"}}


@pytest.mark.parametrize("nome", sorted(PESADOS))
def test_the_help_of_a_heavy_command_imports_its_long_help_and_not_the_others(tmp_path, nome):
    modulos = {m.removeprefix("simplicio_video.") for m in _modulos(tmp_path, _ajuda([nome, "--help"]))}
    assert modulos & {"swap", "jobs", "social", "openverse", "busca_ajuda"} == CARREGA[nome], sorted(modulos)
    assert not modulos & (set(PROIBIDOS) - {"swap", "jobs", "social", "openverse", "busca_ajuda"}), sorted(modulos)


# ------------------------------------------------------------------------------------------------ MAIN_DESC on demand

def _linha_mcp(texto: str) -> list[str]:
    linha = next(ln for ln in texto.splitlines() if re.match(r"\s+mcp\s+servidor MCP", ln))
    return linha.split("com as tools video.", 1)[1].split("/")


def test_main_desc_names_the_tools_of_the_server_in_its_order_without_importing_it(tmp_path):
    corpo = "d = cli.MAIN_DESC\nprint(json.dumps({'desc': d, 'importou': 'simplicio_video.mcp_server' in sys.modules}))\n"
    env = offline_env(HOME=str(tmp_path / "home"), SIMPLICIO_VIDEO_DATA=str(tmp_path / "data"))
    r = subprocess.run([sys.executable, "-c", "import json, sys\nfrom simplicio_video import cli\n" + corpo],
                       capture_output=True, text=True, cwd=tmp_path, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["importou"] is False, "reading MAIN_DESC imported the MCP server (19 modules) just to list its tools"
    assert _linha_mcp(d["desc"]) == [nome.removeprefix("video.") for nome, _fn, _desc in mcp_server.TOOLS]
    assert len(_linha_mcp(d["desc"])) == 32


def test_main_desc_is_what_the_main_help_prints():
    rc, out, _ = _roda(["--help"])
    assert rc == 0
    assert cli.MAIN_DESC in out
    assert cli.MAIN_DESC.startswith("simplicio-video ") and cli.MAIN_DESC.endswith("Skill para LLMs: skills/simplicio-video/SKILL.md")


def test_the_lines_around_the_mcp_line_are_fixed_text():
    """Only the list of tools in MAIN_DESC is computed; the lines around it read the same wherever the tools come from."""
    linhas = cli.MAIN_DESC.splitlines()
    i = next(n for n, ln in enumerate(linhas) if re.match(r"\s+mcp\s+servidor MCP", ln))
    assert linhas[i].startswith("  mcp          servidor MCP (stdio) com as tools video.init/validate/voice/render/run/list/")
    assert linhas[i + 1].startswith("  status       ferramentas (instaladas, versão, versão fixada)")
    assert linhas[i - 1].startswith("  busca        pesquisa e leitura de páginas na internet pelo CLI tinyfish")


# ------------------------------------------------------------------------------------------------ the names read from the source

def _nomes_do_servidor() -> list[str]:
    return [nome for nome, _fn, _desc in mcp_server.TOOLS]


def test_the_names_read_from_the_source_are_the_names_of_tools():
    assert cli._nomes_das_tools_no_fonte() == _nomes_do_servidor()
    assert cli._tools_mcp() == "/".join(nome.removeprefix("video.") for nome in _nomes_do_servidor())


@pytest.mark.parametrize("fonte,esperado", [
    ('TOOLS = [("video.a", f, D), ("video.b", g, E)]\n', ["video.a", "video.b"]),
    ('X = 1\nTOOLS = [("video.a", f, D)]\n', ["video.a"]),
    ("TOOLS = [(n, f, d) for n, f, d in outras]\n", None),          # not a literal list
    ('TOOLS = [("video.a", f, D), (nome, g, E)]\n', None),          # a name that is not a string: do not guess
    ('TOOLS = [("video.a", f, D), g]\n', None),                     # an item that is not a tuple
    ("TOOLS = []\n", None),
    ('TOOLS: list = [("video.a", f, D)]\n', None),                  # another shape of assignment: ask the module
    ("OUTRA = [('video.a', f, D)]\n", None),
    ("def isto(:\n", None),                                         # does not parse
])
def test_the_source_is_trusted_only_when_tools_is_a_literal_list_of_named_tuples(tmp_path, monkeypatch, fonte, esperado):
    (tmp_path / "mcp_server.py").write_text(fonte, encoding="utf-8")
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli.py"))
    assert cli._nomes_das_tools_no_fonte() == esperado


def test_without_the_source_the_names_come_from_the_module_and_are_the_same(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli.py"))  # no mcp_server.py there
    assert cli._nomes_das_tools_no_fonte() is None
    assert cli._tools_mcp() == "/".join(nome.removeprefix("video.") for nome in _nomes_do_servidor())


def test_main_desc_is_made_once():
    assert cli.MAIN_DESC is cli.MAIN_DESC
    assert cli._main_desc() is cli.MAIN_DESC


def test_an_unknown_attribute_of_the_module_is_still_an_attribute_error():
    assert not hasattr(cli, "NAO_EXISTE")
    with pytest.raises(AttributeError, match="NAO_EXISTE"):
        cli.NAO_EXISTE  # noqa: B018


# ------------------------------------------------------------------------------------------------ TOOLS must stay a literal list

MUTADORES = {"append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse", "__iadd__", "__setitem__", "__delitem__"}


def _mudancas_de_tools(fonte: str) -> list[str]:
    """What, besides the single literal `TOOLS = [...]` at the top level, changes the list: an `append`/`extend`/..., a `+=`, a
    `TOOLS[i] = x`, a second assignment, a `del`. The names read from the source would not see any of them."""
    arvore = ast.parse(fonte)
    achados: list[str] = []
    atribuicoes = 0
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name) and no.id == "TOOLS" and isinstance(no.ctx, (ast.Store, ast.Del)):
            atribuicoes += 1
        if isinstance(no, ast.AugAssign) and isinstance(no.target, ast.Name) and no.target.id == "TOOLS":
            achados.append(f"linha {no.lineno}: TOOLS {type(no.op).__name__}=")
        if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and isinstance(no.func.value, ast.Name)
                and no.func.value.id == "TOOLS" and no.func.attr in MUTADORES):
            achados.append(f"linha {no.lineno}: TOOLS.{no.func.attr}(...)")
        if isinstance(no, ast.Subscript) and isinstance(no.value, ast.Name) and no.value.id == "TOOLS" and isinstance(no.ctx, (ast.Store, ast.Del)):
            achados.append(f"linha {no.lineno}: TOOLS[...] alterado")
    if atribuicoes != 1:
        achados.append(f"TOOLS é atribuída {atribuicoes} vezes (só uma, a lista literal)")
    return achados


@pytest.mark.parametrize("fonte,muda", [
    ('TOOLS = [("video.a", f, D)]\n', False),
    ('TOOLS = [("video.a", f, D)]\nTOOLS.append(("video.b", g, E))\n', True),
    ('TOOLS = [("video.a", f, D)]\nTOOLS += [("video.b", g, E)]\n', True),
    ('TOOLS = [("video.a", f, D)]\nTOOLS.extend(OUTRAS)\n', True),
    ('TOOLS = [("video.a", f, D)]\nTOOLS.insert(0, x)\n', True),
    ('TOOLS = [("video.a", f, D)]\nTOOLS[0] = x\n', True),
    ('TOOLS = [("video.a", f, D)]\ndel TOOLS[0]\n', True),
    ('TOOLS = [("video.a", f, D)]\nTOOLS = TOOLS + OUTRAS\n', True),
    ('TOOLS = [("video.a", f, D)]\ndef g():\n    TOOLS.append(x)\n', True),
    ('TOOLS = [("video.a", f, D)]\nfor n, fn, d in TOOLS:\n    pass\n', False),
])
def test_the_checker_of_tools_sees_every_way_to_change_the_list(fonte, muda):
    assert bool(_mudancas_de_tools(fonte)) is muda, _mudancas_de_tools(fonte)


def test_mcp_server_never_changes_tools_after_the_literal_list():
    """`cli._nomes_das_tools_no_fonte` reads the names from the source. A `TOOLS.append(...)` after the list would give `--help` 32
    names (and none for the added tool) with no error in production: whoever needs to add a tool this way must change the reader."""
    fonte = (Path(cli.__file__).with_name("mcp_server.py")).read_text(encoding="utf-8")
    assert _mudancas_de_tools(fonte) == []

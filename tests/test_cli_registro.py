"""The table of the track commands of the CLI (U10a): what `simplicio-video <track>` does is told by `cli.COMANDOS`, not by a
chain of `if cmd == ...` blocks.

Three kinds of test, so the refactor is provable and the table cannot drift:

* CHARACTERIZATION (green before and after): for each of the 20 track commands, `<cmd> --help`, `<cmd> <invalid sub>` and
  `--json <cmd>` are run in-process in a sealed box (empty PATH, offline, own HOME) and the return code, stdout and stderr are
  compared with what origin/main printed. A stream is compared exactly when the module wrote it; a screen that argparse
  formats (a `usage:` block, a help page) is compared by its first line, because argparse changes its layout from one Python
  to the next. The routing rules (who prints `--help`, where `--json` goes, how an error becomes `<cmd>: message`) are also
  pinned with fake modules, which does not depend on the machine at all;
* PARITY (red before): the `mcp` line of `simplicio-video --help` names every tool of `mcp_server.TOOLS` (it forgot 10 of 32),
  and `COMANDOS` agrees with the frozen routing and with the two tables of `--json` derived from it;
* STRUCTURE (red before): one generic `except` in `cli.py`, and no branch after the parse for a command the table dispatches.

The only output that changes with U10a is the list of tools in the main `--help` (generated from `mcp_server.TOOLS`) and the
two or three paths of `docs/` and `colab/` in the help of `render` and the main epilog, which become the versioned URL
(`paths.doc_url`, as in `tests/test_wheel_links.py`).
"""
from __future__ import annotations

import ast
import contextlib
import importlib
import io
import os
import re
import sys
from pathlib import Path

import pytest

from simplicio_video import cli, mcp_server, paths

ROOT = Path(__file__).resolve().parents[1]
CLI_PY = ROOT / "src" / "simplicio_video" / "cli.py"

# (command, module of the package, function that runs it, error class that the CLI turns into `<cmd>: message`, "" = none).
# Frozen from cli.py of origin/main (a7ac9e3): the 20 commands that the CLI handles before argparse.
TRILHAS = [
    ("clone", "clone", "run_hypit", "CloneError"),
    ("montage", "montage", "run_montage", "MontageError"),
    ("opencut", "opencut", "run_opencut", "OpenCutError"),
    ("edit", "edit", "run_edit", "EditError"),
    ("shorts", "shorts", "run_shorts", "ShortsError"),
    ("media", "media", "run_media", "MediaError"),
    ("qc", "qc", "run_qc", "QcError"),
    ("toonflow", "toonflow", "run_toonflow", "ToonflowError"),
    ("moneyprinter", "moneyprinter", "run_moneyprinter", "MoneyPrinterError"),
    ("matchcut", "matchcut", "run_matchcut", "MatchcutError"),
    ("instagram", "instagram", "run_instagram", "InstagramError"),
    ("rea-video", "rea_video", "run_rea_video", "ReaVideoError"),
    ("video-to-skill", "video_to_skill", "run_video_to_skill", "VideoToSkillError"),
    ("voicestudio", "voicestudio", "run_voicestudio", ""),
    ("formats", "formats", "run_formats", "FormatError"),
    ("swap", "swap", "run_swap", ""),
    ("jobs", "jobs", "run_jobs", ""),
    ("social", "social", "run_social", ""),
    ("openverse", "openverse", "run_openverse", ""),
    ("busca", "busca", "run_busca", ""),
]
NOMES = [t[0] for t in TRILHAS]

# `--json` before the command moves to it (where the command takes it): everywhere, or only after one of these verbs.
JSON_EM_QUALQUER_LUGAR = ("busca", "qc", "voicestudio", "swap", "jobs", "social", "openverse", "formats")
JSON_SO_EM = {"instagram": ("where", "status", "skills"), "moneyprinter": ("generate",), "video-to-skill": ("where", "status")}


# ------------------------------------------------------------------------------------------------ the sealed box

@pytest.fixture
def caixa(tmp_path, monkeypatch):
    """No PATH, no network, an empty HOME and data folder: the commands cannot find a tool, a checkout or a real file."""
    (tmp_path / "home").mkdir()
    (tmp_path / "bin").mkdir()
    env = {"HOME": str(tmp_path / "home"), "PATH": str(tmp_path / "bin"), "SIMPLICIO_OFFLINE": "1",
           "SIMPLICIO_VIDEO_DATA": str(tmp_path / "data"), "NO_COLOR": "1", "COLUMNS": "100", "LANG": "C.UTF-8"}
    monkeypatch.setattr(os, "environ", env)
    return tmp_path


def _normaliza(texto: str, tmp: Path) -> str:
    for caminho, marca in ((str(tmp.resolve()), "<TMP>"), (str(tmp), "<TMP>"), (str(ROOT), "<ROOT>")):
        texto = texto.replace(caminho, marca)
    return texto


def roda(argv: list[str], tmp: Path) -> tuple[int | str, str, str]:
    """`cli.main(argv)` in-process: (return code, stdout, stderr). A `SystemExit` is the exit code, like in a shell."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(argv)
        except SystemExit as e:
            rc = e.code
            if isinstance(rc, str):
                print(rc, file=sys.stderr)
                rc = 1
            rc = 0 if rc is None else rc
    return rc, _normaliza(out.getvalue(), tmp), _normaliza(err.getvalue(), tmp)


def _confere(real: str, esperado: str) -> bool:
    """`~line` = the stream starts with that line (an argparse screen); anything else is the exact text."""
    if esperado.startswith("~"):
        return real.splitlines()[:1] == [esperado[1:]]
    return real == esperado


def _casos() -> list[tuple[str, list[str]]]:
    casos = []
    for nome in NOMES:
        # `edit <unknown>` would run video-use's setup.sh through bash (a clone): `edit transcribe` alone is refused before that.
        invalido = ["edit", "transcribe"] if nome == "edit" else [nome, "nao-existe-xyz"]
        casos += [(f"{nome} --help", [nome, "--help"]), (f"{nome} sub-invalido", invalido), (f"--json {nome}", ["--json", nome])]
    return casos + [
        ("clone --engine-help", ["clone", "--engine-help"]),
        ("clone --help --engine-help", ["clone", "--help", "--engine-help"]),
        ("clone -- --engine-help", ["clone", "--", "--engine-help"]),
        ("rea-video decompose --help", ["rea-video", "decompose", "--help"]),
        ("rea-video clone --help", ["rea-video", "clone", "--help"]),
        ("rea-video -v --help", ["rea-video", "-v", "--help"]),
        ("media burn --help", ["media", "burn", "--help"]),
        ("media -- --help", ["media", "--", "--help"]),
        ("edit grade --help", ["edit", "grade", "--help"]),
        ("edit nao-existe --help", ["edit", "nao-existe", "--help"]),
        ("video-to-skill extract --help", ["video-to-skill", "extract", "--help"]),
        ("montage tools --help", ["montage", "tools", "--help"]),
        ("montage clone --help", ["montage", "clone", "--help"]),
        ("shorts plan -h", ["shorts", "plan", "-h"]),
        ("--json instagram where", ["--json", "instagram", "where"]),
        ("--json instagram run", ["--json", "instagram", "run"]),
        ("--json moneyprinter generate", ["--json", "moneyprinter", "generate"]),
        ("--json moneyprinter run", ["--json", "moneyprinter", "run"]),
        ("--json video-to-skill status", ["--json", "video-to-skill", "status"]),
        ("--json video-to-skill clone", ["--json", "video-to-skill", "clone"]),
        ("--json busca status", ["--json", "busca", "status"]),
        ("--json qc congelado", ["--json", "qc", "congelado"]),
        ("--json --json formats list", ["--json", "--json", "formats", "list"]),
    ]


CASOS = _casos()

# case -> (return code, stdout, stderr), recorded on origin/main (a7ac9e3) with `roda` in the box above. "~line" = starts with it.
GOLDEN: dict[str, tuple[int | str, str, str]] = {
    'clone --help': (1, '', 'clone: Nem `hypit` nem `npx` foram encontrados no PATH. Instale o Hypit AI (https://github.com/hypit-ai/hypit).\n'),
    'clone sub-invalido': (1, '', 'clone: Nem `hypit` nem `npx` foram encontrados no PATH. Instale o Hypit AI (https://github.com/hypit-ai/hypit).\n'),
    '--json clone': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'montage --help': (0, '~usage: simplicio-video montage [-h] ...', ''),
    'montage sub-invalido': (1, '', 'montage: modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o OpenMontage. Instale fora do modo offline com `simplicio-video montage clone` ou aponte OPENMONTAGE_DIR para um checkout.\n'),
    '--json montage': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'opencut --help': (0, '~usage: simplicio-video opencut [-h] ...', ''),
    'opencut sub-invalido': (1, '', 'opencut: subcomando desconhecido: nao-existe-xyz (clone|dev|status|where)\n'),
    '--json opencut': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'edit --help': (0, '~usage: simplicio-video edit [-h] ...', ''),
    'edit sub-invalido': (1, '', 'edit: transcribe: informe FONTE.mp4 -o OUT.json\n'),
    '--json edit': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'shorts --help': (0, '~usage: simplicio-video shorts [-h] ...', ''),
    'shorts sub-invalido': (1, '', 'shorts: subcomando desconhecido: nao-existe-xyz (inspect|plan|cut|run)\n'),
    '--json shorts': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'media --help': (0, '~usage: simplicio-video media [-h] ...', ''),
    'media sub-invalido': (1, '', 'media: subcomando desconhecido: nao-existe-xyz (fetch|probe|audio|sheet|subs|burn|mask|replace-audio|voice-track)\n'),
    '--json media': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'qc --help': (0, '~usage: simplicio-video qc [-h] AÇÃO ...', ''),
    'qc sub-invalido': (2, '', '~usage: simplicio-video qc [-h] AÇÃO ...'),
    '--json qc': (2, '', '~usage: simplicio-video qc [-h] AÇÃO ...'),
    'toonflow --help': (0, '~usage: simplicio-video toonflow [-h] ...', ''),
    'toonflow sub-invalido': (1, '', 'toonflow: subcomando desconhecido: nao-existe-xyz (clone|serve|where|status|mcp)\n'),
    '--json toonflow': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'moneyprinter --help': (0, '~usage: simplicio-video moneyprinter [-h] ...', ''),
    'moneyprinter sub-invalido': (1, '', 'moneyprinter: subcomando desconhecido: nao-existe-xyz (clone|setup|serve|generate|run|where|status)\n'),
    '--json moneyprinter': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'matchcut --help': (0, '~usage: simplicio-video matchcut [-h] ...', ''),
    'matchcut sub-invalido': (1, '', "matchcut: subcomando desconhecido: 'nao-existe-xyz' (clone|where|status|setup|run)\n"),
    '--json matchcut': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'instagram --help': (0, '~usage: simplicio-video instagram [-h] ...', ''),
    'instagram sub-invalido': (1, '', "instagram: subcomando desconhecido: 'nao-existe-xyz' (clone|where|status|skills|skill|run)\n"),
    '--json instagram': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'rea-video --help': (0, '~usage: simplicio-video rea-video [-h] ...', ''),
    'rea-video sub-invalido': (1, '', 'rea-video: rea-video não está instalado no venv: rode `simplicio-video rea-video clone` e depois `simplicio-video rea-video setup`.\n'),
    '--json rea-video': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'video-to-skill --help': (0, '~usage: simplicio-video video-to-skill [-h] ...', ''),
    'video-to-skill sub-invalido': (1, '', "video-to-skill: subcomando desconhecido: 'nao-existe-xyz' (clone|setup|where|status|check|skill|extract|frame-at|clip|compile|merge|install)\n"),
    '--json video-to-skill': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    'voicestudio --help': (0, '~usage: simplicio-video voicestudio [-h] ...', ''),
    'voicestudio sub-invalido': (2, '', '~usage: simplicio-video voicestudio [-h] SUBCOMANDO ...'),
    '--json voicestudio': (2, '', '~usage: simplicio-video voicestudio [-h] SUBCOMANDO ...'),
    'formats --help': (0, '~usage: simplicio-video formats [-h] ...', ''),
    'formats sub-invalido': (2, '', '~usage: simplicio-video formats [-h] {list,show,prompt} ...'),
    '--json formats': (2, '', '~usage: simplicio-video formats [-h] {list,show,prompt} ...'),
    'swap --help': (0, '~usage: simplicio-video swap [-h] ...', ''),
    'swap sub-invalido': (2, '', '~usage: simplicio-video swap [-h] {providers,estimate,run,status} ...'),
    '--json swap': (2, '', '~usage: simplicio-video swap [-h] {providers,estimate,run,status} ...'),
    'jobs --help': (0, '~usage: simplicio-video jobs [-h] ...', ''),
    'jobs sub-invalido': (2, '', '~usage: simplicio-video jobs [-h] {submit,status,result,cancel,list,clean,_run} ...'),
    '--json jobs': (2, '', '~usage: simplicio-video jobs [-h] {submit,status,result,cancel,list,clean,_run} ...'),
    'social --help': (0, '~usage: simplicio-video social [-h] ...', ''),
    'social sub-invalido': (2, '', '~usage: simplicio-video social [-h] {providers,plan,check,recipe} ...'),
    '--json social': (2, '', '~usage: simplicio-video social [-h] {providers,plan,check,recipe} ...'),
    'openverse --help': (0, '~usage: simplicio-video openverse [-h] ...', ''),
    'openverse sub-invalido': (2, '', '~usage: simplicio-video openverse [-h] {search,get,library} ...'),
    '--json openverse': (2, '', '~usage: simplicio-video openverse [-h] {search,get,library} ...'),
    'busca --help': (0, '~usage: simplicio-video busca [-h] ...', ''),
    'busca sub-invalido': (2, '', '~usage: simplicio-video busca [-h] {consulta,pagina,status,log} ...'),
    '--json busca': (2, '', '~usage: simplicio-video busca [-h] {consulta,pagina,status,log} ...'),
    'clone --engine-help': (0, '~usage: simplicio-video clone [-h] ...', ''),
    'clone --help --engine-help': (0, '~usage: simplicio-video clone [-h] ...', ''),
    'clone -- --engine-help': (1, '', 'clone: Nem `hypit` nem `npx` foram encontrados no PATH. Instale o Hypit AI (https://github.com/hypit-ai/hypit).\n'),
    'rea-video decompose --help': (1, '', 'rea-video: rea-video não está instalado no venv: rode `simplicio-video rea-video clone` e depois `simplicio-video rea-video setup`.\n'),
    'rea-video clone --help': (0, '~usage: simplicio-video rea-video [-h] ...', ''),
    'rea-video -v --help': (1, '', 'rea-video: rea-video não está instalado no venv: rode `simplicio-video rea-video clone` e depois `simplicio-video rea-video setup`.\n'),
    'media burn --help': (0, 'media burn\n\n  burn FONTE SUBS -o OUT [--crf 20] [--preset medium]\n                                                   burn an SRT or ASS file into the picture (needs libass)\n\nExemplos:\n  simplicio-video media burn clean.mp4 subs.ass -o final.mp4\n', ''),
    'media -- --help': (1, '', 'media: subcomando desconhecido: -- (fetch|probe|audio|sheet|subs|burn|mask|replace-audio|voice-track)\n'),
    'edit grade --help': (0, "~edit grade FONTE.mp4 -o OUT.mp4 [--preset NOME | --filter 'FFMPEG'] | --analyze FONTE.mp4 | --list-presets", ''),
    'edit nao-existe --help': (0, '~usage: simplicio-video edit [-h] ...', ''),
    'video-to-skill extract --help': (0, 'uso: simplicio-video video-to-skill extract VIDEO --out PASTA [--autorizo]\nExtrai um vídeo local para PASTA (nova ou vazia, com pasta-mãe existente). Uma URL exige --autorizo, só roda no terminal, e o motor não verifica o seu direito de uso. Grava PASTA.extract.json de procedência.\n', ''),
    'montage tools --help': (0, '~usage: simplicio-video montage tools [-h] {list,info} ...', ''),
    'montage clone --help': (0, '~usage: simplicio-video montage [-h] ...', ''),
    'shorts plan -h': (0, '~usage: simplicio-video shorts [-h] ...', ''),
    '--json instagram where': (1, '', 'instagram: instagram não encontrado: rode `simplicio-video instagram clone` ou defina INSTAGRAM_DIR.\n'),
    '--json instagram run': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    '--json moneyprinter generate': (1, '', 'moneyprinter: MoneyPrinterTurbo não encontrado: rode `simplicio-video moneyprinter clone` ou defina MONEYPRINTER_DIR.\n'),
    '--json moneyprinter run': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    '--json video-to-skill status': (0, '~{', ''),
    '--json video-to-skill clone': (2, '', '~usage: simplicio-video [-h] [--version] [--json] COMANDO ...'),
    '--json busca status': (0, '~{', ''),
    '--json qc congelado': (2, '', '~usage: simplicio-video qc congelado [-h] [--min-s S] [--json] mp4'),
    '--json --json formats list': (0, '~[', ''),
}


@pytest.mark.parametrize("nome, argv", CASOS, ids=[c[0] for c in CASOS])
def test_each_track_command_behaves_as_it_did_before_the_table(caixa, nome, argv):
    esperado = GOLDEN[nome]
    rc, out, err = roda(argv, caixa)
    assert rc == esperado[0], (nome, rc, out[:300], err[:300])
    assert _confere(out, esperado[1]), (nome, "stdout", out[:600])
    assert _confere(err, esperado[2]), (nome, "stderr", err[:600])


def test_the_golden_covers_every_case():
    assert set(GOLDEN) == {c[0] for c in CASOS}


# ------------------------------------------------------------------------ routing and errors, with fake modules

def _modulo(nome: str):
    return importlib.import_module(f"simplicio_video.{nome}")


@pytest.mark.parametrize("cmd, modulo, run, erro", TRILHAS, ids=NOMES)
def test_the_command_runs_its_module_with_the_words_after_it_and_returns_its_code(cmd, modulo, run, erro, monkeypatch):
    chamadas = []
    monkeypatch.setattr(_modulo(modulo), run, lambda argv: chamadas.append(list(argv)) or 7)
    assert cli.main([cmd, "uma", "--coisa", "x"]) == 7
    assert chamadas == [["uma", "--coisa", "x"]]


@pytest.mark.parametrize("cmd, modulo, run, erro", [t for t in TRILHAS if t[3]], ids=[t[0] for t in TRILHAS if t[3]])
def test_the_error_class_of_the_module_becomes_the_message_of_the_command_and_exit_1(cmd, modulo, run, erro, monkeypatch, capsys):
    mod = _modulo(modulo)

    def falha(argv):
        raise getattr(mod, erro)("boom")

    monkeypatch.setattr(mod, run, falha)
    assert cli.main([cmd, "x"]) == 1
    cap = capsys.readouterr()
    assert cap.out == ""
    # The QcError messages already carry `qc: `, so that one is printed as it is: every other command adds its own name.
    assert cap.err == ("boom\n" if cmd == "qc" else f"{cmd}: boom\n")


@pytest.mark.parametrize("cmd, modulo, run, erro", [t for t in TRILHAS if not t[3]], ids=[t[0] for t in TRILHAS if not t[3]])
def test_a_command_without_an_error_class_lets_the_exit_of_its_module_through(cmd, modulo, run, erro, monkeypatch):
    def sai(argv):
        raise SystemExit(5)

    monkeypatch.setattr(_modulo(modulo), run, sai)
    with pytest.raises(SystemExit) as e:
        cli.main([cmd, "x"])
    assert e.value.code == 5


@pytest.mark.parametrize("cmd, modulo, run, erro", [t for t in TRILHAS if t[3]], ids=[t[0] for t in TRILHAS if t[3]])
def test_an_error_of_another_class_is_not_swallowed(cmd, modulo, run, erro, monkeypatch):
    def falha(argv):
        raise KeyError("fora do contrato")

    monkeypatch.setattr(_modulo(modulo), run, falha)
    with pytest.raises(KeyError):
        cli.main([cmd, "x"])


def _roteia(monkeypatch, argv: list[str]) -> list:
    """Run `cli.main(argv)` with every track module faked: [(command, words the module got)] or [] if the parser answered."""
    chamadas = []
    for cmd, modulo, run, _ in TRILHAS:
        monkeypatch.setattr(_modulo(modulo), run, lambda a, cmd=cmd: chamadas.append((cmd, list(a))) or 0)
    with contextlib.suppress(SystemExit), contextlib.redirect_stdout(io.StringIO()):
        cli.main(argv)
    return chamadas


@pytest.mark.parametrize("argv, vai_ao_modulo", [
    # an argparse command: `--help` is ours (also `-h`), unless it comes after `--` (then it is a value)
    (["toonflow", "--help"], False),
    (["toonflow", "serve", "-h"], False),
    (["toonflow", "serve", "--", "--help"], True),
    (["shorts", "plan", "-h"], False),
    # clone: the help is Hypit's, ours is `--engine-help` (before `--`)
    (["clone", "--help"], True),
    (["clone", "-h"], True),
    (["clone"], True),
    (["clone", "--engine-help"], False),
    (["clone", "--help", "--engine-help"], False),
    (["clone", "--", "--engine-help"], True),
    # rea-video: the words that are not its own commands (or help) belong to the upstream, `--help` included
    (["rea-video", "--help"], False),
    (["rea-video", "clone", "--help"], False),
    (["rea-video", "decompose", "--help"], True),
    (["rea-video", "-v", "--help"], True),
    # media, edit and video-to-skill: a verb of the module prints its own help
    (["media", "--help"], False),
    (["media", "burn", "--help"], True),
    (["media", "nao-existe", "--help"], False),
    (["media", "--", "--help"], True),
    (["edit", "--help"], False),
    (["edit", "grade", "--help"], True),
    (["edit", "nao-existe", "--help"], False),
    (["video-to-skill", "--help"], False),
    (["video-to-skill", "extract", "--help"], True),
    (["video-to-skill", "nao-existe", "--help"], False),
    # montage: the verbs of the registry have an argparse of their own inside montage.py
    (["montage", "--help"], False),
    (["montage", "tools", "--help"], True),
    (["montage", "clone", "--help"], False),
    # no help word: always the module
    (["media", "burn", "x.mp4"], True),
    (["formats", "list"], True),
])
def test_who_prints_the_help(monkeypatch, argv, vai_ao_modulo):
    chamadas = _roteia(monkeypatch, argv)
    assert bool(chamadas) is vai_ao_modulo, (argv, chamadas)
    if vai_ao_modulo:
        assert chamadas == [(argv[0], argv[1:])]


def test_the_json_that_comes_first_goes_to_the_command_that_takes_it(monkeypatch):
    chamadas = _roteia(monkeypatch, ["--json", "busca", "consulta", "x", "--", "--json"])
    assert chamadas == [("busca", ["consulta", "x", "--json", "--", "--json"])]
    assert _roteia(monkeypatch, ["--json", "--json", "formats", "list"]) == [("formats", ["list", "--json"])]
    assert _roteia(monkeypatch, ["--json", "instagram", "where", "--skills"]) == [("instagram", ["where", "--json", "--skills"])]
    assert _roteia(monkeypatch, ["--json", "video-to-skill", "status"]) == [("video-to-skill", ["status", "--json"])]
    assert _roteia(monkeypatch, ["--json", "moneyprinter", "generate", "--out", "o"]) == [("moneyprinter", ["generate", "--json", "--out", "o"])]


@pytest.mark.parametrize("argv, mensagem", [
    (["--json", "instagram", "run"], "--json não vale para `instagram run` (só em where, status, skills)"),
    # sic: with no verb the message keeps the blank inside the backticks (`instagram `): origin/main prints it so, and so does this
    (["--json", "instagram"], "--json não vale para `instagram ` (só em where, status, skills)"),
    (["--json", "moneyprinter", "serve"], "--json não vale para `moneyprinter serve` (só em generate)"),
    (["--json", "video-to-skill", "clone"], "--json não vale para `video-to-skill clone` (só em where, status)"),
    (["--json", "clone"], "--json não vale para `clone` (esse subcomando não tem saída JSON)"),
    (["--json", "montage", "status"], "--json não vale para `montage` (esse subcomando não tem saída JSON)"),
    (["--json", "toonflow", "status"], "--json não vale para `toonflow` (esse subcomando não tem saída JSON)"),
])
def test_the_json_that_the_command_does_not_take_is_a_usage_error(monkeypatch, capsys, argv, mensagem):
    assert _roteia(monkeypatch, argv) == []
    assert mensagem in capsys.readouterr().err


def test_the_two_json_tables_are_the_ones_of_before():
    assert set(cli._PASSTHROUGH_JSON) == set(JSON_EM_QUALQUER_LUGAR)
    assert {k: tuple(v) for k, v in cli._JSON_SO_EM.items()} == JSON_SO_EM


# ------------------------------------------------------------------------------------------------ the table

def test_the_table_has_the_20_track_commands_and_where_to_find_each():
    assert set(cli.COMANDOS) == set(NOMES)
    for cmd, modulo, run, erro in TRILHAS:
        c = cli.COMANDOS[cmd]
        mod = c.modulo()  # the loader of the command: it imports the module now
        assert (c.nome, mod.__name__, c.run, c.erro) == (cmd, f"simplicio_video.{modulo}", run, erro), cmd
        assert callable(getattr(mod, c.run)), cmd
        if c.erro:
            assert issubclass(getattr(mod, c.erro), Exception), cmd


def test_the_json_tables_are_derived_from_the_table():
    """One place says where `--json` goes: a new command cannot be in the table and forgotten here."""
    assert set(cli._PASSTHROUGH_JSON) == {n for n, c in cli.COMANDOS.items() if c.json_em == ("*",)}
    assert {k: tuple(v) for k, v in cli._JSON_SO_EM.items()} == {n: c.json_em for n, c in cli.COMANDOS.items()
                                                                  if c.json_em and c.json_em != ("*",)}


def test_the_table_says_who_prints_the_help():
    assert {n: c.ajuda for n, c in cli.COMANDOS.items() if c.ajuda != "argparse"} == {
        "clone": "upstream", "montage": "propria", "edit": "propria", "media": "propria", "rea-video": "propria",
        "video-to-skill": "propria"}
    for c in cli.COMANDOS.values():
        if c.ajuda == "propria":
            assert hasattr(c.modulo(), c.ajuda_em), c.nome  # the verbs (or the test) that the module answers for


def test_the_table_is_immutable_data():
    c = cli.COMANDOS["media"]
    with pytest.raises(Exception):
        c.nome = "outro"  # type: ignore[misc]


# -------------------------------------------------------------------------------- the `mcp` line of the main help

def _tools_do_help(texto: str) -> list[str]:
    linha = next(ln for ln in texto.splitlines() if re.match(r"\s+mcp\s+servidor MCP", ln))
    return linha.split("com as tools video.", 1)[1].split("/")


def test_the_main_help_names_every_tool_of_the_mcp_server():
    ferramentas = [nome.removeprefix("video.") for nome, _fn, _desc in mcp_server.TOOLS]
    no_help = _tools_do_help(cli.MAIN_DESC)
    assert not set(ferramentas) - set(no_help), f"`--help` forgot {sorted(set(ferramentas) - set(no_help))}"
    assert not set(no_help) - set(ferramentas), f"`--help` names tools the server does not have: {sorted(set(no_help) - set(ferramentas))}"
    assert no_help == ferramentas  # in the order of the server, so a new tool shows up where it was registered


def test_the_main_help_the_cli_prints_is_the_generated_one(caixa):
    rc, out, _ = roda(["--help"], caixa)
    assert rc == 0
    assert _tools_do_help(out) == [nome.removeprefix("video.") for nome, _fn, _desc in mcp_server.TOOLS]
    assert len(_tools_do_help(out)) == len(mcp_server.TOOLS) == 32


def test_the_main_help_points_to_the_versioned_url_of_the_docs_not_to_a_checkout_path(caixa):
    rc, out, _ = roda(["--help"], caixa)
    assert rc == 0
    assert paths.doc_url("docs/custos.md") in out
    assert paths.doc_url("docs/decisoes/ADR-0003-fluxo-100-script.md") in out
    assert " docs/custos.md" not in out and "(medido e oficial): docs/" not in out


def test_the_help_of_render_points_to_the_versioned_url_of_the_docs_and_the_notebook(caixa):
    rc, out, _ = roda(["render", "--help"], caixa)
    assert rc == 0
    assert paths.doc_url("docs/custos.md") in out
    assert paths.doc_url("colab/render.ipynb") in out
    assert "em docs/custos.md" not in out and "para colab/render.ipynb" not in out


# ----------------------------------------------------------------------------------------- the shape of cli.py

def _cli_tree() -> ast.Module:
    return ast.parse(CLI_PY.read_text(encoding="utf8"))


def test_cli_has_one_error_handler_for_the_tracks_and_one_for_status():
    """17 `except <Track>Error as e` blocks (one per command, two of them after the parse) became the single handler of the dispatch.

    The count is the one of the plan's metric (`except .*Error as e` over the text of cli.py: 17 before), so the generic handler,
    which names its class by data, does not count and `status.StatusError` does."""
    assert len(re.findall(r"except .*Error as e", CLI_PY.read_text(encoding="utf8"))) <= 2
    handlers = [n for n in ast.walk(_cli_tree()) if isinstance(n, ast.ExceptHandler) and n.name == "e"
                and "Error" in ast.unparse(n.type) and "FileNotFoundError" not in ast.unparse(n.type)]
    assert [ast.unparse(h.type) for h in handlers] == ["status.StatusError"]


def test_no_branch_after_the_parse_runs_a_command_the_table_dispatches():
    """The branches `a.cmd == "clone"` and `== "montage"` after the parse are gone: the table answers for those before argparse sees them.

    They were reachable only with a leading `--` (`simplicio-video -- clone`, `-- montage status`), an invocation nobody generates
    (not the MCP server, not the docs, not a test) that already ended in `AttributeError: 'Namespace' object has no attribute
    'contrato'` for every other command (`-- media probe x`, `-- opencut where`, `-- edit`, `-- swap`). They were removed on purpose and
    now fail like the rest: an accepted deviation from "identical behaviour" for a call that was never supported (see the PR #223)."""
    comparados = {c.value for n in ast.walk(_cli_tree()) if isinstance(n, ast.Compare)
                  and ast.unparse(n.left) == "a.cmd" for c in n.comparators if isinstance(c, ast.Constant)}
    assert not comparados & set(NOMES), sorted(comparados & set(NOMES))


def test_cli_does_not_know_the_internals_of_the_track_modules():
    """The words that decide who prints a track's help come from the table, not from `media.SUBCOMMANDS` & co. written in cli.py."""
    fonte = CLI_PY.read_text(encoding="utf8")
    for interno in ("rea_video.repassa", "media.SUBCOMMANDS", "edit.SUBCOMMANDS", "video_to_skill.SUBCOMMANDS", "montage.REGISTRY_COMMANDS"):
        assert interno not in fonte, interno


def test_every_module_the_table_dispatches_to_is_still_a_static_import_of_cli():
    """tests/test_childio.py finds the modules the MCP server can reach by reading the imports (inside functions too), and the MCP
    runs `cli.main`; tests/test_motor_sem_vendas.py refuses an `import_module` by a name it cannot read. So each loader of the
    table is a plain `from . import x` (`clone.py` was only reachable through the CLI: a dynamic import would drop it from the scan)."""
    importados = {a.name for n in ast.walk(_cli_tree()) if isinstance(n, ast.ImportFrom) and n.level == 1 for a in n.names}
    assert {c.modulo().__name__.rpartition(".")[2] for c in cli.COMANDOS.values()} <= importados
    assert "import_module" not in CLI_PY.read_text(encoding="utf8")

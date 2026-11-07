"""rea-video track: reverse-engineers a video shot by shot (live action, AI video, 3D, code render, mixed) and plans a
remake (https://github.com/JuneYaooo/rea-video, MIT; declared in its pyproject.toml, no LICENSE file at the pin).

The checkout is pinned in tools.TOOLS['rea_video'] and runs as a separate program. `setup` builds a venv of its own in
the simplicio-video data folder and installs the checkout there. Only this track's own commands (clone, setup, where,
status) and its help are handled here; every other word, and every upstream flag such as `--env-file`, goes unchanged
to the `rea-video` of that venv, from the folder the user is in. The track never imports the upstream package and never
downloads a video (that is `media fetch`, with --autorizo). Its output is an analysis folder (breakdown.json,
report.html) that the user reads and decides on; it is outside the deterministic render.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import childio, paths, tools, trilha_base
from .rede import offline as _offline
from .trilha_base import Trilha

REA_VIDEO_REPO = tools.get("rea_video").source
OWN_SUBCOMMANDS = ("clone", "setup", "where", "status")
HELP_WORDS = ("-h", "--help", "help")
EXTRA = "ocr"  # the upstream extra that brings the OCR of the report (rapidocr-onnxruntime)
VLM_KEY_NAMES = ("REA_VLM_API_KEY", "VIDEO_ANALYSIS_API_KEY", "GEMINI3_API_KEY")  # keys the upstream reads for its vision model

USAGE = (
    f"rea-video ({REA_VIDEO_REPO}, MIT)\n"
    "  simplicio-video rea-video clone [dir]     # baixa o commit fixado (REA_VIDEO_DIR ou ~/.simplicio-video/tools/rea_video)\n"
    "  simplicio-video rea-video setup           # venv próprio com o checkout (pip: precisa de rede); recusa o modo offline\n"
    "  simplicio-video rea-video <comando> ...   # repassa tudo ao rea-video do venv, na pasta em que você está\n"
    "                                            # ex.: simplicio-video rea-video decompose ref.mp4 -o out/ref --no-stems\n"
    "                                            # a ajuda desses comandos é a do upstream, em chinês: rea-video decompose --help\n"
    "  simplicio-video rea-video where           # imprime o checkout\n"
    "  simplicio-video rea-video status          # checkout, venv, OCR, ffmpeg; as chaves VLM aparecem só como definida ou não\n"
    "Analisa um vídeo que já existe e devolve a pasta do relatório (breakdown.json, report.html). Não baixa vídeo: para isso, media fetch com --autorizo.\n"
    "Sem --vlm, nada sai da máquina além dos downloads de modelo abaixo. Com --vlm, até 60 planos vão ao provedor de modelo de visão\n"
    "configurado, cada um num clipe de até 12 s em 480p, e o vídeo inteiro em 480p com áudio: é um terceiro. Endereço e chave vêm de\n"
    "REA_VLM_BASE_URL e REA_VLM_API_KEY (ou VIDEO_ANALYSIS_* e GEMINI3_*), do ambiente ou de --env-file. A chave nunca é impressa.\n"
    "O rea-video lê um .env da pasta em que você roda: rode a análise numa pasta sem .env de outro projeto.\n"
    "Downloads no primeiro uso: modelo de separação de voz do GitHub, cerca de 67 MB (--no-stems pula); um detector de rosto pequeno\n"
    "(sem ele, cai para Haar); OCR em japonês (--ocr-lang ja) do ModelScope. Tudo vai para REA_VIDEO_MODELS.\n"
    "OCR de legendas e textos na tela precisa de rapidocr-onnxruntime, que não instala em todo Python (3.13 não; 3.11 sim).\n"
    "Para ele: REA_VIDEO_PYTHON=python3.11 simplicio-video rea-video setup (antes, apague a pasta venv da pasta de dados).\n"
    "remake-run e capsule-draft importam e executam código da pasta do capsule-cinema que você indicar: só aponte para pasta sua e de confiança.\n"
    "Estado do upstream (memória e preferências) em REA_VIDEO_HOME, padrão ~/.simplicio-video/rea-video-data/home (não o ~/.rea-video).\n"
    "Exige ffmpeg no PATH e Python 3.10 ou mais novo. clone e setup precisam de rede e recusam o modo offline (SIMPLICIO_OFFLINE=1).\n"
    "Fica fora do render determinístico: a análise é um arquivo para você ler; não entra num contrato sozinha.\n"
)


class ReaVideoError(Exception):
    pass


T = Trilha("rea_video", "REA_VIDEO_DIR", "REA_VIDEO_DATA_DIR")


def find_rea_video_dir() -> Path | None:
    """The pinned checkout (REA_VIDEO_DIR, else SIMPLICIO_TOOLS_DIR/rea_video, else ~/.simplicio-video/tools/rea_video)."""
    return T.find()


def data_dir() -> Path:
    """Where the venv and the upstream state live: absolute, and outside the checkout so a re-clone never wipes them."""
    return T.data_dir()


def venv_bin(name: str) -> Path:
    sub, ext = ("Scripts", ".exe") if os.name == "nt" else ("bin", "")
    return data_dir() / "venv" / sub / (name + ext)


def _rea_video_exe() -> Path | None:
    exe = venv_bin("rea-video")
    return exe if exe.is_file() else None


def clone_rea_video(target: Path | None = None) -> Path:
    """Install rea-video at its pinned commit (target overrides the location). Never in offline mode."""
    return T.clone(target, erro=ReaVideoError, offline=_offline, acao=(
        "clonar o rea-video. "
        "Rode `simplicio-video rea-video clone` fora do modo offline ou aponte REA_VIDEO_DIR para um checkout."
    ))


def _checkout_head(d: Path) -> str | None:
    """The commit that is really in the checkout (the pin is only what it should be)."""
    return T.head(d)  # without .git, git would answer with the parent repository: not this checkout (T.head gives None)


def _warn_if_not_pinned(d: Path) -> None:
    """pip installs whatever checkout is there: say so when it is not the pinned commit."""
    ref = tools.pinned_ref(tools.get("rea_video"))
    head = _checkout_head(d)
    if head and head != ref:
        print(f"aviso: o checkout {d} está em {head[:12]}, não no commit fixado {ref[:12]}; o venv vai receber esse outro "
              "commit. Rode `simplicio-video rea-video clone` para voltar ao pino.", file=sys.stderr)


def _print_ffmpeg() -> None:
    if shutil.which("ffmpeg"):
        print("ffmpeg: encontrado no PATH")
    else:
        print("ffmpeg: não encontrado no PATH (a análise precisa dele)")


def _setup(d: Path, args: list[str]) -> int:
    if args:
        raise ReaVideoError(f"setup não recebe argumentos; recebi: {args[0]}")
    if _offline():
        raise ReaVideoError(
            "modo offline (SIMPLICIO_OFFLINE=1): não vou instalar o rea-video, porque o pip precisa de rede. "
            "Rode `simplicio-video rea-video setup` fora do modo offline."
        )
    _warn_if_not_pinned(d)
    data = data_dir()
    venv = data / "venv"
    try:
        data.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ReaVideoError(f"não consegui criar a pasta de dados {data}: {e}") from None
    py = str(venv_bin("python"))
    try:
        if not venv_bin("python").is_file():  # an existing venv is kept: to change its Python, delete the folder
            base = os.environ.get("REA_VIDEO_PYTHON", "").strip() or sys.executable  # e.g. python3.11 for the OCR extra
            rc = subprocess.call([base, "-m", "venv", str(venv)])
            if rc != 0:
                print(f"rea-video: não consegui criar o venv (código {rc}); a saída acima diz por quê.", file=sys.stderr)
                return rc
        if subprocess.call([py, "-m", "pip", "install", f"{d}[{EXTRA}]"]) != 0:
            # rapidocr-onnxruntime has no release for every Python. The analysis needs the core; OCR is optional upstream.
            print(f"aviso: o extra {EXTRA} não instalou; instalo só o núcleo. Sem OCR, legendas e textos na tela ficam de "
                  "fora da análise, e o rea-video avisa e segue.", file=sys.stderr)
            rc = subprocess.call([py, "-m", "pip", "install", str(d)])
            if rc != 0:
                print(f"rea-video: não consegui instalar o rea-video com o pip (código {rc}); a saída acima diz por quê.",
                      file=sys.stderr)
                return rc
    except OSError as e:
        raise ReaVideoError(f"não consegui rodar o Python para criar o venv ou o pip: {e}") from None
    except KeyboardInterrupt:
        print("rea-video: interrompido durante o setup", file=sys.stderr)
        return 130
    if _rea_video_exe() is None:
        raise ReaVideoError(f"o pip terminou, mas o comando rea-video não apareceu em {venv_bin('rea-video').parent}.")
    print(f"rea-video instalado no venv {venv}, a partir de {d}.")
    print(f"ocr: {_ocr_state()}")
    print("As dependências vêm do pip sem hash: o upstream não tem lock. O commit é o fixado em tools.py.")
    _print_ffmpeg()
    return 0


def _ocr_state() -> str:
    """Whether the upstream OCR imports in the venv, asked of the venv's own Python (nothing is guessed from files)."""
    py = venv_bin("python")
    if not py.is_file():
        return "sem venv"
    probe = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('rapidocr_onnxruntime') else 1)"
    try:
        rc = subprocess.call([str(py), "-c", probe], timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "não verificado"
    return "instalado" if rc == 0 else "não instalado (sem legendas nem textos na tela)"


def _status(d: Path | None) -> None:
    t = tools.get("rea_video")
    ref = tools.pinned_ref(t)
    print(f"rea-video, licença {t.license}: {REA_VIDEO_REPO}")
    print(f"commit fixado: {ref}")
    if d is None:
        print("checkout: não encontrado (rode `simplicio-video rea-video clone`)")
    else:
        head = _checkout_head(d)
        print(f"checkout: {d}")
        if head is None:
            print("commit do checkout: desconhecido")
        else:
            print(f"commit do checkout: {head}{'' if head == ref else ' (diferente do fixado)'}")
    exe = _rea_video_exe()
    if exe is None:
        print("venv: não existe (rode `simplicio-video rea-video setup`)")
    else:
        print(f"venv: {exe.parent.parent}")
    print(f"ocr: {_ocr_state()}")
    print(f"dados: {data_dir()}")
    if (Path.cwd() / ".env").is_file():
        print("aviso: há um .env nesta pasta; o rea-video o lê sozinho, com os endereços e as chaves dele. "
              "Rode a análise numa pasta sem .env de outro projeto.")
    _print_ffmpeg()
    for name in VLM_KEY_NAMES:  # the names only: the upstream reads these, and their values are never printed
        print(f"{name}: {'definida' if os.environ.get(name, '').strip() else 'não definida'}")


def repassa(args: list[str]) -> bool:
    """True when the words are rea-video's: everything but this track's own commands and help. Upstream flags such as
    `-v` or `--env-file FILE` come before its command, so they go to rea-video too."""
    return bool(args) and args[0] not in (*OWN_SUBCOMMANDS, *HELP_WORDS)


def _upstream_env() -> dict[str, str]:
    """The environment of rea-video: the user's own, plus where its state and models go by default (the data folder)."""
    env = dict(os.environ)
    base = data_dir()
    env.setdefault("REA_VIDEO_HOME", str(base / "home"))
    env.setdefault("REA_VIDEO_MODELS", str(base / "models"))
    return env


def _vlm_free(args: list[str]) -> bool:
    """True when this call cannot reach the vision model: --no-vlm, or a command that never calls it (and no --vlm,
    no --env-file). Then the upstream does not receive the VLM settings at all."""
    if "--vlm" in args or any(a == "--env-file" or a.startswith("--env-file=") for a in args):
        return False
    cmd = next((a for a in args if not a.startswith("-")), "")
    return "--no-vlm" in args or cmd in NO_VLM_COMMANDS


def _run_upstream(args: list[str]) -> int:
    exe = _rea_video_exe()
    if exe is None:
        raise ReaVideoError("rea-video não está instalado no venv: rode `simplicio-video rea-video clone` e depois "
                            "`simplicio-video rea-video setup`.")
    try:
        return subprocess.call([str(exe), *args], env=_mcp_env() if _vlm_free(args) else _upstream_env())
    except KeyboardInterrupt:  # Ctrl+C reaches the upstream too; it decides how to stop
        return 130
    except OSError as e:
        raise ReaVideoError(f"não consegui rodar {exe}: {e}") from None


def _own(args: list[str]) -> int:
    first, rest = args[0], args[1:]
    if first == "clone":
        if len(rest) > 1:
            raise ReaVideoError(f"clone recebe no máximo uma pasta; argumento a mais: {rest[1]}")
        print(clone_rea_video(Path(rest[0]) if rest else None))
        return 0
    if first == "status":
        if rest:
            raise ReaVideoError(f"status não recebe argumentos; argumento a mais: {rest[0]}")
        _status(find_rea_video_dir())
        return 0
    d = find_rea_video_dir()
    if d is None:
        raise ReaVideoError("rea-video não encontrado: rode `simplicio-video rea-video clone` ou defina REA_VIDEO_DIR.")
    if first == "where":
        if rest:
            raise ReaVideoError(f"where não recebe argumentos; argumento a mais: {rest[0]}")
        print(d)
        return 0
    if first == "setup":
        return _setup(d, rest)
    raise ReaVideoError(f"comando desconhecido: {first}")


def run_rea_video(args: list[str]) -> int:
    if not args or args[0] in HELP_WORDS:
        print(USAGE)
        return 0
    if repassa(args):
        return _run_upstream(args)
    return _own(args)


# ---- MCP section: a closed list of commands and flags, run in a private folder -------------------------------------
# Over MCP the calling agent plays the vision model (`review` writes the tasks and the frame paths, the agent looks and
# fills the answers, `apply-review` merges them), so nothing goes to a third party. Checked in the upstream at the pin:
# summary, probe, tiles, stems, review, apply-review and remake-plan make no network call and no paid call; the model
# downloads (voice separation, face detector) are fetched by `stems` and `decompose` on first use. `remake-plan` only
# writes jobs.json (it never runs the capsule-cinema folder). `--vlm` and `--env-file` are never accepted here, and the
# upstream prefs (vlm=on) cannot turn the vision model back on: decompose always gets `--no-vlm`.

MCP_TIMEOUT = 300  # s; the slow commands (decompose, stems) are jobs, not inline calls
JOB_JOBS = ("decompose", "stems")  # the commands that run as background jobs
JOB_CWD_PREFIX = "rea-video-job-"
NO_VLM_COMMANDS = ("stems", "probe", "summary", "review", "apply-review", "remake-plan", "tiles")  # never call the vision model
TERMINAL_ONLY = ("setup", "remake-run", "capsule-draft", "prefs", "correct", "memory", "eval", "capsule", "assemble")
VLM_ENV_PREFIXES = ("REA_VLM_", "VIDEO_ANALYSIS_", "GEMINI3_")
_NUM = re.compile(r"^\d+$")
_FLOAT = re.compile(r"^\d+(\.\d+)?$")

# command -> (positionals [(kind, required)], flags {name: kind}, required flag destinations)
# kinds: file/dir (absolute and existing), abs (absolute, may not exist), int, float, text, bool, ("choice", a, b, ...)
SPECS: dict[str, tuple[list[tuple[str, bool]], dict[str, object], tuple[str, ...]]] = {
    "summary": ([("file", True)], {}, ()),
    "probe": ([("file", True)], {"--tags": "bool"}, ()),
    "tiles": ([("file", True)], {"--start": "float", "--end": "float", "--every": "pfloat", "--cols": "int", "--cell": "int",
                                 "--max": "int", "-o": "outfile", "--out": "outfile"}, ("out",)),
    "stems": ([("file", True)], {"-o": "outdir", "--out": "outdir"}, ("out",)),
    "review": ([("adir", True)], {"--force": "bool"}, ()),
    "apply-review": ([("adir", True), ("file", False)], {"--by": "text"}, ()),
    "remake-plan": ([("breakdown", True)], {"--capsule-root": "abs", "--engine": "text", "--labels": "text",
                                       "--mode": ("choice", "first_last_frame", "image_to_video", "text_to_video")}, ()),
    "decompose": ([("file", True)], {"-o": "outdir", "--out": "outdir", "--no-vlm": "bool", "--no-whole": "bool", "--no-ocr": "bool",
                                      "--ocr-lang": ("choice", "zh", "ja"), "--no-packaging": "bool", "--no-stems": "bool",
                                      "--workers": "int", "--engine": "text", "--meta": "file"}, ("out",)),
}
_SPECS = SPECS  # the old name: callers that read it keep working
_DEST = {"-o": "out", "--out": "out"}


def _terminal(what: str) -> ReaVideoError:
    return ReaVideoError(f"{what}: só pelo terminal (simplicio-video rea-video ...). Pelo MCP nada vai a um modelo de visão "
                         "de terceiros, nada gasta e nada roda código de fora; o agente que chama faz o papel do modelo "
                         "com review e apply-review.")


def _plain_path(value: str, label: str) -> Path:
    """Absolute, no '..', and no component that is a symlink: an MCP path cannot be steered somewhere else."""
    if not os.path.isabs(value):
        raise ReaVideoError(f"{label}: caminho absoluto, recebi {value!r} (pelo MCP a pasta de trabalho é privada)")
    path = Path(value)
    if ".." in path.parts:
        raise ReaVideoError(f"{label}: sem '..' no caminho: {value}")
    cur = Path(path.parts[0])
    for part in path.parts[1:]:
        cur = cur / part
        if cur.is_symlink():
            raise ReaVideoError(f"{label}: {cur} é um link simbólico; pelo MCP só caminho real")
    return path


def _analysis_dir(d: Path, label: str) -> None:
    """A folder an earlier `decompose` wrote: it holds a real breakdown.json and none of its entries is a link
    (the commands that rewrite files there would otherwise follow a link to somewhere else)."""
    bd = d / "breakdown.json"
    if not bd.is_file() or bd.is_symlink():
        raise ReaVideoError(f"{label}: {d} não é uma pasta de análise (falta o breakdown.json do decompose)")
    for entry in d.iterdir():
        if entry.is_symlink():
            raise ReaVideoError(f"{label}: {entry} é um link simbólico dentro da pasta de análise")
    rj = d / "remake" / "jobs.json"
    if rj.is_symlink():
        raise ReaVideoError(f"{label}: {rj} é um link simbólico")


def _check_value(kind, value: str, label: str) -> str:
    if "\0" in value or not value:
        raise ReaVideoError(f"{label}: valor inválido")
    if isinstance(kind, tuple):  # ("choice", a, b, ...)
        if value not in kind[1:]:
            raise ReaVideoError(f"{label}: use um destes: {', '.join(kind[1:])}")
    elif kind == "int":
        if not _NUM.match(value) or int(value) < 1:
            raise ReaVideoError(f"{label}: inteiro maior que zero, recebi {value!r}")
    elif kind in ("float", "pfloat"):
        if not _FLOAT.match(value) or (kind == "pfloat" and float(value) <= 0):
            raise ReaVideoError(f"{label}: número em segundos{' maior que zero' if kind == 'pfloat' else ''} (sem sinal), recebi {value!r}")
    elif kind == "text":
        if value.startswith("-") or len(value) > 300:
            raise ReaVideoError(f"{label}: texto simples, sem começar com '-'")
    else:  # file | abs | adir | breakdown | outfile | outdir
        path = _plain_path(value, label) if kind != "file" else Path(value)
        if kind == "file":
            if not os.path.isabs(value):
                raise ReaVideoError(f"{label}: caminho absoluto, recebi {value!r} (pelo MCP a pasta de trabalho é privada)")
            if not path.is_file():
                raise ReaVideoError(f"{label}: arquivo não encontrado: {value}")
        elif kind == "adir":
            if not path.is_dir():
                raise ReaVideoError(f"{label}: pasta não encontrada: {value}")
            _analysis_dir(path, label)
        elif kind == "breakdown":
            if path.name != "breakdown.json" or not path.is_file():
                raise ReaVideoError(f"{label}: use o breakdown.json de uma pasta de análise: {value}")
            _analysis_dir(path.parent, label)
        elif kind == "outfile":
            if os.path.lexists(path):
                raise ReaVideoError(f"{label}: {value} já existe; pelo MCP não se sobrescreve arquivo")
            if not path.parent.is_dir():
                raise ReaVideoError(f"{label}: a pasta {path.parent} precisa existir")
            derived = re.compile(re.escape(path.stem) + r"_\d+" + re.escape(path.suffix) + "$")
            clash = [e.name for e in path.parent.iterdir() if derived.match(e.name)]
            if clash:
                raise ReaVideoError(f"{label}: já existe {clash[0]} ao lado; o tiles grava {path.stem}_N{path.suffix}")
        elif kind == "outdir":
            if os.path.lexists(path) and (not path.is_dir() or any(path.iterdir())):
                raise ReaVideoError(f"{label}: {value} já existe e não está vazia; pelo MCP a saída vai para uma pasta nova ou vazia")
    return value


def mcp_command(args) -> list[str]:
    """Validate the words of an MCP call and return the canonical upstream arguments (command first), or raise
    ReaVideoError. A closed list: the open commands, their own flags, absolute paths; everything else is terminal-only."""
    try:
        words = shlex.split(args) if isinstance(args, str) else [str(a) for a in args]
    except ValueError as e:
        raise ReaVideoError(f"argumentos ilegíveis: {e}") from None
    if not words:
        raise ReaVideoError("diga o comando: " + ", ".join(SPECS) + " (setup e o resto, só pelo terminal)")
    cmd, rest = words[0], words[1:]
    if cmd.startswith("-"):
        raise _terminal(f"a opção global {cmd}")
    if cmd in TERMINAL_ONLY or cmd not in SPECS:
        raise _terminal(f"o comando {cmd}")
    pos_spec, flags, required = SPECS[cmd]
    positionals: list[str] = []
    out: list[str] = []
    seen: set[str] = set()
    checks: list[tuple] = []  # values are checked after every token: a terminal-only flag is named before a path problem
    i = 0
    while i < len(rest):
        tok = rest[i]
        i += 1
        if not tok.startswith("-"):
            if len(positionals) >= len(pos_spec):
                raise ReaVideoError(f"{cmd}: argumento a mais: {tok}")
            checks.append((pos_spec[len(positionals)][0], tok, f"{cmd} {tok[:40]}"))
            positionals.append(tok)
            continue
        name, eq, inline = tok.partition("=") if tok.startswith("--") else (tok, "", "")
        if name in ("--vlm", "--env-file"):
            raise _terminal(name)
        kind = flags.get(name)
        if kind is None:
            raise _terminal(f"a opção {name} em {cmd}")
        dest = _DEST.get(name, name)
        if dest in seen:
            raise ReaVideoError(f"{cmd}: {name} repetida")
        seen.add(dest)
        if kind == "bool":
            if eq:
                raise ReaVideoError(f"{cmd}: {name} não recebe valor")
            out.append(name)
            continue
        if eq:
            value = inline
        elif i < len(rest):
            value, i = rest[i], i + 1
        else:
            raise ReaVideoError(f"{cmd}: {name} precisa de um valor")
        checks.append((kind, value, f"{cmd} {name}"))
        out += [name, value]
    for kind, value, label in checks:
        _check_value(kind, value, label)
    for n, (_, req) in enumerate(pos_spec):
        if req and n >= len(positionals):
            raise ReaVideoError(f"{cmd}: faltou o argumento {n + 1}")
    for dest in required:
        if dest not in seen:
            raise ReaVideoError(f"{cmd}: -o/--out é obrigatório e absoluto (pelo MCP a pasta de trabalho é privada)")
    argv = [cmd, *positionals, *out]
    if cmd == "decompose" and "--no-vlm" not in argv:
        argv.append("--no-vlm")  # the upstream prefs may say vlm=on: say no, every time
    return argv


def job_args(args) -> list[str]:
    """The canonical arguments of a background job: `decompose` or `stems` (raises ReaVideoError for anything else)."""
    argv = mcp_command(args)
    if argv[0] not in JOB_JOBS:
        raise ReaVideoError(f"só {' e '.join(JOB_JOBS)} rodam como tarefa; recebi {argv[0]}")
    return argv


def make_job_cwd() -> str:
    """A private empty folder for a job child. Folders of jobs that ended without a result (failed, cancelled, lost) and
    are older than a week are swept here, on the next submit; rmdir only removes an empty one."""
    return str(trilha_base.job_cwd(JOB_CWD_PREFIX))


def drop_job_cwd(path) -> None:
    """Remove the private folder of a finished job (only ours: under the temp folder, with our prefix, empty)."""
    trilha_base.drop_job_cwd(path, JOB_CWD_PREFIX)


class ReaVideoRecusa(ReaVideoError):
    """A refusal at the submit of a background job: `jobs` tells it as a `JobError` with the same text (`JOB.erro_terceiro`). A subclass
    on purpose: the check the runner repeats (`_job_argv`) raises the plain `ReaVideoError`, and the runner tells that one by its own
    name in job.json, as it always did."""


def _job_prepare(params: dict, confirm_yes: bool, origin: str) -> tuple[dict, bool, dict]:
    """`decompose` (WITHOUT the vision model) or `stems` as a task: nothing leaves the machine and nothing is spent, so MCP may submit
    them. The arguments pass the same closed list as the MCP call (--vlm and --env-file are refused whatever the origin; --no-vlm is
    always added). The child starts in a private empty folder, so the upstream never reads a stray .env. A refusal is a
    `ReaVideoRecusa` (`jobs` tells it as `JobError`)."""
    try:
        paths.check_job_keys(params, {"args"}, ReaVideoError)
        args = job_args(params.get("args"))
        if _rea_video_exe() is None:
            raise ReaVideoError("rea-video não está instalado no venv: `simplicio-video rea-video clone` e depois `setup` "
                                "(setup só pelo terminal)")
    except ReaVideoError as e:
        raise ReaVideoRecusa(str(e)) from None
    cwd = make_job_cwd()
    return {"args": args, "cwd": cwd}, False, {"cwd": cwd, "estimate_usd": None, "confirmed": None}


def _job_argv(p: dict, origin: str | None = None) -> list[str]:  # origin: the job's own (unused by rea-video)
    """Checked again here, in the runner, so state edited on disk after the submit cannot add --vlm or --env-file. The refusal is the
    plain `ReaVideoError`, not a `ReaVideoRecusa`: it stays what it was (`jobs` does not turn it into a `JobError`)."""
    return ["rea-video", *job_args(p["args"])]


def _job_result(p: dict, last_json: dict | None) -> dict | None:
    drop_job_cwd(p.get("cwd"))
    args = p["args"]
    out = Path(args[args.index("-o" if "-o" in args else "--out") + 1])
    if args[0] == "stems":
        files = {n: out / "stems" / f"{n}.wav" for n in ("original", "vocals", "music")}
        if not files["original"].is_file():
            return None
        return {"out": str(out), **{n: str(f) for n, f in files.items() if f.is_file()}}
    bd = out / "breakdown.json"
    try:
        raw = bd.read_bytes()
        summ = json.loads(raw).get("summary") or {}
    except (OSError, ValueError, AttributeError):
        return None
    report = out / "report.html"
    return {"out": str(out), "breakdown": str(bd), "breakdown_sha256": hashlib.sha256(raw).hexdigest(),
            "report": str(report) if report.is_file() else None, "verdict": summ.get("verdict"), "shots": summ.get("shots"),
            "confidence": summ.get("confidence"), "vlm": summ.get("vlm")}


# No `cleanup`: the private folder of a job that failed or was cancelled stays (the age sweep in `make_job_cwd` removes it on a later
# submit), as it did when `jobs.py` wrapped these hooks.
JOB = paths.JobSpec("rea-video", prepare=_job_prepare, argv=_job_argv, result=_job_result, erro_terceiro=ReaVideoRecusa)


def _mcp_env() -> dict[str, str]:
    """The environment of an MCP child: the upstream state and models stay put, the vision-model settings are removed."""
    return {k: v for k, v in _upstream_env().items() if not k.startswith(VLM_ENV_PREFIXES)}


def _mcp_exec(argv: list[str], cwd, env: dict[str, str]) -> tuple[int, str]:
    """Run the upstream to completion with no stdin, in `cwd`, capturing what it prints. The one place the MCP path starts
    it. It leads its own process group, so a timeout kills the upstream and everything it started."""
    timed_out = False
    # SIGTERM, SIGHUP and Ctrl+C (also the one that lands while Popen starts the child) kill the upstream's group on the way out
    # and end the engine the usual way, so mcp_run removes its private folder (childio.guarded_child)
    with contextlib.ExitStack() as guard:
        try:
            proc = guard.enter_context(childio.guarded_child(
                argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                cwd=cwd, env=env, start_new_session=(os.name != "nt")))
        except OSError as e:
            raise ReaVideoError(f"não consegui rodar {argv[0]}: {e}") from None
        try:
            so, se = proc.communicate(timeout=MCP_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            with contextlib.suppress(OSError):
                os.killpg(proc.pid, 9) if os.name != "nt" else proc.kill()
            so, se = proc.communicate()
        finally:
            if proc.poll() is None:
                with contextlib.suppress(OSError):
                    os.killpg(proc.pid, 9) if os.name != "nt" else proc.kill()
    text = "\n".join(x.strip() for x in (so, se) if x and x.strip())
    if timed_out:
        return 124, f"{text}\nrea-video passou de {MCP_TIMEOUT} s e foi encerrado".strip()
    return proc.returncode, text


def mcp_run(args) -> tuple[int, str]:
    """Run one open command (not decompose: that is a job) in a private empty folder; returns (exit code, output)."""
    argv = mcp_command(args)
    if argv[0] in JOB_JOBS:
        raise ReaVideoError(f"{argv[0]} roda como tarefa em segundo plano; envie pelo video.rea-video")
    exe = _rea_video_exe()
    if exe is None:
        raise ReaVideoError("rea-video não está instalado no venv: `simplicio-video rea-video clone` e depois `setup` "
                            "(setup só pelo terminal).")
    cwd = tempfile.mkdtemp(prefix="rea-video-cwd-")
    try:
        return _mcp_exec([str(exe), *argv], cwd, _mcp_env())
    finally:
        shutil.rmtree(cwd, ignore_errors=True)

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
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import tools
from .toonflow import _offline

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


def find_rea_video_dir() -> Path | None:
    """The pinned checkout (REA_VIDEO_DIR, else SIMPLICIO_TOOLS_DIR/rea_video, else ~/.simplicio-video/tools/rea_video)."""
    return tools.find("rea_video")


def data_dir() -> Path:
    """Where the venv and the upstream state live: absolute, and outside the checkout so a re-clone never wipes them."""
    explicit = os.environ.get("REA_VIDEO_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(data).expanduser() if data else Path.home() / ".simplicio-video"
    return (base / "rea-video-data").resolve()


def venv_bin(name: str) -> Path:
    sub, ext = ("Scripts", ".exe") if os.name == "nt" else ("bin", "")
    return data_dir() / "venv" / sub / (name + ext)


def _rea_video_exe() -> Path | None:
    exe = venv_bin("rea-video")
    return exe if exe.is_file() else None


@contextlib.contextmanager
def _checkout_at(target: Path):
    """Point tools.install at `target` for the duration of the block, then restore the environment."""
    previous = os.environ.get("REA_VIDEO_DIR")
    os.environ["REA_VIDEO_DIR"] = str(target)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("REA_VIDEO_DIR", None)
        else:
            os.environ["REA_VIDEO_DIR"] = previous


def clone_rea_video(target: Path | None = None) -> Path:
    """Install rea-video at its pinned commit (target overrides the location). Never in offline mode."""
    if _offline():
        raise ReaVideoError(
            "modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o rea-video. "
            "Rode `simplicio-video rea-video clone` fora do modo offline ou aponte REA_VIDEO_DIR para um checkout."
        )
    try:
        if target is None:
            return Path(tools.install("rea_video"))
        with _checkout_at(Path(target).expanduser()):
            return Path(tools.install("rea_video"))
    except tools.ToolError as e:
        raise ReaVideoError(str(e)) from None


def _checkout_head(d: Path) -> str | None:
    """The commit that is really in the checkout (the pin is only what it should be)."""
    if not (d / ".git").exists():  # without .git, git would answer with the parent repository: not this checkout
        return None
    try:
        return tools._git("rev-parse", "HEAD", cwd=d)
    except tools.ToolError:
        return None


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


def _run_upstream(args: list[str]) -> int:
    exe = _rea_video_exe()
    if exe is None:
        raise ReaVideoError("rea-video não está instalado no venv: rode `simplicio-video rea-video clone` e depois "
                            "`simplicio-video rea-video setup`.")
    try:
        return subprocess.call([str(exe), *args], env=_upstream_env())
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

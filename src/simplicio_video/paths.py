"""Locate the plugin home (checkout root with plugin.json) and the engine data (schema/, schemas/, templates/, motion/).

Os dados vivem dentro do pacote (`src/simplicio_video/data/`, issue #74): um `pip install` numa pasta limpa basta
para `list`, `validate` e `render`. SIMPLICIO_VIDEO_HOME (checkout) continua valendo e troca os dados para os do checkout.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import __version__, hostos

PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
ENGINE_DIR = PKG_DIR / "engine"
REPO_URL = "https://github.com/simpletibr/simplicio-videos"
_RELEASE = re.compile(r"\d+(?:\.\d+){1,3}(?:\.post\d+)?", re.ASCII)  # X.Y[.Z[.W]][.postN]: the versions that have a tag


def doc_url(rel: str) -> str:
    """URL, at the tag of this release, of a repository file (a doc, a voice guide, the Colab notebook, the intake).

    Those folders belong to the checkout and are not in the wheel: a message that ships in the package names the file by
    this URL, never by a path that only exists next to the source. Only a release has a tag: a development, pre-release or
    dirty version (0.8.1.dev0, 0.9.0rc1, 0.8.0+dirty) points at `main` instead of a `v<version>` that would be a 404."""
    ref = f"v{__version__}" if _RELEASE.fullmatch(__version__) else "main"
    return f"{REPO_URL}/blob/{ref}/{rel}"


def _is_home(p: Path) -> bool:
    pj = p / "plugin.json"
    if not hostos.is_file(pj):  # a folder that cannot be searched is not the home, and not a PermissionError either
        return False
    try:
        return json.loads(pj.read_text(encoding="utf8")).get("name") == "videos"
    except (OSError, ValueError):
        return False


def home(start: Path | None = None) -> Path:
    """SIMPLICIO_VIDEO_HOME, else walk up from `start`/cwd to the checkout, else the package itself (wheel install)."""
    env = os.environ.get("SIMPLICIO_VIDEO_HOME")
    if env:
        return Path(env).resolve()
    for base in [start, Path.cwd(), PKG_DIR]:
        if base is None:
            continue
        for p in [base.resolve(), *base.resolve().parents]:
            if _is_home(p):
                return p
    return DATA_DIR


def workspace_dir() -> Path:
    """$SIMPLICIO_WORKSPACE, else ~/.simplicio-video/workspaces/default
    (https://github.com/simpletibr/simplicio-videos/blob/main/arquivo/docs/factory/contracts.md).

    Lives here and not in `commands/setup.py`: `install` needs it before the `.venv` exists, under the system python, and
    `setup` imports PyYAML at the top. This module is standard library only."""
    env = os.environ.get("SIMPLICIO_WORKSPACE")
    if env:
        try:
            return Path(env).expanduser()
        except RuntimeError:  # `~someone` of a user that does not exist: the text is used as it is
            return Path(env)
    return hostos.home_absoluta("SIMPLICIO_WORKSPACE") / ".simplicio-video" / "workspaces" / "default"


def user_home(escolha: str | None = None) -> Path:
    """The home as an absolute path, or hostos.SemCasa (a RuntimeError): for the modules that may import nothing but `paths`."""
    return hostos.home_absoluta(escolha)


def data_dir() -> Path:
    """Dados do motor: os do pacote, ou os do checkout apontado por SIMPLICIO_VIDEO_HOME."""
    env = os.environ.get("SIMPLICIO_VIDEO_HOME")
    if env:
        return Path(env).resolve() / "src" / "simplicio_video" / "data"
    return DATA_DIR


def schema_path(d: Path | None = None) -> Path:
    return (d or data_dir()) / "schema" / "contract.schema.json"


def tts_python() -> str:
    """Python with kokoro-onnx/soundfile for the local provider."""
    return os.environ.get("SIMPLICIO_TTS_PY", str(hostos.home_dir() / ".local/share/simplicio-tts/cbvenv/bin/python"))


def node_env() -> dict:
    env = dict(os.environ)
    extra = hostos.home_dir() / ".local/node22/bin"
    if extra.is_dir():
        env["PATH"] = f"{extra}{os.pathsep}{env.get('PATH', '')}"
    ff = env.get("SIMPLICIO_FFMPEG_DIR")  # pinned ffmpeg toolchain (ADR-0003): HyperFrames + master.sh + build.mjs use it
    if ff:
        env["PATH"] = f"{ff}{os.pathsep}{env['PATH']}"
        env.setdefault("HYPERFRAMES_FFMPEG_PATH", str(Path(ff) / "ffmpeg"))
        env.setdefault("HYPERFRAMES_FFPROBE_PATH", str(Path(ff) / "ffprobe"))
    return env


# ------------------------------------------------------------------------------------------------- background jobs
# What `jobs` and the tracks share and neither may import from the other (a track that imports `jobs`, which imports the track,
# was the cycle montage <-> jobs <-> moneyprinter): the protocol of a task, where its state lives and how long it is given to stop.

JOBS_GRACE_S = 15.0


@dataclass(frozen=True)
class JobSpec:
    """One kind of background task, as the track that owns it declares it (`JOB` in the module); `jobs` only runs it.

    kind            the id in `simplicio.job/v1` and in the closed list `jobs.KINDS` (never renamed)
    prepare         `(params, confirm_yes, origin) -> (params, spends, extra)` at submit: the checks, the canonical params that go to
                    the state, whether it spends money, and the extra fields of the state (`estimate_usd`, `confirmed`, ...)
    argv            `(params, origin) -> list[str]` the words after `python -m simplicio_video`, built again in the runner from the
                    state on disk (a state edited after the submit must not add a flag); `origin` is None unless `origem_mcp`
    result          `(params, last_json) -> dict | None` after a `done` run: what the task left, from the last JSON line it printed
    cleanup         `(params) -> None` after a `failed` or `cancelled` run, which never reaches `result` (its private folder)
    erro_terceiro   the track's own error class: what `prepare` and `argv` raise for a refusal becomes a `JobError` with the same
                    text (None: the hooks raise `JobError` themselves)
    origem_mcp      True when `argv` turns the origin of the job into a gate of the child (montage: `--sob-mcp`): only then does
                    `argv` get the origin
    texto_terceiro  `(tail) -> (text, notice)` when the output of a failed run is a third party's text: the state keeps it only in
                    `untrusted_erro` with `aviso`, never in `error` (None: the tail is ours and stays in `error`)
    """
    kind: str
    prepare: Callable
    argv: Callable
    result: Callable
    cleanup: Callable | None = None
    erro_terceiro: type[Exception] | None = None
    origem_mcp: bool = False
    texto_terceiro: Callable | None = None


def check_job_keys(params: dict, allowed: set[str], erro: type[Exception]) -> None:
    """The first check of every `prepare`: a key the kind does not know is refused with `erro` (a `JobError`, or the track's own)."""
    extra = sorted(set(params) - allowed)
    if extra:
        raise erro(f"parâmetros desconhecidos: {', '.join(extra)} (aceitos: {', '.join(sorted(allowed))})")


def data_root() -> Path:
    """The data folder of the engine, where `jobs/<id>/job.json` lives ($SIMPLICIO_VIDEO_DATA, with `~` expanded, else
    ~/.simplicio-video): the folder an MCP output may never be written into. The one place that reads the variable: the tools lock,
    the update cache, `busca`, the Openverse library and the data of the tracks add their subfolder (and their own `.resolve()`) to it.
    Not resolved: a relative value stays relative, as it always was."""
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    return Path(data).expanduser() if data else hostos.home_absoluta("SIMPLICIO_VIDEO_DATA") / ".simplicio-video"


jobs_root = data_root  # the name `jobs` and `montage` (and their tests) call: the same function


def jobs_grace_s() -> float:
    """Seconds between the SIGINT and the SIGKILL when a job is stopped ($SIMPLICIO_JOBS_GRACE_S, default 15). The runner reads it
    here and so does the child it starts (the environment is how it reaches `moneyprinter run`, which stops its upstream first)."""
    try:
        return float(os.environ.get("SIMPLICIO_JOBS_GRACE_S", "") or JOBS_GRACE_S)
    except ValueError:
        return JOBS_GRACE_S

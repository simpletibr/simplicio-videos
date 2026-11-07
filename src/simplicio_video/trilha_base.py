"""What every external track repeats, in one place: the checkout, its clone, its data folder, the commit really in it, the private cwd of
a background job and the stop of a process group. Below the tracks: it imports `tools`, `rede` and `paths`, never a track.

* `Trilha(nome, env_dir, env_data)` declares a track by its name in tools.TOOLS, the variable that points at its checkout
  (`{NAME}_DIR`, which `tools.checkout_dir` reads) and, when it has a data folder, the variable that points at that (`{NAME}_DATA_DIR`).
  `clone` installs through `tools.install(name, dir=)`, so a clone into a chosen folder never writes the process environment (each
  track used to point `tools.install` at it by setting `<NAME>_DIR` and put it back, which leaks across threads).
* `job_cwd` and `drop_job_cwd` are the private empty folder a background job runs in (and its sweep and removal).
* `stop_group` and `on_term` are what the server tracks use to stop a child and its whole group on Ctrl+C or SIGTERM.

The bodies are the ones the tracks carry today (toonflow, moneyprinter, rea_video, video_to_skill, matchcut, montage); the tracks
migrate to this module later and keep their own names as aliases wherever a test replaces them.
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import paths, rede, tools


@dataclass(frozen=True)
class Trilha:
    nome: str                     # the name in tools.TOOLS ("toonflow", "rea_video", ...)
    env_dir: str                  # the variable that points at the checkout ("TOONFLOW_DIR"): {NAME}_DIR, as tools.checkout_dir reads it
    env_data: str | None = None   # the variable that points at the data folder ("TOONFLOW_DATA_DIR"); None: the track has none

    def find(self) -> Path | None:
        """The pinned checkout, or None when it is not installed (`tools.find`: {NAME}_DIR, else SIMPLICIO_{NAME}_DIR, else the tools cache)."""
        return tools.find(self.nome)

    def data_dir(self) -> Path:
        """Where the track keeps its venv and its data, absolute and outside the checkout, so a re-clone never wipes it: `env_data`,
        else <paths.data_root(): SIMPLICIO_VIDEO_DATA, or ~/.simplicio-video>/<name with hyphens>-data (`rea_video` keeps
        its data in `rea-video-data`)."""
        explicit = os.environ.get(self.env_data) if self.env_data else None
        if explicit:
            return Path(explicit).expanduser().resolve()
        return (paths.data_root() / f"{self.nome.replace('_', '-')}-data").resolve()

    def clone(self, target: Path | None = None, *, erro: type[Exception], acao: str | None = None,
              offline: Callable[[], bool] | None = None) -> Path:
        """Install the track at its pinned commit (`target` overrides the location). Never in offline mode: the refusal is `erro` with
        the phrase of rede.PREFIXO_OFFLINE and `acao` (the rest of the sentence, with whatever the track adds: the command to run
        instead). `offline` is the function that says whether the network is off (default rede.offline): a track hands in its own
        `_offline` name, the one its tests replace. A failing install is `erro` with the message of tools."""
        if (offline or rede.offline)():
            if acao is None:
                acao = f"clonar a trilha {self.nome}. Aponte {self.env_dir} para um checkout já feito."
            raise erro(rede.PREFIXO_OFFLINE + acao)
        try:
            if target is None:
                return Path(tools.install(self.nome))
            return Path(tools.install(self.nome, dir=Path(target).expanduser()))
        except tools.ToolError as e:
            raise erro(str(e)) from None

    def head(self, d: Path) -> str | None:
        """The commit that is really in the checkout `d` (the pin is only what it should be), or None (`tools.git_head`)."""
        return tools.git_head(d)

    def venv_python(self, d: Path | None = None) -> Path:
        """The Python of the venv under `d` (default: the data folder of the track)."""
        sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
        return (d if d is not None else self.data_dir()) / "venv" / sub[0] / sub[1]


def _prefixo_valido(prefixo: str) -> None:
    if not prefixo or any(c in prefixo for c in "/\\*?[]"):
        raise ValueError(f"prefixo de pasta de tarefa inválido: {prefixo!r}")


def job_cwd(prefixo: str, *, idade_max_s: int = 7 * 86400) -> Path:
    """A private empty folder for a job child. Folders of jobs that ended without a result (failed, cancelled, lost) and are older
    than `idade_max_s` (a week) are swept here, on the next submit; rmdir only removes an empty one."""
    _prefixo_valido(prefixo)
    base = Path(tempfile.gettempdir())
    cutoff = time.time() - idade_max_s
    for old in base.glob(prefixo + "*"):
        with contextlib.suppress(OSError):
            if old.stat().st_mtime < cutoff:
                old.rmdir()
    return Path(tempfile.mkdtemp(prefix=prefixo))


def drop_job_cwd(p, prefixo: str) -> None:
    """Remove the private folder of a finished job (only ours: directly under the temp folder, with our prefix, empty)."""
    _prefixo_valido(prefixo)
    p = Path(str(p or ""))
    if p.name.startswith(prefixo) and p.parent == Path(tempfile.gettempdir()):
        with contextlib.suppress(OSError):
            p.rmdir()


def on_term(signum, frame):
    raise KeyboardInterrupt  # `kill <this process>` stops the server the same way Ctrl+C does


def stop_group(proc: subprocess.Popen, grace_s: float = 15) -> None:
    """SIGINT to the server's whole process group; SIGKILL if it outlives `grace_s` seconds; then a SIGKILL sweep of the group.
    The sweep matters: a helper the server started may still be finishing after the server exited, and it must not
    keep running (or keep port 3000 open without login) once this returns."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGINT)
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)

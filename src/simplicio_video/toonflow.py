"""Toonflow track: open-source AI studio for short dramas, comic dramas and videos
(https://github.com/HBAI-Ltd/Toonflow-app, MIT).

The checkout is pinned in tools.TOOLS['toonflow'] and runs as a separate program: one Bun process that serves the
API and the web UI. It is a human-in-the-loop creation tool outside the deterministic render. Whatever it produces
enters a contract as a file with a hash, so the render stays reproducible.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import tools

TOONFLOW_REPO = tools.get("toonflow").source
# Fixed in the Toonflow server (apps/server/src/index.ts). The server listens on every interface with no login,
# so `serve` only starts when the caller says LAN_FLAG on purpose.
PORT = 3000
LAN_FLAG = "--lan"

USAGE = (
    f"Toonflow ({TOONFLOW_REPO}, MIT)\n"
    "  simplicio-video toonflow clone [dir]   # clona o Toonflow no commit fixado (TOONFLOW_DIR ou ~/.simplicio-video/tools)\n"
    f"  simplicio-video toonflow serve {LAN_FLAG}   # bun install --frozen-lockfile, build e start: http://localhost:{PORT}\n"
    "  simplicio-video toonflow where         # imprime o checkout\n"
    f"Sem {LAN_FLAG}, serve não sobe: o Toonflow escuta em 0.0.0.0:{PORT} (todas as interfaces) e não tem login.\n"
    f"Para ficar só no seu computador, use o docker compose do próprio Toonflow (127.0.0.1:{PORT}) ou bloqueie a porta no firewall.\n"
    "Dados em TOONFLOW_DATA_DIR (padrão ~/.simplicio-video/toonflow-data), fora do checkout.\n"
    "O Toonflow fica fora do render determinístico: o que ele gera entra num contrato como arquivo com hash.\n"
)


class ToonflowError(Exception):
    pass


def _offline() -> bool:
    return os.environ.get("SIMPLICIO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


def find_toonflow_dir() -> Path | None:
    """The pinned checkout (TOONFLOW_DIR, else SIMPLICIO_TOOLS_DIR/toonflow, else ~/.simplicio-video/tools/toonflow)."""
    return tools.find("toonflow")


def data_dir() -> Path:
    """Where the server keeps its data, absolute: the server runs inside the checkout, so a relative path would
    point somewhere else. Outside the checkout by default, so a re-clone never wipes it."""
    explicit = os.environ.get("TOONFLOW_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(data).expanduser() if data else Path.home() / ".simplicio-video"
    return (base / "toonflow-data").resolve()


@contextlib.contextmanager
def _checkout_at(target: Path):
    """Point tools.install at `target` for the duration of the block, then restore the environment."""
    previous = os.environ.get("TOONFLOW_DIR")
    os.environ["TOONFLOW_DIR"] = str(target)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TOONFLOW_DIR", None)
        else:
            os.environ["TOONFLOW_DIR"] = previous


def clone_toonflow(target: Path | None = None) -> Path:
    """Install Toonflow at its pinned commit (target overrides the location). Never in offline mode."""
    if _offline():
        raise ToonflowError(
            "modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o Toonflow. "
            "Instale fora do modo offline com `simplicio-video toonflow clone` ou aponte TOONFLOW_DIR para um checkout."
        )
    try:
        if target is None:
            return Path(tools.install("toonflow"))
        with _checkout_at(Path(target).expanduser()):
            return Path(tools.install("toonflow"))
    except tools.ToolError as e:
        raise ToonflowError(str(e)) from None


def _bun() -> str:
    bun = shutil.which("bun")
    if not bun:
        raise ToonflowError("bun não encontrado (https://bun.sh); a versão exigida está no campo packageManager do package.json do checkout.")
    return bun


def _serve(d: Path, args: list[str]) -> int:
    if [a for a in args if a != LAN_FLAG]:
        raise ToonflowError(f"serve aceita só {LAN_FLAG}: a porta é fixa no Toonflow ({PORT}).")
    if LAN_FLAG not in args:
        raise ToonflowError(
            f"serve não sobe sem {LAN_FLAG}: o Toonflow escuta em 0.0.0.0:{PORT} (todas as interfaces) e não tem login, "
            "então qualquer máquina da mesma rede alcança a API e os arquivos. "
            f"Para ficar só no seu computador, use o docker compose do próprio Toonflow (127.0.0.1:{PORT}) ou bloqueie a porta no firewall. "
            f"Para aceitar a exposição, rode `simplicio-video toonflow serve {LAN_FLAG}`."
        )
    bun = _bun()
    data = data_dir()
    try:
        for step in ([bun, "install", "--frozen-lockfile"], [bun, "run", "build:server"]):
            if subprocess.call(step, cwd=d) != 0:
                return 1
    except KeyboardInterrupt:
        print("toonflow: interrompido durante a instalação ou o build", file=sys.stderr)
        return 130
    (data / "workspaces" / "myProject").mkdir(parents=True, exist_ok=True)
    print(f"Toonflow em http://localhost:{PORT}, também em todas as interfaces e sem login (dados: {data}). Ctrl+C para parar.")
    try:
        return subprocess.call([bun, "run", "start:server"], cwd=d, env={**os.environ, "TOONFLOW_DATA_DIR": str(data)})
    except KeyboardInterrupt:  # Ctrl+C is how the user stops the server: not an error
        return 0


def run_toonflow(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if first not in ("clone", "serve", "where"):
        raise ToonflowError(f"subcomando desconhecido: {first} (clone|serve|where)")
    if first == "clone":
        print(clone_toonflow(Path(args[1]) if len(args) > 1 else None))
        return 0
    d = find_toonflow_dir()
    if d is None:
        raise ToonflowError("Toonflow não encontrado: rode `simplicio-video toonflow clone` ou defina TOONFLOW_DIR.")
    if first == "where":
        print(d)
        return 0
    return _serve(d, args[1:])

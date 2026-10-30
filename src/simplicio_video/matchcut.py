"""match-cut track: an agent skill for product films in the match-cut relay style
(https://github.com/Sac-Y/match-cut, MIT).

The checkout is pinned in tools.TOOLS['matchcut']. It is a skill (SKILL.md, scripts, references) for Claude Code or
Codex, not a program: this module only downloads the pinned commit and points at it. It never runs the skill, never uses
npx and never calls Renoise (the skill's video, music and voice service, which needs the user's own sign-in and paid
credits). It asks for and stores no secret.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

from . import tools
from .toonflow import _offline

MATCHCUT_REPO = tools.get("matchcut").source

USAGE = (
    f"match-cut ({MATCHCUT_REPO}, MIT)\n"
    "  simplicio-video matchcut clone [dir]   # baixa o commit fixado (MATCHCUT_DIR ou ~/.simplicio-video/tools)\n"
    "  simplicio-video matchcut where         # imprime o caminho do SKILL.md\n"
    "  simplicio-video matchcut status        # instalado? commit fixado e commit do checkout\n"
    "É um skill de agente (Claude Code ou Codex): o comando só baixa e aponta, não roda o skill.\n"
    "O uso do skill exige login no Renoise pela sua conta e gasta créditos pagos; este comando nunca chama o Renoise.\n"
)


class MatchcutError(Exception):
    pass


def find_matchcut_dir() -> Path | None:
    """The pinned checkout (MATCHCUT_DIR, else SIMPLICIO_TOOLS_DIR/matchcut, else ~/.simplicio-video/tools/matchcut)."""
    return tools.find("matchcut")


@contextlib.contextmanager
def _checkout_at(target: Path):
    """Point tools.install at `target` for the duration of the block, then restore the environment."""
    previous = os.environ.get("MATCHCUT_DIR")
    os.environ["MATCHCUT_DIR"] = str(target)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MATCHCUT_DIR", None)
        else:
            os.environ["MATCHCUT_DIR"] = previous


def clone_matchcut(target: Path | None = None) -> Path:
    """Download the pinned commit (target overrides the location). Never in offline mode."""
    if _offline():
        raise MatchcutError(
            "modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o match-cut. "
            "Rode `simplicio-video matchcut clone` fora do modo offline ou aponte MATCHCUT_DIR para um checkout."
        )
    try:
        if target is None:
            return Path(tools.install("matchcut"))
        with _checkout_at(Path(target).expanduser()):
            return Path(tools.install("matchcut"))
    except tools.ToolError as e:
        raise MatchcutError(str(e)) from None


def run_matchcut(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if first not in ("clone", "where", "status"):
        raise MatchcutError(f"subcomando desconhecido: {first} (clone|where|status)")
    if first == "clone":
        print(clone_matchcut(Path(args[1]) if len(args) > 1 else None))
        return 0
    t = tools.get("matchcut")
    d = find_matchcut_dir()
    if first == "where":
        if d is None:
            raise MatchcutError("match-cut não encontrado: rode `simplicio-video matchcut clone` ou defina MATCHCUT_DIR.")
        print(d / "SKILL.md")
        return 0
    print(f"match-cut ({t.license}) {t.source}")
    print(f"commit fixado: {tools.pinned_ref(t)}")
    if d is None:
        print("instalado: não (rode `simplicio-video matchcut clone`)")
        return 0
    try:
        head = tools._git("rev-parse", "HEAD", cwd=d)
    except tools.ToolError:
        head = "desconhecido"
    print("instalado: sim")
    print(f"SKILL.md: {d / 'SKILL.md'}")
    print(f"commit do checkout: {head}{'' if head == tools.pinned_ref(t) else ' (diferente do fixado)'}")
    return 0

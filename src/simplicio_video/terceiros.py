"""What a third-party program receives, and the helpers the sandbox tracks share. A leaf: at import it needs only the standard library.

ENVIRONMENT. A child of a third-party track must not get a key, a token or any SIMPLICIO_* of the shell: each module passes a closed
list of names. `NUCLEO_ENV` is what every one of those lists has in common; `env_para_terceiro(extra)` is that core plus the names the
module asks for on top (its proxy and certificate variables, its own key, ...), read from the environment and only when they exist.
A name that is in neither is never passed, whatever the shell has.

HELPERS. `chave`, `dentro`, `real` and `commit_do_checkout` are the copies that instagram, matchcut and video_to_skill each carry
(`_chave`, `_dentro`, `_real`, `_commit_do_checkout`), with the same bodies. montage has a `_dentro` of its own (it compares real
paths another way) and keeps it.
"""
from __future__ import annotations

import os
import sys
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path

# PATH, HOME, LANG and LC_ALL: the intersection of the lists of download, busca, status (and doctor_trilhas), matchcut, montage,
# video_to_skill and instagram (tests/test_terceiros.py freezes each of them).
NUCLEO_ENV: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL")

# macOS (APFS) and Windows compare folder names without regard to case (macOS also to Unicode normalization)
CASE_INSENSITIVE = sys.platform in ("darwin", "win32")


def env_para_terceiro(extra: Iterable[str] = (), *, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment of a third-party child: the names of NUCLEO_ENV and of `extra` that exist in `base` (the `os.environ` of the call
    by default: not the object it was at import), value as it is, and nothing else. A new dict; `base` is not touched."""
    if base is None:
        base = os.environ
    if isinstance(extra, str):  # a lone name, never its letters
        extra = (extra,)
    return {k: base[k] for k in (*NUCLEO_ENV, *extra) if k in base}


def chave(caminho: Path) -> tuple:
    if CASE_INSENSITIVE:
        return tuple(unicodedata.normalize("NFC", parte).casefold() for parte in caminho.parts)
    return tuple(caminho.parts)


def dentro(caminho: Path, pasta: Path) -> bool:
    a, b = chave(caminho), chave(pasta.resolve())
    return a[:len(b)] == b


def real(caminho: str) -> Path | None:
    try:
        return Path(caminho).resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def commit_do_checkout(d: Path) -> str:
    from . import tools  # at call time: the leaf does not drag the registry of tools in at import
    try:
        return tools.git("rev-parse", "HEAD", cwd=d)
    except tools.ToolError:
        return ""

"""What a third-party program receives, and the helpers the sandbox tracks share. A leaf: at import it needs only the standard library.

ENVIRONMENT. A child of a third-party track must not get a key, a token or any SIMPLICIO_* of the shell: each module passes a closed
list of names. `NUCLEO_ENV` is what every one of those lists has in common; `env_para_terceiro(extra)` is that core plus the names the
module asks for on top (its proxy and certificate variables, its own key, ...), read from the environment and only when they exist.
A name that is in neither is never passed, whatever the shell has. `PROXIES` is the one list of the eight proxy names: the modules that
let a proxy through write `(*terceiros.PROXIES, ...)` instead of typing them again.

HELPERS. `chave`, `dentro`, `real` and `commit_do_checkout` are the copies that instagram, matchcut and video_to_skill each carry
(`_chave`, `_dentro`, `_real`, `_commit_do_checkout`), with the same bodies. montage has a `_dentro` of its own (it compares real
paths another way) and keeps it.

TEXT. `limpa_mcp` (the text an agent gets) and `visivel` (the text a terminal gets) are what matchcut, instagram and video_to_skill each
carried (`_limpa_mcp`/`limpa_mcp`, `visivel`): the strictest of the three, instagram's, which also drops (or shows) the variation selectors.
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

# The names under which a shell hands its proxy to a program: HTTP, HTTPS and ALL, the NO_PROXY list of exceptions, each in upper and lower
# case. Eight lists of the tracks carried this set typed by hand (tests/test_terceiros.py freezes what each one passes).
PROXIES: tuple[str, ...] = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy")

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


# ---- the text of a third party, for an agent and for a terminal --------------------------------------------------------------------

# Unicode categories that can hide an instruction or move a terminal: control, format (bidirectional, zero-width, tag, BOM), surrogate, private
# use, unassigned, line and paragraph separators.
RUIM = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")


def seletor_de_variacao(c: str) -> bool:
    """Variation selectors (U+FE00-FE0F, U+E0100-E01EF) are category Mn but can carry hidden data after a visible character."""
    n = ord(c)
    return 0xFE00 <= n <= 0xFE0F or 0xE0100 <= n <= 0xE01EF


def limpa_mcp(texto: str) -> str:
    """Third-party text for an agent: no control, bidirectional, zero-width, line-separator, tag or variation-selector character (they can
    hide instructions); newline and tab stay."""
    texto = texto.replace("\r\n", "\n")
    return "".join(c for c in texto if c in "\n\t" or (not seletor_de_variacao(c) and unicodedata.category(c) not in RUIM))


def visivel(texto: str) -> str:
    """Third-party text for a terminal: ESC and the other controls become their visible marks (U+2400 block), and C1, bidirectional,
    zero-width, line-separator, BOM, tag and variation-selector characters become <U+XXXX>; newline and tab stay. A terminal never
    receives an escape sequence that came from a script (and so, possibly, from a third party's text)."""
    saida = []
    for c in texto.replace("\r\n", "\n"):
        n = ord(c)
        if c in "\n\t":
            saida.append(c)
        elif n < 0x20:
            saida.append(chr(0x2400 + n))
        elif n == 0x7F:
            saida.append(chr(0x2421))
        elif seletor_de_variacao(c) or unicodedata.category(c) in RUIM:
            saida.append(f"<U+{n:04X}>")
        else:
            saida.append(c)
    return "".join(saida)

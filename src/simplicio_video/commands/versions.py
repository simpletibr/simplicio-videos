"""The release parser and the state of the last `update --check`: what `doctor` needs, without the client of GitHub, pip and git.

Moved out of `update.py` (U13): `doctor` shows the cached answer of the last `update --check` offline, and used to import the whole
`update` module (a GitHub client, the pip and the checkout flows, `git`) just to read a version and a JSON file. `update` re-exports
every public name here, so `update.parse_version`, `update.read_check` and the others still exist and mean the same.

Nothing here touches the network, git or pip. The state file is `update-check.json` in $SIMPLICIO_VIDEO_DATA (default
~/.simplicio-video).
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

from .. import distribution, hostos

CHECK_FILE = "update-check.json"

# A release tag: `v` optional, 2 to 4 numbers, and the post-release suffix of PEP 440; nothing else. ASCII digits only (`\d` would
# also match full-width digits), and the whole text must match: `v0.5.0 --index-url=...` or `0.5.0 @ git+https://...` are not versions.
_VERSION = re.compile(r"v?(\d+(?:\.\d+){1,3})(?:\.post(\d+))?", re.ASCII)
# The INSTALLED version is our own `__version__`: it may be a development or pre-release one (PEP 440: dev < a < b < rc < final < post).
_INSTALLED = re.compile(r"\s*v?(\d+(?:\.\d+){0,3})(?:[-_.]?(dev|alpha|a|beta|b|preview|pre|rc|c)[-_.]?(\d*))?"
                        r"(?:[-_.]?post[-_.]?(\d*))?", re.ASCII | re.IGNORECASE)
_PHASES = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "c": 3, "rc": 3, "pre": 3, "preview": 3}
FINAL = 4  # the phase of a final release, above every pre-release


def parse_version(text: str) -> Tuple[int, ...]:
    """A release as a tuple of integers that compares like PEP 440: four release numbers, the phase, its number, the post number.

    STRICT on purpose. The tag comes from the network and ends up in pip's argv, so only a final release is read (`X.Y`,
    `X.Y.Z`, `X.Y.Z.W`, optional `v`, optional `.postN`) and the argv is rebuilt from the integers (`format_version`), never from
    the text. A pre-release, a local version, an epoch or any extra text raises ValueError: a pre-release is never a TARGET."""
    found = _VERSION.fullmatch(text.strip()) if isinstance(text, str) else None
    if not found:
        raise ValueError(f"não é uma versão de release (esperava algo como 1.2.3 ou v1.2.3): {str(text)[:60]!r}")
    release = [int(part) for part in found.group(1).split(".")]
    return (*release, *([0] * (4 - len(release))), FINAL, 0, int(found.group(2) or 0))


def format_version(parts: Tuple[int, ...]) -> str:
    """`(1, 2, 0, 0, 4, 0, 0)` -> `1.2.0`: three release numbers at least, the fourth only when it is not zero, then `.postN`.

    Only final releases are ever printed (a pre-release is a source of a comparison, never a target)."""
    release, post = list(parts[:4]), parts[6]
    while len(release) > 3 and release[-1] == 0:
        release.pop()
    return ".".join(str(part) for part in release) + (f".post{post}" if post else "")


def release_tuple(text: str) -> Tuple[int, ...]:
    """The INSTALLED version in the order of PEP 440, never an error: `0.5.0.dev1` < `0.5.0a1` < `0.5.0b1` < `0.5.0rc1` <
    `0.5.0` < `0.5.0.post1`, and a local label (`+local`) does not count. Text with no number at all reads as 0.0.0."""
    try:
        return parse_version(text)
    except ValueError:
        pass
    found = _INSTALLED.match(str(text))
    try:
        numbers = [int(n) for n in found.group(1).split(".")] if found else []
    except ValueError:
        numbers = []
    release = (*numbers, *([0] * (4 - len(numbers))))
    if not found:
        return (*release, FINAL, 0, 0)
    phase, number, post = found.group(2), found.group(3), found.group(4)
    if phase:
        return (*release, _PHASES[phase.lower()], int(number or 0), 0)
    return (*release, FINAL, 0, int(post or 0) if post is not None else 0)


# --- the last check, for `doctor` to show offline ---------------------------------------------------------------------


def default_state_dir() -> Path:
    """$SIMPLICIO_VIDEO_DATA, else ~/.simplicio-video (the same folder the other tracks use)."""
    explicit = os.environ.get("SIMPLICIO_VIDEO_DATA")
    return Path(explicit) if explicit else hostos.home_absoluta("SIMPLICIO_VIDEO_DATA") / ".simplicio-video"


class CheckInvalid(ValueError):
    """update-check.json is there but is not a usable answer: corrupt, hostile or written by something else."""


MAX_CHECK_BYTES = 64 * 1024  # the file is a few hundred bytes


def _clean_check(raw: object) -> dict:
    """Only the keys of the schema, each with its type; `latest` as a normalized release and `checked_at` as a real instant."""
    if not isinstance(raw, dict):
        raise CheckInvalid("não é um objeto JSON")
    stamp = raw.get("checked_at")
    if isinstance(stamp, bool) or not isinstance(stamp, int) or not 0 <= stamp <= hostos.MAX_TIMESTAMP:
        raise CheckInvalid("checked_at não é um instante válido")
    try:
        latest = format_version(parse_version(raw.get("latest")))
    except ValueError:
        raise CheckInvalid("latest não é uma versão de release") from None
    clean: dict = {"latest": latest, "checked_at": stamp}
    installed = raw.get("installed")
    if isinstance(installed, str) and 0 < len(installed) <= 64 and installed.isprintable():
        clean["installed"] = installed
    if isinstance(raw.get("update_available"), bool):
        clean["update_available"] = raw["update_available"]
    kind = raw.get("kind")
    if kind in (distribution.SOURCE, distribution.PIP):
        clean["kind"] = kind
    behind = raw.get("commits_behind")
    if kind == distribution.SOURCE and isinstance(behind, int) and not isinstance(behind, bool) and 0 <= behind <= 10**9:
        clean["commits_behind"] = behind
    return clean


def read_check(state_dir: Optional[Path] = None) -> Optional[dict]:
    """The answer of the last `update --check` (only the keys of the schema, validated), or None when there is none.

    Raises CheckInvalid when the file is there and is not usable: the `doctor` shows that as a warning, never as a traceback."""
    try:
        path = (state_dir or default_state_dir()) / CHECK_FILE
    except hostos.SemCasa:  # no home, no cache to read
        return None
    try:
        raw = hostos.read_regular(path, MAX_CHECK_BYTES)  # O_NONBLOCK and fstat: a FIFO there must not hang the doctor
    except (FileNotFoundError, NotADirectoryError):
        return None
    except hostos.NotARegularFile:
        raise CheckInvalid("não é um arquivo comum (pasta, fifo, dispositivo...)") from None
    except OSError as exc:
        raise CheckInvalid(f"não consegui ler: {exc.strerror or exc}") from None
    if len(raw) > MAX_CHECK_BYTES:
        raise CheckInvalid("grande demais")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise CheckInvalid("não é JSON") from None
    return _clean_check(data)


def write_check(info: dict, state_dir: Optional[Path] = None) -> None:
    """Best effort and atomic: a temp file in the same folder, then os.replace. A cache that cannot be written never fails an
    update, never leaves a half-written file where the doctor reads, and never leaves its temp file behind."""
    try:
        directory = state_dir or default_state_dir()
    except hostos.SemCasa:  # no home: the cache is not written (never a `~` folder in the cwd)
        return
    tmp = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=CHECK_FILE + ".", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({**info, "checked_at": int(time.time())}, handle, sort_keys=True)
        os.replace(tmp, directory / CHECK_FILE)
    except (OSError, TypeError, ValueError):
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)

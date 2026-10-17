"""Host facts for install, update, doctor and login: which system this is, where tools live and how to find them.

Everything here reads `sys.platform` and the environment at CALL time, never at import time, so the tests can simulate
Linux, macOS and Windows (tests/packaging/_caixa.py: `simula_so`). It never reads `os.name` for decisions: pathlib picks
its flavour from `os.name`, and a fake `nt` on Linux breaks every Path().

Finding a program is done here and not with `shutil.which`, for three reasons: on Windows `shutil.which` looks in the
current directory first (a planted `simplicio.exe` would be run by `simplicio-video login`), an injected environment
without PATH would silently fall back to the real PATH of the process, and PATHEXT must come from the environment that
was passed in, not from the process's own.

Standard library only: `install` runs under the SYSTEM python, before the `.venv` (and PyYAML) exists.

Looking at a file never raises: `Path.is_file()` and `Path.exists()` raise PermissionError on Python 3.12 and 3.13 when
a folder cannot be searched (a PATH folder with mode 0000, a `~/.simplicio` of another user after `sudo`), where
`shutil.which` swallowed it. `is_file`, `is_dir` and `exists` here are `os.path` calls, which say False instead.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePath
from typing import Any, Mapping, Optional

# macOS GUI and ssh sessions often lack the Homebrew prefixes on PATH (Apple Silicon, then Intel).
EXTRA_TOOL_DIRS = {"darwin": ["/opt/homebrew/bin", "/usr/local/bin"]}
DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"


def system() -> str:
    """`linux`, `darwin` or `win32` (every other POSIX system, Cygwin included, counts as `linux`)."""
    if sys.platform == "win32":
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def is_windows() -> bool:
    return system() == "win32"


def is_macos() -> bool:
    return system() == "darwin"


def home_dir(environ: Optional[Mapping[str, str]] = None) -> Path:
    """The user's home: HOME, then USERPROFILE, then Path.home(), on EVERY system.

    This is the order the Runtime reads it (runtime_auth.rs `auth_file`) and the loop too (auth.py `_home`). The login file is
    shared with the Runtime: with USERPROFILE first on Windows this program would read, and delete, another file than the one
    the Runtime writes (MSYS2, Cygwin, a HOME set by hand). A blank value is skipped, as in the loop."""
    if environ is not None:
        for name in ("HOME", "USERPROFILE"):
            value = (environ.get(name) or "").strip()
            if value:
                return Path(value)
    try:
        return Path.home()
    except (RuntimeError, KeyError):  # no HOME and no passwd entry: a path that finds nothing, not a traceback
        return Path("~")


def say(text: str) -> None:
    """print(), but a console that cannot encode a character (a cp1252 Windows console, an odd folder name) shows `?`."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding))


# 9999-12-31T23:59:59Z: the last instant a `datetime` can hold (and the cap of every date read from a file).
MAX_TIMESTAMP = 253402300799
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def utc_stamp(seconds: Any) -> str:
    """`2030-03-17T17:46:40Z`, or `data inválida` for anything that is no instant between 1970 and year 9999.

    Plain arithmetic on the epoch: `datetime.fromtimestamp` raises OSError past year 3000 on Windows, OverflowError and
    ValueError for a huge number, and a date shown to the user must never be the reason for a traceback."""
    try:
        if isinstance(seconds, bool) or not 0 <= seconds <= MAX_TIMESTAMP:  # a NaN fails the comparison too
            return "data inválida"
        return (_EPOCH + timedelta(seconds=int(seconds))).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError):
        return "data inválida"


def exe_name(base: str) -> str:
    return base + ".exe" if is_windows() else base


def venv_python(venv: PurePath, system_name: Optional[str] = None):
    """The interpreter inside a virtual environment: Scripts/python.exe on Windows, bin/python elsewhere."""
    if (system_name or system()) == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


# --- looking at files: never an exception ------------------------------------------------------------------------------------


def is_file(path: Any) -> bool:
    """True for a regular file. False for anything else, a folder that cannot be searched and a bad path included."""
    return os.path.isfile(path)


def is_dir(path: Any) -> bool:
    return os.path.isdir(path)


def exists(path: Any) -> bool:
    return os.path.exists(path)


# --- finding a program -----------------------------------------------------------------------------------------------


def _search_dirs(path: Optional[str]) -> list:
    """The absolute entries of a PATH string. An empty entry, `.` or a relative one would mean the current directory."""
    dirs = []
    for entry in (path or "").split(os.pathsep):
        entry = entry.strip().strip('"')
        if entry and entry != "." and os.path.isabs(entry):
            dirs.append(entry)
    return dirs


def _file_names(name: str, environ: Optional[Mapping[str, str]] = None) -> list:
    """The file names to try for `name`: itself on POSIX; with every PATHEXT extension of `environ` on Windows."""
    if not is_windows():
        return [name]
    environ = os.environ if environ is None else environ
    exts = [ext for ext in (environ.get("PATHEXT") or DEFAULT_PATHEXT).split(";") if ext]  # PATHEXT is always ;-separated
    if any(name.lower().endswith(ext.lower()) for ext in exts):
        return [name]
    return list(dict.fromkeys(item for ext in exts for item in (name + ext, name + ext.lower())))


def which(name: str, path: Optional[str] = None, environ: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    """The first executable file called `name` in the absolute entries of `path` (PATHEXT of `environ` on Windows), else None.

    A folder that cannot be searched is skipped, never an error."""
    for directory in _search_dirs(path):
        for file_name in _file_names(name, environ):
            candidate = Path(directory) / file_name
            if is_file(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def extra_tool_dirs(system_name: Optional[str] = None) -> list:
    return list(EXTRA_TOOL_DIRS.get(system_name or system(), []))


def find_tool(name: str, environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """`name` on PATH, then (macOS) in the Homebrew prefixes. The path as a string, or None."""
    env = os.environ if environ is None else environ
    found = which(name, env.get("PATH", ""), env)
    if found is None:
        found = which(name, os.pathsep.join(extra_tool_dirs()), env)
    return str(found) if found else None


def uv_candidates(home: PurePath, environ: Optional[Mapping[str, str]] = None, system_name: Optional[str] = None) -> list:
    """Where uv usually lives when it is not on PATH: ~/.local/bin and ~/.cargo/bin, plus Homebrew on macOS."""
    name = system_name or system()
    exe = "uv.exe" if name == "win32" else "uv"
    found = [home / ".local" / "bin" / exe, home / ".cargo" / "bin" / exe]
    if name == "darwin":
        found += [type(home)(directory) / exe for directory in EXTRA_TOOL_DIRS["darwin"]]
    return found


def find_uv(environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    found = find_tool("uv", environ)
    if found:
        return found
    for candidate in uv_candidates(home_dir(environ), environ):
        path = Path(candidate)
        if is_file(path) and os.access(path, os.X_OK):
            return str(path)
    return None


_HINTS = {
    ("uv", "linux"): "curl -LsSf https://astral.sh/uv/install.sh | sh",
    ("uv", "darwin"): "brew install uv (ou: curl -LsSf https://astral.sh/uv/install.sh | sh)",
    ("uv", "win32"): 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
    ("ffmpeg", "linux"): "Debian/Ubuntu: apt install ffmpeg",
    ("ffmpeg", "darwin"): "brew install ffmpeg",
    ("ffmpeg", "win32"): "winget install Gyan.FFmpeg",
    ("node", "linux"): "nvm install 22",
    ("node", "darwin"): "nvm install 22",
    ("node", "win32"): "baixe o Node 22 ou superior em https://nodejs.org (ou use o nvm-windows)",
}


def hint(tool: str, system_name: Optional[str] = None) -> str:
    """How to install `tool` (uv, ffmpeg or node) on this system."""
    return _HINTS[(tool, system_name or system())]

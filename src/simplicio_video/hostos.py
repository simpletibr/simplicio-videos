"""Host facts for install, update, doctor and login: which system this is, where tools live and how to find them.

Everything here reads `sys.platform` and the environment at CALL time, never at import time, so the tests can simulate
Linux, macOS and Windows (tests/packaging/_caixa.py: `simula_so`). It never reads `os.name` for decisions: pathlib picks
its flavour from `os.name`, and a fake `nt` on Linux breaks every Path().

Finding a program is done here and not with `shutil.which`, for two reasons: on Windows `shutil.which` looks in the
current directory first (a planted `simplicio.exe` would be run by `simplicio-video login`), and an injected environment
without PATH would silently fall back to the real PATH of the process.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path, PurePath
from typing import Mapping, Optional

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
    """The user's home: USERPROFILE first on Windows, HOME first elsewhere; Path.home() when the environment has none."""
    if environ is None:
        return Path.home()
    for name in (("USERPROFILE", "HOME") if is_windows() else ("HOME", "USERPROFILE")):
        value = (environ.get(name) or "").strip()
        if value:
            return Path(value)
    return Path.home()


def say(text: str) -> None:
    """print(), but a console that cannot encode a character (a cp1252 Windows console, an odd folder name) shows `?`."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding))


def exe_name(base: str) -> str:
    return base + ".exe" if is_windows() else base


def venv_python(venv: PurePath, system_name: Optional[str] = None):
    """The interpreter inside a virtual environment: Scripts/python.exe on Windows, bin/python elsewhere."""
    if (system_name or system()) == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


# --- finding a program -----------------------------------------------------------------------------------------------


def _search_dirs(path: Optional[str]) -> list:
    """The absolute entries of a PATH string. An empty entry, `.` or a relative one would mean the current directory."""
    dirs = []
    for entry in (path or "").split(os.pathsep):
        entry = entry.strip().strip('"')
        if entry and entry != "." and os.path.isabs(entry):
            dirs.append(entry)
    return dirs


def _file_names(name: str) -> list:
    """The file names to try for `name`: itself on POSIX; with every PATHEXT extension on Windows."""
    if not is_windows():
        return [name]
    exts = [ext for ext in (os.environ.get("PATHEXT") or DEFAULT_PATHEXT).split(";") if ext]  # PATHEXT is always ;-separated
    if any(name.lower().endswith(ext.lower()) for ext in exts):
        return [name]
    return list(dict.fromkeys(item for ext in exts for item in (name + ext, name + ext.lower())))


def which(name: str, path: Optional[str] = None) -> Optional[Path]:
    """The first executable file called `name` in the absolute entries of `path` (PATHEXT on Windows), else None."""
    for directory in _search_dirs(path):
        for file_name in _file_names(name):
            candidate = Path(directory) / file_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    return None


def extra_tool_dirs(system_name: Optional[str] = None) -> list:
    return list(EXTRA_TOOL_DIRS.get(system_name or system(), []))


def find_tool(name: str, environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """`name` on PATH, then (macOS) in the Homebrew prefixes. The path as a string, or None."""
    env = os.environ if environ is None else environ
    found = which(name, env.get("PATH", ""))
    if found is None:
        found = which(name, os.pathsep.join(extra_tool_dirs()))
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
        if path.is_file() and os.access(path, os.X_OK):
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

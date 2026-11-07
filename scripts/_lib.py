"""What the scripts of this folder repeated, byte for byte, in one place: the root of the checkout, the `git` call and `UsageError` of the
two gate checks (check_tdd, check_ownership) and the kill of a child's process group (smoke_trilhas, e2e_real).

Only scripts import this file, never `src/simplicio_video` (a test pins it), and it uses the standard library only: the scripts start
before the package is installed. A script that runs as a file finds it next to itself; the ones the tests load by path put their own folder
on `sys.path` first.

What is NOT here is what only looks alike. `Resultado`, `Passo`, `Saida`, `_executar` and `_resumo` of smoke_so, smoke_trilhas and
e2e_real share the name, not the fields or the body. `smoke_so.py` keeps its own `REPO`: its test pins that the script starts on a bare
Python with nothing but the standard library imported at the top, and `REPO` is the only line it would share.
"""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class UsageError(Exception):
    pass


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode:
        raise UsageError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def matar_grupo(proc: subprocess.Popen) -> None:
    """Kills the child and everything it started: on POSIX its whole process group (it was started in a new session)."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        pass  # the group already ended

"""Waiting for processes and for conditions."""

import os
import time
from pathlib import Path


def vivo(pid: int) -> bool:
    """Is the process alive (a zombie that nobody reaped counts as dead)?"""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def espera(condicao, segundos: float = 20.0) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(0.05)
    return bool(condicao())

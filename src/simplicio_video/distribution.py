"""How this simplicio-video was installed: as a source checkout (or an editable install) or as a package (pip).

`update` acts on it (a checkout is left to `git pull --ff-only`, a package is upgraded from PyPI), `install` refuses to
create a `.venv` inside site-packages and `doctor` shows it. There is no binary distribution here (the loop has one).
Ported from simplicio-loop simplicio_loop/distribution.py (2034e2d), reduced to the two kinds this engine ships.
"""
from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path
from typing import Optional

from . import hostos

PIP = "pip"
SOURCE = "source"
DIST_NAME = "simplicio-video"


def _installed() -> Optional[metadata.Distribution]:
    try:
        return metadata.distribution(DIST_NAME)
    except metadata.PackageNotFoundError:
        return None


def is_editable() -> bool:
    """Installed with `pip install -e` (pip records it in direct_url.json)."""
    dist = _installed()
    try:
        raw = dist.read_text("direct_url.json") if dist else None
        return bool(raw and json.loads(raw).get("dir_info", {}).get("editable"))
    except (ValueError, AttributeError, OSError):
        return False


def checkout_marker(root: Path) -> bool:
    """`root` is a checkout of this repository: a .git (a folder, or a file in a worktree) AND the plugin.json beside it."""
    return hostos.exists(Path(root) / ".git") and hostos.is_file(Path(root) / "plugin.json")  # never a PermissionError


def in_checkout() -> bool:
    """This code runs from a checkout: src/simplicio_video/distribution.py -> the repository root is two levels up."""
    return checkout_marker(Path(__file__).resolve().parents[2])


def kind(*, editable: Optional[bool] = None, checkout: Optional[bool] = None) -> str:
    """`source` or `pip`. An argument that is None is detected.

    A tree that pip never installed (PYTHONPATH=src, no metadata) counts as `source`: there is nothing to upgrade by pip."""
    if is_editable() if editable is None else editable:
        return SOURCE
    if in_checkout() if checkout is None else checkout:
        return SOURCE
    return PIP if _installed() is not None else SOURCE

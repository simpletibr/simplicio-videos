"""Which hosts ALREADY hold a copy of the skills, and whether that copy differs from the package.

Ported from simplicio-loop (`simplicio_loop/skill_sync.py`, 2034e2d) with one deliberate difference (review of PR #117, ADR-0020):
the loop REFRESHES those copies and deletes the files that left the package; this module only REPORTS them. A copy in
`~/.codex/skills` or `~/.cursor/skills` is not in the ownership receipt, so it is not ours to overwrite or to delete: the review
measured a `minhas-notas.md` of the user disappearing from two hosts, and `update` did it by itself through `install --global`.
`simplicio-video install --global` shows these copies as "left alone" and never changes them.

Only skill directories that are ALREADY installed are looked at, and a skill folder that is a symlink (the owner's link into a clone)
is never judged. This module writes nothing. Standard library only, like the installer it uses.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional, Union

from . import distribution, hostos, installer

SKILLS = installer.SKILLS

# host -> skills root under the home. One table, read by the report of `install --global`, the same relative path
# on Linux, macOS and Windows (pathlib joins it with the right separator). `claude` is also where every `--global` install lands.
# `simplicio_agent` keeps the folder the loop defines for that host (`~/.simplicio-loop/skills`): it is the host's, not ours.
HOST_SKILL_ROOTS = {
    "claude": ".claude/skills",
    "cursor": ".cursor/skills",
    "codex": ".codex/skills",
    "grok": ".grok/skills",
    "agents": ".agents/skills",
    "copilot": ".copilot/skills",
    "vscode": ".vscode/simplicio-skills",
    "opencode": ".config/opencode/skills",
    "amp": ".config/amp/skills",
    "kiro": ".kiro/steering",
    "simplicio_agent": ".simplicio-loop/skills",
}

PathLike = Union[str, os.PathLike]


def package_skills_dir():
    """The skills of the package as a Traversable (`data/skills`)."""
    return distribution.bundle_root().joinpath("skills")


def default_home() -> Path:
    """HOME, then USERPROFILE, then the system's idea of the home, on every system (a blank value is skipped)."""
    return hostos.home_dir(os.environ)


def skill_digest(skill_dir) -> str:
    """SHA256 over the relative paths and the bytes of every file under `skill_dir` ('' if it is not a folder)."""
    if isinstance(skill_dir, str):
        skill_dir = Path(skill_dir)
    if not (hostos.is_dir(skill_dir) if isinstance(skill_dir, Path) else skill_dir.is_dir()):
        return ""
    digest = hashlib.sha256()
    for parts, node in installer.iter_files(skill_dir):
        digest.update("/".join(parts).encode("utf-8") + b"\0")
        try:
            digest.update(installer.read_node(node))
        except OSError:  # a file that vanished or cannot be read: the digest then differs from the package's, which is the point
            digest.update(b"\0unreadable")
    return digest.hexdigest()


def installed_skill_hosts(home: Optional[PathLike] = None) -> dict:
    """host -> skills root, for hosts that already have `simplicio-video` installed."""
    base = Path(home) if home is not None else default_home()
    return {host: base / rel for host, rel in HOST_SKILL_ROOTS.items() if hostos.is_dir(base / rel / SKILLS[0])}


def stale_skills(home: Optional[PathLike] = None, *, source=None) -> list:
    """Installed skill dirs whose digest differs from the package copy (`source` = the skills folder; default: the package's).

    One entry per (host, skill): `{"host", "skill", "path", "reason"}`, reason `stale` (content differs) or `missing` (the host has the
    video skill but not this one). A skill folder that is a symlink is not ours to judge and is skipped."""
    source = package_skills_dir() if source is None else source
    out = []
    for host, root in sorted(installed_skill_hosts(home).items()):
        for skill in SKILLS:
            want = skill_digest(source.joinpath(skill))
            if not want or installer.is_link(root / skill):
                continue
            have = skill_digest(root / skill)
            if have != want:
                out.append({"host": host, "skill": skill, "path": str(root / skill), "reason": "missing" if not have else "stale"})
    return out

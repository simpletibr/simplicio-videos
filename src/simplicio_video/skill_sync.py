"""The folders where each host keeps its skills under the home, and the names of the skills.

Ported from simplicio-loop (`simplicio_loop/skill_sync.py`, 2034e2d). The loop keeps ONE table of host skill folders, the same relative
path on Linux, macOS and Windows (pathlib joins it with the right separator), and `install --global` puts the skills in every one of
them. The loop's `resync` refreshes the copies a host already has, overwriting them and deleting the files that left the package; the
video installs and updates them under the ownership rule of the review of PR #117 (ADR-0020), implemented in `installer.py`:

* a file that is missing is created, and enters the receipt with its sha256;
* a file is updated ONLY when it is in the receipt and still has the sha256 that was written (our copy, not edited);
* a file that was already there, or that the user edited, is `left_alone`; an extra file of the user is never deleted;
* the uninstall removes only what is ours.

This module is the registry only and imports nothing from the package: the installer (which runs under a system Python without PyYAML)
imports it, never the other way round.
"""
from __future__ import annotations

SKILLS = ("simplicio-video", "simplicio-video-social", "simplicio-video-media", "simplicio-video-voicestudio",
          "simplicio-video-shorts", "simplicio-video-edit")

# host -> skills root under the home. `claude` is where every install lands and what `--verify` is anchored to.
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

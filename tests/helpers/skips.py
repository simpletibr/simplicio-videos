"""Skips for tests that need a binary the machine may not have."""

import shutil

import pytest

# The module-level marker of the tests that need ffmpeg and ffprobe.
needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg ausente")


def ffmpeg_ou_pula(motivo: str) -> None:
    """Skip the running test with `motivo` unless both ffmpeg and ffprobe are on the PATH (each file says why it needs them)."""
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip(motivo)

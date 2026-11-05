"""Smoke-test regressions: global --json, media <sub> --help, edit transcribe -o and the video-use setup check."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import run_cli

ROOT = Path(__file__).resolve().parents[1]


def test_global_json_before_a_subcommand_never_leaves_a_traceback():
    # `--json busca status` used to fall through to the validate/render branch (AttributeError: 'contrato')
    r = run_cli("--json", "busca", "status")
    assert "Traceback" not in r.stderr and "AttributeError" not in r.stderr, r.stderr
    assert r.returncode == 0, r.stderr
    assert isinstance(json.loads(r.stdout), dict)


def test_global_json_before_a_subcommand_without_json_is_a_usage_error():
    r = run_cli("--json", "media", "probe", "x.mp4")
    assert r.returncode == 2
    assert "Traceback" not in r.stderr and "--json" in r.stderr


def test_global_json_before_an_argparse_subcommand_is_accepted():
    r = run_cli("--json", "tools")
    assert r.returncode == 0, r.stderr
    assert isinstance(json.loads(r.stdout), list)


@pytest.mark.parametrize("sub,flags", [
    ("burn", ["--crf", "--preset"]),
    ("mask", ["--box", "--from", "--to"]),
    ("voice-track", ["--duration", "--max-stretch"]),
    ("subs", ["--style", "--wrap"]),
    ("probe", ["info.json"]),
    ("sheet", ["--every", "--cols"]),
    ("audio", ["--rate"]),
    ("replace-audio", ["--keep-length"]),
    ("fetch", ["--autorizo", "--max-mb"]),
])
def test_media_subcommand_help_shows_its_own_flags_and_an_example(sub, flags):
    r = run_cli("media", sub, "--help")
    assert r.returncode == 0, r.stderr
    for f in flags:
        assert f in r.stdout, f"media {sub} --help missing {f!r}"
    assert f"simplicio-video media {sub}" in r.stdout and "exemplo" in r.stdout.lower()
    assert "voice-track" not in r.stdout or sub == "voice-track"  # not the generic page listing every subcommand


def test_edit_transcribe_without_output_is_a_clean_error():
    from simplicio_video import edit
    with pytest.raises(edit.EditError, match="-o"):
        edit.run_edit(["transcribe", "x.mp4"])


def test_video_use_setup_checks_soundfile(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg ausente")
    fake = tmp_path / "py"
    fake.write_text('#!/usr/bin/env bash\ncase "$*" in *soundfile*) exit 1;; esac\nexit 0\n')
    fake.chmod(0o755)
    setup = ROOT / "tools" / "video-use" / "setup.sh"
    r = subprocess.run(["bash", str(setup), "--quiet"], capture_output=True, text=True,
                       env={**os.environ, "SIMPLICIO_TTS_PY": str(fake), "VIDEO_USE_DIR": str(tmp_path / "vu")})
    assert r.returncode != 0 and "soundfile" in r.stderr

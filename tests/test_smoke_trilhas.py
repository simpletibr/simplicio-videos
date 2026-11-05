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


# --- review round: --json never becomes a value, repeated --json, edit transcribe output forms ---

@pytest.mark.parametrize("args", [
    ("instagram", "clone"),
    ("instagram",),
    ("instagram", "run", "hookscore", "--", "--hook", "x"),
    ("moneyprinter", "clone"),
    ("moneyprinter", "where"),
    ("media", "probe", "x.mp4"),
    ("edit", "pack", "d"),
])
def test_global_json_is_refused_where_the_subcommand_has_no_json(args, tmp_path):
    r = run_cli("--json", *args, cwd=tmp_path)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "Traceback" not in r.stderr and "--json" in r.stderr
    assert not (tmp_path / "--json").exists()  # no checkout named --json
    assert list(tmp_path.iterdir()) == []


def test_global_json_reaches_instagram_status_and_where():
    for sub in ("status", "where"):
        r = run_cli("--json", "instagram", sub)
        assert r.returncode == 0, r.stderr
        assert isinstance(json.loads(r.stdout), dict)


def test_global_json_never_becomes_the_value_of_a_missing_option():
    r = run_cli("--json", "moneyprinter", "generate", "--material")
    assert r.returncode in (1, 2)
    assert "--json" not in r.stderr.split("pede um valor")[0].split("--material")[-1]  # not consumed as the material path
    assert "Traceback" not in r.stderr


def test_repeated_global_json_is_collapsed():
    r = run_cli("--json", "--json", "busca", "status")
    assert r.returncode == 0, r.stderr
    assert isinstance(json.loads(r.stdout), dict)


@pytest.mark.parametrize("forma", [["-o", "w.json"], ["--out", "w.json"], ["--output", "w.json"], ["--output=w.json"], ["--out=w.json"], ["-ow.json"]])
def test_edit_transcribe_accepts_every_output_spelling(forma, monkeypatch):
    from simplicio_video import edit
    chamadas = []
    monkeypatch.setattr(edit, "helpers_dir", lambda: __import__("pathlib").Path("/h"))
    monkeypatch.setattr(edit, "_run", lambda cmd: chamadas.append(cmd) or 0)
    assert edit.run_edit(["transcribe", "x.mp4", *forma]) == 0
    assert chamadas


def test_edit_transcribe_help_reaches_the_help(capsys):
    from simplicio_video import edit
    assert edit.run_edit(["transcribe", "--help"]) == 0
    assert "transcribe" in capsys.readouterr().out

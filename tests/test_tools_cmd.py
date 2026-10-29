"""`simplicio-video tools`: the pinned external tracks, read from tools.py. Offline and hermetic."""
from __future__ import annotations

import json

import pytest

from simplicio_video import tools
from simplicio_video.cli import main

NAMES = {"openmontage", "opencut", "hypit", "toonflow", "moneyprinter", "tinyfish", "voicestudio", "video-use"}


def _run(argv, capsys):
    try:
        rc = main(argv)
    except SystemExit as e:  # argparse exits for --help
        rc = e.code
    out, err = capsys.readouterr()
    return rc, out, err


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """No real checkout, no binary on PATH: every track starts absent."""
    for t in tools.TOOLS.values():
        for var in (f"{t.name.upper()}_DIR", f"SIMPLICIO_{t.name.upper()}_DIR", f"SIMPLICIO_{t.name.upper()}_REF"):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    return tmp_path


def test_json_lists_every_pinned_track_with_the_registry_data(capsys):
    rc, out, err = _run(["tools", "--json"], capsys)
    assert rc == 0, err
    rows = json.loads(out)
    assert {r["name"] for r in rows} == NAMES
    for r in rows:
        assert {"name", "command", "repo", "version", "installed", "license", "produces"} <= set(r)
        assert isinstance(r["installed"], bool) and r["installed"] is False
        assert r["version"] == tools.pinned_ref(tools.get(r["name"]))
        assert r["produces"] and r["repo"] and r["license"]


def test_voicestudio_is_pinned_to_the_release_commit(capsys):
    rc, out, _ = _run(["tools", "--json"], capsys)
    voicestudio = next(r for r in json.loads(out) if r["name"] == "voicestudio")
    assert voicestudio["repo"] == "https://github.com/debpalash/VoiceStudio"
    assert voicestudio["command"] == "simplicio-video voicestudio"
    assert voicestudio["version"] == "beeaae08204f0de5f49d4a087ef2b0ea8fecfcb9"
    assert voicestudio["license"] == "AGPL-3.0"
    assert "v0.5.7" in tools.get("voicestudio").note
    assert "voicestudio.sh/install" in tools.get("voicestudio").note
    assert "bun install" in tools.get("voicestudio").note


def test_commands_match_the_cli_front_door(capsys):
    rc, out, _ = _run(["tools", "--json"], capsys)
    by = {r["name"]: r["command"] for r in json.loads(out)}
    assert by["openmontage"] == "simplicio-video montage"
    assert by["hypit"] == "simplicio-video clone"
    assert by["tinyfish"] == "simplicio-video busca"
    assert by["toonflow"] == "simplicio-video toonflow"


def test_text_output_names_every_track_and_its_state(capsys):
    rc, out, _ = _run(["tools"], capsys)
    assert rc == 0
    assert "trilhas externas" in out
    for name in NAMES:
        assert name in out
    assert "instalada: não" in out and "instalada: sim" not in out
    assert "versão fixada:" in out and "produz:" in out and "comando:" in out
    assert "render determinístico não depende" in out


def test_a_checkout_in_the_tools_cache_shows_as_installed(_isolated, capsys):
    checkout = _isolated / "tools" / "voicestudio"
    checkout.mkdir(parents=True)
    (checkout / "package.json").write_text("{}")
    rc, out, _ = _run(["tools", "--json"], capsys)
    rows = {r["name"]: r["installed"] for r in json.loads(out)}
    assert rows["voicestudio"] is True
    assert rows["moneyprinter"] is False


def test_ref_override_is_reflected_in_the_listing(monkeypatch, capsys):
    monkeypatch.setenv("SIMPLICIO_VOICESTUDIO_REF", "main")
    rc, out, _ = _run(["tools", "--json"], capsys)
    by = {r["name"]: r["version"] for r in json.loads(out)}
    assert by["voicestudio"] == "main"


def test_main_help_lists_the_new_commands(capsys):
    rc, out, _ = _run(["--help"], capsys)
    assert rc == 0
    assert "    tools" in out and "trilhas externas fixadas" in out
    assert "    voicestudio" in out and "VoiceStudio" in out


def test_help_is_complete(capsys):
    rc, out, err = _run(["tools", "--help"], capsys)
    assert rc == 0
    for word in ("trilhas externas", "tools.py", "SIMPLICIO_TOOLS_DIR", "render determinístico", "exemplos:"):
        assert word in out, word

def test_video_use_is_the_edit_command():
    assert tools.command(tools.TOOLS["video-use"]) == "simplicio-video edit"
    assert tools.TOOLS["video-use"].ref == "b877063"

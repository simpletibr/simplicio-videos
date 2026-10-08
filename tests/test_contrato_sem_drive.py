"""Issue #75: the engine has no `drive` block. Delivery (Drive, link, Real Oficial) belongs to the caller.

- a contract without `drive` validates and renders;
- a contract with `drive` is rejected by `validate` (exit 1, message points to the delivery outside the engine);
- the render manifest has no `drive` key;
- `publish` receives the destination by parameter and never reads `drive` from the contract.
"""
import json

import pytest
import yaml

from conftest import ROOT, LOTHUS, have_render_tools, run_cli
from simplicio_video import contract as ct
from simplicio_video import publish as pub
from simplicio_video import render, voice

DESTINO = {"caminho": "simplicio-video/clientes/Teste_Mini/2026/Teste_Hash", "arquivo": "Teste - mini - v01.mp4"}
DRIVE_BLOCK = {"caminho": "simplicio-video/clientes/Teste_Mini/2026/Teste_Hash", "arquivo": "Teste - mini - v01.mp4"}


def _edit(path, fn):
    d = yaml.safe_load(path.read_text())
    fn(d)
    path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))


def _mp4(mini):
    p = mini.parent / "out" / "mini.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"fake-mp4-bytes")
    return p


# (a) contract without drive validates

def test_schema_accepts_real_contract_without_drive():
    d = yaml.safe_load(LOTHUS.read_text())
    d.pop("drive")
    assert ct.schema_errors(d, ROOT) == []


def test_contract_without_drive_is_valid(mini):
    _edit(mini, lambda d: d.pop("drive"))
    assert ct.schema_errors(yaml.safe_load(mini.read_text()), ROOT) == []
    rep = ct.validate(ct.load(mini))
    assert rep.ok, rep.errors


@pytest.mark.render
@pytest.mark.skipif(not have_render_tools(), reason="needs node, npx and ffmpeg")
def test_contract_without_drive_renders_and_manifest_has_no_drive(mini):
    _edit(mini, lambda d: d.pop("drive"))
    voice.run(ct.load(mini), log=lambda *_: None)
    man = render.render_local(ct.load(mini), log=lambda *_: None)
    assert man["output"]["frames"] == 30
    assert "drive" not in man
    assert "drive" not in json.loads((mini.parent / "render.manifest.json").read_text())


# (b) contract with drive is rejected by validate

def test_contract_with_drive_is_rejected(mini):
    _edit(mini, lambda d: d.update(drive=dict(DRIVE_BLOCK)))
    rep = ct.validate(ct.load(mini))
    assert not rep.ok
    assert any("drive" in e for e in rep.errors), rep.errors


def test_cli_validate_rejects_drive_with_exit_code_1(mini):
    _edit(mini, lambda d: d.update(drive=dict(DRIVE_BLOCK)))
    r = run_cli("validate", mini)
    assert r.returncode != 0
    erros = [ln for ln in r.stdout.splitlines() if ln.startswith("ERRO")]
    assert any("drive" in ln and "entrega" in ln for ln in erros), r.stdout


# (c) manifest has no drive key (unit: write_manifest with the media probes faked, no ffmpeg needed)

def test_manifest_written_without_drive_key(mini, monkeypatch):
    _edit(mini, lambda d: d.pop("drive"))
    c = ct.load(mini)
    fake_media = {"frame_md5": [], "sha256": "0" * 64, "video_frames_sha256": "0" * 64, "audio_pcm_sha256": "0" * 64,
                  "frames": 30, "duration_s": 1.0}
    monkeypatch.setattr(render, "media_hashes", lambda p: dict(fake_media))
    monkeypatch.setattr(render, "loudness", lambda p: {"integrated_lufs": -14.0, "true_peak_dbtp": -1.5})
    dst = _mp4(mini)
    man = render.write_manifest(c, dst, backend="local", quality="draft", gpu=False,
                                info={"inputs_sha256": "0" * 64, "files": []}, timings={}, tools={"ffmpeg": "fake"},
                                log=lambda *_: None)
    assert "drive" not in man
    assert "drive" not in json.loads((mini.parent / "render.manifest.json").read_text())


# (d) publish takes the destination by parameter and does not read drive from the contract

class _NoDriveRead(dict):
    """Contract data that fails the test if anything reads its `drive` block."""

    def __getitem__(self, k):
        if k == "drive":
            raise AssertionError("publish leu o bloco drive do contrato")
        return super().__getitem__(k)

    def get(self, k, default=None):
        if k == "drive":
            raise AssertionError("publish leu o bloco drive do contrato")
        return super().get(k, default)


def test_publish_accepts_destino_parameter_without_drive_in_contract(mini):
    _edit(mini, lambda d: d.pop("drive"))
    _mp4(mini)
    res = pub.publish(ct.load(mini), remote="gdrive", dry_run=True, destino=DESTINO, log=lambda *_: None)
    assert res["dest"] == "gdrive:simplicio-video/clientes/Teste_Mini/2026/Teste_Hash/Teste - mini - v01.mp4"


def test_publish_uses_destino_and_never_reads_contract_drive(mini):
    _mp4(mini)
    c = ct.load(mini)  # fixture still carries a stale drive block; publish must ignore it
    c.data = _NoDriveRead(c.data)
    res = pub.publish(c, remote="gdrive", dry_run=True, destino=DESTINO, log=lambda *_: None)
    assert res["dest"] == "gdrive:simplicio-video/clientes/Teste_Mini/2026/Teste_Hash/Teste - mini - v01.mp4"


def test_publish_without_destino_refuses_instead_of_reading_drive(mini):
    _edit(mini, lambda d: d.pop("drive"))
    _mp4(mini)
    with pytest.raises(SystemExit, match="destino"):
        pub.publish(ct.load(mini), dry_run=True, log=lambda *_: None)

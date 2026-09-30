"""Short real renders (1 s, 180x320): same contract + assets => same hashes, locally and in the Colab bundle."""
import json
import shutil
import zipfile

import pytest

from conftest import have_render_tools
from simplicio_video import contract as ct
from simplicio_video import render, voice

pytestmark = [pytest.mark.render, pytest.mark.skipif(not have_render_tools(), reason="needs node, npx and ffmpeg")]


def _render(contract_path):
    c = ct.load(contract_path)
    voice.run(c, log=lambda *_: None)
    return render.render_local(ct.load(contract_path), log=lambda *_: None)


def test_same_input_same_output(mini, tmp_path):
    other = tmp_path / "copy"
    shutil.copytree(mini.parent, other)
    a, b = _render(mini), _render(other / "contract.yaml")
    assert a["contract_sha256"] == b["contract_sha256"]
    assert a["inputs_sha256"] == b["inputs_sha256"]
    for k in ("video_frames_sha256", "audio_pcm_sha256", "sha256", "frames", "duration_s"):
        assert a["output"][k] == b["output"][k], k
    assert a["output"]["frames"] == 30
    man = json.loads((mini.parent / "render.manifest.json").read_text())
    assert man["drive"]["caminho"].startswith("simplicio-video/clientes/")


def test_contract_change_changes_hash(mini):
    a = _render(mini)
    txt = mini.read_text().replace('cta: "Fim"', 'cta: "Outro"')
    mini.write_text(txt)
    b = _render(mini)
    assert a["contract_sha256"] != b["contract_sha256"] and a["inputs_sha256"] != b["inputs_sha256"]


def test_colab_bundle_is_reproducible(mini):
    c = ct.load(mini)
    voice.run(c, log=lambda *_: None)
    x = render.render_colab(ct.load(mini), log=lambda *_: None)
    y = render.render_colab(ct.load(mini), log=lambda *_: None)
    assert x["bundle_sha256"] == y["bundle_sha256"]
    names = zipfile.ZipFile(x["bundle"]).namelist()
    for n in ("index.html", "render_bundle.sh", "bundle.json", "scripts/master.sh", "build/variables.json", "assets/audio/build/mix.wav"):
        assert n in names

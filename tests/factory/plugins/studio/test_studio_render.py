"""Render real (#16): o mini fixture renderizado duas vezes dá o mesmo hash. Precisa de node, npx e ffmpeg."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import have_render_tools
from tests.factory.plugins.studio._studio import renderer_module

ROOT = Path(__file__).resolve().parents[4]
MINI = ROOT / "tests" / "fixtures" / "mini"

pytestmark = [
    pytest.mark.render,
    pytest.mark.skipif(not have_render_tools(), reason="precisa de node >= 22, npx e ffmpeg no PATH para o render real"),
]


def _copy_mini(dst: Path) -> Path:
    shutil.copytree(MINI, dst, ignore=shutil.ignore_patterns("out", "build", "timing.lock.json", "render.manifest.json", "voz"))
    return dst / "contract.yaml"


def test_render_do_mini_tem_hash_estavel(tmp_path):
    from simplicio_factory.contracts import Draft
    from tests.factory.plugins.studio._studio import hashing_module

    draft = Draft(item_id="itm_01HZMINI0000000000000001", idea="tom de teste", facts={}, claims=[], platform="9:16", duration_s=1)
    results = []
    for name in ("a", "b"):
        contract = _copy_mini(tmp_path / name)
        result = renderer_module().EngineRenderer(tmp_path / f"renders-{name}").render(str(contract), preview=False)
        assert Path(result.mp4_path).is_file()
        assert Path(result.mp4_path).stat().st_size > 0
        results.append((result.content_hash, hashing_module().content_hash(contract, draft)))

    assert results[0] == results[1]

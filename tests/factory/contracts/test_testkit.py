"""testkit do kernel (#33): StubRenderer (bytes determinísticos, sem HyperFrames) e ForbiddenLLM (falha se chamado)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.factory._fixtures import kit_module

CONTRACT = "schema: simplicio.video-contract/v1\nduration_s: 5\nscenes: []\n"
OTHER_CONTRACT = "schema: simplicio.video-contract/v1\nduration_s: 9\nscenes: []\n"


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_stub_renderer_same_input_same_file_and_hash(tmp_path):
    contract = _write(tmp_path / "contract.yaml", CONTRACT)
    renderer = kit_module().StubRenderer(tmp_path / "out")

    first = renderer.render(contract, preview=False)
    second = renderer.render(contract, preview=False)

    assert Path(first.mp4_path) == Path(second.mp4_path)
    first_bytes = Path(first.mp4_path).read_bytes()
    assert first_bytes
    assert Path(second.mp4_path).read_bytes() == first_bytes
    assert first.content_hash == second.content_hash


def test_stub_renderer_is_deterministic_across_instances(tmp_path):
    contract = _write(tmp_path / "contract.yaml", CONTRACT)

    a = kit_module().StubRenderer(tmp_path / "a").render(contract, preview=False)
    b = kit_module().StubRenderer(tmp_path / "b").render(contract, preview=False)

    assert Path(a.mp4_path).read_bytes() == Path(b.mp4_path).read_bytes()
    assert a.content_hash == b.content_hash


def test_stub_renderer_output_depends_on_input(tmp_path):
    """Um stub que grava bytes constantes passaria no teste de determinismo; este teste impede isso."""
    renderer = kit_module().StubRenderer(tmp_path / "out")
    first = renderer.render(_write(tmp_path / "a.yaml", CONTRACT), preview=False)
    first_bytes = Path(first.mp4_path).read_bytes()

    second = renderer.render(_write(tmp_path / "b.yaml", OTHER_CONTRACT), preview=False)

    assert Path(second.mp4_path).read_bytes() != first_bytes
    assert second.content_hash != first.content_hash


def test_forbidden_llm_fails_when_called():
    llm = kit_module().ForbiddenLLM()

    with pytest.raises(AssertionError):
        llm.complete({"prompt": "qualquer coisa"})

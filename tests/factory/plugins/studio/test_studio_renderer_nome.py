"""Regressão (#16): o MP4 de cada item tem nome próprio, na prévia e na entrega.

Antes, o nome vinha de `Path(contract_path).parent.name`. A prévia fica sempre em `<item>/preview/`, então todas as
prévias gravavam `preview-previa.mp4` e uma sobrescrevia a outra. O motor é trocado por um fake: o teste não precisa de ffmpeg.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.factory.plugins.studio._studio import renderer_module


@pytest.fixture
def motor(monkeypatch):
    from simplicio_video import contract as motor_contract
    from simplicio_video import render as motor_render

    def fake_render(contrato, out, log=None):
        Path(out).write_bytes(b"mp4 falso")

    monkeypatch.setattr(motor_contract, "load", lambda caminho: SimpleNamespace(data={"voz": {"habilitada": False}}))
    monkeypatch.setattr(motor_render, "render_preview", fake_render)
    monkeypatch.setattr(motor_render, "render_local", fake_render)


def _contrato(raiz: Path, item_id: str, preview: bool) -> str:
    pasta = raiz / item_id / ("preview" if preview else "")
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / "contract.yaml"
    caminho.write_text("schema: simplicio.video-contract/v1\n", encoding="utf-8")
    return str(caminho)


def test_previas_de_itens_diferentes_gravam_em_arquivos_diferentes(tmp_path, motor):
    renderer = renderer_module().EngineRenderer(tmp_path / "renders")

    previa_a = renderer.render(_contrato(tmp_path / "studio", "itm_A", preview=True), preview=True).mp4_path
    previa_b = renderer.render(_contrato(tmp_path / "studio", "itm_B", preview=True), preview=True).mp4_path

    assert previa_a != previa_b
    assert "itm_A" in Path(previa_a).name
    assert "itm_B" in Path(previa_b).name


def test_entrega_usa_o_id_do_item_como_nome(tmp_path, motor):
    renderer = renderer_module().EngineRenderer(tmp_path / "renders")

    entrega = renderer.render(_contrato(tmp_path / "studio", "itm_A", preview=False), preview=False).mp4_path

    assert Path(entrega).name == "itm_A.mp4"

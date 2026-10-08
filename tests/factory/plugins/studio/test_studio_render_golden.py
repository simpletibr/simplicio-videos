"""Render real do golden do brand-promo (#16): o contrato gerado pelo composer renderiza de verdade (15 s, mp4) e o
texto das provas (prova_1, prova_2) e do CTA chega à composição. Precisa de node >= 22, npx e ffmpeg no PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import have_render_tools
from tests.factory.plugins.studio._studio import FIXTURES, GOLDEN, renderer_module

PROVA_1 = "Atendimento com hora marcada."
PROVA_2 = "Garantia de 1 ano no tratamento."
CTA = "Agende sua visita."

pytestmark = [
    pytest.mark.render,
    pytest.mark.skipif(not have_render_tools(), reason="precisa de node >= 22, npx e ffmpeg no PATH para o render real"),
]


def _duracao_s(mp4: Path) -> float:
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(mp4)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(saida.strip())


def test_golden_renderiza_15s_com_textos_das_provas_e_do_cta(tmp_path):
    contract_dir = tmp_path / "golden"
    (contract_dir / "assets").mkdir(parents=True)
    shutil.copy(GOLDEN, contract_dir / "contract.yaml")
    shutil.copy(FIXTURES / "logo.svg", contract_dir / "assets" / "logo.svg")

    result = renderer_module().EngineRenderer(tmp_path / "renders").render(str(contract_dir / "contract.yaml"), preview=False)

    mp4 = Path(result.mp4_path)
    assert mp4.is_file() and mp4.stat().st_size > 0
    assert abs(_duracao_s(mp4) - 15.0) < 0.2

    variaveis = json.loads((contract_dir / "build" / "simplicio-video" / "build" / "variables.json").read_text(encoding="utf-8"))
    assert variaveis["prova_1"] == PROVA_1
    assert variaveis["prova_2"] == PROVA_2
    assert variaveis["cta"] == CTA

    composicao = (contract_dir / "build" / "simplicio-video" / "index.html").read_text(encoding="utf-8")
    assert PROVA_1 in composicao
    assert PROVA_2 in composicao
    assert CTA in composicao

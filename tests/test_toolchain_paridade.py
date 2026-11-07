"""Parity of the toolchain pins that are copied by hand (U19): nothing moves, the copies are only compared.

Four places carry the HyperFrames pin, and the remote renderer and the Colab notebook also carry the Node,
@puppeteer/browsers and Chrome pins:

* ``simplicio_video.HYPERFRAMES``                      (the pin the CLI uses)
* ``engine/remote_render.py``  HF NODE PB CHROME_FALLBACK  (headless script of the remote backends)
* ``colab/render.ipynb``       HF NODE PB CHROME_FALLBACK  (manual notebook, cell 2)
* ``data/motion/scripts/preview.sh``  HF                   (motion preview)

``remote_render.py`` and the notebook are read by AST/JSON, never imported or run: they live outside the
package contract (the first one is a script for a remote box, the second one is a notebook).
"""
import ast
import json
import re
from pathlib import Path

import pytest

import simplicio_video

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "simplicio_video"
REMOTE_RENDER = PKG / "engine" / "remote_render.py"
NOTEBOOK = ROOT / "colab" / "render.ipynb"
PREVIEW_SH = PKG / "data" / "motion" / "scripts" / "preview.sh"

PINS = ("NODE", "HF", "PB", "CHROME_FALLBACK")


def _literals(source: str, names: tuple[str, ...]) -> dict[str, str]:
    """Top-level ``NAME = "literal"`` assignments of a Python source, by AST (nothing is executed)."""
    found: dict[str, str] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name in names and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            found[name] = node.value.value
    return found


def _remote_render_pins() -> dict[str, str]:
    return _literals(REMOTE_RENDER.read_text(encoding="utf8"), PINS)


def _notebook_pins() -> dict[str, str]:
    cells = json.loads(NOTEBOOK.read_text(encoding="utf8"))["cells"]
    found: dict[str, str] = {}
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        found.update(_literals("".join(cell.get("source", [])), PINS))
    return found


def _preview_sh_hf() -> str:
    m = re.search(r'^HF="npx --yes (hyperframes@[^"\s]+)"$', PREVIEW_SH.read_text(encoding="utf8"), re.M)
    assert m, f"{PREVIEW_SH}: sem a linha HF=\"npx --yes hyperframes@<versão>\""
    return m.group(1)


def test_cada_fonte_traz_os_quatro_pins():
    assert set(_remote_render_pins()) == set(PINS), "engine/remote_render.py perdeu uma das constantes NODE, HF, PB, CHROME_FALLBACK"
    assert set(_notebook_pins()) == set(PINS), "colab/render.ipynb perdeu uma das constantes NODE, HF, PB, CHROME_FALLBACK"
    assert re.fullmatch(r"hyperframes@\d+\.\d+\.\d+", _preview_sh_hf())
    assert re.fullmatch(r"hyperframes@\d+\.\d+\.\d+", simplicio_video.HYPERFRAMES)


def test_hyperframes_do_cli_e_igual_ao_do_render_remoto():
    assert _remote_render_pins()["HF"] == simplicio_video.HYPERFRAMES


def test_hyperframes_do_cli_e_igual_ao_do_notebook():
    assert _notebook_pins()["HF"] == simplicio_video.HYPERFRAMES


def test_hyperframes_do_cli_e_igual_ao_do_preview_do_motion():
    assert _preview_sh_hf() == simplicio_video.HYPERFRAMES


@pytest.mark.parametrize("nome", ["NODE", "PB", "CHROME_FALLBACK"])
def test_notebook_e_render_remoto_usam_o_mesmo_node_puppeteer_e_chrome(nome):
    assert _notebook_pins()[nome] == _remote_render_pins()[nome]

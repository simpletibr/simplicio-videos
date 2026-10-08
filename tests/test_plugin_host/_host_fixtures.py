"""Fixtures do host de plugins (#32). Os manifestos de teste ficam em tmp_path; nada é lido do repo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from simplicio_video import registry

HANDLER_MODULE = "pluginfake_hosttest"
RETORNO_HANDLER = 7  # código de saída que o handler de teste devolve (não-trivial, para provar que o retorno passa)


def _manifesto(**campos) -> dict:
    base = {
        "id": "fake",
        "kind": "stage",
        "version": "0.1.0",
        "commands": [{"name": "fakecmd", "handler": f"{HANDLER_MODULE}:run",
                      "help": "comando de teste do host", "example": "simplicio-video fakecmd ARG"}],
        "stages": [],
    }
    base.update(campos)
    return base


@pytest.fixture
def manifesto():
    """Fábrica de manifesto válido: manifesto(id="x", commands=[...])."""
    return _manifesto


@pytest.fixture
def escreve_manifesto():
    """Grava <dir>/plugin.json e devolve o caminho."""
    def escreve(dir_: Path, dados: dict) -> Path:
        dir_.mkdir(parents=True, exist_ok=True)
        path = dir_ / "plugin.json"
        path.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return path
    return escreve


@pytest.fixture
def handler_fake(tmp_path, monkeypatch):
    """Módulo de handler de teste, importável pelo nome HANDLER_MODULE. Grava as chamadas em CHAMADAS."""
    pasta = tmp_path / "fakes"
    pasta.mkdir()
    (pasta / f"{HANDLER_MODULE}.py").write_text(
        "CHAMADAS = []\n\n\n"
        "def run(argv):\n"
        "    CHAMADAS.append(list(argv))\n"
        f"    return {RETORNO_HANDLER}\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(pasta))
    sys.modules.pop(HANDLER_MODULE, None)
    yield RETORNO_HANDLER
    sys.modules.pop(HANDLER_MODULE, None)


@pytest.fixture
def plugin_root(tmp_path, monkeypatch, escreve_manifesto, manifesto, handler_fake):
    """Aponta o registro para tmp_path/plugins, com um plugin de teste (id fake, comando fakecmd)."""
    raiz = tmp_path / "plugins"
    escreve_manifesto(raiz / "fake", manifesto())
    monkeypatch.setattr(registry, "PLUGINS_DIR", raiz)
    return raiz

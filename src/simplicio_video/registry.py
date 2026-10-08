"""Registro de plugins do simplicio-video (#32, M0a).

Manifesto por plugin: src/simplicio_factory/plugins/<id>/plugin.json (schemas/plugin.manifest.schema.json).

STUB da fase 1 (testes vermelhos): só o contrato de import. A implementação é da fase 2 do #32.
"""
from __future__ import annotations

from pathlib import Path

# Diretório de plugins de primeira parte. A CLI lê este atributo no momento da chamada (testes o trocam).
PLUGINS_DIR = Path(__file__).resolve().parents[1] / "simplicio_factory" / "plugins"


class ManifestError(ValueError):
    """Manifesto de plugin inválido: campo obrigatório ausente, handler sem ':' ou nome de comando duplicado."""


def load_manifest(path: Path):
    raise NotImplementedError("registry.load_manifest: implementação da fase 2 do #32")


def discover(root: Path):
    raise NotImplementedError("registry.discover: implementação da fase 2 do #32")


def commands_index(manifests):
    raise NotImplementedError("registry.commands_index: implementação da fase 2 do #32")

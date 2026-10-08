"""Registro de plugins do simplicio-video (#32, M0a).

Manifesto por plugin: src/simplicio_factory/plugins/<id>/plugin.json (schemas/plugin.manifest.schema.json).
A descoberta varre as pastas <raiz>/*/plugin.json; não há lista fixa de plugins em código.
"""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Diretório de plugins de primeira parte. A CLI lê este atributo no momento da chamada (testes o trocam).
PLUGINS_DIR = Path(__file__).resolve().parents[1] / "simplicio_factory" / "plugins"

MANIFEST_NAME = "plugin.json"

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+")
_HANDLER_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")


class ManifestError(ValueError):
    """Manifesto de plugin inválido: campo obrigatório ausente, handler sem ':' ou nome de comando duplicado."""


@dataclass(frozen=True)
class Command:
    name: str
    handler: str  # formato "modulo:funcao"
    help: str
    example: str


@dataclass(frozen=True)
class Manifest:
    id: str
    kind: str
    version: str
    commands: tuple[Command, ...]
    stages: tuple[str, ...] = field(default=())
    path: Path | None = None


def _erro(path: Path | None, msg: str) -> ManifestError:
    onde = f"{path}: " if path is not None else ""
    return ManifestError(f"{onde}{msg}")


def _texto(dados: dict, campo: str, path: Path | None, *, obrigatorio: bool = True) -> str:
    valor = dados.get(campo)
    if valor is None:
        if obrigatorio:
            raise _erro(path, f"campo obrigatório ausente: {campo}")
        return ""
    if not isinstance(valor, str) or not valor.strip():
        raise _erro(path, f"campo {campo} deve ser um texto não vazio")
    return valor


def _comando(item, path: Path | None) -> Command:
    if not isinstance(item, dict):
        raise _erro(path, "cada item de commands deve ser um objeto {name, handler, help, example}")
    nome = _texto(item, "name", path)
    if not _NAME_RE.match(nome):
        raise _erro(path, f"nome de comando inválido: {nome!r} (use minúsculas, dígitos e hífen)")
    handler = _texto(item, "handler", path)
    if ":" not in handler:
        raise _erro(path, f"handler de {nome!r} deve ter o formato modulo:funcao (recebeu {handler!r})")
    if not _HANDLER_RE.match(handler):
        raise _erro(path, f"handler de {nome!r} inválido: {handler!r} (formato modulo:funcao)")
    return Command(name=nome, handler=handler,
                   help=_texto(item, "help", path), example=_texto(item, "example", path))


def load_manifest(path: Path) -> Manifest:
    """Lê e valida um plugin.json. Levanta ManifestError com o caminho e o campo com problema."""
    path = Path(path)
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _erro(path, f"não foi possível ler o manifesto: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise _erro(path, f"JSON inválido: {exc}") from exc
    if not isinstance(dados, dict):
        raise _erro(path, "o manifesto deve ser um objeto JSON")

    plugin_id = _texto(dados, "id", path)
    if not _ID_RE.match(plugin_id):
        raise _erro(path, f"id inválido: {plugin_id!r} (use minúsculas, dígitos, _ e -)")
    kind = _texto(dados, "kind", path)
    version = _texto(dados, "version", path)
    if not _VERSION_RE.match(version):
        raise _erro(path, f"version deve estar no formato X.Y.Z (recebeu {version!r})")

    brutos = dados.get("commands")
    if brutos is None:
        raise _erro(path, "campo obrigatório ausente: commands")
    if not isinstance(brutos, list):
        raise _erro(path, "commands deve ser uma lista")
    comandos = tuple(_comando(item, path) for item in brutos)
    vistos: set[str] = set()
    for c in comandos:
        if c.name in vistos:
            raise _erro(path, f"comando duplicado no mesmo plugin: {c.name!r}")
        vistos.add(c.name)

    stages = dados.get("stages", [])
    if not isinstance(stages, list) or not all(isinstance(s, str) and s.strip() for s in stages):
        raise _erro(path, "stages deve ser uma lista de textos não vazios")

    return Manifest(id=plugin_id, kind=kind, version=version, commands=comandos,
                    stages=tuple(stages), path=path)


def discover(root: Path) -> list[Manifest]:
    """Varre root/*/plugin.json e devolve os manifestos ordenados por id. Pastas sem manifesto são ignoradas.

    O id do manifesto tem de ser igual ao nome da pasta, para que o caminho e o id não divirjam.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    achados: list[Manifest] = []
    for pasta in sorted(p for p in root.iterdir() if p.is_dir()):
        path = pasta / MANIFEST_NAME
        if not path.is_file():
            continue
        m = load_manifest(path)
        if m.id != pasta.name:
            raise _erro(path, f"id {m.id!r} difere do nome da pasta {pasta.name!r}")
        achados.append(m)
    return sorted(achados, key=lambda m: m.id)


def commands_index(manifests) -> dict[str, tuple[Manifest, Command]]:
    """Índice nome do comando -> (manifesto, comando). Nome repetido entre plugins é erro."""
    indice: dict[str, tuple[Manifest, Command]] = {}
    for m in manifests:
        for c in m.commands:
            if c.name in indice:
                outro = indice[c.name][0].id
                raise ManifestError(f"comando {c.name!r} declarado por dois plugins: {outro!r} e {m.id!r}")
            indice[c.name] = (m, c)
    return indice


def resolve_handler(handler: str) -> Callable:
    """Importa modulo:funcao e devolve a função. Só é chamado no despacho, nunca na descoberta."""
    modulo, _, funcao = handler.partition(":")
    try:
        mod = importlib.import_module(modulo)
    except ImportError as exc:
        raise ManifestError(f"handler {handler!r}: módulo não importável ({exc})") from exc
    alvo = getattr(mod, funcao, None)
    if not callable(alvo):
        raise ManifestError(f"handler {handler!r}: {funcao!r} não é uma função em {modulo!r}")
    return alvo

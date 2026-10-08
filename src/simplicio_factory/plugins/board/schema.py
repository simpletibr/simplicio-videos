"""Schema do quadro (#86): schemas/factory/board.schema.json, gravado por `make factory-schema` (gerador em contracts/schema.py).

Não edite o JSON à mão: mude este módulo e rode `make factory-schema`. As oito colunas são fixas e na ordem do quadro
(`prefixItems`), e cada cartão traz só os campos que `board list --json` mostra.
"""

from __future__ import annotations

from simplicio_factory.contracts.models import REVIEW_VALUES, ROUTES, STATES
from simplicio_factory.contracts.schema import FAILED_FROM
from simplicio_factory.plugins.board.model import COLUNAS, SCHEMA


def _cartao() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "brand", "state", "route", "review", "failed_from", "comments"],
        "properties": {
            "id": {"type": "string", "pattern": "^[A-Za-z0-9_-]+$"},
            "brand": {"type": "string", "minLength": 1},
            "state": {"enum": list(STATES)},
            "route": {"enum": list(ROUTES)},
            "review": {"enum": [*REVIEW_VALUES, None]},
            "failed_from": {"enum": [*FAILED_FROM, None]},
            "comments": {"type": "integer", "minimum": 0},
        },
    }


def _coluna(chave: str, titulo: str) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "title", "cards"],
        "properties": {
            "id": {"const": chave},
            "title": {"const": titulo},
            "cards": {"type": "array", "items": _cartao()},
        },
    }


def build_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": SCHEMA,
        "description": "Quadro kanban derivado dos itens (#86, épico #81). Gerado por simplicio_factory.plugins.board.schema.",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "columns"],
        "properties": {
            "schema": {"const": SCHEMA},
            "columns": {
                "type": "array",
                "prefixItems": [_coluna(chave, titulo) for chave, titulo in COLUNAS],
                "minItems": len(COLUNAS),
                "maxItems": len(COLUNAS),
            },
        },
    }

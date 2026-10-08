"""Gerador de schemas/factory/item.schema.json (#33). Não edite o JSON à mão.

Uso (pelo alvo `make factory-schema`, que entra em `make regen`):
    python -m simplicio_factory.contracts.schema [caminho_de_saida]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = ROOT / "schemas" / "factory" / "item.schema.json"
STATES = ["idea", "drafted", "rendering", "rendered", "failed"]


def build_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "simplicio.factory-item/v1",
        "description": "Estado de um item da fábrica (kernel #33). Gerado por simplicio_factory.contracts.schema.",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "id", "brand", "state"],
        "properties": {
            "schema": {"const": "simplicio.factory-item/v1"},
            "id": {"type": "string", "pattern": "^[A-Za-z0-9_-]+$"},
            "brand": {"type": "string", "minLength": 1},
            "state": {"enum": STATES},
            "failed_from": {"enum": ["rendering", None]},
        },
    }


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

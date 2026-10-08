"""Schema do manifesto de plugin (#32): schemas/plugin.manifest.schema.json (fase 1: vermelho, arquivo ainda não existe)."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from _host_fixtures import manifesto  # noqa: F401 (fixtures do host de plugins)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "plugin.manifest.schema.json"


def _carrega_schema() -> dict:
    assert SCHEMA.is_file(), "schemas/plugin.manifest.schema.json ainda não existe (fase 2 do #32)"
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_schema_e_json_schema_valido():
    Draft202012Validator.check_schema(_carrega_schema())


def test_manifesto_valido_passa_no_schema(manifesto):
    validador = Draft202012Validator(_carrega_schema())
    assert list(validador.iter_errors(manifesto())) == []


def test_manifesto_sem_commands_e_rejeitado(manifesto):
    dados = manifesto()
    del dados["commands"]
    validador = Draft202012Validator(_carrega_schema())
    assert list(validador.iter_errors(dados)), "manifesto sem commands deveria falhar na validação"

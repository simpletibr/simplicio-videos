"""schemas/factory/item.schema.json (#33): JSON Schema válido, aceita item válido, rejeita item sem `state`.

O arquivo é gerado pelo alvo `factory-schema` (mk/kernel.mk), que entra em `make regen`. O teste regera em
um caminho temporário (FACTORY_SCHEMA_OUT) e confere que o arquivo commitado é igual ao gerado.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schemas" / "factory" / "item.schema.json"

VALID_ITEM = {
    "schema": "simplicio.factory-item/v1",
    "id": "itm_01HZTEST0000000000000001",
    "brand": "acme",
    "state": "idea",
}


def _load_schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_schema_is_valid_json_schema_2020_12():
    jsonschema.Draft202012Validator.check_schema(_load_schema())


def test_valid_item_passes():
    validator = jsonschema.Draft202012Validator(_load_schema())

    assert list(validator.iter_errors(VALID_ITEM)) == []


def test_item_without_state_is_rejected():
    validator = jsonschema.Draft202012Validator(_load_schema())
    item = {key: value for key, value in VALID_ITEM.items() if key != "state"}

    assert list(validator.iter_errors(item)), "item sem state deveria ser rejeitado"


def test_committed_schema_equals_make_factory_schema_output(tmp_path):
    committed = SCHEMA.read_bytes()
    generated = tmp_path / "item.schema.json"

    subprocess.run(
        ["make", "-s", "factory-schema", f"FACTORY_SCHEMA_OUT={generated}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert generated.read_bytes() == committed


def test_make_regen_runs_factory_schema():
    dry_run = subprocess.run(["make", "-n", "regen"], cwd=ROOT, check=True, capture_output=True, text=True)

    assert "item.schema.json" in dry_run.stdout

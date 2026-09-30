import copy
import json

import pytest
import yaml
from jsonschema import Draft202012Validator

from conftest import FIXTURE, LOTHUS, ROOT, WJR
from simplicio_video.contract import schema_errors

SCHEMA = json.loads((ROOT / "schema" / "contract.schema.json").read_text())


def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("path", [WJR, LOTHUS, FIXTURE / "contract.yaml"], ids=["wjr", "lothus", "mini"])
def test_real_contracts_match_schema(path):
    assert schema_errors(yaml.safe_load(path.read_text()), ROOT) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d.pop("drive"), "drive"),
    (lambda d: d["drive"].update(caminho="clientes/Lothus/2026/Dia"), "caminho"),
    (lambda d: d["drive"].update(arquivo="lothus final.mp4"), "arquivo"),
    (lambda d: d["cliente"].update(drive_nome="Lothus Odontologia"), "drive_nome"),
    (lambda d: d["voz"].update(provider="azure"), "provider"),
    (lambda d: d["cenas"][0]["fala"].pop("max_s"), "max_s"),
    (lambda d: d["cenas"][0]["sfx"][0].update(tipo="explosao"), "tipo"),
    (lambda d: d.update(extra=1), "extra"),
])
def test_schema_rejects_bad_contracts(mutate, needle):
    d = copy.deepcopy(yaml.safe_load(LOTHUS.read_text()))
    mutate(d)
    errs = schema_errors(d, ROOT)
    assert errs and any(needle in e for e in errs), errs

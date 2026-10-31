import copy
import json

import pytest
import yaml
from jsonschema import Draft202012Validator

from conftest import FIXTURE, LOTHUS, ROOT, WJR, needs_client
from simplicio_video.contract import schema_errors

DATA = ROOT / "src" / "simplicio_video" / "data"  # esquemas, templates e motion: dentro do pacote (#74)
SCHEMA = json.loads((DATA / "schema" / "contract.schema.json").read_text())


def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("path", [pytest.param(WJR, marks=needs_client(WJR)), pytest.param(LOTHUS, marks=needs_client(LOTHUS)),
                                  FIXTURE / "contract.yaml"], ids=["wjr", "lothus", "mini"])
def test_real_contracts_match_schema(path):
    assert schema_errors(yaml.safe_load(path.read_text())) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d.update(drive={"caminho": "simplicio-video/clientes/Lothus/2026/Dia", "arquivo": "Lothus - Dia - v01.mp4"}), "drive"),
    (lambda d: d.update(drive={"caminho": "clientes/Lothus/2026/Dia"}), "drive"),
    (lambda d: d.update(drive={"arquivo": "lothus final.mp4"}), "drive"),
    (lambda d: d["cliente"].update(drive_nome="Lothus Odontologia"), "drive_nome"),
    (lambda d: d["voz"].update(provider="azure"), "provider"),
    (lambda d: d["cenas"][0]["fala"].pop("max_s"), "max_s"),
    (lambda d: d["cenas"][0]["sfx"][0].update(tipo="explosao"), "tipo"),
    (lambda d: d.update(extra=1), "extra"),
])
def test_schema_rejects_bad_contracts(mutate, needle):
    d = copy.deepcopy(yaml.safe_load(LOTHUS.read_text()))
    mutate(d)
    errs = schema_errors(d)
    assert errs and any(needle in e for e in errs), errs

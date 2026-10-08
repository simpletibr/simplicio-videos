"""Golden do contrato (#16): Draft + brand da fixture gera golden/contract.yaml byte a byte, e o YAML passa no
validador do motor (simplicio_video.contract), não só no schema.
"""

from __future__ import annotations

import shutil

from tests.factory.plugins.studio._studio import FIXTURES, GOLDEN, composer_module, load_brand, load_draft


def test_composer_gera_os_bytes_do_golden():
    produced = composer_module().compose_contract(load_draft(), load_brand())

    assert produced.encode("utf-8") == GOLDEN.read_bytes()


def test_golden_passa_no_validador_do_motor(tmp_path):
    from simplicio_video.contract import load, validate

    contract_dir = tmp_path / "item"
    (contract_dir / "assets").mkdir(parents=True)
    shutil.copy(GOLDEN, contract_dir / "contract.yaml")
    shutil.copy(FIXTURES / "logo.svg", contract_dir / "assets" / "logo.svg")

    report = validate(load(contract_dir / "contract.yaml"))

    assert report.errors == []
    assert report.ok

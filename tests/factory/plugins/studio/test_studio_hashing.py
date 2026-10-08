"""content_hash (#16): sha256 sobre contrato, draft e assets; estável para a mesma entrada e muda com qualquer um deles."""

from __future__ import annotations

import re
import shutil

from tests.factory.plugins.studio._studio import FIXTURES, GOLDEN, draft_with, hashing_module, load_draft


def _project(tmp_path):
    root = tmp_path / "item"
    (root / "assets").mkdir(parents=True)
    shutil.copy(GOLDEN, root / "contract.yaml")
    shutil.copy(FIXTURES / "logo.svg", root / "assets" / "logo.svg")
    return root / "contract.yaml"


def test_hash_e_sha256_e_estavel(tmp_path):
    contract = _project(tmp_path)

    first = hashing_module().content_hash(contract, load_draft())

    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert hashing_module().content_hash(contract, load_draft()) == first


def test_mudar_o_draft_muda_o_hash(tmp_path):
    contract = _project(tmp_path)
    base = hashing_module().content_hash(contract, load_draft())

    changed = hashing_module().content_hash(contract, draft_with(idea="Outra ideia, mesma marca."))

    assert changed != base


def test_mudar_um_asset_muda_o_hash(tmp_path):
    contract = _project(tmp_path)
    base = hashing_module().content_hash(contract, load_draft())
    (tmp_path / "item" / "assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")

    assert hashing_module().content_hash(contract, load_draft()) != base

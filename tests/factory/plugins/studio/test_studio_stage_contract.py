"""StudioStage sob o contrato de estágio do kernel (#16): herda do Stage, nome `studio`, roda com `run(item, store)`.

A classe de teste herda de `StageContract` (base de teste do kernel, #33), como o StoreContractSuite em
tests/factory/contracts/test_store_contract.py. O `make_stage()` devolve o estágio real.
"""

from __future__ import annotations

import pytest

from tests.factory._fixtures import contracts
from tests.factory.plugins.studio._studio import json_store, make_item, make_stage, stage_module

StageContract = contracts().StageContract


class TestStudioStageContract(StageContract):
    @pytest.fixture(autouse=True)
    def _tmp(self, tmp_path):
        self.tmp = tmp_path

    def make_stage(self):
        return make_stage(self.tmp)

    def test_studio_stage_herda_do_stage_do_kernel(self):
        stage_cls = stage_module().StudioStage

        assert contracts().Stage in stage_cls.__mro__

    def test_nome_do_estagio_e_studio(self):
        assert self.make_stage().name == "studio"

    def test_run_recebe_item_e_store_e_leva_a_rendered(self):
        store = json_store(self.tmp / "factory")
        item = make_item()
        store.save_item(item)
        stage = self.make_stage()

        result = stage.run(item, store)

        assert result is None
        assert store.get_item(item.id).state == "rendered"

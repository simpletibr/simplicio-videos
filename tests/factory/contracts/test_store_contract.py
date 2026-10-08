"""Contract suite do Store (#33): MemoryStore (testkit) e JsonStore (arquivo em tmp_path) passam o mesmo conjunto.

Interface usada: `save_item(item)`, `get_item(id) -> Item | None`, `list_items() -> list[Item]` e, para eventos,
`read() -> list[Event]` (com `kind`, `item_id`, `seq`). Eventos entram só via `transition()`.
"""

from __future__ import annotations

from dataclasses import replace

from tests.factory._fixtures import contracts, json_store, make_item, memory_store


class StoreContractSuite:
    """Base sem prefixo Test: o pytest não a coleta sozinha, só as subclasses abaixo."""

    def make_store(self, tmp_path):
        raise NotImplementedError

    def test_save_then_get_returns_equal_item(self, tmp_path):
        store = self.make_store(tmp_path)
        item = make_item(state="drafted")

        store.save_item(item)

        assert store.get_item(item.id) == item

    def test_get_unknown_id_returns_none(self, tmp_path):
        store = self.make_store(tmp_path)

        assert store.get_item("itm_01HZNAOEXISTE000000000000") is None

    def test_save_same_id_overwrites(self, tmp_path):
        store = self.make_store(tmp_path)
        item = make_item(state="idea")
        store.save_item(item)

        store.save_item(replace(item, state="drafted"))

        assert store.get_item(item.id).state == "drafted"
        assert [i.id for i in store.list_items()] == [item.id]

    def test_list_returns_every_saved_item(self, tmp_path):
        store = self.make_store(tmp_path)
        for item_id in ("itm_01HZAAAA000000000000000001", "itm_01HZBBBB000000000000000002", "itm_01HZCCCC000000000000000003"):
            store.save_item(make_item(item_id=item_id))

        ids = sorted(i.id for i in store.list_items())

        assert ids == ["itm_01HZAAAA000000000000000001", "itm_01HZBBBB000000000000000002", "itm_01HZCCCC000000000000000003"]

    def test_transition_registers_one_event_readable_from_store(self, tmp_path):
        store = self.make_store(tmp_path)
        item = make_item()
        store.save_item(item)

        contracts().transition(item, "drafted", store)

        events = store.read()
        assert [e.kind for e in events] == ["item.state_changed"]
        assert events[0].item_id == item.id

    def test_event_seq_is_strictly_increasing(self, tmp_path):
        store = self.make_store(tmp_path)
        item = make_item()
        store.save_item(item)
        contracts().transition(item, "drafted", store)
        contracts().transition(item, "rendering", store)

        seqs = [e.seq for e in store.read()]

        assert len(seqs) == 2
        assert seqs == sorted(set(seqs))


class TestMemoryStoreContract(StoreContractSuite):
    def make_store(self, tmp_path):
        return memory_store()


class TestJsonStoreContract(StoreContractSuite):
    def make_store(self, tmp_path):
        return json_store(tmp_path / "factory")

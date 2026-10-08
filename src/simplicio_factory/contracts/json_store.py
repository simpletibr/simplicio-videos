"""JsonStore: um arquivo JSON por item e um log de eventos JSON Lines, em SIMPLICIO_FACTORY_HOME.

Padrão da raiz: `.simplicio-factory/` (gitignored). Nenhum outro backend no MVP.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from simplicio_factory.contracts.models import Event, Item, default_production

ITEM_SCHEMA = "simplicio.factory-item/v1"
DEFAULT_HOME = ".simplicio-factory"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _check_id(item_id: str) -> str:
    if not _ID_RE.match(item_id):
        raise ValueError(f"id de item inválido: {item_id!r}")
    return item_id


class JsonStore:
    def __init__(self, root: Optional[os.PathLike | str] = None) -> None:
        if root is None:
            root = os.environ.get("SIMPLICIO_FACTORY_HOME") or DEFAULT_HOME
        self.root = Path(root)
        self._items_dir = self.root / "items"
        self._events_path = self.root / "events.jsonl"

    def _item_path(self, item_id: str) -> Path:
        return self._items_dir / f"{_check_id(item_id)}.json"

    def save_item(self, item: Item) -> None:
        self._items_dir.mkdir(parents=True, exist_ok=True)
        path = self._item_path(item.id)
        payload = {
            "schema": ITEM_SCHEMA,
            "id": item.id,
            "brand": item.brand,
            "state": item.state,
            "failed_from": item.failed_from,
            "production": item.production,
            "review": item.review,
        }
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def get_item(self, item_id: str) -> Optional[Item]:
        path = self._item_path(item_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Item(
            id=data["id"],
            brand=data["brand"],
            state=data["state"],
            failed_from=data.get("failed_from"),
            production=data.get("production") or default_production(),
            review=data.get("review"),
        )

    def list_items(self) -> list[Item]:
        if not self._items_dir.is_dir():
            return []
        return [self.get_item(p.stem) for p in sorted(self._items_dir.glob("*.json"))]

    def append_event(self, kind: str, item_id: str, data: dict) -> Event:
        event = Event(seq=len(self.read()) + 1, kind=kind, item_id=item_id, data=dict(data))
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"seq": event.seq, "kind": event.kind, "item_id": event.item_id, "data": event.data},
            ensure_ascii=False,
            sort_keys=True,
        )
        with self._events_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return event

    def read(self) -> list[Event]:
        if not self._events_path.is_file():
            return []
        events = []
        for line in self._events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                events.append(Event(seq=row["seq"], kind=row["kind"], item_id=row["item_id"], data=row["data"]))
        return events

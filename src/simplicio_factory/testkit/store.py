"""MemoryStore: Store em memória (testkit). Guarda cópias, como um store real faria."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from simplicio_factory.contracts.models import Event, Item


class MemoryStore:
    def __init__(self) -> None:
        self._items: dict[str, Item] = {}
        self._events: list[Event] = []

    def save_item(self, item: Item) -> None:
        self._items[item.id] = replace(item)

    def get_item(self, item_id: str) -> Optional[Item]:
        item = self._items.get(item_id)
        return None if item is None else replace(item)

    def list_items(self) -> list[Item]:
        return [replace(item) for item in self._items.values()]

    def append_event(self, kind: str, item_id: str, data: dict) -> Event:
        event = Event(seq=len(self._events) + 1, kind=kind, item_id=item_id, data=dict(data))
        self._events.append(event)
        return event

    def read(self) -> list[Event]:
        return list(self._events)

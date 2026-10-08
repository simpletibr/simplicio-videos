"""Protocols do kernel: Store, Renderer, Stage e a base de teste StageContract."""

from __future__ import annotations

import abc
from typing import Optional, Protocol

from simplicio_factory.contracts.models import Event, Item, RenderResult


class Store(Protocol):
    def save_item(self, item: Item) -> None: ...

    def get_item(self, item_id: str) -> Optional[Item]: ...

    def list_items(self) -> list[Item]: ...

    def append_event(self, kind: str, item_id: str, data: dict) -> Event: ...

    def read(self) -> list[Event]: ...


class Renderer(Protocol):
    def render(self, contract_path: str, preview: bool) -> RenderResult: ...


class Stage(Protocol):
    name: str

    def run(self, item: Item, store: Store) -> None: ...


class StageContract(abc.ABC):
    """Base da suíte de contrato de um estágio: a subclasse diz como construir o estágio."""

    @abc.abstractmethod
    def make_stage(self) -> Stage:
        """Devolve uma instância nova do estágio sob teste."""

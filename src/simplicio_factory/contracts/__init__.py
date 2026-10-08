"""Contratos do kernel: dataclasses, Protocols, InvalidTransition e transition().

O JsonStore fica em `simplicio_factory.contracts.json_store` (import explícito).
"""

from simplicio_factory.contracts.errors import InvalidTransition
from simplicio_factory.contracts.models import Brand, Draft, Event, Item, RenderResult
from simplicio_factory.contracts.protocols import Renderer, Stage, StageContract, Store
from simplicio_factory.contracts.transitions import VALID_TRANSITIONS, transition

__all__ = [
    "Brand",
    "Draft",
    "Event",
    "InvalidTransition",
    "Item",
    "RenderResult",
    "Renderer",
    "Stage",
    "StageContract",
    "Store",
    "VALID_TRANSITIONS",
    "transition",
]

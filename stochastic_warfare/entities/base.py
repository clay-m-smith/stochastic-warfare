"""Minimal base entity — extended in Phase 2."""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.types import Position


@dataclass
class Entity:
    """Base class for all simulation entities (units, platforms, etc.)."""

    entity_id: str
    position: Position

    def get_state(self) -> dict:
        """Serialize entity state for checkpointing."""
        return {
            "entity_id": self.entity_id,
            "position": tuple(self.position),
        }

    def set_state(self, state: dict) -> None:
        """Restore entity state from a checkpoint dict."""
        self.entity_id = state["entity_id"]
        self.position = Position(*state["position"])

"""Tests for entities/base.py — minimal entity."""

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Entity


class TestEntityBasics:
    def test_creation(self) -> None:
        e = Entity(entity_id="tank-01", position=Position(100.0, 200.0, 0.0))
        assert e.entity_id == "tank-01"
        assert e.position == Position(100.0, 200.0, 0.0)

    def test_position_mutable(self) -> None:
        e = Entity(entity_id="inf-01", position=Position(0.0, 0.0))
        e.position = Position(50.0, 75.0, 10.0)
        assert e.position.easting == 50.0


class TestEntityState:
    def test_get_state(self) -> None:
        e = Entity(entity_id="arty-01", position=Position(1.0, 2.0, 3.0))
        state = e.get_state()
        assert state["entity_id"] == "arty-01"
        assert state["position"] == (1.0, 2.0, 3.0)

    def test_roundtrip(self) -> None:
        original = Entity(entity_id="helo-01", position=Position(500.0, 600.0, 100.0))
        state = original.get_state()

        restored = Entity(entity_id="", position=Position(0.0, 0.0))
        restored.set_state(state)

        assert restored.entity_id == original.entity_id
        assert restored.position == original.position

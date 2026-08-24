"""Phase 58e: GroundUnit fuel state and checkpoint contracts."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.unit_classes.ground import GroundUnit


class TestGroundUnitFuel:
    """GroundUnit has a fuel_remaining field."""

    def test_default_fuel_is_full(self):
        u = GroundUnit(entity_id="t1", position=Position(0, 0, 0))
        assert u.fuel_remaining == 1.0

    def test_custom_fuel(self):
        u = GroundUnit(entity_id="t1", position=Position(0, 0, 0), fuel_remaining=0.5)
        assert u.fuel_remaining == 0.5

    def test_get_state_preserves_fuel(self):
        u = GroundUnit(entity_id="t1", position=Position(0, 0, 0), fuel_remaining=0.3)
        state = u.get_state()
        assert state["fuel_remaining"] == pytest.approx(0.3)

    def test_set_state_restores_fuel(self):
        u = GroundUnit(entity_id="t1", position=Position(0, 0, 0))
        state = u.get_state()
        state["fuel_remaining"] = 0.42
        u.set_state(state)
        assert u.fuel_remaining == pytest.approx(0.42)

    def test_set_state_backward_compat(self):
        """Old state dicts without fuel_remaining default to 1.0."""
        u = GroundUnit(entity_id="t1", position=Position(0, 0, 0), fuel_remaining=0.1)
        state = u.get_state()
        del state["fuel_remaining"]
        u.set_state(state)
        assert u.fuel_remaining == 1.0

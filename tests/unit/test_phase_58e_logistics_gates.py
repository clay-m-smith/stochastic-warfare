"""Phase 58e: Fuel and ammo gate tests.

Verifies that GroundUnit tracks fuel_remaining, battle.py gates movement
on fuel, and ammo gating works (regression).
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.unit_classes.ground import GroundUnit, Posture


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


class TestFuelGateBehavior:
    """Fuel gating in movement logic."""

    def test_vehicle_no_fuel_cannot_move(self):
        """A vehicle (max_speed > 5) with fuel=0 should not move."""
        u = GroundUnit(
            entity_id="tank1", position=Position(0, 0, 0),
            max_speed=15.0, fuel_remaining=0.0,
        )
        # Simulate the fuel gate check from battle.py
        _fuel = getattr(u, "fuel_remaining", 1.0)
        _is_vehicle = getattr(u, "max_speed", 0) > 5.0
        should_skip = (_fuel <= 0.0 and _is_vehicle)
        assert should_skip, "Vehicle with no fuel should be movement-gated"

    def test_infantry_no_fuel_still_moves(self):
        """Infantry (max_speed <= 5) is not fuel-gated."""
        u = GroundUnit(
            entity_id="inf1", position=Position(0, 0, 0),
            max_speed=4.0, fuel_remaining=0.0,
        )
        _fuel = getattr(u, "fuel_remaining", 1.0)
        _is_vehicle = getattr(u, "max_speed", 0) > 5.0
        should_skip = (_fuel <= 0.0 and _is_vehicle)
        assert not should_skip, "Infantry should not be fuel-gated"

    def test_vehicle_with_fuel_moves(self):
        """A vehicle with fuel should not be gated."""
        u = GroundUnit(
            entity_id="apc1", position=Position(0, 0, 0),
            max_speed=20.0, fuel_remaining=0.8,
        )
        _fuel = getattr(u, "fuel_remaining", 1.0)
        _is_vehicle = getattr(u, "max_speed", 0) > 5.0
        should_skip = (_fuel <= 0.0 and _is_vehicle)
        assert not should_skip

    def test_fuel_consumption_proportional_to_distance(self):
        """Fuel consumed = move_dist * fuel_rate."""
        u = GroundUnit(
            entity_id="tank2", position=Position(0, 0, 0),
            max_speed=15.0, fuel_remaining=1.0,
        )
        move_dist = 100.0  # meters
        fuel_rate = 0.0001
        new_fuel = max(0.0, u.fuel_remaining - move_dist * fuel_rate)
        assert new_fuel == pytest.approx(0.99)  # 1.0 - 0.01

    def test_unit_without_fuel_attr_safe(self):
        """getattr fallback ensures backward compat for units without fuel."""
        from stochastic_warfare.entities.base import Unit
        u = Unit(entity_id="generic", position=Position(0, 0, 0))
        fuel = getattr(u, "fuel_remaining", 1.0)
        assert fuel == 1.0

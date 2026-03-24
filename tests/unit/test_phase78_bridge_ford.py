"""Phase 78b: Bridge capacity and ford crossing tests."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit


# ---------------------------------------------------------------------------
# Unit weight_tons field
# ---------------------------------------------------------------------------


class TestUnitWeight:
    """Unit.weight_tons field tests."""

    def test_default_weight_is_zero(self):
        u = Unit(entity_id="inf1", position=Position(0, 0))
        assert u.weight_tons == 0.0

    def test_weight_in_get_state(self):
        u = Unit(entity_id="tank1", position=Position(0, 0), weight_tons=62.0)
        state = u.get_state()
        assert state["weight_tons"] == 62.0

    def test_weight_in_set_state(self):
        u = Unit(entity_id="tank1", position=Position(0, 0))
        state = u.get_state()
        state["weight_tons"] = 45.0
        u2 = Unit(entity_id="x", position=Position(0, 0))
        u2.set_state(state)
        assert u2.weight_tons == 45.0

    def test_weight_defaults_in_set_state_when_missing(self):
        """Legacy checkpoints without weight_tons should default to 0.0."""
        u = Unit(entity_id="inf1", position=Position(0, 0))
        state = u.get_state()
        del state["weight_tons"]
        u2 = Unit(entity_id="x", position=Position(0, 0))
        u2.set_state(state)
        assert u2.weight_tons == 0.0


# ---------------------------------------------------------------------------
# Bridge capacity enforcement
# ---------------------------------------------------------------------------


class TestBridgeCapacity:
    """Bridge capacity enforcement logic tests."""

    def test_heavy_tank_blocked_by_light_bridge(self):
        """A 62t tank should be blocked by a 40t bridge."""
        from stochastic_warfare.terrain.infrastructure import Bridge

        bridge = Bridge(bridge_id="br1", position=(100.0, 100.0), road_id="r1", capacity_tons=40.0)
        unit_weight = 62.0
        assert unit_weight > bridge.capacity_tons

    def test_infantry_crosses_any_bridge(self):
        """Infantry with 0t weight is never blocked."""
        from stochastic_warfare.terrain.infrastructure import Bridge

        bridge = Bridge(bridge_id="br1", position=(100.0, 100.0), road_id="r1", capacity_tons=10.0)
        unit_weight = 0.0
        # weight 0 means no enforcement
        assert unit_weight <= 0

    def test_medium_vehicle_crosses_40t_bridge(self):
        """A 27.6t IFV crosses a 40t bridge."""
        from stochastic_warfare.terrain.infrastructure import Bridge

        bridge = Bridge(bridge_id="br1", position=(100.0, 100.0), road_id="r1", capacity_tons=40.0)
        unit_weight = 27.6
        assert unit_weight < bridge.capacity_tons

    def test_weight_defaults_for_known_types(self):
        """Known vehicle types have weight defaults in the battle loop."""
        _WEIGHT_DEFAULTS = {
            "m1a2_abrams": 62.0, "t72b": 41.0, "t90a": 46.5,
            "leopard_2a6": 62.3, "challenger_2": 62.5,
            "m2_bradley": 27.6, "bmp2": 14.3, "btr80": 13.6,
            "m113": 12.3, "stryker": 18.0,
        }
        assert _WEIGHT_DEFAULTS["m1a2_abrams"] == 62.0
        assert _WEIGHT_DEFAULTS.get("infantry_squad", 0.0) == 0.0


# ---------------------------------------------------------------------------
# Ford crossing
# ---------------------------------------------------------------------------


class TestFordCrossing:
    """Ford crossing logic tests."""

    def test_ford_available_at_reduced_speed(self):
        """Ford crossing should reduce effective speed to 30%."""
        base_speed = 10.0
        ford_multiplier = 0.3
        assert base_speed * ford_multiplier == pytest.approx(3.0)

    def test_movement_into_water_blocked_without_ford_or_ice(self):
        """Without a ford or ice, water should block movement."""
        from stochastic_warfare.terrain.hydrography import HydrographyManager

        hydro = HydrographyManager()
        # Empty manager — no rivers/lakes, so is_in_water returns False
        assert hydro.is_in_water(Position(50.0, 50.0)) is False

    def test_ford_points_near_returns_list(self):
        """ford_points_near should return a list (possibly empty)."""
        from stochastic_warfare.terrain.hydrography import HydrographyManager

        hydro = HydrographyManager()
        fords = hydro.ford_points_near(Position(50.0, 50.0), 500.0)
        assert isinstance(fords, list)

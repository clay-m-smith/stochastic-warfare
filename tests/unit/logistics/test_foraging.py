"""Unit tests for ForagingEngine — Napoleonic living off the land.

Phase 75d: Tests zones, capacity, foraging operations, state persistence.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.logistics.foraging import (
    ForagingConfig,
    ForagingEngine,
    TerrainProductivity,
)

from .conftest import _rng


# ===================================================================
# Zones
# ===================================================================


class TestForagingZones:
    """Zone registration and productivity lookup."""

    def test_register(self):
        engine = ForagingEngine(rng=_rng())
        zone = engine.register_zone("z1", (1000.0, 2000.0), 5000.0, TerrainProductivity.GOOD)
        assert zone.zone_id == "z1"
        assert zone.remaining_fraction == 1.0

    def test_unknown_zone_zero_capacity(self):
        engine = ForagingEngine(rng=_rng())
        assert engine.compute_daily_capacity("nonexistent") == 0.0

    def test_productivity_ordering(self):
        engine = ForagingEngine(rng=_rng())
        capacities = {}
        for prod in TerrainProductivity:
            engine.register_zone(f"z_{prod.name}", (0, 0), 5000.0, prod)
            capacities[prod] = engine.compute_daily_capacity(f"z_{prod.name}")
        assert capacities[TerrainProductivity.ABUNDANT] > capacities[TerrainProductivity.GOOD]
        assert capacities[TerrainProductivity.GOOD] > capacities[TerrainProductivity.AVERAGE]
        assert capacities[TerrainProductivity.AVERAGE] > capacities[TerrainProductivity.POOR]
        assert capacities[TerrainProductivity.POOR] > capacities[TerrainProductivity.BARREN]


# ===================================================================
# Capacity
# ===================================================================


class TestForagingCapacity:
    """Seasonal and depletion effects on capacity."""

    def test_summer_capacity(self):
        engine = ForagingEngine(rng=_rng())
        engine.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
        cap = engine.compute_daily_capacity("z1", season="summer")
        assert cap > 0

    def test_winter_much_lower(self):
        engine = ForagingEngine(rng=_rng())
        engine.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
        summer = engine.compute_daily_capacity("z1", season="summer")
        winter = engine.compute_daily_capacity("z1", season="winter")
        assert winter < summer * 0.2

    def test_depleted_fraction(self):
        engine = ForagingEngine(rng=_rng())
        zone = engine.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
        full_cap = engine.compute_daily_capacity("z1")
        zone.remaining_fraction = 0.5
        half_cap = engine.compute_daily_capacity("z1")
        assert half_cap == pytest.approx(full_cap * 0.5, rel=0.01)

    def test_area_scales_with_radius(self):
        engine = ForagingEngine(rng=_rng())
        engine.register_zone("small", (0, 0), 1000.0, TerrainProductivity.AVERAGE)
        engine.register_zone("big", (0, 0), 5000.0, TerrainProductivity.AVERAGE)
        cap_small = engine.compute_daily_capacity("small")
        cap_big = engine.compute_daily_capacity("big")
        assert cap_big > cap_small


# ===================================================================
# Foraging operation
# ===================================================================


class TestForagingOperation:
    """One-day foraging operations."""

    def test_below_capacity_full_supply(self):
        engine = ForagingEngine(rng=_rng())
        engine.register_zone("z1", (0, 0), 10000.0, TerrainProductivity.ABUNDANT)
        result = engine.forage("z1", army_size=100, season="summer")
        assert result.rations_supplied >= 100.0
        assert result.deficit == 0.0

    def test_exceeds_capacity_deficit(self):
        cfg = ForagingConfig(men_per_km2_per_day=10.0)
        engine = ForagingEngine(config=cfg, rng=_rng())
        engine.register_zone("z1", (0, 0), 100.0, TerrainProductivity.POOR)
        result = engine.forage("z1", army_size=100000, season="winter")
        assert result.deficit > 0

    def test_zone_depleted(self):
        engine = ForagingEngine(rng=_rng())
        engine.register_zone("z1", (0, 0), 1000.0, TerrainProductivity.AVERAGE)
        cap = engine.compute_daily_capacity("z1")
        # Forage with army much larger than capacity → depletion
        engine.forage("z1", army_size=int(cap * 10), season="summer")
        assert engine._zones["z1"].remaining_fraction < 1.0

    def test_ambush_rate(self):
        # With many runs, ambush should occur ~5% of time
        cfg = ForagingConfig(ambush_risk_per_mission=1.0)  # guaranteed ambush
        engine = ForagingEngine(config=cfg, rng=_rng())
        engine.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
        result = engine.forage("z1", army_size=1000)
        assert result.ambush_occurred is True


# ===================================================================
# State persistence
# ===================================================================


class TestForagingState:
    """Checkpoint roundtrip."""

    def test_roundtrip(self):
        engine = ForagingEngine(rng=_rng())
        engine.register_zone("z1", (100.0, 200.0), 5000.0, TerrainProductivity.GOOD)
        state = engine.get_state()
        engine2 = ForagingEngine(rng=_rng())
        engine2.set_state(state)
        cap = engine2.compute_daily_capacity("z1", season="summer")
        assert cap > 0

    def test_depletion_preserved(self):
        engine = ForagingEngine(rng=_rng())
        engine.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
        engine._zones["z1"].remaining_fraction = 0.3
        state = engine.get_state()
        engine2 = ForagingEngine(rng=_rng())
        engine2.set_state(state)
        assert engine2._zones["z1"].remaining_fraction == pytest.approx(0.3)

    def test_recovery(self):
        engine = ForagingEngine(rng=_rng())
        engine.register_zone("z1", (0, 0), 5000.0, TerrainProductivity.GOOD)
        engine._zones["z1"].remaining_fraction = 0.5
        engine.update_recovery(dt_days=10.0)
        assert engine._zones["z1"].remaining_fraction > 0.5

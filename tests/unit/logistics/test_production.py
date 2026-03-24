"""Unit tests for ProductionEngine — supply production at depots.

Phase 75d: Tests facility registration, condition, production output, state.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.logistics.production import (
    ProductionEngine,
    ProductionFacilityConfig,
)

from .conftest import _rng


# ===================================================================
# Facility registration
# ===================================================================


class TestProductionFacility:
    """Facility registration and condition management."""

    def test_register_default_condition(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        cfg = ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"ammo": 10.0},
        )
        engine.register_facility(cfg)
        assert engine.get_facility_condition("f1") == 1.0

    def test_set_condition_clamped(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        cfg = ProductionFacilityConfig(facility_id="f1", facility_type="depot")
        engine.register_facility(cfg)
        engine.set_facility_condition("f1", 1.5)
        assert engine.get_facility_condition("f1") == 1.0
        engine.set_facility_condition("f1", -0.5)
        assert engine.get_facility_condition("f1") == 0.0

    def test_missing_facility_zero(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        assert engine.get_facility_condition("nonexistent") == 0.0

    def test_output_scales_with_condition(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        cfg = ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"ammo": 10.0},
        )
        engine.register_facility(cfg)
        engine.set_facility_condition("f1", 0.5)
        result = engine.update(dt_hours=1.0)
        assert result["f1"]["ammo"] == pytest.approx(5.0)


# ===================================================================
# Production output
# ===================================================================


class TestProductionOutput:
    """Production rates and condition effects."""

    def test_damaged_half_output(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        cfg = ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"fuel": 20.0},
        )
        engine.register_facility(cfg)
        engine.set_facility_condition("f1", 0.5)
        result = engine.update(dt_hours=2.0)
        assert result["f1"]["fuel"] == pytest.approx(20.0)  # 20 * 0.5 * 2

    def test_destroyed_nothing(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        cfg = ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"ammo": 10.0},
        )
        engine.register_facility(cfg)
        engine.set_facility_condition("f1", 0.0)
        result = engine.update(dt_hours=1.0)
        assert "f1" not in result  # zero production → not in results

    def test_multiple_supply_classes(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        cfg = ProductionFacilityConfig(
            facility_id="f1",
            facility_type="arsenal",
            production_rates={"ammo": 10.0, "fuel": 5.0, "food": 8.0},
        )
        engine.register_facility(cfg)
        result = engine.update(dt_hours=1.0)
        assert len(result["f1"]) == 3
        assert result["f1"]["ammo"] == pytest.approx(10.0)
        assert result["f1"]["fuel"] == pytest.approx(5.0)


# ===================================================================
# State persistence
# ===================================================================


class TestProductionState:
    """Checkpoint roundtrip."""

    def test_roundtrip(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        cfg = ProductionFacilityConfig(
            facility_id="f1",
            facility_type="factory",
            production_rates={"ammo": 10.0},
        )
        engine.register_facility(cfg)
        engine.set_facility_condition("f1", 0.7)
        state = engine.get_state()
        engine2 = ProductionEngine(bus, _rng())
        engine2.set_state(state)
        assert engine2.get_facility_condition("f1") == pytest.approx(0.7)

    def test_condition_preserved(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        cfg = ProductionFacilityConfig(
            facility_id="f1",
            facility_type="depot",
            production_rates={"food": 5.0},
        )
        engine.register_facility(cfg)
        engine.set_facility_condition("f1", 0.3)
        state = engine.get_state()
        assert state["conditions"]["f1"] == pytest.approx(0.3)

    def test_empty_valid(self):
        bus = EventBus()
        engine = ProductionEngine(bus, _rng())
        state = engine.get_state()
        engine2 = ProductionEngine(bus, _rng())
        engine2.set_state(state)
        assert engine2.get_facility_condition("f1") == 0.0

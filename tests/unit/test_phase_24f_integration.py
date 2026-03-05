"""Phase 24f integration tests --- war termination, engine wiring, backward compat.

Tests cover:
  - WarTerminationEngine (config, willingness, ceasefire, capitulation, state)
  - SimulationContext new fields (escalation & unconventional engines)
  - VictoryConditionType new enum values (CEASEFIRE, ARMISTICE)
  - Engine _update_escalation wiring
  - Backward compatibility (all defaults remain None)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from tests.conftest import TS, make_rng

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.escalation.war_termination import (
    WarTerminationConfig,
    WarTerminationEngine,
)
from stochastic_warfare.simulation.scenario import (
    CampaignScenarioConfig,
    SimulationContext,
    TerrainConfig,
    VictoryConditionConfig,
)
from stochastic_warfare.simulation.victory import VictoryConditionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bus() -> EventBus:
    return EventBus()


def _make_engine(
    config: WarTerminationConfig | None = None,
) -> WarTerminationEngine:
    return WarTerminationEngine(_make_bus(), config)


def _make_context(**overrides) -> SimulationContext:
    """Build a minimal SimulationContext for field-presence tests."""
    cfg = CampaignScenarioConfig(
        name="test",
        date="2024-01-01",
        duration_hours=24,
        terrain=TerrainConfig(width_m=1000, height_m=1000),
        sides=[
            {"side": "blue", "units": [{"unit_type": "infantry_platoon", "count": 1}]},
            {"side": "red", "units": [{"unit_type": "infantry_platoon", "count": 1}]},
        ],
    )
    clock = SimulationClock(
        start=TS,
        tick_duration=timedelta(seconds=3600),
    )
    rng_mgr = RNGManager(42)
    bus = EventBus()
    return SimulationContext(
        config=cfg,
        clock=clock,
        rng_manager=rng_mgr,
        event_bus=bus,
        **overrides,
    )


# ===========================================================================
# 1. War termination engine tests
# ===========================================================================


class TestWarTerminationConfig:
    """Config defaults are correct."""

    def test_defaults(self):
        cfg = WarTerminationConfig()
        assert cfg.ceasefire_threshold == 0.7
        assert cfg.armistice_delay_hours == 48.0
        assert cfg.min_stalemate_for_negotiation_hours == 72.0
        assert cfg.capitulation_threshold == 0.95
        assert cfg.territory_weight == 0.4
        assert cfg.force_correlation_weight == 0.3
        assert cfg.political_weight == 0.3


class TestNegotiationWillingness:
    """Willingness computation tests."""

    def test_basic_willingness(self):
        eng = _make_engine()
        w = eng.evaluate_negotiation_willingness(
            side="blue",
            territory_control_fraction=0.5,
            territory_objective_fraction=0.3,  # losing 70% of objectives
            force_correlation_trend=0.4,       # losing
            domestic_pressure=0.5,
            international_pressure=0.6,
            coalition_pressure=0.4,
        )
        # territory_weight * (1 - 0.3) + force_weight * (1 - 0.4)
        #   + political_weight * max(0.5, 0.6, 0.4)
        # = 0.4 * 0.7 + 0.3 * 0.6 + 0.3 * 0.6
        # = 0.28 + 0.18 + 0.18 = 0.64
        assert abs(w - 0.64) < 1e-9

    def test_willingness_stored(self):
        eng = _make_engine()
        eng.evaluate_negotiation_willingness(
            "red", 0.5, 0.0, 0.0, 0.8, 0.8, 0.8,
        )
        assert eng.get_willingness("red") > 0.0

    def test_willingness_clamped_low(self):
        eng = _make_engine()
        # All factors at 1.0 => (1-1)=0 for territory and force
        w = eng.evaluate_negotiation_willingness(
            "blue", 1.0, 1.0, 1.0, 0.0, 0.0, 0.0,
        )
        assert w == 0.0

    def test_willingness_clamped_high(self):
        eng = _make_engine()
        # Everything screaming "negotiate"
        w = eng.evaluate_negotiation_willingness(
            "blue", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0,
        )
        # 0.4*1 + 0.3*1 + 0.3*1 = 1.0
        assert w == 1.0

    def test_default_willingness_zero(self):
        eng = _make_engine()
        assert eng.get_willingness("nonexistent") == 0.0


class TestCeasefire:
    """Ceasefire trigger tests."""

    def test_ceasefire_triggers(self):
        eng = _make_engine()
        willingness = {"blue": 0.8, "red": 0.9}
        result = eng.check_ceasefire(willingness, 100.0, TS)
        assert result is True
        assert eng.is_ceasefire_active() is True

    def test_ceasefire_no_trigger_short_stalemate(self):
        eng = _make_engine()
        willingness = {"blue": 0.8, "red": 0.9}
        result = eng.check_ceasefire(willingness, 10.0, TS)
        assert result is False
        assert eng.is_ceasefire_active() is False

    def test_ceasefire_no_trigger_one_unwilling(self):
        eng = _make_engine()
        willingness = {"blue": 0.8, "red": 0.3}
        result = eng.check_ceasefire(willingness, 100.0, TS)
        assert result is False

    def test_activate_ceasefire_forced(self):
        eng = _make_engine()
        assert eng.is_ceasefire_active() is False
        eng.activate_ceasefire(TS)
        assert eng.is_ceasefire_active() is True


class TestCapitulation:
    """Capitulation threshold tests."""

    def test_capitulation_triggers(self):
        eng = _make_engine()
        result = eng.check_capitulation("blue", 0.6, 0.4, TS)
        # 0.6 + 0.4 = 1.0 > 0.95
        assert result is True

    def test_capitulation_no_trigger(self):
        eng = _make_engine()
        result = eng.check_capitulation("blue", 0.3, 0.3, TS)
        # 0.3 + 0.3 = 0.6 < 0.95
        assert result is False


class TestWarTerminationState:
    """State roundtrip tests."""

    def test_state_roundtrip(self):
        eng1 = _make_engine()
        eng1.evaluate_negotiation_willingness(
            "blue", 0.5, 0.3, 0.4, 0.5, 0.6, 0.7,
        )
        eng1.activate_ceasefire(TS)

        state = eng1.get_state()

        eng2 = _make_engine()
        eng2.set_state(state)

        assert eng2.get_willingness("blue") == eng1.get_willingness("blue")
        assert eng2.is_ceasefire_active() is True

    def test_ceasefire_time_serialized(self):
        eng = _make_engine()
        eng.activate_ceasefire(TS)
        state = eng.get_state()
        assert state["ceasefire_time"] == TS.isoformat()
        assert state["ceasefire_active"] is True

    def test_state_empty_by_default(self):
        eng = _make_engine()
        state = eng.get_state()
        assert state["willingness"] == {}
        assert state["ceasefire_active"] is False
        assert state["ceasefire_time"] is None


# ===========================================================================
# 2. Engine wiring tests
# ===========================================================================


class TestEngineWiring:
    """Verify SimulationContext fields and VictoryCondition types."""

    def test_context_accepts_new_fields(self):
        ctx = _make_context(
            escalation_engine="mock_esc",
            political_engine="mock_pol",
            consequence_engine="mock_con",
            unconventional_engine="mock_uw",
            insurgency_engine="mock_ins",
            sof_engine="mock_sof",
            war_termination_engine="mock_wt",
            incendiary_engine="mock_inc",
            uxo_engine="mock_uxo",
        )
        assert ctx.escalation_engine == "mock_esc"
        assert ctx.political_engine == "mock_pol"
        assert ctx.consequence_engine == "mock_con"
        assert ctx.unconventional_engine == "mock_uw"
        assert ctx.insurgency_engine == "mock_ins"
        assert ctx.sof_engine == "mock_sof"
        assert ctx.war_termination_engine == "mock_wt"
        assert ctx.incendiary_engine == "mock_inc"
        assert ctx.uxo_engine == "mock_uxo"

    def test_escalation_config_field(self):
        cfg = CampaignScenarioConfig(
            name="test",
            date="2024-01-01",
            duration_hours=24,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                {"side": "a", "units": [{"unit_type": "x", "count": 1}]},
                {"side": "b", "units": [{"unit_type": "x", "count": 1}]},
            ],
            escalation_config={"entry_thresholds": [0.0, 0.1]},
        )
        assert cfg.escalation_config is not None
        assert cfg.escalation_config["entry_thresholds"] == [0.0, 0.1]

    def test_escalation_config_defaults_none(self):
        cfg = CampaignScenarioConfig(
            name="test",
            date="2024-01-01",
            duration_hours=24,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                {"side": "a", "units": [{"unit_type": "x", "count": 1}]},
                {"side": "b", "units": [{"unit_type": "x", "count": 1}]},
            ],
        )
        assert cfg.escalation_config is None

    def test_victory_condition_ceasefire(self):
        assert VictoryConditionType.CEASEFIRE == 5

    def test_victory_condition_armistice(self):
        assert VictoryConditionType.ARMISTICE == 6

    def test_ceasefire_in_allowed_vc_types(self):
        vc = VictoryConditionConfig(type="ceasefire", side="blue")
        assert vc.type == "ceasefire"

    def test_armistice_in_allowed_vc_types(self):
        vc = VictoryConditionConfig(type="armistice", side="blue")
        assert vc.type == "armistice"


# ===========================================================================
# 3. Backward compatibility tests
# ===========================================================================


class TestBackwardCompatibility:
    """Existing behavior unchanged."""

    def test_all_new_fields_default_none(self):
        ctx = _make_context()
        assert ctx.escalation_engine is None
        assert ctx.political_engine is None
        assert ctx.consequence_engine is None
        assert ctx.unconventional_engine is None
        assert ctx.insurgency_engine is None
        assert ctx.sof_engine is None
        assert ctx.war_termination_engine is None
        assert ctx.incendiary_engine is None
        assert ctx.uxo_engine is None

    def test_escalation_config_none_is_fine(self):
        cfg = CampaignScenarioConfig(
            name="test",
            date="2024-01-01",
            duration_hours=24,
            terrain=TerrainConfig(width_m=1000, height_m=1000),
            sides=[
                {"side": "a", "units": [{"unit_type": "x", "count": 1}]},
                {"side": "b", "units": [{"unit_type": "x", "count": 1}]},
            ],
        )
        assert cfg.escalation_config is None

    def test_existing_vc_types_unchanged(self):
        assert VictoryConditionType.TERRITORY_CONTROL == 0
        assert VictoryConditionType.FORCE_DESTROYED == 1
        assert VictoryConditionType.TIME_EXPIRED == 2
        assert VictoryConditionType.MORALE_COLLAPSED == 3
        assert VictoryConditionType.SUPPLY_EXHAUSTED == 4

    def test_context_state_roundtrip_with_engines(self):
        """SimulationContext get_state/set_state includes new engines."""
        bus = EventBus()
        wt = WarTerminationEngine(bus)
        wt.activate_ceasefire(TS)
        wt.evaluate_negotiation_willingness(
            "blue", 0.5, 0.3, 0.4, 0.5, 0.6, 0.7,
        )

        ctx = _make_context(war_termination_engine=wt)
        state = ctx.get_state()
        assert "war_termination_engine" in state
        assert state["war_termination_engine"]["ceasefire_active"] is True

    def test_context_set_state_restores_engines(self):
        """set_state restores war termination engine state."""
        bus = EventBus()
        wt = WarTerminationEngine(bus)
        wt.activate_ceasefire(TS)
        wt.evaluate_negotiation_willingness(
            "red", 0.5, 0.2, 0.3, 0.4, 0.5, 0.6,
        )

        ctx1 = _make_context(war_termination_engine=wt)
        state = ctx1.get_state()

        # Build new context with a fresh engine
        wt2 = WarTerminationEngine(bus)
        assert wt2.is_ceasefire_active() is False
        ctx2 = _make_context(war_termination_engine=wt2)
        ctx2.set_state(state)

        assert wt2.is_ceasefire_active() is True
        assert wt2.get_willingness("red") == wt.get_willingness("red")

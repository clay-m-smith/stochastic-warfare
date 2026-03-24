"""Unit tests for CavalryEngine — multi-phase charge state machine.

Phase 75c: Tests charge phases, fatigue, rally, and state persistence.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.movement.cavalry import (
    CavalryConfig,
    CavalryEngine,
    ChargePhase,
)

from .conftest import _rng


# ===================================================================
# Charge phase transitions
# ===================================================================


class TestCavalryCharge:
    """Phase transitions: WALK → TROT → GALLOP → CHARGE → IMPACT → PURSUIT."""

    def test_initiate_far(self):
        engine = CavalryEngine(rng=_rng())
        state = engine.initiate_charge("c1", "u1", "t1", 500.0)
        assert state.phase == ChargePhase.WALK
        assert state.distance_to_target_m == 500.0

    def test_initiate_close(self):
        engine = CavalryEngine(rng=_rng())
        state = engine.initiate_charge("c1", "u1", "t1", 40.0)
        assert state.phase == ChargePhase.CHARGE

    def test_initiate_gallop_range(self):
        engine = CavalryEngine(rng=_rng())
        state = engine.initiate_charge("c1", "u1", "t1", 100.0)
        assert state.phase == ChargePhase.GALLOP

    def test_walk_to_trot(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 160.0)
        # Walk at 2.0 m/s, advance 10s = 20m → 140m < 150m → transitions
        phase = engine.update_charge("c1", 10.0)
        assert phase in (ChargePhase.TROT, ChargePhase.GALLOP)

    def test_gallop_to_charge(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 60.0)
        # At gallop speed 8 m/s, 2s = 16m → 44m < 50m → CHARGE
        phase = engine.update_charge("c1", 2.0)
        assert phase == ChargePhase.CHARGE

    def test_charge_to_impact(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 10.0)
        # At charge speed 10 m/s, 1s = 10m → contact
        phase = engine.update_charge("c1", 1.0)
        assert phase == ChargePhase.IMPACT

    def test_impact_to_pursuit(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 10.0)
        engine.update_charge("c1", 1.0)  # → IMPACT
        phase = engine.update_charge("c1", 0.1)  # → PURSUIT
        assert phase == ChargePhase.PURSUIT

    def test_dt_advances_distance(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 500.0)
        engine.update_charge("c1", 5.0)  # walk at 2 m/s → 10m
        state = engine._charges["c1"]
        assert state.distance_to_target_m == pytest.approx(490.0)

    def test_completed_charge_returns_rally(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 500.0)
        engine._charges["c1"].completed = True
        assert engine.update_charge("c1", 1.0) == ChargePhase.RALLY

    def test_missing_charge_returns_rally(self):
        engine = CavalryEngine(rng=_rng())
        assert engine.update_charge("nonexistent", 1.0) == ChargePhase.RALLY


# ===================================================================
# Fatigue and exhaustion
# ===================================================================


class TestCavalryExhaustion:
    """Fatigue accumulation at gallop+ speeds."""

    def test_fatigue_at_gallop(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 100.0)
        engine.update_charge("c1", 5.0)  # gallop: 0.02 * 5 = 0.1
        state = engine._charges["c1"]
        assert state.fatigue > 0

    def test_exhaustion_threshold(self):
        # Use a very long distance so the charge stays at gallop
        cfg = CavalryConfig(
            gallop_start_distance_m=10000.0,
            charge_start_distance_m=100.0,
            max_gallop_duration_s=60.0,
            exhaustion_threshold=1.0,
        )
        engine = CavalryEngine(config=cfg, rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 5000.0)
        # Walk to gallop range, then hold at gallop for >60s
        # Walk at 2 m/s → need (5000-10000) but let's force gallop
        state = engine._charges["c1"]
        state.phase = ChargePhase.GALLOP
        state.distance_to_target_m = 5000.0
        for _ in range(15):
            engine.update_charge("c1", 5.0)  # 75s > 60s max_gallop
        assert engine.is_exhausted("c1") is True

    def test_screening_modifier(self):
        engine = CavalryEngine(rng=_rng())
        assert engine.screening_modifier("hussar_light") == 1.5
        assert engine.screening_modifier("heavy_cavalry") == 1.0

    def test_not_exhausted_initially(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 500.0)
        assert engine.is_exhausted("c1") is False


# ===================================================================
# Rally phase
# ===================================================================


class TestCavalryRally:
    """Rally phase after charge."""

    def test_begin_rally(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 500.0)
        engine.begin_rally("c1")
        assert engine._charges["c1"].phase == ChargePhase.RALLY

    def test_rally_completes_after_duration(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 500.0)
        engine.begin_rally("c1")
        engine.update_charge("c1", 121.0)  # rally_duration_s = 120
        assert engine._charges["c1"].completed is True

    def test_speed_during_rally(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 500.0)
        engine.begin_rally("c1")
        assert engine.get_charge_speed("c1") == pytest.approx(0.5)

    def test_completed_speed_zero(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 500.0)
        engine._charges["c1"].completed = True
        assert engine.get_charge_speed("c1") == 0.0


# ===================================================================
# State persistence
# ===================================================================


class TestCavalryState:
    """Checkpoint roundtrip."""

    def test_roundtrip(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 300.0)
        engine.update_charge("c1", 5.0)
        state = engine.get_state()
        engine2 = CavalryEngine(rng=_rng())
        engine2.set_state(state)
        assert "c1" in engine2._charges
        assert engine2._charges["c1"].distance_to_target_m == pytest.approx(
            engine._charges["c1"].distance_to_target_m
        )

    def test_charge_fields_preserved(self):
        engine = CavalryEngine(rng=_rng())
        engine.initiate_charge("c1", "u1", "t1", 100.0)
        engine.update_charge("c1", 5.0)
        state = engine.get_state()
        c = state["charges"]["c1"]
        assert c["unit_id"] == "u1"
        assert c["target_id"] == "t1"
        assert c["fatigue"] >= 0

    def test_empty_valid(self):
        engine = CavalryEngine(rng=_rng())
        state = engine.get_state()
        engine2 = CavalryEngine(rng=_rng())
        engine2.set_state(state)
        assert len(engine2._charges) == 0

"""Unit tests for AncientFormationEngine — 7 formation types.

Phase 75c: Tests formation setup, transitions, modifiers, state persistence.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.movement.formation_ancient import (
    AncientFormationEngine,
    AncientFormationType,
)


# ===================================================================
# Formation setup
# ===================================================================


class TestAncientFormationSetup:
    """Initial formation assignment."""

    def test_set_formation_immediate(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.TESTUDO)
        assert engine.get_formation("u1") == AncientFormationType.TESTUDO

    def test_default_phalanx(self):
        engine = AncientFormationEngine()
        assert engine.get_formation("unknown") == AncientFormationType.PHALANX

    def test_all_types_valid(self):
        engine = AncientFormationEngine()
        for ft in AncientFormationType:
            engine.set_formation(f"u_{ft.name}", ft)
            assert engine.get_formation(f"u_{ft.name}") == ft

    def test_order_returns_time(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        time_s = engine.order_formation_change("u1", AncientFormationType.WEDGE)
        assert time_s > 0


# ===================================================================
# Transitions
# ===================================================================


class TestAncientFormationTransition:
    """Formation transition timing and behavior."""

    def test_completes_after_time(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        time_s = engine.order_formation_change("u1", AncientFormationType.TESTUDO)
        completed = engine.update(time_s + 1.0)
        assert "u1" in completed
        assert engine.get_formation("u1") == AncientFormationType.TESTUDO

    def test_is_transitioning(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        engine.order_formation_change("u1", AncientFormationType.WEDGE)
        assert engine.is_transitioning("u1") is True

    def test_rejected_during_transition(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        engine.order_formation_change("u1", AncientFormationType.WEDGE)
        # Second order during transition returns 0
        assert engine.order_formation_change("u1", AncientFormationType.SKIRMISH) == 0.0

    def test_same_formation_zero(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.TESTUDO)
        assert engine.order_formation_change("u1", AncientFormationType.TESTUDO) == 0.0

    def test_update_returns_completed(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        engine.set_formation("u2", AncientFormationType.SKIRMISH)
        engine.order_formation_change("u1", AncientFormationType.COLUMN)
        # u2 is not transitioning
        completed = engine.update(1000.0)  # enough time for any transition
        assert "u1" in completed
        assert "u2" not in completed


# ===================================================================
# Modifiers
# ===================================================================


class TestAncientFormationModifiers:
    """Formation-dependent combat modifiers."""

    def test_phalanx_melee_power(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        assert engine.melee_power("u1") == pytest.approx(1.2)

    def test_testudo_archery_vulnerability(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.TESTUDO)
        assert engine.archery_vulnerability("u1") == pytest.approx(0.1)

    def test_wedge_high_melee(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.WEDGE)
        assert engine.melee_power("u1") == pytest.approx(1.5)

    def test_skirmish_cavalry_vulnerable(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.SKIRMISH)
        assert engine.cavalry_vulnerability("u1") == pytest.approx(2.0)

    def test_worst_of_both_during_transition(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        engine.order_formation_change("u1", AncientFormationType.WEDGE)
        # Melee power: min(1.2, 1.5) = 1.2 (worst for beneficial)
        assert engine.melee_power("u1") == pytest.approx(1.2)
        # Flanking vuln: max(2.0, 0.5) = 2.0 (worst for vulnerability)
        assert engine.flanking_vulnerability("u1") == pytest.approx(2.0)

    def test_phalanx_low_cavalry_vulnerability(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        assert engine.cavalry_vulnerability("u1") == pytest.approx(0.3)

    def test_speed_multiplier(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.SKIRMISH)
        assert engine.speed_multiplier("u1") == pytest.approx(1.0)
        engine.set_formation("u2", AncientFormationType.TESTUDO)
        assert engine.speed_multiplier("u2") == pytest.approx(0.2)


# ===================================================================
# State persistence
# ===================================================================


class TestAncientFormationState:
    """Checkpoint roundtrip."""

    def test_roundtrip(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.WEDGE)
        state = engine.get_state()
        engine2 = AncientFormationEngine()
        engine2.set_state(state)
        assert engine2.get_formation("u1") == AncientFormationType.WEDGE

    def test_mid_transition_preserved(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.PHALANX)
        engine.order_formation_change("u1", AncientFormationType.SKIRMISH)
        engine.update(10.0)  # partial transition
        state = engine.get_state()
        engine2 = AncientFormationEngine()
        engine2.set_state(state)
        assert engine2.is_transitioning("u1") is True

    def test_none_target(self):
        engine = AncientFormationEngine()
        engine.set_formation("u1", AncientFormationType.COLUMN)
        state = engine.get_state()
        assert state["states"]["u1"]["target"] is None

    def test_empty_valid(self):
        engine = AncientFormationEngine()
        state = engine.get_state()
        engine2 = AncientFormationEngine()
        engine2.set_state(state)
        assert len(engine2._states) == 0

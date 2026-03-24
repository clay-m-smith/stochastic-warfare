"""Unit tests for NapoleonicFormationEngine — LINE, COLUMN, SQUARE, SKIRMISH.

Phase 75c: Tests formation setup, transitions, modifiers, state persistence.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.movement.formation_napoleonic import (
    NapoleonicFormationEngine,
    NapoleonicFormationType,
)


# ===================================================================
# Setup
# ===================================================================


class TestNapoleonicFormationSetup:
    """Initial formation assignment."""

    def test_set_immediate(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        assert engine.get_formation("u1") == NapoleonicFormationType.SQUARE

    def test_default_line(self):
        engine = NapoleonicFormationEngine()
        assert engine.get_formation("unknown") == NapoleonicFormationType.LINE

    def test_order_returns_time(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        time_s = engine.order_formation_change("u1", NapoleonicFormationType.COLUMN)
        assert time_s == pytest.approx(45.0)


# ===================================================================
# Transitions
# ===================================================================


class TestNapoleonicFormationTransition:
    """Formation transition timing."""

    def test_completes(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        time_s = engine.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        completed = engine.update(time_s + 1.0)
        assert "u1" in completed
        assert engine.get_formation("u1") == NapoleonicFormationType.SQUARE

    def test_mid_transition(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        engine.update(1.0)
        assert engine.is_transitioning("u1") is True

    def test_rejected_during(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.order_formation_change("u1", NapoleonicFormationType.COLUMN)
        assert engine.order_formation_change("u1", NapoleonicFormationType.SKIRMISH) == 0.0

    def test_update_returns_completed(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.set_formation("u2", NapoleonicFormationType.COLUMN)
        engine.order_formation_change("u1", NapoleonicFormationType.SKIRMISH)
        completed = engine.update(1000.0)
        assert "u1" in completed
        assert "u2" not in completed


# ===================================================================
# Modifiers
# ===================================================================


class TestNapoleonicModifiers:
    """Formation combat modifiers."""

    def test_line_firepower(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        assert engine.firepower_fraction("u1") == pytest.approx(1.0)

    def test_column_firepower(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.COLUMN)
        assert engine.firepower_fraction("u1") == pytest.approx(0.3)

    def test_square_cavalry_vulnerability(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        assert engine.cavalry_vulnerability("u1") == pytest.approx(0.1)

    def test_skirmish_artillery_vulnerability(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.SKIRMISH)
        assert engine.artillery_vulnerability("u1") == pytest.approx(0.3)

    def test_speed_multipliers(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.COLUMN)
        assert engine.speed_multiplier("u1") == pytest.approx(0.9)
        engine.set_formation("u2", NapoleonicFormationType.SQUARE)
        assert engine.speed_multiplier("u2") == pytest.approx(0.3)

    def test_worst_of_both_during_transition(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.order_formation_change("u1", NapoleonicFormationType.SQUARE)
        # Firepower: min(1.0, 0.25) = 0.25 (worst for beneficial)
        assert engine.firepower_fraction("u1") == pytest.approx(0.25)
        # Cav vuln: max(1.0, 0.1) = 1.0 (worst for vulnerability)
        assert engine.cavalry_vulnerability("u1") == pytest.approx(1.0)

    def test_square_firepower(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        assert engine.firepower_fraction("u1") == pytest.approx(0.25)


# ===================================================================
# State persistence
# ===================================================================


class TestNapoleonicState:
    """Checkpoint roundtrip."""

    def test_roundtrip(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.SQUARE)
        state = engine.get_state()
        engine2 = NapoleonicFormationEngine()
        engine2.set_state(state)
        assert engine2.get_formation("u1") == NapoleonicFormationType.SQUARE

    def test_transition_preserved(self):
        engine = NapoleonicFormationEngine()
        engine.set_formation("u1", NapoleonicFormationType.LINE)
        engine.order_formation_change("u1", NapoleonicFormationType.COLUMN)
        engine.update(5.0)
        state = engine.get_state()
        engine2 = NapoleonicFormationEngine()
        engine2.set_state(state)
        assert engine2.is_transitioning("u1") is True

    def test_multiple_units(self):
        engine = NapoleonicFormationEngine()
        for ft in NapoleonicFormationType:
            engine.set_formation(f"u_{ft.name}", ft)
        state = engine.get_state()
        assert len(state["states"]) == 4

    def test_empty(self):
        engine = NapoleonicFormationEngine()
        state = engine.get_state()
        engine2 = NapoleonicFormationEngine()
        engine2.set_state(state)
        assert len(engine2._states) == 0

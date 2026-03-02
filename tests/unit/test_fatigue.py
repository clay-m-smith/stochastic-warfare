"""Tests for movement/fatigue.py."""

import pytest

from stochastic_warfare.movement.fatigue import FatigueConfig, FatigueManager


class TestFatigueAccumulate:
    def test_march_increases_physical(self) -> None:
        mgr = FatigueManager()
        s = mgr.accumulate("u1", 2.0, "march")
        assert s.physical > 0.0

    def test_combat_more_than_march(self) -> None:
        mgr = FatigueManager()
        s_march = mgr.accumulate("u1", 2.0, "march")
        mgr2 = FatigueManager()
        s_combat = mgr2.accumulate("u2", 2.0, "combat")
        assert s_combat.physical > s_march.physical

    def test_idle_minimal(self) -> None:
        mgr = FatigueManager()
        s = mgr.accumulate("u1", 2.0, "idle")
        assert s.physical < 0.1  # very small

    def test_accumulates_over_time(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 4.0, "march")
        s = mgr.accumulate("u1", 4.0, "march")
        assert s.physical > 0.3

    def test_capped_at_one(self) -> None:
        mgr = FatigueManager()
        s = mgr.accumulate("u1", 100.0, "march")
        assert s.physical <= 1.0
        assert s.mental <= 1.0

    def test_altitude_penalty(self) -> None:
        mgr = FatigueManager()
        s_low = mgr.accumulate("u1", 4.0, "march", altitude=500.0)
        mgr2 = FatigueManager()
        s_high = mgr2.accumulate("u2", 4.0, "march", altitude=4000.0)
        assert s_high.physical > s_low.physical

    def test_hours_since_rest_tracks(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 3.0, "march")
        s = mgr.accumulate("u1", 5.0, "march")
        assert s.hours_since_rest == 8.0


class TestFatigueRest:
    def test_rest_reduces_fatigue(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 8.0, "march")
        s = mgr.rest("u1", 8.0)
        assert s.physical < 0.64  # started high, came down

    def test_rest_floors_at_zero(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 1.0, "march")
        s = mgr.rest("u1", 100.0)
        assert s.physical >= 0.0
        assert s.mental >= 0.0

    def test_rest_resets_hours_counter(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 8.0, "march")
        s = mgr.rest("u1", 4.0)
        assert s.hours_since_rest == 0.0


class TestSpeedModifier:
    def test_fresh_is_one(self) -> None:
        mgr = FatigueManager()
        assert mgr.speed_modifier("u1") == 1.0

    def test_tired_reduces(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 10.0, "march")
        mod = mgr.speed_modifier("u1")
        assert 0.4 < mod < 1.0


class TestAccuracyModifier:
    def test_fresh_is_one(self) -> None:
        mgr = FatigueManager()
        assert mgr.accuracy_modifier("u1") == 1.0

    def test_tired_reduces(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 10.0, "combat")
        mod = mgr.accuracy_modifier("u1")
        assert 0.5 < mod < 1.0


class TestFatigueState:
    def test_roundtrip(self) -> None:
        mgr = FatigueManager()
        mgr.accumulate("u1", 5.0, "march")
        mgr.accumulate("u2", 3.0, "combat")

        state = mgr.get_state()
        restored = FatigueManager()
        restored.set_state(state)

        assert restored.get_fatigue("u1") == mgr.get_fatigue("u1")
        assert restored.get_fatigue("u2") == mgr.get_fatigue("u2")

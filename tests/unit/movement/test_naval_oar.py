"""Unit tests for NavalOarEngine — galley propulsion, fatigue, combat.

Phase 75c: Tests rowing speeds, fatigue, ramming, boarding, state persistence.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.movement.naval_oar import (
    GalleyConfig,
    NavalOarEngine,
    RowingSpeed,
)

from .conftest import _rng


# ===================================================================
# Galley propulsion
# ===================================================================


class TestGalleyPropulsion:
    """Speed settings and base speed calculation."""

    def test_register_and_set(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.CRUISE)
        assert engine.get_speed("g1") == pytest.approx(2.5)

    def test_cruise_speed(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.CRUISE)
        assert engine.get_speed("g1") == pytest.approx(2.5)

    def test_battle_speed(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.BATTLE)
        assert engine.get_speed("g1") == pytest.approx(4.0)

    def test_ramming_speed(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.RAMMING)
        assert engine.get_speed("g1") == pytest.approx(6.0)

    def test_rest_speed_zero(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.REST)
        assert engine.get_speed("g1") == 0.0

    def test_unregistered_zero(self):
        engine = NavalOarEngine(rng=_rng())
        assert engine.get_speed("nonexistent") == 0.0


# ===================================================================
# Fatigue model
# ===================================================================


class TestGalleyFatigue:
    """Fatigue accumulation and exhaustion."""

    def test_cruise_slow_fatigue(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.CRUISE)
        engine.update(60.0)
        assert engine.get_fatigue("g1") == pytest.approx(0.005 * 60.0, rel=0.01)

    def test_battle_moderate_fatigue(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.BATTLE)
        engine.update(10.0)
        assert engine.get_fatigue("g1") == pytest.approx(0.02 * 10.0, rel=0.01)

    def test_ramming_fast_fatigue(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.RAMMING)
        engine.update(10.0)
        assert engine.get_fatigue("g1") == pytest.approx(0.05 * 10.0, rel=0.01)

    def test_rest_recovery(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.BATTLE)
        engine.update(20.0)  # accumulate fatigue
        fatigue_before = engine.get_fatigue("g1")
        engine.set_speed("g1", RowingSpeed.REST)
        engine.update(10.0)  # recover
        assert engine.get_fatigue("g1") < fatigue_before

    def test_exhaustion_halves_speed(self):
        cfg = GalleyConfig(exhaustion_threshold=0.1)
        engine = NavalOarEngine(config=cfg, rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.RAMMING)
        engine.update(10.0)  # fatigue > 0.1
        speed = engine.get_speed("g1")
        assert speed == pytest.approx(6.0 * 0.5)  # exhaustion penalty


# ===================================================================
# Combat — ramming and boarding
# ===================================================================


class TestGalleyCombat:
    """Ramming damage and boarding mechanics."""

    def test_ram_damage(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.RAMMING)
        damage = engine.compute_ram_damage("g1")
        # base(100) + factor(20) * speed(6) = 220
        assert damage == pytest.approx(220.0)

    def test_ram_override_speed(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        damage = engine.compute_ram_damage("g1", approach_speed=10.0)
        assert damage == pytest.approx(100.0 + 20.0 * 10.0)

    def test_boarding_initiation(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.BATTLE)
        time_s = engine.initiate_boarding("g1", "t1")
        assert time_s == pytest.approx(30.0)
        assert engine.is_boarding("g1") is True
        # Should set speed to REST
        assert engine.get_speed("g1") == 0.0

    def test_boarding_completes(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.initiate_boarding("g1", "t1")
        engine.update(31.0)  # boarding_transition_time_s = 30
        assert engine.is_boarding("g1") is False


# ===================================================================
# State persistence
# ===================================================================


class TestGalleyState:
    """Checkpoint roundtrip."""

    def test_roundtrip(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.set_speed("g1", RowingSpeed.BATTLE)
        engine.update(10.0)
        state = engine.get_state()
        engine2 = NavalOarEngine(rng=_rng())
        engine2.set_state(state)
        assert engine2.get_fatigue("g1") == pytest.approx(engine.get_fatigue("g1"))

    def test_boarding_preserved(self):
        engine = NavalOarEngine(rng=_rng())
        engine.register_vessel("g1")
        engine.initiate_boarding("g1", "t1")
        state = engine.get_state()
        engine2 = NavalOarEngine(rng=_rng())
        engine2.set_state(state)
        assert engine2.is_boarding("g1") is True

    def test_empty_valid(self):
        engine = NavalOarEngine(rng=_rng())
        state = engine.get_state()
        engine2 = NavalOarEngine(rng=_rng())
        engine2.set_state(state)
        assert len(engine2._galleys) == 0

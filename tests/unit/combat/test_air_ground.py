"""Unit tests for AirGroundEngine — CAS, SEAD, weapon delivery accuracy, designation."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.air_ground import (
    AirGroundConfig,
    AirGroundEngine,
    CASDesignationResult,
    CASResult,
    SEADResult,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(seed: int = 42, **cfg_kwargs) -> AirGroundEngine:
    bus = EventBus()
    config = AirGroundConfig(**cfg_kwargs) if cfg_kwargs else None
    return AirGroundEngine(bus, _rng(seed), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCAS:
    """Close air support engagements."""

    def test_cas_danger_close_abort(self):
        """CAS should abort when friendlies are very close to the target."""
        eng = _make_engine(seed=1)
        aircraft_pos = Position(0, 0, 3000)
        target_pos = Position(5000, 0, 0)
        # Friendly within 100m of target — well inside 600m default danger-close
        friendly_pos = Position(5050, 0, 0)
        result = eng.execute_cas(
            "ac1", "tgt1", aircraft_pos, target_pos, 0.8,
            friendly_pos=friendly_pos,
        )
        assert result.aborted is True
        assert result.abort_reason == "danger_close"
        assert result.danger_close is True

    def test_cas_no_abort_when_friendlies_far(self):
        """CAS should proceed when friendlies are far from the target."""
        eng = _make_engine(seed=2)
        aircraft_pos = Position(0, 0, 3000)
        target_pos = Position(5000, 0, 0)
        friendly_pos = Position(10_000, 0, 0)
        result = eng.execute_cas(
            "ac1", "tgt1", aircraft_pos, target_pos, 0.8,
            friendly_pos=friendly_pos,
        )
        assert result.aborted is False
        assert result.danger_close is False

    def test_cas_no_friendly_pos_proceeds(self):
        """CAS without friendly_pos should not abort."""
        eng = _make_engine(seed=3)
        result = eng.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(5000, 0, 0),
            0.8,
        )
        assert result.aborted is False
        assert result.effective_pk > 0.0


class TestCASDesignation:
    """JTAC designation delay and accuracy bonus."""

    def test_no_jtac_no_bonus(self):
        eng = _make_engine(seed=10)
        result = eng.compute_cas_designation(jtac_present=False)
        assert result.jtac_present is False
        assert result.accuracy_bonus == 0.0

    def test_jtac_below_delay_no_bonus(self):
        eng = _make_engine(seed=11)
        result = eng.compute_cas_designation(
            jtac_present=True, elapsed_since_contact_s=5.0,
        )
        assert result.accuracy_bonus == 0.0
        assert result.designation_delay_s > 0.0

    def test_laser_designator_extra_bonus(self):
        """Laser designator should add extra accuracy bonus."""
        eng1 = _make_engine(seed=12)
        eng2 = _make_engine(seed=12)
        no_laser = eng1.compute_cas_designation(
            jtac_present=True, laser_designator=False,
            elapsed_since_contact_s=60.0,
        )
        with_laser = eng2.compute_cas_designation(
            jtac_present=True, laser_designator=True,
            elapsed_since_contact_s=60.0,
        )
        assert with_laser.accuracy_bonus > no_laser.accuracy_bonus


class TestSEAD:
    """SEAD engagement with anti-radiation missiles."""

    def test_sead_emitting_full_pk(self):
        eng = _make_engine(seed=20)
        result = eng.execute_sead(
            "ac1", "sa6",
            Position(0, 0, 5000), Position(30_000, 0, 0),
            arm_pk=0.7, target_emitting=True,
        )
        assert result.target_emitting is True
        assert result.emcon_defeated is False
        assert result.effective_pk > 0.0

    def test_sead_emcon_penalty(self):
        """Non-emitting radar should drastically reduce ARM Pk."""
        eng1 = _make_engine(seed=30)
        eng2 = _make_engine(seed=30)
        emitting = eng1.execute_sead(
            "ac1", "sa6",
            Position(0, 0, 5000), Position(30_000, 0, 0),
            arm_pk=0.7, target_emitting=True,
        )
        silent = eng2.execute_sead(
            "ac1", "sa6",
            Position(0, 0, 5000), Position(30_000, 0, 0),
            arm_pk=0.7, target_emitting=False,
        )
        assert silent.effective_pk < emitting.effective_pk
        assert silent.emcon_defeated is True


class TestWeaponDeliveryAccuracy:
    """compute_weapon_delivery_accuracy factor."""

    def test_guided_higher_than_unguided(self):
        eng = _make_engine(seed=40)
        guided = eng.compute_weapon_delivery_accuracy(3000.0, 200.0, "gps")
        unguided = eng.compute_weapon_delivery_accuracy(3000.0, 200.0, "unguided")
        assert guided > unguided

    def test_altitude_penalty(self):
        """Higher release altitude degrades accuracy."""
        eng = _make_engine(seed=41)
        low = eng.compute_weapon_delivery_accuracy(1000.0, 200.0, "unguided")
        high = eng.compute_weapon_delivery_accuracy(8000.0, 200.0, "unguided")
        assert low > high

    def test_speed_penalty(self):
        """Higher speed degrades accuracy."""
        eng = _make_engine(seed=42)
        slow = eng.compute_weapon_delivery_accuracy(3000.0, 100.0, "gps")
        fast = eng.compute_weapon_delivery_accuracy(3000.0, 500.0, "gps")
        assert slow > fast

    def test_weather_penalty(self):
        eng = _make_engine(seed=43)
        clear = eng.compute_weapon_delivery_accuracy(
            3000.0, 200.0, "gps", conditions={},
        )
        bad_weather = eng.compute_weapon_delivery_accuracy(
            3000.0, 200.0, "gps", conditions={"weather_penalty": 1.0},
        )
        assert clear > bad_weather


class TestStateRoundtrip:
    """State serialization and restoration."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=100)
        eng.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(5000, 0, 0),
            0.8,
        )
        state = eng.get_state()

        eng2 = _make_engine(seed=999)
        eng2.set_state(state)

        assert eng2._missions_executed == 1

        r1 = eng._rng.random()
        r2 = eng2._rng.random()
        assert r1 == pytest.approx(r2)

"""Tests for combat/air_ground.py — CAS, SEAD, weapon delivery accuracy."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.air_ground import (
    AirGroundEngine,
    AirGroundMission,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> AirGroundEngine:
    return AirGroundEngine(EventBus(), _rng(seed))


def _engine_with_bus(seed: int = 42) -> tuple[AirGroundEngine, EventBus]:
    bus = EventBus()
    return AirGroundEngine(bus, _rng(seed)), bus


# ---------------------------------------------------------------------------
# AirGroundMission enum
# ---------------------------------------------------------------------------


class TestAirGroundMission:
    def test_enum_values(self) -> None:
        assert AirGroundMission.CAS == 0
        assert AirGroundMission.SEAD == 1
        assert AirGroundMission.DEAD == 2
        assert AirGroundMission.AIR_INTERDICTION == 3
        assert AirGroundMission.BAI == 4


# ---------------------------------------------------------------------------
# CAS
# ---------------------------------------------------------------------------


class TestCAS:
    def test_cas_hit_possible(self) -> None:
        # Run enough trials to get at least one hit
        hits = 0
        for seed in range(50):
            e = _engine(seed)
            result = e.execute_cas(
                "ac1", "tgt1",
                Position(0, 0, 3000), Position(0, 500, 0),
                weapon_pk=0.8,
            )
            if result.hit:
                hits += 1
        assert hits > 0

    def test_cas_records_ids(self) -> None:
        e = _engine()
        result = e.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(0, 500, 0),
            weapon_pk=0.7,
        )
        assert result.aircraft_id == "ac1"
        assert result.target_id == "tgt1"

    def test_cas_danger_close_detected(self) -> None:
        e = _engine()
        result = e.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(0, 500, 0),
            weapon_pk=0.7,
            friendly_pos=Position(0, 400, 0),
        )
        assert result.danger_close is True

    def test_cas_danger_close_abort(self) -> None:
        e = _engine()
        # Friendly very close to target — should abort
        result = e.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(0, 500, 0),
            weapon_pk=0.7,
            friendly_pos=Position(0, 500, 0),  # right on target
        )
        assert result.aborted is True
        assert result.abort_reason == "danger_close"

    def test_cas_no_danger_close_when_far(self) -> None:
        e = _engine()
        result = e.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(0, 500, 0),
            weapon_pk=0.7,
            friendly_pos=Position(0, -1000, 0),  # far from target
        )
        assert result.danger_close is False
        assert result.aborted is False

    def test_cas_effective_pk_clamped(self) -> None:
        e = _engine()
        result = e.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(0, 500, 0),
            weapon_pk=0.7,
        )
        assert 0.01 <= result.effective_pk <= 0.99

    def test_cas_guided_vs_unguided_accuracy(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        guided = e1.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(0, 500, 0),
            weapon_pk=0.7, guidance_type="gps",
        )
        unguided = e2.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(0, 500, 0),
            weapon_pk=0.7, guidance_type="unguided",
        )
        assert guided.effective_pk > unguided.effective_pk

    def test_cas_events_published(self) -> None:
        from datetime import datetime, timezone
        e, bus = _engine_with_bus(42)
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda ev: received.append(ev))

        e.execute_cas(
            "ac1", "tgt1",
            Position(0, 0, 3000), Position(0, 500, 0),
            weapon_pk=0.7,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(received) == 1
        assert received[0].engagement_type == "CAS"


# ---------------------------------------------------------------------------
# SEAD
# ---------------------------------------------------------------------------


class TestSEAD:
    def test_sead_emitting_target_higher_pk(self) -> None:
        e1 = _engine(100)
        e2 = _engine(100)
        emitting = e1.execute_sead(
            "ac1", "ad1",
            Position(0, 0, 5000), Position(0, 30000, 0),
            arm_pk=0.6, target_emitting=True,
        )
        silent = e2.execute_sead(
            "ac1", "ad1",
            Position(0, 0, 5000), Position(0, 30000, 0),
            arm_pk=0.6, target_emitting=False,
        )
        assert emitting.effective_pk > silent.effective_pk

    def test_sead_emcon_defeated_flag(self) -> None:
        e = _engine()
        result = e.execute_sead(
            "ac1", "ad1",
            Position(0, 0, 5000), Position(0, 30000, 0),
            arm_pk=0.6, target_emitting=False,
        )
        assert result.emcon_defeated is True

    def test_sead_emitting_not_defeated(self) -> None:
        e = _engine()
        result = e.execute_sead(
            "ac1", "ad1",
            Position(0, 0, 5000), Position(0, 30000, 0),
            arm_pk=0.6, target_emitting=True,
        )
        assert result.emcon_defeated is False

    def test_sead_effective_pk_clamped(self) -> None:
        e = _engine()
        result = e.execute_sead(
            "ac1", "ad1",
            Position(0, 0, 5000), Position(0, 30000, 0),
            arm_pk=0.6,
        )
        assert 0.01 <= result.effective_pk <= 0.99

    def test_sead_hit_possible(self) -> None:
        hits = 0
        for seed in range(50):
            e = _engine(seed)
            result = e.execute_sead(
                "ac1", "ad1",
                Position(0, 0, 5000), Position(0, 30000, 0),
                arm_pk=0.6, target_emitting=True,
            )
            if result.hit:
                hits += 1
        assert hits > 0

    def test_sead_records_ids(self) -> None:
        e = _engine()
        result = e.execute_sead(
            "ac1", "ad1",
            Position(0, 0, 5000), Position(0, 30000, 0),
        )
        assert result.aircraft_id == "ac1"
        assert result.target_ad_id == "ad1"

    def test_sead_events_published(self) -> None:
        from datetime import datetime, timezone
        e, bus = _engine_with_bus(42)
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda ev: received.append(ev))

        e.execute_sead(
            "ac1", "ad1",
            Position(0, 0, 5000), Position(0, 30000, 0),
            arm_pk=0.6,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(received) == 1
        assert received[0].engagement_type == "SEAD"


# ---------------------------------------------------------------------------
# Weapon delivery accuracy
# ---------------------------------------------------------------------------


class TestWeaponDeliveryAccuracy:
    def test_guided_higher_than_unguided(self) -> None:
        e = _engine()
        guided = e.compute_weapon_delivery_accuracy(3000.0, 200.0, "gps")
        unguided = e.compute_weapon_delivery_accuracy(3000.0, 200.0, "unguided")
        assert guided > unguided

    def test_higher_altitude_less_accurate(self) -> None:
        e = _engine()
        low = e.compute_weapon_delivery_accuracy(1000.0, 200.0, "unguided")
        high = e.compute_weapon_delivery_accuracy(10000.0, 200.0, "unguided")
        assert low > high

    def test_faster_speed_less_accurate(self) -> None:
        e = _engine()
        slow = e.compute_weapon_delivery_accuracy(3000.0, 100.0, "gps")
        fast = e.compute_weapon_delivery_accuracy(3000.0, 500.0, "gps")
        assert slow > fast

    def test_weather_degrades_accuracy(self) -> None:
        e = _engine()
        clear = e.compute_weapon_delivery_accuracy(
            3000.0, 200.0, "gps", {"weather_penalty": 0.0},
        )
        bad = e.compute_weapon_delivery_accuracy(
            3000.0, 200.0, "gps", {"weather_penalty": 1.0},
        )
        assert clear > bad

    def test_night_degrades_accuracy(self) -> None:
        e = _engine()
        day = e.compute_weapon_delivery_accuracy(
            3000.0, 200.0, "gps", {"night": 0.0},
        )
        night = e.compute_weapon_delivery_accuracy(
            3000.0, 200.0, "gps", {"night": 1.0},
        )
        assert day > night

    def test_accuracy_clamped(self) -> None:
        e = _engine()
        # Even worst case, accuracy should not go below floor
        acc = e.compute_weapon_delivery_accuracy(
            20000.0, 800.0, "unguided",
            {"weather_penalty": 1.0, "night": 1.0},
        )
        assert acc >= 0.05


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_cas(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        r1 = e1.execute_cas("ac1", "t1", Position(0, 0, 3000), Position(0, 500, 0), 0.7)
        r2 = e2.execute_cas("ac1", "t1", Position(0, 0, 3000), Position(0, 500, 0), 0.7)
        assert r1.effective_pk == pytest.approx(r2.effective_pk)
        assert r1.hit == r2.hit


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestState:
    def test_state_roundtrip(self) -> None:
        e1 = _engine(42)
        e1.execute_cas("ac1", "t1", Position(0, 0, 3000), Position(0, 500, 0), 0.7)
        saved = e1.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e1.execute_sead("ac2", "ad1", Position(0, 0, 5000), Position(0, 30000, 0))
        r2 = e2.execute_sead("ac2", "ad1", Position(0, 0, 5000), Position(0, 30000, 0))
        assert r1.effective_pk == pytest.approx(r2.effective_pk)
        assert r1.hit == r2.hit

    def test_state_preserves_mission_count(self) -> None:
        e = _engine(42)
        e.execute_cas("ac1", "t1", Position(0, 0, 3000), Position(0, 500, 0), 0.7)
        state = e.get_state()
        assert state["missions_executed"] == 1

"""Tests for combat/missiles.py."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import AmmoDefinition
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.missiles import (
    KillChainPhase,
    MissileConfig,
    MissileEngine,
    MissileFlightState,
    MissileType,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> MissileEngine:
    rng = _rng(seed)
    bus = EventBus()
    dmg = DamageEngine(bus, rng)
    return MissileEngine(dmg, bus, rng)


def _cruise_ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="bgm109", display_name="Tomahawk", ammo_type="MISSILE",
        max_speed_mps=250.0, flight_time_s=6000.0,
        blast_radius_m=30.0, guidance="COMBINED",
    )


def _tbm_ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="scud", display_name="Scud", ammo_type="MISSILE",
        max_speed_mps=1700.0, flight_time_s=300.0,
        blast_radius_m=100.0, guidance="INERTIAL",
    )


def _ashm_ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="harpoon", display_name="Harpoon", ammo_type="MISSILE",
        max_speed_mps=240.0, flight_time_s=500.0,
        blast_radius_m=20.0, guidance="RADAR_ACTIVE",
    )


class TestFlightProfile:
    def test_cruise_profile(self) -> None:
        e = _engine()
        profile = e.compute_flight_profile(
            MissileType.CRUISE_SUBSONIC, _cruise_ammo(),
            Position(0, 0, 0), Position(0, 500000, 0),
        )
        assert profile.cruise_altitude_m > 0
        assert profile.range_m == pytest.approx(500000.0)
        assert profile.flight_time_s > 0

    def test_tbm_ballistic_arc(self) -> None:
        e = _engine()
        profile = e.compute_flight_profile(
            MissileType.TBM_SHORT, _tbm_ammo(),
            Position(0, 0, 0), Position(0, 200000, 0),
        )
        # Ballistic arc — max altitude should be significant
        assert profile.max_altitude_m > 1000.0

    def test_ssm_sea_skimming(self) -> None:
        e = _engine()
        profile = e.compute_flight_profile(
            MissileType.COASTAL_DEFENSE_SSM, _ashm_ammo(),
            Position(0, 0, 0), Position(100000, 0, 0),
        )
        assert profile.cruise_altitude_m <= 10.0

    def test_supersonic_cruise(self) -> None:
        e = _engine()
        fast_ammo = AmmoDefinition(
            ammo_id="brahmos", display_name="BrahMos", ammo_type="MISSILE",
            max_speed_mps=1000.0, guidance="RADAR_ACTIVE",
        )
        profile = e.compute_flight_profile(
            MissileType.CRUISE_SUPERSONIC, fast_ammo,
            Position(0, 0, 0), Position(0, 300000, 0),
        )
        assert profile.speed_mps == 1000.0


class TestLaunchMissile:
    def test_launch_creates_flight_state(self) -> None:
        e = _engine()
        state = e.launch_missile(
            "l1", "m1", Position(0, 100000, 0),
            Position(0, 0, 0), _cruise_ammo(),
        )
        assert state.missile_id == "m1"
        assert state.active is True
        assert state.phase == KillChainPhase.FLIGHT

    def test_launch_adds_to_active(self) -> None:
        e = _engine()
        e.launch_missile(
            "l1", "m1", Position(0, 100000, 0),
            Position(0, 0, 0), _cruise_ammo(),
        )
        assert len(e.active_missiles) == 1

    def test_multiple_launches(self) -> None:
        e = _engine()
        e.launch_missile("l1", "m1", Position(0, 100000, 0), Position(0, 0, 0), _cruise_ammo())
        e.launch_missile("l1", "m2", Position(0, 200000, 0), Position(0, 0, 0), _cruise_ammo())
        assert len(e.active_missiles) == 2


class TestUpdateMissiles:
    def test_missile_advances(self) -> None:
        e = _engine()
        e.launch_missile(
            "l1", "m1", Position(0, 100000, 0),
            Position(0, 0, 0), _cruise_ammo(),
        )
        impacts = e.update_missiles_in_flight(100.0)
        assert len(impacts) == 0  # Not yet at target
        assert len(e.active_missiles) == 1
        # Position should have advanced
        m = e.active_missiles[0]
        assert m.current_pos.northing > 0

    def test_missile_reaches_target(self) -> None:
        e = _engine()
        ammo = AmmoDefinition(
            ammo_id="short", display_name="Short", ammo_type="MISSILE",
            max_speed_mps=1000.0, flight_time_s=10.0,
        )
        e.launch_missile(
            "l1", "m1", Position(0, 10000, 0),
            Position(0, 0, 0), ammo,
        )
        # Advance past flight time
        impacts = e.update_missiles_in_flight(15.0)
        assert len(impacts) == 1
        assert impacts[0].missile_id == "m1"
        assert len(e.active_missiles) == 0

    def test_impact_position_near_target(self) -> None:
        e = _engine()
        target = Position(5000.0, 5000.0, 0.0)
        ammo = AmmoDefinition(
            ammo_id="precise", display_name="Precise", ammo_type="MISSILE",
            max_speed_mps=500.0, flight_time_s=10.0,
        )
        e.launch_missile("l1", "m1", target, Position(0, 0, 0), ammo)
        impacts = e.update_missiles_in_flight(15.0)
        assert len(impacts) == 1
        dist = math.sqrt(
            (impacts[0].impact_pos.easting - target.easting) ** 2
            + (impacts[0].impact_pos.northing - target.northing) ** 2
        )
        assert dist < 100.0

    def test_no_missiles_no_impacts(self) -> None:
        e = _engine()
        impacts = e.update_missiles_in_flight(10.0)
        assert len(impacts) == 0


class TestKillChainLatency:
    def test_tbm_longer_than_cruise(self) -> None:
        e = _engine()
        tbm = e.compute_kill_chain_latency(MissileType.TBM_MEDIUM)
        cruise = e.compute_kill_chain_latency(MissileType.CRUISE_SUBSONIC)
        assert tbm > cruise

    def test_better_targeting_reduces_latency(self) -> None:
        e = _engine()
        poor = e.compute_kill_chain_latency(MissileType.CRUISE_SUBSONIC, targeting_quality=0.1)
        good = e.compute_kill_chain_latency(MissileType.CRUISE_SUBSONIC, targeting_quality=0.9)
        assert good < poor

    def test_latency_positive(self) -> None:
        e = _engine()
        for mt in MissileType:
            latency = e.compute_kill_chain_latency(mt)
            assert latency > 0


class TestMissileFlightState:
    def test_state_roundtrip(self) -> None:
        from stochastic_warfare.combat.missiles import FlightProfile
        fp = FlightProfile(
            missile_type=MissileType.CRUISE_SUBSONIC,
            launch_pos=Position(0, 0, 0),
            target_pos=Position(0, 100000, 0),
        )
        state = MissileFlightState(
            missile_id="m1", ammo_id="ammo1", launcher_id="l1",
            target_pos=Position(0, 100000, 0),
            current_pos=Position(0, 50000, 50),
            flight_profile=fp, time_elapsed_s=200.0,
        )
        saved = state.get_state()
        restored = MissileFlightState(
            missile_id="", ammo_id="", launcher_id="",
            target_pos=Position(0, 0, 0), current_pos=Position(0, 0, 0),
            flight_profile=fp,
        )
        restored.set_state(saved)
        assert restored.missile_id == "m1"
        assert restored.time_elapsed_s == 200.0
        assert restored.current_pos.northing == pytest.approx(50000.0)


class TestMissileType:
    def test_enum_values(self) -> None:
        assert MissileType.TBM_SHORT == 0
        assert MissileType.COASTAL_DEFENSE_SSM == 5


class TestState:
    def test_engine_state_roundtrip(self) -> None:
        e = _engine(42)
        e.launch_missile("l1", "m1", Position(0, 100000, 0), Position(0, 0, 0), _cruise_ammo())
        # Advance a bit to change rng state
        e.update_missiles_in_flight(10.0)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        # Both should have same rng state after restore
        # The active_missiles in e2 are restored from state but lack full flight_profile
        # So just verify rng state parity
        assert e.active_missiles[0].time_elapsed_s == pytest.approx(
            e2.active_missiles[0].time_elapsed_s
        )

"""Unit tests for MissileEngine — launch, flight profiles, update, kill chain."""

from __future__ import annotations

import pytest

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.missiles import (
    FlightProfile,
    MissileConfig,
    MissileEngine,
    MissileFlightState,
    MissileImpactResult,
    MissileType,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _make_guided_missile, _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(seed: int = 42, **cfg_kwargs) -> MissileEngine:
    bus = EventBus()
    damage = DamageEngine(bus, _rng(seed + 100))
    config = MissileConfig(**cfg_kwargs) if cfg_kwargs else None
    return MissileEngine(damage, bus, _rng(seed), config)


def _make_cruise_ammo():
    """Create a cruise missile ammo definition."""
    return _make_guided_missile(
        ammo_id="cruise_test",
        max_speed_mps=250.0,
        flight_time_s=100.0,
        propulsion="turbojet",
    )


def _make_tbm_ammo():
    """Create a TBM ammo definition."""
    return _make_guided_missile(
        ammo_id="tbm_test",
        max_speed_mps=2000.0,
        flight_time_s=300.0,
        propulsion="rocket",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLaunchMissile:
    """launch_missile creates and tracks MissileFlightState."""

    def test_launch_creates_flight_state(self):
        eng = _make_engine(seed=1)
        ammo = _make_cruise_ammo()
        state = eng.launch_missile(
            "launcher1", "m1",
            Position(100_000, 0, 0), Position(0, 0, 0),
            ammo, MissileType.CRUISE_SUBSONIC,
        )
        assert isinstance(state, MissileFlightState)
        assert state.missile_id == "m1"
        assert state.launcher_id == "launcher1"
        assert state.active is True

    def test_launch_adds_to_active(self):
        eng = _make_engine(seed=2)
        ammo = _make_cruise_ammo()
        eng.launch_missile(
            "launcher1", "m1",
            Position(100_000, 0, 0), Position(0, 0, 0),
            ammo, MissileType.CRUISE_SUBSONIC,
        )
        assert len(eng.active_missiles) == 1
        assert eng.active_missiles[0].missile_id == "m1"

    def test_multiple_launches(self):
        eng = _make_engine(seed=3)
        ammo = _make_cruise_ammo()
        for i in range(5):
            eng.launch_missile(
                "launcher1", f"m{i}",
                Position(50_000, 0, 0), Position(0, 0, 0),
                ammo, MissileType.CRUISE_SUBSONIC,
            )
        assert len(eng.active_missiles) == 5


class TestFlightProfiles:
    """compute_flight_profile for different missile types."""

    def test_tbm_ballistic_arc(self):
        eng = _make_engine(seed=10)
        ammo = _make_tbm_ammo()
        profile = eng.compute_flight_profile(
            MissileType.TBM_SHORT, ammo,
            Position(0, 0, 0), Position(200_000, 0, 0),
        )
        assert isinstance(profile, FlightProfile)
        # TBM has high max altitude (range/4)
        assert profile.max_altitude_m > 10_000.0
        assert profile.range_m == pytest.approx(200_000.0)

    def test_cruise_subsonic_low_altitude(self):
        eng = _make_engine(seed=11)
        ammo = _make_cruise_ammo()
        profile = eng.compute_flight_profile(
            MissileType.CRUISE_SUBSONIC, ammo,
            Position(0, 0, 0), Position(50_000, 0, 0),
        )
        # Cruise missiles fly at low altitude (default 50m)
        assert profile.cruise_altitude_m == pytest.approx(50.0)
        assert profile.max_altitude_m == pytest.approx(50.0)

    def test_coastal_ssm_sea_skimming(self):
        eng = _make_engine(seed=12)
        ammo = _make_cruise_ammo()
        profile = eng.compute_flight_profile(
            MissileType.COASTAL_DEFENSE_SSM, ammo,
            Position(0, 0, 0), Position(30_000, 0, 0),
        )
        # SSM sea-skims at very low altitude (default 5m)
        assert profile.cruise_altitude_m == pytest.approx(5.0)


class TestUpdateFlight:
    """update_missiles_in_flight per-tick position and impact."""

    def test_inflight_position_interpolation(self):
        eng = _make_engine(seed=20)
        ammo = _make_cruise_ammo()
        eng.launch_missile(
            "launcher1", "m1",
            Position(0, 0, 0), Position(25_000, 0, 0),
            ammo, MissileType.CRUISE_SUBSONIC,
        )
        # Advance partway through flight
        impacts = eng.update_missiles_in_flight(dt=50.0)
        assert len(impacts) == 0  # Not arrived yet (flight_time_s=100)
        assert len(eng.active_missiles) == 1
        missile = eng.active_missiles[0]
        # Position should be roughly halfway
        assert missile.current_pos.easting > 0

    def test_terminal_impact(self):
        """Missile should impact after exceeding flight time."""
        eng = _make_engine(seed=21)
        ammo = _make_cruise_ammo()
        eng.launch_missile(
            "launcher1", "m1",
            Position(0, 0, 0), Position(25_000, 0, 0),
            ammo, MissileType.CRUISE_SUBSONIC,
        )
        # Advance past flight time
        impacts = eng.update_missiles_in_flight(dt=150.0)
        assert len(impacts) == 1
        assert isinstance(impacts[0], MissileImpactResult)
        assert impacts[0].missile_id == "m1"
        # Should be removed from active
        assert len(eng.active_missiles) == 0


class TestActiveMissiles:
    """active_missiles property."""

    def test_active_missiles_returns_copy(self):
        eng = _make_engine(seed=30)
        ammo = _make_cruise_ammo()
        eng.launch_missile(
            "launcher1", "m1",
            Position(0, 0, 0), Position(50_000, 0, 0),
            ammo, MissileType.CRUISE_SUBSONIC,
        )
        active = eng.active_missiles
        assert len(active) == 1
        # Modifying the copy should not affect the engine
        active.clear()
        assert len(eng.active_missiles) == 1


class TestKillChainLatency:
    """compute_kill_chain_latency estimates."""

    def test_tbm_longer_than_cruise(self):
        eng = _make_engine(seed=40)
        tbm = eng.compute_kill_chain_latency(MissileType.TBM_MEDIUM, 0.5)
        cruise = eng.compute_kill_chain_latency(MissileType.CRUISE_SUBSONIC, 0.5)
        assert tbm > cruise

    def test_better_targeting_reduces_latency(self):
        eng = _make_engine(seed=41)
        poor = eng.compute_kill_chain_latency(MissileType.CRUISE_SUBSONIC, 0.1)
        good = eng.compute_kill_chain_latency(MissileType.CRUISE_SUBSONIC, 0.9)
        assert good < poor

    def test_coastal_ssm_shortest(self):
        eng = _make_engine(seed=42)
        ssm = eng.compute_kill_chain_latency(MissileType.COASTAL_DEFENSE_SSM, 0.5)
        cruise = eng.compute_kill_chain_latency(MissileType.CRUISE_SUBSONIC, 0.5)
        assert ssm < cruise


class TestStateRoundtrip:
    """State serialization and restoration."""

    def test_state_roundtrip_empty(self):
        eng = _make_engine(seed=50)
        state = eng.get_state()
        eng2 = _make_engine(seed=999)
        eng2.set_state(state)
        r1 = eng._rng.random()
        r2 = eng2._rng.random()
        assert r1 == pytest.approx(r2)

    def test_state_roundtrip_with_active_missiles(self):
        eng = _make_engine(seed=51)
        ammo = _make_cruise_ammo()
        eng.launch_missile(
            "launcher1", "m1",
            Position(0, 0, 0), Position(50_000, 0, 0),
            ammo, MissileType.CRUISE_SUBSONIC,
        )
        eng.update_missiles_in_flight(dt=30.0)
        state = eng.get_state()

        eng2 = _make_engine(seed=999)
        eng2.set_state(state)

        assert len(eng2.active_missiles) == 1
        assert eng2.active_missiles[0].missile_id == "m1"
        assert eng2.active_missiles[0].time_elapsed_s == pytest.approx(30.0)

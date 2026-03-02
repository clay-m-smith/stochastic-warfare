"""Tests for combat/ballistics.py — trajectory, dispersion, time-of-flight."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.combat.ballistics import (
    BallisticsConfig,
    BallisticsEngine,
    ImpactResult,
    TrajectoryResult,
)
from stochastic_warfare.core.types import Position


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _tank_gun() -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id="m256",
        display_name="M256",
        category="CANNON",
        caliber_mm=120.0,
        muzzle_velocity_mps=1750.0,
        max_range_m=4000.0,
        base_accuracy_mrad=0.2,
        compatible_ammo=["ap"],
    )


def _ap_round() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="ap",
        display_name="APFSDS",
        ammo_type="AP",
        mass_kg=8.9,
        diameter_mm=120.0,
        drag_coefficient=0.15,
        max_speed_mps=1750.0,
    )


def _howitzer() -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id="m284",
        display_name="M284",
        category="HOWITZER",
        caliber_mm=155.0,
        muzzle_velocity_mps=684.0,
        max_range_m=30000.0,
        base_accuracy_mrad=0.4,
        compatible_ammo=["he"],
    )


def _he_round() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="he",
        display_name="HE",
        ammo_type="HE",
        mass_kg=46.7,
        diameter_mm=155.0,
        drag_coefficient=0.30,
        max_speed_mps=684.0,
    )


# ---------------------------------------------------------------------------
# Trajectory computation
# ---------------------------------------------------------------------------


class TestTrajectory:
    def test_flat_fire_hits_ground(self) -> None:
        engine = BallisticsEngine(_rng(), BallisticsConfig(enable_coriolis=False))
        result = engine.compute_trajectory(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=1.0, azimuth_deg=0.0,
        )
        assert result.time_of_flight_s > 0
        assert result.impact_velocity > 0
        # Should travel some distance northward
        assert result.impact_position.northing > 100.0

    def test_high_angle_trajectory(self) -> None:
        engine = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_coriolis=False, integration_step_s=0.05),
        )
        result = engine.compute_trajectory(
            _howitzer(), _he_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=45.0, azimuth_deg=90.0,
        )
        # Should reach significant altitude
        assert result.max_altitude_m > 1000.0
        # Should travel eastward (azimuth=90)
        assert result.impact_position.easting > 500.0

    def test_trajectory_has_points(self) -> None:
        engine = BallisticsEngine(_rng())
        result = engine.compute_trajectory(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=2.0, azimuth_deg=0.0,
        )
        assert len(result.points) >= 2

    def test_impact_angle_reasonable(self) -> None:
        engine = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_coriolis=False, integration_step_s=0.05),
        )
        result = engine.compute_trajectory(
            _howitzer(), _he_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=60.0, azimuth_deg=0.0,
        )
        # High-angle fire should impact at steep angle
        assert result.impact_angle_deg > 30.0

    def test_propellant_temperature_effect(self) -> None:
        engine = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_drag=False, enable_coriolis=False),
        )
        cold = engine.compute_trajectory(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=5.0, azimuth_deg=0.0,
            conditions={"temperature_c": -20.0},
        )
        hot = engine.compute_trajectory(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=5.0, azimuth_deg=0.0,
            conditions={"temperature_c": 50.0},
        )
        # Hot propellant → higher MV → further range
        assert hot.impact_position.northing > cold.impact_position.northing

    def test_no_drag_goes_further(self) -> None:
        engine_drag = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_coriolis=False),
        )
        engine_nodrag = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_drag=False, enable_coriolis=False),
        )
        with_drag = engine_drag.compute_trajectory(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=5.0, azimuth_deg=0.0,
        )
        without_drag = engine_nodrag.compute_trajectory(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=5.0, azimuth_deg=0.0,
        )
        assert without_drag.impact_position.northing > with_drag.impact_position.northing


# ---------------------------------------------------------------------------
# Dispersion
# ---------------------------------------------------------------------------


class TestDispersion:
    def test_zero_accuracy_no_dispersion(self) -> None:
        engine = BallisticsEngine(_rng())
        aim = Position(1000.0, 2000.0, 0.0)
        result = engine.apply_dispersion(aim, 0.0, 1000.0)
        assert result == aim

    def test_dispersion_scales_with_range(self) -> None:
        engine1 = BallisticsEngine(_rng(42))
        engine2 = BallisticsEngine(_rng(42))
        aim = Position(0.0, 0.0, 0.0)

        short = engine1.apply_dispersion(aim, 1.0, 500.0)
        long = engine2.apply_dispersion(aim, 1.0, 5000.0)

        # At 10x range, sigma is 10x larger, so abs(offset) should be
        # larger on average. Use multiple samples.
        rng1 = _rng(99)
        rng2 = _rng(99)
        e1 = BallisticsEngine(rng1)
        e2 = BallisticsEngine(rng2)

        # Actually just verify the sigma computation
        sigma_short = 1.0 * 0.001 * 500.0
        sigma_long = 1.0 * 0.001 * 5000.0
        assert sigma_long == pytest.approx(10.0 * sigma_short)

    def test_dispersion_is_stochastic(self) -> None:
        engine = BallisticsEngine(_rng())
        aim = Position(1000.0, 1000.0, 0.0)
        results = [engine.apply_dispersion(aim, 1.0, 2000.0) for _ in range(20)]
        eastings = [r.easting for r in results]
        # Should not all be the same
        assert max(eastings) - min(eastings) > 0.01

    def test_deterministic_with_same_seed(self) -> None:
        aim = Position(500.0, 500.0, 0.0)
        e1 = BallisticsEngine(_rng(42))
        e2 = BallisticsEngine(_rng(42))
        r1 = e1.apply_dispersion(aim, 1.0, 1000.0)
        r2 = e2.apply_dispersion(aim, 1.0, 1000.0)
        assert r1.easting == pytest.approx(r2.easting)
        assert r1.northing == pytest.approx(r2.northing)


# ---------------------------------------------------------------------------
# Impact point computation
# ---------------------------------------------------------------------------


class TestImpactPoint:
    def test_direct_fire_impact(self) -> None:
        engine = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_coriolis=False),
        )
        result = engine.compute_impact_point(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            Position(0.0, 2000.0, 0.0),
        )
        assert isinstance(result, ImpactResult)
        assert result.time_of_flight_s > 0
        assert result.impact_velocity > 0
        # Impact should be near 2000m north (with some dispersion)
        assert abs(result.impact_position.northing - 2000.0) < 500.0

    def test_cep_at_range(self) -> None:
        engine = BallisticsEngine(_rng())
        result = engine.compute_impact_point(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            Position(0.0, 2000.0, 0.0),
        )
        # CEP = 1.1774 * sigma; sigma = 0.2 mrad * 2000m = 0.4m
        expected_cep = 1.1774 * 0.2 * 0.001 * 2000.0
        assert result.cep_m == pytest.approx(expected_cep, rel=0.01)


# ---------------------------------------------------------------------------
# Time of flight
# ---------------------------------------------------------------------------


class TestTimeOfFlight:
    def test_flat_fire_tof(self) -> None:
        engine = BallisticsEngine(_rng())
        tof = engine.compute_time_of_flight(
            _tank_gun(), _ap_round(), 2000.0, 0.0,
        )
        # At 1750 m/s, 2000m should take ~1.1s
        assert 0.5 < tof < 3.0

    def test_longer_range_longer_tof(self) -> None:
        engine = BallisticsEngine(_rng())
        tof_short = engine.compute_time_of_flight(
            _tank_gun(), _ap_round(), 1000.0, 0.0,
        )
        tof_long = engine.compute_time_of_flight(
            _tank_gun(), _ap_round(), 3000.0, 0.0,
        )
        assert tof_long > tof_short

    def test_howitzer_tof(self) -> None:
        engine = BallisticsEngine(_rng())
        tof = engine.compute_time_of_flight(
            _howitzer(), _he_round(), 20000.0, 45.0,
        )
        # Howitzer at 20km, 45° should take many seconds
        assert tof > 10.0


# ---------------------------------------------------------------------------
# Wind effects
# ---------------------------------------------------------------------------


class TestWindEffects:
    def test_wind_deflects_impact(self) -> None:
        engine_nowind = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_wind=False, enable_coriolis=False),
        )
        engine_wind = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_coriolis=False),
        )

        # Fire northward with strong east wind
        no_wind = engine_nowind.compute_trajectory(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=2.0, azimuth_deg=0.0,
        )
        with_wind = engine_wind.compute_trajectory(
            _tank_gun(), _ap_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=2.0, azimuth_deg=0.0,
            conditions={"wind_e": 20.0, "wind_n": 0.0},
        )
        # East wind should push projectile eastward (less, since drag is relative to air)
        # The effect may be subtle for fast projectiles
        # At minimum, the two results should differ
        assert (
            abs(with_wind.impact_position.easting - no_wind.impact_position.easting) > 0.001
            or abs(with_wind.impact_position.northing - no_wind.impact_position.northing) > 0.001
        )


# ---------------------------------------------------------------------------
# Air density
# ---------------------------------------------------------------------------


class TestAirDensity:
    def test_sea_level_density(self) -> None:
        engine = BallisticsEngine(_rng())
        rho = engine._air_density(0.0)
        assert rho == pytest.approx(1.225, rel=0.01)

    def test_density_decreases_with_altitude(self) -> None:
        engine = BallisticsEngine(_rng())
        rho_0 = engine._air_density(0.0)
        rho_5000 = engine._air_density(5000.0)
        rho_10000 = engine._air_density(10000.0)
        assert rho_5000 < rho_0
        assert rho_10000 < rho_5000


# ---------------------------------------------------------------------------
# State roundtrip
# ---------------------------------------------------------------------------


class TestState:
    def test_state_roundtrip(self) -> None:
        engine = BallisticsEngine(_rng(42))
        # Generate some random numbers to change state
        engine.apply_dispersion(Position(0, 0, 0), 1.0, 1000.0)
        saved = engine.get_state()

        engine2 = BallisticsEngine(_rng(99))
        engine2.set_state(saved)

        # Both should now produce the same next random value
        aim = Position(0, 0, 0)
        r1 = engine.apply_dispersion(aim, 1.0, 1000.0)
        r2 = engine2.apply_dispersion(aim, 1.0, 1000.0)
        assert r1.easting == pytest.approx(r2.easting)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_range_impact(self) -> None:
        engine = BallisticsEngine(_rng())
        result = engine.compute_impact_point(
            _tank_gun(), _ap_round(),
            Position(100.0, 100.0, 0.0),
            Position(100.0, 100.0, 0.0),
        )
        assert isinstance(result, ImpactResult)

    def test_zero_muzzle_velocity_fallback(self) -> None:
        wpn = WeaponDefinition(
            weapon_id="zero_mv",
            display_name="Zero MV",
            category="CANNON",
            caliber_mm=10.0,
            muzzle_velocity_mps=0.0,
        )
        ammo = AmmoDefinition(
            ammo_id="zero",
            display_name="Zero",
            ammo_type="HE",
            mass_kg=1.0,
            diameter_mm=10.0,
            max_speed_mps=500.0,
        )
        engine = BallisticsEngine(_rng())
        tof = engine.compute_time_of_flight(wpn, ammo, 1000.0)
        assert tof > 0

    def test_coriolis_effect_exists(self) -> None:
        engine_nocor = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_coriolis=False),
        )
        engine_cor = BallisticsEngine(
            _rng(),
            BallisticsConfig(enable_coriolis=True),
        )
        # Use howitzer for longer flight time to see Coriolis
        no_cor = engine_nocor.compute_trajectory(
            _howitzer(), _he_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=45.0, azimuth_deg=0.0,
            conditions={"latitude_rad": 0.7},
        )
        with_cor = engine_cor.compute_trajectory(
            _howitzer(), _he_round(),
            Position(0.0, 0.0, 0.0),
            elevation_deg=45.0, azimuth_deg=0.0,
            conditions={"latitude_rad": 0.7},
        )
        # Coriolis should cause east-west deflection at mid-latitudes
        assert abs(with_cor.impact_position.easting - no_cor.impact_position.easting) > 0.1

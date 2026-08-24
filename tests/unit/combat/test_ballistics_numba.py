"""Phase 13b-2: Numba JIT for RK4 trajectory tests."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.combat.ballistics import (
    BallisticsConfig,
    BallisticsEngine,
    TrajectoryResult,
    _rk4_trajectory_kernel,
    _speed_of_sound,
    _mach_drag_multiplier,
)
from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.core.types import Position, STANDARD_GRAVITY


def _make_weapon() -> WeaponDefinition:
    return WeaponDefinition(
        weapon_id="test_gun",
        display_name="Test Gun",
        category="CANNON",
        caliber_mm=120,
        muzzle_velocity_mps=1700,
        max_range_m=4000,
        base_accuracy_mrad=0.3,
        rate_of_fire_rpm=6,
    )


def _make_ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="test_round",
        display_name="Test APFSDS",
        ammo_type="AP",
        caliber_mm=120,
        mass_kg=4.5,
        diameter_mm=30,
        drag_coefficient=0.3,
    )


class TestSpeedOfSound:
    def test_standard_temperature(self):
        """Speed of sound at 21 deg C should be ~344 m/s."""
        sos = _speed_of_sound(21.0)
        assert 343.0 < sos < 345.0

    def test_zero_celsius(self):
        """Speed of sound at 0 deg C should be ~331 m/s."""
        sos = _speed_of_sound(0.0)
        assert 330.0 < sos < 332.0


class TestMachDragMultiplier:
    def test_subsonic(self):
        assert _mach_drag_multiplier(0.5) == 1.0

    def test_transonic_peak(self):
        m = _mach_drag_multiplier(1.2)
        assert 1.9 < m < 2.1

    def test_supersonic_decay(self):
        m = _mach_drag_multiplier(2.0)
        assert m < 2.0


class TestRK4Kernel:
    def test_kernel_returns_tuple(self):
        result = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,     # position
            100.0, 0.0, 100.0,  # velocity
            0.01, 10.0, 0.0,   # dt, max_t, fire_alt
            0, 0, 0, 0,        # all physics disabled
            0.3, 4.5, 0.001,   # drag_coeff, mass, area
            1.225, 8500.0, 344.0,  # rho0, scale_height, sos
            0.0, 0.0,          # wind
            0.7, 7.29e-5, 9.81,  # lat, omega, g
        )
        assert len(result) == 9

    def test_kernel_no_drag_parabolic(self):
        """Without drag/wind/coriolis, trajectory should be parabolic."""
        result = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            500.0, 0.0, 500.0,
            0.01, 200.0, 0.0,
            0, 0, 0, 0,  # all disabled
            0.0, 4.5, 0.001,
            1.225, 8500.0, 344.0,
            0.0, 0.0,
            0.0, 0.0, STANDARD_GRAVITY,
        )
        fx, fy, fz, fvx, fvy, fvz, tof, max_alt, impact_angle = result
        # Time of flight for 45 deg launch: 2*v0*sin(45)/g ~= 72s
        # But here vx=500, vz=500 (not a 45-degree launch with speed 500;
        # total speed is sqrt(500^2+500^2) ~ 707 m/s).
        # tof = 2*vz/g = 2*500/9.80665 ~= 101.97s
        expected_tof = 2 * 500.0 / STANDARD_GRAVITY
        assert abs(tof - expected_tof) < 1.0  # within 1 second
        # Range = vx * tof = 500 * ~101.97 ~= 50985m
        expected_range = 500.0 * expected_tof
        assert abs(fx - expected_range) < 100.0

    def test_kernel_with_drag_shorter_range(self):
        """Drag should reduce range compared to no-drag."""
        no_drag = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            1000.0, 0.0, 500.0,
            0.01, 200.0, 0.0,
            0, 0, 0, 0,
            0.3, 4.5, 0.0007,
            1.225, 8500.0, 344.0,
            0.0, 0.0,
            0.0, 0.0, STANDARD_GRAVITY,
        )
        with_drag = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            1000.0, 0.0, 500.0,
            0.01, 200.0, 0.0,
            1, 0, 0, 0,  # drag enabled
            0.3, 4.5, 0.0007,
            1.225, 8500.0, 344.0,
            0.0, 0.0,
            0.0, 0.0, STANDARD_GRAVITY,
        )
        assert with_drag[0] < no_drag[0]  # shorter range with drag

    def test_kernel_max_altitude_tracked(self):
        """Max altitude should be positive for an upward launch."""
        result = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            500.0, 0.0, 500.0,
            0.01, 200.0, 0.0,
            0, 0, 0, 0,
            0.0, 4.5, 0.001,
            1.225, 8500.0, 344.0,
            0.0, 0.0,
            0.0, 0.0, STANDARD_GRAVITY,
        )
        max_alt = result[7]
        assert max_alt > 1000.0  # vz=500 -> max_alt ~= 500^2/(2*g) ~= 12742m

    def test_kernel_impact_angle_positive(self):
        """Impact angle should be positive (magnitude)."""
        result = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            500.0, 0.0, 500.0,
            0.01, 200.0, 0.0,
            0, 0, 0, 0,
            0.0, 4.5, 0.001,
            1.225, 8500.0, 344.0,
            0.0, 0.0,
            0.0, 0.0, STANDARD_GRAVITY,
        )
        impact_angle = result[8]
        assert impact_angle > 0.0

    def test_kernel_wind_deflection(self):
        """Wind should cause lateral deflection."""
        no_wind = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            0.0, 500.0, 200.0,
            0.01, 100.0, 0.0,
            1, 0, 0, 0,
            0.3, 4.5, 0.001,
            1.225, 8500.0, 344.0,
            0.0, 0.0,  # no wind
            0.0, 0.0, STANDARD_GRAVITY,
        )
        with_wind = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            0.0, 500.0, 200.0,
            0.01, 100.0, 0.0,
            1, 0, 1, 0,  # drag + wind enabled
            0.3, 4.5, 0.001,
            1.225, 8500.0, 344.0,
            20.0, 0.0,  # 20 m/s east wind
            0.0, 0.0, STANDARD_GRAVITY,
        )
        # With east wind and drag based on air-relative velocity, impact
        # should differ in easting
        assert abs(with_wind[0] - no_wind[0]) > 0.01

    def test_kernel_coriolis_effect(self):
        """Coriolis should cause lateral deflection at mid-latitudes."""
        no_cor = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            0.0, 500.0, 500.0,
            0.05, 200.0, 0.0,
            0, 0, 0, 0,  # all disabled
            0.0, 4.5, 0.001,
            1.225, 8500.0, 344.0,
            0.0, 0.0,
            0.7, 7.2921e-5, STANDARD_GRAVITY,
        )
        with_cor = _rk4_trajectory_kernel(
            0.0, 0.0, 0.0,
            0.0, 500.0, 500.0,
            0.05, 200.0, 0.0,
            0, 0, 0, 1,  # coriolis only
            0.0, 4.5, 0.001,
            1.225, 8500.0, 344.0,
            0.0, 0.0,
            0.7, 7.2921e-5, STANDARD_GRAVITY,
        )
        # Coriolis at 40 deg N should cause east-west deflection
        assert abs(with_cor[0] - no_cor[0]) > 0.1


class TestComputeTrajectoryParity:
    def test_trajectory_result_structure(self):
        """compute_trajectory should return valid TrajectoryResult."""
        rng = np.random.default_rng(42)
        engine = BallisticsEngine(rng, BallisticsConfig())
        weapon = _make_weapon()
        ammo = _make_ammo()
        result = engine.compute_trajectory(
            weapon, ammo, Position(0, 0, 0), 5.0, 0.0,
        )
        assert isinstance(result, TrajectoryResult)
        assert result.time_of_flight_s > 0
        assert result.impact_velocity > 0
        assert len(result.points) >= 2

    def test_trajectory_azimuth_direction(self):
        """0 deg azimuth should fire northward (positive y)."""
        rng = np.random.default_rng(42)
        engine = BallisticsEngine(rng, BallisticsConfig())
        weapon = _make_weapon()
        ammo = _make_ammo()
        result = engine.compute_trajectory(
            weapon, ammo, Position(0, 0, 0), 5.0, 0.0,
        )
        # Northward: impact_position.northing should be positive
        assert result.impact_position.northing > 0

    def test_trajectory_elevation_affects_range(self):
        """Higher elevation should increase range (up to 45 deg)."""
        rng = np.random.default_rng(42)
        engine = BallisticsEngine(rng, BallisticsConfig(
            enable_drag=False, enable_wind=False, enable_coriolis=False,
        ))
        weapon = _make_weapon()
        ammo = _make_ammo()

        r5 = engine.compute_trajectory(weapon, ammo, Position(0, 0, 0), 5.0, 90.0)
        r30 = engine.compute_trajectory(weapon, ammo, Position(0, 0, 0), 30.0, 90.0)
        # 30 deg should give longer range than 5 deg (both < 45 deg)
        range5 = math.sqrt(r5.impact_position.easting**2 + r5.impact_position.northing**2)
        range30 = math.sqrt(r30.impact_position.easting**2 + r30.impact_position.northing**2)
        assert range30 > range5

    def test_trajectory_with_all_physics(self):
        """Full physics should produce reasonable results."""
        rng = np.random.default_rng(42)
        engine = BallisticsEngine(rng, BallisticsConfig(
            enable_drag=True, enable_mach_drag=True,
            enable_wind=True, enable_coriolis=True,
        ))
        weapon = _make_weapon()
        ammo = _make_ammo()
        result = engine.compute_trajectory(
            weapon, ammo, Position(0, 0, 0), 10.0, 45.0,
            conditions={"wind_e": 5.0, "wind_n": -3.0, "temperature_c": 25.0},
        )
        assert result.time_of_flight_s > 0
        assert result.max_altitude_m > 0

    def test_deterministic_trajectory(self):
        """Same inputs should produce same trajectory."""
        results = []
        for _ in range(2):
            rng = np.random.default_rng(42)
            engine = BallisticsEngine(rng, BallisticsConfig())
            weapon = _make_weapon()
            ammo = _make_ammo()
            result = engine.compute_trajectory(
                weapon, ammo, Position(0, 0, 0), 10.0, 90.0,
            )
            results.append(result)
        assert results[0].impact_position.easting == pytest.approx(
            results[1].impact_position.easting, abs=0.01,
        )
        assert results[0].impact_position.northing == pytest.approx(
            results[1].impact_position.northing, abs=0.01,
        )
        assert results[0].time_of_flight_s == pytest.approx(
            results[1].time_of_flight_s, abs=0.001,
        )

    def test_impact_below_zero_clamped(self):
        """Impact altitude should be clamped to >= 0."""
        rng = np.random.default_rng(42)
        engine = BallisticsEngine(rng, BallisticsConfig())
        weapon = _make_weapon()
        ammo = _make_ammo()
        result = engine.compute_trajectory(
            weapon, ammo, Position(0, 0, 0), 5.0, 0.0,
        )
        assert result.impact_position.altitude >= 0.0

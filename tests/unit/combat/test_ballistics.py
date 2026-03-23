"""Unit tests for BallisticsEngine — RK4 trajectory, drag, dispersion."""

from __future__ import annotations

import math

import numpy as np
import pytest

from stochastic_warfare.combat.ballistics import (
    BallisticsConfig,
    BallisticsEngine,
)
from stochastic_warfare.core.types import Position

from .conftest import _make_ap, _make_gun, _rng


class TestBallisticsConfig:
    def test_default_config_values(self):
        cfg = BallisticsConfig()
        assert cfg.enable_drag is True
        assert cfg.enable_mach_drag is True
        assert cfg.enable_wind is True
        assert cfg.enable_coriolis is True
        assert cfg.max_flight_time_s == 300.0


class TestTrajectoryComputation:
    """RK4 trajectory integration with toggleable physics."""

    def test_basic_trajectory(self):
        eng = BallisticsEngine(_rng())
        weapon = _make_gun(muzzle_velocity_mps=800.0)
        ammo = _make_ap(mass_kg=10.0)
        result = eng.compute_trajectory(
            weapon, ammo,
            fire_pos=Position(0.0, 0.0, 0.0),
            elevation_deg=5.0,
            azimuth_deg=0.0,
        )
        assert result.time_of_flight_s > 0
        assert result.impact_velocity > 0

    def test_drag_reduces_range(self):
        """With drag enabled, projectile lands shorter than without."""
        ammo = _make_ap(mass_kg=10.0, drag_coefficient=0.5)
        weapon = _make_gun(muzzle_velocity_mps=800.0)

        eng_drag = BallisticsEngine(_rng(), config=BallisticsConfig(enable_drag=True))
        r_drag = eng_drag.compute_trajectory(
            weapon, ammo, Position(0.0, 0.0, 0.0), elevation_deg=10.0, azimuth_deg=0.0,
        )
        eng_nodrag = BallisticsEngine(_rng(), config=BallisticsConfig(enable_drag=False))
        r_nodrag = eng_nodrag.compute_trajectory(
            weapon, ammo, Position(0.0, 0.0, 0.0), elevation_deg=10.0, azimuth_deg=0.0,
        )
        dist_drag = math.sqrt(
            r_drag.impact_position.easting ** 2 + r_drag.impact_position.northing ** 2
        )
        dist_nodrag = math.sqrt(
            r_nodrag.impact_position.easting ** 2 + r_nodrag.impact_position.northing ** 2
        )
        assert dist_drag < dist_nodrag

    def test_no_drag_no_wind_no_coriolis(self):
        """All effects disabled = simple parabolic trajectory."""
        cfg = BallisticsConfig(
            enable_drag=False, enable_mach_drag=False,
            enable_wind=False, enable_coriolis=False,
        )
        eng = BallisticsEngine(_rng(), config=cfg)
        weapon = _make_gun(muzzle_velocity_mps=500.0)
        ammo = _make_ap(mass_kg=5.0)
        result = eng.compute_trajectory(
            weapon, ammo, Position(0.0, 0.0, 0.0), elevation_deg=45.0, azimuth_deg=0.0,
        )
        assert result.time_of_flight_s > 0
        assert result.max_altitude_m > 0

    def test_high_angle_indirect(self):
        """High-angle (> 45°) produces mortar-like trajectory."""
        cfg = BallisticsConfig(enable_drag=False, enable_wind=False, enable_coriolis=False)
        eng = BallisticsEngine(_rng(), config=cfg)
        weapon = _make_gun(muzzle_velocity_mps=200.0)
        ammo = _make_ap(mass_kg=3.0)
        result = eng.compute_trajectory(
            weapon, ammo, Position(0.0, 0.0, 0.0), elevation_deg=70.0, azimuth_deg=0.0,
        )
        assert result.max_altitude_m > 100.0

    def test_temperature_affects_density(self):
        """Higher temperature = lower air density = less drag."""
        ammo = _make_ap(mass_kg=10.0, drag_coefficient=0.4)
        weapon = _make_gun(muzzle_velocity_mps=800.0)

        cold = BallisticsEngine(_rng(), config=BallisticsConfig(temperature_c=-20.0))
        hot = BallisticsEngine(_rng(), config=BallisticsConfig(temperature_c=40.0))
        r_cold = cold.compute_trajectory(weapon, ammo, Position(0.0, 0.0, 0.0), 10.0, 0.0)
        r_hot = hot.compute_trajectory(weapon, ammo, Position(0.0, 0.0, 0.0), 10.0, 0.0)
        dist_cold = math.sqrt(r_cold.impact_position.easting ** 2 + r_cold.impact_position.northing ** 2)
        dist_hot = math.sqrt(r_hot.impact_position.easting ** 2 + r_hot.impact_position.northing ** 2)
        assert dist_hot > dist_cold

    def test_max_flight_time_cutoff(self):
        cfg = BallisticsConfig(max_flight_time_s=0.5, enable_drag=False, enable_coriolis=False, enable_wind=False)
        eng = BallisticsEngine(_rng(), config=cfg)
        weapon = _make_gun(muzzle_velocity_mps=500.0)
        ammo = _make_ap(mass_kg=5.0)
        result = eng.compute_trajectory(
            weapon, ammo, Position(0.0, 0.0, 0.0), elevation_deg=80.0, azimuth_deg=0.0,
        )
        assert result.time_of_flight_s <= 0.6  # within one integration step of limit

    def test_wind_deflects_trajectory(self):
        """Crosswind produces lateral offset."""
        cfg = BallisticsConfig(enable_drag=True, enable_wind=True, enable_coriolis=False)
        eng = BallisticsEngine(_rng(), config=cfg)
        weapon = _make_gun(muzzle_velocity_mps=800.0)
        ammo = _make_ap(mass_kg=10.0)
        no_wind = eng.compute_trajectory(
            weapon, ammo, Position(0.0, 0.0, 0.0), 10.0, 0.0,
        )
        with_wind = eng.compute_trajectory(
            weapon, ammo, Position(0.0, 0.0, 0.0), 10.0, 0.0,
            conditions={"wind_e": 20.0, "wind_n": 0.0},
        )
        # Crosswind should deflect eastward
        assert abs(with_wind.impact_position.easting) > abs(no_wind.impact_position.easting)


class TestDispersion:
    """Dispersion and impact point calculation."""

    def test_dispersion_scales_with_range(self):
        eng = BallisticsEngine(_rng(seed=10))
        weapon = _make_gun(base_accuracy_mrad=1.0)
        ammo = _make_ap()
        near = eng.compute_impact_point(
            weapon, ammo, Position(0, 0, 0), Position(500, 0, 0),
        )
        far = eng.compute_impact_point(
            weapon, ammo, Position(0, 0, 0), Position(3000, 0, 0),
        )
        assert far.cep_m > near.cep_m

    def test_zero_accuracy_no_dispersion(self):
        """base_accuracy_mrad=0 produces zero CEP."""
        eng = BallisticsEngine(_rng(seed=10))
        weapon = _make_gun(base_accuracy_mrad=0.0)
        ammo = _make_ap()
        result = eng.compute_impact_point(
            weapon, ammo, Position(0, 0, 0), Position(1000, 0, 0),
        )
        assert result.cep_m == 0.0

    def test_determinism(self):
        """Same seed produces identical results."""
        weapon = _make_gun()
        ammo = _make_ap()
        eng1 = BallisticsEngine(_rng(seed=42))
        eng2 = BallisticsEngine(_rng(seed=42))
        r1 = eng1.compute_impact_point(weapon, ammo, Position(0, 0, 0), Position(1000, 0, 0))
        r2 = eng2.compute_impact_point(weapon, ammo, Position(0, 0, 0), Position(1000, 0, 0))
        assert r1.impact_position.easting == r2.impact_position.easting

    def test_state_roundtrip(self):
        eng = BallisticsEngine(_rng(seed=55))
        state = eng.get_state()
        eng2 = BallisticsEngine(_rng(seed=1))
        eng2.set_state(state)
        assert eng._rng.random() == eng2._rng.random()

    def test_apply_dispersion_gaussian(self):
        """apply_dispersion adds Gaussian noise to aim point."""
        eng = BallisticsEngine(_rng(seed=42))
        aim = Position(1000.0, 0.0, 0.0)
        dispersed = eng.apply_dispersion(aim, accuracy_mrad=2.0, range_m=1000.0)
        # Should not be exactly the aim point
        assert (dispersed.easting != aim.easting) or (dispersed.northing != aim.northing)

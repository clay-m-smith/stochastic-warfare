"""Integration tests: environment conditions flowing into combat modules.

Validates that environmental parameters (visibility, wind, temperature,
weather, night) actually affect combat outcomes when passed through the
combat module APIs.
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.air_ground import AirGroundEngine
from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_rng(seed: int = 42) -> np.random.Generator:
    """Project-standard PRNG construction."""
    return np.random.Generator(np.random.PCG64(seed))


def _rifle_weapon() -> WeaponDefinition:
    """Generic direct-fire weapon for hit probability tests."""
    return WeaponDefinition(
        weapon_id="test_rifle",
        display_name="Test Rifle",
        category="CANNON",
        caliber_mm=7.62,
        muzzle_velocity_mps=850.0,
        max_range_m=3000.0,
        base_accuracy_mrad=1.0,
        rate_of_fire_rpm=600.0,
    )


def _rifle_ammo() -> AmmoDefinition:
    """Generic ball ammo for hit probability tests."""
    return AmmoDefinition(
        ammo_id="test_762_ball",
        display_name="7.62mm Ball",
        ammo_type="HE",
        mass_kg=0.0095,
        diameter_mm=7.62,
        drag_coefficient=0.3,
        blast_radius_m=0.0,
        fragmentation_radius_m=0.0,
    )


def _tank_weapon() -> WeaponDefinition:
    """120mm smoothbore for ballistics tests."""
    return WeaponDefinition(
        weapon_id="test_120mm",
        display_name="Test 120mm",
        category="CANNON",
        caliber_mm=120.0,
        muzzle_velocity_mps=1750.0,
        max_range_m=4000.0,
        base_accuracy_mrad=0.3,
    )


def _tank_apfsds() -> AmmoDefinition:
    """120mm APFSDS round for ballistics tests."""
    return AmmoDefinition(
        ammo_id="test_apfsds",
        display_name="Test APFSDS",
        ammo_type="AP",
        mass_kg=4.6,
        diameter_mm=120.0,
        drag_coefficient=0.15,
        penetration_mm_rha=600.0,
        penetration_reference_range_m=2000.0,
    )


def _howitzer_weapon() -> WeaponDefinition:
    """155mm howitzer for indirect fire tests."""
    return WeaponDefinition(
        weapon_id="test_155mm",
        display_name="Test 155mm",
        category="HOWITZER",
        caliber_mm=155.0,
        muzzle_velocity_mps=800.0,
        max_range_m=30000.0,
        base_accuracy_mrad=1.5,
        cep_m=150.0,
    )


def _he_ammo() -> AmmoDefinition:
    """155mm HE round for indirect fire tests."""
    return AmmoDefinition(
        ammo_id="test_155_he",
        display_name="Test 155mm HE",
        ammo_type="HE",
        mass_kg=43.0,
        diameter_mm=155.0,
        drag_coefficient=0.4,
        blast_radius_m=50.0,
        fragmentation_radius_m=150.0,
    )


# =========================================================================
# TestVisibilityAffectsHitProbability
# =========================================================================


class TestVisibilityAffectsHitProbability:
    """Verify that the visibility parameter in compute_phit modifies P(hit)."""

    def _make_engine(self, seed: int = 100) -> HitProbabilityEngine:
        rng = _make_rng(seed)
        ballistics = BallisticsEngine(rng=_make_rng(seed + 1))
        return HitProbabilityEngine(ballistics=ballistics, rng=rng)

    def test_poor_visibility_reduces_phit(self) -> None:
        """P(hit) at visibility=0.2 should be lower than at visibility=1.0."""
        engine = self._make_engine()
        weapon = _rifle_weapon()
        ammo = _rifle_ammo()

        result_good = engine.compute_phit(
            weapon=weapon, ammo=ammo, range_m=500.0,
            target_size_m2=6.0, visibility=1.0,
        )
        result_poor = engine.compute_phit(
            weapon=weapon, ammo=ammo, range_m=500.0,
            target_size_m2=6.0, visibility=0.2,
        )

        assert result_poor.p_hit < result_good.p_hit, (
            f"Poor visibility P(hit)={result_poor.p_hit:.4f} should be less "
            f"than good visibility P(hit)={result_good.p_hit:.4f}"
        )

    def test_zero_visibility_minimum_phit(self) -> None:
        """At visibility=0.0, P(hit) should be very low (near min_phit)."""
        engine = self._make_engine()
        weapon = _rifle_weapon()
        ammo = _rifle_ammo()

        result = engine.compute_phit(
            weapon=weapon, ammo=ammo, range_m=500.0,
            target_size_m2=6.0, visibility=0.0,
        )

        # Visibility modifier is 0.3 + 0.7 * 0.0 = 0.3; combined with
        # other modifiers, P(hit) should be substantially below 0.5.
        assert result.p_hit < 0.5, (
            f"Zero visibility P(hit)={result.p_hit:.4f} should be well below 0.5"
        )
        # The visibility modifier in the modifiers dict should reflect this
        assert result.modifiers["visibility"] == pytest.approx(0.3, abs=1e-6)

    def test_full_visibility_baseline(self) -> None:
        """At visibility=1.0, the visibility modifier should be 1.0."""
        engine = self._make_engine()
        weapon = _rifle_weapon()
        ammo = _rifle_ammo()

        result = engine.compute_phit(
            weapon=weapon, ammo=ammo, range_m=500.0,
            target_size_m2=6.0, visibility=1.0,
        )

        assert result.modifiers["visibility"] == pytest.approx(1.0, abs=1e-6)
        # P(hit) should be meaningfully above zero at 500 m
        assert result.p_hit > 0.05


# =========================================================================
# TestWindAffectsTrajectory
# =========================================================================


class TestWindAffectsTrajectory:
    """Verify that wind conditions in compute_trajectory shift impact point."""

    def _make_engine(self, seed: int = 200) -> BallisticsEngine:
        return BallisticsEngine(rng=_make_rng(seed))

    def test_crosswind_shifts_impact(self) -> None:
        """A 10 m/s eastward crosswind should shift the impact easting."""
        engine = self._make_engine()
        weapon = _tank_weapon()
        ammo = _tank_apfsds()
        fire_pos = Position(0.0, 0.0, 0.0)

        # Fire due north (azimuth=0) at a low elevation for a flat trajectory
        traj_no_wind = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=2.0, azimuth_deg=0.0,
            conditions={"wind_e": 0.0, "wind_n": 0.0},
        )
        traj_crosswind = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=2.0, azimuth_deg=0.0,
            conditions={"wind_e": 10.0, "wind_n": 0.0},
        )

        # Crosswind from the east: relative air velocity shifts projectile
        # Impact easting should differ between the two shots
        east_no_wind = traj_no_wind.impact_position.easting
        east_crosswind = traj_crosswind.impact_position.easting
        assert east_no_wind != pytest.approx(east_crosswind, abs=0.01), (
            f"Crosswind should shift impact: no-wind easting={east_no_wind:.2f}, "
            f"crosswind easting={east_crosswind:.2f}"
        )

    def test_headwind_changes_range(self) -> None:
        """Strong headwind (from north) vs tailwind (from south) should
        produce different northing impact points for a northward shot."""
        engine = self._make_engine()
        weapon = _tank_weapon()
        ammo = _tank_apfsds()
        fire_pos = Position(0.0, 0.0, 0.0)

        traj_headwind = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=2.0, azimuth_deg=0.0,
            conditions={"wind_e": 0.0, "wind_n": -20.0},  # headwind
        )
        traj_tailwind = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=2.0, azimuth_deg=0.0,
            conditions={"wind_e": 0.0, "wind_n": 20.0},  # tailwind
        )

        north_head = traj_headwind.impact_position.northing
        north_tail = traj_tailwind.impact_position.northing
        assert north_head != pytest.approx(north_tail, abs=0.01), (
            f"Headwind vs tailwind should differ: head={north_head:.2f}, "
            f"tail={north_tail:.2f}"
        )

    def test_no_wind_baseline(self) -> None:
        """With explicit zero wind, trajectory should match no-conditions baseline."""
        engine = self._make_engine()
        weapon = _tank_weapon()
        ammo = _tank_apfsds()
        fire_pos = Position(0.0, 0.0, 0.0)

        traj_none = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=2.0, azimuth_deg=0.0,
            conditions=None,
        )
        traj_zero = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=2.0, azimuth_deg=0.0,
            conditions={"wind_e": 0.0, "wind_n": 0.0},
        )

        # Default wind is already (0,0), so trajectories should match
        assert traj_none.impact_position.easting == pytest.approx(
            traj_zero.impact_position.easting, abs=0.01
        )
        assert traj_none.impact_position.northing == pytest.approx(
            traj_zero.impact_position.northing, abs=0.01
        )


# =========================================================================
# TestTemperatureAffectsBallistics
# =========================================================================


class TestTemperatureAffectsBallistics:
    """Verify that temperature_c in conditions dict affects muzzle velocity
    and therefore trajectory range."""

    def _make_engine(self, seed: int = 300) -> BallisticsEngine:
        from stochastic_warfare.combat.ballistics import BallisticsConfig
        # Disable Mach-dependent drag to isolate MV-temperature effect
        config = BallisticsConfig(enable_mach_drag=False)
        return BallisticsEngine(rng=_make_rng(seed), config=config)

    def test_cold_reduces_muzzle_velocity(self) -> None:
        """At -20 C propellant burns slower; muzzle velocity decreases,
        reducing range compared to +40 C."""
        engine = self._make_engine()
        weapon = _tank_weapon()
        ammo = _tank_apfsds()
        fire_pos = Position(0.0, 0.0, 0.0)

        traj_cold = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=5.0, azimuth_deg=0.0,
            conditions={"temperature_c": -20.0},
        )
        traj_hot = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=5.0, azimuth_deg=0.0,
            conditions={"temperature_c": 40.0},
        )

        # Hot propellant => higher MV => greater range (northing)
        range_cold = traj_cold.impact_position.northing
        range_hot = traj_hot.impact_position.northing
        assert range_cold < range_hot, (
            f"Cold temp range={range_cold:.1f} should be less than "
            f"hot temp range={range_hot:.1f}"
        )

    def test_standard_temperature_baseline(self) -> None:
        """At 21 C (standard), trajectory should match the default
        (no conditions dict) since BallisticsConfig defaults to 21 C."""
        engine = self._make_engine()
        weapon = _tank_weapon()
        ammo = _tank_apfsds()
        fire_pos = Position(0.0, 0.0, 0.0)

        traj_default = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=5.0, azimuth_deg=0.0,
            conditions=None,
        )
        traj_standard = engine.compute_trajectory(
            weapon=weapon, ammo=ammo, fire_pos=fire_pos,
            elevation_deg=5.0, azimuth_deg=0.0,
            conditions={"temperature_c": 21.0},
        )

        assert traj_default.impact_position.northing == pytest.approx(
            traj_standard.impact_position.northing, abs=0.01
        )
        assert traj_default.time_of_flight_s == pytest.approx(
            traj_standard.time_of_flight_s, abs=0.001
        )


# =========================================================================
# TestAirGroundWeatherPenalty
# =========================================================================


class TestAirGroundWeatherPenalty:
    """Verify weather_penalty and night conditions degrade air-to-ground accuracy."""

    def _make_engine(self, seed: int = 400) -> AirGroundEngine:
        event_bus = EventBus()
        rng = _make_rng(seed)
        return AirGroundEngine(event_bus=event_bus, rng=rng)

    def test_weather_penalty_reduces_accuracy(self) -> None:
        """weapon_delivery_accuracy should be lower with weather_penalty=0.5
        than with weather_penalty=0.0."""
        engine = self._make_engine()

        acc_clear = engine.compute_weapon_delivery_accuracy(
            altitude_m=5000.0,
            speed_mps=200.0,
            guidance_type="gps",
            conditions={"weather_penalty": 0.0},
        )
        acc_weather = engine.compute_weapon_delivery_accuracy(
            altitude_m=5000.0,
            speed_mps=200.0,
            guidance_type="gps",
            conditions={"weather_penalty": 0.5},
        )

        assert acc_weather < acc_clear, (
            f"Weather-degraded accuracy={acc_weather:.4f} should be less "
            f"than clear accuracy={acc_clear:.4f}"
        )

    def test_night_reduces_accuracy(self) -> None:
        """Night penalty should reduce weapon delivery accuracy."""
        engine = self._make_engine()

        acc_day = engine.compute_weapon_delivery_accuracy(
            altitude_m=5000.0,
            speed_mps=200.0,
            guidance_type="gps",
            conditions={"night": 0.0},
        )
        acc_night = engine.compute_weapon_delivery_accuracy(
            altitude_m=5000.0,
            speed_mps=200.0,
            guidance_type="gps",
            conditions={"night": 1.0},
        )

        assert acc_night < acc_day, (
            f"Night accuracy={acc_night:.4f} should be less "
            f"than day accuracy={acc_day:.4f}"
        )

    def test_combined_weather_and_night(self) -> None:
        """Combined weather + night should be worse than either alone."""
        engine = self._make_engine()

        acc_weather_only = engine.compute_weapon_delivery_accuracy(
            altitude_m=5000.0,
            speed_mps=200.0,
            guidance_type="gps",
            conditions={"weather_penalty": 0.5, "night": 0.0},
        )
        acc_night_only = engine.compute_weapon_delivery_accuracy(
            altitude_m=5000.0,
            speed_mps=200.0,
            guidance_type="gps",
            conditions={"weather_penalty": 0.0, "night": 1.0},
        )
        acc_both = engine.compute_weapon_delivery_accuracy(
            altitude_m=5000.0,
            speed_mps=200.0,
            guidance_type="gps",
            conditions={"weather_penalty": 0.5, "night": 1.0},
        )

        assert acc_both < acc_weather_only, (
            f"Combined={acc_both:.4f} should be less than weather-only={acc_weather_only:.4f}"
        )
        assert acc_both < acc_night_only, (
            f"Combined={acc_both:.4f} should be less than night-only={acc_night_only:.4f}"
        )

    def test_cas_effective_pk_degrades_with_weather(self) -> None:
        """CAS execute_cas with weather conditions should produce lower
        effective Pk than clear conditions."""
        event_bus = EventBus()
        # Use separate RNG instances with same seed for fair comparison
        engine_clear = AirGroundEngine(event_bus=event_bus, rng=_make_rng(500))
        engine_weather = AirGroundEngine(event_bus=event_bus, rng=_make_rng(500))

        aircraft_pos = Position(0.0, 0.0, 5000.0)
        target_pos = Position(1000.0, 1000.0, 0.0)

        result_clear = engine_clear.execute_cas(
            aircraft_id="ac1", target_id="tgt1",
            aircraft_pos=aircraft_pos, target_pos=target_pos,
            weapon_pk=0.8, guidance_type="gps",
            conditions={"weather_penalty": 0.0, "night": 0.0},
        )
        result_weather = engine_weather.execute_cas(
            aircraft_id="ac1", target_id="tgt1",
            aircraft_pos=aircraft_pos, target_pos=target_pos,
            weapon_pk=0.8, guidance_type="gps",
            conditions={"weather_penalty": 0.8, "night": 1.0},
        )

        assert result_weather.effective_pk < result_clear.effective_pk, (
            f"Weather-degraded CAS Pk={result_weather.effective_pk:.4f} should be "
            f"less than clear CAS Pk={result_clear.effective_pk:.4f}"
        )

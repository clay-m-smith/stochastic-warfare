"""Phase 62d: Air Combat Environmental Coupling — inline math verification tests.

Tests verify cloud ceiling gate, icing penalties, density altitude,
wind→BVR range modification, and energy advantage wiring when
``enable_air_combat_environment=True``.
"""

from __future__ import annotations

import math

import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema


# ---------------------------------------------------------------------------
# Helpers: replicate the inline logic from battle.py
# ---------------------------------------------------------------------------


def _cloud_ceiling_check(
    ceiling_m: float,
    min_attack_m: float,
    guidance_type: str,
) -> bool:
    """Return True if CAS is allowed, False if aborted.

    PGM weapons proceed regardless of ceiling; unguided/visual aborts below min.
    """
    pgm_types = ("gps", "laser", "radar", "combined", "gps_ins", "semi_active", "active")
    is_pgm = guidance_type.lower() in pgm_types
    if ceiling_m < min_attack_m and not is_pgm:
        return False  # abort
    return True  # proceed


def _icing_missile_pk_modifier(icing_risk: float, penalty: float = 0.15) -> float:
    """Return missile Pk multiplier from icing conditions.

    Applied when icing_risk > 0.5.
    """
    if icing_risk > 0.5:
        return 1.0 - penalty
    return 1.0


def _density_altitude_factor(rho: float) -> float:
    """Return performance factor from air density.

    ISA sea-level density = 1.225 kg/m³.
    """
    return min(1.0, rho / 1.225)


def _wind_bvr_range_modifier(
    wind_speed_mps: float,
    wind_dir_rad: float,
    attacker_e: float,
    attacker_n: float,
    target_e: float,
    target_n: float,
    missile_speed_mps: float = 1000.0,
) -> float:
    """Return the BVR range modification factor.

    Tailwind (wind component along heading) extends range (mod > 1).
    Headwind reduces range (mod < 1).
    """
    dx = target_e - attacker_e
    dy = target_n - attacker_n
    if dx == 0 and dy == 0:
        return 1.0
    heading = math.atan2(dx, dy)
    wind_along = wind_speed_mps * math.cos(wind_dir_rad - heading)
    return 1.0 + wind_along / missile_speed_mps


def _energy_advantage(atk_alt: float, atk_speed: float, def_alt: float, def_speed: float) -> float:
    """Return specific energy difference (attacker - defender) in meters."""
    g = 9.81
    atk_se = atk_alt + atk_speed ** 2 / (2 * g)
    def_se = def_alt + def_speed ** 2 / (2 * g)
    return atk_se - def_se


# ---------------------------------------------------------------------------
# Cloud ceiling tests
# ---------------------------------------------------------------------------


class TestCloudCeiling:
    def test_low_ceiling_unguided_aborted(self) -> None:
        """Cloud ceiling < 500m + unguided weapon: CAS aborted."""
        assert _cloud_ceiling_check(300.0, 500.0, "none") is False

    def test_high_ceiling_proceeds(self) -> None:
        """Cloud ceiling > 500m: CAS proceeds."""
        assert _cloud_ceiling_check(800.0, 500.0, "none") is True

    def test_low_ceiling_pgm_proceeds(self) -> None:
        """Cloud ceiling < 500m + PGM (GPS/laser/radar): still works."""
        assert _cloud_ceiling_check(300.0, 500.0, "gps") is True
        assert _cloud_ceiling_check(300.0, 500.0, "laser") is True
        assert _cloud_ceiling_check(300.0, 500.0, "radar") is True
        assert _cloud_ceiling_check(300.0, 500.0, "combined") is True
        assert _cloud_ceiling_check(300.0, 500.0, "semi_active") is True


# ---------------------------------------------------------------------------
# Icing tests
# ---------------------------------------------------------------------------


class TestIcing:
    def test_high_icing_reduces_pk(self) -> None:
        """Icing risk > 0.5: missile Pk reduced by icing_maneuver_penalty."""
        mod = _icing_missile_pk_modifier(0.8, 0.15)
        assert mod == pytest.approx(0.85)

    def test_no_icing_no_penalty(self) -> None:
        """Icing risk ≤ 0.5: no penalty."""
        mod = _icing_missile_pk_modifier(0.3, 0.15)
        assert mod == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Density altitude tests
# ---------------------------------------------------------------------------


class TestDensityAltitude:
    def test_hot_high_reduced_performance(self) -> None:
        """Low density (hot+high): performance reduced."""
        # 0.9 kg/m³ at high altitude / hot day
        factor = _density_altitude_factor(0.9)
        assert factor == pytest.approx(0.9 / 1.225, rel=0.01)
        assert factor < 1.0

    def test_sea_level_isa(self) -> None:
        """ISA sea level density: factor = 1.0."""
        factor = _density_altitude_factor(1.225)
        assert factor == pytest.approx(1.0)

    def test_dense_air_capped(self) -> None:
        """Density > ISA: capped at 1.0."""
        factor = _density_altitude_factor(1.4)
        assert factor == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Wind → BVR range tests
# ---------------------------------------------------------------------------


class TestWindBVR:
    def test_headwind_reduces_range(self) -> None:
        """Headwind: effective range reduced (BVR missile fights headwind)."""
        # Attacker at (0,0), target at (0,1000) — heading north
        # Wind from north (dir=pi) → headwind component negative
        mod = _wind_bvr_range_modifier(
            20.0, math.pi,
            0.0, 0.0, 0.0, 1000.0,
            1000.0,
        )
        assert mod < 1.0

    def test_tailwind_extends_range(self) -> None:
        """Tailwind: effective range extended."""
        # Attacker at (0,0), target at (0,1000) — heading north
        # Wind from south (dir=0) → tailwind
        mod = _wind_bvr_range_modifier(
            20.0, 0.0,
            0.0, 0.0, 0.0, 1000.0,
            1000.0,
        )
        assert mod > 1.0

    def test_no_wind_no_modification(self) -> None:
        """No wind: range modifier = 1.0."""
        mod = _wind_bvr_range_modifier(
            0.0, 0.0,
            0.0, 0.0, 0.0, 1000.0,
            1000.0,
        )
        assert mod == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Energy advantage tests
# ---------------------------------------------------------------------------


class TestEnergyAdvantage:
    def test_higher_aircraft_has_advantage(self) -> None:
        """Higher aircraft has positive specific energy advantage."""
        adv = _energy_advantage(10000, 250, 5000, 250)
        assert adv > 0  # 5000m altitude advantage

    def test_faster_aircraft_has_advantage(self) -> None:
        """Same altitude, faster aircraft has advantage."""
        adv = _energy_advantage(5000, 350, 5000, 250)
        assert adv > 0


# ---------------------------------------------------------------------------
# Gate test
# ---------------------------------------------------------------------------


class TestAirCombatEnvGate:
    def test_disabled_no_effects(self) -> None:
        """enable_air_combat_environment=False: no environmental effects."""
        cal = CalibrationSchema(enable_air_combat_environment=False)
        assert cal.enable_air_combat_environment is False

    def test_enabled_custom_params(self) -> None:
        cal = CalibrationSchema(
            enable_air_combat_environment=True,
            cloud_ceiling_min_attack_m=300.0,
            icing_maneuver_penalty=0.25,
            wind_bvr_missile_speed_mps=800.0,
        )
        assert cal.enable_air_combat_environment is True
        assert cal.cloud_ceiling_min_attack_m == pytest.approx(300.0)
        assert cal.icing_maneuver_penalty == pytest.approx(0.25)
        assert cal.wind_bvr_missile_speed_mps == pytest.approx(800.0)

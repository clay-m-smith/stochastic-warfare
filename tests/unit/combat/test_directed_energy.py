"""Unit tests for DEWEngine — Beer-Lambert transmittance, laser Pk, HPM Pk, engagements."""

from __future__ import annotations

import math

import pytest

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponDefinition, WeaponInstance
from stochastic_warfare.combat.directed_energy import (
    DEWConfig,
    DEWEngine,
    DEWEngagementResult,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _make_gun, _make_weapon_instance, _make_ap, _rng


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(seed: int = 42, **cfg_kwargs) -> DEWEngine:
    bus = EventBus()
    config = DEWConfig(**cfg_kwargs) if cfg_kwargs else None
    return DEWEngine(bus, _rng(seed), config)


def _make_laser_weapon(
    *,
    beam_power_kw: float = 100.0,
    max_range_m: float = 5000.0,
    dwell_time_s: float = 3.0,
    beam_divergence_mrad: float = 0.5,
    beam_wavelength_nm: float = 1064.0,
) -> WeaponDefinition:
    """Create a laser weapon definition."""
    return WeaponDefinition(
        weapon_id="test_laser",
        display_name="Test HEL",
        category="DEW",
        caliber_mm=0.0,
        max_range_m=max_range_m,
        rate_of_fire_rpm=6.0,
        compatible_ammo=["laser_charge"],
        beam_power_kw=beam_power_kw,
        dwell_time_s=dwell_time_s,
        beam_divergence_mrad=beam_divergence_mrad,
        beam_wavelength_nm=beam_wavelength_nm,
    )


def _make_hpm_weapon(
    *,
    beam_power_kw: float = 500.0,
    max_range_m: float = 1000.0,
) -> WeaponDefinition:
    """Create an HPM weapon definition."""
    return WeaponDefinition(
        weapon_id="test_hpm",
        display_name="Test HPM",
        category="DEW",
        caliber_mm=0.0,
        max_range_m=max_range_m,
        rate_of_fire_rpm=2.0,
        compatible_ammo=["hpm_charge"],
        beam_power_kw=beam_power_kw,
    )


def _make_laser_ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="laser_charge",
        display_name="Laser Charge",
        ammo_type="DEW",
        mass_kg=0.0,
        diameter_mm=0.0,
    )


def _make_hpm_ammo() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="hpm_charge",
        display_name="HPM Charge",
        ammo_type="DEW",
        mass_kg=0.0,
        diameter_mm=0.0,
    )


def _make_laser_instance(rounds: int = 10) -> WeaponInstance:
    from stochastic_warfare.combat.ammunition import AmmoState
    defn = _make_laser_weapon()
    state = AmmoState()
    state.add("laser_charge", rounds)
    return WeaponInstance(definition=defn, ammo_state=state)


def _make_hpm_instance(rounds: int = 5) -> WeaponInstance:
    from stochastic_warfare.combat.ammunition import AmmoState
    defn = _make_hpm_weapon()
    state = AmmoState()
    state.add("hpm_charge", rounds)
    return WeaponInstance(definition=defn, ammo_state=state)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAtmosphericTransmittance:
    """Beer-Lambert extinction model."""

    def test_transmittance_decreases_with_range(self):
        eng = _make_engine(seed=1)
        t_close = eng.compute_atmospheric_transmittance(500.0)
        t_far = eng.compute_atmospheric_transmittance(5000.0)
        assert t_close > t_far

    def test_humidity_increases_extinction(self):
        eng = _make_engine(seed=2)
        dry = eng.compute_atmospheric_transmittance(2000.0, humidity=0.1)
        humid = eng.compute_atmospheric_transmittance(2000.0, humidity=0.9)
        assert dry > humid

    def test_fog_adds_extinction(self):
        """Visibility < 1000m should trigger fog extinction."""
        eng = _make_engine(seed=3)
        clear = eng.compute_atmospheric_transmittance(1000.0, visibility=10_000.0)
        foggy = eng.compute_atmospheric_transmittance(1000.0, visibility=500.0)
        assert foggy < clear

    def test_min_transmittance_floor(self):
        """Transmittance should stay >= 0 even at extreme range."""
        eng = _make_engine(seed=4)
        t = eng.compute_atmospheric_transmittance(100_000.0, humidity=1.0)
        assert t >= 0.0

    def test_zero_range_full_transmittance(self):
        eng = _make_engine(seed=5)
        t = eng.compute_atmospheric_transmittance(0.0)
        assert t == pytest.approx(1.0)


class TestLaserPk:
    """Laser dwell-time / thermal-mass Pk model."""

    def test_higher_power_higher_pk(self):
        eng = _make_engine(seed=10)
        weak = _make_laser_weapon(beam_power_kw=10.0)
        strong = _make_laser_weapon(beam_power_kw=500.0)
        pk_weak = eng.compute_laser_pk(weak, 1000.0, 0.9, 50.0)
        pk_strong = eng.compute_laser_pk(strong, 1000.0, 0.9, 50.0)
        assert pk_strong > pk_weak

    def test_higher_thermal_mass_lower_pk(self):
        eng = _make_engine(seed=11)
        weapon = _make_laser_weapon(beam_power_kw=100.0, dwell_time_s=3.0)
        pk_light = eng.compute_laser_pk(weapon, 1000.0, 0.9, 20.0)
        pk_armored = eng.compute_laser_pk(weapon, 1000.0, 0.9, 5000.0)
        assert pk_light > pk_armored

    def test_zero_power_zero_pk(self):
        eng = _make_engine(seed=12)
        weapon = _make_laser_weapon(beam_power_kw=0.0)
        pk = eng.compute_laser_pk(weapon, 1000.0, 0.9, 50.0)
        assert pk == 0.0


class TestHPMPk:
    """HPM inverse-square falloff model."""

    def test_hpm_inverse_square_falloff(self):
        eng = _make_engine(seed=20)
        weapon = _make_hpm_weapon(max_range_m=1000.0)
        pk_close = eng.compute_hpm_pk(weapon, 100.0)
        pk_far = eng.compute_hpm_pk(weapon, 500.0)
        # Inverse square: pk at 100m should be 25x pk at 500m (all else equal)
        assert pk_close > pk_far

    def test_hpm_shielding_reduction(self):
        eng = _make_engine(seed=21)
        weapon = _make_hpm_weapon()
        pk_unshielded = eng.compute_hpm_pk(weapon, 200.0, target_is_shielded=False)
        pk_shielded = eng.compute_hpm_pk(weapon, 200.0, target_is_shielded=True)
        assert pk_shielded < pk_unshielded

    def test_hpm_beyond_max_range(self):
        eng = _make_engine(seed=22)
        weapon = _make_hpm_weapon(max_range_m=500.0)
        pk = eng.compute_hpm_pk(weapon, 600.0)
        assert pk == 0.0


class TestLaserEngagement:
    """execute_laser_engagement full pipeline."""

    def test_laser_engagement_in_range(self):
        eng = _make_engine(seed=30)
        weapon = _make_laser_instance()
        ammo = _make_laser_ammo()
        result = eng.execute_laser_engagement(
            "unit1", "tgt1",
            Position(0, 0, 0), Position(2000, 0, 0),
            weapon, "laser_charge", ammo,
            target_thermal_mass_kj=50.0,
        )
        assert result.engaged is True
        assert result.range_m == pytest.approx(2000.0)
        assert result.pk > 0.0

    def test_laser_engagement_out_of_range(self):
        eng = _make_engine(seed=31)
        weapon = _make_laser_instance()
        ammo = _make_laser_ammo()
        result = eng.execute_laser_engagement(
            "unit1", "tgt1",
            Position(0, 0, 0), Position(10_000, 0, 0),
            weapon, "laser_charge", ammo,
        )
        assert result.engaged is False
        assert result.aborted_reason == "out_of_range"


class TestHPMEngagement:
    """execute_hpm_engagement area effect."""

    def test_hpm_multi_target(self):
        eng = _make_engine(seed=40)
        weapon = _make_hpm_instance()
        ammo = _make_hpm_ammo()
        targets = [
            ("t1", Position(100, 0, 0), False),
            ("t2", Position(200, 0, 0), True),
        ]
        results = eng.execute_hpm_engagement(
            "unit1", Position(0, 0, 0),
            weapon, "hpm_charge", ammo, targets,
        )
        assert len(results) == 2
        assert results[0].target_id == "t1"
        assert results[1].target_id == "t2"
        # Shielded target should have lower Pk
        assert results[1].pk < results[0].pk


class TestStateRoundtrip:
    """State serialization and restoration."""

    def test_state_roundtrip(self):
        eng = _make_engine(seed=50)
        # Advance PRNG state
        eng.compute_atmospheric_transmittance(1000.0)
        state = eng.get_state()

        eng2 = _make_engine(seed=999)
        eng2.set_state(state)

        r1 = eng._rng.random()
        r2 = eng2._rng.random()
        assert r1 == pytest.approx(r2)

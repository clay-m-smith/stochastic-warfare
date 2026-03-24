"""Phase 28.5a — DEW physics engine tests.

Tests atmospheric transmittance, laser Pk, HPM Pk, engagement execution,
and state persistence for the directed energy weapons engine.
"""

from __future__ import annotations

import math

import numpy as np

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    AmmoType,
    WeaponCategory,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.combat.damage import DamageType
from stochastic_warfare.combat.directed_energy import (
    DEWConfig,
    DEWEngine,
    DEWType,
)
from stochastic_warfare.combat.events import DEWEngagementEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from tests.conftest import TS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _bus() -> EventBus:
    return EventBus()


def _engine(seed: int = 42, config: DEWConfig | None = None) -> DEWEngine:
    return DEWEngine(_bus(), _rng(seed), config)


def _laser_weapon(
    power_kw: float = 50.0,
    max_range_m: float = 5000.0,
    dwell_time_s: float = 3.0,
    divergence_mrad: float = 0.5,
    magazine: int = 200,
) -> tuple[WeaponInstance, str, AmmoDefinition]:
    wdef = WeaponDefinition(
        weapon_id="test_laser",
        display_name="Test Laser",
        category="DIRECTED_ENERGY",
        caliber_mm=0.0,
        beam_power_kw=power_kw,
        beam_wavelength_nm=1064.0,
        dwell_time_s=dwell_time_s,
        beam_divergence_mrad=divergence_mrad,
        max_range_m=max_range_m,
        rate_of_fire_rpm=10.0,
        magazine_capacity=magazine,
        compatible_ammo=["dew_charge"],
    )
    ammo_def = AmmoDefinition(
        ammo_id="dew_charge",
        display_name="DEW Charge",
        ammo_type="DIRECTED_ENERGY",
        mass_kg=0.0,
    )
    ammo_state = AmmoState(rounds_by_type={"dew_charge": magazine})
    weapon = WeaponInstance(wdef, ammo_state)
    return weapon, "dew_charge", ammo_def


def _hpm_weapon(
    max_range_m: float = 1000.0,
    magazine: int = 50,
) -> tuple[WeaponInstance, str, AmmoDefinition]:
    wdef = WeaponDefinition(
        weapon_id="test_hpm",
        display_name="Test HPM",
        category="DIRECTED_ENERGY",
        caliber_mm=0.0,
        beam_power_kw=0.0,
        beam_wavelength_nm=0.0,
        max_range_m=max_range_m,
        rate_of_fire_rpm=5.0,
        magazine_capacity=magazine,
        compatible_ammo=["hpm_pulse"],
    )
    ammo_def = AmmoDefinition(
        ammo_id="hpm_pulse",
        display_name="HPM Pulse",
        ammo_type="DIRECTED_ENERGY",
        mass_kg=0.0,
        pk_at_reference=0.9,
    )
    ammo_state = AmmoState(rounds_by_type={"hpm_pulse": magazine})
    weapon = WeaponInstance(wdef, ammo_state)
    return weapon, "hpm_pulse", ammo_def


# ===========================================================================
# DEWConfig
# ===========================================================================


class TestDEWConfig:
    def test_default_values(self) -> None:
        cfg = DEWConfig()
        assert cfg.base_extinction_per_km == 0.2
        assert cfg.min_transmittance == 0.01
        assert cfg.hpm_reference_range_m == 300.0

    def test_custom_override(self) -> None:
        cfg = DEWConfig(base_extinction_per_km=0.5, min_transmittance=0.05)
        assert cfg.base_extinction_per_km == 0.5
        assert cfg.min_transmittance == 0.05

    def test_validation(self) -> None:
        cfg = DEWConfig(fog_extinction_per_km=20.0)
        assert cfg.fog_extinction_per_km == 20.0


# ===========================================================================
# DEWType enum
# ===========================================================================


class TestDEWType:
    def test_values(self) -> None:
        assert DEWType.LASER == 0
        assert DEWType.HPM == 1
        assert len(DEWType) >= 2


# ===========================================================================
# Atmospheric Transmittance
# ===========================================================================


class TestAtmosphericTransmittance:
    def test_clear_air_short_range(self) -> None:
        eng = _engine()
        t = eng.compute_atmospheric_transmittance(100.0, humidity=0.0)
        # 100m, 0 humidity → very high transmittance
        assert t > 0.95

    def test_clear_air_long_range(self) -> None:
        eng = _engine()
        t = eng.compute_atmospheric_transmittance(10000.0, humidity=0.0)
        # 10km, clear → exp(-0.2 * 10) = exp(-2) ≈ 0.135
        assert abs(t - math.exp(-2.0)) < 0.01

    def test_humidity_increases_extinction(self) -> None:
        eng = _engine()
        t_dry = eng.compute_atmospheric_transmittance(5000.0, humidity=0.0)
        t_humid = eng.compute_atmospheric_transmittance(5000.0, humidity=0.9)
        assert t_humid < t_dry

    def test_rain_increases_extinction(self) -> None:
        eng = _engine()
        t_clear = eng.compute_atmospheric_transmittance(3000.0, precipitation_rate=0.0)
        t_rain = eng.compute_atmospheric_transmittance(3000.0, precipitation_rate=10.0)
        assert t_rain < t_clear

    def test_fog_severe_extinction(self) -> None:
        eng = _engine()
        t_clear = eng.compute_atmospheric_transmittance(2000.0, visibility=10000.0)
        t_fog = eng.compute_atmospheric_transmittance(2000.0, visibility=500.0)
        assert t_fog < t_clear * 0.1  # fog causes massive reduction

    def test_zero_range_returns_one(self) -> None:
        eng = _engine()
        t = eng.compute_atmospheric_transmittance(0.0)
        assert t == 1.0

    def test_extreme_range_near_zero(self) -> None:
        eng = _engine()
        t = eng.compute_atmospheric_transmittance(100000.0, humidity=0.5)
        assert t < 0.001

    def test_bounds_zero_to_one(self) -> None:
        eng = _engine()
        for r in [0, 100, 1000, 5000, 50000]:
            t = eng.compute_atmospheric_transmittance(float(r))
            assert 0.0 <= t <= 1.0

    def test_fog_threshold_exactly_1000m(self) -> None:
        eng = _engine()
        t_below = eng.compute_atmospheric_transmittance(1000.0, visibility=999.0)
        t_at = eng.compute_atmospheric_transmittance(1000.0, visibility=1000.0)
        assert t_below < t_at  # fog kicks in below 1000m vis

    def test_combined_weather_effects(self) -> None:
        eng = _engine()
        t = eng.compute_atmospheric_transmittance(
            5000.0, humidity=0.8, precipitation_rate=5.0, visibility=800.0,
        )
        # All effects combined → very low transmittance
        assert t < 0.01


# ===========================================================================
# Laser Pk
# ===========================================================================


class TestLaserPk:
    def test_close_range_high_power_high_pk(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(power_kw=100.0, dwell_time_s=5.0)
        pk = eng.compute_laser_pk(weapon.definition, 500.0, 0.95, 50.0)
        # 100kW * 0.95 * 5s = 475 kJ vs 50 kJ → very high Pk
        assert pk > 0.9

    def test_long_range_lower_pk(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(power_kw=50.0)
        pk_close = eng.compute_laser_pk(weapon.definition, 1000.0, 0.9, 50.0)
        pk_far = eng.compute_laser_pk(weapon.definition, 4500.0, 0.5, 50.0)
        assert pk_far < pk_close

    def test_armored_target_lower_pk(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(power_kw=50.0, dwell_time_s=3.0)
        pk_soft = eng.compute_laser_pk(weapon.definition, 2000.0, 0.8, 50.0)
        pk_armored = eng.compute_laser_pk(weapon.definition, 2000.0, 0.8, 5000.0)
        assert pk_armored < pk_soft

    def test_zero_transmittance_zero_pk(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon()
        pk = eng.compute_laser_pk(weapon.definition, 1000.0, 0.0, 50.0)
        assert pk == 0.0

    def test_zero_power_zero_pk(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(power_kw=0.0)
        pk = eng.compute_laser_pk(weapon.definition, 1000.0, 0.9, 50.0)
        assert pk == 0.0

    def test_zero_dwell_zero_pk(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(dwell_time_s=0.0)
        pk = eng.compute_laser_pk(weapon.definition, 1000.0, 0.9, 50.0)
        assert pk == 0.0

    def test_pk_bounded_above(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(power_kw=1000.0, dwell_time_s=10.0)
        pk = eng.compute_laser_pk(weapon.definition, 100.0, 1.0, 1.0)
        assert pk <= 0.99

    def test_pk_bounded_below(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(power_kw=0.1, dwell_time_s=0.1)
        pk = eng.compute_laser_pk(weapon.definition, 5000.0, 0.1, 5000.0)
        assert pk >= 0.0

    def test_divergence_affects_pk(self) -> None:
        eng = _engine()
        weapon_tight, _, _ = _laser_weapon(divergence_mrad=0.1)
        weapon_wide, _, _ = _laser_weapon(divergence_mrad=2.0)
        pk_tight = eng.compute_laser_pk(weapon_tight.definition, 2000.0, 0.9, 50.0)
        pk_wide = eng.compute_laser_pk(weapon_wide.definition, 2000.0, 0.9, 50.0)
        # Tighter beam at close range → more concentrated energy
        assert pk_tight >= pk_wide

    def test_no_divergence_full_aperture(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(divergence_mrad=0.0, power_kw=50.0, dwell_time_s=3.0)
        pk = eng.compute_laser_pk(weapon.definition, 2000.0, 0.9, 50.0)
        # No divergence → aperture_factor = 1.0 → full power
        expected_energy = 50.0 * 0.9 * 3.0
        expected_pk = 1.0 - math.exp(-expected_energy / 50.0)
        assert abs(pk - min(0.99, expected_pk)) < 0.01

    def test_exponential_damage_model(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon(power_kw=50.0, dwell_time_s=1.0, divergence_mrad=0.0)
        # energy = 50 * 0.9 * 1 = 45 kJ, target = 50 kJ
        pk = eng.compute_laser_pk(weapon.definition, 1000.0, 0.9, 50.0)
        expected = 1.0 - math.exp(-45.0 / 50.0)
        assert abs(pk - expected) < 0.01

    def test_negative_thermal_mass_returns_zero(self) -> None:
        eng = _engine()
        weapon, _, _ = _laser_weapon()
        pk = eng.compute_laser_pk(weapon.definition, 1000.0, 0.9, -10.0)
        assert pk == 0.0


# ===========================================================================
# HPM Pk
# ===========================================================================


class TestHPMPk:
    def test_at_reference_range(self) -> None:
        eng = _engine()
        weapon, _, _ = _hpm_weapon()
        pk = eng.compute_hpm_pk(weapon.definition, 300.0)
        # At reference range: 0.9 * (300/300)^2 * 1.0 = 0.9
        assert abs(pk - 0.9) < 0.01

    def test_inverse_square_falloff(self) -> None:
        eng = _engine()
        weapon, _, _ = _hpm_weapon()
        pk_300 = eng.compute_hpm_pk(weapon.definition, 300.0)
        pk_600 = eng.compute_hpm_pk(weapon.definition, 600.0)
        # At 2x range, power density is 1/4
        assert abs(pk_600 / pk_300 - 0.25) < 0.05

    def test_shielded_target_lower_pk(self) -> None:
        eng = _engine()
        weapon, _, _ = _hpm_weapon()
        pk_unshielded = eng.compute_hpm_pk(weapon.definition, 300.0, target_is_shielded=False)
        pk_shielded = eng.compute_hpm_pk(weapon.definition, 300.0, target_is_shielded=True)
        assert pk_shielded < pk_unshielded
        # Shielding factor = 0.3
        assert abs(pk_shielded / pk_unshielded - 0.3) < 0.05

    def test_close_range_high_pk(self) -> None:
        eng = _engine()
        weapon, _, _ = _hpm_weapon()
        pk = eng.compute_hpm_pk(weapon.definition, 50.0)
        assert pk == 0.99  # Capped at 0.99

    def test_beyond_max_range_zero(self) -> None:
        eng = _engine()
        weapon, _, _ = _hpm_weapon(max_range_m=1000.0)
        pk = eng.compute_hpm_pk(weapon.definition, 1500.0)
        assert pk == 0.0

    def test_very_far_range_near_zero(self) -> None:
        eng = _engine()
        weapon, _, _ = _hpm_weapon(max_range_m=10000.0)
        pk = eng.compute_hpm_pk(weapon.definition, 5000.0)
        # (300/5000)^2 = 0.0036, * 0.9 ≈ 0.003
        assert pk < 0.01

    def test_zero_range_clamped(self) -> None:
        eng = _engine()
        weapon, _, _ = _hpm_weapon()
        pk = eng.compute_hpm_pk(weapon.definition, 0.0)
        # range clamped to 1m → very high pk, capped at 0.99
        assert pk == 0.99

    def test_pk_bounded(self) -> None:
        eng = _engine()
        weapon, _, _ = _hpm_weapon()
        for r in [10, 100, 300, 500, 900]:
            pk = eng.compute_hpm_pk(weapon.definition, float(r))
            assert 0.0 <= pk <= 0.99


# ===========================================================================
# Laser Engagement (execute)
# ===========================================================================


class TestLaserEngagement:
    def test_hit_engagement(self) -> None:
        bus = _bus()
        eng = DEWEngine(bus, _rng(0), DEWConfig())  # seed for consistent roll
        weapon, ammo_id, ammo_def = _laser_weapon(power_kw=100.0, dwell_time_s=5.0)

        result = eng.execute_laser_engagement(
            attacker_id="unit_a", target_id="unit_b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(500, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            target_thermal_mass_kj=50.0,
        )
        assert result.engaged
        assert result.pk > 0.5
        assert result.damage_type == "THERMAL_ENERGY"
        assert result.transmittance > 0.7

    def test_miss_engagement(self) -> None:
        eng = _engine(seed=42)
        weapon, ammo_id, ammo_def = _laser_weapon(power_kw=1.0, dwell_time_s=0.1)

        result = eng.execute_laser_engagement(
            attacker_id="unit_a", target_id="unit_b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(4000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            target_thermal_mass_kj=5000.0,
        )
        assert result.engaged
        assert result.pk < 0.05

    def test_out_of_range(self) -> None:
        eng = _engine()
        weapon, ammo_id, ammo_def = _laser_weapon(max_range_m=5000.0)

        result = eng.execute_laser_engagement(
            attacker_id="unit_a", target_id="unit_b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(6000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
        )
        assert not result.engaged
        assert result.aborted_reason == "out_of_range"

    def test_low_transmittance_abort(self) -> None:
        eng = _engine(config=DEWConfig(min_transmittance=0.5))
        weapon, ammo_id, ammo_def = _laser_weapon()

        result = eng.execute_laser_engagement(
            attacker_id="unit_a", target_id="unit_b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(3000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            visibility=500.0,  # fog
        )
        assert not result.engaged
        assert result.aborted_reason == "low_transmittance"

    def test_ammo_consumed(self) -> None:
        eng = _engine()
        weapon, ammo_id, ammo_def = _laser_weapon(magazine=5)

        initial = weapon.ammo_state.available(ammo_id)
        eng.execute_laser_engagement(
            attacker_id="a", target_id="b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(1000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
        )
        assert weapon.ammo_state.available(ammo_id) == initial - 1

    def test_no_ammo(self) -> None:
        eng = _engine()
        weapon, ammo_id, ammo_def = _laser_weapon(magazine=0)
        weapon.ammo_state.rounds_by_type["dew_charge"] = 0

        result = eng.execute_laser_engagement(
            attacker_id="a", target_id="b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(1000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
        )
        assert not result.engaged
        assert result.aborted_reason == "no_ammo"

    def test_event_published_on_hit(self) -> None:
        bus = _bus()
        events: list[DEWEngagementEvent] = []
        bus.subscribe(DEWEngagementEvent, events.append)

        eng = DEWEngine(bus, _rng(0), DEWConfig())
        weapon, ammo_id, ammo_def = _laser_weapon(power_kw=100.0, dwell_time_s=5.0)

        eng.execute_laser_engagement(
            attacker_id="a", target_id="b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(500, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            target_thermal_mass_kj=50.0,
            timestamp=TS,
        )
        assert len(events) == 1
        assert events[0].dew_type == "LASER"

    def test_weather_affects_engagement(self) -> None:
        eng = _engine()
        weapon_c, ammo_id, ammo_def = _laser_weapon(power_kw=50.0)
        weapon_r, _, _ = _laser_weapon(power_kw=50.0)

        res_clear = eng.execute_laser_engagement(
            attacker_id="a", target_id="b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(2000, 0, 0),
            weapon=weapon_c, ammo_id=ammo_id, ammo_def=ammo_def,
            humidity=0.2, precipitation_rate=0.0,
        )
        eng2 = _engine()
        res_rain = eng2.execute_laser_engagement(
            attacker_id="a", target_id="b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(2000, 0, 0),
            weapon=weapon_r, ammo_id=ammo_id, ammo_def=ammo_def,
            humidity=0.9, precipitation_rate=20.0,
        )
        assert res_rain.pk < res_clear.pk

    def test_3d_range(self) -> None:
        eng = _engine()
        weapon, ammo_id, ammo_def = _laser_weapon()

        result = eng.execute_laser_engagement(
            attacker_id="a", target_id="b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(3000, 4000, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
        )
        assert result.engaged
        assert abs(result.range_m - 5000.0) < 1.0

    def test_no_event_without_timestamp(self) -> None:
        bus = _bus()
        events: list[DEWEngagementEvent] = []
        bus.subscribe(DEWEngagementEvent, events.append)

        eng = DEWEngine(bus, _rng(0))
        weapon, ammo_id, ammo_def = _laser_weapon()

        eng.execute_laser_engagement(
            attacker_id="a", target_id="b",
            shooter_pos=Position(0, 0, 0), target_pos=Position(1000, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            timestamp=None,
        )
        assert len(events) == 0


# ===========================================================================
# HPM Engagement (execute)
# ===========================================================================


class TestHPMEngagement:
    def test_multiple_targets(self) -> None:
        eng = _engine(seed=0)
        weapon, ammo_id, ammo_def = _hpm_weapon()

        targets = [
            ("drone_1", Position(200, 0, 0), False),
            ("drone_2", Position(250, 0, 0), False),
            ("drone_3", Position(100, 0, 0), True),
        ]
        results = eng.execute_hpm_engagement(
            attacker_id="hpm_unit",
            shooter_pos=Position(0, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            targets=targets,
        )
        assert len(results) == 3
        assert all(r.engaged for r in results)
        assert all(r.damage_type == "ELECTRONIC" for r in results)

    def test_mixed_shielding(self) -> None:
        eng = _engine()
        weapon, ammo_id, ammo_def = _hpm_weapon()

        targets = [
            ("soft", Position(300, 0, 0), False),
            ("hard", Position(300, 0, 0), True),
        ]
        results = eng.execute_hpm_engagement(
            attacker_id="hpm_unit",
            shooter_pos=Position(0, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            targets=targets,
        )
        assert results[0].pk > results[1].pk

    def test_out_of_range_target(self) -> None:
        eng = _engine()
        weapon, ammo_id, ammo_def = _hpm_weapon(max_range_m=500.0)

        targets = [
            ("close", Position(200, 0, 0), False),
            ("far", Position(800, 0, 0), False),
        ]
        results = eng.execute_hpm_engagement(
            attacker_id="hpm_unit",
            shooter_pos=Position(0, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            targets=targets,
        )
        assert results[0].engaged
        assert not results[1].engaged
        assert results[1].aborted_reason == "out_of_range"

    def test_ammo_consumed_once_per_burst(self) -> None:
        eng = _engine()
        weapon, ammo_id, ammo_def = _hpm_weapon(magazine=10)

        initial = weapon.ammo_state.available(ammo_id)
        targets = [
            ("d1", Position(100, 0, 0), False),
            ("d2", Position(200, 0, 0), False),
        ]
        eng.execute_hpm_engagement(
            attacker_id="hpm_unit",
            shooter_pos=Position(0, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            targets=targets,
        )
        # Only 1 charge consumed regardless of target count
        assert weapon.ammo_state.available(ammo_id) == initial - 1

    def test_no_ammo(self) -> None:
        eng = _engine()
        weapon, ammo_id, ammo_def = _hpm_weapon(magazine=0)
        weapon.ammo_state.rounds_by_type["hpm_pulse"] = 0

        results = eng.execute_hpm_engagement(
            attacker_id="hpm_unit",
            shooter_pos=Position(0, 0, 0),
            weapon=weapon, ammo_id=ammo_id, ammo_def=ammo_def,
            targets=[("d1", Position(100, 0, 0), False)],
        )
        assert len(results) == 1
        assert not results[0].engaged
        assert results[0].aborted_reason == "no_ammo"


# ===========================================================================
# State persistence
# ===========================================================================


class TestDEWState:
    def test_get_set_state_roundtrip(self) -> None:
        eng1 = _engine(seed=99)
        # Advance RNG state
        eng1._rng.random()
        eng1._rng.random()

        state = eng1.get_state()
        eng2 = _engine(seed=0)  # different seed
        eng2.set_state(state)

        # After set_state, both should produce same next value
        v1 = eng1._rng.random()
        v2 = eng2._rng.random()
        assert v1 == v2

    def test_empty_engine_state(self) -> None:
        eng = _engine()
        state = eng.get_state()
        assert "rng_state" in state


# ===========================================================================
# Enum extensions
# ===========================================================================


class TestEnumExtensions:
    def test_weapon_category_directed_energy(self) -> None:
        assert WeaponCategory.DIRECTED_ENERGY == 12
        assert WeaponCategory["DIRECTED_ENERGY"] == 12

    def test_ammo_type_directed_energy(self) -> None:
        assert AmmoType.DIRECTED_ENERGY == 14
        assert AmmoType["DIRECTED_ENERGY"] == 14

    def test_damage_type_thermal_energy(self) -> None:
        assert DamageType.THERMAL_ENERGY == 5

    def test_damage_type_electronic(self) -> None:
        assert DamageType.ELECTRONIC == 6

    def test_weapon_definition_dew_fields(self) -> None:
        wdef = WeaponDefinition(
            weapon_id="test",
            display_name="Test",
            category="DIRECTED_ENERGY",
            caliber_mm=0.0,
            beam_power_kw=50.0,
            beam_wavelength_nm=1064.0,
            dwell_time_s=3.0,
            beam_divergence_mrad=0.5,
        )
        assert wdef.beam_power_kw == 50.0
        assert wdef.beam_wavelength_nm == 1064.0
        assert wdef.dwell_time_s == 3.0
        assert wdef.beam_divergence_mrad == 0.5

    def test_weapon_definition_dew_defaults(self) -> None:
        wdef = WeaponDefinition(
            weapon_id="test",
            display_name="Test",
            category="CANNON",
            caliber_mm=120.0,
        )
        assert wdef.beam_power_kw == 0.0
        assert wdef.beam_wavelength_nm == 0.0
        assert wdef.dwell_time_s == 0.0
        assert wdef.beam_divergence_mrad == 0.0

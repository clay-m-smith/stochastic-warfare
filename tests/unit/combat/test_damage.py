"""Unit tests for DamageEngine, IncendiaryDamageEngine, and UXOEngine."""

from __future__ import annotations


from stochastic_warfare.combat.damage import (
    BurnedZone,
    DamageConfig,
    DamageEngine,
    DamageType,
    IncendiaryDamageEngine,
    UXOEngine,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import Position

from .conftest import _make_ap, _make_he, _make_heat, _rng


# ---------------------------------------------------------------------------
# DamageEngine — penetration
# ---------------------------------------------------------------------------


class TestDamageEnginePenetration:
    """DeMarre penetration and behind-armor effects."""

    def test_ap_penetrates_thin_armor(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_ap(penetration_mm_rha=400.0)
        result = eng.compute_penetration(ammo, armor_mm=100.0)
        assert result.penetrated
        assert result.margin_mm > 0

    def test_ap_stopped_by_thick_armor(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_ap(penetration_mm_rha=100.0)
        result = eng.compute_penetration(ammo, armor_mm=500.0)
        assert not result.penetrated
        assert result.margin_mm < 0

    def test_heat_ignores_range_decay(self):
        """HEAT penetration is independent of range (shaped charge)."""
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_heat(penetration_mm_rha=600.0)
        near = eng.compute_penetration(ammo, armor_mm=200.0, range_m=100.0)
        far = eng.compute_penetration(ammo, armor_mm=200.0, range_m=5000.0)
        assert near.penetration_mm == far.penetration_mm

    def test_composite_armor_multiplier_vs_heat(self):
        """COMPOSITE armor is 2.5x effective vs HEAT."""
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_heat(penetration_mm_rha=600.0)
        rha = eng.compute_penetration(ammo, armor_mm=300.0, armor_type="RHA")
        comp = eng.compute_penetration(ammo, armor_mm=300.0, armor_type="COMPOSITE")
        # Composite should have higher effective armor
        assert comp.armor_effective_mm > rha.armor_effective_mm

    def test_oblique_impact_increases_effective_armor(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_ap(penetration_mm_rha=400.0)
        normal = eng.compute_penetration(ammo, armor_mm=200.0, impact_angle_deg=0.0)
        oblique = eng.compute_penetration(ammo, armor_mm=200.0, impact_angle_deg=60.0)
        assert oblique.armor_effective_mm > normal.armor_effective_mm

    def test_extreme_obliquity_ricochet(self):
        """Impact angle > 75° causes ricochet (no penetration)."""
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_ap(penetration_mm_rha=1000.0)
        result = eng.compute_penetration(ammo, armor_mm=10.0, impact_angle_deg=80.0)
        assert not result.penetrated

    def test_zero_penetration_ammo(self):
        """Ammo with zero penetration never penetrates."""
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_ap(penetration_mm_rha=0.0)
        result = eng.compute_penetration(ammo, armor_mm=50.0)
        assert not result.penetrated


# ---------------------------------------------------------------------------
# DamageEngine — blast
# ---------------------------------------------------------------------------


class TestDamageEngineBlast:
    """Hopkinson-Cranz overpressure and fragmentation."""

    def test_blast_damage_at_zero_distance(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_he(blast_radius_m=50.0, explosive_fill_kg=6.6)
        result = eng.apply_blast_damage(ammo, distance_m=0.1)
        assert result.damage_fraction > 0.5

    def test_blast_damage_decreases_with_distance(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_he(blast_radius_m=50.0, explosive_fill_kg=6.6)
        near = eng.apply_blast_damage(ammo, distance_m=5.0)
        far = eng.apply_blast_damage(ammo, distance_m=100.0)
        assert near.damage_fraction >= far.damage_fraction

    def test_zero_blast_radius_no_damage(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_he(blast_radius_m=0.0, fragmentation_radius_m=0.0)
        result = eng.apply_blast_damage(ammo, distance_m=10.0)
        assert result.damage_fraction == 0.0

    def test_dug_in_posture_reduces_blast(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_he(blast_radius_m=50.0, explosive_fill_kg=6.6)
        moving = eng.apply_blast_damage(ammo, distance_m=15.0, posture="MOVING")
        dug_in = eng.apply_blast_damage(ammo, distance_m=15.0, posture="DUG_IN")
        assert dug_in.damage_fraction <= moving.damage_fraction

    def test_fragmentation_1_over_r2(self):
        """Fragmentation uses 1/r² falloff within frag radius."""
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_he(blast_radius_m=0.0, fragmentation_radius_m=100.0)
        close = eng.apply_blast_damage(ammo, distance_m=10.0)
        mid = eng.apply_blast_damage(ammo, distance_m=50.0)
        assert close.damage_fraction > mid.damage_fraction > 0.0

    def test_legacy_gaussian_blast_model(self):
        """use_overpressure_blast=False uses Gaussian model."""
        cfg = DamageConfig(use_overpressure_blast=False)
        eng = DamageEngine(EventBus(), _rng(), config=cfg)
        ammo = _make_he(blast_radius_m=50.0)
        result = eng.apply_blast_damage(ammo, distance_m=10.0)
        assert result.damage_fraction > 0.0

    def test_custom_damage_config(self):
        cfg = DamageConfig(demare_exponent=2.0, spall_probability=0.5)
        eng = DamageEngine(EventBus(), _rng(), config=cfg)
        assert eng._config.demare_exponent == 2.0
        assert eng._config.spall_probability == 0.5


# ---------------------------------------------------------------------------
# DamageEngine — resolve_damage integration
# ---------------------------------------------------------------------------


class TestDamageEngineResolveDamage:
    """Full damage resolution path."""

    def test_kinetic_vs_unarmored(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_ap(penetration_mm_rha=400.0)
        result = eng.resolve_damage("target_1", ammo, armor_mm=0.0)
        assert result.penetrated
        assert result.damage_fraction > 0.0
        assert result.damage_type == DamageType.KINETIC

    def test_he_vs_unarmored(self):
        eng = DamageEngine(EventBus(), _rng())
        ammo = _make_he()
        result = eng.resolve_damage("target_1", ammo, armor_mm=0.0, distance_from_impact_m=10.0)
        assert result.damage_fraction > 0.0

    def test_state_roundtrip(self):
        eng = DamageEngine(EventBus(), _rng(seed=99))
        state = eng.get_state()
        eng2 = DamageEngine(EventBus(), _rng(seed=1))
        eng2.set_state(state)
        # After set_state, engines should produce same random sequence
        assert eng._rng.random() == eng2._rng.random()


# ---------------------------------------------------------------------------
# IncendiaryDamageEngine
# ---------------------------------------------------------------------------


class TestIncendiaryDamageEngine:
    """Fire zone creation, expansion, burnout."""

    def test_create_fire_zone(self):
        eng = IncendiaryDamageEngine(_rng())
        zone = eng.create_fire_zone(
            position=Position(100.0, 200.0, 0.0),
            radius_m=20.0,
            fuel_load=0.8,
            wind_speed_mps=5.0,
            wind_dir_rad=0.0,
            duration_s=300.0,
            timestamp=0.0,
        )
        assert zone.zone_id == "fire_1"
        assert zone.radius_m == 20.0
        assert zone.current_radius_m == 20.0

    def test_update_expands_radius(self):
        eng = IncendiaryDamageEngine(_rng())
        eng.create_fire_zone(
            position=Position(0.0, 0.0, 0.0),
            radius_m=10.0,
            fuel_load=1.0,
            wind_speed_mps=10.0,
            wind_dir_rad=0.0,
            duration_s=600.0,
            timestamp=0.0,
        )
        active = eng.update_fire_zones(dt=60.0)
        assert len(active) == 1
        assert active[0].current_radius_m > 10.0

    def test_expired_zone_becomes_burned(self):
        eng = IncendiaryDamageEngine(_rng())
        eng.create_fire_zone(
            position=Position(0.0, 0.0, 0.0),
            radius_m=10.0,
            fuel_load=0.5,
            wind_speed_mps=2.0,
            wind_dir_rad=0.0,
            duration_s=10.0,
            timestamp=0.0,
        )
        active = eng.update_fire_zones(dt=15.0)
        assert len(active) == 0
        burned = eng.get_burned_zones()
        assert len(burned) == 1
        assert isinstance(burned[0], BurnedZone)

    def test_state_roundtrip(self):
        eng = IncendiaryDamageEngine(_rng(seed=7))
        eng.create_fire_zone(
            position=Position(50.0, 50.0, 0.0),
            radius_m=15.0,
            fuel_load=0.6,
            wind_speed_mps=3.0,
            wind_dir_rad=1.0,
            duration_s=100.0,
            timestamp=5.0,
        )
        state = eng.get_state()
        eng2 = IncendiaryDamageEngine(_rng(seed=1))
        eng2.set_state(state)
        assert eng2._zone_counter == 1
        assert len(eng2._active_zones) == 1
        assert eng2._active_zones[0].zone_id == "fire_1"


# ---------------------------------------------------------------------------
# UXOEngine
# ---------------------------------------------------------------------------


class TestUXOEngine:
    """UXO field creation and encounter checks."""

    def test_create_uxo_field(self):
        eng = UXOEngine(_rng())
        field = eng.create_uxo_field(
            position=Position(0.0, 0.0, 0.0),
            radius_m=100.0,
            submunition_count=88,
            uxo_rate=0.05,
            timestamp=0.0,
        )
        assert field.field_id == "uxo_1"
        assert field.density > 0.0
        assert len(eng.get_fields()) == 1

    def test_encounter_inside_field(self):
        """Unit inside UXO field has nonzero encounter probability."""
        rng = _rng(seed=0)
        eng = UXOEngine(rng)
        eng.create_uxo_field(
            position=Position(0.0, 0.0, 0.0),
            radius_m=50.0,
            submunition_count=1000,
            uxo_rate=0.3,
            timestamp=0.0,
        )
        # With high density, at least one of many checks should trigger
        encounters = sum(
            eng.check_uxo_encounter(Position(10.0, 10.0, 0.0))
            for _ in range(100)
        )
        assert encounters > 0

    def test_encounter_outside_field(self):
        """Unit outside all UXO fields never encounters UXO."""
        eng = UXOEngine(_rng())
        eng.create_uxo_field(
            position=Position(0.0, 0.0, 0.0),
            radius_m=10.0,
            submunition_count=100,
            uxo_rate=0.1,
            timestamp=0.0,
        )
        assert not eng.check_uxo_encounter(Position(500.0, 500.0, 0.0))

    def test_state_roundtrip(self):
        eng = UXOEngine(_rng(seed=3))
        eng.create_uxo_field(
            position=Position(10.0, 20.0, 0.0),
            radius_m=30.0,
            submunition_count=50,
            uxo_rate=0.1,
            timestamp=10.0,
        )
        state = eng.get_state()
        eng2 = UXOEngine(_rng(seed=1))
        eng2.set_state(state)
        assert eng2._field_counter == 1
        assert len(eng2._fields) == 1
        assert eng2._fields[0].field_id == "uxo_1"

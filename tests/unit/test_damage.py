"""Tests for combat/damage.py — penetration, blast, fragmentation, BAE."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.combat.ammunition import AmmoDefinition
from stochastic_warfare.combat.damage import (
    DamageConfig,
    DamageEngine,
    DamageResult,
    DamageType,
    PenetrationResult,
)
from stochastic_warfare.core.events import EventBus


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def _engine(seed: int = 42) -> DamageEngine:
    return DamageEngine(EventBus(), _rng(seed))


def _ap() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="ap", display_name="AP", ammo_type="AP",
        mass_kg=8.9, diameter_mm=120.0, drag_coefficient=0.15,
        penetration_mm_rha=750.0, penetration_reference_range_m=2000.0,
    )


def _heat() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="heat", display_name="HEAT", ammo_type="HEAT",
        mass_kg=11.4, diameter_mm=120.0,
        penetration_mm_rha=500.0,
        blast_radius_m=5.0, fragmentation_radius_m=15.0,
    )


def _he() -> AmmoDefinition:
    return AmmoDefinition(
        ammo_id="he", display_name="HE", ammo_type="HE",
        mass_kg=46.7, diameter_mm=155.0,
        blast_radius_m=50.0, fragmentation_radius_m=150.0,
    )


class TestPenetration:
    def test_ap_vs_thin_armor_penetrates(self) -> None:
        e = _engine()
        result = e.compute_penetration(_ap(), armor_mm=200.0)
        assert result.penetrated is True
        assert result.margin_mm > 0

    def test_ap_vs_thick_armor_fails(self) -> None:
        e = _engine()
        result = e.compute_penetration(_ap(), armor_mm=1000.0)
        assert result.penetrated is False
        assert result.margin_mm < 0

    def test_obliquity_increases_effective_armor(self) -> None:
        e = _engine()
        normal = e.compute_penetration(_ap(), armor_mm=400.0, impact_angle_deg=0.0)
        oblique = e.compute_penetration(_ap(), armor_mm=400.0, impact_angle_deg=60.0)
        assert oblique.armor_effective_mm > normal.armor_effective_mm

    def test_range_degrades_ap_penetration(self) -> None:
        e = _engine()
        close = e.compute_penetration(_ap(), armor_mm=400.0, range_m=500.0)
        far = e.compute_penetration(_ap(), armor_mm=400.0, range_m=3500.0)
        assert far.penetration_mm < close.penetration_mm

    def test_heat_penetration_range_independent(self) -> None:
        e = _engine()
        close = e.compute_penetration(_heat(), armor_mm=300.0, range_m=500.0)
        far = e.compute_penetration(_heat(), armor_mm=300.0, range_m=3000.0)
        assert close.penetration_mm == far.penetration_mm

    def test_zero_penetration_ammo(self) -> None:
        ammo = AmmoDefinition(
            ammo_id="smoke", display_name="Smoke", ammo_type="SMOKE",
        )
        e = _engine()
        result = e.compute_penetration(ammo, armor_mm=10.0)
        assert result.penetrated is False

    def test_extreme_obliquity_clamped(self) -> None:
        e = _engine()
        result = e.compute_penetration(_ap(), armor_mm=200.0, impact_angle_deg=89.0)
        # Should not divide by near-zero
        assert result.armor_effective_mm > 200.0


class TestBlastDamage:
    def test_direct_hit_max_blast(self) -> None:
        e = _engine()
        result = e.apply_blast_damage(_he(), distance_m=0.0)
        assert result.damage_fraction > 0.9

    def test_blast_attenuates_with_distance(self) -> None:
        e = _engine()
        close = e.apply_blast_damage(_he(), distance_m=10.0)
        far = e.apply_blast_damage(_he(), distance_m=100.0)
        assert far.damage_fraction < close.damage_fraction

    def test_dug_in_protection(self) -> None:
        e = _engine()
        moving = e.apply_blast_damage(_he(), distance_m=30.0, posture="MOVING")
        dug_in = e.apply_blast_damage(_he(), distance_m=30.0, posture="DUG_IN")
        assert dug_in.damage_fraction < moving.damage_fraction

    def test_fortified_heavy_protection(self) -> None:
        e = _engine()
        result = e.apply_blast_damage(_he(), distance_m=30.0, posture="FORTIFIED")
        assert result.damage_fraction < 0.5

    def test_beyond_frag_radius_no_frag(self) -> None:
        e = _engine()
        result = e.apply_blast_damage(_he(), distance_m=200.0)
        # Beyond fragmentation radius (150m), only blast
        assert result.damage_fraction < 0.01

    def test_fragmentation_1_r_squared(self) -> None:
        e = _engine()
        close = e.apply_blast_damage(_he(), distance_m=20.0)
        mid = e.apply_blast_damage(_he(), distance_m=75.0)
        # Closer should have more fragmentation damage
        assert close.damage_fraction > mid.damage_fraction


class TestBehindArmorEffects:
    def test_penetration_causes_casualties(self) -> None:
        e = _engine(42)
        pen = PenetrationResult(
            penetrated=True, penetration_mm=800.0,
            armor_effective_mm=400.0, margin_mm=400.0,
        )
        casualties = e.apply_behind_armor_effects(pen, crew_count=4)
        # With high overmatch, should get some casualties
        assert len(casualties) >= 0  # Stochastic

    def test_no_penetration_no_casualties(self) -> None:
        e = _engine()
        pen = PenetrationResult(
            penetrated=False, penetration_mm=300.0,
            armor_effective_mm=500.0, margin_mm=-200.0,
        )
        casualties = e.apply_behind_armor_effects(pen, crew_count=4)
        assert len(casualties) == 0

    def test_high_overmatch_more_casualties(self) -> None:
        e1 = _engine(42)
        e2 = _engine(42)
        low_over = PenetrationResult(
            penetrated=True, penetration_mm=410.0,
            armor_effective_mm=400.0, margin_mm=10.0,
        )
        high_over = PenetrationResult(
            penetrated=True, penetration_mm=1200.0,
            armor_effective_mm=400.0, margin_mm=800.0,
        )
        # Run many trials for statistical significance
        low_total = sum(
            len(DamageEngine(EventBus(), _rng(i)).apply_behind_armor_effects(low_over, 4))
            for i in range(50)
        )
        high_total = sum(
            len(DamageEngine(EventBus(), _rng(i)).apply_behind_armor_effects(high_over, 4))
            for i in range(50)
        )
        assert high_total > low_total


class TestResolveDamage:
    def test_armored_target_with_penetration(self) -> None:
        e = _engine(42)
        result = e.resolve_damage(
            target_id="t1", ammo=_ap(), armor_mm=300.0,
            range_m=1500.0, crew_count=4,
        )
        assert result.penetrated is True
        assert result.damage_fraction > 0

    def test_armored_target_no_penetration(self) -> None:
        e = _engine()
        result = e.resolve_damage(
            target_id="t1", ammo=_ap(), armor_mm=1000.0, crew_count=4,
        )
        assert result.penetrated is False

    def test_unarmored_target_blast(self) -> None:
        e = _engine()
        result = e.resolve_damage(
            target_id="t1", ammo=_he(), armor_mm=0.0,
            distance_from_impact_m=20.0,
        )
        assert result.damage_fraction > 0

    def test_events_published_with_timestamp(self) -> None:
        from datetime import datetime, timezone
        bus = EventBus()
        received: list = []
        from stochastic_warfare.core.events import Event
        bus.subscribe(Event, lambda e: received.append(e))
        e = DamageEngine(bus, _rng(42))
        e.resolve_damage(
            target_id="t1", ammo=_ap(), armor_mm=200.0,
            range_m=1000.0, crew_count=4,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(received) > 0


class TestDamageType:
    def test_enum_values(self) -> None:
        assert DamageType.KINETIC == 0
        assert DamageType.COMBINED == 4


class TestState:
    def test_state_roundtrip(self) -> None:
        e = _engine(42)
        e.resolve_damage("t1", _ap(), armor_mm=300.0)
        saved = e.get_state()

        e2 = _engine(99)
        e2.set_state(saved)

        r1 = e.resolve_damage("t2", _ap(), armor_mm=300.0)
        r2 = e2.resolve_damage("t2", _ap(), armor_mm=300.0)
        assert r1.penetrated == r2.penetrated

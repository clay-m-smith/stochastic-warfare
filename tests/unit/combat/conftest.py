"""Shared fixtures and factory functions for combat engine unit tests.

Supplements the top-level ``tests/conftest.py`` (which provides ``rng``,
``event_bus``, ``sim_clock`` fixtures).  Factories here build lightweight
combat domain objects without requiring YAML loaders or full entity graphs.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoState,
    MissileState,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.core.types import Position


# ---------------------------------------------------------------------------
# RNG helper (independent of fixtures — usable at module scope)
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> np.random.Generator:
    """Create a deterministic PRNG."""
    return np.random.Generator(np.random.PCG64(seed))


# ---------------------------------------------------------------------------
# Ammo factories
# ---------------------------------------------------------------------------

def _make_ap(
    *,
    ammo_id: str = "test_ap",
    penetration_mm_rha: float = 400.0,
    mass_kg: float = 5.0,
    diameter_mm: float = 120.0,
    drag_coefficient: float = 0.3,
    penetration_reference_range_m: float = 2000.0,
) -> AmmoDefinition:
    """Armor-piercing kinetic round."""
    return AmmoDefinition(
        ammo_id=ammo_id,
        display_name="Test AP",
        ammo_type="AP",
        mass_kg=mass_kg,
        diameter_mm=diameter_mm,
        drag_coefficient=drag_coefficient,
        penetration_mm_rha=penetration_mm_rha,
        penetration_reference_range_m=penetration_reference_range_m,
    )


def _make_he(
    *,
    ammo_id: str = "test_he",
    blast_radius_m: float = 50.0,
    fragmentation_radius_m: float = 100.0,
    explosive_fill_kg: float = 6.6,
    mass_kg: float = 43.0,
    diameter_mm: float = 155.0,
) -> AmmoDefinition:
    """High-explosive fragmentation round."""
    return AmmoDefinition(
        ammo_id=ammo_id,
        display_name="Test HE",
        ammo_type="HE",
        mass_kg=mass_kg,
        diameter_mm=diameter_mm,
        blast_radius_m=blast_radius_m,
        fragmentation_radius_m=fragmentation_radius_m,
        explosive_fill_kg=explosive_fill_kg,
    )


def _make_heat(
    *,
    ammo_id: str = "test_heat",
    penetration_mm_rha: float = 600.0,
    blast_radius_m: float = 5.0,
    mass_kg: float = 10.0,
    diameter_mm: float = 125.0,
) -> AmmoDefinition:
    """HEAT (shaped-charge) round."""
    return AmmoDefinition(
        ammo_id=ammo_id,
        display_name="Test HEAT",
        ammo_type="HEAT",
        mass_kg=mass_kg,
        diameter_mm=diameter_mm,
        penetration_mm_rha=penetration_mm_rha,
        blast_radius_m=blast_radius_m,
    )


def _make_guided_missile(
    *,
    ammo_id: str = "test_missile",
    pk_at_reference: float = 0.85,
    seeker_range_m: float = 5000.0,
    countermeasure_susceptibility: float = 0.3,
    max_speed_mps: float = 300.0,
    blast_radius_m: float = 10.0,
    guidance: str = "RADAR_ACTIVE",
    propulsion: str = "rocket",
    flight_time_s: float = 30.0,
) -> AmmoDefinition:
    """Guided missile ammo."""
    return AmmoDefinition(
        ammo_id=ammo_id,
        display_name="Test Missile",
        ammo_type="MISSILE",
        mass_kg=150.0,
        diameter_mm=200.0,
        pk_at_reference=pk_at_reference,
        seeker_range_m=seeker_range_m,
        countermeasure_susceptibility=countermeasure_susceptibility,
        max_speed_mps=max_speed_mps,
        blast_radius_m=blast_radius_m,
        guidance=guidance,
        propulsion=propulsion,
        flight_time_s=flight_time_s,
    )


def _make_dpicm(
    *,
    ammo_id: str = "test_dpicm",
    submunition_count: int = 88,
    submunition_lethal_radius_m: float = 5.0,
    blast_radius_m: float = 30.0,
    uxo_rate: float = 0.05,
) -> AmmoDefinition:
    """DPICM cluster round."""
    return AmmoDefinition(
        ammo_id=ammo_id,
        display_name="Test DPICM",
        ammo_type="DPICM",
        mass_kg=43.0,
        diameter_mm=155.0,
        submunition_count=submunition_count,
        submunition_lethal_radius_m=submunition_lethal_radius_m,
        blast_radius_m=blast_radius_m,
        uxo_rate=uxo_rate,
    )


# ---------------------------------------------------------------------------
# Weapon factories
# ---------------------------------------------------------------------------

def _make_gun(
    *,
    weapon_id: str = "test_gun",
    max_range_m: float = 3000.0,
    caliber_mm: float = 120.0,
    muzzle_velocity_mps: float = 1700.0,
    rate_of_fire_rpm: float = 6.0,
    base_accuracy_mrad: float = 0.3,
    category: str = "CANNON",
    compatible_ammo: list[str] | None = None,
    barrel_life_rounds: int = 0,
) -> WeaponDefinition:
    """Generic direct-fire weapon."""
    return WeaponDefinition(
        weapon_id=weapon_id,
        display_name="Test Gun",
        category=category,
        caliber_mm=caliber_mm,
        muzzle_velocity_mps=muzzle_velocity_mps,
        max_range_m=max_range_m,
        rate_of_fire_rpm=rate_of_fire_rpm,
        base_accuracy_mrad=base_accuracy_mrad,
        compatible_ammo=compatible_ammo or ["test_ap", "test_he", "test_heat"],
        barrel_life_rounds=barrel_life_rounds,
    )


def _make_weapon_instance(
    rounds: int = 40,
    *,
    weapon: WeaponDefinition | None = None,
    ammo_id: str = "test_ap",
) -> WeaponInstance:
    """Weapon instance with ammo loaded."""
    defn = weapon or _make_gun()
    state = AmmoState()
    state.add(ammo_id, rounds)
    return WeaponInstance(definition=defn, ammo_state=state)


def _make_missile_launcher(
    *,
    weapon_id: str = "test_launcher",
    max_range_m: float = 10000.0,
    missile_count: int = 4,
    ammo_id: str = "test_missile",
) -> WeaponInstance:
    """Missile launcher with ready missiles."""
    defn = WeaponDefinition(
        weapon_id=weapon_id,
        display_name="Test Launcher",
        category="MISSILE_LAUNCHER",
        caliber_mm=200.0,
        max_range_m=max_range_m,
        rate_of_fire_rpm=2.0,
        compatible_ammo=[ammo_id],
    )
    state = AmmoState()
    state.add(ammo_id, missile_count)
    for i in range(missile_count):
        state.missiles.append(MissileState(
            missile_id=f"{weapon_id}_m{i}",
            ammo_id=ammo_id,
        ))
    return WeaponInstance(definition=defn, ammo_state=state)


# ---------------------------------------------------------------------------
# Mock unit factory
# ---------------------------------------------------------------------------

def _make_unit(
    unit_id: str = "unit_1",
    side: str = "BLUE",
    position: Position | None = None,
    *,
    domain: str = "GROUND",
    speed: float = 0.0,
    posture: str = "MOVING",
    armor_mm: float = 0.0,
    personnel_count: int = 4,
    training_level: float = 0.5,
) -> SimpleNamespace:
    """Lightweight mock unit for combat engine tests.

    Returns a SimpleNamespace rather than a full Unit to avoid
    importing the full entity graph.
    """
    return SimpleNamespace(
        entity_id=unit_id,
        side=side,
        position=position or Position(0.0, 0.0, 0.0),
        domain=domain,
        speed=speed,
        posture=posture,
        armor_front=armor_mm,
        armor_side=armor_mm * 0.5,
        armor_type="RHA",
        personnel_count=personnel_count,
        training_level=training_level,
        status="ACTIVE",
    )

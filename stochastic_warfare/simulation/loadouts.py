"""Typed, deterministic production construction of unit runtime loadouts.

The mapping registry in this module is deliberately data-only.  It validates
declaration shape and uniqueness without consulting one particular era's
catalog.  :class:`RuntimeLoadoutBuilder` then validates only the records
reachable from a scenario against the effective unit, weapon, ammunition,
sensor, and era envelope before it can build any live attachment.
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
import re
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from types import MappingProxyType
from typing import Any, TypeAlias, TypeVar

from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoLoader,
    AmmoState,
    AmmoType,
    GuidanceType,
    WeaponCategory,
    WeaponDefinition,
    WeaponInstance,
    WeaponLoader,
)
from stochastic_warfare.core.era import EraConfig
from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.sensors import (
    SensorDefinition,
    SensorInstance,
    SensorLoader,
    SensorType,
    signature_domain_for_sensor_type,
)
from stochastic_warfare.detection.signatures import SignatureDomain
from stochastic_warfare.entities.base import Unit
from stochastic_warfare.entities.equipment import EquipmentCategory, EquipmentItem
from stochastic_warfare.entities.loader import (
    SensorPolicy,
    UnitDefinition,
    runtime_domain_for_definition,
)


class EquipmentMappingError(ValueError):
    """Base exception for an invalid mapping or runtime loadout envelope."""


class DuplicateEquipmentMappingError(EquipmentMappingError):
    """Raised before indexing when two mapping declarations share one key."""


class UnsupportedEquipmentError(EquipmentMappingError):
    """Raised when reachable equipment is explicitly unsupported."""


_AUTHORED_SYSTEM_COUNT_PATTERN = re.compile(
    r"""
    (?:
        \(\s*x\d+(?:x\d+)?(?:\s+[^)]*)?\)
        |\b\d+x\d+\b
        |^\d+x\s+
        |\bx\d+\b
        |\(\s*\d+\s+bow,\s*\d+\s+stern\s*\)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def equipment_name_declares_system_count(equipment_name: str) -> bool:
    """Return whether an authored label explicitly encodes multiplicity."""
    return _AUTHORED_SYSTEM_COUNT_PATTERN.search(equipment_name) is not None


def _validate_system_counts(
    *,
    equipment_name: str,
    source_system_count: int,
    target_system_count: int,
) -> int:
    """Validate and return the exact runtime multiplicity for one mapping."""
    for value, label in (
        (source_system_count, "source_system_count"),
        (target_system_count, "target_system_count"),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise EquipmentMappingError(
                f"{label} must be a positive non-bool integer",
            )
    if equipment_name_declares_system_count(equipment_name) and (
        source_system_count == 1
    ):
        raise EquipmentMappingError(
            f"Count-bearing weapon equipment {equipment_name!r} requires an "
            "explicit source_system_count greater than one",
        )
    if source_system_count % target_system_count != 0:
        raise EquipmentMappingError(
            f"source_system_count {source_system_count} must be exactly "
            f"divisible by target_system_count {target_system_count}",
        )
    return source_system_count // target_system_count


class ReferenceKind(str, enum.Enum):
    """How a supported target represents the authored equipment."""

    EXACT = "exact"
    VARIANT = "variant"
    FUNCTIONAL_ANALOGUE = "functional_analogue"


class WeaponModeledRole(str, enum.Enum):
    """Production behavior role represented by a weapon attachment."""

    GROUND_DIRECT_FIRE = "ground_direct_fire"
    AIR_DEFENSE_GUN = "air_defense_gun"
    NAVAL_GUNFIRE = "naval_gunfire"
    NAVAL_AIR_DEFENSE_GUN = "naval_air_defense_gun"
    FIELD_ARTILLERY = "field_artillery"
    MORTAR_FIRE = "mortar_fire"
    ROCKET_ARTILLERY = "rocket_artillery"
    ASSAULT_RIFLE = "assault_rifle"
    MUZZLE_LOADING_MUSKET = "muzzle_loading_musket"
    BOLT_ACTION_RIFLE = "bolt_action_rifle"
    SEMI_AUTOMATIC_RIFLE = "semi_automatic_rifle"
    SNIPER_RIFLE = "sniper_rifle"
    ANTI_MATERIEL_RIFLE = "anti_materiel_rifle"
    SUBMACHINE_GUN = "submachine_gun"
    LIGHT_MACHINE_GUN = "light_machine_gun"
    GENERAL_PURPOSE_MACHINE_GUN = "general_purpose_machine_gun"
    HEAVY_MACHINE_GUN = "heavy_machine_gun"
    INDIVIDUAL_GRENADE_LAUNCHER = "individual_grenade_launcher"
    AUTOMATIC_GRENADE_LAUNCHER = "automatic_grenade_launcher"
    HAND_GRENADE = "hand_grenade"
    MELEE = "melee"
    ANCIENT_PROJECTILE = "ancient_projectile"
    ANTI_ARMOR = "anti_armor"
    AIR_DEFENSE_MISSILE = "air_defense_missile"
    AIR_TO_AIR_MISSILE = "air_to_air_missile"
    AIR_TO_GROUND_MISSILE = "air_to_ground_missile"
    ANTI_SHIP_MISSILE = "anti_ship_missile"
    MULTI_ROLE_VLS = "multi_role_vls"
    BOMB_DELIVERY = "bomb_delivery"
    AIRCRAFT_GUN = "aircraft_gun"
    TORPEDO = "torpedo"
    ANTI_SUBMARINE = "anti_submarine"
    CLOSE_IN_DEFENSE = "close_in_defense"
    DIRECTED_ENERGY = "directed_energy"
    INCENDIARY_PROJECTOR = "incendiary_projector"


class SensorModeledRole(str, enum.Enum):
    """Production detection role represented by a sensor attachment."""

    VISUAL_OBSERVATION = "visual_observation"
    NIGHT_VISION = "night_vision"
    THERMAL_TARGETING = "thermal_targeting"
    AIRBORNE_FIRE_CONTROL_RADAR = "airborne_fire_control_radar"
    AIRBORNE_GROUND_FIRE_CONTROL_RADAR = (
        "airborne_ground_fire_control_radar"
    )
    AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR = (
        "airborne_multi_domain_fire_control_radar"
    )
    AIRBORNE_MARITIME_SEARCH_RADAR = "airborne_maritime_search_radar"
    AIR_SEARCH_RADAR = "air_search_radar"
    SHIP_AIR_SURFACE_SEARCH_RADAR = "ship_air_surface_search_radar"
    SURFACE_SEARCH_RADAR = "surface_search_radar"
    SHIP_SURFACE_SEARCH_RADAR = "ship_surface_search_radar"
    SUBMARINE_SURFACE_SEARCH_RADAR = "submarine_surface_search_radar"
    GROUND_SURVEILLANCE_RADAR = "ground_surveillance_radar"
    COASTAL_SURVEILLANCE_RADAR = "coastal_surveillance_radar"
    FIRE_CONTROL_RADAR = "fire_control_radar"
    GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR = (
        "ground_air_defense_fire_control_radar"
    )
    NAVAL_FIRE_CONTROL_RADAR = "naval_fire_control_radar"
    NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR = (
        "naval_air_defense_fire_control_radar"
    )
    GROUND_VISUAL_SIGHT = "ground_visual_sight"
    GROUND_AIR_DEFENSE_OPTICAL_SIGHT = (
        "ground_air_defense_optical_sight"
    )
    AIRBORNE_VISUAL_SIGHT = "airborne_visual_sight"
    AIRBORNE_GROUND_VISUAL_TARGETING = (
        "airborne_ground_visual_targeting"
    )
    AIRBORNE_GROUND_BOMBSIGHT = "airborne_ground_bombsight"
    NAVAL_VISUAL_DIRECTOR = "naval_visual_director"
    NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR = (
        "naval_air_defense_optical_director"
    )
    NAVAL_LOOKOUT = "naval_lookout"
    GROUND_NIGHT_SIGHT = "ground_night_sight"
    GROUND_ACTIVE_IR_SIGHT = "ground_active_ir_sight"
    AIRBORNE_LOW_LIGHT_OBSERVATION = "airborne_low_light_observation"
    INDIVIDUAL_NIGHT_VISION = "individual_night_vision"
    GROUND_THERMAL_TARGETING = "ground_thermal_targeting"
    AIRBORNE_GROUND_THERMAL_TARGETING = (
        "airborne_ground_thermal_targeting"
    )
    AIRBORNE_AIR_THERMAL_SEARCH = "airborne_air_thermal_search"
    AIRBORNE_SURFACE_THERMAL_SEARCH = (
        "airborne_surface_thermal_search"
    )
    RADAR_WARNING_ESM = "radar_warning_esm"
    ELECTRONIC_SUPPORT = "electronic_support"
    ACTIVE_SONAR = "active_sonar"
    PASSIVE_SONAR = "passive_sonar"


class WeaponStandoffClass(str, enum.Enum):
    """Whether a weapon role can create an automatic tactical hold."""

    ORGANIC_DIRECT_AIM = "organic_direct_aim"
    COMPATIBLE_DIRECTOR_REQUIRED = "compatible_director_required"
    UNSUPPORTED = "unsupported"


class SensorTargetingClass(str, enum.Enum):
    """Whether a mapped sensor role can provide local fire control."""

    LOCAL_FIRE_CONTROL = "local_fire_control"
    CONTACT_SEARCH_ONLY = "contact_search_only"


_RoleT = TypeVar("_RoleT", bound=enum.Enum)
_PolicyT = TypeVar("_PolicyT")


def _build_total_role_policy(
    *,
    label: str,
    enum_type: type[_RoleT],
    declarations: tuple[tuple[_RoleT, _PolicyT], ...],
) -> Mapping[_RoleT, _PolicyT]:
    """Build one duplicate-safe, exhaustive enum policy."""
    policy: dict[_RoleT, _PolicyT] = {}
    duplicate_roles: list[str] = []
    for role, value in declarations:
        if not isinstance(role, enum_type):
            raise EquipmentMappingError(
                f"{label} contains non-{enum_type.__name__} key {role!r}",
            )
        if role in policy:
            duplicate_roles.append(role.name)
            continue
        policy[role] = value
    if duplicate_roles:
        raise EquipmentMappingError(
            f"{label} contains duplicate roles {duplicate_roles!r}",
        )
    expected = set(enum_type)
    actual = set(policy)
    if actual != expected:
        raise EquipmentMappingError(
            f"{label} is not exhaustive: missing "
            f"{sorted(role.name for role in expected - actual)!r}; extra "
            f"{sorted(role.name for role in actual - expected)!r}",
        )
    return MappingProxyType(policy)


_WEAPON_STANDOFF_CLASSES = _build_total_role_policy(
    label="weapon standoff policy",
    enum_type=WeaponModeledRole,
    declarations=(
        (WeaponModeledRole.GROUND_DIRECT_FIRE, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.AIR_DEFENSE_GUN, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.NAVAL_GUNFIRE, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.FIELD_ARTILLERY, WeaponStandoffClass.UNSUPPORTED),
        (WeaponModeledRole.MORTAR_FIRE, WeaponStandoffClass.UNSUPPORTED),
        (WeaponModeledRole.ROCKET_ARTILLERY, WeaponStandoffClass.UNSUPPORTED),
        (WeaponModeledRole.ASSAULT_RIFLE, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.MUZZLE_LOADING_MUSKET, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.BOLT_ACTION_RIFLE, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.SEMI_AUTOMATIC_RIFLE, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.SNIPER_RIFLE, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.ANTI_MATERIEL_RIFLE, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.SUBMACHINE_GUN, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.LIGHT_MACHINE_GUN, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.HEAVY_MACHINE_GUN, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.INDIVIDUAL_GRENADE_LAUNCHER, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.AUTOMATIC_GRENADE_LAUNCHER, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.HAND_GRENADE, WeaponStandoffClass.UNSUPPORTED),
        (WeaponModeledRole.MELEE, WeaponStandoffClass.UNSUPPORTED),
        (WeaponModeledRole.ANCIENT_PROJECTILE, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.ANTI_ARMOR, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
        (WeaponModeledRole.AIR_DEFENSE_MISSILE, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.AIR_TO_AIR_MISSILE, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.AIR_TO_GROUND_MISSILE, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.ANTI_SHIP_MISSILE, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.MULTI_ROLE_VLS, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.BOMB_DELIVERY, WeaponStandoffClass.UNSUPPORTED),
        (WeaponModeledRole.AIRCRAFT_GUN, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.TORPEDO, WeaponStandoffClass.UNSUPPORTED),
        (WeaponModeledRole.ANTI_SUBMARINE, WeaponStandoffClass.UNSUPPORTED),
        (WeaponModeledRole.CLOSE_IN_DEFENSE, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.DIRECTED_ENERGY, WeaponStandoffClass.COMPATIBLE_DIRECTOR_REQUIRED),
        (WeaponModeledRole.INCENDIARY_PROJECTOR, WeaponStandoffClass.ORGANIC_DIRECT_AIM),
    ),
)


_SENSOR_TARGETING_CLASSES = _build_total_role_policy(
    label="sensor targeting policy",
    enum_type=SensorModeledRole,
    declarations=(
        (SensorModeledRole.VISUAL_OBSERVATION, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.NIGHT_VISION, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.THERMAL_TARGETING, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_MARITIME_SEARCH_RADAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.AIR_SEARCH_RADAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.SHIP_AIR_SURFACE_SEARCH_RADAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.SURFACE_SEARCH_RADAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.SUBMARINE_SURFACE_SEARCH_RADAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.GROUND_SURVEILLANCE_RADAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.COASTAL_SURVEILLANCE_RADAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.FIRE_CONTROL_RADAR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.GROUND_VISUAL_SIGHT, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_VISUAL_SIGHT, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.NAVAL_VISUAL_DIRECTOR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.NAVAL_LOOKOUT, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.GROUND_NIGHT_SIGHT, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.GROUND_ACTIVE_IR_SIGHT, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.INDIVIDUAL_NIGHT_VISION, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.GROUND_THERMAL_TARGETING, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING, SensorTargetingClass.LOCAL_FIRE_CONTROL),
        (SensorModeledRole.AIRBORNE_AIR_THERMAL_SEARCH, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.AIRBORNE_SURFACE_THERMAL_SEARCH, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.RADAR_WARNING_ESM, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.ELECTRONIC_SUPPORT, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.ACTIVE_SONAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
        (SensorModeledRole.PASSIVE_SONAR, SensorTargetingClass.CONTACT_SEARCH_ONLY),
    ),
)


_WEAPON_ROLE_CATEGORIES: Mapping[
    WeaponModeledRole,
    frozenset[WeaponCategory],
] = MappingProxyType({
    WeaponModeledRole.GROUND_DIRECT_FIRE: frozenset({
        WeaponCategory.CANNON,
        WeaponCategory.AUTOCANNON,
    }),
    WeaponModeledRole.AIR_DEFENSE_GUN: frozenset({
        WeaponCategory.AAA,
        WeaponCategory.CANNON,
        WeaponCategory.MACHINE_GUN,
        WeaponCategory.LIGHT_MG,
        WeaponCategory.HEAVY_MG,
        WeaponCategory.AUTOCANNON,
    }),
    WeaponModeledRole.NAVAL_GUNFIRE: frozenset({
        WeaponCategory.NAVAL_GUN,
    }),
    WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN: frozenset({
        WeaponCategory.NAVAL_GUN,
        WeaponCategory.AAA,
        WeaponCategory.AUTOCANNON,
    }),
    WeaponModeledRole.FIELD_ARTILLERY: frozenset({
        WeaponCategory.CANNON,
        WeaponCategory.HOWITZER,
        WeaponCategory.ARTILLERY,
    }),
    WeaponModeledRole.MORTAR_FIRE: frozenset({
        WeaponCategory.MORTAR,
    }),
    WeaponModeledRole.ROCKET_ARTILLERY: frozenset({
        WeaponCategory.ROCKET_LAUNCHER,
    }),
    WeaponModeledRole.ASSAULT_RIFLE: frozenset({
        WeaponCategory.RIFLE,
        WeaponCategory.MACHINE_GUN,
    }),
    WeaponModeledRole.MUZZLE_LOADING_MUSKET: frozenset({
        WeaponCategory.RIFLE,
    }),
    WeaponModeledRole.BOLT_ACTION_RIFLE: frozenset({
        WeaponCategory.RIFLE,
    }),
    WeaponModeledRole.SEMI_AUTOMATIC_RIFLE: frozenset({
        WeaponCategory.RIFLE,
    }),
    WeaponModeledRole.SNIPER_RIFLE: frozenset({
        WeaponCategory.RIFLE,
    }),
    WeaponModeledRole.ANTI_MATERIEL_RIFLE: frozenset({
        WeaponCategory.RIFLE,
        WeaponCategory.HEAVY_MG,
    }),
    WeaponModeledRole.SUBMACHINE_GUN: frozenset({
        WeaponCategory.SUBMACHINE_GUN,
    }),
    WeaponModeledRole.LIGHT_MACHINE_GUN: frozenset({
        WeaponCategory.LIGHT_MG,
        WeaponCategory.MACHINE_GUN,
    }),
    WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN: frozenset({
        WeaponCategory.LIGHT_MG,
        WeaponCategory.MACHINE_GUN,
    }),
    WeaponModeledRole.HEAVY_MACHINE_GUN: frozenset({
        WeaponCategory.HEAVY_MG,
        WeaponCategory.MACHINE_GUN,
    }),
    WeaponModeledRole.INDIVIDUAL_GRENADE_LAUNCHER: frozenset({
        WeaponCategory.GRENADE,
        WeaponCategory.ROCKET_LAUNCHER,
    }),
    WeaponModeledRole.AUTOMATIC_GRENADE_LAUNCHER: frozenset({
        WeaponCategory.GRENADE,
        WeaponCategory.ROCKET_LAUNCHER,
    }),
    WeaponModeledRole.HAND_GRENADE: frozenset({
        WeaponCategory.GRENADE,
    }),
    WeaponModeledRole.MELEE: frozenset({
        WeaponCategory.MELEE,
    }),
    WeaponModeledRole.ANCIENT_PROJECTILE: frozenset({
        WeaponCategory.RIFLE,
    }),
    WeaponModeledRole.ANTI_ARMOR: frozenset({
        WeaponCategory.MISSILE_LAUNCHER,
        WeaponCategory.ROCKET_LAUNCHER,
    }),
    WeaponModeledRole.AIR_DEFENSE_MISSILE: frozenset({
        WeaponCategory.MISSILE_LAUNCHER,
    }),
    WeaponModeledRole.AIR_TO_AIR_MISSILE: frozenset({
        WeaponCategory.MISSILE_LAUNCHER,
    }),
    WeaponModeledRole.AIR_TO_GROUND_MISSILE: frozenset({
        WeaponCategory.MISSILE_LAUNCHER,
    }),
    WeaponModeledRole.ANTI_SHIP_MISSILE: frozenset({
        WeaponCategory.MISSILE_LAUNCHER,
    }),
    WeaponModeledRole.MULTI_ROLE_VLS: frozenset({
        WeaponCategory.MISSILE_LAUNCHER,
    }),
    WeaponModeledRole.BOMB_DELIVERY: frozenset({
        WeaponCategory.ROCKET_LAUNCHER,
    }),
    WeaponModeledRole.AIRCRAFT_GUN: frozenset({
        WeaponCategory.CANNON,
        WeaponCategory.MACHINE_GUN,
        WeaponCategory.AIRCRAFT_GUN,
        WeaponCategory.LIGHT_MG,
        WeaponCategory.HEAVY_MG,
        WeaponCategory.AUTOCANNON,
    }),
    WeaponModeledRole.TORPEDO: frozenset({
        WeaponCategory.TORPEDO_TUBE,
    }),
    WeaponModeledRole.ANTI_SUBMARINE: frozenset({
        WeaponCategory.DEPTH_CHARGE,
    }),
    WeaponModeledRole.CLOSE_IN_DEFENSE: frozenset({
        WeaponCategory.CIWS,
        WeaponCategory.MISSILE_LAUNCHER,
    }),
    WeaponModeledRole.DIRECTED_ENERGY: frozenset({
        WeaponCategory.DIRECTED_ENERGY,
    }),
    WeaponModeledRole.INCENDIARY_PROJECTOR: frozenset({
        WeaponCategory.CANNON,
    }),
})

_WEAPON_ROLE_DOMAINS: Mapping[
    WeaponModeledRole,
    tuple[Domain, ...],
] = MappingProxyType({
    WeaponModeledRole.GROUND_DIRECT_FIRE: (Domain.GROUND,),
    WeaponModeledRole.AIR_DEFENSE_GUN: (Domain.AERIAL,),
    WeaponModeledRole.NAVAL_GUNFIRE: (Domain.GROUND, Domain.NAVAL),
    WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN: (Domain.AERIAL,),
    WeaponModeledRole.FIELD_ARTILLERY: (Domain.GROUND,),
    WeaponModeledRole.MORTAR_FIRE: (Domain.GROUND,),
    WeaponModeledRole.ROCKET_ARTILLERY: (Domain.GROUND,),
    WeaponModeledRole.ASSAULT_RIFLE: (Domain.GROUND,),
    WeaponModeledRole.MUZZLE_LOADING_MUSKET: (Domain.GROUND,),
    WeaponModeledRole.BOLT_ACTION_RIFLE: (Domain.GROUND,),
    WeaponModeledRole.SEMI_AUTOMATIC_RIFLE: (Domain.GROUND,),
    WeaponModeledRole.SNIPER_RIFLE: (Domain.GROUND,),
    WeaponModeledRole.ANTI_MATERIEL_RIFLE: (Domain.GROUND,),
    WeaponModeledRole.SUBMACHINE_GUN: (Domain.GROUND,),
    WeaponModeledRole.LIGHT_MACHINE_GUN: (Domain.GROUND,),
    WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN: (Domain.GROUND,),
    WeaponModeledRole.HEAVY_MACHINE_GUN: (Domain.GROUND,),
    WeaponModeledRole.INDIVIDUAL_GRENADE_LAUNCHER: (Domain.GROUND,),
    WeaponModeledRole.AUTOMATIC_GRENADE_LAUNCHER: (Domain.GROUND,),
    WeaponModeledRole.HAND_GRENADE: (Domain.GROUND,),
    WeaponModeledRole.MELEE: (Domain.GROUND,),
    WeaponModeledRole.ANCIENT_PROJECTILE: (Domain.GROUND,),
    WeaponModeledRole.ANTI_ARMOR: (Domain.GROUND,),
    WeaponModeledRole.AIR_DEFENSE_MISSILE: (Domain.AERIAL,),
    WeaponModeledRole.AIR_TO_AIR_MISSILE: (Domain.AERIAL,),
    WeaponModeledRole.AIR_TO_GROUND_MISSILE: (Domain.GROUND,),
    WeaponModeledRole.ANTI_SHIP_MISSILE: (Domain.NAVAL,),
    WeaponModeledRole.MULTI_ROLE_VLS: (Domain.AERIAL, Domain.NAVAL),
    WeaponModeledRole.BOMB_DELIVERY: (Domain.GROUND,),
    WeaponModeledRole.AIRCRAFT_GUN: (Domain.GROUND, Domain.AERIAL),
    WeaponModeledRole.TORPEDO: (Domain.NAVAL, Domain.SUBMARINE),
    WeaponModeledRole.ANTI_SUBMARINE: (Domain.SUBMARINE,),
    WeaponModeledRole.CLOSE_IN_DEFENSE: (Domain.AERIAL, Domain.NAVAL),
    WeaponModeledRole.DIRECTED_ENERGY: (Domain.AERIAL,),
    WeaponModeledRole.INCENDIARY_PROJECTOR: (Domain.GROUND,),
})

_WEAPON_ROLE_DOMAIN_PROFILES: Mapping[
    WeaponModeledRole,
    tuple[tuple[Domain, ...], ...],
] = MappingProxyType({
    role: (
        (
            (Domain.GROUND,),
            (Domain.NAVAL,),
            (Domain.GROUND, Domain.NAVAL),
        )
        if role in {
            WeaponModeledRole.MELEE,
            WeaponModeledRole.ANCIENT_PROJECTILE,
            WeaponModeledRole.INCENDIARY_PROJECTOR,
            WeaponModeledRole.MUZZLE_LOADING_MUSKET,
        }
        else (
            (Domain.NAVAL,),
            (Domain.SUBMARINE,),
            (Domain.NAVAL, Domain.SUBMARINE),
        )
        if role is WeaponModeledRole.TORPEDO
        else (domains,)
    )
    for role, domains in _WEAPON_ROLE_DOMAINS.items()
})

_SENSOR_ROLE_CONTRACTS: Mapping[
    SensorModeledRole,
    tuple[SensorType, SignatureDomain, tuple[Domain, ...]],
] = MappingProxyType({
    SensorModeledRole.VISUAL_OBSERVATION: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.GROUND, Domain.AERIAL, Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.NIGHT_VISION: (
        SensorType.NVG,
        SignatureDomain.VISUAL,
        (Domain.GROUND, Domain.AERIAL, Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.THERMAL_TARGETING: (
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        (Domain.GROUND, Domain.AERIAL, Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.AERIAL,),
    ),
    SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.GROUND,),
    ),
    SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.GROUND, Domain.AERIAL, Domain.NAVAL),
    ),
    SensorModeledRole.AIRBORNE_MARITIME_SEARCH_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.NAVAL,),
    ),
    SensorModeledRole.AIR_SEARCH_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.AERIAL,),
    ),
    SensorModeledRole.SHIP_AIR_SURFACE_SEARCH_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.AERIAL, Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.SURFACE_SEARCH_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.GROUND, Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.SUBMARINE_SURFACE_SEARCH_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.NAVAL,),
    ),
    SensorModeledRole.GROUND_SURVEILLANCE_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.GROUND, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.COASTAL_SURVEILLANCE_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.GROUND, Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.FIRE_CONTROL_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.GROUND, Domain.AERIAL, Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.AERIAL,),
    ),
    SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.AERIAL, Domain.NAVAL),
    ),
    SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR: (
        SensorType.RADAR,
        SignatureDomain.RADAR,
        (Domain.AERIAL,),
    ),
    SensorModeledRole.GROUND_VISUAL_SIGHT: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.GROUND,),
    ),
    SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.AERIAL,),
    ),
    SensorModeledRole.AIRBORNE_VISUAL_SIGHT: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.GROUND, Domain.AERIAL),
    ),
    SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.GROUND,),
    ),
    SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.GROUND,),
    ),
    SensorModeledRole.NAVAL_VISUAL_DIRECTOR: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.AERIAL, Domain.NAVAL),
    ),
    SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.AERIAL,),
    ),
    SensorModeledRole.NAVAL_LOOKOUT: (
        SensorType.VISUAL,
        SignatureDomain.VISUAL,
        (Domain.AERIAL, Domain.NAVAL),
    ),
    SensorModeledRole.GROUND_NIGHT_SIGHT: (
        SensorType.NVG,
        SignatureDomain.VISUAL,
        (Domain.GROUND,),
    ),
    SensorModeledRole.GROUND_ACTIVE_IR_SIGHT: (
        SensorType.NVG,
        SignatureDomain.VISUAL,
        (Domain.GROUND,),
    ),
    SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION: (
        SensorType.NVG,
        SignatureDomain.VISUAL,
        (Domain.GROUND, Domain.AERIAL),
    ),
    SensorModeledRole.INDIVIDUAL_NIGHT_VISION: (
        SensorType.NVG,
        SignatureDomain.VISUAL,
        (Domain.GROUND, Domain.AERIAL),
    ),
    SensorModeledRole.GROUND_THERMAL_TARGETING: (
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        (Domain.GROUND,),
    ),
    SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING: (
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        (Domain.GROUND,),
    ),
    SensorModeledRole.AIRBORNE_AIR_THERMAL_SEARCH: (
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        (Domain.AERIAL,),
    ),
    SensorModeledRole.AIRBORNE_SURFACE_THERMAL_SEARCH: (
        SensorType.THERMAL,
        SignatureDomain.THERMAL,
        (Domain.GROUND, Domain.NAVAL, Domain.AMPHIBIOUS),
    ),
    SensorModeledRole.RADAR_WARNING_ESM: (
        SensorType.ESM,
        SignatureDomain.ELECTROMAGNETIC,
        (
            Domain.GROUND,
            Domain.AERIAL,
            Domain.NAVAL,
            Domain.SUBMARINE,
            Domain.AMPHIBIOUS,
        ),
    ),
    SensorModeledRole.ELECTRONIC_SUPPORT: (
        SensorType.ESM,
        SignatureDomain.ELECTROMAGNETIC,
        (
            Domain.GROUND,
            Domain.AERIAL,
            Domain.NAVAL,
            Domain.SUBMARINE,
            Domain.AMPHIBIOUS,
        ),
    ),
    SensorModeledRole.ACTIVE_SONAR: (
        SensorType.ACTIVE_SONAR,
        SignatureDomain.ACOUSTIC,
        (Domain.NAVAL, Domain.SUBMARINE),
    ),
    SensorModeledRole.PASSIVE_SONAR: (
        SensorType.PASSIVE_SONAR,
        SignatureDomain.ACOUSTIC,
        (Domain.NAVAL, Domain.SUBMARINE),
    ),
})

_ALL_SHOOTER_DOMAINS = (
    Domain.GROUND,
    Domain.AERIAL,
    Domain.NAVAL,
    Domain.SUBMARINE,
    Domain.AMPHIBIOUS,
)
_AERIAL_SHOOTER_DOMAINS = (Domain.AERIAL,)
_GROUND_AMPHIBIOUS_SHOOTER_DOMAINS = (Domain.GROUND, Domain.AMPHIBIOUS)
_NAVAL_SHOOTER_DOMAINS = (Domain.NAVAL,)
_SURFACE_SHOOTER_DOMAINS = (
    Domain.GROUND,
    Domain.AERIAL,
    Domain.NAVAL,
    Domain.AMPHIBIOUS,
)
_SUBMARINE_SHOOTER_DOMAINS = (Domain.SUBMARINE,)
_SONAR_SHOOTER_DOMAINS = (Domain.NAVAL, Domain.SUBMARINE)

_SENSOR_ROLE_SHOOTER_DOMAINS = _build_total_role_policy(
    label="sensor shooter-domain policy",
    enum_type=SensorModeledRole,
    declarations=(
        (SensorModeledRole.VISUAL_OBSERVATION, _ALL_SHOOTER_DOMAINS),
        (SensorModeledRole.NIGHT_VISION, _ALL_SHOOTER_DOMAINS),
        (SensorModeledRole.THERMAL_TARGETING, _ALL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_MARITIME_SEARCH_RADAR, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIR_SEARCH_RADAR, _SURFACE_SHOOTER_DOMAINS),
        (SensorModeledRole.SHIP_AIR_SURFACE_SEARCH_RADAR, _NAVAL_SHOOTER_DOMAINS),
        (SensorModeledRole.SURFACE_SEARCH_RADAR, _SURFACE_SHOOTER_DOMAINS),
        (SensorModeledRole.SHIP_SURFACE_SEARCH_RADAR, _NAVAL_SHOOTER_DOMAINS),
        (SensorModeledRole.SUBMARINE_SURFACE_SEARCH_RADAR, _SUBMARINE_SHOOTER_DOMAINS),
        (SensorModeledRole.GROUND_SURVEILLANCE_RADAR, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.COASTAL_SURVEILLANCE_RADAR, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.FIRE_CONTROL_RADAR, _ALL_SHOOTER_DOMAINS),
        (SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR, _NAVAL_SHOOTER_DOMAINS),
        (SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR, _NAVAL_SHOOTER_DOMAINS),
        (SensorModeledRole.GROUND_VISUAL_SIGHT, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_VISUAL_SIGHT, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.NAVAL_VISUAL_DIRECTOR, _NAVAL_SHOOTER_DOMAINS),
        (SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR, _NAVAL_SHOOTER_DOMAINS),
        (SensorModeledRole.NAVAL_LOOKOUT, _NAVAL_SHOOTER_DOMAINS),
        (SensorModeledRole.GROUND_NIGHT_SIGHT, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.GROUND_ACTIVE_IR_SIGHT, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_LOW_LIGHT_OBSERVATION, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.INDIVIDUAL_NIGHT_VISION, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.GROUND_THERMAL_TARGETING, _GROUND_AMPHIBIOUS_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_AIR_THERMAL_SEARCH, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.AIRBORNE_SURFACE_THERMAL_SEARCH, _AERIAL_SHOOTER_DOMAINS),
        (SensorModeledRole.RADAR_WARNING_ESM, _ALL_SHOOTER_DOMAINS),
        (SensorModeledRole.ELECTRONIC_SUPPORT, _ALL_SHOOTER_DOMAINS),
        (SensorModeledRole.ACTIVE_SONAR, _SONAR_SHOOTER_DOMAINS),
        (SensorModeledRole.PASSIVE_SONAR, _SONAR_SHOOTER_DOMAINS),
    ),
)

_ORGANIC_DIRECT_SENSOR_ROLES = (
    SensorModeledRole.THERMAL_TARGETING,
    SensorModeledRole.FIRE_CONTROL_RADAR,
    SensorModeledRole.GROUND_VISUAL_SIGHT,
    SensorModeledRole.GROUND_NIGHT_SIGHT,
    SensorModeledRole.GROUND_ACTIVE_IR_SIGHT,
    SensorModeledRole.GROUND_THERMAL_TARGETING,
)
_GROUND_AIR_DEFENSE_SENSOR_ROLES = (
    SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT,
    SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
    SensorModeledRole.FIRE_CONTROL_RADAR,
)
_NAVAL_GUNFIRE_SENSOR_ROLES = (
    SensorModeledRole.NAVAL_VISUAL_DIRECTOR,
    SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
)
_NAVAL_AIR_DEFENSE_SENSOR_ROLES = (
    SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR,
    SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR,
    SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
)
_AIR_TO_AIR_SENSOR_ROLES = (
    SensorModeledRole.AIRBORNE_VISUAL_SIGHT,
    SensorModeledRole.AIRBORNE_FIRE_CONTROL_RADAR,
    SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
)
_AIRCRAFT_GUN_SENSOR_ROLES = (
    *_AIR_TO_AIR_SENSOR_ROLES,
    SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING,
    SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
    SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
)
_AIR_TO_GROUND_SENSOR_ROLES = (
    SensorModeledRole.AIRBORNE_GROUND_VISUAL_TARGETING,
    SensorModeledRole.AIRBORNE_GROUND_THERMAL_TARGETING,
    SensorModeledRole.AIRBORNE_GROUND_FIRE_CONTROL_RADAR,
    SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
)
_ANTI_SHIP_SENSOR_ROLES = (
    SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
    SensorModeledRole.AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR,
    SensorModeledRole.FIRE_CONTROL_RADAR,
)
_MULTI_ROLE_VLS_SENSOR_ROLES = (
    SensorModeledRole.FIRE_CONTROL_RADAR,
    SensorModeledRole.GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR,
    SensorModeledRole.NAVAL_FIRE_CONTROL_RADAR,
    SensorModeledRole.NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR,
)
_DIRECTED_ENERGY_SENSOR_ROLES = (
    *_MULTI_ROLE_VLS_SENSOR_ROLES,
    SensorModeledRole.GROUND_AIR_DEFENSE_OPTICAL_SIGHT,
    SensorModeledRole.NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR,
)

_WEAPON_COMPATIBLE_SENSOR_ROLES = _build_total_role_policy(
    label="weapon/sensor global compatibility policy",
    enum_type=WeaponModeledRole,
    declarations=(
        (WeaponModeledRole.GROUND_DIRECT_FIRE, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.AIR_DEFENSE_GUN, _GROUND_AIR_DEFENSE_SENSOR_ROLES),
        (WeaponModeledRole.NAVAL_GUNFIRE, _NAVAL_GUNFIRE_SENSOR_ROLES),
        (WeaponModeledRole.NAVAL_AIR_DEFENSE_GUN, _NAVAL_AIR_DEFENSE_SENSOR_ROLES),
        (WeaponModeledRole.FIELD_ARTILLERY, ()),
        (WeaponModeledRole.MORTAR_FIRE, ()),
        (WeaponModeledRole.ROCKET_ARTILLERY, ()),
        (WeaponModeledRole.ASSAULT_RIFLE, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.MUZZLE_LOADING_MUSKET, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.BOLT_ACTION_RIFLE, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.SEMI_AUTOMATIC_RIFLE, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.SNIPER_RIFLE, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.ANTI_MATERIEL_RIFLE, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.SUBMACHINE_GUN, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.LIGHT_MACHINE_GUN, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.GENERAL_PURPOSE_MACHINE_GUN, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.HEAVY_MACHINE_GUN, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.INDIVIDUAL_GRENADE_LAUNCHER, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.AUTOMATIC_GRENADE_LAUNCHER, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.HAND_GRENADE, ()),
        (WeaponModeledRole.MELEE, ()),
        (WeaponModeledRole.ANCIENT_PROJECTILE, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.ANTI_ARMOR, _ORGANIC_DIRECT_SENSOR_ROLES),
        (WeaponModeledRole.AIR_DEFENSE_MISSILE, _GROUND_AIR_DEFENSE_SENSOR_ROLES),
        (WeaponModeledRole.AIR_TO_AIR_MISSILE, _AIR_TO_AIR_SENSOR_ROLES),
        (WeaponModeledRole.AIR_TO_GROUND_MISSILE, _AIR_TO_GROUND_SENSOR_ROLES),
        (WeaponModeledRole.ANTI_SHIP_MISSILE, _ANTI_SHIP_SENSOR_ROLES),
        (WeaponModeledRole.MULTI_ROLE_VLS, _MULTI_ROLE_VLS_SENSOR_ROLES),
        (WeaponModeledRole.BOMB_DELIVERY, ()),
        (WeaponModeledRole.AIRCRAFT_GUN, _AIRCRAFT_GUN_SENSOR_ROLES),
        (WeaponModeledRole.TORPEDO, ()),
        (WeaponModeledRole.ANTI_SUBMARINE, ()),
        (WeaponModeledRole.CLOSE_IN_DEFENSE, _NAVAL_AIR_DEFENSE_SENSOR_ROLES),
        (WeaponModeledRole.DIRECTED_ENERGY, _DIRECTED_ENERGY_SENSOR_ROLES),
        (WeaponModeledRole.INCENDIARY_PROJECTOR, _ORGANIC_DIRECT_SENSOR_ROLES),
    ),
)

# These mapping-local links preserve routed-owner semantics while the global
# tactical-standoff matrix continues to reject both weapon roles.
_ROUTED_MAPPING_COMPATIBILITY = frozenset({
    (SensorModeledRole.GROUND_VISUAL_SIGHT, WeaponModeledRole.FIELD_ARTILLERY),
    (SensorModeledRole.AIRBORNE_GROUND_BOMBSIGHT, WeaponModeledRole.BOMB_DELIVERY),
})


def required_domains_for_weapon_role(
    modeled_role: WeaponModeledRole,
) -> tuple[Domain, ...]:
    """Return the complete typed engagement-domain contract for one role."""
    _require_enum(modeled_role, WeaponModeledRole, "modeled_role")
    return _WEAPON_ROLE_DOMAINS[modeled_role]


def weapon_role_supports_target_domain(
    modeled_role: WeaponModeledRole,
    target_domain: Domain,
) -> bool:
    """Return whether any valid mapping profile for a role admits a domain."""
    _require_enum(modeled_role, WeaponModeledRole, "modeled_role")
    _require_enum(target_domain, Domain, "target_domain")
    return any(
        target_domain in profile
        for profile in _WEAPON_ROLE_DOMAIN_PROFILES[modeled_role]
    )


def required_domains_for_sensor_role(
    modeled_role: SensorModeledRole,
) -> tuple[Domain, ...]:
    """Return the production target-domain contract for one sensor role."""
    _require_enum(modeled_role, SensorModeledRole, "modeled_role")
    return _SENSOR_ROLE_CONTRACTS[modeled_role][2]


def weapon_standoff_class(
    modeled_role: WeaponModeledRole,
) -> WeaponStandoffClass:
    """Return the exhaustive tactical-standoff class for a weapon role."""
    _require_enum(modeled_role, WeaponModeledRole, "modeled_role")
    return _WEAPON_STANDOFF_CLASSES[modeled_role]


def sensor_targeting_class(
    modeled_role: SensorModeledRole,
) -> SensorTargetingClass:
    """Return whether a sensor role can supply local fire control."""
    _require_enum(modeled_role, SensorModeledRole, "modeled_role")
    return _SENSOR_TARGETING_CLASSES[modeled_role]


def allowed_shooter_domains_for_sensor_role(
    modeled_role: SensorModeledRole,
) -> tuple[Domain, ...]:
    """Return the exhaustive shooter-platform domain contract."""
    _require_enum(modeled_role, SensorModeledRole, "modeled_role")
    return _SENSOR_ROLE_SHOOTER_DOMAINS[modeled_role]


def compatible_sensor_roles_for_weapon_role(
    modeled_role: WeaponModeledRole,
) -> tuple[SensorModeledRole, ...]:
    """Return the global fire-control upper bound for one weapon role."""
    _require_enum(modeled_role, WeaponModeledRole, "modeled_role")
    return _WEAPON_COMPATIBLE_SENSOR_ROLES[modeled_role]


def _mapping_roles_are_semantically_compatible(
    sensor_role: SensorModeledRole,
    weapon_role: WeaponModeledRole,
) -> bool:
    return (
        sensor_role in compatible_sensor_roles_for_weapon_role(weapon_role)
        or (sensor_role, weapon_role) in _ROUTED_MAPPING_COMPATIBILITY
    )


class ResolutionDisposition(str, enum.Enum):
    """The runtime outcome of one mapped weapon or sensor equipment item."""

    ATTACHMENT = "attachment"
    STORE = "store"
    NON_RUNTIME = "non_runtime"
    UNSUPPORTED = "unsupported"


def _require_trimmed(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EquipmentMappingError(
            f"{label} must be a non-empty, trimmed, case-sensitive string",
        )
    return value


def _require_optional_trimmed(value: object, label: str) -> None:
    if value is not None:
        _require_trimmed(value, label)


def _require_source_index(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative non-bool integer")
    return value


def _require_enum(value: object, enum_type: type[enum.Enum], label: str) -> None:
    if not isinstance(value, enum_type):
        raise EquipmentMappingError(
            f"{label} must be a {enum_type.__name__}, got {value!r}",
        )


def _require_enum_tuple(
    values: object,
    enum_type: type[enum.Enum],
    label: str,
) -> None:
    if not isinstance(values, tuple):
        raise EquipmentMappingError(f"{label} must be an immutable tuple")
    if len(values) != len(set(values)):
        raise EquipmentMappingError(f"{label} contains duplicate values")
    for value in values:
        _require_enum(value, enum_type, label)


def _require_string_tuple(
    values: object,
    label: str,
    *,
    non_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise EquipmentMappingError(f"{label} must be an immutable tuple")
    if non_empty and not values:
        raise EquipmentMappingError(f"{label} must not be empty")
    for value in values:
        _require_trimmed(value, label)
    if len(values) != len(set(values)):
        raise EquipmentMappingError(f"{label} contains duplicate values")
    return values


def _validate_reference(
    *,
    reference_kind: ReferenceKind,
    target_id: str,
    allowed_target_ids: tuple[str, ...],
    rationale: str | None,
    source: str | None,
) -> None:
    _require_enum(reference_kind, ReferenceKind, "reference_kind")
    _require_trimmed(target_id, "target_id")
    _require_string_tuple(
        allowed_target_ids,
        "allowed_target_ids",
        non_empty=reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE,
    )
    _require_optional_trimmed(rationale, "rationale")
    _require_optional_trimmed(source, "source")

    if reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE:
        if target_id not in allowed_target_ids:
            raise EquipmentMappingError(
                "A functional analogue target_id must be present in its "
                "explicit allowed_target_ids",
            )
        _require_trimmed(rationale, "functional-analogue rationale")
        _require_trimmed(source, "functional-analogue source")
    elif allowed_target_ids:
        raise EquipmentMappingError(
            "allowed_target_ids is only valid for a functional analogue",
        )


def _validate_live_reference_provenance(
    *,
    reference_kind: ReferenceKind,
    mapping_rationale: str | None,
    mapping_source: str | None,
) -> None:
    """Validate provenance copied from one exact mapping declaration."""
    _require_enum(reference_kind, ReferenceKind, "reference_kind")
    _require_optional_trimmed(mapping_rationale, "mapping_rationale")
    _require_optional_trimmed(mapping_source, "mapping_source")
    if reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE:
        _require_trimmed(
            mapping_rationale,
            "functional-analogue mapping_rationale",
        )
        _require_trimmed(
            mapping_source,
            "functional-analogue mapping_source",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class WeaponAttachmentMapping:
    """Map weapon equipment to one live :class:`WeaponInstance`."""

    equipment_name: str
    weapon_id: str
    expected_weapon_category: WeaponCategory
    modeled_role: WeaponModeledRole
    reference_kind: ReferenceKind = ReferenceKind.EXACT
    allowed_target_ids: tuple[str, ...] = ()
    rationale: str | None = None
    source: str | None = None
    expected_guidance: GuidanceType | None = None
    required_ammo_types: tuple[AmmoType, ...] = ()
    allowed_ammo_ids: tuple[str, ...] = ()
    required_target_domains: tuple[Domain, ...] = ()
    expected_caliber_mm: float | None = None
    source_system_count: int = 1
    target_system_count: int = 1

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "equipment_name")
        _validate_reference(
            reference_kind=self.reference_kind,
            target_id=self.weapon_id,
            allowed_target_ids=self.allowed_target_ids,
            rationale=self.rationale,
            source=self.source,
        )
        _require_enum(
            self.expected_weapon_category,
            WeaponCategory,
            "expected_weapon_category",
        )
        _require_enum(
            self.modeled_role,
            WeaponModeledRole,
            "modeled_role",
        )
        if self.expected_guidance is not None:
            _require_enum(
                self.expected_guidance,
                GuidanceType,
                "expected_guidance",
            )
        _require_enum_tuple(
            self.required_ammo_types,
            AmmoType,
            "required_ammo_types",
        )
        _require_string_tuple(
            self.allowed_ammo_ids,
            "allowed_ammo_ids",
            non_empty=False,
        )
        _require_enum_tuple(
            self.required_target_domains,
            Domain,
            "required_target_domains",
        )
        _validate_system_counts(
            equipment_name=self.equipment_name,
            source_system_count=self.source_system_count,
            target_system_count=self.target_system_count,
        )
        if not self.required_target_domains:
            raise EquipmentMappingError(
                "Weapon attachment mappings require at least one typed target "
                "domain constraint",
            )
        allowed_categories = _WEAPON_ROLE_CATEGORIES[self.modeled_role]
        if self.expected_weapon_category not in allowed_categories:
            raise EquipmentMappingError(
                f"Weapon role {self.modeled_role.value!r} cannot use category "
                f"{self.expected_weapon_category.name!r}; allowed categories "
                f"are {sorted(category.name for category in allowed_categories)}",
            )
        allowed_domain_profiles = _WEAPON_ROLE_DOMAIN_PROFILES[
            self.modeled_role
        ]
        if self.required_target_domains not in allowed_domain_profiles:
            raise EquipmentMappingError(
                f"Weapon role {self.modeled_role.value!r} requires one exact "
                "target-domain profile from "
                f"{[[domain.name for domain in profile] for profile in allowed_domain_profiles]}, "
                "got "
                f"{[domain.name for domain in self.required_target_domains]}",
            )
        if (
            self.expected_caliber_mm is not None
            and (
                not isinstance(self.expected_caliber_mm, (int, float))
                or isinstance(self.expected_caliber_mm, bool)
                or not math.isfinite(float(self.expected_caliber_mm))
                or self.expected_caliber_mm < 0.0
            )
        ):
            raise EquipmentMappingError(
                "expected_caliber_mm must be a finite non-negative number",
            )

        if self.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE and not (
            self.required_ammo_types
            or self.allowed_ammo_ids
            or self.expected_caliber_mm is not None
            or self.expected_guidance is not None
        ):
            raise EquipmentMappingError(
                "Functional weapon analogues require at least one "
                "outcome-consumed caliber, guidance, or ammunition "
                "constraint",
            )

    @property
    def category(self) -> EquipmentCategory:
        return EquipmentCategory.WEAPON

    @property
    def disposition(self) -> ResolutionDisposition:
        return ResolutionDisposition.ATTACHMENT

    @property
    def target_id(self) -> str:
        return self.weapon_id

    @property
    def runtime_system_multiplier(self) -> int:
        """Number of target-definition systems represented at runtime."""
        return _validate_system_counts(
            equipment_name=self.equipment_name,
            source_system_count=self.source_system_count,
            target_system_count=self.target_system_count,
        )

    def permits_target(self, weapon_id: str) -> bool:
        if self.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE:
            return weapon_id in self.allowed_target_ids
        return weapon_id == self.weapon_id


@dataclass(frozen=True, slots=True, kw_only=True)
class WeaponStoreMapping:
    """Map carried weapon equipment to ammunition for one same-unit launcher."""

    equipment_name: str
    ammo_id: str
    compatible_weapon_ids: tuple[str, ...]
    reference_kind: ReferenceKind = ReferenceKind.EXACT
    allowed_target_ids: tuple[str, ...] = ()
    rationale: str | None = None
    source: str | None = None
    expected_ammo_type: AmmoType | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "equipment_name")
        _validate_reference(
            reference_kind=self.reference_kind,
            target_id=self.ammo_id,
            allowed_target_ids=self.allowed_target_ids,
            rationale=self.rationale,
            source=self.source,
        )
        _require_string_tuple(
            self.compatible_weapon_ids,
            "compatible_weapon_ids",
            non_empty=True,
        )
        if self.expected_ammo_type is not None:
            _require_enum(
                self.expected_ammo_type,
                AmmoType,
                "expected_ammo_type",
            )

    @property
    def category(self) -> EquipmentCategory:
        return EquipmentCategory.WEAPON

    @property
    def disposition(self) -> ResolutionDisposition:
        return ResolutionDisposition.STORE

    @property
    def target_id(self) -> str:
        return self.ammo_id


@dataclass(frozen=True, slots=True, kw_only=True)
class WeaponNonRuntimeMapping:
    """Classify weapon-authored equipment outside the modeled runtime boundary."""

    equipment_name: str
    reason: str
    source: str | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "equipment_name")
        _require_trimmed(self.reason, "non-runtime reason")
        _require_optional_trimmed(self.source, "source")

    @property
    def category(self) -> EquipmentCategory:
        return EquipmentCategory.WEAPON

    @property
    def disposition(self) -> ResolutionDisposition:
        return ResolutionDisposition.NON_RUNTIME


@dataclass(frozen=True, slots=True, kw_only=True)
class WeaponUnsupportedMapping:
    """Declare weapon equipment that must reject if it becomes reachable."""

    equipment_name: str
    reason: str

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "equipment_name")
        _require_trimmed(self.reason, "unsupported reason")

    @property
    def category(self) -> EquipmentCategory:
        return EquipmentCategory.WEAPON

    @property
    def disposition(self) -> ResolutionDisposition:
        return ResolutionDisposition.UNSUPPORTED


@dataclass(frozen=True, slots=True, kw_only=True)
class SensorAttachmentMapping:
    """Map sensor equipment to one live :class:`SensorInstance`."""

    equipment_name: str
    sensor_id: str
    expected_sensor_type: SensorType
    expected_signature_domain: SignatureDomain
    modeled_role: SensorModeledRole
    compatible_weapon_roles: tuple[WeaponModeledRole, ...]
    required_target_domains: tuple[Domain, ...]
    modeled_max_range_m: float | None = None
    modeled_fov_deg: float | None = None
    reference_kind: ReferenceKind = ReferenceKind.EXACT
    allowed_target_ids: tuple[str, ...] = ()
    rationale: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "equipment_name")
        _validate_reference(
            reference_kind=self.reference_kind,
            target_id=self.sensor_id,
            allowed_target_ids=self.allowed_target_ids,
            rationale=self.rationale,
            source=self.source,
        )
        _require_enum(
            self.expected_sensor_type,
            SensorType,
            "expected_sensor_type",
        )
        _require_enum(
            self.expected_signature_domain,
            SignatureDomain,
            "expected_signature_domain",
        )
        _require_enum(
            self.modeled_role,
            SensorModeledRole,
            "modeled_role",
        )
        _require_enum_tuple(
            self.compatible_weapon_roles,
            WeaponModeledRole,
            "compatible_weapon_roles",
        )
        if (
            sensor_targeting_class(self.modeled_role)
            is SensorTargetingClass.CONTACT_SEARCH_ONLY
            and self.compatible_weapon_roles
        ):
            raise EquipmentMappingError(
                f"Contact/search-only sensor role {self.modeled_role.value!r} "
                "cannot declare compatible weapon roles",
            )
        incompatible_roles = [
            role.value
            for role in self.compatible_weapon_roles
            if not _mapping_roles_are_semantically_compatible(
                self.modeled_role,
                role,
            )
        ]
        if incompatible_roles:
            raise EquipmentMappingError(
                f"Sensor role {self.modeled_role.value!r} cannot bind mapping "
                f"weapon roles {incompatible_roles!r}",
            )
        empty_domain_intersections = [
            role.value
            for role in self.compatible_weapon_roles
            if not (
                set(required_domains_for_sensor_role(self.modeled_role))
                & set(required_domains_for_weapon_role(role))
            )
        ]
        if empty_domain_intersections:
            raise EquipmentMappingError(
                f"Sensor role {self.modeled_role.value!r} has no common "
                "target domain with mapping weapon roles "
                f"{empty_domain_intersections!r}",
            )
        expected_type, expected_domain, required_domains = _SENSOR_ROLE_CONTRACTS[
            self.modeled_role
        ]
        if (
            self.expected_sensor_type is not expected_type
            or self.expected_signature_domain is not expected_domain
        ):
            raise EquipmentMappingError(
                f"Sensor role {self.modeled_role.value!r} requires "
                f"{expected_type.name}/{expected_domain.name}, got "
                f"{self.expected_sensor_type.name}/"
                f"{self.expected_signature_domain.name}",
            )
        _require_enum_tuple(
            self.required_target_domains,
            Domain,
            "required_target_domains",
        )
        if self.required_target_domains != required_domains:
            raise EquipmentMappingError(
                f"Sensor role {self.modeled_role.value!r} requires exact target "
                f"domains {[domain.name for domain in required_domains]}, got "
                f"{[domain.name for domain in self.required_target_domains]}",
            )
        for value, label, upper_bound in (
            (self.modeled_max_range_m, "modeled_max_range_m", None),
            (self.modeled_fov_deg, "modeled_fov_deg", 360.0),
        ):
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or value <= 0.0
                or (upper_bound is not None and value > upper_bound)
            ):
                suffix = (
                    f" and at most {upper_bound}"
                    if upper_bound is not None
                    else ""
                )
                raise EquipmentMappingError(
                    f"{label} must be finite and positive{suffix}",
                )
        if self.reference_kind is ReferenceKind.FUNCTIONAL_ANALOGUE and (
            self.modeled_max_range_m is None
            or self.modeled_fov_deg is None
        ):
            raise EquipmentMappingError(
                "Functional sensor analogues require an outcome-consumed "
                "modeled_max_range_m and modeled_fov_deg envelope",
            )

    @property
    def category(self) -> EquipmentCategory:
        return EquipmentCategory.SENSOR

    @property
    def disposition(self) -> ResolutionDisposition:
        return ResolutionDisposition.ATTACHMENT

    @property
    def target_id(self) -> str:
        return self.sensor_id


@dataclass(frozen=True, slots=True, kw_only=True)
class SensorNonRuntimeMapping:
    """Classify sensor-authored equipment outside the detection interface."""

    equipment_name: str
    reason: str
    source: str | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "equipment_name")
        _require_trimmed(self.reason, "non-runtime reason")
        _require_optional_trimmed(self.source, "source")

    @property
    def category(self) -> EquipmentCategory:
        return EquipmentCategory.SENSOR

    @property
    def disposition(self) -> ResolutionDisposition:
        return ResolutionDisposition.NON_RUNTIME


@dataclass(frozen=True, slots=True, kw_only=True)
class SensorUnsupportedMapping:
    """Declare sensor equipment that must reject if it becomes reachable."""

    equipment_name: str
    reason: str

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "equipment_name")
        _require_trimmed(self.reason, "unsupported reason")

    @property
    def category(self) -> EquipmentCategory:
        return EquipmentCategory.SENSOR

    @property
    def disposition(self) -> ResolutionDisposition:
        return ResolutionDisposition.UNSUPPORTED


EquipmentMappingRecord: TypeAlias = (
    WeaponAttachmentMapping
    | WeaponStoreMapping
    | WeaponNonRuntimeMapping
    | WeaponUnsupportedMapping
    | SensorAttachmentMapping
    | SensorNonRuntimeMapping
    | SensorUnsupportedMapping
)

_MAPPING_RECORD_TYPES = (
    WeaponAttachmentMapping,
    WeaponStoreMapping,
    WeaponNonRuntimeMapping,
    WeaponUnsupportedMapping,
    SensorAttachmentMapping,
    SensorNonRuntimeMapping,
    SensorUnsupportedMapping,
)


@dataclass(frozen=True, slots=True, init=False)
class EquipmentMappingRegistry:
    """Ordered, immutable mapping declarations with a uniqueness-checked index."""

    _records: tuple[EquipmentMappingRecord, ...]
    _index: Mapping[
        tuple[EquipmentCategory, str],
        EquipmentMappingRecord,
    ]

    def __init__(self, records: Sequence[EquipmentMappingRecord]) -> None:
        if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
            raise TypeError("Equipment mappings must be an ordered sequence")
        frozen_records = tuple(records)

        # Validate every key and reject duplicates before constructing an index.
        seen: dict[tuple[EquipmentCategory, str], int] = {}
        exact_target_roles: dict[
            tuple[EquipmentCategory, str],
            tuple[
                WeaponModeledRole | SensorModeledRole,
                int,
            ],
        ] = {}
        for index, record in enumerate(frozen_records):
            if not isinstance(record, _MAPPING_RECORD_TYPES):
                raise TypeError(
                    "Equipment mapping declarations must use the typed "
                    f"record union, got {type(record).__name__} at index {index}",
                )
            key = (record.category, record.equipment_name)
            if key in seen:
                first_index = seen[key]
                raise DuplicateEquipmentMappingError(
                    "Duplicate equipment mapping for "
                    f"({record.category.name}, {record.equipment_name!r}) "
                    f"at declaration indexes {first_index} and {index}",
                )
            seen[key] = index
            if isinstance(
                record,
                (WeaponAttachmentMapping, SensorAttachmentMapping),
            ) and record.reference_kind is ReferenceKind.EXACT:
                target_key = (record.category, record.target_id)
                previous = exact_target_roles.get(target_key)
                if (
                    previous is not None
                    and previous[0] is not record.modeled_role
                ):
                    raise EquipmentMappingError(
                        f"Target {record.target_id!r} is declared with "
                        f"conflicting modeled roles "
                        f"{previous[0].value!r} (index {previous[1]}) and "
                        f"{record.modeled_role.value!r} (index {index})",
                    )
                if previous is None:
                    exact_target_roles[target_key] = (
                        record.modeled_role,
                        index,
                    )

        object.__setattr__(self, "_records", frozen_records)
        object.__setattr__(
            self,
            "_index",
            MappingProxyType({
                (record.category, record.equipment_name): record
                for record in frozen_records
            }),
        )

    @property
    def records(self) -> tuple[EquipmentMappingRecord, ...]:
        return self._records

    def get(
        self,
        category: EquipmentCategory,
        equipment_name: str,
    ) -> EquipmentMappingRecord | None:
        return self._index.get((category, equipment_name))

    def require(
        self,
        category: EquipmentCategory,
        equipment_name: str,
    ) -> EquipmentMappingRecord:
        try:
            return self._index[(category, equipment_name)]
        except KeyError as exc:
            raise EquipmentMappingError(
                "No equipment mapping for "
                f"({category.name}, {equipment_name!r})",
            ) from exc


@dataclass(frozen=True, slots=True)
class WeaponAssignment:
    """One typed scenario-local weapon target override."""

    equipment_name: str
    weapon_id: str

    def __post_init__(self) -> None:
        _require_trimmed(self.equipment_name, "assignment equipment_name")
        _require_trimmed(self.weapon_id, "assignment weapon_id")


@dataclass(frozen=True, slots=True)
class WeaponAttachment:
    """One live weapon plus its immutable catalog/source links."""

    weapon: WeaponInstance
    ammunition: tuple[AmmoDefinition, ...]
    source_equipment: EquipmentItem
    source_equipment_index: int
    modeled_role: WeaponModeledRole
    reference_kind: ReferenceKind
    mapping_rationale: str | None
    mapping_source: str | None
    source_system_count: int
    target_system_count: int
    runtime_system_multiplier: int

    def __post_init__(self) -> None:
        if self.weapon.equipment is not self.source_equipment:
            raise ValueError(
                "WeaponAttachment source_equipment must be the exact object "
                "linked by its WeaponInstance",
            )
        if not isinstance(self.ammunition, tuple) or not self.ammunition:
            raise ValueError("WeaponAttachment ammunition must be a non-empty tuple")
        _require_source_index(
            self.source_equipment_index,
            "source_equipment_index",
        )
        _require_enum(self.modeled_role, WeaponModeledRole, "modeled_role")
        _validate_live_reference_provenance(
            reference_kind=self.reference_kind,
            mapping_rationale=self.mapping_rationale,
            mapping_source=self.mapping_source,
        )
        expected_multiplier = _validate_system_counts(
            equipment_name=self.source_equipment.name,
            source_system_count=self.source_system_count,
            target_system_count=self.target_system_count,
        )
        if self.runtime_system_multiplier != expected_multiplier:
            raise ValueError(
                "WeaponAttachment runtime_system_multiplier must equal "
                "source_system_count // target_system_count",
            )

    @property
    def weapon_instance(self) -> WeaponInstance:
        """Explicit alias for consumers migrating from tuple-shaped entries."""
        return self.weapon

    @property
    def ammo_definitions(self) -> tuple[AmmoDefinition, ...]:
        return self.ammunition

    def first_fireable_ammunition(
        self,
        *,
        excluded_ammo_ids: Collection[str] = (),
    ) -> AmmoDefinition | None:
        """Return the first currently usable definition in declaration order."""
        return next(
            (
                ammunition
                for ammunition in self.ammunition
                if (
                    ammunition.ammo_id not in excluded_ammo_ids
                    and self.weapon.can_fire(ammunition.ammo_id)
                )
            ),
            None,
        )

    def __iter__(self) -> Iterator[WeaponInstance | tuple[AmmoDefinition, ...]]:
        """Preserve tuple unpacking while callers migrate to named fields."""
        yield self.weapon
        yield self.ammunition

    def __len__(self) -> int:
        return 2

    def __getitem__(
        self,
        index: int,
    ) -> WeaponInstance | tuple[AmmoDefinition, ...]:
        return (self.weapon, self.ammunition)[index]


@dataclass(frozen=True, slots=True)
class SensorAttachment:
    """One live sensor plus immutable mapping and fire-control bindings."""

    sensor: SensorInstance
    source_equipment: EquipmentItem
    source_equipment_index: int
    modeled_role: SensorModeledRole
    reference_kind: ReferenceKind
    mapping_rationale: str | None
    mapping_source: str | None
    compatible_weapon_roles: tuple[WeaponModeledRole, ...]
    compatible_weapon_source_indexes: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.sensor.equipment is not self.source_equipment:
            raise ValueError(
                "SensorAttachment source_equipment must be the exact object "
                "linked by its SensorInstance",
            )
        _require_source_index(
            self.source_equipment_index,
            "source_equipment_index",
        )
        _require_enum(self.modeled_role, SensorModeledRole, "modeled_role")
        _validate_live_reference_provenance(
            reference_kind=self.reference_kind,
            mapping_rationale=self.mapping_rationale,
            mapping_source=self.mapping_source,
        )
        _require_enum_tuple(
            self.compatible_weapon_roles,
            WeaponModeledRole,
            "compatible_weapon_roles",
        )
        if not isinstance(self.compatible_weapon_source_indexes, tuple):
            raise ValueError(
                "compatible_weapon_source_indexes must be an immutable tuple",
            )
        if tuple(sorted(self.compatible_weapon_source_indexes)) != (
            self.compatible_weapon_source_indexes
        ):
            raise ValueError(
                "compatible_weapon_source_indexes must be in source order",
            )
        if len(self.compatible_weapon_source_indexes) != len(
            set(self.compatible_weapon_source_indexes),
        ):
            raise ValueError(
                "compatible_weapon_source_indexes contains duplicates",
            )
        for index in self.compatible_weapon_source_indexes:
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or index < 0
            ):
                raise ValueError(
                    "compatible_weapon_source_indexes must contain only "
                    "non-negative integers",
                )

    @property
    def sensor_instance(self) -> SensorInstance:
        """Return the exact compatibility-projection object."""
        return self.sensor

    @property
    def sensor_id(self) -> str:
        return self.sensor.sensor_id


@dataclass(frozen=True, slots=True)
class EquipmentResolution:
    """Transparent outcome for one mapped runtime equipment item."""

    unit_id: str
    unit_type: str
    source_equipment: EquipmentItem
    source_equipment_index: int
    category: EquipmentCategory
    disposition: ResolutionDisposition
    modeled_role: WeaponModeledRole | SensorModeledRole | None = None
    reference_kind: ReferenceKind | None = None
    target_id: str | None = None
    attached_to_equipment_index: int | None = None
    attached_to_target_id: str | None = None
    reason: str | None = None
    source_system_count: int | None = None
    target_system_count: int | None = None
    runtime_system_multiplier: int | None = None

    def __post_init__(self) -> None:
        _require_trimmed(self.unit_id, "resolution unit_id")
        _require_trimmed(self.unit_type, "resolution unit_type")
        _require_source_index(
            self.source_equipment_index,
            "source_equipment_index",
        )
        if self.attached_to_equipment_index is not None:
            _require_source_index(
                self.attached_to_equipment_index,
                "attached_to_equipment_index",
            )
        _require_enum(self.category, EquipmentCategory, "resolution category")
        if self.source_equipment.category is not self.category:
            raise ValueError(
                "resolution category must match the exact source equipment",
            )
        _require_enum(
            self.disposition,
            ResolutionDisposition,
            "resolution disposition",
        )
        if self.reference_kind is not None:
            _require_enum(
                self.reference_kind,
                ReferenceKind,
                "resolution reference_kind",
            )
        if self.modeled_role is not None and not isinstance(
            self.modeled_role,
            (WeaponModeledRole, SensorModeledRole),
        ):
            raise ValueError(
                "resolution modeled_role must be a typed weapon or sensor role",
            )
        _require_optional_trimmed(self.target_id, "resolution target_id")
        _require_optional_trimmed(
            self.attached_to_target_id,
            "resolution attached_to_target_id",
        )
        _require_optional_trimmed(self.reason, "resolution reason")

        if self.disposition is ResolutionDisposition.ATTACHMENT:
            if (
                self.target_id is None
                or self.reference_kind is None
                or self.modeled_role is None
            ):
                raise ValueError(
                    "Attachment resolutions require target_id, reference_kind, "
                    "and modeled_role",
                )
            if (
                self.attached_to_equipment_index is not None
                or self.attached_to_target_id is not None
                or self.reason is not None
            ):
                raise ValueError(
                    "Attachment resolutions cannot carry store/non-runtime fields",
                )
            if self.category is EquipmentCategory.WEAPON:
                if (
                    self.source_system_count is None
                    or self.target_system_count is None
                    or self.runtime_system_multiplier is None
                ):
                    raise ValueError(
                        "Weapon attachment resolutions require complete system "
                        "count topology",
                    )
                expected_multiplier = _validate_system_counts(
                    equipment_name=self.source_equipment.name,
                    source_system_count=self.source_system_count,
                    target_system_count=self.target_system_count,
                )
                if self.runtime_system_multiplier != expected_multiplier:
                    raise ValueError(
                        "Resolution runtime_system_multiplier must equal "
                        "source_system_count // target_system_count",
                    )
            elif any(
                count is not None
                for count in (
                    self.source_system_count,
                    self.target_system_count,
                    self.runtime_system_multiplier,
                )
            ):
                raise ValueError(
                    "Sensor attachment resolutions cannot carry weapon system "
                    "count topology",
                )
        elif self.disposition is ResolutionDisposition.STORE:
            if (
                self.category is not EquipmentCategory.WEAPON
                or
                self.target_id is None
                or self.reference_kind is None
                or self.modeled_role is not None
                or self.attached_to_equipment_index is None
                or self.attached_to_target_id is None
                or self.reason is not None
            ):
                raise ValueError(
                    "Weapon store resolutions require a target and one "
                    "attachment link",
                )
            if any(
                count is not None
                for count in (
                    self.source_system_count,
                    self.target_system_count,
                    self.runtime_system_multiplier,
                )
            ):
                raise ValueError(
                    "Store resolutions cannot carry live system count topology",
                )
        elif self.disposition is ResolutionDisposition.NON_RUNTIME:
            if (
                self.reason is None
                or self.target_id is not None
                or self.reference_kind is not None
                or self.modeled_role is not None
                or self.attached_to_equipment_index is not None
                or self.attached_to_target_id is not None
            ):
                raise ValueError(
                    "Non-runtime resolutions require only an explicit reason",
                )
            if any(
                count is not None
                for count in (
                    self.source_system_count,
                    self.target_system_count,
                    self.runtime_system_multiplier,
                )
            ):
                raise ValueError(
                    "Non-runtime resolutions cannot carry live system count "
                    "topology",
                )
        else:
            raise ValueError(
                "Unsupported equipment raises before RuntimeLoadouts publication",
            )

    @property
    def equipment_id(self) -> str:
        return self.source_equipment.equipment_id

    @property
    def equipment_name(self) -> str:
        return self.source_equipment.name

    def topology(self) -> dict[str, Any]:
        return {
            "source_equipment_index": self.source_equipment_index,
            "equipment_id": self.source_equipment.equipment_id,
            "equipment_name": self.source_equipment.name,
            "category": self.category.name,
            "disposition": self.disposition.value,
            "modeled_role": (
                self.modeled_role.value
                if self.modeled_role is not None
                else None
            ),
            "reference_kind": (
                self.reference_kind.value
                if self.reference_kind is not None
                else None
            ),
            "target_id": self.target_id,
            "attached_to_equipment_index": self.attached_to_equipment_index,
            "attached_to_target_id": self.attached_to_target_id,
            "reason": self.reason,
            "source_system_count": self.source_system_count,
            "target_system_count": self.target_system_count,
            "runtime_system_multiplier": self.runtime_system_multiplier,
        }


@dataclass(frozen=True, slots=True)
class RuntimeLoadouts:
    """Immutable per-unit runtime attachments and equipment outcomes."""

    unit_weapons: Mapping[str, tuple[WeaponAttachment, ...]]
    unit_sensor_attachments: Mapping[str, tuple[SensorAttachment, ...]]
    equipment_resolutions: Mapping[str, tuple[EquipmentResolution, ...]]
    unit_sensors: Mapping[str, tuple[SensorInstance, ...]] = field(init=False)

    def __post_init__(self) -> None:
        weapon_keys = set(self.unit_weapons)
        sensor_keys = set(self.unit_sensor_attachments)
        resolution_keys = set(self.equipment_resolutions)
        if weapon_keys != sensor_keys or weapon_keys != resolution_keys:
            raise ValueError(
                "RuntimeLoadouts must contain weapons, sensor attachments, "
                "and resolutions for exactly the same unit IDs",
            )
        normalized_weapons = {
            unit_id: tuple(attachments)
            for unit_id, attachments in self.unit_weapons.items()
        }
        normalized_sensor_attachments = {
            unit_id: tuple(attachments)
            for unit_id, attachments in self.unit_sensor_attachments.items()
        }
        normalized_resolutions = {
            unit_id: tuple(resolutions)
            for unit_id, resolutions in self.equipment_resolutions.items()
        }
        normalized_sensors: dict[str, tuple[SensorInstance, ...]] = {}

        for unit_id in normalized_weapons:
            weapons = normalized_weapons[unit_id]
            sensor_attachments = normalized_sensor_attachments[unit_id]
            resolutions = normalized_resolutions[unit_id]

            weapon_by_source_index: dict[int, WeaponAttachment] = {}
            for attachment in weapons:
                if not isinstance(attachment, WeaponAttachment):
                    raise TypeError(
                        f"unit_weapons[{unit_id!r}] must contain only "
                        "WeaponAttachment values",
                    )
                if attachment.source_equipment_index in weapon_by_source_index:
                    raise ValueError(
                        f"unit {unit_id!r} has duplicate weapon source index "
                        f"{attachment.source_equipment_index}",
                    )
                weapon_by_source_index[
                    attachment.source_equipment_index
                ] = attachment
            weapon_order = tuple(
                (
                    -attachment.weapon.definition.max_range_m,
                    attachment.source_equipment_index,
                    attachment.weapon.weapon_id,
                )
                for attachment in weapons
            )
            if weapon_order != tuple(sorted(weapon_order)):
                raise ValueError(
                    f"unit {unit_id!r} weapon attachments must retain "
                    "canonical range/source/ID order",
                )

            sensor_indexes = tuple(
                attachment.source_equipment_index
                for attachment in sensor_attachments
            )
            if sensor_indexes != tuple(sorted(sensor_indexes)):
                raise ValueError(
                    f"unit {unit_id!r} sensor attachments must retain source "
                    "equipment order",
                )
            if len(sensor_indexes) != len(set(sensor_indexes)):
                raise ValueError(
                    f"unit {unit_id!r} has duplicate sensor source indexes",
                )
            sensor_by_source_index: dict[int, SensorAttachment] = {}
            for attachment in sensor_attachments:
                if not isinstance(attachment, SensorAttachment):
                    raise TypeError(
                        f"unit_sensor_attachments[{unit_id!r}] must contain "
                        "only SensorAttachment values",
                    )
                sensor_by_source_index[
                    attachment.source_equipment_index
                ] = attachment
                expected_indexes = tuple(sorted(
                    source_index
                    for source_index, weapon_attachment
                    in weapon_by_source_index.items()
                    if weapon_attachment.modeled_role
                    in attachment.compatible_weapon_roles
                ))
                if (
                    attachment.compatible_weapon_source_indexes
                    != expected_indexes
                ):
                    raise ValueError(
                        f"unit {unit_id!r} sensor source index "
                        f"{attachment.source_equipment_index} declares resolved "
                        "weapon indexes "
                        f"{attachment.compatible_weapon_source_indexes!r}, "
                        f"expected {expected_indexes!r}",
                    )

            resolution_by_key: dict[
                tuple[EquipmentCategory, int],
                EquipmentResolution,
            ] = {}
            resolution_indexes: list[int] = []
            for resolution in resolutions:
                if not isinstance(resolution, EquipmentResolution):
                    raise TypeError(
                        f"equipment_resolutions[{unit_id!r}] must contain "
                        "only EquipmentResolution values",
                    )
                if resolution.unit_id != unit_id:
                    raise ValueError(
                        f"RuntimeLoadouts key {unit_id!r} contains resolution "
                        f"for unit {resolution.unit_id!r}",
                    )
                key = (resolution.category, resolution.source_equipment_index)
                if key in resolution_by_key:
                    raise ValueError(
                        f"unit {unit_id!r} has duplicate resolution for "
                        f"{resolution.category.name} source index "
                        f"{resolution.source_equipment_index}",
                    )
                resolution_by_key[key] = resolution
                resolution_indexes.append(resolution.source_equipment_index)
            if resolution_indexes != sorted(resolution_indexes):
                raise ValueError(
                    f"unit {unit_id!r} equipment resolutions must retain "
                    "source equipment order",
                )
            if len(resolution_indexes) != len(set(resolution_indexes)):
                raise ValueError(
                    f"unit {unit_id!r} has duplicate equipment resolution "
                    "source indexes",
                )

            for attachment in weapons:
                resolution = resolution_by_key.get((
                    EquipmentCategory.WEAPON,
                    attachment.source_equipment_index,
                ))
                if (
                    resolution is None
                    or resolution.disposition
                    is not ResolutionDisposition.ATTACHMENT
                    or resolution.source_equipment
                    is not attachment.source_equipment
                    or resolution.target_id != attachment.weapon.weapon_id
                    or resolution.modeled_role is not attachment.modeled_role
                    or resolution.reference_kind
                    is not attachment.reference_kind
                ):
                    raise ValueError(
                        f"unit {unit_id!r} weapon source index "
                        f"{attachment.source_equipment_index} lacks an exact "
                        "attachment resolution",
                    )
            for attachment in sensor_attachments:
                resolution = resolution_by_key.get((
                    EquipmentCategory.SENSOR,
                    attachment.source_equipment_index,
                ))
                if (
                    resolution is None
                    or resolution.disposition
                    is not ResolutionDisposition.ATTACHMENT
                    or resolution.source_equipment
                    is not attachment.source_equipment
                    or resolution.target_id != attachment.sensor.sensor_id
                    or resolution.modeled_role is not attachment.modeled_role
                    or resolution.reference_kind
                    is not attachment.reference_kind
                ):
                    raise ValueError(
                        f"unit {unit_id!r} sensor source index "
                        f"{attachment.source_equipment_index} lacks an exact "
                        "attachment resolution",
                    )
            for resolution in resolutions:
                if resolution.disposition is not ResolutionDisposition.ATTACHMENT:
                    if resolution.disposition is ResolutionDisposition.STORE:
                        linked_weapon = weapon_by_source_index.get(
                            resolution.attached_to_equipment_index,
                        )
                        if (
                            linked_weapon is None
                            or linked_weapon.weapon.weapon_id
                            != resolution.attached_to_target_id
                            or resolution.target_id
                            not in {
                                ammunition.ammo_id
                                for ammunition in linked_weapon.ammunition
                            }
                        ):
                            raise ValueError(
                                f"unit {unit_id!r} store resolution at source "
                                f"index {resolution.source_equipment_index} "
                                "does not match an exact weapon/ammunition "
                                "attachment",
                            )
                    continue
                attachment = (
                    weapon_by_source_index.get(
                        resolution.source_equipment_index,
                    )
                    if resolution.category is EquipmentCategory.WEAPON
                    else sensor_by_source_index.get(
                        resolution.source_equipment_index,
                    )
                )
                if attachment is None:
                    raise ValueError(
                        f"unit {unit_id!r} {resolution.category.name.lower()} "
                        f"resolution at source index "
                        f"{resolution.source_equipment_index} has no exact "
                        "live attachment",
                    )

            normalized_sensors[unit_id] = tuple(
                attachment.sensor
                for attachment in sensor_attachments
            )

        object.__setattr__(
            self,
            "unit_weapons",
            MappingProxyType(normalized_weapons),
        )
        object.__setattr__(
            self,
            "unit_sensor_attachments",
            MappingProxyType(normalized_sensor_attachments),
        )
        object.__setattr__(
            self,
            "equipment_resolutions",
            MappingProxyType(normalized_resolutions),
        )
        object.__setattr__(
            self,
            "unit_sensors",
            MappingProxyType(normalized_sensors),
        )

    @property
    def weapons(self) -> Mapping[str, tuple[WeaponAttachment, ...]]:
        return self.unit_weapons

    @property
    def sensors(self) -> Mapping[str, tuple[SensorInstance, ...]]:
        return self.unit_sensors

    @property
    def sensor_attachments(self) -> Mapping[str, tuple[SensorAttachment, ...]]:
        return self.unit_sensor_attachments

    @property
    def resolutions(self) -> Mapping[str, tuple[EquipmentResolution, ...]]:
        return self.equipment_resolutions

    def topology(self) -> dict[str, list[dict[str, Any]]]:
        """Return transparent, canonicalizable ordered attachment decisions."""
        return {
            unit_id: [
                resolution.topology()
                for resolution in self.equipment_resolutions[unit_id]
            ]
            for unit_id in sorted(self.equipment_resolutions)
        }

    def topology_fingerprint(self) -> str:
        """Return SHA-256 of the current ordered resolution topology."""
        return _sha256_payload(self.topology())


@dataclass(frozen=True, slots=True)
class _EquipmentPlan:
    source_equipment_index: int
    record: EquipmentMappingRecord
    target_id: str | None = None
    ammo_ids: tuple[str, ...] = ()
    attached_to_equipment_index: int | None = None
    attached_to_target_id: str | None = None


def _canonical_value(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "record_type": type(value).__name__,
            **{
                field.name: _canonical_value(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_canonical_value(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
    return value


def _sha256_payload(payload: Any) -> str:
    serialized = json.dumps(
        _canonical_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _coerce_assignments(
    assignments: Mapping[str, str] | Sequence[WeaponAssignment],
) -> tuple[
    tuple[WeaponAssignment, ...],
    Mapping[str, WeaponAssignment],
]:
    if isinstance(assignments, Mapping):
        frozen = tuple(
            WeaponAssignment(equipment_name=name, weapon_id=weapon_id)
            for name, weapon_id in sorted(assignments.items())
        )
    elif isinstance(assignments, Sequence) and not isinstance(
        assignments,
        (str, bytes),
    ):
        frozen = tuple(assignments)
    else:
        raise TypeError(
            "assignment_overrides must be a mapping or ordered sequence "
            "of WeaponAssignment records",
        )

    seen: dict[str, int] = {}
    for index, assignment in enumerate(frozen):
        if not isinstance(assignment, WeaponAssignment):
            raise TypeError(
                "Typed assignment sequence contains "
                f"{type(assignment).__name__} at index {index}",
            )
        if assignment.equipment_name in seen:
            raise EquipmentMappingError(
                "Duplicate weapon assignment for "
                f"{assignment.equipment_name!r} at indexes "
                f"{seen[assignment.equipment_name]} and {index}",
            )
        seen[assignment.equipment_name] = index
    return frozen, MappingProxyType({
        assignment.equipment_name: assignment
        for assignment in frozen
    })


def _definition_context(
    unit_type: str,
    source_index: int,
    category: EquipmentCategory,
    equipment_name: str,
) -> str:
    return (
        f"unit_type {unit_type!r} equipment[{source_index}] "
        f"{equipment_name!r} ({category.name})"
    )


def _runtime_context(
    unit: Unit,
    source_index: int,
    equipment: EquipmentItem,
) -> str:
    return (
        f"unit {unit.entity_id!r} ({unit.unit_type!r}) equipment[{source_index}] "
        f"{equipment.name!r} ({equipment.category.name})"
    )


@dataclass(frozen=True, slots=True, init=False)
class RuntimeLoadoutBuilder:
    """Preflight and build all reachable loadouts through one strict boundary."""

    _weapon_definitions: Mapping[str, WeaponDefinition]
    _ammo_definitions: Mapping[str, AmmoDefinition]
    _sensor_definitions: Mapping[str, SensorDefinition]
    _unit_definitions: Mapping[str, UnitDefinition]
    _era_config: EraConfig
    _registry: EquipmentMappingRegistry
    _assignments: tuple[WeaponAssignment, ...]
    _assignment_index: Mapping[str, WeaponAssignment]
    _reachable_unit_types: tuple[str, ...]
    _plans: Mapping[str, tuple[_EquipmentPlan, ...]]
    _fingerprint: str

    def __init__(
        self,
        *,
        weapon_loader: WeaponLoader,
        ammo_loader: AmmoLoader,
        sensor_loader: SensorLoader,
        unit_definitions: Mapping[str, UnitDefinition],
        era_config: EraConfig,
        assignment_overrides: (
            Mapping[str, str] | Sequence[WeaponAssignment]
        ),
        reachable_unit_types: Sequence[str],
        registry: EquipmentMappingRegistry,
    ) -> None:
        if not isinstance(weapon_loader, WeaponLoader):
            raise TypeError("weapon_loader must be a concrete WeaponLoader")
        if not isinstance(ammo_loader, AmmoLoader):
            raise TypeError("ammo_loader must be a concrete AmmoLoader")
        if not isinstance(sensor_loader, SensorLoader):
            raise TypeError("sensor_loader must be a concrete SensorLoader")
        if not isinstance(era_config, EraConfig):
            raise TypeError("era_config must be an effective EraConfig")
        if not isinstance(registry, EquipmentMappingRegistry):
            raise TypeError("registry must be an EquipmentMappingRegistry")
        if not isinstance(unit_definitions, Mapping):
            raise TypeError("unit_definitions must be a mapping")
        if not isinstance(reachable_unit_types, Sequence) or isinstance(
            reachable_unit_types,
            (str, bytes),
        ):
            raise TypeError("reachable_unit_types must be an ordered sequence")

        frozen_units: dict[str, UnitDefinition] = {}
        for key, definition in unit_definitions.items():
            _require_trimmed(key, "unit_definitions key")
            if not isinstance(definition, UnitDefinition):
                raise TypeError(
                    f"unit_definitions[{key!r}] must be a UnitDefinition",
                )
            if definition.unit_type != key:
                raise EquipmentMappingError(
                    f"Unit definition key {key!r} does not match "
                    f"definition.unit_type {definition.unit_type!r}",
                )
            frozen_units[key] = definition.model_copy(deep=True)

        reachable: set[str] = set()
        for unit_type in reachable_unit_types:
            _require_trimmed(unit_type, "reachable unit_type")
            reachable.add(unit_type)

        assignments, assignment_index = _coerce_assignments(
            assignment_overrides,
        )
        object.__setattr__(
            self,
            "_weapon_definitions",
            MappingProxyType({
                weapon_id: WeaponDefinition.model_validate(
                    definition.model_dump(mode="python"),
                )
                for weapon_id, definition in weapon_loader.definitions().items()
            }),
        )
        object.__setattr__(
            self,
            "_ammo_definitions",
            MappingProxyType({
                ammo_id: AmmoDefinition.model_validate(
                    definition.model_dump(mode="python"),
                )
                for ammo_id, definition in ammo_loader.definitions().items()
            }),
        )
        object.__setattr__(
            self,
            "_sensor_definitions",
            MappingProxyType({
                sensor_id: SensorDefinition.model_validate(
                    definition.model_dump(mode="python"),
                )
                for sensor_id, definition in sensor_loader.definitions().items()
            }),
        )
        object.__setattr__(
            self,
            "_unit_definitions",
            MappingProxyType(frozen_units),
        )
        object.__setattr__(
            self,
            "_era_config",
            EraConfig.model_validate(era_config.model_dump(mode="python")),
        )
        object.__setattr__(self, "_registry", registry)
        object.__setattr__(self, "_assignments", assignments)
        object.__setattr__(self, "_assignment_index", assignment_index)
        object.__setattr__(
            self,
            "_reachable_unit_types",
            tuple(sorted(reachable)),
        )

        plans = self._preflight_plans()
        object.__setattr__(self, "_plans", MappingProxyType(plans))
        object.__setattr__(self, "_fingerprint", self._compute_fingerprint())

    @property
    def reachable_unit_types(self) -> tuple[str, ...]:
        return self._reachable_unit_types

    @property
    def era_config(self) -> EraConfig:
        """Return an isolated copy of the era gates frozen at preflight."""
        return EraConfig.model_validate(
            self._era_config.model_dump(mode="python"),
        )

    @property
    def registry(self) -> EquipmentMappingRegistry:
        return self._registry

    @property
    def assignments(self) -> tuple[WeaponAssignment, ...]:
        return self._assignments

    def preflight(self) -> None:
        """Repeat reachable validation against the builder's frozen envelope."""
        self._preflight_plans()

    def fingerprint(self) -> str:
        """Return active SHA-256 over the frozen reachable build envelope."""
        return self._fingerprint

    def topology(
        self,
        loadouts: RuntimeLoadouts,
    ) -> dict[str, list[dict[str, Any]]]:
        """Expose the transparent ordered topology produced by this boundary."""
        if not isinstance(loadouts, RuntimeLoadouts):
            raise TypeError("loadouts must be RuntimeLoadouts")
        return loadouts.topology()

    def _preflight_plans(self) -> dict[str, tuple[_EquipmentPlan, ...]]:
        plans: dict[str, tuple[_EquipmentPlan, ...]] = {}
        used_assignments: set[str] = set()
        for unit_type in self._reachable_unit_types:
            try:
                definition = self._unit_definitions[unit_type]
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"Reachable unit_type {unit_type!r} has no effective "
                    "UnitDefinition",
                ) from exc
            plans[unit_type] = self._preflight_unit(
                definition,
                used_assignments,
            )

        stale_assignments = sorted(
            set(self._assignment_index) - used_assignments,
        )
        if stale_assignments:
            raise EquipmentMappingError(
                "Weapon assignments do not name reachable declared weapon "
                f"equipment: {stale_assignments}",
            )
        return plans

    def _preflight_unit(
        self,
        definition: UnitDefinition,
        used_assignments: set[str],
    ) -> tuple[_EquipmentPlan, ...]:
        plans: list[_EquipmentPlan] = []
        attachment_plans: list[_EquipmentPlan] = []
        sensor_attachments = 0

        if (
            not self._era_config.feature_enabled("data_links")
            and definition.data_link_range is not None
            and definition.data_link_range > 0
        ):
            raise EquipmentMappingError(
                f"unit_type {definition.unit_type!r}: era feature "
                f"'data_links' is disabled but data_link_range="
                f"{definition.data_link_range}",
            )

        for source_index, equipment in enumerate(definition.equipment):
            try:
                category = EquipmentCategory[equipment.category.upper()]
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"unit_type {definition.unit_type!r} equipment[{source_index}] "
                    f"{equipment.name!r}: unknown category {equipment.category!r}",
                ) from exc
            if category not in (
                EquipmentCategory.WEAPON,
                EquipmentCategory.SENSOR,
            ):
                continue

            context = _definition_context(
                definition.unit_type,
                source_index,
                category,
                equipment.name,
            )
            record = self._registry.get(category, equipment.name)
            if record is None:
                raise EquipmentMappingError(f"{context}: no mapping declaration")
            if isinstance(
                record,
                (WeaponUnsupportedMapping, SensorUnsupportedMapping),
            ):
                raise UnsupportedEquipmentError(
                    f"{context}: explicitly unsupported: {record.reason}",
                )

            if isinstance(record, WeaponAttachmentMapping):
                assignment = self._assignment_index.get(equipment.name)
                target_id = record.weapon_id
                if assignment is not None:
                    used_assignments.add(equipment.name)
                    target_id = assignment.weapon_id
                    if not record.permits_target(target_id):
                        raise EquipmentMappingError(
                            f"{context}: assignment target {target_id!r} "
                            "contradicts the registry identity/role contract "
                            f"for {record.weapon_id!r}",
                        )
                ammo_definitions = self._validate_weapon_target(
                    context,
                    target_id,
                    record,
                )
                plan = _EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                    target_id=target_id,
                    ammo_ids=tuple(
                        ammo.ammo_id for ammo in ammo_definitions
                    ),
                )
                plans.append(plan)
                attachment_plans.append(plan)
            elif isinstance(record, WeaponStoreMapping):
                self._validate_store_target(context, record)
                plans.append(_EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                    target_id=record.ammo_id,
                ))
            elif isinstance(record, WeaponNonRuntimeMapping):
                if equipment.name in self._assignment_index:
                    used_assignments.add(equipment.name)
                    raise EquipmentMappingError(
                        f"{context}: weapon assignment cannot convert explicit "
                        "non-runtime equipment into a live attachment",
                    )
                plans.append(_EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                ))
            elif isinstance(record, SensorAttachmentMapping):
                shooter_domain = runtime_domain_for_definition(definition)
                allowed_shooter_domains = (
                    allowed_shooter_domains_for_sensor_role(
                        record.modeled_role,
                    )
                )
                if shooter_domain not in allowed_shooter_domains:
                    raise EquipmentMappingError(
                        f"{context}: sensor role {record.modeled_role.value!r} "
                        f"cannot be mounted on shooter domain "
                        f"{shooter_domain.name}; allowed domains are "
                        f"{[domain.name for domain in allowed_shooter_domains]}",
                    )
                self._validate_sensor_target(context, record)
                plans.append(_EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                    target_id=record.sensor_id,
                ))
                sensor_attachments += 1
            elif isinstance(record, SensorNonRuntimeMapping):
                plans.append(_EquipmentPlan(
                    source_equipment_index=source_index,
                    record=record,
                ))
            else:  # pragma: no cover - the typed registry makes this impossible
                raise AssertionError(f"Unhandled mapping record {record!r}")

        plans = self._link_stores(
            definition.unit_type,
            plans,
            attachment_plans,
        )
        if definition.sensor_policy is SensorPolicy.REQUIRED:
            if sensor_attachments == 0:
                raise EquipmentMappingError(
                    f"unit_type {definition.unit_type!r}: "
                    "sensor_policy='required' produced no live sensor attachment",
                )
        elif definition.sensor_policy is SensorPolicy.INTENTIONALLY_NONE:
            if sensor_attachments:
                raise EquipmentMappingError(
                    f"unit_type {definition.unit_type!r}: "
                    "sensor_policy='intentionally_none' produced a sensor",
                )
            _require_trimmed(
                definition.sensor_policy_reason,
                f"unit_type {definition.unit_type!r} sensor_policy_reason",
            )
        else:  # pragma: no cover - Pydantic validates this enum
            raise EquipmentMappingError(
                f"unit_type {definition.unit_type!r}: unhandled sensor policy "
                f"{definition.sensor_policy!r}",
            )
        return tuple(plans)

    def _validate_weapon_target(
        self,
        context: str,
        target_id: str,
        record: WeaponAttachmentMapping,
    ) -> tuple[AmmoDefinition, ...]:
        try:
            definition = self._weapon_definitions[target_id]
        except KeyError as exc:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} is absent from the "
                "effective catalog",
            ) from exc
        try:
            category = definition.parsed_category()
        except (KeyError, ValueError) as exc:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} has invalid category "
                f"{definition.category!r}",
            ) from exc
        if category is not record.expected_weapon_category:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} category "
                f"{category.name} does not match required "
                f"{record.expected_weapon_category.name}",
            )
        try:
            guidance = definition.parsed_guidance()
        except (KeyError, ValueError) as exc:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} has invalid guidance "
                f"{definition.guidance!r}",
            ) from exc
        if (
            record.expected_guidance is not None
            and guidance is not record.expected_guidance
        ):
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} guidance "
                f"{guidance.name} does not match required "
                f"{record.expected_guidance.name}",
            )
        if (
            record.expected_caliber_mm is not None
            and not math.isclose(
                definition.caliber_mm,
                float(record.expected_caliber_mm),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} caliber "
                f"{definition.caliber_mm} mm does not match required "
                f"{record.expected_caliber_mm} mm",
            )
        if definition.magazine_capacity <= 0:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} has no usable "
                f"magazine capacity ({definition.magazine_capacity})",
            )
        compatible_ids = tuple(definition.compatible_ammo)
        _require_string_tuple(
            compatible_ids,
            f"{context} weapon target {target_id!r} compatible_ammo",
            non_empty=True,
        )
        ammunition_by_id: dict[str, AmmoDefinition] = {}
        ammo_type_by_id: dict[str, AmmoType] = {}
        ammo_guidance_by_id: dict[str, GuidanceType] = {}
        for ammo_id in compatible_ids:
            try:
                ammo = self._ammo_definitions[ammo_id]
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"{context}: weapon target {target_id!r} references missing "
                    f"ammunition {ammo_id!r}",
                ) from exc
            try:
                ammo_type = ammo.parsed_ammo_type()
                ammo_guidance = ammo.parsed_guidance()
            except (KeyError, ValueError) as exc:
                raise EquipmentMappingError(
                    f"{context}: ammunition {ammo_id!r} has an invalid typed "
                    "ammo_type or guidance",
                ) from exc
            ammunition_by_id[ammo_id] = ammo
            ammo_type_by_id[ammo_id] = ammo_type
            ammo_guidance_by_id[ammo_id] = ammo_guidance

        selected_ids = (
            record.allowed_ammo_ids
            if record.allowed_ammo_ids
            else compatible_ids
        )
        disallowed_ids = [
            ammo_id
            for ammo_id in selected_ids
            if ammo_id not in ammunition_by_id
        ]
        if disallowed_ids:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} does not declare "
                f"mapping-allowed ammunition {disallowed_ids}",
            )
        ammunition = [
            ammunition_by_id[ammo_id]
            for ammo_id in selected_ids
        ]
        ammo_types = {
            ammo_type_by_id[ammo_id]
            for ammo_id in selected_ids
        }
        for ammo in ammunition:
            self._validate_era_guidance(
                context,
                target_id,
                ammo.ammo_id,
                ammo_guidance_by_id[ammo.ammo_id],
            )

        missing_ammo_types = [
            ammo_type.name
            for ammo_type in record.required_ammo_types
            if ammo_type not in ammo_types
        ]
        if missing_ammo_types:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} lacks required "
                f"ammunition roles {missing_ammo_types}",
            )

        actual_domains: set[Domain] = set()
        for domain_name in definition.effective_target_domains():
            try:
                actual_domains.add(Domain[domain_name.upper()])
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"{context}: weapon target {target_id!r} has invalid target "
                    f"domain {domain_name!r}",
                ) from exc
        missing_domains = [
            domain.name
            for domain in record.required_target_domains
            if domain not in actual_domains
        ]
        if missing_domains:
            raise EquipmentMappingError(
                f"{context}: weapon target {target_id!r} lacks required target "
                f"domains {missing_domains}",
            )
        self._validate_era_guidance(
            context,
            target_id,
            None,
            guidance,
        )
        return tuple(ammunition)

    def _validate_era_guidance(
        self,
        context: str,
        weapon_id: str,
        ammo_id: str | None,
        guidance: GuidanceType,
    ) -> None:
        reference = (
            f"ammunition {ammo_id!r} for weapon {weapon_id!r}"
            if ammo_id is not None
            else f"weapon {weapon_id!r}"
        )
        if (
            not self._era_config.feature_enabled("gps")
            and guidance is GuidanceType.GPS
        ):
            raise EquipmentMappingError(
                f"{context}: era feature 'gps' is disabled but {reference} "
                "uses GPS guidance",
            )
        if (
            not self._era_config.feature_enabled("pgm")
            and guidance is not GuidanceType.NONE
        ):
            raise EquipmentMappingError(
                f"{context}: era feature 'pgm' is disabled but {reference} "
                f"uses {guidance.name} guidance",
            )

    def _validate_store_target(
        self,
        context: str,
        record: WeaponStoreMapping,
    ) -> None:
        try:
            ammo = self._ammo_definitions[record.ammo_id]
        except KeyError as exc:
            raise EquipmentMappingError(
                f"{context}: store ammunition {record.ammo_id!r} is absent "
                "from the effective catalog",
            ) from exc
        try:
            ammo_type = ammo.parsed_ammo_type()
            ammo_guidance = ammo.parsed_guidance()
        except (KeyError, ValueError) as exc:
            raise EquipmentMappingError(
                f"{context}: store ammunition {record.ammo_id!r} has an "
                "invalid typed ammo_type or guidance",
            ) from exc
        if (
            record.expected_ammo_type is not None
            and ammo_type is not record.expected_ammo_type
        ):
            raise EquipmentMappingError(
                f"{context}: store ammunition {record.ammo_id!r} type "
                f"{ammo_type.name} does not match required "
                f"{record.expected_ammo_type.name}",
            )
        self._validate_era_guidance(
            context,
            "<store attachment pending>",
            record.ammo_id,
            ammo_guidance,
        )

    def _validate_sensor_target(
        self,
        context: str,
        record: SensorAttachmentMapping,
    ) -> None:
        try:
            definition = self._sensor_definitions[record.sensor_id]
        except KeyError as exc:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} is absent from "
                "the effective catalog",
            ) from exc
        try:
            sensor_type = definition.parsed_sensor_type()
        except (KeyError, ValueError) as exc:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} has invalid "
                f"sensor_type {definition.sensor_type!r}",
            ) from exc
        if sensor_type is not record.expected_sensor_type:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} type "
                f"{sensor_type.name} does not match required "
                f"{record.expected_sensor_type.name}",
            )
        try:
            signature_domain = signature_domain_for_sensor_type(sensor_type)
        except ValueError as exc:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} is not handled "
                "by the production detection path",
            ) from exc
        if signature_domain is not record.expected_signature_domain:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} production "
                f"domain {signature_domain.name} does not match required "
                f"{record.expected_signature_domain.name}",
            )

        authored_domains: list[SignatureDomain] = []
        for domain_name in definition.detects_domain:
            try:
                authored_domains.append(
                    SignatureDomain[domain_name.upper()],
                )
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"{context}: sensor target {record.sensor_id!r} has invalid "
                    f"detects_domain value {domain_name!r}",
                ) from exc
        if authored_domains != [signature_domain]:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} authored "
                f"detects_domain {[domain.name for domain in authored_domains]} "
                "disagrees with production dispatch "
                f"{signature_domain.name}",
            )

        actual_target_domains: set[Domain] = set()
        for domain_name in definition.effective_target_domains():
            try:
                actual_target_domains.add(Domain[domain_name.upper()])
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"{context}: sensor target {record.sensor_id!r} has invalid "
                    f"target domain {domain_name!r}",
                ) from exc
        missing_target_domains = [
            domain.name
            for domain in record.required_target_domains
            if domain not in actual_target_domains
        ]
        if missing_target_domains:
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} lacks required "
                f"target domains {missing_target_domains}",
            )

        allowed_sensor_types = {
            sensor_name.upper()
            for sensor_name in self._era_config.available_sensor_types
        }
        if (
            allowed_sensor_types
            and sensor_type.name not in allowed_sensor_types
        ):
            raise EquipmentMappingError(
                f"{context}: era available_sensor_types forbids "
                f"{sensor_type.name} sensor {record.sensor_id!r}",
            )
        if (
            sensor_type is SensorType.THERMAL
            and not self._era_config.feature_enabled("thermal_sights")
        ):
            raise EquipmentMappingError(
                f"{context}: era feature 'thermal_sights' is disabled but "
                f"sensor {record.sensor_id!r} is THERMAL",
            )
        if (
            record.modeled_max_range_m is not None
            and record.modeled_max_range_m > definition.max_range_m
        ):
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} catalog range "
                f"{definition.max_range_m} m is below mapping-owned envelope "
                f"{record.modeled_max_range_m} m",
            )
        if (
            record.modeled_fov_deg is not None
            and record.modeled_fov_deg > definition.fov_deg
        ):
            raise EquipmentMappingError(
                f"{context}: sensor target {record.sensor_id!r} catalog FOV "
                f"{definition.fov_deg} degrees is below mapping-owned envelope "
                f"{record.modeled_fov_deg} degrees",
            )

    def _link_stores(
        self,
        unit_type: str,
        plans: list[_EquipmentPlan],
        attachment_plans: list[_EquipmentPlan],
    ) -> list[_EquipmentPlan]:
        linked: list[_EquipmentPlan] = []
        for plan in plans:
            if not isinstance(plan.record, WeaponStoreMapping):
                linked.append(plan)
                continue
            candidates = [
                attachment
                for attachment in attachment_plans
                if (
                    attachment.target_id
                    in plan.record.compatible_weapon_ids
                    and plan.record.ammo_id in attachment.ammo_ids
                )
            ]
            context = _definition_context(
                unit_type,
                plan.source_equipment_index,
                EquipmentCategory.WEAPON,
                plan.record.equipment_name,
            )
            if not candidates:
                raise EquipmentMappingError(
                    f"{context}: store {plan.record.ammo_id!r} has no "
                    "compatible same-unit live attachment",
                )
            if len(candidates) != 1:
                indexes = [
                    candidate.source_equipment_index
                    for candidate in candidates
                ]
                raise EquipmentMappingError(
                    f"{context}: store {plan.record.ammo_id!r} ambiguously "
                    f"matches attachment equipment indexes {indexes}",
                )
            attachment = candidates[0]
            linked.append(_EquipmentPlan(
                source_equipment_index=plan.source_equipment_index,
                record=plan.record,
                target_id=plan.target_id,
                attached_to_equipment_index=(
                    attachment.source_equipment_index
                ),
                attached_to_target_id=attachment.target_id,
            ))
        return linked

    def _compute_fingerprint(self) -> str:
        reachable_record_keys = {
            (plan.record.category, plan.record.equipment_name)
            for plans in self._plans.values()
            for plan in plans
        }
        reachable_records = [
            record
            for record in self._registry.records
            if (record.category, record.equipment_name)
            in reachable_record_keys
        ]

        referenced_weapon_ids = sorted({
            plan.target_id
            for plans in self._plans.values()
            for plan in plans
            if isinstance(plan.record, WeaponAttachmentMapping)
            and plan.target_id is not None
        })
        referenced_ammo_ids = sorted({
            ammo_id
            for plans in self._plans.values()
            for plan in plans
            for ammo_id in (
                plan.ammo_ids
                if isinstance(plan.record, WeaponAttachmentMapping)
                else (
                    (plan.target_id,)
                    if isinstance(plan.record, WeaponStoreMapping)
                    and plan.target_id is not None
                    else ()
                )
            )
        })
        referenced_sensor_ids = sorted({
            plan.target_id
            for plans in self._plans.values()
            for plan in plans
            if isinstance(plan.record, SensorAttachmentMapping)
            and plan.target_id is not None
        })
        payload = {
            "registry_records": reachable_records,
            "units": {
                unit_type: definition.model_dump(mode="python")
                for unit_type, definition in sorted(
                    (
                        (unit_type, self._unit_definitions[unit_type])
                        for unit_type in self._reachable_unit_types
                    ),
                )
            },
            "weapons": {
                weapon_id: self._weapon_definitions[weapon_id]
                for weapon_id in referenced_weapon_ids
            },
            "ammunition": {
                ammo_id: self._ammo_definitions[ammo_id]
                for ammo_id in referenced_ammo_ids
            },
            "sensors": {
                sensor_id: self._sensor_definitions[sensor_id]
                for sensor_id in referenced_sensor_ids
            },
            "era": self._era_config,
            "assignments": sorted(
                self._assignments,
                key=lambda assignment: assignment.equipment_name,
            ),
            "plans": self._plans,
        }
        return _sha256_payload(payload)

    def build(self, units: Sequence[Unit]) -> RuntimeLoadouts:
        """Atomically construct deterministic live attachments for *units*."""
        if not isinstance(units, Sequence) or isinstance(units, (str, bytes)):
            raise TypeError("units must be an ordered sequence")
        seen_ids: dict[str, int] = {}
        for index, unit in enumerate(units):
            if not isinstance(unit, Unit):
                raise TypeError(
                    f"units[{index}] must be a Unit, got {type(unit).__name__}",
                )
            if not unit.entity_id or not unit.entity_id.strip():
                raise EquipmentMappingError(
                    f"units[{index}] has an empty unit ID",
                )
            if unit.entity_id in seen_ids:
                raise EquipmentMappingError(
                    f"Duplicate unit ID {unit.entity_id!r} at indexes "
                    f"{seen_ids[unit.entity_id]} and {index}",
                )
            seen_ids[unit.entity_id] = index
            self._validate_runtime_topology(unit)

        unit_weapons: dict[str, tuple[WeaponAttachment, ...]] = {}
        unit_sensor_attachments: dict[
            str,
            tuple[SensorAttachment, ...],
        ] = {}
        unit_resolutions: dict[str, tuple[EquipmentResolution, ...]] = {}
        for unit in units:
            weapons: list[WeaponAttachment] = []
            for plan in self._plans[unit.unit_type]:
                record = plan.record
                if not isinstance(record, WeaponAttachmentMapping):
                    continue
                if plan.target_id is None:
                    raise AssertionError("Validated weapon plan has no target")
                equipment = unit.equipment[plan.source_equipment_index]
                definition = self._weapon_definitions[plan.target_id]
                # A catalog target can be a deliberately broad same-role
                # abstraction. The mapping remains the runtime authority for
                # this attachment's exact engagement envelope.
                runtime_definition = WeaponDefinition.model_validate({
                    **definition.model_dump(mode="python"),
                    "target_domains": [
                        domain.name
                        for domain in record.required_target_domains
                    ],
                    "compatible_ammo": list(plan.ammo_ids),
                    "rate_of_fire_rpm": (
                        definition.rate_of_fire_rpm
                        * record.runtime_system_multiplier
                    ),
                    # Aggregate systems produce more firing events, not more
                    # rounds in each target-system burst.
                    "burst_size": definition.burst_size,
                    "magazine_capacity": (
                        definition.magazine_capacity
                        * record.runtime_system_multiplier
                    ),
                    "barrel_life_rounds": (
                        definition.barrel_life_rounds
                        * record.runtime_system_multiplier
                    ),
                })
                ammo_definitions = tuple(
                    self._ammo_definitions[ammo_id]
                    for ammo_id in plan.ammo_ids
                )
                instance = WeaponInstance(
                    definition=runtime_definition,
                    ammo_state=AmmoState(rounds_by_type={
                        ammo.ammo_id: runtime_definition.magazine_capacity
                        for ammo in ammo_definitions
                    }),
                    equipment=equipment,
                )
                weapons.append(WeaponAttachment(
                    weapon=instance,
                    ammunition=ammo_definitions,
                    source_equipment=equipment,
                    source_equipment_index=plan.source_equipment_index,
                    modeled_role=record.modeled_role,
                    reference_kind=record.reference_kind,
                    mapping_rationale=record.rationale,
                    mapping_source=record.source,
                    source_system_count=record.source_system_count,
                    target_system_count=record.target_system_count,
                    runtime_system_multiplier=(
                        record.runtime_system_multiplier
                    ),
                ))

            weapon_by_source_index = {
                attachment.source_equipment_index: attachment
                for attachment in weapons
            }
            if len(weapon_by_source_index) != len(weapons):
                raise AssertionError("Validated weapon source indexes collided")

            sensor_attachments: list[SensorAttachment] = []
            resolutions: list[EquipmentResolution] = []
            for plan in self._plans[unit.unit_type]:
                equipment = unit.equipment[plan.source_equipment_index]
                record = plan.record
                if isinstance(record, WeaponAttachmentMapping):
                    if plan.target_id is None:
                        raise AssertionError("Validated weapon plan has no target")
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.WEAPON,
                        disposition=ResolutionDisposition.ATTACHMENT,
                        modeled_role=record.modeled_role,
                        reference_kind=record.reference_kind,
                        target_id=plan.target_id,
                        source_system_count=record.source_system_count,
                        target_system_count=record.target_system_count,
                        runtime_system_multiplier=(
                            record.runtime_system_multiplier
                        ),
                    ))
                elif isinstance(record, WeaponStoreMapping):
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.WEAPON,
                        disposition=ResolutionDisposition.STORE,
                        reference_kind=record.reference_kind,
                        target_id=record.ammo_id,
                        attached_to_equipment_index=(
                            plan.attached_to_equipment_index
                        ),
                        attached_to_target_id=plan.attached_to_target_id,
                    ))
                elif isinstance(record, WeaponNonRuntimeMapping):
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.WEAPON,
                        disposition=ResolutionDisposition.NON_RUNTIME,
                        reason=record.reason,
                    ))
                elif isinstance(record, SensorAttachmentMapping):
                    if plan.target_id is None:
                        raise AssertionError("Validated sensor plan has no target")
                    definition = self._sensor_definitions[plan.target_id]
                    runtime_definition = SensorDefinition.model_validate({
                        **definition.model_dump(mode="python"),
                        "max_range_m": (
                            record.modeled_max_range_m
                            if record.modeled_max_range_m is not None
                            else definition.max_range_m
                        ),
                        "fov_deg": (
                            record.modeled_fov_deg
                            if record.modeled_fov_deg is not None
                            else definition.fov_deg
                        ),
                        "target_domains": [
                            domain.name
                            for domain in record.required_target_domains
                        ],
                    })
                    sensor = SensorInstance(
                        runtime_definition,
                        equipment,
                    )
                    compatible_weapon_source_indexes = tuple(sorted(
                        source_index
                        for source_index, weapon_attachment
                        in weapon_by_source_index.items()
                        if weapon_attachment.modeled_role
                        in record.compatible_weapon_roles
                    ))
                    sensor_attachments.append(SensorAttachment(
                        sensor=sensor,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        modeled_role=record.modeled_role,
                        reference_kind=record.reference_kind,
                        mapping_rationale=record.rationale,
                        mapping_source=record.source,
                        compatible_weapon_roles=(
                            record.compatible_weapon_roles
                        ),
                        compatible_weapon_source_indexes=(
                            compatible_weapon_source_indexes
                        ),
                    ))
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.SENSOR,
                        disposition=ResolutionDisposition.ATTACHMENT,
                        modeled_role=record.modeled_role,
                        reference_kind=record.reference_kind,
                        target_id=plan.target_id,
                    ))
                elif isinstance(record, SensorNonRuntimeMapping):
                    resolutions.append(EquipmentResolution(
                        unit_id=unit.entity_id,
                        unit_type=unit.unit_type,
                        source_equipment=equipment,
                        source_equipment_index=plan.source_equipment_index,
                        category=EquipmentCategory.SENSOR,
                        disposition=ResolutionDisposition.NON_RUNTIME,
                        reason=record.reason,
                    ))
                else:  # pragma: no cover - unsupported fails preflight
                    raise AssertionError(f"Unhandled mapping record {record!r}")

            weapons.sort(key=lambda attachment: (
                -attachment.weapon.definition.max_range_m,
                attachment.source_equipment_index,
                attachment.weapon.weapon_id,
            ))
            unit_weapons[unit.entity_id] = tuple(weapons)
            unit_sensor_attachments[unit.entity_id] = tuple(
                sensor_attachments
            )
            unit_resolutions[unit.entity_id] = tuple(resolutions)

        return RuntimeLoadouts(
            unit_weapons=unit_weapons,
            unit_sensor_attachments=unit_sensor_attachments,
            equipment_resolutions=unit_resolutions,
        )

    def _validate_runtime_topology(self, unit: Unit) -> None:
        if unit.unit_type not in self._plans:
            raise EquipmentMappingError(
                f"unit {unit.entity_id!r} has unit_type {unit.unit_type!r} "
                "outside this builder's reachable envelope",
            )
        definition = self._unit_definitions[unit.unit_type]
        expected_domain = runtime_domain_for_definition(definition)
        if unit.domain is not expected_domain:
            raise EquipmentMappingError(
                f"unit {unit.entity_id!r} ({unit.unit_type!r}) has runtime "
                f"domain {unit.domain.name}, expected {expected_domain.name}",
            )
        if len(unit.equipment) != len(definition.equipment):
            raise EquipmentMappingError(
                f"unit {unit.entity_id!r} ({unit.unit_type!r}) has "
                f"{len(unit.equipment)} live equipment items but its effective "
                f"definition has {len(definition.equipment)}",
            )
        equipment_ids: dict[str, int] = {}
        for source_index, (live, authored) in enumerate(
            zip(unit.equipment, definition.equipment, strict=True),
        ):
            if not live.equipment_id or not live.equipment_id.strip():
                raise EquipmentMappingError(
                    f"{_runtime_context(unit, source_index, live)}: empty "
                    "equipment_id",
                )
            if live.equipment_id in equipment_ids:
                raise EquipmentMappingError(
                    f"{_runtime_context(unit, source_index, live)}: duplicate "
                    f"equipment_id also used at index "
                    f"{equipment_ids[live.equipment_id]}",
                )
            equipment_ids[live.equipment_id] = source_index
            try:
                authored_category = EquipmentCategory[
                    authored.category.upper()
                ]
            except KeyError as exc:
                raise EquipmentMappingError(
                    f"Effective unit definition {unit.unit_type!r} has unknown "
                    f"equipment category {authored.category!r}",
                ) from exc
            if (
                live.name != authored.name
                or live.category is not authored_category
                or live.weight_kg != authored.weight_kg
                or live.reliability != authored.reliability
                or live.temperature_range
                != (
                    tuple(authored.temperature_range)
                    if authored.temperature_range
                    else (-40.0, 50.0)
                )
            ):
                raise EquipmentMappingError(
                    f"{_runtime_context(unit, source_index, live)} does not "
                    "match effective authored topology "
                    f"({authored_category.name}, {authored.name!r}, "
                    f"weight_kg={authored.weight_kg}, "
                    f"reliability={authored.reliability}, "
                    "temperature_range="
                    f"{authored.temperature_range!r})",
                )


__all__ = [
    "DuplicateEquipmentMappingError",
    "EquipmentMappingError",
    "EquipmentMappingRecord",
    "EquipmentMappingRegistry",
    "EquipmentResolution",
    "ReferenceKind",
    "ResolutionDisposition",
    "RuntimeLoadoutBuilder",
    "RuntimeLoadouts",
    "SensorAttachment",
    "SensorAttachmentMapping",
    "SensorModeledRole",
    "SensorNonRuntimeMapping",
    "SensorTargetingClass",
    "SensorUnsupportedMapping",
    "UnsupportedEquipmentError",
    "WeaponAssignment",
    "WeaponAttachment",
    "WeaponAttachmentMapping",
    "WeaponModeledRole",
    "WeaponNonRuntimeMapping",
    "WeaponStandoffClass",
    "WeaponStoreMapping",
    "WeaponUnsupportedMapping",
    "allowed_shooter_domains_for_sensor_role",
    "compatible_sensor_roles_for_weapon_role",
    "equipment_name_declares_system_count",
    "required_domains_for_sensor_role",
    "required_domains_for_weapon_role",
    "sensor_targeting_class",
    "weapon_role_supports_target_domain",
    "weapon_standoff_class",
]

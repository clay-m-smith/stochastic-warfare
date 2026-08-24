"""Typed loadout mapping records, semantic policies, and canonical hashing."""

from __future__ import annotations

import enum
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any, TypeAlias, TypeVar

from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import (
    AmmoType,
    GuidanceType,
    WeaponCategory,
)
from stochastic_warfare.core.types import Domain
from stochastic_warfare.detection.sensors import (
    SensorType,
)
from stochastic_warfare.detection.sensor_roles import SensorModeledRole
from stochastic_warfare.detection.signatures import SignatureDomain
from stochastic_warfare.entities.equipment import EquipmentCategory


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

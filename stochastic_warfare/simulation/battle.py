"""Tactical battle manager — detection, engagement, and AI resolution.

Orchestrates the per-tick tactical loop for active engagements.
Evolves Phase 7's ``ScenarioRunner._run_tick()`` with AI commanders
replacing pre-scripted behavior and full C2/logistics integration.
No domain logic lives here — only sequencing and data routing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import WeaponCategory
from stochastic_warfare.combat.engagement import EngagementType
from stochastic_warfare.combat.suppression import UnitSuppressionState
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Domain, ModuleId, Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.events import UnitDestroyedEvent, UnitDisabledEvent
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.morale.state import MoraleState, _MORALE_EFFECTS

from typing import NamedTuple

from shapely import STRtree
from shapely.geometry import Point

from stochastic_warfare.simulation.calibration import CalibrationSchema


class _ObserverModifiers(NamedTuple):
    """Pre-computed per-observer modifiers (Phase 86b).

    Batched once per attacker at tick start to avoid redundant engine
    queries when an attacker engages multiple targets.
    """

    mopp_detection: float = 1.0   # MOPP detection factor [0-1]
    mopp_fov_mod: float = 1.0     # MOPP FOV reduction [0-1]
    mopp_fatigue: float = 1.0     # MOPP fatigue divisor [1.0+]
    mopp_reload_mod: float = 1.0  # MOPP reload multiplier [1.0+]
    mopp_level: int = 0           # MOPP level [0-4]
    altitude_factor: float = 1.0  # Altitude sickness [0.5-1.0]
    readiness: float = 1.0        # Equipment readiness [0-1]


_DEFAULT_OBS_MODS = _ObserverModifiers()

logger = get_logger(__name__)


def _resolve_cal_flat(ctx: Any) -> dict[str, Any]:
    """Get or build the flat calibration dict from *ctx*.

    Returns ``ctx.cal_flat`` when available (the fast path set up by
    :class:`ScenarioLoader`).  Falls back to building one on-the-fly
    for backward compatibility with tests that pass raw dicts or
    ``SimpleNamespace`` contexts.
    """
    flat = getattr(ctx, "cal_flat", None)
    if flat:
        return flat
    cal = getattr(ctx, "calibration", None)
    if cal is None:
        return {}
    if isinstance(cal, CalibrationSchema):
        sides = list(getattr(ctx, "units_by_side", {}).keys())
        return cal.to_flat_dict(sorted(sides) if sides else ["blue", "red"])
    if isinstance(cal, dict):
        return cal
    return {}


class UnitLodTier(IntEnum):
    """Level-of-detail tier for per-unit update frequency (Phase 85)."""

    ACTIVE = 0    # Full processing every tick
    NEARBY = 1    # Reduced: full update every N ticks
    DISTANT = 2   # Minimal: full update every M ticks


# Sensor types that bypass visual weather degradation
_WEATHER_BYPASS_TYPES: frozenset[SensorType] = frozenset({
    SensorType.THERMAL,
    SensorType.RADAR,
    SensorType.ESM,
})

# Phase 44a: weather Pk modifier lookup (by WeatherState int value)
_WEATHER_PK_TABLE: dict[int, float] = {
    0: 1.00,  # CLEAR
    1: 1.00,  # PARTLY_CLOUDY
    2: 0.95,  # OVERCAST
    3: 0.90,  # LIGHT_RAIN
    4: 0.80,  # HEAVY_RAIN
    5: 0.85,  # SNOW
    6: 0.65,  # FOG
    7: 0.55,  # STORM
}


def _compute_weather_pk_modifier(weather_state: int) -> float:
    """Return hit probability modifier for the given weather state."""
    return _WEATHER_PK_TABLE.get(int(weather_state), 1.0)


# Phase 52a: twilight gradation lookup
_TWILIGHT_VISUAL_MODIFIER: dict[str | None, float] = {
    "civil": 0.8,
    "nautical": 0.5,
    "astronomical": 0.3,
    None: 0.2,  # full night
}


def _compute_night_modifiers(illum, night_thermal_floor: float = 0.8) -> tuple[float, float]:
    """Return (visual_modifier, thermal_modifier) from illumination.

    Day → (1.0, 1.0).  At night, visual degrades through twilight
    stages while thermal is barely affected (floor 0.8).
    """
    if illum.is_day:
        return 1.0, 1.0
    stage = getattr(illum, "twilight_stage", None)
    visual = _TWILIGHT_VISUAL_MODIFIER.get(stage, 0.2)
    thermal = max(night_thermal_floor, visual)
    return visual, thermal


# Phase 52b: cross-wind accuracy penalty
def _compute_crosswind_penalty(
    wind_e: float, wind_n: float,
    att_e: float, att_n: float,
    tgt_e: float, tgt_n: float,
    scale: float = 0.03,
) -> float:
    """Return crew skill multiplier due to crosswind [0.7–1.0].

    *scale* is m/s → penalty fraction (default 0.03 → 10 m/s = 30%).
    """
    dx = tgt_e - att_e
    dy = tgt_n - att_n
    if dx == 0.0 and dy == 0.0:
        return 1.0
    heading = math.atan2(dx, dy)
    crosswind = abs(wind_e * math.cos(heading) - wind_n * math.sin(heading))
    return max(0.7, 1.0 - crosswind * scale)


# Phase 62a: WBGT and wind chill helpers for heat/cold casualties
def _compute_wbgt(temperature_c: float, humidity: float) -> float:
    """Simplified Wet Bulb Globe Temperature estimate.

    WBGT ≈ 0.7·T·√(humidity) + 0.3·T.  Threshold for heat stress ~28°C.
    """
    return 0.7 * temperature_c * math.sqrt(max(0.0, min(1.0, humidity))) + 0.3 * temperature_c


def _compute_wind_chill(temperature_c: float, wind_speed_mps: float) -> float:
    """NWS wind chill formula (valid for T ≤ 10°C, V ≥ 4.8 km/h).

    Returns wind chill temperature in °C.
    """
    v_kmh = wind_speed_mps * 3.6
    if temperature_c > 10.0 or v_kmh < 4.8:
        return temperature_c
    return (
        13.12
        + 0.6215 * temperature_c
        - 11.37 * (v_kmh ** 0.16)
        + 0.3965 * temperature_c * (v_kmh ** 0.16)
    )


# Phase 63a: unit signature lookup for FOW detection
def _get_unit_signature(ctx: Any, unit: Any) -> Any:
    """Retrieve signature profile for a unit, or None if unavailable."""
    _sl = getattr(ctx, "sig_loader", None)
    if _sl is None:
        return None
    try:
        return _sl.get_profile(getattr(unit, "unit_type", ""))
    except (KeyError, AttributeError, Exception):
        return None


# Phase 52b: ITU-R P.838 rain attenuation for radar sensors
def _compute_rain_detection_factor(precip_rate_mmhr: float, range_km: float) -> float:
    """Return detection range multiplier due to rain [0.1–1.0].

    Uses ITU-R P.838 power law for X-band (~10 GHz): k~0.01, alpha~1.28.
    Radar range equation R^4: factor = 10^(-atten_dB / 40).
    """
    if precip_rate_mmhr <= 0 or range_km <= 0:
        return 1.0
    specific_atten = 0.01 * (precip_rate_mmhr ** 1.28)
    total_atten_db = specific_atten * range_km
    return max(0.1, 10.0 ** (-total_atten_db / 40.0))


# Phase 48a: configurable naval engagement defaults
class NavalEngagementConfig(BaseModel):
    """Default Pk / dimensions for naval engagement routing."""

    default_torpedo_pk: float = 0.4
    default_missile_pk: float = 0.7
    default_pd_count: int = 2
    default_pd_pk: float = 0.3
    default_target_length_m: float = 150.0
    default_target_beam_m: float = 20.0


# Phase 43a: melee range threshold (metres)
_MELEE_RANGE_M = 10.0

# Phase 50a: posture → movement speed multiplier
_POSTURE_SPEED_MULT: dict[int, float] = {
    0: 1.0,  # MOVING
    1: 1.0,  # HALTED
    2: 0.5,  # DEFENSIVE
    3: 0.0,  # DUG_IN
    4: 0.0,  # FORTIFIED
}

# Phase 51b: naval posture → movement speed multiplier
_NAVAL_POSTURE_SPEED_MULT: dict[int, float] = {
    0: 0.0,   # ANCHORED
    1: 1.0,   # UNDERWAY
    2: 1.2,   # TRANSIT
    3: 0.9,   # BATTLE_STATIONS
}

# Phase 56e: naval posture → target detection range multiplier
_NAVAL_POSTURE_DETECT_MULT: dict[int, float] = {
    0: 1.2,   # ANCHORED — easier to detect (stationary, no wake)
    1: 1.0,   # UNDERWAY — baseline
    2: 0.85,  # TRANSIT — reduced signature at speed
    3: 1.3,   # BATTLE_STATIONS — active radar/emissions increase signature
}

# Phase 43b: weapon categories that route to indirect fire
_INDIRECT_FIRE_CATEGORIES = frozenset({"HOWITZER", "MORTAR", "ARTILLERY"})


# ---------------------------------------------------------------------------
# Phase 64 helper — unit position lookup
# ---------------------------------------------------------------------------


def _get_unit_position(ctx: Any, unit_id: str) -> Position:
    """Return the position of a unit, or a default origin position."""
    for units in ctx.units_by_side.values():
        for u in units:
            if u.entity_id == unit_id and u.position is not None:
                return u.position
    return Position(0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Phase 43 helpers — aggregate engagement routing
# ---------------------------------------------------------------------------


def _get_formation_firepower(ctx: Any, unit: Unit) -> float:
    """Get formation firepower fraction for Napoleonic units."""
    engine = getattr(ctx, "formation_napoleonic_engine", None)
    if engine is not None:
        try:
            return engine.get_firepower_fraction(unit.entity_id)
        except Exception:
            pass
    return 1.0  # Default: all muskets fire (LINE formation)


def _infer_melee_type(attacker: Unit, wpn_inst: Any) -> Any:
    """Infer MeleeType from unit/weapon characteristics."""
    from stochastic_warfare.combat.melee import MeleeType

    wpn_id = wpn_inst.definition.weapon_id.lower()
    if "cavalry" in wpn_id or "saber" in wpn_id or "lance" in wpn_id:
        return MeleeType.CAVALRY_CHARGE
    if "bayonet" in wpn_id:
        return MeleeType.BAYONET_CHARGE
    if "pike" in wpn_id or "spear" in wpn_id:
        return MeleeType.PIKE_PUSH
    if "sword" in wpn_id or "axe" in wpn_id or "gladius" in wpn_id:
        return MeleeType.SHIELD_WALL
    return MeleeType.BAYONET_CHARGE  # Default


def _infer_missile_type(wpn_inst: Any) -> Any:
    """Infer archery MissileType from weapon."""
    from stochastic_warfare.combat.archery import MissileType

    wpn_id = wpn_inst.definition.weapon_id.lower()
    if "longbow" in wpn_id:
        return MissileType.LONGBOW
    if "crossbow" in wpn_id:
        return MissileType.CROSSBOW
    if "composite" in wpn_id:
        return MissileType.COMPOSITE_BOW
    if "javelin" in wpn_id:
        return MissileType.JAVELIN
    if "sling" in wpn_id:
        return MissileType.SLING
    return MissileType.LONGBOW  # Default


def _apply_aggregate_casualties(
    casualties: int,
    target: Unit,
    pending_damage: list[tuple[Unit, UnitStatus]],
    destruction_threshold: float = 0.5,
    disable_threshold: float = 0.3,
    cumulative_tracker: dict[str, int] | None = None,
) -> None:
    """Convert aggregate casualty count to pending unit status changes.

    When *cumulative_tracker* is provided, casualties are accumulated across
    ticks and thresholds are evaluated against the running total.  This is
    essential for aggregate models (volley fire, archery) where a single
    volley rarely exceeds the threshold on its own.
    """
    if casualties <= 0:
        return
    total = max(1, len(target.personnel))
    if cumulative_tracker is not None:
        cumulative_tracker[target.entity_id] = (
            cumulative_tracker.get(target.entity_id, 0) + casualties
        )
        fraction = cumulative_tracker[target.entity_id] / total
    else:
        fraction = casualties / total
    if fraction >= destruction_threshold:
        pending_damage.append((target, UnitStatus.DESTROYED))
    elif fraction >= disable_threshold:
        pending_damage.append((target, UnitStatus.DISABLED))


def _apply_melee_result(
    mr: Any,
    attacker: Unit,
    defender: Unit,
    pending_damage: list[tuple[Unit, UnitStatus]],
    morale_states: dict[str, Any],
    destruction_threshold: float = 0.5,
    disable_threshold: float = 0.3,
) -> None:
    """Convert melee result to damage entries for both sides."""
    # Defender casualties
    if mr.defender_casualties > 0:
        def_total = max(1, len(defender.personnel))
        frac = mr.defender_casualties / def_total
        if frac >= destruction_threshold:
            pending_damage.append((defender, UnitStatus.DESTROYED))
        elif frac >= disable_threshold:
            pending_damage.append((defender, UnitStatus.DISABLED))
    # Attacker casualties
    if mr.attacker_casualties > 0:
        att_total = max(1, len(attacker.personnel))
        frac = mr.attacker_casualties / att_total
        if frac >= destruction_threshold:
            pending_damage.append((attacker, UnitStatus.DESTROYED))
        elif frac >= disable_threshold:
            pending_damage.append((attacker, UnitStatus.DISABLED))
    # Morale effects — rout
    if mr.defender_routed:
        morale_states[defender.entity_id] = 3  # ROUTED
        object.__setattr__(defender, "status", UnitStatus.ROUTING)
    if mr.attacker_routed:
        morale_states[attacker.entity_id] = 3
        object.__setattr__(attacker, "status", UnitStatus.ROUTING)


def _route_naval_engagement(
    ctx: Any,
    attacker: Unit,
    target: Unit,
    wpn_inst: Any,
    best_range: float,
    dt: float,
    timestamp: Any,
    naval_config: NavalEngagementConfig | None = None,
    force_ratio_mod: float = 1.0,
    vls_launches: dict[str, int] | None = None,
) -> tuple[bool, UnitStatus | None]:
    """Route naval engagement to appropriate engine.

    Returns ``(handled, status)`` — *handled* is ``True`` when the weapon
    was processed by a naval engine (even on a miss), ``False`` when the
    weapon type is not naval-specific and should fall through.

    *force_ratio_mod* scales per-side Pk values (Dupuy CEV).
    """
    nc = naval_config or NavalEngagementConfig()
    wpn_cat_str = wpn_inst.definition.category.upper()

    # Torpedo
    if wpn_cat_str == "TORPEDO_TUBE":
        engine = getattr(ctx, "naval_subsurface_engine", None)
        if engine is not None:
            result = engine.torpedo_engagement(
                sub_id=attacker.entity_id,
                target_id=target.entity_id,
                torpedo_pk=min(1.0, nc.default_torpedo_pk * force_ratio_mod),
                range_m=best_range,
                timestamp=timestamp,
            )
            if result.hit:
                status = (
                    UnitStatus.DESTROYED
                    if result.damage_fraction >= 0.6
                    else UnitStatus.DISABLED
                )
                return True, status
            return True, None  # handled, miss

    # Phase 51a: depth charge routing
    if wpn_cat_str == "DEPTH_CHARGE":
        engine = getattr(ctx, "naval_subsurface_engine", None)
        if engine is not None:
            result = engine.depth_charge_attack(
                ship_id=attacker.entity_id,
                target_id=target.entity_id,
                num_charges=max(1, int(wpn_inst.definition.rate_of_fire_rpm)),
                target_depth_m=getattr(target, "depth", 100.0),
                target_range_m=best_range,
                timestamp=timestamp,
            )
            if result.hits > 0:
                status = (
                    UnitStatus.DESTROYED
                    if result.damage_fraction >= 0.6
                    else UnitStatus.DISABLED
                )
                return True, status
            return True, None  # handled, miss

    # Phase 51a: ASROC — missile launcher targeting submarine
    if wpn_cat_str == "MISSILE_LAUNCHER" and target.domain == Domain.SUBMARINE:
        subsurface = getattr(ctx, "naval_subsurface_engine", None)
        if subsurface is not None:
            result = subsurface.asroc_engagement(
                ship_id=attacker.entity_id,
                target_id=target.entity_id,
                range_m=best_range,
                target_depth_m=getattr(target, "depth", 100.0),
                timestamp=timestamp,
            )
            if result.torpedo_hit:
                status = (
                    UnitStatus.DESTROYED
                    if result.damage_fraction >= 0.6
                    else UnitStatus.DISABLED
                )
                return True, status
            return True, None  # handled, miss

    # Missile (ASHM) — surface-to-surface salvo
    if wpn_cat_str == "MISSILE_LAUNCHER":
        # Phase 51a: VLS ammo tracking
        _mc_raw = getattr(wpn_inst.definition, "magazine_capacity", 0)
        try:
            mag_cap = int(_mc_raw) if _mc_raw else 0
        except (TypeError, ValueError):
            mag_cap = 0
        if mag_cap > 0:
            uid = attacker.entity_id
            launched = vls_launches.get(uid, 0) if vls_launches is not None else 0
            if launched >= mag_cap:
                logger.info("VLS exhausted: unit %s (%d/%d)", uid, launched, mag_cap)
                return True, None  # magazine exhausted
        engine = getattr(ctx, "naval_surface_engine", None)
        if engine is not None:
            missiles_fired = max(1, int(wpn_inst.definition.rate_of_fire_rpm))
            salvo = engine.salvo_exchange(
                attacker_missiles=missiles_fired,
                attacker_pk=min(1.0, nc.default_missile_pk * force_ratio_mod),
                defender_point_defense_count=nc.default_pd_count,
                defender_pd_pk=nc.default_pd_pk,
            )
            # Track VLS expenditure
            if mag_cap > 0 and vls_launches is not None:
                uid = attacker.entity_id
                vls_launches[uid] = vls_launches.get(uid, 0) + missiles_fired
            if salvo.hits > 0:
                status = (
                    UnitStatus.DESTROYED if salvo.hits >= 2
                    else UnitStatus.DISABLED
                )
                return True, status
            return True, None  # handled, all intercepted

    # Naval gun
    if wpn_cat_str == "NAVAL_GUN":
        gunnery = getattr(ctx, "naval_gunnery_engine", None)
        if gunnery is not None:
            salvo = gunnery.fire_salvo(
                firer_id=attacker.entity_id,
                target_id=target.entity_id,
                range_m=best_range,
                target_length_m=nc.default_target_length_m,
                target_beam_m=nc.default_target_beam_m,
                num_guns=max(1, int(wpn_inst.definition.rate_of_fire_rpm)),
            )
            if salvo.get("hits", 0) > 0:
                return True, UnitStatus.DISABLED
            return True, None
        # Fallback: modern naval gun engagement
        ns_engine = getattr(ctx, "naval_surface_engine", None)
        if ns_engine is not None:
            gun_result = ns_engine.naval_gun_engagement(
                ship_id=attacker.entity_id,
                target_id=target.entity_id,
                range_m=best_range,
                rounds_fired=max(
                    1, int(wpn_inst.definition.rate_of_fire_rpm * dt / 60),
                ),
                timestamp=timestamp,
            )
            if gun_result.hits > 0:
                return True, UnitStatus.DISABLED
            return True, None

    # Shore bombardment: naval gun vs ground target (attacker must be naval)
    if (wpn_cat_str in ("NAVAL_GUN", "CANNON")
            and target.domain == Domain.GROUND
            and attacker.domain in (Domain.NAVAL, Domain.SUBMARINE)):
        ngse = getattr(ctx, "naval_gunfire_support_engine", None)
        if ngse is not None:
            bom_result = ngse.shore_bombardment(
                ship_id=attacker.entity_id,
                ship_pos=attacker.position,
                target_pos=target.position,
                round_count=max(
                    1, int(wpn_inst.definition.rate_of_fire_rpm * dt / 60),
                ),
                timestamp=timestamp,
            )
            if bom_result.hits_in_lethal_radius > 0:
                return True, UnitStatus.DISABLED
            return True, None

    return False, None  # Not a naval-specific weapon, fall through


def _route_air_engagement(
    ctx: Any,
    attacker: Unit,
    target: Unit,
    wpn_inst: Any,
    best_range: float,
    dt: float,
    timestamp: Any,
    force_ratio_mod: float = 1.0,
) -> tuple[bool, UnitStatus | None]:
    """Route air-domain engagement to the appropriate engine.

    Returns ``(handled, status)`` — same pattern as naval routing.

    Priority:
    - Both AERIAL → air_combat_engine (BVR/WVR)
    - Attacker AERIAL, target GROUND/NAVAL → air_ground_engine (CAS)
    - Target AERIAL, attacker non-AERIAL → air_defense_engine (SAM/AAA)
    """
    atk_air = attacker.domain == Domain.AERIAL
    tgt_air = target.domain == Domain.AERIAL
    wpn_cat = getattr(wpn_inst.definition, "category", "").upper()

    # Phase 62d: air combat environmental coupling
    cal_flat = _resolve_cal_flat(ctx)
    _ace = cal_flat.get("enable_air_combat_environment", False)

    # Phase 64c: ATO sortie gate — check available sorties before air engagement
    _ato_64 = getattr(ctx, "ato_engine", None)
    if _ato_64 is not None and cal_flat.get("enable_c2_friction", False):
        _sim_time = ctx.clock.elapsed.total_seconds() if hasattr(ctx.clock, "elapsed") else 0.0
        if _ato_64.get_available_sorties(_sim_time) <= 0:
            logger.debug("ATO: no sorties available, air engagement skipped")
            return (True, None)

    # Air-to-air: route missile engagements through air combat engine
    if atk_air and tgt_air and wpn_cat == "MISSILE_LAUNCHER":
        engine = getattr(ctx, "air_combat_engine", None)
        if engine is None:
            return False, None
        missile_pk = min(1.0, 0.5 * force_ratio_mod)
        pilot_skill = getattr(attacker, "training_level", 0.5)

        # Phase 62d: environmental modifiers for A2A
        _atk_energy = None
        _def_energy = None
        if _ace:
            # Icing penalty
            _cond = getattr(ctx, "conditions_engine", None)
            if _cond is not None:
                try:
                    _air_c = _cond.air()
                    _icing = getattr(_air_c, "icing_risk", 0.0)
                    if _icing > 0.5:
                        missile_pk *= (1.0 - cal_flat.get("icing_maneuver_penalty", 0.15))
                except Exception:
                    pass

            # Density altitude → reduced thrust
            _wx_aa = getattr(ctx, "weather_engine", None)
            if _wx_aa is not None:
                try:
                    _alt_aa = getattr(attacker.position, "altitude", 0.0)
                    _rho = _wx_aa.atmospheric_density(_alt_aa)
                    _density_factor = min(1.0, _rho / 1.225)
                    missile_pk *= _density_factor
                except Exception:
                    pass

            # Wind → BVR range modification
            if _wx_aa is not None:
                try:
                    _w_cur = _wx_aa.current.wind
                    _w_spd = _w_cur.speed
                    _w_dir = _w_cur.direction
                    # Wind component along attacker→target axis
                    _dx = target.position.easting - attacker.position.easting
                    _dy = target.position.northing - attacker.position.northing
                    _hdg = math.atan2(_dx, _dy)
                    _wind_along = _w_spd * math.cos(_w_dir - _hdg)
                    # Tailwind extends range, headwind reduces
                    _range_mod = 1.0 + _wind_along / cal_flat.get("wind_bvr_missile_speed_mps", 1000.0)
                    best_range /= max(0.5, _range_mod)
                except Exception:
                    pass

            # Altitude energy advantage
            from stochastic_warfare.combat.air_combat import EnergyState
            _atk_alt = getattr(attacker.position, "altitude", 0.0)
            _atk_spd = getattr(attacker, "speed", 250.0)
            _def_alt = getattr(target.position, "altitude", 0.0)
            _def_spd = getattr(target, "speed", 250.0)
            _atk_energy = EnergyState(altitude_m=_atk_alt, speed_mps=_atk_spd)
            _def_energy = EnergyState(altitude_m=_def_alt, speed_mps=_def_spd)

        result = engine.resolve_air_engagement(
            attacker_id=attacker.entity_id,
            defender_id=target.entity_id,
            attacker_pos=attacker.position,
            defender_pos=target.position,
            missile_pk=missile_pk,
            pilot_skill=pilot_skill,
            timestamp=timestamp,
            attacker_energy=_atk_energy,
            defender_energy=_def_energy,
        )
        if result.hit:
            return True, UnitStatus.DESTROYED
        return True, None

    # Air-to-ground (CAS): route bombs and missiles through air-ground engine
    if atk_air and not tgt_air and wpn_cat in (
        "BOMB", "GUIDED_BOMB", "MISSILE_LAUNCHER",
    ):
        # Phase 62d: cloud ceiling gate — unguided weapons need visual delivery
        if _ace:
            _wx_cas = getattr(ctx, "weather_engine", None)
            if _wx_cas is not None:
                try:
                    _ceiling = getattr(_wx_cas.current, "cloud_ceiling", 10000.0)
                    _guidance = getattr(
                        getattr(wpn_inst, "definition", None), "guidance_type",
                        getattr(
                            # check ammo guidance if weapon has no guidance_type
                            getattr(wpn_inst, "current_ammo", None), "guidance_type",
                            "none",
                        ),
                    )
                    _pgm_types = ("gps", "laser", "radar", "combined", "gps_ins", "semi_active", "active")
                    _is_pgm = str(_guidance).lower() in _pgm_types
                    if _ceiling < cal_flat.get("cloud_ceiling_min_attack_m", 500.0) and not _is_pgm:
                        logger.debug(
                            "CAS aborted: cloud ceiling %.0fm < %.0fm (unguided)",
                            _ceiling, cal_flat.get("cloud_ceiling_min_attack_m", 500.0),
                        )
                        return True, None  # mission aborted
                except Exception:
                    pass

        engine = getattr(ctx, "air_ground_engine", None)
        if engine is None:
            return False, None
        weapon_pk = min(1.0, 0.4 * force_ratio_mod)

        # Phase 62d: icing + density penalties on CAS Pk
        if _ace:
            _cond_cas = getattr(ctx, "conditions_engine", None)
            if _cond_cas is not None:
                try:
                    _air_cas = _cond_cas.air()
                    _icing_cas = getattr(_air_cas, "icing_risk", 0.0)
                    if _icing_cas > 0.5:
                        weapon_pk *= (1.0 - cal_flat.get("icing_power_penalty", 0.10))
                except Exception:
                    pass
            _wx_cas2 = getattr(ctx, "weather_engine", None)
            if _wx_cas2 is not None:
                try:
                    _alt_cas = getattr(attacker.position, "altitude", 0.0)
                    _rho_cas = _wx_cas2.atmospheric_density(_alt_cas)
                    weapon_pk *= min(1.0, _rho_cas / 1.225)
                except Exception:
                    pass

        result = engine.execute_cas(
            aircraft_id=attacker.entity_id,
            target_id=target.entity_id,
            aircraft_pos=attacker.position,
            target_pos=target.position,
            weapon_pk=weapon_pk,
            timestamp=timestamp,
        )
        if result.aborted:
            return True, None
        if result.hit:
            return True, UnitStatus.DISABLED
        return True, None

    # Ground/Naval-to-air (air defense): route SAM/missile weapons
    if tgt_air and not atk_air and wpn_cat in (
        "MISSILE_LAUNCHER", "SAM",
    ):
        engine = getattr(ctx, "air_defense_engine", None)
        if engine is None:
            return False, None
        interceptor_pk = min(1.0, 0.4 * force_ratio_mod)
        result = engine.fire_interceptor(
            ad_id=attacker.entity_id,
            target_id=target.entity_id,
            interceptor_pk=interceptor_pk,
            range_m=best_range,
            timestamp=timestamp,
        )
        if result.hit:
            return True, UnitStatus.DESTROYED
        return True, None

    return False, None  # Non-air weapon category, fall through to direct fire


def _apply_indirect_fire_result(
    fm_result: Any,
    target: Unit,
    pending_damage: list[tuple[Unit, UnitStatus]],
    destruction_threshold: float = 0.5,
    disable_threshold: float = 0.3,
    cumulative_tracker: dict[str, int] | None = None,
    terrain_modifier: float = 1.0,
    lethal_radius_m: float = 50.0,
    casualty_per_hit: float = 0.15,
) -> None:
    """Convert indirect fire impacts to damage.

    ``terrain_modifier`` scales the per-hit damage fraction — cover reduces
    effective indirect-fire lethality.
    ``lethal_radius_m`` overrides the default 50 m lethal radius — pass
    ``ammo_def.blast_radius_m`` when available.
    ``casualty_per_hit`` overrides the default 0.15 casualty fraction per
    impact within the lethal radius.
    """
    hits_near = 0
    for impact in fm_result.impacts:
        dx = impact.position.easting - target.position.easting
        dy = impact.position.northing - target.position.northing
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < lethal_radius_m:
            hits_near += 1
    if hits_near > 0:
        per_hit = casualty_per_hit * terrain_modifier
        if cumulative_tracker is not None:
            cumulative_tracker[target.entity_id] = (
                cumulative_tracker.get(target.entity_id, 0) + hits_near
            )
            fraction = min(1.0, cumulative_tracker[target.entity_id] * per_hit)
        else:
            fraction = min(1.0, hits_near * per_hit)
        if fraction >= destruction_threshold:
            pending_damage.append((target, UnitStatus.DESTROYED))
        elif fraction >= disable_threshold:
            pending_damage.append((target, UnitStatus.DISABLED))


# ---------------------------------------------------------------------------
# Aggregate-path suppression helper (Phase 47)
# ---------------------------------------------------------------------------


def _apply_aggregate_suppression(
    ctx: Any,
    target: Unit,
    wpn_inst: Any,
    range_m: float,
    dt: float,
    suppression_states: dict[str, Any],
) -> None:
    """Apply suppression from aggregate fire (volley, archery, indirect).

    Mirrors the suppression wiring in the direct-fire path so that older-era
    engagements also generate suppression effects on the target.
    """
    sup_eng = getattr(ctx, "suppression_engine", None)
    if sup_eng is None:
        return
    tid = target.entity_id
    if tid not in suppression_states:
        suppression_states[tid] = UnitSuppressionState()
    sup_eng.apply_fire_volume(
        state=suppression_states[tid],
        rounds_per_minute=wpn_inst.definition.rate_of_fire_rpm,
        caliber_mm=wpn_inst.definition.caliber_mm,
        range_m=range_m,
        duration_s=dt,
    )


# ---------------------------------------------------------------------------
# Target scoring (Phase 41c)
# ---------------------------------------------------------------------------


def _target_value(
    target: Unit,
    *,
    hq: float = 2.0,
    ad: float = 1.8,
    artillery: float = 1.5,
    armor: float = 1.3,
    default: float = 1.0,
) -> float:
    """Target type priority for threat-based selection."""
    # HQ is highest value
    st = getattr(target, "support_type", None)
    if st is not None:
        st_name = st.name if hasattr(st, "name") else str(st)
        if st_name == "HQ":
            return hq
    # Air defense enables air ops
    if hasattr(target, "ad_type"):
        return ad
    # Artillery/rocket and armor
    gt = getattr(target, "ground_type", None)
    if gt is not None:
        gt_name = gt.name if hasattr(gt, "name") else str(gt)
        if "ARTILLERY" in gt_name or "ROCKET" in gt_name:
            return artillery
        if gt_name == "ARMOR":
            return armor
    return default


# ---------------------------------------------------------------------------
# Movement helpers
# ---------------------------------------------------------------------------


def _should_hold_position(unit: Unit) -> bool:
    """Return True if the unit should not advance toward enemies.

    Emplaced systems (SAMs, deployed artillery) fight from their
    position rather than maneuvering toward the enemy.
    """
    # Air defense units are always emplaced
    try:
        from stochastic_warfare.entities.unit_classes.air_defense import AirDefenseUnit
        if isinstance(unit, AirDefenseUnit):
            return True
    except ImportError:
        pass
    return False


def _movement_target(
    unit_pos: Position,
    enemies: list[Unit],
    centroid_weight: float = 0.5,
    enemy_pos_arr: np.ndarray | None = None,
) -> tuple[float, float]:
    """Compute a blended movement target from centroid and nearest enemy.

    Returns a point that is a weighted average of the enemy centroid
    (general advance toward the line) and the nearest enemy (local
    threat response).  This produces natural "lines closing" behavior
    rather than all units collapsing onto a single point.

    Phase 70a: vectorized path when *enemy_pos_arr* (shape (m,2)) is provided.
    """
    if enemy_pos_arr is not None and enemy_pos_arr.shape[0] > 0:
        centroid = np.mean(enemy_pos_arr, axis=0)
        upos = np.array([unit_pos.easting, unit_pos.northing])
        diffs = enemy_pos_arr - upos
        nearest = enemy_pos_arr[int(np.argmin(np.sum(diffs * diffs, axis=1)))]
        w = centroid_weight
        return (
            float(centroid[0] * w + nearest[0] * (1 - w)),
            float(centroid[1] * w + nearest[1] * (1 - w)),
        )

    # Scalar fallback
    cx = sum(e.position.easting for e in enemies) / len(enemies)
    cy = sum(e.position.northing for e in enemies) / len(enemies)

    best_dist_sq = float("inf")
    nx, ny = cx, cy
    ux, uy = unit_pos.easting, unit_pos.northing
    for e in enemies:
        dx = e.position.easting - ux
        dy = e.position.northing - uy
        d2 = dx * dx + dy * dy
        if d2 < best_dist_sq:
            best_dist_sq = d2
            nx, ny = e.position.easting, e.position.northing

    w = centroid_weight
    return cx * w + nx * (1 - w), cy * w + ny * (1 - w)


def _nearest_enemy_dist(
    unit_pos: Position,
    enemies: list[Unit],
    enemy_pos_arr: np.ndarray | None = None,
) -> float:
    """Return distance to the closest enemy.

    Phase 70a: vectorized path when *enemy_pos_arr* (shape (m,2)) is provided.
    """
    if enemy_pos_arr is not None and enemy_pos_arr.shape[0] > 0:
        upos = np.array([unit_pos.easting, unit_pos.northing])
        diffs = enemy_pos_arr - upos
        return float(np.sqrt(np.min(np.sum(diffs * diffs, axis=1))))

    best = float("inf")
    ux, uy = unit_pos.easting, unit_pos.northing
    for e in enemies:
        dx = e.position.easting - ux
        dy = e.position.northing - uy
        d = math.sqrt(dx * dx + dy * dy)
        if d < best:
            best = d
    return best


def _standoff_range(unit: Unit, ctx: Any) -> float:
    """Return the range at which this unit should stop advancing.

    Uses 80% of the best *usable* weapon's max range so the unit parks
    comfortably within engagement distance.  Weapons with no ammo remaining
    are ignored — a unit that has expended all ranged ammo will close to
    melee range.  Units without weapons (or with only melee) close fully.
    """
    weapons = getattr(ctx, "unit_weapons", {}).get(unit.entity_id, [])
    best_range = 0.0
    for wpn_inst, ammo_defs in weapons:
        r = wpn_inst.definition.max_range_m
        if r <= 10:
            continue  # melee / point-blank — no standoff
        # Check that the weapon still has ammo
        has_ammo = False
        for ad in ammo_defs:
            if wpn_inst.can_fire(ad.ammo_id):
                has_ammo = True
                break
        if has_ammo and r > best_range:
            best_range = r
    return best_range * 0.8 if best_range > 10 else 0.0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class BattleConfig(BaseModel):
    """Tuning parameters for the battle manager."""

    engagement_range_m: float = 10000.0
    morale_check_interval: int = 12
    destruction_threshold: float = 0.5
    disable_threshold: float = 0.3
    default_visibility_m: float = 10000.0
    max_ticks_per_battle: int = 50000
    # Phase 13a-6: Auto-resolve
    auto_resolve_enabled: bool = False
    auto_resolve_max_units: int = 0  # battles with <= this many total units get auto-resolved
    # Phase 48b: configurable elevation caps
    elevation_advantage_cap: float = 0.3
    elevation_disadvantage_floor: float = -0.1
    # Phase 48b: configurable target value weights
    target_value_hq: float = 2.0
    target_value_ad: float = 1.8
    target_value_artillery: float = 1.5
    target_value_armor: float = 1.3
    target_value_default: float = 1.0
    # Phase 48a: naval engagement defaults
    naval_config: NavalEngagementConfig = NavalEngagementConfig()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BattleContext:
    """Tracks state for one active battle."""

    battle_id: str
    start_tick: int
    start_time: datetime
    involved_sides: list[str]
    active: bool = True
    ticks_executed: int = 0
    # Track which units are involved in this battle
    unit_ids: set[str] = field(default_factory=set)
    # Wave attack assignments: entity_id → wave number (0=immediate, N=delayed, -1=reserve)
    wave_assignments: dict[str, int] = field(default_factory=dict)
    # Elapsed battle time in seconds (incremented each tactical tick)
    battle_elapsed_s: float = 0.0


@dataclass(frozen=True)
class BattleResult:
    """Outcome of a resolved battle."""

    battle_id: str
    duration_ticks: int
    terminated_by: str
    units_destroyed: dict[str, int] = field(default_factory=dict)
    units_routing: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AutoResolveResult:
    """Outcome of an auto-resolved battle."""

    battle_id: str
    winner: str
    side_losses: dict[str, float] = field(default_factory=dict)  # side -> loss fraction
    duration_s: float = 0.0


# ---------------------------------------------------------------------------
# Battle Manager
# ---------------------------------------------------------------------------


class BattleManager:
    """Manages tactical-level battle resolution.

    Orchestrates the full tactical loop per tick: detection → AI →
    orders → movement → engagement → morale → supply consumption.

    Parameters
    ----------
    event_bus : EventBus
        For publishing battle events.
    config : BattleConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: BattleConfig | None = None,
    ) -> None:
        self._bus = event_bus
        self._config = config or BattleConfig()
        self._battles: dict[str, BattleContext] = {}
        self._next_battle_id = 0
        # Transient assessment cache — not checkpointed
        self._cached_assessments: dict[str, Any] = {}  # unit_id -> SituationAssessment
        # Phase 40b: posture tracking (ticks unit has been stationary)
        self._ticks_stationary: dict[str, int] = {}
        # Phase 40e: per-unit suppression state
        self._suppression_states: dict[str, UnitSuppressionState] = {}
        # Phase 47: cumulative aggregate casualties per unit — volley/archery
        # models produce few casualties per tick, so we must accumulate across
        # volleys and assess thresholds on the running total.
        self._cumulative_casualties: dict[str, int] = {}
        # Phase 50a: units transitioning from DUG_IN/FORTIFIED to MOVING
        self._undigging: dict[str, bool] = {}
        # Phase 50c: persistent concealment scores per target
        self._concealment_scores: dict[str, float] = {}
        # Phase 51a: VLS magazine tracking (entity_id → missiles launched)
        self._vls_launches: dict[str, int] = {}
        # Phase 62a: fractional environmental casualty accumulator
        self._env_casualty_accum: dict[str, float] = {}
        # Phase 68b: general ammo expenditure tracking (unit_id:weapon_name → rounds fired)
        self._ammo_expended: dict[str, int] = {}
        # Phase 68c: pending order decisions (unit_id → execute_at_elapsed_s)
        self._pending_decisions: dict[str, float] = {}
        # Phase 68d: misinterpreted order info (unit_id → PropagationResult)
        self._misinterpreted_orders: dict[str, Any] = {}
        # Phase 70c: signature cache (unit_type → signature profile, immutable)
        self._signature_cache: dict[str, Any] = {}
        # Phase 85: LOD tier tracking
        self._lod_tiers: dict[str, int] = {}
        self._lod_pending_tiers: dict[str, int] = {}
        self._lod_pending_counts: dict[str, int] = {}
        self._lod_promoted: set[str] = set()

    # ── Engagement detection ────────────────────────────────────────

    def detect_engagement(
        self,
        units_by_side: dict[str, list[Unit]],
        engagement_range_m: float | None = None,
    ) -> list[BattleContext]:
        """Detect new engagements based on proximity between opposing forces.

        Returns newly created :class:`BattleContext` instances for each
        detected engagement (forces within engagement range).
        """
        eng_range = engagement_range_m or self._config.engagement_range_m
        sides = list(units_by_side.keys())
        new_battles: list[BattleContext] = []

        for i, side_a in enumerate(sides):
            for side_b in sides[i + 1:]:
                active_a = [u for u in units_by_side[side_a] if u.status == UnitStatus.ACTIVE]
                active_b = [u for u in units_by_side[side_b] if u.status == UnitStatus.ACTIVE]
                if not active_a or not active_b:
                    continue

                # Check if any pair is within engagement range
                min_dist = self._min_distance(active_a, active_b)
                if min_dist <= eng_range:
                    # Check if these sides already have an active battle
                    pair = frozenset({side_a, side_b})
                    already_active = any(
                        frozenset(b.involved_sides) == pair and b.active
                        for b in self._battles.values()
                    )
                    if not already_active:
                        battle = BattleContext(
                            battle_id=f"battle_{self._next_battle_id:04d}",
                            start_tick=0,
                            start_time=datetime.now(),
                            involved_sides=[side_a, side_b],
                            unit_ids={u.entity_id for u in active_a + active_b},
                        )
                        self._next_battle_id += 1
                        self._battles[battle.battle_id] = battle
                        new_battles.append(battle)
                        logger.info(
                            "New battle detected: %s (%s vs %s), min distance %.0fm",
                            battle.battle_id, side_a, side_b, min_dist,
                        )

        return new_battles

    # ── Tactical tick ───────────────────────────────────────────────

    def execute_tick(
        self,
        ctx: Any,  # SimulationContext
        battle: BattleContext,
        dt: float,
    ) -> None:
        """Execute one tactical tick for a battle.

        Sequences: detection → AI → orders → movement → engagement →
        morale → supply.  All domain logic delegated to engines in *ctx*.

        Parameters
        ----------
        ctx:
            SimulationContext with all engines and state.
        battle:
            Active battle to advance.
        dt:
            Tick duration in seconds.
        """
        if not battle.active:
            return

        battle.ticks_executed += 1
        battle.battle_elapsed_s += dt
        units_by_side = ctx.units_by_side
        cal_flat = _resolve_cal_flat(ctx)
        timestamp = ctx.clock.current_time

        # 1. Pre-build per-side active enemy lists and position arrays
        active_enemies, enemy_pos_arrays = self._build_enemy_data(units_by_side)

        # 1a. Phase 70b: entity_id → Unit index for O(1) lookups
        _unit_index: dict[str, Unit] = {}
        for _side_units_idx in units_by_side.values():
            for _u_idx in _side_units_idx:
                _unit_index[_u_idx.entity_id] = _u_idx

        # 1c. Phase 85: LOD tier classification
        _lod_full_update = self._classify_lod_tiers(
            ctx, units_by_side, enemy_pos_arrays, battle,
        )

        # 1b. Phase 53a: Fog of war — per-side detection picture
        _enable_fow = cal_flat.get("enable_fog_of_war", False)
        _enable_det_culling = cal_flat.get("enable_detection_culling", True)
        _enable_scan_sched = cal_flat.get("enable_scan_scheduling", False)
        if _enable_fow and getattr(ctx, "fog_of_war", None) is not None:
            _fow_time = getattr(timestamp, "timestamp", lambda: 0.0)()
            for _fow_side, _fow_units in units_by_side.items():
                _own_data = []
                for _u in _fow_units:
                    if _u.status != UnitStatus.ACTIVE:
                        continue
                    if _u.entity_id not in _lod_full_update:
                        continue  # Phase 85: LOD skip (non-update tick)
                    _own_data.append({
                        "position": _u.position,
                        "sensors": ctx.unit_sensors.get(_u.entity_id, []),
                        "observer_height": 1.8,
                    })
                _enemy_data = []
                for _other_side, _other_units in units_by_side.items():
                    if _other_side == _fow_side:
                        continue
                    for _eu in _other_units:
                        if _eu.status != UnitStatus.ACTIVE:
                            continue
                        # Phase 70c: cached signature lookup
                        _eu_ut = getattr(_eu, "unit_type", "")
                        if _eu_ut not in self._signature_cache:
                            self._signature_cache[_eu_ut] = _get_unit_signature(ctx, _eu)
                        _enemy_data.append({
                            "unit_id": _eu.entity_id,
                            "position": _eu.position,
                            "signature": self._signature_cache[_eu_ut],
                            "unit": _eu,
                            "target_height": 0.0,
                        })
                try:
                    ctx.fog_of_war.update(
                        side=_fow_side,
                        own_units=_own_data,
                        enemy_units=_enemy_data,
                        dt=dt,
                        current_time=_fow_time,
                        detection_culling=_enable_det_culling,
                        scan_scheduling=_enable_scan_sched,
                        current_tick=battle.ticks_executed,
                    )
                except Exception:
                    logger.debug("FogOfWar update failed for %s", _fow_side, exc_info=True)

            # Phase 85: promote non-ACTIVE-tier units that detected contacts
            if cal_flat.get("enable_lod", False):
                for _fow_side, _fow_units in units_by_side.items():
                    try:
                        _wv = ctx.fog_of_war.get_world_view(_fow_side)
                        for _u in _fow_units:
                            _uid = _u.entity_id
                            if self._lod_tiers.get(_uid, 0) == UnitLodTier.ACTIVE:
                                continue
                            if _uid not in _lod_full_update:
                                continue  # didn't scan this tick
                            _max_wpn = max(
                                (w[0].definition.max_range_m
                                 for w in ctx.unit_weapons.get(_uid, [])),
                                default=0,
                            )
                            for _ct in _wv.contacts.values():
                                _cp = _ct.estimated_position
                                if _cp is not None:
                                    _dx = _u.position.easting - _cp.easting
                                    _dy = _u.position.northing - _cp.northing
                                    if math.sqrt(_dx * _dx + _dy * _dy) <= _max_wpn * 2:
                                        self._lod_promoted.add(_uid)
                                        break
                    except Exception:
                        pass

        # 2. AI OODA loop update → completions trigger assess/decide
        if ctx.ooda_engine is not None:
            completions = ctx.ooda_engine.update(dt, ts=timestamp)
            self._process_ooda_completions(ctx, completions, timestamp)

        # 3. Order execution update
        if ctx.order_execution is not None:
            ctx.order_execution.update(dt)

        # 3b. Apply behavior rules — set unit speeds from scenario YAML
        # (pre-scripted behavior for historical scenarios)
        behavior_rules = getattr(ctx.config, "behavior_rules", {})
        if behavior_rules:
            self._apply_behavior_rules(units_by_side, active_enemies, behavior_rules)

        # 3c. Decay suppression (Phase 40e)
        sup_engine = getattr(ctx, "suppression_engine", None)
        if sup_engine is not None:
            for state in self._suppression_states.values():
                sup_engine.update_suppression(state, dt)

        # 4. Movement — units with active movement orders
        # Record pre-movement positions for posture tracking (Phase 40b)
        pre_positions: dict[str, tuple[float, float]] = {}
        for side_units in units_by_side.values():
            for u in side_units:
                if u.status == UnitStatus.ACTIVE:
                    pre_positions[u.entity_id] = (u.position.easting, u.position.northing)

        self._execute_movement(
            ctx, units_by_side, active_enemies, dt, battle, behavior_rules,
            enemy_pos_arrays=enemy_pos_arrays,
        )

        # 4b. Update posture based on movement (Phase 40b)
        defensive_sides = set(cal_flat.get("defensive_sides", []))
        dig_in_ticks = cal_flat.get("dig_in_ticks", 30)
        for side_name, side_units in units_by_side.items():
            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                if not hasattr(u, "posture"):
                    continue
                uid = u.entity_id
                pre = pre_positions.get(uid)
                if pre is None:
                    continue
                cur = (u.position.easting, u.position.northing)
                moved = abs(cur[0] - pre[0]) > 0.01 or abs(cur[1] - pre[1]) > 0.01
                if moved:
                    self._ticks_stationary[uid] = 0
                    object.__setattr__(u, "posture", type(u.posture)(0))  # MOVING
                else:
                    self._ticks_stationary[uid] = self._ticks_stationary.get(uid, 0) + 1
                    ticks = self._ticks_stationary[uid]
                    if side_name in defensive_sides:
                        if ticks > dig_in_ticks:
                            object.__setattr__(u, "posture", type(u.posture)(3))  # DUG_IN
                        else:
                            object.__setattr__(u, "posture", type(u.posture)(2))  # DEFENSIVE
                    else:
                        object.__setattr__(u, "posture", type(u.posture)(1))  # HALTED

        # 4c. Phase 50b: auto-assign air posture based on flight state / fuel
        for side_units in units_by_side.values():
            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                ap = getattr(u, "air_posture", None)
                if ap is None:
                    continue
                from stochastic_warfare.entities.unit_classes.aerial import AirPosture
                fs = getattr(u, "flight_state", None)
                fuel = getattr(u, "fuel_remaining", 1.0)
                if fs is not None and int(fs) == 0:  # FlightState.GROUNDED
                    u.air_posture = AirPosture.GROUNDED
                elif fuel < 0.2:
                    u.air_posture = AirPosture.RETURNING
                elif int(ap) == 0:  # Was GROUNDED posture but operational
                    u.air_posture = AirPosture.ON_STATION

        # 4d. Phase 51b: auto-assign naval posture based on enemy proximity
        # Only for modern/ww2 eras — ancient/napoleonic oar-powered ships
        # don't have the modern battle stations speed concept.
        _era = getattr(ctx.config, "era", "modern")
        if _era in ("modern", "ww2", "ww1"):
            for side_name, side_units in units_by_side.items():
                enemies = active_enemies.get(side_name, [])
                for u in side_units:
                    if u.status != UnitStatus.ACTIVE:
                        continue
                    np_attr = getattr(u, "naval_posture", None)
                    if np_attr is None:
                        continue
                    from stochastic_warfare.entities.unit_classes.naval import NavalPosture
                    if not enemies:
                        if int(np_attr) == 3:  # BATTLE_STATIONS → UNDERWAY
                            object.__setattr__(u, "naval_posture", NavalPosture.UNDERWAY)
                        continue
                    min_dist = _nearest_enemy_dist(
                        u.position, enemies,
                        enemy_pos_arr=enemy_pos_arrays.get(side_name),
                    )
                    if min_dist < self._config.engagement_range_m * 2:
                        object.__setattr__(u, "naval_posture", NavalPosture.BATTLE_STATIONS)
                    elif int(np_attr) == 3:  # No longer in threat range
                        object.__setattr__(u, "naval_posture", NavalPosture.UNDERWAY)

        # 4e. Phase 51d: mine warfare — check moving naval units against minefields
        mine_engine = getattr(ctx, "mine_warfare_engine", None)
        pending_mine_damage: list[tuple[Unit, UnitStatus]] = []
        if mine_engine is not None and mine_engine._mines:
            dest_thresh_m = cal_flat.get(
                "destruction_threshold", self._config.destruction_threshold,
            )
            dis_thresh_m = cal_flat.get(
                "disable_threshold", self._config.disable_threshold,
            )
            for side_units in units_by_side.values():
                for u in side_units:
                    if u.status != UnitStatus.ACTIVE:
                        continue
                    if u.domain not in (Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS):
                        continue
                    if u.speed < 0.1:
                        continue  # stationary — no mine trigger
                    for mine in list(mine_engine._mines):
                        if not mine.armed or mine.detonated:
                            continue
                        dx = u.position.easting - mine.position.easting
                        dy = u.position.northing - mine.position.northing
                        dist_m = math.sqrt(dx * dx + dy * dy)
                        _trigger_radii = {0: 5, 1: 50, 2: 100, 3: 30, 4: 80, 5: 100, 6: 120}
                        trigger_radius = _trigger_radii.get(int(mine.mine_type), 50)
                        if dist_m <= trigger_radius:
                            mr = mine_engine.resolve_mine_encounter(
                                ship_id=u.entity_id, mine=mine,
                                ship_magnetic_sig=0.5, ship_acoustic_sig=0.5,
                                timestamp=timestamp,
                            )
                            if mr.detonated and mr.damage_fraction > 0:
                                if mr.damage_fraction >= dest_thresh_m:
                                    pending_mine_damage.append((u, UnitStatus.DESTROYED))
                                elif mr.damage_fraction >= dis_thresh_m:
                                    pending_mine_damage.append((u, UnitStatus.DISABLED))

        # 4f. Phase 66a: IED encounters during ground movement
        _uw_eng = getattr(ctx, "unconventional_engine", None)
        if (
            cal_flat.get("enable_unconventional_warfare", False)
            and _uw_eng is not None
            and _uw_eng._ieds
        ):
            for _ied_id, _ied_data in list(_uw_eng._ieds.items()):
                if not _ied_data["active"]:
                    continue
                _ied_pos = _ied_data["position"]
                for side_units_ied in units_by_side.values():
                    for _u_ied in side_units_ied:
                        if _u_ied.status != UnitStatus.ACTIVE:
                            continue
                        if getattr(_u_ied, "domain", None) in (
                            Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS,
                        ):
                            continue  # naval mines handled above
                        # Only units that moved this tick
                        _pre_ied = pre_positions.get(_u_ied.entity_id)
                        if _pre_ied is None:
                            continue
                        _cur_ied = (_u_ied.position.easting, _u_ied.position.northing)
                        if abs(_cur_ied[0] - _pre_ied[0]) < 0.01 and abs(_cur_ied[1] - _pre_ied[1]) < 0.01:
                            continue  # didn't move
                        _dx_ied = _u_ied.position.easting - _ied_pos.easting
                        _dy_ied = _u_ied.position.northing - _ied_pos.northing
                        _dist_ied = math.sqrt(_dx_ied * _dx_ied + _dy_ied * _dy_ied)
                        if _dist_ied > _ied_data["blast_radius_m"] * 2:
                            continue
                        # Check EW jamming for remote IEDs
                        if _ied_data["subtype"] == "remote":
                            _ew_eng_ied = getattr(ctx, "ew_engine", None)
                            _jammed = _uw_eng.check_ew_jamming(
                                _ied_id, _ew_eng_ied is not None, 0.5,
                            )
                            if _jammed:
                                continue
                        # Detection roll — speed-based
                        _speed_ied = getattr(_u_ied, "current_speed_mps", getattr(_u_ied, "speed", 5.0))
                        _has_eng = "engineer" in getattr(_u_ied, "unit_type", "").lower()
                        if _uw_eng.check_ied_detection(_speed_ied, _has_eng, _u_ied.entity_id):
                            continue
                        # Detonation
                        _result_ied = _uw_eng.detonate_ied(_ied_id, _u_ied.entity_id, timestamp=timestamp)
                        logger.info(
                            "IED %s detonated on %s (blast=%.1fm)",
                            _ied_id, _u_ied.entity_id, _result_ied.blast_radius_m,
                        )
                        break  # one IED per tick per location

        # 4g. Phase 62a: Heat/cold environmental casualties
        if cal_flat.get("enable_human_factors", False):
            _wx62 = getattr(ctx, "weather_engine", None)
            if _wx62 is not None:
                try:
                    _cur62 = _wx62.current
                    _temp62 = _cur62.temperature
                    _humid62 = getattr(_cur62, "humidity", 0.5)
                    _wind62 = getattr(_cur62.wind, "speed", 0.0)
                    _wbgt = _compute_wbgt(_temp62, _humid62)
                    _wc = _compute_wind_chill(_temp62, _wind62)

                    for _su62 in units_by_side.values():
                        for _u62 in _su62:
                            if _u62.status != UnitStatus.ACTIVE:
                                continue
                            _uid62 = _u62.entity_id
                            _env_rate = 0.0

                            # Heat stress
                            if _wbgt > 28.0:
                                _hr = cal_flat.get("heat_casualty_base_rate", 0.02) * (_wbgt - 28.0) / 10.0
                                # MOPP multiplier: gear traps heat
                                _cbrn62 = getattr(ctx, "cbrn_engine", None)
                                _mopp62 = 0
                                if _cbrn62 is not None:
                                    _mopp62 = getattr(_cbrn62, "_mopp_levels", {}).get(_uid62, 0)
                                _hr *= 1.0 + _mopp62 * 0.5
                                # Exertion: moving units generate more heat
                                _pre62 = pre_positions.get(_uid62)
                                if _pre62 is not None:
                                    _cur_pos62 = (_u62.position.easting, _u62.position.northing)
                                    if abs(_cur_pos62[0] - _pre62[0]) > 0.01 or abs(_cur_pos62[1] - _pre62[1]) > 0.01:
                                        _hr *= 1.5
                                _env_rate += _hr

                            # Cold injury
                            if _wc < -20.0:
                                _cr = cal_flat.get("cold_casualty_base_rate", 0.015) * (abs(_wc) - 20.0) / 20.0
                                _env_rate += _cr

                            if _env_rate > 0:
                                _frac = _env_rate * (dt / 3600.0)
                                self._env_casualty_accum[_uid62] = (
                                    self._env_casualty_accum.get(_uid62, 0.0) + _frac
                                )
                                if self._env_casualty_accum[_uid62] >= 1.0:
                                    _cas = int(self._env_casualty_accum[_uid62])
                                    self._env_casualty_accum[_uid62] -= _cas
                                    _pers = _u62.personnel
                                    if _pers and len(_pers) > _cas:
                                        object.__setattr__(
                                            _u62, "personnel", _pers[:-_cas],
                                        )
                                        logger.debug(
                                            "Env casualty: %s lost %d personnel (heat/cold)",
                                            _uid62, _cas,
                                        )
                except Exception:
                    logger.debug("Phase 62a env casualty failed", exc_info=True)

        # 4g2. Phase 78c: environmental fatigue acceleration (heat/cold)
        if cal_flat.get("enable_environmental_fatigue", False):
            _fatigue_mgr_78 = getattr(ctx, "fatigue_manager", None)
            if _fatigue_mgr_78 is not None:
                _wx78 = getattr(ctx, "weather_engine", None)
                if _wx78 is not None:
                    try:
                        _cur78 = _wx78.current
                        _temp78 = _cur78.temperature
                        _humid78 = getattr(_cur78, "humidity", 0.5)
                        _wind78 = getattr(_cur78.wind, "speed", 0.0)
                        _wbgt78 = _compute_wbgt(_temp78, _humid78)
                        _wc78 = _compute_wind_chill(_temp78, _wind78)

                        _temp_stress78 = 0.0
                        if _wbgt78 > 28.0:
                            _temp_stress78 = (_wbgt78 - 28.0) / 10.0
                        elif _wc78 < -20.0:
                            _temp_stress78 = (-20.0 - _wc78) / 20.0

                        if _temp_stress78 > 0:
                            for _su_fat78 in units_by_side.values():
                                for _u_fat78 in _su_fat78:
                                    if _u_fat78.status == UnitStatus.ACTIVE:
                                        _fatigue_mgr_78.accumulate(
                                            _u_fat78.entity_id,
                                            dt / 3600.0,
                                            "march",
                                            temperature_stress=_temp_stress78,
                                        )
                    except Exception:
                        logger.debug("Phase 78c env fatigue failed", exc_info=True)

        # 4h. Phase 71b: missile flight resolution — advance in-flight missiles
        _missile_eng_71 = getattr(ctx, "missile_engine", None)
        _enable_missile_routing_71 = cal_flat.get("enable_missile_routing", False)
        _pending_missile_damage: list[tuple[Unit, UnitStatus]] = []
        if _missile_eng_71 is not None and _enable_missile_routing_71:
            _gps_acc_71 = 5.0
            _space_eng_71 = getattr(ctx, "space_engine", None)
            if _space_eng_71 is not None:
                _gps_acc_71 = getattr(_space_eng_71, "get_gps_cep", lambda: 5.0)()

            # Phase 71c: missile defense intercept — check AD units
            _md_eng_71 = getattr(ctx, "missile_defense_engine", None)
            if _md_eng_71 is not None:
                for _m71 in list(_missile_eng_71.active_missiles):
                    if not _m71.active:
                        continue
                    # Find which side launched this missile, defenders are the other side
                    _launcher_side_71 = None
                    for _s71, _su71 in units_by_side.items():
                        for _u71 in _su71:
                            if _u71.entity_id == _m71.launcher_id:
                                _launcher_side_71 = _s71
                                break
                        if _launcher_side_71 is not None:
                            break
                    if _launcher_side_71 is None:
                        continue
                    for _ds71, _du71 in units_by_side.items():
                        if _ds71 == _launcher_side_71:
                            continue
                        for _ad71 in _du71:
                            if _ad71.status != UnitStatus.ACTIVE:
                                continue
                            # Check if unit has AD weapons
                            _has_ad = False
                            for _w71 in getattr(_ad71, "weapons", []):
                                _wcat71 = getattr(getattr(_w71, "definition", _w71), "category", "")
                                if _wcat71 in ("SAM", "CIWS", "MISSILE_LAUNCHER"):
                                    _has_ad = True
                                    break
                            if not _has_ad:
                                continue
                            _dx71 = _ad71.position.easting - _m71.current_pos.easting
                            _dy71 = _ad71.position.northing - _m71.current_pos.northing
                            _dist71 = math.sqrt(_dx71 * _dx71 + _dy71 * _dy71)
                            _ad_range_71 = getattr(_ad71, "max_engagement_range_m", 50000.0)
                            if _dist71 > _ad_range_71:
                                continue
                            _ad_pk_71 = 0.7  # base Pk for AD systems
                            from stochastic_warfare.combat.missiles import MissileType as _MT71
                            if _m71.flight_profile.missile_type in (
                                _MT71.CRUISE_SUBSONIC, _MT71.CRUISE_SUPERSONIC,
                                _MT71.COASTAL_DEFENSE_SSM,
                            ):
                                _cmd_result = _md_eng_71.engage_cruise_missile(
                                    defender_pk=_ad_pk_71,
                                    missile_speed_mps=_m71.flight_profile.speed_mps,
                                    sea_skimming=_m71.flight_profile.cruise_altitude_m < 20.0,
                                    defender_id=_ad71.entity_id,
                                    missile_id=_m71.missile_id,
                                )
                                if _cmd_result.hit:
                                    _m71.active = False
                                    logger.info(
                                        "Missile %s intercepted by %s (cruise defense)",
                                        _m71.missile_id, _ad71.entity_id,
                                    )
                                    break
                            else:
                                _bmd_result = _md_eng_71.engage_ballistic_missile(
                                    defender_pks=[_ad_pk_71],
                                    missile_speed_mps=_m71.flight_profile.speed_mps,
                                    defender_id=_ad71.entity_id,
                                    missile_id=_m71.missile_id,
                                )
                                if _bmd_result.intercepted:
                                    _m71.active = False
                                    logger.info(
                                        "Missile %s intercepted by %s (BMD)",
                                        _m71.missile_id, _ad71.entity_id,
                                    )
                                    break

            # Advance missiles and resolve impacts
            _impacts_71 = _missile_eng_71.update_missiles_in_flight(dt, gps_accuracy_m=_gps_acc_71)
            _dest_thresh_71 = cal_flat.get("destruction_threshold", self._config.destruction_threshold)
            _dis_thresh_71 = cal_flat.get("disable_threshold", self._config.disable_threshold)
            for _impact_71 in _impacts_71:
                if not _impact_71.hit:
                    continue
                # Find nearest unit to impact position
                _best_unit_71: Unit | None = None
                _best_dist_71 = 100.0  # max 100m search radius
                for _su71b in units_by_side.values():
                    for _u71b in _su71b:
                        if _u71b.status != UnitStatus.ACTIVE:
                            continue
                        _dx71b = _u71b.position.easting - _impact_71.impact_pos.easting
                        _dy71b = _u71b.position.northing - _impact_71.impact_pos.northing
                        _d71b = math.sqrt(_dx71b * _dx71b + _dy71b * _dy71b)
                        if _d71b < _best_dist_71:
                            _best_dist_71 = _d71b
                            _best_unit_71 = _u71b
                if _best_unit_71 is not None:
                    _apply_aggregate_casualties(
                        max(1, int(_impact_71.damage_fraction * max(1, len(_best_unit_71.personnel) if _best_unit_71.personnel else 4))),
                        _best_unit_71,
                        _pending_missile_damage,
                        _dest_thresh_71,
                        _dis_thresh_71,
                        self._cumulative_casualties,
                    )
                    logger.debug(
                        "Missile %s hit unit %s (dmg=%.2f)",
                        _impact_71.missile_id, _best_unit_71.entity_id,
                        _impact_71.damage_fraction,
                    )

        # 4i. Phase 71d: carrier ops — CAP management and sortie rate
        _carrier_eng_71 = getattr(ctx, "carrier_ops_engine", None)
        _enable_carrier_ops_71 = cal_flat.get("enable_carrier_ops", False)
        if _carrier_eng_71 is not None and _enable_carrier_ops_71:
            # Update CAP stations
            try:
                _cap_updates_71 = _carrier_eng_71.update_cap_stations(dt)
                for _cap71 in _cap_updates_71:
                    if _cap71.relief_needed:
                        logger.debug("CAP station %s needs relief", _cap71.station_id)
            except Exception:
                logger.debug("CAP station update failed", exc_info=True)

            # Process carrier units
            _weather_eng_71 = getattr(ctx, "weather_engine", None)
            for _side_name_71, _side_units_71 in units_by_side.items():
                for _cu71 in _side_units_71:
                    _ut71 = getattr(_cu71, "unit_type", "")
                    if not ("carrier" in _ut71.lower() or "cv" in _ut71.lower()):
                        continue
                    if _cu71.status != UnitStatus.ACTIVE:
                        continue
                    # Sea state check — Beaufort > 7 suspends flight ops
                    _sea_state_71 = 0.0
                    if _weather_eng_71 is not None:
                        _sea_state_71 = getattr(
                            getattr(_weather_eng_71, "current", None), "sea_state", 0.0,
                        )
                    if _sea_state_71 > 7.0:
                        logger.info(
                            "Carrier %s: flight ops suspended (Beaufort %.0f)",
                            _cu71.entity_id, _sea_state_71,
                        )
                        continue
                    # Count aircraft assigned to this carrier
                    _ac_count_71 = 0
                    for _u71c in _side_units_71:
                        if (
                            getattr(_u71c, "parent_id", None) == _cu71.entity_id
                            and getattr(_u71c, "domain", None) == Domain.AIR
                        ):
                            _ac_count_71 += 1
                    from stochastic_warfare.combat.carrier_ops import DeckState
                    _sortie_rate_71 = _carrier_eng_71.compute_sortie_rate(
                        aircraft_available=_ac_count_71,
                        deck_crew_quality=getattr(_cu71, "training_level", 0.7),
                        weather_factor=max(0.0, 1.0 - _sea_state_71 * 0.1),
                        deck_state=DeckState.IDLE,
                    )
                    logger.debug(
                        "Carrier %s sortie rate: %.1f/hr (aircraft=%d)",
                        _cu71.entity_id, _sortie_rate_71, _ac_count_71,
                    )

        # 5. Rebuild enemy data after movement — position arrays from step 1
        #    are stale (captured pre-movement coordinates).  The Unit object
        #    references in active_enemies point to updated positions, but the
        #    numpy arrays are snapshots that must be refreshed.
        active_enemies, enemy_pos_arrays = self._build_enemy_data(units_by_side)

        # 6. Engagement — detection + combat
        pending_damage = self._execute_engagements(
            ctx, units_by_side, active_enemies, enemy_pos_arrays, dt, timestamp,
            _unit_index=_unit_index,
            _lod_full_update=_lod_full_update,
        )
        # Include mine damage and missile impact damage
        pending_damage.extend(pending_mine_damage)
        pending_damage.extend(_pending_missile_damage)

        # 7. Apply deferred damage
        self._apply_deferred_damage(pending_damage, ctx.event_bus, timestamp)

        # 7a. Phase 85: instant promotion for damaged units
        if cal_flat.get("enable_lod", False):
            for _dmg_unit, _dmg_status in pending_damage:
                self._lod_promoted.add(_dmg_unit.entity_id)

        # 7b. Phase 60b/68e: fire zone damage — apply burn damage to units
        _fz_cal = getattr(getattr(ctx, "config", None), "calibration_overrides", None)
        if _fz_cal is not None and _fz_cal.get("enable_fire_zones", False):
            _inc_eng_fz = getattr(ctx, "incendiary_engine", None)
            if _inc_eng_fz is not None and _inc_eng_fz._active_zones:
                # Phase 70b: reuse _unit_index for O(1) lookup
                _unit_positions: dict[str, Position] = {
                    uid: u.position for uid, u in _unit_index.items()
                    if u.status == UnitStatus.ACTIVE
                }
                _unit_lookup = _unit_index
                _fire_hits = _inc_eng_fz.units_in_fire(_unit_positions)
                _fire_damage_base = _fz_cal.get("fire_damage_per_tick", 0.01)
                _fire_pending: list[tuple[Unit, UnitStatus]] = []
                _fire_dest = _fz_cal.get("destruction_threshold", self._config.destruction_threshold)
                _fire_dis = _fz_cal.get("disable_threshold", self._config.disable_threshold)
                for _fu_id, _burn_rate in _fire_hits.items():
                    _fu_unit = _unit_lookup.get(_fu_id)
                    if _fu_unit is None:
                        continue
                    _fire_dmg = _fire_damage_base * _burn_rate
                    # Posture protection: DUG_IN halves fire damage
                    _fu_posture = getattr(_fu_unit, "posture", None)
                    if _fu_posture is not None and int(_fu_posture) >= 3:
                        _fire_dmg *= 0.5
                    _fire_cas = max(1, int(_fire_dmg * max(1, len(_fu_unit.personnel) if _fu_unit.personnel else 4)))
                    _apply_aggregate_casualties(
                        _fire_cas, _fu_unit, _fire_pending,
                        _fire_dest, _fire_dis,
                        self._cumulative_casualties,
                    )
                    logger.debug("Unit %s fire damage: %.3f (burn_rate=%.3f)", _fu_id, _fire_dmg, _burn_rate)
                if _fire_pending:
                    self._apply_deferred_damage(_fire_pending, ctx.event_bus, timestamp)

        # 7c. Phase 69c: degrade active decoys each tick
        _fow_69c_tick = getattr(ctx, "fog_of_war", None)
        if _fow_69c_tick is not None and cal_flat.get("enable_fog_of_war", False):
            try:
                _fow_69c_tick.update_decoys(dt)
            except (AttributeError, TypeError):
                pass

        # 8. Morale checks
        if battle.ticks_executed % self._config.morale_check_interval == 0:
            self._execute_morale(ctx, units_by_side, active_enemies, timestamp,
                                _lod_full_update=_lod_full_update)

        # 9. Supply consumption (combat rate)
        if ctx.consumption_engine is not None and ctx.stockpile_manager is not None:
            self._execute_supply_consumption(ctx, units_by_side, dt,
                                              _lod_full_update=_lod_full_update)

    # ── Battle termination ──────────────────────────────────────────

    def check_battle_termination(
        self,
        battle: BattleContext,
        units_by_side: dict[str, list[Unit]],
    ) -> bool:
        """Check if a battle should terminate.

        A battle ends when:
        - One side has no active units
        - Max ticks exceeded
        - All opposing forces are out of engagement range
        """
        if not battle.active:
            return True

        if battle.ticks_executed >= self._config.max_ticks_per_battle:
            battle.active = False
            return True

        for side in battle.involved_sides:
            units = units_by_side.get(side, [])
            active = [u for u in units if u.status == UnitStatus.ACTIVE]
            if not active:
                battle.active = False
                return True

        # Check if forces are still in range
        sides = battle.involved_sides
        if len(sides) >= 2:
            active_a = [u for u in units_by_side.get(sides[0], []) if u.status == UnitStatus.ACTIVE]
            active_b = [u for u in units_by_side.get(sides[1], []) if u.status == UnitStatus.ACTIVE]
            if active_a and active_b:
                min_dist = self._min_distance(active_a, active_b)
                if min_dist > self._config.engagement_range_m * 2.0:
                    battle.active = False
                    return True

        return False

    def resolve_battle(self, battle: BattleContext, units_by_side: dict[str, list[Unit]]) -> BattleResult:
        """Finalize a terminated battle and produce a result."""
        battle.active = False
        destroyed: dict[str, int] = {}
        routing: dict[str, int] = {}

        for side in battle.involved_sides:
            units = units_by_side.get(side, [])
            destroyed[side] = sum(1 for u in units if u.status == UnitStatus.DESTROYED)
            routing[side] = sum(1 for u in units if u.status == UnitStatus.ROUTING)

        terminated_by = "force_destroyed"
        for side in battle.involved_sides:
            active = [u for u in units_by_side.get(side, []) if u.status == UnitStatus.ACTIVE]
            if not active:
                terminated_by = f"force_destroyed_{side}"
                break
        else:
            if battle.ticks_executed >= self._config.max_ticks_per_battle:
                terminated_by = "max_ticks"
            else:
                terminated_by = "disengaged"

        return BattleResult(
            battle_id=battle.battle_id,
            duration_ticks=battle.ticks_executed,
            terminated_by=terminated_by,
            units_destroyed=destroyed,
            units_routing=routing,
        )

    # ── Auto-resolve (Phase 13a-6) ──────────────────────────────────

    def auto_resolve(
        self,
        battle: BattleContext,
        units_by_side: dict[str, list[Unit]],
        rng: np.random.Generator,
        morale_states: dict | None = None,
        supply_states: dict | None = None,
    ) -> AutoResolveResult:
        """Auto-resolve a minor battle using simplified Lanchester attrition.

        Adapted from c2/planning/coa.py::wargame_coa.  Computes aggregate
        combat power per side, runs 10 steps of Lanchester attrition,
        and applies losses to individual units.

        Parameters
        ----------
        battle : BattleContext
            The battle to resolve.
        units_by_side : dict
            Current force disposition.
        rng : np.random.Generator
            PRNG stream for loss distribution.
        morale_states : dict | None
            Per-unit morale states for morale factor.
        supply_states : dict | None
            Per-unit supply levels for supply factor.
        """
        battle.active = False
        sides = battle.involved_sides
        if len(sides) < 2:
            return AutoResolveResult(
                battle_id=battle.battle_id,
                winner=sides[0] if sides else "",
            )

        # Compute per-side combat power
        side_power: dict[str, float] = {}
        side_units_active: dict[str, list[Unit]] = {}
        for side in sides:
            units = [u for u in units_by_side.get(side, []) if u.status == UnitStatus.ACTIVE]
            side_units_active[side] = units
            power = 0.0
            for u in units:
                personnel = len(u.personnel) if u.personnel else 4
                equipment = len(u.equipment) if u.equipment else 1
                power += personnel + equipment * 2.0
            side_power[side] = power

        # Apply morale and supply factors
        for side in sides:
            morale_factor = 1.0
            supply_factor = 1.0
            if morale_states:
                from stochastic_warfare.morale.state import MoraleState

                side_morale_vals = [
                    morale_states.get(u.entity_id, MoraleState.STEADY)
                    for u in side_units_active[side]
                ]
                if side_morale_vals:
                    avg_morale = sum(int(m) for m in side_morale_vals) / len(side_morale_vals)
                    morale_factor = max(0.3, 1.0 - avg_morale * 0.15)
            if supply_states:
                side_supply = [
                    supply_states.get(u.entity_id, 1.0)
                    for u in side_units_active[side]
                ]
                if side_supply:
                    avg_supply = sum(side_supply) / len(side_supply)
                    supply_factor = max(0.5, avg_supply)
            side_power[side] *= morale_factor * supply_factor

        # Lanchester attrition loop (10 steps, exponent 0.5)
        power = {s: float(side_power[s]) for s in sides}
        initial_power = {s: float(side_power[s]) for s in sides}
        exponent = 0.5
        steps = 10

        for _ in range(steps):
            if any(power[s] <= 0 for s in sides):
                break
            losses: dict[str, float] = {}
            for s in sides:
                enemy_sides = [o for o in sides if o != s]
                enemy_power = sum(power[o] for o in enemy_sides)
                own_power = max(power[s], 1e-10)
                loss_rate = 0.02 * (enemy_power**exponent / own_power**exponent)
                losses[s] = power[s] * loss_rate
            for s in sides:
                power[s] = max(0.0, power[s] - losses[s])

        # Compute loss fractions
        side_losses: dict[str, float] = {}
        for s in sides:
            if initial_power[s] > 0:
                side_losses[s] = 1.0 - power[s] / initial_power[s]
            else:
                side_losses[s] = 1.0

        # Determine winner (side with most remaining power)
        winner = max(sides, key=lambda s: power[s])

        # Apply losses to units
        for side in sides:
            loss_frac = side_losses[side]
            active = side_units_active[side]
            if not active:
                continue
            # Distribute losses randomly across active units
            num_to_destroy = int(round(loss_frac * len(active)))
            if num_to_destroy > 0:
                indices = list(range(len(active)))
                rng.shuffle(indices)
                for i in indices[:num_to_destroy]:
                    unit = active[i]
                    object.__setattr__(unit, "status", UnitStatus.DESTROYED)
                    self._bus.publish(UnitDestroyedEvent(
                        timestamp=datetime.min,
                        source=ModuleId.COMBAT,
                        unit_id=unit.entity_id,
                        cause="auto_resolve",
                        side=unit.side,
                    ))

        # Estimate duration (shorter for one-sided battles)
        power_ratio = max(power.values()) / max(sum(power.values()), 1e-10)
        duration_s = 3600.0 * (1.0 - power_ratio * 0.5)  # 30min to 1hr

        logger.info(
            "Auto-resolved %s: winner=%s, losses=%s",
            battle.battle_id,
            winner,
            {s: f"{l:.1%}" for s, l in side_losses.items()},
        )

        return AutoResolveResult(
            battle_id=battle.battle_id,
            winner=winner,
            side_losses=side_losses,
            duration_s=duration_s,
        )

    # ── State persistence ───────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture battle manager state for checkpointing."""
        return {
            "battles": {
                bid: {
                    "battle_id": b.battle_id,
                    "start_tick": b.start_tick,
                    "start_time": b.start_time.isoformat(),
                    "involved_sides": b.involved_sides,
                    "active": b.active,
                    "ticks_executed": b.ticks_executed,
                    "unit_ids": list(b.unit_ids),
                    "wave_assignments": b.wave_assignments,
                    "battle_elapsed_s": b.battle_elapsed_s,
                }
                for bid, b in self._battles.items()
            },
            "next_battle_id": self._next_battle_id,
            "vls_launches": dict(self._vls_launches),
            "ammo_expended": dict(self._ammo_expended),
            "pending_decisions": dict(self._pending_decisions),
            # Phase 72b: previously missing state
            "ticks_stationary": dict(self._ticks_stationary),
            "suppression_states": {
                uid: s.get_state()
                for uid, s in self._suppression_states.items()
            },
            "cumulative_casualties": dict(self._cumulative_casualties),
            "undigging": dict(self._undigging),
            "concealment_scores": dict(self._concealment_scores),
            "env_casualty_accum": dict(self._env_casualty_accum),
            "misinterpreted_orders": dict(self._misinterpreted_orders),
            # Phase 85: LOD tier state
            "lod_tiers": dict(self._lod_tiers),
            "lod_pending_tiers": dict(self._lod_pending_tiers),
            "lod_pending_counts": dict(self._lod_pending_counts),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore battle manager state from checkpoint."""
        self._next_battle_id = state.get("next_battle_id", 0)
        self._vls_launches = dict(state.get("vls_launches", {}))
        self._ammo_expended = dict(state.get("ammo_expended", {}))
        self._pending_decisions = dict(state.get("pending_decisions", {}))
        self._battles.clear()
        self._cached_assessments.clear()
        for bid, bdata in state.get("battles", {}).items():
            self._battles[bid] = BattleContext(
                battle_id=bdata["battle_id"],
                start_tick=bdata["start_tick"],
                start_time=datetime.fromisoformat(bdata["start_time"]),
                involved_sides=bdata["involved_sides"],
                active=bdata["active"],
                ticks_executed=bdata["ticks_executed"],
                unit_ids=set(bdata.get("unit_ids", [])),
                wave_assignments=bdata.get("wave_assignments", {}),
                battle_elapsed_s=bdata.get("battle_elapsed_s", 0.0),
            )
        # Phase 72b: restore previously missing state
        self._ticks_stationary = dict(state.get("ticks_stationary", {}))
        self._cumulative_casualties = dict(state.get("cumulative_casualties", {}))
        self._undigging = dict(state.get("undigging", {}))
        self._concealment_scores = {
            k: float(v) for k, v in state.get("concealment_scores", {}).items()
        }
        self._env_casualty_accum = {
            k: float(v) for k, v in state.get("env_casualty_accum", {}).items()
        }
        self._misinterpreted_orders = dict(state.get("misinterpreted_orders", {}))
        self._suppression_states = {}
        for uid, sdata in state.get("suppression_states", {}).items():
            s = UnitSuppressionState()
            s.set_state(sdata)
            self._suppression_states[uid] = s
        # Phase 85: LOD tier state
        self._lod_tiers = {k: int(v) for k, v in state.get("lod_tiers", {}).items()}
        self._lod_pending_tiers = {k: int(v) for k, v in state.get("lod_pending_tiers", {}).items()}
        self._lod_pending_counts = {k: int(v) for k, v in state.get("lod_pending_counts", {}).items()}
        self._lod_promoted = set()

    @property
    def active_battles(self) -> list[BattleContext]:
        """Return all currently active battles."""
        return [b for b in self._battles.values() if b.active]

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _min_distance(units_a: list[Unit], units_b: list[Unit]) -> float:
        """Compute minimum distance between any pair of units."""
        if not units_a or not units_b:
            return float("inf")
        pos_a = np.array(
            [(u.position.easting, u.position.northing) for u in units_a],
            dtype=np.float64,
        )
        pos_b = np.array(
            [(u.position.easting, u.position.northing) for u in units_b],
            dtype=np.float64,
        )
        # Broadcast distance computation
        diffs = pos_a[:, np.newaxis, :] - pos_b[np.newaxis, :, :]
        dists = np.sqrt(np.sum(diffs * diffs, axis=2))
        return float(np.min(dists))

    def _classify_lod_tiers(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        enemy_pos_arrays: dict[str, np.ndarray],
        battle: Any,
    ) -> set[str]:
        """Classify units into LOD tiers. Returns entity_ids for full update this tick."""
        cal_flat = _resolve_cal_flat(ctx)
        if not cal_flat.get("enable_lod", False):
            return {
                u.entity_id
                for su in units_by_side.values()
                for u in su
                if u.status == UnitStatus.ACTIVE
            }

        nearby_interval = cal_flat.get("lod_nearby_interval", 5)
        distant_interval = cal_flat.get("lod_distant_interval", 20)
        hysteresis = cal_flat.get("lod_hysteresis_ticks", 3)
        tick = battle.ticks_executed
        full_update: set[str] = set()

        for side_name, side_units in units_by_side.items():
            pos_arr = enemy_pos_arrays.get(side_name, np.empty((0, 2)))

            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                uid = u.entity_id

                # 1. Compute raw tier from distance to nearest enemy
                if uid in self._lod_promoted:
                    raw_tier = UnitLodTier.ACTIVE
                elif pos_arr.shape[0] == 0:
                    raw_tier = UnitLodTier.DISTANT
                else:
                    upos = np.array([u.position.easting, u.position.northing])
                    diffs = pos_arr - upos
                    nearest_dist = float(np.sqrt(np.min(np.sum(diffs * diffs, axis=1))))

                    # Max weapon range for ACTIVE threshold
                    max_wpn = max(
                        (w[0].definition.max_range_m for w in ctx.unit_weapons.get(uid, [])),
                        default=0.0,
                    )
                    # Max sensor range for NEARBY threshold
                    max_sensor = max(
                        (s.effective_range for s in ctx.unit_sensors.get(uid, [])),
                        default=0.0,
                    )

                    active_thresh = max(max_wpn * 2.0, 100.0)
                    nearby_thresh = max(max_sensor, active_thresh)

                    if nearest_dist <= active_thresh:
                        raw_tier = UnitLodTier.ACTIVE
                    elif nearest_dist <= nearby_thresh:
                        raw_tier = UnitLodTier.NEARBY
                    else:
                        raw_tier = UnitLodTier.DISTANT

                # 2. Apply hysteresis (immediate promotion, delayed demotion)
                is_new = uid not in self._lod_tiers
                current = self._lod_tiers.get(uid, UnitLodTier.ACTIVE)
                if is_new:  # first classification — assign directly
                    final = raw_tier
                elif raw_tier < current:  # promotion (lower tier value = higher priority)
                    final = raw_tier
                    self._lod_pending_tiers.pop(uid, None)
                    self._lod_pending_counts.pop(uid, None)
                elif raw_tier > current:  # demotion
                    if self._lod_pending_tiers.get(uid) == raw_tier:
                        count = self._lod_pending_counts.get(uid, 0) + 1
                        self._lod_pending_counts[uid] = count
                        final = raw_tier if count >= hysteresis else current
                        if count >= hysteresis:
                            self._lod_pending_tiers.pop(uid, None)
                            self._lod_pending_counts.pop(uid, None)
                    else:
                        self._lod_pending_tiers[uid] = raw_tier
                        self._lod_pending_counts[uid] = 1
                        final = current
                else:
                    final = raw_tier
                    self._lod_pending_tiers.pop(uid, None)
                    self._lod_pending_counts.pop(uid, None)

                self._lod_tiers[uid] = final

                # 3. Determine if this unit gets full update this tick
                if final == UnitLodTier.ACTIVE:
                    full_update.add(uid)
                elif final == UnitLodTier.NEARBY and tick % nearby_interval == 0:
                    full_update.add(uid)
                elif final == UnitLodTier.DISTANT and tick % distant_interval == 0:
                    full_update.add(uid)

        self._lod_promoted.clear()
        return full_update

    @staticmethod
    def _build_enemy_data(
        units_by_side: dict[str, list[Unit]],
    ) -> tuple[dict[str, list[Unit]], dict[str, np.ndarray]]:
        """Pre-build per-side active enemy lists and position arrays."""
        active_enemies: dict[str, list[Unit]] = {}
        enemy_pos_arrays: dict[str, np.ndarray] = {}

        for side in units_by_side:
            enemies: list[Unit] = []
            for other_side, other_units in units_by_side.items():
                if other_side != side:
                    enemies.extend(u for u in other_units if u.status == UnitStatus.ACTIVE)
            active_enemies[side] = enemies
            if enemies:
                enemy_pos_arrays[side] = np.array(
                    [(e.position.easting, e.position.northing) for e in enemies],
                    dtype=np.float64,
                )
            else:
                enemy_pos_arrays[side] = np.empty((0, 2), dtype=np.float64)

        return active_enemies, enemy_pos_arrays

    def _process_ooda_completions(
        self,
        ctx: Any,
        completions: list[tuple[str, Any]],
        timestamp: datetime,
    ) -> None:
        """Handle OODA phase completions — trigger assessment/decision.

        After processing each completion, advances the OODA loop to the
        next phase with tactical acceleration applied.
        """
        from stochastic_warfare.c2.ai.ooda import OODAPhase

        cal_flat = _resolve_cal_flat(ctx)

        # Tactical acceleration multiplier (< 1 = faster decisions in battle)
        tactical_mult = 1.0
        if ctx.ooda_engine is not None:
            tactical_mult = ctx.ooda_engine.tactical_acceleration

        for unit_id, completed_phase in completions:
            # Look up doctrinal school for this unit
            school = None
            if ctx.school_registry is not None:
                school = ctx.school_registry.get_for_unit(unit_id)

            if completed_phase == OODAPhase.OBSERVE:
                # Run situation assessment with real data
                if ctx.assessor is not None:
                    side = self._find_unit_side(ctx, unit_id)
                    if side:
                        friendly = len(ctx.active_units(side))
                        # Phase 53a: Use fog-of-war detected count if enabled
                        _fow_enabled = cal_flat.get("enable_fog_of_war", False)
                        if _fow_enabled and getattr(ctx, "fog_of_war", None) is not None:
                            try:
                                _wv = ctx.fog_of_war.get_world_view(side)
                                enemies = len(_wv.contacts)
                            except Exception:
                                enemies = sum(
                                    len(ctx.active_units(s))
                                    for s in ctx.side_names()
                                    if s != side
                                )
                        else:
                            enemies = sum(
                                len(ctx.active_units(s))
                                for s in ctx.side_names()
                                if s != side
                            )

                        # Real morale from state tracking
                        morale_level = self._get_unit_morale_level(ctx, unit_id)

                        # Real supply from stockpile manager
                        supply_level = self._get_unit_supply_level(ctx, unit_id)

                        # Get school weight overrides
                        weight_overrides = None
                        if school is not None:
                            weight_overrides = school.get_assessment_weight_overrides() or None
                        # Phase 53b: C2 effectiveness from comms state
                        c2_eff = self._compute_c2_effectiveness(ctx, unit_id, side)
                        # Phase 69c: inflate enemy_power by active decoy count
                        _enemy_power_69c = float(enemies)
                        _fow_69c_obs = getattr(ctx, "fog_of_war", None)
                        if _fow_69c_obs is not None:
                            _cal_69c = getattr(ctx, "calibration", None)
                            if _cal_69c is not None and _cal_69c.get("enable_fog_of_war", False):
                                try:
                                    _active_decoys = _fow_69c_obs.get_active_decoys()
                                    _enemy_power_69c += sum(
                                        1.0 for d in _active_decoys if d.effectiveness > 0
                                    )
                                except (AttributeError, TypeError):
                                    pass

                        assessment = ctx.assessor.assess(
                            unit_id=unit_id,
                            echelon=5,
                            friendly_units=friendly,
                            friendly_power=float(friendly),
                            morale_level=morale_level,
                            supply_level=supply_level,
                            c2_effectiveness=c2_eff,
                            contacts=enemies,
                            enemy_power=_enemy_power_69c,
                            ts=timestamp,
                            weight_overrides=weight_overrides,
                        )
                        # Cache assessment for DECIDE phase
                        self._cached_assessments[unit_id] = assessment
            elif completed_phase == OODAPhase.DECIDE:
                # Phase 63d: C2 friction — skip DECIDE when comms too degraded
                _cal_c2 = getattr(ctx, "calibration", None)
                if _cal_c2 is not None and _cal_c2.get("enable_c2_friction", False):
                    _c2_side = self._find_unit_side(ctx, unit_id)
                    if _c2_side:
                        _c2_eff = self._compute_c2_effectiveness(ctx, unit_id, _c2_side)
                        _c2_min = _cal_c2.get("c2_min_effectiveness", 0.3)
                        if _c2_eff < _c2_min:
                            logger.debug("C2 friction: unit %s DECIDE skipped (eff=%.2f < min=%.2f)",
                                         unit_id, _c2_eff, _c2_min)
                            continue

                # Phase 64b: Planning delay — skip DECIDE if unit is still planning
                _planning_64 = getattr(ctx, "planning_engine", None)
                if _planning_64 is not None and _cal_c2 is not None and _cal_c2.get("enable_c2_friction", False):
                    from stochastic_warfare.c2.planning.process import PlanningPhase as _PP64
                    _plan_status = _planning_64.get_planning_status(unit_id)
                    if _plan_status not in (_PP64.IDLE, _PP64.COMPLETE):
                        logger.debug("Planning delay: unit %s in phase %s, DECIDE deferred",
                                     unit_id, _plan_status.name)
                        continue
                    if _plan_status == _PP64.IDLE:
                        from stochastic_warfare.c2.orders.types import Order as _Ord64b, OrderType as _OT64b, OrderPriority as _OP64b
                        _plan_order = _Ord64b(
                            order_id=f"plan_{unit_id}_{timestamp}",
                            issuer_id=unit_id, recipient_id=unit_id,
                            timestamp=timestamp, order_type=_OT64b.FRAGO,
                            echelon_level=5, priority=_OP64b.PRIORITY,
                            mission_type=0,
                        )
                        _avail_time = _cal_c2.get("planning_available_time_s", 7200.0)
                        try:
                            _method = _planning_64.initiate_planning(
                                unit_id, _plan_order, _avail_time, timestamp,
                            )
                            logger.debug("Initiated %s planning for %s", _method.name, unit_id)
                        except Exception:
                            logger.debug("Planning initiation failed for %s", unit_id, exc_info=True)
                        continue  # Wait for planning to complete

                # Run decision engine with real assessment + personality
                if ctx.decision_engine is not None:
                    # Retrieve cached assessment from OBSERVE phase
                    assessment = self._cached_assessments.get(unit_id)

                    # Get commander personality
                    personality = None
                    if ctx.commander_engine is not None:
                        personality = ctx.commander_engine.get_personality(unit_id)

                    # Build assessment summary from real data
                    assessment_summary = self._build_assessment_summary(
                        ctx, unit_id, assessment,
                    )

                    # Get school decision adjustments
                    school_adjustments = None
                    if school is not None:
                        school_adjustments = school.get_decision_score_adjustments(
                            echelon=5,
                            assessment_summary=assessment_summary,
                        )
                        # Apply opponent modeling if enabled
                        if school.definition.opponent_modeling_enabled:
                            side = self._find_unit_side(ctx, unit_id)
                            enemies = sum(
                                len(ctx.active_units(s))
                                for s in ctx.side_names()
                                if s != side
                            ) if side else 1
                            friendly = len(ctx.active_units(side)) if side else 1
                            opponent_prediction = school.predict_opponent_action(
                                own_assessment=assessment_summary,
                                opponent_power=float(enemies),
                                opponent_morale=assessment_summary.get("morale_level", 0.7),
                                own_power=float(friendly),
                            )
                            if opponent_prediction:
                                temp_scores = dict(school_adjustments)
                                adjusted = school.adjust_scores_for_opponent(
                                    temp_scores, opponent_prediction,
                                )
                                school_adjustments = adjusted

                    # Phase 69b: planning result injection — bias school_adjustments
                    if _planning_64 is not None and _cal_c2 is not None and _cal_c2.get("enable_c2_friction", False):
                        _plan_result_69b = _planning_64.consume_result(unit_id)
                        if _plan_result_69b is not None and school_adjustments is not None:
                            _planning_bonus = 0.10
                            school_adjustments[_plan_result_69b] = (
                                school_adjustments.get(_plan_result_69b, 0.0) + _planning_bonus
                            )
                            logger.debug("Planning result '%s' injected for %s (+%.2f)",
                                         _plan_result_69b, unit_id, _planning_bonus)

                    # Phase 68f: expire old stratagems before evaluating new ones
                    if getattr(ctx, "stratagem_engine", None) is not None and battle is not None:
                        _strat_dur = _cal_c2.get("stratagem_duration_ticks", 100) if _cal_c2 is not None else 100
                        _expired = ctx.stratagem_engine.expire_stratagems(
                            battle.ticks_executed, _strat_dur,
                        )
                        for _exp_id in _expired:
                            logger.debug("Stratagem %s expired at tick %d", _exp_id, battle.ticks_executed)

                    # Phase 53c/64d: Evaluate + activate stratagem opportunities
                    # (before decide() so bonuses flow into school_adjustments)
                    if getattr(ctx, "stratagem_engine", None) is not None and assessment is not None:
                        side = self._find_unit_side(ctx, unit_id)
                        if side:
                            unit_ids = [u.entity_id for u in ctx.active_units(side)]
                            experience = getattr(personality, "experience", 0.5) if personality else 0.5
                            affinity: dict[str, float] = {}
                            if school is not None:
                                affinity = school.get_stratagem_affinity()
                            _strat_activate = (
                                _cal_c2 is not None and _cal_c2.get("enable_c2_friction", False)
                            )
                            conc_viable = False
                            dec_viable = False
                            try:
                                conc_viable, _ = ctx.stratagem_engine.evaluate_concentration_opportunity(
                                    assessment, unit_ids, echelon=5, experience=experience,
                                )
                                if conc_viable:
                                    logger.debug(
                                        "Concentration opportunity for %s (affinity=%.2f)",
                                        unit_id, affinity.get("CONCENTRATION", 0.5),
                                    )
                            except Exception:
                                pass
                            try:
                                dec_viable, _ = ctx.stratagem_engine.evaluate_deception_opportunity(
                                    assessment, unit_ids, echelon=5, experience=experience,
                                )
                                if dec_viable:
                                    logger.debug(
                                        "Deception opportunity for %s (affinity=%.2f)",
                                        unit_id, affinity.get("DECEPTION", 0.5),
                                    )
                            except Exception:
                                pass

                            # Phase 64d: Activate stratagems when c2_friction enabled
                            if _strat_activate:
                                if conc_viable:
                                    _enemy_sides = [s for s in ctx.side_names() if s != side]
                                    _enemy_units_64 = []
                                    for _es in _enemy_sides:
                                        _enemy_units_64.extend(ctx.active_units(_es))
                                    if _enemy_units_64:
                                        _avg_e = sum((getattr(e, "position", None) or Position(0, 0, 0)).easting for e in _enemy_units_64) / len(_enemy_units_64)
                                        _avg_n = sum((getattr(e, "position", None) or Position(0, 0, 0)).northing for e in _enemy_units_64) / len(_enemy_units_64)
                                        _conc_point = Position(_avg_e, _avg_n, 0.0)
                                        _economy = unit_ids[-2:] if len(unit_ids) > 4 else []
                                        _conc_units = [u for u in unit_ids if u not in _economy]
                                        try:
                                            _plan = ctx.stratagem_engine.plan_concentration(_conc_units, _conc_point, _economy)
                                            _strat_tick = battle.ticks_executed if battle is not None else 0
                                            ctx.stratagem_engine.activate_stratagem(unit_id, _plan, timestamp, tick=_strat_tick)
                                            if school_adjustments is not None:
                                                _bonus = _cal_c2.get("stratagem_concentration_bonus", 0.08)
                                                school_adjustments["ATTACK"] = school_adjustments.get("ATTACK", 0.0) + _bonus
                                        except Exception:
                                            logger.debug("Concentration activation failed for %s", unit_id, exc_info=True)
                                if dec_viable:
                                    _feint = unit_ids[:1]
                                    _main = unit_ids[1:]
                                    try:
                                        _plan = ctx.stratagem_engine.plan_deception(_feint, "enemy_front", _main)
                                        _strat_tick = battle.ticks_executed if battle is not None else 0
                                        ctx.stratagem_engine.activate_stratagem(unit_id, _plan, timestamp, tick=_strat_tick)
                                        if school_adjustments is not None:
                                            _bonus = _cal_c2.get("stratagem_deception_bonus", 0.10)
                                            school_adjustments["ATTACK"] = school_adjustments.get("ATTACK", 0.0) + _bonus
                                        # Phase 69c: deploy phantom decoys via FOW
                                        _fow_69c = getattr(ctx, "fog_of_war", None)
                                        if _fow_69c is not None and _cal_c2 is not None and _cal_c2.get("enable_fog_of_war", False):
                                            _phantom_count = _cal_c2.get("deception_phantom_count", 3)
                                            _feint_pos_list = []
                                            for _fid in _feint:
                                                _fp = _get_unit_position(ctx, _fid)
                                                if _fp is not None:
                                                    _feint_pos_list.append(_fp)
                                            if _feint_pos_list:
                                                _rng_69c = getattr(ctx, "rng_manager", None)
                                                _dec_stream = _rng_69c.get_stream(ModuleId.C2) if _rng_69c is not None else None
                                                for _pi in range(_phantom_count):
                                                    _base = _feint_pos_list[_pi % len(_feint_pos_list)]
                                                    _dist = 500.0 + 1000.0 * (_dec_stream.random() if _dec_stream else 0.5)
                                                    _ang = 2 * math.pi * (_dec_stream.random() if _dec_stream else 0.25 * _pi)
                                                    _dec_pos = Position(
                                                        _base.easting + math.cos(_ang) * _dist,
                                                        _base.northing + math.sin(_ang) * _dist,
                                                        _base.altitude,
                                                    )
                                                    _fow_69c.deploy_decoy(_dec_pos)
                                                logger.debug("Deception: %d phantoms deployed for %s", _phantom_count, unit_id)
                                    except Exception:
                                        logger.debug("Deception activation failed for %s", unit_id, exc_info=True)

                    # Phase 64a/68c: Order propagation — compute delay + misinterpretation
                    # When c2_friction is enabled, orders may be delayed or misinterpreted.
                    _order_delayed_68c = False
                    _result_68c = None
                    if getattr(ctx, "order_propagation", None) is not None:
                        _cal_64a = getattr(ctx, "calibration", None)
                        if _cal_64a is not None and _cal_64a.get("enable_c2_friction", False):
                            # Phase 68c: check if unit has a pending delayed decision
                            _pending_at = self._pending_decisions.get(unit_id)
                            _elapsed_s = battle.battle_elapsed_s if battle is not None else 0.0
                            if _pending_at is not None:
                                if _elapsed_s < _pending_at:
                                    logger.debug("Order pending for %s (%.1fs remaining)",
                                                 unit_id, _pending_at - _elapsed_s)
                                    continue  # still waiting
                                else:
                                    # Delay matured — pop and execute
                                    self._pending_decisions.pop(unit_id, None)
                                    logger.debug("Order delay matured for %s", unit_id)
                            else:
                                # First time: propagate order to determine delay
                                from stochastic_warfare.c2.orders.types import Order as _Order64a, OrderType as _OT64a, OrderPriority as _OP64a
                                _order_64a = _Order64a(
                                    order_id=f"decide_{unit_id}_{timestamp}",
                                    issuer_id=unit_id,
                                    recipient_id=unit_id,
                                    timestamp=timestamp,
                                    order_type=_OT64a.FRAGO,
                                    echelon_level=5,
                                    priority=_OP64a.PRIORITY,
                                    mission_type=0,
                                )
                                _sender_pos = _get_unit_position(ctx, unit_id)
                                _prop_cfg = getattr(ctx.order_propagation, "_config", None)
                                if _prop_cfg is not None:
                                    _prop_cfg.delay_sigma = _cal_64a.get("order_propagation_delay_sigma", 0.4)
                                    _prop_cfg.base_misinterpretation = _cal_64a.get("order_misinterpretation_base", 0.05)
                                try:
                                    _result_68c = ctx.order_propagation.propagate_order(
                                        _order_64a, _sender_pos, _sender_pos, timestamp,
                                    )
                                    if not _result_68c.success:
                                        logger.debug("Order propagation failed for %s", unit_id)
                                        continue
                                    # Phase 68c: enforce delay by deferring decide
                                    if _result_68c.total_delay_s > 0:
                                        self._pending_decisions[unit_id] = _elapsed_s + _result_68c.total_delay_s
                                        logger.debug("Order delayed for %s: %.1fs", unit_id, _result_68c.total_delay_s)
                                        _order_delayed_68c = True
                                    # Phase 68d: store misinterpretation for enforcement
                                    if _result_68c.was_misinterpreted:
                                        self._misinterpreted_orders[unit_id] = _result_68c
                                        logger.debug("Order misinterpreted for %s: %s", unit_id, _result_68c.misinterpretation_type)
                                except Exception:
                                    logger.debug("Order propagation error for %s", unit_id, exc_info=True)
                        else:
                            logger.debug("Order propagation available for %s", unit_id)

                    if _order_delayed_68c:
                        continue  # skip decide until delay matures

                    # Phase 68d: apply misinterpretation effects before decide
                    _misinterp = self._misinterpreted_orders.pop(unit_id, None)
                    if _misinterp is not None and hasattr(_misinterp, "misinterpretation_type"):
                        _mistype = _misinterp.misinterpretation_type
                        if _mistype == "timing":
                            # Double the remaining delay — re-queue
                            _elapsed_s = battle.battle_elapsed_s if battle is not None else 0.0
                            _extra = _misinterp.total_delay_s
                            self._pending_decisions[unit_id] = _elapsed_s + _extra
                            logger.debug("Timing misinterpretation: %s re-delayed %.1fs", unit_id, _extra)
                            continue
                        elif _mistype == "unit_designation":
                            # Wrong unit addressed — skip this decide cycle
                            logger.debug("Unit designation misinterpretation: %s skipped", unit_id)
                            continue
                        elif _mistype == "objective" and school_adjustments is not None:
                            # Swap ATTACK ↔ DEFEND
                            _atk = school_adjustments.get("ATTACK", 0.0)
                            _def = school_adjustments.get("DEFEND", 0.0)
                            school_adjustments["ATTACK"] = _def
                            school_adjustments["DEFEND"] = _atk
                            logger.debug("Objective misinterpretation: %s ATTACK/DEFEND swapped", unit_id)
                        elif _mistype == "position":
                            # Offset movement target (handled post-decide via position perturbation)
                            _misinterp_radius = (_cal_c2 or {}).get("misinterpretation_radius_m", 500.0)
                            _rng_mis = getattr(ctx, "rng_manager", None)
                            if _rng_mis is not None:
                                _mis_stream = _rng_mis.get_stream(ModuleId.C2)
                                _angle = _mis_stream.random() * 2 * math.pi
                                _offset_e = math.cos(_angle) * _misinterp_radius
                                _offset_n = math.sin(_angle) * _misinterp_radius
                                _upos = _get_unit_position(ctx, unit_id)
                                if _upos is not None:
                                    _new_pos = Position(
                                        _upos.easting + _offset_e,
                                        _upos.northing + _offset_n,
                                        _upos.altitude,
                                    )
                                    # Find unit and offset its position
                                    for _side_units_68d in units_by_side.values():
                                        for _u_68d in _side_units_68d:
                                            if _u_68d.entity_id == unit_id:
                                                object.__setattr__(_u_68d, "position", _new_pos)
                                                break
                                    logger.debug("Position misinterpretation: %s offset by %.0fm", unit_id, _misinterp_radius)

                    ctx.decision_engine.decide(
                        unit_id=unit_id,
                        echelon=5,
                        assessment=assessment,
                        personality=personality,
                        doctrine=None,
                        ts=timestamp,
                        school_adjustments=school_adjustments,
                    )

            # Advance to the next OODA phase and start its timer
            if ctx.ooda_engine is not None:
                # Fold school + commander OODA multipliers into tactical_mult
                effective_mult = tactical_mult
                if school is not None:
                    effective_mult *= school.get_ooda_multiplier()
                if ctx.commander_engine is not None:
                    effective_mult *= ctx.commander_engine.get_ooda_speed_multiplier(unit_id)
                next_phase = ctx.ooda_engine.advance_phase(unit_id)
                ctx.ooda_engine.start_phase(
                    unit_id,
                    next_phase,
                    tactical_mult=effective_mult,
                    ts=timestamp,
                )

    @staticmethod
    def _apply_behavior_rules(
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        behavior_rules: dict[str, Any],
    ) -> None:
        """Set unit speeds from scenario behavior_rules (pre-scripted behavior).

        Mirrors :func:`~stochastic_warfare.validation.scenario_runner.apply_behavior`.
        For each side, reads ``advance_speed_mps`` or ``hold_position`` and
        sets ``speed`` on active units accordingly.
        """
        for side, units in units_by_side.items():
            rules = behavior_rules.get(side, {})
            if rules.get("hold_position", False):
                for u in units:
                    if u.status == UnitStatus.ACTIVE:
                        object.__setattr__(u, "speed", 0.0)
                continue

            advance_speed = rules.get("advance_speed_mps", 0.0)
            if advance_speed > 0:
                for u in units:
                    if u.status == UnitStatus.ACTIVE:
                        object.__setattr__(u, "speed", advance_speed)

    def _execute_movement(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        dt: float,
        battle: BattleContext | None = None,
        behavior_rules: dict[str, Any] | None = None,
        enemy_pos_arrays: dict[str, np.ndarray] | None = None,
    ) -> None:
        """Execute movement for all active units."""
        cal_flat = _resolve_cal_flat(ctx)
        wave_interval = cal_flat.get("wave_interval_s", 300.0)
        battle_elapsed = battle.battle_elapsed_s if battle is not None else 0.0
        wave_assignments = battle.wave_assignments if battle is not None else {}
        _rules = behavior_rules or {}

        # Sides that should hold position (defensive doctrine)
        defensive_sides = set(cal_flat.get("defensive_sides", []))

        # Phase 70c: hoist movement-loop calibration lookups
        _mv_enable_sea_state = cal_flat.get("enable_sea_state_ops", False)
        _mv_enable_seasonal = cal_flat.get("enable_seasonal_effects", False)
        _mv_enable_obstacle = cal_flat.get("enable_obstacle_effects", False)
        _mv_enable_fire_zones = cal_flat.get("enable_fire_zones", False)
        _mv_enable_obscurants = cal_flat.get("enable_obscurants", False)
        _mv_enable_fuel = cal_flat.get("enable_fuel_consumption", False)
        _mv_enable_ice_crossing = cal_flat.get("enable_ice_crossing", False)
        _mv_enable_bridge = cal_flat.get("enable_bridge_capacity", False)

        # Phase 70c: hoist movement-loop engine references
        _mv_maint_eng = getattr(ctx, "maintenance_engine", None)
        _mv_seasons_eng = getattr(ctx, "seasons_engine", None)
        _mv_weather_eng = getattr(ctx, "weather_engine", None)
        _mv_trench_eng = getattr(ctx, "trench_engine", None)
        _mv_obs_eng = getattr(ctx, "obscurants_engine", None)
        _mv_inc_eng = getattr(ctx, "incendiary_engine", None)
        _mv_obstacle_mgr = getattr(ctx, "obstacle_manager", None)
        _mv_hydro = getattr(ctx, "hydrography_manager", None)
        _mv_infra = getattr(ctx, "infrastructure", None)
        _mv_movement_eng = getattr(ctx, "movement_engine", None)
        _mv_classif = getattr(ctx, "classification", None)

        # Phase 78b: weight defaults for bridge capacity enforcement
        _WEIGHT_DEFAULTS: dict[str, float] = {
            "m1a2_abrams": 62.0, "t72b": 41.0, "t90a": 46.5,
            "leopard_2a6": 62.3, "challenger_2": 62.5,
            "m2_bradley": 27.6, "bmp2": 14.3, "btr80": 13.6,
            "m113": 12.3, "stryker": 18.0,
        }

        for side, units in units_by_side.items():
            enemies = active_enemies.get(side, [])
            if not enemies:
                continue
            # Phase 70a: pre-fetched numpy position array for vectorized helpers
            _epa = enemy_pos_arrays.get(side) if enemy_pos_arrays is not None else None

            # If behavior_rules explicitly say hold_position, skip this side
            side_rules = _rules.get(side, {})
            if side_rules.get("hold_position", False):
                continue

            # Defensive sides don't advance
            if side in defensive_sides:
                continue

            # Phase 70b: hoist formation sort — compute once per side, not per unit
            _sorted_active = sorted(
                [ou for ou in units if ou.status == UnitStatus.ACTIVE],
                key=lambda ou: ou.entity_id,
            )
            _unit_formation_idx: dict[str, int] = {
                ou.entity_id: i for i, ou in enumerate(_sorted_active)
            }
            _n_sorted = len(_sorted_active)
            # Phase 70c: hoist side-specific formation spacing
            _spacing_side = cal_flat.get(
                f"{side}_formation_spacing_m",
                cal_flat.get("formation_spacing_m", 50.0),
            )

            for u in units:
                if u.status != UnitStatus.ACTIVE:
                    continue

                # Emplaced / air-defense units hold position
                if _should_hold_position(u):
                    continue

                # Effective speed: use current speed (set by behavior_rules
                # or AI), fall back to max_speed for scenarios without rules
                effective_speed = u.speed if u.speed > 0 else u.max_speed
                if effective_speed <= 0:
                    continue

                # Phase 50a: posture → movement speed multiplier
                posture_val = getattr(u, "posture", None)
                if posture_val is not None:
                    posture_int = int(posture_val)
                    if posture_int >= 3:  # DUG_IN or FORTIFIED
                        uid = u.entity_id
                        # Defensive sides stay dug in — no un-dig
                        if side not in defensive_sides:
                            if uid not in self._undigging:
                                # First tick: start un-digging, skip movement
                                self._undigging[uid] = True
                                object.__setattr__(u, "posture", type(u.posture)(0))
                                continue
                            else:
                                # Second tick: cleared to move
                                del self._undigging[uid]
                        else:
                            continue  # Defensive side stays put
                    speed_mult = _POSTURE_SPEED_MULT.get(posture_int, 1.0)
                    effective_speed *= speed_mult
                    if effective_speed <= 0:
                        continue

                # Phase 51b: naval posture → speed multiplier
                np_val = getattr(u, "naval_posture", None)
                if np_val is not None:
                    effective_speed *= _NAVAL_POSTURE_SPEED_MULT.get(int(np_val), 1.0)
                    if effective_speed <= 0:
                        continue

                # Phase 61a: sea state ops — Beaufort speed penalty + tidal current
                if _mv_enable_sea_state:
                    _domain_61 = getattr(u, "domain", None)
                    if _domain_61 in (Domain.NAVAL, Domain.SUBMARINE, Domain.AMPHIBIOUS):
                        _sse = getattr(ctx, "sea_state_engine", None)
                        if _sse is not None:
                            try:
                                _sea = _sse.current
                                _bf = _sea.beaufort_scale
                                # Small craft speed penalty: −20% per Beaufort above 3
                                _disp = getattr(u, "displacement_tons", 0)
                                _is_small = _disp > 0 and _disp < 1000
                                if not _is_small:
                                    _is_small = effective_speed > 0 and getattr(u, "max_speed", 0) < 15
                                if _is_small and _bf > 3:
                                    _bf_pen = max(0.0, 1.0 - 0.2 * (_bf - 3))
                                    effective_speed *= _bf_pen
                                # Tidal current adjustment along movement heading
                                if dist > 0:
                                    _heading = math.atan2(dx, dy)
                                    _tc_spd = _sea.tidal_current_speed
                                    _tc_dir = _sea.tidal_current_direction
                                    _tc_effect = _tc_spd * math.cos(_tc_dir - _heading)
                                    effective_speed = max(0.0, effective_speed + _tc_effect)
                            except Exception:
                                pass
                        if effective_speed <= 0:
                            continue

                # Phase 56b: readiness-based movement speed penalty
                if _mv_maint_eng is not None:
                    try:
                        _rdns = _mv_maint_eng.get_unit_readiness(u.entity_id)
                        if _rdns < 1.0:
                            effective_speed *= max(0.3, _rdns)
                            if effective_speed <= 0:
                                continue
                    except (KeyError, Exception):
                        pass

                # Wave gating: check if this unit's wave has been released
                wave = wave_assignments.get(u.entity_id, 0)
                if wave == -1:
                    continue  # Reserve — never moves
                if wave > 0 and battle_elapsed < wave * wave_interval:
                    continue  # Wave not yet released

                # Standoff: stop closing once within best weapon range
                # of the nearest enemy
                standoff = _standoff_range(u, ctx)
                nearest_dist = _nearest_enemy_dist(u.position, enemies, enemy_pos_arr=_epa)
                if nearest_dist <= standoff:
                    continue

                # Blend centroid + nearest enemy for movement target,
                # then add a perpendicular offset to maintain formation
                # spacing and prevent centroid collapse.
                tx, ty = _movement_target(u.position, enemies, enemy_pos_arr=_epa)
                dx = tx - u.position.easting
                dy = ty - u.position.northing
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < 1.0:
                    continue

                # Phase 70b: hoisted formation index — O(1) lookup per unit
                if _n_sorted > 1:
                    _idx = _unit_formation_idx.get(u.entity_id, 0)
                    # Lateral offset: center the formation around the advance
                    # axis so units stay evenly spaced perpendicular to the
                    # direction of movement.
                    _lat_offset = (_idx - (_n_sorted - 1) / 2.0) * _spacing_side
                    perp_x, perp_y = -dy / dist, dx / dist
                    tx += perp_x * _lat_offset
                    ty += perp_y * _lat_offset
                    # Recompute advance vector
                    dx = tx - u.position.easting
                    dy = ty - u.position.northing
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist < 1.0:
                        continue

                # Phase 54b: trench movement factor (WW1)
                if _mv_trench_eng is not None and u.position is not None:
                    try:
                        mvt_factor = _mv_trench_eng.movement_factor_at(
                            u.position.easting, u.position.northing,
                        )
                        if mvt_factor < 1.0:
                            effective_speed *= mvt_factor
                    except Exception:
                        pass

                # Phase 59a: seasonal ground condition speed modifier
                if _mv_seasons_eng is not None and _mv_enable_seasonal:
                    _domain = getattr(u, "domain", None)
                    if _domain not in (Domain.NAVAL, Domain.AERIAL, Domain.SUBMARINE):
                        _sc = _mv_seasons_eng.current
                        _ms = getattr(u, "max_speed", 0)
                        if _ms > 15:  # wheeled
                            _mud_mult = max(0.1, 1.0 - _sc.mud_depth / 0.3)
                        elif _ms > 5:  # tracked
                            _mud_mult = max(0.3, 1.0 - _sc.mud_depth / 0.5)
                        else:  # foot
                            _mud_mult = max(0.4, 1.0 - _sc.mud_depth / 0.4)
                        _snow_mult = max(0.4, 1.0 - _sc.snow_depth / 0.5)
                        _traf_mult = _sc.ground_trafficability
                        effective_speed *= _mud_mult * _snow_mult * _traf_mult
                        if effective_speed <= 0:
                            continue

                # Phase 59c: wind gust operational gates
                if _mv_weather_eng is not None and _mv_enable_seasonal:
                    _gust = getattr(_mv_weather_eng.current.wind, "gust", 0)
                    _domain = getattr(u, "domain", None)
                    if _domain == Domain.AERIAL:
                        _utype = str(getattr(u, "unit_type", ""))
                        if "HELO" in _utype.upper() or "HELICOPTER" in _utype.upper():
                            if _gust > 15.0:
                                continue
                    if _domain in (None, Domain.GROUND) and getattr(u, "max_speed", 0) <= 5.0:
                        if _gust > 25.0:
                            continue

                # MOPP speed factor (Phase 25c)
                mopp_speed_factor = 1.0
                cbrn = getattr(ctx, "cbrn_engine", None)
                if cbrn is not None:
                    mopp_levels = getattr(cbrn, "_mopp_levels", {})
                    mopp_level = mopp_levels.get(u.entity_id, 0)
                    if mopp_level > 0:
                        from stochastic_warfare.cbrn.protection import ProtectionEngine
                        mopp_speed_factor = ProtectionEngine.get_mopp_speed_factor(mopp_level)

                # Don't overshoot past standoff distance
                max_close = max(0.0, nearest_dist - standoff)
                move_dist = min(effective_speed * dt * mopp_speed_factor, dist, max_close)
                if move_dist <= 0:
                    continue

                # Phase 58e: fuel gate — vehicles with no fuel cannot move
                _fuel = getattr(u, "fuel_remaining", 1.0)
                _is_vehicle = getattr(u, "max_speed", 0) > 5.0
                if _fuel <= 0.0 and _is_vehicle:
                    continue

                # Phase 59d: obstacle traversal speed reduction
                if _mv_enable_obstacle:
                    if _mv_obstacle_mgr is not None:
                        try:
                            _obstacles = _mv_obstacle_mgr.obstacles_at(u.position)
                            for _obs in _obstacles:
                                _tmult = getattr(_obs, "traversal_time_multiplier", 1.0)
                                if _tmult > 1.0:
                                    move_dist /= _tmult
                        except Exception:
                            pass
                    if move_dist <= 0:
                        continue

                # Phase 78a: ice crossing speed penalty + water cell gate
                if _mv_enable_ice_crossing and _mv_seasons_eng is not None:
                    _tent_ix = u.position.easting + (dx / dist) * move_dist
                    _tent_iy = u.position.northing + (dy / dist) * move_dist
                    _tent_pos_ice = Position(_tent_ix, _tent_iy)
                    if _mv_movement_eng is not None:
                        _ice_snap = _mv_seasons_eng.current
                        if _mv_movement_eng.is_on_ice(u.position, _ice_snap):
                            move_dist *= 0.5  # 50% speed on ice
                        # Block movement into unfrozen water
                        if _mv_classif is not None:
                            try:
                                from stochastic_warfare.terrain.classification import LandCover as _LC78
                                _tent_lc = _mv_classif.land_cover_at(_tent_pos_ice)
                                if _tent_lc == _LC78.WATER:
                                    if not _mv_movement_eng.is_on_ice(_tent_pos_ice, _ice_snap):
                                        continue
                            except (IndexError, ValueError):
                                pass
                    if move_dist <= 0:
                        continue

                # Phase 78b: bridge capacity + ford crossing
                if _mv_enable_bridge:
                    _tent_bx = u.position.easting + (dx / dist) * move_dist
                    _tent_by = u.position.northing + (dy / dist) * move_dist
                    _tent_bpos = Position(_tent_bx, _tent_by)
                    _u_weight = getattr(u, "weight_tons", 0.0) or _WEIGHT_DEFAULTS.get(u.unit_type, 0.0)
                    # Check bridge capacity
                    _blocked_bridge = False
                    if _mv_infra is not None and _u_weight > 0:
                        try:
                            _bridges = _mv_infra.bridges_near(_tent_bpos, 50.0)
                            for _br in _bridges:
                                if _u_weight > _br.capacity_tons:
                                    logger.debug(
                                        "Unit %s (%.1ft) blocked by bridge %s (%.1ft capacity)",
                                        u.entity_id, _u_weight, _br.bridge_id, _br.capacity_tons,
                                    )
                                    _blocked_bridge = True
                                    break
                        except Exception:
                            pass
                    if _blocked_bridge:
                        continue
                    # Ford crossing: allow at 30% speed
                    if _mv_hydro is not None:
                        try:
                            if _mv_hydro.is_in_water(_tent_bpos):
                                _fords = _mv_hydro.ford_points_near(_tent_bpos, 500.0)
                                if _fords:
                                    move_dist *= 0.3
                                else:
                                    # No ford — block unless ice allows
                                    if not (_mv_enable_ice_crossing and _mv_seasons_eng is not None
                                            and _mv_movement_eng is not None
                                            and _mv_movement_eng.is_on_ice(_tent_bpos, _mv_seasons_eng.current)):
                                        continue
                        except Exception:
                            pass
                    if move_dist <= 0:
                        continue

                # Phase 60b: fire zones block movement
                if _mv_enable_fire_zones:
                    if _mv_inc_eng is not None and _mv_inc_eng._active_zones:
                        _tent_nx = u.position.easting + (dx / dist) * move_dist
                        _tent_ny = u.position.northing + (dy / dist) * move_dist
                        for _fz in _mv_inc_eng._active_zones:
                            _fz_dx = _tent_nx - _fz.center[0]
                            _fz_dy = _tent_ny - _fz.center[1]
                            if math.sqrt(_fz_dx**2 + _fz_dy**2) < _fz.current_radius_m:
                                move_dist = 0
                                break
                        if move_dist <= 0:
                            continue

                nx = u.position.easting + (dx / dist) * move_dist
                ny = u.position.northing + (dy / dist) * move_dist
                object.__setattr__(u, "position", Position(nx, ny, u.position.altitude))

                # Phase 60b: vehicle movement dust trail on dry ground
                if _mv_obs_eng is not None and _mv_enable_obscurants:
                    _domain = getattr(u, "domain", None)
                    if _domain not in (Domain.NAVAL, Domain.AERIAL, Domain.SUBMARINE):
                        if _is_vehicle and move_dist > 5.0:
                            _is_dry = True
                            if _mv_seasons_eng is not None:
                                from stochastic_warfare.environment.seasons import GroundState
                                _is_dry = _mv_seasons_eng.current.ground_state == GroundState.DRY
                            if _is_dry:
                                try:
                                    _dust_r = 10.0 + effective_speed * 0.5
                                    _mv_obs_eng.add_dust(u.position, radius=_dust_r)
                                except Exception:
                                    pass

                # Phase 68a: consume fuel proportional to distance moved
                if _mv_enable_fuel and _is_vehicle and hasattr(u, "fuel_remaining"):
                    _domain_fuel = getattr(u, "domain", None)
                    _fuel_rate = getattr(u, "fuel_consumption_rate", None)
                    if _fuel_rate is None:
                        # Rates per meter of 0.0–1.0 fuel fraction.
                        # Ground: ~500km range → 0.000002/m.  Aerial: ~3000km → 0.0000003/m.
                        # Naval: ~10,000km → 0.0000001/m.
                        if _domain_fuel == Domain.AERIAL:
                            _fuel_rate = 0.0000003
                        elif _domain_fuel == Domain.NAVAL:
                            _fuel_rate = 0.0000001
                        else:
                            _fuel_rate = 0.000002  # ground default ~500km range
                    _new_fuel = max(0.0, u.fuel_remaining - move_dist * _fuel_rate)
                    object.__setattr__(u, "fuel_remaining", _new_fuel)
                    if _new_fuel <= 0.0:
                        object.__setattr__(u, "speed", 0.0)
                        logger.warning("Unit %s out of fuel — speed set to 0", u.entity_id)

    # ------------------------------------------------------------------
    # Phase 41a: Terrain combat modifiers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_terrain_modifiers(
        ctx: Any,
        target_pos: Position,
        attacker_pos: Position,
        *,
        elevation_cap: float = 0.3,
        elevation_floor: float = -0.1,
        seasonal_vegetation: float = 0.0,
    ) -> tuple[float, float, float]:
        """Query terrain at positions and return (cover, elevation_mod, concealment).

        Returns defaults (0.0, 1.0, 0.0) when terrain managers are absent.
        """
        cover = 0.0
        elevation_mod = 1.0
        concealment = 0.0

        # 1. Terrain classification cover & concealment
        classification = getattr(ctx, "classification", None)
        if classification is not None:
            try:
                props = classification.properties_at(target_pos)
                cover = max(cover, props.cover)
                concealment = props.concealment
                # Phase 59b: seasonal vegetation concealment bonus
                if seasonal_vegetation > 0:
                    _lc_name = getattr(
                        getattr(props, "land_cover", None), "name", "",
                    )
                    if "FOREST" in _lc_name or "SHRUB" in _lc_name:
                        concealment = min(1.0, concealment + seasonal_vegetation * 0.3)
            except (IndexError, ValueError, AttributeError):
                pass

        # 2. Trench cover (WW1+)
        trench_engine = getattr(ctx, "trench_engine", None)
        if trench_engine is not None:
            try:
                tq = trench_engine.query_trench(target_pos.easting, target_pos.northing)
                if tq.in_trench:
                    cover = max(cover, tq.cover_value)
            except (IndexError, ValueError, AttributeError):
                pass

        # 3. Building cover
        infra = getattr(ctx, "infrastructure_manager", None)
        if infra is not None:
            try:
                buildings = infra.buildings_at(target_pos)
                for b in buildings:
                    cover = max(cover, getattr(b, "cover_value", 0.0))
            except (IndexError, ValueError, AttributeError):
                pass

        # 4. Obstacle fortification cover
        obstacle_mgr = getattr(ctx, "obstacle_manager", None)
        if obstacle_mgr is not None:
            try:
                obstacles = obstacle_mgr.obstacles_at(target_pos)
                for obs in obstacles:
                    if hasattr(obs, "obstacle_type"):
                        ot_name = obs.obstacle_type.name if hasattr(obs.obstacle_type, "name") else str(obs.obstacle_type)
                        if ot_name == "FORTIFICATION":
                            cover = max(cover, 0.8)
            except (IndexError, ValueError, AttributeError):
                pass

        # 5. Elevation advantage
        heightmap = getattr(ctx, "heightmap", None)
        if heightmap is not None:
            try:
                att_elev = heightmap.elevation_at(attacker_pos)
                tgt_elev = heightmap.elevation_at(target_pos)
                delta = att_elev - tgt_elev
                # +10% per 33m height advantage, configurable cap/floor
                raw = delta / 330.0
                elevation_mod = 1.0 + max(elevation_floor, min(elevation_cap, raw))
            except (IndexError, ValueError):
                pass

        # 6. Phase 69e: Burned zone concealment reduction
        _inc_eng_69e = getattr(ctx, "incendiary_engine", None)
        if _inc_eng_69e is not None:
            try:
                for _bz in _inc_eng_69e.get_burned_zones():
                    _dx = target_pos.easting - _bz.center.easting
                    _dy = target_pos.northing - _bz.center.northing
                    if _dx * _dx + _dy * _dy <= _bz.radius_m * _bz.radius_m:
                        concealment = max(0.0, concealment - _bz.concealment_reduction)
            except (AttributeError, TypeError):
                pass

        return cover, elevation_mod, concealment

    # ------------------------------------------------------------------
    # Phase 41c: Threat-based target scoring
    # ------------------------------------------------------------------

    def _score_target(
        self,
        attacker: Unit,
        target: Unit,
        distance: float,
        attacker_weapons: list,
        ctx: Any,
    ) -> float:
        """Compute threat-based target score. Higher = more attractive."""
        # Threat: target's ability to damage us
        target_weapons = ctx.unit_weapons.get(target.entity_id, [])
        target_max_range = max(
            (w[0].definition.max_range_m for w in target_weapons), default=0.0
        )
        attacker_armor = getattr(attacker, "armor_front", 0.0)
        threat = min(5.0, max(0.1, target_max_range / max(1.0, attacker_armor * 10.0)))

        # Pk: our hit likelihood at this range
        best_wpn_range = max(
            (w[0].definition.max_range_m for w in attacker_weapons), default=1000.0
        )
        pk = min(3.0, best_wpn_range / max(1.0, distance))

        # Value: target type priority (configurable weights)
        # Phase 50e: calibration can override BattleConfig target weights
        cfg = self._config
        cal_flat = _resolve_cal_flat(ctx)
        _tvw = cal_flat.get("target_value_weights")
        if _tvw is not None:
            value = _target_value(
                target,
                hq=_tvw.get("hq", cfg.target_value_hq),
                ad=_tvw.get("ad", cfg.target_value_ad),
                artillery=_tvw.get("artillery", cfg.target_value_artillery),
                armor=_tvw.get("armor", cfg.target_value_armor),
                default=_tvw.get("default", cfg.target_value_default),
            )
        else:
            value = _target_value(
                target,
                hq=cfg.target_value_hq,
                ad=cfg.target_value_ad,
                artillery=cfg.target_value_artillery,
                armor=cfg.target_value_armor,
                default=cfg.target_value_default,
            )

        # Distance penalty
        dist_pen = max(1.0, distance / max(1.0, best_wpn_range))

        return (threat * pk * value) / dist_pen

    def _execute_engagements(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        enemy_pos_arrays: dict[str, np.ndarray],
        dt: float,
        timestamp: datetime,
        _unit_index: dict[str, Unit] | None = None,
        _lod_full_update: set[str] | None = None,
    ) -> list[tuple[Unit, UnitStatus]]:
        """Run detection + engagement for all units. Returns deferred damage."""
        pending_damage: list[tuple[Unit, UnitStatus]] = []
        cal_flat = _resolve_cal_flat(ctx)
        visibility_m = cal_flat.get("visibility_m", self._config.default_visibility_m)
        hit_prob_mod = cal_flat.get("hit_probability_modifier", 1.0)
        # Per-side target_size_modifier: look up target_size_modifier_{side}, fall back to uniform
        target_size_mod_default = cal_flat.get("target_size_modifier", 1.0)
        # Phase 41a: force channeling
        max_engagers = cal_flat.get("max_engagers_per_side", 0)
        # Phase 41c: target selection mode
        target_selection_mode = cal_flat.get("target_selection_mode", "threat_scored")

        # Phase 44a/52b: Weather combat effects (computed once per tick)
        weather_pk_modifier = 1.0
        wind_e = 0.0
        wind_n = 0.0
        precipitation_rate_mmhr = 0.0
        weather_engine = getattr(ctx, "weather_engine", None)
        if weather_engine is not None:
            try:
                conditions = weather_engine.current
                # Use weather visibility when worse than calibration
                weather_vis = conditions.visibility
                if weather_vis < visibility_m:
                    visibility_m = weather_vis
                # Precipitation Pk penalty
                weather_pk_modifier = _compute_weather_pk_modifier(
                    int(conditions.state),
                )
                # Phase 52b: extract wind for crosswind penalty
                wind = conditions.wind
                wind_e = -wind.speed * math.sin(wind.direction)
                wind_n = -wind.speed * math.cos(wind.direction)
                # Phase 52b: extract precipitation for radar attenuation
                precipitation_rate_mmhr = conditions.precipitation_rate
            except Exception:
                pass

        # Phase 52a: Night combat effects — continuous twilight gradation
        night_visual_modifier = 1.0
        night_thermal_modifier = 1.0
        tod_engine = getattr(ctx, "time_of_day_engine", None)
        lat = getattr(ctx.config, "latitude", 0.0)
        lon = getattr(ctx.config, "longitude", 0.0)
        if tod_engine is not None:
            try:
                illum = tod_engine.illumination_at(lat, lon)
                _thermal_floor = cal_flat.get("night_thermal_floor", 0.8)
                night_visual_modifier, night_thermal_modifier = (
                    _compute_night_modifiers(illum, _thermal_floor)
                )
            except Exception:
                pass

        # Phase 60c: physics-based thermal ΔT model (computed once per tick)
        thermal_dt_contrast = 1.0
        if cal_flat.get("enable_thermal_crossover", False) and tod_engine is not None:
            try:
                _therm = tod_engine.thermal_environment(lat, lon)
                # Base contrast from solar-elevation model, scaled by scenario
                # calibration (thermal_contrast > 1 = superior thermal sights,
                # e.g. M1A1 in desert night).
                _cal_tc = cal_flat.get("thermal_contrast", 1.0)
                thermal_dt_contrast = min(1.0, _therm.thermal_contrast * _cal_tc)
                if _therm.crossover_in_hours < 0.5:
                    thermal_dt_contrast *= max(0.1, _therm.crossover_in_hours / 0.5)
            except Exception:
                pass

        # Phase 44a: Sea state effects (computed once per tick)
        sea_dispersion_modifier = 1.0
        _sea_wave_period = 0.0
        _sea_wave_dir = 0.0
        _sea_beaufort = 0
        sea_state_engine = getattr(ctx, "sea_state_engine", None)
        if sea_state_engine is not None:
            try:
                sea = sea_state_engine.current
                _sea_beaufort = sea.beaufort_scale
                _sea_wave_period = sea.wave_period
                _sea_wave_dir = sea.tidal_current_direction  # swell direction
                if sea.beaufort_scale > 4:
                    sea_dispersion_modifier = 1.0 + 0.2 * (
                        sea.beaufort_scale - 4
                    )
            except Exception:
                pass

        # Phase 42a: ROE engine and hold-fire discipline
        roe_engine = getattr(ctx, "roe_engine", None)
        roe_level_str = cal_flat.get("roe_level", None)
        if roe_engine is not None and roe_level_str is not None:
            from stochastic_warfare.c2.roe import RoeLevel
            try:
                roe_engine._default_level = RoeLevel[roe_level_str.upper()]
            except (KeyError, AttributeError):
                pass
        behavior_rules = getattr(ctx.config, "behavior_rules", None) or {}

        if ctx.engagement_engine is None:
            return pending_damage

        # Phase 70c/86a: hoist calibration lookups into local variables
        _enable_seasonal = cal_flat.get("enable_seasonal_effects", False)
        _enable_em_prop = cal_flat.get("enable_em_propagation", False)
        _enable_nvg = cal_flat.get("enable_nvg_detection", False)
        _enable_thermal_xo = cal_flat.get("enable_thermal_crossover", False)
        _enable_obscurants = cal_flat.get("enable_obscurants", False)
        _enable_acoustic = cal_flat.get("enable_acoustic_layers", False)
        _enable_human_factors = cal_flat.get("enable_human_factors", False)
        _enable_air_combat_env = cal_flat.get("enable_air_combat_environment", False)
        _enable_unconventional = cal_flat.get("enable_unconventional_warfare", False)
        _enable_ammo_gate = cal_flat.get("enable_ammo_gate", False)
        _enable_fire_zones = cal_flat.get("enable_fire_zones", False)
        _enable_missile_routing = cal_flat.get("enable_missile_routing", False)
        _enable_air_routing = cal_flat.get("enable_air_routing", False)
        _enable_sea_state_ops = cal_flat.get("enable_sea_state_ops", False)
        _enable_equip_stress = cal_flat.get("enable_equipment_stress", False)
        _observation_decay = cal_flat.get("observation_decay_rate", 0.05)
        _rain_atten_factor = cal_flat.get("rain_attenuation_factor", 1.0)
        _stealth_penalty = cal_flat.get("stealth_detection_penalty", 0.0)
        _sigint_bonus = cal_flat.get("sigint_detection_bonus", 0.0)
        _eng_conceal_thresh = cal_flat.get("engagement_concealment_threshold", 0.5)
        _dest_thresh = cal_flat.get("destruction_threshold", self._config.destruction_threshold)
        _dis_thresh = cal_flat.get("disable_threshold", self._config.disable_threshold)
        _sam_supp = cal_flat.get("sam_suppression_modifier", 0.0)
        _wind_accuracy_scale = cal_flat.get("wind_accuracy_penalty_scale", 0.03)
        _jammer_mult = cal_flat.get("jammer_coverage_mult", 1.0)
        _dew_disable_thresh = cal_flat.get("dew_disable_threshold", 0.5)
        _night_thermal_floor = cal_flat.get("night_thermal_floor", 0.8)

        # Phase 70c: hoist engine references (each getattr is O(1) but ~95 per tick)
        _weather_eng = getattr(ctx, "weather_engine", None)
        _tod_eng = getattr(ctx, "time_of_day_engine", None)
        _sea_eng = getattr(ctx, "sea_state_engine", None)
        _cbrn_eng = getattr(ctx, "cbrn_engine", None)
        _obs_eng = getattr(ctx, "obscurants_engine", None)
        _ua_eng = getattr(ctx, "underwater_acoustics_engine", None)
        _ew_eng = getattr(ctx, "ew_engine", None)
        _eccm_eng = getattr(ctx, "eccm_engine", None)
        _det_eng = getattr(ctx, "detection_engine", None)
        _space_eng = getattr(ctx, "space_engine", None)
        _seasons_eng = getattr(ctx, "seasons_engine", None)
        _maint_eng = getattr(ctx, "maintenance_engine", None)
        _inc_eng = getattr(ctx, "incendiary_engine", None)
        _conditions_eng = getattr(ctx, "conditions_engine", None)
        _gas_eng = getattr(ctx, "gas_warfare_engine", None)
        _uw_eng = getattr(ctx, "unconventional_engine", None)
        _pop_eng = getattr(ctx, "population_engine", None)
        _sup_eng = getattr(ctx, "suppression_engine", None)
        _air_combat_eng = getattr(ctx, "air_combat_engine", None)

        # Phase 84c: Build per-side enemy STRtrees for engagement culling
        _eng_trees: dict[str, STRtree | None] = {}
        for _et_side in units_by_side:
            _et_pos = enemy_pos_arrays.get(_et_side)
            if _et_pos is not None and _et_pos.shape[0] > 0:
                _et_pts = [
                    Point(_et_pos[i, 0], _et_pos[i, 1])
                    for i in range(_et_pos.shape[0])
                ]
                _eng_trees[_et_side] = STRtree(_et_pts)
            else:
                _eng_trees[_et_side] = None

        # Phase 86b: Batch per-observer modifiers — compute once per unit,
        # reuse across all targets/weapons.
        _observer_mods: dict[str, _ObserverModifiers] = {}
        _obs_alt_thresh = cal_flat.get("altitude_sickness_threshold_m", 2500.0)
        _obs_alt_rate = cal_flat.get("altitude_sickness_rate", 0.03)
        _obs_fov_full = cal_flat.get("mopp_fov_reduction_4", 0.7)
        _obs_rl_full = cal_flat.get("mopp_reload_factor_4", 1.5)
        for _obs_units in units_by_side.values():
            for _obs_u in _obs_units:
                if _obs_u.status != UnitStatus.ACTIVE:
                    continue
                _obs_uid = _obs_u.entity_id
                # MOPP
                _obs_mopp_det = 1.0
                _obs_mopp_fat = 1.0
                _obs_mopp_lvl = 0
                if _cbrn_eng is not None:
                    try:
                        _s, _obs_mopp_det, _obs_mopp_fat = _cbrn_eng.get_mopp_effects(_obs_uid)
                        _obs_mopp_lvl = getattr(_cbrn_eng, "_mopp_levels", {}).get(_obs_uid, 0)
                    except Exception:
                        pass
                _obs_mopp_fov = 1.0
                _obs_mopp_rl = 1.0
                if _obs_mopp_lvl > 0 and _enable_human_factors:
                    _fov_sc = _obs_mopp_lvl / 4.0
                    _obs_mopp_fov = 1.0 - _fov_sc * (1.0 - _obs_fov_full)
                    _obs_mopp_rl = 1.0 + _fov_sc * (_obs_rl_full - 1.0)
                # Altitude
                _obs_alt_f = 1.0
                if _enable_human_factors:
                    _obs_alt = getattr(_obs_u.position, "altitude", 0.0) or 0.0
                    if _obs_alt > _obs_alt_thresh:
                        _obs_alt_f = max(
                            0.5,
                            1.0 - _obs_alt_rate * (_obs_alt - _obs_alt_thresh) / 100.0,
                        )
                        if getattr(_obs_u, "acclimatized", False):
                            _obs_alt_f = 1.0 - (1.0 - _obs_alt_f) * 0.5
                # Readiness
                _obs_rdns = 1.0
                if _maint_eng is not None:
                    try:
                        _obs_rdns = _maint_eng.get_unit_readiness(_obs_uid)
                    except Exception:
                        pass
                _observer_mods[_obs_uid] = _ObserverModifiers(
                    mopp_detection=_obs_mopp_det,
                    mopp_fov_mod=_obs_mopp_fov,
                    mopp_fatigue=_obs_mopp_fat,
                    mopp_reload_mod=_obs_mopp_rl,
                    mopp_level=_obs_mopp_lvl,
                    altitude_factor=_obs_alt_f,
                    readiness=_obs_rdns,
                )

        for side_name, side_units in units_by_side.items():
            enemies = active_enemies.get(side_name, [])
            pos_arr = enemy_pos_arrays.get(side_name, np.empty((0, 2)))
            side_engagements = 0

            for attacker in side_units:
                if attacker.status != UnitStatus.ACTIVE:
                    continue

                # Phase 85: LOD gate — only full-update units initiate
                if _lod_full_update is not None and attacker.entity_id not in _lod_full_update:
                    continue

                # Phase 41a: force channeling — limit engagers per side
                if max_engagers > 0 and side_engagements >= max_engagers:
                    break

                # Phase 50b: air posture gate — GROUNDED/RETURNING skip
                air_posture = getattr(attacker, "air_posture", None)
                if air_posture is not None and int(air_posture) in (0, 3):
                    continue

                # Phase 51b: naval posture gate — ANCHORED skip
                naval_posture = getattr(attacker, "naval_posture", None)
                if naval_posture is not None and int(naval_posture) == 0:
                    continue

                # Phase 40f: morale gate — routed/surrendered units don't fire
                attacker_morale = ctx.morale_states.get(attacker.entity_id)
                if attacker_morale is not None:
                    ms = MoraleState(int(attacker_morale)) if not isinstance(attacker_morale, MoraleState) else attacker_morale
                    if ms in (MoraleState.ROUTED, MoraleState.SURRENDERED):
                        continue

                # Phase 66b: data link range gates UAV engagement
                if _enable_unconventional:
                    _dlr = getattr(attacker, "data_link_range", None)
                    if _dlr is not None and _dlr > 0:
                        # Phase 70b: O(1) parent lookup via _unit_index
                        _cmd_pos_dlr = None
                        _cmd_id_dlr = getattr(attacker, "parent_id", None)
                        if _cmd_id_dlr:
                            _parent_dlr = _unit_index.get(_cmd_id_dlr)
                            if _parent_dlr is not None:
                                _cmd_pos_dlr = getattr(_parent_dlr, "position", None)
                        if _cmd_pos_dlr is not None:
                            _dx_dlr = attacker.position.easting - _cmd_pos_dlr.easting
                            _dy_dlr = attacker.position.northing - _cmd_pos_dlr.northing
                            if math.sqrt(_dx_dlr * _dx_dlr + _dy_dlr * _dy_dlr) > _dlr:
                                logger.debug("UAV %s beyond data link range (%.0fm)", attacker.entity_id, _dlr)
                                continue  # skip engagement

                weapons = ctx.unit_weapons.get(attacker.entity_id, [])
                if not weapons or pos_arr.shape[0] == 0:
                    continue

                # Target selection (vectorized distance computation)
                att_pos = np.array([attacker.position.easting, attacker.position.northing])
                diffs = pos_arr - att_pos
                dists = np.sqrt(np.sum(diffs * diffs, axis=1))

                # Phase 41c: threat-based or closest target selection
                if target_selection_mode == "closest":
                    best_idx = int(np.argmin(dists))
                else:
                    # Phase 84c: pre-filter candidates within weapon range
                    _eng_tree = _eng_trees.get(side_name)
                    _max_wpn_range = max(
                        (w[0].definition.max_range_m for w in weapons),
                        default=1000.0,
                    )
                    if _eng_tree is not None:
                        _cand_idxs = sorted(_eng_tree.query(
                            Point(
                                attacker.position.easting,
                                attacker.position.northing,
                            ).buffer(_max_wpn_range),
                        ))
                    else:
                        _cand_idxs = list(range(len(enemies)))
                    if not _cand_idxs:
                        _cand_idxs = list(range(len(enemies)))
                    best_score = -1.0
                    best_idx = _cand_idxs[0]
                    for ei in _cand_idxs:
                        score = self._score_target(
                            attacker, enemies[ei], float(dists[ei]), weapons, ctx,
                        )
                        if score > best_score:
                            best_score = score
                            best_idx = ei

                best_range = float(dists[best_idx])
                best_target = enemies[best_idx]

                # Phase 41a: terrain modifiers
                # Phase 59b: pass seasonal vegetation for concealment bonus
                _sv = 0.0
                if _seasons_eng is not None and _enable_seasonal:
                    _sv = _seasons_eng.current.vegetation_density
                terrain_cover, elevation_mod, concealment = self._compute_terrain_modifiers(
                    ctx, best_target.position, attacker.position,
                    elevation_cap=self._config.elevation_advantage_cap,
                    elevation_floor=self._config.elevation_disadvantage_floor,
                    seasonal_vegetation=_sv,
                )

                # Detection check
                detection_range = visibility_m
                weather_independent = False
                sensors = ctx.unit_sensors.get(attacker.entity_id, [])
                for sensor in sensors:
                    if sensor.effective_range > detection_range:
                        detection_range = sensor.effective_range
                        if sensor.sensor_type in _WEATHER_BYPASS_TYPES:
                            weather_independent = True

                # Phase 61c: radar horizon gate + EM ducting
                if _enable_em_prop and weather_independent:
                    _best_st_em = getattr(
                        sensors[0] if sensors else None, "sensor_type", None,
                    )
                    if _best_st_em == SensorType.RADAR:
                        _em_env = _conditions_eng
                        if _em_env is not None:
                            try:
                                # Antenna height: aircraft=altitude, ship~30m, ground~10m
                                _att_domain = getattr(attacker, "domain", None)
                                if _att_domain == Domain.AERIAL:
                                    _ant_h = max(10.0, attacker.position.altitude)
                                elif _att_domain in (Domain.NAVAL, Domain.SUBMARINE):
                                    _ant_h = 30.0
                                else:
                                    _ant_h = 10.0
                                _tgt_alt = best_target.position.altitude
                                _radar_hz = _em_env.radar_horizon(_ant_h)
                                _tgt_hz = _em_env.radar_horizon(max(0, _tgt_alt))
                                _total_hz = _radar_hz + _tgt_hz
                                if best_range > _total_hz and _tgt_alt < 500:
                                    detection_range = 0.0  # below radar horizon
                                # EM ducting: extend range in maritime environments
                                from stochastic_warfare.environment.electromagnetic import FrequencyBand
                                _prop = _em_env.propagation(
                                    FrequencyBand.SHF,
                                    best_range / 1000.0,
                                )
                                if _prop.ducting_possible and _att_domain in (
                                    Domain.NAVAL, Domain.SUBMARINE,
                                ):
                                    _duct_ext = min(
                                        2.0,
                                        _em_env.effective_earth_radius_factor() / (4.0 / 3.0),
                                    )
                                    detection_range *= _duct_ext
                            except Exception:
                                pass

                # Phase 50c: continuous concealment — persistent per-target,
                # decays with sustained observation, resets on target movement
                tid = best_target.entity_id
                terrain_concealment = concealment
                if tid not in self._concealment_scores:
                    self._concealment_scores[tid] = terrain_concealment
                # Moving target resets concealment (harder to stay hidden)
                if best_target.speed > 0.5:
                    self._concealment_scores[tid] = terrain_concealment * 0.5
                # Decay with sustained observation
                decay = _observation_decay
                self._concealment_scores[tid] = max(
                    0.0, self._concealment_scores[tid] - decay,
                )
                effective_concealment = self._concealment_scores[tid]

                # Concealment reduces detection range; thermal/radar get 0.3x effect
                if effective_concealment > 0 and not weather_independent:
                    detection_range *= (1.0 - effective_concealment)
                elif effective_concealment > 0 and weather_independent:
                    detection_range *= (1.0 - effective_concealment * 0.3)

                # Phase 52a / 60c: Night degrades visual detection; thermal barely affected
                if not weather_independent:
                    detection_range *= night_visual_modifier
                    # Phase 60c: NVG detection recovery
                    if _enable_nvg and night_visual_modifier < 1.0:
                        _has_nvg = any(
                            getattr(s, "sensor_type", None) == SensorType.NVG
                            for s in sensors
                        )
                        if _has_nvg and tod_engine is not None:
                            try:
                                _nvg_eff = tod_engine.nvg_effectiveness(lat, lon)
                                _nvg_recovery = _nvg_eff * 0.5
                                _nvg_visual = night_visual_modifier + _nvg_recovery * (1.0 - night_visual_modifier)
                                detection_range /= night_visual_modifier
                                detection_range *= _nvg_visual
                            except Exception:
                                pass
                else:
                    if _enable_thermal_xo:
                        _tdc = thermal_dt_contrast
                        if _tdc < 0.5 and getattr(best_target, "speed", 0) > 1.0:
                            _tdc = max(_tdc, 0.5)
                        detection_range *= _tdc
                    else:
                        detection_range *= night_thermal_modifier

                # Phase 52b: Rain attenuates radar/weather-independent sensors
                if weather_independent and precipitation_rate_mmhr > 0:
                    _rain_f = _compute_rain_detection_factor(
                        precipitation_rate_mmhr, detection_range / 1000.0,
                    )
                    _rain_scale = _rain_atten_factor
                    detection_range *= _rain_f ** _rain_scale

                # Phase 62d: icing degrades radar detection (ice on radome)
                if _enable_air_combat_env and weather_independent:
                    _cond62r = _conditions_eng
                    if _cond62r is not None:
                        try:
                            _air62r = _cond62r.air()
                            _icing62r = getattr(_air62r, "icing_risk", 0.0)
                            if _icing62r > 0.5:
                                _ice_db = cal_flat.get("icing_radar_penalty_db", 3.0)
                                # Convert dB loss to linear factor on range
                                # Radar range eq: R^4, so factor = 10^(-dB/40)
                                _ice_factor = 10.0 ** (-_ice_db / 40.0)
                                detection_range *= _ice_factor
                        except Exception:
                            pass

                # Phase 86b: MOPP + altitude modifiers from pre-computed batch
                _obs = _observer_mods.get(attacker.entity_id, _DEFAULT_OBS_MODS)
                detection_range *= _obs.mopp_detection
                detection_range *= _obs.mopp_fov_mod
                detection_range *= _obs.altitude_factor
                mopp_fatigue_factor = _obs.mopp_fatigue
                _mopp_level_62 = _obs.mopp_level

                # Phase 55c-1: WW1 gas warfare MOPP — query gas mask protection
                _gas_protection = 0.0
                if _gas_eng is not None:
                    try:
                        _mopp, _gas_protection = _gas_eng.get_effective_mopp_level(
                            best_target.entity_id,
                            time_since_alert_s=ctx.clock.elapsed.total_seconds(),
                        )
                    except Exception:
                        pass

                # Phase 56e: naval posture modifies target detectability
                _tnp = getattr(best_target, "naval_posture", None)
                if _tnp is not None:
                    detection_range *= _NAVAL_POSTURE_DETECT_MULT.get(int(_tnp), 1.0)

                # Phase 60a: obscurant opacity at target position
                if _obs_eng is not None and _enable_obscurants:
                    try:
                        _opacity = _obs_eng.opacity_at(best_target.position)
                        if not weather_independent:
                            detection_range *= (1.0 - _opacity.visual)
                        else:
                            _best_st = getattr(
                                sensors[0] if sensors else None, "sensor_type", None,
                            )
                            if _best_st == SensorType.THERMAL:
                                detection_range *= (1.0 - _opacity.thermal)
                            elif _best_st == SensorType.RADAR:
                                detection_range *= (1.0 - _opacity.radar)
                    except Exception:
                        pass

                # Phase 61b: acoustic layer modifiers for sonar sensors
                if _enable_acoustic and sensors:
                    _best_st61 = getattr(
                        sensors[0] if sensors else None, "sensor_type", None,
                    )
                    _SONAR_TYPES_61 = frozenset({
                        SensorType.ACTIVE_SONAR,
                        SensorType.PASSIVE_SONAR,
                        SensorType.PASSIVE_ACOUSTIC,
                    })
                    if _best_st61 in _SONAR_TYPES_61:
                        if _ua_eng is not None:
                            try:
                                _ac = _ua_eng.conditions
                                _obs_depth = getattr(attacker, "depth", 0.0)
                                _tgt_depth = getattr(best_target, "depth", 0.0)
                                _layer_mod = 1.0
                                # Thermocline: target below, observer above
                                if (_ac.thermocline_depth
                                        and _tgt_depth > _ac.thermocline_depth
                                        and _obs_depth <= _ac.thermocline_depth):
                                    _layer_mod *= 0.1  # ~20 dB loss
                                # Surface duct
                                if _ac.surface_duct_depth:
                                    if (_obs_depth < _ac.surface_duct_depth
                                            and _tgt_depth < _ac.surface_duct_depth):
                                        _layer_mod *= 3.0  # +10 dB gain
                                    elif (_obs_depth < _ac.surface_duct_depth
                                            and _tgt_depth > _ac.surface_duct_depth):
                                        _layer_mod *= 0.06  # +15 dB loss
                                # Convergence zones
                                _cz_ranges = _ua_eng.convergence_zone_ranges(_obs_depth)
                                _in_cz = any(
                                    abs(best_range - cz_r) < 5000
                                    for cz_r in _cz_ranges
                                )
                                if _cz_ranges and best_range > 30000 and not _in_cz:
                                    _layer_mod *= 0.05  # acoustic shadow
                                elif _in_cz:
                                    _layer_mod *= 2.0  # CZ spike
                                detection_range *= _layer_mod
                            except Exception:
                                pass

                if best_range > detection_range:
                    continue

                # Phase 41d: detection quality modulates engagement effectiveness
                detection_quality_mod = 1.0
                if _det_eng is not None and sensors:
                    best_snr = -100.0
                    for sensor in sensors:
                        if best_range > getattr(sensor, "effective_range", 0.0):
                            continue
                        try:
                            snr = _det_eng.compute_snr_visual(
                                sensor, 1.0, best_range, visibility_m=visibility_m,
                            )
                            if snr > best_snr:
                                best_snr = snr
                        except Exception:
                            pass
                    if best_snr > -100.0:
                        # SNR excess → quality mod (linear scale)
                        snr_linear = 10.0 ** (best_snr / 20.0)
                        detection_quality_mod = min(1.0, max(0.3, snr_linear / 10.0))

                # Phase 44b: EW jamming degrades radar/electronic detection
                if _ew_eng is not None and weather_independent:
                    try:
                        snr_penalty_db = _ew_eng.compute_radar_snr_penalty(
                            sensor_pos=attacker.position,
                            sensor_freq_ghz=getattr(
                                sensors[0], "frequency_ghz", 10.0,
                            ) if sensors else 10.0,
                            sensor_power_dbm=getattr(
                                sensors[0], "power_dbm", 70.0,
                            ) if sensors else 70.0,
                            sensor_gain_dbi=getattr(
                                sensors[0], "antenna_gain_dbi", 30.0,
                            ) if sensors else 30.0,
                            sensor_bw_ghz=getattr(
                                sensors[0], "bandwidth_ghz", 0.1,
                            ) if sensors else 0.1,
                            target_range_m=best_range,
                        )
                        if snr_penalty_db > 0:
                            # Phase 65c: ECCM reduces jamming effectiveness
                            if _eccm_eng is not None:
                                _eccm_suite = _eccm_eng.get_suite_for_unit(
                                    attacker.entity_id,
                                )
                                if _eccm_suite is not None and _eccm_suite.active:
                                    _eccm_reduction = _eccm_eng.compute_jam_reduction(
                                        _eccm_suite,
                                        jammer_freq_ghz=getattr(
                                            sensors[0], "frequency_ghz", 10.0,
                                        ) if sensors else 10.0,
                                        jammer_bw_ghz=getattr(
                                            sensors[0], "bandwidth_ghz", 0.1,
                                        ) if sensors else 0.1,
                                        js_ratio_db=snr_penalty_db,
                                    )
                                    snr_penalty_db = max(
                                        0.0, snr_penalty_db - _eccm_reduction,
                                    )
                            # Phase 48: jammer_coverage_mult scales EW effect
                            ew_factor = max(
                                0.1, 1.0 - (snr_penalty_db * _jammer_mult) / 40.0,
                            )
                            detection_quality_mod *= ew_factor
                    except Exception:
                        pass

                # Phase 48: stealth_detection_penalty — reduce detection
                # quality for stealth-configured targets
                if _stealth_penalty > 0:
                    target_rcs = getattr(best_target, "radar_cross_section_m2", None)
                    if target_rcs is not None and target_rcs < 1.0:
                        detection_quality_mod *= max(0.1, 1.0 - _stealth_penalty)

                # Phase 48: sigint_detection_bonus — boost detection for
                # SIGINT-capable sensors
                if _sigint_bonus > 0 and sensors:
                    for sensor in sensors:
                        if getattr(sensor, "sensor_type", None) == SensorType.ESM:
                            detection_quality_mod = min(
                                1.0, detection_quality_mod * (1.0 + _sigint_bonus),
                            )
                            break

                vis_mod = 1.0 if weather_independent else (min(visibility_m / best_range, 1.0) if best_range > 0 else 1.0)
                vis_mod = vis_mod * detection_quality_mod

                # Phase 60a: obscurant Pk reduction
                if _obs_eng is not None and _enable_obscurants:
                    try:
                        _opacity_pk = _obs_eng.opacity_at(best_target.position)
                        vis_mod *= (1.0 - _opacity_pk.visual)
                    except Exception:
                        pass

                # Phase 42a: ROE gate
                if roe_engine is not None:
                    from stochastic_warfare.c2.roe import TargetCategory
                    id_confidence = detection_quality_mod
                    authorized, _reason = roe_engine.check_engagement_authorized(
                        shooter_id=attacker.entity_id,
                        target_id=best_target.entity_id,
                        target_category=TargetCategory.MILITARY_COMBATANT,
                        id_confidence=id_confidence,
                        target_position=best_target.position,
                    )
                    if not authorized:
                        continue

                # Phase 50c: concealment engagement threshold
                if effective_concealment > _eng_conceal_thresh:
                    continue

                # Select best weapon for current range — prefer ranged weapons
                # at distance, melee weapons at close range.  Skip weapons
                # that are out of ammo or out of range.
                target_domain = best_target.domain.name
                selected_wpn = None
                selected_ammo_def = None
                selected_ammo_id = None
                best_wpn_score = -1.0
                for wpn_inst, ammo_defs in weapons:
                    if not ammo_defs:
                        continue
                    ammo_def = ammo_defs[0]
                    ammo_id = ammo_def.ammo_id
                    if not wpn_inst.can_fire(ammo_id):
                        continue
                    max_r = wpn_inst.definition.max_range_m
                    if max_r > 0 and best_range > max_r:
                        continue
                    # Phase 40d: domain filtering
                    if target_domain not in wpn_inst.definition.effective_target_domains():
                        continue
                    # Phase 40c: deployed weapons can't fire while moving
                    if attacker.speed > 0.5 and wpn_inst.definition.requires_deployed:
                        continue
                    # Phase 54f: weapon traverse arc constraint
                    # traverse_deg 0 or 360 = no constraint (platform-aimed)
                    _traverse = getattr(wpn_inst.definition, "traverse_deg", 360.0)
                    if isinstance(_traverse, (int, float)) and 0 < _traverse < 360.0:
                        _att_heading = getattr(attacker, "heading", 0.0) or 0.0
                        _tgt_bearing = math.atan2(
                            best_target.position.easting - attacker.position.easting,
                            best_target.position.northing - attacker.position.northing,
                        )
                        _bearing_diff = abs(_tgt_bearing - _att_heading)
                        if _bearing_diff > math.pi:
                            _bearing_diff = 2 * math.pi - _bearing_diff
                        if _bearing_diff > math.radians(_traverse / 2):
                            continue  # target outside weapon traverse arc
                    # Phase 54f: weapon elevation constraint — only for
                    # weapons with explicitly set (non-default) elevation arcs
                    _elev_min = getattr(wpn_inst.definition, "elevation_min_deg", -5.0)
                    _elev_max = getattr(wpn_inst.definition, "elevation_max_deg", 85.0)
                    if (
                        best_range > 0
                        and isinstance(_elev_min, (int, float))
                        and isinstance(_elev_max, (int, float))
                        and (_elev_min != -5.0 or _elev_max != 85.0)
                    ):
                        _alt_diff = (
                            getattr(best_target.position, "altitude", 0.0)
                            - getattr(attacker.position, "altitude", 0.0)
                        )
                        _elev_deg = math.degrees(math.atan2(_alt_diff, best_range))
                        if _elev_deg < _elev_min or _elev_deg > _elev_max:
                            continue  # target outside weapon elevation arc
                    # Phase 55c-2: seeker FOV constraint — guided munitions
                    # must acquire target within seeker cone.
                    # Phase 67: aircraft can turn to face targets before firing,
                    # so seeker FOV only constrains non-aerial platforms.
                    _seeker_fov = getattr(ammo_def, "seeker_fov_deg", 0.0)
                    if isinstance(_seeker_fov, (int, float)) and _seeker_fov > 0:
                        _att_domain_sk = getattr(attacker, "domain", None)
                        if _att_domain_sk != Domain.AERIAL:
                            _launch_bearing = math.atan2(
                                best_target.position.easting - attacker.position.easting,
                                best_target.position.northing - attacker.position.northing,
                            )
                            _att_heading_sk = getattr(attacker, "heading", 0.0) or 0.0
                            _seeker_diff = abs(_launch_bearing - _att_heading_sk)
                            if _seeker_diff > math.pi:
                                _seeker_diff = 2 * math.pi - _seeker_diff
                            if _seeker_diff > math.radians(_seeker_fov / 2):
                                continue  # target outside seeker acquisition cone
                    # Score: prefer weapon whose max range best fits current
                    # distance.  Ranged weapons score higher when target is
                    # far; melee weapons score higher when target is very
                    # close (ratio > 1 means "within comfortable range").
                    if max_r > 0:
                        ratio = max_r / max(best_range, 1.0)
                        # Ideal ratio is ~1.5 (target well within range)
                        score = min(ratio, 3.0)
                    else:
                        score = 0.1  # fallback for weapons with 0 range
                    if score > best_wpn_score:
                        best_wpn_score = score
                        selected_wpn = wpn_inst
                        selected_ammo_def = ammo_def
                        selected_ammo_id = ammo_id

                if selected_wpn is None:
                    continue

                # Phase 42a: hold-fire — defensive units wait for effective range
                side_rules = behavior_rules.get(side_name, {})
                if isinstance(side_rules, dict) and side_rules.get("hold_fire_until_effective_range", False):
                    best_eff_range = max(
                        (w[0].definition.get_effective_range()
                         for w in weapons if w[0].definition.max_range_m > 0),
                        default=0.0,
                    )
                    if best_eff_range > 0 and best_range > best_eff_range:
                        continue  # Hold fire — target not yet in effective range

                wpn_inst = selected_wpn
                ammo_def = selected_ammo_def
                ammo_id = selected_ammo_id

                # Phase 68b: ammo depletion gate — skip if magazine exhausted
                if _enable_ammo_gate:
                    _mag_cap = getattr(wpn_inst.definition, "magazine_capacity", 0)
                    if _mag_cap > 0:
                        _ammo_key = f"{attacker.entity_id}:{wpn_inst.definition.weapon_id}"
                        _rounds_fired = self._ammo_expended.get(_ammo_key, 0)
                        if _rounds_fired >= _mag_cap:
                            logger.debug(
                                "Ammo depleted: %s weapon %s (%d/%d)",
                                attacker.entity_id, wpn_inst.definition.weapon_id,
                                _rounds_fired, _mag_cap,
                            )
                            continue

                target_armor = getattr(best_target, "armor_front", 0.0)
                crew_count = len(best_target.personnel) if best_target.personnel else 4

                # Find side config for crew skill
                side_cfg = None
                for sc in ctx.config.sides:
                    if sc.side == side_name:
                        side_cfg = sc
                        break

                # Phase 40f: morale accuracy modifier
                morale_accuracy_mod = 1.0
                if attacker_morale is not None:
                    ms = MoraleState(int(attacker_morale)) if not isinstance(attacker_morale, MoraleState) else attacker_morale
                    effects = _MORALE_EFFECTS.get(ms, {})
                    morale_accuracy_mod = effects.get("accuracy_mult", 1.0)

                # Phase 41b: per-unit training_level modulates crew skill
                base_skill = side_cfg.experience_level if side_cfg else 0.5
                unit_training = getattr(attacker, "training_level", 0.5)
                effective_skill = base_skill * (0.5 + 0.5 * unit_training)
                # Per-side hit probability modifier (Phase 48)
                side_hit_prob = cal_flat.get(
                    f"hit_probability_modifier_{side_name}", hit_prob_mod,
                )
                # Phase 48: force_ratio_modifier — Dupuy CEV (Combat
                # Effectiveness Value).  Captures training, doctrine,
                # weapon superiority, and C2 quality as a single scalar.
                # Values >1 = more effective than raw numbers suggest.
                force_ratio_mod = cal_flat.get(
                    f"{side_name}_force_ratio_modifier", 1.0,
                )
                crew_skill = (
                    effective_skill * side_hit_prob
                    * morale_accuracy_mod * weather_pk_modifier
                    * force_ratio_mod
                )

                # Phase 52b: crosswind accuracy penalty
                if wind_e != 0.0 or wind_n != 0.0:
                    _wind_scale = _wind_accuracy_scale
                    crew_skill *= _compute_crosswind_penalty(
                        wind_e, wind_n,
                        attacker.position.easting, attacker.position.northing,
                        best_target.position.easting, best_target.position.northing,
                        _wind_scale,
                    )

                # Phase 86b: MOPP + altitude + readiness from batched modifiers
                if _obs.mopp_fatigue > 1.0:
                    crew_skill /= _obs.mopp_fatigue
                if _obs.mopp_reload_mod > 1.0:
                    crew_skill /= _obs.mopp_reload_mod
                crew_skill *= _obs.altitude_factor
                if _obs.readiness < 0.3:
                    continue  # Too degraded to engage
                crew_skill *= max(0.5, _obs.readiness)

                # Phase 59d: equipment temperature stress → weapon jam
                if _enable_equip_stress:
                    _wx59d = getattr(ctx, "weather_engine", None)
                    if _wx59d is not None:
                        _temp59d = _wx59d.current.temperature
                        _wpn_equip = getattr(wpn_inst, "equipment", None)
                        if _wpn_equip is not None:
                            from stochastic_warfare.entities.equipment import EquipmentManager
                            _stress = EquipmentManager.environment_stress(
                                _wpn_equip, _temp59d,
                            )
                            if _stress > 0:
                                _jam_rng = getattr(ctx, "rng_manager", None)
                                if _jam_rng is not None:
                                    _jam_stream = _jam_rng.get_stream(ModuleId.COMBAT)
                                    if _jam_stream.random() < min(0.5, _stress * 0.1):
                                        continue  # weapon jam from temperature stress

                # Phase 50e: compute weapon category early for fire-on-move exemption
                _early_wpn_cat = getattr(
                    wpn_inst.definition, "category", "",
                ).upper()

                # Phase 48a: fire-on-move accuracy penalty (non-deployed)
                # Phase 50e: exempt indirect fire categories (D7 fix)
                if (
                    attacker.speed > 0.5
                    and not wpn_inst.definition.requires_deployed
                    and _early_wpn_cat not in _INDIRECT_FIRE_CATEGORIES
                ):
                    _max_spd = getattr(attacker, "max_speed_mps", 20.0) or 20.0
                    _speed_frac = min(1.0, attacker.speed / max(1.0, _max_spd))
                    crew_skill *= 1.0 - _speed_frac * 0.5  # Up to 50% penalty

                # Phase 48: sam_suppression_modifier — SEAD degrades AD
                # unit effectiveness (SAM crews forced to shut down radar)
                if _sam_supp > 0:
                    _wpn_cat = getattr(wpn_inst.definition, "category", "").upper()
                    if _wpn_cat in ("SAM", "AAA", "MISSILE_LAUNCHER"):
                        att_type = getattr(attacker, "unit_type_id", "")
                        if any(k in att_type.lower() for k in ("sa-", "sam", "s-300", "buk", "patriot")):
                            crew_skill *= max(0.1, 1.0 - _sam_supp)

                # Per-side target_size_modifier: use target's side
                target_side = self._find_unit_side(ctx, best_target.entity_id)
                target_size_mod = cal_flat.get(
                    f"target_size_modifier_{target_side}",
                    target_size_mod_default,
                )

                # Phase 44a: Sea state degrades naval target accuracy
                if best_target.domain in (Domain.NAVAL, Domain.SUBMARINE):
                    target_size_mod /= sea_dispersion_modifier

                # Phase 61a: wave period resonance + swell direction → gunnery
                if _enable_sea_state_ops:
                    if (attacker.domain in (Domain.NAVAL, Domain.SUBMARINE)
                            or best_target.domain in (Domain.NAVAL, Domain.SUBMARINE)):
                        # Wave period resonance: hull natural period ~8–12s
                        _hull_period = 10.0  # typical destroyer
                        _disp_a = getattr(attacker, "displacement_tons", 0)
                        if _disp_a and _disp_a > 10000:
                            _hull_period = 12.0  # larger ships
                        if _sea_wave_period > 0 and abs(_sea_wave_period - _hull_period) < 0.1 * _hull_period:
                            crew_skill *= max(0.3, 1.0 / 1.5)  # resonance penalty
                        # Swell direction: beam seas = max roll
                        _att_heading = 0.0
                        _dx_sw = best_target.position.easting - attacker.position.easting
                        _dy_sw = best_target.position.northing - attacker.position.northing
                        _dist_sw = math.sqrt(_dx_sw * _dx_sw + _dy_sw * _dy_sw)
                        if _dist_sw > 0:
                            _att_heading = math.atan2(_dx_sw, _dy_sw)
                        _roll_factor = math.sin(_sea_wave_dir - _att_heading) ** 2
                        crew_skill *= max(0.5, 1.0 - _roll_factor * 0.5)

                # Current time for fire rate limiting
                current_time_s = ctx.clock.elapsed.total_seconds()

                # Phase 44b: GPS accuracy affects guided weapon Pk
                gps_cep_factor = 1.0
                if _space_eng is not None:
                    gps_eng = getattr(_space_eng, "gps_engine", None)
                    if gps_eng is not None:
                        try:
                            guidance = getattr(
                                ammo_def, "guidance_type", "none",
                            )
                            if guidance in ("gps", "gps_ins"):
                                gps_state = gps_eng.compute_gps_accuracy(
                                    side_name,
                                    current_time_s,
                                )
                                gps_cep_factor = gps_eng.compute_cep_factor(
                                    gps_state.position_accuracy_m,
                                    guidance,
                                )
                        except Exception:
                            pass
                # Apply GPS degradation
                if gps_cep_factor > 1.0:
                    crew_skill /= gps_cep_factor

                # Phase 66a: human shield — reduce crew_skill when civilian
                # population near target (proxy for ROE constraint)
                _civ_density_66 = 0.0
                if _enable_unconventional and _uw_eng is not None:
                    if _pop_eng is not None:
                        _tgt_pos_66 = getattr(best_target, "position", None)
                        if _tgt_pos_66 is not None:
                            _civ_density_66 = getattr(
                                _pop_eng, "get_density_at", lambda p: 0.0,
                            )(_tgt_pos_66)
                    if _civ_density_66 > 0:
                        _shield_val = _uw_eng.evaluate_human_shield(
                            best_target.position, _civ_density_66,
                        )
                        _pk_red = cal_flat.get("human_shield_pk_reduction", 0.5) * _shield_val
                        crew_skill *= max(0.1, 1.0 - _pk_red)

                # Phase 68b: track ammo expenditure for this engagement
                if _enable_ammo_gate:
                    _mag_cap_trk = getattr(wpn_inst.definition, "magazine_capacity", 0)
                    if _mag_cap_trk > 0:
                        _ammo_key_trk = f"{attacker.entity_id}:{wpn_inst.definition.weapon_id}"
                        self._ammo_expended[_ammo_key_trk] = self._ammo_expended.get(_ammo_key_trk, 0) + 1

                # ── Phase 43: domain-specific engagement routing ──────
                routed_aggregate = False
                wpn_cat_str = getattr(
                    wpn_inst.definition, "category", "",
                ).upper()
                dest_thresh = _dest_thresh
                dis_thresh = _dis_thresh

                # Phase 43c: naval domain routing (all eras, highest priority)
                if (
                    not routed_aggregate
                    and (attacker.domain in (Domain.NAVAL, Domain.SUBMARINE)
                         or best_target.domain in (Domain.NAVAL, Domain.SUBMARINE))
                ):
                    handled, naval_status = _route_naval_engagement(
                        ctx, attacker, best_target, wpn_inst,
                        best_range, dt, timestamp,
                        naval_config=self._config.naval_config,
                        force_ratio_mod=force_ratio_mod,
                        vls_launches=self._vls_launches,
                    )
                    if handled:
                        if naval_status is not None:
                            pending_damage.append((best_target, naval_status))
                        side_engagements += 1
                        routed_aggregate = True

                # Phase 58b: air domain routing (opt-in via enable_air_routing)
                if (
                    not routed_aggregate
                    and _enable_air_routing
                    and (attacker.domain == Domain.AERIAL
                         or best_target.domain == Domain.AERIAL)
                    and _air_combat_eng is not None
                ):
                    handled, air_status = _route_air_engagement(
                        ctx, attacker, best_target, wpn_inst,
                        best_range, dt, timestamp,
                        force_ratio_mod=force_ratio_mod,
                    )
                    if handled:
                        if air_status is not None:
                            pending_damage.append((best_target, air_status))
                        side_engagements += 1
                        routed_aggregate = True
                        # Phase 69a: record sortie consumption
                        _ato_69a = getattr(ctx, "ato_engine", None)
                        if _ato_69a is not None:
                            _sim_time_69a = ctx.clock.elapsed.total_seconds() if hasattr(ctx.clock, "elapsed") else 0.0
                            _ato_69a.record_sortie(attacker.entity_id, _sim_time_69a)

                # Phase 43a: era-aware aggregate model routing
                # Phase 47: aggregate effectiveness modifier — terrain cover
                # reduces effective casualties, elevation advantage boosts them,
                # and crew_skill (morale × training × weather × CBRN × readiness)
                # scales aggregate lethality the same way it scales direct-fire Pk.
                _terrain_cas_mult = max(0.1, (1.0 - terrain_cover) * elevation_mod)
                _agg_skill = min(1.0, max(0.1, crew_skill))
                _agg_modifier = _terrain_cas_mult * _agg_skill

                if not routed_aggregate:
                    era = getattr(ctx.config, "era", "modern")

                    if era == "napoleonic":
                        if wpn_cat_str in ("RIFLE", "CANNON", "ARTILLERY") and best_range > _MELEE_RANGE_M:
                            vf = getattr(ctx, "volley_fire_engine", None)
                            if vf is not None:
                                n_muskets = max(1, len(attacker.personnel))
                                formation_frac = _get_formation_firepower(ctx, attacker)
                                is_rifle = "rifle" in wpn_inst.definition.weapon_id.lower()
                                vr = vf.fire_volley(
                                    n_muskets=n_muskets,
                                    range_m=best_range,
                                    is_rifle=is_rifle,
                                    formation_firepower_fraction=formation_frac,
                                )
                                _apply_aggregate_casualties(
                                    int(vr.casualties * _agg_modifier),
                                    best_target, pending_damage,
                                    dest_thresh, dis_thresh,
                                    self._cumulative_casualties,
                                )
                                side_engagements += 1
                                routed_aggregate = True
                                # Suppression from volley fire
                                _apply_aggregate_suppression(
                                    ctx, best_target, wpn_inst,
                                    best_range, dt, self._suppression_states,
                                )
                        if not routed_aggregate and (
                            wpn_cat_str == "MELEE" or best_range <= _MELEE_RANGE_M
                        ):
                            # Phase 54c: cavalry charge state machine
                            cavalry_eng = getattr(ctx, "cavalry_engine", None)
                            unit_type_lower = getattr(
                                attacker, "unit_type", "",
                            ).lower()
                            is_cavalry = any(
                                kw in unit_type_lower for kw in
                                ("cavalry", "hussar", "dragoon",
                                 "lancer", "cuirassier")
                            )
                            if (
                                cavalry_eng is not None
                                and is_cavalry
                            ):
                                charge_id = (
                                    f"{attacker.entity_id}"
                                    f"_vs_{best_target.entity_id}"
                                )
                                try:
                                    charges = getattr(
                                        cavalry_eng, "_charges", {},
                                    )
                                    if charge_id not in charges:
                                        cavalry_eng.initiate_charge(
                                            charge_id,
                                            attacker.entity_id,
                                            best_target.entity_id,
                                            distance_m=best_range,
                                        )
                                    phase = cavalry_eng.update_charge(
                                        charge_id, dt,
                                    )
                                    logger.debug(
                                        "Cavalry charge %s phase: %s",
                                        charge_id, phase,
                                    )
                                    routed_aggregate = True
                                    side_engagements += 1
                                except Exception:
                                    logger.debug(
                                        "Cavalry charge failed for %s",
                                        charge_id, exc_info=True,
                                    )

                            if not routed_aggregate:
                                me = getattr(ctx, "melee_engine", None)
                                if me is not None:
                                    mr = me.resolve_melee_round(
                                        attacker_strength=max(1, len(attacker.personnel)),
                                        defender_strength=max(1, len(best_target.personnel)),
                                        melee_type=_infer_melee_type(attacker, wpn_inst),
                                    )
                                    _apply_melee_result(
                                        mr, attacker, best_target, pending_damage,
                                        ctx.morale_states, dest_thresh, dis_thresh,
                                    )
                                    side_engagements += 1
                                    routed_aggregate = True

                    elif era == "ancient_medieval":
                        # Phase 54d: ancient formation modifiers
                        af_eng = getattr(ctx, "formation_ancient_engine", None)
                        if wpn_cat_str == "RIFLE" and best_range > _MELEE_RANGE_M:
                            ae = getattr(ctx, "archery_engine", None)
                            if ae is not None:
                                n_archers = max(1, len(attacker.personnel))
                                ar = ae.fire_volley(
                                    unit_id=attacker.entity_id,
                                    n_archers=n_archers,
                                    range_m=best_range,
                                    missile_type=_infer_missile_type(wpn_inst),
                                )
                                # Phase 54d: archery vulnerability from formation
                                arch_vuln = 1.0
                                if af_eng is not None:
                                    try:
                                        arch_vuln = af_eng.archery_vulnerability(
                                            best_target.entity_id,
                                        )
                                    except Exception:
                                        pass
                                _apply_aggregate_casualties(
                                    int(ar.casualties * _agg_modifier * arch_vuln),
                                    best_target, pending_damage,
                                    dest_thresh, dis_thresh,
                                    self._cumulative_casualties,
                                )
                                side_engagements += 1
                                routed_aggregate = True
                                _apply_aggregate_suppression(
                                    ctx, best_target, wpn_inst,
                                    best_range, dt, self._suppression_states,
                                )
                        if not routed_aggregate and (
                            wpn_cat_str == "MELEE" or best_range <= _MELEE_RANGE_M
                        ):
                            me = getattr(ctx, "melee_engine", None)
                            if me is not None:
                                # Phase 54d: formation melee/defense modifiers
                                melee_power_mod = 1.0
                                defense_mod_val = 1.0
                                if af_eng is not None:
                                    try:
                                        melee_power_mod = af_eng.melee_power(
                                            attacker.entity_id,
                                        )
                                    except Exception:
                                        pass
                                    try:
                                        defense_mod_val = af_eng.defense_mod(
                                            best_target.entity_id,
                                        )
                                    except Exception:
                                        pass
                                mr = me.resolve_melee_round(
                                    attacker_strength=int(
                                        max(1, len(attacker.personnel))
                                        * melee_power_mod
                                    ),
                                    defender_strength=int(
                                        max(1, len(best_target.personnel))
                                        * defense_mod_val
                                    ),
                                    melee_type=_infer_melee_type(attacker, wpn_inst),
                                )
                                _apply_melee_result(
                                    mr, attacker, best_target, pending_damage,
                                    ctx.morale_states, dest_thresh, dis_thresh,
                                )
                                side_engagements += 1
                                routed_aggregate = True

                    elif era == "ww1":
                        # Phase 55c-1: gas warfare protection modifier
                        # If ammo is gas-related, defender's gas mask reduces casualties
                        _gas_cas_mod = 1.0
                        _ammo_id_lower = (ammo_def.ammo_id if ammo_def else "").lower()
                        if _gas_protection > 0 and any(
                            kw in _ammo_id_lower for kw in ("gas", "chlorine", "phosgene", "mustard")
                        ):
                            _gas_floor = cal_flat.get("gas_casualty_floor", 0.1)
                            _gas_scale = cal_flat.get("gas_protection_scaling", 0.8)
                            _gas_cas_mod = max(_gas_floor, 1.0 - _gas_protection * _gas_scale)

                        # Phase 54b: barrage zone suppression on defender
                        barrage_eng = getattr(ctx, "barrage_engine", None)
                        if barrage_eng is not None and best_target is not None:
                            try:
                                bz = barrage_eng.get_barrage_zone_at(
                                    best_target.position.easting,
                                    best_target.position.northing,
                                )
                                if bz is not None:
                                    b_effects = barrage_eng.compute_effects(
                                        best_target.position.easting,
                                        best_target.position.northing,
                                        in_dugout=(
                                            getattr(best_target, "posture", None)
                                            is not None
                                            and int(getattr(best_target, "posture", 0)) >= 3
                                        ),
                                    )
                                    b_supp = b_effects.get("suppression_p", 0.0)
                                    if b_supp > 0:
                                        logger.debug(
                                            "Barrage suppression on %s: %.2f",
                                            best_target.entity_id, b_supp,
                                        )
                            except Exception:
                                pass

                        if wpn_cat_str in ("RIFLE", "MACHINE_GUN", "LIGHT_MG", "CANNON"):
                            vf = getattr(ctx, "volley_fire_engine", None)
                            if vf is not None:
                                n_rifles = max(1, len(attacker.personnel))
                                vr = vf.fire_volley(
                                    n_muskets=n_rifles,
                                    range_m=best_range,
                                    is_rifle=True,
                                    formation_firepower_fraction=1.0,
                                )
                                _apply_aggregate_casualties(
                                    int(vr.casualties * _agg_modifier * _gas_cas_mod),
                                    best_target, pending_damage,
                                    dest_thresh, dis_thresh,
                                    self._cumulative_casualties,
                                )
                                side_engagements += 1
                                routed_aggregate = True
                                _apply_aggregate_suppression(
                                    ctx, best_target, wpn_inst,
                                    best_range, dt, self._suppression_states,
                                )
                        if not routed_aggregate and (
                            wpn_cat_str == "MELEE" or best_range <= _MELEE_RANGE_M
                        ):
                            me = getattr(ctx, "melee_engine", None)
                            if me is not None:
                                mr = me.resolve_melee_round(
                                    attacker_strength=max(1, len(attacker.personnel)),
                                    defender_strength=max(1, len(best_target.personnel)),
                                    melee_type=_infer_melee_type(attacker, wpn_inst),
                                )
                                _apply_melee_result(
                                    mr, attacker, best_target, pending_damage,
                                    ctx.morale_states, dest_thresh, dis_thresh,
                                )
                                side_engagements += 1
                                routed_aggregate = True
                    # era == "modern" or "ww2" → no aggregate routing

                # Phase 43b: indirect fire routing (all eras)
                if not routed_aggregate and wpn_cat_str in _INDIRECT_FIRE_CATEGORIES:
                    ife = getattr(ctx, "indirect_fire_engine", None)
                    if ife is not None:
                        min_range = getattr(wpn_inst.definition, "min_range_m", 0.0)
                        if best_range >= min_range:
                            from stochastic_warfare.combat.indirect_fire import (
                                FireMissionType,
                            )
                            round_count = max(
                                1,
                                int(wpn_inst.definition.rate_of_fire_rpm * dt / 60),
                            )
                            fm_result = ife.fire_mission(
                                battery_id=attacker.entity_id,
                                fire_pos=attacker.position,
                                target_pos=best_target.position,
                                weapon=wpn_inst.definition,
                                ammo=ammo_def,
                                mission_type=FireMissionType.FIRE_FOR_EFFECT,
                                round_count=round_count,
                                timestamp=timestamp,
                            )
                            if fm_result.impacts:
                                _ifire_radius = getattr(
                                    ammo_def, "blast_radius_m", 0.0,
                                ) or 50.0
                                _apply_indirect_fire_result(
                                    fm_result, best_target, pending_damage,
                                    dest_thresh, dis_thresh,
                                    self._cumulative_casualties,
                                    _agg_modifier,
                                    lethal_radius_m=_ifire_radius,
                                )
                                # Phase 60a: artillery impact dust
                                if _obs_eng is not None and _enable_obscurants:
                                    try:
                                        _blast_r = getattr(ammo_def, "blast_radius_m", 20.0) or 20.0
                                        _obs_eng.add_dust(best_target.position, radius=_blast_r)
                                    except Exception:
                                        pass
                            side_engagements += 1
                            routed_aggregate = True
                            _apply_aggregate_suppression(
                                ctx, best_target, wpn_inst,
                                best_range, dt, self._suppression_states,
                            )

                # ── Standard direct-fire path (modern, WW2, fallback) ─────
                if not routed_aggregate:
                    # Determine engagement type — DEW weapons route through
                    # Beer-Lambert / HPM models instead of ballistic physics
                    engagement_type = EngagementType.DIRECT_FIRE
                    try:
                        if wpn_inst.definition.parsed_category() == WeaponCategory.DIRECTED_ENERGY:
                            if wpn_inst.definition.beam_power_kw > 0:
                                engagement_type = EngagementType.DEW_LASER
                            else:
                                engagement_type = EngagementType.DEW_HPM
                    except (KeyError, ValueError):
                        pass

                    # Phase 63d: MISSILE type inference for guided missile launchers
                    if engagement_type == EngagementType.DIRECT_FIRE and _enable_missile_routing:
                        try:
                            if wpn_inst.definition.parsed_category() == WeaponCategory.MISSILE_LAUNCHER:
                                from stochastic_warfare.combat.ammunition import GuidanceType
                                _g = ammo_def.parsed_guidance()
                                if _g != GuidanceType.NONE:
                                    engagement_type = EngagementType.MISSILE
                        except (KeyError, ValueError, AttributeError):
                            pass

                    # Phase 54f: terminal maneuver hit probability bonus
                    if getattr(ammo_def, "terminal_maneuver", False) is True:
                        crew_skill *= 1.05

                    # Phase 40b: extract target posture
                    target_posture_val = getattr(best_target, "posture", None)
                    target_posture_str = target_posture_val.name if target_posture_val is not None else "MOVING"

                    # Phase 61c: extract humidity/precipitation for DEW
                    _dew_humidity = 0.5
                    _dew_precip = 0.0
                    if _enable_em_prop:
                        if _weather_eng is not None:
                            try:
                                _wc = _weather_eng.current
                                _dew_humidity = getattr(_wc, "humidity", 0.5)
                                _dew_precip = getattr(_wc, "precipitation_rate", 0.0)
                            except Exception:
                                pass

                    result = ctx.engagement_engine.route_engagement(
                        engagement_type=engagement_type,
                        attacker_id=attacker.entity_id,
                        target_id=best_target.entity_id,
                        attacker_pos=attacker.position,
                        target_pos=best_target.position,
                        weapon=wpn_inst,
                        ammo_id=ammo_id,
                        ammo_def=ammo_def,
                        missile_engine=getattr(ctx, 'missile_engine', None),
                        dew_engine=getattr(ctx, 'dew_engine', None),
                        crew_skill=crew_skill,
                        target_size_m2=8.5 * target_size_mod,
                        target_armor_mm=target_armor,
                        shooter_speed_mps=attacker.speed,
                        target_posture=target_posture_str,
                        visibility=vis_mod,
                        timestamp=timestamp,
                        current_time_s=current_time_s,
                        terrain_cover=terrain_cover,
                        elevation_mod=elevation_mod,
                        humidity=_dew_humidity,
                        precipitation_rate=_dew_precip,
                    )

                    # Phase 40e: apply fire volume to target suppression
                    if result.engaged:
                        side_engagements += 1
                        if _sup_eng is not None:
                            tid = best_target.entity_id
                            if tid not in self._suppression_states:
                                self._suppression_states[tid] = UnitSuppressionState()
                            _sup_eng.apply_fire_volume(
                                state=self._suppression_states[tid],
                                rounds_per_minute=wpn_inst.definition.rate_of_fire_rpm,
                                caliber_mm=wpn_inst.definition.caliber_mm,
                                range_m=best_range,
                                duration_s=dt,
                            )

                    if result.engaged and result.hit_result and result.hit_result.hit:
                        if engagement_type in (EngagementType.DEW_LASER, EngagementType.DEW_HPM):
                            # Phase 51c: DEW disable path — threshold-based
                            dew_pk = result.hit_result.p_hit if hasattr(result.hit_result, "p_hit") else 0.5
                            dew_thresh = _dew_disable_thresh
                            if dew_pk >= dew_thresh:
                                pending_damage.append((best_target, UnitStatus.DESTROYED))
                            else:
                                pending_damage.append((best_target, UnitStatus.DISABLED))
                        elif (result.damage_result
                                and result.damage_result.damage_fraction > 0):
                            if result.damage_result.damage_fraction >= dest_thresh:
                                pending_damage.append((best_target, UnitStatus.DESTROYED))
                            elif result.damage_result.damage_fraction >= dis_thresh:
                                pending_damage.append((best_target, UnitStatus.DISABLED))

                            # Phase 58c: extract damage detail (logged;
                            # behavioral application deferred to calibration)
                            _dmg = result.damage_result
                            if _dmg.casualties:
                                logger.debug(
                                    "%d casualties on %s",
                                    len(_dmg.casualties), best_target.entity_id,
                                )
                            if _dmg.systems_damaged:
                                logger.debug(
                                    "%d systems_damaged on %s",
                                    len(_dmg.systems_damaged), best_target.entity_id,
                                )
                            if _dmg.fire_started:
                                logger.debug(
                                    "Fire started at %s from hit on %s",
                                    best_target.position, best_target.entity_id,
                                )
                                # Phase 60b: create fire zone on combustible terrain
                                if _enable_fire_zones:
                                    _classif = getattr(ctx, "classification", None)
                                    if _inc_eng is not None:
                                        try:
                                            _combustibility = 0.5
                                            if _classif is not None:
                                                _tp = _classif.properties_at(best_target.position)
                                                _combustibility = _tp.combustibility
                                            if _combustibility > 0.3:
                                                _ws, _wd = 0.0, 0.0
                                                if _weather_eng is not None:
                                                    _ws = _weather_eng.current.wind.speed
                                                    _wd = _weather_eng.current.wind.direction
                                                _inc_eng.create_fire_zone(
                                                    position=best_target.position,
                                                    radius_m=20.0 * _combustibility,
                                                    fuel_load=_combustibility,
                                                    wind_speed_mps=_ws,
                                                    wind_dir_rad=_wd,
                                                    duration_s=1800.0 * _combustibility,
                                                    timestamp=ctx.clock.elapsed.total_seconds(),
                                                )
                                                # Cross-engine: fire produces smoke
                                                if _obs_eng is not None:
                                                    _obs_eng.deploy_smoke(
                                                        best_target.position,
                                                        radius=_inc_eng._config.smoke_obscurant_radius_m,
                                                    )
                                        except Exception:
                                            logger.debug("Fire zone creation failed", exc_info=True)

        # Phase 66a/68g: guerrilla disengage + retreat movement
        if _enable_unconventional:
            if _uw_eng is not None:
                _retreat_dist = cal_flat.get("retreat_distance_m", 2000.0)
                for _guer_side, _su_guer in units_by_side.items():
                    _guer_enemies = active_enemies.get(_guer_side, [])
                    for _u_guer in _su_guer:
                        if _u_guer.status != UnitStatus.ACTIVE:
                            continue
                        _att_type_guer = getattr(_u_guer, "unit_type", "").lower()
                        if not any(kw in _att_type_guer for kw in ("insurgent", "militia", "guerrilla")):
                            continue
                        # Compute casualty fraction from cumulative tracking
                        _cas_key = _u_guer.entity_id
                        _total_pers = len(_u_guer.personnel) if _u_guer.personnel else 4
                        _cum = self._cumulative_casualties.get(_cas_key, 0)
                        _cas_frac = _cum / max(1, _total_pers + _cum)
                        # Override engine threshold with calibration value
                        _guer_thresh = cal_flat.get("guerrilla_disengage_threshold", 0.3)
                        _uw_eng._cfg_guer.disengage_threshold = _guer_thresh
                        _in_pop = False
                        if _pop_eng is not None:
                            _gp = getattr(_u_guer, "position", None)
                            if _gp is not None:
                                _gd = getattr(_pop_eng, "get_density_at", lambda p: 0.0)(_gp)
                                _in_pop = _gd > 0
                        _disengage, _blend = _uw_eng.evaluate_guerrilla_disengage(
                            _u_guer.entity_id, _cas_frac, _in_pop,
                        )
                        if _disengage:
                            logger.debug(
                                "Guerrilla %s disengaging (blend=%.2f)",
                                _u_guer.entity_id, _blend,
                            )
                            # Phase 68g: move unit away from nearest enemy
                            _gp = getattr(_u_guer, "position", None)
                            if _gp is not None and _guer_enemies:
                                # Find nearest enemy direction
                                _ne_dist = float("inf")
                                _ne_dx, _ne_dy = 0.0, 0.0
                                for _ge in _guer_enemies:
                                    _gdx = _ge.position.easting - _gp.easting
                                    _gdy = _ge.position.northing - _gp.northing
                                    _gd2 = _gdx * _gdx + _gdy * _gdy
                                    if _gd2 < _ne_dist:
                                        _ne_dist = _gd2
                                        _ne_dx, _ne_dy = _gdx, _gdy
                                _ne_dist_m = math.sqrt(_ne_dist) if _ne_dist > 0 else 1.0
                                # Retreat vector: opposite of enemy direction
                                _rx = -_ne_dx / _ne_dist_m * _retreat_dist
                                _ry = -_ne_dy / _ne_dist_m * _retreat_dist
                                _new_pos = Position(
                                    _gp.easting + _rx,
                                    _gp.northing + _ry,
                                    _gp.altitude,
                                )
                                object.__setattr__(_u_guer, "position", _new_pos)
                                logger.debug(
                                    "Guerrilla %s retreated %.0fm to (%s)",
                                    _u_guer.entity_id, _retreat_dist, _new_pos,
                                )
                            # Blend probability → set ROUTING status
                            if _blend > 0:
                                _rng_guer = getattr(ctx, "rng_manager", None)
                                if _rng_guer is not None:
                                    _guer_stream = _rng_guer.get_stream(ModuleId.COMBAT)
                                    if _guer_stream.random() < _blend:
                                        object.__setattr__(_u_guer, "status", UnitStatus.ROUTING)
                                        logger.debug("Guerrilla %s routing", _u_guer.entity_id)

        return pending_damage

    @staticmethod
    def _apply_deferred_damage(
        pending_damage: list[tuple[Unit, UnitStatus]],
        event_bus: Any | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Apply deferred damage — worst outcome wins per unit."""
        applied: dict[str, UnitStatus] = {}
        for target, new_status in pending_damage:
            prev = applied.get(target.entity_id)
            if prev is None or new_status.value > prev.value:
                applied[target.entity_id] = new_status

        ts = timestamp or datetime.min
        for target, new_status in pending_damage:
            if applied.get(target.entity_id) == new_status:
                object.__setattr__(target, "status", new_status)
                applied.pop(target.entity_id, None)
                if event_bus is not None:
                    if new_status == UnitStatus.DESTROYED:
                        event_bus.publish(UnitDestroyedEvent(
                            timestamp=ts,
                            source=ModuleId.COMBAT,
                            unit_id=target.entity_id,
                            cause="combat_damage",
                            side=target.side,
                        ))
                    elif new_status == UnitStatus.DISABLED:
                        event_bus.publish(UnitDisabledEvent(
                            timestamp=ts,
                            source=ModuleId.COMBAT,
                            unit_id=target.entity_id,
                            cause="combat_damage",
                            side=target.side,
                        ))

    def _execute_morale(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        active_enemies: dict[str, list[Unit]],
        timestamp: datetime,
        _lod_full_update: set[str] | None = None,
    ) -> None:
        """Run morale checks for all active/routing units."""
        if ctx.morale_machine is None:
            return

        cal_flat = _resolve_cal_flat(ctx)
        morale_degrade_mod = cal_flat.get("morale_degrade_rate_modifier", 1.0)
        rout_engine = getattr(ctx, "rout_engine", None)

        # Phase 56a: build per-side STRtree for rally + cascade (O(n log n))
        _side_trees: dict[str, tuple[STRtree, list[Unit]]] = {}
        if rout_engine is not None:
            for _sn, _su in units_by_side.items():
                _eligible = [
                    u for u in _su
                    if u.status in (UnitStatus.ACTIVE, UnitStatus.ROUTING)
                ]
                if _eligible:
                    _pts = [
                        Point(u.position.easting, u.position.northing)
                        for u in _eligible
                    ]
                    _side_trees[_sn] = (STRtree(_pts), _eligible)

        # Phase 42c / 56a: rally check for routing units (STRtree)
        if rout_engine is not None:
            _rally_r = rout_engine._config.cascade_radius_m
            for side_name, side_units in units_by_side.items():
                tree_data = _side_trees.get(side_name)
                for u in side_units:
                    if u.status != UnitStatus.ROUTING:
                        continue
                    ms = ctx.morale_states.get(u.entity_id)
                    if ms is None or int(ms) != MoraleState.ROUTED:
                        continue
                    nearby_count = 0
                    leader_present = False
                    if tree_data is not None:
                        tree, eligible = tree_data
                        query_geom = Point(
                            u.position.easting, u.position.northing,
                        ).buffer(_rally_r)
                        idxs = tree.query(query_geom)
                        for idx in idxs:
                            other = eligible[idx]
                            if other.entity_id == u.entity_id:
                                continue
                            if other.status != UnitStatus.ACTIVE:
                                continue
                            dx = other.position.easting - u.position.easting
                            dy = other.position.northing - u.position.northing
                            if math.sqrt(dx * dx + dy * dy) < _rally_r:
                                nearby_count += 1
                                st = getattr(other, "support_type", None)
                                if st is not None:
                                    st_name = st.name if hasattr(st, "name") else str(st)
                                    if st_name == "HQ":
                                        leader_present = True
                    if rout_engine.check_rally(u.entity_id, nearby_count, leader_present):
                        ctx.morale_states[u.entity_id] = MoraleState.SHAKEN
                        object.__setattr__(u, "status", UnitStatus.ACTIVE)

        for side_name, side_units in units_by_side.items():
            total = len(side_units)
            destroyed = sum(
                1 for u in side_units
                if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
            )
            casualty_rate = destroyed / total if total > 0 else 0.0

            enemies = active_enemies.get(side_name, [])
            active_own = sum(1 for u in side_units if u.status == UnitStatus.ACTIVE)
            active_enemy = len(enemies)
            force_ratio = active_own / active_enemy if active_enemy > 0 else 10.0

            cohesion = cal_flat.get(f"{side_name}_cohesion", 0.7)

            for u in side_units:
                if u.status not in (UnitStatus.ACTIVE, UnitStatus.ROUTING):
                    continue

                # Phase 85: LOD skip for morale degradation (ROUTING
                # units always checked so rally works regardless of tier)
                if (
                    _lod_full_update is not None
                    and u.status == UnitStatus.ACTIVE
                    and u.entity_id not in _lod_full_update
                ):
                    continue

                # Phase 40e: use actual suppression level
                sup_state = self._suppression_states.get(u.entity_id)
                suppression_level = sup_state.value if sup_state is not None else 0.0

                new_morale = ctx.morale_machine.check_transition(
                    unit_id=u.entity_id,
                    casualty_rate=casualty_rate * morale_degrade_mod,
                    suppression_level=suppression_level,
                    leadership_present=True,
                    cohesion=cohesion,
                    force_ratio=force_ratio,
                    timestamp=timestamp,
                )
                ctx.morale_states[u.entity_id] = new_morale

                if new_morale == MoraleState.ROUTED:
                    object.__setattr__(u, "status", UnitStatus.ROUTING)
                elif new_morale == MoraleState.SURRENDERED:
                    object.__setattr__(u, "status", UnitStatus.SURRENDERED)

        # Phase 42c / 56a: rout cascade — STRtree spatial query
        if rout_engine is not None:
            _cascade_r = rout_engine._config.cascade_radius_m
            newly_routed: list[tuple[str, Unit]] = []
            for side_name, side_units in units_by_side.items():
                for u in side_units:
                    if u.status == UnitStatus.ROUTING:
                        ms = ctx.morale_states.get(u.entity_id)
                        if ms is not None and int(ms) == MoraleState.ROUTED:
                            newly_routed.append((side_name, u))

            for side_name, routing_unit in newly_routed:
                same_side = units_by_side.get(side_name, [])
                adjacent_morale: dict[str, int] = {}
                distances: dict[str, float] = {}
                tree_data = _side_trees.get(side_name)
                if tree_data is not None:
                    tree, eligible = tree_data
                    query_geom = Point(
                        routing_unit.position.easting,
                        routing_unit.position.northing,
                    ).buffer(_cascade_r)
                    idxs = tree.query(query_geom)
                    for idx in idxs:
                        other = eligible[idx]
                        if other.entity_id == routing_unit.entity_id:
                            continue
                        if other.status not in (UnitStatus.ACTIVE, UnitStatus.ROUTING):
                            continue
                        dx = other.position.easting - routing_unit.position.easting
                        dy = other.position.northing - routing_unit.position.northing
                        dist = math.sqrt(dx * dx + dy * dy)
                        distances[other.entity_id] = dist
                        ms = ctx.morale_states.get(other.entity_id)
                        if ms is not None:
                            adjacent_morale[other.entity_id] = int(ms)

                cascaded_ids = rout_engine.rout_cascade(
                    routing_unit_id=routing_unit.entity_id,
                    adjacent_unit_morale_states=adjacent_morale,
                    distances_m=distances,
                )
                for cid in cascaded_ids:
                    ctx.morale_states[cid] = MoraleState.ROUTED
                    for u in same_side:
                        if u.entity_id == cid:
                            object.__setattr__(u, "status", UnitStatus.ROUTING)
                            break

    def _execute_supply_consumption(
        self,
        ctx: Any,
        units_by_side: dict[str, list[Unit]],
        dt: float,
        _lod_full_update: set[str] | None = None,
    ) -> None:
        """Consume supplies for active units during combat."""
        dt_hours = dt / 3600.0
        for side_units in units_by_side.values():
            for u in side_units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                if _lod_full_update is not None and u.entity_id not in _lod_full_update:
                    continue  # Phase 85: LOD skip
                personnel = len(u.personnel) if u.personnel else 4
                equipment = len(u.equipment) if u.equipment else 1
                try:
                    result = ctx.consumption_engine.compute_consumption(
                        personnel_count=personnel,
                        equipment_count=equipment,
                        base_fuel_rate_per_hour=10.0,
                        activity=3,  # COMBAT
                        dt_hours=dt_hours,
                    )
                except Exception:
                    pass  # Non-critical — don't halt battle over supply math

    @staticmethod
    def _find_unit_side(ctx: Any, unit_id: str) -> str:
        """Find which side a unit belongs to."""
        for side, units in ctx.units_by_side.items():
            if any(u.entity_id == unit_id for u in units):
                return side
        return ""

    @staticmethod
    def _compute_c2_effectiveness(ctx: Any, unit_id: str, side: str) -> float:
        """Compute C2 effectiveness from comms state. Returns 1.0 if unavailable."""
        comms = getattr(ctx, "comms_engine", None)
        if comms is None:
            return 1.0
        if not hasattr(comms, "compute_c2_effectiveness"):
            return 1.0
        # Build position dict for the unit's side
        positions: dict[str, Position] = {}
        for u in ctx.active_units(side):
            if u.position is not None:
                positions[u.entity_id] = u.position
        if not positions:
            return 1.0
        cal_flat = _resolve_cal_flat(ctx)
        min_eff = cal_flat.get("c2_min_effectiveness", 0.3)
        try:
            eff = comms.compute_c2_effectiveness(
                unit_id, positions, min_effectiveness=min_eff,
            )
        except Exception:
            eff = 1.0
        # Phase 62b: MOPP comms degradation
        if cal_flat.get("enable_human_factors", False):
            _cbrn_c2 = getattr(ctx, "cbrn_engine", None)
            if _cbrn_c2 is not None:
                _ml_c2 = getattr(_cbrn_c2, "_mopp_levels", {}).get(unit_id, 0)
                if _ml_c2 > 0:
                    _cf = cal_flat.get("mopp_comms_factor_4", 0.5)
                    _sc = _ml_c2 / 4.0
                    _comms_mod = 1.0 - _sc * (1.0 - _cf)
                    eff *= _comms_mod
        return eff

    @staticmethod
    def _get_unit_morale_level(ctx: Any, unit_id: str) -> float:
        """Derive morale level [0, 1] from morale state.

        STEADY=1.0, SHAKEN=0.75, BROKEN=0.5, ROUTED=0.25, SURRENDERED=0.0.
        """
        ms = ctx.morale_states.get(unit_id)
        if ms is None:
            return 0.7  # sensible default
        val = int(ms)
        return max(0.0, 1.0 - val * 0.25)

    @staticmethod
    def _get_unit_supply_level(ctx: Any, unit_id: str) -> float:
        """Query stockpile manager for supply state [0, 1]."""
        if ctx.stockpile_manager is None:
            return 1.0
        if not hasattr(ctx.stockpile_manager, "get_supply_state"):
            return 1.0
        try:
            return ctx.stockpile_manager.get_supply_state(unit_id)
        except Exception:
            return 1.0

    @staticmethod
    def _build_assessment_summary(
        ctx: Any,
        unit_id: str,
        assessment: Any,
    ) -> dict[str, float]:
        """Build assessment summary dict from real or default data.

        Used by school decision adjustments and opponent modeling.
        """
        if assessment is not None:
            return {
                "force_ratio": getattr(assessment, "force_ratio", 1.0),
                "supply_level": getattr(assessment, "supply_level", 1.0),
                "morale_level": getattr(assessment, "morale_level", 0.7),
                "intel_quality": getattr(assessment, "intel_quality", 0.5),
                "c2_effectiveness": getattr(assessment, "c2_effectiveness", 1.0),
            }
        # Fallback: compute basic values
        side = ""
        for s, units in ctx.units_by_side.items():
            if any(u.entity_id == unit_id for u in units):
                side = s
                break
        friendly = len(ctx.active_units(side)) if side else 1
        enemies = sum(
            len(ctx.active_units(s))
            for s in ctx.side_names()
            if s != side
        ) if side else 1
        force_ratio = friendly / max(enemies, 1)
        return {
            "force_ratio": force_ratio,
            "supply_level": BattleManager._get_unit_supply_level(ctx, unit_id),
            "morale_level": BattleManager._get_unit_morale_level(ctx, unit_id),
            "intel_quality": 0.5,
            "c2_effectiveness": BattleManager._compute_c2_effectiveness(ctx, unit_id, side),
        }

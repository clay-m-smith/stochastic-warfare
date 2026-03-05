"""Damage resolution — penetration, blast, fragmentation, behind-armor effects.

Implements DeMarre-variant penetration for kinetic rounds, shaped-charge
penetration for HEAT, Gaussian blast attenuation, and 1/r^2 fragmentation.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import AmmoDefinition
from stochastic_warfare.combat.events import DamageEvent, HitEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)

# Constant posture protection factors (blast and fragmentation)
_POSTURE_BLAST_PROTECT: dict[str, float] = {
    "MOVING": 1.0, "HALTED": 0.9, "DEFENSIVE": 0.7,
    "DUG_IN": 0.3, "FORTIFIED": 0.1,
}
_POSTURE_FRAG_PROTECT: dict[str, float] = {
    "MOVING": 1.0, "HALTED": 0.85, "DEFENSIVE": 0.5,
    "DUG_IN": 0.15, "FORTIFIED": 0.05,
}


class DamageType(enum.IntEnum):
    """Terminal effect classification."""

    KINETIC = 0
    BLAST = 1
    FRAGMENTATION = 2
    INCENDIARY = 3
    COMBINED = 4
    THERMAL_ENERGY = 5
    ELECTRONIC = 6


class ArmorType(enum.IntEnum):
    """Armor composition type affecting protection effectiveness."""

    RHA = 0
    COMPOSITE = 1
    REACTIVE = 2
    SPACED = 3


# Armor effectiveness multipliers: (armor_type, ammo_category) -> multiplier
# Higher multiplier = more effective armor (harder to penetrate)
_ARMOR_EFFECTIVENESS: dict[tuple[int, str], float] = {
    (ArmorType.RHA, "KE"): 1.0,
    (ArmorType.RHA, "HEAT"): 1.0,
    (ArmorType.COMPOSITE, "KE"): 1.5,
    (ArmorType.COMPOSITE, "HEAT"): 2.5,
    (ArmorType.REACTIVE, "KE"): 1.0,
    (ArmorType.REACTIVE, "HEAT"): 2.0,
    (ArmorType.SPACED, "KE"): 0.9,
    (ArmorType.SPACED, "HEAT"): 1.3,
}


class DamageConfig(BaseModel):
    """Tunable parameters for damage resolution."""

    demare_exponent: float = 1.5
    spall_probability: float = 0.3
    fire_probability: float = 0.1
    ammo_cookoff_probability: float = 0.05
    min_penetration_fraction: float = 0.5
    blast_sigma_scale: float = 1.0
    # Submunition scatter (Phase 27b)
    enable_submunition_scatter: bool = False
    submunition_scatter_sigma_fraction: float = 0.7


@dataclass
class PenetrationResult:
    """Outcome of a penetration calculation."""

    penetrated: bool
    penetration_mm: float
    armor_effective_mm: float
    margin_mm: float  # positive = overmatch, negative = stopped


@dataclass
class CasualtyResult:
    """Individual casualty from behind-armor effects."""

    member_index: int
    severity: str  # "minor", "serious", "critical", "kia"
    cause: str  # "spall", "fire", "blast_overpressure"


@dataclass
class DamageResult:
    """Complete damage outcome."""

    damage_type: DamageType
    damage_fraction: float  # 0.0–1.0 condition reduction
    penetrated: bool = False
    casualties: list[CasualtyResult] = field(default_factory=list)
    systems_damaged: list[str] = field(default_factory=list)
    fire_started: bool = False
    ammo_cookoff: bool = False


class DamageEngine:
    """Resolves terminal effects of projectile impacts.

    Parameters
    ----------
    event_bus:
        For publishing damage events.
    rng:
        PRNG generator for stochastic effects.
    config:
        Tunable damage parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: DamageConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or DamageConfig()

    def compute_penetration(
        self,
        ammo: AmmoDefinition,
        armor_mm: float,
        impact_angle_deg: float = 0.0,
        range_m: float = 0.0,
        armor_type: str = "RHA",
    ) -> PenetrationResult:
        """Compute whether a round penetrates armor.

        Parameters
        ----------
        ammo:
            Ammunition definition with penetration data.
        armor_mm:
            Armor thickness in mm RHA.
        impact_angle_deg:
            Impact angle from normal (0 = perpendicular).
        range_m:
            Engagement range for velocity-dependent penetration.
        armor_type:
            Armor composition type (RHA, COMPOSITE, REACTIVE, SPACED).
        """
        if ammo.penetration_mm_rha <= 0:
            return PenetrationResult(
                penetrated=False, penetration_mm=0.0,
                armor_effective_mm=armor_mm, margin_mm=-armor_mm,
            )

        # Effective armor thickness (obliquity)
        angle_rad = math.radians(min(abs(impact_angle_deg), 80.0))
        cos_angle = math.cos(angle_rad)
        if cos_angle < 0.1:
            cos_angle = 0.1
        armor_eff = armor_mm / cos_angle

        # Ricochet check: extreme obliquity causes round to skip off surface
        if abs(impact_angle_deg) > 75.0:
            return PenetrationResult(
                penetrated=False,
                penetration_mm=0.0,
                armor_effective_mm=armor_eff,
                margin_mm=-armor_eff,
            )

        # Armor effectiveness multiplier based on composition and ammo category
        ammo_type_str = ammo.ammo_type.upper()
        ammo_category = "HEAT" if ammo_type_str == "HEAT" else "KE"
        try:
            at_enum = ArmorType[armor_type.upper()]
        except KeyError:
            at_enum = ArmorType.RHA
        effectiveness = _ARMOR_EFFECTIVENESS.get((at_enum, ammo_category), 1.0)
        armor_eff *= effectiveness

        # Penetration calculation
        pen_ref = ammo.penetration_mm_rha

        if ammo_type_str == "HEAT":
            # HEAT: penetration independent of range (shaped charge)
            penetration = pen_ref
        elif ammo.penetration_reference_range_m > 0 and range_m > 0:
            # DeMarre variant: pen = pen_ref × (v/v_ref)^1.5
            # Approximate velocity decay: v/v_ref ≈ 1 - drag_factor * range
            decay = 1.0 - ammo.drag_coefficient * range_m / 100000.0
            decay = max(0.3, decay)
            penetration = pen_ref * decay ** self._config.demare_exponent
        else:
            penetration = pen_ref

        margin = penetration - armor_eff
        penetrated = margin > 0

        return PenetrationResult(
            penetrated=penetrated,
            penetration_mm=penetration,
            armor_effective_mm=armor_eff,
            margin_mm=margin,
        )

    def apply_behind_armor_effects(
        self,
        penetration: PenetrationResult,
        crew_count: int,
    ) -> list[CasualtyResult]:
        """Resolve behind-armor effects for a penetrating hit.

        Parameters
        ----------
        penetration:
            Result of penetration calculation.
        crew_count:
            Number of crew in the vehicle.
        """
        if not penetration.penetrated:
            return []

        casualties: list[CasualtyResult] = []
        cfg = self._config

        # Overmatch factor: more penetration → worse effects
        overmatch = penetration.margin_mm / max(
            1.0, penetration.armor_effective_mm
        )
        overmatch = min(overmatch, 3.0)

        # Spalling
        for i in range(crew_count):
            if self._rng.random() < cfg.spall_probability * (0.5 + 0.5 * overmatch):
                severity = self._resolve_severity(overmatch)
                casualties.append(CasualtyResult(
                    member_index=i, severity=severity, cause="spall",
                ))

        return casualties

    def _resolve_severity(self, overmatch: float) -> str:
        """Determine casualty severity based on overmatch factor."""
        roll = float(self._rng.random())
        # Higher overmatch → more severe
        kia_threshold = 0.1 + 0.2 * overmatch
        critical_threshold = kia_threshold + 0.2
        serious_threshold = critical_threshold + 0.3

        if roll < kia_threshold:
            return "kia"
        elif roll < critical_threshold:
            return "critical"
        elif roll < serious_threshold:
            return "serious"
        else:
            return "minor"

    def apply_blast_damage(
        self,
        ammo: AmmoDefinition,
        distance_m: float,
        posture: str = "MOVING",
    ) -> DamageResult:
        """Compute blast and fragmentation damage.

        Parameters
        ----------
        ammo:
            Ammunition with blast_radius_m and fragmentation_radius_m.
        distance_m:
            Distance from detonation point to target.
        posture:
            Target posture for protection calculation.
        """
        damage_fraction = 0.0
        casualties: list[CasualtyResult] = []

        # Blast: P_kill = exp(-distance^2 / (2 * blast_radius^2))
        if ammo.blast_radius_m > 0:
            sigma = ammo.blast_radius_m * self._config.blast_sigma_scale
            p_kill_blast = math.exp(
                -distance_m * distance_m / (2.0 * sigma * sigma)
            )
            # Posture protection
            protection = _POSTURE_BLAST_PROTECT.get(posture, 1.0)
            damage_fraction = max(damage_fraction, p_kill_blast * protection)

        # Fragmentation: 1/r^2 falloff
        if ammo.fragmentation_radius_m > 0 and distance_m < ammo.fragmentation_radius_m:
            frag_factor = 1.0 - (distance_m / ammo.fragmentation_radius_m) ** 2
            frag_protection = _POSTURE_FRAG_PROTECT.get(posture, 1.0)
            frag_damage = frag_factor * frag_protection
            damage_fraction = max(damage_fraction, frag_damage)

        return DamageResult(
            damage_type=DamageType.COMBINED if ammo.fragmentation_radius_m > 0 else DamageType.BLAST,
            damage_fraction=min(1.0, damage_fraction),
        )

    def resolve_damage(
        self,
        target_id: str,
        ammo: AmmoDefinition,
        armor_mm: float = 0.0,
        impact_angle_deg: float = 0.0,
        range_m: float = 0.0,
        distance_from_impact_m: float = 0.0,
        crew_count: int = 4,
        posture: str = "MOVING",
        timestamp: Any = None,
        armor_type: str = "RHA",
    ) -> DamageResult:
        """Full damage resolution: penetration + blast + behind-armor effects.

        Parameters
        ----------
        target_id:
            Entity ID of the target.
        ammo:
            Ammunition that hit.
        armor_mm:
            Target armor in mm RHA (0 for unarmored).
        impact_angle_deg:
            Impact angle from normal.
        range_m:
            Engagement range.
        distance_from_impact_m:
            Distance from detonation point (for blast/frag; 0 = direct hit).
        crew_count:
            Number of crew members.
        posture:
            Target posture.
        timestamp:
            Simulation timestamp for events.
        armor_type:
            Armor composition type (RHA, COMPOSITE, REACTIVE, SPACED).
        """
        result = DamageResult(damage_type=DamageType.COMBINED, damage_fraction=0.0)

        # Kinetic / penetration
        if armor_mm > 0 and ammo.penetration_mm_rha > 0:
            pen = self.compute_penetration(ammo, armor_mm, impact_angle_deg, range_m, armor_type)
            result.penetrated = pen.penetrated

            if pen.penetrated:
                bae = self.apply_behind_armor_effects(pen, crew_count)
                result.casualties.extend(bae)
                result.damage_fraction = min(1.0, 0.3 + 0.3 * (pen.margin_mm / max(1.0, armor_mm)))

                # Fire / cookoff
                if self._rng.random() < self._config.fire_probability:
                    result.fire_started = True
                if self._rng.random() < self._config.ammo_cookoff_probability:
                    result.ammo_cookoff = True
                    result.damage_fraction = 1.0

            # Publish events
            if timestamp is not None:
                self._event_bus.publish(HitEvent(
                    timestamp=timestamp, source=ModuleId.COMBAT,
                    target_id=target_id, weapon_id="",
                    damage_type="KINETIC", penetrated=pen.penetrated,
                ))
        else:
            # Blast/frag against unarmored or soft target
            blast_result = self.apply_blast_damage(ammo, distance_from_impact_m, posture)
            result.damage_fraction = blast_result.damage_fraction
            result.damage_type = blast_result.damage_type

        if timestamp is not None and result.damage_fraction > 0:
            self._event_bus.publish(DamageEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                target_id=target_id, damage_amount=result.damage_fraction,
                damage_type=result.damage_type.name, location="hull",
            ))

        return result

    def resolve_submunition_damage(
        self,
        ammo: AmmoDefinition,
        impact_pos: Position,
        target_positions: dict[str, Position],
        posture: str = "MOVING",
        uxo_engine: Any | None = None,
        timestamp: float = 0.0,
    ) -> dict[str, DamageResult]:
        """Scatter submunitions from a DPICM or cluster round and resolve damage.

        Parameters
        ----------
        ammo:
            Ammunition with submunition_count and submunition_lethal_radius_m.
        impact_pos:
            Center of the cluster impact area.
        target_positions:
            Mapping of target_id -> Position for potential targets.
        posture:
            Target posture for blast damage.
        uxo_engine:
            Optional UXO engine for failed submunition tracking.
        timestamp:
            Simulation timestamp.
        """
        count = ammo.submunition_count
        if count <= 0:
            return {}

        lethal_r = ammo.submunition_lethal_radius_m
        if lethal_r <= 0:
            lethal_r = ammo.blast_radius_m

        # Scatter sigma proportional to blast radius
        sigma = ammo.blast_radius_m * self._config.submunition_scatter_sigma_fraction
        if sigma <= 0:
            sigma = 50.0

        # Determine failed submunitions
        failed = int(count * ammo.uxo_rate)
        live = count - failed

        # Create UXO field if engine provided and there are duds
        if uxo_engine is not None and failed > 0:
            uxo_engine.create_uxo_field(
                position=impact_pos,
                radius_m=sigma * 3.0,
                submunition_count=count,
                uxo_rate=ammo.uxo_rate,
                timestamp=timestamp,
            )

        # Scatter live submunitions
        results: dict[str, DamageResult] = {}
        for _ in range(live):
            off_e = self._rng.normal(0.0, sigma)
            off_n = self._rng.normal(0.0, sigma)
            sub_pos = Position(
                impact_pos.easting + off_e,
                impact_pos.northing + off_n,
                impact_pos.altitude,
            )
            # Check each target
            for tid, tpos in target_positions.items():
                dx = sub_pos.easting - tpos.easting
                dy = sub_pos.northing - tpos.northing
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= lethal_r:
                    dmg = self.apply_blast_damage(ammo, dist, posture)
                    if tid in results:
                        results[tid].damage_fraction = min(
                            1.0, results[tid].damage_fraction + dmg.damage_fraction,
                        )
                    else:
                        results[tid] = dmg

        return results

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]


# ---------------------------------------------------------------------------
# Incendiary damage (Phase 24b)
# ---------------------------------------------------------------------------


class IncendiaryConfig(BaseModel):
    """Tunable parameters for incendiary weapon effects."""

    expansion_factor: float = 0.1
    max_expansion_ratio: float = 3.0
    burn_damage_per_second: float = 0.02
    smoke_obscurant_radius_m: float = 200.0


@dataclass
class FireZone:
    """An active fire zone from an incendiary weapon."""

    zone_id: str
    center: "Position"
    radius_m: float
    wind_offset_mps: tuple[float, float]
    fuel_load: float
    ignition_time_s: float
    duration_s: float
    current_radius_m: float


@dataclass
class BurnedZone:
    """A burned-out fire zone that affects concealment."""

    zone_id: str
    center: "Position"
    radius_m: float
    concealment_reduction: float = 0.5


class IncendiaryDamageEngine:
    """Manages incendiary weapon fire zones, expansion, and burn damage.

    Parameters
    ----------
    rng:
        PRNG generator for stochastic effects.
    config:
        Tunable incendiary parameters.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        config: IncendiaryConfig | None = None,
    ) -> None:
        self._rng = rng
        self._config = config or IncendiaryConfig()
        self._active_zones: list[FireZone] = []
        self._burned_zones: list[BurnedZone] = []
        self._zone_counter: int = 0

    def create_fire_zone(
        self,
        position: "Position",
        radius_m: float,
        fuel_load: float,
        wind_speed_mps: float,
        wind_dir_rad: float,
        duration_s: float,
        timestamp: float,
    ) -> FireZone:
        """Create a new fire zone from an incendiary strike.

        Parameters
        ----------
        position:
            Impact/ignition point.
        radius_m:
            Initial fire radius.
        fuel_load:
            Fuel density factor (0.0-1.0).
        wind_speed_mps:
            Wind speed in meters per second.
        wind_dir_rad:
            Wind direction in radians.
        duration_s:
            Expected burn duration.
        timestamp:
            Simulation time of ignition.
        """
        self._zone_counter += 1
        zone_id = f"fire_{self._zone_counter}"
        wind_offset = (
            wind_speed_mps * math.cos(wind_dir_rad),
            wind_speed_mps * math.sin(wind_dir_rad),
        )
        zone = FireZone(
            zone_id=zone_id,
            center=position,
            radius_m=radius_m,
            wind_offset_mps=wind_offset,
            fuel_load=fuel_load,
            ignition_time_s=timestamp,
            duration_s=duration_s,
            current_radius_m=radius_m,
        )
        self._active_zones.append(zone)
        logger.info("Created fire zone %s at %s, radius=%.1fm", zone_id, position, radius_m)
        return zone

    def update_fire_zones(self, dt: float) -> list[FireZone]:
        """Advance fire zones by *dt* seconds.

        Expands each active zone based on wind, fuel load, and expansion
        factor.  Zones that exceed their duration are converted to burned
        zones and removed from the active list.

        Returns the list of currently active fire zones.
        """
        cfg = self._config
        still_active: list[FireZone] = []
        for zone in self._active_zones:
            # Expand radius: wind_speed * expansion_factor * fuel_load * dt
            wind_speed = math.sqrt(
                zone.wind_offset_mps[0] ** 2 + zone.wind_offset_mps[1] ** 2
            )
            expansion = wind_speed * cfg.expansion_factor * zone.fuel_load * dt
            zone.current_radius_m += expansion
            # Cap at max_expansion_ratio * initial radius
            max_radius = zone.radius_m * cfg.max_expansion_ratio
            if zone.current_radius_m > max_radius:
                zone.current_radius_m = max_radius

            # Check duration
            zone.duration_s -= dt
            if zone.duration_s <= 0:
                # Convert to burned zone
                self._burned_zones.append(BurnedZone(
                    zone_id=zone.zone_id,
                    center=zone.center,
                    radius_m=zone.current_radius_m,
                ))
                logger.info("Fire zone %s burned out", zone.zone_id)
            else:
                still_active.append(zone)

        self._active_zones = still_active
        return list(self._active_zones)

    def get_burned_zones(self) -> list[BurnedZone]:
        """Return all burned-out zones."""
        return list(self._burned_zones)

    def units_in_fire(
        self, unit_positions: dict[str, "Position"],
    ) -> dict[str, float]:
        """Check which units are inside active fire zones.

        Returns a dict mapping unit_id to damage_fraction (burn damage
        per second) for units inside any fire zone.
        """
        result: dict[str, float] = {}
        for uid, pos in unit_positions.items():
            for zone in self._active_zones:
                dx = pos[0] - zone.center[0]
                dy = pos[1] - zone.center[1]
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= zone.current_radius_m:
                    result[uid] = self._config.burn_damage_per_second
                    break  # one zone is enough to cause damage
        return result

    def get_state(self) -> dict[str, Any]:
        """Serialize engine state for checkpointing."""
        return {
            "zone_counter": self._zone_counter,
            "active_zones": [
                {
                    "zone_id": z.zone_id,
                    "center": list(z.center),
                    "radius_m": z.radius_m,
                    "wind_offset_mps": list(z.wind_offset_mps),
                    "fuel_load": z.fuel_load,
                    "ignition_time_s": z.ignition_time_s,
                    "duration_s": z.duration_s,
                    "current_radius_m": z.current_radius_m,
                }
                for z in self._active_zones
            ],
            "burned_zones": [
                {
                    "zone_id": bz.zone_id,
                    "center": list(bz.center),
                    "radius_m": bz.radius_m,
                    "concealment_reduction": bz.concealment_reduction,
                }
                for bz in self._burned_zones
            ],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a checkpoint."""
        from stochastic_warfare.core.types import Position as Pos

        self._zone_counter = state["zone_counter"]
        self._active_zones = [
            FireZone(
                zone_id=z["zone_id"],
                center=Pos(*z["center"]),
                radius_m=z["radius_m"],
                wind_offset_mps=tuple(z["wind_offset_mps"]),
                fuel_load=z["fuel_load"],
                ignition_time_s=z["ignition_time_s"],
                duration_s=z["duration_s"],
                current_radius_m=z["current_radius_m"],
            )
            for z in state["active_zones"]
        ]
        self._burned_zones = [
            BurnedZone(
                zone_id=bz["zone_id"],
                center=Pos(*bz["center"]),
                radius_m=bz["radius_m"],
                concealment_reduction=bz["concealment_reduction"],
            )
            for bz in state["burned_zones"]
        ]


# ---------------------------------------------------------------------------
# UXO (unexploded ordnance) fields (Phase 24b)
# ---------------------------------------------------------------------------


@dataclass
class UXOField:
    """An area contaminated by unexploded submunitions."""

    field_id: str
    center: "Position"
    radius_m: float
    density: float  # UXO per square meter
    submunition_count: int
    uxo_rate: float
    creation_time_s: float


class UXOEngine:
    """Tracks UXO fields and encounter probability.

    Parameters
    ----------
    rng:
        PRNG generator for stochastic encounter resolution.
    """

    def __init__(
        self,
        rng: np.random.Generator,
    ) -> None:
        self._rng = rng
        self._fields: list[UXOField] = []
        self._field_counter: int = 0

    def create_uxo_field(
        self,
        position: "Position",
        radius_m: float,
        submunition_count: int,
        uxo_rate: float,
        timestamp: float,
    ) -> UXOField:
        """Create a UXO field from a cluster munition strike.

        Parameters
        ----------
        position:
            Center of the strike area.
        radius_m:
            Radius of the contaminated area.
        submunition_count:
            Total submunitions deployed.
        uxo_rate:
            Fraction of submunitions that fail to detonate.
        timestamp:
            Simulation time of creation.
        """
        self._field_counter += 1
        field_id = f"uxo_{self._field_counter}"
        area = math.pi * radius_m * radius_m
        density = (submunition_count * uxo_rate) / area if area > 0 else 0.0
        uxo_field = UXOField(
            field_id=field_id,
            center=position,
            radius_m=radius_m,
            density=density,
            submunition_count=submunition_count,
            uxo_rate=uxo_rate,
            creation_time_s=timestamp,
        )
        self._fields.append(uxo_field)
        logger.info(
            "Created UXO field %s at %s, density=%.6f/m²",
            field_id, position, density,
        )
        return uxo_field

    def check_uxo_encounter(
        self,
        position: "Position",
        is_civilian: bool = False,
    ) -> bool:
        """Check whether a unit at *position* encounters a UXO.

        Parameters
        ----------
        position:
            Current position of the entity.
        is_civilian:
            Whether the entity is civilian (not currently used for
            probability but tracked for war-crimes accounting).

        Returns True if an encounter occurs.
        """
        for uxo_field in self._fields:
            dx = position[0] - uxo_field.center[0]
            dy = position[1] - uxo_field.center[1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= uxo_field.radius_m:
                # Probability scales with density; use a 1m² check area
                probability = uxo_field.density
                if float(self._rng.random()) < probability:
                    return True
        return False

    def get_fields(self) -> list[UXOField]:
        """Return all active UXO fields."""
        return list(self._fields)

    def get_state(self) -> dict[str, Any]:
        """Serialize engine state for checkpointing."""
        return {
            "field_counter": self._field_counter,
            "fields": [
                {
                    "field_id": f.field_id,
                    "center": list(f.center),
                    "radius_m": f.radius_m,
                    "density": f.density,
                    "submunition_count": f.submunition_count,
                    "uxo_rate": f.uxo_rate,
                    "creation_time_s": f.creation_time_s,
                }
                for f in self._fields
            ],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a checkpoint."""
        from stochastic_warfare.core.types import Position as Pos

        self._field_counter = state["field_counter"]
        self._fields = [
            UXOField(
                field_id=f["field_id"],
                center=Pos(*f["center"]),
                radius_m=f["radius_m"],
                density=f["density"],
                submunition_count=f["submunition_count"],
                uxo_rate=f["uxo_rate"],
                creation_time_s=f["creation_time_s"],
            )
            for f in state["fields"]
        ]

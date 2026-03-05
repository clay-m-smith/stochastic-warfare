"""Submarine warfare — torpedo attack, evasion, counter-torpedo, patrol ops.

Models torpedo engagement with wire-guided and autonomous seekers,
submarine evasion maneuvers (decoy, depth change, knuckle, geometric),
counter-torpedo defense, and patrol area operations.  Torpedo kill
probability depends on range, guidance mode, and environmental conditions
(thermocline, ambient noise).  Geometric evasion models bearing-rate
maneuvers and thermocline exploitation.  Patrol operations model
area-coverage detection over time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.events import TorpedoEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class NavalSubsurfaceConfig(BaseModel):
    """Tunable parameters for submarine combat."""

    max_torpedo_range_m: float = 50_000.0
    wire_guidance_bonus: float = 0.15  # pk bonus for wire-guided
    shallow_launch_depth_m: float = 50.0  # max depth for missile launch
    decoy_effectiveness: float = 0.4
    depth_change_effectiveness: float = 0.3
    knuckle_effectiveness: float = 0.2
    counter_torpedo_base_pk: float = 0.2
    range_decay_factor: float = 0.00002  # pk degrades with range
    malfunction_probability: float = 0.05
    # ASROC (Phase 27c)
    asroc_max_range_m: float = 22_000.0
    asroc_flight_time_s: float = 30.0
    asroc_torpedo_pk: float = 0.3
    # Depth charges (Phase 27c)
    depth_charge_pattern_radius_m: float = 100.0
    depth_charge_lethal_radius_m: float = 15.0
    depth_charge_pk_per_charge: float = 0.05
    # Torpedo countermeasures (Phase 27c)
    nixie_seduction_probability: float = 0.35
    acoustic_cm_confusion_probability: float = 0.25
    enable_torpedo_countermeasures: bool = False

    # Geometric evasion (Phase 12c)
    enable_geometric_evasion: bool = False
    bearing_rate_threshold: float = 0.05  # rad/s — minimum rate for evasion
    thermocline_bonus: float = 0.2  # success probability bonus for crossing
    speed_diff_threshold: float = 0.3  # minimum speed differential ratio
    range_proxy_m: float = 5000.0  # proxy range for bearing rate calc


@dataclass
class TorpedoResult:
    """Outcome of a torpedo engagement."""

    torpedo_id: str
    hit: bool
    evaded: bool = False
    decoyed: bool = False
    malfunction: bool = False
    damage_fraction: float = 0.0


@dataclass
class EvasionResult:
    """Outcome of a submarine evasion maneuver."""

    evasion_type: str  # "decoy", "depth_change", "knuckle"
    success: bool
    effectiveness: float  # 0.0–1.0 reduction in incoming pk


# ---------------------------------------------------------------------------
# Geometric evasion (Phase 12c)
# ---------------------------------------------------------------------------


@dataclass
class SubmarineState:
    """Snapshot of a submarine's kinematic state for evasion computations."""

    speed_kts: float = 5.0
    depth_m: float = 100.0
    heading_deg: float = 0.0
    below_thermocline: bool = False


@dataclass
class GeometricEvasionResult:
    """Outcome of a geometry-based evasion maneuver."""

    success: bool
    bearing_rate_change: float
    speed_differential: float
    crossed_thermocline: bool
    evasion_type: str


# ---------------------------------------------------------------------------
# Patrol operations (Phase 12c)
# ---------------------------------------------------------------------------


@dataclass
class PatrolArea:
    """Defines a submarine patrol area."""

    patrol_id: str
    center: Position
    radius_m: float
    area_type: str = "barrier"  # "barrier", "area_search", "chokepoint"


@dataclass
class PatrolResult:
    """Outcome of a patrol update tick."""

    contacts_detected: int
    area_covered_fraction: float
    time_on_station_hours: float


@dataclass
class ASROCResult:
    """Outcome of an ASROC engagement."""

    ship_id: str
    target_id: str
    flight_success: bool = False
    torpedo_hit: bool = False
    damage_fraction: float = 0.0


@dataclass
class DepthChargeResult:
    """Outcome of a depth charge attack."""

    ship_id: str
    target_id: str
    charges_dropped: int = 0
    hits: int = 0
    damage_fraction: float = 0.0


@dataclass
class TorpedoCountermeasureResult:
    """Outcome of torpedo countermeasure employment."""

    defender_id: str
    torpedo_defeated: bool = False
    nixie_success: bool = False
    acoustic_cm_success: bool = False
    evasion_success: bool = False
    effective_pk: float = 0.0


class SubmarinePatrolConfig(BaseModel):
    """Configuration for patrol operations."""

    detection_rate_base: float = 0.02  # contacts per hour per unit sensor quality
    enable_patrol_ops: bool = False


class NavalSubsurfaceEngine:
    """Manages submarine torpedo attacks and evasion.

    Parameters
    ----------
    damage_engine:
        For resolving torpedo damage.
    event_bus:
        For publishing torpedo events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        damage_engine: DamageEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: NavalSubsurfaceConfig | None = None,
        patrol_config: SubmarinePatrolConfig | None = None,
    ) -> None:
        self._damage = damage_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or NavalSubsurfaceConfig()
        self._patrol_config = patrol_config or SubmarinePatrolConfig()
        self._torpedo_count: int = 0
        # Patrol state: sub_id -> (PatrolArea, cumulative hours)
        self._patrol_assignments: dict[str, PatrolArea] = {}
        self._patrol_hours: dict[str, float] = {}

    def torpedo_engagement(
        self,
        sub_id: str,
        target_id: str,
        torpedo_pk: float,
        range_m: float,
        wire_guided: bool = False,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
    ) -> TorpedoResult:
        """Resolve a torpedo engagement.

        Parameters
        ----------
        sub_id:
            Entity ID of the attacking submarine.
        target_id:
            Entity ID of the target.
        torpedo_pk:
            Base kill probability of the torpedo.
        range_m:
            Range to target in meters.
        wire_guided:
            Whether the torpedo is wire-guided (improves pk).
        conditions:
            Environmental conditions (thermocline_depth_m, ambient_noise_db).
        timestamp:
            Simulation timestamp.
        """
        self._torpedo_count += 1
        torpedo_id = f"{sub_id}_torp_{self._torpedo_count}"

        cfg = self._config

        # Check malfunction
        if self._rng.random() < cfg.malfunction_probability:
            result = TorpedoResult(
                torpedo_id=torpedo_id, hit=False, malfunction=True,
            )
            if timestamp is not None:
                self._event_bus.publish(TorpedoEvent(
                    timestamp=timestamp, source=ModuleId.COMBAT,
                    shooter_id=sub_id, target_id=target_id,
                    torpedo_id=torpedo_id, result="malfunction",
                ))
            return result

        # Compute effective pk
        pk = torpedo_pk

        # Range degradation
        pk -= cfg.range_decay_factor * range_m

        # Wire guidance bonus
        if wire_guided:
            pk += cfg.wire_guidance_bonus

        # Environmental conditions
        if conditions:
            # Thermocline crossing degrades sonar/guidance
            thermocline = conditions.get("thermocline_depth_m", 0.0)
            if thermocline > 0:
                pk *= 0.85  # 15% penalty for thermocline crossing
            # High ambient noise degrades acoustic homing
            ambient_noise = conditions.get("ambient_noise_db", 60.0)
            if ambient_noise > 80.0:
                noise_penalty = (ambient_noise - 80.0) / 100.0
                pk -= noise_penalty

        pk = max(0.0, min(1.0, pk))

        # Resolve hit
        hit = self._rng.random() < pk

        damage = 0.0
        if hit:
            # Torpedoes are devastating — high damage per hit
            damage = 0.3 + 0.5 * self._rng.random()

        result_str = "hit" if hit else "evaded"
        result = TorpedoResult(
            torpedo_id=torpedo_id,
            hit=hit,
            evaded=not hit,
            damage_fraction=damage,
        )

        if timestamp is not None:
            self._event_bus.publish(TorpedoEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                shooter_id=sub_id, target_id=target_id,
                torpedo_id=torpedo_id, result=result_str,
            ))

        return result

    def submarine_launched_missile(
        self,
        sub_id: str,
        launch_depth_m: float,
        missile_ammo_id: str,
    ) -> bool:
        """Attempt to launch a missile from a submarine.

        Requires the submarine to be at or above the shallow launch depth.

        Parameters
        ----------
        sub_id:
            Entity ID of the submarine.
        launch_depth_m:
            Current depth of the submarine in meters.
        missile_ammo_id:
            Ammo ID of the missile to launch.
        """
        if launch_depth_m > self._config.shallow_launch_depth_m:
            logger.debug(
                "Sub %s too deep (%.0fm) for missile launch (max %.0fm)",
                sub_id, launch_depth_m, self._config.shallow_launch_depth_m,
            )
            return False

        # Shallower depth = better launch conditions
        depth_factor = 1.0 - (launch_depth_m / self._config.shallow_launch_depth_m) * 0.2
        success = self._rng.random() < depth_factor

        logger.debug(
            "Sub %s missile launch at %.0fm depth: %s",
            sub_id, launch_depth_m, "success" if success else "failed",
        )
        return success

    def evasion_maneuver(
        self,
        sub_id: str,
        threat_bearing_deg: float,
        evasion_type: str,
        sub_state: SubmarineState | None = None,
        threat_speed_kts: float = 15.0,
    ) -> EvasionResult:
        """Execute an evasion maneuver against an incoming threat.

        When ``enable_geometric_evasion`` is *True* in the config and
        *sub_state* is provided, the method delegates to
        :meth:`geometric_evasion` and wraps the result in an
        :class:`EvasionResult` for backward compatibility.

        Parameters
        ----------
        sub_id:
            Entity ID of the evading submarine.
        threat_bearing_deg:
            Bearing to the incoming threat (degrees from north).
        evasion_type:
            Type of evasion: "decoy", "depth_change", "knuckle".
        sub_state:
            Optional submarine kinematic state (required when geometric
            evasion is enabled).
        threat_speed_kts:
            Speed of the threat in knots (used by geometric evasion).
        """
        cfg = self._config

        # --- geometric evasion delegation ---
        if cfg.enable_geometric_evasion and sub_state is not None:
            geo = self.geometric_evasion(
                sub_state, threat_bearing_deg, threat_speed_kts,
            )
            effectiveness = min(
                1.0, abs(geo.bearing_rate_change) / max(cfg.bearing_rate_threshold, 1e-9),
            )
            logger.debug(
                "Sub %s geometric evasion against bearing %.0f°: success=%s",
                sub_id, threat_bearing_deg, geo.success,
            )
            return EvasionResult(
                evasion_type=geo.evasion_type,
                success=geo.success,
                effectiveness=effectiveness,
            )

        # --- legacy path ---
        effectiveness_map = {
            "decoy": cfg.decoy_effectiveness,
            "depth_change": cfg.depth_change_effectiveness,
            "knuckle": cfg.knuckle_effectiveness,
        }

        base_effectiveness = effectiveness_map.get(evasion_type, 0.1)

        # Add random variation
        actual_effectiveness = base_effectiveness * (0.5 + self._rng.random())
        actual_effectiveness = min(1.0, actual_effectiveness)

        # Success means the maneuver achieves meaningful evasion
        success = actual_effectiveness > 0.2

        logger.debug(
            "Sub %s evasion (%s) against bearing %.0f°: effectiveness=%.2f",
            sub_id, evasion_type, threat_bearing_deg, actual_effectiveness,
        )

        return EvasionResult(
            evasion_type=evasion_type,
            success=success,
            effectiveness=actual_effectiveness,
        )

    def counter_torpedo(
        self,
        defender_id: str,
        incoming_pk: float,
        countermeasure_effectiveness: float,
    ) -> bool:
        """Attempt to defeat an incoming torpedo with countermeasures.

        Parameters
        ----------
        defender_id:
            Entity ID of the defending vessel.
        incoming_pk:
            Kill probability of the incoming torpedo.
        countermeasure_effectiveness:
            Effectiveness of countermeasures (0.0–1.0).
        """
        # Counter-torpedo pk combines base capability with countermeasure quality
        counter_pk = self._config.counter_torpedo_base_pk + (
            countermeasure_effectiveness * (1.0 - self._config.counter_torpedo_base_pk)
        )
        counter_pk = min(1.0, counter_pk)

        defeated = self._rng.random() < counter_pk

        logger.debug(
            "Counter-torpedo by %s: pk=%.2f, result=%s",
            defender_id, counter_pk, "defeated" if defeated else "failed",
        )
        return defeated

    def asroc_engagement(
        self,
        ship_id: str,
        target_id: str,
        range_m: float,
        target_depth_m: float = 100.0,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
    ) -> ASROCResult:
        """Resolve an ASROC (rocket-delivered torpedo) engagement.

        Two-phase: rocket flight (0.9 success) then torpedo engagement.
        """
        cfg = self._config
        result = ASROCResult(ship_id=ship_id, target_id=target_id)

        # Range check
        if range_m > cfg.asroc_max_range_m:
            return result

        # Rocket delivery phase (0.9 reliability)
        if self._rng.random() >= 0.9:
            return result
        result.flight_success = True

        # Lightweight torpedo engagement
        torp_pk = cfg.asroc_torpedo_pk
        # Depth penalty: deeper targets harder to acquire
        depth_factor = max(0.5, 1.0 - target_depth_m / 500.0)
        effective_pk = torp_pk * depth_factor
        effective_pk = max(0.01, min(0.99, effective_pk))

        hit = self._rng.random() < effective_pk
        result.torpedo_hit = hit
        if hit:
            result.damage_fraction = 0.3 + 0.4 * self._rng.random()

        if timestamp is not None:
            self._event_bus.publish(TorpedoEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                shooter_id=ship_id, target_id=target_id,
                torpedo_id=f"{ship_id}_asroc",
                result="hit" if hit else "miss",
            ))

        return result

    def depth_charge_attack(
        self,
        ship_id: str,
        target_id: str,
        num_charges: int,
        target_depth_m: float = 100.0,
        target_range_m: float = 500.0,
        timestamp: Any = None,
    ) -> DepthChargeResult:
        """Resolve a depth charge attack pattern.

        Each charge is scattered within the pattern radius. A charge within
        the lethal radius scores a hit.
        """
        cfg = self._config
        result = DepthChargeResult(
            ship_id=ship_id, target_id=target_id,
            charges_dropped=num_charges,
        )

        for _ in range(num_charges):
            # Scatter each charge within pattern radius
            offset = self._rng.normal(0.0, cfg.depth_charge_pattern_radius_m / 2.0)
            distance = abs(target_range_m + offset)
            if distance <= cfg.depth_charge_lethal_radius_m:
                if self._rng.random() < cfg.depth_charge_pk_per_charge:
                    result.hits += 1

        if result.hits > 0:
            result.damage_fraction = result.hits * 0.2 * (0.5 + 0.5 * self._rng.random())
            result.damage_fraction = min(1.0, result.damage_fraction)

        return result

    def resolve_torpedo_countermeasures(
        self,
        defender_id: str,
        torpedo_pk: float,
        nixie_deployed: bool = False,
        acoustic_cm: bool = False,
        evasion_type: str = "none",
    ) -> TorpedoCountermeasureResult:
        """Resolve layered torpedo countermeasures.

        Layers: NIXIE seduction -> acoustic CM confusion -> evasive maneuver.
        Torpedo defeated if any layer succeeds.
        """
        cfg = self._config
        result = TorpedoCountermeasureResult(
            defender_id=defender_id, effective_pk=torpedo_pk,
        )

        effective_pk = torpedo_pk

        # Layer 1: NIXIE towed decoy
        if nixie_deployed:
            if self._rng.random() < cfg.nixie_seduction_probability:
                result.nixie_success = True
                result.torpedo_defeated = True
                result.effective_pk = 0.0
                return result

        # Layer 2: Acoustic countermeasures
        if acoustic_cm:
            if self._rng.random() < cfg.acoustic_cm_confusion_probability:
                result.acoustic_cm_success = True
                result.torpedo_defeated = True
                result.effective_pk = 0.0
                return result

        # Layer 3: Evasive maneuver
        evasion_effectiveness = {
            "hard_turn": 0.15,
            "sprint": 0.10,
            "none": 0.0,
        }
        evasion_pk = evasion_effectiveness.get(evasion_type, 0.0)
        if evasion_pk > 0 and self._rng.random() < evasion_pk:
            result.evasion_success = True
            result.torpedo_defeated = True
            result.effective_pk = 0.0
            return result

        result.effective_pk = effective_pk
        return result

    # ------------------------------------------------------------------
    # Geometric evasion (Phase 12c)
    # ------------------------------------------------------------------

    def geometric_evasion(
        self,
        sub_state: SubmarineState,
        threat_bearing_deg: float,
        threat_speed_kts: float,
    ) -> GeometricEvasionResult:
        """Evaluate a geometry-based evasion maneuver.

        The submarine tries to generate a high bearing-rate relative to
        the threat by turning perpendicular and exploiting speed and
        thermocline differences.

        Parameters
        ----------
        sub_state:
            Current kinematic state of the submarine.
        threat_bearing_deg:
            Bearing to the threat in degrees from north.
        threat_speed_kts:
            Speed of the threat (torpedo / ASW ship) in knots.
        """
        cfg = self._config

        # Relative bearing between sub heading and threat
        rel_bearing_rad = math.radians(threat_bearing_deg - sub_state.heading_deg)

        # Threat speed component along the submarine's beam
        threat_component = threat_speed_kts * math.cos(rel_bearing_rad)

        # Bearing rate proxy: lateral speed difference over range
        bearing_rate = (
            (sub_state.speed_kts - threat_component) / cfg.range_proxy_m
        )

        # Speed differential ratio
        speed_diff = sub_state.speed_kts / max(threat_speed_kts, 0.1)

        # Thermocline crossing bonus
        crossed = sub_state.below_thermocline

        # Success determination
        rate_ok = abs(bearing_rate) > cfg.bearing_rate_threshold
        speed_ok = speed_diff > cfg.speed_diff_threshold
        success = rate_ok and (speed_ok or crossed)

        # Apply thermocline bonus to success probability (stochastic)
        if not success and crossed:
            success = self._rng.random() < cfg.thermocline_bonus

        evasion_type = "geometric_thermocline" if crossed else "geometric_maneuver"

        logger.debug(
            "Geometric evasion: bearing_rate=%.4f, speed_diff=%.2f, "
            "thermocline=%s, success=%s",
            bearing_rate, speed_diff, crossed, success,
        )

        return GeometricEvasionResult(
            success=success,
            bearing_rate_change=bearing_rate,
            speed_differential=speed_diff,
            crossed_thermocline=crossed,
            evasion_type=evasion_type,
        )

    # ------------------------------------------------------------------
    # Patrol operations (Phase 12c)
    # ------------------------------------------------------------------

    def assign_patrol(self, sub_id: str, patrol_area: PatrolArea) -> None:
        """Assign a submarine to a patrol area.

        Parameters
        ----------
        sub_id:
            Entity ID of the submarine.
        patrol_area:
            Patrol area definition.
        """
        self._patrol_assignments[sub_id] = patrol_area
        self._patrol_hours[sub_id] = 0.0
        logger.debug(
            "Sub %s assigned to patrol %s (type=%s, radius=%.0fm)",
            sub_id, patrol_area.patrol_id, patrol_area.area_type,
            patrol_area.radius_m,
        )

    def update_patrol(
        self,
        sub_id: str,
        dt_hours: float,
        sensor_quality: float = 1.0,
    ) -> PatrolResult:
        """Advance patrol simulation for a submarine.

        Parameters
        ----------
        sub_id:
            Entity ID of the submarine on patrol.
        dt_hours:
            Time increment in hours.
        sensor_quality:
            Sensor effectiveness factor (0.0-1.0).

        Returns
        -------
        PatrolResult
            Contacts detected this tick, area coverage, and cumulative
            time on station.
        """
        pcfg = self._patrol_config
        if sub_id not in self._patrol_assignments:
            logger.warning("Sub %s has no patrol assignment", sub_id)
            return PatrolResult(
                contacts_detected=0,
                area_covered_fraction=0.0,
                time_on_station_hours=0.0,
            )

        patrol = self._patrol_assignments[sub_id]
        self._patrol_hours[sub_id] += dt_hours
        total_hours = self._patrol_hours[sub_id]

        # Area coverage saturates over time (1 - e^(-t/tau))
        # tau scales with patrol area size
        area_km2 = math.pi * (patrol.radius_m / 1000.0) ** 2
        tau = max(1.0, area_km2 / 10.0)  # hours to ~63% coverage
        area_covered = 1.0 - math.exp(-total_hours / tau)

        # Contact detection: Poisson process modulated by sensor quality,
        # area type, and detection rate
        type_mult = {
            "chokepoint": 2.0,
            "barrier": 1.0,
            "area_search": 0.5,
        }.get(patrol.area_type, 1.0)

        rate = pcfg.detection_rate_base * sensor_quality * type_mult * dt_hours
        contacts = int(self._rng.poisson(rate))

        logger.debug(
            "Sub %s patrol update: dt=%.1fh, area=%.1f%%, contacts=%d",
            sub_id, dt_hours, area_covered * 100.0, contacts,
        )

        return PatrolResult(
            contacts_detected=contacts,
            area_covered_fraction=area_covered,
            time_on_station_hours=total_hours,
        )

    # ------------------------------------------------------------------
    # State protocol
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        patrol_state = {
            sub_id: {
                "patrol_id": pa.patrol_id,
                "center": (pa.center.easting, pa.center.northing, pa.center.altitude),
                "radius_m": pa.radius_m,
                "area_type": pa.area_type,
            }
            for sub_id, pa in self._patrol_assignments.items()
        }
        return {
            "rng_state": self._rng.bit_generator.state,
            "torpedo_count": self._torpedo_count,
            "patrol_assignments": patrol_state,
            "patrol_hours": dict(self._patrol_hours),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._torpedo_count = state["torpedo_count"]
        # Restore patrol state (backward-compatible — keys may be absent)
        self._patrol_assignments = {}
        self._patrol_hours = {}
        for sub_id, pa_dict in state.get("patrol_assignments", {}).items():
            cx, cy, cz = pa_dict["center"]
            self._patrol_assignments[sub_id] = PatrolArea(
                patrol_id=pa_dict["patrol_id"],
                center=Position(cx, cy, cz),
                radius_m=pa_dict["radius_m"],
                area_type=pa_dict["area_type"],
            )
        for sub_id, hours in state.get("patrol_hours", {}).items():
            self._patrol_hours[sub_id] = hours

"""Indirect fire — tube artillery, rocket artillery, counterbattery.

Supports fire missions (adjust fire, FFE, immediate suppression, TOT),
rocket salvos with wider dispersion, guided precision (GMLRS, Excalibur),
and counterbattery back-trace.
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    WeaponDefinition,
    WeaponInstance,
)
from stochastic_warfare.combat.ballistics import BallisticsEngine
from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.events import (
    AmmoExpendedEvent,
    ArtilleryFireEvent,
    TimeOnTargetBatteryResult,
    TimeOnTargetMissionEvent,
)
from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.runtime_failure import (
    RuntimeFailureHandler,
    RuntimeFailurePolicyBinding,
)
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.entities.base import UnitStatus
from stochastic_warfare.entities.events import (
    UnitDestroyedEvent,
    UnitDisabledEvent,
)

if TYPE_CHECKING:
    from stochastic_warfare.combat.indirect_fire_config import (
        ResolvedTimeOnTargetBattery,
        ResolvedTimeOnTargetMission,
    )

logger = get_logger(__name__)


class FireMissionType(enum.IntEnum):
    """Fire mission classification."""

    ADJUST_FIRE = 0
    FIRE_FOR_EFFECT = 1
    IMMEDIATE_SUPPRESSION = 2
    TIME_ON_TARGET = 3
    ILLUMINATION = 4
    SMOKE = 5
    COUNTERBATTERY = 6


class IndirectFireConfig(BaseModel):
    """Tunable parameters for indirect fire."""

    adjust_fire_rounds: int = 2
    ffe_cep_improvement: float = 0.5
    rocket_dispersion_multiplier: float = 2.0
    counterbattery_error_m: float = 200.0
    max_simultaneous_missions: int = 3


@dataclass
class ImpactPoint:
    """Single round impact."""

    position: Position
    ammo_id: str
    damage_fraction: float = 0.0


@dataclass
class FireMissionResult:
    """Result of a tube artillery fire mission."""

    mission_type: FireMissionType
    rounds_fired: int
    impacts: list[ImpactPoint] = field(default_factory=list)
    suppression_achieved: bool = False
    target_pos: Position = Position(0.0, 0.0, 0.0)


@dataclass
class SalvoResult:
    """Result of a rocket salvo."""

    rockets_fired: int
    impacts: list[ImpactPoint] = field(default_factory=list)
    target_pos: Position = Position(0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class IndirectFireAssessment:
    """Pure aggregate assessment of indirect-fire impacts against one point."""

    near_impact_count: int
    cumulative_near_impact_count: int
    casualty_fraction: float
    resulting_status: UnitStatus | None


def assess_indirect_fire_impacts(
    impacts: Sequence[ImpactPoint],
    target_position: Position,
    blast_radius_by_ammo_id: Mapping[str, float],
    *,
    prior_near_impact_count: int = 0,
    terrain_modifier: float = 1.0,
    casualty_per_impact: float = 0.15,
    destruction_threshold: float = 0.5,
    disable_threshold: float = 0.3,
) -> IndirectFireAssessment:
    """Assess aggregate effects without mutating a target or caller state."""
    near_impact_count = 0
    for impact in impacts:
        try:
            blast_radius_m = blast_radius_by_ammo_id[impact.ammo_id]
        except KeyError as exc:
            raise ValueError(
                f"No blast radius supplied for ammunition {impact.ammo_id!r}",
            ) from exc
        if (
            isinstance(blast_radius_m, bool)
            or not isinstance(blast_radius_m, (int, float))
            or not math.isfinite(float(blast_radius_m))
            or float(blast_radius_m) <= 0.0
        ):
            raise ValueError(
                f"Blast radius for {impact.ammo_id!r} must be finite and positive",
            )
        dx = impact.position.easting - target_position.easting
        dy = impact.position.northing - target_position.northing
        if math.hypot(dx, dy) < float(blast_radius_m):
            near_impact_count += 1

    cumulative_count = prior_near_impact_count + near_impact_count
    casualty_fraction = min(
        1.0,
        cumulative_count * casualty_per_impact * terrain_modifier,
    )
    resulting_status: UnitStatus | None = None
    if near_impact_count > 0:
        if casualty_fraction >= destruction_threshold:
            resulting_status = UnitStatus.DESTROYED
        elif casualty_fraction >= disable_threshold:
            resulting_status = UnitStatus.DISABLED
    return IndirectFireAssessment(
        near_impact_count=near_impact_count,
        cumulative_near_impact_count=cumulative_count,
        casualty_fraction=casualty_fraction,
        resulting_status=resulting_status,
    )


class IndirectFireEngine:
    """Manages artillery and rocket fire missions.

    Parameters
    ----------
    ballistics:
        Ballistics engine for trajectory/dispersion.
    damage_engine:
        For resolving impact effects.
    event_bus:
        For publishing fire events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        ballistics: BallisticsEngine,
        damage_engine: DamageEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: IndirectFireConfig | None = None,
        *,
        time_on_target_enabled: bool = False,
        time_on_target_missions: tuple[ResolvedTimeOnTargetMission, ...] = (),
        destruction_threshold: float = 0.5,
        disable_threshold: float = 0.3,
    ) -> None:
        self._ballistics = ballistics
        self._damage = damage_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or IndirectFireConfig()
        self._time_on_target_enabled = time_on_target_enabled
        self._time_on_target_missions = time_on_target_missions
        self._destruction_threshold = destruction_threshold
        self._disable_threshold = disable_threshold
        self._runtime_failure_handler: RuntimeFailurePolicyBinding | None = None
        self._topology_fingerprint = self._fingerprint_time_on_target_topology()
        initial_status = "pending" if time_on_target_enabled else "dormant"
        self._time_on_target_state: list[dict[str, Any]] = [
            {
                "mission_id": mission.mission_id,
                "status": initial_status,
                "batteries": [
                    {
                        "battery_id": battery.unit_id,
                        "status": initial_status,
                        "reason": "",
                        "processed_time_s": None,
                        "actual_fire_position": None,
                        "rounds_fired": 0,
                        "impacts": [],
                        "resource_before": None,
                        "resource_after": None,
                        "precondition": None,
                    }
                    for battery in mission.batteries
                ],
                "terminal_result": None,
                "target_transition": None,
            }
            for mission in time_on_target_missions
        ]
        self._initial_resource_observations = {
            key: self._resource_observation(weapon)
            for key, weapon in self._planned_weapons().items()
        }

    def bind_runtime_failure_handler(
        self,
        handler: RuntimeFailureHandler,
    ) -> None:
        """Bind the production strict/degraded failure-policy owner."""
        binding = RuntimeFailurePolicyBinding(handler)
        existing = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if existing is not None and existing != handler:
            raise RuntimeError(
                "IndirectFireEngine already has a different runtime "
                "failure-policy owner",
            )
        self._runtime_failure_handler = binding

    def validate_runtime_failure_handler(
        self,
        handler: RuntimeFailureHandler,
    ) -> None:
        """Reject failure-policy owner drift after runtime construction."""
        bound = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if bound != handler:
            raise RuntimeError(
                "IndirectFireEngine runtime failure-policy binding changed",
            )

    def fire_mission(
        self,
        battery_id: str,
        fire_pos: Position,
        target_pos: Position,
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        mission_type: FireMissionType,
        round_count: int,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
        wind_speed_mps: float = 0.0,
        wind_direction_deg: float = 0.0,
    ) -> FireMissionResult:
        """Execute a tube artillery fire mission.

        Parameters
        ----------
        battery_id:
            Entity ID of the firing battery.
        fire_pos:
            Battery position.
        target_pos:
            Target grid reference.
        weapon:
            Howitzer/mortar weapon definition.
        ammo:
            Ammo type to fire.
        mission_type:
            Type of fire mission.
        round_count:
            Number of rounds to fire.
        conditions:
            Environmental conditions.
        timestamp:
            Simulation timestamp.
        wind_speed_mps:
            Wind speed in m/s (crosswind increases dispersion).
        wind_direction_deg:
            Wind direction in degrees from north (meteorological convention).
        """
        result = FireMissionResult(
            mission_type=mission_type,
            rounds_fired=round_count,
            target_pos=target_pos,
        )

        # CEP from weapon
        cep_m = weapon.cep_m
        if ammo.guidance != "NONE" and ammo.pk_at_reference > 0:
            # Guided round: use much smaller CEP
            cep_m = max(5.0, cep_m * 0.1)

        # FFE improves accuracy (adjust fire brackets target)
        if mission_type == FireMissionType.FIRE_FOR_EFFECT:
            cep_m *= self._config.ffe_cep_improvement

        # Convert CEP to sigma: sigma = CEP / 1.1774
        sigma_m = cep_m / 1.1774 if cep_m > 0 else weapon.base_accuracy_mrad * 10.0

        # Wind increases CEP: crosswind component adds to dispersion
        if wind_speed_mps > 0:
            dx = target_pos.easting - fire_pos.easting
            dy = target_pos.northing - fire_pos.northing
            fire_range = math.sqrt(dx * dx + dy * dy)
            if fire_range > 0:
                fire_dir_deg = math.degrees(math.atan2(dx, dy)) % 360.0
                crosswind_angle_rad = math.radians(wind_direction_deg - fire_dir_deg)
                crosswind_mps = abs(wind_speed_mps * math.sin(crosswind_angle_rad))
                # Each m/s of crosswind adds ~0.5% CEP increase per km range
                wind_cep_factor = 1.0 + 0.005 * crosswind_mps * (fire_range / 1000.0)
                sigma_m *= wind_cep_factor

        for _ in range(round_count):
            offset_e = self._rng.normal(0.0, sigma_m)
            offset_n = self._rng.normal(0.0, sigma_m)
            impact_pos = Position(
                target_pos.easting + offset_e,
                target_pos.northing + offset_n,
                target_pos.altitude,
            )
            result.impacts.append(ImpactPoint(
                position=impact_pos,
                ammo_id=ammo.ammo_id,
            ))

        # Suppression: any HE fire mission with >3 rounds suppresses
        if round_count >= 3 and ammo.blast_radius_m > 0:
            result.suppression_achieved = True

        # Publish event
        if timestamp is not None:
            self._event_bus.publish(ArtilleryFireEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                battery_id=battery_id,
                target_pos=tuple(target_pos),
                ammo_type=ammo.ammo_id,
                round_count=round_count,
            ))

        return result

    def rocket_salvo(
        self,
        launcher_id: str,
        fire_pos: Position,
        target_pos: Position,
        weapon: WeaponDefinition,
        ammo: AmmoDefinition,
        rocket_count: int,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
    ) -> SalvoResult:
        """Fire a rocket salvo (MLRS/HIMARS).

        Rockets have wider dispersion than tube artillery but deliver
        more firepower in a short time.
        """
        result = SalvoResult(rockets_fired=rocket_count, target_pos=target_pos)

        # Rocket dispersion: wider than tube
        if ammo.guidance != "NONE" and ammo.pk_at_reference > 0:
            # Guided rocket (GMLRS): tight CEP
            sigma_m = 5.0 / 1.1774
        else:
            # Unguided: use weapon CEP with rocket multiplier
            cep_m = weapon.cep_m * self._config.rocket_dispersion_multiplier
            sigma_m = cep_m / 1.1774 if cep_m > 0 else 100.0

        for _ in range(rocket_count):
            offset_e = self._rng.normal(0.0, sigma_m)
            offset_n = self._rng.normal(0.0, sigma_m)
            impact_pos = Position(
                target_pos.easting + offset_e,
                target_pos.northing + offset_n,
                target_pos.altitude,
            )
            result.impacts.append(ImpactPoint(
                position=impact_pos,
                ammo_id=ammo.ammo_id,
            ))

        if timestamp is not None:
            self._event_bus.publish(ArtilleryFireEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                battery_id=launcher_id,
                target_pos=tuple(target_pos),
                ammo_type=ammo.ammo_id,
                round_count=rocket_count,
            ))

        return result

    def compute_counterbattery_solution(
        self,
        incoming_direction_rad: float,
        estimated_range_m: float,
    ) -> Position:
        """Back-trace incoming fire to estimate enemy firing position.

        Parameters
        ----------
        incoming_direction_rad:
            Direction the incoming fire came from (radians from north).
        estimated_range_m:
            Estimated range of the enemy battery.

        Returns
        -------
        Position:
            Estimated enemy battery position (with error).
        """
        error_m = self._config.counterbattery_error_m
        error_e = self._rng.normal(0.0, error_m)
        error_n = self._rng.normal(0.0, error_m)

        est_e = estimated_range_m * math.sin(incoming_direction_rad) + error_e
        est_n = estimated_range_m * math.cos(incoming_direction_rad) + error_n

        return Position(est_e, est_n, 0.0)

    @staticmethod
    def _attachment_key(
        battery: ResolvedTimeOnTargetBattery,
    ) -> tuple[str, int, str]:
        return (
            battery.unit_id,
            battery.source_equipment_index,
            battery.weapon.weapon_id,
        )

    @staticmethod
    def _resource_key_record(
        key: tuple[str, int, str],
        observation: Mapping[str, Any],
    ) -> dict[str, Any]:
        unit_id, source_equipment_index, weapon_id = key
        return {
            "unit_id": unit_id,
            "source_equipment_index": source_equipment_index,
            "weapon_id": weapon_id,
            **copy.deepcopy(dict(observation)),
        }

    @staticmethod
    def _resource_observation(weapon: WeaponInstance) -> dict[str, Any]:
        return IndirectFireEngine.canonical_resource_observation(
            weapon.get_state(),
        )

    @staticmethod
    def canonical_resource_observation(
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Canonicalize one persisted ``WeaponInstance`` authority snapshot."""
        last_fire_time_s = state["last_fire_time_s"]
        if last_fire_time_s is None:
            canonical_last_fire: float | None = None
        elif (
            isinstance(last_fire_time_s, bool)
            or not isinstance(last_fire_time_s, (int, float))
            or not math.isfinite(float(last_fire_time_s))
            or float(last_fire_time_s) < 0.0
        ):
            raise ValueError(
                "Weapon last_fire_time_s must be null or "
                "a finite non-negative number",
            )
        else:
            canonical_last_fire = float(last_fire_time_s)
        ammo_state = state["ammo_state"]
        return {
            "ammunition_by_type": {
                ammo_id: rounds
                for ammo_id, rounds in sorted(
                    ammo_state["rounds_by_type"].items(),
                )
            },
            "total_rounds_fired": ammo_state["total_rounds_fired"],
            "rounds_since_maintenance": state["rounds_since_maintenance"],
            "last_fire_time_s": canonical_last_fire,
        }

    def _planned_weapons(self) -> dict[tuple[str, int, str], WeaponInstance]:
        result: dict[tuple[str, int, str], WeaponInstance] = {}
        for mission in self._time_on_target_missions:
            for battery in mission.batteries:
                result.setdefault(
                    self._attachment_key(battery),
                    battery.weapon,
                )
        return result

    def _fingerprint_time_on_target_topology(self) -> str:
        payload = [
            {
                "declaration_index": mission.declaration_index,
                "mission_id": mission.mission_id,
                "attacker_side": mission.attacker_side,
                "target_unit_id": mission.target_unit_id,
                "target_position": list(mission.target_position),
                "scheduled_impact_time_s": mission.scheduled_impact_time_s,
                "rounds_per_battery": mission.rounds_per_battery,
                "batteries": [
                    {
                        "declaration_index": battery.declaration_index,
                        "unit_id": battery.unit_id,
                        "source_equipment_index": (
                            battery.source_equipment_index
                        ),
                        "runtime_system_multiplier": (
                            battery.runtime_system_multiplier
                        ),
                        "weapon_id": battery.weapon.weapon_id,
                        "ammo_id": battery.ammunition.ammo_id,
                        "planned_fire_position": list(
                            battery.planned_fire_position,
                        ),
                        "scheduled_fire_time_s": (
                            battery.scheduled_fire_time_s
                        ),
                        "predicted_time_of_flight_s": (
                            battery.predicted_time_of_flight_s
                        ),
                        "rounds": battery.rounds,
                    }
                    for battery in mission.batteries
                ],
            }
            for mission in self._time_on_target_missions
        ]
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def has_declared_time_on_target_missions(self) -> bool:
        """Whether the runtime topology contains any declared mission."""
        return bool(self._time_on_target_missions)

    @property
    def planned_attachment_keys(self) -> tuple[tuple[str, int, str], ...]:
        """Return exact scheduled attachment identities in canonical order."""
        return tuple(self._planned_weapons())

    @property
    def time_on_target_enabled(self) -> bool:
        """Whether declared scheduled missions are executable."""
        return self._time_on_target_enabled

    def is_attachment_reserved(
        self,
        unit_id: str,
        source_equipment_index: int,
        weapon_id: str,
    ) -> bool:
        """Return whether an exact attachment remains committed to a plan."""
        if not self._time_on_target_enabled:
            return False
        key = (unit_id, source_equipment_index, weapon_id)
        for mission, mission_state in zip(
            self._time_on_target_missions,
            self._time_on_target_state,
            strict=True,
        ):
            if mission_state["status"] == "completed":
                continue
            if any(
                self._attachment_key(battery) == key
                for battery in mission.batteries
            ):
                return True
        return False

    def update_time_on_target(
        self,
        current_time_s: float,
        timestamp: datetime,
    ) -> None:
        """Process every scheduled fire or impact due at this tick boundary."""
        if not self._time_on_target_enabled:
            return
        if (
            isinstance(current_time_s, bool)
            or not isinstance(current_time_s, (int, float))
            or not math.isfinite(float(current_time_s))
            or float(current_time_s) < 0.0
        ):
            raise ValueError("current_time_s must be finite and non-negative")
        current = float(current_time_s)
        milestones: list[tuple[float, int, int, int]] = []
        for mission_index, (mission, mission_state) in enumerate(
            zip(
                self._time_on_target_missions,
                self._time_on_target_state,
                strict=True,
            ),
        ):
            if mission_state["status"] == "completed":
                continue
            for battery_index, (battery, battery_state) in enumerate(
                zip(
                    mission.batteries,
                    mission_state["batteries"],
                    strict=True,
                ),
            ):
                if (
                    battery_state["status"] == "pending"
                    and battery.scheduled_fire_time_s <= current
                ):
                    milestones.append((
                        battery.scheduled_fire_time_s,
                        0,
                        mission_index,
                        battery_index,
                    ))
            if mission.scheduled_impact_time_s <= current:
                milestones.append((
                    mission.scheduled_impact_time_s,
                    1,
                    mission_index,
                    -1,
                ))

        for scheduled_time_s, kind, mission_index, battery_index in sorted(
            milestones,
        ):
            if not math.isclose(
                scheduled_time_s,
                current,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise RuntimeError(
                    "Time-on-target milestone was skipped by the production "
                    f"clock: scheduled={scheduled_time_s}, current={current}",
                )
            if kind == 0:
                self._process_scheduled_fire(
                    mission_index,
                    battery_index,
                    current,
                    timestamp,
                )
            else:
                self._complete_scheduled_mission(
                    mission_index,
                    current,
                    timestamp,
                )

    @staticmethod
    def _precondition_snapshot(
        battery: ResolvedTimeOnTargetBattery,
    ) -> dict[str, Any]:
        equipment = battery.weapon.equipment
        return {
            "unit_status": battery.unit.status.name,
            "unit_position": list(battery.unit.position),
            "unit_speed_mps": float(battery.unit.speed),
            "equipment_condition": (
                float(equipment.condition) if equipment is not None else 1.0
            ),
            "equipment_operational": (
                bool(equipment.operational) if equipment is not None else True
            ),
        }

    @staticmethod
    def _rejection_reason(
        battery: ResolvedTimeOnTargetBattery,
    ) -> str:
        if battery.unit.status is not UnitStatus.ACTIVE:
            return "battery_inactive"
        if (
            battery.weapon.definition.requires_deployed
            and battery.unit.speed > 0.5
        ):
            return "battery_moving"
        if tuple(battery.unit.position) != tuple(
            battery.planned_fire_position,
        ):
            return "battery_displaced"
        if not battery.weapon.operational:
            return "weapon_inoperable"
        if (
            battery.weapon.ammo_state.available(
                battery.ammunition.ammo_id,
            )
            < battery.rounds
        ):
            return "insufficient_ammunition"
        if not battery.weapon.can_fire_timed(
            battery.scheduled_fire_time_s,
            cooldown_multiplier=battery.rounds,
        ):
            return "weapon_cooldown"
        return ""

    def _process_scheduled_fire(
        self,
        mission_index: int,
        battery_index: int,
        current_time_s: float,
        timestamp: datetime,
    ) -> None:
        mission = self._time_on_target_missions[mission_index]
        mission_state = self._time_on_target_state[mission_index]
        battery = mission.batteries[battery_index]
        battery_state = mission_state["batteries"][battery_index]
        if battery_state["status"] != "pending":
            return

        resource_before = self._resource_observation(battery.weapon)
        precondition = self._precondition_snapshot(battery)
        actual_position = list(battery.unit.position)
        rejection_reason = self._rejection_reason(battery)
        battery_state.update({
            "reason": rejection_reason,
            "processed_time_s": current_time_s,
            "actual_fire_position": actual_position,
            "resource_before": resource_before,
            "precondition": precondition,
        })
        if rejection_reason:
            battery_state.update({
                "status": "rejected",
                "resource_after": copy.deepcopy(resource_before),
            })
            return

        if not battery.weapon.fire(
            battery.ammunition.ammo_id,
            battery.rounds,
        ):
            raise RuntimeError(
                "Validated time-on-target weapon fire failed during commit",
            )
        battery.weapon.record_fire(battery.scheduled_fire_time_s)
        result = self.fire_mission(
            battery_id=battery.unit_id,
            fire_pos=battery.unit.position,
            target_pos=mission.target_position,
            weapon=battery.weapon.definition,
            ammo=battery.ammunition,
            mission_type=FireMissionType.TIME_ON_TARGET,
            round_count=battery.rounds,
            timestamp=None,
        )
        battery_state.update({
            "status": "fired",
            "rounds_fired": result.rounds_fired,
            "impacts": [
                {
                    "position": list(impact.position),
                    "ammo_id": impact.ammo_id,
                }
                for impact in result.impacts
            ],
            "resource_after": self._resource_observation(battery.weapon),
        })

        self._publish_committed(AmmoExpendedEvent(
            timestamp=timestamp,
            source=ModuleId.COMBAT,
            unit_id=battery.unit_id,
            ammo_type=battery.ammunition.ammo_id,
            quantity=battery.rounds,
        ))
        self._publish_committed(ArtilleryFireEvent(
            timestamp=timestamp,
            source=ModuleId.COMBAT,
            battery_id=battery.unit_id,
            target_pos=tuple(mission.target_position),
            ammo_type=battery.ammunition.ammo_id,
            round_count=battery.rounds,
        ))

    def _complete_scheduled_mission(
        self,
        mission_index: int,
        current_time_s: float,
        timestamp: datetime,
    ) -> None:
        mission = self._time_on_target_missions[mission_index]
        mission_state = self._time_on_target_state[mission_index]
        if mission_state["status"] == "completed":
            return
        if any(
            state["status"] not in {"fired", "rejected"}
            for state in mission_state["batteries"]
        ):
            raise RuntimeError(
                f"Mission {mission.mission_id!r} reached impact with a "
                "pending battery",
            )

        impacts: list[ImpactPoint] = []
        radii: dict[str, float] = {}
        for battery, battery_state in zip(
            mission.batteries,
            mission_state["batteries"],
            strict=True,
        ):
            radii[battery.ammunition.ammo_id] = (
                battery.ammunition.blast_radius_m
            )
            impacts.extend(
                ImpactPoint(
                    position=Position(*impact["position"]),
                    ammo_id=impact["ammo_id"],
                )
                for impact in battery_state["impacts"]
            )
        assessment = assess_indirect_fire_impacts(
            impacts,
            mission.target_unit.position,
            radii,
            prior_near_impact_count=0,
            terrain_modifier=1.0,
            casualty_per_impact=0.15,
            destruction_threshold=self._destruction_threshold,
            disable_threshold=self._disable_threshold,
        )
        status_before = mission.target_unit.status
        status_after = status_before
        status_event: UnitDestroyedEvent | UnitDisabledEvent | None = None
        if status_before is not UnitStatus.ACTIVE:
            target_effect = "target_inactive"
        elif assessment.near_impact_count == 0:
            target_effect = "missed"
        elif assessment.resulting_status is UnitStatus.DESTROYED:
            target_effect = "destroyed"
            status_after = UnitStatus.DESTROYED
            object.__setattr__(mission.target_unit, "status", status_after)
            status_event = UnitDestroyedEvent(
                timestamp=timestamp,
                source=ModuleId.COMBAT,
                unit_id=mission.target_unit_id,
                cause="time_on_target",
                side=mission.target_unit.side,
                weapon_id="",
            )
        elif assessment.resulting_status is UnitStatus.DISABLED:
            target_effect = "disabled"
            status_after = UnitStatus.DISABLED
            object.__setattr__(mission.target_unit, "status", status_after)
            status_event = UnitDisabledEvent(
                timestamp=timestamp,
                source=ModuleId.COMBAT,
                unit_id=mission.target_unit_id,
                cause="time_on_target",
                side=mission.target_unit.side,
                weapon_id="",
            )
        else:
            target_effect = "unchanged"

        fired_count = sum(
            state["status"] == "fired"
            for state in mission_state["batteries"]
        )
        if fired_count == len(mission_state["batteries"]):
            outcome = "completed"
        elif fired_count:
            outcome = "partial"
        else:
            outcome = "rejected"

        battery_results = tuple(
            TimeOnTargetBatteryResult(
                battery_id=battery.unit_id,
                source_equipment_index=battery.source_equipment_index,
                runtime_system_multiplier=battery.runtime_system_multiplier,
                weapon_id=battery.weapon.weapon_id,
                ammo_id=battery.ammunition.ammo_id,
                planned_fire_position=tuple(
                    battery.planned_fire_position,
                ),
                actual_fire_position=tuple(
                    battery_state["actual_fire_position"],
                ),
                scheduled_fire_time_s=battery.scheduled_fire_time_s,
                predicted_time_of_flight_s=(
                    battery.predicted_time_of_flight_s
                ),
                processing_time_s=battery_state["processed_time_s"],
                status=battery_state["status"],
                reason=battery_state["reason"],
                rounds_fired=battery_state["rounds_fired"],
                generated_impact_count=len(battery_state["impacts"]),
            )
            for battery, battery_state in zip(
                mission.batteries,
                mission_state["batteries"],
                strict=True,
            )
        )
        terminal_event = TimeOnTargetMissionEvent(
            timestamp=timestamp,
            source=ModuleId.COMBAT,
            mission_id=mission.mission_id,
            attacker_side=mission.attacker_side,
            target_unit_id=mission.target_unit_id,
            target_position=tuple(mission.target_position),
            scheduled_impact_time_s=mission.scheduled_impact_time_s,
            processing_time_s=current_time_s,
            battery_results=battery_results,
            total_generated_impacts=len(impacts),
            near_target_impacts=assessment.near_impact_count,
            outcome=outcome,
            target_effect=target_effect,
            target_status_before=status_before.name,
            target_status_after=status_after.name,
        )
        terminal_result = asdict(terminal_event)
        terminal_result.pop("timestamp")
        terminal_result.pop("source")
        mission_state.update({
            "status": "completed",
            "terminal_result": terminal_result,
            "target_transition": {
                "position": list(mission.target_unit.position),
                "status_before": status_before.name,
                "status_after": status_after.name,
            },
        })

        if status_event is not None:
            self._publish_committed(status_event)
        self._publish_committed(terminal_event)

    def _publish_committed(self, event: Event) -> None:
        for error in self._event_bus.publish_collecting(event):
            logger.error(
                "Time-on-target observer failed for %s: %s",
                type(event).__name__,
                error,
                exc_info=(
                    type(error),
                    error,
                    error.__traceback__,
                ),
            )
            binding = getattr(
                self,
                "_runtime_failure_handler",
                None,
            )
            handler = (
                binding.resolve()
                if binding is not None
                else None
            )
            if handler is None or not handler(
                "combat.indirect_fire",
                "publish_committed_event",
                error,
            ):
                raise error

    def get_state(self) -> dict[str, Any]:
        """Capture scheduled lifecycle plus the shared COMBAT RNG mirror."""
        if not self._time_on_target_missions:
            return {"rng_state": copy.deepcopy(self._rng.bit_generator.state)}
        planned_weapons = self._planned_weapons()
        return {
            "topology_fingerprint": self._topology_fingerprint,
            "enabled": self._time_on_target_enabled,
            "missions": copy.deepcopy(self._time_on_target_state),
            "resource_observations": [
                self._resource_key_record(
                    key,
                    self._resource_observation(weapon),
                )
                for key, weapon in planned_weapons.items()
            ],
            "rng_state": copy.deepcopy(self._rng.bit_generator.state),
        }

    @staticmethod
    def _validate_resource_record(
        record: Any,
    ) -> tuple[tuple[str, int, str], dict[str, Any]]:
        if not isinstance(record, dict):
            raise ValueError("Resource observation must be a mapping")
        expected_keys = {
            "unit_id",
            "source_equipment_index",
            "weapon_id",
            "ammunition_by_type",
            "total_rounds_fired",
            "rounds_since_maintenance",
            "last_fire_time_s",
        }
        if set(record) != expected_keys:
            raise ValueError(
                "Resource observation key topology is invalid",
            )
        unit_id = record["unit_id"]
        source_index = record["source_equipment_index"]
        weapon_id = record["weapon_id"]
        if (
            not isinstance(unit_id, str)
            or not unit_id
            or isinstance(source_index, bool)
            or not isinstance(source_index, int)
            or source_index < 0
            or not isinstance(weapon_id, str)
            or not weapon_id
        ):
            raise ValueError("Resource observation identity is invalid")
        ammunition = record["ammunition_by_type"]
        if not isinstance(ammunition, dict) or any(
            not isinstance(ammo_id, str)
            or not ammo_id
            or isinstance(rounds, bool)
            or not isinstance(rounds, int)
            or rounds < 0
            for ammo_id, rounds in ammunition.items()
        ):
            raise ValueError("Resource ammunition observation is invalid")
        for field_name in (
            "total_rounds_fired",
            "rounds_since_maintenance",
        ):
            value = record[field_name]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"Resource {field_name} observation is invalid",
                )
        last_fire = record["last_fire_time_s"]
        if last_fire is not None and (
            isinstance(last_fire, bool)
            or not isinstance(last_fire, (int, float))
            or not math.isfinite(float(last_fire))
            or float(last_fire) < 0.0
        ):
            raise ValueError(
                "Resource last_fire_time_s observation is invalid",
            )
        observation = {
            key: copy.deepcopy(value)
            for key, value in record.items()
            if key not in {
                "unit_id",
                "source_equipment_index",
                "weapon_id",
            }
        }
        if last_fire is not None:
            observation["last_fire_time_s"] = float(last_fire)
        return (unit_id, source_index, weapon_id), observation

    @staticmethod
    def _validate_fired_resource_delta(
        state: Mapping[str, Any],
        battery: ResolvedTimeOnTargetBattery,
    ) -> None:
        before = state["resource_before"]
        after = state["resource_after"]
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ValueError("Fired battery resource snapshots are required")
        ammo_id = battery.ammunition.ammo_id
        expected_ammunition = dict(before["ammunition_by_type"])
        if ammo_id not in expected_ammunition:
            raise ValueError(
                "Fired battery resource snapshot lacks planned ammunition",
            )
        expected_ammunition[ammo_id] -= battery.rounds
        if expected_ammunition[ammo_id] < 0:
            raise ValueError("Fired battery resource snapshot overdraws ammo")
        if after["ammunition_by_type"] != expected_ammunition:
            raise ValueError("Fired battery ammunition delta is inconsistent")
        if (
            after["total_rounds_fired"]
            != before["total_rounds_fired"] + battery.rounds
            or after["rounds_since_maintenance"]
            != before["rounds_since_maintenance"] + battery.rounds
            or after["last_fire_time_s"]
            != battery.scheduled_fire_time_s
        ):
            raise ValueError("Fired battery live-state delta is inconsistent")

    @classmethod
    def _validate_resource_snapshot(
        cls,
        value: Any,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("Battery resource snapshot must be a mapping")
        _key, observation = cls._validate_resource_record({
            "unit_id": "__snapshot__",
            "source_equipment_index": 0,
            "weapon_id": "__snapshot__",
            **value,
        })
        return observation

    @staticmethod
    def _validate_precondition_snapshot(
        value: Any,
    ) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != {
            "unit_status",
            "unit_position",
            "unit_speed_mps",
            "equipment_condition",
            "equipment_operational",
        }:
            raise ValueError(
                "Indirect-fire precondition snapshot is malformed",
            )
        if value["unit_status"] not in UnitStatus.__members__:
            raise ValueError(
                "Indirect-fire precondition unit status is invalid",
            )
        position = value["unit_position"]
        if (
            not isinstance(position, (list, tuple))
            or len(position) != 3
            or any(
                isinstance(component, bool)
                or not isinstance(component, (int, float))
                or not math.isfinite(float(component))
                for component in position
            )
        ):
            raise ValueError(
                "Indirect-fire precondition position is invalid",
            )
        speed = value["unit_speed_mps"]
        if (
            isinstance(speed, bool)
            or not isinstance(speed, (int, float))
            or not math.isfinite(float(speed))
            or float(speed) < 0.0
        ):
            raise ValueError(
                "Indirect-fire precondition speed is invalid",
            )
        condition = value["equipment_condition"]
        if (
            isinstance(condition, bool)
            or not isinstance(condition, (int, float))
            or not math.isfinite(float(condition))
            or not 0.0 <= float(condition) <= 1.0
            or not isinstance(value["equipment_operational"], bool)
        ):
            raise ValueError(
                "Indirect-fire precondition equipment state is invalid",
            )
        return {
            "unit_status": value["unit_status"],
            "unit_position": [
                float(component)
                for component in position
            ],
            "unit_speed_mps": float(speed),
            "equipment_condition": float(condition),
            "equipment_operational": value["equipment_operational"],
        }

    @staticmethod
    def _snapshot_rejection_reason(
        battery: ResolvedTimeOnTargetBattery,
        precondition: Mapping[str, Any],
        resources: Mapping[str, Any],
    ) -> str:
        if precondition["unit_status"] != "ACTIVE":
            return "battery_inactive"
        if (
            battery.weapon.definition.requires_deployed
            and precondition["unit_speed_mps"] > 0.5
        ):
            return "battery_moving"
        if tuple(precondition["unit_position"]) != tuple(
            battery.planned_fire_position,
        ):
            return "battery_displaced"
        if (
            not precondition["equipment_operational"]
            or precondition["equipment_condition"] <= 0.0
        ):
            return "weapon_inoperable"
        if (
            resources["ammunition_by_type"].get(
                battery.ammunition.ammo_id,
                0,
            )
            < battery.rounds
        ):
            return "insufficient_ammunition"
        last_fire_time_s = resources["last_fire_time_s"]
        if (
            last_fire_time_s is not None
            and (
                battery.scheduled_fire_time_s - last_fire_time_s
                < battery.weapon.cooldown_s * battery.rounds
            )
        ):
            return "weapon_cooldown"
        return ""

    @staticmethod
    def _validate_external_resource_transition(
        prior: Mapping[str, Any],
        current: Mapping[str, Any],
        *,
        processed_time_s: float,
        weapon: WeaponInstance,
        minimum_fire_time_s: float | None = None,
    ) -> None:
        """Validate one monotonic external live-fire transition within bounds."""
        prior_ammunition = prior["ammunition_by_type"]
        current_ammunition = current["ammunition_by_type"]
        if set(current_ammunition) != set(prior_ammunition):
            raise ValueError(
                "External indirect-fire resource ammunition topology changed",
            )
        if any(
            current_ammunition[ammo_id] > prior_rounds
            for ammo_id, prior_rounds in prior_ammunition.items()
        ):
            raise ValueError(
                "External indirect-fire resource ammunition increased",
            )
        ammunition_delta = sum(
            prior_rounds - current_ammunition[ammo_id]
            for ammo_id, prior_rounds in prior_ammunition.items()
        )
        total_delta = (
            current["total_rounds_fired"]
            - prior["total_rounds_fired"]
        )
        maintenance_delta = (
            current["rounds_since_maintenance"]
            - prior["rounds_since_maintenance"]
        )
        last_fire = current["last_fire_time_s"]
        prior_last_fire = prior["last_fire_time_s"]
        required_gap_s = weapon.cooldown_s * ammunition_delta
        if (
            ammunition_delta <= 0
            or total_delta != ammunition_delta
            or maintenance_delta != ammunition_delta
            or last_fire is None
            or last_fire > processed_time_s
            or (
                minimum_fire_time_s is not None
                and last_fire < minimum_fire_time_s
            )
            or (
                prior_last_fire is not None
                and (
                    last_fire <= prior_last_fire
                    or last_fire - prior_last_fire < required_gap_s
                )
            )
        ):
            raise ValueError(
                "External indirect-fire resource transition is impossible",
            )

    @staticmethod
    def _checkpoint_values_equal(left: Any, right: Any) -> bool:
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            return set(left) == set(right) and all(
                IndirectFireEngine._checkpoint_values_equal(
                    left[key],
                    right[key],
                )
                for key in left
            )
        if (
            isinstance(left, (list, tuple))
            and isinstance(right, (list, tuple))
        ):
            return len(left) == len(right) and all(
                IndirectFireEngine._checkpoint_values_equal(
                    left_item,
                    right_item,
                )
                for left_item, right_item in zip(
                    left,
                    right,
                    strict=True,
                )
            )
        return type(left) is type(right) and bool(left == right)

    def _validate_terminal_result(
        self,
        mission: ResolvedTimeOnTargetMission,
        raw_mission: Mapping[str, Any],
    ) -> None:
        transition = raw_mission["target_transition"]
        if not isinstance(transition, dict) or set(transition) != {
            "position",
            "status_before",
            "status_after",
        }:
            raise ValueError(
                "Completed indirect-fire target transition is malformed",
            )
        target_position = transition["position"]
        if (
            not isinstance(target_position, (list, tuple))
            or len(target_position) != 3
            or any(
                isinstance(component, bool)
                or not isinstance(component, (int, float))
                or not math.isfinite(float(component))
                for component in target_position
            )
            or transition["status_before"] not in UnitStatus.__members__
            or transition["status_after"] not in UnitStatus.__members__
        ):
            raise ValueError(
                "Completed indirect-fire target transition is invalid",
            )

        raw_batteries = raw_mission["batteries"]
        impacts: list[ImpactPoint] = []
        radii: dict[str, float] = {}
        battery_results: list[dict[str, Any]] = []
        for battery, battery_state in zip(
            mission.batteries,
            raw_batteries,
            strict=True,
        ):
            impacts.extend(
                ImpactPoint(
                    position=Position(*impact["position"]),
                    ammo_id=impact["ammo_id"],
                )
                for impact in battery_state["impacts"]
            )
            radii[battery.ammunition.ammo_id] = (
                battery.ammunition.blast_radius_m
            )
            battery_results.append({
                "battery_id": battery.unit_id,
                "source_equipment_index": battery.source_equipment_index,
                "runtime_system_multiplier": (
                    battery.runtime_system_multiplier
                ),
                "weapon_id": battery.weapon.weapon_id,
                "ammo_id": battery.ammunition.ammo_id,
                "planned_fire_position": tuple(
                    battery.planned_fire_position,
                ),
                "actual_fire_position": tuple(
                    battery_state["actual_fire_position"],
                ),
                "scheduled_fire_time_s": battery.scheduled_fire_time_s,
                "predicted_time_of_flight_s": (
                    battery.predicted_time_of_flight_s
                ),
                "processing_time_s": battery_state["processed_time_s"],
                "status": battery_state["status"],
                "reason": battery_state["reason"],
                "rounds_fired": battery_state["rounds_fired"],
                "generated_impact_count": len(battery_state["impacts"]),
            })
        assessment = assess_indirect_fire_impacts(
            impacts,
            Position(*target_position),
            radii,
            prior_near_impact_count=0,
            terrain_modifier=1.0,
            casualty_per_impact=0.15,
            destruction_threshold=self._destruction_threshold,
            disable_threshold=self._disable_threshold,
        )
        status_before = transition["status_before"]
        if status_before != "ACTIVE":
            expected_effect = "target_inactive"
            expected_status_after = status_before
        elif assessment.near_impact_count == 0:
            expected_effect = "missed"
            expected_status_after = "ACTIVE"
        elif assessment.resulting_status is UnitStatus.DESTROYED:
            expected_effect = "destroyed"
            expected_status_after = "DESTROYED"
        elif assessment.resulting_status is UnitStatus.DISABLED:
            expected_effect = "disabled"
            expected_status_after = "DISABLED"
        else:
            expected_effect = "unchanged"
            expected_status_after = "ACTIVE"
        if transition["status_after"] != expected_status_after:
            raise ValueError(
                "Indirect-fire target transition outcome is inconsistent",
            )
        fired_count = sum(
            battery_state["status"] == "fired"
            for battery_state in raw_batteries
        )
        expected_outcome = (
            "completed"
            if fired_count == len(raw_batteries)
            else "partial"
            if fired_count
            else "rejected"
        )
        expected_terminal = {
            "mission_id": mission.mission_id,
            "attacker_side": mission.attacker_side,
            "target_unit_id": mission.target_unit_id,
            "target_position": tuple(mission.target_position),
            "scheduled_impact_time_s": mission.scheduled_impact_time_s,
            "processing_time_s": mission.scheduled_impact_time_s,
            "battery_results": tuple(battery_results),
            "total_generated_impacts": len(impacts),
            "near_target_impacts": assessment.near_impact_count,
            "outcome": expected_outcome,
            "target_effect": expected_effect,
            "target_status_before": status_before,
            "target_status_after": expected_status_after,
        }
        if not self._checkpoint_values_equal(
            raw_mission["terminal_result"],
            expected_terminal,
        ):
            raise ValueError(
                "Indirect-fire terminal result does not match lifecycle",
            )

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        expected_elapsed_s: float | None = None,
        expected_combat_rng_state: dict[str, Any] | None = None,
        expected_resource_observations: (
            Sequence[Mapping[str, Any]] | None
        ) = None,
        expected_unit_statuses: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Validate checkpoint lifecycle and external authorities without mutation."""
        if not isinstance(state, dict):
            raise ValueError("Indirect-fire checkpoint state must be a mapping")
        if not self._time_on_target_missions:
            if set(state) != {"rng_state"}:
                raise ValueError(
                    "Unconfigured indirect-fire state has invalid topology",
                )
            if expected_combat_rng_state is not None and not (
                self._checkpoint_values_equal(
                    state["rng_state"],
                    expected_combat_rng_state,
                )
            ):
                raise ValueError(
                    "Indirect-fire COMBAT RNG mirror disagrees with RNGManager",
                )
            return copy.deepcopy(state)

        expected_keys = {
            "topology_fingerprint",
            "enabled",
            "missions",
            "resource_observations",
            "rng_state",
        }
        if set(state) != expected_keys:
            raise ValueError("Indirect-fire checkpoint key topology is invalid")
        if state["topology_fingerprint"] != self._topology_fingerprint:
            raise ValueError(
                "Indirect-fire checkpoint topology fingerprint mismatch",
            )
        if state["enabled"] is not self._time_on_target_enabled:
            raise ValueError("Indirect-fire checkpoint enable state mismatch")
        if expected_combat_rng_state is not None and not (
            self._checkpoint_values_equal(
                state["rng_state"],
                expected_combat_rng_state,
            )
        ):
            raise ValueError(
                "Indirect-fire COMBAT RNG mirror disagrees with RNGManager",
            )

        raw_resources = state["resource_observations"]
        if not isinstance(raw_resources, list):
            raise ValueError(
                "Indirect-fire resource observations must be a list",
            )
        resources: dict[tuple[str, int, str], dict[str, Any]] = {}
        resource_keys: list[tuple[str, int, str]] = []
        for raw_record in raw_resources:
            key, observation = self._validate_resource_record(raw_record)
            if key in resources:
                raise ValueError(
                    f"Duplicate indirect-fire resource observation {key!r}",
                )
            resources[key] = observation
            resource_keys.append(key)
        planned_keys = tuple(self._planned_weapons())
        if tuple(resource_keys) != planned_keys:
            raise ValueError(
                "Indirect-fire resource observation topology or ordering "
                "mismatch",
            )
        if expected_resource_observations is not None:
            expected_resources = dict(
                self._validate_resource_record(record)
                for record in expected_resource_observations
            )
            if resources != expected_resources:
                raise ValueError(
                    "Indirect-fire resource observations disagree with "
                    "staged live weapons",
                )

        raw_missions = state["missions"]
        if (
            not isinstance(raw_missions, list)
            or len(raw_missions) != len(self._time_on_target_missions)
        ):
            raise ValueError("Indirect-fire mission topology mismatch")
        planned_weapons = self._planned_weapons()
        transitions_by_attachment: dict[
            tuple[str, int, str],
            list[
                tuple[
                    float,
                    int,
                    int,
                    dict[str, Any],
                    dict[str, Any],
                ]
            ],
        ] = {
            key: []
            for key in planned_weapons
        }
        for mission, raw_mission in zip(
            self._time_on_target_missions,
            raw_missions,
            strict=True,
        ):
            if not isinstance(raw_mission, dict) or set(raw_mission) != {
                "mission_id",
                "status",
                "batteries",
                "terminal_result",
                "target_transition",
            }:
                raise ValueError("Indirect-fire mission state is malformed")
            if raw_mission["mission_id"] != mission.mission_id:
                raise ValueError("Indirect-fire mission identity mismatch")
            raw_batteries = raw_mission["batteries"]
            if (
                not isinstance(raw_batteries, list)
                or len(raw_batteries) != len(mission.batteries)
            ):
                raise ValueError("Indirect-fire battery topology mismatch")
            if not self._time_on_target_enabled:
                if (
                    raw_mission["status"] != "dormant"
                    or raw_mission["terminal_result"] is not None
                    or raw_mission["target_transition"] is not None
                ):
                    raise ValueError(
                        "Disabled indirect-fire mission is not pristine",
                    )
            elif raw_mission["status"] not in {"pending", "completed"}:
                raise ValueError("Invalid indirect-fire mission lifecycle")

            for battery, raw_battery in zip(
                mission.batteries,
                raw_batteries,
                strict=True,
            ):
                if not isinstance(raw_battery, dict) or set(raw_battery) != {
                    "battery_id",
                    "status",
                    "reason",
                    "processed_time_s",
                    "actual_fire_position",
                    "rounds_fired",
                    "impacts",
                    "resource_before",
                    "resource_after",
                    "precondition",
                }:
                    raise ValueError(
                        "Indirect-fire battery state is malformed",
                    )
                if raw_battery["battery_id"] != battery.unit_id:
                    raise ValueError(
                        "Indirect-fire battery identity mismatch",
                    )
                status = raw_battery["status"]
                rounds_fired = raw_battery["rounds_fired"]
                if (
                    isinstance(rounds_fired, bool)
                    or not isinstance(rounds_fired, int)
                    or rounds_fired < 0
                ):
                    raise ValueError(
                        "Indirect-fire rounds_fired is invalid",
                    )
                key = self._attachment_key(battery)
                if not self._time_on_target_enabled:
                    if raw_battery != {
                        "battery_id": battery.unit_id,
                        "status": "dormant",
                        "reason": "",
                        "processed_time_s": None,
                        "actual_fire_position": None,
                        "rounds_fired": 0,
                        "impacts": [],
                        "resource_before": None,
                        "resource_after": None,
                        "precondition": None,
                    }:
                        raise ValueError(
                            "Disabled indirect-fire battery is not pristine",
                        )
                    continue
                if status == "pending":
                    if raw_battery != {
                        "battery_id": battery.unit_id,
                        "status": "pending",
                        "reason": "",
                        "processed_time_s": None,
                        "actual_fire_position": None,
                        "rounds_fired": 0,
                        "impacts": [],
                        "resource_before": None,
                        "resource_after": None,
                        "precondition": None,
                    }:
                        raise ValueError(
                            "Pending indirect-fire battery is not pristine",
                        )
                    if (
                        expected_elapsed_s is not None
                        and battery.scheduled_fire_time_s
                        <= expected_elapsed_s
                    ):
                        raise ValueError(
                            "Pending indirect-fire milestone is already due",
                        )
                elif status in {"fired", "rejected"}:
                    processed_time = raw_battery["processed_time_s"]
                    if (
                        type(processed_time) is not float
                        or not math.isfinite(processed_time)
                        or processed_time != battery.scheduled_fire_time_s
                    ):
                        raise ValueError(
                            "Indirect-fire processing chronology mismatch",
                        )
                    if (
                        expected_elapsed_s is not None
                        and processed_time > expected_elapsed_s
                    ):
                        raise ValueError(
                            "Processed indirect-fire milestone is in the future",
                        )
                    if (
                        not isinstance(
                            raw_battery["actual_fire_position"],
                            (list, tuple),
                        )
                        or len(raw_battery["actual_fire_position"]) != 3
                    ):
                        raise ValueError(
                            "Indirect-fire transition snapshot is malformed",
                        )
                    before = self._validate_resource_snapshot(
                        raw_battery["resource_before"],
                    )
                    after = self._validate_resource_snapshot(
                        raw_battery["resource_after"],
                    )
                    precondition = self._validate_precondition_snapshot(
                        raw_battery["precondition"],
                    )
                    if (
                        not self._checkpoint_values_equal(
                            raw_battery["resource_before"],
                            before,
                        )
                        or not self._checkpoint_values_equal(
                            raw_battery["resource_after"],
                            after,
                        )
                        or not self._checkpoint_values_equal(
                            raw_battery["precondition"],
                            precondition,
                        )
                        or not self._checkpoint_values_equal(
                            raw_battery["actual_fire_position"],
                            precondition["unit_position"],
                        )
                    ):
                        raise ValueError(
                            "Indirect-fire transition snapshot is not canonical",
                        )
                    impacts = raw_battery["impacts"]
                    if not isinstance(impacts, list):
                        raise ValueError(
                            "Indirect-fire impacts must be a list",
                        )
                    for impact in impacts:
                        if (
                            not isinstance(impact, dict)
                            or set(impact) != {"position", "ammo_id"}
                            or impact["ammo_id"]
                            != battery.ammunition.ammo_id
                            or not isinstance(
                                impact["position"],
                                (list, tuple),
                            )
                            or len(impact["position"]) != 3
                            or any(
                                isinstance(component, bool)
                                or not isinstance(
                                    component,
                                    (int, float),
                                )
                                or not math.isfinite(float(component))
                                for component in impact["position"]
                            )
                        ):
                            raise ValueError(
                                "Indirect-fire impact snapshot is invalid",
                            )
                    rejection_reason = self._snapshot_rejection_reason(
                        battery,
                        precondition,
                        before,
                    )
                    if status == "fired":
                        if (
                            raw_battery["reason"] != ""
                            or rejection_reason
                            or raw_battery["rounds_fired"] != battery.rounds
                            or len(impacts) != battery.rounds
                        ):
                            raise ValueError(
                                "Fired indirect-fire lifecycle is inconsistent",
                            )
                        self._validate_fired_resource_delta(
                            raw_battery,
                            battery,
                        )
                    else:
                        if (
                            not rejection_reason
                            or raw_battery["reason"] != rejection_reason
                            or raw_battery["rounds_fired"] != 0
                            or impacts
                            or before != after
                        ):
                            raise ValueError(
                                "Rejected indirect-fire lifecycle is inconsistent",
                            )
                    transitions_by_attachment[key].append((
                        processed_time,
                        mission.declaration_index,
                        battery.declaration_index,
                        before,
                        after,
                    ))
                else:
                    raise ValueError("Invalid indirect-fire battery lifecycle")

            if self._time_on_target_enabled:
                completed = raw_mission["status"] == "completed"
                if completed:
                    if any(
                        battery_state["status"]
                        not in {"fired", "rejected"}
                        for battery_state in raw_batteries
                    ):
                        raise ValueError(
                            "Completed indirect-fire mission has a "
                            "pending battery",
                        )
                    if (
                        expected_elapsed_s is not None
                        and mission.scheduled_impact_time_s
                        > expected_elapsed_s
                    ):
                        raise ValueError(
                            "Completed indirect-fire mission is in the future",
                        )
                    terminal = raw_mission["terminal_result"]
                    if (
                        not isinstance(terminal, dict)
                        or terminal.get("mission_id") != mission.mission_id
                        or terminal.get("scheduled_impact_time_s")
                        != mission.scheduled_impact_time_s
                        or terminal.get("processing_time_s")
                        != mission.scheduled_impact_time_s
                    ):
                        raise ValueError(
                            "Indirect-fire terminal result is inconsistent",
                        )
                    self._validate_terminal_result(
                        mission,
                        raw_mission,
                    )
                    if expected_unit_statuses is not None:
                        staged_status = expected_unit_statuses.get(
                            mission.target_unit_id,
                        )
                        terminal_after = raw_mission[
                            "target_transition"
                        ]["status_after"]
                        if (
                            terminal_after == "DESTROYED"
                            and staged_status != "DESTROYED"
                        ):
                            raise ValueError(
                                "Destroyed TOT target checkpoint regressed",
                            )
                        if (
                            terminal_after == "DISABLED"
                            and staged_status
                            not in {"DISABLED", "DESTROYED"}
                        ):
                            raise ValueError(
                                "Disabled TOT target checkpoint regressed",
                            )
                        if (
                            terminal_after == "SURRENDERED"
                            and staged_status
                            not in {"SURRENDERED", "DESTROYED"}
                        ):
                            raise ValueError(
                                "Surrendered TOT target checkpoint regressed",
                            )
                else:
                    if (
                        raw_mission["terminal_result"] is not None
                        or raw_mission["target_transition"] is not None
                    ):
                        raise ValueError(
                            "Pending indirect-fire mission has terminal state",
                        )
                    if (
                        expected_elapsed_s is not None
                        and mission.scheduled_impact_time_s
                        <= expected_elapsed_s
                    ):
                        raise ValueError(
                            "Pending indirect-fire impact is already due",
                        )
        for key, transitions in transitions_by_attachment.items():
            expected_observation = self._initial_resource_observations[key]
            latest_processed_time_s = 0.0
            for (
                processed_time,
                _mission_index,
                _battery_index,
                before,
                after,
            ) in sorted(transitions):
                if before != expected_observation:
                    self._validate_external_resource_transition(
                        expected_observation,
                        before,
                        processed_time_s=processed_time,
                        weapon=planned_weapons[key],
                        minimum_fire_time_s=latest_processed_time_s,
                    )
                expected_observation = after
                latest_processed_time_s = processed_time
            if resources[key] != expected_observation:
                if expected_elapsed_s is None:
                    raise ValueError(
                        "Indirect-fire lifecycle disagrees with live resource "
                        f"history for {key!r}",
                    )
                self._validate_external_resource_transition(
                    expected_observation,
                    resources[key],
                    processed_time_s=expected_elapsed_s,
                    weapon=planned_weapons[key],
                    minimum_fire_time_s=latest_processed_time_s,
                )
        return copy.deepcopy(state)

    def commit_state(self, staged_state: dict[str, Any]) -> None:
        """Commit a state previously accepted by :meth:`stage_state`."""
        if self._time_on_target_missions:
            self._time_on_target_state = copy.deepcopy(
                staged_state["missions"],
            )

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore direct-engine state, including its compatibility RNG mirror."""
        expected_resources = None
        if self._time_on_target_missions:
            expected_resources = [
                self._resource_key_record(
                    key,
                    self._resource_observation(weapon),
                )
                for key, weapon in self._planned_weapons().items()
            ]
        staged = self.stage_state(
            state,
            expected_combat_rng_state=state.get("rng_state"),
            expected_resource_observations=expected_resources,
        )
        self._rng.bit_generator.state = copy.deepcopy(state["rng_state"])
        self.commit_state(staged)

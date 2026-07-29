"""Production resolution boundary for preplanned time-on-target missions."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from stochastic_warfare.combat.ammunition import (
    AmmoDefinition,
    AmmoType,
    WeaponCategory,
    WeaponInstance,
)
from stochastic_warfare.combat.indirect_fire_config import (
    IndirectFireScenarioConfig,
    ResolvedTimeOnTargetBattery,
    ResolvedTimeOnTargetMission,
    TimeOnTargetBatteryConfig,
    TimeOnTargetMissionConfig,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.loadouts import RuntimeLoadouts, WeaponAttachment
from stochastic_warfare.terrain.heightmap import Heightmap


class TimeOnTargetResolutionError(ValueError):
    """Raised when a declared mission cannot resolve to exact live topology."""


@dataclass(frozen=True, slots=True)
class _ScheduledAttachmentFire:
    mission_id: str
    battery_id: str
    mission_index: int
    battery_index: int
    scheduled_fire_time_s: float
    rounds: int
    weapon: WeaponInstance


def _unit_side(unit: Unit) -> str:
    side = unit.side
    return side.value if hasattr(side, "value") else side


def _require_finite_position(position: Position, *, label: str) -> Position:
    if not all(
        isinstance(component, (int, float)) and not isinstance(component, bool) and math.isfinite(float(component))
        for component in position
    ):
        raise TimeOnTargetResolutionError(
            f"{label} must contain three finite numbers",
        )
    return Position(
        float(position.easting),
        float(position.northing),
        float(position.altitude),
    )


class TimeOnTargetMissionResolver:
    """Resolve strict declarations against one exact initial runtime loadout."""

    @classmethod
    def resolve(
        cls,
        config: IndirectFireScenarioConfig,
        *,
        units_by_side: Mapping[str, Sequence[Unit]],
        runtime_loadouts: RuntimeLoadouts,
        terrain: Heightmap,
        duration_hours: float,
        tick_duration_seconds: float | None,
    ) -> tuple[ResolvedTimeOnTargetMission, ...]:
        """Return immutable plans or raise before a context can be published."""
        if not config.time_on_target_missions:
            return ()

        duration_s, cadence_s = cls._validate_scenario_timing(
            duration_hours=duration_hours,
            tick_duration_seconds=tick_duration_seconds,
        )
        roster, roster_sides = cls._index_roster(units_by_side)
        if set(runtime_loadouts.unit_weapons) != set(roster):
            missing = sorted(set(roster) - set(runtime_loadouts.unit_weapons))
            unexpected = sorted(set(runtime_loadouts.unit_weapons) - set(roster))
            raise TimeOnTargetResolutionError(
                "RuntimeLoadouts unit roster does not match the initial force "
                f"roster; missing={missing!r}, unexpected={unexpected!r}",
            )

        resolved_missions: list[ResolvedTimeOnTargetMission] = []
        requested_ammunition: defaultdict[
            tuple[str, int, str, str],
            int,
        ] = defaultdict(int)
        ammunition_sources: dict[
            tuple[str, int, str, str],
            WeaponInstance,
        ] = {}
        fires_by_attachment: defaultdict[
            tuple[str, int, str],
            list[_ScheduledAttachmentFire],
        ] = defaultdict(list)

        for mission_index, mission in enumerate(
            config.time_on_target_missions,
        ):
            cls._validate_mission_schedule(
                mission,
                duration_s=duration_s,
                cadence_s=cadence_s,
            )
            target = cls._require_unit(
                roster,
                mission.target_unit_id,
                role=f"mission {mission.mission_id!r} target",
            )
            if target.status is not UnitStatus.ACTIVE:
                raise TimeOnTargetResolutionError(
                    f"mission {mission.mission_id!r} target {target.entity_id!r} must initially be ACTIVE",
                )

            target_position = mission.target_position.to_position()
            if not terrain.in_bounds(target_position):
                raise TimeOnTargetResolutionError(
                    f"mission {mission.mission_id!r} target_position "
                    f"{tuple(target_position)!r} lies outside loaded terrain "
                    f"bounds {terrain.extent!r}",
                )

            battery_sides = {roster_sides.get(battery.unit_id) for battery in mission.batteries}
            if None in battery_sides:
                missing_ids = sorted(
                    battery.unit_id for battery in mission.batteries if battery.unit_id not in roster_sides
                )
                raise TimeOnTargetResolutionError(
                    f"mission {mission.mission_id!r} references unknown battery unit(s) {missing_ids!r}",
                )
            if len(battery_sides) != 1:
                raise TimeOnTargetResolutionError(
                    f"mission {mission.mission_id!r} batteries must all belong to one scenario side",
                )
            attacker_side = next(iter(battery_sides))
            if attacker_side is None:
                raise TimeOnTargetResolutionError(
                    f"mission {mission.mission_id!r} has no attacker side",
                )
            if roster_sides[target.entity_id] == attacker_side:
                raise TimeOnTargetResolutionError(
                    f"mission {mission.mission_id!r} target {target.entity_id!r} is friendly to side {attacker_side!r}",
                )

            resolved_batteries: list[ResolvedTimeOnTargetBattery] = []
            for battery_index, battery in enumerate(mission.batteries):
                unit = cls._require_unit(
                    roster,
                    battery.unit_id,
                    role=f"mission {mission.mission_id!r} battery",
                )
                if unit.status is not UnitStatus.ACTIVE:
                    raise TimeOnTargetResolutionError(
                        f"mission {mission.mission_id!r} battery {unit.entity_id!r} must initially be ACTIVE",
                    )
                attachment, ammunition = cls._resolve_attachment(
                    mission=mission,
                    battery=battery,
                    unit=unit,
                    runtime_loadouts=runtime_loadouts,
                )
                cls._validate_weapon_and_solution(
                    mission=mission,
                    battery=battery,
                    unit=unit,
                    target=target,
                    target_position=target_position,
                    attachment=attachment,
                    ammunition=ammunition,
                )

                scheduled_fire_time_s = mission.impact_time_s - battery.time_of_flight_s
                planned_fire_position = _require_finite_position(
                    unit.position,
                    label=(f"mission {mission.mission_id!r} battery {unit.entity_id!r} position"),
                )
                resolved_battery = ResolvedTimeOnTargetBattery(
                    declaration_index=battery_index,
                    unit_id=unit.entity_id,
                    unit=unit,
                    source_equipment_index=battery.source_equipment_index,
                    runtime_system_multiplier=(attachment.runtime_system_multiplier),
                    weapon=attachment.weapon,
                    ammunition=ammunition,
                    planned_fire_position=planned_fire_position,
                    scheduled_fire_time_s=scheduled_fire_time_s,
                    predicted_time_of_flight_s=battery.time_of_flight_s,
                    rounds=mission.rounds_per_battery,
                )
                resolved_batteries.append(resolved_battery)

                ammo_key = (
                    unit.entity_id,
                    battery.source_equipment_index,
                    attachment.weapon.weapon_id,
                    ammunition.ammo_id,
                )
                requested_ammunition[ammo_key] += mission.rounds_per_battery
                ammunition_sources[ammo_key] = attachment.weapon

                attachment_key = (
                    unit.entity_id,
                    battery.source_equipment_index,
                    attachment.weapon.weapon_id,
                )
                fires_by_attachment[attachment_key].append(
                    _ScheduledAttachmentFire(
                        mission_id=mission.mission_id,
                        battery_id=unit.entity_id,
                        mission_index=mission_index,
                        battery_index=battery_index,
                        scheduled_fire_time_s=scheduled_fire_time_s,
                        rounds=mission.rounds_per_battery,
                        weapon=attachment.weapon,
                    ),
                )

            resolved_missions.append(
                ResolvedTimeOnTargetMission(
                    declaration_index=mission_index,
                    mission_id=mission.mission_id,
                    attacker_side=attacker_side,
                    target_unit_id=target.entity_id,
                    target_unit=target,
                    target_position=target_position,
                    scheduled_impact_time_s=mission.impact_time_s,
                    rounds_per_battery=mission.rounds_per_battery,
                    batteries=tuple(resolved_batteries),
                ),
            )

        cls._validate_aggregate_ammunition(
            requested_ammunition=requested_ammunition,
            ammunition_sources=ammunition_sources,
        )
        cls._validate_aggregate_cooldowns(fires_by_attachment)
        return tuple(resolved_missions)

    @staticmethod
    def _validate_scenario_timing(
        *,
        duration_hours: float,
        tick_duration_seconds: float | None,
    ) -> tuple[float, int]:
        if (
            isinstance(duration_hours, bool)
            or not isinstance(duration_hours, (int, float))
            or not math.isfinite(float(duration_hours))
            or duration_hours <= 0.0
        ):
            raise TimeOnTargetResolutionError(
                "duration_hours must be a finite positive number",
            )
        if (
            isinstance(tick_duration_seconds, bool)
            or not isinstance(tick_duration_seconds, (int, float))
            or not math.isfinite(float(tick_duration_seconds))
            or tick_duration_seconds <= 0.0
            or not float(tick_duration_seconds).is_integer()
        ):
            raise TimeOnTargetResolutionError(
                "declared time-on-target missions require a finite positive whole-second tick_duration_seconds",
            )
        return float(duration_hours) * 3600.0, int(tick_duration_seconds)

    @staticmethod
    def _validate_mission_schedule(
        mission: TimeOnTargetMissionConfig,
        *,
        duration_s: float,
        cadence_s: int,
    ) -> None:
        impact_time_s = int(mission.impact_time_s)
        if mission.impact_time_s > duration_s:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} impact_time_s "
                f"{mission.impact_time_s} exceeds scenario duration "
                f"{duration_s}",
            )
        if impact_time_s % cadence_s:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} impact_time_s "
                f"{impact_time_s} is not aligned to the "
                f"{cadence_s}-second scenario cadence",
            )
        for battery in mission.batteries:
            fire_time_s = int(
                mission.impact_time_s - battery.time_of_flight_s,
            )
            if fire_time_s % cadence_s:
                raise TimeOnTargetResolutionError(
                    f"mission {mission.mission_id!r} battery "
                    f"{battery.unit_id!r} fire time {fire_time_s} is not "
                    f"aligned to the {cadence_s}-second scenario cadence",
                )

    @staticmethod
    def _index_roster(
        units_by_side: Mapping[str, Sequence[Unit]],
    ) -> tuple[dict[str, Unit], dict[str, str]]:
        roster: dict[str, Unit] = {}
        roster_sides: dict[str, str] = {}
        for side, units in units_by_side.items():
            if not isinstance(side, str) or not side or side != side.strip():
                raise TimeOnTargetResolutionError(
                    "initial force roster side IDs must be non-empty trimmed strings",
                )
            for unit in units:
                unit_id = unit.entity_id
                if unit_id in roster:
                    raise TimeOnTargetResolutionError(
                        f"initial force roster contains duplicate unit ID {unit_id!r}",
                    )
                if _unit_side(unit) != side:
                    raise TimeOnTargetResolutionError(
                        f"unit {unit_id!r} side {_unit_side(unit)!r} does not match roster side {side!r}",
                    )
                roster[unit_id] = unit
                roster_sides[unit_id] = side
        return roster, roster_sides

    @staticmethod
    def _require_unit(
        roster: Mapping[str, Unit],
        unit_id: str,
        *,
        role: str,
    ) -> Unit:
        try:
            return roster[unit_id]
        except KeyError as exc:
            raise TimeOnTargetResolutionError(
                f"{role} references unknown unit {unit_id!r}",
            ) from exc

    @staticmethod
    def _resolve_attachment(
        *,
        mission: TimeOnTargetMissionConfig,
        battery: TimeOnTargetBatteryConfig,
        unit: Unit,
        runtime_loadouts: RuntimeLoadouts,
    ) -> tuple[WeaponAttachment, AmmoDefinition]:
        attachments = runtime_loadouts.unit_weapons[unit.entity_id]
        matches = [
            attachment
            for attachment in attachments
            if (attachment.source_equipment_index == battery.source_equipment_index)
        ]
        if len(matches) != 1:
            detail = "unknown" if not matches else "ambiguous"
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                f"has {detail} source_equipment_index "
                f"{battery.source_equipment_index}",
            )
        attachment = matches[0]
        source_index = battery.source_equipment_index
        if source_index >= len(unit.equipment) or attachment.source_equipment is not unit.equipment[source_index]:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                "attachment does not retain the exact source equipment object",
            )
        if attachment.weapon.weapon_id != battery.weapon_id:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                f"source index {source_index} resolves weapon "
                f"{attachment.weapon.weapon_id!r}, not declared "
                f"{battery.weapon_id!r}",
            )
        ammunition_matches = [
            ammunition for ammunition in attachment.ammunition if ammunition.ammo_id == battery.ammo_id
        ]
        if len(ammunition_matches) != 1:
            detail = "unknown" if not ammunition_matches else "ambiguous"
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                f"has {detail} ammunition {battery.ammo_id!r} on source "
                f"index {source_index}",
            )
        return attachment, ammunition_matches[0]

    @staticmethod
    def _validate_weapon_and_solution(
        *,
        mission: TimeOnTargetMissionConfig,
        battery: TimeOnTargetBatteryConfig,
        unit: Unit,
        target: Unit,
        target_position: Position,
        attachment: WeaponAttachment,
        ammunition: AmmoDefinition,
    ) -> None:
        weapon = attachment.weapon
        try:
            category = weapon.definition.parsed_category()
        except (KeyError, ValueError) as exc:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                f"has invalid weapon category "
                f"{weapon.definition.category!r}",
            ) from exc
        supported_categories = {
            WeaponCategory.HOWITZER,
            WeaponCategory.MORTAR,
            WeaponCategory.ARTILLERY,
        }
        if category not in supported_categories:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                f"uses unsupported time-on-target weapon category "
                f"{category.name}",
            )

        target_domain = target.domain.name
        if target_domain not in weapon.definition.effective_target_domains():
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} weapon "
                f"{weapon.weapon_id!r} cannot engage target domain "
                f"{target_domain}",
            )
        if ammunition.ammo_id not in weapon.definition.compatible_ammo:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} ammunition "
                f"{ammunition.ammo_id!r} is incompatible with weapon "
                f"{weapon.weapon_id!r}",
            )
        try:
            ammunition_type = ammunition.parsed_ammo_type()
        except (KeyError, ValueError) as exc:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} ammunition "
                f"{ammunition.ammo_id!r} has invalid type "
                f"{ammunition.ammo_type!r}",
            ) from exc
        if ammunition_type in {AmmoType.SMOKE, AmmoType.ILLUMINATION}:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} ammunition {ammunition.ammo_id!r} is non-damaging and unsupported",
            )
        if not math.isfinite(ammunition.blast_radius_m) or ammunition.blast_radius_m <= 0.0:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} ammunition "
                f"{ammunition.ammo_id!r} requires a finite positive "
                "blast_radius_m",
            )

        rounds = mission.rounds_per_battery
        if rounds > attachment.runtime_system_multiplier:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} requests {rounds} "
                f"simultaneous rounds from battery {unit.entity_id!r}, "
                "exceeding runtime_system_multiplier "
                f"{attachment.runtime_system_multiplier}",
            )
        available = weapon.ammo_state.available(ammunition.ammo_id)
        if available < rounds:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                f"has {available} {ammunition.ammo_id!r} rounds but "
                f"requires {rounds}",
            )

        battery_position = _require_finite_position(
            unit.position,
            label=(f"mission {mission.mission_id!r} battery {unit.entity_id!r} position"),
        )
        horizontal_distance_m = math.hypot(
            target_position.easting - battery_position.easting,
            target_position.northing - battery_position.northing,
        )
        minimum_range_m = weapon.definition.min_range_m
        maximum_range_m = weapon.definition.max_range_m
        if (
            not math.isfinite(minimum_range_m)
            or minimum_range_m < 0.0
            or not math.isfinite(maximum_range_m)
            or maximum_range_m <= 0.0
        ):
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} weapon {weapon.weapon_id!r} has invalid declared range bounds",
            )
        if not minimum_range_m <= horizontal_distance_m <= maximum_range_m:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                f"horizontal range {horizontal_distance_m:.6g} m lies "
                f"outside weapon bounds [{minimum_range_m:.6g}, "
                f"{maximum_range_m:.6g}] m",
            )

        speed_bounds = [
            float(speed)
            for speed in (
                weapon.definition.muzzle_velocity_mps,
                ammunition.max_speed_mps,
            )
            if math.isfinite(speed) and speed > 0.0
        ]
        if not speed_bounds:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} weapon/ammunition "
                f"{weapon.weapon_id!r}/{ammunition.ammo_id!r} has no finite "
                "positive projectile-speed bound",
            )
        three_dimensional_distance_m = math.dist(
            tuple(battery_position),
            tuple(target_position),
        )
        physical_lower_bound_s = three_dimensional_distance_m / max(speed_bounds)
        if battery.time_of_flight_s < physical_lower_bound_s:
            raise TimeOnTargetResolutionError(
                f"mission {mission.mission_id!r} battery {unit.entity_id!r} "
                f"time_of_flight_s={battery.time_of_flight_s:g} is shorter "
                f"than physical lower bound {physical_lower_bound_s:.6g} s",
            )

    @staticmethod
    def _validate_aggregate_ammunition(
        *,
        requested_ammunition: Mapping[tuple[str, int, str, str], int],
        ammunition_sources: Mapping[
            tuple[str, int, str, str],
            WeaponInstance,
        ],
    ) -> None:
        for key in sorted(requested_ammunition):
            requested = requested_ammunition[key]
            weapon = ammunition_sources[key]
            ammunition_id = key[3]
            available = weapon.ammo_state.available(ammunition_id)
            if requested > available:
                raise TimeOnTargetResolutionError(
                    "time-on-target missions aggregate-overbook attachment "
                    f"{key[:3]!r} ammunition {ammunition_id!r}: "
                    f"requested={requested}, available={available}",
                )

    @staticmethod
    def _validate_aggregate_cooldowns(
        fires_by_attachment: Mapping[
            tuple[str, int, str],
            Sequence[_ScheduledAttachmentFire],
        ],
    ) -> None:
        for attachment_key in sorted(fires_by_attachment):
            scheduled = sorted(
                fires_by_attachment[attachment_key],
                key=lambda fire: (
                    fire.scheduled_fire_time_s,
                    fire.mission_index,
                    fire.battery_index,
                ),
            )
            for previous, current in zip(scheduled, scheduled[1:], strict=False):
                authored_gap_s = current.scheduled_fire_time_s - previous.scheduled_fire_time_s
                required_gap_s = current.weapon.cooldown_s * current.rounds
                if authored_gap_s < required_gap_s:
                    raise TimeOnTargetResolutionError(
                        "time-on-target missions violate quantity-aware "
                        f"cooldown for attachment {attachment_key!r}: "
                        f"{previous.mission_id!r} fires at "
                        f"{previous.scheduled_fire_time_s:g}s and "
                        f"{current.mission_id!r} fires at "
                        f"{current.scheduled_fire_time_s:g}s; "
                        f"gap={authored_gap_s:g}s, "
                        f"required={required_gap_s:g}s",
                    )


__all__ = [
    "TimeOnTargetMissionResolver",
    "TimeOnTargetResolutionError",
]

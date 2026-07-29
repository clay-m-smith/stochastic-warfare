"""Strict configuration and immutable plans for scheduled indirect fire.

Scenario-facing declarations live here so the combat layer owns the contract
it executes.  The simulation-layer resolver is the only boundary that may
translate those declarations and runtime loadouts into the resolved records
below.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from stochastic_warfare.combat.ammunition import AmmoDefinition, WeaponInstance
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit


def _require_trimmed_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    return value


def _require_finite_position(position: Position, field_name: str) -> None:
    if not all(
        isinstance(component, (int, float)) and not isinstance(component, bool) and math.isfinite(float(component))
        for component in position
    ):
        raise ValueError(f"{field_name} must contain three finite numbers")


def _unit_side(unit: Unit) -> str:
    value = unit.side
    return value.value if hasattr(value, "value") else value


class TimeOnTargetPositionConfig(BaseModel):
    """One explicit internal ENU target point in metres."""

    model_config = ConfigDict(extra="forbid", strict=True)

    easting: float = Field(strict=True, allow_inf_nan=False)
    northing: float = Field(strict=True, allow_inf_nan=False)
    altitude: float = Field(strict=True, allow_inf_nan=False)

    def to_position(self) -> Position:
        """Return the lower-layer immutable ENU position."""
        return Position(self.easting, self.northing, self.altitude)


class TimeOnTargetBatteryConfig(BaseModel):
    """One exact authored battery attachment and fire-control solution."""

    model_config = ConfigDict(extra="forbid", strict=True)

    unit_id: str
    source_equipment_index: int = Field(strict=True, ge=0)
    weapon_id: str
    ammo_id: str
    time_of_flight_s: float = Field(
        strict=True,
        gt=0.0,
        allow_inf_nan=False,
    )

    @field_validator("unit_id", "weapon_id", "ammo_id", mode="before")
    @classmethod
    def _strict_identifier(cls, value: object, info: ValidationInfo) -> str:
        return _require_trimmed_identifier(value, info.field_name)

    @field_validator("time_of_flight_s")
    @classmethod
    def _whole_second_time_of_flight(cls, value: float) -> float:
        if not value.is_integer():
            raise ValueError("time_of_flight_s must be a whole number of seconds")
        return value


class TimeOnTargetMissionConfig(BaseModel):
    """One preplanned mission sharing a common impact time."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mission_id: str
    target_unit_id: str
    target_position: TimeOnTargetPositionConfig
    impact_time_s: float = Field(
        strict=True,
        gt=0.0,
        allow_inf_nan=False,
    )
    rounds_per_battery: int = Field(strict=True, gt=0)
    batteries: list[TimeOnTargetBatteryConfig] = Field(
        min_length=1,
        max_length=6,
    )

    @field_validator("mission_id", "target_unit_id", mode="before")
    @classmethod
    def _strict_identifier(cls, value: object, info: ValidationInfo) -> str:
        return _require_trimmed_identifier(value, info.field_name)

    @field_validator("impact_time_s")
    @classmethod
    def _whole_second_impact(cls, value: float) -> float:
        if not value.is_integer():
            raise ValueError("impact_time_s must be a whole number of seconds")
        return value

    @model_validator(mode="after")
    def _unique_batteries_and_positive_fire_times(self) -> Self:
        battery_ids = [battery.unit_id for battery in self.batteries]
        if len(battery_ids) != len(set(battery_ids)):
            raise ValueError(
                f"mission {self.mission_id!r} battery unit IDs must be unique",
            )
        for battery in self.batteries:
            fire_time_s = self.impact_time_s - battery.time_of_flight_s
            if fire_time_s <= 0.0:
                raise ValueError(
                    f"mission {self.mission_id!r} battery "
                    f"{battery.unit_id!r} derives non-positive fire time "
                    f"{fire_time_s}",
                )
        return self


class IndirectFireScenarioConfig(BaseModel):
    """Strict scenario gate and declarations for scheduled indirect fire."""

    model_config = ConfigDict(extra="forbid", strict=True)

    enable_time_on_target: bool = False
    time_on_target_missions: list[TimeOnTargetMissionConfig] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def _enabled_requires_mission(self) -> Self:
        mission_ids = [mission.mission_id for mission in self.time_on_target_missions]
        if len(mission_ids) != len(set(mission_ids)):
            raise ValueError("time-on-target mission IDs must be unique")
        if self.enable_time_on_target and not self.time_on_target_missions:
            raise ValueError(
                "enable_time_on_target requires at least one mission",
            )
        return self


@dataclass(frozen=True, slots=True)
class ResolvedTimeOnTargetBattery:
    """Immutable topology plus exact live references for one battery."""

    declaration_index: int
    unit_id: str
    unit: Unit
    source_equipment_index: int
    runtime_system_multiplier: int
    weapon: WeaponInstance
    ammunition: AmmoDefinition
    planned_fire_position: Position
    scheduled_fire_time_s: float
    predicted_time_of_flight_s: float
    rounds: int

    def __post_init__(self) -> None:
        _require_trimmed_identifier(self.unit_id, "unit_id")
        if self.unit.entity_id != self.unit_id:
            raise ValueError("resolved battery unit reference does not match unit_id")
        for value, field_name in (
            (self.declaration_index, "declaration_index"),
            (self.source_equipment_index, "source_equipment_index"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for value, field_name in (
            (self.runtime_system_multiplier, "runtime_system_multiplier"),
            (self.rounds, "rounds"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.rounds > self.runtime_system_multiplier:
            raise ValueError("rounds cannot exceed runtime_system_multiplier")
        _require_finite_position(
            self.planned_fire_position,
            "planned_fire_position",
        )
        for value, field_name in (
            (self.scheduled_fire_time_s, "scheduled_fire_time_s"),
            (self.predicted_time_of_flight_s, "predicted_time_of_flight_s"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value <= 0.0
            ):
                raise ValueError(f"{field_name} must be finite and positive")
            if not float(value).is_integer():
                raise ValueError(f"{field_name} must be a whole number of seconds")
        if (
            self.source_equipment_index >= len(self.unit.equipment)
            or self.weapon.equipment is not self.unit.equipment[self.source_equipment_index]
        ):
            raise ValueError(
                "resolved battery weapon must retain the exact indexed unit equipment object",
            )
        if self.ammunition.ammo_id not in self.weapon.definition.compatible_ammo:
            raise ValueError(
                "resolved battery ammunition is incompatible with its weapon",
            )


@dataclass(frozen=True, slots=True)
class ResolvedTimeOnTargetMission:
    """Immutable resolved mission consumed by the indirect-fire engine."""

    declaration_index: int
    mission_id: str
    attacker_side: str
    target_unit_id: str
    target_unit: Unit
    target_position: Position
    scheduled_impact_time_s: float
    rounds_per_battery: int
    batteries: tuple[ResolvedTimeOnTargetBattery, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.declaration_index, int)
            or isinstance(self.declaration_index, bool)
            or self.declaration_index < 0
        ):
            raise ValueError("declaration_index must be a non-negative integer")
        if (
            not isinstance(self.rounds_per_battery, int)
            or isinstance(self.rounds_per_battery, bool)
            or self.rounds_per_battery <= 0
        ):
            raise ValueError("rounds_per_battery must be a positive integer")
        _require_trimmed_identifier(self.mission_id, "mission_id")
        _require_trimmed_identifier(self.attacker_side, "attacker_side")
        _require_trimmed_identifier(self.target_unit_id, "target_unit_id")
        if self.target_unit.entity_id != self.target_unit_id:
            raise ValueError("resolved target reference does not match target_unit_id")
        if _unit_side(self.target_unit) == self.attacker_side:
            raise ValueError("resolved mission target must be on another side")
        _require_finite_position(self.target_position, "target_position")
        if (
            isinstance(self.scheduled_impact_time_s, bool)
            or not isinstance(self.scheduled_impact_time_s, (int, float))
            or not math.isfinite(float(self.scheduled_impact_time_s))
            or self.scheduled_impact_time_s <= 0.0
        ):
            raise ValueError(
                "scheduled_impact_time_s must be finite and positive",
            )
        if not float(self.scheduled_impact_time_s).is_integer():
            raise ValueError(
                "scheduled_impact_time_s must be a whole number of seconds",
            )
        if not isinstance(self.batteries, tuple) or not 1 <= len(self.batteries) <= 6:
            raise ValueError("batteries must be a tuple containing one to six entries")
        if tuple(battery.declaration_index for battery in self.batteries) != tuple(range(len(self.batteries))):
            raise ValueError(
                "resolved batteries must retain canonical declaration ordering",
            )
        if len({battery.unit_id for battery in self.batteries}) != len(
            self.batteries,
        ):
            raise ValueError("resolved battery unit IDs must be unique")
        for battery in self.batteries:
            if battery.rounds != self.rounds_per_battery:
                raise ValueError(
                    "resolved battery round count must match its mission",
                )
            if _unit_side(battery.unit) != self.attacker_side:
                raise ValueError(
                    "all resolved batteries must belong to attacker_side",
                )
            if battery.scheduled_fire_time_s + battery.predicted_time_of_flight_s != self.scheduled_impact_time_s:
                raise ValueError(
                    "resolved battery fire time and time of flight must equal the common impact time",
                )


__all__ = [
    "IndirectFireScenarioConfig",
    "ResolvedTimeOnTargetBattery",
    "ResolvedTimeOnTargetMission",
    "TimeOnTargetBatteryConfig",
    "TimeOnTargetMissionConfig",
    "TimeOnTargetPositionConfig",
]

"""Campaign scenario configuration, context, and loading.

Defines the pydantic models for campaign scenario YAML files and the
:class:`SimulationContext` that holds all engines and state for an
in-progress simulation run.  :class:`ScenarioLoader` wires domain
modules together from a scenario definition.
"""

from __future__ import annotations

import copy
import enum
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from stochastic_warfare.combat.indirect_fire_config import (
    IndirectFireScenarioConfig,
    ResolvedTimeOnTargetMission,
)
from stochastic_warfare.c2.ai.commander import (
    CommanderAssignmentPlan,
    CommanderEngine,
    CommanderProfileLoader,
    CommanderScenarioConfig,
)
from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.strict_yaml import load_yaml_unique
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.detection.sensors import SensorInstance
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.logistics.config import (
    LogisticsConfig,
    SupplyQuantityConfig,
)
from stochastic_warfare.logistics.stockpile import DepotType
from stochastic_warfare.morale.rout import RoutConfig, RoutEngine
from stochastic_warfare.morale.runtime import (
    MoraleRegistration,
    MoraleRuntime,
)
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.deployment import (
    DeploymentConfig,
    DeploymentMode,
    FormationTemplateLoader,
    deploy_units,
    check_side_separation,
)
from stochastic_warfare.simulation.equipment_mappings import (
    EQUIPMENT_MAPPING_REGISTRY,
)
from stochastic_warfare.simulation.force_builder import (
    InitialForcePlan,
    InitialUnitConfig,
    RuntimeForceBuilder,
)
from stochastic_warfare.simulation.loadouts import (
    EquipmentResolution,
    RuntimeLoadoutBuilder,
    RuntimeLoadouts,
    WeaponAttachment,
)
from stochastic_warfare.simulation.movement_diagnostics import (
    MovementDiagnostics,
)
from stochastic_warfare.space.config import SpaceConfig
from stochastic_warfare.terrain.heightmap import Heightmap

logger = get_logger(__name__)


class ScenarioReferenceError(ValueError):
    """A typed scenario reference cannot resolve before runtime mutation."""


def _looks_like_logistics_key(value: object) -> bool:
    if not isinstance(value, str) or value == "logistics":
        return False
    normalized = value.lower().replace("-", "_")
    return normalized.startswith("logist") or normalized == "logisitics"


def _is_within_edit_distance(
    value: str,
    expected: str,
    *,
    maximum: int,
) -> bool:
    """Return whether two short normalized config keys are near matches."""
    if abs(len(value) - len(expected)) > maximum:
        return False
    previous = list(range(len(expected) + 1))
    for row, value_character in enumerate(value, start=1):
        current = [row]
        for column, expected_character in enumerate(expected, start=1):
            current.append(
                min(
                    current[column - 1] + 1,
                    previous[column] + 1,
                    previous[column - 1]
                    + (value_character != expected_character),
                ),
            )
        previous = current
    return previous[-1] <= maximum


def _looks_like_indirect_fire_key(value: object) -> bool:
    if not isinstance(value, str) or value == "indirect_fire":
        return False
    normalized = value.casefold().replace("-", "_")
    compact = "".join(character for character in normalized if character.isalnum())
    return (
        "time_on_target" in normalized
        or normalized.startswith("tot_")
        or "indirectfire" in compact
        or "timeontarget" in compact
        or "totplan" in compact
        or "totmission" in compact
        or compact in {"enabletot", "totenabled"}
        or any(
            _is_within_edit_distance(compact, expected, maximum=2)
            for expected in (
                "indirectfire",
                "enableindirectfire",
                "enabletimeontarget",
                "timeontarget",
                "timeontargetmission",
                "timeontargetmissions",
            )
        )
    )


# ---------------------------------------------------------------------------
# Pydantic config models (campaign YAML schema)
# ---------------------------------------------------------------------------


class DepotConfig(BaseModel):
    """Supply depot definition within a scenario."""

    model_config = ConfigDict(extra="forbid")

    depot_id: str
    position: list[float]  # [easting, northing]
    depot_type: str | None = None
    capacity_tons: float = 1000.0
    throughput_tons_per_hour: float = 50.0
    condition: float | None = None
    initial_inventory: list[SupplyQuantityConfig] | None = None

    @field_validator("depot_id")
    @classmethod
    def _nonempty_depot_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip() or v != v.strip():
            raise ValueError("depot_id must be a non-empty trimmed string")
        return v

    @field_validator("position", mode="before")
    @classmethod
    def _valid_position(cls, v: Any) -> list[float]:
        if not isinstance(v, (list, tuple)) or len(v) not in (2, 3):
            raise ValueError(
                "position must contain [easting, northing] and optional altitude",
            )
        if any(
            isinstance(coordinate, bool)
            or not isinstance(coordinate, (int, float))
            or not math.isfinite(float(coordinate))
            for coordinate in v
        ):
            raise ValueError("position coordinates must be finite numbers")
        return [float(coordinate) for coordinate in v]

    @field_validator("depot_type")
    @classmethod
    def _known_depot_type(cls, v: str | None) -> str | None:
        if v is not None and v not in DepotType.__members__:
            raise ValueError(
                "depot_type must be an exact DepotType name; "
                f"got {v!r}",
            )
        return v

    @field_validator(
        "capacity_tons",
        "throughput_tons_per_hour",
        mode="before",
    )
    @classmethod
    def _positive_rates(cls, v: Any, info: Any) -> float:
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(float(v))
            or float(v) <= 0.0
        ):
            raise ValueError(f"{info.field_name} must be finite and positive")
        return float(v)

    @field_validator("condition", mode="before")
    @classmethod
    def _valid_condition(cls, v: Any) -> float | None:
        if v is None:
            return None
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(float(v))
            or not 0.0 <= float(v) <= 1.0
        ):
            raise ValueError("condition must be finite and in [0, 1]")
        return float(v)

    @field_validator("initial_inventory")
    @classmethod
    def _unique_inventory_items(
        cls,
        v: list[SupplyQuantityConfig] | None,
    ) -> list[SupplyQuantityConfig] | None:
        if v is None:
            return None
        keys = [
            (entry.supply_class_value, entry.item_id)
            for entry in v
        ]
        if len(keys) != len(set(keys)):
            raise ValueError(
                "initial_inventory contains duplicate supply items",
            )
        return v


class ReinforcementUnitConfig(BaseModel):
    """Single unit entry in a reinforcement schedule."""

    model_config = ConfigDict(extra="forbid")

    unit_type: str
    count: int = 1
    overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("unit_type")
    @classmethod
    def _non_empty_unit_type(cls, v: str) -> str:
        if not v:
            raise ValueError("reinforcement unit_type must be non-empty")
        return v

    @field_validator("count")
    @classmethod
    def _positive_count(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("reinforcement unit count must be positive")
        return v

    @field_validator("overrides")
    @classmethod
    def _preserve_structural_fields(
        cls,
        v: dict[str, Any],
    ) -> dict[str, Any]:
        if v:
            raise ValueError(
                "reinforcement unit overrides are not supported; define a "
                "validated unit catalog variant instead",
            )
        return v


class ReinforcementConfig(BaseModel):
    """Scheduled reinforcement arrival."""

    model_config = ConfigDict(extra="forbid")

    side: str
    arrival_time_s: float
    units: list[ReinforcementUnitConfig]
    position: list[float] = Field(
        default_factory=lambda: [0.0, 0.0],
    )  # spawn position
    arrival_sigma: float = 0.0  # log-normal sigma for stochastic arrival

    @field_validator("arrival_time_s")
    @classmethod
    def _positive_time(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0:
            raise ValueError(
                "arrival_time_s must be finite and non-negative",
            )
        return v

    @field_validator("arrival_sigma")
    @classmethod
    def _non_negative_sigma(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0:
            raise ValueError(
                "arrival_sigma must be finite and non-negative",
            )
        return v

    @field_validator("units")
    @classmethod
    def _non_empty_units(
        cls,
        v: list[ReinforcementUnitConfig],
    ) -> list[ReinforcementUnitConfig]:
        if not v:
            raise ValueError("reinforcement units must not be empty")
        return v

    @field_validator("position")
    @classmethod
    def _valid_position(cls, v: list[float]) -> list[float]:
        if len(v) not in (2, 3):
            raise ValueError(
                "reinforcement position must contain [easting, northing] "
                "and optional altitude",
            )
        if not all(math.isfinite(coordinate) for coordinate in v):
            raise ValueError(
                "reinforcement position coordinates must be finite",
            )
        return v


class InitialIEDConfig(BaseModel):
    """Pre-emplaced IED / HBIED at scenario start (Phase 101).

    Used for urban scenarios where insurgents have pre-prepared the
    battlespace (e.g. Fallujah house-borne IEDs, Chechnya wired blocks).
    """

    position: list[float]  # [easting, northing]
    subtype: str = "command_wire"  # command_wire | pressure_plate | remote | vbied | hbied
    blast_radius_m: float = 10.0
    concealment: float = 0.7
    emplaced_by: str = "pre_emplaced"  # placeholder unit id

    @field_validator("subtype")
    @classmethod
    def _known_subtype(cls, v: str) -> str:
        allowed = {"command_wire", "pressure_plate", "remote", "vbied", "hbied"}
        if v not in allowed:
            raise ValueError(f"IED subtype must be one of {allowed}; got {v!r}")
        return v

    @field_validator("concealment")
    @classmethod
    def _clamp_concealment(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"concealment must be in [0, 1]; got {v}")
        return v


class ScriptedEventConfig(BaseModel):
    """Timed scripted event (Phase 101).

    Fired once at the configured ``time_s`` by the campaign manager.
    ``event_type`` selects the handler and ``params`` is forwarded to it.
    Honest types only — each handler invokes real engine APIs so outcomes
    are not magic (no scripted kills/wins).
    """

    time_s: float
    event_type: str
    params: dict[str, Any] = {}

    @field_validator("time_s")
    @classmethod
    def _non_negative_time(cls, v: float) -> float:
        if v < 0:
            raise ValueError("time_s must be non-negative")
        return v

    @field_validator("event_type")
    @classmethod
    def _known_event_type(cls, v: str) -> str:
        allowed = {
            "hbied_detonation",   # params: obstacle_id, target_unit_id
            "wp_fire_zone",       # params: center (list), radius_m, duration_s?, fuel_load?
            "unit_teleport",      # params: unit_id, position (list)
            "casualty_pulse",     # params: unit_id, casualties (int)
        }
        if v not in allowed:
            raise ValueError(f"event_type must be one of {allowed}; got {v!r}")
        return v


class ObjectiveConfig(BaseModel):
    """Campaign objective definition."""

    objective_id: str
    position: list[float]  # [easting, northing]
    radius_m: float = 500.0
    type: str = "territory"  # territory | key_terrain | infrastructure

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        allowed = {"territory", "key_terrain", "infrastructure"}
        if v not in allowed:
            raise ValueError(f"objective type must be one of {allowed}; got {v!r}")
        return v

    @field_validator("radius_m")
    @classmethod
    def _positive_radius(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("radius_m must be positive")
        return v


class VictoryConditionConfig(BaseModel):
    """Campaign victory condition."""

    type: str  # territory_control | force_destroyed | time_expired | morale_collapsed | supply_exhausted
    side: str = ""  # which side wins when condition met (empty = any)
    params: dict[str, Any] = {}

    @field_validator("type")
    @classmethod
    def _known_vc_type(cls, v: str) -> str:
        allowed = {
            "territory_control",
            "force_destroyed",
            "time_expired",
            "morale_collapsed",
            "supply_exhausted",
            "ceasefire",
            "armistice",
            "attrition_ratio",
        }
        if v not in allowed:
            raise ValueError(f"victory condition type must be one of {allowed}; got {v!r}")
        return v


class SideConfig(BaseModel):
    """One side of a campaign — units, AI profile, logistics."""

    model_config = ConfigDict(extra="forbid")

    side: str
    units: list[InitialUnitConfig]
    experience_level: float = 0.5
    morale_initial: str = "STEADY"
    commander_profile: str = ""  # YAML commander personality ID
    doctrine_template: str = ""  # YAML doctrine template ID
    # Legacy side-level value is retained for schema compatibility; runtime
    # ROE is scenario-wide under calibration_overrides.
    roe_level: Literal[
        "WEAPONS_HOLD",
        "WEAPONS_TIGHT",
        "WEAPONS_FREE",
    ] | None = Field(default=None, exclude=True)
    depots: list[DepotConfig] = Field(default_factory=list)

    @field_validator("side", mode="before")
    @classmethod
    def _valid_side(cls, value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise ValueError("side must be a non-empty trimmed string")
        return value

    @field_validator("commander_profile", mode="before")
    @classmethod
    def _valid_commander_profile(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("commander_profile must be a string")
        if value and value != value.strip():
            raise ValueError(
                "commander_profile must be empty or a trimmed profile ID",
            )
        return value

    @field_validator("experience_level")
    @classmethod
    def _clamp_experience(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"experience_level must be in [0, 1]; got {v}")
        return v

    @field_validator("morale_initial")
    @classmethod
    def _known_morale(cls, v: str) -> str:
        from stochastic_warfare.morale.state import validate_morale_state_name

        return validate_morale_state_name(v)


class DoctrineSideAssignment(BaseModel):
    """One strict side-to-school assignment supplied by runtime analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    side: str
    school_id: str

    @field_validator("side", "school_id", mode="before")
    @classmethod
    def _trimmed_identifier(cls, value: Any, info: Any) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise ValueError(
                f"{info.field_name} must be a non-empty trimmed string",
            )
        return value


class TickResolutionConfig(BaseModel):
    """Tick duration settings per resolution level."""

    strategic_s: float = 3600.0
    operational_s: float = 300.0
    tactical_s: float = 5.0


class TerrainConfig(BaseModel):
    """Programmatic terrain specification for campaigns."""

    width_m: float
    height_m: float
    cell_size_m: float = 100.0
    base_elevation_m: float = 0.0
    terrain_source: str = "procedural"
    terrain_type: str = "flat_desert"
    features: list[dict[str, Any]] = []
    data_dir: str = "data/terrain_raw"
    cache_dir: str = "data/terrain_cache"

    @field_validator("terrain_source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        allowed = {"procedural", "real"}
        if v not in allowed:
            raise ValueError(f"terrain_source must be one of {allowed}; got {v!r}")
        return v

    @field_validator("terrain_type")
    @classmethod
    def _known_terrain(cls, v: str, info: Any) -> str:
        source = info.data.get("terrain_source", "procedural")
        if source == "real":
            return v  # No constraint when using real terrain
        allowed = {"flat_desert", "open_ocean", "hilly_defense", "trench_warfare", "open_field"}
        if v not in allowed:
            raise ValueError(f"terrain_type must be one of {allowed}; got {v!r}")
        return v


class CampaignScenarioConfig(BaseModel):
    """Top-level campaign scenario definition loaded from YAML."""

    name: str
    date: str
    duration_hours: float
    latitude: float = 0.0
    longitude: float = 0.0
    era: str = "modern"
    tick_duration_seconds: float | None = None
    tick_resolution: TickResolutionConfig = TickResolutionConfig()
    weather_conditions: dict[str, Any] = {}
    terrain: TerrainConfig
    sides: list[SideConfig]
    objectives: list[ObjectiveConfig] = []
    victory_conditions: list[VictoryConditionConfig] = []
    reinforcements: list[ReinforcementConfig] = []
    initial_ieds: list[InitialIEDConfig] = []  # Phase 101 — pre-emplaced IEDs/HBIEDs
    scripted_events: list[ScriptedEventConfig] = []  # Phase 101 — timed scripted events
    deployment: DeploymentConfig = DeploymentConfig()  # Phase 104 — deployment modes
    calibration_overrides: CalibrationSchema = CalibrationSchema()
    escalation_config: dict[str, Any] | None = None
    ew_config: dict[str, Any] | None = None
    space_config: SpaceConfig | None = None
    cbrn_config: dict[str, Any] | None = None
    school_config: dict[str, Any] | None = None
    commander_config: CommanderScenarioConfig | None = None
    dew_config: dict[str, Any] | None = None
    behavior_rules: dict[str, Any] = {}
    indirect_fire: IndirectFireScenarioConfig = Field(
        default_factory=IndirectFireScenarioConfig,
    )
    logistics: LogisticsConfig = Field(default_factory=LogisticsConfig)

    @field_validator("calibration_overrides", mode="before")
    @classmethod
    def _strict_calibration_overrides(
        cls,
        value: Any,
    ) -> CalibrationSchema:
        if isinstance(value, CalibrationSchema):
            return value
        return CalibrationSchema.model_validate(value, strict=True)

    @field_validator("sides")
    @classmethod
    def _at_least_two_sides(cls, v: list[SideConfig]) -> list[SideConfig]:
        if len(v) < 2:
            raise ValueError("campaign requires at least 2 sides")
        return v

    @field_validator("duration_hours", mode="before")
    @classmethod
    def _positive_duration(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                "duration_hours must be a finite positive number",
            )
        try:
            normalized = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValueError(
                "duration_hours must be a finite positive number",
            ) from exc
        if not math.isfinite(normalized) or normalized <= 0.0:
            raise ValueError(
                "duration_hours must be a finite positive number",
            )
        return normalized

    @field_validator("era")
    @classmethod
    def _registered_era(cls, v: str) -> str:
        from stochastic_warfare.core.era import get_era_config

        normalized = v.lower()
        get_era_config(normalized)
        return normalized

    @model_validator(mode="before")
    @classmethod
    def _reject_misplaced_feature_gate(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            if "disabled_modules" in data:
                raise ValueError(
                    "disabled_modules belongs to the registered era "
                    "configuration, not the scenario root",
                )
            logistics_typos = sorted(
                key
                for key in data
                if _looks_like_logistics_key(key)
            )
            if logistics_typos:
                raise ValueError(
                    "Unknown scenario logistics field(s): "
                    f"{logistics_typos!r}",
                )
            indirect_fire_typos = sorted(
                key
                for key in data
                if _looks_like_indirect_fire_key(key)
            )
            if indirect_fire_typos:
                raise ValueError(
                    "Unknown or misplaced scenario indirect-fire field(s): "
                    f"{indirect_fire_typos!r}",
                )
            indirect_fire = data.get("indirect_fire")
            declared_missions = (
                indirect_fire.get("time_on_target_missions")
                if isinstance(indirect_fire, Mapping)
                else None
            )
            if declared_missions:
                cadence = data.get("tick_duration_seconds")
                if (
                    isinstance(cadence, bool)
                    or not isinstance(cadence, (int, float))
                    or not math.isfinite(float(cadence))
                    or float(cadence) <= 0.0
                    or not float(cadence).is_integer()
                ):
                    raise ValueError(
                        "declared time-on-target missions require a finite "
                        "positive whole-second tick_duration_seconds",
                    )
        return data

    @model_validator(mode="after")
    def _validate_side_references(self) -> CampaignScenarioConfig:
        side_names = [side.side for side in self.sides]
        if len(side_names) != len(set(side_names)):
            raise ValueError("scenario side names must be unique")
        known_sides = set(side_names)
        commander_profiles = [
            side.commander_profile
            for side in self.sides
        ]
        populated_profiles = [
            profile_id
            for profile_id in commander_profiles
            if profile_id
        ]
        if populated_profiles and len(populated_profiles) != len(self.sides):
            raise ValueError(
                "commander profiles must be populated for every side or "
                "omitted for every side",
            )
        if self.commander_config is not None and not populated_profiles:
            raise ValueError(
                "commander_config requires canonical commander_profile "
                "values on every side",
            )
        if self.space_config is not None:
            space_config = self.space_config
            if space_config.enable_space and not space_config.constellation_ids:
                raise ValueError(
                    "space_config.enable_space requires at least one explicit "
                    "constellation_id",
                )
            for asset in space_config.asat_assets:
                if asset.side not in known_sides:
                    raise ValueError(
                        f"ASAT asset {asset.asset_id!r} references unknown "
                        f"scenario side {asset.side!r}",
                    )
            maximum_time_s = self.duration_hours * 3600.0
            for order in space_config.asat_orders:
                if order.execute_at_s > maximum_time_s:
                    raise ValueError(
                        f"ASAT order {order.order_id!r} execute_at_s "
                        f"{order.execute_at_s} exceeds scenario duration "
                        f"{maximum_time_s}",
                    )
            theater_updates: dict[str, float] = {}
            if space_config.theater_lat is None:
                theater_updates["theater_lat"] = self.latitude
            if space_config.theater_lon is None:
                theater_updates["theater_lon"] = self.longitude
            if theater_updates:
                self.space_config = SpaceConfig.model_validate(
                    {
                        **space_config.model_dump(mode="python"),
                        **theater_updates,
                    },
                )
                space_config = self.space_config
            if (
                space_config.imint_fusion_constellation_ids
                and not self.calibration_overrides.enable_space_effects
            ):
                raise ValueError(
                    "space_config.imint_fusion_constellation_ids requires "
                    "calibration_overrides.enable_space_effects=true",
                )
        for index, reinforcement in enumerate(self.reinforcements):
            if reinforcement.side not in known_sides:
                raise ValueError(
                    f"reinforcement {index} references unknown side "
                    f"{reinforcement.side!r}",
                )

        depots_by_id: dict[str, str] = {}
        declared_unit_types: dict[str, set[str]] = {
            side.side: {
                unit.unit_type
                for unit in side.units
            }
            for side in self.sides
        }
        for reinforcement in self.reinforcements:
            declared_unit_types[reinforcement.side].update(
                unit.unit_type
                for unit in reinforcement.units
            )
        for side in self.sides:
            for depot in side.depots:
                if depot.depot_id in depots_by_id:
                    raise ValueError(
                        f"depot_id {depot.depot_id!r} must be globally unique",
                    )
                depots_by_id[depot.depot_id] = side.side
                if self.logistics.enabled and (
                    depot.depot_type is None
                    or depot.condition is None
                    or depot.initial_inventory is None
                ):
                    raise ValueError(
                        f"enabled logistics depot {depot.depot_id!r} requires "
                        "explicit depot_type, condition, and initial_inventory",
                    )

        profile_keys = {
            (profile.side, profile.unit_type)
            for profile in self.logistics.unit_profiles
        }
        for side, unit_type in sorted(profile_keys):
            if side not in known_sides:
                raise ValueError(
                    f"logistics profile references unknown side {side!r}",
                )
            if unit_type not in declared_unit_types[side]:
                raise ValueError(
                    "logistics profile references an undeclared unit type "
                    f"{side!r}/{unit_type!r}",
                )
        if self.logistics.enabled:
            expected_profiles = {
                (side, unit_type)
                for side, unit_types in declared_unit_types.items()
                for unit_type in unit_types
            }
            missing_profiles = sorted(expected_profiles - profile_keys)
            if missing_profiles:
                raise ValueError(
                    "enabled logistics requires profiles for every initial "
                    "and reinforcement unit type; missing "
                    f"{missing_profiles!r}",
                )

        expanded_template_keys: set[tuple[str, str]] = set()
        for route in self.logistics.route_templates:
            depot_side = depots_by_id.get(route.depot_id)
            if depot_side is None:
                raise ValueError(
                    f"route {route.route_id!r} references unknown depot "
                    f"{route.depot_id!r}",
                )
            if depot_side != route.side:
                raise ValueError(
                    f"route {route.route_id!r} crosses scenario sides",
                )
            for unit_type in route.unit_types:
                if (route.side, unit_type) not in profile_keys:
                    raise ValueError(
                        f"route {route.route_id!r} references unit type "
                        f"without a matching profile: "
                        f"{route.side!r}/{unit_type!r}",
                    )
                key = (route.depot_id, unit_type)
                if key in expanded_template_keys:
                    raise ValueError(
                        "parallel route templates for the same depot and "
                        f"unit type are unsupported: {key!r}",
                    )
                expanded_template_keys.add(key)

        missions = self.indirect_fire.time_on_target_missions
        if missions:
            cadence = self.tick_duration_seconds
            if (
                isinstance(cadence, bool)
                or not isinstance(cadence, (int, float))
                or not math.isfinite(float(cadence))
                or float(cadence) <= 0.0
                or not float(cadence).is_integer()
            ):
                raise ValueError(
                    "declared time-on-target missions require a finite "
                    "positive whole-second tick_duration_seconds",
                )
            cadence_seconds = int(cadence)
            duration_seconds = self.duration_hours * 3600.0
            for mission in missions:
                if mission.impact_time_s > duration_seconds:
                    raise ValueError(
                        f"time-on-target mission {mission.mission_id!r} "
                        f"impact_time_s {mission.impact_time_s:g} exceeds "
                        f"scenario duration {duration_seconds:g}",
                    )
                if int(mission.impact_time_s) % cadence_seconds:
                    raise ValueError(
                        f"time-on-target mission {mission.mission_id!r} "
                        "impact time is not aligned to "
                        "tick_duration_seconds",
                    )
                for battery in mission.batteries:
                    fire_time_s = (
                        mission.impact_time_s
                        - battery.time_of_flight_s
                    )
                    if int(fire_time_s) % cadence_seconds:
                        raise ValueError(
                            f"time-on-target mission {mission.mission_id!r} "
                            f"battery {battery.unit_id!r} fire time is not "
                            "aligned to tick_duration_seconds",
                        )
        return self


def _merge_config_patch(
    base: dict[str, Any],
    patch: Mapping[str, Any],
) -> None:
    """Recursively merge one sparse configuration patch into ``base``."""
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _merge_config_patch(base[key], value)
        else:
            base[key] = copy.deepcopy(value)


NON_RUNTIME_SCENARIO_ROOT_FIELDS = frozenset(
    {
        "ai_expectations",
        "blue_forces",
        "documented_outcomes",
        "id",
        "master_seed",
        "red_forces",
        "sources",
        "start_time",
        "weather",
    },
)


def _reject_nonfinite_source_numbers(
    value: Any,
    *,
    path: str,
) -> None:
    """Reject NaN/Inf anywhere in authored runtime or metadata input."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                f"{path} must contain only finite numbers",
            )
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _reject_nonfinite_source_numbers(
                nested,
                path=f"{path}.{key}",
            )
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_nonfinite_source_numbers(
                nested,
                path=f"{path}[{index}]",
            )


def parse_campaign_scenario_config(
    raw: Any,
) -> CampaignScenarioConfig:
    """Parse one strict runtime config while explicitly excluding metadata."""
    if not isinstance(raw, Mapping):
        raise ValueError("campaign scenario source must be a mapping")
    _reject_nonfinite_source_numbers(raw, path="scenario")
    runtime_fields = set(CampaignScenarioConfig.model_fields)
    unknown = sorted(
        set(raw)
        - runtime_fields
        - NON_RUNTIME_SCENARIO_ROOT_FIELDS,
    )
    if unknown:
        raise ValueError(
            f"unknown scenario root field(s): {unknown!r}",
        )
    normalized = {
        key: copy.deepcopy(value)
        for key, value in raw.items()
        if key in runtime_fields
    }
    return CampaignScenarioConfig.model_validate_json(
        json.dumps(
            normalized,
            allow_nan=False,
            separators=(",", ":"),
        ),
        strict=True,
        extra="forbid",
    )


def load_campaign_scenario_config(
    scenario_path: Path | None = None,
    calibration_overrides: Mapping[str, Any] | CalibrationSchema | None = None,
    *,
    source_config: CampaignScenarioConfig | None = None,
) -> CampaignScenarioConfig:
    """Load or revalidate one source and apply a sparse typed overlay."""
    if (scenario_path is None) == (source_config is None):
        raise ValueError(
            "Provide exactly one of scenario_path or source_config",
        )
    if source_config is None:
        with open(scenario_path, encoding="utf-8") as config_file:
            raw = load_yaml_unique(config_file)
        config = parse_campaign_scenario_config(raw)
    else:
        config = CampaignScenarioConfig.model_validate(
            source_config.model_dump(mode="python"),
            strict=True,
            extra="forbid",
        )
    if calibration_overrides is None:
        return config

    if isinstance(calibration_overrides, CalibrationSchema):
        patch = calibration_overrides.to_sparse_patch(mode="json")
    else:
        raw_patch = dict(calibration_overrides)
        dead_keys = sorted(
            set(raw_patch) & CalibrationSchema._DEAD_KEYS,
        )
        if dead_keys:
            raise ValueError(
                f"Unsupported dead calibration overrides: {dead_keys!r}",
            )
        patch = CalibrationSchema.model_validate(
            raw_patch,
            strict=True,
        ).to_sparse_patch(mode="json")

    scenario_sides = {side.side for side in config.sides}
    referenced_sides = set(patch.get("side_overrides", {}))
    referenced_sides.update(patch.get("defensive_sides", []))
    unknown_sides = sorted(referenced_sides - scenario_sides)
    if unknown_sides:
        raise ScenarioReferenceError(
            f"Calibration overrides reference unknown sides: {unknown_sides!r}",
        )

    merged = config.calibration_overrides.model_dump(mode="json")
    _merge_config_patch(merged, patch)
    config.calibration_overrides = CalibrationSchema.model_validate(
        merged,
        strict=True,
    )
    return config


# ---------------------------------------------------------------------------
# Simulation context — shared state container
# ---------------------------------------------------------------------------


def _unit_class_from_state(state: dict[str, Any]) -> type[Unit]:
    """Resolve a serialized unit state through a fixed, safe class allowlist."""
    from stochastic_warfare.entities.unit_classes.aerial import AerialUnit
    from stochastic_warfare.entities.unit_classes.air_defense import AirDefenseUnit
    from stochastic_warfare.entities.unit_classes.ground import GroundUnit
    from stochastic_warfare.entities.unit_classes.naval import NavalUnit
    from stochastic_warfare.entities.unit_classes.support import SupportUnit

    classes: dict[str, type[Unit]] = {
        "Unit": Unit,
        "GroundUnit": GroundUnit,
        "AerialUnit": AerialUnit,
        "NavalUnit": NavalUnit,
        "AirDefenseUnit": AirDefenseUnit,
        "SupportUnit": SupportUnit,
    }
    discriminator = state.get("unit_class")
    if discriminator is not None:
        try:
            return classes[discriminator]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"Unknown checkpoint unit_class {discriminator!r}",
            ) from exc

    legacy_fields = (
        ("ground_type", GroundUnit),
        ("aerial_type", AerialUnit),
        ("naval_type", NavalUnit),
        ("ad_type", AirDefenseUnit),
        ("support_type", SupportUnit),
    )
    inferred_classes = [
        unit_class
        for field_name, unit_class in legacy_fields
        if field_name in state
    ]
    if len(inferred_classes) > 1:
        markers = [
            field_name
            for field_name, _ in legacy_fields
            if field_name in state
        ]
        raise ValueError(
            f"Ambiguous legacy checkpoint unit fields: {markers!r}",
        )
    if inferred_classes:
        return inferred_classes[0]
    return Unit


def _stage_checkpoint_unit(state: Any, side: str) -> Unit:
    """Validate and build one checkpoint unit without touching live state."""
    if not isinstance(state, dict):
        raise ValueError(
            f"Checkpoint unit for side {side!r} must be a mapping",
        )
    entity_id = state.get("entity_id")
    if not isinstance(entity_id, str) or not entity_id:
        raise ValueError(
            f"Checkpoint unit for side {side!r} has an invalid entity_id",
        )
    state_side = state.get("side")
    if state_side != side:
        raise ValueError(
            f"Checkpoint unit {entity_id!r} is stored under side {side!r} "
            f"but declares side {state_side!r}",
        )

    unit_class = _unit_class_from_state(state)
    unit = unit_class(entity_id=entity_id, position=Position(0.0, 0.0, 0.0))
    try:
        unit.set_state(state)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid checkpoint state for unit {entity_id!r}: {exc}",
        ) from exc
    return unit


def _validate_checkpoint_ammunition_state(
    saved_state: dict[str, Any],
    runtime_entry: Any,
    instance: Any,
    *,
    entity_id: str,
    index: int,
) -> None:
    """Validate exact live ammunition topology before staging a weapon."""
    compatible_ammo = tuple(instance.definition.compatible_ammo)
    expected_ammo = compatible_ammo
    if isinstance(runtime_entry, WeaponAttachment):
        attachment_ammo = tuple(
            ammunition.ammo_id
            for ammunition in runtime_entry.ammunition
        )
        if attachment_ammo != compatible_ammo:
            raise ValueError(
                f"Runtime weapon ammunition topology for unit "
                f"{entity_id!r} at index {index} is inconsistent: "
                f"attachment={attachment_ammo!r}, "
                f"compatible_ammo={compatible_ammo!r}",
            )
        expected_ammo = attachment_ammo

    ammo_state = saved_state.get("ammo_state")
    if not isinstance(ammo_state, dict):
        raise ValueError(
            f"Checkpoint weapon state {entity_id!r}[{index}] ammo_state "
            "must be a mapping",
        )
    rounds_by_type = ammo_state.get("rounds_by_type")
    if not isinstance(rounds_by_type, dict):
        raise ValueError(
            f"Checkpoint weapon state {entity_id!r}[{index}] "
            "rounds_by_type must be a mapping",
        )
    expected_keys = set(expected_ammo)
    saved_keys = set(rounds_by_type)
    if saved_keys != expected_keys:
        raise ValueError(
            f"Incompatible weapon ammunition topology for unit "
            f"{entity_id!r} at index {index}: "
            f"missing={sorted(expected_keys - saved_keys, key=repr)!r}, "
            f"extra={sorted(saved_keys - expected_keys, key=repr)!r}",
        )
    for ammo_id, rounds in rounds_by_type.items():
        if (
            not isinstance(rounds, int)
            or isinstance(rounds, bool)
            or rounds < 0
        ):
            raise ValueError(
                f"Checkpoint weapon state {entity_id!r}[{index}] "
                f"rounds_by_type[{ammo_id!r}] must be a non-negative "
                "integer",
            )
    total_rounds_fired = ammo_state.get("total_rounds_fired")
    if (
        not isinstance(total_rounds_fired, int)
        or isinstance(total_rounds_fired, bool)
        or total_rounds_fired < 0
    ):
        raise ValueError(
            f"Checkpoint weapon state {entity_id!r}[{index}] "
            "total_rounds_fired must be a non-negative integer",
        )


def _stage_runtime_instance_states(
    raw_states: Any,
    current_instances: dict[str, list[Any]],
    checkpoint_unit_ids: set[str],
    compatible_unit_ids: set[str],
    checkpoint_equipment: dict[str, dict[str, dict[str, Any]]] | None,
    *,
    kind: str,
) -> list[tuple[Any, dict[str, Any]]]:
    """Validate weapon or sensor instance state without mutating live objects."""
    if not isinstance(raw_states, dict):
        raise ValueError(f"Checkpoint {kind} states must be a mapping")

    expected_ids = set(current_instances) & compatible_unit_ids
    serialized_ids = set(raw_states)
    missing = sorted(expected_ids - serialized_ids)
    if missing:
        extra = sorted(serialized_ids - expected_ids)
        raise ValueError(
            f"Incompatible {kind} unit topology: missing={missing!r}, "
            f"extra={extra!r}",
        )

    staged: list[tuple[Any, dict[str, Any]]] = []
    for entity_id, saved_instances in raw_states.items():
        if not isinstance(entity_id, str) or entity_id not in checkpoint_unit_ids:
            raise ValueError(
                f"Checkpoint {kind} state references unknown unit {entity_id!r}",
            )
        if not isinstance(saved_instances, list):
            raise ValueError(
                f"Checkpoint {kind} state for {entity_id!r} must be a list",
            )
        if saved_instances and entity_id not in compatible_unit_ids:
            raise ValueError(
                f"Cannot restore {kind} state for reconstructed unit "
                f"{entity_id!r}; build a compatible runtime first",
            )
        runtime_entries = (
            current_instances.get(entity_id, [])
            if entity_id in compatible_unit_ids
            else []
        )
        if len(runtime_entries) != len(saved_instances):
            raise ValueError(
                f"Incompatible {kind} topology for unit {entity_id!r}: "
                f"checkpoint has {len(saved_instances)}, runtime has "
                f"{len(runtime_entries)}",
            )

        for index, saved_state in enumerate(saved_instances):
            if not isinstance(saved_state, dict):
                raise ValueError(
                    f"Checkpoint {kind} state {entity_id!r}[{index}] "
                    "must be a mapping",
                )
            runtime_entry = runtime_entries[index]
            instance = runtime_entry[0] if kind == "weapon" else runtime_entry
            identity_field = "weapon_id" if kind == "weapon" else "sensor_id"
            runtime_id = getattr(instance, identity_field, None)
            if saved_state.get(identity_field) != runtime_id:
                raise ValueError(
                    f"Incompatible {kind} identity for unit {entity_id!r} "
                    f"at index {index}: checkpoint has "
                    f"{saved_state.get(identity_field)!r}, runtime has "
                    f"{runtime_id!r}",
                )
            if kind == "weapon":
                _validate_checkpoint_ammunition_state(
                    saved_state,
                    runtime_entry,
                    instance,
                    entity_id=entity_id,
                    index=index,
                )
            equipment = getattr(instance, "equipment", None)
            if equipment is not None and checkpoint_equipment is not None:
                saved_equipment = checkpoint_equipment.get(
                    entity_id, {},
                ).get(equipment.equipment_id)
                if saved_equipment is None:
                    raise ValueError(
                        f"Checkpoint {kind} {runtime_id!r} references "
                        f"missing equipment {equipment.equipment_id!r}",
                    )
                if (
                    saved_state.get("equipment_condition")
                    != saved_equipment.get("condition")
                    or saved_state.get("equipment_operational")
                    != saved_equipment.get("operational")
                ):
                    raise ValueError(
                        f"Conflicting checkpoint equipment state for "
                        f"{kind} {runtime_id!r} on unit {entity_id!r}",
                    )
            try:
                staged_instance = copy.deepcopy(instance)
                staged_instance.set_state(saved_state)
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid {kind} state for unit {entity_id!r} "
                    f"at index {index}: {exc}",
                ) from exc
            staged.append((instance, saved_state))

    return staged


def _json_compatible_value(value: Any) -> Any:
    """Convert model values to deterministic JSON-compatible structures."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            key: _json_compatible_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (set, frozenset)):
        converted = [_json_compatible_value(item) for item in value]
        return sorted(converted, key=repr)
    if isinstance(value, (list, tuple)):
        return [_json_compatible_value(item) for item in value]
    return value


def _model_dump_json_compatible(model: Any) -> dict[str, Any]:
    """Dump Pydantic models canonically while supporting legacy test doubles."""
    try:
        raw = model.model_dump(mode="python")
    except TypeError:
        raw = model.model_dump()
    return _json_compatible_value(raw)


def _json_values_equal(left: Any, right: Any) -> bool:
    """Compare JSON-compatible values without bool/number coercion."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_values_equal(left[key], right[key])
            for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return bool(left == right)


@dataclass(frozen=True, slots=True)
class _CheckpointAggregateMoraleTopology:
    """Validated aggregate constituent IDs and captured unit statuses."""

    constituents: dict[str, tuple[str, ...]]
    statuses: dict[str, UnitStatus]


def _checkpoint_aggregate_morale_topology(
    raw_aggregation: Any,
) -> _CheckpointAggregateMoraleTopology:
    """Parse aggregate morale topology and statuses in one strict pass."""
    if raw_aggregation is None:
        return _CheckpointAggregateMoraleTopology({}, {})
    if not isinstance(raw_aggregation, dict):
        raise ValueError("Checkpoint aggregation_engine must be a mapping")
    raw_aggregates = raw_aggregation.get("aggregates", {})
    if not isinstance(raw_aggregates, dict):
        raise ValueError(
            "Checkpoint aggregation_engine.aggregates must be a mapping",
        )
    result: dict[str, tuple[str, ...]] = {}
    statuses: dict[str, UnitStatus] = {}
    seen_constituents: set[str] = set()
    for aggregate_id in sorted(raw_aggregates):
        raw_aggregate = raw_aggregates[aggregate_id]
        if not isinstance(aggregate_id, str) or not aggregate_id:
            raise ValueError("Checkpoint aggregate IDs must be non-empty strings")
        if not isinstance(raw_aggregate, dict):
            raise ValueError("Checkpoint aggregate entries must be mappings")
        if raw_aggregate.get("aggregate_id") != aggregate_id:
            raise ValueError(
                f"Checkpoint aggregate identity mismatch for {aggregate_id!r}",
            )
        raw_snapshots = raw_aggregate.get("snapshots")
        if not isinstance(raw_snapshots, list) or not raw_snapshots:
            raise ValueError(
                f"Checkpoint aggregate {aggregate_id!r} requires snapshots",
            )
        constituent_ids: list[str] = []
        for raw_snapshot in raw_snapshots:
            if not isinstance(raw_snapshot, dict):
                raise ValueError("Checkpoint aggregate snapshots must be mappings")
            raw_unit = raw_snapshot.get("unit_state")
            if not isinstance(raw_unit, dict):
                raise ValueError(
                    "Checkpoint aggregate unit_state must be a mapping",
                )
            unit_id = raw_unit.get("entity_id")
            raw_status = raw_unit.get("status")
            if not isinstance(unit_id, str) or not unit_id:
                raise ValueError(
                    "Checkpoint aggregate constituent IDs must be non-empty strings",
                )
            if (
                isinstance(raw_status, bool)
                or not isinstance(raw_status, int)
            ):
                raise ValueError(
                    "Checkpoint aggregate constituent status is malformed",
                )
            if unit_id in seen_constituents:
                raise ValueError(
                    f"Duplicate aggregate constituent ID {unit_id!r}",
                )
            seen_constituents.add(unit_id)
            constituent_ids.append(unit_id)
            try:
                statuses[unit_id] = UnitStatus(raw_status)
            except ValueError as exc:
                raise ValueError(
                    f"Unknown aggregate constituent status for {unit_id!r}",
                ) from exc
        result[aggregate_id] = tuple(sorted(constituent_ids))
    return _CheckpointAggregateMoraleTopology(result, statuses)


def _checkpoint_has_active_routes(raw_rout_state: Any) -> bool:
    """Return whether a validated-enough rout envelope is non-empty."""
    if raw_rout_state is None:
        return False
    if not isinstance(raw_rout_state, dict):
        raise ValueError("Checkpoint rout_engine state must be a mapping")
    raw_routes = raw_rout_state.get("active_routs", {})
    if not isinstance(raw_routes, dict):
        raise ValueError("Checkpoint active_routs must be a mapping")
    return bool(raw_routes)


def _legacy_morale_value(value: Any, *, owner: str, unit_id: str) -> Any:
    """Parse one strict legacy context or machine morale value."""
    try:
        if owner == "context" and isinstance(value, str):
            return MoraleState[value]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("must be an integer enum value")
        return MoraleState(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid legacy {owner} morale for {unit_id!r}: {value!r}",
        ) from exc


def _migrate_legacy_morale_runtime(
    *,
    context_morale: Any,
    machine_state: Any,
    units: Mapping[str, Unit],
    side_initial: Mapping[str, str],
    elapsed_time_s: float,
    continuous_time: bool,
    authoritative_rng_state: Any,
    rout_state: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Build one bounded format-113 morale envelope from versionless state."""
    if continuous_time and elapsed_time_s > 0.0:
        raise ValueError(
            "A started continuous-time runtime cannot reconstruct legacy "
            "morale check history",
        )
    if context_morale is None:
        raw_context: Mapping[str, Any] = {}
    elif isinstance(context_morale, dict):
        raw_context = context_morale
    else:
        raise ValueError("Legacy morale_states must be a mapping")

    raw_machine_units: Mapping[str, Any] = {}
    if machine_state is not None:
        if not isinstance(machine_state, dict):
            raise ValueError("Legacy morale_machine must be a mapping")
        if set(machine_state) != {"unit_states", "rng_state"}:
            raise ValueError(
                "Legacy morale_machine has invalid key topology",
            )
        raw_machine_units = machine_state["unit_states"]
        if not isinstance(raw_machine_units, dict):
            raise ValueError(
                "Legacy morale_machine.unit_states must be a mapping",
            )
        if not _json_values_equal(
            machine_state["rng_state"],
            authoritative_rng_state,
        ):
            raise ValueError(
                "Legacy morale_machine RNG disagrees with RNGManager",
            )

    normalized_rout_state: dict[str, Any] | None = None
    if rout_state is not None:
        if not isinstance(rout_state, dict):
            raise ValueError("Legacy rout_engine must be a mapping")
        if set(rout_state) != {"active_routs", "rng_state"}:
            raise ValueError(
                "Legacy rout_engine has invalid key topology",
            )
        if not _json_values_equal(
            rout_state["rng_state"],
            authoritative_rng_state,
        ):
            raise ValueError(
                "Legacy rout_engine RNG disagrees with RNGManager",
            )
        normalized_rout_state = {
            "active_routs": copy.deepcopy(rout_state["active_routs"]),
        }

    expected_ids = set(units)
    extra_context = set(raw_context) - expected_ids
    extra_machine = set(raw_machine_units) - expected_ids
    if extra_context:
        raise ValueError(
            "Legacy morale_states contains units outside the force roster: "
            f"{sorted(extra_context)!r}",
        )
    if extra_machine:
        raise ValueError(
            "Legacy morale_machine contains units outside the force roster: "
            f"{sorted(extra_machine)!r}",
        )

    active_records: dict[str, dict[str, Any]] = {}
    for unit_id in sorted(expected_ids):
        context_value = raw_context.get(unit_id)
        context_state = (
            _legacy_morale_value(
                context_value,
                owner="context",
                unit_id=unit_id,
            )
            if unit_id in raw_context
            else None
        )

        machine_morale = None
        transition_time: float | None = None
        generation = 0
        if unit_id in raw_machine_units:
            raw_record = raw_machine_units[unit_id]
            if not isinstance(raw_record, dict):
                raise ValueError(
                    f"Legacy morale record for {unit_id!r} must be a mapping",
                )
            if set(raw_record) != {
                "current_state",
                "transition_cooldown_s",
                "last_transition_time",
            }:
                raise ValueError(
                    f"Legacy morale record for {unit_id!r} has invalid keys",
                )
            machine_morale = _legacy_morale_value(
                raw_record["current_state"],
                owner="machine",
                unit_id=unit_id,
            )
            cooldown = raw_record["transition_cooldown_s"]
            if (
                isinstance(cooldown, bool)
                or not isinstance(cooldown, (int, float))
                or not math.isfinite(float(cooldown))
                or float(cooldown) != 0.0
            ):
                raise ValueError(
                    "Legacy per-record transition_cooldown_s must be the "
                    f"canonical inert 0.0 for {unit_id!r}",
                )
            raw_time = raw_record["last_transition_time"]
            if (
                isinstance(raw_time, bool)
                or not isinstance(raw_time, (int, float))
                or not math.isfinite(float(raw_time))
            ):
                raise ValueError(
                    f"Legacy transition time for {unit_id!r} is invalid",
                )
            normalized_time = float(raw_time)
            if normalized_time == -1e9:
                transition_time = None
            elif 0.0 <= normalized_time <= elapsed_time_s:
                transition_time = normalized_time
                generation = 1
            else:
                raise ValueError(
                    f"Legacy transition time for {unit_id!r} is impossible",
                )

        if (
            context_state is not None
            and machine_morale is not None
            and context_state is not machine_morale
        ):
            raise ValueError(
                f"Legacy morale stores disagree for unit {unit_id!r}",
            )

        chosen_state = (
            machine_morale
            if machine_morale is not None
            else context_state
        )
        if chosen_state is None:
            side = units[unit_id].side
            side_name = side if isinstance(side, str) else side.value
            try:
                chosen_state = MoraleState[side_initial[side_name]]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Cannot backfill legacy morale for unit {unit_id!r}",
                ) from exc

        active_records[unit_id] = {
            "current_state": int(chosen_state),
            "last_transition_time_s": transition_time,
            "last_check_time_s": transition_time,
            "generation": generation,
        }

    return (
        {
            "active_records": active_records,
            "suspended_archives": {},
        },
        normalized_rout_state,
    )


def _initial_morale_for_units(
    config: CampaignScenarioConfig,
    units: list[Unit],
) -> dict[str, MoraleState]:
    """Derive typed side morale without mutating caller-owned units."""
    state_by_side = {
        side.side: MoraleState[side.morale_initial]
        for side in config.sides
    }
    result: dict[str, MoraleState] = {}
    for unit in units:
        side = unit.side if isinstance(unit.side, str) else unit.side.value
        try:
            morale = state_by_side[side]
        except KeyError as exc:
            raise ValueError(
                f"Unit {unit.entity_id!r} references unknown side {side!r}",
            ) from exc
        result[unit.entity_id] = morale
    return result


def _initial_status_for_morale(morale: MoraleState) -> UnitStatus:
    """Return the required initial unit-status projection for morale."""
    if morale is MoraleState.ROUTED:
        return UnitStatus.ROUTING
    if morale is MoraleState.SURRENDERED:
        return UnitStatus.SURRENDERED
    return UnitStatus.ACTIVE


_CONTEXT_STATE_ENGINE_NAMES = (
    "ooda_engine",
    "planning_engine",
    "order_execution",
    "logistics_runtime",
    "stockpile_manager",
    "fog_of_war",
    "aggregation_engine",
    "space_engine",
    "cbrn_engine",
    "school_registry",
    "trench_engine",
    "barrage_engine",
    "gas_warfare_engine",
    "volley_fire_engine",
    "melee_engine",
    "cavalry_engine",
    "formation_napoleonic_engine",
    "courier_engine",
    "foraging_engine",
    "archery_engine",
    "siege_engine",
    "formation_ancient_engine",
    "naval_oar_engine",
    "visual_signals_engine",
    "escalation_engine",
    "political_engine",
    "consequence_engine",
    "unconventional_engine",
    "insurgency_engine",
    "sof_engine",
    "war_termination_engine",
    "incendiary_engine",
    "uxo_engine",
    "commander_engine",
    "eccm_engine",
    "sigint_engine",
    "ew_decoy_engine",
    "dew_engine",
    "indirect_fire_engine",
    "naval_surface_engine",
    "naval_subsurface_engine",
    "naval_gunfire_support_engine",
    "mine_warfare_engine",
    "disruption_engine",
    "maintenance_engine",
    "medical_engine",
    "engineering_engine",
    "collateral_engine",
    "weather_engine",
    "sea_state_engine",
    "stratagem_engine",
    "iads_engine",
    "ato_engine",
    "underwater_acoustics_engine",
    "carrier_ops_engine",
    "comms_engine",
    "detection_engine",
    "movement_engine",
    "movement_diagnostics",
    "conditions_engine",
    "engagement_engine",
    "suppression_engine",
    "air_combat_engine",
    "air_ground_engine",
    "air_defense_engine",
    "missile_engine",
    "missile_defense_engine",
    "naval_gunnery_engine",
    "convoy_engine",
    "strategic_bombing_engine",
    "time_of_day_engine",
    "seasons_engine",
    "obscurants_engine",
    "order_propagation",
    "assessor",
    "decision_engine",
    "adaptation_engine",
    "roe_engine",
    "rout_engine",
    "ew_engine",
    "consumption_engine",
    "supply_network_engine",
    "command_engine",
)


@dataclass(frozen=True)
class SimulationContextStatePlan:
    """Validated, owner-bound whole-context checkpoint plan."""

    owner_id: int
    state: dict[str, Any]
    allow_legacy_morale: bool


@dataclass
class SimulationContext:
    """Shared state for an in-progress simulation run.

    Holds configuration, core infrastructure, domain engines, and forces.
    Passed to :class:`BattleManager` and :class:`CampaignManager` as the
    single context object for each tick.
    """

    config: CampaignScenarioConfig
    clock: SimulationClock
    rng_manager: RNGManager
    event_bus: EventBus

    # Terrain
    heightmap: Heightmap | None = None
    los_engine: Any = None
    classification: Any = None
    infrastructure_manager: Any = None
    bathymetry: Any = None
    obstacle_manager: Any = None
    hydrography_manager: Any = None
    population_manager: Any = None

    # Suppression (Phase 40e)
    suppression_engine: Any = None

    # Forces
    units_by_side: dict[str, list[Unit]] = field(default_factory=dict)
    unit_weapons: dict[str, tuple[WeaponAttachment, ...]] = field(
        default_factory=dict,
    )
    unit_sensors: dict[str, tuple[SensorInstance, ...]] = field(
        default_factory=dict,
    )
    equipment_resolutions: dict[
        str,
        tuple[EquipmentResolution, ...],
    ] = field(default_factory=dict)
    force_builder: RuntimeForceBuilder | None = None
    loadout_builder: RuntimeLoadoutBuilder | None = None
    morale_states: Mapping[str, MoraleState] = field(
        default_factory=dict,
        repr=False,
    )

    # Environment engines
    weather_engine: Any = None
    time_of_day_engine: Any = None
    seasons_engine: Any = None
    sea_state_engine: Any = None
    obscurants_engine: Any = None
    conditions_engine: Any = None  # Used by SpaceEngine — keep

    # Combat
    engagement_engine: Any = None

    # Detection
    detection_engine: Any = None
    fog_of_war: Any = None

    # Movement
    movement_engine: Any = None
    movement_diagnostics: MovementDiagnostics | None = None

    # Morale
    morale_runtime: MoraleRuntime | None = None

    # ROE (Phase 42a)
    roe_engine: Any = None

    # Rout (Phase 42c)
    rout_engine: RoutEngine | None = None

    # C2
    command_engine: Any = None
    comms_engine: Any = None
    order_propagation: Any = None
    order_execution: Any = None

    # AI
    ooda_engine: Any = None
    planning_engine: Any = None
    assessor: Any = None
    decision_engine: Any = None
    adaptation_engine: Any = None

    # Aggregation (Phase 13a-7)
    aggregation_engine: Any = None

    # Electronic Warfare (Phase 16)
    ew_engine: Any = None

    # Space & Satellite (Phase 17)
    space_engine: Any = None

    # CBRN (Phase 18)
    cbrn_engine: Any = None

    # Doctrinal AI Schools (Phase 19)
    school_registry: Any = None
    doctrine_side_assignments: tuple[
        DoctrineSideAssignment,
        ...,
    ] = ()

    # Commander (Phase 25)
    commander_engine: Any = None

    # EW sub-engines (Phase 25 wiring)
    eccm_engine: Any = None
    sigint_engine: Any = None
    ew_decoy_engine: Any = None

    # Era Framework (Phase 20)
    era_config: Any = None

    # WW2 Engine Extensions (Phase 20b)
    naval_gunnery_engine: Any = None
    convoy_engine: Any = None
    strategic_bombing_engine: Any = None

    # WW1 Engine Extensions (Phase 21b)
    trench_engine: Any = None
    barrage_engine: Any = None
    gas_warfare_engine: Any = None

    # Napoleonic Engine Extensions (Phase 22b)
    volley_fire_engine: Any = None
    melee_engine: Any = None
    cavalry_engine: Any = None
    formation_napoleonic_engine: Any = None
    courier_engine: Any = None
    foraging_engine: Any = None

    # Ancient/Medieval Engine Extensions (Phase 23b)
    archery_engine: Any = None
    siege_engine: Any = None
    formation_ancient_engine: Any = None
    naval_oar_engine: Any = None
    visual_signals_engine: Any = None

    # Escalation & Unconventional (Phase 24)
    escalation_engine: Any = None
    political_engine: Any = None
    consequence_engine: Any = None
    unconventional_engine: Any = None
    insurgency_engine: Any = None
    sof_engine: Any = None
    war_termination_engine: Any = None
    incendiary_engine: Any = None
    uxo_engine: Any = None

    # Stratagems (Phase 53c)
    stratagem_engine: Any = None

    # IADS (Phase 53e)
    iads_engine: Any = None

    # ATO Planning (Phase 53d)
    ato_engine: Any = None

    # Air Combat Engines (Phase 58b)
    air_combat_engine: Any = None
    air_ground_engine: Any = None
    air_defense_engine: Any = None

    # Underwater Acoustics (Phase 61)
    underwater_acoustics_engine: Any = None

    # Carrier Ops (Phase 61)
    carrier_ops_engine: Any = None

    # Missile (Phase 63d)
    missile_engine: Any = None

    # Missile Defense (Phase 71c)
    missile_defense_engine: Any = None

    # Conditions facade (Phase 66b)
    conditions_facade: Any = None

    # Directed Energy (Phase 28.5)
    dew_engine: Any = None

    # Indirect Fire (Phase 43b)
    indirect_fire_engine: Any = None

    # Naval Engines (Phase 43c)
    naval_surface_engine: Any = None
    naval_subsurface_engine: Any = None
    naval_gunfire_support_engine: Any = None
    mine_warfare_engine: Any = None

    # Disruption (Phase 51d — blockade / interdiction)
    disruption_engine: Any = None

    # Logistics
    consumption_engine: Any = None
    stockpile_manager: Any = None
    supply_network_engine: Any = None
    logistics_runtime: Any = None
    maintenance_engine: Any = None
    medical_engine: Any = None
    engineering_engine: Any = None

    # Collateral (Phase 44d)
    collateral_engine: Any = None

    # Loaders (needed for reinforcements)
    unit_loader: Any = None
    weapon_loader: Any = None
    ammo_loader: Any = None
    sensor_loader: Any = None
    sig_loader: Any = None
    supply_item_loader: Any = None
    commander_profile_loader: Any = None

    # Calibration
    calibration: CalibrationSchema | dict[str, Any] = field(default_factory=CalibrationSchema)

    # Flat calibration dict for O(1) battle-loop access (Phase 86)
    cal_flat: dict[str, Any] = field(default_factory=dict)

    # Phase 101 — Fallujah urban scenario support
    scripted_events: list[Any] = field(default_factory=list)
    initial_ied_obstacle_ids: list[str] = field(default_factory=list)

    _morale_states_bound: bool = field(
        default=False,
        init=False,
        repr=False,
    )

    # ── Helpers ──────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        """Bind the stable, read-only public morale projection."""
        initial_projection = dict(self.morale_states)
        if self.morale_runtime is None:
            if initial_projection:
                raise ValueError(
                    "A non-empty morale projection requires MoraleRuntime",
                )
            morale_view: Mapping[str, MoraleState] = MappingProxyType({})
        else:
            morale_view = self.morale_runtime.states
            if initial_projection and initial_projection != dict(morale_view):
                raise ValueError(
                    "Initial morale projection disagrees with MoraleRuntime",
                )
            authoritative_rng = self.rng_manager.get_stream(ModuleId.MORALE)
            if self.morale_runtime.rng is not authoritative_rng:
                raise ValueError(
                    "MoraleRuntime must use RNGManager's MORALE generator",
                )
            if (
                self.rout_engine is not None
                and self.rout_engine.rng is not authoritative_rng
            ):
                raise ValueError(
                    "RoutEngine must use RNGManager's MORALE generator",
                )
            if self.morale_runtime.rout_engine is not self.rout_engine:
                raise ValueError(
                    "MoraleRuntime and SimulationContext must share RoutEngine",
                )
        object.__setattr__(self, "morale_states", morale_view)
        self._validate_morale_bindings()
        object.__setattr__(self, "_morale_states_bound", True)

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent replacement of the bound morale owner graph."""
        if (
            name in {"morale_states", "morale_runtime", "rout_engine"}
            and getattr(self, "_morale_states_bound", False)
        ):
            raise AttributeError(
                f"{name} is a stable MoraleRuntime ownership binding",
            )
        object.__setattr__(self, name, value)

    def _morale_roster(self) -> dict[str, Unit]:
        """Return the exact active roster, rejecting duplicate entity IDs."""
        roster: dict[str, Unit] = {}
        for unit in self.all_units():
            if unit.entity_id in roster:
                raise ValueError(
                    f"Duplicate runtime entity_id {unit.entity_id!r}",
                )
            roster[unit.entity_id] = unit
        return roster

    def _validate_morale_bindings(
        self,
        *,
        require_runtime_for_roster: bool = False,
    ) -> None:
        """Fail closed when context, runtime, rout, RNG, or roster diverge."""
        roster = self._morale_roster()
        runtime = self.morale_runtime
        if runtime is None:
            if self.morale_states:
                raise ValueError(
                    "A null MoraleRuntime requires an empty morale view",
                )
            if require_runtime_for_roster and roster:
                raise RuntimeError(
                    "A non-empty roster requires MoraleRuntime ownership",
                )
            return

        if self.morale_states is not runtime.states:
            raise ValueError(
                "SimulationContext morale view is detached from MoraleRuntime",
            )
        authoritative_rng = self.rng_manager.get_stream(ModuleId.MORALE)
        if runtime.rng is not authoritative_rng:
            raise ValueError(
                "MoraleRuntime must use RNGManager's MORALE generator",
            )
        if runtime.rout_engine is not self.rout_engine:
            raise ValueError(
                "MoraleRuntime and SimulationContext must share RoutEngine",
            )
        runtime.validate_bindings(roster)

    def all_units(self) -> list[Unit]:
        """Return a flat list of all units across all sides."""
        result: list[Unit] = []
        for units in self.units_by_side.values():
            result.extend(units)
        return result

    def active_units(self, side: str) -> list[Unit]:
        """Return active units for *side*."""
        return [
            u for u in self.units_by_side.get(side, [])
            if u.status == UnitStatus.ACTIVE
        ]

    def side_names(self) -> list[str]:
        """Return sorted side names."""
        return sorted(self.units_by_side.keys())

    # ── State persistence ────────────────────────────────────────────

    def _checkpoint_engines(self) -> tuple[tuple[str, Any], ...]:
        """Return the single ordered registry of context state owners."""
        return tuple(
            (name, getattr(self, name))
            for name in _CONTEXT_STATE_ENGINE_NAMES
        )

    def get_state(self) -> dict[str, Any]:
        """Capture full simulation state for checkpointing."""
        self._validate_morale_bindings(require_runtime_for_roster=True)
        state: dict[str, Any] = {
            "config": _model_dump_json_compatible(self.config),
            "doctrine_side_assignments": [
                assignment.model_dump(mode="json")
                for assignment in self.doctrine_side_assignments
            ],
            "clock": self.clock.get_state(),
            "rng": self.rng_manager.get_state(),
            "units_by_side": {
                side: [u.get_state() for u in units]
                for side, units in self.units_by_side.items()
            },
            "morale_runtime": (
                self.morale_runtime.get_state()
                if self.morale_runtime is not None
                else None
            ),
            "unit_weapon_states": {
                uid: [weapon.get_state() for weapon, _ in weapons]
                for uid, weapons in getattr(self, "unit_weapons", {}).items()
            },
            "unit_sensor_states": {
                uid: [sensor.get_state() for sensor in sensors]
                for uid, sensors in getattr(self, "unit_sensors", {}).items()
            },
            "loadout_builder_fingerprint": (
                self.loadout_builder.fingerprint()
                if self.loadout_builder is not None
                else None
            ),
            "loadout_topology": {
                unit_id: [
                    resolution.topology()
                    for resolution in resolutions
                ]
                for unit_id, resolutions in sorted(
                    self.equipment_resolutions.items(),
                )
            },
            "calibration": (
                self.calibration.model_dump()
                if isinstance(self.calibration, CalibrationSchema)
                else dict(self.calibration)
            ),
        }
        # Delegate to the single ordered registry of context state owners.
        engines = self._checkpoint_engines()
        for name, eng in engines:
            if (
                name in {"stockpile_manager", "supply_network_engine"}
                and self.logistics_runtime is not None
            ):
                continue
            if eng is not None and hasattr(eng, "get_state"):
                state[name] = eng.get_state()
        # Era config
        if self.era_config is not None and hasattr(self.era_config, "model_dump"):
            state["era_config"] = _model_dump_json_compatible(self.era_config)
        return state

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy_morale: bool = False,
    ) -> SimulationContextStatePlan:
        """Validate all context state without mutating the live runtime."""
        self._validate_morale_bindings(require_runtime_for_roster=True)
        staged_state = copy.deepcopy(state)
        self._apply_state(
            staged_state,
            allow_legacy_morale=allow_legacy_morale,
            commit=False,
        )
        return SimulationContextStatePlan(
            owner_id=id(self),
            state=staged_state,
            allow_legacy_morale=allow_legacy_morale,
        )

    def commit_state(self, plan: SimulationContextStatePlan) -> None:
        """Commit a whole-context plan after every owner has preflighted."""
        if plan.owner_id != id(self):
            raise ValueError(
                "Simulation-context checkpoint plan belongs to another "
                "runtime",
            )
        self._apply_state(
            plan.state,
            allow_legacy_morale=plan.allow_legacy_morale,
            commit=True,
        )

    def set_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy_morale: bool = False,
    ) -> None:
        """Validate and atomically restore simulation context state."""
        self.commit_state(
            self.stage_state(
                state,
                allow_legacy_morale=allow_legacy_morale,
            ),
        )

    def _apply_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy_morale: bool,
        commit: bool,
    ) -> None:
        """Preflight context state and optionally commit it."""
        if allow_legacy_morale and "morale_runtime" in state:
            raise ValueError(
                "Versionless checkpoints cannot contain format-113 "
                "morale_runtime state",
            )
        if "config" in state:
            checkpoint_config = state["config"]
            comparable_config = checkpoint_config
            if allow_legacy_morale and isinstance(checkpoint_config, dict):
                comparable_config = copy.deepcopy(checkpoint_config)
                calibration = comparable_config.get(
                    "calibration_overrides",
                )
                morale = (
                    calibration.get("morale")
                    if isinstance(calibration, dict)
                    else None
                )
                if (
                    isinstance(morale, dict)
                    and "use_continuous_time" not in morale
                ):
                    morale["use_continuous_time"] = False
            if (
                not isinstance(checkpoint_config, dict)
                or not _json_values_equal(
                    comparable_config,
                    _model_dump_json_compatible(self.config),
                )
            ):
                raise ValueError(
                    "Checkpoint configuration does not match the runtime "
                    "configuration",
                )
        raw_doctrine_policy = state.get("doctrine_side_assignments")
        if raw_doctrine_policy is None:
            if self.doctrine_side_assignments and not allow_legacy_morale:
                raise ValueError(
                    "Checkpoint is missing runtime doctrine policy",
                )
        else:
            if not isinstance(raw_doctrine_policy, list):
                raise ValueError(
                    "Checkpoint doctrine_side_assignments must be a list",
                )
            try:
                checkpoint_policy = tuple(
                    DoctrineSideAssignment.model_validate(assignment)
                    for assignment in raw_doctrine_policy
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint doctrine policy: {exc}",
                ) from exc
            _doctrine_policy_index(checkpoint_policy)
            if checkpoint_policy != self.doctrine_side_assignments:
                raise ValueError(
                    "Checkpoint doctrine policy does not match the runtime",
                )

        if "era_config" in state:
            from stochastic_warfare.core.era import EraConfig

            raw_era_config = state["era_config"]
            try:
                checkpoint_era_config = EraConfig.model_validate(
                    raw_era_config,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint era configuration: {exc}",
                ) from exc
            if (
                self.era_config is None
                or checkpoint_era_config != self.era_config
            ):
                raise ValueError(
                    "Checkpoint effective era configuration or feature gates "
                    "(including disabled_modules) do not match the runtime",
                )

        if not allow_legacy_morale:
            expected_builder_fingerprint = (
                self.loadout_builder.fingerprint()
                if self.loadout_builder is not None
                else None
            )
            if (
                state.get("loadout_builder_fingerprint")
                != expected_builder_fingerprint
            ):
                raise ValueError(
                    "Checkpoint loadout-builder fingerprint does not match "
                    "the runtime mapping/catalog envelope",
                )
            if not isinstance(state.get("loadout_topology"), dict):
                raise ValueError(
                    "Checkpoint loadout_topology must be a mapping",
                )

        clock_state = state["clock"]
        rng_state = state["rng"]
        expected_clock_fields = {
            "start",
            "current",
            "tick_duration_seconds",
            "tick_count",
        }
        if (
            not isinstance(clock_state, dict)
            or set(clock_state) != expected_clock_fields
        ):
            raise ValueError(
                "Checkpoint clock state has invalid key topology",
            )
        raw_tick_count = clock_state["tick_count"]
        if (
            isinstance(raw_tick_count, bool)
            or not isinstance(raw_tick_count, int)
            or raw_tick_count < 0
        ):
            raise ValueError(
                "Checkpoint clock tick_count must be a non-negative strict "
                "integer",
            )
        raw_tick_duration = clock_state["tick_duration_seconds"]
        if (
            isinstance(raw_tick_duration, bool)
            or not isinstance(raw_tick_duration, (int, float))
            or not math.isfinite(float(raw_tick_duration))
            or float(raw_tick_duration) <= 0.0
        ):
            raise ValueError(
                "Checkpoint clock tick_duration_seconds must be finite and "
                "positive",
            )
        try:
            staged_clock = copy.deepcopy(self.clock)
            staged_clock.set_state(clock_state)
            copy.deepcopy(self.rng_manager).set_state(rng_state)
            elapsed_seconds = staged_clock.elapsed.total_seconds()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid checkpoint clock or RNG state: {exc}") from exc
        if (
            not math.isfinite(elapsed_seconds)
            or elapsed_seconds < 0.0
            or (
                raw_tick_count == 0
                and elapsed_seconds != 0.0
            )
            or (
                raw_tick_count > 0
                and elapsed_seconds <= 0.0
            )
        ):
            raise ValueError(
                "Checkpoint clock tick count and logical time are inconsistent",
            )

        cal_data = state.get("calibration", {})
        if not isinstance(cal_data, dict):
            raise ValueError("Checkpoint calibration must be a mapping")
        staged_calibration = CalibrationSchema(**cal_data)
        current_calibration = (
            self.calibration
            if isinstance(self.calibration, CalibrationSchema)
            else CalibrationSchema.model_validate(self.calibration)
        )
        if staged_calibration != current_calibration:
            raise ValueError(
                "Checkpoint calibration does not match the validated runtime "
                "configuration",
            )

        staged_units: dict[str, list[tuple[dict[str, Any], Unit]]] | None = None
        checkpoint_unit_ids: set[str] = set()
        checkpoint_equipment: (
            dict[str, dict[str, dict[str, Any]]] | None
        ) = None

        if "units_by_side" in state:
            raw_forces = state["units_by_side"]
            if not isinstance(raw_forces, dict):
                raise ValueError("Checkpoint units_by_side must be a mapping")
            staged_units = {}
            seen_ids: set[str] = set()
            for side, raw_units in raw_forces.items():
                if not isinstance(side, str) or not isinstance(raw_units, list):
                    raise ValueError(
                        "Checkpoint force sides must map names to unit lists",
                    )
                staged_units[side] = []
                for raw_unit in raw_units:
                    staged = _stage_checkpoint_unit(raw_unit, side)
                    if staged.entity_id in seen_ids:
                        raise ValueError(
                            "Duplicate checkpoint entity_id "
                            f"{staged.entity_id!r}",
                        )
                    seen_ids.add(staged.entity_id)
                    staged_units[side].append((raw_unit, staged))
            checkpoint_unit_ids = seen_ids
            checkpoint_equipment = {
                staged.entity_id: {
                    equipment_state["equipment_id"]: equipment_state
                    for equipment_state in raw_unit["equipment"]
                }
                for staged_side in staged_units.values()
                for raw_unit, staged in staged_side
            }

        raw_legacy_morale = state.get("morale_states")
        raw_legacy_machine = state.get("morale_machine")
        raw_morale_runtime = state.get("morale_runtime")
        raw_rout_state = state.get("rout_engine")
        staged_morale_plan: Any = None
        existing_by_id: dict[str, Unit] = {}
        for unit in self.all_units():
            if unit.entity_id in existing_by_id:
                raise ValueError(
                    f"Duplicate runtime entity_id {unit.entity_id!r}",
                )
            existing_by_id[unit.entity_id] = unit

        validated_staged_loadouts: RuntimeLoadouts | None = None
        if staged_units is None:
            checkpoint_unit_ids = set(existing_by_id)
            reusable_ids = set(existing_by_id)
        else:
            all_staged_units = [
                staged
                for staged_side in staged_units.values()
                for _, staged in staged_side
            ]
            if not allow_legacy_morale and self.loadout_builder is not None:
                validated_staged_loadouts = self.loadout_builder.build(
                    all_staged_units,
                )

            reusable_ids: set[str] = set()
            for staged in all_staged_units:
                existing = existing_by_id.get(staged.entity_id)
                if existing is None:
                    continue
                if allow_legacy_morale:
                    if type(existing) is type(staged):
                        reusable_ids.add(staged.entity_id)
                    continue
                if (
                    type(existing) is not type(staged)
                    or existing.unit_type != staged.unit_type
                    or existing.domain is not staged.domain
                ):
                    raise ValueError(
                        "Checkpoint unit identity topology does not match the "
                        f"runtime for {staged.entity_id!r}",
                    )
                existing_equipment_ids = [
                    equipment.equipment_id
                    for equipment in existing.equipment
                ]
                staged_equipment_ids = [
                    equipment.equipment_id
                    for equipment in staged.equipment
                ]
                if staged_equipment_ids != existing_equipment_ids:
                    raise ValueError(
                        "Checkpoint equipment identity/order topology does not "
                        f"match the runtime for {staged.entity_id!r}",
                    )
                reusable_ids.add(staged.entity_id)

        if (
            (
                self.commander_engine is not None
                or self.school_registry is not None
            )
            and self.aggregation_engine is not None
            and self.aggregation_engine._config.enable_aggregation
        ):
            raise ValueError(
                "Commander/school checkpoint restoration with enabled force "
                "aggregation is unsupported",
            )

        staged_commander_plan: CommanderAssignmentPlan | None = None
        if self.commander_engine is not None:
            raw_commander_state = state.get("commander_engine")
            if raw_commander_state is None:
                if not allow_legacy_morale:
                    raise ValueError(
                        "Checkpoint is missing commander_engine state",
                    )
            elif not isinstance(raw_commander_state, Mapping):
                raise ValueError(
                    "Checkpoint commander_engine state must be a mapping",
                )
            else:
                try:
                    staged_commander_plan = (
                        self.commander_engine.stage_state(
                            raw_commander_state,
                            expected_unit_ids=checkpoint_unit_ids,
                        )
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid checkpoint commander state: {exc}",
                    ) from exc
        elif "commander_engine" in state:
            raise ValueError(
                "Checkpoint contains commander state for a runtime without "
                "a commander engine",
            )

        staged_school_plan: Any = None
        if self.school_registry is not None:
            raw_school_state = state.get("school_registry")
            if raw_school_state is None:
                if not allow_legacy_morale:
                    raise ValueError(
                        "Checkpoint is missing school_registry state",
                    )
            elif not isinstance(raw_school_state, Mapping):
                raise ValueError(
                    "Checkpoint school_registry state must be a mapping",
                )
            else:
                try:
                    staged_school_plan = self.school_registry.stage_state(
                        raw_school_state,
                        expected_unit_ids=checkpoint_unit_ids,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid checkpoint school state: {exc}",
                    ) from exc
        elif "school_registry" in state:
            raise ValueError(
                "Checkpoint contains school state for a runtime without a "
                "school registry",
            )

        staged_ooda_plan: Any = None
        if self.commander_engine is not None:
            if self.ooda_engine is None:
                raise ValueError(
                    "Commander checkpoint runtime is missing its OODA engine",
                )
            raw_ooda_state = state.get("ooda_engine")
            if raw_ooda_state is None:
                if not allow_legacy_morale:
                    raise ValueError(
                        "Checkpoint is missing commander OODA state",
                    )
            elif not isinstance(raw_ooda_state, Mapping):
                raise ValueError(
                    "Checkpoint OODA state must be a mapping",
                )
            else:
                try:
                    staged_ooda_plan = self.ooda_engine.stage_state(
                        raw_ooda_state,
                        expected_unit_ids=checkpoint_unit_ids,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid checkpoint commander OODA state: {exc}",
                    ) from exc

        current_unit_weapons = getattr(self, "unit_weapons", {})
        current_unit_sensors = getattr(self, "unit_sensors", {})
        current_equipment_resolutions = getattr(
            self,
            "equipment_resolutions",
            {},
        )
        runtime_unit_weapons = dict(current_unit_weapons)
        runtime_unit_sensors = dict(current_unit_sensors)
        runtime_equipment_resolutions = dict(
            current_equipment_resolutions,
        )
        compatible_weapon_ids = set(reusable_ids)
        compatible_sensor_ids = set(reusable_ids)

        if staged_units is not None:
            reconstructed_units = [
                staged
                for staged_side in staged_units.values()
                for _, staged in staged_side
                if staged.entity_id not in reusable_ids
            ]
            can_rebuild_loadouts = self.loadout_builder is not None
            if reconstructed_units and can_rebuild_loadouts:
                rebuilt_loadouts = (
                    validated_staged_loadouts
                    if validated_staged_loadouts is not None
                    else self.loadout_builder.build(reconstructed_units)
                )
                reconstructed_ids = {
                    unit.entity_id
                    for unit in reconstructed_units
                }
                runtime_unit_weapons.update({
                    entity_id: attachments
                    for entity_id, attachments
                    in rebuilt_loadouts.unit_weapons.items()
                    if entity_id in reconstructed_ids
                })
                runtime_unit_sensors.update({
                    entity_id: sensors
                    for entity_id, sensors
                    in rebuilt_loadouts.unit_sensors.items()
                    if entity_id in reconstructed_ids
                })
                runtime_equipment_resolutions.update({
                    entity_id: resolutions
                    for entity_id, resolutions
                    in rebuilt_loadouts.equipment_resolutions.items()
                    if entity_id in reconstructed_ids
                })
                compatible_weapon_ids.update(reconstructed_ids)
                compatible_sensor_ids.update(reconstructed_ids)

        if not allow_legacy_morale:
            topology_resolutions = (
                validated_staged_loadouts.equipment_resolutions
                if validated_staged_loadouts is not None
                else runtime_equipment_resolutions
            )
            runtime_topology = {
                entity_id: [
                    resolution.topology()
                    for resolution in topology_resolutions.get(
                        entity_id,
                        (),
                    )
                ]
                for entity_id in sorted(
                    set(topology_resolutions)
                    & checkpoint_unit_ids,
                )
            }
            if not _json_values_equal(
                state["loadout_topology"],
                runtime_topology,
            ):
                raise ValueError(
                    "Checkpoint loadout resolution topology does not match "
                    "the runtime builder output",
                )

        staged_weapon_states: list[tuple[Any, dict[str, Any]]] = []
        if "unit_weapon_states" in state:
            staged_weapon_states = _stage_runtime_instance_states(
                state["unit_weapon_states"],
                runtime_unit_weapons,
                checkpoint_unit_ids,
                compatible_weapon_ids,
                checkpoint_equipment,
                kind="weapon",
            )

        staged_sensor_states: list[tuple[Any, dict[str, Any]]] = []
        if "unit_sensor_states" in state:
            staged_sensor_states = _stage_runtime_instance_states(
                state["unit_sensor_states"],
                runtime_unit_sensors,
                checkpoint_unit_ids,
                compatible_sensor_ids,
                checkpoint_equipment,
                kind="sensor",
            )

        prospective_units_by_side = (
            {
                side: [
                    staged
                    for _, staged in staged_side
                ]
                for side, staged_side in staged_units.items()
            }
            if staged_units is not None
            else {
                side: list(units)
                for side, units in self.units_by_side.items()
            }
        )
        configured_sides = getattr(self.config, "sides", ())
        declared_sides = {
            side.side
            for side in configured_sides
        }
        requires_exact_force_topology = any(
            component is not None
            for component in (
                self.fog_of_war,
                self.space_engine,
                self.movement_diagnostics,
            )
        )
        if (
            requires_exact_force_topology
            and set(prospective_units_by_side) != declared_sides
        ):
            raise ValueError(
                "Checkpoint unit-side topology does not match scenario sides",
            )
        expected_sides = (
            declared_sides
            if requires_exact_force_topology
            else set(prospective_units_by_side)
        )
        expected_target_sides = {
            unit.entity_id: side
            for side, units in prospective_units_by_side.items()
            for unit in units
        }
        prospective_morale_units = {
            unit.entity_id: unit
            for units in prospective_units_by_side.values()
            for unit in units
        }
        aggregate_morale_topology = _checkpoint_aggregate_morale_topology(
            state.get("aggregation_engine"),
        )
        aggregate_constituents = aggregate_morale_topology.constituents
        if allow_legacy_morale and aggregate_constituents:
            raise ValueError(
                "Versionless checkpoints with active aggregation cannot "
                "reconstruct complete morale records",
            )

        if self.morale_runtime is None:
            if prospective_morale_units:
                raise ValueError(
                    "A non-empty checkpoint roster requires MoraleRuntime",
                )
            if raw_morale_runtime is not None:
                raise ValueError(
                    "Checkpoint contains morale state for a context without "
                    "MoraleRuntime",
                )
            if aggregate_constituents or _checkpoint_has_active_routes(
                state.get("rout_engine"),
            ):
                raise ValueError(
                    "A null morale runtime requires empty route and "
                    "aggregation state",
                )
        else:
            if allow_legacy_morale:
                (
                    raw_morale_runtime,
                    raw_rout_state,
                ) = _migrate_legacy_morale_runtime(
                    context_morale=raw_legacy_morale,
                    machine_state=raw_legacy_machine,
                    units=prospective_morale_units,
                    side_initial={
                        side.side: side.morale_initial
                        for side in self.config.sides
                    },
                    elapsed_time_s=elapsed_seconds,
                    continuous_time=(
                        self.morale_runtime.config.use_continuous_time
                    ),
                    authoritative_rng_state=(
                        rng_state["streams"][ModuleId.MORALE.value]
                    ),
                    rout_state=raw_rout_state,
                )
            if not isinstance(raw_morale_runtime, dict):
                raise ValueError(
                    "Checkpoint morale_runtime must be a mapping",
                )
            try:
                staged_morale_plan = self.morale_runtime.stage_state(
                    raw_morale_runtime,
                    expected_units=prospective_morale_units,
                    elapsed_time_s=elapsed_seconds,
                    aggregate_constituents=aggregate_constituents,
                    suspended_statuses=aggregate_morale_topology.statuses,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint morale runtime state: {exc}",
                ) from exc

        staged_rout_plan: Any = None
        if self.rout_engine is None:
            if state.get("rout_engine") is not None:
                raise ValueError(
                    "Checkpoint contains rout state for a context without "
                    "RoutEngine",
                )
        else:
            if raw_rout_state is None:
                if not allow_legacy_morale:
                    raise ValueError("Checkpoint is missing RoutEngine state")
                raw_rout_state = {"active_routs": {}}
            routed_ids = (
                {
                    unit_id
                    for unit_id, record in staged_morale_plan.active_records
                    if record.current_state.name == "ROUTED"
                }
                if staged_morale_plan is not None
                else set()
            )
            try:
                staged_rout_plan = self.rout_engine.stage_state(
                    raw_rout_state,
                    expected_routing_unit_ids=routed_ids,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint RoutEngine state: {exc}",
                ) from exc

        staged_movement_plan: Any = None
        if (
            self.movement_diagnostics is not None
            and "movement_diagnostics" in state
        ):
            try:
                staged_movement_plan = (
                    self.movement_diagnostics.stage_state(
                        state["movement_diagnostics"],
                        expected_unit_sides=expected_target_sides,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint movement diagnostics state: {exc}",
                ) from exc
        elif (
            self.movement_diagnostics is None
            and "movement_diagnostics" in state
        ):
            raise ValueError(
                "Checkpoint contains movement diagnostics for a context "
                "without a movement-diagnostics owner",
            )

        staged_obscurants_plan: Any = None
        if (
            self.obscurants_engine is not None
            and "obscurants_engine" in state
        ):
            try:
                staged_obscurants_plan = (
                    self.obscurants_engine.stage_state(
                        state["obscurants_engine"],
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint obscurants state: {exc}",
                ) from exc
        elif self.obscurants_engine is None and "obscurants_engine" in state:
            raise ValueError(
                "Checkpoint contains obscurants state for a context without "
                "an obscurants engine",
            )

        staged_fog_plan: Any = None
        if self.fog_of_war is not None and "fog_of_war" in state:
            satellite_topology = (
                {
                    satellite.satellite_id: (
                        satellite.side,
                        satellite.constellation_id,
                    )
                    for satellite in (
                        self.space_engine.constellation_manager
                        .all_satellites()
                    )
                }
                if self.space_engine is not None
                else {}
            )
            try:
                staged_fog_plan = self.fog_of_war.stage_state(
                    state["fog_of_war"],
                    expected_sides=expected_sides,
                    expected_target_sides=expected_target_sides,
                    satellite_topology=satellite_topology,
                    checkpoint_elapsed_s=(
                        staged_clock.elapsed.total_seconds()
                    ),
                    authoritative_rng_state=(
                        rng_state["streams"][ModuleId.DETECTION.value]
                    ),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint fog/fusion state: {exc}",
                ) from exc
        elif self.fog_of_war is None and "fog_of_war" in state:
            raise ValueError(
                "Checkpoint contains fog-of-war state for a context without "
                "a fog-of-war manager",
            )

        staged_logistics_plan: Any = None
        if (
            self.logistics_runtime is not None
            and "logistics_runtime" in state
        ):
            checkpoint_units = (
                {
                    staged.entity_id: staged
                    for staged_side in staged_units.values()
                    for _, staged in staged_side
                }
                if staged_units is not None
                else existing_by_id
            )
            try:
                staged_logistics_plan = (
                    self.logistics_runtime.stage_state(
                        state["logistics_runtime"],
                        expected_units=checkpoint_units,
                        expected_elapsed_seconds=(
                            staged_clock.elapsed.total_seconds()
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint logistics runtime state: {exc}",
                ) from exc

        staged_space_plan: Any = None
        if self.space_engine is not None and "space_engine" in state:
            delivered_receipts = (
                tuple(staged_fog_plan["intel_fusion"]["delivery_receipts"])
                if staged_fog_plan is not None
                else ()
            )
            try:
                staged_space_plan = self.space_engine.stage_state(
                    state["space_engine"],
                    expected_elapsed_s=(
                        staged_clock.elapsed.total_seconds()
                    ),
                    expected_tick_count=staged_clock.tick_count,
                    expected_sides=tuple(sorted(expected_sides)),
                    expected_units_by_side=prospective_units_by_side,
                    delivered_receipts=delivered_receipts,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint space runtime state: {exc}",
                ) from exc
        elif self.space_engine is None and "space_engine" in state:
            raise ValueError(
                "Checkpoint contains space runtime state for a context without "
                "a space engine",
            )

        staged_indirect_fire_plan: Any = None
        if (
            self.indirect_fire_engine is not None
            and "indirect_fire_engine" in state
        ):
            prospective_units = (
                {
                    staged.entity_id: staged
                    for staged_side in staged_units.values()
                    for _, staged in staged_side
                }
                if staged_units is not None
                else existing_by_id
            )
            raw_weapon_states = state.get("unit_weapon_states")
            if not isinstance(raw_weapon_states, dict):
                raise ValueError(
                    "Checkpoint with indirect-fire plans requires "
                    "unit_weapon_states",
                )
            expected_resources: list[dict[str, Any]] = []
            for (
                unit_id,
                source_equipment_index,
                weapon_id,
            ) in self.indirect_fire_engine.planned_attachment_keys:
                attachments = runtime_unit_weapons.get(unit_id, ())
                matches = [
                    (index, attachment)
                    for index, attachment in enumerate(attachments)
                    if (
                        attachment.source_equipment_index
                        == source_equipment_index
                        and attachment.weapon.weapon_id == weapon_id
                    )
                ]
                if len(matches) != 1:
                    raise ValueError(
                        "Checkpoint indirect-fire attachment topology "
                        f"mismatch for {(unit_id, source_equipment_index, weapon_id)!r}",
                    )
                attachment_index, _attachment = matches[0]
                saved_unit_weapons = raw_weapon_states.get(unit_id)
                if (
                    not isinstance(saved_unit_weapons, list)
                    or attachment_index >= len(saved_unit_weapons)
                ):
                    raise ValueError(
                        "Checkpoint indirect-fire weapon state is missing "
                        f"for {unit_id!r}",
                    )
                observation = (
                    self.indirect_fire_engine
                    .canonical_resource_observation(
                        saved_unit_weapons[attachment_index],
                    )
                )
                expected_resources.append({
                    "unit_id": unit_id,
                    "source_equipment_index": source_equipment_index,
                    "weapon_id": weapon_id,
                    **observation,
                })
            try:
                staged_indirect_fire_plan = (
                    self.indirect_fire_engine.stage_state(
                        state["indirect_fire_engine"],
                        expected_elapsed_s=(
                            staged_clock.elapsed.total_seconds()
                        ),
                        expected_combat_rng_state=(
                            rng_state["streams"][ModuleId.COMBAT.value]
                        ),
                        expected_resource_observations=expected_resources,
                        expected_unit_statuses={
                            unit_id: unit.status.name
                            for unit_id, unit in prospective_units.items()
                        },
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint indirect-fire runtime state: {exc}",
                ) from exc
        elif (
            self.indirect_fire_engine is None
            and "indirect_fire_engine" in state
        ):
            raise ValueError(
                "Checkpoint contains indirect-fire state for a context "
                "without an indirect-fire engine",
            )

        # Legacy state owners do not yet expose typed stage/commit plans.
        # Validate each one on an isolated clone and require an exact
        # canonical round trip before any context-owned state is mutated.
        canonical_engine_states: dict[str, Any] = {}
        for name, engine in self._checkpoint_engines():
            if name in {
                "logistics_runtime",
                "space_engine",
                "indirect_fire_engine",
                "commander_engine",
                "school_registry",
                "rout_engine",
            }:
                continue
            if name == "ooda_engine" and staged_ooda_plan is not None:
                continue
            if name == "fog_of_war" and staged_fog_plan is not None:
                continue
            if (
                name == "movement_diagnostics"
                and staged_movement_plan is not None
            ):
                continue
            if (
                name == "obscurants_engine"
                and staged_obscurants_plan is not None
            ):
                continue
            if (
                name in {"stockpile_manager", "supply_network_engine"}
                and "logistics_runtime" in state
            ):
                continue
            if (
                engine is None
                or name not in state
                or not hasattr(engine, "set_state")
            ):
                continue
            try:
                isolated_bus = EventBus()
                staged_engine = copy.deepcopy(
                    engine,
                    {id(self.event_bus): isolated_bus},
                )
                staged_engine.set_state(copy.deepcopy(state[name]))
                canonical_state = (
                    staged_engine.get_state()
                    if hasattr(staged_engine, "get_state")
                    else copy.deepcopy(state[name])
                )
                if not _json_values_equal(
                    _json_compatible_value(state[name]),
                    _json_compatible_value(canonical_state),
                ):
                    raise ValueError(
                        "state does not round-trip canonically",
                    )
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid checkpoint {name} state: {exc}",
                ) from exc
            canonical_engine_states[name] = canonical_state

        if not commit:
            return

        # Commit only after all context-owned checkpoint state validates.
        self.clock.set_state(clock_state)
        self.rng_manager.set_state(rng_state)

        if staged_units is not None:
            restored_by_side: dict[str, list[Unit]] = {}
            for side, staged_side in staged_units.items():
                restored_by_side[side] = []
                for raw_unit, staged in staged_side:
                    existing = existing_by_id.get(staged.entity_id)
                    if existing is not None and type(existing) is type(staged):
                        existing.set_state(raw_unit)
                        restored = existing
                    else:
                        restored = staged
                    restored_by_side[side].append(restored)

            self.units_by_side = restored_by_side
            if "unit_weapon_states" in state:
                self.unit_weapons = {
                    entity_id: (
                        runtime_unit_weapons.get(entity_id, ())
                        if entity_id in compatible_weapon_ids
                        else ()
                    )
                    for entity_id in state["unit_weapon_states"]
                }
            else:
                self.unit_weapons = {
                    entity_id: weapons
                    for entity_id, weapons in runtime_unit_weapons.items()
                    if entity_id in checkpoint_unit_ids
                }
            if "unit_sensor_states" in state:
                self.unit_sensors = {
                    entity_id: (
                        runtime_unit_sensors.get(entity_id, ())
                        if entity_id in compatible_sensor_ids
                        else ()
                    )
                    for entity_id in state["unit_sensor_states"]
                }
            else:
                self.unit_sensors = {
                    entity_id: sensors
                    for entity_id, sensors in runtime_unit_sensors.items()
                    if entity_id in checkpoint_unit_ids
                }
            self.equipment_resolutions = {
                entity_id: resolutions
                for entity_id, resolutions
                in runtime_equipment_resolutions.items()
                if entity_id in checkpoint_unit_ids
            }

        if staged_morale_plan is not None:
            self.morale_runtime.commit_state(
                staged_morale_plan,
                units={
                    unit.entity_id: unit
                    for unit in self.all_units()
                },
                elapsed_time_s=elapsed_seconds,
                aggregate_constituents=aggregate_constituents,
                suspended_statuses=aggregate_morale_topology.statuses,
            )
        if staged_rout_plan is not None:
            self.rout_engine.commit_state(staged_rout_plan)

        for instance, saved_state in staged_weapon_states:
            instance.set_state(saved_state)
        for instance, saved_state in staged_sensor_states:
            instance.set_state(saved_state)
        if staged_indirect_fire_plan is not None:
            self.indirect_fire_engine.commit_state(
                staged_indirect_fire_plan,
            )
        if staged_logistics_plan is not None:
            self.logistics_runtime.commit_state(staged_logistics_plan)
        if staged_fog_plan is not None:
            self.fog_of_war.commit_state(staged_fog_plan)
        if staged_space_plan is not None:
            self.space_engine.commit_state(staged_space_plan)
        if staged_movement_plan is not None:
            self.movement_diagnostics.commit_state(staged_movement_plan)
        if staged_obscurants_plan is not None:
            self.obscurants_engine.commit_state(staged_obscurants_plan)
        if staged_commander_plan is not None:
            self.commander_engine.commit_state(staged_commander_plan)
        if staged_school_plan is not None:
            self.school_registry.commit_state(staged_school_plan)
        if staged_ooda_plan is not None:
            self.ooda_engine.commit_state(staged_ooda_plan)

        # Regenerate flat dict after restoring forces (Phase 86).
        if isinstance(self.calibration, CalibrationSchema):
            self.cal_flat = self.calibration.to_flat_dict(self.side_names())

        # Restore generic owners in the same registry order used by capture.
        engines = self._checkpoint_engines()
        for name, eng in engines:
            if name in {
                "logistics_runtime",
                "space_engine",
                "indirect_fire_engine",
                "commander_engine",
                "school_registry",
                "rout_engine",
            }:
                continue
            if name == "ooda_engine" and staged_ooda_plan is not None:
                continue
            if name == "fog_of_war" and staged_fog_plan is not None:
                continue
            if (
                name == "movement_diagnostics"
                and staged_movement_plan is not None
            ):
                continue
            if (
                name == "obscurants_engine"
                and staged_obscurants_plan is not None
            ):
                continue
            if (
                name in {"stockpile_manager", "supply_network_engine"}
                and "logistics_runtime" in state
            ):
                continue
            if (
                eng is not None
                and name in canonical_engine_states
                and hasattr(eng, "set_state")
            ):
                eng.set_state(canonical_engine_states[name])

        self._validate_morale_bindings(require_runtime_for_roster=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _initialize_commander_ooda(
    *,
    commander_engine: CommanderEngine,
    ooda_engine: Any,
    school_registry: Any,
    assignments: tuple[tuple[str, str], ...],
    c2_rng: np.random.Generator,
    timestamp: datetime,
) -> None:
    """Register and start exact commander OODA state transactionally."""
    from stochastic_warfare.c2.ai.ooda import OODAPhase
    from stochastic_warfare.entities.organization.echelons import (
        EchelonLevel,
    )

    ooda_before = ooda_engine.get_state()
    c2_rng_before = copy.deepcopy(c2_rng.bit_generator.state)
    try:
        for unit_id, _profile_id in sorted(assignments):
            ooda_engine.register_commander(
                unit_id,
                int(EchelonLevel.COMPANY),
            )
            school_multiplier = 1.0
            if school_registry is not None:
                school = school_registry.get_for_unit(unit_id)
                if school is not None:
                    school_multiplier = school.get_ooda_multiplier()
            ooda_engine.start_phase(
                unit_id,
                OODAPhase.OBSERVE,
                personality_mult=(
                    commander_engine.get_ooda_speed_multiplier(unit_id)
                ),
                tactical_mult=(
                    ooda_engine.tactical_acceleration
                    * school_multiplier
                ),
                ts=timestamp,
                publish_event=False,
            )
    except Exception:
        ooda_engine.set_state(ooda_before)
        c2_rng.bit_generator.state = c2_rng_before
        raise


def _doctrine_policy_index(
    assignments: tuple[DoctrineSideAssignment, ...],
) -> dict[str, str]:
    """Validate a typed ordered policy before creating an internal index."""
    sides = [assignment.side for assignment in assignments]
    if len(sides) != len(set(sides)):
        raise ValueError(
            f"Doctrine policy side IDs must be unique: {sides!r}",
        )
    return {
        assignment.side: assignment.school_id
        for assignment in assignments
    }


def _prepare_runtime_school_plan(
    *,
    config: CampaignScenarioConfig,
    commander_engine: CommanderEngine | None,
    commander_assignments: tuple[tuple[str, str], ...],
    school_registry: Any,
    unit_sides: Mapping[str, str],
    doctrine_side_assignments: tuple[DoctrineSideAssignment, ...],
) -> Any:
    """Stage profile, exact-unit, then highest-precedence side policy."""
    school_assignments: dict[str, str] = {}
    if commander_engine is not None:
        school_assignments.update({
            unit_id: personality.school_id
            for unit_id, profile_id in commander_assignments
            if (
                personality
                := commander_engine.get_profile_definition(profile_id)
            ).school_id is not None
        })

    exact_assignments = (
        config.school_config.get("unit_assignments", {})
        if config.school_config is not None
        else {}
    )
    if not isinstance(exact_assignments, Mapping):
        raise ValueError(
            "school_config.unit_assignments must be a mapping",
        )
    school_assignments.update({
        unit_id: exact_assignments[unit_id]
        for unit_id in unit_sides
        if unit_id in exact_assignments
    })

    side_policy = _doctrine_policy_index(doctrine_side_assignments)
    school_assignments.update({
        unit_id: side_policy[side]
        for unit_id, side in unit_sides.items()
        if side in side_policy
    })
    if not school_assignments:
        return None
    if school_registry is None:
        raise ValueError(
            "Runtime school assignments require a loaded school registry",
        )
    return school_registry.prepare_assignments(
        school_assignments,
        expected_unit_ids=set(unit_sides),
    )


def register_dynamic_units(
    ctx: SimulationContext,
    units: list[Unit],
) -> None:
    """Atomically register fully constructed units and their runtime state.

    Loadouts and side-derived morale are staged before any context-owned
    mapping changes.  A failed wave therefore remains retryable and cannot
    leave partial roster, loadout, or morale state behind.
    """
    if not units:
        return

    unit_ids = [unit.entity_id for unit in units]
    if any(not unit_id for unit_id in unit_ids):
        raise ValueError("Dynamic units require non-empty entity IDs")
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError(
            f"Dynamic unit wave contains duplicate entity IDs: {unit_ids!r}",
        )

    existing_ids = {unit.entity_id for unit in ctx.all_units()}
    collisions = sorted(existing_ids & set(unit_ids))
    if collisions:
        raise ValueError(
            f"Dynamic unit IDs already exist in the scenario: {collisions!r}",
        )

    unknown_sides = sorted(
        {
            unit.side if isinstance(unit.side, str) else unit.side.value
            for unit in units
        }
        - set(ctx.units_by_side)
    )
    if unknown_sides:
        raise ValueError(
            f"Dynamic units reference unknown sides: {unknown_sides!r}",
        )

    if ctx.loadout_builder is None:
        raise RuntimeError(
            "Dynamic units require the scenario's RuntimeLoadoutBuilder",
        )
    incoming_loadouts = ctx.loadout_builder.build(units)
    incoming_weapons = incoming_loadouts.unit_weapons
    incoming_sensors = incoming_loadouts.unit_sensors
    incoming_resolutions = incoming_loadouts.equipment_resolutions
    incoming_ids = set(unit_ids)
    if set(incoming_weapons) != incoming_ids:
        raise ValueError("Dynamic weapon loadout topology is incomplete")
    if set(incoming_sensors) != incoming_ids:
        raise ValueError("Dynamic sensor loadout topology is incomplete")

    incoming_morale = _initial_morale_for_units(ctx.config, units)
    incoming_statuses = {
        unit.entity_id: _initial_status_for_morale(
            incoming_morale[unit.entity_id],
        )
        for unit in units
    }
    if set(ctx.unit_weapons) & incoming_ids:
        raise ValueError("Dynamic weapon loadout IDs already exist")
    if set(ctx.unit_sensors) & incoming_ids:
        raise ValueError("Dynamic sensor loadout IDs already exist")
    if set(ctx.equipment_resolutions) & incoming_ids:
        raise ValueError("Dynamic equipment-resolution IDs already exist")
    if set(ctx.morale_states) & incoming_ids:
        raise ValueError("Dynamic morale IDs already exist")
    if ctx.morale_runtime is None:
        raise RuntimeError("Dynamic units require a morale runtime")

    commander_plan: CommanderAssignmentPlan | None = None
    school_plan: Any = None
    if ctx.commander_engine is not None:
        if ctx.ooda_engine is None:
            raise RuntimeError(
                "Dynamic commander assignments require an OODA engine",
            )
        existing_commander_ids = set(
            ctx.commander_engine.assignments(),
        )
        if existing_commander_ids != existing_ids:
            raise ValueError(
                "Commander assignment topology does not match the current "
                "runtime roster",
            )
        existing_ooda_ids = set(
            ctx.ooda_engine.get_state()["commanders"],
        )
        if existing_ooda_ids != existing_ids:
            raise ValueError(
                "OODA commander topology does not match the current "
                "runtime roster",
            )
        side_profiles = {
            side.side: side.commander_profile
            for side in ctx.config.sides
        }
        commander_overrides = (
            ctx.config.commander_config.assignments
            if ctx.config.commander_config is not None
            else {}
        )
        incoming_assignments = {
            unit.entity_id: commander_overrides.get(
                unit.entity_id,
                side_profiles[
                    (
                        unit.side
                        if isinstance(unit.side, str)
                        else unit.side.value
                    )
                ],
            )
            for unit in units
        }
        commander_plan = ctx.commander_engine.prepare_assignments(
            incoming_assignments,
            expected_unit_ids=incoming_ids,
            require_complete=True,
        )
    school_plan = _prepare_runtime_school_plan(
        config=ctx.config,
        commander_engine=ctx.commander_engine,
        commander_assignments=(
            commander_plan.assignments
            if commander_plan is not None
            else ()
        ),
        school_registry=ctx.school_registry,
        unit_sides={
            unit.entity_id: (
                unit.side
                if isinstance(unit.side, str)
                else unit.side.value
            )
            for unit in units
        },
        doctrine_side_assignments=ctx.doctrine_side_assignments,
    )

    logistics_plan = None
    logistics_before = None
    if ctx.logistics_runtime is not None:
        elapsed_seconds = ctx.clock.elapsed.total_seconds()
        logistics_plan = ctx.logistics_runtime.prepare_unit_registration(
            units,
            eligible_from_seconds=elapsed_seconds,
        )
        logistics_before = ctx.logistics_runtime.get_state()

    staged_units_by_side = {
        side: list(side_units)
        for side, side_units in ctx.units_by_side.items()
    }
    for unit in units:
        side = unit.side if isinstance(unit.side, str) else unit.side.value
        staged_units_by_side[side].append(unit)
    staged_weapons = dict(ctx.unit_weapons)
    staged_weapons.update(incoming_weapons)
    staged_sensors = dict(ctx.unit_sensors)
    staged_sensors.update(incoming_sensors)
    staged_resolutions = dict(ctx.equipment_resolutions)
    staged_resolutions.update(incoming_resolutions)
    morale_before = ctx.morale_runtime.get_state()
    commander_before = (
        ctx.commander_engine.get_state()
        if ctx.commander_engine is not None
        else None
    )
    school_before = (
        ctx.school_registry.get_state()
        if ctx.school_registry is not None
        else None
    )
    ooda_before = (
        ctx.ooda_engine.get_state()
        if ctx.commander_engine is not None
        else None
    )
    c2_rng = ctx.rng_manager.get_stream(ModuleId.C2)
    c2_rng_before = copy.deepcopy(c2_rng.bit_generator.state)
    incoming_status_before = tuple((unit, unit.status) for unit in units)

    # Every component has validated the complete batch before the first
    # commit. Roll back all component-owned state if an unexpected commit
    # failure occurs so the reinforcement wave remains retryable.
    try:
        if logistics_plan is not None:
            ctx.logistics_runtime.commit_unit_registration(logistics_plan)
        for unit in units:
            unit.status = incoming_statuses[unit.entity_id]
        ctx.morale_runtime.register_units(
            tuple(
                MoraleRegistration(
                    unit_id=unit.entity_id,
                    initial_state=incoming_morale[unit.entity_id],
                )
                for unit in units
            ),
            {unit.entity_id: unit for unit in units},
        )
        if commander_plan is not None:
            ctx.commander_engine.commit_assignments(commander_plan)
        if school_plan is not None:
            ctx.school_registry.commit_assignments(school_plan)
        if commander_plan is not None:
            _initialize_commander_ooda(
                commander_engine=ctx.commander_engine,
                ooda_engine=ctx.ooda_engine,
                school_registry=ctx.school_registry,
                assignments=commander_plan.assignments,
                c2_rng=c2_rng,
                timestamp=ctx.clock.current_time,
            )
        if ctx.movement_diagnostics is not None:
            ctx.movement_diagnostics.register_units({
                unit.entity_id: unit.side
                for unit in units
            })
    except Exception:
        for unit, status in incoming_status_before:
            unit.status = status
        if logistics_before is not None:
            ctx.logistics_runtime.set_state(
                logistics_before,
                expected_units={
                    unit.entity_id: unit
                    for unit in ctx.all_units()
                },
            )
        rollback_aggregate_topology = (
            _checkpoint_aggregate_morale_topology(
                ctx.aggregation_engine.get_state(),
            )
            if ctx.aggregation_engine is not None
            else _CheckpointAggregateMoraleTopology({}, {})
        )
        ctx.morale_runtime.set_state(
            morale_before,
            expected_units={
                unit.entity_id: unit
                for unit in ctx.all_units()
            },
            elapsed_time_s=ctx.clock.elapsed.total_seconds(),
            aggregate_constituents=rollback_aggregate_topology.constituents,
            suspended_statuses=rollback_aggregate_topology.statuses,
        )
        if commander_before is not None:
            ctx.commander_engine.set_state(commander_before)
        if school_before is not None:
            ctx.school_registry.set_state(school_before)
        if ooda_before is not None:
            ctx.ooda_engine.set_state(ooda_before)
        c2_rng.bit_generator.state = c2_rng_before
        raise
    ctx.units_by_side = staged_units_by_side
    ctx.unit_weapons = staged_weapons
    ctx.unit_sensors = staged_sensors
    ctx.equipment_resolutions = staged_resolutions


def _parse_weather_state(precip: str) -> int:
    """Map scenario precipitation string to WeatherState int."""
    from stochastic_warfare.environment.weather import WeatherState

    _MAP = {
        "clear": WeatherState.CLEAR,
        "partly_cloudy": WeatherState.PARTLY_CLOUDY,
        "overcast": WeatherState.OVERCAST,
        "light_rain": WeatherState.LIGHT_RAIN,
        "heavy_rain": WeatherState.HEAVY_RAIN,
        "snow": WeatherState.SNOW,
        "fog": WeatherState.FOG,
        "storm": WeatherState.STORM,
    }
    return _MAP.get(precip.lower(), WeatherState.CLEAR)


# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------


def _parse_start_time(date_str: str) -> datetime:
    """Parse ISO date/datetime string into UTC-aware datetime."""
    if "T" in date_str:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    parts = date_str.split("-")
    return datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)


class ScenarioLoader:
    """Load a campaign scenario from YAML and wire all domain engines.

    Parameters
    ----------
    data_dir:
        Root data directory containing ``units/``, ``weapons/``, etc.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    def load(
        self,
        scenario_path: Path,
        seed: int = 42,
        *,
        calibration_overrides: Mapping[str, Any] | CalibrationSchema | None = None,
        scenario_config: CampaignScenarioConfig | None = None,
        doctrine_side_assignments: tuple[
            DoctrineSideAssignment,
            ...,
        ] | None = None,
    ) -> SimulationContext:
        """Load a campaign scenario and create a fully-wired context.

        Parameters
        ----------
        scenario_path:
            Path to the campaign scenario YAML file.
        seed:
            Master PRNG seed for deterministic replay.
        calibration_overrides:
            Sparse ``CalibrationSchema`` overlay applied without mutating the
            source scenario.
        scenario_config:
            Prevalidated effective configuration supplied by an orchestrator.
        doctrine_side_assignments:
            Highest-precedence typed per-side school policy supplied by the
            runtime factory. It is not written into scenario YAML.
        """
        # 1. Parse config
        if scenario_config is not None and calibration_overrides is not None:
            raise ValueError(
                "scenario_config and calibration_overrides are mutually exclusive",
            )
        if scenario_config is None:
            config = load_campaign_scenario_config(
                scenario_path,
                calibration_overrides,
            )
        else:
            config = CampaignScenarioConfig.model_validate(
                scenario_config.model_dump(mode="python"),
            )
        doctrine_policy = tuple(doctrine_side_assignments or ())
        if any(
            not isinstance(assignment, DoctrineSideAssignment)
            for assignment in doctrine_policy
        ):
            raise TypeError(
                "doctrine_side_assignments must contain only "
                "DoctrineSideAssignment values",
            )
        doctrine_index = _doctrine_policy_index(doctrine_policy)
        known_sides = {side.side for side in config.sides}
        unknown_doctrine_sides = sorted(
            set(doctrine_index) - known_sides,
        )
        if unknown_doctrine_sides:
            raise ScenarioReferenceError(
                "Doctrine policy references unknown scenario sides: "
                f"{unknown_doctrine_sides!r}",
            )
        logger.info("Loaded campaign %r from %s", config.name, scenario_path)

        # 2. Core infrastructure
        rng_mgr = RNGManager(seed)
        bus = EventBus()
        start_dt = _parse_start_time(config.date)

        # When tick_duration_seconds is set (engagement-scale scenarios),
        # use it as the tactical tick resolution so the engine runs at
        # the scenario-appropriate cadence during combat.
        if config.tick_duration_seconds is not None:
            config.tick_resolution = TickResolutionConfig(
                strategic_s=config.tick_duration_seconds,
                operational_s=config.tick_duration_seconds,
                tactical_s=config.tick_duration_seconds,
            )

        # The engine detects initial force proximity and picks the right
        # starting resolution (strategic vs tactical), so we always
        # initialize the clock at strategic pace here.
        clock = SimulationClock(
            start=start_dt,
            tick_duration=timedelta(seconds=config.tick_resolution.strategic_s),
        )

        # 3. Terrain
        self._real_terrain_ctx = None
        heightmap = self._build_terrain(config.terrain, rng_mgr, config)

        # 4. Load YAML data (era-aware)
        from stochastic_warfare.core.era import get_era_config
        era_config = get_era_config(config.era)
        loaders = self._create_loaders(era=config.era)
        self._validate_reinforcement_unit_types(config, loaders["unit_loader"])
        self._validate_logistics_catalog(
            config,
            loaders["supply_item_loader"],
        )
        initial_force_plans = self._initial_force_plans(config)
        initial_unit_ids = set(
            RuntimeForceBuilder.initial_entity_ids(initial_force_plans),
        )
        planned_unit_sides = self._planned_unit_sides(
            config,
            initial_force_plans,
        )
        commander_engine, initial_commander_plan = (
            self._prepare_commander_engine(
                config,
                loaders["commander_profile_loader"],
                rng_mgr.get_stream(ModuleId.C2),
                initial_unit_ids=initial_unit_ids,
                planned_unit_sides=planned_unit_sides,
                schools_enabled=(
                    config.school_config is not None
                    or bool(doctrine_policy)
                ),
            )
        )
        self._validate_school_assignments(
            config,
            planned_unit_sides=planned_unit_sides,
            doctrine_side_assignments=doctrine_policy,
        )
        reachable_unit_types = tuple(
            entry.unit_type
            for side in config.sides
            for entry in side.units
        ) + tuple(
            unit.unit_type
            for wave in config.reinforcements
            for unit in wave.units
        )
        loadout_builder = RuntimeLoadoutBuilder(
            weapon_loader=loaders["weapon_loader"],
            ammo_loader=loaders["ammo_loader"],
            sensor_loader=loaders["sensor_loader"],
            unit_definitions=loaders["unit_loader"].definitions(),
            era_config=era_config,
            assignment_overrides=(
                config.calibration_overrides.weapon_assignments
            ),
            reachable_unit_types=reachable_unit_types,
            registry=EQUIPMENT_MAPPING_REGISTRY,
        )

        # 5. Build forces
        entities_rng = rng_mgr.get_stream(ModuleId.ENTITIES)
        force_builder = RuntimeForceBuilder(
            unit_loader=loaders["unit_loader"],
            rng=entities_rng,
        )
        entities_rng_before = copy.deepcopy(
            entities_rng.bit_generator.state,
        )
        try:
            units_by_side, runtime_loadouts = self._build_all_forces(
                config,
                initial_force_plans,
                force_builder,
                entities_rng,
                loadout_builder,
            )
        except Exception:
            entities_rng.bit_generator.state = entities_rng_before
            raise
        from stochastic_warfare.simulation.time_on_target import (
            TimeOnTargetMissionResolver,
        )

        time_on_target_missions = TimeOnTargetMissionResolver.resolve(
            config.indirect_fire,
            units_by_side=units_by_side,
            runtime_loadouts=runtime_loadouts,
            terrain=heightmap,
            duration_hours=config.duration_hours,
            tick_duration_seconds=config.tick_duration_seconds,
        )

        # 6. Morale state tracking
        all_units = [
            unit
            for side_units in units_by_side.values()
            for unit in side_units
        ]
        morale_states = _initial_morale_for_units(config, all_units)

        # 7. Create domain engines (era-gated)
        engines = self._create_engines(
            rng_mgr,
            bus,
            heightmap,
            loaders,
            config,
            clock,
            units_by_side,
            era_config,
            doctrine_side_assignments=doctrine_policy,
            time_on_target_missions=time_on_target_missions,
        )
        if commander_engine is not None:
            if initial_commander_plan is None:
                raise RuntimeError(
                    "Commander engine was created without an assignment plan",
                )
            engines["commander_engine"] = commander_engine
            commander_engine.commit_assignments(
                initial_commander_plan,
                replace=True,
            )
        initial_school_plan = _prepare_runtime_school_plan(
            config=config,
            commander_engine=commander_engine,
            commander_assignments=(
                initial_commander_plan.assignments
                if initial_commander_plan is not None
                else ()
            ),
            school_registry=engines.get("school_registry"),
            unit_sides={
                unit_id: planned_unit_sides[unit_id]
                for unit_id in initial_unit_ids
            },
            doctrine_side_assignments=doctrine_policy,
        )
        if initial_school_plan is not None:
            engines["school_registry"].commit_assignments(
                initial_school_plan,
            )
        if commander_engine is not None:
            ooda_engine = engines.get("ooda_engine")
            if ooda_engine is None:
                raise RuntimeError(
                    "Commander engine was created without an OODA engine",
                )
            _initialize_commander_ooda(
                commander_engine=commander_engine,
                ooda_engine=ooda_engine,
                school_registry=engines.get("school_registry"),
                assignments=initial_commander_plan.assignments,
                c2_rng=rng_mgr.get_stream(ModuleId.C2),
                timestamp=clock.current_time,
            )

        morale_runtime = engines.get("morale_runtime")
        if morale_runtime is None:
            raise RuntimeError(
                "Scenario loader did not create a morale runtime",
            )
        for unit in all_units:
            unit.status = _initial_status_for_morale(
                morale_states[unit.entity_id],
            )
        morale_runtime.register_units(
            tuple(
                MoraleRegistration(
                    unit_id=unit.entity_id,
                    initial_state=morale_states[unit.entity_id],
                )
                for unit in all_units
            ),
            {unit.entity_id: unit for unit in all_units},
        )

        # 8. Assemble context
        real_ctx = self._real_terrain_ctx
        movement_diagnostics = MovementDiagnostics({
            unit.entity_id: unit.side
            for unit in all_units
        })
        ctx = SimulationContext(
            config=config,
            clock=clock,
            rng_manager=rng_mgr,
            event_bus=bus,
            heightmap=heightmap,
            classification=real_ctx.classification if real_ctx else None,
            infrastructure_manager=real_ctx.infrastructure if real_ctx else None,
            bathymetry=real_ctx.bathymetry if real_ctx else None,
            units_by_side=units_by_side,
            unit_weapons=dict(runtime_loadouts.unit_weapons),
            unit_sensors=dict(runtime_loadouts.unit_sensors),
            equipment_resolutions=dict(
                runtime_loadouts.equipment_resolutions,
            ),
            force_builder=force_builder,
            loadout_builder=loadout_builder,
            movement_diagnostics=movement_diagnostics,
            doctrine_side_assignments=doctrine_policy,
            calibration=config.calibration_overrides,
            era_config=era_config,
            **engines,
            **loaders,
        )

        # 9. Flat calibration dict (Phase 86 — O(1) battle-loop access)
        if isinstance(ctx.calibration, CalibrationSchema):
            side_names = sorted(units_by_side.keys())
            ctx.cal_flat = ctx.calibration.to_flat_dict(side_names)

        # Phase 104: warn if deployment boxes are too close or overlap
        if config.deployment.mode.value != "legacy":
            check_side_separation(
                config.deployment.blue_box,
                config.deployment.red_box,
                config.deployment.min_side_separation_m,
            )

        # 10. Pre-emplaced IEDs / HBIEDs (Phase 101)
        self._emplace_initial_ieds(ctx, config)

        # 11. Scripted events — stash on context for campaign manager (Phase 101)
        ctx.scripted_events = list(config.scripted_events)

        return ctx

    # ── Private helpers ──────────────────────────────────────────────

    def _emplace_initial_ieds(
        self,
        ctx: SimulationContext,
        config: CampaignScenarioConfig,
    ) -> None:
        """Emplace pre-prepared IEDs / HBIEDs (Phase 101).

        Used for urban scenarios where insurgents have pre-wired the
        battlespace before coalition forces arrive (e.g. Fallujah 2004).
        Each entry calls ``unconventional_engine.emplace_ied`` and the
        returned obstacle IDs are registered on the context in order so
        scripted events can reference them by index.
        """
        if not config.initial_ieds:
            return
        uw_eng = getattr(ctx, "unconventional_engine", None)
        if uw_eng is None:
            logger.warning(
                "initial_ieds configured but unconventional_engine is None — skipping",
            )
            return
        from stochastic_warfare.core.types import Position
        obstacle_ids: list[str] = []
        for idx, ied in enumerate(config.initial_ieds):
            pos = Position(easting=ied.position[0], northing=ied.position[1], altitude=0.0)
            obs_id = uw_eng.emplace_ied(
                position=pos,
                subtype=ied.subtype,
                blast_radius_m=ied.blast_radius_m,
                concealment=ied.concealment,
                emplaced_by=ied.emplaced_by or f"pre_emplaced_{idx}",
                timestamp=ctx.clock.current_time,
            )
            obstacle_ids.append(obs_id)
        ctx.initial_ied_obstacle_ids = obstacle_ids
        logger.info("Emplaced %d pre-prepared IEDs/HBIEDs", len(obstacle_ids))

    @staticmethod
    def _initial_force_plans(
        config: CampaignScenarioConfig,
    ) -> tuple[InitialForcePlan, ...]:
        """Resolve typed initial placement inputs without consuming RNG."""
        plans: list[InitialForcePlan] = []
        calibration = config.calibration_overrides
        for side_index, side_config in enumerate(config.sides):
            prefix = side_config.side
            default_easting = (
                100.0
                if side_index == 0
                else config.terrain.width_m - 100.0
            )
            default_northing = config.terrain.height_m / 2
            start_easting = calibration.get(
                f"{prefix}_start_x",
                default_easting,
            )
            start_northing = calibration.get(
                f"{prefix}_start_y",
                default_northing,
            )
            spacing = calibration.get(
                f"{prefix}_formation_spacing_m",
                calibration.get("formation_spacing_m", 50.0),
            )
            plans.append(
                InitialForcePlan(
                    side=side_config.side,
                    units=tuple(side_config.units),
                    start_easting=float(start_easting),
                    start_northing=float(start_northing),
                    spacing_m=float(spacing),
                ),
            )
        return tuple(plans)

    @staticmethod
    def _planned_unit_sides(
        config: CampaignScenarioConfig,
        initial_plans: tuple[InitialForcePlan, ...],
    ) -> dict[str, str]:
        """Return exact initial and future reinforcement identity topology."""
        planned = {
            spec.entity_id: spec.side
            for spec in RuntimeForceBuilder.initial_specs(initial_plans)
        }
        for wave_ordinal, reinforcement in enumerate(
            config.reinforcements,
        ):
            unit_index = 0
            for unit_config in reinforcement.units:
                for _ in range(unit_config.count):
                    entity_id = (
                        f"reinforce_{reinforcement.side}_"
                        f"{wave_ordinal:04d}_"
                        f"{unit_config.unit_type}_{unit_index:04d}"
                    )
                    if entity_id in planned:
                        raise ValueError(
                            f"Duplicate planned unit ID {entity_id!r}",
                        )
                    planned[entity_id] = reinforcement.side
                    unit_index += 1
        return planned

    def _validate_school_assignments(
        self,
        config: CampaignScenarioConfig,
        *,
        planned_unit_sides: Mapping[str, str],
        doctrine_side_assignments: tuple[
            DoctrineSideAssignment,
            ...,
        ],
    ) -> None:
        """Validate exact-unit and analysis school references pre-runtime."""
        raw_exact = (
            config.school_config.get("unit_assignments", {})
            if config.school_config is not None
            else {}
        )
        if not isinstance(raw_exact, Mapping):
            raise ScenarioReferenceError(
                "school_config.unit_assignments must be a mapping",
            )
        exact_assignments: dict[str, str] = {}
        for unit_id, school_id in raw_exact.items():
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or unit_id != unit_id.strip()
            ):
                raise ScenarioReferenceError(
                    "School assignment unit IDs must be non-empty "
                    "trimmed strings",
                )
            if (
                not isinstance(school_id, str)
                or not school_id
                or school_id != school_id.strip()
            ):
                raise ScenarioReferenceError(
                    "School assignment school IDs must be non-empty "
                    "trimmed strings",
                )
            exact_assignments[unit_id] = school_id
        unknown_units = sorted(
            set(exact_assignments) - set(planned_unit_sides),
        )
        if unknown_units:
            raise ScenarioReferenceError(
                "School assignments reference unknown initial or future "
                f"unit IDs: {unknown_units!r}",
            )

        referenced_schools = set(exact_assignments.values()) | {
            assignment.school_id
            for assignment in doctrine_side_assignments
        }
        if not referenced_schools:
            return
        from stochastic_warfare.c2.ai.schools import SchoolLoader

        school_loader = SchoolLoader(self._data_dir / "schools")
        school_loader.load_all()
        missing_schools = sorted(
            referenced_schools - set(school_loader.available_schools()),
        )
        if missing_schools:
            raise ScenarioReferenceError(
                "Runtime assignments reference unknown doctrinal schools: "
                f"{missing_schools!r}",
            )

    def _prepare_commander_engine(
        self,
        config: CampaignScenarioConfig,
        profile_loader: CommanderProfileLoader,
        c2_rng: np.random.Generator,
        *,
        initial_unit_ids: set[str],
        planned_unit_sides: Mapping[str, str],
        schools_enabled: bool,
    ) -> tuple[
        CommanderEngine | None,
        CommanderAssignmentPlan | None,
    ]:
        """Validate commander authority before any unit construction."""
        side_profiles = {
            side.side: side.commander_profile
            for side in config.sides
            if side.commander_profile
        }
        if not side_profiles:
            return None, None

        for side, profile_id in sorted(side_profiles.items()):
            try:
                profile_loader.get_definition(profile_id)
            except KeyError as exc:
                raise ScenarioReferenceError(
                    f"Side {side!r} references unknown commander_profile "
                    f"{profile_id!r}",
                ) from exc

        commander_config = (
            config.commander_config
            if config.commander_config is not None
            else CommanderScenarioConfig()
        )
        planned_ids = set(planned_unit_sides)
        unknown_assignment_ids = sorted(
            set(commander_config.assignments) - planned_ids,
        )
        if unknown_assignment_ids:
            raise ScenarioReferenceError(
                "Commander assignments reference unknown initial or future "
                f"unit IDs: {unknown_assignment_ids!r}",
            )
        for unit_id, profile_id in sorted(
            commander_config.assignments.items(),
        ):
            try:
                profile_loader.get_definition(profile_id)
            except KeyError as exc:
                raise ScenarioReferenceError(
                    f"Commander assignment for {unit_id!r} references "
                    f"unknown profile {profile_id!r}",
                ) from exc

        referenced_profile_ids = set(side_profiles.values()) | set(
            commander_config.assignments.values(),
        )
        referenced_school_ids = {
            definition.school_id
            for profile_id in referenced_profile_ids
            if (
                definition := profile_loader.get_definition(profile_id)
            ).school_id is not None
        }
        if referenced_school_ids:
            if not schools_enabled:
                raise ScenarioReferenceError(
                    "Commander profiles reference doctrinal schools but "
                    "no runtime school registry is enabled",
                )
            from stochastic_warfare.c2.ai.schools import SchoolLoader

            school_loader = SchoolLoader(self._data_dir / "schools")
            school_loader.load_all()
            missing_schools = sorted(
                referenced_school_ids
                - set(school_loader.available_schools()),
            )
            if missing_schools:
                raise ScenarioReferenceError(
                    "Commander profiles reference unknown doctrinal schools: "
                    f"{missing_schools!r}",
                )

        initial_assignments = {
            unit_id: side_profiles[planned_unit_sides[unit_id]]
            for unit_id in sorted(initial_unit_ids)
        }
        initial_assignments.update({
            unit_id: profile_id
            for unit_id, profile_id
            in commander_config.assignments.items()
            if unit_id in initial_unit_ids
        })
        engine = CommanderEngine(
            profile_loader,
            c2_rng,
            commander_config.engine_config(),
        )
        plan = engine.prepare_assignments(
            initial_assignments,
            expected_unit_ids=initial_unit_ids,
            require_complete=True,
        )
        return engine, plan

    def _build_terrain(
        self,
        spec: TerrainConfig,
        rng_mgr: RNGManager,
        config: CampaignScenarioConfig | None = None,
    ) -> Heightmap:
        """Build heightmap from terrain specification."""
        if spec.terrain_source == "real":
            return self._build_real_terrain(spec, config)

        from stochastic_warfare.terrain.procedural import build_terrain

        terrain_rng = rng_mgr.get_stream(ModuleId.TERRAIN)
        return build_terrain(spec, terrain_rng)

    def _build_real_terrain(
        self,
        spec: TerrainConfig,
        config: CampaignScenarioConfig | None = None,
    ) -> Heightmap:
        """Build terrain from real-world geospatial data."""
        from stochastic_warfare.terrain.data_pipeline import (
            BoundingBox,
            TerrainDataConfig,
            load_real_terrain,
        )
        from stochastic_warfare.coordinates.transforms import ScenarioProjection

        lat = config.latitude if config else 0.0
        lon = config.longitude if config else 0.0
        projection = ScenarioProjection(lat, lon)

        # Compute bbox from lat/lon + width/height
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
        half_h = (spec.height_m / 2) / meters_per_deg_lat
        half_w = (spec.width_m / 2) / meters_per_deg_lon

        bbox = BoundingBox(
            south=lat - half_h,
            west=lon - half_w,
            north=lat + half_h,
            east=lon + half_w,
        )
        tdc = TerrainDataConfig(
            bbox=bbox,
            cell_size_m=spec.cell_size_m,
            data_dir=spec.data_dir,
            cache_dir=spec.cache_dir,
        )

        ctx = load_real_terrain(tdc, projection)

        # Stash extra layers for the SimulationContext to pick up
        self._real_terrain_ctx = ctx
        return ctx.heightmap

    def _create_loaders(self, era: str = "modern") -> dict[str, Any]:
        """Create and initialize all YAML data loaders.

        When *era* is not ``"modern"``, also loads YAML definitions from
        ``data/eras/{era}/`` — era-specific files add to (not replace)
        the base data set.
        """
        from stochastic_warfare.entities.loader import UnitLoader
        from stochastic_warfare.combat.ammunition import AmmoLoader, WeaponLoader
        from stochastic_warfare.detection.signatures import SignatureLoader
        from stochastic_warfare.detection.sensors import SensorLoader
        from stochastic_warfare.logistics.supply_classes import SupplyItemLoader

        unit_loader = UnitLoader(self._data_dir / "units")
        unit_loader.load_all()

        weapon_loader = WeaponLoader(self._data_dir / "weapons")
        weapon_loader.load_all()

        ammo_loader = AmmoLoader(self._data_dir / "ammunition")
        ammo_loader.load_all()

        sig_loader = SignatureLoader(self._data_dir / "signatures")
        sig_loader.load_all()

        sensor_loader = SensorLoader(self._data_dir / "sensors")
        sensor_loader.load_all()

        supply_item_loader = SupplyItemLoader(
            self._data_dir / "logistics" / "supply_items",
        )
        supply_item_loader.load_all()

        commander_profile_loader = CommanderProfileLoader(
            self._data_dir / "commander_profiles",
        )
        commander_catalogs = [self._data_dir / "commander_profiles"]
        if era != "modern":
            commander_catalogs.append(
                self._data_dir / "eras" / era / "commanders",
            )
        commander_profile_loader.load_directories(commander_catalogs)

        # Load era-specific data on top of base data
        if era != "modern":
            era_dir = self._data_dir / "eras" / era
            if era_dir.is_dir():
                era_units = era_dir / "units"
                if era_units.is_dir():
                    era_unit_loader = UnitLoader(era_units)
                    era_unit_loader.load_all()
                    unit_loader._definitions.update(era_unit_loader._definitions)

                era_weapons = era_dir / "weapons"
                if era_weapons.is_dir():
                    era_weapon_loader = WeaponLoader(era_weapons)
                    era_weapon_loader.load_all()
                    weapon_loader._definitions.update(era_weapon_loader._definitions)

                era_ammo = era_dir / "ammunition"
                if era_ammo.is_dir():
                    era_ammo_loader = AmmoLoader(era_ammo)
                    era_ammo_loader.load_all()
                    ammo_loader._definitions.update(era_ammo_loader._definitions)

                era_sigs = era_dir / "signatures"
                if era_sigs.is_dir():
                    era_sig_loader = SignatureLoader(era_sigs)
                    era_sig_loader.load_all()
                    sig_loader._profiles.update(era_sig_loader._profiles)

                era_sensors = era_dir / "sensors"
                if era_sensors.is_dir():
                    era_sensor_loader = SensorLoader(era_sensors)
                    era_sensor_loader.load_all()
                    sensor_loader._definitions.update(era_sensor_loader._definitions)

                logger.info("Loaded era-specific data from %s", era_dir)

        return {
            "unit_loader": unit_loader,
            "weapon_loader": weapon_loader,
            "ammo_loader": ammo_loader,
            "sig_loader": sig_loader,
            "sensor_loader": sensor_loader,
            "supply_item_loader": supply_item_loader,
            "commander_profile_loader": commander_profile_loader,
        }

    @staticmethod
    def _validate_reinforcement_unit_types(
        config: CampaignScenarioConfig,
        unit_loader: Any,
    ) -> None:
        """Reject unresolved reinforcement definitions during scenario load."""
        available = set(unit_loader.available_types())
        unknown = [
            (wave_index, unit_config.unit_type)
            for wave_index, wave in enumerate(config.reinforcements)
            for unit_config in wave.units
            if unit_config.unit_type not in available
        ]
        if unknown:
            details = ", ".join(
                f"wave {wave_index}: {unit_type!r}"
                for wave_index, unit_type in unknown
            )
            raise ScenarioReferenceError(
                "Reinforcement schedule references unknown unit types "
                f"({details})",
            )

    @staticmethod
    def _validate_logistics_catalog(
        config: CampaignScenarioConfig,
        supply_item_loader: Any,
    ) -> None:
        """Validate configured logistics items and depot mass before RNG use."""

        def definition_for(
            entry: SupplyQuantityConfig,
            location: str,
        ) -> Any:
            try:
                definition = supply_item_loader.get_definition(entry.item_id)
            except KeyError as exc:
                raise ScenarioReferenceError(
                    f"{location} references unknown supply item "
                    f"{entry.item_id!r}",
                ) from exc
            if definition.supply_class != entry.supply_class:
                raise ScenarioReferenceError(
                    f"{location} declares {entry.supply_class} for "
                    f"{entry.item_id!r}, but the catalog declares "
                    f"{definition.supply_class}",
                )
            if (
                isinstance(definition.weight_per_unit_kg, bool)
                or not math.isfinite(definition.weight_per_unit_kg)
                or definition.weight_per_unit_kg <= 0.0
            ):
                raise RuntimeError(
                    f"Catalog item {entry.item_id!r} has invalid "
                    "weight_per_unit_kg",
                )
            return definition

        for profile in config.logistics.unit_profiles:
            for field_name in (
                "initial_inventory",
                "maximum_inventory",
                "idle_consumption_per_hour",
            ):
                entries = getattr(profile, field_name)
                for entry in entries:
                    definition_for(
                        entry,
                        f"profile {profile.side}/{profile.unit_type} "
                        f"{field_name}",
                    )

        for side in config.sides:
            for depot in side.depots:
                total_kg = 0.0
                for entry in depot.initial_inventory or []:
                    definition = definition_for(
                        entry,
                        f"depot {depot.depot_id} initial_inventory",
                    )
                    total_kg += (
                        entry.quantity * definition.weight_per_unit_kg
                    )
                if total_kg > depot.capacity_tons * 1000.0 + 1e-9:
                    raise ScenarioReferenceError(
                        f"depot {depot.depot_id!r} initial inventory weighs "
                        f"{total_kg / 1000.0:.6g} tons and exceeds "
                        f"capacity_tons={depot.capacity_tons:.6g}",
                    )

    def _build_all_forces(
        self,
        config: CampaignScenarioConfig,
        plans: tuple[InitialForcePlan, ...],
        force_builder: RuntimeForceBuilder,
        entities_rng: np.random.Generator,
        loadout_builder: RuntimeLoadoutBuilder,
    ) -> tuple[dict[str, list[Unit]], RuntimeLoadouts]:
        """Build the exact typed roster, then attach runtime loadouts."""
        units_by_side = force_builder.build_initial(plans)
        for plan in plans:
            units = units_by_side[plan.side]
            # Phase 104: apply configured deployment mode (legacy preserves
            # the line-abreast positions assigned by RuntimeForceBuilder).
            # Per-unit `_manually_positioned` flag skips auto-deployment.
            if config.deployment.mode.value != "legacy":
                template = None
                if config.deployment.mode == DeploymentMode.DOCTRINAL:
                    template_id = (
                        config.deployment.blue_template
                        if plan.side == "blue"
                        else config.deployment.red_template
                    )
                    if template_id is not None:
                        template_loader = FormationTemplateLoader(
                            self._data_dir / "formations",
                        )
                        template_loader.load_all()
                        template = template_loader.get(template_id)
                        if template is None:
                            raise ScenarioReferenceError(
                                f"Formation template {template_id!r} "
                                f"referenced by side {plan.side!r} is unknown; "
                                f"available={template_loader.available()!r}",
                            )
                deploy_units(
                    units=units,
                    side=plan.side,
                    config=config.deployment,
                    legacy_start_x=plan.start_easting,
                    legacy_start_y=plan.start_northing,
                    legacy_spacing_m=plan.spacing_m,
                    template=template,
                    rng=entities_rng,
                )

        # Assign weapons and sensors
        all_units = [u for us in units_by_side.values() for u in us]
        runtime_loadouts = loadout_builder.build(all_units)

        return units_by_side, runtime_loadouts

    def _create_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        heightmap: Heightmap,
        loaders: dict[str, Any],
        config: CampaignScenarioConfig,
        clock: SimulationClock | None = None,
        units_by_side: dict[str, list] | None = None,
        era_config: Any = None,
        *,
        doctrine_side_assignments: tuple[
            DoctrineSideAssignment,
            ...,
        ] = (),
        time_on_target_missions: tuple[ResolvedTimeOnTargetMission, ...] = (),
    ) -> dict[str, Any]:
        """Create all domain engine instances."""
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)
        detection_rng = rng_mgr.get_stream(ModuleId.DETECTION)
        morale_rng = rng_mgr.get_stream(ModuleId.MORALE)
        movement_rng = rng_mgr.get_stream(ModuleId.MOVEMENT)
        c2_rng = rng_mgr.get_stream(ModuleId.C2)
        logistics_rng = rng_mgr.get_stream(ModuleId.LOGISTICS)

        # Combat stack
        from stochastic_warfare.combat.ballistics import BallisticsEngine
        from stochastic_warfare.combat.hit_probability import HitProbabilityEngine
        from stochastic_warfare.combat.damage import DamageEngine
        from stochastic_warfare.combat.suppression import SuppressionEngine
        from stochastic_warfare.combat.fratricide import FratricideEngine
        from stochastic_warfare.combat.engagement import EngagementEngine

        bal = BallisticsEngine(combat_rng)
        hit_engine = HitProbabilityEngine(bal, combat_rng)
        cal = config.calibration_overrides
        dmg_engine = DamageEngine(
            bus, combat_rng,
            posture_blast_overrides=cal.get("posture_blast_protection") if cal else None,
            posture_frag_overrides=cal.get("posture_frag_protection") if cal else None,
        )
        sup_engine = SuppressionEngine(bus, combat_rng)
        frat_engine = FratricideEngine(bus, combat_rng)
        engagement_engine = EngagementEngine(
            hit_engine, dmg_engine, sup_engine, frat_engine, bus, combat_rng,
        )

        # Missile engine (Phase 63d)
        from stochastic_warfare.combat.missiles import MissileEngine

        missile_engine = MissileEngine(dmg_engine, bus, combat_rng)

        # Missile defense engine (Phase 71c)
        from stochastic_warfare.combat.missile_defense import MissileDefenseEngine

        missile_defense_engine = MissileDefenseEngine(
            event_bus=bus,
            rng=combat_rng,
        )

        # Indirect fire (Phase 43b)
        from stochastic_warfare.combat.indirect_fire import IndirectFireEngine

        indirect_fire_engine = IndirectFireEngine(
            bal,
            dmg_engine,
            bus,
            combat_rng,
            time_on_target_enabled=(
                config.indirect_fire.enable_time_on_target
            ),
            time_on_target_missions=time_on_target_missions,
            destruction_threshold=cal.get(
                "destruction_threshold",
                0.5,
            ),
            disable_threshold=cal.get(
                "disable_threshold",
                0.3,
            ),
        )

        # Naval engines (Phase 43c)
        from stochastic_warfare.combat.naval_surface import NavalSurfaceEngine
        from stochastic_warfare.combat.naval_subsurface import NavalSubsurfaceEngine
        from stochastic_warfare.combat.naval_gunfire_support import NavalGunfireSupportEngine
        from stochastic_warfare.combat.naval_mine import MineWarfareEngine

        naval_surface_engine = NavalSurfaceEngine(dmg_engine, bus, combat_rng)
        naval_subsurface_engine = NavalSubsurfaceEngine(dmg_engine, bus, combat_rng)
        naval_gunfire_support_engine = NavalGunfireSupportEngine(
            indirect_fire_engine, bus, combat_rng,
        )
        mine_warfare_engine = MineWarfareEngine(dmg_engine, bus, combat_rng)

        # Air combat engines (Phase 58b) — only when enable_air_routing is set
        air_combat_engine = None
        air_ground_engine = None
        air_defense_engine = None
        if cal and cal.get("enable_air_routing", False):
            from stochastic_warfare.combat.air_combat import AirCombatEngine
            from stochastic_warfare.combat.air_ground import AirGroundEngine
            from stochastic_warfare.combat.air_defense import AirDefenseEngine

            air_combat_engine = AirCombatEngine(bus, combat_rng)
            air_ground_engine = AirGroundEngine(bus, combat_rng)
            air_defense_engine = AirDefenseEngine(bus, combat_rng)

        # Disruption engine (Phase 51d — blockade / interdiction)
        from stochastic_warfare.logistics.disruption import DisruptionEngine

        disruption_engine = DisruptionEngine(bus, logistics_rng)

        # LOS engine (built from heightmap, cached per tick)
        from stochastic_warfare.terrain.los import LOSEngine

        los_engine = LOSEngine(heightmap)

        # Detection
        from stochastic_warfare.detection.detection import DetectionEngine
        from stochastic_warfare.detection.fog_of_war import FogOfWarManager

        det_engine = DetectionEngine(
            los_checker=los_engine.check_los,
            rng=detection_rng,
            signature_loader=loaders["sig_loader"],
            sensor_loader=loaders["sensor_loader"],
        )
        fog_of_war = FogOfWarManager(
            detection_engine=det_engine,
            rng=detection_rng,
        )

        # Morale
        from stochastic_warfare.morale.config import build_morale_config

        cal = config.calibration_overrides
        morale_config = build_morale_config(cal.morale)

        # ROE (Phase 42a)
        from stochastic_warfare.c2.roe import RoeEngine, RoeLevel
        roe_engine = RoeEngine(bus, default_level=RoeLevel.WEAPONS_FREE)

        # Rout (Phase 42c / Phase 55 per-scenario config)
        _rout_cfg_kwargs: dict[str, float] = {}
        for _rout_field in ("cascade_radius_m", "cascade_base_chance", "cascade_shaken_susceptibility"):
            _rout_val = cal.get(f"rout_{_rout_field}")
            if _rout_val is not None:
                _rout_cfg_kwargs[_rout_field] = _rout_val
        rout_engine = RoutEngine(
            bus, morale_rng,
            config=RoutConfig(**_rout_cfg_kwargs) if _rout_cfg_kwargs else None,
        )
        morale_runtime = MoraleRuntime(
            bus,
            morale_rng,
            morale_config,
            rout_engine=rout_engine,
        )

        # Movement
        from stochastic_warfare.movement.engine import MovementEngine

        movement_engine = MovementEngine(
            heightmap=heightmap,
            rng=movement_rng,
        )

        # C2
        from stochastic_warfare.c2.communications import CommunicationsEngine
        from stochastic_warfare.c2.orders.propagation import OrderPropagationEngine
        from stochastic_warfare.c2.orders.execution import OrderExecutionEngine

        comms_engine = CommunicationsEngine(bus, c2_rng)

        # Phase 69d: Command hierarchy enforcement
        _command_engine_69d = None
        if cal.get("enable_command_hierarchy", False) and units_by_side:
            from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
            from stochastic_warfare.entities.organization.task_org import TaskOrgManager
            from stochastic_warfare.entities.organization.echelons import EchelonLevel
            from stochastic_warfare.c2.command import CommandEngine, CommandConfig

            _hierarchy = HierarchyTree()
            # Build virtual HQ per side + add each unit as child
            for _side_key, _side_units in units_by_side.items():
                _hq_id = f"{_side_key}_hq"
                _hierarchy.add_unit(_hq_id, EchelonLevel.DIVISION, side=_side_key)
                for _u in _side_units:
                    try:
                        _hierarchy.add_unit(
                            _u.entity_id, EchelonLevel.COMPANY,
                            parent_id=_hq_id, side=_side_key,
                        )
                    except (ValueError, KeyError):
                        pass  # duplicate or missing parent — skip
            _task_org = TaskOrgManager(_hierarchy)
            _command_engine_69d = CommandEngine(
                _hierarchy, _task_org, {},
                bus, c2_rng, CommandConfig(),
            )
            logger.info("Command hierarchy built with %d units",
                         sum(len(u) for u in units_by_side.values()))

        order_propagation = OrderPropagationEngine(
            comms_engine=comms_engine,
            command_engine=_command_engine_69d,
            event_bus=bus,
            rng=c2_rng,
        )
        order_execution = OrderExecutionEngine(
            propagation_engine=order_propagation,
            event_bus=bus,
            rng=c2_rng,
        )

        # AI
        from stochastic_warfare.c2.ai.ooda import OODALoopEngine
        from stochastic_warfare.c2.planning.process import PlanningProcessEngine
        from stochastic_warfare.c2.ai.assessment import SituationAssessor
        from stochastic_warfare.c2.ai.decisions import DecisionEngine
        from stochastic_warfare.c2.ai.adaptation import AdaptationEngine

        ooda_engine = OODALoopEngine(bus, c2_rng)
        planning_engine = PlanningProcessEngine(bus, c2_rng)
        assessor = SituationAssessor(bus, c2_rng)
        decision_engine = DecisionEngine(bus, c2_rng)
        adaptation_engine = AdaptationEngine(bus, c2_rng)

        # Phase 53c: Stratagem engine
        from stochastic_warfare.c2.ai.stratagems import StratagemEngine
        stratagem_engine = StratagemEngine(bus, c2_rng)

        # Phase 53d: ATO planning engine
        from stochastic_warfare.c2.orders.air_orders import ATOPlanningEngine
        ato_engine = ATOPlanningEngine(bus)

        # Phase 53e: IADS engine
        from stochastic_warfare.combat.iads import IadsEngine, IadsConfig
        iads_cfg = IadsConfig()
        _cal = config.calibration_overrides
        if _cal is not None:
            _iads_rate = _cal.get("iads_degradation_rate", None) if hasattr(_cal, "get") else None
            if _iads_rate is not None:
                iads_cfg = IadsConfig(sead_degradation_rate=_iads_rate)
            _sead_eff = _cal.get("sead_effectiveness", None) if hasattr(_cal, "get") else None
            if _sead_eff is not None:
                iads_cfg.sead_effectiveness = _sead_eff
            _sead_arm = _cal.get("sead_arm_effectiveness", None) if hasattr(_cal, "get") else None
            if _sead_arm is not None:
                iads_cfg.sead_arm_effectiveness = _sead_arm
        iads_engine = IadsEngine(bus, combat_rng, iads_cfg)

        # Logistics
        from stochastic_warfare.logistics.consumption import ConsumptionEngine
        from stochastic_warfare.logistics.stockpile import StockpileManager
        from stochastic_warfare.logistics.supply_network import SupplyNetworkEngine
        from stochastic_warfare.logistics.maintenance import MaintenanceEngine

        consumption_engine = ConsumptionEngine(bus, logistics_rng)
        stockpile_manager = StockpileManager(
            bus,
            logistics_rng,
            loader=loaders["supply_item_loader"],
        )
        supply_network_engine = SupplyNetworkEngine(bus, logistics_rng)
        from stochastic_warfare.logistics.runtime import LogisticsRuntime

        logistics_runtime = LogisticsRuntime(
            config=config.logistics,
            stockpile_manager=stockpile_manager,
            supply_network_engine=supply_network_engine,
            supply_item_loader=loaders["supply_item_loader"],
            disruption_engine=disruption_engine,
        )
        logistics_runtime.initialize(
            {
                side.side: side.depots
                for side in config.sides
            },
            [
                unit
                for side in sorted(units_by_side or {})
                for unit in (units_by_side or {})[side]
            ],
        )
        maintenance_engine = MaintenanceEngine(bus, logistics_rng)

        # Phase 56c: per-subsystem Weibull shapes from calibration
        _cal = config.calibration_overrides
        _weibull = (
            _cal.get("subsystem_weibull_shapes", {})
            if hasattr(_cal, "get") else {}
        )
        if _weibull:
            maintenance_engine._config.use_weibull = True
            maintenance_engine.set_subsystem_shapes(_weibull)

        # Aggregation (Phase 13a-7)
        from stochastic_warfare.simulation.aggregation import (
            AggregationConfig,
            AggregationEngine,
        )

        agg_config = AggregationConfig()
        aggregation_engine = AggregationEngine(
            config=agg_config,
            rng=rng_mgr.get_stream(ModuleId.CORE),
            event_bus=bus,
        )

        # Terrain managers (Phase 40g)
        from stochastic_warfare.terrain.obstacles import ObstacleManager
        from stochastic_warfare.terrain.hydrography import HydrographyManager

        obstacle_mgr = ObstacleManager()
        hydro_mgr = HydrographyManager()

        # Phase 44a: Environment engines
        weather_engine = None
        time_of_day_engine = None
        sea_state_engine = None
        seasons_engine = None
        underwater_acoustics_engine = None
        conditions_engine = None

        if clock is not None:
            from stochastic_warfare.environment.weather import (
                WeatherConfig,
                WeatherEngine,
            )
            from stochastic_warfare.environment.astronomy import AstronomyEngine
            from stochastic_warfare.environment.time_of_day import TimeOfDayEngine
            from stochastic_warfare.environment.sea_state import (
                SeaStateConfig,
                SeaStateEngine,
            )

            env_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
            wc = config.weather_conditions
            weather_cfg = WeatherConfig(
                latitude=config.latitude,
                initial_state=_parse_weather_state(
                    wc.get("precipitation", "clear"),
                ),
                initial_temperature=wc.get("temperature_c", 20.0),
            )
            weather_engine = WeatherEngine(weather_cfg, clock, env_rng)
            astronomy_engine = AstronomyEngine(clock)
            time_of_day_engine = TimeOfDayEngine(
                astronomy_engine, weather_engine, clock,
            )
            sea_state_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
            sea_state_engine = SeaStateEngine(
                SeaStateConfig(), clock, astronomy_engine, weather_engine,
                sea_state_rng,
            )

            # Phase 59: SeasonsEngine instantiation
            from stochastic_warfare.environment.seasons import SeasonsConfig, SeasonsEngine
            seasons_engine = SeasonsEngine(
                SeasonsConfig(latitude=config.latitude),
                clock, weather_engine, astronomy_engine,
            )

            # Phase 60: ObscurantsEngine instantiation
            from stochastic_warfare.environment.obscurants import ObscurantsEngine
            obs_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
            obscurants_engine = ObscurantsEngine(
                weather_engine, time_of_day_engine, clock, obs_rng,
            )

            # Phase 61: UnderwaterAcousticsEngine instantiation
            from stochastic_warfare.environment.underwater_acoustics import UnderwaterAcousticsEngine
            ua_rng = rng_mgr.get_stream(ModuleId.ENVIRONMENT)
            underwater_acoustics_engine = UnderwaterAcousticsEngine(
                sea_state_engine, clock, ua_rng,
            )

            # Phase 61: EMEnvironment instantiation (conditions_engine)
            from stochastic_warfare.environment.electromagnetic import EMEnvironment
            conditions_engine = EMEnvironment(
                weather_engine, sea_state_engine, clock,
            )

            # Phase 66b: ConditionsEngine facade — composites all env sub-engines
            from stochastic_warfare.environment.conditions import ConditionsEngine as _CondFacade
            try:
                conditions_facade = _CondFacade(
                    weather=weather_engine,
                    time_of_day=time_of_day_engine,
                    seasons=seasons_engine,
                    obscurants=obscurants_engine,
                    sea_state=sea_state_engine,
                    acoustics=underwater_acoustics_engine,
                    em=conditions_engine,
                )
            except Exception:
                conditions_facade = None

            # Merge weather visibility into calibration if not already set
            cal = config.calibration_overrides
            if "visibility_m" in wc:
                from stochastic_warfare.simulation.calibration import CalibrationSchema
                if isinstance(cal, CalibrationSchema):
                    if cal.visibility_m is None:
                        cal.visibility_m = wc["visibility_m"]
                elif "visibility_m" not in cal:
                    cal["visibility_m"] = wc["visibility_m"]

        # Phase 44c / 56c: Medical & engineering engines (era-aware)
        from stochastic_warfare.logistics.medical import MedicalConfig, MedicalEngine
        from stochastic_warfare.logistics.engineering import (
            EngineeringConfig,
            EngineeringEngine,
        )

        _era_cfg = getattr(config, "era_config", None)
        if _era_cfg is None:
            _era_cfg = getattr(config, "era", None)
            if _era_cfg is not None and not hasattr(_era_cfg, "physics_overrides"):
                _era_cfg = None
        _med_kw: dict[str, Any] = {}
        _eng_kw: dict[str, Any] = {}
        if _era_cfg is not None:
            _po = getattr(_era_cfg, "physics_overrides", {})
            for _mk in (
                "treatment_hours_minor",
                "treatment_hours_serious",
                "treatment_hours_critical",
            ):
                if _mk in _po:
                    _med_kw[_mk] = _po[_mk]
            if "repair_time_hours" in _po:
                _eng_kw["repair_time_hours"] = _po["repair_time_hours"]

        medical_config = MedicalConfig(**_med_kw) if _med_kw else None
        engineering_config = EngineeringConfig(**_eng_kw) if _eng_kw else None
        medical_engine = MedicalEngine(bus, logistics_rng, config=medical_config)
        engineering_engine = EngineeringEngine(
            bus, logistics_rng, config=engineering_config,
        )

        # Phase 61: CarrierOpsEngine instantiation
        from stochastic_warfare.combat.carrier_ops import CarrierOpsEngine
        carrier_ops_rng = rng_mgr.get_stream(ModuleId.COMBAT)
        carrier_ops_engine = CarrierOpsEngine(
            event_bus=bus,
            rng=carrier_ops_rng,
        )

        # Phase 61c: wire EM environment to comms engine
        if conditions_engine is not None:
            comms_engine.set_em_environment(conditions_engine)

        result = {
            "los_engine": los_engine,
            "engagement_engine": engagement_engine,
            "missile_engine": missile_engine,
            "missile_defense_engine": missile_defense_engine,
            "detection_engine": det_engine,
            "fog_of_war": fog_of_war,
            "morale_runtime": morale_runtime,
            "roe_engine": roe_engine,
            "rout_engine": rout_engine,
            "movement_engine": movement_engine,
            "comms_engine": comms_engine,
            "order_propagation": order_propagation,
            "order_execution": order_execution,
            "ooda_engine": ooda_engine,
            "planning_engine": planning_engine,
            "assessor": assessor,
            "decision_engine": decision_engine,
            "adaptation_engine": adaptation_engine,
            "consumption_engine": consumption_engine,
            "stockpile_manager": stockpile_manager,
            "supply_network_engine": supply_network_engine,
            "logistics_runtime": logistics_runtime,
            "maintenance_engine": maintenance_engine,
            "aggregation_engine": aggregation_engine,
            "suppression_engine": sup_engine,
            "indirect_fire_engine": indirect_fire_engine,
            "naval_surface_engine": naval_surface_engine,
            "naval_subsurface_engine": naval_subsurface_engine,
            "naval_gunfire_support_engine": naval_gunfire_support_engine,
            "mine_warfare_engine": mine_warfare_engine,
            "air_combat_engine": air_combat_engine,
            "air_ground_engine": air_ground_engine,
            "air_defense_engine": air_defense_engine,
            "disruption_engine": disruption_engine,
            "obstacle_manager": obstacle_mgr,
            "hydrography_manager": hydro_mgr,
            "weather_engine": weather_engine,
            "time_of_day_engine": time_of_day_engine,
            "sea_state_engine": sea_state_engine,
            "seasons_engine": seasons_engine,
            "obscurants_engine": obscurants_engine,
            "underwater_acoustics_engine": underwater_acoustics_engine,
            "conditions_engine": conditions_engine,
            "conditions_facade": locals().get("conditions_facade"),
            "carrier_ops_engine": carrier_ops_engine,
            "medical_engine": medical_engine,
            "engineering_engine": engineering_engine,
            "stratagem_engine": stratagem_engine,
            "ato_engine": ato_engine,
            "iads_engine": iads_engine,
            "command_engine": _command_engine_69d,
        }

        # ── Optional engine wiring (Phase 25) ────────────────────────
        result.update(
            self._create_optional_engines(
                rng_mgr,
                bus,
                config,
                c2_rng,
                era_config,
                clock,
                doctrine_side_assignments=doctrine_side_assignments,
            ),
        )
        return result

    def _create_optional_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        config: CampaignScenarioConfig,
        c2_rng: np.random.Generator,
        era_config: Any = None,
        clock: SimulationClock | None = None,
        *,
        doctrine_side_assignments: tuple[
            DoctrineSideAssignment,
            ...,
        ] = (),
    ) -> dict[str, Any]:
        """Create optional domain engines from explicit flags and era gates."""
        if era_config is None:
            from stochastic_warfare.core.era import get_era_config

            era_config = get_era_config(config.era)
        disabled = set(era_config.disabled_modules)
        result: dict[str, Any] = {}

        # 1. EW engines
        ew_enabled = self._optional_suite_enabled(
            config.ew_config,
            enable_field="enable_ew",
            config_field="ew_config",
        )
        if ew_enabled and "ew" in disabled:
            raise ScenarioReferenceError(
                "Era feature 'ew' is disabled but ew_config.enable_ew is true",
            )
        if ew_enabled:
            result.update(self._create_ew_engines(rng_mgr, bus, config.ew_config))

        # 2. Space engines
        space_enabled = (
            config.space_config is not None
            and config.space_config.enable_space
        )
        if space_enabled and "space" in disabled:
            raise ScenarioReferenceError(
                "Era feature 'space' is disabled but "
                "space_config.enable_space is true",
            )
        if space_enabled:
            result.update(
                self._create_space_engines(
                    rng_mgr,
                    bus,
                    config,
                    gps_enabled="gps" not in disabled,
                    clock=clock,
                ),
            )

        # 3. CBRN engines
        cbrn_enabled = self._optional_suite_enabled(
            config.cbrn_config,
            enable_field="enable_cbrn",
            config_field="cbrn_config",
        )
        if cbrn_enabled and "cbrn" in disabled:
            raise ScenarioReferenceError(
                "Era feature 'cbrn' is disabled but "
                "cbrn_config.enable_cbrn is true",
            )
        if cbrn_enabled:
            result.update(self._create_cbrn_engines(rng_mgr, bus, config))

        # 4. Schools
        if config.school_config is not None or doctrine_side_assignments:
            school_config = dict(config.school_config or {})
            # Exact per-unit assignments are committed with profile-derived
            # and analysis assignments in one precedence-ordered plan.
            school_config["unit_assignments"] = {}
            result.update(self._create_school_engines(school_config))

        # 5. Commander
        # Production commander construction is preflighted in ``load()``
        # before the first ENTITIES draw and injected into the engine map
        # after this optional-suite factory returns.

        # 6. Escalation
        if config.escalation_config is not None:
            result.update(self._create_escalation_engines(rng_mgr, bus, config.escalation_config))

            # Phase 44d: Population engines for escalation scenarios
            from stochastic_warfare.population.civilians import CivilianManager
            from stochastic_warfare.population.collateral import CollateralEngine

            pop_rng = rng_mgr.get_stream(ModuleId.POPULATION)
            result["population_manager"] = CivilianManager(bus, pop_rng)
            result["collateral_engine"] = CollateralEngine(bus)
        else:
            # Phase 101 — unconventional_engine is needed for initial_ieds /
            # urban scenarios even without a full escalation_config.  Lightweight
            # engines (bus + rng only) so zero cost when unused.
            if config.initial_ieds:
                from stochastic_warfare.combat.unconventional import (
                    UnconventionalWarfareEngine,
                )
                from stochastic_warfare.combat.damage import IncendiaryDamageEngine
                combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)
                result["unconventional_engine"] = UnconventionalWarfareEngine(
                    bus, combat_rng,
                )
                if "incendiary_engine" not in result:
                    result["incendiary_engine"] = IncendiaryDamageEngine(combat_rng)

        # 7. Era engines
        if config.era != "modern":
            result.update(self._create_era_engines(rng_mgr, bus, config))

        # 8. DEW engines
        if config.dew_config is not None:
            result.update(self._create_dew_engine(rng_mgr, bus, config.dew_config))

        return result

    @staticmethod
    def _optional_suite_enabled(
        config_block: dict[str, Any] | None,
        *,
        enable_field: str,
        config_field: str,
    ) -> bool:
        """Return an optional suite's explicit, validated enable flag."""
        if config_block is None:
            return False
        enabled = config_block.get(enable_field, False)
        if not isinstance(enabled, bool):
            raise ValueError(
                f"{config_field}.{enable_field} must be a boolean",
            )
        return enabled

    def _create_ew_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        ew_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Create EW sub-engines from ew_config."""
        ew_rng = rng_mgr.get_stream(ModuleId.EW)

        from stochastic_warfare.ew.jamming import JammingConfig, JammingEngine
        from stochastic_warfare.ew.eccm import ECCMEngine
        from stochastic_warfare.ew.sigint import SIGINTEngine
        from stochastic_warfare.ew.decoys_ew import EWDecoyEngine

        jam_config = JammingConfig.model_validate(ew_cfg)
        ew_engine = JammingEngine(bus, ew_rng, jam_config)
        eccm_engine = ECCMEngine(bus)
        sigint_engine = SIGINTEngine(bus, ew_rng)
        ew_decoy_engine = EWDecoyEngine(bus, ew_rng)

        # Phase 65b: Load SIGINT collectors from scenario ew_config
        from stochastic_warfare.ew.sigint import SIGINTCollector
        for side_key in ("blue_sigint_collectors", "red_sigint_collectors"):
            for coll_data in ew_cfg.get(side_key, []):
                side = "blue" if "blue" in side_key else "red"
                collector = SIGINTCollector(
                    collector_id=coll_data["collector_id"],
                    unit_id=coll_data.get("unit_id", coll_data["collector_id"]),
                    position=Position(0.0, 0.0, 0.0),
                    receiver_sensitivity_dbm=coll_data["receiver_sensitivity_dbm"],
                    frequency_range_ghz=tuple(coll_data["frequency_range_ghz"]),
                    bandwidth_ghz=coll_data["bandwidth_ghz"],
                    df_accuracy_deg=coll_data["df_accuracy_deg"],
                    has_tdoa=coll_data.get("has_tdoa", False),
                    side=side,
                    aperture_m=coll_data.get("aperture_m", 1.0),
                )
                sigint_engine.register_collector(collector)

        # Phase 65c: Load ECCM suites from scenario ew_config
        from stochastic_warfare.ew.eccm import ECCMSuite, ECCMTechnique
        for side_key in ("blue_eccm_suites", "red_eccm_suites"):
            for suite_data in ew_cfg.get(side_key, []):
                suite = ECCMSuite(
                    suite_id=suite_data["suite_id"],
                    unit_id=suite_data.get("unit_id", suite_data["suite_id"]),
                    techniques=[ECCMTechnique(t) for t in suite_data.get("techniques", [])],
                    hop_bandwidth_ghz=suite_data.get("hop_bandwidth_ghz", 0.0),
                    hop_rate_hz=suite_data.get("hop_rate_hz", 0.0),
                    spread_bandwidth_ghz=suite_data.get("spread_bandwidth_ghz", 0.0),
                    signal_bandwidth_ghz=suite_data.get("signal_bandwidth_ghz", 0.001),
                    processing_gain_db=suite_data.get("processing_gain_db", 0.0),
                    sidelobe_ratio_db=suite_data.get("sidelobe_ratio_db", 25.0),
                    null_depth_db=suite_data.get("null_depth_db", 30.0),
                    num_elements=suite_data.get("num_elements", 1),
                    max_nulls=suite_data.get("max_nulls", 1),
                )
                eccm_engine.register_suite(suite)

        logger.info("Created EW engines (jamming, ECCM, SIGINT, decoys)")
        return {
            "ew_engine": ew_engine,
            "eccm_engine": eccm_engine,
            "sigint_engine": sigint_engine,
            "ew_decoy_engine": ew_decoy_engine,
        }

    def _create_space_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        config: CampaignScenarioConfig,
        *,
        gps_enabled: bool = True,
        clock: SimulationClock | None = None,
    ) -> dict[str, Any]:
        """Strictly resolve catalogs and create the space-domain runtime."""
        if config.space_config is None:
            raise ValueError(
                "Cannot create space engines without space_config",
            )
        space_rng = rng_mgr.get_stream(ModuleId.SPACE)

        from stochastic_warfare.space.constellations import (
            ConstellationManager,
            SpaceEngine,
        )
        from stochastic_warfare.space.catalog import SpaceCatalog
        from stochastic_warfare.space.orbits import OrbitalMechanicsEngine
        from stochastic_warfare.space.gps import GPSEngine
        from stochastic_warfare.space.isr import SpaceISREngine
        from stochastic_warfare.space.early_warning import EarlyWarningEngine
        from stochastic_warfare.space.satcom import SATCOMEngine
        from stochastic_warfare.space.asat import ASATEngine

        sc = config.space_config
        catalog = SpaceCatalog.load(self._data_dir)
        resolved = catalog.resolve(
            sc,
            scenario_sides={side.side for side in config.sides},
        )
        orbits = OrbitalMechanicsEngine()
        constellation = ConstellationManager(orbits, bus, space_rng, sc)
        for definition in resolved.constellations:
            constellation.add_constellation(definition)

        gps = (
            GPSEngine(constellation, sc, bus, space_rng, clock=clock)
            if gps_enabled
            else None
        )
        isr = SpaceISREngine(
            constellation,
            sc,
            bus,
            space_rng,
            clock=clock,
            scenario_sides=tuple(side.side for side in config.sides),
        )
        ew_sat = EarlyWarningEngine(
            constellation,
            sc,
            bus,
            space_rng,
            clock=clock,
        )
        satcom = SATCOMEngine(
            constellation,
            sc,
            bus,
            space_rng,
            clock=clock,
        )
        asat = ASATEngine(
            constellation,
            sc,
            bus,
            space_rng,
            clock=clock,
            weapon_definitions=resolved.weapon_definitions,
            assets=resolved.assets,
            orders=resolved.orders,
            configuration_fingerprint=resolved.fingerprint,
        )

        space_engine = SpaceEngine(
            config=sc,
            constellation_manager=constellation,
            gps_engine=gps,
            isr_engine=isr,
            early_warning_engine=ew_sat,
            satcom_engine=satcom,
            asat_engine=asat,
            catalog_fingerprint=resolved.fingerprint,
        )

        logger.info(
            "Created space engines (%sGPS, ISR, EW, SATCOM, ASAT): "
            "%d constellations, %d satellites, %d ASAT assets, %d orders",
            "" if gps_enabled else "no ",
            len(resolved.constellations),
            len(constellation.all_satellites()),
            len(resolved.assets),
            len(resolved.orders),
        )
        return {"space_engine": space_engine}

    def _create_cbrn_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        config: CampaignScenarioConfig,
    ) -> dict[str, Any]:
        """Create CBRN engines from cbrn_config."""
        cbrn_rng = rng_mgr.get_stream(ModuleId.CBRN)
        cbrn_cfg = config.cbrn_config

        from stochastic_warfare.cbrn.agents import AgentRegistry
        from stochastic_warfare.cbrn.dispersal import DispersalEngine
        from stochastic_warfare.cbrn.contamination import ContaminationManager
        from stochastic_warfare.cbrn.protection import ProtectionEngine
        from stochastic_warfare.cbrn.casualties import CBRNCasualtyEngine
        from stochastic_warfare.cbrn.decontamination import DecontaminationEngine
        from stochastic_warfare.cbrn.nuclear import NuclearEffectsEngine
        from stochastic_warfare.cbrn.engine import CBRNConfig, CBRNEngine

        agent_registry = AgentRegistry()
        dispersal = DispersalEngine()

        # Grid from terrain config
        rows = max(1, int(config.terrain.height_m / config.terrain.cell_size_m))
        cols = max(1, int(config.terrain.width_m / config.terrain.cell_size_m))
        contamination = ContaminationManager(
            grid_shape=(rows, cols),
            cell_size_m=config.terrain.cell_size_m,
            origin_easting=0.0,
            origin_northing=0.0,
            event_bus=bus,
            rng=cbrn_rng,
        )
        protection = ProtectionEngine()
        casualty = CBRNCasualtyEngine(bus, cbrn_rng)
        decon = DecontaminationEngine(bus, cbrn_rng)
        nuclear = NuclearEffectsEngine(bus, cbrn_rng, dispersal)

        cbrn_config_obj = CBRNConfig.model_validate(cbrn_cfg)
        cbrn_engine = CBRNEngine(
            config=cbrn_config_obj,
            event_bus=bus,
            rng=cbrn_rng,
            agent_registry=agent_registry,
            dispersal_engine=dispersal,
            contamination_manager=contamination,
            protection_engine=protection,
            casualty_engine=casualty,
            decon_engine=decon,
            nuclear_engine=nuclear,
        )

        logger.info("Created CBRN engines")
        return {"cbrn_engine": cbrn_engine}

    def _create_school_engines(
        self,
        school_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Create doctrinal school registry from school_config."""
        from stochastic_warfare.c2.ai.schools import (
            SchoolLoader,
            SchoolRegistry,
            create_school,
        )

        loader = SchoolLoader(self._data_dir / "schools")
        definitions = loader.load_all()

        registry = SchoolRegistry()
        for defn in definitions:
            school = create_school(defn)
            registry.register(school)

        # Apply unit assignments
        unit_assignments = school_cfg.get("unit_assignments", {})
        for unit_id, school_id in unit_assignments.items():
            registry.assign_to_unit(unit_id, school_id)

        logger.info(
            "Created school registry with %d schools, %d assignments",
            len(definitions),
            len(unit_assignments),
        )
        return {"school_registry": registry}

    def _create_commander_engine(
        self,
        c2_rng: np.random.Generator,
        commander_cfg: CommanderScenarioConfig | Mapping[str, Any],
        *,
        era: str = "modern",
    ) -> dict[str, Any]:
        """Create an isolated commander engine for focused consumers."""
        loader = CommanderProfileLoader(self._data_dir / "commander_profiles")
        catalogs = [self._data_dir / "commander_profiles"]
        if era != "modern":
            catalogs.append(
                self._data_dir / "eras" / era / "commanders",
            )
        loader.load_directories(catalogs)
        config = (
            commander_cfg
            if isinstance(commander_cfg, CommanderScenarioConfig)
            else CommanderScenarioConfig.model_validate(commander_cfg)
        )
        engine = CommanderEngine(loader, c2_rng, config.engine_config())

        logger.info("Created commander engine")
        return {"commander_engine": engine}

    def _create_escalation_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        esc_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Create escalation and unconventional warfare engines."""
        esc_rng = rng_mgr.get_stream(ModuleId.ESCALATION)
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)

        from stochastic_warfare.escalation.ladder import EscalationLadder
        from stochastic_warfare.escalation.political import PoliticalPressureEngine
        from stochastic_warfare.escalation.consequences import ConsequenceEngine
        from stochastic_warfare.escalation.war_termination import WarTerminationEngine
        from stochastic_warfare.combat.unconventional import UnconventionalWarfareEngine
        from stochastic_warfare.c2.ai.sof_ops import SOFOpsEngine
        from stochastic_warfare.population.insurgency import InsurgencyEngine
        from stochastic_warfare.combat.damage import IncendiaryDamageEngine, UXOEngine

        escalation_engine = EscalationLadder(bus, esc_rng)
        political_engine = PoliticalPressureEngine(bus)
        consequence_engine = ConsequenceEngine(bus, esc_rng)
        war_termination_engine = WarTerminationEngine(bus)
        unconventional_engine = UnconventionalWarfareEngine(bus, combat_rng)
        sof_engine = SOFOpsEngine(bus, combat_rng)
        insurgency_engine = InsurgencyEngine(bus, esc_rng)
        incendiary_engine = IncendiaryDamageEngine(combat_rng)
        uxo_engine = UXOEngine(combat_rng)

        logger.info("Created escalation and unconventional engines")
        return {
            "escalation_engine": escalation_engine,
            "political_engine": political_engine,
            "consequence_engine": consequence_engine,
            "war_termination_engine": war_termination_engine,
            "unconventional_engine": unconventional_engine,
            "sof_engine": sof_engine,
            "insurgency_engine": insurgency_engine,
            "incendiary_engine": incendiary_engine,
            "uxo_engine": uxo_engine,
        }

    def _create_era_engines(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        config: CampaignScenarioConfig,
    ) -> dict[str, Any]:
        """Create era-specific engines based on config.era."""
        era = config.era
        result: dict[str, Any] = {}
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)
        movement_rng = rng_mgr.get_stream(ModuleId.MOVEMENT)
        c2_rng = rng_mgr.get_stream(ModuleId.C2)
        logistics_rng = rng_mgr.get_stream(ModuleId.LOGISTICS)

        if era == "ww2":
            from stochastic_warfare.combat.naval_gunnery import NavalGunneryEngine
            from stochastic_warfare.movement.convoy import ConvoyEngine
            from stochastic_warfare.combat.strategic_bombing import StrategicBombingEngine

            result["naval_gunnery_engine"] = NavalGunneryEngine(rng=combat_rng)
            result["convoy_engine"] = ConvoyEngine(rng=movement_rng)
            result["strategic_bombing_engine"] = StrategicBombingEngine(rng=combat_rng)
            logger.info("Created WW2 era engines")

        elif era == "ww1":
            from stochastic_warfare.terrain.trenches import TrenchSystemEngine
            from stochastic_warfare.combat.barrage import BarrageEngine
            from stochastic_warfare.combat.gas_warfare import GasWarfareEngine
            from stochastic_warfare.combat.volley_fire import VolleyFireEngine
            from stochastic_warfare.combat.melee import MeleeEngine

            result["trench_engine"] = TrenchSystemEngine()
            result["barrage_engine"] = BarrageEngine(rng=combat_rng)
            result["gas_warfare_engine"] = GasWarfareEngine(rng=combat_rng)
            result["volley_fire_engine"] = VolleyFireEngine(rng=combat_rng)
            result["melee_engine"] = MeleeEngine(rng=combat_rng)
            logger.info("Created WW1 era engines")

        elif era == "napoleonic":
            from stochastic_warfare.combat.volley_fire import VolleyFireEngine
            from stochastic_warfare.combat.melee import MeleeEngine
            from stochastic_warfare.movement.cavalry import CavalryEngine
            from stochastic_warfare.movement.formation_napoleonic import NapoleonicFormationEngine
            from stochastic_warfare.c2.courier import CourierEngine
            from stochastic_warfare.logistics.foraging import ForagingEngine

            result["volley_fire_engine"] = VolleyFireEngine(rng=combat_rng)
            result["melee_engine"] = MeleeEngine(rng=combat_rng)
            result["cavalry_engine"] = CavalryEngine(rng=movement_rng)
            result["formation_napoleonic_engine"] = NapoleonicFormationEngine()
            result["courier_engine"] = CourierEngine(rng=c2_rng)
            result["foraging_engine"] = ForagingEngine(rng=logistics_rng)
            logger.info("Created Napoleonic era engines")

        elif era == "ancient_medieval":
            from stochastic_warfare.combat.archery import ArcheryEngine
            from stochastic_warfare.combat.melee import MeleeEngine
            from stochastic_warfare.combat.siege import SiegeEngine
            from stochastic_warfare.movement.formation_ancient import AncientFormationEngine
            from stochastic_warfare.movement.naval_oar import NavalOarEngine
            from stochastic_warfare.c2.visual_signals import VisualSignalEngine

            result["archery_engine"] = ArcheryEngine(rng=combat_rng)
            result["melee_engine"] = MeleeEngine(rng=combat_rng)
            result["siege_engine"] = SiegeEngine(rng=combat_rng)
            result["formation_ancient_engine"] = AncientFormationEngine()
            result["naval_oar_engine"] = NavalOarEngine(rng=movement_rng)
            result["visual_signals_engine"] = VisualSignalEngine(rng=c2_rng)
            logger.info("Created Ancient/Medieval era engines")

        return result

    def _create_dew_engine(
        self,
        rng_mgr: RNGManager,
        bus: EventBus,
        dew_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Create directed energy weapon engine from dew_config."""
        combat_rng = rng_mgr.get_stream(ModuleId.COMBAT)

        from stochastic_warfare.combat.directed_energy import DEWConfig, DEWEngine

        config = DEWConfig.model_validate(dew_cfg)
        dew_engine = DEWEngine(bus, combat_rng, config)

        logger.info("Created DEW engine")
        return {"dew_engine": dew_engine}

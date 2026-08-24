"""Typed campaign-scenario configuration and strict source parsing."""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from stochastic_warfare.combat.indirect_fire_config import (
    IndirectFireScenarioConfig,
)
from stochastic_warfare.c2.ai.commander import (
    CommanderScenarioConfig,
)
from stochastic_warfare.core.clock import (
    normalize_clock_duration_seconds,
)
from stochastic_warfare.core.strict_yaml import load_yaml_unique
from stochastic_warfare.logistics.config import (
    LogisticsConfig,
    SupplyQuantityConfig,
)
from stochastic_warfare.logistics.stockpile import DepotType
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.deployment import (
    DeploymentConfig,
)
from stochastic_warfare.simulation.force_builder import (
    InitialUnitConfig,
)
from stochastic_warfare.space.config import SpaceConfig


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
                    previous[column - 1] + (value_character != expected_character),
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
                f"depot_type must be an exact DepotType name; got {v!r}",
            )
        return v

    @field_validator(
        "capacity_tons",
        "throughput_tons_per_hour",
        mode="before",
    )
    @classmethod
    def _positive_rates(cls, v: Any, info: Any) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or float(v) <= 0.0:
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
        keys = [(entry.supply_class_value, entry.item_id) for entry in v]
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
                "reinforcement unit overrides are not supported; define a validated unit catalog variant instead",
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
                "reinforcement position must contain [easting, northing] and optional altitude",
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
            "hbied_detonation",  # params: obstacle_id, target_unit_id
            "wp_fire_zone",  # params: center (list), radius_m, duration_s?, fuel_load?
            "unit_teleport",  # params: unit_id, position (list)
            "casualty_pulse",  # params: unit_id, casualties (int)
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
    roe_level: (
        Literal[
            "WEAPONS_HOLD",
            "WEAPONS_TIGHT",
            "WEAPONS_FREE",
        ]
        | None
    ) = Field(default=None, exclude=True)
    depots: list[DepotConfig] = Field(default_factory=list)

    @field_validator("side", mode="before")
    @classmethod
    def _valid_side(cls, value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
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
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(
                f"{info.field_name} must be a non-empty trimmed string",
            )
        return value


class TickResolutionConfig(BaseModel):
    """Tick duration settings per resolution level."""

    model_config = ConfigDict(extra="forbid")

    strategic_s: float = 3600.0
    operational_s: float = 300.0
    tactical_s: float = 5.0

    @field_validator(
        "strategic_s",
        "operational_s",
        "tactical_s",
        mode="before",
    )
    @classmethod
    def _positive_finite_duration(cls, value: Any, info: Any) -> float:
        return normalize_clock_duration_seconds(
            value,
            field_name=info.field_name,
        )


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


class SchoolScenarioConfig(BaseModel):
    """Strict source-scenario configuration for exact school assignments."""

    model_config = ConfigDict(extra="forbid")

    unit_assignments: dict[str, str] = Field(default_factory=dict)

    @field_validator("unit_assignments", mode="before")
    @classmethod
    def _strict_assignments(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, Mapping):
            raise ValueError("unit_assignments must be a mapping")
        assignments: dict[str, str] = {}
        for unit_id, school_id in value.items():
            if not isinstance(unit_id, str) or not unit_id or unit_id != unit_id.strip():
                raise ValueError(
                    "unit assignment IDs must be non-empty trimmed strings",
                )
            if not isinstance(school_id, str) or not school_id or school_id != school_id.strip():
                raise ValueError(
                    "unit assignment school IDs must be non-empty trimmed strings",
                )
            assignments[unit_id] = school_id
        return assignments


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
    school_config: SchoolScenarioConfig | None = None
    commander_config: CommanderScenarioConfig | None = None
    dew_config: dict[str, Any] | None = None
    behavior_rules: dict[str, Any] = {}
    indirect_fire: IndirectFireScenarioConfig = Field(
        default_factory=IndirectFireScenarioConfig,
    )
    logistics: LogisticsConfig = Field(default_factory=LogisticsConfig)

    @field_validator("date", mode="before")
    @classmethod
    def _strict_date(cls, value: Any) -> str:
        if type(value) is not str or not value or value != value.strip():
            raise ValueError("date must be a non-empty trimmed strict string")
        return value

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

    @field_validator("era", mode="before")
    @classmethod
    def _normalized_era_identifier(cls, value: Any) -> str:
        """Validate identity syntax; runtime boundaries resolve registry data."""
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("era must be a non-empty trimmed string")
        return value.lower()

    @field_validator("tick_duration_seconds", mode="before")
    @classmethod
    def _positive_uniform_duration(cls, value: Any) -> float | None:
        if value is None:
            return None
        return normalize_clock_duration_seconds(
            value,
            field_name="tick_duration_seconds",
        )

    @model_validator(mode="before")
    @classmethod
    def _reject_misplaced_feature_gate(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            if "disabled_modules" in data:
                raise ValueError(
                    "disabled_modules belongs to the registered era configuration, not the scenario root",
                )
            logistics_typos = sorted(key for key in data if _looks_like_logistics_key(key))
            if logistics_typos:
                raise ValueError(
                    f"Unknown scenario logistics field(s): {logistics_typos!r}",
                )
            indirect_fire_typos = sorted(key for key in data if _looks_like_indirect_fire_key(key))
            if indirect_fire_typos:
                raise ValueError(
                    f"Unknown or misplaced scenario indirect-fire field(s): {indirect_fire_typos!r}",
                )
            indirect_fire = data.get("indirect_fire")
            declared_missions = (
                indirect_fire.get("time_on_target_missions") if isinstance(indirect_fire, Mapping) else None
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
                        "declared time-on-target missions require a finite positive whole-second tick_duration_seconds",
                    )
        return data

    @model_validator(mode="after")
    def _validate_side_references(self) -> CampaignScenarioConfig:
        side_names = [side.side for side in self.sides]
        if len(side_names) != len(set(side_names)):
            raise ValueError("scenario side names must be unique")
        known_sides = set(side_names)
        commander_profiles = [side.commander_profile for side in self.sides]
        populated_profiles = [profile_id for profile_id in commander_profiles if profile_id]
        if populated_profiles and len(populated_profiles) != len(self.sides):
            raise ValueError(
                "commander profiles must be populated for every side or omitted for every side",
            )
        if self.commander_config is not None and not populated_profiles:
            raise ValueError(
                "commander_config requires canonical commander_profile values on every side",
            )
        if self.space_config is not None:
            space_config = self.space_config
            if space_config.enable_space and not space_config.constellation_ids:
                raise ValueError(
                    "space_config.enable_space requires at least one explicit constellation_id",
                )
            for asset in space_config.asat_assets:
                if asset.side not in known_sides:
                    raise ValueError(
                        f"ASAT asset {asset.asset_id!r} references unknown scenario side {asset.side!r}",
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
            if space_config.imint_fusion_constellation_ids and not self.calibration_overrides.enable_space_effects:
                raise ValueError(
                    "space_config.imint_fusion_constellation_ids requires "
                    "calibration_overrides.enable_space_effects=true",
                )
        for index, reinforcement in enumerate(self.reinforcements):
            if reinforcement.side not in known_sides:
                raise ValueError(
                    f"reinforcement {index} references unknown side {reinforcement.side!r}",
                )

        depots_by_id: dict[str, str] = {}
        declared_unit_types: dict[str, set[str]] = {
            side.side: {unit.unit_type for unit in side.units} for side in self.sides
        }
        for reinforcement in self.reinforcements:
            declared_unit_types[reinforcement.side].update(unit.unit_type for unit in reinforcement.units)
        for side in self.sides:
            for depot in side.depots:
                if depot.depot_id in depots_by_id:
                    raise ValueError(
                        f"depot_id {depot.depot_id!r} must be globally unique",
                    )
                depots_by_id[depot.depot_id] = side.side
                if self.logistics.enabled and (
                    depot.depot_type is None or depot.condition is None or depot.initial_inventory is None
                ):
                    raise ValueError(
                        f"enabled logistics depot {depot.depot_id!r} requires "
                        "explicit depot_type, condition, and initial_inventory",
                    )

        profile_keys = {(profile.side, profile.unit_type) for profile in self.logistics.unit_profiles}
        for side, unit_type in sorted(profile_keys):
            if side not in known_sides:
                raise ValueError(
                    f"logistics profile references unknown side {side!r}",
                )
            if unit_type not in declared_unit_types[side]:
                raise ValueError(
                    f"logistics profile references an undeclared unit type {side!r}/{unit_type!r}",
                )
        if self.logistics.enabled:
            expected_profiles = {
                (side, unit_type) for side, unit_types in declared_unit_types.items() for unit_type in unit_types
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
                    f"route {route.route_id!r} references unknown depot {route.depot_id!r}",
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
                        f"parallel route templates for the same depot and unit type are unsupported: {key!r}",
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
                    "declared time-on-target missions require a finite positive whole-second tick_duration_seconds",
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
                    fire_time_s = mission.impact_time_s - battery.time_of_flight_s
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
        set(raw) - runtime_fields - NON_RUNTIME_SCENARIO_ROOT_FIELDS,
    )
    if unknown:
        raise ValueError(
            f"unknown scenario root field(s): {unknown!r}",
        )
    normalized = {key: copy.deepcopy(value) for key, value in raw.items() if key in runtime_fields}
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


def _doctrine_policy_index(
    assignments: tuple[DoctrineSideAssignment, ...],
) -> dict[str, str]:
    """Validate a typed ordered policy before creating an internal index."""
    sides = [assignment.side for assignment in assignments]
    if len(sides) != len(set(sides)):
        raise ValueError(
            f"Doctrine policy side IDs must be unique: {sides!r}",
        )
    return {assignment.side: assignment.school_id for assignment in assignments}


def parse_scenario_start_time(date_str: str) -> datetime:
    """Parse ISO date/datetime string into UTC-aware datetime."""
    if "T" in date_str:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    parts = date_str.split("-")
    return datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)

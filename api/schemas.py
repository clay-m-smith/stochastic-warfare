"""Pydantic request/response models for the API."""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.scenario_names import validate_scenario_name


_SQLITE_SIGNED_INTEGER_MAX = (1 << 63) - 1


def _check_dict_depth(
    d: dict,
    max_depth: int = 5,
    max_keys: int = 200,
    _current: int = 0,
) -> None:
    """Validate nesting depth and key count of a dict tree."""
    if _current > max_depth:
        raise ValueError(f"Nesting exceeds max depth {max_depth}")
    if len(d) > max_keys:
        raise ValueError(f"More than {max_keys} keys at one level")
    for v in d.values():
        if isinstance(v, dict):
            _check_dict_depth(v, max_depth, max_keys, _current + 1)


def _validate_metric_names(values: list[str]) -> list[str]:
    """Validate an ordered metric request before runtime side resolution."""
    if any(not isinstance(value, str) or not value or value != value.strip() for value in values):
        raise ValueError(
            "metrics must contain non-empty trimmed strings",
        )
    if len(values) != len(set(values)):
        raise ValueError("metrics must be duplicate-free")
    return values


def _validate_scenario_identifier(value: Any) -> str:
    """Reject malformed scenario identifiers before path resolution."""
    return validate_scenario_name(value)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


class ScenarioSummary(BaseModel):
    """Lightweight scenario listing entry."""

    name: str
    display_name: str = ""
    era: str = "modern"
    duration_hours: float = 0
    sides: list[str] = Field(default_factory=list)
    terrain_type: str = ""
    has_ew: bool = False
    has_cbrn: bool = False
    has_escalation: bool = False
    has_schools: bool = False
    has_space: bool = False
    has_dew: bool = False


class ScenarioDetail(BaseModel):
    """Full scenario detail."""

    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    force_summary: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


class UnitSummary(BaseModel):
    """Lightweight unit listing entry."""

    unit_type: str
    display_name: str = ""
    domain: str = ""
    category: str = ""
    era: str = "modern"
    max_speed: float = 0
    crew_size: int = 0


class UnitDetail(BaseModel):
    """Full unit definition."""

    unit_type: str
    definition: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


class RunStatus(str, Enum):
    """Simulation run lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunSubmitRequest(BaseModel):
    """Request to start a simulation run."""

    model_config = ConfigDict(extra="forbid", str_max_length=100_000)

    scenario: str
    seed: StrictInt = Field(
        default=42,
        ge=0,
        le=_SQLITE_SIGNED_INTEGER_MAX,
    )
    max_ticks: StrictInt = Field(default=10_000, ge=1, le=1_000_000)
    config_overrides: CalibrationSchema = Field(
        default_factory=CalibrationSchema,
        description="Sparse CalibrationSchema overlay. Supports enable_* boolean flags, "
        "numeric modifiers, nested morale calibration, per-side overrides, and "
        "weapon assignments. Absent fields preserve scenario values.",
    )
    frame_interval: int | None = None

    @field_validator("scenario", mode="before")
    @classmethod
    def _valid_scenario(cls, value: Any) -> str:
        return _validate_scenario_identifier(value)

    @field_validator("config_overrides", mode="before")
    @classmethod
    def _validate_overrides(cls, v: Any) -> Any:
        if isinstance(v, dict):
            _check_dict_depth(v)
            return CalibrationSchema.model_validate(v, strict=True)
        return v


class RunSubmitResponse(BaseModel):
    """Response after submitting a run."""

    run_id: str
    status: RunStatus = RunStatus.PENDING


class RunSummary(BaseModel):
    """Run listing entry."""

    run_id: str
    scenario_name: str
    seed: int
    status: RunStatus
    created_at: str
    completed_at: str | None = None
    error_message: str | None = None


class RunDetail(BaseModel):
    """Full run detail including results."""

    run_id: str
    scenario_name: str
    scenario_path: str
    seed: int
    max_ticks: int
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    status: RunStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None


class EventItem(BaseModel):
    """A single recorded event."""

    tick: int
    event_type: str
    source: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class EventsResponse(BaseModel):
    """Paginated events response."""

    events: list[EventItem] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 100


class NarrativeResponse(BaseModel):
    """Formatted narrative text."""

    narrative: str = ""
    tick_count: int = 0


class ForcesResponse(BaseModel):
    """Side force states from result."""

    sides: dict[str, Any] = Field(default_factory=dict)


class SnapshotsResponse(BaseModel):
    """State snapshots from run."""

    snapshots: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Map / Spatial Data
# ---------------------------------------------------------------------------


class MapUnitFrame(BaseModel):
    """A single unit's position in one frame."""

    id: str
    side: str
    x: float
    y: float
    domain: int = 0
    status: int = 0
    heading: float = 0.0
    type: str = ""
    sensor_range: float = 0.0
    # Phase 92: enriched unit state for tactical map overlays
    morale: int = 0  # 0=STEADY..4=SURRENDERED
    posture: str = ""  # MOVING, DEFENSIVE, DUG_IN, ASSAULT, etc.
    health: float = 1.0  # 0.0–1.0
    fuel_pct: float = 1.0  # 0.0–1.0
    ammo_pct: float = 1.0  # 0.0–1.0
    suppression: int = 0  # 0–4
    engaged: bool = False


class ReplayFrame(BaseModel):
    """One tick's worth of unit positions."""

    tick: int
    units: list[MapUnitFrame] = Field(default_factory=list)
    detected: dict[str, list[str]] = Field(default_factory=dict)


class FramesResponse(BaseModel):
    """Paginated replay frames."""

    frames: list[ReplayFrame] = Field(default_factory=list)
    total_frames: int = 0


class ObjectiveInfo(BaseModel):
    """Map objective marker."""

    id: str
    x: float
    y: float
    radius: float = 500.0


class TerrainResponse(BaseModel):
    """Static terrain data for a run."""

    width_cells: int = 0
    height_cells: int = 0
    cell_size: float = 100.0
    origin_easting: float = 0.0
    origin_northing: float = 0.0
    land_cover: list[list[int]] = Field(default_factory=list)
    elevation: list[list[float]] = Field(default_factory=list)
    objectives: list[ObjectiveInfo] = Field(default_factory=list)
    extent: list[float] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Batch / MC
# ---------------------------------------------------------------------------


class BatchSubmitRequest(BaseModel):
    """Request to run Monte Carlo batch."""

    model_config = ConfigDict(extra="forbid", str_max_length=100_000)

    scenario: str
    num_iterations: StrictInt = Field(default=20, ge=1, le=1_000)
    base_seed: StrictInt = Field(
        default=42,
        ge=0,
        le=_SQLITE_SIGNED_INTEGER_MAX,
    )
    max_ticks: StrictInt = Field(default=1000, ge=1, le=1_000_000)
    config_overrides: CalibrationSchema = Field(
        default_factory=CalibrationSchema,
        description=(
            "Strict sparse CalibrationSchema overlay applied to every iteration before the batch is published."
        ),
    )
    metrics: list[str] | None = Field(
        default=None,
        min_length=1,
        description=(
            "Exact ordered metrics. When omitted, active/destroyed metrics are derived for every exact loaded side."
        ),
    )

    @field_validator("scenario", mode="before")
    @classmethod
    def _valid_scenario(cls, value: Any) -> str:
        return _validate_scenario_identifier(value)

    @field_validator("config_overrides", mode="before")
    @classmethod
    def _strict_batch_overrides(cls, value: Any) -> Any:
        if isinstance(value, dict):
            _check_dict_depth(value)
            return CalibrationSchema.model_validate(value, strict=True)
        return value

    @field_validator("metrics")
    @classmethod
    def _batch_metrics_unique(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        if values is None:
            return values
        return _validate_metric_names(values)


class BatchSubmitResponse(BaseModel):
    """Response after submitting a batch."""

    batch_id: str
    status: RunStatus = RunStatus.PENDING


class BatchDetail(BaseModel):
    """Batch run detail."""

    batch_id: str
    scenario_name: str
    num_iterations: int
    base_seed: int
    max_ticks: int
    completed_iterations: int = 0
    status: RunStatus
    created_at: str
    completed_at: str | None = None
    metrics: dict[str, Any] | None = None
    ordered_metrics: list[str] = Field(default_factory=list)
    raw_metrics: dict[str, list[float]] | None = None
    provenance: dict[str, Any] | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    """Request for A/B comparison."""

    model_config = ConfigDict(extra="forbid", str_max_length=100_000)

    scenario: str
    overrides_a: CalibrationSchema = Field(default_factory=CalibrationSchema)
    overrides_b: CalibrationSchema = Field(default_factory=CalibrationSchema)
    label_a: str = "A"
    label_b: str = "B"
    metrics: list[str] | None = Field(default=None, min_length=1)
    num_iterations: StrictInt = Field(default=20, ge=2, le=500)
    base_seed: StrictInt = Field(default=42, ge=0)
    max_ticks: StrictInt = Field(default=100, ge=1, le=1_000_000)
    alpha: StrictFloat = Field(default=0.05, gt=0.0, lt=1.0)

    @field_validator("scenario", mode="before")
    @classmethod
    def _valid_scenario(cls, value: Any) -> str:
        return _validate_scenario_identifier(value)

    @field_validator("label_a", "label_b", mode="before")
    @classmethod
    def _valid_label(cls, value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise ValueError(
                "comparison labels must be non-empty trimmed strings",
            )
        return value

    @field_validator("overrides_a", "overrides_b", mode="before")
    @classmethod
    def _strict_analysis_overrides(cls, value: Any) -> CalibrationSchema:
        if not isinstance(value, dict):
            return value
        _check_dict_depth(value)
        return CalibrationSchema.model_validate(value, strict=True)

    @field_validator("metrics")
    @classmethod
    def _compare_metrics_unique(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None
        return _validate_metric_names(values)

    @field_validator("alpha")
    @classmethod
    def _compare_alpha_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("alpha must be finite")
        return value


class SweepRequest(BaseModel):
    """Request for parameter sweep."""

    model_config = ConfigDict(extra="forbid", str_max_length=100_000)

    scenario: str
    parameter_name: str
    values: list[StrictFloat] = Field(min_length=1, max_length=50)
    metrics: list[str] | None = Field(default=None, min_length=1)
    num_iterations: StrictInt = Field(default=10, ge=2, le=500)
    base_seed: StrictInt = Field(default=42, ge=0)
    max_ticks: StrictInt = Field(default=100, ge=1, le=1_000_000)

    @field_validator("scenario", mode="before")
    @classmethod
    def _valid_scenario(cls, value: Any) -> str:
        return _validate_scenario_identifier(value)

    @field_validator("parameter_name", mode="before")
    @classmethod
    def _valid_parameter_name(cls, value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise ValueError(
                "parameter_name must be a non-empty trimmed string",
            )
        CalibrationSchema.model_validate(
            {value: 0.0},
            strict=True,
        )
        return value

    @field_validator("values")
    @classmethod
    def _sweep_values_finite_unique(
        cls,
        values: list[float],
    ) -> list[float]:
        if any(isinstance(value, bool) or not math.isfinite(value) for value in values):
            raise ValueError("sweep values must be finite")
        if len(values) != len(set(values)):
            raise ValueError("sweep values must be duplicate-free")
        return values

    @field_validator("metrics")
    @classmethod
    def _sweep_metrics_unique(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None
        return _validate_metric_names(values)


class DoctrineSideAssignmentRequest(BaseModel):
    """One explicit public side-to-school assignment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    side: str
    school_id: str

    @field_validator("side", "school_id", mode="before")
    @classmethod
    def _trimmed_identifier(cls, value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("assignment identifiers must be trimmed")
        return value


class DoctrineVariantRequest(BaseModel):
    """One named doctrine policy represented as an ordered assignment list."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    variant_id: str
    assignments: list[DoctrineSideAssignmentRequest] = Field(
        min_length=1,
        max_length=20,
    )
    calibration_patch: CalibrationSchema = Field(
        default_factory=CalibrationSchema,
        description=("Strict sparse calibration overlay held identical across doctrine variants."),
    )

    @field_validator("variant_id", mode="before")
    @classmethod
    def _trimmed_variant_id(cls, value: Any) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("variant_id must be a trimmed identifier")
        return value

    @field_validator("assignments")
    @classmethod
    def _unique_assignment_sides(
        cls,
        values: list[DoctrineSideAssignmentRequest],
    ) -> list[DoctrineSideAssignmentRequest]:
        sides = [assignment.side for assignment in values]
        if len(sides) != len(set(sides)):
            raise ValueError("assignment sides must be duplicate-free")
        return values

    @field_validator("calibration_patch", mode="before")
    @classmethod
    def _strict_doctrine_patch(cls, value: Any) -> Any:
        if isinstance(value, dict):
            _check_dict_depth(value)
            return CalibrationSchema.model_validate(value, strict=True)
        return value


class DoctrineCompareRequest(BaseModel):
    """Strict request for a doctrine-only common-seed comparison."""

    model_config = ConfigDict(extra="forbid", str_max_length=100_000)

    scenario: str
    variants: list[DoctrineVariantRequest] = Field(
        min_length=2,
        max_length=20,
    )
    metrics: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=20,
    )
    num_iterations: StrictInt = Field(default=10, ge=2, le=500)
    base_seed: StrictInt = Field(default=42, ge=0)
    max_ticks: StrictInt = Field(default=100, ge=1, le=1_000_000)

    @field_validator("scenario", mode="before")
    @classmethod
    def _trimmed_scenario(cls, value: Any) -> str:
        return _validate_scenario_identifier(value)

    @field_validator("metrics")
    @classmethod
    def _doctrine_metrics_unique(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None
        return _validate_metric_names(values)

    @model_validator(mode="after")
    def _comparable_policies(self) -> DoctrineCompareRequest:
        variant_ids = [variant.variant_id for variant in self.variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("variant_id values must be duplicate-free")
        side_sets = [frozenset(assignment.side for assignment in variant.assignments) for variant in self.variants]
        if any(side_set != side_sets[0] for side_set in side_sets[1:]):
            raise ValueError(
                "all variants must assign the same exact side set",
            )
        policies = {
            tuple(
                sorted(
                    (
                        assignment.side,
                        assignment.school_id,
                    )
                    for assignment in variant.assignments
                ),
            )
            for variant in self.variants
        }
        if len(policies) < 2:
            raise ValueError(
                "doctrine comparison requires distinct assignment policies",
            )
        schools = {assignment.school_id for variant in self.variants for assignment in variant.assignments}
        if len(schools) < 2:
            raise ValueError(
                "doctrine comparison requires two distinct schools",
            )
        patches = [
            variant.calibration_patch.to_sparse_patch(mode="json")
            for variant in self.variants
        ]
        if any(patch != patches[0] for patch in patches[1:]):
            raise ValueError(
                "doctrine comparison must hold calibration patches identical",
            )
        return self


class DoctrineMetricResult(BaseModel):
    """Exact values and sample statistics for a doctrine metric."""

    metric: str
    mean: float
    std: float
    values: list[float]


class DoctrineVariantResult(BaseModel):
    """One doctrine policy result."""

    variant_id: str
    assignments: list[DoctrineSideAssignmentRequest]
    metrics: list[DoctrineMetricResult]
    batch: dict[str, Any]


class DoctrineCompareResult(BaseModel):
    """Result from doctrine comparison analysis."""

    scenario: str
    num_iterations: int
    base_seed: int
    max_ticks: int
    ordered_metrics: list[str]
    seeds: list[int]
    results: list[DoctrineVariantResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = ""
    scenario_count: int = 0
    unit_count: int = 0


class HealthLiveResponse(BaseModel):
    """Liveness probe response — instant, no external checks."""

    status: str = "ok"


class HealthReadyResponse(BaseModel):
    """Readiness probe response — includes DB connectivity check."""

    status: str = "ok"
    version: str = ""
    scenario_count: int = 0
    unit_count: int = 0
    db_connected: bool = False


class EraInfo(BaseModel):
    """Era metadata."""

    name: str
    value: str
    disabled_modules: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scenario Editor (Phase 36)
# ---------------------------------------------------------------------------


class RunFromConfigRequest(BaseModel):
    """Request to start a run from an inline config dict."""

    model_config = ConfigDict(extra="forbid", str_max_length=100_000)

    config: dict[str, Any]
    seed: StrictInt = Field(
        default=42,
        ge=0,
        le=_SQLITE_SIGNED_INTEGER_MAX,
    )
    max_ticks: StrictInt = Field(default=10_000, ge=1, le=1_000_000)

    @field_validator("config")
    @classmethod
    def _validate_config(cls, v: dict[str, Any]) -> dict[str, Any]:
        _check_dict_depth(v)
        return v


class ValidateConfigRequest(BaseModel):
    """Request to validate a scenario config."""

    config: dict[str, Any]


class ValidateConfigResponse(BaseModel):
    """Response from config validation."""

    valid: bool = True
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Analytics (Phase 92)
# ---------------------------------------------------------------------------


class CasualtyGroup(BaseModel):
    """A group of casualties (by weapon, side, or tick)."""

    label: str
    count: int = 0
    side: str = ""


class CasualtyAnalytics(BaseModel):
    """Casualty breakdown for a completed run."""

    groups: list[CasualtyGroup] = Field(default_factory=list)
    total: int = 0


class SuppressionTimelinePoint(BaseModel):
    """Suppression count at a single tick."""

    tick: int
    count: int = 0


class SuppressionAnalytics(BaseModel):
    """Suppression metrics for a completed run."""

    peak_suppressed: int = 0
    peak_tick: int = 0
    rout_cascades: int = 0
    timeline: list[SuppressionTimelinePoint] = Field(default_factory=list)


class MoraleTimelinePoint(BaseModel):
    """Morale state distribution at a single tick."""

    tick: int
    steady: int = 0
    shaken: int = 0
    broken: int = 0
    routed: int = 0
    surrendered: int = 0


class MoraleAnalytics(BaseModel):
    """Morale state distribution over time."""

    timeline: list[MoraleTimelinePoint] = Field(default_factory=list)


class EngagementTypeGroup(BaseModel):
    """Engagement count and hit rate for one engagement type."""

    type: str
    count: int = 0
    hit_rate: float = 0.0


class EngagementAnalytics(BaseModel):
    """Engagement summary for a completed run."""

    by_type: list[EngagementTypeGroup] = Field(default_factory=list)
    total: int = 0


class AnalyticsSummary(BaseModel):
    """Combined analytics for a completed run."""

    casualties: CasualtyAnalytics = Field(default_factory=CasualtyAnalytics)
    suppression: SuppressionAnalytics = Field(default_factory=SuppressionAnalytics)
    morale: MoraleAnalytics = Field(default_factory=MoraleAnalytics)
    engagements: EngagementAnalytics = Field(default_factory=EngagementAnalytics)


# ---------------------------------------------------------------------------
# Metadata (Phase 92)
# ---------------------------------------------------------------------------


class SchoolInfo(BaseModel):
    """Doctrinal school summary."""

    school_id: str
    display_name: str = ""
    description: str = ""
    ooda_multiplier: float = 1.0
    risk_tolerance: str = ""


class CommanderInfo(BaseModel):
    """Commander profile summary."""

    profile_id: str
    display_name: str = ""
    description: str = ""
    traits: dict[str, float] = Field(default_factory=dict)


class WeaponSummary(BaseModel):
    """Weapon listing entry."""

    weapon_id: str
    display_name: str = ""
    category: str = ""
    max_range_m: float = 0.0
    caliber_mm: float = 0.0


class WeaponDetail(BaseModel):
    """Full weapon definition."""

    weapon_id: str
    definition: dict[str, Any] = Field(default_factory=dict)

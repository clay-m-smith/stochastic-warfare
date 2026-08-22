"""Pydantic request/response models for the API."""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from stochastic_warfare.detection.intel_fusion import validate_fow_track_id
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.loadouts import (
    SensorModeledRole,
    WeaponModeledRole,
)
from stochastic_warfare.simulation.performance_flags import (
    GovernedPerformanceFlag,
    PerformanceFlagClassification,
    PerformanceFlagSupportDisposition,
    RetainedSemanticVerdict,
    validate_supported_runtime_performance_parameter_name,
)
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    EffectiveRangeBasis,
    FireControlSource,
    TargetingDisposition,
)
from stochastic_warfare.simulation.targeting_exposure import (
    PublicIdentificationLevel,
    PublicTrackStatus,
    TargetingExposureScope,
)
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


class HistoricalClaimDisposition(str, Enum):
    """Public disposition for one historical-validation claim."""

    PRODUCTION_VALIDATED = "production_validated"
    CURRENT_ENGINE_REGRESSION_ONLY = "current_engine_regression_only"
    UNSUPPORTED = "unsupported"


class HistoricalValidationClaim(BaseModel):
    """Claim-level historical-validation status published by the API."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    disposition: HistoricalClaimDisposition
    reason_codes: list[str]
    limitation: str
    intended_use: str
    metric_scope: list[str]
    event_scope: str
    current_engine_regression_evidence: bool
    accepted_study_id: str | None
    accepted_artifact_path: str | None


class HistoricalValidationSummary(BaseModel):
    """Conservative aggregate of a scenario's inventoried claims."""

    model_config = ConfigDict(extra="forbid")

    aggregate_disposition: HistoricalClaimDisposition
    claims: list[HistoricalValidationClaim]
    accepted_claim_ids: list[str]
    current_engine_regression_evidence: bool
    ledger_sha256: str


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
    historical_validation: HistoricalValidationSummary


class ScenarioDetail(BaseModel):
    """Full scenario detail."""

    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    force_summary: dict[str, Any] = Field(default_factory=dict)
    historical_validation: HistoricalValidationSummary


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


class PrivilegedObserverTrackSupportIdentity(BaseModel):
    """Exact observer-attachment identity for privileged support evidence."""

    model_config = ConfigDict(extra="forbid")

    reporting_side: str
    observer_unit_id: str
    source_equipment_index: int
    sensor_id: str
    modeled_role: Literal[
        "airborne_fire_control_radar",
        "airborne_ground_fire_control_radar",
        "airborne_multi_domain_fire_control_radar",
        "fire_control_radar",
        "ground_air_defense_fire_control_radar",
        "naval_fire_control_radar",
        "naval_air_defense_fire_control_radar",
    ]
    target_id: str


class PrivilegedObserverTrackSupportEvidence(BaseModel):
    """Lossless projected observer-track support for privileged consumers."""

    model_config = ConfigDict(extra="forbid")

    identity: PrivilegedObserverTrackSupportIdentity
    fusion_track_id: str
    sensor_type: Literal["RADAR"]
    observation_ordinal: int
    observation_time_s: float
    native_period: int
    native_phase_residue: int
    native_due_ordinal: int
    position_m: tuple[float, float]
    velocity_mps: tuple[float, float]
    covariance: tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
    ]
    projection_ordinal: int
    projection_time_s: float


class PrivilegedTargetingDecision(BaseModel):
    """Exact engine/evaluator targeting evidence for one shooter."""

    model_config = ConfigDict(extra="forbid")

    engine_tick: int
    logical_time_s: float
    battle_id: str
    ordinal: int
    shooter_id: str
    shooter_side: str
    shooter_domain: str
    target_id: str | None
    target_side: str | None
    target_domain: str | None
    distance_m: float
    weapon_id: str | None
    weapon_source_equipment_index: int | None
    weapon_modeled_role: WeaponModeledRole | None
    ammunition_id: str | None
    physical_max_range_m: float
    predictive_effective_range_m: float
    effective_range_basis: EffectiveRangeBasis | None
    legacy_derived_reference_range_m: float
    contact_source: ContactSource
    observing_unit_id: str | None
    contact_sensor_source_equipment_index: int | None
    contact_sensor_id: str | None
    contact_sensor_modeled_role: SensorModeledRole | None
    contact_time_s: float | None
    contact_range_m: float
    visibility_bound_m: float
    sensing_sensor_source_equipment_index: int | None
    sensing_sensor_id: str | None
    sensing_sensor_modeled_role: SensorModeledRole | None
    sensing_range_m: float
    fire_control_source: FireControlSource
    fire_control_sensor_source_equipment_index: int | None
    fire_control_sensor_id: str | None
    fire_control_sensor_modeled_role: SensorModeledRole | None
    fire_control_range_m: float
    disposition: TargetingDisposition
    authorized_standoff_m: float
    hold_authorized: bool
    engagement_solution_valid: bool
    sensing_aware_standoff_enabled: bool
    fog_of_war_enabled: bool
    consumable: bool
    observer_track_support: PrivilegedObserverTrackSupportEvidence | None


class PrivilegedEngagementRevalidationOutcome(BaseModel):
    """Exact post-movement targeting outcome for privileged consumers."""

    model_config = ConfigDict(extra="forbid")

    engine_tick: int
    logical_time_s: float
    battle_id: str
    shooter_id: str
    target_id: str
    weapon_id: str
    weapon_source_equipment_index: int
    weapon_modeled_role: WeaponModeledRole
    ammunition_id: str
    disposition: TargetingDisposition
    revalidation_passed: bool
    fog_of_war_enabled: bool
    consumable: bool


class SideFowPublicTrack(BaseModel):
    """Opaque public track fields visible to one reporting side."""

    model_config = ConfigDict(extra="forbid")

    track_id: str
    reporting_side: str
    easting_m: float
    northing_m: float
    velocity_east_mps: float
    velocity_north_mps: float
    position_uncertainty_m: float
    status: PublicTrackStatus
    identification_level: PublicIdentificationLevel
    domain_estimate: str | None
    type_estimate: str | None
    specific_estimate: str | None
    confidence: float
    first_detected_time_s: float
    last_sensor_contact_time_s: float

    @field_validator("track_id", mode="before")
    @classmethod
    def _canonical_track_id(cls, value: Any) -> str:
        return validate_fow_track_id(value, "track_id")


class SideFowTargetingDecision(BaseModel):
    """Attachment- and target-identity-free targeting result for one side."""

    model_config = ConfigDict(extra="forbid")

    engine_tick: int
    logical_time_s: float
    battle_id: str
    ordinal: int
    shooter_id: str
    viewer_side: str
    target_track_id: str | None
    disposition: TargetingDisposition
    contact_source: ContactSource
    contact_time_s: float | None
    authorized_standoff_m: float
    hold_authorized: bool
    engagement_solution_valid: bool
    sensing_aware_standoff_enabled: bool
    fog_of_war_enabled: bool
    consumable: bool

    @field_validator("target_track_id", mode="before")
    @classmethod
    def _canonical_target_track_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        return validate_fow_track_id(value, "target_track_id")


class SideFowEngagementRevalidationOutcome(BaseModel):
    """Identity-bounded post-movement outcome for one viewer side."""

    model_config = ConfigDict(extra="forbid")

    engine_tick: int
    logical_time_s: float
    battle_id: str
    shooter_id: str
    viewer_side: str
    target_track_id: str
    disposition: TargetingDisposition
    revalidation_passed: bool
    fog_of_war_enabled: bool
    consumable: bool

    @field_validator("target_track_id", mode="before")
    @classmethod
    def _canonical_target_track_id(cls, value: Any) -> str:
        return validate_fow_track_id(value, "target_track_id")


class ReplayFrame(BaseModel):
    """One tick's worth of unit positions."""

    scope: TargetingExposureScope = TargetingExposureScope.PRIVILEGED_ENGINE
    viewer_side: str | None = None
    tick: int
    units: list[MapUnitFrame] = Field(default_factory=list)
    detected: dict[str, list[str]] = Field(default_factory=dict)
    targeting: list[PrivilegedTargetingDecision] = Field(default_factory=list)
    targeting_outcomes: list[PrivilegedEngagementRevalidationOutcome] = Field(
        default_factory=list,
    )
    tracks: list[SideFowPublicTrack] = Field(default_factory=list)
    side_targeting: list[SideFowTargetingDecision] = Field(
        default_factory=list,
    )
    side_targeting_outcomes: list[SideFowEngagementRevalidationOutcome] = Field(default_factory=list)

    @model_validator(mode="after")
    def _scope_isolated(self) -> ReplayFrame:
        if self.scope is TargetingExposureScope.PRIVILEGED_ENGINE:
            if self.viewer_side is not None or self.tracks or self.side_targeting or self.side_targeting_outcomes:
                raise ValueError(
                    "PRIVILEGED_ENGINE frame cannot carry SIDE_FOW fields",
                )
            return self
        if not self.viewer_side:
            raise ValueError("SIDE_FOW frame requires viewer_side")
        if self.targeting or self.targeting_outcomes:
            raise ValueError("SIDE_FOW frame cannot carry privileged targeting")
        if any(unit.side != self.viewer_side for unit in self.units):
            raise ValueError("SIDE_FOW frame contains another side's unit")
        if set(self.detected) - {self.viewer_side}:
            raise ValueError("SIDE_FOW detections contain another side")
        if any(track.reporting_side != self.viewer_side for track in self.tracks):
            raise ValueError("SIDE_FOW frame contains another side's track")
        track_ids = {track.track_id for track in self.tracks}
        for decision in self.side_targeting:
            if decision.viewer_side != self.viewer_side:
                raise ValueError("SIDE_FOW frame contains another side's decision")
            if decision.target_track_id is not None and decision.target_track_id not in track_ids:
                raise ValueError("SIDE_FOW decision references an absent track")
        decision_keys = {
            (decision.engine_tick, decision.battle_id, decision.shooter_id) for decision in self.side_targeting
        }
        for outcome in self.side_targeting_outcomes:
            if outcome.viewer_side != self.viewer_side:
                raise ValueError("SIDE_FOW frame contains another side's outcome")
            if outcome.target_track_id not in track_ids:
                raise ValueError("SIDE_FOW outcome references an absent track")
            if (
                outcome.engine_tick,
                outcome.battle_id,
                outcome.shooter_id,
            ) not in decision_keys:
                raise ValueError("SIDE_FOW outcome lacks its targeting decision")
        return self


class FramesResponse(BaseModel):
    """Paginated replay frames."""

    scope: TargetingExposureScope = TargetingExposureScope.PRIVILEGED_ENGINE
    viewer_side: str | None = None
    frames: list[ReplayFrame] = Field(default_factory=list)
    total_frames: int = 0

    @model_validator(mode="after")
    def _consistent_scope(self) -> FramesResponse:
        if self.scope is TargetingExposureScope.PRIVILEGED_ENGINE:
            if self.viewer_side is not None:
                raise ValueError(
                    "PRIVILEGED_ENGINE response cannot carry viewer_side",
                )
        elif not self.viewer_side:
            raise ValueError("SIDE_FOW response requires viewer_side")
        if any(frame.scope is not self.scope or frame.viewer_side != self.viewer_side for frame in self.frames):
            raise ValueError("frame scope disagrees with response scope")
        return self


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
        if not isinstance(value, str) or not value or value != value.strip():
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
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError(
                "parameter_name must be a non-empty trimmed string",
            )
        validate_supported_runtime_performance_parameter_name(value)
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
        patches = [variant.calibration_patch.to_sparse_patch(mode="json") for variant in self.variants]
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


class PerformanceFlagSupportInfo(BaseModel):
    """Canonical production support and retained-evidence status for one flag."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    flag: GovernedPerformanceFlag
    classification: PerformanceFlagClassification
    support_disposition: PerformanceFlagSupportDisposition
    required_meaning: str
    evidence_plan_id: str
    evidence_manifest_artifact_sha256: str
    retained_shard_status: RetainedSemanticVerdict


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

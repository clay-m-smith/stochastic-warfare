"""Pydantic request/response models for the API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    model_config = ConfigDict(str_max_length=100_000)

    scenario: str
    seed: int = 42
    max_ticks: int = Field(default=10_000, ge=1, le=1_000_000)
    config_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="CalibrationSchema overrides. Supports 29 enable_* boolean flags, "
        "50+ numeric modifiers (hit_probability_modifier, thermal_contrast, etc.), "
        "nested morale calibration, per-side overrides, and weapon_assignments. "
        "See stochastic_warfare.simulation.calibration.CalibrationSchema for full reference.",
    )
    frame_interval: int | None = None

    @field_validator("config_overrides")
    @classmethod
    def _validate_overrides(cls, v: dict[str, Any]) -> dict[str, Any]:
        _check_dict_depth(v)
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

    model_config = ConfigDict(str_max_length=100_000)

    scenario: str
    num_iterations: int = Field(default=20, ge=1, le=1_000)
    base_seed: int = 42
    max_ticks: int = Field(default=1000, ge=1, le=1_000_000)


class BatchSubmitResponse(BaseModel):
    """Response after submitting a batch."""

    batch_id: str
    status: RunStatus = RunStatus.PENDING


class BatchDetail(BaseModel):
    """Batch run detail."""

    batch_id: str
    scenario_name: str
    num_iterations: int
    completed_iterations: int = 0
    status: RunStatus
    created_at: str
    completed_at: str | None = None
    metrics: dict[str, Any] | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    """Request for A/B comparison."""

    model_config = ConfigDict(str_max_length=100_000)

    scenario: str
    overrides_a: dict[str, Any] = Field(default_factory=dict)
    overrides_b: dict[str, Any] = Field(default_factory=dict)
    label_a: str = "A"
    label_b: str = "B"
    num_iterations: int = Field(default=20, ge=1, le=500)
    max_ticks: int = Field(default=100, ge=1, le=1_000_000)


class SweepRequest(BaseModel):
    """Request for parameter sweep."""

    model_config = ConfigDict(str_max_length=100_000)

    scenario: str
    parameter_name: str
    values: list[float] = Field(max_length=50)
    num_iterations: int = Field(default=10, ge=1, le=500)
    max_ticks: int = Field(default=100, ge=1, le=1_000_000)


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

    model_config = ConfigDict(str_max_length=100_000)

    config: dict[str, Any]
    seed: int = 42
    max_ticks: int = Field(default=10_000, ge=1, le=1_000_000)

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

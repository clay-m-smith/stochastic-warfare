"""Pydantic request/response models for the API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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

    scenario: str
    seed: int = 42
    max_ticks: int = 10_000
    config_overrides: dict[str, Any] = Field(default_factory=dict)


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
# Batch / MC
# ---------------------------------------------------------------------------


class BatchSubmitRequest(BaseModel):
    """Request to run Monte Carlo batch."""

    scenario: str
    num_iterations: int = 20
    base_seed: int = 42
    max_ticks: int = 1000


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

    scenario: str
    overrides_a: dict[str, Any] = Field(default_factory=dict)
    overrides_b: dict[str, Any] = Field(default_factory=dict)
    label_a: str = "A"
    label_b: str = "B"
    num_iterations: int = 20
    max_ticks: int = 100


class SweepRequest(BaseModel):
    """Request for parameter sweep."""

    scenario: str
    parameter_name: str
    values: list[float]
    num_iterations: int = 10
    max_ticks: int = 100


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = ""
    scenario_count: int = 0
    unit_count: int = 0


class EraInfo(BaseModel):
    """Era metadata."""

    name: str
    value: str
    disabled_modules: list[str] = Field(default_factory=list)

"""Legacy historical-reference loading and diagnostic comparison.

This compatibility module can describe how aggregate simulation values differ
from legacy ``documented_outcomes`` metadata.  It is not the production
historical-validation boundary and cannot establish a historical verdict.
"""

from __future__ import annotations

import enum
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.strict_yaml import load_yaml_unique
from stochastic_warfare.morale.state import validate_morale_state_name
from stochastic_warfare.simulation.calibration import CalibrationSchema

logger = get_logger(__name__)


def _finite_float(value: Any, *, field_name: str) -> float:
    """Return one finite numeric input or reject it explicitly."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _reject_duplicate_metric_names(
    metrics: list[HistoricalMetric],
) -> list[HistoricalMetric]:
    """Reject ambiguous legacy metric collections."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for metric in metrics:
        if metric.name in seen:
            duplicates.add(metric.name)
        seen.add(metric.name)
    if duplicates:
        raise ValueError(
            f"duplicate historical metric names are not allowed: {sorted(duplicates)!r}",
        )
    return metrics


# ---------------------------------------------------------------------------
# Source quality
# ---------------------------------------------------------------------------


class SourceQuality(enum.IntEnum):
    """Confidence tier for historical data provenance."""

    PRIMARY = 0  # After-action reports, unit logs
    SECONDARY = 1  # Military histories, scholarly works
    TERTIARY = 2  # General histories, journalistic accounts


# ---------------------------------------------------------------------------
# Historical metrics
# ---------------------------------------------------------------------------


class HistoricalMetric(BaseModel):
    """One legacy documented outcome retained for diagnostic comparison."""

    name: str
    value: float
    tolerance_factor: float = 2.0  # simulated must be within Nx of historical
    unit: str = ""
    source: str = ""
    source_quality: int = SourceQuality.SECONDARY
    notes: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def _finite_value(cls, v: Any) -> float:
        return _finite_float(v, field_name="value")

    @field_validator("tolerance_factor", mode="before")
    @classmethod
    def _positive_tolerance(cls, v: Any) -> float:
        v = _finite_float(v, field_name="tolerance_factor")
        if v <= 0:
            raise ValueError("tolerance_factor must be positive")
        return v

    @field_validator("source_quality", mode="before")
    @classmethod
    def _valid_quality(cls, v: Any) -> int:
        if isinstance(v, bool):
            raise ValueError("source_quality must be 0, 1, or 2")
        if v not in (0, 1, 2):
            raise ValueError(f"source_quality must be 0, 1, or 2; got {v}")
        return v


# ---------------------------------------------------------------------------
# Force and terrain definitions
# ---------------------------------------------------------------------------


class ForceDefinition(BaseModel):
    """One side of an engagement — units, personnel, and initial state."""

    side: str
    units: list[dict[str, Any]]  # [{unit_type, count, overrides}]
    personnel_total: int
    experience_level: float  # 0-1
    morale_initial: str = "STEADY"

    @field_validator("experience_level")
    @classmethod
    def _clamp_experience(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"experience_level must be in [0, 1]; got {v}")
        return v

    @field_validator("morale_initial")
    @classmethod
    def _known_morale(cls, v: str) -> str:
        return validate_morale_state_name(v)


class TerrainSpec(BaseModel):
    """Programmatic terrain description for a scenario."""

    width_m: float
    height_m: float
    cell_size_m: float = 100.0
    base_elevation_m: float = 0.0
    terrain_type: str = "flat_desert"  # flat_desert | open_ocean | hilly_defense
    features: list[dict[str, Any]] = []  # [{type, position, params}]

    @field_validator("terrain_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        allowed = {"flat_desert", "open_ocean", "hilly_defense", "trench_warfare", "open_field"}
        if v not in allowed:
            raise ValueError(f"terrain_type must be one of {allowed}; got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Engagement definition
# ---------------------------------------------------------------------------


class HistoricalEngagement(BaseModel):
    """Legacy compatibility scenario definition loaded from YAML."""

    name: str
    date: str
    duration_hours: float
    tick_duration_seconds: float
    latitude: float
    longitude: float
    weather_conditions: dict[str, Any]
    blue_forces: ForceDefinition
    red_forces: ForceDefinition
    terrain: TerrainSpec
    documented_outcomes: list[HistoricalMetric]
    calibration_overrides: CalibrationSchema = CalibrationSchema()
    behavior_rules: dict[str, Any] = {}  # pre-scripted behavior per side
    sources: list[str] = []

    @field_validator("documented_outcomes")
    @classmethod
    def _unique_documented_outcomes(
        cls,
        metrics: list[HistoricalMetric],
    ) -> list[HistoricalMetric]:
        return _reject_duplicate_metric_names(metrics)


# ---------------------------------------------------------------------------
# Comparison results
# ---------------------------------------------------------------------------


class ComparisonResult(BaseModel):
    """Per-metric legacy diagnostic, not a historical-validation verdict."""

    metric_name: str
    historical_value: float
    simulated_mean: float
    simulated_std: float
    tolerance_factor: float
    within_tolerance: bool
    deviation_factor: float | None  # undefined when historical_value is zero

    @field_validator("historical_value", "simulated_mean", mode="before")
    @classmethod
    def _finite_measurement(cls, v: Any) -> float:
        return _finite_float(v, field_name="comparison measurement")

    @field_validator("simulated_std", mode="before")
    @classmethod
    def _finite_standard_deviation(cls, v: Any) -> float:
        v = _finite_float(v, field_name="comparison standard deviation")
        if v < 0.0:
            raise ValueError("comparison standard deviation must be non-negative")
        return v

    @field_validator("tolerance_factor", mode="before")
    @classmethod
    def _finite_tolerance(cls, v: Any) -> float:
        v = _finite_float(v, field_name="comparison tolerance")
        if v <= 0.0:
            raise ValueError("comparison tolerance must be positive")
        return v

    @field_validator("deviation_factor", mode="before")
    @classmethod
    def _finite_deviation(cls, v: Any) -> float | None:
        if v is None:
            return None
        return _finite_float(v, field_name="comparison deviation")


# ---------------------------------------------------------------------------
# Loader and comparison utilities
# ---------------------------------------------------------------------------


class HistoricalDataLoader:
    """Load and diagnose legacy historical metadata for compatibility only."""

    def load(self, path: Path) -> HistoricalEngagement:
        """Load a single engagement definition from *path*."""
        with open(path, encoding="utf-8") as data_file:
            raw = load_yaml_unique(data_file)
        engagement = HistoricalEngagement.model_validate(raw)
        logger.info("Loaded engagement %r from %s", engagement.name, path)
        return engagement

    @staticmethod
    def compare_metric(
        simulated: float,
        historical: HistoricalMetric,
        simulated_std: float = 0.0,
    ) -> ComparisonResult:
        """Return a finite per-metric diagnostic for legacy metadata.

        The metric is considered within tolerance if::

            historical / tolerance <= simulated <= historical * tolerance

        For historical values of zero, the simulated value must also be
        within ``tolerance_factor`` of zero (i.e. <= tolerance_factor).
        """
        sim_val = _finite_float(simulated, field_name="simulated value")
        sim_std = _finite_float(simulated_std, field_name="simulated standard deviation")
        if sim_std < 0.0:
            raise ValueError("simulated standard deviation must be non-negative")
        hist_val = _finite_float(
            historical.value,
            field_name=f"historical value for {historical.name!r}",
        )
        tol = _finite_float(
            historical.tolerance_factor,
            field_name=f"historical tolerance for {historical.name!r}",
        )
        if tol <= 0.0:
            raise ValueError("historical tolerance must be positive")

        if hist_val == 0.0:
            # Special case: historical is zero
            deviation = abs(sim_val)
            within = deviation <= tol
            dev_factor = 0.0 if sim_val == 0.0 else None
        else:
            dev_factor = sim_val / hist_val
            lo = hist_val / tol
            hi = hist_val * tol
            if lo > hi:
                lo, hi = hi, lo  # handle negative historical values
            within = lo <= sim_val <= hi

        return ComparisonResult(
            metric_name=historical.name,
            historical_value=hist_val,
            simulated_mean=sim_val,
            simulated_std=sim_std,
            tolerance_factor=tol,
            within_tolerance=within,
            deviation_factor=dev_factor,
        )

    @staticmethod
    def compare_all(
        simulated: dict[str, float],
        historical: list[HistoricalMetric],
        simulated_stds: dict[str, float] | None = None,
    ) -> list[ComparisonResult]:
        """Return complete legacy diagnostics or reject ambiguous input.

        The historical list must be nonempty and duplicate-free.  Every
        historical metric must have a finite simulated value, and a supplied
        standard-deviation mapping must be complete and finite.
        """
        if not historical:
            raise ValueError("historical comparison requires at least one metric")
        _reject_duplicate_metric_names(historical)

        finite_simulated = {
            name: _finite_float(value, field_name=f"simulated value {name!r}") for name, value in simulated.items()
        }
        finite_stds: dict[str, float] | None = None
        if simulated_stds is not None:
            finite_stds = {}
            for name, value in simulated_stds.items():
                std = _finite_float(
                    value,
                    field_name=f"simulated standard deviation {name!r}",
                )
                if std < 0.0:
                    raise ValueError(
                        f"simulated standard deviation {name!r} must be non-negative",
                    )
                finite_stds[name] = std

        results: list[ComparisonResult] = []
        for metric in historical:
            if metric.name not in finite_simulated:
                raise ValueError(
                    f"missing simulated comparison input for metric {metric.name!r}",
                )
            if finite_stds is not None and metric.name not in finite_stds:
                raise ValueError(
                    f"missing simulated standard deviation for metric {metric.name!r}",
                )
            sim_std = 0.0 if finite_stds is None else finite_stds[metric.name]
            results.append(
                HistoricalDataLoader.compare_metric(
                    finite_simulated[metric.name],
                    metric,
                    sim_std,
                ),
            )
        return results

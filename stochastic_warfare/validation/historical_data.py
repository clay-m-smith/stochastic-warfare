"""Data structures for historical engagement references and comparison.

Provides pydantic models for loading scenario definitions from YAML,
and comparison utilities for evaluating simulation output against
documented historical outcomes.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any

import yaml
from stochastic_warfare.simulation.calibration import CalibrationSchema
from pydantic import BaseModel, field_validator

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


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
    """A single documented outcome from a historical engagement."""

    name: str
    value: float
    tolerance_factor: float = 2.0  # simulated must be within Nx of historical
    unit: str = ""
    source: str = ""
    source_quality: int = SourceQuality.SECONDARY
    notes: str = ""

    @field_validator("tolerance_factor")
    @classmethod
    def _positive_tolerance(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("tolerance_factor must be positive")
        return v

    @field_validator("source_quality")
    @classmethod
    def _valid_quality(cls, v: int) -> int:
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
    """Complete scenario definition loaded from YAML."""

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


# ---------------------------------------------------------------------------
# Comparison results
# ---------------------------------------------------------------------------


class ComparisonResult(BaseModel):
    """Result of comparing one simulated metric to its historical value."""

    metric_name: str
    historical_value: float
    simulated_mean: float
    simulated_std: float
    tolerance_factor: float
    within_tolerance: bool
    deviation_factor: float  # simulated_mean / historical_value


# ---------------------------------------------------------------------------
# Loader and comparison utilities
# ---------------------------------------------------------------------------


class HistoricalDataLoader:
    """Load historical engagement definitions from YAML files."""

    def load(self, path: Path) -> HistoricalEngagement:
        """Load a single engagement definition from *path*."""
        with open(path) as f:
            raw = yaml.safe_load(f)
        engagement = HistoricalEngagement.model_validate(raw)
        logger.info("Loaded engagement %r from %s", engagement.name, path)
        return engagement

    @staticmethod
    def compare_metric(
        simulated: float,
        historical: HistoricalMetric,
        simulated_std: float = 0.0,
    ) -> ComparisonResult:
        """Compare a single simulated value against a historical metric.

        The metric is considered within tolerance if::

            historical / tolerance <= simulated <= historical * tolerance

        For historical values of zero, the simulated value must also be
        within ``tolerance_factor`` of zero (i.e. <= tolerance_factor).
        """
        hist_val = historical.value
        tol = historical.tolerance_factor

        if hist_val == 0.0:
            # Special case: historical is zero
            deviation = abs(simulated)
            within = deviation <= tol
            dev_factor = float("inf") if hist_val == 0.0 and simulated != 0.0 else 0.0
        else:
            dev_factor = simulated / hist_val
            lo = hist_val / tol
            hi = hist_val * tol
            if lo > hi:
                lo, hi = hi, lo  # handle negative historical values
            within = lo <= simulated <= hi

        return ComparisonResult(
            metric_name=historical.name,
            historical_value=hist_val,
            simulated_mean=simulated,
            simulated_std=simulated_std,
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
        """Compare all historical metrics against simulated values.

        Metrics present in *historical* but missing from *simulated* are
        reported with ``simulated_mean=NaN`` and ``within_tolerance=False``.
        """
        stds = simulated_stds or {}
        results: list[ComparisonResult] = []
        for metric in historical:
            if metric.name in simulated:
                sim_val = simulated[metric.name]
                sim_std = stds.get(metric.name, 0.0)
                results.append(
                    HistoricalDataLoader.compare_metric(sim_val, metric, sim_std)
                )
            else:
                results.append(
                    ComparisonResult(
                        metric_name=metric.name,
                        historical_value=metric.value,
                        simulated_mean=float("nan"),
                        simulated_std=0.0,
                        tolerance_factor=metric.tolerance_factor,
                        within_tolerance=False,
                        deviation_factor=float("nan"),
                    )
                )
        return results

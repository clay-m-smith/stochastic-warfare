"""Neutral typed contracts shared by current and legacy validation code."""

from __future__ import annotations

import enum
import math
from typing import Any

from pydantic import BaseModel, field_validator


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


class SourceQuality(enum.IntEnum):
    """Confidence tier for historical data provenance."""

    PRIMARY = 0
    SECONDARY = 1
    TERTIARY = 2


class HistoricalMetric(BaseModel):
    """One documented outcome retained for diagnostic comparison."""

    name: str
    value: float
    tolerance_factor: float = 2.0
    unit: str = ""
    source: str = ""
    source_quality: int = SourceQuality.SECONDARY
    notes: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def _finite_value(cls, value: Any) -> float:
        return _finite_float(value, field_name="value")

    @field_validator("tolerance_factor", mode="before")
    @classmethod
    def _positive_tolerance(cls, value: Any) -> float:
        value = _finite_float(value, field_name="tolerance_factor")
        if value <= 0:
            raise ValueError("tolerance_factor must be positive")
        return value

    @field_validator("source_quality", mode="before")
    @classmethod
    def _valid_quality(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("source_quality must be 0, 1, or 2")
        if value not in (0, 1, 2):
            raise ValueError(
                f"source_quality must be 0, 1, or 2; got {value}",
            )
        return value

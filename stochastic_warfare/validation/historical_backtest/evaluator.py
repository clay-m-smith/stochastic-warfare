"""Exact joint-coverage evaluation for production historical backtests."""

from __future__ import annotations

import math
from typing import Any, Sequence

from pydantic import field_validator, model_validator
from scipy.stats import beta

from .common import StrictFrozenModel, require_trimmed


class JointCoverageEvaluation(StrictFrozenModel):
    """Complete exact-binomial verdict for one ordered joint outcome."""

    metric_in_range: tuple[tuple[str, tuple[bool, ...]], ...]
    joint_in_range: tuple[bool, ...]
    sample_size: int
    joint_successes: int
    confidence: float
    minimum_joint_coverage: float
    lower_confidence_bound: float
    passed: bool

    @field_validator("metric_in_range", mode="before")
    @classmethod
    def _metric_vectors(
        cls,
        value: Any,
    ) -> tuple[tuple[str, tuple[bool, ...]], ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("metric_in_range must be a nonempty ordered list")
        result: list[tuple[str, tuple[bool, ...]]] = []
        for entry in value:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise ValueError("metric_in_range entries must contain an ID and vector")
            metric_id = require_trimmed(entry[0], field_name="metric ID")
            if not isinstance(entry[1], (list, tuple)) or not entry[1]:
                raise ValueError("metric in-range vectors must be nonempty")
            vector = tuple(entry[1])
            if any(type(item) is not bool for item in vector):
                raise ValueError("metric in-range vectors require strict booleans")
            result.append((metric_id, vector))
        return tuple(result)

    @field_validator("joint_in_range", mode="before")
    @classmethod
    def _joint_vector(cls, value: Any) -> tuple[bool, ...]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("joint_in_range must be a nonempty ordered list")
        result = tuple(value)
        if any(type(item) is not bool for item in result):
            raise ValueError("joint_in_range requires strict booleans")
        return result

    @field_validator("sample_size", "joint_successes", mode="before")
    @classmethod
    def _counts(cls, value: Any, info: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{info.field_name} must be a non-negative strict integer")
        if info.field_name == "sample_size" and value == 0:
            raise ValueError("sample_size must be positive")
        return value

    @field_validator("lower_confidence_bound", mode="before")
    @classmethod
    def _bound(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("lower_confidence_bound must be finite")
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError("lower_confidence_bound must be within [0, 1]")
        return number

    @field_validator("passed", mode="before")
    @classmethod
    def _passed(cls, value: Any) -> bool:
        if type(value) is not bool:
            raise ValueError("passed must be a strict boolean")
        return value

    @field_validator("confidence", "minimum_joint_coverage", mode="before")
    @classmethod
    def _probability(cls, value: Any, info: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{info.field_name} must be a finite probability")
        number = float(value)
        if not math.isfinite(number) or not 0.0 < number < 1.0:
            raise ValueError(f"{info.field_name} must be strictly between zero and one")
        return number

    @model_validator(mode="after")
    def _internally_consistent(self) -> JointCoverageEvaluation:
        if self.joint_successes > self.sample_size:
            raise ValueError("joint_successes must not exceed sample_size")
        expected = evaluate_joint_coverage(
            metric_in_range=self.metric_in_range,
            confidence=self.confidence,
            minimum_joint_coverage=self.minimum_joint_coverage,
            _validate_model=False,
        )
        if (
            self.joint_in_range != expected.joint_in_range
            or self.sample_size != expected.sample_size
            or self.joint_successes != expected.joint_successes
            or self.lower_confidence_bound != expected.lower_confidence_bound
            or self.passed is not expected.passed
        ):
            raise ValueError("joint coverage evaluation is internally inconsistent")
        return self


def exact_binomial_lower_bound(
    successes: int,
    sample_size: int,
    *,
    confidence: float,
) -> float:
    """Return the exact one-sided Clopper-Pearson lower confidence bound."""
    if (
        isinstance(successes, bool)
        or not isinstance(successes, int)
        or isinstance(sample_size, bool)
        or not isinstance(sample_size, int)
        or sample_size <= 0
        or not 0 <= successes <= sample_size
    ):
        raise ValueError(
            "successes and sample_size must be strict integers with 0 <= successes <= sample_size",
        )
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0.0 < float(confidence) < 1.0
    ):
        raise ValueError("confidence must be a finite probability in (0, 1)")
    if successes == 0:
        return 0.0
    return float(
        beta.ppf(
            1.0 - float(confidence),
            successes,
            sample_size - successes + 1,
        ),
    )


def evaluate_joint_coverage(
    *,
    metric_in_range: Sequence[tuple[str, Sequence[bool]]],
    confidence: float,
    minimum_joint_coverage: float,
    _validate_model: bool = True,
) -> JointCoverageEvaluation:
    """Evaluate one joint success vector without marginal substitution."""
    for field_name, value in (
        ("confidence", confidence),
        ("minimum_joint_coverage", minimum_joint_coverage),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 < float(value) < 1.0
        ):
            raise ValueError(f"{field_name} must be a finite probability in (0, 1)")
    if not metric_in_range:
        raise ValueError("metric_in_range must contain at least one gating metric")
    normalized: list[tuple[str, tuple[bool, ...]]] = []
    for index, (metric_id, values) in enumerate(metric_in_range):
        name = require_trimmed(
            metric_id,
            field_name=f"metric_in_range[{index}].metric_id",
        )
        vector = tuple(values)
        if not vector or any(type(value) is not bool for value in vector):
            raise ValueError(
                f"metric_in_range[{index}] must contain nonempty strict booleans",
            )
        normalized.append((name, vector))
    names = [name for name, _ in normalized]
    if len(names) != len(set(names)):
        raise ValueError("metric_in_range metric IDs must be duplicate-free")
    sample_size = len(normalized[0][1])
    if any(len(values) != sample_size for _, values in normalized):
        raise ValueError("metric_in_range vectors must have equal length")
    joint = tuple(all(values[index] for _, values in normalized) for index in range(sample_size))
    successes = sum(joint)
    lower = exact_binomial_lower_bound(
        successes,
        sample_size,
        confidence=float(confidence),
    )
    payload = {
        "metric_in_range": tuple(normalized),
        "joint_in_range": joint,
        "sample_size": sample_size,
        "joint_successes": successes,
        "confidence": float(confidence),
        "minimum_joint_coverage": float(minimum_joint_coverage),
        "lower_confidence_bound": lower,
        "passed": lower >= float(minimum_joint_coverage),
    }
    if _validate_model:
        return JointCoverageEvaluation.model_validate(payload)
    return JointCoverageEvaluation.model_construct(**payload)

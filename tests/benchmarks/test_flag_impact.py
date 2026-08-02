"""Flag-impact measurement-plan validation.

The configurations remain available for explicit manual measurement, but no
single candidate/baseline timing pair makes a speed or interaction claim.
Each flag needs its own promoted version-4 paired reference before gating.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema
from tests.benchmarks.benchmark_suite import BenchmarkBaseline


_PERFORMANCE_FLAGS = (
    "enable_detection_culling",
    "enable_scan_scheduling",
    "enable_lod",
    "enable_soa",
    "enable_parallel_detection",
)
_BASE = {
    "enable_fog_of_war": True,
    **{flag: False for flag in _PERFORMANCE_FLAGS},
}


def flag_impact_measurement_plan() -> dict[str, dict[str, bool]]:
    """Return exact, deterministic measurement-only configurations."""
    plan = {
        "all_off": dict(_BASE),
        "all_on": {
            **_BASE,
            **{flag: True for flag in _PERFORMANCE_FLAGS},
        },
    }
    for flag in _PERFORMANCE_FLAGS:
        plan[f"only_{flag}"] = {
            **_BASE,
            flag: True,
        }
    return plan


@pytest.mark.benchmark
class TestFlagImpactMeasurementPlan:
    def test_every_flag_is_a_strict_calibration_field(self) -> None:
        assert set(_PERFORMANCE_FLAGS) <= set(CalibrationSchema.model_fields)
        for overrides in flag_impact_measurement_plan().values():
            CalibrationSchema.model_validate(overrides)

    def test_plan_is_complete_and_deterministic(self) -> None:
        plan = flag_impact_measurement_plan()
        assert list(plan) == [
            "all_off",
            "all_on",
            *[f"only_{flag}" for flag in _PERFORMANCE_FLAGS],
        ]
        assert plan["all_off"]["enable_fog_of_war"] is True
        assert all(plan["all_off"][flag] is False for flag in _PERFORMANCE_FLAGS)
        assert all(plan["all_on"][flag] is True for flag in _PERFORMANCE_FLAGS)

    def test_no_flag_configuration_has_a_promoted_gate(self) -> None:
        entries = BenchmarkBaseline().load()
        assert all(name not in entries for name in flag_impact_measurement_plan())

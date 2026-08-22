"""Supported exact-flag measurement-plan validation.

Detection culling, SoA, and parallel detection remain available for explicit
manual measurement. Scan scheduling and LOD failed the retained semantic
evaluation and therefore have no production benchmark configuration.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from stochastic_warfare.simulation.calibration import CalibrationSchema
from tests.benchmarks.benchmark_suite import BenchmarkBaseline


_SUPPORTED_PERFORMANCE_FLAGS = (
    "enable_detection_culling",
    "enable_soa",
    "enable_parallel_detection",
)
_RETIRED_MODEL_CONTROLS = (
    "enable_scan_scheduling",
    "enable_lod",
)
_BASE = {
    "enable_fog_of_war": True,
    **{
        flag: False
        for flag in (
            *_SUPPORTED_PERFORMANCE_FLAGS,
            *_RETIRED_MODEL_CONTROLS,
        )
    },
}


def flag_impact_measurement_plan() -> dict[str, dict[str, bool]]:
    """Return exact, deterministic measurement-only configurations."""
    plan = {
        "all_off": dict(_BASE),
        "all_on": {
            **_BASE,
            **{flag: True for flag in _SUPPORTED_PERFORMANCE_FLAGS},
        },
    }
    for flag in _SUPPORTED_PERFORMANCE_FLAGS:
        plan[f"only_{flag}"] = {
            **_BASE,
            flag: True,
        }
    return plan


@pytest.mark.benchmark
class TestFlagImpactMeasurementPlan:
    def test_every_flag_is_a_strict_calibration_field(self) -> None:
        assert set(_SUPPORTED_PERFORMANCE_FLAGS) <= set(
            CalibrationSchema.model_fields,
        )
        for overrides in flag_impact_measurement_plan().values():
            CalibrationSchema.model_validate(overrides)

    @pytest.mark.parametrize("flag", _RETIRED_MODEL_CONTROLS)
    def test_retired_model_control_has_no_measurement_configuration(
        self,
        flag: str,
    ) -> None:
        with pytest.raises(ValidationError, match=flag):
            CalibrationSchema.model_validate({flag: True})
        assert f"only_{flag}" not in flag_impact_measurement_plan()

    def test_plan_is_complete_and_deterministic(self) -> None:
        plan = flag_impact_measurement_plan()
        assert list(plan) == [
            "all_off",
            "all_on",
            *[f"only_{flag}" for flag in _SUPPORTED_PERFORMANCE_FLAGS],
        ]
        assert plan["all_off"]["enable_fog_of_war"] is True
        assert all(plan["all_off"][flag] is False for flag in _SUPPORTED_PERFORMANCE_FLAGS)
        assert all(plan["all_on"][flag] is True for flag in _SUPPORTED_PERFORMANCE_FLAGS)
        assert all(plan["all_on"][flag] is False for flag in _RETIRED_MODEL_CONTROLS)

    def test_no_flag_configuration_has_a_promoted_gate(self) -> None:
        entries = BenchmarkBaseline().load()
        assert all(name not in entries for name in flag_impact_measurement_plan())

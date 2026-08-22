"""Current Block 9 performance-configuration declaration checks.

This module verifies only the typed configuration and catalog declaration
boundary. Detection culling, SoA, and parallel detection retain supported
production evidence. Scan scheduling and LOD are explicit false-only retired
inputs after the terminal Phase 118 semantic failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from stochastic_warfare.simulation.calibration import CalibrationSchema
from tests.validation.test_historical_accuracy import EVALUATOR_EXCLUSIONS

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

SUPPORTED_EXECUTION_FLAGS = {
    "enable_detection_culling",
    "enable_soa",
    "enable_parallel_detection",
}
RETIRED_MODEL_CONTROLS = {
    "enable_scan_scheduling",
    "enable_lod",
}
PERFORMANCE_FLAGS = SUPPORTED_EXECUTION_FLAGS | RETIRED_MODEL_CONTROLS
SUPPORTED_FLAG_SCENARIOS = {
    "benchmark_battalion",
    "benchmark_brigade",
}


def _catalog_declarations() -> dict[str, set[str]]:
    declarations = {flag: set() for flag in PERFORMANCE_FLAGS}
    for path in sorted(DATA_DIR.rglob("scenario.yaml")):
        if path.parent.name.startswith("test_campaign"):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        overrides = data.get("calibration_overrides") or {}
        for flag in PERFORMANCE_FLAGS:
            if overrides.get(flag) is True:
                declarations[flag].add(path.parent.name)
    return declarations


class TestPerformanceFlagSchema:
    """Supported flags stay typed while retired controls are false-only."""

    @pytest.mark.parametrize(
        ("flag", "default"),
        (
            ("enable_detection_culling", True),
            ("enable_parallel_detection", False),
            ("enable_soa", False),
        ),
    )
    def test_supported_flag_accepts_explicit_true(
        self,
        flag: str,
        default: bool,
    ) -> None:
        field = CalibrationSchema.model_fields[flag]
        assert field.annotation is bool
        assert field.default is default
        assert getattr(CalibrationSchema.model_validate({flag: True}), flag)

    @pytest.mark.parametrize("flag", sorted(RETIRED_MODEL_CONTROLS))
    def test_retired_flag_accepts_false_and_rejects_true(
        self,
        flag: str,
    ) -> None:
        field = CalibrationSchema.model_fields[flag]
        assert field.annotation is bool
        assert field.default is False
        assert (
            getattr(
                CalibrationSchema.model_validate({flag: False}),
                flag,
            )
            is False
        )
        with pytest.raises(ValidationError, match=flag):
            CalibrationSchema.model_validate({flag: True})

    @pytest.mark.parametrize("flag", sorted(PERFORMANCE_FLAGS))
    def test_invalid_boolean_value_is_rejected(self, flag: str) -> None:
        with pytest.raises(ValidationError):
            CalibrationSchema.model_validate({flag: "not-a-boolean"})


class TestPerformanceFlagCatalogDeclarations:
    """Catalog activation follows the supported/retired disposition."""

    def test_supported_flags_are_authored_only_by_benchmark_scenarios(
        self,
    ) -> None:
        declarations = _catalog_declarations()
        assert {flag: declarations[flag] for flag in SUPPORTED_EXECUTION_FLAGS} == {
            flag: SUPPORTED_FLAG_SCENARIOS for flag in SUPPORTED_EXECUTION_FLAGS
        }

    def test_all_supported_flag_scenarios_are_evaluator_exclusions(
        self,
    ) -> None:
        declarations = _catalog_declarations()
        all_supported = set.intersection(
            *(declarations[flag] for flag in SUPPORTED_EXECUTION_FLAGS),
        )
        assert all_supported == SUPPORTED_FLAG_SCENARIOS
        assert all_supported == EVALUATOR_EXCLUSIONS

    @pytest.mark.parametrize("flag", sorted(RETIRED_MODEL_CONTROLS))
    def test_retired_model_control_has_no_catalog_activation(
        self,
        flag: str,
    ) -> None:
        declarations = _catalog_declarations()

        assert declarations[flag] == set()

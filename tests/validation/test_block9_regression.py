"""Phase 91 performance-flag declaration checks.

This module verifies only the typed configuration and catalog declaration
boundary for the four opt-in Block 9 flags.  It does not claim that enabling a
flag is outcome-neutral, historically accurate, deterministic, or manually
benchmark-validated.  Those semantic and performance obligations require
controlled enabled/disabled production runs.

The former tests reran the full evaluator while assuming its ordinary scenarios
had all four flags enabled.  In fact, only the two benchmark scenarios author
all four flags, and the evaluator intentionally excludes both.  Repeating that
run could therefore prove none of the claimed flag effects.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from stochastic_warfare.simulation.calibration import CalibrationSchema
from tests.validation.test_historical_accuracy import EVALUATOR_EXCLUSIONS

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

PERFORMANCE_FLAGS = {
    "enable_scan_scheduling",
    "enable_lod",
    "enable_soa",
    "enable_parallel_detection",
}
ALL_FLAG_SCENARIOS = {
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
    """The four opt-in declarations are typed, disabled-by-default inputs."""

    @pytest.mark.parametrize("flag", sorted(PERFORMANCE_FLAGS))
    def test_flag_is_declared_as_boolean(self, flag: str) -> None:
        field = CalibrationSchema.model_fields[flag]
        assert field.annotation is bool
        assert field.default is False

    @pytest.mark.parametrize("flag", sorted(PERFORMANCE_FLAGS))
    def test_invalid_boolean_value_is_rejected(self, flag: str) -> None:
        with pytest.raises(ValidationError):
            CalibrationSchema.model_validate({flag: "not-a-boolean"})


class TestPerformanceFlagCatalogDeclarations:
    """Catalog declaration inventory, without a behavior-equivalence claim."""

    def test_each_flag_is_authored_only_by_benchmark_scenarios(self) -> None:
        declarations = _catalog_declarations()
        assert declarations == {
            flag: ALL_FLAG_SCENARIOS
            for flag in PERFORMANCE_FLAGS
        }

    def test_all_flag_scenarios_are_exactly_evaluator_exclusions(self) -> None:
        declarations = _catalog_declarations()
        all_four = set.intersection(*declarations.values())
        assert all_four == ALL_FLAG_SCENARIOS
        assert all_four == EVALUATOR_EXCLUSIONS

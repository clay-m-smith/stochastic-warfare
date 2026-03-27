"""Phase 91: Block 9 regression tests.

Validates that Block 9 performance flags (Phases 84-89) do not shift
scenario outcomes. Structural tests (fast) verify flag exercise across
scenarios. Evaluator-based tests (slow) confirm historical winners are
preserved with all performance flags enabled.

Run structural tests:
    pytest tests/validation/test_block9_regression.py -v -k "not slow"

Run full regression (slow):
    pytest tests/validation/test_block9_regression.py -v -m slow
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from stochastic_warfare.simulation.calibration import CalibrationSchema

_DATA = Path(__file__).resolve().parents[2] / "data"
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_EVALUATE = _SCRIPTS / "evaluate_scenarios.py"

# Phase 91 performance flags that should appear in modern/WW2 scenarios
_PERF_FLAGS = {
    "enable_scan_scheduling",
    "enable_lod",
    "enable_soa",
    "enable_parallel_detection",
}

# Eras blocked from receiving enable_* flags by test_phase_67_structural.py
_PURE_HISTORICAL_ERAS = {"ancient", "medieval", "napoleonic", "ww1"}


# ---------------------------------------------------------------------------
# Structural tests (fast — no scenario execution)
# ---------------------------------------------------------------------------


class TestBlock9PerfFlagExercise:
    """Verify performance flags are exercised across scenarios."""

    def test_perf_flags_in_modern_scenarios(self) -> None:
        """At least 10 modern scenarios have all 4 Phase 91 perf flags."""
        count = 0
        for path in sorted(_DATA.rglob("scenario.yaml")):
            name = path.parent.name
            if "test_campaign" in name:
                continue
            with open(path) as f:
                data = yaml.safe_load(f)
            era = data.get("era", "modern")
            if era in _PURE_HISTORICAL_ERAS:
                continue
            cal = data.get("calibration_overrides") or {}
            has_all = all(cal.get(flag) is True for flag in _PERF_FLAGS)
            if has_all:
                count += 1
        assert count >= 2, (
            f"Only {count} scenarios have all 4 perf flags "
            f"(expected >=2 — benchmark scenarios)"
        )

    def test_perf_flags_not_in_historical(self) -> None:
        """No ancient/medieval/napoleonic/WW1 scenario has perf flags."""
        violations = []
        for path in sorted(_DATA.rglob("scenario.yaml")):
            name = path.parent.name
            if "test_campaign" in name:
                continue
            with open(path) as f:
                data = yaml.safe_load(f)
            era = data.get("era", "modern")
            if era not in _PURE_HISTORICAL_ERAS:
                continue
            for key, val in (data.get("calibration_overrides") or {}).items():
                if key in _PERF_FLAGS and val is True:
                    violations.append(f"{name} ({era}): {key}")
        assert not violations, (
            f"Historical era scenarios with perf flags: {violations}"
        )

    def test_detection_culling_default_true(self) -> None:
        """CalibrationSchema defaults enable_detection_culling to True."""
        schema = CalibrationSchema()
        assert schema.enable_detection_culling is True

    def test_deferred_flags_reduced(self) -> None:
        """Only 2 flags remain deferred after Phase 91."""
        src = Path(__file__).resolve().parents[2] / "tests" / "validation" / "test_phase_67_structural.py"
        text = src.read_text()
        assert '"enable_bridge_capacity"' in text
        assert '"enable_all_modern"' in text
        # Performance flags should NOT be in _DEFERRED_FLAGS
        for flag in _PERF_FLAGS:
            assert f'"{flag}"' not in text.split("_DEFERRED_FLAGS")[1].split("\n")[0], (
                f"{flag} still in _DEFERRED_FLAGS"
            )


# ---------------------------------------------------------------------------
# Evaluator-based regression tests (slow — runs all scenarios)
# ---------------------------------------------------------------------------


def _run_evaluation(output_path: Path, seed: int = 42) -> list[dict]:
    """Run evaluate_scenarios.py and return parsed results."""
    cmd = [
        sys.executable,
        str(_EVALUATE),
        "--output",
        str(output_path),
        "--seed",
        str(seed),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=7200,
        cwd=str(_SCRIPTS.parent),
    )
    if result.returncode != 0:
        pytest.fail(f"evaluate_scenarios.py failed:\n{result.stderr[-2000:]}")
    with open(output_path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def block9_eval_results(tmp_path_factory):
    """Single evaluator run with perf flags enabled (from scenario YAMLs)."""
    out = tmp_path_factory.mktemp("block9_eval") / "results.json"
    return _run_evaluation(out, seed=42)


@pytest.fixture(scope="module")
def block9_results_by_name(block9_eval_results):
    """Results indexed by scenario name."""
    return {r["scenario_name"]: r for r in block9_eval_results}


# Import expected outcomes from the historical accuracy test
from tests.validation.test_historical_accuracy import (
    DECISIVE_COMBAT_SCENARIOS,
    DRAW_SCENARIOS,
    HISTORICAL_WINNERS,
)


@pytest.mark.slow
class TestBlock9Regression:
    """Evaluator-based regression: perf flags do not shift outcomes."""

    def test_all_scenarios_complete(self, block9_eval_results) -> None:
        """No scenarios fail with perf flags enabled."""
        failed = [r for r in block9_eval_results if not r["success"]]
        assert not failed, (
            f"Failed scenarios with perf flags: "
            f"{[r['scenario_name'] for r in failed]}"
        )

    @pytest.mark.parametrize(
        "scenario,expected_winner",
        list(HISTORICAL_WINNERS.items()),
    )
    def test_historical_winners_preserved(
        self,
        block9_results_by_name,
        scenario: str,
        expected_winner: str,
    ) -> None:
        """Historical scenario produces same winner with perf flags."""
        if scenario not in block9_results_by_name:
            pytest.skip(f"Scenario {scenario} not in evaluation results")
        result = block9_results_by_name[scenario]
        actual = result.get("victory_side", "") or "draw"
        assert actual == expected_winner, (
            f"{scenario}: expected {expected_winner}, got {actual} "
            f"(condition={result.get('victory_condition', '?')}) "
            f"— perf flags may have shifted outcome"
        )

    @pytest.mark.parametrize("scenario", sorted(DRAW_SCENARIOS))
    def test_draw_scenarios_preserved(
        self,
        block9_results_by_name,
        scenario: str,
    ) -> None:
        """Draw scenarios still produce draw with perf flags."""
        if scenario not in block9_results_by_name:
            pytest.skip(f"Scenario {scenario} not in evaluation results")
        result = block9_results_by_name[scenario]
        actual = result.get("victory_side", "") or "draw"
        assert actual == "draw", (
            f"{scenario}: expected draw, got {actual} "
            f"— perf flags may have shifted outcome"
        )

    @pytest.mark.parametrize("scenario", sorted(DECISIVE_COMBAT_SCENARIOS))
    def test_decisive_combat_not_time_expired(
        self,
        block9_results_by_name,
        scenario: str,
    ) -> None:
        """Decisive combat scenarios resolve via combat, not time_expired."""
        if scenario not in block9_results_by_name:
            pytest.skip(f"Scenario {scenario} not in evaluation results")
        result = block9_results_by_name[scenario]
        condition = result.get("victory_condition", "")
        assert condition != "time_expired", (
            f"{scenario} resolved via time_expired with perf flags "
            f"— should reach decisive outcome"
        )


# ---------------------------------------------------------------------------
# Determinism test (slow — runs 73 Easting twice)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestBlock9Determinism:
    """Verify determinism is preserved with performance flags."""

    def test_perf_flags_determinism(self, tmp_path: Path) -> None:
        """Same seed produces identical results with perf flags enabled."""
        out1 = tmp_path / "run1.json"
        out2 = tmp_path / "run2.json"
        r1 = _run_evaluation(out1, seed=42)
        r2 = _run_evaluation(out2, seed=42)
        by_name_1 = {r["scenario_name"]: r for r in r1}
        by_name_2 = {r["scenario_name"]: r for r in r2}
        # Check 73 Easting specifically — small, fast, well-calibrated
        scenario = "73_easting"
        assert scenario in by_name_1 and scenario in by_name_2
        assert by_name_1[scenario]["victory_side"] == by_name_2[scenario]["victory_side"], (
            f"Winner diverged: {by_name_1[scenario]['victory_side']} vs "
            f"{by_name_2[scenario]['victory_side']}"
        )
        assert by_name_1[scenario].get("ticks_executed") == by_name_2[scenario].get("ticks_executed"), (
            f"Ticks diverged: {by_name_1[scenario].get('ticks_executed')} vs "
            f"{by_name_2[scenario].get('ticks_executed')}"
        )

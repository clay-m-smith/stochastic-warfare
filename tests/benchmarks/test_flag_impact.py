"""Phase 90: Optimization flag impact matrix.

Measures the individual and combined impact of Block 9 performance flags
on the Golan Heights scenario (290 units). All tests use ``enable_fog_of_war=True``
so that detection optimizations are exercised.

All tests marked ``@pytest.mark.benchmark`` + ``@pytest.mark.slow`` — excluded
from default runs. Run with:

    pytest tests/benchmarks/test_flag_impact.py --override-ini="addopts=" -v
"""

from __future__ import annotations

import pytest

from tests.benchmarks.benchmark_suite import SCENARIOS_DIR, run_benchmark

_GOLAN = SCENARIOS_DIR / "golan_heights" / "scenario.yaml"

# Phase 84-89 performance flags
_PERF_FLAGS = [
    "enable_detection_culling",
    "enable_scan_scheduling",
    "enable_lod",
    "enable_soa",
    "enable_parallel_detection",
]

_ALL_OFF: dict[str, object] = {f: False for f in _PERF_FLAGS}
_ALL_ON: dict[str, object] = {f: True for f in _PERF_FLAGS}

# FOW must be on for detection optimizations to activate
_BASE_OVERRIDES: dict[str, object] = {"enable_fog_of_war": True}


def _run_golan(overrides: dict[str, object]) -> float:
    """Run Golan Heights with calibration overrides, return wall_clock_s."""
    merged = {**_BASE_OVERRIDES, **overrides}
    result = run_benchmark(_GOLAN, seed=42, profile=False, calibration_overrides=merged)
    return result.wall_clock_s


@pytest.mark.benchmark
@pytest.mark.slow
class TestFlagImpact:
    """Measure individual and combined impact of performance flags."""

    def test_baseline_measurement(self) -> None:
        """Golan Heights with all perf flags OFF + FOW on — establishes baseline."""
        elapsed = _run_golan(_ALL_OFF)
        # No assertion — this is a measurement. Print for developer reference.
        print(f"\n  Baseline (all perf flags OFF): {elapsed:.1f}s")

    @pytest.mark.parametrize("flag_name", _PERF_FLAGS)
    def test_individual_flag_not_slower(self, flag_name: str) -> None:
        """Each individual flag should not make things significantly slower."""
        overrides = {**_ALL_OFF, flag_name: True}
        elapsed = _run_golan(overrides)
        # Run baseline for comparison
        baseline = _run_golan(_ALL_OFF)
        # Allow up to 15% slower (noise margin on consumer hardware)
        assert elapsed < baseline * 1.15, (
            f"{flag_name} made things slower: {elapsed:.1f}s vs "
            f"baseline {baseline:.1f}s (+{((elapsed / baseline) - 1) * 100:.0f}%)"
        )

    def test_all_flags_combined(self) -> None:
        """All flags combined should be faster than no-flags baseline."""
        baseline = _run_golan(_ALL_OFF)
        combined = _run_golan(_ALL_ON)
        print(
            f"\n  Baseline: {baseline:.1f}s | Combined: {combined:.1f}s | "
            f"Speedup: {baseline / combined:.2f}x"
        )
        # Combined should be at least 10% faster than baseline
        assert combined < baseline * 0.90, (
            f"Combined flags not faster: {combined:.1f}s vs "
            f"baseline {baseline:.1f}s (expected <{baseline * 0.90:.1f}s)"
        )

    def test_no_negative_interaction(self) -> None:
        """Combined flags should not be slower than the best individual flag."""
        combined = _run_golan(_ALL_ON)
        # Find best individual
        best_individual = float("inf")
        best_flag = ""
        for flag in _PERF_FLAGS:
            overrides = {**_ALL_OFF, flag: True}
            elapsed = _run_golan(overrides)
            if elapsed < best_individual:
                best_individual = elapsed
                best_flag = flag
        print(
            f"\n  Best individual: {best_flag} ({best_individual:.1f}s) | "
            f"Combined: {combined:.1f}s"
        )
        # Combined should be at least as fast as the best individual (with 10% noise margin)
        assert combined < best_individual * 1.10, (
            f"Combined ({combined:.1f}s) slower than best individual "
            f"{best_flag} ({best_individual:.1f}s)"
        )

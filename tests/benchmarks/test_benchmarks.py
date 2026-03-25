"""Phase 83: Benchmark tests with baseline regression detection.

All tests marked ``@pytest.mark.benchmark`` — excluded from default runs.
Run with: ``pytest tests/benchmarks/test_benchmarks.py --override-ini="addopts=" -v``
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.benchmarks.benchmark_suite import (
    BaselineEntry,
    BenchmarkBaseline,
    BenchmarkResult,
    SCENARIOS_DIR,
    run_benchmark,
)


# ---------------------------------------------------------------------------
# 73 Easting benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
class TestBenchmark73Easting:
    """73 Easting scenario benchmarks."""

    def test_wall_clock(self) -> None:
        """73 Easting completes in <30s."""
        result = run_benchmark(SCENARIOS_DIR / "73_easting" / "scenario.yaml", profile=False)
        assert result.wall_clock_s < 30.0, (
            f"73 Easting took {result.wall_clock_s:.1f}s (limit: 30s)"
        )

    def test_regression(self) -> None:
        """73 Easting does not regress >20% vs baseline."""
        result = run_benchmark(SCENARIOS_DIR / "73_easting" / "scenario.yaml", profile=False)
        baseline = BenchmarkBaseline()
        is_regression, msg = baseline.check_regression("73_easting", result)
        assert not is_regression, msg

    def test_determinism(self) -> None:
        """Same seed produces same winner and ticks."""
        r1 = run_benchmark(SCENARIOS_DIR / "73_easting" / "scenario.yaml", seed=42, profile=False)
        r2 = run_benchmark(SCENARIOS_DIR / "73_easting" / "scenario.yaml", seed=42, profile=False)
        assert r1.winner == r2.winner, f"Winner diverged: {r1.winner} vs {r2.winner}"
        assert r1.ticks_executed == r2.ticks_executed, (
            f"Ticks diverged: {r1.ticks_executed} vs {r2.ticks_executed}"
        )


# ---------------------------------------------------------------------------
# Golan Heights benchmarks (slow — manual CI only)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
class TestBenchmarkGolanHeights:
    """Golan Heights scenario benchmarks (slow)."""

    def test_wall_clock(self) -> None:
        """Golan Heights completes in <120s."""
        result = run_benchmark(SCENARIOS_DIR / "golan_heights" / "scenario.yaml", profile=False)
        assert result.wall_clock_s < 120.0, (
            f"Golan Heights took {result.wall_clock_s:.1f}s (limit: 120s)"
        )

    def test_regression(self) -> None:
        """Golan Heights does not regress >20% vs baseline."""
        result = run_benchmark(SCENARIOS_DIR / "golan_heights" / "scenario.yaml", profile=False)
        baseline = BenchmarkBaseline()
        is_regression, msg = baseline.check_regression("golan_heights", result)
        assert not is_regression, msg


# ---------------------------------------------------------------------------
# Infrastructure tests (fast — no scenario runs)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
class TestBenchmarkInfra:
    """Benchmark infrastructure tests — no scenario execution needed."""

    def test_result_fields(self) -> None:
        """BenchmarkResult has all expected fields."""
        result = BenchmarkResult(
            scenario_name="test",
            unit_count=10,
            wall_clock_s=1.5,
            ticks_executed=100,
            ticks_per_second=66.7,
            peak_memory_mb=50.0,
            hotspots=[("func:1(test)", 0.5, 100)],
            seed=42,
            winner="blue",
            commit="abc1234",
        )
        assert result.scenario_name == "test"
        assert result.unit_count == 10
        assert result.wall_clock_s == 1.5
        assert result.ticks_executed == 100
        assert result.ticks_per_second == 66.7
        assert result.peak_memory_mb == 50.0
        assert len(result.hotspots) == 1
        assert result.seed == 42
        assert result.winner == "blue"
        assert result.commit == "abc1234"

    def test_baseline_roundtrip(self, tmp_path: Path) -> None:
        """Baselines can be saved and loaded via a temp file."""
        path = tmp_path / "baselines.json"
        bl = BenchmarkBaseline(path)

        entries = {
            "test_scenario": BaselineEntry(
                wall_clock_s=5.0,
                ticks_executed=200,
                peak_memory_mb=30.0,
                commit="abc1234",
                timestamp="2026-03-24T00:00:00Z",
            ),
        }
        bl.save(entries)
        loaded = bl.load()

        assert "test_scenario" in loaded
        entry = loaded["test_scenario"]
        assert entry.wall_clock_s == 5.0
        assert entry.ticks_executed == 200
        assert entry.peak_memory_mb == 30.0
        assert entry.commit == "abc1234"

    def test_regression_detection(self, tmp_path: Path) -> None:
        """Regression detected when >20% slower, passes when within margin."""
        path = tmp_path / "baselines.json"
        bl = BenchmarkBaseline(path)

        # Set baseline at 10s
        bl.save({
            "test": BaselineEntry(
                wall_clock_s=10.0,
                ticks_executed=100,
                peak_memory_mb=50.0,
                commit="base",
                timestamp="2026-03-24T00:00:00Z",
            ),
        })

        # 25% slower — should trigger regression
        slow_result = BenchmarkResult(
            scenario_name="test",
            unit_count=10,
            wall_clock_s=12.5,
            ticks_executed=100,
            ticks_per_second=8.0,
            peak_memory_mb=50.0,
            seed=42,
            commit="slow",
        )
        is_reg, msg = bl.check_regression("test", slow_result)
        assert is_reg, f"Expected regression, got: {msg}"
        assert "REGRESSION" in msg

        # 10% slower — should pass (within 20% margin)
        ok_result = BenchmarkResult(
            scenario_name="test",
            unit_count=10,
            wall_clock_s=11.0,
            ticks_executed=100,
            ticks_per_second=9.1,
            peak_memory_mb=50.0,
            seed=42,
            commit="ok",
        )
        is_reg, msg = bl.check_regression("test", ok_result)
        assert not is_reg, f"Unexpected regression: {msg}"
        assert "OK" in msg

    def test_baselines_json_valid(self) -> None:
        """Checked-in baselines.json parses and contains both scenarios."""
        path = Path(__file__).parent / "baselines.json"
        assert path.exists(), f"baselines.json not found at {path}"
        with open(path) as f:
            data = json.load(f)
        assert "73_easting" in data, "Missing 73_easting baseline"
        assert "golan_heights" in data, "Missing golan_heights baseline"
        for scenario in ("73_easting", "golan_heights"):
            entry = data[scenario]
            assert "wall_clock_s" in entry
            assert "ticks_executed" in entry
            assert "peak_memory_mb" in entry

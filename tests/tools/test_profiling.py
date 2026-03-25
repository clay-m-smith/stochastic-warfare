"""Phase 83: Tests for profiling tooling."""

from __future__ import annotations

from unittest.mock import patch

from tests.benchmarks.benchmark_suite import BenchmarkResult
from stochastic_warfare.tools.profiling import (
    compare_profiles,
    generate_hotspot_report,
    save_flame_graph,
)


def _make_result(
    scenario_name: str = "test_scenario",
    wall_clock_s: float = 10.0,
    ticks_executed: int = 500,
    ticks_per_second: float = 50.0,
    peak_memory_mb: float = 100.0,
    unit_count: int = 20,
    hotspots: list | None = None,
    **kwargs,
) -> BenchmarkResult:
    """Build a synthetic BenchmarkResult for testing."""
    if hotspots is None:
        hotspots = [
            ("engine.py:100(run)", 5.0, 1),
            ("battle.py:200(tick)", 3.0, 500),
            ("detection.py:50(scan)", 1.5, 10000),
        ]
    return BenchmarkResult(
        scenario_name=scenario_name,
        unit_count=unit_count,
        wall_clock_s=wall_clock_s,
        ticks_executed=ticks_executed,
        ticks_per_second=ticks_per_second,
        peak_memory_mb=peak_memory_mb,
        hotspots=hotspots,
        seed=kwargs.get("seed", 42),
        winner=kwargs.get("winner", "blue"),
        commit=kwargs.get("commit", "abc1234"),
    )


class TestHotspotReport:
    """Tests for generate_hotspot_report."""

    def test_report_contains_scenario_name(self) -> None:
        result = _make_result(scenario_name="73_easting")
        report = generate_hotspot_report(result)
        assert "73_easting" in report

    def test_report_contains_table(self) -> None:
        result = _make_result()
        report = generate_hotspot_report(result)
        assert "Rank" in report
        assert "Cumulative" in report
        assert "engine.py:100(run)" in report

    def test_report_without_hotspots(self) -> None:
        result = _make_result(hotspots=[])
        report = generate_hotspot_report(result)
        assert "No hotspot data" in report


class TestCompareProfiles:
    """Tests for compare_profiles."""

    def test_delta_and_indicators(self) -> None:
        before = _make_result(wall_clock_s=10.0, ticks_per_second=50.0)
        after = _make_result(wall_clock_s=8.0, ticks_per_second=62.5)
        report = compare_profiles(before, after)
        assert "FASTER" in report
        assert "Wall clock" in report

    def test_slower_indicator(self) -> None:
        before = _make_result(wall_clock_s=10.0, ticks_per_second=50.0)
        after = _make_result(wall_clock_s=15.0, ticks_per_second=33.3)
        report = compare_profiles(before, after)
        assert "SLOWER" in report


class TestFlameGraph:
    """Tests for save_flame_graph."""

    def test_returns_none_without_pyspy(self, tmp_path) -> None:
        with patch("shutil.which", return_value=None):
            from pathlib import Path

            result = save_flame_graph(
                Path("fake/scenario.yaml"),
                tmp_path / "flame.svg",
            )
            assert result is None

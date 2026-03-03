"""Tests for stochastic_warfare.validation.historical_data."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

import pytest

from stochastic_warfare.validation.historical_data import (
    ComparisonResult,
    ForceDefinition,
    HistoricalDataLoader,
    HistoricalEngagement,
    HistoricalMetric,
    SourceQuality,
    TerrainSpec,
)


# ── SourceQuality ────────────────────────────────────────────────────


class TestSourceQuality:
    def test_enum_values(self) -> None:
        assert SourceQuality.PRIMARY == 0
        assert SourceQuality.SECONDARY == 1
        assert SourceQuality.TERTIARY == 2

    def test_ordering(self) -> None:
        assert SourceQuality.PRIMARY < SourceQuality.SECONDARY
        assert SourceQuality.SECONDARY < SourceQuality.TERTIARY


# ── HistoricalMetric ─────────────────────────────────────────────────


class TestHistoricalMetric:
    def test_minimal_construction(self) -> None:
        m = HistoricalMetric(name="exchange_ratio", value=28.0)
        assert m.name == "exchange_ratio"
        assert m.value == 28.0
        assert m.tolerance_factor == 2.0
        assert m.unit == ""
        assert m.source_quality == SourceQuality.SECONDARY

    def test_full_construction(self) -> None:
        m = HistoricalMetric(
            name="blue_kia",
            value=0.0,
            tolerance_factor=3.0,
            unit="personnel",
            source="73 Easting AAR",
            source_quality=SourceQuality.PRIMARY,
            notes="Eagle Troop only",
        )
        assert m.source_quality == 0
        assert m.notes == "Eagle Troop only"

    def test_negative_tolerance_rejected(self) -> None:
        with pytest.raises(Exception):
            HistoricalMetric(name="x", value=1.0, tolerance_factor=-1.0)

    def test_zero_tolerance_rejected(self) -> None:
        with pytest.raises(Exception):
            HistoricalMetric(name="x", value=1.0, tolerance_factor=0.0)

    def test_invalid_source_quality(self) -> None:
        with pytest.raises(Exception):
            HistoricalMetric(name="x", value=1.0, source_quality=5)


# ── ForceDefinition ──────────────────────────────────────────────────


class TestForceDefinition:
    def test_construction(self) -> None:
        fd = ForceDefinition(
            side="blue",
            units=[{"unit_type": "m1a1", "count": 9}],
            personnel_total=120,
            experience_level=0.8,
        )
        assert fd.side == "blue"
        assert fd.morale_initial == "STEADY"

    def test_experience_out_of_range(self) -> None:
        with pytest.raises(Exception):
            ForceDefinition(
                side="red", units=[], personnel_total=100, experience_level=1.5
            )

    def test_negative_experience(self) -> None:
        with pytest.raises(Exception):
            ForceDefinition(
                side="red", units=[], personnel_total=100, experience_level=-0.1
            )


# ── TerrainSpec ──────────────────────────────────────────────────────


class TestTerrainSpec:
    def test_defaults(self) -> None:
        ts = TerrainSpec(width_m=4000, height_m=6000)
        assert ts.cell_size_m == 100.0
        assert ts.base_elevation_m == 0.0
        assert ts.terrain_type == "flat_desert"
        assert ts.features == []

    def test_hilly_defense(self) -> None:
        ts = TerrainSpec(
            width_m=10000,
            height_m=15000,
            terrain_type="hilly_defense",
            base_elevation_m=900.0,
            features=[{"type": "ridge", "position": [5000, 7500]}],
        )
        assert ts.terrain_type == "hilly_defense"
        assert len(ts.features) == 1

    def test_unknown_terrain_type(self) -> None:
        with pytest.raises(Exception):
            TerrainSpec(width_m=1000, height_m=1000, terrain_type="jungle_swamp")


# ── HistoricalEngagement ─────────────────────────────────────────────


def _minimal_engagement_dict() -> dict:
    """Smallest valid engagement definition."""
    return {
        "name": "Test Battle",
        "date": "2024-01-01",
        "duration_hours": 1.0,
        "tick_duration_seconds": 5.0,
        "latitude": 30.0,
        "longitude": 47.0,
        "weather_conditions": {"visibility_m": 400},
        "blue_forces": {
            "side": "blue",
            "units": [{"unit_type": "m1a1", "count": 9}],
            "personnel_total": 120,
            "experience_level": 0.8,
        },
        "red_forces": {
            "side": "red",
            "units": [{"unit_type": "t72m", "count": 30}],
            "personnel_total": 500,
            "experience_level": 0.3,
        },
        "terrain": {"width_m": 4000, "height_m": 6000},
        "documented_outcomes": [
            {"name": "exchange_ratio", "value": 28.0},
        ],
    }


class TestHistoricalEngagement:
    def test_from_dict(self) -> None:
        raw = _minimal_engagement_dict()
        eng = HistoricalEngagement.model_validate(raw)
        assert eng.name == "Test Battle"
        assert eng.duration_hours == 1.0
        assert eng.blue_forces.side == "blue"
        assert len(eng.documented_outcomes) == 1

    def test_defaults(self) -> None:
        raw = _minimal_engagement_dict()
        eng = HistoricalEngagement.model_validate(raw)
        assert eng.calibration_overrides == {}
        assert eng.behavior_rules == {}
        assert eng.sources == []

    def test_with_calibration_overrides(self) -> None:
        raw = _minimal_engagement_dict()
        raw["calibration_overrides"] = {"hit_probability_modifier": 1.2}
        eng = HistoricalEngagement.model_validate(raw)
        assert eng.calibration_overrides["hit_probability_modifier"] == 1.2

    def test_missing_required_field(self) -> None:
        raw = _minimal_engagement_dict()
        del raw["name"]
        with pytest.raises(Exception):
            HistoricalEngagement.model_validate(raw)


# ── ComparisonResult ─────────────────────────────────────────────────


class TestComparisonResult:
    def test_construction(self) -> None:
        cr = ComparisonResult(
            metric_name="exchange_ratio",
            historical_value=28.0,
            simulated_mean=25.0,
            simulated_std=3.0,
            tolerance_factor=2.0,
            within_tolerance=True,
            deviation_factor=25.0 / 28.0,
        )
        assert cr.within_tolerance is True
        assert cr.deviation_factor == pytest.approx(0.8929, rel=1e-3)


# ── HistoricalDataLoader — compare_metric ────────────────────────────


class TestCompareMetric:
    def test_within_tolerance(self) -> None:
        m = HistoricalMetric(name="ratio", value=28.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(25.0, m)
        # 28/2=14 <= 25 <= 28*2=56 → within
        assert result.within_tolerance is True
        assert result.deviation_factor == pytest.approx(25.0 / 28.0)

    def test_below_tolerance(self) -> None:
        m = HistoricalMetric(name="ratio", value=28.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(10.0, m)
        # 14 <= 10 → False
        assert result.within_tolerance is False

    def test_above_tolerance(self) -> None:
        m = HistoricalMetric(name="ratio", value=28.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(60.0, m)
        # 60 <= 56 → False
        assert result.within_tolerance is False

    def test_exact_match(self) -> None:
        m = HistoricalMetric(name="ratio", value=28.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(28.0, m)
        assert result.within_tolerance is True
        assert result.deviation_factor == pytest.approx(1.0)

    def test_at_lower_boundary(self) -> None:
        m = HistoricalMetric(name="ratio", value=28.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(14.0, m)
        assert result.within_tolerance is True

    def test_at_upper_boundary(self) -> None:
        m = HistoricalMetric(name="ratio", value=28.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(56.0, m)
        assert result.within_tolerance is True

    def test_zero_historical_simulated_zero(self) -> None:
        m = HistoricalMetric(name="blue_kia", value=0.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(0.0, m)
        assert result.within_tolerance is True
        assert result.deviation_factor == 0.0

    def test_zero_historical_simulated_small(self) -> None:
        m = HistoricalMetric(name="blue_kia", value=0.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(1.5, m)
        assert result.within_tolerance is True  # 1.5 <= 2.0

    def test_zero_historical_simulated_large(self) -> None:
        m = HistoricalMetric(name="blue_kia", value=0.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(5.0, m)
        assert result.within_tolerance is False  # 5.0 > 2.0

    def test_negative_historical_value(self) -> None:
        m = HistoricalMetric(name="morale_change", value=-5.0, tolerance_factor=2.0)
        result = HistoricalDataLoader.compare_metric(-4.0, m)
        # lo = min(-5*2, -5/2) = min(-10, -2.5) = -10
        # hi = max(-5*2, -5/2) = -2.5
        # -10 <= -4.0 <= -2.5 → True
        assert result.within_tolerance is True

    def test_std_passed_through(self) -> None:
        m = HistoricalMetric(name="x", value=10.0)
        result = HistoricalDataLoader.compare_metric(9.0, m, simulated_std=2.5)
        assert result.simulated_std == 2.5

    def test_tight_tolerance(self) -> None:
        m = HistoricalMetric(name="x", value=10.0, tolerance_factor=1.1)
        # 10/1.1 = 9.09 <= 10.5 <= 10*1.1 = 11.0 → True
        result = HistoricalDataLoader.compare_metric(10.5, m)
        assert result.within_tolerance is True
        # But 8.0 < 9.09 → False
        result2 = HistoricalDataLoader.compare_metric(8.0, m)
        assert result2.within_tolerance is False


# ── HistoricalDataLoader — compare_all ───────────────────────────────


class TestCompareAll:
    def test_all_metrics_present(self) -> None:
        metrics = [
            HistoricalMetric(name="ratio", value=28.0),
            HistoricalMetric(name="duration_min", value=23.0),
        ]
        simulated = {"ratio": 25.0, "duration_min": 20.0}
        results = HistoricalDataLoader.compare_all(simulated, metrics)
        assert len(results) == 2
        assert all(r.within_tolerance for r in results)

    def test_missing_metric(self) -> None:
        metrics = [
            HistoricalMetric(name="ratio", value=28.0),
            HistoricalMetric(name="missing_one", value=10.0),
        ]
        simulated = {"ratio": 25.0}
        results = HistoricalDataLoader.compare_all(simulated, metrics)
        assert len(results) == 2
        assert results[0].within_tolerance is True
        assert results[1].within_tolerance is False
        assert math.isnan(results[1].simulated_mean)

    def test_empty_historical(self) -> None:
        results = HistoricalDataLoader.compare_all({"x": 1.0}, [])
        assert results == []

    def test_empty_simulated(self) -> None:
        metrics = [HistoricalMetric(name="ratio", value=28.0)]
        results = HistoricalDataLoader.compare_all({}, metrics)
        assert len(results) == 1
        assert results[0].within_tolerance is False

    def test_with_stds(self) -> None:
        metrics = [HistoricalMetric(name="ratio", value=28.0)]
        simulated = {"ratio": 25.0}
        stds = {"ratio": 3.0}
        results = HistoricalDataLoader.compare_all(simulated, metrics, stds)
        assert results[0].simulated_std == 3.0


# ── HistoricalDataLoader — YAML loading ──────────────────────────────


class TestHistoricalDataLoaderYAML:
    def test_load_from_file(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            name: "Test Engagement"
            date: "1991-02-26"
            duration_hours: 0.5
            tick_duration_seconds: 5.0
            latitude: 30.0
            longitude: 47.0
            weather_conditions:
              visibility_m: 400
            blue_forces:
              side: blue
              units:
                - unit_type: m1a1
                  count: 9
              personnel_total: 120
              experience_level: 0.8
            red_forces:
              side: red
              units:
                - unit_type: t72m
                  count: 30
              personnel_total: 500
              experience_level: 0.3
            terrain:
              width_m: 4000
              height_m: 6000
              terrain_type: flat_desert
            documented_outcomes:
              - name: exchange_ratio
                value: 28.0
                tolerance_factor: 2.0
                source: "Eagle Troop AAR"
                source_quality: 0
            sources:
              - "McMaster, *Eagles in the Desert*"
        """)
        yaml_path = tmp_path / "test_scenario.yaml"
        yaml_path.write_text(content)

        loader = HistoricalDataLoader()
        eng = loader.load(yaml_path)

        assert eng.name == "Test Engagement"
        assert eng.blue_forces.personnel_total == 120
        assert eng.documented_outcomes[0].source_quality == 0
        assert len(eng.sources) == 1

    def test_load_invalid_file(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("name: Test\n")
        loader = HistoricalDataLoader()
        with pytest.raises(Exception):
            loader.load(yaml_path)

    def test_load_with_calibration(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            name: "Calibrated"
            date: "2024-01-01"
            duration_hours: 1.0
            tick_duration_seconds: 5.0
            latitude: 0.0
            longitude: 0.0
            weather_conditions: {}
            blue_forces:
              side: blue
              units: []
              personnel_total: 0
              experience_level: 0.0
            red_forces:
              side: red
              units: []
              personnel_total: 0
              experience_level: 0.0
            terrain:
              width_m: 1000
              height_m: 1000
            documented_outcomes: []
            calibration_overrides:
              hit_probability_modifier: 1.2
              morale_degrade_rate: 0.08
        """)
        yaml_path = tmp_path / "cal.yaml"
        yaml_path.write_text(content)

        loader = HistoricalDataLoader()
        eng = loader.load(yaml_path)
        assert eng.calibration_overrides["hit_probability_modifier"] == 1.2
        assert eng.calibration_overrides["morale_degrade_rate"] == 0.08

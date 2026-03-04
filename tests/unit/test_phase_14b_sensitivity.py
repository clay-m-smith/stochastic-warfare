"""Tests for Phase 14b: parameter sensitivity sweep."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from stochastic_warfare.tools.sensitivity import (
    MetricResult,
    SweepConfig,
    SweepPoint,
    SweepResult,
    plot_sweep,
)


# ---------------------------------------------------------------------------
# SweepConfig validation
# ---------------------------------------------------------------------------


class TestSweepConfig:
    """Configuration validation."""

    def test_basic_config(self) -> None:
        cfg = SweepConfig(
            scenario_path="data/scenarios/test_campaign/scenario.yaml",
            parameter_name="hit_probability_modifier",
            values=[0.5, 1.0, 1.5],
        )
        assert cfg.parameter_name == "hit_probability_modifier"
        assert len(cfg.values) == 3

    def test_defaults(self) -> None:
        cfg = SweepConfig(
            scenario_path="test.yaml",
            parameter_name="param",
            values=[1.0],
        )
        assert cfg.iterations_per_point == 10
        assert cfg.base_seed == 42
        assert cfg.max_ticks == 100


# ---------------------------------------------------------------------------
# Result structure tests
# ---------------------------------------------------------------------------


class TestSweepResult:
    """Sweep result data structures."""

    def test_metric_result(self) -> None:
        mr = MetricResult(
            metric="blue_destroyed",
            mean=2.5,
            std=0.8,
            min=1.0,
            max=4.0,
            values=[1.0, 2.0, 3.0, 4.0],
        )
        assert mr.metric == "blue_destroyed"
        assert mr.mean == 2.5

    def test_sweep_point(self) -> None:
        sp = SweepPoint(
            parameter_value=1.5,
            metric_results=[
                MetricResult(metric="m1", mean=1.0, std=0.1, min=0.8, max=1.2),
            ],
        )
        assert sp.parameter_value == 1.5
        assert len(sp.metric_results) == 1

    def test_sweep_result_structure(self) -> None:
        sr = SweepResult(
            parameter_name="hit_probability_modifier",
            points=[
                SweepPoint(parameter_value=0.5, metric_results=[
                    MetricResult(metric="blue_destroyed", mean=1.0, std=0.5, min=0.0, max=2.0),
                ]),
                SweepPoint(parameter_value=1.0, metric_results=[
                    MetricResult(metric="blue_destroyed", mean=2.0, std=0.5, min=1.0, max=3.0),
                ]),
            ],
        )
        assert sr.parameter_name == "hit_probability_modifier"
        assert len(sr.points) == 2


# ---------------------------------------------------------------------------
# Plot tests
# ---------------------------------------------------------------------------


class TestPlotSweep:
    """Sweep plot generation."""

    def test_plot_returns_figure(self) -> None:
        import matplotlib.figure

        result = SweepResult(
            parameter_name="hit_prob",
            points=[
                SweepPoint(parameter_value=v, metric_results=[
                    MetricResult(metric="blue_destroyed", mean=v * 2, std=0.5, min=v, max=v * 3),
                ])
                for v in [0.5, 1.0, 1.5, 2.0]
            ],
        )
        fig = plot_sweep(result)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_empty_data(self) -> None:
        import matplotlib.figure

        result = SweepResult(parameter_name="param", points=[])
        fig = plot_sweep(result)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_specific_metric(self) -> None:
        import matplotlib.figure

        result = SweepResult(
            parameter_name="param",
            points=[
                SweepPoint(parameter_value=1.0, metric_results=[
                    MetricResult(metric="m1", mean=1.0, std=0.1, min=0.8, max=1.2),
                    MetricResult(metric="m2", mean=2.0, std=0.2, min=1.5, max=2.5),
                ]),
            ],
        )
        fig = plot_sweep(result, metric="m2")
        assert isinstance(fig, matplotlib.figure.Figure)

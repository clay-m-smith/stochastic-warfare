"""Tests for Phase 14c: chart library."""

from __future__ import annotations

import matplotlib
import matplotlib.figure
import numpy as np

from stochastic_warfare.tools.charts import (
    engagement_network,
    engagement_timeline,
    force_strength_chart,
    mc_distribution_grid,
    morale_progression,
    supply_flow_diagram,
)


class TestForceStrengthChart:
    """Force strength area chart."""

    def test_returns_figure(self) -> None:
        data = {
            "blue": [(0, 10), (100, 8), (200, 6)],
            "red": [(0, 12), (100, 9), (200, 3)],
        }
        fig = force_strength_chart(data)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_data(self) -> None:
        fig = force_strength_chart({})
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_single_side(self) -> None:
        fig = force_strength_chart({"blue": [(0, 5), (10, 3)]})
        assert isinstance(fig, matplotlib.figure.Figure)


class TestEngagementNetwork:
    """Engagement network graph."""

    def test_returns_figure(self) -> None:
        events = [
            {"attacker_id": "b1", "target_id": "r1", "result": "hit"},
            {"attacker_id": "b2", "target_id": "r1", "result": "miss"},
        ]
        sides = {"b1": "blue", "b2": "blue", "r1": "red"}
        fig = engagement_network(events, sides)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_events(self) -> None:
        fig = engagement_network([], {})
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_node_count(self) -> None:
        events = [
            {"attacker_id": "a", "target_id": "b", "result": "hit"},
            {"attacker_id": "c", "target_id": "b", "result": "miss"},
        ]
        fig = engagement_network(events, {"a": "blue", "b": "red", "c": "blue"})
        assert isinstance(fig, matplotlib.figure.Figure)


class TestSupplyFlowDiagram:
    """Supply flow timeline chart."""

    def test_returns_figure(self) -> None:
        snapshots = [
            {"tick": 0, "supply_level": 1.0},
            {"tick": 50, "supply_level": 0.8},
            {"tick": 100, "supply_level": 0.3},
        ]
        fig = supply_flow_diagram(snapshots, "blue")
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_snapshots(self) -> None:
        fig = supply_flow_diagram([], "blue")
        assert isinstance(fig, matplotlib.figure.Figure)


class TestEngagementTimeline:
    """Engagement timeline scatter plot."""

    def test_returns_figure(self) -> None:
        events = [
            {"tick": 10, "range_m": 2000, "result": "hit"},
            {"tick": 20, "range_m": 1500, "result": "miss"},
            {"tick": 30, "range_m": 800, "result": "hit"},
        ]
        fig = engagement_timeline(events)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_events(self) -> None:
        fig = engagement_timeline([])
        assert isinstance(fig, matplotlib.figure.Figure)


class TestMoraleProgression:
    """Morale state step plot."""

    def test_returns_figure(self) -> None:
        events = [
            {"tick": 0, "unit_id": "r1", "new_state": 0},
            {"tick": 50, "unit_id": "r1", "new_state": 1},
            {"tick": 100, "unit_id": "r1", "new_state": 2},
        ]
        fig = morale_progression(events)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_events(self) -> None:
        fig = morale_progression([])
        assert isinstance(fig, matplotlib.figure.Figure)


class TestMCDistributionGrid:
    """Monte Carlo distribution histogram grid."""

    def test_returns_figure(self) -> None:
        rng = np.random.default_rng(42)
        metrics = {
            "exchange_ratio": rng.normal(3.0, 0.5, 50).tolist(),
            "blue_destroyed": rng.poisson(2, 50).tolist(),
        }
        fig = mc_distribution_grid(metrics)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_with_historical(self) -> None:
        rng = np.random.default_rng(42)
        metrics = {"exchange_ratio": rng.normal(3.0, 0.5, 50).tolist()}
        fig = mc_distribution_grid(metrics, historical={"exchange_ratio": 4.6})
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_metrics(self) -> None:
        fig = mc_distribution_grid({})
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_subset_metrics(self) -> None:
        rng = np.random.default_rng(42)
        metrics = {
            "m1": rng.normal(1.0, 0.1, 20).tolist(),
            "m2": rng.normal(2.0, 0.2, 20).tolist(),
            "m3": rng.normal(3.0, 0.3, 20).tolist(),
        }
        fig = mc_distribution_grid(metrics, metric_names=["m1", "m3"])
        assert isinstance(fig, matplotlib.figure.Figure)

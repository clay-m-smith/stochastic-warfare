"""Tests for campaign metrics extraction (simulation.metrics).

Uses shared fixtures from conftest.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest

from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.simulation.metrics import (
    CampaignMetrics,
    CampaignSummary,
    SideSummary,
    TimeSeriesPoint,
)

from tests.conftest import POS_ORIGIN, TS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _MockSnapshot:
    """Lightweight snapshot for testing."""

    tick: int
    timestamp: datetime
    state: dict[str, Any]


@dataclass
class _MockEvent:
    """Lightweight recorded event for testing."""

    tick: int
    timestamp: datetime
    event_type: str
    source: str = "combat"
    data: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.data is None:
            self.data = {}


@dataclass
class _MockVictory:
    """Lightweight victory result for testing."""

    game_over: bool = False
    winning_side: str = ""
    condition_type: str = ""


@dataclass
class _MockRecorder:
    """Lightweight recorder for testing."""

    events: list[Any] | None = None

    def __post_init__(self) -> None:
        if self.events is None:
            self.events = []


def _make_snap(
    tick: int,
    blue_active: int = 4,
    red_active: int = 6,
    blue_destroyed: int = 0,
    red_destroyed: int = 0,
    supply_states: dict[str, float] | None = None,
    objectives: dict[str, Any] | None = None,
) -> _MockSnapshot:
    """Create a snapshot with unit/supply/objective data."""
    blue_units = [
        {"entity_id": f"blue_{i:04d}", "status": "ACTIVE"} for i in range(blue_active)
    ] + [
        {"entity_id": f"blue_d_{i:04d}", "status": "DESTROYED"} for i in range(blue_destroyed)
    ]
    red_units = [
        {"entity_id": f"red_{i:04d}", "status": "ACTIVE"} for i in range(red_active)
    ] + [
        {"entity_id": f"red_d_{i:04d}", "status": "DESTROYED"} for i in range(red_destroyed)
    ]
    state: dict[str, Any] = {
        "units_by_side": {"blue": blue_units, "red": red_units},
    }
    if supply_states is not None:
        state["supply_states"] = supply_states
    if objectives is not None:
        state["objectives"] = objectives
    ts = TS + timedelta(seconds=tick * 10)
    return _MockSnapshot(tick=tick, timestamp=ts, state=state)


# ---------------------------------------------------------------------------
# TimeSeriesPoint
# ---------------------------------------------------------------------------


class TestTimeSeriesPoint:
    """TimeSeriesPoint dataclass."""

    def test_creation(self) -> None:
        p = TimeSeriesPoint(tick=0, timestamp=TS, value=4.0)
        assert p.tick == 0
        assert p.value == 4.0

    def test_frozen(self) -> None:
        p = TimeSeriesPoint(tick=0, timestamp=TS, value=4.0)
        with pytest.raises(AttributeError):
            p.value = 5.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SideSummary
# ---------------------------------------------------------------------------


class TestSideSummary:
    """SideSummary dataclass."""

    def test_creation(self) -> None:
        s = SideSummary(
            side="blue", initial_units=10, final_active_units=8,
            units_destroyed=1, units_routing=1, units_surrendered=0,
        )
        assert s.side == "blue"
        assert s.initial_units == 10

    def test_defaults(self) -> None:
        s = SideSummary(
            side="red", initial_units=5, final_active_units=5,
            units_destroyed=0, units_routing=0, units_surrendered=0,
        )
        assert s.total_engagements == 0
        assert s.avg_supply_level == 1.0


# ---------------------------------------------------------------------------
# CampaignSummary
# ---------------------------------------------------------------------------


class TestCampaignSummary:
    """CampaignSummary dataclass."""

    def test_creation(self) -> None:
        s = CampaignSummary(
            name="test",
            duration_simulated_s=3600.0,
            ticks_executed=100,
            game_over=True,
            winning_side="blue",
            victory_condition="force_destroyed",
            sides={},
            total_events=50,
        )
        assert s.name == "test"
        assert s.game_over is True

    def test_defaults(self) -> None:
        s = CampaignSummary(
            name="", duration_simulated_s=0, ticks_executed=0,
            game_over=False, winning_side="", victory_condition="",
            sides={}, total_events=0,
        )
        assert s.total_engagements == 0
        assert s.objectives_controlled == {}


# ---------------------------------------------------------------------------
# Force strength time-series
# ---------------------------------------------------------------------------


class TestForceStrength:
    """CampaignMetrics.force_strength_over_time."""

    def test_constant_strength(self) -> None:
        snaps = [_make_snap(0, blue_active=4), _make_snap(1, blue_active=4)]
        pts = CampaignMetrics.force_strength_over_time(snaps, "blue")
        assert len(pts) == 2
        assert all(p.value == 4.0 for p in pts)

    def test_declining_strength(self) -> None:
        snaps = [_make_snap(0, blue_active=4), _make_snap(1, blue_active=2)]
        pts = CampaignMetrics.force_strength_over_time(snaps, "blue")
        assert pts[0].value == 4.0
        assert pts[1].value == 2.0

    def test_red_side(self) -> None:
        snaps = [_make_snap(0, red_active=10)]
        pts = CampaignMetrics.force_strength_over_time(snaps, "red")
        assert pts[0].value == 10.0

    def test_empty_snapshots(self) -> None:
        pts = CampaignMetrics.force_strength_over_time([], "blue")
        assert pts == []

    def test_missing_side_returns_zero(self) -> None:
        snaps = [_make_snap(0)]
        pts = CampaignMetrics.force_strength_over_time(snaps, "green")
        assert pts[0].value == 0.0


# ---------------------------------------------------------------------------
# Supply level time-series
# ---------------------------------------------------------------------------


class TestSupplyLevel:
    """CampaignMetrics.supply_level_over_time."""

    def test_full_supply(self) -> None:
        snaps = [_make_snap(0, blue_active=2, supply_states={"blue_0000": 1.0, "blue_0001": 1.0})]
        pts = CampaignMetrics.supply_level_over_time(snaps, "blue")
        assert pts[0].value == pytest.approx(1.0)

    def test_half_supply(self) -> None:
        snaps = [_make_snap(0, blue_active=2, supply_states={"blue_0000": 0.5, "blue_0001": 0.5})]
        pts = CampaignMetrics.supply_level_over_time(snaps, "blue")
        assert pts[0].value == pytest.approx(0.5)

    def test_mixed_supply(self) -> None:
        snaps = [_make_snap(0, blue_active=2, supply_states={"blue_0000": 1.0, "blue_0001": 0.0})]
        pts = CampaignMetrics.supply_level_over_time(snaps, "blue")
        assert pts[0].value == pytest.approx(0.5)

    def test_missing_supply_defaults_to_one(self) -> None:
        snaps = [_make_snap(0, blue_active=2, supply_states={})]
        pts = CampaignMetrics.supply_level_over_time(snaps, "blue")
        assert pts[0].value == pytest.approx(1.0)

    def test_empty_snapshots(self) -> None:
        pts = CampaignMetrics.supply_level_over_time([], "blue")
        assert pts == []


# ---------------------------------------------------------------------------
# Objective control timeline
# ---------------------------------------------------------------------------


class TestObjectiveTimeline:
    """CampaignMetrics.objective_control_timeline."""

    def test_uncontrolled_returns_zero(self) -> None:
        obj = {"obj1": {"controlling_side": "", "contested": False}}
        snaps = [_make_snap(0, objectives=obj)]
        pts = CampaignMetrics.objective_control_timeline(snaps, "obj1")
        assert pts[0].value == 0.0

    def test_controlled_returns_positive(self) -> None:
        obj = {"obj1": {"controlling_side": "blue", "contested": False}}
        snaps = [_make_snap(0, objectives=obj)]
        pts = CampaignMetrics.objective_control_timeline(snaps, "obj1")
        assert pts[0].value == 1.0

    def test_contested_returns_negative(self) -> None:
        obj = {"obj1": {"controlling_side": "blue", "contested": True}}
        snaps = [_make_snap(0, objectives=obj)]
        pts = CampaignMetrics.objective_control_timeline(snaps, "obj1")
        assert pts[0].value == -1.0

    def test_control_changes(self) -> None:
        snaps = [
            _make_snap(0, objectives={"obj1": {"controlling_side": "blue", "contested": False}}),
            _make_snap(1, objectives={"obj1": {"controlling_side": "red", "contested": False}}),
        ]
        pts = CampaignMetrics.objective_control_timeline(snaps, "obj1")
        assert pts[0].value == 1.0  # blue
        assert pts[1].value == 2.0  # red

    def test_missing_objective_returns_zero(self) -> None:
        snaps = [_make_snap(0, objectives={})]
        pts = CampaignMetrics.objective_control_timeline(snaps, "nonexistent")
        assert pts[0].value == 0.0


# ---------------------------------------------------------------------------
# Engagement outcomes
# ---------------------------------------------------------------------------


class TestEngagementOutcomes:
    """CampaignMetrics.engagement_outcomes."""

    def test_no_engagements(self) -> None:
        outcomes = CampaignMetrics.engagement_outcomes([])
        assert outcomes["total"] == 0

    def test_hit_counted(self) -> None:
        events = [_MockEvent(tick=0, timestamp=TS, event_type="EngagementEvent", data={"hit": True})]
        outcomes = CampaignMetrics.engagement_outcomes(events)
        assert outcomes["total"] == 1
        assert outcomes["hits"] == 1

    def test_miss_counted(self) -> None:
        events = [_MockEvent(tick=0, timestamp=TS, event_type="EngagementEvent", data={"hit": False})]
        outcomes = CampaignMetrics.engagement_outcomes(events)
        assert outcomes["misses"] == 1

    def test_aborted_counted(self) -> None:
        events = [_MockEvent(tick=0, timestamp=TS, event_type="EngagementEvent", data={"aborted_reason": "roe"})]
        outcomes = CampaignMetrics.engagement_outcomes(events)
        assert outcomes["aborted"] == 1


# ---------------------------------------------------------------------------
# Campaign summary extraction
# ---------------------------------------------------------------------------


class TestExtractCampaignSummary:
    """CampaignMetrics.extract_campaign_summary."""

    def _make_units(self, side: str, active: int = 4, destroyed: int = 0) -> list[Unit]:
        units: list[Unit] = []
        for i in range(active):
            units.append(Unit(entity_id=f"{side}_a{i}", position=POS_ORIGIN))
        for i in range(destroyed):
            u = Unit(entity_id=f"{side}_d{i}", position=POS_ORIGIN)
            object.__setattr__(u, "status", UnitStatus.DESTROYED)
            units.append(u)
        return units

    def test_basic_summary(self) -> None:
        recorder = _MockRecorder()
        victory = _MockVictory(game_over=True, winning_side="blue", condition_type="force_destroyed")
        units = {"blue": self._make_units("blue", 4, 0), "red": self._make_units("red", 2, 4)}
        summary = CampaignMetrics.extract_campaign_summary(
            recorder, victory, units, campaign_name="test", ticks_executed=100, duration_s=1000,
        )
        assert summary.game_over is True
        assert summary.winning_side == "blue"
        assert summary.sides["blue"].initial_units == 4
        assert summary.sides["red"].initial_units == 6
        assert summary.sides["red"].units_destroyed == 4

    def test_not_game_over(self) -> None:
        recorder = _MockRecorder()
        victory = _MockVictory()
        units = {"blue": self._make_units("blue"), "red": self._make_units("red")}
        summary = CampaignMetrics.extract_campaign_summary(recorder, victory, units)
        assert summary.game_over is False

    def test_with_events(self) -> None:
        events = [
            _MockEvent(tick=0, timestamp=TS, event_type="EngagementEvent", data={"hit": True}),
            _MockEvent(tick=1, timestamp=TS, event_type="EngagementEvent", data={"hit": False}),
        ]
        recorder = _MockRecorder(events=events)
        victory = _MockVictory()
        units = {"blue": self._make_units("blue"), "red": self._make_units("red")}
        summary = CampaignMetrics.extract_campaign_summary(recorder, victory, units)
        assert summary.total_events == 2
        assert summary.total_engagements == 2

    def test_with_objectives(self) -> None:
        recorder = _MockRecorder()
        victory = _MockVictory()
        units = {"blue": [], "red": []}

        @dataclass
        class _Obj:
            controlling_side: str = "blue"

        objectives = {"obj1": _Obj()}
        summary = CampaignMetrics.extract_campaign_summary(
            recorder, victory, units, objectives=objectives,
        )
        assert summary.objectives_controlled["obj1"] == "blue"

    def test_routing_and_surrendered_counted(self) -> None:
        recorder = _MockRecorder()
        victory = _MockVictory()
        units_list: list[Unit] = []
        for i in range(2):
            units_list.append(Unit(entity_id=f"r_{i}", position=POS_ORIGIN))
        u_rout = Unit(entity_id="r_rout", position=POS_ORIGIN)
        object.__setattr__(u_rout, "status", UnitStatus.ROUTING)
        units_list.append(u_rout)
        u_surr = Unit(entity_id="r_surr", position=POS_ORIGIN)
        object.__setattr__(u_surr, "status", UnitStatus.SURRENDERED)
        units_list.append(u_surr)
        units = {"red": units_list}
        summary = CampaignMetrics.extract_campaign_summary(recorder, victory, units)
        assert summary.sides["red"].units_routing == 1
        assert summary.sides["red"].units_surrendered == 1

    def test_empty_units(self) -> None:
        recorder = _MockRecorder()
        victory = _MockVictory()
        summary = CampaignMetrics.extract_campaign_summary(recorder, victory, {})
        assert summary.sides == {}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_single_snapshot_series(self) -> None:
        snaps = [_make_snap(0)]
        pts = CampaignMetrics.force_strength_over_time(snaps, "blue")
        assert len(pts) == 1

    def test_non_engagement_events_ignored(self) -> None:
        events = [
            _MockEvent(tick=0, timestamp=TS, event_type="MoraleChangeEvent"),
            _MockEvent(tick=0, timestamp=TS, event_type="MovementEvent"),
        ]
        outcomes = CampaignMetrics.engagement_outcomes(events)
        assert outcomes["total"] == 0

    def test_many_snapshots_performance(self) -> None:
        snaps = [_make_snap(i) for i in range(100)]
        pts = CampaignMetrics.force_strength_over_time(snaps, "blue")
        assert len(pts) == 100

    def test_tick_values_preserved(self) -> None:
        snaps = [_make_snap(0), _make_snap(10), _make_snap(20)]
        pts = CampaignMetrics.force_strength_over_time(snaps, "blue")
        assert [p.tick for p in pts] == [0, 10, 20]

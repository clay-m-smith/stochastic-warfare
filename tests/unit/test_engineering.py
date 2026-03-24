"""Tests for logistics/engineering.py -- project management, completion events."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.engineering import (
    EngineeringConfig,
    EngineeringEngine,
    EngineeringTask,
)
from stochastic_warfare.logistics.events import (
    ConstructionCompletedEvent,
    ConstructionStartedEvent,
    InfrastructureRepairedEvent,
    ObstacleClearedEvent,
    ObstacleEmplacedEvent,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS = Position(1000.0, 2000.0)


def _make_engine(
    seed: int = 42, config: EngineeringConfig | None = None,
) -> tuple[EngineeringEngine, EventBus]:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    engine = EngineeringEngine(event_bus=bus, rng=rng, config=config)
    return engine, bus


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEngineeringTaskEnum:
    def test_values(self) -> None:
        assert EngineeringTask.BUILD_BRIDGE == 0
        assert EngineeringTask.BUILD_AIRFIELD == 6

    def test_all_members(self) -> None:
        assert len(EngineeringTask) == 7


# ---------------------------------------------------------------------------
# Project management
# ---------------------------------------------------------------------------


class TestProjectManagement:
    def test_start_project(self) -> None:
        engine, _ = _make_engine()
        project = engine.start_project(
            EngineeringTask.BUILD_BRIDGE, _POS, "eng_1",
        )
        assert project.progress == 0.0
        assert project.task_type == EngineeringTask.BUILD_BRIDGE

    def test_start_project_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(ConstructionStartedEvent, events.append)
        engine.start_project(
            EngineeringTask.BUILD_BRIDGE, _POS, "eng_1",
            timestamp=_TS,
        )
        assert len(events) == 1

    def test_get_project(self) -> None:
        engine, _ = _make_engine()
        p = engine.start_project(EngineeringTask.BUILD_BRIDGE, _POS, "eng_1")
        assert engine.get_project(p.project_id) is p

    def test_get_project_missing_raises(self) -> None:
        engine, _ = _make_engine()
        with pytest.raises(KeyError):
            engine.get_project("nonexistent")

    def test_active_projects(self) -> None:
        engine, _ = _make_engine()
        engine.start_project(EngineeringTask.BUILD_BRIDGE, _POS, "eng_1")
        engine.start_project(EngineeringTask.BUILD_FORTIFICATION, _POS, "eng_2")
        assert len(engine.active_projects()) == 2

    def test_assess_task(self) -> None:
        engine, _ = _make_engine()
        hours = engine.assess_task(EngineeringTask.BUILD_BRIDGE)
        assert hours == 8.0  # default config


# ---------------------------------------------------------------------------
# Progress and completion
# ---------------------------------------------------------------------------


class TestProgress:
    def test_progress_advances(self) -> None:
        cfg = EngineeringConfig(bridge_build_hours=10.0)
        engine, _ = _make_engine(config=cfg)
        p = engine.start_project(EngineeringTask.BUILD_BRIDGE, _POS, "eng_1")
        engine.update(5.0)
        assert p.progress == pytest.approx(0.5)

    def test_completion(self) -> None:
        cfg = EngineeringConfig(fortification_build_hours=4.0)
        engine, _ = _make_engine(config=cfg)
        engine.start_project(EngineeringTask.BUILD_FORTIFICATION, _POS, "eng_1")
        completed = engine.update(5.0)
        assert len(completed) == 1

    def test_completion_publishes_construction_event(self) -> None:
        cfg = EngineeringConfig(bridge_build_hours=1.0)
        engine, bus = _make_engine(config=cfg)
        events: list[Event] = []
        bus.subscribe(ConstructionCompletedEvent, events.append)
        engine.start_project(
            EngineeringTask.BUILD_BRIDGE, _POS, "eng_1",
            target_feature_id="bridge_1",
        )
        engine.update(2.0, timestamp=_TS)
        assert len(events) == 1
        assert events[0].target_feature_id == "bridge_1"

    def test_repair_publishes_infrastructure_event(self) -> None:
        cfg = EngineeringConfig(bridge_repair_hours=1.0)
        engine, bus = _make_engine(config=cfg)
        events: list[Event] = []
        bus.subscribe(InfrastructureRepairedEvent, events.append)
        engine.start_project(
            EngineeringTask.REPAIR_BRIDGE, _POS, "eng_1",
            target_feature_id="bridge_1",
        )
        engine.update(2.0, timestamp=_TS)
        assert len(events) == 1

    def test_emplace_obstacle_publishes_event(self) -> None:
        cfg = EngineeringConfig(minefield_emplace_hours=1.0)
        engine, bus = _make_engine(config=cfg)
        events: list[Event] = []
        bus.subscribe(ObstacleEmplacedEvent, events.append)
        engine.start_project(
            EngineeringTask.EMPLACE_OBSTACLE, _POS, "eng_1",
            target_feature_id="mine_1",
        )
        engine.update(2.0, timestamp=_TS)
        assert len(events) == 1
        assert events[0].position == _POS

    def test_clear_obstacle_publishes_event(self) -> None:
        cfg = EngineeringConfig(minefield_clear_hours_per_density=1.0)
        engine, bus = _make_engine(config=cfg)
        events: list[Event] = []
        bus.subscribe(ObstacleClearedEvent, events.append)
        engine.start_project(
            EngineeringTask.CLEAR_OBSTACLE, _POS, "eng_1",
            target_feature_id="mine_1",
        )
        engine.update(2.0, timestamp=_TS)
        assert len(events) == 1

    def test_completed_project_not_active(self) -> None:
        cfg = EngineeringConfig(fortification_build_hours=1.0)
        engine, _ = _make_engine(config=cfg)
        engine.start_project(EngineeringTask.BUILD_FORTIFICATION, _POS, "eng_1")
        engine.update(2.0)
        assert len(engine.active_projects()) == 0

    def test_progress_capped_at_one(self) -> None:
        cfg = EngineeringConfig(fortification_build_hours=1.0)
        engine, _ = _make_engine(config=cfg)
        p = engine.start_project(EngineeringTask.BUILD_FORTIFICATION, _POS, "eng_1")
        engine.update(100.0)
        assert p.progress == 1.0


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        engine, _ = _make_engine()
        engine.start_project(EngineeringTask.BUILD_BRIDGE, _POS, "eng_1")
        engine.update(2.0)

        state = engine.get_state()
        engine2, _ = _make_engine()
        engine2.set_state(state)
        assert engine2.get_state() == state

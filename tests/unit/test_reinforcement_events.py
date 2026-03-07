"""Tests for ReinforcementArrivedEvent publishing (Phase 37a, Bug 2)."""

from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.simulation.campaign import (
    CampaignManager,
    ReinforcementArrivedEvent,
)
from stochastic_warfare.simulation.scenario import ReinforcementConfig

from tests.conftest import TS, make_rng


def _make_clock(elapsed_s: float = 0.0) -> SimulationClock:
    clock = SimulationClock(start=TS, tick_duration=timedelta(seconds=10))
    ticks = int(elapsed_s / 10)
    for _ in range(ticks):
        clock.advance()
    return clock


class _FakeUnitLoader:
    """Minimal loader that creates SimpleNamespace 'units'."""

    def create_unit(self, *, unit_type: str, entity_id: str,
                    position: Position, side: str, rng: np.random.Generator):
        return types.SimpleNamespace(
            entity_id=entity_id,
            unit_type=unit_type,
            position=position,
            side=side,
            status=None,
        )


def _ctx(clock: SimulationClock | None = None):
    return types.SimpleNamespace(
        clock=clock or _make_clock(200.0),
        unit_loader=_FakeUnitLoader(),
        rng_manager=RNGManager(42),
    )


class TestReinforcementEvent:
    """Verify ReinforcementArrivedEvent is published on reinforcement arrival."""

    def test_event_published_on_arrival(self) -> None:
        bus = EventBus()
        received: list[ReinforcementArrivedEvent] = []
        bus.subscribe(ReinforcementArrivedEvent, received.append)

        mgr = CampaignManager(bus, make_rng(42))
        cfg = ReinforcementConfig(
            side="blue", arrival_time_s=100.0,
            units=[{"unit_type": "tank", "count": 3}],
        )
        mgr.set_reinforcements([cfg])

        ctx = _ctx()
        mgr.check_reinforcements(ctx, elapsed_s=150.0)

        assert len(received) == 1
        evt = received[0]
        assert evt.side == "blue"
        assert evt.unit_count == 3
        assert evt.unit_types == ("tank", "tank", "tank")

    def test_event_has_correct_source(self) -> None:
        bus = EventBus()
        received: list[ReinforcementArrivedEvent] = []
        bus.subscribe(ReinforcementArrivedEvent, received.append)

        mgr = CampaignManager(bus, make_rng(42))
        cfg = ReinforcementConfig(
            side="red", arrival_time_s=50.0,
            units=[{"unit_type": "inf", "count": 1}],
        )
        mgr.set_reinforcements([cfg])

        ctx = _ctx()
        mgr.check_reinforcements(ctx, elapsed_s=60.0)

        assert len(received) == 1
        assert received[0].source == ModuleId.CORE

    def test_multiple_reinforcement_waves(self) -> None:
        bus = EventBus()
        received: list[ReinforcementArrivedEvent] = []
        bus.subscribe(ReinforcementArrivedEvent, received.append)

        mgr = CampaignManager(bus, make_rng(42))
        cfgs = [
            ReinforcementConfig(
                side="blue", arrival_time_s=100.0,
                units=[{"unit_type": "tank", "count": 2}],
            ),
            ReinforcementConfig(
                side="red", arrival_time_s=200.0,
                units=[{"unit_type": "inf", "count": 1}],
            ),
        ]
        mgr.set_reinforcements(cfgs)

        ctx = _ctx(_make_clock(300.0))
        mgr.check_reinforcements(ctx, elapsed_s=300.0)

        assert len(received) == 2
        assert received[0].side == "blue"
        assert received[1].side == "red"

    def test_no_reinforcements_no_event(self) -> None:
        bus = EventBus()
        received: list[ReinforcementArrivedEvent] = []
        bus.subscribe(ReinforcementArrivedEvent, received.append)

        mgr = CampaignManager(bus, make_rng(42))
        mgr.set_reinforcements([])

        ctx = _ctx()
        mgr.check_reinforcements(ctx, elapsed_s=1000.0)

        assert len(received) == 0

    def test_not_yet_arrived_no_event(self) -> None:
        bus = EventBus()
        received: list[ReinforcementArrivedEvent] = []
        bus.subscribe(ReinforcementArrivedEvent, received.append)

        mgr = CampaignManager(bus, make_rng(42))
        cfg = ReinforcementConfig(
            side="blue", arrival_time_s=500.0,
            units=[{"unit_type": "tank", "count": 1}],
        )
        mgr.set_reinforcements([cfg])

        ctx = _ctx()
        mgr.check_reinforcements(ctx, elapsed_s=100.0)

        assert len(received) == 0

    def test_no_clock_uses_fallback_timestamp(self) -> None:
        """Ctx without clock still publishes event (backward compat)."""
        bus = EventBus()
        received: list[ReinforcementArrivedEvent] = []
        bus.subscribe(ReinforcementArrivedEvent, received.append)

        mgr = CampaignManager(bus, make_rng(42))
        cfg = ReinforcementConfig(
            side="blue", arrival_time_s=50.0,
            units=[],
        )
        mgr.set_reinforcements([cfg])

        ctx = types.SimpleNamespace(unit_loader=None, rng_manager=None)
        mgr.check_reinforcements(ctx, elapsed_s=100.0)

        assert len(received) == 1
        assert received[0].timestamp == datetime.min

    def test_event_unit_count_zero_for_empty_units(self) -> None:
        bus = EventBus()
        received: list[ReinforcementArrivedEvent] = []
        bus.subscribe(ReinforcementArrivedEvent, received.append)

        mgr = CampaignManager(bus, make_rng(42))
        cfg = ReinforcementConfig(
            side="blue", arrival_time_s=50.0,
            units=[],
        )
        mgr.set_reinforcements([cfg])

        ctx = _ctx()
        mgr.check_reinforcements(ctx, elapsed_s=100.0)

        assert len(received) == 1
        assert received[0].unit_count == 0
        assert received[0].unit_types == ()

    def test_already_arrived_no_duplicate_event(self) -> None:
        bus = EventBus()
        received: list[ReinforcementArrivedEvent] = []
        bus.subscribe(ReinforcementArrivedEvent, received.append)

        mgr = CampaignManager(bus, make_rng(42))
        cfg = ReinforcementConfig(
            side="blue", arrival_time_s=50.0,
            units=[{"unit_type": "tank", "count": 1}],
        )
        mgr.set_reinforcements([cfg])

        ctx = _ctx()
        mgr.check_reinforcements(ctx, elapsed_s=100.0)
        mgr.check_reinforcements(ctx, elapsed_s=200.0)

        assert len(received) == 1

"""Tests for logistics/prisoners.py -- POW capture, processing, evacuation."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    PrisonerCapturedEvent,
    PrisonerTransferredEvent,
)
from stochastic_warfare.logistics.prisoners import (
    PrisonerConfig,
    PrisonerEngine,
    PrisonerGroup,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS = Position(1000.0, 2000.0)


def _make_engine(
    seed: int = 42, config: PrisonerConfig | None = None,
) -> tuple[PrisonerEngine, EventBus]:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    engine = PrisonerEngine(event_bus=bus, rng=rng, config=config)
    return engine, bus


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


class TestCapture:
    def test_capture_creates_group(self) -> None:
        engine, _ = _make_engine()
        group = engine.capture("u1", 12, _POS, "red")
        assert group.count == 12
        assert group.side_captured == "red"
        assert group.status == "UNPROCESSED"

    def test_capture_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(PrisonerCapturedEvent, events.append)
        engine.capture("u1", 5, _POS, "red", timestamp=_TS)
        assert len(events) == 1
        assert events[0].prisoner_count == 5

    def test_total_prisoners(self) -> None:
        engine, _ = _make_engine()
        engine.capture("u1", 10, _POS, "red")
        engine.capture("u2", 5, _POS, "red")
        assert engine.total_prisoners() == 15

    def test_get_group(self) -> None:
        engine, _ = _make_engine()
        g = engine.capture("u1", 10, _POS, "red")
        assert engine.get_group(g.group_id) is g

    def test_get_group_missing_raises(self) -> None:
        engine, _ = _make_engine()
        with pytest.raises(KeyError):
            engine.get_group("nonexistent")


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


class TestProcessing:
    def test_processing_starts(self) -> None:
        engine, _ = _make_engine()
        g = engine.capture("u1", 10, _POS, "red")
        engine.update(0.5)
        assert g.status == "PROCESSING"

    def test_processing_completes(self) -> None:
        cfg = PrisonerConfig(processing_time_hours=2.0)
        engine, _ = _make_engine(config=cfg)
        g = engine.capture("u1", 10, _POS, "red")
        engine.update(3.0)
        assert g.status == "HELD"

    def test_processing_not_complete_early(self) -> None:
        cfg = PrisonerConfig(processing_time_hours=5.0)
        engine, _ = _make_engine(config=cfg)
        g = engine.capture("u1", 10, _POS, "red")
        engine.update(2.0)
        assert g.status == "PROCESSING"


# ---------------------------------------------------------------------------
# Guards and supply
# ---------------------------------------------------------------------------


class TestGuardsAndSupply:
    def test_guards_required(self) -> None:
        cfg = PrisonerConfig(guard_ratio=10)
        engine, _ = _make_engine(config=cfg)
        engine.capture("u1", 25, _POS, "red")
        assert engine.guards_required() == 3  # ceil(25/10)

    def test_guards_zero_when_empty(self) -> None:
        engine, _ = _make_engine()
        assert engine.guards_required() == 0

    def test_supply_consumption(self) -> None:
        engine, _ = _make_engine()
        engine.capture("u1", 10, _POS, "red")
        consumption = engine.supply_consumption_per_hour()
        assert consumption["food_kg"] == pytest.approx(10 * 0.104)
        assert consumption["water_liters"] == pytest.approx(10 * 0.167)


# ---------------------------------------------------------------------------
# Evacuation
# ---------------------------------------------------------------------------


class TestEvacuation:
    def test_evacuate(self) -> None:
        engine, _ = _make_engine()
        g = engine.capture("u1", 10, _POS, "red")
        engine.update(3.0)
        engine.evacuate(g.group_id, "camp_1")
        assert g.status == "EVACUATED"

    def test_evacuate_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(PrisonerTransferredEvent, events.append)
        g = engine.capture("u1", 10, _POS, "red")
        engine.evacuate(g.group_id, "camp_1", timestamp=_TS)
        assert len(events) == 1
        assert events[0].destination_id == "camp_1"

    def test_evacuated_not_counted(self) -> None:
        engine, _ = _make_engine()
        g = engine.capture("u1", 10, _POS, "red")
        engine.evacuate(g.group_id, "camp_1")
        assert engine.total_prisoners() == 0


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        engine, _ = _make_engine()
        engine.capture("u1", 10, _POS, "red")
        engine.update(1.0)

        state = engine.get_state()
        engine2, _ = _make_engine()
        engine2.set_state(state)
        assert engine2.get_state() == state

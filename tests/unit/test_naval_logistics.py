"""Tests for logistics/naval_logistics.py -- UNREP, port ops, LOTS."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    PortLoadingEvent,
    UnrepCompletedEvent,
    UnrepStartedEvent,
)
from stochastic_warfare.logistics.naval_logistics import (
    NavalLogisticsConfig,
    NavalLogisticsEngine,
    NavalSupplyOp,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_engine(
    seed: int = 42, config: NavalLogisticsConfig | None = None,
) -> tuple[NavalLogisticsEngine, EventBus]:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    engine = NavalLogisticsEngine(event_bus=bus, rng=rng, config=config)
    return engine, bus


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestNavalSupplyOpEnum:
    def test_values(self) -> None:
        assert NavalSupplyOp.UNREP == 0
        assert NavalSupplyOp.SEALIFT_TRANSIT == 4

    def test_all_members(self) -> None:
        assert len(NavalSupplyOp) == 5


# ---------------------------------------------------------------------------
# UNREP
# ---------------------------------------------------------------------------


class TestUNREP:
    def test_unrep_calm_seas(self) -> None:
        engine, _ = _make_engine()
        mission = engine.start_unrep("aoe_1", ["ddg_1"], 100.0, 20.0, sea_state=3)
        assert mission is not None
        assert mission.op_type == NavalSupplyOp.UNREP

    def test_unrep_blocked_heavy_seas(self) -> None:
        engine, _ = _make_engine()
        mission = engine.start_unrep("aoe_1", ["ddg_1"], 100.0, 20.0, sea_state=6)
        assert mission is None

    def test_unrep_publishes_started(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(UnrepStartedEvent, events.append)
        engine.start_unrep("aoe_1", ["ddg_1", "cg_1"], 100.0, 20.0,
                           sea_state=3, timestamp=_TS)
        assert len(events) == 1
        assert len(events[0].receiving_unit_ids) == 2

    def test_unrep_completes(self) -> None:
        cfg = NavalLogisticsConfig(
            unrep_fuel_transfer_rate_tons_per_hour=100.0,
            unrep_ammo_transfer_rate_tons_per_hour=50.0,
        )
        engine, _ = _make_engine(config=cfg)
        engine.start_unrep("aoe_1", ["ddg_1"], 50.0, 10.0, sea_state=3)
        # 50/100 = 0.5h for fuel, 10/50 = 0.2h for ammo, bottleneck = 0.5h
        completed = engine.update(1.0, sea_state=3)
        assert len(completed) == 1

    def test_unrep_publishes_completed(self) -> None:
        cfg = NavalLogisticsConfig(
            unrep_fuel_transfer_rate_tons_per_hour=1000.0,
            unrep_ammo_transfer_rate_tons_per_hour=1000.0,
        )
        engine, bus = _make_engine(config=cfg)
        events: list[Event] = []
        bus.subscribe(UnrepCompletedEvent, events.append)
        engine.start_unrep("aoe_1", ["ddg_1"], 10.0, 5.0, sea_state=3)
        engine.update(1.0, sea_state=3, timestamp=_TS)
        assert len(events) == 1
        assert events[0].fuel_transferred_tons == 10.0

    def test_unrep_suspended_in_storm(self) -> None:
        engine, _ = _make_engine()
        engine.start_unrep("aoe_1", ["ddg_1"], 200.0, 50.0, sea_state=3)
        # Sea state 6 during update → no progress
        completed = engine.update(1.0, sea_state=6)
        assert len(completed) == 0
        m = engine.get_mission(engine.active_missions()[0].mission_id)
        assert m.progress_fraction == 0.0


# ---------------------------------------------------------------------------
# Port ops
# ---------------------------------------------------------------------------


class TestPortOps:
    def test_port_loading(self) -> None:
        engine, _ = _make_engine()
        mission = engine.start_port_ops(
            "port_1", ["ddg_1"], NavalSupplyOp.PORT_LOADING, 500.0,
        )
        assert mission.op_type == NavalSupplyOp.PORT_LOADING

    def test_port_loading_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(PortLoadingEvent, events.append)
        engine.start_port_ops(
            "port_1", ["ddg_1"], NavalSupplyOp.PORT_LOADING, 500.0,
            timestamp=_TS,
        )
        assert len(events) == 1

    def test_port_ops_complete(self) -> None:
        cfg = NavalLogisticsConfig(port_throughput_tons_per_hour=200.0)
        engine, _ = _make_engine(config=cfg)
        engine.start_port_ops(
            "port_1", ["ddg_1"], NavalSupplyOp.PORT_LOADING, 100.0,
        )
        # 100/200 = 0.5h to complete
        completed = engine.update(1.0)
        assert len(completed) == 1


# ---------------------------------------------------------------------------
# LOTS
# ---------------------------------------------------------------------------


class TestLOTS:
    def test_lots_calm_seas(self) -> None:
        engine, _ = _make_engine()
        mission = engine.start_lots(
            Position(0.0, 0.0), ["lcu_1"], 50.0, sea_state=2,
        )
        assert mission is not None

    def test_lots_blocked_heavy_seas(self) -> None:
        engine, _ = _make_engine()
        mission = engine.start_lots(
            Position(0.0, 0.0), ["lcu_1"], 50.0, sea_state=4,
        )
        assert mission is None

    def test_lots_low_throughput(self) -> None:
        cfg = NavalLogisticsConfig(
            port_throughput_tons_per_hour=100.0,
            lots_throughput_fraction=0.1,
        )
        engine, _ = _make_engine(config=cfg)
        engine.start_lots(Position(0.0, 0.0), ["lcu_1"], 100.0, sea_state=2)
        # LOTS throughput = 100*0.1 = 10 t/h; 100/10 = 10h to complete
        completed = engine.update(5.0)
        assert len(completed) == 0  # not enough time
        completed = engine.update(6.0)
        assert len(completed) == 1


# ---------------------------------------------------------------------------
# Active missions
# ---------------------------------------------------------------------------


class TestActiveMissions:
    def test_active_missions(self) -> None:
        engine, _ = _make_engine()
        engine.start_unrep("aoe_1", ["ddg_1"], 1000.0, 100.0, sea_state=3)
        engine.start_port_ops("port_1", ["ddg_2"], NavalSupplyOp.PORT_LOADING, 500.0)
        assert len(engine.active_missions()) == 2

    def test_completed_not_active(self) -> None:
        cfg = NavalLogisticsConfig(
            unrep_fuel_transfer_rate_tons_per_hour=10000.0,
            unrep_ammo_transfer_rate_tons_per_hour=10000.0,
        )
        engine, _ = _make_engine(config=cfg)
        engine.start_unrep("aoe_1", ["ddg_1"], 1.0, 1.0, sea_state=3)
        engine.update(1.0, sea_state=3)
        assert len(engine.active_missions()) == 0


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        engine, _ = _make_engine()
        engine.start_unrep("aoe_1", ["ddg_1"], 100.0, 20.0, sea_state=3)
        engine.update(0.1, sea_state=3)

        state = engine.get_state()
        engine2, _ = _make_engine()
        engine2.set_state(state)
        assert engine2.get_state() == state

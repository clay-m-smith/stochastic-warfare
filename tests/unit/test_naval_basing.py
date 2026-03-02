"""Tests for logistics/naval_basing.py -- bases, repair, station time, tidal access."""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.naval_basing import (
    NavalBase,
    NavalBasingConfig,
    NavalBasingEngine,
    NavalBaseType,
)

_POS = Position(0.0, 0.0)


def _make_engine(
    seed: int = 42, config: NavalBasingConfig | None = None,
) -> NavalBasingEngine:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    return NavalBasingEngine(event_bus=bus, rng=rng, config=config)


def _make_base(
    base_id: str = "base_1",
    base_type: NavalBaseType = NavalBaseType.NAVAL_BASE,
    condition: float = 1.0,
) -> NavalBase:
    return NavalBase(
        base_id=base_id,
        base_type=base_type,
        port_id="port_1",
        position=_POS,
        side="blue",
        repair_capacity=3,
        fuel_storage_tons=10000.0,
        berths=8,
        condition=condition,
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestNavalBaseTypeEnum:
    def test_values(self) -> None:
        assert NavalBaseType.NAVAL_BASE == 0
        assert NavalBaseType.DRY_DOCK == 3

    def test_all_members(self) -> None:
        assert len(NavalBaseType) == 4


# ---------------------------------------------------------------------------
# Base management
# ---------------------------------------------------------------------------


class TestBaseManagement:
    def test_register_base(self) -> None:
        engine = _make_engine()
        base = _make_base()
        engine.register_base(base)
        assert engine.get_base("base_1") is base

    def test_get_base_missing_raises(self) -> None:
        engine = _make_engine()
        with pytest.raises(KeyError):
            engine.get_base("nonexistent")

    def test_list_bases_all(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base("b1"))
        engine.register_base(_make_base("b2"))
        assert len(engine.list_bases()) == 2

    def test_list_bases_by_side(self) -> None:
        engine = _make_engine()
        b1 = _make_base("b1")
        b2 = _make_base("b2")
        b2.side = "red"
        engine.register_base(b1)
        engine.register_base(b2)
        assert len(engine.list_bases("blue")) == 1


# ---------------------------------------------------------------------------
# Repair capacity
# ---------------------------------------------------------------------------


class TestRepairCapacity:
    def test_full_capacity(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base())
        assert engine.get_repair_capacity("base_1") == 3

    def test_degraded_capacity(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base(condition=0.5))
        assert engine.get_repair_capacity("base_1") == 1  # floor(3 * 0.5)


# ---------------------------------------------------------------------------
# Station time
# ---------------------------------------------------------------------------


class TestStationTime:
    def test_basic_station_time(self) -> None:
        engine = _make_engine()
        # 100 tons fuel, 10 t/h consumption, 0 distance → 10 hours
        time = engine.compute_station_time(100.0, 10.0, 0.0)
        assert time == pytest.approx(10.0)

    def test_station_time_with_transit(self) -> None:
        engine = _make_engine()
        # 100 tons, 10 t/h, 28800m (8 km/h × 1h transit), 8 m/s speed
        time = engine.compute_station_time(100.0, 10.0, 28800.0, transit_speed_mps=8.0)
        # Transit: 28800/(8*3600) = 1h each way = 2h round trip
        # Transit fuel: 10 * 2 = 20 tons
        # Usable: 100 - 20 = 80 tons
        # Station time: 80/10 = 8h
        assert time == pytest.approx(8.0)

    def test_station_time_insufficient_fuel(self) -> None:
        engine = _make_engine()
        # Only 10 tons, need 20 for transit
        time = engine.compute_station_time(10.0, 10.0, 28800.0, transit_speed_mps=8.0)
        assert time == 0.0

    def test_station_time_zero_consumption(self) -> None:
        engine = _make_engine()
        time = engine.compute_station_time(100.0, 0.0, 28800.0)
        assert time == float("inf")


# ---------------------------------------------------------------------------
# Port throughput
# ---------------------------------------------------------------------------


class TestPortThroughput:
    def test_base_throughput(self) -> None:
        cfg = NavalBasingConfig(base_throughput_tons_per_hour=100.0)
        engine = _make_engine(config=cfg)
        engine.register_base(_make_base())
        assert engine.port_throughput("base_1") == pytest.approx(100.0)

    def test_degraded_base_throughput(self) -> None:
        cfg = NavalBasingConfig(base_throughput_tons_per_hour=100.0)
        engine = _make_engine(config=cfg)
        engine.register_base(_make_base(condition=0.5))
        assert engine.port_throughput("base_1") == pytest.approx(50.0)

    def test_anchorage_sea_state_penalty(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base(base_type=NavalBaseType.ANCHORAGE))
        throughput_calm = engine.port_throughput("base_1", sea_state=0)
        throughput_rough = engine.port_throughput("base_1", sea_state=4)
        assert throughput_rough < throughput_calm

    def test_naval_base_no_sea_state_penalty(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base(base_type=NavalBaseType.NAVAL_BASE))
        throughput_calm = engine.port_throughput("base_1", sea_state=0)
        throughput_rough = engine.port_throughput("base_1", sea_state=4)
        assert throughput_rough == throughput_calm


# ---------------------------------------------------------------------------
# Tidal access
# ---------------------------------------------------------------------------


class TestTidalAccess:
    def test_sufficient_tide(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base())
        # Channel 10m, tide +2m, ship 8m draft, margin 1m → 8+1=9 <= 12
        assert engine.tidal_access("base_1", 2.0, 8.0) is True

    def test_insufficient_tide(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base())
        # Channel 10m, tide -2m, ship 10m draft, margin 1m → 10+1=11 > 8
        assert engine.tidal_access("base_1", -2.0, 10.0) is False

    def test_exactly_at_limit(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base())
        # Channel 10m, tide 0m, ship 9m draft, margin 1m → 9+1=10 <= 10
        assert engine.tidal_access("base_1", 0.0, 9.0) is True

    def test_custom_channel_depth(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base())
        # Channel 5m, tide +3m, ship 6m draft, margin 1m → 6+1=7 <= 8
        assert engine.tidal_access("base_1", 3.0, 6.0, channel_depth_m=5.0) is True


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base())
        engine.register_base(_make_base("b2", NavalBaseType.FORWARD_OPERATING_BASE))

        state = engine.get_state()
        engine2 = _make_engine()
        engine2.set_state(state)
        assert engine2.get_state() == state

    def test_set_state_clears_previous(self) -> None:
        engine = _make_engine()
        engine.register_base(_make_base())
        engine.set_state({"bases": {}})
        assert len(engine.list_bases()) == 0

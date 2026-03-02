"""Tests for logistics/transport.py -- missions, delays, weather, airdrop."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.consumption import EnvironmentConditions, GroundState
from stochastic_warfare.logistics.events import (
    ConvoyArrivedEvent,
    ConvoyDestroyedEvent,
    ConvoyDispatchedEvent,
)
from stochastic_warfare.logistics.supply_classes import SupplyClass
from stochastic_warfare.logistics.supply_network import SupplyRoute, TransportMode
from stochastic_warfare.logistics.transport import (
    TransportConfig,
    TransportEngine,
    TransportMission,
    TransportProfile,
    TransportProfileLoader,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_engine(
    seed: int = 42, config: TransportConfig | None = None,
) -> tuple[TransportEngine, EventBus]:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    engine = TransportEngine(event_bus=bus, rng=rng, config=config)
    return engine, bus


def _make_route(
    route_id: str = "r1",
    from_node: str = "A",
    to_node: str = "B",
    transit_hours: float = 2.0,
    condition: float = 1.0,
) -> SupplyRoute:
    return SupplyRoute(
        route_id=route_id,
        from_node=from_node,
        to_node=to_node,
        transport_mode=TransportMode.ROAD,
        distance_m=5000.0,
        capacity_tons_per_hour=10.0,
        base_transit_time_hours=transit_hours,
        condition=condition,
    )


def _simple_cargo() -> dict[int, dict[str, float]]:
    return {int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0}}


# ---------------------------------------------------------------------------
# Transport profile loader
# ---------------------------------------------------------------------------


class TestTransportProfileLoader:
    def test_load_all(self) -> None:
        loader = TransportProfileLoader()
        loader.load_all()
        profiles = loader.available_profiles()
        assert len(profiles) == 4

    def test_get_truck_convoy(self) -> None:
        loader = TransportProfileLoader()
        loader.load_all()
        profile = loader.get_definition("truck_convoy")
        assert profile.capacity_tons == 20.0

    def test_get_unknown_raises(self) -> None:
        loader = TransportProfileLoader()
        with pytest.raises(KeyError):
            loader.get_definition("nonexistent")

    def test_airlift_has_weather_limits(self) -> None:
        loader = TransportProfileLoader()
        loader.load_all()
        profile = loader.get_definition("c130_airlift")
        assert profile.weather_ceiling_m is not None
        assert profile.weather_visibility_m is not None


# ---------------------------------------------------------------------------
# Dispatch and arrival
# ---------------------------------------------------------------------------


class TestDispatchArrival:
    def test_dispatch_creates_mission(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route()]
        m = engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        assert m.status == "IN_TRANSIT"
        assert m.progress_fraction == 0.0

    def test_dispatch_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(ConvoyDispatchedEvent, events.append)
        route = [_make_route()]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B",
                        timestamp=_TS)
        assert len(events) == 1
        assert events[0].mission_id == "m1"

    def test_mission_arrives_after_time(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route(transit_hours=1.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        # Advance enough time (log-normal delay means we need more than base)
        completed = engine.update(10.0)
        assert len(completed) == 1
        assert completed[0].mission_id == "m1"
        assert completed[0].status == "ARRIVED"

    def test_arrival_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(ConvoyArrivedEvent, events.append)
        route = [_make_route(transit_hours=1.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        engine.update(10.0, timestamp=_TS)
        assert len(events) == 1

    def test_mission_not_arrived_early(self) -> None:
        # Use large transit time so dt is insufficient
        engine, _ = _make_engine()
        route = [_make_route(transit_hours=100.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        completed = engine.update(1.0)
        assert len(completed) == 0
        m = engine.get_mission("m1")
        assert m.status == "IN_TRANSIT"
        assert 0 < m.progress_fraction < 1.0

    def test_get_mission(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route()]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        m = engine.get_mission("m1")
        assert m.mission_id == "m1"

    def test_active_missions(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route(transit_hours=100.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        engine.dispatch("m2", TransportMode.ROAD, route, _simple_cargo(), "C", "D")
        assert len(engine.active_missions()) == 2


# ---------------------------------------------------------------------------
# Log-normal delay
# ---------------------------------------------------------------------------


class TestLogNormalDelay:
    def test_delay_varies_with_seed(self) -> None:
        engine1, _ = _make_engine(seed=1)
        engine2, _ = _make_engine(seed=2)
        route = [_make_route(transit_hours=10.0)]
        m1 = engine1.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        m2 = engine2.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        # Different seeds should produce different ETAs
        assert m1.estimated_arrival != m2.estimated_arrival

    def test_deterministic_with_same_seed(self) -> None:
        def run(seed: int) -> float:
            engine, _ = _make_engine(seed=seed)
            route = [_make_route(transit_hours=10.0)]
            m = engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
            return m.estimated_arrival
        assert run(42) == run(42)


# ---------------------------------------------------------------------------
# Weather effects
# ---------------------------------------------------------------------------


class TestWeatherEffects:
    def test_airlift_delayed_low_visibility(self) -> None:
        engine, _ = _make_engine()
        air_route = [SupplyRoute(
            "ar1", "A", "B", TransportMode.AIR,
            50000.0, 100.0, 1.0,
        )]
        engine.dispatch("m1", TransportMode.AIR, air_route, _simple_cargo(), "A", "B")
        env = EnvironmentConditions(visibility_m=500.0)  # below 1600m minimum
        completed = engine.update(10.0, env=env)
        m = engine.get_mission("m1")
        assert m.status == "DELAYED"

    def test_mud_slows_road_transport(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route(transit_hours=10.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        env_mud = EnvironmentConditions(ground_state=int(GroundState.MUD))
        engine.update(5.0, env=env_mud)
        m = engine.get_mission("m1")
        # With mud, speed is 50%, so 5 hours of real time = 2.5 hours effective
        # Progress should be less than without mud
        assert m.progress_fraction < 0.5

    def test_snow_slows_road_transport(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route(transit_hours=10.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        env_snow = EnvironmentConditions(ground_state=int(GroundState.SNOW))
        engine.update(5.0, env=env_snow)
        m = engine.get_mission("m1")
        assert m.progress_fraction < 0.5


# ---------------------------------------------------------------------------
# Destruction
# ---------------------------------------------------------------------------


class TestDestruction:
    def test_destroy_mission(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route(transit_hours=100.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        engine.destroy_mission("m1")
        m = engine.get_mission("m1")
        assert m.status == "DESTROYED"

    def test_destroy_publishes_event(self) -> None:
        engine, bus = _make_engine()
        events: list[Event] = []
        bus.subscribe(ConvoyDestroyedEvent, events.append)
        route = [_make_route(transit_hours=100.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        engine.destroy_mission("m1", cause="air_strike", timestamp=_TS)
        assert len(events) == 1
        assert events[0].cause == "air_strike"

    def test_destroyed_mission_not_active(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route(transit_hours=100.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        engine.destroy_mission("m1")
        assert len(engine.active_missions()) == 0


# ---------------------------------------------------------------------------
# Airdrop
# ---------------------------------------------------------------------------


class TestAirdrop:
    def test_airdrop_scatter(self) -> None:
        engine, _ = _make_engine()
        target = Position(5000.0, 5000.0)
        actual, cargo = engine.airdrop(target, _simple_cargo())
        # Should be near target but not exact
        assert actual != target
        dist = ((actual.easting - target.easting) ** 2 +
                (actual.northing - target.northing) ** 2) ** 0.5
        # Within reasonable CEP distance
        assert dist < 2000.0

    def test_airdrop_wind_offset(self) -> None:
        engine, _ = _make_engine(seed=99)
        target = Position(5000.0, 5000.0)
        actual_calm, _ = engine.airdrop(target, _simple_cargo(), wind_speed_mps=0.0)

        engine2, _ = _make_engine(seed=99)
        actual_windy, _ = engine2.airdrop(target, _simple_cargo(),
                                           wind_speed_mps=20.0, wind_direction_rad=0.0)
        # Wind at 0 rad (north) should push northward
        assert actual_windy.northing > actual_calm.northing

    def test_airdrop_deterministic(self) -> None:
        def run(seed: int) -> Position:
            engine, _ = _make_engine(seed=seed)
            target = Position(0.0, 0.0)
            actual, _ = engine.airdrop(target, _simple_cargo())
            return actual
        assert run(42) == run(42)

    def test_airdrop_returns_cargo(self) -> None:
        engine, _ = _make_engine()
        cargo = _simple_cargo()
        _, returned_cargo = engine.airdrop(Position(0.0, 0.0), cargo)
        assert returned_cargo == cargo


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        engine, _ = _make_engine()
        route = [_make_route(transit_hours=100.0)]
        engine.dispatch("m1", TransportMode.ROAD, route, _simple_cargo(), "A", "B")
        engine.update(5.0)

        state = engine.get_state()
        engine2, _ = _make_engine()
        engine2.set_state(state)

        m = engine2.get_mission("m1")
        assert m.status == "IN_TRANSIT"
        assert m.progress_fraction > 0

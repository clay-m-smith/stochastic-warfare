"""Tests for logistics/supply_network.py -- graph, routing, capacity."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.supply_network import (
    SupplyNetworkConfig,
    SupplyNetworkEngine,
    SupplyNode,
    SupplyRoute,
    TransportMode,
)


_POS_A = Position(0.0, 0.0)
_POS_B = Position(5000.0, 0.0)
_POS_C = Position(10000.0, 0.0)
_POS_D = Position(5000.0, 5000.0)


def _make_engine(
    seed: int = 42, config: SupplyNetworkConfig | None = None,
) -> SupplyNetworkEngine:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    return SupplyNetworkEngine(event_bus=bus, rng=rng, config=config)


def _build_simple_network(engine: SupplyNetworkEngine) -> None:
    """Build A -> B -> C linear network."""
    engine.add_node(SupplyNode("A", _POS_A, "DEPOT"))
    engine.add_node(SupplyNode("B", _POS_B, "DEPOT"))
    engine.add_node(SupplyNode("C", _POS_C, "UNIT"))
    engine.add_route(SupplyRoute(
        "r1", "A", "B", TransportMode.ROAD,
        distance_m=5000.0, capacity_tons_per_hour=10.0,
        base_transit_time_hours=1.0,
    ))
    engine.add_route(SupplyRoute(
        "r2", "B", "C", TransportMode.ROAD,
        distance_m=5000.0, capacity_tons_per_hour=8.0,
        base_transit_time_hours=1.0,
    ))


# ---------------------------------------------------------------------------
# TransportMode enum
# ---------------------------------------------------------------------------


class TestTransportModeEnum:
    def test_values(self) -> None:
        assert TransportMode.ROAD == 0
        assert TransportMode.SEA == 3
        assert TransportMode.CROSS_COUNTRY == 4

    def test_all_members(self) -> None:
        assert len(TransportMode) == 5


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


class TestGraphConstruction:
    def test_add_node(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("n1", _POS_A, "DEPOT"))
        assert engine.node_count() == 1

    def test_add_route(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("n1", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("n2", _POS_B, "UNIT"))
        engine.add_route(SupplyRoute(
            "r1", "n1", "n2", TransportMode.ROAD,
            distance_m=5000.0, capacity_tons_per_hour=10.0,
            base_transit_time_hours=1.0,
        ))
        assert engine.route_count() == 1

    def test_get_node(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("n1", _POS_A, "DEPOT", linked_id="depot_1"))
        node = engine.get_node("n1")
        assert node.linked_id == "depot_1"

    def test_get_node_missing(self) -> None:
        engine = _make_engine()
        with pytest.raises(KeyError):
            engine.get_node("missing")

    def test_get_route(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("A", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("B", _POS_B, "UNIT"))
        engine.add_route(SupplyRoute(
            "r1", "A", "B", TransportMode.ROAD,
            5000.0, 10.0, 1.0,
        ))
        route = engine.get_route("r1")
        assert route.distance_m == 5000.0


# ---------------------------------------------------------------------------
# Pathfinding
# ---------------------------------------------------------------------------


class TestPathfinding:
    def test_direct_route(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("A", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("B", _POS_B, "UNIT"))
        engine.add_route(SupplyRoute(
            "r1", "A", "B", TransportMode.ROAD,
            5000.0, 10.0, 1.0,
        ))
        path = engine.find_supply_route("A", "B")
        assert path is not None
        assert len(path) == 1
        assert path[0].route_id == "r1"

    def test_multi_hop_route(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        path = engine.find_supply_route("A", "C")
        assert path is not None
        assert len(path) == 2

    def test_no_route_returns_none(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("A", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("B", _POS_B, "UNIT"))
        # No edge between A and B
        path = engine.find_supply_route("A", "B")
        assert path is None

    def test_nonexistent_node_returns_none(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("A", _POS_A, "DEPOT"))
        path = engine.find_supply_route("A", "Z")
        assert path is None

    def test_shortest_path_by_time(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("A", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("B", _POS_B, "UNIT"))
        engine.add_node(SupplyNode("C", _POS_C, "UNIT"))
        # Direct A->C slow, via B fast
        engine.add_route(SupplyRoute(
            "r_direct", "A", "C", TransportMode.CROSS_COUNTRY,
            10000.0, 5.0, 10.0,  # 10 hours
        ))
        engine.add_route(SupplyRoute(
            "r_ab", "A", "B", TransportMode.ROAD,
            5000.0, 10.0, 1.0,  # 1 hour
        ))
        engine.add_route(SupplyRoute(
            "r_bc", "B", "C", TransportMode.ROAD,
            5000.0, 10.0, 1.0,  # 1 hour
        ))
        path = engine.find_supply_route("A", "C")
        assert path is not None
        assert len(path) == 2  # via B, not direct


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


class TestCapacity:
    def test_bottleneck_capacity(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        path = engine.find_supply_route("A", "C")
        assert path is not None
        cap = engine.compute_route_capacity(path)
        # Route r1=10, r2=8; bottleneck is 8
        assert cap == pytest.approx(8.0)

    def test_capacity_degraded_by_condition(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.update_route_condition("r2", 0.5)
        path = engine.find_supply_route("A", "C")
        assert path is not None
        cap = engine.compute_route_capacity(path)
        # r1: 10*1.0=10, r2: 8*0.5=4; bottleneck is 4
        assert cap == pytest.approx(4.0)

    def test_empty_path_zero_capacity(self) -> None:
        engine = _make_engine()
        assert engine.compute_route_capacity([]) == 0.0


# ---------------------------------------------------------------------------
# Transit time
# ---------------------------------------------------------------------------


class TestTransitTime:
    def test_simple_transit(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        path = engine.find_supply_route("A", "C")
        assert path is not None
        time = engine.compute_route_transit_time(path)
        assert time == pytest.approx(2.0)  # 1 + 1

    def test_degraded_route_slower(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.update_route_condition("r2", 0.5)
        path = engine.find_supply_route("A", "C")
        assert path is not None
        time = engine.compute_route_transit_time(path)
        # r1: 1/1=1, r2: 1/0.5=2; total 3
        assert time == pytest.approx(3.0)

    def test_empty_path_zero_time(self) -> None:
        engine = _make_engine()
        assert engine.compute_route_transit_time([]) == 0.0


# ---------------------------------------------------------------------------
# Route condition updates
# ---------------------------------------------------------------------------


class TestRouteCondition:
    def test_update_condition(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.update_route_condition("r1", 0.6)
        route = engine.get_route("r1")
        assert route.condition == pytest.approx(0.6)

    def test_condition_clamped_to_zero(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.update_route_condition("r1", -0.5)
        route = engine.get_route("r1")
        assert route.condition == 0.0

    def test_condition_clamped_to_one(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.update_route_condition("r1", 1.5)
        route = engine.get_route("r1")
        assert route.condition == 1.0


# ---------------------------------------------------------------------------
# Seasonal degradation
# ---------------------------------------------------------------------------


class TestSeasonalDegradation:
    def test_no_degradation_in_dry(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.update(10.0, ground_state=0)  # DRY
        route = engine.get_route("r1")
        assert route.condition == 1.0

    def test_degradation_in_mud(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.update(10.0, ground_state=2)  # MUD
        route = engine.get_route("r1")
        assert route.condition < 1.0

    def test_degradation_rate(self) -> None:
        cfg = SupplyNetworkConfig(seasonal_degradation_rate=0.05)
        engine = _make_engine(config=cfg)
        _build_simple_network(engine)
        engine.update(1.0, ground_state=2)
        route = engine.get_route("r1")
        assert route.condition == pytest.approx(0.95)

    def test_rail_not_degraded_by_mud(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("A", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("B", _POS_B, "UNIT"))
        engine.add_route(SupplyRoute(
            "rail1", "A", "B", TransportMode.RAIL,
            5000.0, 50.0, 0.5,
        ))
        engine.update(100.0, ground_state=2)
        assert engine.get_route("rail1").condition == 1.0


# ---------------------------------------------------------------------------
# Nearest depot
# ---------------------------------------------------------------------------


class TestNearestDepot:
    def test_find_nearest(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("D1", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("D2", _POS_D, "DEPOT"))
        engine.add_node(SupplyNode("U", _POS_B, "UNIT"))
        engine.add_route(SupplyRoute(
            "r1", "D1", "U", TransportMode.ROAD,
            5000.0, 10.0, 1.0,
        ))
        engine.add_route(SupplyRoute(
            "r2", "D2", "U", TransportMode.ROAD,
            7000.0, 10.0, 3.0,
        ))
        result = engine.find_nearest_depot_node("U", ["D1", "D2"])
        assert result is not None
        assert result[0] == "D1"

    def test_no_reachable_depot(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("D1", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("U", _POS_B, "UNIT"))
        # No routes
        result = engine.find_nearest_depot_node("U", ["D1"])
        assert result is None


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.update_route_condition("r1", 0.7)

        state = engine.get_state()
        engine2 = _make_engine()
        engine2.set_state(state)

        assert engine2.node_count() == 3
        assert engine2.route_count() == 2
        assert engine2.get_route("r1").condition == pytest.approx(0.7)
        # Pathfinding still works
        path = engine2.find_supply_route("A", "C")
        assert path is not None

    def test_set_state_clears_previous(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        engine.set_state({"nodes": {}, "routes": {}})
        assert engine.node_count() == 0
        assert engine.route_count() == 0

"""Tests for logistics/supply_network.py -- graph, routing, capacity."""

from __future__ import annotations

import json

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

    def test_duplicate_node_and_route_rejected_without_overwrite(self) -> None:
        engine = _make_engine()
        original = SupplyNode("A", _POS_A, "DEPOT", side="blue")
        engine.add_node(original)
        with pytest.raises(ValueError, match="Duplicate supply node ID"):
            engine.add_node(SupplyNode("A", _POS_B, "UNIT", side="red"))
        assert engine.get_node("A") is original

        engine.add_node(SupplyNode("B", _POS_B, "UNIT", side="blue"))
        route = SupplyRoute(
            "r1", "A", "B", TransportMode.ROAD,
            5000.0, 10.0, 1.0,
        )
        engine.add_route(route)
        with pytest.raises(ValueError, match="Duplicate supply route ID"):
            engine.add_route(SupplyRoute(
                "r1", "A", "B", TransportMode.ROAD,
                5000.0, 1.0, 1.0,
            ))
        assert engine.get_route("r1") is route

    def test_route_requires_existing_endpoints_and_unique_directed_edge(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("A", _POS_A, "DEPOT"))
        with pytest.raises(ValueError, match="unknown endpoint"):
            engine.add_route(SupplyRoute(
                "missing", "A", "B", TransportMode.ROAD,
                5000.0, 10.0, 1.0,
            ))
        engine.add_node(SupplyNode("B", _POS_B, "UNIT"))
        engine.add_route(SupplyRoute(
            "r1", "A", "B", TransportMode.ROAD,
            5000.0, 10.0, 1.0,
        ))
        with pytest.raises(ValueError, match="Parallel supply route"):
            engine.add_route(SupplyRoute(
                "r2", "A", "B", TransportMode.RAIL,
                5000.0, 10.0, 1.0,
            ))

    def test_sorted_public_node_and_route_views(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("z", _POS_A, "DEPOT", side="blue"))
        engine.add_node(SupplyNode("a", _POS_B, "UNIT", side="blue"))
        engine.add_node(SupplyNode("m", _POS_C, "UNIT", side="blue"))
        engine.add_node(SupplyNode("r", _POS_D, "DEPOT", side="red"))
        engine.add_route(SupplyRoute(
            "z-route", "z", "a", TransportMode.ROAD,
            5000.0, 10.0, 1.0,
        ))
        engine.add_route(SupplyRoute(
            "a-route", "a", "m", TransportMode.ROAD,
            5000.0, 10.0, 1.0,
        ))
        assert [n.node_id for n in engine.list_nodes()] == ["a", "m", "r", "z"]
        assert [n.node_id for n in engine.list_nodes(side="blue")] == ["a", "m", "z"]
        assert [r.route_id for r in engine.list_routes()] == ["a-route", "z-route"]


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

    def test_equal_time_paths_use_stable_route_id_tie_break(self) -> None:
        engine = _make_engine()
        for node_id in ("A", "B", "C", "D"):
            engine.add_node(SupplyNode(node_id, _POS_A, "UNIT"))
        engine.add_route(SupplyRoute(
            "z-first", "A", "B", TransportMode.ROAD, 1.0, 1.0, 1.0,
        ))
        engine.add_route(SupplyRoute(
            "z-second", "B", "D", TransportMode.ROAD, 1.0, 1.0, 1.0,
        ))
        engine.add_route(SupplyRoute(
            "a-first", "A", "C", TransportMode.ROAD, 1.0, 1.0, 1.0,
        ))
        engine.add_route(SupplyRoute(
            "a-second", "C", "D", TransportMode.ROAD, 1.0, 1.0, 1.0,
        ))
        path = engine.find_supply_route("A", "D")
        assert path is not None
        assert [route.route_id for route in path] == ["a-first", "a-second"]


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

    def test_flow_accounting_is_capacity_limited_and_resettable(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        path = engine.find_supply_route("A", "C")
        assert path is not None
        assert engine.remaining_route_capacity_tons(path, 2.0) == pytest.approx(16.0)

        engine.record_route_flow(path, quantity_tons=6.0, dt_hours=2.0)
        assert engine.get_route("r1").current_flow_tons_per_hour == pytest.approx(3.0)
        assert engine.get_route("r2").current_flow_tons_per_hour == pytest.approx(3.0)
        assert engine.remaining_route_capacity_tons(path, 2.0) == pytest.approx(10.0)

        with pytest.raises(ValueError, match="remaining route capacity"):
            engine.record_route_flow(path, quantity_tons=11.0, dt_hours=2.0)
        assert engine.get_route("r1").current_flow_tons_per_hour == pytest.approx(3.0)
        engine.begin_flow_interval()
        assert all(route.current_flow_tons_per_hour == 0.0 for route in path)


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

    def test_reachable_depots_are_sorted_by_transit_then_id(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("D-z", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("D-a", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("U", _POS_B, "UNIT"))
        for depot_id, route_id in (("D-z", "rz"), ("D-a", "ra")):
            engine.add_route(SupplyRoute(
                route_id, depot_id, "U", TransportMode.ROAD,
                5000.0, 10.0, 1.0,
            ))
        paths = engine.reachable_depot_paths("U", ["D-z", "D-a"])
        assert [depot_id for depot_id, _path in paths] == ["D-a", "D-z"]

    def test_depot_order_uses_same_low_condition_weight_as_pathfinding(
        self,
    ) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("D-bad", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("D-good", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("U", _POS_B, "UNIT"))
        engine.add_route(SupplyRoute(
            "r-bad", "D-bad", "U", TransportMode.ROAD,
            100.0, 10.0, 0.1, condition=0.001,
        ))
        engine.add_route(SupplyRoute(
            "r-good", "D-good", "U", TransportMode.ROAD,
            20_000.0, 10.0, 20.0, condition=1.0,
        ))

        paths = engine.reachable_depot_paths(
            "U",
            ["D-bad", "D-good"],
        )

        assert [depot_id for depot_id, _path in paths] == [
            "D-good",
            "D-bad",
        ]

    def test_direct_depot_paths_scan_only_inbound_routes_in_source_order(
        self,
    ) -> None:
        engine = _make_engine()
        for node_id, node_type in (
            ("D-slow", "DEPOT"),
            ("D-fast", "DEPOT"),
            ("D-indirect", "DEPOT"),
            ("X", "TRANSFER"),
            ("U", "UNIT"),
        ):
            engine.add_node(SupplyNode(node_id, _POS_A, node_type))
        engine.add_route(SupplyRoute(
            "r-slow", "D-slow", "U", TransportMode.ROAD,
            10_000.0, 10.0, 2.0,
        ))
        engine.add_route(SupplyRoute(
            "r-fast", "D-fast", "U", TransportMode.ROAD,
            5_000.0, 10.0, 1.0,
        ))
        engine.add_route(SupplyRoute(
            "r-indirect-a", "D-indirect", "X", TransportMode.ROAD,
            1_000.0, 10.0, 0.1,
        ))
        engine.add_route(SupplyRoute(
            "r-indirect-b", "X", "U", TransportMode.ROAD,
            1_000.0, 10.0, 0.1,
        ))

        paths = engine.reachable_direct_depot_paths(
            "U",
            ["D-indirect", "D-slow", "D-fast"],
        )

        assert [
            (depot_id, [route.route_id for route in path])
            for depot_id, path in paths
        ] == [
            ("D-fast", ["r-fast"]),
            ("D-slow", ["r-slow"]),
        ]


# ---------------------------------------------------------------------------
# Dynamic geometry
# ---------------------------------------------------------------------------


class TestGeometry:
    def test_node_position_update_recomputes_direct_route_geometry(self) -> None:
        engine = _make_engine()
        engine.add_node(SupplyNode("D", _POS_A, "DEPOT"))
        engine.add_node(SupplyNode("U", _POS_B, "UNIT"))
        engine.add_route(SupplyRoute(
            "r1", "D", "U", TransportMode.ROAD,
            5000.0, 10.0, 0.5,
            transport_speed_kph=10.0,
        ))

        engine.update_node_position("U", Position(30000.0, 40000.0, 0.0))

        assert engine.get_node("U").position == Position(30000.0, 40000.0, 0.0)
        assert engine.get_route("r1").distance_m == pytest.approx(50000.0)
        assert engine.get_route("r1").base_transit_time_hours == pytest.approx(5.0)

    def test_explicit_geometry_updates_persisted_speed_consistently(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)

        engine.update_route_geometry(
            "r1",
            distance_m=10000.0,
            base_transit_time_hours=5.0,
        )
        assert engine.get_route("r1").transport_speed_kph == pytest.approx(2.0)

        engine.update_node_position("B", Position(10000.0, 0.0))
        assert engine.get_route("r1").distance_m == pytest.approx(10000.0)
        assert engine.get_route("r1").base_transit_time_hours == pytest.approx(
            5.0,
        )


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

    def test_json_round_trip_preserves_complete_node_route_and_config(self) -> None:
        cfg = SupplyNetworkConfig(
            seasonal_degradation_rate=0.02,
            enable_capacity_constraints=True,
        )
        engine = _make_engine(config=cfg)
        engine.add_node(SupplyNode(
            "D", _POS_A, "DEPOT", linked_id="d1", echelon_level=3,
            infrastructure_id="railhead", throughput_tons_per_hour=55.0,
            side="blue",
        ))
        engine.add_node(SupplyNode("U", _POS_B, "UNIT", linked_id="u1", side="blue"))
        engine.add_route(SupplyRoute(
            "r1", "D", "U", TransportMode.ROAD,
            5000.0, 10.0, 0.5, condition=0.8,
            current_flow_tons_per_hour=2.5,
            infrastructure_ids=["bridge", "road"],
            transport_speed_kph=10.0,
        ))
        state = json.loads(json.dumps(engine.get_state()))

        restored = _make_engine()
        restored.set_state(state)

        assert restored.get_state() == state
        assert restored.get_node("D").side == "blue"
        assert restored.get_node("D").echelon_level == 3
        assert restored.get_node("D").infrastructure_id == "railhead"
        assert restored.get_node("D").throughput_tons_per_hour == 55.0
        assert restored.get_route("r1").current_flow_tons_per_hour == 2.5
        assert restored.get_route("r1").infrastructure_ids == ["bridge", "road"]
        assert restored.get_route("r1").transport_speed_kph == 10.0

    def test_corrupt_or_dangling_state_rejects_atomically(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        before = engine.get_state()
        corrupt = json.loads(json.dumps(before))
        corrupt["routes"]["r1"]["to_node"] = "missing"

        with pytest.raises(ValueError, match="unknown endpoint"):
            engine.set_state(corrupt)

        assert engine.get_state() == before

    def test_boolean_transport_mode_rejects_atomically(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        before = engine.get_state()
        corrupt = json.loads(json.dumps(before))
        corrupt["routes"]["r1"]["transport_mode"] = False

        with pytest.raises(ValueError, match="transport_mode"):
            engine.set_state(corrupt)

        assert engine.get_state() == before

    @pytest.mark.parametrize("invalid_mode", [0.0, "0"])
    def test_coercible_transport_mode_rejects_atomically(
        self,
        invalid_mode: object,
    ) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        before = engine.get_state()
        corrupt = json.loads(json.dumps(before))
        corrupt["routes"]["r1"]["transport_mode"] = invalid_mode

        with pytest.raises(ValueError, match="transport_mode"):
            engine.set_state(corrupt)

        assert engine.get_state() == before

    def test_degraded_route_with_prior_flow_round_trips(self) -> None:
        engine = _make_engine()
        _build_simple_network(engine)
        path = engine.find_supply_route("A", "C")
        assert path is not None
        engine.record_route_flow(path, quantity_tons=8.0, dt_hours=1.0)
        engine.update_route_condition("r1", 0.5)
        state = json.loads(json.dumps(engine.get_state()))

        restored = _make_engine()
        restored.set_state(state)

        assert restored.get_state() == state
        restored_path = restored.find_supply_route("A", "C")
        assert restored_path is not None
        assert (
            restored.remaining_route_capacity_tons(
                restored_path,
                dt_hours=1.0,
            )
            == 0.0
        )

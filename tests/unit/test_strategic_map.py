"""Tests for terrain.strategic_map — graph-based operational pathfinding."""

from __future__ import annotations

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.strategic_map import (
    StrategicEdge,
    StrategicMap,
    StrategicMapConfig,
    StrategicNode,
    StrategicNodeType,
)


def _simple_map() -> StrategicMap:
    nodes = [
        StrategicNode(node_id="A", node_type=StrategicNodeType.TOWN, position=(0, 0), name="Alpha"),
        StrategicNode(node_id="B", node_type=StrategicNodeType.CROSSROADS, position=(1000, 0), name="Bravo"),
        StrategicNode(node_id="C", node_type=StrategicNodeType.BRIDGE, position=(500, 500), name="Charlie"),
        StrategicNode(node_id="D", node_type=StrategicNodeType.PORT, position=(2000, 0), name="Delta"),
    ]
    edges = [
        StrategicEdge(edge_id="AB", from_node="A", to_node="B", distance=1000, movement_cost=10),
        StrategicEdge(edge_id="BC", from_node="B", to_node="C", distance=700, movement_cost=8),
        StrategicEdge(edge_id="AC", from_node="A", to_node="C", distance=700, movement_cost=7),
        StrategicEdge(edge_id="BD", from_node="B", to_node="D", distance=1000, movement_cost=10),
        StrategicEdge(edge_id="CD", from_node="C", to_node="D", distance=1500, movement_cost=20),
    ]
    return StrategicMap(StrategicMapConfig(nodes=nodes, edges=edges))


class TestShortestPath:
    def test_direct_path(self) -> None:
        sm = _simple_map()
        path = sm.shortest_path("A", "B")
        assert path == ["A", "B"]

    def test_shortest_path_via_intermediate(self) -> None:
        sm = _simple_map()
        path = sm.shortest_path("A", "D")
        cost = sm.shortest_path_cost("A", "D")
        # A→B→D = 20, A→C→D = 27, A→B→C→D = 38, A→C→B→D = 25
        assert cost == pytest.approx(20.0)
        assert path == ["A", "B", "D"]


class TestSpatialQueries:
    def test_nodes_within(self) -> None:
        sm = _simple_map()
        nearby = sm.nodes_within(Position(0, 0), radius=100)
        assert len(nearby) == 1
        assert nearby[0].node_id == "A"

    def test_nearest_node(self) -> None:
        sm = _simple_map()
        node, dist = sm.nearest_node(Position(100, 0))
        assert node.node_id == "A"

    def test_no_nodes_raises(self) -> None:
        sm = StrategicMap(StrategicMapConfig())
        with pytest.raises(ValueError):
            sm.nearest_node(Position(0, 0))


class TestDynamicUpdates:
    def test_update_edge_cost(self) -> None:
        sm = _simple_map()
        sm.update_edge_cost("AB", 100.0)  # "destroy bridge" on A→B
        # Now A→C→B→D should be cheaper
        path = sm.shortest_path("A", "D")
        assert "C" in path  # should route via C

    def test_unknown_edge_raises(self) -> None:
        sm = _simple_map()
        with pytest.raises(KeyError):
            sm.update_edge_cost("XY", 50.0)


class TestGraph:
    def test_graph_structure(self) -> None:
        sm = _simple_map()
        g = sm.graph
        assert len(g.nodes) == 4
        assert len(g.edges) == 5


class TestMaritimeEdges:
    def test_maritime_edge(self) -> None:
        nodes = [
            StrategicNode(node_id="P1", node_type=StrategicNodeType.PORT, position=(0, 0)),
            StrategicNode(node_id="S1", node_type=StrategicNodeType.SEA_ZONE, position=(5000, 0)),
            StrategicNode(node_id="P2", node_type=StrategicNodeType.PORT, position=(10000, 0)),
        ]
        edges = [
            StrategicEdge(edge_id="PS", from_node="P1", to_node="S1", distance=5000, movement_cost=5, is_maritime=True),
            StrategicEdge(edge_id="SP", from_node="S1", to_node="P2", distance=5000, movement_cost=5, is_maritime=True),
        ]
        sm = StrategicMap(StrategicMapConfig(nodes=nodes, edges=edges))
        path = sm.shortest_path("P1", "P2")
        assert path == ["P1", "S1", "P2"]


class TestStateRoundTrip:
    def test_edge_cost_round_trip(self) -> None:
        sm1 = _simple_map()
        sm1.update_edge_cost("AB", 50.0)
        state = sm1.get_state()

        sm2 = _simple_map()
        sm2.set_state(state)

        # Edge AB should now cost 50, making A→C→B (15) cheaper than A→B (50)
        assert sm2._edges["AB"].movement_cost == pytest.approx(50.0)
        path = sm2.shortest_path("A", "B")
        assert "C" in path  # routes via C since AB is expensive

"""Strategic-level graph for operational movement and planning.

Nodes represent key terrain features (towns, crossroads, ports, etc.).
Edges represent connections with movement costs reflecting distance,
terrain, and road type.  Built on networkx.
"""

from __future__ import annotations

import enum
import math

import networkx as nx
from pydantic import BaseModel

from stochastic_warfare.core.types import Meters, Position


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class StrategicNodeType(enum.IntEnum):
    """Types of strategic map nodes."""

    TOWN = 0
    CROSSROADS = 1
    BRIDGE = 2
    PASS = 3
    PORT = 4
    AIRFIELD = 5
    HILLTOP = 6
    CHOKEPOINT = 7
    SEA_ZONE = 8
    ANCHORAGE = 9


class StrategicNode(BaseModel):
    """A node on the strategic map."""

    node_id: str
    node_type: StrategicNodeType
    position: tuple[float, float]  # (easting, northing)
    name: str = ""


class StrategicEdge(BaseModel):
    """An edge (connection) on the strategic map."""

    edge_id: str
    from_node: str
    to_node: str
    distance: float  # metres
    movement_cost: float  # abstract cost units
    road_type: int | None = None
    is_maritime: bool = False


class StrategicMapConfig(BaseModel):
    """Strategic map configuration."""

    auto_generate: bool = False
    nodes: list[StrategicNode] | None = None
    edges: list[StrategicEdge] | None = None


# ---------------------------------------------------------------------------
# StrategicMap
# ---------------------------------------------------------------------------


class StrategicMap:
    """Graph-based strategic map for operational-level pathfinding.

    Parameters
    ----------
    config:
        Map configuration with explicit nodes/edges or auto-generation.
    classification, infrastructure, bathymetry, maritime:
        Optional terrain data for auto-generation (future).
    """

    def __init__(
        self,
        config: StrategicMapConfig,
        classification=None,
        infrastructure=None,
        bathymetry=None,
        maritime=None,
    ) -> None:
        self._config = config
        self._graph = nx.Graph()
        self._nodes: dict[str, StrategicNode] = {}
        self._edges: dict[str, StrategicEdge] = {}

        if config.nodes:
            for node in config.nodes:
                self._add_node(node)
        if config.edges:
            for edge in config.edges:
                self._add_edge(edge)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def graph(self) -> nx.Graph:
        return self._graph

    # ------------------------------------------------------------------
    # Pathfinding
    # ------------------------------------------------------------------

    def shortest_path(self, from_id: str, to_id: str) -> list[str]:
        """Shortest path as a list of node IDs."""
        return nx.shortest_path(self._graph, from_id, to_id, weight="cost")

    def shortest_path_cost(self, from_id: str, to_id: str) -> float:
        """Cost of the shortest path."""
        return nx.shortest_path_length(self._graph, from_id, to_id, weight="cost")

    # ------------------------------------------------------------------
    # Spatial queries
    # ------------------------------------------------------------------

    def nodes_within(self, pos: Position, radius: Meters) -> list[StrategicNode]:
        """Return nodes within *radius* of *pos*."""
        result: list[StrategicNode] = []
        for node in self._nodes.values():
            d = math.sqrt(
                (pos.easting - node.position[0]) ** 2
                + (pos.northing - node.position[1]) ** 2
            )
            if d <= radius:
                result.append(node)
        return result

    def nearest_node(self, pos: Position) -> tuple[StrategicNode, Meters]:
        """Return the nearest node and its distance."""
        best: tuple[StrategicNode, float] | None = None
        for node in self._nodes.values():
            d = math.sqrt(
                (pos.easting - node.position[0]) ** 2
                + (pos.northing - node.position[1]) ** 2
            )
            if best is None or d < best[1]:
                best = (node, d)
        if best is None:
            raise ValueError("No nodes in the strategic map")
        return best

    # ------------------------------------------------------------------
    # Dynamic updates
    # ------------------------------------------------------------------

    def update_edge_cost(self, edge_id: str, new_cost: float) -> None:
        """Update the movement cost of an edge (e.g. bridge destroyed)."""
        if edge_id not in self._edges:
            raise KeyError(f"Unknown edge: {edge_id}")
        edge = self._edges[edge_id]
        edge.movement_cost = new_cost
        self._graph[edge.from_node][edge.to_node]["cost"] = new_cost

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "edge_costs": {
                eid: e.movement_cost for eid, e in self._edges.items()
            },
        }

    def set_state(self, state: dict) -> None:
        for eid, cost in state["edge_costs"].items():
            if eid in self._edges:
                self.update_edge_cost(eid, cost)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _add_node(self, node: StrategicNode) -> None:
        self._nodes[node.node_id] = node
        self._graph.add_node(
            node.node_id,
            pos=node.position,
            node_type=node.node_type,
            name=node.name,
        )

    def _add_edge(self, edge: StrategicEdge) -> None:
        self._edges[edge.edge_id] = edge
        self._graph.add_edge(
            edge.from_node,
            edge.to_node,
            cost=edge.movement_cost,
            distance=edge.distance,
            edge_id=edge.edge_id,
            is_maritime=edge.is_maritime,
        )

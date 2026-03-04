"""Supply network -- directed graph connecting depots to consuming units.

Pull-based: units request supplies, the network finds the nearest depot
with available stock and dispatches via the shortest route.  No LP solver
-- optimization belongs to Phase 8 AI.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class TransportMode(enum.IntEnum):
    """Transport mode for a supply route."""

    ROAD = 0
    RAIL = 1
    AIR = 2
    SEA = 3
    CROSS_COUNTRY = 4


@dataclass
class SupplyRoute:
    """An edge in the supply network graph."""

    route_id: str
    from_node: str
    to_node: str
    transport_mode: TransportMode
    distance_m: float
    capacity_tons_per_hour: float
    base_transit_time_hours: float
    condition: float = 1.0  # 0-1, degrades from damage/weather
    current_flow_tons_per_hour: float = 0.0  # 12b-1: current utilization
    infrastructure_ids: list[str] = field(default_factory=list)  # 12b-1: linked infrastructure


@dataclass
class SupplyNode:
    """A node in the supply network graph."""

    node_id: str
    position: Position
    node_type: str  # DEPOT, UNIT, PORT, AIRFIELD
    linked_id: str | None = None  # depot_id or unit_id
    echelon_level: int = 0  # 12b-1: supply echelon (0=unit, 1=fwd, 2=main, 3=theater)
    infrastructure_id: str | None = None  # 12b-1: linked infrastructure
    throughput_tons_per_hour: float = 100.0  # 12b-1: node throughput cap


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class SupplyNetworkConfig(BaseModel):
    """Tuning parameters for supply network."""

    road_capacity_multiplier: float = 1.0
    rail_capacity_multiplier: float = 5.0
    cross_country_capacity_fraction: float = 0.1
    seasonal_degradation_rate: float = 0.01  # per hour in bad conditions

    # 12b-1: Capacity constraints & infrastructure coupling
    enable_capacity_constraints: bool = False
    enable_infrastructure_coupling: bool = False
    enable_min_cost_flow: bool = False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SupplyNetworkEngine:
    """Directed supply network graph with pull-based request routing.

    Parameters
    ----------
    event_bus : EventBus
        For future event publishing.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : SupplyNetworkConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: SupplyNetworkConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or SupplyNetworkConfig()
        self._graph: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, SupplyNode] = {}
        self._routes: dict[str, SupplyRoute] = {}

    # -- Graph construction --

    def add_node(self, node: SupplyNode) -> None:
        """Add a node to the supply network."""
        self._nodes[node.node_id] = node
        self._graph.add_node(node.node_id)
        logger.debug("Added supply node %s (%s)", node.node_id, node.node_type)

    def add_route(self, route: SupplyRoute) -> None:
        """Add a directed route (edge) to the supply network."""
        self._routes[route.route_id] = route
        # Edge weight = transit time adjusted by condition
        weight = route.base_transit_time_hours / max(route.condition, 0.01)
        self._graph.add_edge(
            route.from_node,
            route.to_node,
            route_id=route.route_id,
            weight=weight,
        )
        logger.debug(
            "Added route %s: %s -> %s (%.1f km, %.1f t/h)",
            route.route_id, route.from_node, route.to_node,
            route.distance_m / 1000, route.capacity_tons_per_hour,
        )

    def get_node(self, node_id: str) -> SupplyNode:
        """Return a node; raises ``KeyError`` if not found."""
        return self._nodes[node_id]

    def get_route(self, route_id: str) -> SupplyRoute:
        """Return a route; raises ``KeyError`` if not found."""
        return self._routes[route_id]

    def node_count(self) -> int:
        """Return the number of nodes."""
        return len(self._nodes)

    def route_count(self) -> int:
        """Return the number of routes."""
        return len(self._routes)

    # -- Pathfinding --

    def find_supply_route(
        self, from_id: str, to_id: str,
    ) -> list[SupplyRoute] | None:
        """Find the shortest (fastest) route between two nodes.

        Returns a list of ``SupplyRoute`` objects forming the path, or
        ``None`` if no path exists.
        """
        try:
            node_path = nx.shortest_path(
                self._graph, from_id, to_id, weight="weight",
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        routes: list[SupplyRoute] = []
        for i in range(len(node_path) - 1):
            edge_data = self._graph.edges[node_path[i], node_path[i + 1]]
            route = self._routes[edge_data["route_id"]]
            routes.append(route)
        return routes

    def compute_route_capacity(self, route_path: list[SupplyRoute]) -> float:
        """Return the bottleneck capacity (tons/hour) along a route path."""
        if not route_path:
            return 0.0
        return min(r.capacity_tons_per_hour * r.condition for r in route_path)

    def compute_route_transit_time(self, route_path: list[SupplyRoute]) -> float:
        """Return total transit time in hours along a route path."""
        if not route_path:
            return 0.0
        return sum(r.base_transit_time_hours / max(r.condition, 0.01) for r in route_path)

    # -- Route condition --

    def update_route_condition(self, route_id: str, condition: float) -> None:
        """Update a route's condition (0-1) and recalculate graph weight."""
        route = self._routes[route_id]
        route.condition = max(0.0, min(1.0, condition))
        weight = route.base_transit_time_hours / max(route.condition, 0.01)
        if self._graph.has_edge(route.from_node, route.to_node):
            self._graph.edges[route.from_node, route.to_node]["weight"] = weight

    def update(self, dt_hours: float, ground_state: int = 0) -> None:
        """Apply seasonal degradation to routes.

        Parameters
        ----------
        dt_hours:
            Time step in hours.
        ground_state:
            Ground condition (0=dry, 2=mud, 3=snow).
        """
        if ground_state < 2:
            return  # no degradation in dry/wet conditions
        rate = self._config.seasonal_degradation_rate
        for route in self._routes.values():
            if route.transport_mode in (TransportMode.ROAD, TransportMode.CROSS_COUNTRY):
                old = route.condition
                route.condition = max(0.0, route.condition - rate * dt_hours)
                if route.condition != old:
                    self.update_route_condition(route.route_id, route.condition)

    # -- Pull-based supply request --

    def find_nearest_depot_node(
        self, unit_node_id: str, depot_node_ids: list[str],
    ) -> tuple[str, list[SupplyRoute]] | None:
        """Find the nearest reachable depot to a unit node.

        Returns ``(depot_node_id, route_path)`` or ``None``.
        """
        best: tuple[str, list[SupplyRoute], float] | None = None
        for depot_id in depot_node_ids:
            path = self.find_supply_route(depot_id, unit_node_id)
            if path is not None:
                transit = self.compute_route_transit_time(path)
                if best is None or transit < best[2]:
                    best = (depot_id, path, transit)
        if best is None:
            return None
        return (best[0], best[1])

    # -- 12b-1: Infrastructure coupling & capacity-aware routing --

    def sync_infrastructure(self, infrastructure_manager: object) -> None:
        """Propagate infrastructure damage to route conditions.

        Parameters
        ----------
        infrastructure_manager:
            Object with ``get_feature_condition(feature_id) -> float`` method.
        """
        if not self._config.enable_infrastructure_coupling:
            return
        for route in self._routes.values():
            for infra_id in route.infrastructure_ids:
                if hasattr(infrastructure_manager, "get_feature_condition"):
                    cond = infrastructure_manager.get_feature_condition(infra_id)
                    if cond < route.condition:
                        self.update_route_condition(route.route_id, cond)

    def sever_route(self, route_id: str) -> list[str]:
        """Destroy a supply route. Returns IDs of units that may be affected.

        Sets condition to 0, effectively removing the route from pathfinding.
        """
        from stochastic_warfare.logistics.events import SupplyShortageEvent

        route = self._routes.get(route_id)
        if route is None:
            return []

        self.update_route_condition(route_id, 0.0)

        # Find affected unit nodes downstream of this route
        affected: list[str] = []
        try:
            downstream = nx.descendants(self._graph, route.to_node)
            for nid in downstream:
                node = self._nodes.get(nid)
                if node and node.node_type == "UNIT" and node.linked_id:
                    affected.append(node.linked_id)
            # Also the immediate to_node
            to_node = self._nodes.get(route.to_node)
            if to_node and to_node.node_type == "UNIT" and to_node.linked_id:
                affected.append(to_node.linked_id)
        except nx.NetworkXError:
            pass

        logger.info("Route %s severed, %d units affected", route_id, len(affected))
        return affected

    def find_alternate_route(
        self,
        from_id: str,
        to_id: str,
        blocked_routes: set[str] | None = None,
    ) -> list[SupplyRoute] | None:
        """Find alternate route avoiding blocked routes.

        Parameters
        ----------
        blocked_routes:
            Set of route_ids to exclude from pathfinding.

        Returns route path or None.
        """
        if blocked_routes is None:
            return self.find_supply_route(from_id, to_id)

        # Build temporary graph excluding blocked routes
        temp_graph = self._graph.copy()
        for route_id in blocked_routes:
            route = self._routes.get(route_id)
            if route and temp_graph.has_edge(route.from_node, route.to_node):
                temp_graph.remove_edge(route.from_node, route.to_node)

        try:
            node_path = nx.shortest_path(temp_graph, from_id, to_id, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        routes: list[SupplyRoute] = []
        for i in range(len(node_path) - 1):
            edge_data = temp_graph.edges[node_path[i], node_path[i + 1]]
            route = self._routes[edge_data["route_id"]]
            routes.append(route)
        return routes

    def compute_network_redundancy(self, node_id: str) -> float:
        """Compute redundancy score for a node (0=single point of failure, 1=fully redundant).

        Based on the number of independent paths from depot nodes.
        """
        depot_nodes = [
            nid for nid, n in self._nodes.items()
            if n.node_type == "DEPOT"
        ]
        if not depot_nodes:
            return 0.0

        paths_found = 0
        for depot_id in depot_nodes:
            try:
                # Check for at least 2 node-disjoint paths
                paths = list(nx.node_disjoint_paths(
                    self._graph, depot_id, node_id,
                ))
                paths_found += min(len(paths), 2)
            except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
                # Try simple connectivity
                if nx.has_path(self._graph, depot_id, node_id):
                    paths_found += 1

        if not depot_nodes:
            return 0.0

        # Score: 0 = no paths, 0.5 = one path, 1.0 = multiple paths
        max_possible = len(depot_nodes) * 2
        return min(1.0, paths_found / max(1, max_possible))

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "nodes": {
                nid: {
                    "node_id": n.node_id,
                    "position": list(n.position),
                    "node_type": n.node_type,
                    "linked_id": n.linked_id,
                }
                for nid, n in self._nodes.items()
            },
            "routes": {
                rid: {
                    "route_id": r.route_id,
                    "from_node": r.from_node,
                    "to_node": r.to_node,
                    "transport_mode": int(r.transport_mode),
                    "distance_m": r.distance_m,
                    "capacity_tons_per_hour": r.capacity_tons_per_hour,
                    "base_transit_time_hours": r.base_transit_time_hours,
                    "condition": r.condition,
                }
                for rid, r in self._routes.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._nodes.clear()
        self._routes.clear()
        self._graph.clear()
        for nid, nd in state["nodes"].items():
            node = SupplyNode(
                node_id=nd["node_id"],
                position=Position(*nd["position"]),
                node_type=nd["node_type"],
                linked_id=nd.get("linked_id"),
            )
            self.add_node(node)
        for rid, rd in state["routes"].items():
            route = SupplyRoute(
                route_id=rd["route_id"],
                from_node=rd["from_node"],
                to_node=rd["to_node"],
                transport_mode=TransportMode(rd["transport_mode"]),
                distance_m=rd["distance_m"],
                capacity_tons_per_hour=rd["capacity_tons_per_hour"],
                base_transit_time_hours=rd["base_transit_time_hours"],
                condition=rd["condition"],
            )
            self.add_route(route)

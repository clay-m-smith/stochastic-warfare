"""Supply network -- directed graph connecting depots to consuming units.

Pull-based: units request supplies, the network finds the nearest depot
with available stock and dispatches via the shortest route.  No LP solver
-- optimization belongs to Phase 8 AI.
"""

from __future__ import annotations

import enum
import heapq
import math
from dataclasses import dataclass, field
from typing import Iterable

import networkx as nx
import numpy as np
from pydantic import BaseModel, ConfigDict

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position

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
    transport_speed_kph: float | None = None


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
    side: str | None = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class SupplyNetworkConfig(BaseModel):
    """Tuning parameters for supply network."""

    model_config = ConfigDict(extra="forbid")

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
        _validate_config(self._config)
        self._graph: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, SupplyNode] = {}
        self._routes: dict[str, SupplyRoute] = {}

    # -- Graph construction --

    def add_node(self, node: SupplyNode) -> None:
        """Add a node to the supply network."""
        _validate_node(node)
        if node.node_id in self._nodes:
            raise ValueError(f"Duplicate supply node ID: {node.node_id}")
        self._nodes[node.node_id] = node
        self._graph.add_node(node.node_id)
        logger.debug("Added supply node %s (%s)", node.node_id, node.node_type)

    def add_route(self, route: SupplyRoute) -> None:
        """Add a directed route (edge) to the supply network."""
        _validate_route(route)
        if route.route_id in self._routes:
            raise ValueError(f"Duplicate supply route ID: {route.route_id}")
        missing = [
            node_id
            for node_id in (route.from_node, route.to_node)
            if node_id not in self._nodes
        ]
        if missing:
            raise ValueError(
                f"Supply route {route.route_id} has unknown endpoint(s): "
                f"{', '.join(missing)}",
            )
        if self._graph.has_edge(route.from_node, route.to_node):
            existing = self._graph.edges[route.from_node, route.to_node]["route_id"]
            raise ValueError(
                f"Parallel supply route {route.route_id} duplicates directed edge "
                f"{route.from_node}->{route.to_node} already owned by {existing}",
            )
        from_side = self._nodes[route.from_node].side
        to_side = self._nodes[route.to_node].side
        if from_side is not None and to_side is not None and from_side != to_side:
            raise ValueError(
                f"Supply route {route.route_id} crosses sides "
                f"{from_side!r}->{to_side!r}",
            )
        if route.transport_speed_kph is None:
            if route.distance_m > 0.0 and route.base_transit_time_hours > 0.0:
                route.transport_speed_kph = (
                    route.distance_m / 1000.0 / route.base_transit_time_hours
                )
            elif route.distance_m == 0.0 and route.base_transit_time_hours == 0.0:
                route.transport_speed_kph = None
            else:
                raise ValueError(
                    f"Supply route {route.route_id} cannot derive transport speed",
                )
        self._routes[route.route_id] = route
        # Edge weight = transit time adjusted by condition
        weight = _route_weight(route)
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

    def list_nodes(
        self,
        *,
        side: str | None = None,
        node_type: str | None = None,
    ) -> list[SupplyNode]:
        """Return nodes in deterministic ID order with optional filters."""
        return [
            self._nodes[node_id]
            for node_id in sorted(self._nodes)
            if (side is None or self._nodes[node_id].side == side)
            and (node_type is None or self._nodes[node_id].node_type == node_type)
        ]

    def list_routes(self) -> list[SupplyRoute]:
        """Return routes in deterministic ID order."""
        return [self._routes[route_id] for route_id in sorted(self._routes)]

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
        return self._find_supply_route(from_id, to_id, blocked_routes=frozenset())

    def _find_supply_route(
        self,
        from_id: str,
        to_id: str,
        *,
        blocked_routes: frozenset[str],
    ) -> list[SupplyRoute] | None:
        """Deterministic Dijkstra traversal with route-ID tie breaking."""
        if from_id not in self._nodes or to_id not in self._nodes:
            return None
        if from_id == to_id:
            return []

        queue: list[tuple[float, tuple[str, ...], str, tuple[str, ...]]] = [
            (0.0, (), from_id, (from_id,)),
        ]
        best: dict[str, tuple[float, tuple[str, ...]]] = {from_id: (0.0, ())}
        while queue:
            total, route_ids, node_id, node_path = heapq.heappop(queue)
            if best.get(node_id) != (total, route_ids):
                continue
            if node_id == to_id:
                return [self._routes[route_id] for route_id in route_ids]
            outgoing: list[tuple[str, str]] = []
            for successor in self._graph.successors(node_id):
                route_id = self._graph.edges[node_id, successor]["route_id"]
                outgoing.append((route_id, successor))
            for route_id, successor in sorted(outgoing):
                route = self._routes[route_id]
                if (
                    route_id in blocked_routes
                    or route.condition <= 0.0
                    or successor in node_path
                ):
                    continue
                candidate = (
                    total + _route_weight(route),
                    route_ids + (route_id,),
                )
                if successor not in best or candidate < best[successor]:
                    best[successor] = candidate
                    heapq.heappush(
                        queue,
                        (
                            candidate[0],
                            candidate[1],
                            successor,
                            node_path + (successor,),
                        ),
                    )
        return None

    def compute_route_capacity(self, route_path: list[SupplyRoute]) -> float:
        """Return the bottleneck capacity (tons/hour) along a route path."""
        if not route_path:
            return 0.0
        return min(r.capacity_tons_per_hour * r.condition for r in route_path)

    def compute_route_transit_time(self, route_path: list[SupplyRoute]) -> float:
        """Return total transit time in hours along a route path."""
        if not route_path:
            return 0.0
        return sum(_route_weight(route) for route in route_path)

    # -- Route condition --

    def update_route_condition(self, route_id: str, condition: float) -> None:
        """Update a route's condition (0-1) and recalculate graph weight."""
        route = self._routes[route_id]
        numeric_condition = _validate_finite(condition, "route condition")
        route.condition = max(0.0, min(1.0, numeric_condition))
        weight = _route_weight(route)
        if self._graph.has_edge(route.from_node, route.to_node):
            self._graph.edges[route.from_node, route.to_node]["weight"] = weight

    def update_node_position(self, node_id: str, position: Position) -> None:
        """Update a node and recompute geometry for every attached route."""
        _validate_position(position, f"supply node {node_id} position")
        node = self._nodes[node_id]
        attached_route_ids = sorted({
            data["route_id"]
            for _from_node, _to_node, data in (
                list(self._graph.in_edges(node_id, data=True))
                + list(self._graph.out_edges(node_id, data=True))
            )
        })
        staged_geometry: dict[str, tuple[float, float]] = {}
        for route_id in attached_route_ids:
            route = self._routes[route_id]
            from_position = (
                position
                if route.from_node == node_id
                else self._nodes[route.from_node].position
            )
            to_position = (
                position
                if route.to_node == node_id
                else self._nodes[route.to_node].position
            )
            distance = math.dist(from_position, to_position)
            speed = route.transport_speed_kph
            if speed is None:
                if route.distance_m > 0.0 and route.base_transit_time_hours > 0.0:
                    speed = route.distance_m / 1000.0 / route.base_transit_time_hours
                else:
                    raise ValueError(
                        f"Supply route {route_id} has no transport speed",
                    )
            staged_geometry[route_id] = (
                distance,
                distance / 1000.0 / speed,
            )

        node.position = position
        for route_id in attached_route_ids:
            route = self._routes[route_id]
            distance, transit_time = staged_geometry[route_id]
            route.distance_m = distance
            route.base_transit_time_hours = transit_time
            self._graph.edges[route.from_node, route.to_node]["weight"] = (
                _route_weight(route)
            )

    def update_route_geometry(
        self,
        route_id: str,
        distance_m: float | None = None,
        base_transit_time_hours: float | None = None,
    ) -> None:
        """Update direct-route geometry explicitly or from endpoint positions."""
        route = self._routes[route_id]
        if distance_m is None:
            distance = math.dist(
                self._nodes[route.from_node].position,
                self._nodes[route.to_node].position,
            )
        else:
            distance = _validate_nonnegative_finite(
                distance_m,
                f"supply route {route_id} distance",
            )

        if base_transit_time_hours is None:
            speed = route.transport_speed_kph
            if speed is None:
                raise ValueError(f"Supply route {route_id} has no transport speed")
            transit_time = distance / 1000.0 / speed
        else:
            transit_time = _validate_nonnegative_finite(
                base_transit_time_hours,
                f"supply route {route_id} transit time",
            )
            if distance > 0.0 and transit_time == 0.0:
                raise ValueError(
                    f"Supply route {route_id} cannot have zero transit time "
                    "for positive distance",
                )
            if distance == 0.0 and transit_time > 0.0:
                raise ValueError(
                    f"Supply route {route_id} cannot have positive transit "
                    "time for zero distance",
                )

        route.distance_m = distance
        route.base_transit_time_hours = transit_time
        if distance > 0.0:
            route.transport_speed_kph = (
                distance / 1000.0 / transit_time
            )
        self._graph.edges[route.from_node, route.to_node]["weight"] = (
            _route_weight(route)
        )

    def update(self, dt_hours: float, ground_state: int = 0) -> None:
        """Apply seasonal degradation to routes.

        Parameters
        ----------
        dt_hours:
            Time step in hours.
        ground_state:
            Ground condition (0=dry, 2=mud, 3=snow).
        """
        dt = _validate_nonnegative_finite(dt_hours, "network update hours")
        if ground_state < 2:
            return  # no degradation in dry/wet conditions
        rate = self._config.seasonal_degradation_rate
        for route_id in sorted(self._routes):
            route = self._routes[route_id]
            if route.transport_mode in (TransportMode.ROAD, TransportMode.CROSS_COUNTRY):
                old = route.condition
                route.condition = max(0.0, route.condition - rate * dt)
                if route.condition != old:
                    self.update_route_condition(route.route_id, route.condition)

    # -- Pull-based supply request --

    def find_nearest_depot_node(
        self, unit_node_id: str, depot_node_ids: list[str],
    ) -> tuple[str, list[SupplyRoute]] | None:
        """Find the nearest reachable depot to a unit node.

        Returns ``(depot_node_id, route_path)`` or ``None``.
        """
        candidates = self.reachable_depot_paths(unit_node_id, depot_node_ids)
        if not candidates:
            return None
        return candidates[0]

    def reachable_depot_paths(
        self,
        unit_node_id: str,
        depot_node_ids: Iterable[str],
    ) -> list[tuple[str, list[SupplyRoute]]]:
        """Return positive-capacity depot paths sorted by transit time and ID."""
        candidates: list[tuple[float, str, list[SupplyRoute]]] = []
        for depot_id in sorted(set(depot_node_ids)):
            path = self.find_supply_route(depot_id, unit_node_id)
            if path and self.compute_route_capacity(path) > 0.0:
                candidates.append((
                    self.compute_route_transit_time(path),
                    depot_id,
                    path,
                ))
        candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))
        return [
            (depot_id, path)
            for _transit, depot_id, path in candidates
        ]

    def reachable_direct_depot_paths(
        self,
        unit_node_id: str,
        depot_node_ids: Iterable[str],
    ) -> list[tuple[str, list[SupplyRoute]]]:
        """Return direct inbound depot routes in deterministic source order."""
        if unit_node_id not in self._nodes:
            return []
        depot_ids = set(depot_node_ids)
        candidates: list[tuple[float, str, str, SupplyRoute]] = []
        for from_node, _to_node, data in self._graph.in_edges(
            unit_node_id,
            data=True,
        ):
            if from_node not in depot_ids:
                continue
            route = self._routes[data["route_id"]]
            if (
                route.condition <= 0.0
                or route.capacity_tons_per_hour <= 0.0
            ):
                continue
            candidates.append(
                (
                    _route_weight(route),
                    from_node,
                    route.route_id,
                    route,
                ),
            )
        candidates.sort(
            key=lambda candidate: (
                candidate[0],
                candidate[1],
                candidate[2],
            ),
        )
        return [
            (depot_id, [route])
            for _transit, depot_id, _route_id, route in candidates
        ]

    def begin_flow_interval(self) -> None:
        """Reset deterministic per-route flow accounting for a new interval."""
        for route_id in sorted(self._routes):
            self._routes[route_id].current_flow_tons_per_hour = 0.0

    def remaining_route_capacity_tons(
        self,
        route_path: list[SupplyRoute],
        dt_hours: float,
    ) -> float:
        """Return remaining tonnage over *dt_hours* for a registered path."""
        dt = _validate_nonnegative_finite(dt_hours, "route capacity interval")
        if not route_path or dt == 0.0:
            return 0.0
        self._validate_registered_path(route_path)
        return min(
            max(
                0.0,
                (
                    route.capacity_tons_per_hour * route.condition
                    - route.current_flow_tons_per_hour
                ) * dt,
            )
            for route in route_path
        )

    def record_route_flow(
        self,
        route_path: list[SupplyRoute],
        quantity_tons: float,
        dt_hours: float,
    ) -> None:
        """Atomically record a delivered mass against every route in a path."""
        quantity = _validate_nonnegative_finite(
            quantity_tons,
            "route flow quantity",
        )
        dt = _validate_positive_finite(dt_hours, "route flow interval")
        self._validate_registered_path(route_path)
        remaining = self.remaining_route_capacity_tons(route_path, dt)
        if quantity > remaining + 1e-12:
            raise ValueError(
                f"Flow {quantity} tons exceeds remaining route capacity "
                f"{remaining} tons",
            )
        increment = quantity / dt
        for route in route_path:
            route.current_flow_tons_per_hour += increment

    def _validate_registered_path(self, route_path: list[SupplyRoute]) -> None:
        if not route_path:
            raise ValueError("Supply route path must not be empty")
        previous_to: str | None = None
        for route in route_path:
            registered = self._routes.get(route.route_id)
            if registered is not route:
                raise ValueError(
                    f"Supply route path contains unregistered route {route.route_id}",
                )
            if previous_to is not None and route.from_node != previous_to:
                raise ValueError("Supply route path is not contiguous")
            previous_to = route.to_node

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
        for route_id in sorted(self._routes):
            route = self._routes[route_id]
            for infra_id in sorted(route.infrastructure_ids):
                if hasattr(infrastructure_manager, "get_feature_condition"):
                    cond = infrastructure_manager.get_feature_condition(infra_id)
                    if cond < route.condition:
                        self.update_route_condition(route.route_id, cond)

    def sever_route(self, route_id: str) -> list[str]:
        """Destroy a supply route. Returns IDs of units that may be affected.

        Sets condition to 0, effectively removing the route from pathfinding.
        """

        route = self._routes.get(route_id)
        if route is None:
            return []

        self.update_route_condition(route_id, 0.0)

        # Find affected unit nodes downstream of this route
        affected: list[str] = []
        try:
            downstream = nx.descendants(self._graph, route.to_node)
            for nid in sorted(downstream):
                node = self._nodes.get(nid)
                if node and node.node_type == "UNIT" and node.linked_id:
                    affected.append(node.linked_id)
            # Also the immediate to_node
            to_node = self._nodes.get(route.to_node)
            if to_node and to_node.node_type == "UNIT" and to_node.linked_id:
                affected.append(to_node.linked_id)
        except nx.NetworkXError:
            pass

        affected = sorted(set(affected))
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
        return self._find_supply_route(
            from_id,
            to_id,
            blocked_routes=frozenset(blocked_routes),
        )

    def compute_network_redundancy(self, node_id: str) -> float:
        """Compute redundancy score for a node (0=single point of failure, 1=fully redundant).

        Based on the number of independent paths from depot nodes.
        """
        depot_nodes = [
            nid for nid, n in sorted(self._nodes.items())
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
            "config": self._config.model_dump(mode="json"),
            "nodes": {
                nid: {
                    "node_id": n.node_id,
                    "position": list(n.position),
                    "node_type": n.node_type,
                    "linked_id": n.linked_id,
                    "echelon_level": n.echelon_level,
                    "infrastructure_id": n.infrastructure_id,
                    "throughput_tons_per_hour": n.throughput_tons_per_hour,
                    "side": n.side,
                }
                for nid, n in (
                    (node_id, self._nodes[node_id])
                    for node_id in sorted(self._nodes)
                )
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
                    "current_flow_tons_per_hour": r.current_flow_tons_per_hour,
                    "infrastructure_ids": list(r.infrastructure_ids),
                    "transport_speed_kph": r.transport_speed_kph,
                }
                for rid, r in (
                    (route_id, self._routes[route_id])
                    for route_id in sorted(self._routes)
                )
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore a validated checkpoint without partial mutation."""
        if not isinstance(state, dict):
            raise TypeError("Supply network state must be a mapping")
        node_states = state.get("nodes")
        route_states = state.get("routes")
        if not isinstance(node_states, dict):
            raise ValueError("Supply network nodes must be a mapping")
        if not isinstance(route_states, dict):
            raise ValueError("Supply network routes must be a mapping")

        staged_config = self._config
        if "config" in state:
            try:
                staged_config = SupplyNetworkConfig.model_validate(state["config"])
            except Exception as exc:
                raise ValueError("Invalid supply network configuration state") from exc
            _validate_config(staged_config)

        staged_nodes: dict[str, SupplyNode] = {}
        for nid, nd in sorted(node_states.items()):
            _validate_identifier(nid, "supply node state key")
            if not isinstance(nd, dict):
                raise ValueError(f"Supply node state {nid} must be a mapping")
            declared_id = nd.get("node_id")
            if declared_id != nid:
                raise ValueError(
                    f"Supply node state key {nid!r} does not match node_id "
                    f"{declared_id!r}",
                )
            position_values = nd.get("position")
            if not isinstance(position_values, (list, tuple)):
                raise ValueError(f"Supply node {nid} position must be a sequence")
            try:
                position = Position(*position_values)
            except TypeError as exc:
                raise ValueError(
                    f"Supply node {nid} position must have two or three coordinates",
                ) from exc
            node = SupplyNode(
                node_id=nid,
                position=position,
                node_type=nd.get("node_type"),
                linked_id=nd.get("linked_id"),
                echelon_level=nd.get("echelon_level", 0),
                infrastructure_id=nd.get("infrastructure_id"),
                throughput_tons_per_hour=nd.get(
                    "throughput_tons_per_hour",
                    100.0,
                ),
                side=nd.get("side"),
            )
            _validate_node(node)
            staged_nodes[nid] = node

        staged_routes: dict[str, SupplyRoute] = {}
        staged_graph: nx.DiGraph = nx.DiGraph()
        staged_graph.add_nodes_from(sorted(staged_nodes))
        for rid, rd in sorted(route_states.items()):
            _validate_identifier(rid, "supply route state key")
            if not isinstance(rd, dict):
                raise ValueError(f"Supply route state {rid} must be a mapping")
            declared_id = rd.get("route_id")
            if declared_id != rid:
                raise ValueError(
                    f"Supply route state key {rid!r} does not match route_id "
                    f"{declared_id!r}",
                )
            raw_transport_mode = rd.get("transport_mode")
            if (
                isinstance(raw_transport_mode, bool)
                or not isinstance(raw_transport_mode, int)
            ):
                raise ValueError(
                    f"Supply route {rid} transport_mode must be an integer "
                    "enum value",
                )
            route = SupplyRoute(
                route_id=rid,
                from_node=rd.get("from_node"),
                to_node=rd.get("to_node"),
                transport_mode=TransportMode(raw_transport_mode),
                distance_m=rd.get("distance_m"),
                capacity_tons_per_hour=rd.get("capacity_tons_per_hour"),
                base_transit_time_hours=rd.get("base_transit_time_hours"),
                condition=rd.get("condition", 1.0),
                current_flow_tons_per_hour=rd.get(
                    "current_flow_tons_per_hour",
                    0.0,
                ),
                infrastructure_ids=rd.get("infrastructure_ids", []),
                transport_speed_kph=rd.get("transport_speed_kph"),
            )
            _validate_route(route)
            missing = [
                node_id
                for node_id in (route.from_node, route.to_node)
                if node_id not in staged_nodes
            ]
            if missing:
                raise ValueError(
                    f"Supply route {rid} has unknown endpoint(s): "
                    f"{', '.join(missing)}",
                )
            if staged_graph.has_edge(route.from_node, route.to_node):
                existing = staged_graph.edges[
                    route.from_node,
                    route.to_node,
                ]["route_id"]
                raise ValueError(
                    f"Parallel supply route {rid} duplicates directed edge "
                    f"{route.from_node}->{route.to_node} owned by {existing}",
                )
            from_side = staged_nodes[route.from_node].side
            to_side = staged_nodes[route.to_node].side
            if (
                from_side is not None
                and to_side is not None
                and from_side != to_side
            ):
                raise ValueError(
                    f"Supply route {rid} crosses sides "
                    f"{from_side!r}->{to_side!r}",
                )
            if route.transport_speed_kph is None:
                if route.distance_m > 0.0 and route.base_transit_time_hours > 0.0:
                    route.transport_speed_kph = (
                        route.distance_m
                        / 1000.0
                        / route.base_transit_time_hours
                    )
                elif not (
                    route.distance_m == 0.0
                    and route.base_transit_time_hours == 0.0
                ):
                    raise ValueError(
                        f"Supply route {rid} cannot derive transport speed",
                    )
            staged_routes[rid] = route
            staged_graph.add_edge(
                route.from_node,
                route.to_node,
                route_id=rid,
                weight=_route_weight(route),
            )

        self._config = staged_config
        self._nodes = staged_nodes
        self._routes = staged_routes
        self._graph = staged_graph


def _validate_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _validate_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _validate_positive_finite(value: object, label: str) -> float:
    number = _validate_finite(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _validate_nonnegative_finite(value: object, label: str) -> float:
    number = _validate_finite(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be non-negative")
    return number


def _validate_unit_interval(value: object, label: str) -> float:
    number = _validate_finite(value, label)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
    return number


def _validate_position(position: Position, label: str) -> None:
    if not isinstance(position, Position):
        raise ValueError(f"{label} must be a Position")
    for coordinate in position:
        _validate_finite(coordinate, label)


def _validate_node(node: SupplyNode) -> None:
    if not isinstance(node, SupplyNode):
        raise TypeError("Supply network nodes must be SupplyNode instances")
    _validate_identifier(node.node_id, "supply node ID")
    _validate_position(node.position, f"supply node {node.node_id} position")
    _validate_identifier(node.node_type, f"supply node {node.node_id} type")
    if node.linked_id is not None:
        _validate_identifier(
            node.linked_id,
            f"supply node {node.node_id} linked ID",
        )
    if isinstance(node.echelon_level, bool) or not isinstance(
        node.echelon_level,
        int,
    ) or node.echelon_level < 0:
        raise ValueError(
            f"supply node {node.node_id} echelon level must be non-negative",
        )
    if node.infrastructure_id is not None:
        _validate_identifier(
            node.infrastructure_id,
            f"supply node {node.node_id} infrastructure ID",
        )
    _validate_positive_finite(
        node.throughput_tons_per_hour,
        f"supply node {node.node_id} throughput",
    )
    if node.side is not None:
        _validate_identifier(node.side, f"supply node {node.node_id} side")


def _validate_route(route: SupplyRoute) -> None:
    if not isinstance(route, SupplyRoute):
        raise TypeError("Supply network routes must be SupplyRoute instances")
    _validate_identifier(route.route_id, "supply route ID")
    _validate_identifier(
        route.from_node,
        f"supply route {route.route_id} origin",
    )
    _validate_identifier(
        route.to_node,
        f"supply route {route.route_id} destination",
    )
    if route.from_node == route.to_node:
        raise ValueError(f"Supply route {route.route_id} cannot be a self-loop")
    if (
        isinstance(route.transport_mode, bool)
        or not isinstance(route.transport_mode, int)
    ):
        raise ValueError(
            f"Supply route {route.route_id} has invalid transport mode",
        )
    try:
        route.transport_mode = TransportMode(route.transport_mode)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Supply route {route.route_id} has invalid transport mode",
        ) from exc
    _validate_nonnegative_finite(
        route.distance_m,
        f"supply route {route.route_id} distance",
    )
    _validate_positive_finite(
        route.capacity_tons_per_hour,
        f"supply route {route.route_id} capacity",
    )
    _validate_nonnegative_finite(
        route.base_transit_time_hours,
        f"supply route {route.route_id} transit time",
    )
    if route.distance_m > 0.0 and route.base_transit_time_hours == 0.0:
        raise ValueError(
            f"Supply route {route.route_id} has zero transit time "
            "for positive distance",
        )
    _validate_unit_interval(
        route.condition,
        f"supply route {route.route_id} condition",
    )
    current_flow = _validate_nonnegative_finite(
        route.current_flow_tons_per_hour,
        f"supply route {route.route_id} current flow",
    )
    # Flow records the completed interval. A later damage/ground update may
    # lower current condition without invalidating that historical accounting.
    if current_flow > route.capacity_tons_per_hour + 1e-12:
        raise ValueError(
            f"Supply route {route.route_id} current flow exceeds capacity",
        )
    if not isinstance(route.infrastructure_ids, list):
        raise ValueError(
            f"Supply route {route.route_id} infrastructure IDs must be a list",
        )
    seen_infrastructure: set[str] = set()
    for infrastructure_id in route.infrastructure_ids:
        _validate_identifier(
            infrastructure_id,
            f"supply route {route.route_id} infrastructure ID",
        )
        if infrastructure_id in seen_infrastructure:
            raise ValueError(
                f"Supply route {route.route_id} contains duplicate "
                f"infrastructure ID {infrastructure_id}",
            )
        seen_infrastructure.add(infrastructure_id)
    route.infrastructure_ids = sorted(route.infrastructure_ids)
    if route.transport_speed_kph is not None:
        _validate_positive_finite(
            route.transport_speed_kph,
            f"supply route {route.route_id} transport speed",
        )


def _validate_config(config: SupplyNetworkConfig) -> None:
    _validate_positive_finite(
        config.road_capacity_multiplier,
        "road capacity multiplier",
    )
    _validate_positive_finite(
        config.rail_capacity_multiplier,
        "rail capacity multiplier",
    )
    _validate_unit_interval(
        config.cross_country_capacity_fraction,
        "cross-country capacity fraction",
    )
    _validate_nonnegative_finite(
        config.seasonal_degradation_rate,
        "seasonal degradation rate",
    )
    for field_name in (
        "enable_capacity_constraints",
        "enable_infrastructure_coupling",
        "enable_min_cost_flow",
    ):
        if not isinstance(getattr(config, field_name), bool):
            raise ValueError(f"{field_name} must be a boolean")


def _route_weight(route: SupplyRoute) -> float:
    if route.condition <= 0.0:
        return math.inf
    return route.base_transit_time_hours / route.condition

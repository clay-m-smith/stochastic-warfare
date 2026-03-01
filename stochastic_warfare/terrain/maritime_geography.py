"""Maritime geography: coastlines, ports, straits, sea lanes, anchorages.

Coastline is modelled as a shapely Polygon (sea area).  Ports, straits, sea
lanes, and anchorages are point/line features with mutable condition (ports).
"""

from __future__ import annotations

import math

from pydantic import BaseModel
from shapely.geometry import LineString, Point, Polygon

from stochastic_warfare.core.types import Meters, Position


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Port(BaseModel):
    """A port facility."""

    port_id: str
    name: str
    position: tuple[float, float]  # (easting, northing)
    max_draft: float  # meters
    berths: int = 4
    crane_capacity_tons: float = 50.0
    throughput_tons_per_day: float = 5000.0
    condition: float = 1.0


class Strait(BaseModel):
    """A strait or narrow passage."""

    strait_id: str
    name: str
    centerline: list[tuple[float, float]]
    width: float  # meters
    depth: float  # meters


class SeaLane(BaseModel):
    """A shipping lane."""

    lane_id: str
    name: str
    waypoints: list[tuple[float, float]]


class Anchorage(BaseModel):
    """A sheltered anchorage area."""

    anchorage_id: str
    position: tuple[float, float]
    radius: float  # meters
    max_draft: float
    shelter_factor: float  # 0–1 (1 = fully sheltered)


# ---------------------------------------------------------------------------
# MaritimeGeography
# ---------------------------------------------------------------------------


class MaritimeGeography:
    """Manages maritime geographic features.

    Parameters
    ----------
    coastline:
        Polygon vertices defining the sea area.  Points inside the polygon
        are considered sea; outside are land.  Can be None for all-sea.
    ports, straits, sea_lanes, anchorages:
        Lists of maritime features.
    """

    def __init__(
        self,
        coastline: list[tuple[float, float]] | None = None,
        ports: list[Port] | None = None,
        straits: list[Strait] | None = None,
        sea_lanes: list[SeaLane] | None = None,
        anchorages: list[Anchorage] | None = None,
    ) -> None:
        self._coastline_poly: Polygon | None = (
            Polygon(coastline) if coastline else None
        )
        self._ports: dict[str, Port] = {p.port_id: p for p in (ports or [])}
        self._straits: dict[str, Strait] = {s.strait_id: s for s in (straits or [])}
        self._strait_polys: dict[str, Polygon] = {}
        for sid, s in self._straits.items():
            line = LineString(s.centerline)
            self._strait_polys[sid] = line.buffer(s.width / 2)
        self._sea_lanes: dict[str, SeaLane] = {l.lane_id: l for l in (sea_lanes or [])}
        self._sea_lane_lines: dict[str, LineString] = {
            lid: LineString(l.waypoints) for lid, l in self._sea_lanes.items()
        }
        self._anchorages: dict[str, Anchorage] = {
            a.anchorage_id: a for a in (anchorages or [])
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_sea(self, pos: Position) -> bool:
        """True if *pos* is within the coastline polygon (i.e. at sea)."""
        if self._coastline_poly is None:
            return True  # all-sea scenario
        return self._coastline_poly.contains(Point(pos.easting, pos.northing))

    def nearest_port(self, pos: Position) -> tuple[Port, Meters] | None:
        """Return the nearest non-destroyed port and its distance."""
        best: tuple[Port, float] | None = None
        for port in self._ports.values():
            if port.condition <= 0:
                continue
            d = math.sqrt(
                (pos.easting - port.position[0]) ** 2
                + (pos.northing - port.position[1]) ** 2
            )
            if best is None or d < best[1]:
                best = (port, d)
        return best

    def ports_within(self, pos: Position, radius: Meters) -> list[Port]:
        """Return all non-destroyed ports within *radius* of *pos*."""
        result: list[Port] = []
        for port in self._ports.values():
            if port.condition <= 0:
                continue
            d = math.sqrt(
                (pos.easting - port.position[0]) ** 2
                + (pos.northing - port.position[1]) ** 2
            )
            if d <= radius:
                result.append(port)
        return result

    def strait_at(self, pos: Position) -> Strait | None:
        """Return the strait containing *pos*, if any."""
        pt = Point(pos.easting, pos.northing)
        for sid, poly in self._strait_polys.items():
            if poly.contains(pt):
                return self._straits[sid]
        return None

    def nearest_sea_lane(self, pos: Position) -> tuple[SeaLane, Meters] | None:
        """Return the nearest sea lane and distance."""
        pt = Point(pos.easting, pos.northing)
        best: tuple[SeaLane, float] | None = None
        for lid, line in self._sea_lane_lines.items():
            d = line.distance(pt)
            if best is None or d < best[1]:
                best = (self._sea_lanes[lid], d)
        return best

    def anchorages_near(self, pos: Position, radius: Meters) -> list[Anchorage]:
        """Return anchorages within *radius* of *pos*."""
        result: list[Anchorage] = []
        for anch in self._anchorages.values():
            d = math.sqrt(
                (pos.easting - anch.position[0]) ** 2
                + (pos.northing - anch.position[1]) ** 2
            )
            if d <= radius:
                result.append(anch)
        return result

    # ------------------------------------------------------------------
    # Mutable state
    # ------------------------------------------------------------------

    def damage_port(self, port_id: str, amount: float) -> None:
        """Reduce port condition."""
        if port_id not in self._ports:
            raise KeyError(f"Unknown port: {port_id}")
        port = self._ports[port_id]
        port.condition = max(0.0, port.condition - amount)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "port_conditions": {
                pid: p.condition for pid, p in self._ports.items()
            },
        }

    def set_state(self, state: dict) -> None:
        for pid, cond in state["port_conditions"].items():
            if pid in self._ports:
                self._ports[pid].condition = cond

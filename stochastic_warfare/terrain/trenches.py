"""WW1 trench system — spatial overlay with cover and movement modifiers.

Trench segments are represented as :class:`shapely.LineString` geometries
with :class:`shapely.STRtree` indexing for O(log n) spatial queries.
Provides ``cover_value_at()`` and ``movement_factor_at()`` consumed by
combat, movement, and detection modules.

Trenches are a **terrain overlay**, not heightmap features (trench depth
is below cell resolution).  Bombardment degrades trench condition, which
reduces cover and movement bonuses.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from shapely import STRtree
from shapely.geometry import LineString, Point

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TrenchType(enum.IntEnum):
    """Classification of trench segments."""

    FIRE_TRENCH = 0
    SUPPORT_TRENCH = 1
    COMMUNICATION_TRENCH = 2
    SAP = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TrenchConfig(BaseModel):
    """Configuration for trench system behaviour."""

    cover_fire_trench: float = 0.85
    cover_support_trench: float = 0.70
    cover_communication_trench: float = 0.50
    cover_sap: float = 0.60

    movement_along: float = 0.5
    """Speed multiplier when moving along a trench."""
    movement_crossing: float = 0.3
    """Speed multiplier when crossing over a trench."""
    movement_no_mans_land: float = 0.2
    """Speed multiplier in no-man's-land."""

    trench_query_radius_m: float = 5.0
    """Distance from trench centreline within which a unit is 'in' the trench."""

    no_mans_land_width_m: float = 200.0
    """Default width of no-man's-land zone between opposing trench lines."""

    bombardment_condition_loss_per_intensity: float = 0.15
    """Condition loss per unit bombardment intensity (0–1)."""


_COVER_BY_TYPE: dict[TrenchType, str] = {
    TrenchType.FIRE_TRENCH: "cover_fire_trench",
    TrenchType.SUPPORT_TRENCH: "cover_support_trench",
    TrenchType.COMMUNICATION_TRENCH: "cover_communication_trench",
    TrenchType.SAP: "cover_sap",
}


# ---------------------------------------------------------------------------
# Trench segment model
# ---------------------------------------------------------------------------


class TrenchSegment(BaseModel):
    """A single trench segment."""

    trench_id: str
    trench_type: TrenchType
    side: str
    points: list[list[float]]
    """Vertices [[easting, northing], ...]."""
    width_m: float = 2.0
    condition: float = 1.0
    """0.0 = destroyed, 1.0 = pristine."""
    has_wire: bool = False
    has_dugout: bool = False


# ---------------------------------------------------------------------------
# Query result
# ---------------------------------------------------------------------------


@dataclass
class TrenchQueryResult:
    """Result of a spatial trench query at a position."""

    in_trench: bool = False
    trench_type: TrenchType | None = None
    trench_id: str | None = None
    side: str | None = None
    cover_value: float = 0.0
    movement_factor: float = 1.0
    condition: float = 0.0
    has_wire: bool = False
    has_dugout: bool = False


# ---------------------------------------------------------------------------
# Trench System Engine
# ---------------------------------------------------------------------------


class TrenchSystemEngine:
    """Manages trench segments with STRtree-backed spatial queries.

    Parameters
    ----------
    config:
        Trench system configuration.
    """

    def __init__(self, config: TrenchConfig | None = None) -> None:
        self._config = config or TrenchConfig()
        self._segments: dict[str, TrenchSegment] = {}
        self._geometries: dict[str, LineString] = {}
        self._tree: STRtree | None = None
        self._seg_ids: list[str] = []
        self._geom_list: list[LineString] = []
        self._no_mans_land_zones: list[dict[str, Any]] = []
        self._dirty = True

    # ── Mutations ─────────────────────────────────────────────────────

    def add_trench(self, segment: TrenchSegment) -> None:
        """Add a trench segment."""
        self._segments[segment.trench_id] = segment
        pts = [(p[0], p[1]) for p in segment.points]
        self._geometries[segment.trench_id] = LineString(pts)
        self._dirty = True

    def _rebuild_index(self) -> None:
        """Rebuild the STRtree spatial index."""
        self._seg_ids = list(self._geometries.keys())
        self._geom_list = [self._geometries[sid] for sid in self._seg_ids]
        self._tree = STRtree(self._geom_list) if self._seg_ids else None
        self._dirty = False

    def add_no_mans_land(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        width_m: float | None = None,
    ) -> None:
        """Define a no-man's-land zone between two points."""
        w = width_m or self._config.no_mans_land_width_m
        self._no_mans_land_zones.append({
            "line": LineString([start, end]),
            "width_m": w,
        })

    # ── Spatial queries ───────────────────────────────────────────────

    def query_trench(self, easting: float, northing: float) -> TrenchQueryResult:
        """Query trench presence at a position.

        Returns the nearest trench within ``trench_query_radius_m``, or
        a default result if none found.
        """
        if self._dirty:
            self._rebuild_index()

        if self._tree is None:
            return TrenchQueryResult()

        pt = Point(easting, northing)
        radius = self._config.trench_query_radius_m

        # Find candidate trenches within radius
        indices = self._tree.query(pt.buffer(radius))
        best_dist = float("inf")
        best_idx: int | None = None
        for i in indices:
            d = self._geom_list[i].distance(pt)
            if d <= radius and d < best_dist:
                best_dist = d
                best_idx = i

        if best_idx is None:
            return TrenchQueryResult()

        seg_id = self._seg_ids[best_idx]
        seg = self._segments[seg_id]

        # Cover value scaled by condition
        cover_attr = _COVER_BY_TYPE.get(TrenchType(seg.trench_type), "cover_fire_trench")
        base_cover = getattr(self._config, cover_attr, 0.5)
        cover = base_cover * seg.condition

        return TrenchQueryResult(
            in_trench=True,
            trench_type=TrenchType(seg.trench_type),
            trench_id=seg.trench_id,
            side=seg.side,
            cover_value=cover,
            movement_factor=self._config.movement_along,
            condition=seg.condition,
            has_wire=seg.has_wire,
            has_dugout=seg.has_dugout,
        )

    def cover_value_at(self, easting: float, northing: float) -> float:
        """Return cover value at a position (0 if not in trench)."""
        result = self.query_trench(easting, northing)
        return result.cover_value

    def movement_factor_at(
        self,
        easting: float,
        northing: float,
        heading_deg: float = 0.0,
    ) -> float:
        """Return movement speed factor at a position.

        Parameters
        ----------
        easting, northing:
            Position in metres.
        heading_deg:
            Movement heading in degrees (0 = north, 90 = east).

        Returns
        -------
        Speed multiplier (< 1.0 means slower).
        """
        result = self.query_trench(easting, northing)

        if not result.in_trench:
            # Check no-man's-land
            if self.is_no_mans_land(easting, northing):
                return self._config.movement_no_mans_land
            return 1.0

        # Determine if moving along or across the trench
        seg = self._segments[result.trench_id]  # type: ignore[arg-type]
        geom = self._geometries[result.trench_id]  # type: ignore[arg-type]

        # Approximate trench bearing at nearest point
        pt = Point(easting, northing)
        proj = geom.project(pt)
        # Get two points along trench near projection
        p1 = geom.interpolate(max(0, proj - 1.0))
        p2 = geom.interpolate(min(geom.length, proj + 1.0))
        trench_bearing = math.degrees(math.atan2(
            p2.x - p1.x, p2.y - p1.y,
        )) % 360.0

        # Angle difference
        diff = abs(heading_deg - trench_bearing) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff

        # Along (< 30°) vs crossing (> 60°), interpolate between
        if diff < 30.0:
            return self._config.movement_along
        elif diff > 60.0:
            return self._config.movement_crossing
        else:
            t = (diff - 30.0) / 30.0
            return (
                self._config.movement_along * (1.0 - t)
                + self._config.movement_crossing * t
            )

    def is_no_mans_land(self, easting: float, northing: float) -> bool:
        """Check if position is in a defined no-man's-land zone."""
        pt = Point(easting, northing)
        for zone in self._no_mans_land_zones:
            line: LineString = zone["line"]
            w: float = zone["width_m"]
            if line.distance(pt) <= w / 2:
                return True
        return False

    def apply_bombardment(
        self,
        center_easting: float,
        center_northing: float,
        radius_m: float,
        intensity: float,
    ) -> list[str]:
        """Degrade trench condition within bombardment area.

        Parameters
        ----------
        center_easting, center_northing:
            Centre of bombardment area.
        radius_m:
            Radius of bombardment effect.
        intensity:
            Bombardment intensity (0–1).

        Returns
        -------
        List of affected trench IDs.
        """
        if self._dirty:
            self._rebuild_index()

        if self._tree is None:
            return []

        pt = Point(center_easting, center_northing)
        indices = self._tree.query(pt.buffer(radius_m))
        affected: list[str] = []

        loss = self._config.bombardment_condition_loss_per_intensity * intensity

        for i in indices:
            geom = self._geom_list[i]
            if geom.distance(pt) <= radius_m:
                seg_id = self._seg_ids[i]
                seg = self._segments[seg_id]
                seg.condition = max(0.0, seg.condition - loss)
                affected.append(seg_id)

        return affected

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "segments": {
                sid: {
                    "trench_id": seg.trench_id,
                    "trench_type": int(seg.trench_type),
                    "side": seg.side,
                    "points": seg.points,
                    "width_m": seg.width_m,
                    "condition": seg.condition,
                    "has_wire": seg.has_wire,
                    "has_dugout": seg.has_dugout,
                }
                for sid, seg in self._segments.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._segments.clear()
        self._geometries.clear()
        for sid, sdata in state.get("segments", {}).items():
            seg = TrenchSegment(**sdata)
            self._segments[sid] = seg
            pts = [(p[0], p[1]) for p in seg.points]
            self._geometries[sid] = LineString(pts)
        self._dirty = True

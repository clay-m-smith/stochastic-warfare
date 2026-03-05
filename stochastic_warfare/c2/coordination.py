"""Fire support coordination and airspace deconfliction.

Data structures and geometric check functions ONLY. No fire support
planning logic (Phase 8).

Coordination measures: FSCL, CFL, NFA, RFA, FFA, BOUNDARY,
AIRSPACE_CORRIDOR, MISSILE_FLIGHT_CORRIDOR.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.events import CoordinationViolationEvent, JIPTLGeneratedEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CoordinationMeasureType(enum.IntEnum):
    """Fire support coordination measure types."""

    FSCL = 0           # Fire Support Coordination Line
    CFL = 1            # Coordinated Fire Line
    NFA = 2            # No Fire Area
    RFA = 3            # Restrictive Fire Area (requires coordination)
    FFA = 4            # Free Fire Area
    BOUNDARY = 5       # Unit boundary
    AIRSPACE_CORRIDOR = 6
    MISSILE_FLIGHT_CORRIDOR = 7


class FireType(enum.IntEnum):
    """Type of fire for coordination checks."""

    DIRECT = 0
    INDIRECT = 1
    AIR_DELIVERED = 2
    NAVAL_GUNFIRE = 3
    MISSILE = 4


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoordinationMeasure:
    """A single fire support coordination measure."""

    measure_id: str
    measure_type: CoordinationMeasureType
    center: Position  # For area measures
    radius_m: float  # For area measures
    line_start: Position | None = None  # For linear measures (FSCL, CFL, BOUNDARY)
    line_end: Position | None = None
    owning_unit: str = ""
    requires_coordination_with: str = ""  # For RFA


# ---------------------------------------------------------------------------
# 12a-5: JTAC/FAC Observer Model
# ---------------------------------------------------------------------------


@dataclass
class JTACObservation:
    """JTAC observation of a target."""

    jtac_id: str
    target_id: str
    estimated_position: Position
    position_error_m: float
    has_los: bool
    range_m: float


# ---------------------------------------------------------------------------
# 12a-6: JIPTL (Joint Integrated Prioritized Target List)
# ---------------------------------------------------------------------------


@dataclass
class TargetNomination:
    """A nominated target for the JIPTL."""

    target_id: str
    target_type: str  # "armor", "artillery", "c2_node", "sam_site", "logistics"
    position: Position
    priority: int  # 1 = highest
    time_sensitive: bool = False
    nominating_unit: str = ""


@dataclass
class TargetAllocation:
    """Allocation of a shooter to a target from the JIPTL."""

    target_id: str
    shooter_id: str
    score: float
    range_m: float


class JIPTLConfig(BaseModel):
    """Configuration for JIPTL target prioritization."""

    target_type_weights: dict[str, float] = {
        "c2_node": 1.5,
        "sam_site": 1.3,
        "armor": 1.0,
        "artillery": 1.2,
        "logistics": 0.8,
    }
    time_sensitive_boost: float = 2.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CoordinationEngine:
    """Manages fire support coordination measures.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``CoordinationViolationEvent``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        los_engine: Any | None = None,
        jiptl_config: JIPTLConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._los_engine = los_engine
        self._jiptl_config = jiptl_config or JIPTLConfig()
        self._measures: dict[str, CoordinationMeasure] = {}
        self._fscl_line: tuple[Position, Position] | None = None
        self._fscl_waypoints: list[Position] | None = None
        # 12a-5: JTAC registry
        self._jtacs: dict[str, Position] = {}
        # 12a-6: target nominations
        self._nominations: list[TargetNomination] = []

    # -- Measure management -------------------------------------------------

    def add_measure(self, measure: CoordinationMeasure) -> None:
        """Add a coordination measure."""
        self._measures[measure.measure_id] = measure

    def remove_measure(self, measure_id: str) -> None:
        """Remove a coordination measure."""
        del self._measures[measure_id]

    def set_fscl(
        self,
        start: Position,
        end: Position,
        waypoints: list[Position] | None = None,
    ) -> None:
        """Set the Fire Support Coordination Line.

        Parameters
        ----------
        waypoints:
            Optional polyline waypoints for non-linear FSCL.
            When provided, the FSCL is the polyline [start, *waypoints, end].
        """
        self._fscl_line = (start, end)
        if waypoints:
            self._fscl_waypoints = [start] + list(waypoints) + [end]
        else:
            self._fscl_waypoints = None

    def get_fscl(self) -> tuple[Position, Position] | None:
        """Return the FSCL line, or None if not set."""
        return self._fscl_line

    # -- Geometric checks ---------------------------------------------------

    def is_beyond_fscl(self, pos: Position) -> bool:
        """Check if a position is beyond (north of) the FSCL.

        When a polyline FSCL is set, uses cross-product side-of-line test
        against the nearest segment. Otherwise uses midpoint northing.
        """
        if self._fscl_line is None:
            return False

        if self._fscl_waypoints is not None:
            return self._is_beyond_polyline_fscl(pos)

        fscl_northing = (
            self._fscl_line[0].northing + self._fscl_line[1].northing
        ) / 2
        return pos.northing > fscl_northing

    def _is_beyond_polyline_fscl(self, pos: Position) -> bool:
        """Side-of-line test against nearest segment of polyline FSCL.

        Convention: "beyond" = left side of the polyline when walking
        from first to last waypoint (typically north).
        """
        wps = self._fscl_waypoints
        if not wps or len(wps) < 2:
            return False

        # Find nearest segment
        best_dist_sq = float("inf")
        best_cross = 0.0
        for i in range(len(wps) - 1):
            ax, ay = wps[i].easting, wps[i].northing
            bx, by = wps[i + 1].easting, wps[i + 1].northing
            px, py = pos.easting, pos.northing

            # Cross product: positive = left of line (beyond)
            cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)

            # Distance to segment (for nearest-segment selection)
            dx, dy = bx - ax, by - ay
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-12:
                dist_sq = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
                proj_x = ax + t * dx
                proj_y = ay + t * dy
                dist_sq = (px - proj_x) ** 2 + (py - proj_y) ** 2

            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_cross = cross

        return best_cross > 0.0

    def _is_in_area(self, pos: Position, measure: CoordinationMeasure) -> bool:
        """Check if position is within an area measure's radius."""
        dx = pos.easting - measure.center.easting
        dy = pos.northing - measure.center.northing
        return math.sqrt(dx * dx + dy * dy) <= measure.radius_m

    def _crosses_boundary(
        self,
        current_pos: Position,
        dest: Position,
        measure: CoordinationMeasure,
    ) -> bool:
        """Check if movement from current_pos to dest crosses a boundary line."""
        if measure.line_start is None or measure.line_end is None:
            return False
        # Simplified: check if the two positions are on different sides
        # of the line defined by line_start → line_end
        ls, le = measure.line_start, measure.line_end
        d1 = (
            (le.easting - ls.easting) * (current_pos.northing - ls.northing)
            - (le.northing - ls.northing) * (current_pos.easting - ls.easting)
        )
        d2 = (
            (le.easting - ls.easting) * (dest.northing - ls.northing)
            - (le.northing - ls.northing) * (dest.easting - ls.easting)
        )
        return (d1 * d2) < 0  # Different signs = crossing

    # -- Authorization checks -----------------------------------------------

    def check_fire_clearance(
        self,
        shooter_id: str,
        target_pos: Position,
        fire_type: FireType,
        timestamp: datetime | None = None,
    ) -> tuple[bool, str]:
        """Check if fires are cleared at the target position.

        Returns (cleared, reason).
        """
        from datetime import timezone

        ts = timestamp or datetime.now(tz=timezone.utc)

        for m in self._measures.values():
            if not self._is_in_area(target_pos, m):
                continue

            if m.measure_type == CoordinationMeasureType.NFA:
                self._publish_violation(shooter_id, "NFA", m.measure_id, ts)
                return False, f"target_in_nfa_{m.measure_id}"

            if m.measure_type == CoordinationMeasureType.RFA:
                # RFA requires coordination — flag but don't auto-block
                return False, f"requires_coordination_{m.measure_id}"

            if m.measure_type == CoordinationMeasureType.FFA:
                return True, "free_fire_area"

        # FSCL check (12a-4: added MISSILE to gating)
        if self._fscl_line is not None:
            if not self.is_beyond_fscl(target_pos):
                if fire_type in (FireType.AIR_DELIVERED, FireType.NAVAL_GUNFIRE, FireType.MISSILE):
                    return False, "short_of_fscl_requires_ground_coordination"

        return True, "cleared"

    def check_movement_clearance(
        self,
        unit_id: str,
        current_pos: Position,
        dest: Position,
        timestamp: datetime | None = None,
    ) -> tuple[bool, str]:
        """Check if movement is cleared (boundary crossing check).

        Returns (cleared, reason).
        """
        from datetime import timezone

        ts = timestamp or datetime.now(tz=timezone.utc)

        for m in self._measures.values():
            if m.measure_type == CoordinationMeasureType.BOUNDARY:
                if self._crosses_boundary(current_pos, dest, m):
                    self._publish_violation(
                        unit_id, "BOUNDARY", m.measure_id, ts,
                    )
                    return False, f"crosses_boundary_{m.measure_id}"

            if m.measure_type == CoordinationMeasureType.NFA:
                if self._is_in_area(dest, m):
                    return False, f"destination_in_nfa_{m.measure_id}"

        return True, "cleared"

    # -- 12a-5: JTAC/FAC methods -----------------------------------------------

    def register_jtac(self, jtac_id: str, position: Position) -> None:
        """Register a JTAC/FAC observer at a position."""
        self._jtacs[jtac_id] = position

    def unregister_jtac(self, jtac_id: str) -> None:
        """Remove a JTAC."""
        self._jtacs.pop(jtac_id, None)

    def update_jtac_position(self, jtac_id: str, position: Position) -> None:
        """Update a JTAC's position."""
        self._jtacs[jtac_id] = position

    def check_cas_feasibility(
        self,
        target_id: str,
        target_position: Position,
    ) -> JTACObservation | None:
        """Check if any registered JTAC has LOS to the target.

        Returns the best JTAC observation, or None if no JTAC can observe.
        """
        best: JTACObservation | None = None
        best_range = float("inf")

        for jtac_id, jtac_pos in self._jtacs.items():
            dx = target_position.easting - jtac_pos.easting
            dy = target_position.northing - jtac_pos.northing
            range_m = math.sqrt(dx * dx + dy * dy)

            # Check LOS if engine available
            has_los = True
            if self._los_engine is not None:
                result = self._los_engine.check_los(jtac_pos, target_position)
                has_los = result.has_los

            if not has_los:
                continue

            if range_m < best_range:
                # Position error inversely proportional to range
                error_m = max(5.0, range_m * 0.01)
                noise_e = float(self._rng.normal(0.0, error_m))
                noise_n = float(self._rng.normal(0.0, error_m))
                estimated_pos = Position(
                    target_position.easting + noise_e,
                    target_position.northing + noise_n,
                    target_position.altitude,
                )
                best = JTACObservation(
                    jtac_id=jtac_id,
                    target_id=target_id,
                    estimated_position=estimated_pos,
                    position_error_m=error_m,
                    has_los=True,
                    range_m=range_m,
                )
                best_range = range_m

        return best

    # -- 12a-6: JIPTL methods -----------------------------------------------

    def submit_target_nomination(self, nomination: TargetNomination) -> None:
        """Submit a target nomination for JIPTL processing."""
        self._nominations.append(nomination)

    def clear_nominations(self) -> None:
        """Clear all pending nominations."""
        self._nominations.clear()

    def generate_jiptl(
        self,
        available_shooters: dict[str, Position],
        timestamp: datetime | None = None,
    ) -> list[TargetAllocation]:
        """Generate JIPTL: prioritized target list with greedy allocation.

        Parameters
        ----------
        available_shooters:
            Dict of shooter_id → position for available fire assets.

        Returns list of TargetAllocation sorted by priority.
        """
        from datetime import timezone

        ts = timestamp or datetime.now(tz=timezone.utc)
        cfg = self._jiptl_config

        if not self._nominations or not available_shooters:
            return []

        # Score each nomination
        scored: list[tuple[float, TargetNomination]] = []
        for nom in self._nominations:
            type_weight = cfg.target_type_weights.get(nom.target_type, 1.0)
            priority_factor = 1.0 / max(1, nom.priority)
            ts_boost = cfg.time_sensitive_boost if nom.time_sensitive else 1.0
            score = type_weight * priority_factor * ts_boost
            scored.append((score, nom))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Greedy allocation
        allocated_shooters: set[str] = set()
        allocations: list[TargetAllocation] = []

        for score, nom in scored:
            # Find nearest available shooter
            best_shooter: str | None = None
            best_range = float("inf")

            for sid, spos in available_shooters.items():
                if sid in allocated_shooters:
                    continue
                dx = nom.position.easting - spos.easting
                dy = nom.position.northing - spos.northing
                range_m = math.sqrt(dx * dx + dy * dy)
                if range_m < best_range:
                    best_range = range_m
                    best_shooter = sid

            if best_shooter is not None:
                allocations.append(TargetAllocation(
                    target_id=nom.target_id,
                    shooter_id=best_shooter,
                    score=score,
                    range_m=best_range,
                ))
                allocated_shooters.add(best_shooter)

        # Publish event
        highest_target = scored[0][1].target_id if scored else ""
        self._event_bus.publish(JIPTLGeneratedEvent(
            timestamp=ts, source=ModuleId.C2,
            num_nominations=len(self._nominations),
            num_allocated=len(allocations),
            highest_priority_target=highest_target,
        ))

        return allocations

    def _publish_violation(
        self,
        unit_id: str,
        measure_type: str,
        measure_id: str,
        timestamp: datetime,
    ) -> None:
        self._event_bus.publish(CoordinationViolationEvent(
            timestamp=timestamp, source=ModuleId.C2,
            unit_id=unit_id,
            measure_type=measure_type,
            measure_id=measure_id,
        ))

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        return {
            "measures": {
                mid: {
                    "measure_id": m.measure_id,
                    "measure_type": int(m.measure_type),
                    "center": list(m.center),
                    "radius_m": m.radius_m,
                    "line_start": list(m.line_start) if m.line_start else None,
                    "line_end": list(m.line_end) if m.line_end else None,
                    "owning_unit": m.owning_unit,
                    "requires_coordination_with": m.requires_coordination_with,
                }
                for mid, m in self._measures.items()
            },
            "fscl_line": (
                [list(self._fscl_line[0]), list(self._fscl_line[1])]
                if self._fscl_line else None
            ),
        }

    def set_state(self, state: dict) -> None:
        self._measures.clear()
        for mid, md in state["measures"].items():
            self._measures[mid] = CoordinationMeasure(
                measure_id=md["measure_id"],
                measure_type=CoordinationMeasureType(md["measure_type"]),
                center=Position(*md["center"]),
                radius_m=md["radius_m"],
                line_start=Position(*md["line_start"]) if md["line_start"] else None,
                line_end=Position(*md["line_end"]) if md["line_end"] else None,
                owning_unit=md["owning_unit"],
                requires_coordination_with=md["requires_coordination_with"],
            )
        if state["fscl_line"]:
            self._fscl_line = (
                Position(*state["fscl_line"][0]),
                Position(*state["fscl_line"][1]),
            )
        else:
            self._fscl_line = None

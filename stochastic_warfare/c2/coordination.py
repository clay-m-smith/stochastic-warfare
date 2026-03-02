"""Fire support coordination and airspace deconfliction.

Data structures and geometric check functions ONLY. No fire support
planning logic (Phase 8).

Coordination measures: FSCL, CFL, NFA, RFA, FFA, BOUNDARY,
AIRSPACE_CORRIDOR, MISSILE_FLIGHT_CORRIDOR.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from datetime import datetime

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.c2.events import CoordinationViolationEvent

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
# Engine
# ---------------------------------------------------------------------------


class CoordinationEngine:
    """Manages fire support coordination measures.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``CoordinationViolationEvent``.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._measures: dict[str, CoordinationMeasure] = {}
        self._fscl_line: tuple[Position, Position] | None = None

    # -- Measure management -------------------------------------------------

    def add_measure(self, measure: CoordinationMeasure) -> None:
        """Add a coordination measure."""
        self._measures[measure.measure_id] = measure

    def remove_measure(self, measure_id: str) -> None:
        """Remove a coordination measure."""
        del self._measures[measure_id]

    def set_fscl(self, start: Position, end: Position) -> None:
        """Set the Fire Support Coordination Line."""
        self._fscl_line = (start, end)

    def get_fscl(self) -> tuple[Position, Position] | None:
        """Return the FSCL line, or None if not set."""
        return self._fscl_line

    # -- Geometric checks ---------------------------------------------------

    def is_beyond_fscl(self, pos: Position) -> bool:
        """Check if a position is beyond (north of) the FSCL.

        Beyond FSCL: fires may be executed without ground coordination
        (service-coordinated fires). Short of FSCL: requires ground
        commander coordination.
        """
        if self._fscl_line is None:
            return False
        # Simple: FSCL is an east-west line; beyond = north of the line
        # Use the northing of the midpoint as threshold
        fscl_northing = (
            self._fscl_line[0].northing + self._fscl_line[1].northing
        ) / 2
        return pos.northing > fscl_northing

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

        # FSCL check
        if self._fscl_line is not None:
            if not self.is_beyond_fscl(target_pos):
                if fire_type in (FireType.AIR_DELIVERED, FireType.NAVAL_GUNFIRE):
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

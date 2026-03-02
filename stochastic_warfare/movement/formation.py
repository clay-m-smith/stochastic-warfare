"""Formation geometry and coherence."""

from __future__ import annotations

import enum
import math

from stochastic_warfare.core.types import Position


class FormationType(enum.IntEnum):
    """Standard tactical formation types."""

    COLUMN = 0
    LINE = 1
    WEDGE = 2
    VEE = 3
    ECHELON_LEFT = 4
    ECHELON_RIGHT = 5
    BOX = 6
    DIAMOND = 7
    STAGGERED_COLUMN = 8
    FILE = 9


# Speed factor relative to column (baseline).
_FORMATION_SPEED: dict[FormationType, float] = {
    FormationType.COLUMN: 1.0,
    FormationType.LINE: 0.7,
    FormationType.WEDGE: 0.85,
    FormationType.VEE: 0.85,
    FormationType.ECHELON_LEFT: 0.9,
    FormationType.ECHELON_RIGHT: 0.9,
    FormationType.BOX: 0.75,
    FormationType.DIAMOND: 0.8,
    FormationType.STAGGERED_COLUMN: 0.95,
    FormationType.FILE: 1.0,
}


class FormationManager:
    """Compute formation positions, coherence, and speed factors."""

    @staticmethod
    def compute_positions(
        lead_pos: Position,
        heading: float,
        num_elements: int,
        formation: FormationType,
        spacing: float = 50.0,
    ) -> list[Position]:
        """Compute ideal positions for *num_elements* in *formation*.

        Parameters
        ----------
        lead_pos:
            Position of the lead element.
        heading:
            Direction of movement in radians (0 = north, CW).
        num_elements:
            Total elements including lead.
        spacing:
            Distance between elements in meters.

        Returns
        -------
        List of Position objects (first is lead_pos).
        """
        if num_elements <= 0:
            return []
        if num_elements == 1:
            return [lead_pos]

        positions = [lead_pos]
        sin_h = math.sin(heading)
        cos_h = math.cos(heading)

        for i in range(1, num_elements):
            # (dx, dy) in formation-local coords (forward, right)
            fwd, right = _element_offset(formation, i, num_elements, spacing)
            # Rotate to world coords
            de = fwd * sin_h + right * cos_h
            dn = fwd * cos_h - right * sin_h
            positions.append(
                Position(
                    lead_pos.easting + de,
                    lead_pos.northing + dn,
                    lead_pos.altitude,
                )
            )

        return positions

    @staticmethod
    def coherence(intended: list[Position], actual: list[Position]) -> float:
        """Return 0.0–1.0 coherence score between intended and actual positions.

        1.0 = perfect formation, 0.0 = completely scattered.
        Uses mean distance error relative to spacing.
        """
        if len(intended) != len(actual) or len(intended) == 0:
            return 0.0
        if len(intended) == 1:
            return 1.0

        total_error = 0.0
        for ip, ap in zip(intended, actual):
            dx = ip.easting - ap.easting
            dy = ip.northing - ap.northing
            total_error += math.sqrt(dx * dx + dy * dy)

        mean_error = total_error / len(intended)
        # Normalize: 50m average error → coherence ~0.37
        return math.exp(-mean_error / 50.0)

    @staticmethod
    def formation_speed_factor(formation: FormationType) -> float:
        """Return movement speed multiplier for *formation*."""
        return _FORMATION_SPEED.get(formation, 0.8)

    @staticmethod
    def formation_frontage(
        formation: FormationType,
        num_elements: int,
        spacing: float = 50.0,
    ) -> float:
        """Return the lateral frontage in meters."""
        if num_elements <= 1:
            return 0.0

        if formation in (FormationType.COLUMN, FormationType.FILE):
            return 0.0  # no lateral spread
        if formation == FormationType.LINE:
            return (num_elements - 1) * spacing
        if formation in (FormationType.WEDGE, FormationType.VEE):
            return (num_elements - 1) * spacing * 0.5
        if formation in (FormationType.ECHELON_LEFT, FormationType.ECHELON_RIGHT):
            return (num_elements - 1) * spacing * 0.5
        if formation == FormationType.BOX:
            side = math.ceil(math.sqrt(num_elements))
            return (side - 1) * spacing
        if formation == FormationType.DIAMOND:
            return (num_elements // 2) * spacing * 0.5
        if formation == FormationType.STAGGERED_COLUMN:
            return spacing * 0.5

        return (num_elements - 1) * spacing


def _element_offset(
    formation: FormationType,
    index: int,
    total: int,
    spacing: float,
) -> tuple[float, float]:
    """Return (forward, right) offset for element *index* in local coords.

    Element 0 is the lead at (0, 0). Forward is negative (behind lead).
    """
    if formation == FormationType.COLUMN:
        return (-index * spacing, 0.0)

    if formation == FormationType.FILE:
        return (-index * spacing, 0.0)

    if formation == FormationType.LINE:
        # Spread elements left and right of center
        center = (total - 1) / 2.0
        return (0.0, (index - center) * spacing)

    if formation == FormationType.WEDGE:
        # V shape trailing behind lead
        side = 1 if index % 2 == 1 else -1
        rank = (index + 1) // 2
        return (-rank * spacing * 0.7, side * rank * spacing * 0.5)

    if formation == FormationType.VEE:
        # Inverted V — flanks forward
        side = 1 if index % 2 == 1 else -1
        rank = (index + 1) // 2
        return (rank * spacing * 0.3, side * rank * spacing * 0.5)

    if formation == FormationType.ECHELON_LEFT:
        return (-index * spacing * 0.7, -index * spacing * 0.5)

    if formation == FormationType.ECHELON_RIGHT:
        return (-index * spacing * 0.7, index * spacing * 0.5)

    if formation == FormationType.BOX:
        side = math.ceil(math.sqrt(total))
        row = index // side
        col = index % side
        center = (side - 1) / 2.0
        return (-row * spacing, (col - center) * spacing)

    if formation == FormationType.DIAMOND:
        # Diamond: 1 front, spread middle, 1 rear
        if index == 1:
            return (-spacing * 0.5, -spacing * 0.5)
        if index == 2:
            return (-spacing * 0.5, spacing * 0.5)
        if index == 3:
            return (-spacing, 0.0)
        # For larger diamonds, stack behind
        rank = (index - 1) // 2 + 1
        side = 1 if index % 2 == 0 else -1
        return (-rank * spacing * 0.5, side * spacing * 0.5)

    if formation == FormationType.STAGGERED_COLUMN:
        side = 1 if index % 2 == 1 else -1
        return (-index * spacing, side * spacing * 0.25)

    # Fallback: column
    return (-index * spacing, 0.0)

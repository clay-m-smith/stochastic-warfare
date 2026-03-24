"""Shared fixtures and factory functions for terrain unit tests."""

from __future__ import annotations

from stochastic_warfare.terrain.trenches import TrenchSegment, TrenchType


def _make_trench_segment(
    trench_id: str = "t1",
    side: str = "blue",
    points: list[list[float]] | None = None,
    trench_type: TrenchType = TrenchType.FIRE_TRENCH,
    condition: float = 1.0,
    has_wire: bool = False,
    has_dugout: bool = False,
) -> TrenchSegment:
    """Create a TrenchSegment for testing."""
    return TrenchSegment(
        trench_id=trench_id,
        trench_type=trench_type,
        side=side,
        points=points or [[0.0, 0.0], [100.0, 0.0]],
        condition=condition,
        has_wire=has_wire,
        has_dugout=has_dugout,
    )

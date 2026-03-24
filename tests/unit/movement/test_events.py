"""Unit tests for movement events — frozen dataclass validation.

Phase 75c: Tests UnitMovedEvent, FormationChangedEvent, FatigueChangedEvent.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.movement.events import (
    FatigueChangedEvent,
    FormationChangedEvent,
    UnitMovedEvent,
)

TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
SRC = ModuleId.MOVEMENT


class TestMovementEvents:
    """Frozen dataclass event validation."""

    def test_unit_moved_event(self):
        ev = UnitMovedEvent(
            timestamp=TS,
            source=SRC,
            unit_id="u1",
            from_pos=Position(0.0, 0.0, 0.0),
            to_pos=Position(100.0, 0.0, 0.0),
            distance=100.0,
            duration=10.0,
        )
        assert ev.unit_id == "u1"
        assert ev.distance == 100.0
        with pytest.raises(AttributeError):
            ev.unit_id = "u2"  # frozen

    def test_formation_changed_event(self):
        ev = FormationChangedEvent(
            timestamp=TS, source=SRC, unit_id="u1", new_formation=2,
        )
        assert ev.new_formation == 2

    def test_fatigue_changed_event(self):
        ev = FatigueChangedEvent(
            timestamp=TS, source=SRC, unit_id="u1", fatigue_level=0.75,
        )
        assert ev.fatigue_level == 0.75

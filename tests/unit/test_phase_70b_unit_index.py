"""Phase 70b: Unit ID index and formation sort hoisting tests.

Verifies that the per-tick unit index and pre-computed formation indices
produce identical results to the original per-unit scan/sort approaches.
"""

from __future__ import annotations

import numpy as np
import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeUnit:
    """Minimal frozen Unit-like stub."""

    def __init__(self, entity_id: str, easting: float = 0.0, northing: float = 0.0) -> None:
        self.entity_id = entity_id
        self.position = Position(easting, northing, 0.0)
        self.status = UnitStatus.ACTIVE
        self.side = "blue"
        self.parent_id: str | None = None


def _build_unit_index(units_by_side: dict[str, list]) -> dict[str, object]:
    """Reproduce the index-building logic from execute_tick."""
    idx: dict[str, object] = {}
    for side_units in units_by_side.values():
        for u in side_units:
            idx[u.entity_id] = u
    return idx


def _build_formation_index(units: list) -> tuple[dict[str, int], int]:
    """Reproduce the hoisted formation sort from _execute_movement."""
    sorted_active = sorted(
        [u for u in units if u.status == UnitStatus.ACTIVE],
        key=lambda u: u.entity_id,
    )
    idx = {u.entity_id: i for i, u in enumerate(sorted_active)}
    return idx, len(sorted_active)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUnitIndex:
    """Entity_id → Unit index."""

    def test_index_contains_all_units(self) -> None:
        """Index maps every entity_id to its unit."""
        units = [_FakeUnit(f"u{i}") for i in range(10)]
        ubs = {"blue": units[:5], "red": units[5:]}
        idx = _build_unit_index(ubs)
        assert len(idx) == 10
        for u in units:
            assert idx[u.entity_id] is u

    def test_parent_lookup_matches_linear_scan(self) -> None:
        """Index parent lookup equivalent to linear scan."""
        parent = _FakeUnit("hq_1", easting=100.0, northing=200.0)
        child = _FakeUnit("uav_1")
        child.parent_id = "hq_1"
        ubs = {"blue": [parent, child]}
        idx = _build_unit_index(ubs)

        # Index lookup
        idx_parent = idx.get(child.parent_id)
        assert idx_parent is parent

        # Linear scan (original code path)
        scan_parent = None
        for u in ubs["blue"]:
            if u.entity_id == child.parent_id:
                scan_parent = u
                break
        assert scan_parent is parent
        assert idx_parent is scan_parent

    def test_missing_parent_returns_none(self) -> None:
        """Index returns None for non-existent parent_id."""
        child = _FakeUnit("uav_2")
        child.parent_id = "missing_hq"
        idx = _build_unit_index({"blue": [child]})
        assert idx.get(child.parent_id) is None


class TestFormationIndex:
    """Pre-computed formation sort index."""

    def test_formation_index_matches_sorted_order(self) -> None:
        """Index assigns same positions as inline sorted()."""
        units = [_FakeUnit(f"u{i:02d}") for i in [5, 3, 8, 1, 7]]
        idx, n = _build_formation_index(units)

        # Expected: sorted by entity_id → u01, u03, u05, u07, u08
        assert n == 5
        assert idx["u01"] == 0
        assert idx["u03"] == 1
        assert idx["u05"] == 2
        assert idx["u07"] == 3
        assert idx["u08"] == 4

    def test_formation_lateral_offset_matches(self) -> None:
        """Lateral offsets from hoisted index match original per-unit sort."""
        units = [_FakeUnit(f"u{i:02d}") for i in [3, 1, 2]]
        spacing = 50.0

        # Hoisted approach
        idx, n = _build_formation_index(units)
        hoisted_offsets = {}
        for u in units:
            if u.status == UnitStatus.ACTIVE:
                i = idx.get(u.entity_id, 0)
                hoisted_offsets[u.entity_id] = (i - (n - 1) / 2.0) * spacing

        # Original inline approach
        own_units = sorted(
            [u for u in units if u.status == UnitStatus.ACTIVE],
            key=lambda u: u.entity_id,
        )
        n_own = len(own_units)
        inline_offsets = {}
        for u in units:
            if u.status == UnitStatus.ACTIVE:
                _idx = next(
                    (i for i, ou in enumerate(own_units) if ou.entity_id == u.entity_id), 0
                )
                inline_offsets[u.entity_id] = (_idx - (n_own - 1) / 2.0) * spacing

        for uid in hoisted_offsets:
            assert abs(hoisted_offsets[uid] - inline_offsets[uid]) < 1e-10

    def test_destroyed_units_excluded(self) -> None:
        """Destroyed units don't appear in formation index."""
        units = [_FakeUnit(f"u{i}") for i in range(3)]
        units[1].status = UnitStatus.DESTROYED
        idx, n = _build_formation_index(units)
        assert n == 2
        assert "u1" not in idx

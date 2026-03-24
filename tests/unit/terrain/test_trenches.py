"""Unit tests for TrenchSystemEngine — WW1 trench overlay.

Phase 75c: Tests trench setup, spatial queries, movement, bombardment, state.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.terrain.trenches import (
    TrenchSystemEngine,
    TrenchType,
)

from .conftest import _make_trench_segment


# ===================================================================
# Setup
# ===================================================================


class TestTrenchSetup:
    """Adding trench segments."""

    def test_add_segment(self):
        engine = TrenchSystemEngine()
        seg = _make_trench_segment("t1")
        engine.add_trench(seg)
        result = engine.query_trench(50.0, 0.0)
        assert result.in_trench is True

    def test_multiple_segments(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1", points=[[0, 0], [100, 0]]))
        engine.add_trench(_make_trench_segment("t2", points=[[0, 500], [100, 500]]))
        r1 = engine.query_trench(50.0, 0.0)
        r2 = engine.query_trench(50.0, 500.0)
        assert r1.trench_id == "t1"
        assert r2.trench_id == "t2"

    def test_no_mans_land(self):
        engine = TrenchSystemEngine()
        engine.add_no_mans_land((0, 100), (200, 100), width_m=50.0)
        assert engine.is_no_mans_land(100.0, 100.0) is True
        assert engine.is_no_mans_land(100.0, 200.0) is False


# ===================================================================
# Spatial queries
# ===================================================================


class TestTrenchQuery:
    """Position-based trench queries."""

    def test_in_trench_near_line(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1", points=[[0, 0], [200, 0]]))
        result = engine.query_trench(100.0, 2.0)  # 2m from trench
        assert result.in_trench is True

    def test_outside_trench(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1", points=[[0, 0], [100, 0]]))
        result = engine.query_trench(50.0, 100.0)  # 100m away
        assert result.in_trench is False

    def test_cover_scaled_by_condition(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1", condition=0.5))
        result = engine.query_trench(50.0, 0.0)
        # Fire trench base cover = 0.85, × condition 0.5 = 0.425
        assert result.cover_value == pytest.approx(0.425, abs=0.01)

    def test_fire_vs_support_cover(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1", trench_type=TrenchType.FIRE_TRENCH,
                                                points=[[0, 0], [100, 0]]))
        engine.add_trench(_make_trench_segment("t2", trench_type=TrenchType.SUPPORT_TRENCH,
                                                points=[[0, 100], [100, 100]]))
        r_fire = engine.query_trench(50.0, 0.0)
        r_support = engine.query_trench(50.0, 100.0)
        assert r_fire.cover_value > r_support.cover_value

    def test_bombardment_degrades(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1", points=[[0, 0], [200, 0]]))
        affected = engine.apply_bombardment(100.0, 0.0, 50.0, intensity=1.0)
        assert "t1" in affected
        result = engine.query_trench(100.0, 0.0)
        assert result.condition < 1.0


# ===================================================================
# Movement factors
# ===================================================================


class TestTrenchMovement:
    """Speed multipliers in and around trenches."""

    def test_along_factor(self):
        engine = TrenchSystemEngine()
        # Trench runs east (0→100, 0)
        engine.add_trench(_make_trench_segment("t1", points=[[0, 0], [100, 0]]))
        # Heading east (90°) — along the trench
        factor = engine.movement_factor_at(50.0, 0.0, heading_deg=90.0)
        assert factor == pytest.approx(0.5, abs=0.1)

    def test_crossing_factor(self):
        engine = TrenchSystemEngine()
        # Trench runs east (0→100, 0)
        engine.add_trench(_make_trench_segment("t1", points=[[0, 0], [100, 0]]))
        # Heading north (0°) — crossing the trench
        factor = engine.movement_factor_at(50.0, 0.0, heading_deg=0.0)
        assert factor <= 0.5  # crossing or interpolated

    def test_nml_slowest(self):
        engine = TrenchSystemEngine()
        engine.add_no_mans_land((0, 50), (200, 50), width_m=100.0)
        factor = engine.movement_factor_at(100.0, 50.0)
        assert factor == pytest.approx(0.2)


# ===================================================================
# State persistence
# ===================================================================


class TestTrenchState:
    """Checkpoint roundtrip."""

    def test_roundtrip(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1"))
        state = engine.get_state()
        engine2 = TrenchSystemEngine()
        engine2.set_state(state)
        result = engine2.query_trench(50.0, 0.0)
        assert result.in_trench is True

    def test_condition_preserved(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1"))
        engine.apply_bombardment(50.0, 0.0, 50.0, intensity=0.5)
        state = engine.get_state()
        engine2 = TrenchSystemEngine()
        engine2.set_state(state)
        result = engine2.query_trench(50.0, 0.0)
        assert result.condition < 1.0

    def test_strtree_rebuilt(self):
        engine = TrenchSystemEngine()
        engine.add_trench(_make_trench_segment("t1"))
        state = engine.get_state()
        engine2 = TrenchSystemEngine()
        engine2.set_state(state)
        # After set_state, _dirty should be True
        assert engine2._dirty is True
        # First query should rebuild and succeed
        result = engine2.query_trench(50.0, 0.0)
        assert result.in_trench is True

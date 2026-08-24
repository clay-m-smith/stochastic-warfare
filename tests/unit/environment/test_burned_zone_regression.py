"""Phase 69e — Burned zone concealment reduction tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stochastic_warfare.core.types import Position
from stochastic_warfare.simulation.battle import BattleManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_burned_zone(center: Position, radius_m: float, reduction: float = 0.5):
    """Return a minimal BurnedZone-like object."""
    return SimpleNamespace(center=center, radius_m=radius_m, concealment_reduction=reduction)


def _make_ctx(burned_zones=None, classification=None):
    """Return a minimal context with an optional incendiary engine."""
    ctx = SimpleNamespace()
    if burned_zones is not None:
        ctx.incendiary_engine = SimpleNamespace(get_burned_zones=lambda: burned_zones)
    else:
        ctx.incendiary_engine = None
    ctx.classification = classification
    ctx.heightmap = None
    ctx.infrastructure_manager = None
    ctx.obstacle_manager = None
    ctx.trench_engine = None
    return ctx


def _make_classification(concealment: float):
    """Return a classification manager that returns fixed concealment."""
    props = SimpleNamespace(cover=0.0, concealment=concealment, land_cover=None)
    return SimpleNamespace(properties_at=lambda pos: props)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBurnedZoneConcealment:
    """Phase 69e: Burned zone concealment reduction."""

    def test_unit_in_burned_zone_reduced_concealment(self):
        """Unit inside a burned zone has concealment reduced."""
        bz = _make_burned_zone(Position(100, 100, 0), radius_m=50.0, reduction=0.5)
        cls_ = _make_classification(0.6)
        ctx = _make_ctx(burned_zones=[bz], classification=cls_)

        cover, elev, concealment = BattleManager._compute_terrain_modifiers(
            ctx, Position(100, 100, 0), Position(0, 0, 0),
        )
        # 0.6 - 0.5 = 0.1
        assert concealment == pytest.approx(0.1, abs=1e-9)

    def test_multiple_burned_zones_worst_applies(self):
        """Multiple overlapping burned zones stack reductions."""
        bz1 = _make_burned_zone(Position(100, 100, 0), radius_m=200.0, reduction=0.3)
        bz2 = _make_burned_zone(Position(110, 110, 0), radius_m=200.0, reduction=0.4)
        cls_ = _make_classification(0.8)
        ctx = _make_ctx(burned_zones=[bz1, bz2], classification=cls_)

        cover, elev, concealment = BattleManager._compute_terrain_modifiers(
            ctx, Position(105, 105, 0), Position(0, 0, 0),
        )
        # 0.8 - 0.3 - 0.4 = 0.1
        assert concealment == pytest.approx(0.1, abs=1e-9)

    def test_unit_outside_burned_zone_unchanged(self):
        """Unit outside all burned zones keeps original concealment."""
        bz = _make_burned_zone(Position(100, 100, 0), radius_m=10.0, reduction=0.5)
        cls_ = _make_classification(0.7)
        ctx = _make_ctx(burned_zones=[bz], classification=cls_)

        cover, elev, concealment = BattleManager._compute_terrain_modifiers(
            ctx, Position(500, 500, 0), Position(0, 0, 0),
        )
        assert concealment == pytest.approx(0.7, abs=1e-9)

    def test_no_incendiary_engine_no_change(self):
        """No incendiary engine → concealment unchanged (backward compat)."""
        cls_ = _make_classification(0.6)
        ctx = _make_ctx(burned_zones=None, classification=cls_)

        cover, elev, concealment = BattleManager._compute_terrain_modifiers(
            ctx, Position(100, 100, 0), Position(0, 0, 0),
        )
        assert concealment == pytest.approx(0.6, abs=1e-9)

    def test_zero_radius_burned_zone(self):
        """Zero-radius burned zone only affects exact position."""
        bz = _make_burned_zone(Position(100, 100, 0), radius_m=0.0, reduction=0.5)
        cls_ = _make_classification(0.6)
        ctx = _make_ctx(burned_zones=[bz], classification=cls_)

        # Exactly at center — distance=0 <= 0 → inside
        cover, elev, concealment = BattleManager._compute_terrain_modifiers(
            ctx, Position(100, 100, 0), Position(0, 0, 0),
        )
        assert concealment == pytest.approx(0.1, abs=1e-9)

        # 1m away — outside
        cover2, elev2, concealment2 = BattleManager._compute_terrain_modifiers(
            ctx, Position(101, 100, 0), Position(0, 0, 0),
        )
        assert concealment2 == pytest.approx(0.6, abs=1e-9)

    def test_seasonal_vegetation_negated_by_burned_zone(self):
        """Seasonal vegetation concealment bonus negated by burned zone."""
        bz = _make_burned_zone(Position(100, 100, 0), radius_m=200.0, reduction=0.5)
        # Classification with FOREST land cover
        lc = SimpleNamespace(name="FOREST_DECIDUOUS")
        props = SimpleNamespace(cover=0.0, concealment=0.4, land_cover=lc)
        cls_ = SimpleNamespace(properties_at=lambda pos: props)
        ctx = _make_ctx(burned_zones=[bz], classification=cls_)

        cover, elev, concealment = BattleManager._compute_terrain_modifiers(
            ctx, Position(100, 100, 0), Position(0, 0, 0),
            seasonal_vegetation=0.5,
        )
        # Base concealment 0.4 + seasonal (0.5 * 0.3) = 0.55 → burned: 0.55 - 0.5 = 0.05
        assert concealment == pytest.approx(0.05, abs=1e-9)

    def test_concealment_floor_at_zero(self):
        """Concealment never goes below 0.0 even with large reduction."""
        bz = _make_burned_zone(Position(100, 100, 0), radius_m=200.0, reduction=0.9)
        cls_ = _make_classification(0.3)
        ctx = _make_ctx(burned_zones=[bz], classification=cls_)

        cover, elev, concealment = BattleManager._compute_terrain_modifiers(
            ctx, Position(100, 100, 0), Position(0, 0, 0),
        )
        assert concealment == pytest.approx(0.0, abs=1e-9)

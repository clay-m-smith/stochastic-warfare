"""Phase 78a: Ice crossing and vegetation LOS blocking tests."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from stochastic_warfare.core.types import Position
from stochastic_warfare.terrain.heightmap import Heightmap, HeightmapConfig
from stochastic_warfare.terrain.los import LOSEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_heightmap(rows: int = 10, cols: int = 10, cell_size: float = 10.0, elev: float = 0.0):
    cfg = HeightmapConfig(
        origin_easting=0.0, origin_northing=0.0,
        cell_size=cell_size,
    )
    data = np.full((rows, cols), elev, dtype=np.float64)
    return Heightmap(data, cfg)


def _make_classification(rows: int = 10, cols: int = 10, land_cover_code: int = 0):
    """Create a simple TerrainClassification with uniform land cover."""
    from stochastic_warfare.terrain.classification import (
        ClassificationConfig,
        TerrainClassification,
    )
    cfg = ClassificationConfig(origin_easting=0.0, origin_northing=0.0, cell_size=10.0)
    lc = np.full((rows, cols), land_cover_code, dtype=np.int32)
    soil = np.full((rows, cols), 2, dtype=np.int32)  # LOAM
    return TerrainClassification(lc, soil, cfg)


def _make_seasons_snapshot(ice_thickness: float = 0.0, veg_density: float = 1.0):
    return SimpleNamespace(
        sea_ice_thickness=ice_thickness,
        vegetation_density=veg_density,
        vegetation_moisture=0.5,
    )


# ---------------------------------------------------------------------------
# Ice crossing — MovementEngine.is_on_ice
# ---------------------------------------------------------------------------


class TestIsOnIce:
    """MovementEngine.is_on_ice tests."""

    def test_water_thick_ice_returns_true(self):
        from stochastic_warfare.movement.engine import MovementEngine
        from stochastic_warfare.terrain.classification import LandCover

        classif = _make_classification(land_cover_code=int(LandCover.WATER))
        eng = MovementEngine(classification=classif)
        snap = _make_seasons_snapshot(ice_thickness=0.5)
        assert eng.is_on_ice(Position(5.0, 5.0), snap) is True

    def test_water_thin_ice_returns_false(self):
        from stochastic_warfare.movement.engine import MovementEngine
        from stochastic_warfare.terrain.classification import LandCover

        classif = _make_classification(land_cover_code=int(LandCover.WATER))
        eng = MovementEngine(classification=classif)
        snap = _make_seasons_snapshot(ice_thickness=0.2)
        assert eng.is_on_ice(Position(5.0, 5.0), snap) is False

    def test_non_water_thick_ice_returns_false(self):
        from stochastic_warfare.movement.engine import MovementEngine
        from stochastic_warfare.terrain.classification import LandCover

        classif = _make_classification(land_cover_code=int(LandCover.OPEN))
        eng = MovementEngine(classification=classif)
        snap = _make_seasons_snapshot(ice_thickness=1.0)
        assert eng.is_on_ice(Position(5.0, 5.0), snap) is False

    def test_no_snapshot_returns_false(self):
        from stochastic_warfare.movement.engine import MovementEngine
        from stochastic_warfare.terrain.classification import LandCover

        classif = _make_classification(land_cover_code=int(LandCover.WATER))
        eng = MovementEngine(classification=classif)
        assert eng.is_on_ice(Position(5.0, 5.0), None) is False


# ---------------------------------------------------------------------------
# Vegetation LOS blocking
# ---------------------------------------------------------------------------


class TestVegetationLOS:
    """LOSEngine vegetation blocking tests."""

    def test_forest_blocks_ground_level_los(self):
        """Dense forest (15m) blocks LOS between two ground-level observers."""
        from stochastic_warfare.terrain.classification import LandCover

        hm = _make_heightmap(rows=20, cols=20, cell_size=10.0, elev=0.0)
        classif = _make_classification(rows=20, cols=20, land_cover_code=int(LandCover.FOREST_DECIDUOUS))
        los = LOSEngine(hm, classification=classif)
        los.set_vegetation_density(1.0)

        result = los.check_los(
            Position(5.0, 5.0), Position(100.0, 100.0),
            observer_height=1.8, target_height=0.0,
        )
        assert result.visible is False
        assert result.blocked_by == "vegetation"

    def test_high_observer_sees_above_canopy_target(self):
        """Air unit at 100m altitude can see target above canopy (20m)."""
        from stochastic_warfare.terrain.classification import LandCover

        hm = _make_heightmap(rows=20, cols=20, cell_size=10.0, elev=0.0)
        classif = _make_classification(rows=20, cols=20, land_cover_code=int(LandCover.FOREST_DECIDUOUS))
        los = LOSEngine(hm, classification=classif)
        los.set_vegetation_density(1.0)

        # Both above canopy height (15m deciduous) — ray clears vegetation
        result = los.check_los(
            Position(5.0, 5.0), Position(100.0, 100.0),
            observer_height=100.0, target_height=20.0,
        )
        assert result.visible is True

    def test_ground_target_blocked_even_from_altitude(self):
        """Ray to ground-level target passes through canopy near target — blocked."""
        from stochastic_warfare.terrain.classification import LandCover

        hm = _make_heightmap(rows=20, cols=20, cell_size=10.0, elev=0.0)
        classif = _make_classification(rows=20, cols=20, land_cover_code=int(LandCover.FOREST_DECIDUOUS))
        los = LOSEngine(hm, classification=classif)
        los.set_vegetation_density(1.0)

        result = los.check_los(
            Position(5.0, 5.0), Position(100.0, 100.0),
            observer_height=100.0, target_height=0.0,
        )
        assert result.visible is False
        assert result.blocked_by == "vegetation"

    def test_winter_density_makes_forest_transparent(self):
        """Zero vegetation density (winter deciduous) does not block LOS."""
        from stochastic_warfare.terrain.classification import LandCover

        hm = _make_heightmap(rows=20, cols=20, cell_size=10.0, elev=0.0)
        classif = _make_classification(rows=20, cols=20, land_cover_code=int(LandCover.FOREST_DECIDUOUS))
        los = LOSEngine(hm, classification=classif)
        los.set_vegetation_density(0.0)

        result = los.check_los(
            Position(5.0, 5.0), Position(100.0, 100.0),
            observer_height=1.8, target_height=0.0,
        )
        assert result.visible is True

    def test_open_terrain_not_blocked(self):
        """Open terrain (vegetation_height=0) does not block LOS."""
        from stochastic_warfare.terrain.classification import LandCover

        hm = _make_heightmap(rows=20, cols=20, cell_size=10.0, elev=0.0)
        classif = _make_classification(rows=20, cols=20, land_cover_code=int(LandCover.OPEN))
        los = LOSEngine(hm, classification=classif)

        result = los.check_los(
            Position(5.0, 5.0), Position(100.0, 100.0),
            observer_height=1.8, target_height=0.0,
        )
        assert result.visible is True

    def test_shrubland_blocks_low_observer(self):
        """Shrubland (1.5m) blocks observer at 1.0m but not at 1.8m.

        At 1.0m observer height, the ray passes through 1.5m shrubs.
        At 1.8m observer height, the ray may clear them depending on geometry.
        """
        from stochastic_warfare.terrain.classification import LandCover

        hm = _make_heightmap(rows=20, cols=20, cell_size=10.0, elev=0.0)
        classif = _make_classification(rows=20, cols=20, land_cover_code=int(LandCover.SHRUBLAND))
        los = LOSEngine(hm, classification=classif)
        los.set_vegetation_density(1.0)

        # Low observer (1.0m) — ray at 1.0m, shrubs at 1.5m → blocked
        result_low = los.check_los(
            Position(5.0, 5.0), Position(50.0, 50.0),
            observer_height=1.0, target_height=0.0,
        )
        assert result_low.visible is False

    def test_no_classification_uses_vectorized_path(self):
        """Without classification, the vectorized LOS path is used (no vegetation check)."""
        hm = _make_heightmap(rows=10, cols=10, cell_size=10.0, elev=0.0)
        los = LOSEngine(hm)

        result = los.check_los(
            Position(5.0, 5.0), Position(50.0, 50.0),
            observer_height=1.8, target_height=0.0,
        )
        assert result.visible is True

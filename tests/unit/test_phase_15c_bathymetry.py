"""Phase 15c tests — GEBCO bathymetry loader."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from stochastic_warfare.terrain.data_pipeline import BoundingBox
from stochastic_warfare.terrain.bathymetry import BottomType


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def bbox() -> BoundingBox:
    return BoundingBox(south=-52.5, west=-60.0, north=-51.0, east=-58.5)


@pytest.fixture
def projection():
    from stochastic_warfare.coordinates.transforms import ScenarioProjection
    return ScenarioProjection(-51.75, -59.25)


def _make_gebco_netcdf(
    path: Path,
    lats: np.ndarray,
    lons: np.ndarray,
    elevation: np.ndarray,
) -> None:
    """Write a synthetic GEBCO-format NetCDF file."""
    xr = pytest.importorskip("xarray")
    ds = xr.Dataset(
        {"elevation": (["lat", "lon"], elevation)},
        coords={"lat": lats, "lon": lons},
    )
    ds.to_netcdf(str(path))
    ds.close()


# ── Depth → BottomType ───────────────────────────────────────────────────


class TestDepthToBottomType:
    def test_land_is_rock(self) -> None:
        from stochastic_warfare.terrain.real_bathymetry import depth_to_bottom_type
        assert depth_to_bottom_type(0.0) == BottomType.ROCK
        assert depth_to_bottom_type(-10.0) == BottomType.ROCK

    def test_shallow_is_sand(self) -> None:
        from stochastic_warfare.terrain.real_bathymetry import depth_to_bottom_type
        assert depth_to_bottom_type(30.0) == BottomType.SAND

    def test_shelf_is_gravel(self) -> None:
        from stochastic_warfare.terrain.real_bathymetry import depth_to_bottom_type
        assert depth_to_bottom_type(100.0) == BottomType.GRAVEL

    def test_slope_is_mud(self) -> None:
        from stochastic_warfare.terrain.real_bathymetry import depth_to_bottom_type
        assert depth_to_bottom_type(500.0) == BottomType.MUD

    def test_deep_is_clay(self) -> None:
        from stochastic_warfare.terrain.real_bathymetry import depth_to_bottom_type
        assert depth_to_bottom_type(2000.0) == BottomType.CLAY


# ── GEBCO Loader ─────────────────────────────────────────────────────────


class TestGebcoBathymetryLoader:
    @pytest.fixture(autouse=True)
    def _skip_without_xarray(self) -> None:
        pytest.importorskip("xarray")

    def test_depth_convention_negated(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_bathymetry import load_gebco_bathymetry

        lats = np.linspace(-52.5, -51.0, 20)
        lons = np.linspace(-60.0, -58.5, 20)
        # GEBCO: negative = below sea level → our depth should be positive
        elevation = np.full((20, 20), -500.0)
        nc_path = tmp_path / "gebco.nc"
        _make_gebco_netcdf(nc_path, lats, lons, elevation)

        bathy = load_gebco_bathymetry(nc_path, bbox, 1000.0, projection)
        # All cells should have positive depth ~500
        assert np.all(bathy._depth > 0)
        assert np.mean(bathy._depth) > 400

    def test_land_cells_clamped(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_bathymetry import load_gebco_bathymetry

        lats = np.linspace(-52.5, -51.0, 10)
        lons = np.linspace(-60.0, -58.5, 10)
        # Mix of land (+100m) and sea (-200m)
        elevation = np.full((10, 10), -200.0)
        elevation[:5, :] = 100.0  # Southern half is land
        nc_path = tmp_path / "gebco_mixed.nc"
        _make_gebco_netcdf(nc_path, lats, lons, elevation)

        bathy = load_gebco_bathymetry(nc_path, bbox, 2000.0, projection)
        # All depth values should be >= 0
        assert np.all(bathy._depth >= 0)

    def test_bottom_type_classification(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_bathymetry import load_gebco_bathymetry

        lats = np.linspace(-52.5, -51.0, 10)
        lons = np.linspace(-60.0, -58.5, 10)
        elevation = np.full((10, 10), -30.0)  # Shallow → SAND
        nc_path = tmp_path / "gebco_shallow.nc"
        _make_gebco_netcdf(nc_path, lats, lons, elevation)

        bathy = load_gebco_bathymetry(nc_path, bbox, 2000.0, projection)
        # Shallow water should be SAND
        assert np.all(bathy._bottom == BottomType.SAND.value)

    def test_bilinear_resampling(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_bathymetry import load_gebco_bathymetry

        lats = np.linspace(-52.5, -51.0, 30)
        lons = np.linspace(-60.0, -58.5, 30)
        elevation = np.full((30, 30), -100.0)
        nc_path = tmp_path / "gebco_resample.nc"
        _make_gebco_netcdf(nc_path, lats, lons, elevation)

        bathy_coarse = load_gebco_bathymetry(nc_path, bbox, 5000.0, projection)
        bathy_fine = load_gebco_bathymetry(nc_path, bbox, 2000.0, projection)
        assert bathy_fine.shape[0] > bathy_coarse.shape[0]

    def test_enu_grid_alignment(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_bathymetry import load_gebco_bathymetry

        lats = np.linspace(-52.5, -51.0, 10)
        lons = np.linspace(-60.0, -58.5, 10)
        elevation = np.full((10, 10), -500.0)
        nc_path = tmp_path / "gebco_enu.nc"
        _make_gebco_netcdf(nc_path, lats, lons, elevation)

        bathy = load_gebco_bathymetry(nc_path, bbox, 2000.0, projection)
        sw = projection.geodetic_to_enu(-52.5, -60.0)
        assert abs(bathy._config.origin_easting - sw.easting) < 1.0
        assert abs(bathy._config.origin_northing - sw.northing) < 1.0

    def test_get_state_set_state(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_bathymetry import load_gebco_bathymetry

        lats = np.linspace(-52.5, -51.0, 10)
        lons = np.linspace(-60.0, -58.5, 10)
        elevation = np.full((10, 10), -100.0)
        nc_path = tmp_path / "gebco_state.nc"
        _make_gebco_netcdf(nc_path, lats, lons, elevation)

        bathy = load_gebco_bathymetry(nc_path, bbox, 5000.0, projection)
        state = bathy.get_state()
        assert "depth" in state

    def test_deep_ocean_clay(
        self, tmp_path: Path, bbox: BoundingBox, projection,
    ) -> None:
        from stochastic_warfare.terrain.real_bathymetry import load_gebco_bathymetry

        lats = np.linspace(-52.5, -51.0, 10)
        lons = np.linspace(-60.0, -58.5, 10)
        elevation = np.full((10, 10), -5000.0)  # Very deep
        nc_path = tmp_path / "gebco_deep.nc"
        _make_gebco_netcdf(nc_path, lats, lons, elevation)

        bathy = load_gebco_bathymetry(nc_path, bbox, 5000.0, projection)
        assert np.all(bathy._bottom == BottomType.CLAY.value)

"""Tests for coordinates/transforms.py."""

import pytest

from stochastic_warfare.coordinates.transforms import ScenarioProjection
from stochastic_warfare.core.types import Position


class TestOrigin:
    def test_origin_maps_to_zero(self) -> None:
        proj = ScenarioProjection(origin_lat=29.0, origin_lon=47.0)
        pos = proj.geodetic_to_enu(29.0, 47.0)
        assert abs(pos.easting) < 0.001
        assert abs(pos.northing) < 0.001

    def test_origin_enu_property(self) -> None:
        proj = ScenarioProjection(origin_lat=0.0, origin_lon=0.0)
        assert proj.origin_enu == Position(0.0, 0.0, 0.0)


class TestRoundTrip:
    @pytest.mark.parametrize(
        "lat,lon",
        [
            (29.3, 47.9),     # Kuwait
            (48.8566, 2.3522),  # Paris
            (-33.87, 151.21),   # Sydney
            (0.0, 0.0),        # Null Island
        ],
    )
    def test_geodetic_enu_roundtrip(self, lat: float, lon: float) -> None:
        proj = ScenarioProjection(origin_lat=lat, origin_lon=lon)
        # Pick a point ~1km away
        test_lat = lat + 0.009  # ~1km north
        test_lon = lon + 0.012  # ~1km east (varies with latitude)

        enu = proj.geodetic_to_enu(test_lat, test_lon, alt=50.0)
        geo = proj.enu_to_geodetic(enu)

        assert geo.latitude == pytest.approx(test_lat, abs=1e-6)
        assert geo.longitude == pytest.approx(test_lon, abs=1e-6)
        assert geo.altitude == pytest.approx(50.0)


class TestUTM:
    def test_utm_zone(self) -> None:
        proj = ScenarioProjection(origin_lat=29.0, origin_lon=47.0)
        assert proj.utm_zone == 38

    def test_geodetic_to_utm_returns_four_tuple(self) -> None:
        proj = ScenarioProjection(origin_lat=29.0, origin_lon=47.0)
        e, n, zone, band = proj.geodetic_to_utm(29.0, 47.0)
        assert isinstance(e, float)
        assert isinstance(n, float)
        assert zone == 38
        assert isinstance(band, str)

    def test_utm_round_trip(self) -> None:
        proj = ScenarioProjection(origin_lat=29.0, origin_lon=47.0)
        e, n, zone, band = proj.geodetic_to_utm(29.5, 47.5)
        geo = proj.utm_to_geodetic(e, n, zone, band)
        assert geo.latitude == pytest.approx(29.5, abs=1e-6)
        assert geo.longitude == pytest.approx(47.5, abs=1e-6)

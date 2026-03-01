"""Coordinate transforms: Geodetic <-> UTM <-> ENU.

All internal simulation math uses ENU (East-North-Up) meters relative to
a scenario-defined origin.  This module wraps ``pyproj`` for the heavy
lifting and provides a clean, scenario-scoped API.
"""

from __future__ import annotations

import math

from pyproj import Transformer

from stochastic_warfare.core.types import GeodeticPosition, Position


def _utm_zone_from_lon(lon: float) -> int:
    """Return the UTM zone number for a given longitude."""
    return int((lon + 180) / 6) + 1


def _utm_band_from_lat(lat: float) -> str:
    """Return the UTM latitude band letter."""
    bands = "CDEFGHJKLMNPQRSTUVWX"
    idx = int((lat + 80) / 8)
    idx = max(0, min(idx, len(bands) - 1))
    return bands[idx]


class ScenarioProjection:
    """Defines the coordinate projection for a scenario.

    All conversions are anchored to a geodetic origin that becomes
    ENU ``(0, 0, 0)``.

    Parameters
    ----------
    origin_lat, origin_lon:
        WGS-84 coordinates of the scenario origin.
    """

    def __init__(self, origin_lat: float, origin_lon: float) -> None:
        self._origin_lat = origin_lat
        self._origin_lon = origin_lon
        self._utm_zone = _utm_zone_from_lon(origin_lon)
        self._utm_band = _utm_band_from_lat(origin_lat)

        # pyproj transformers (thread-safe, reusable)
        utm_crs = f"+proj=utm +zone={self._utm_zone} +datum=WGS84"
        if origin_lat < 0:
            utm_crs += " +south"

        self._geo_to_utm = Transformer.from_crs(
            "EPSG:4326", utm_crs, always_xy=True
        )
        self._utm_to_geo = Transformer.from_crs(
            utm_crs, "EPSG:4326", always_xy=True
        )

        # Origin in UTM (used to compute ENU offsets)
        self._origin_utm_e, self._origin_utm_n = self._geo_to_utm.transform(
            origin_lon, origin_lat
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def utm_zone(self) -> int:
        return self._utm_zone

    @property
    def utm_band(self) -> str:
        return self._utm_band

    @property
    def origin_enu(self) -> Position:
        return Position(0.0, 0.0, 0.0)

    # ------------------------------------------------------------------
    # Conversions
    # ------------------------------------------------------------------

    def geodetic_to_enu(
        self, lat: float, lon: float, alt: float = 0.0
    ) -> Position:
        """Convert WGS-84 geodetic to local ENU meters."""
        utm_e, utm_n = self._geo_to_utm.transform(lon, lat)
        return Position(
            easting=utm_e - self._origin_utm_e,
            northing=utm_n - self._origin_utm_n,
            altitude=alt,
        )

    def enu_to_geodetic(self, pos: Position) -> GeodeticPosition:
        """Convert local ENU meters back to WGS-84 geodetic."""
        utm_e = pos.easting + self._origin_utm_e
        utm_n = pos.northing + self._origin_utm_n
        lon, lat = self._utm_to_geo.transform(utm_e, utm_n)
        return GeodeticPosition(latitude=lat, longitude=lon, altitude=pos.altitude)

    def geodetic_to_utm(
        self, lat: float, lon: float
    ) -> tuple[float, float, int, str]:
        """Convert geodetic to UTM (easting, northing, zone, band)."""
        e, n = self._geo_to_utm.transform(lon, lat)
        return (e, n, self._utm_zone, self._utm_band)

    def utm_to_geodetic(
        self, easting: float, northing: float, zone: int, band: str
    ) -> GeodeticPosition:
        """Convert UTM back to geodetic.

        Note: *zone* and *band* are accepted for API consistency but this
        method uses the scenario's projection.  Cross-zone conversion is
        not yet supported.
        """
        lon, lat = self._utm_to_geo.transform(easting, northing)
        return GeodeticPosition(latitude=lat, longitude=lon, altitude=0.0)

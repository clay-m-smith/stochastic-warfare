"""Spatial utility functions operating on ENU positions."""

from __future__ import annotations

import math

from stochastic_warfare.core.types import Meters, Position, Radians


def distance(a: Position, b: Position) -> Meters:
    """3-D Euclidean distance between two ENU positions."""
    return math.sqrt(
        (b.easting - a.easting) ** 2
        + (b.northing - a.northing) ** 2
        + (b.altitude - a.altitude) ** 2
    )


def distance_2d(a: Position, b: Position) -> Meters:
    """Horizontal (easting/northing) distance, ignoring altitude."""
    return math.sqrt(
        (b.easting - a.easting) ** 2 + (b.northing - a.northing) ** 2
    )


def bearing(from_pos: Position, to_pos: Position) -> Radians:
    """Azimuth from *from_pos* to *to_pos* in radians (0 = north, π/2 = east).

    Returns a value in ``[0, 2π)``.
    """
    de = to_pos.easting - from_pos.easting
    dn = to_pos.northing - from_pos.northing
    angle = math.atan2(de, dn)  # atan2(east, north) → azimuth from north
    if angle < 0:
        angle += 2 * math.pi
    return angle


def point_at(
    origin: Position, brg: Radians, dist: Meters
) -> Position:
    """Return the position at *dist* meters along azimuth *brg* from *origin*.

    Altitude is preserved from *origin*.
    """
    de = dist * math.sin(brg)
    dn = dist * math.cos(brg)
    return Position(
        easting=origin.easting + de,
        northing=origin.northing + dn,
        altitude=origin.altitude,
    )

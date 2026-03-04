"""Space-domain events published on the EventBus.

Covers satellite overpasses, GPS accuracy changes, SATCOM windows, ASAT
engagements, constellation degradation, early warning detections, and
debris cascade events.
"""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event


# ---------------------------------------------------------------------------
# Satellite overpass / constellation events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SatelliteOverpassEvent(Event):
    """Published when a satellite enters or exits coverage of the theater."""

    satellite_id: str
    constellation_id: str
    side: str
    overpass_start: bool
    coverage_center_x: float
    coverage_center_y: float
    coverage_radius_m: float
    resolution_m: float


@dataclass(frozen=True)
class ConstellationDegradedEvent(Event):
    """Published when a constellation loses satellites."""

    constellation_id: str
    previous_count: int
    new_count: int
    cause: str  # "asat_kinetic", "asat_laser", "debris", "malfunction"


# ---------------------------------------------------------------------------
# GPS events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GPSAccuracyChangedEvent(Event):
    """Published when GPS accuracy changes significantly."""

    side: str
    previous_accuracy_m: float
    new_accuracy_m: float
    visible_satellites: int
    dop: float


# ---------------------------------------------------------------------------
# SATCOM events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SATCOMWindowEvent(Event):
    """Published when a SATCOM window opens or closes."""

    side: str
    satellite_id: str
    window_open: bool
    bandwidth_bps: float


# ---------------------------------------------------------------------------
# ASAT events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ASATEngagementEvent(Event):
    """Published when an ASAT weapon engages a satellite."""

    weapon_id: str
    target_satellite_id: str
    hit: bool
    pk: float
    debris_generated: int


@dataclass(frozen=True)
class DebrisCascadeEvent(Event):
    """Published when orbital debris causes a cascade risk increase."""

    altitude_band_km: float
    debris_count: int
    collision_probability_per_orbit: float


# ---------------------------------------------------------------------------
# Early warning events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EarlyWarningDetectionEvent(Event):
    """Published when an early warning satellite detects a missile launch."""

    satellite_id: str
    launch_position_x: float
    launch_position_y: float
    detection_delay_s: float
    confidence: float

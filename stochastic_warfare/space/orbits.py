"""Orbital mechanics engine — simplified Keplerian propagation.

Provides two-body orbital propagation with J2 secular perturbations for
RAAN precession.  Sufficient for campaign-scale "when does satellite see
theater?" queries without full SGP4/TLE complexity.

Key physics:
- Kepler's equation solved via Newton-Raphson
- J2 secular RAAN drift: dΩ/dt = -3/2 · J2 · (R_e/a)² · n · cos(i)
- Subsatellite point accounting for Earth rotation
- Geometric visibility from satellite altitude and ground distance
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MU_EARTH: float = 3.986004418e14  # m³/s² — Earth gravitational parameter
R_EARTH: float = 6_371_000.0  # m — mean Earth radius
J2: float = 1.08263e-3  # second zonal harmonic
T_EARTH: float = 86164.1  # s — sidereal day
OMEGA_EARTH: float = 2.0 * math.pi / T_EARTH  # rad/s — Earth rotation rate

_DEG2RAD: float = math.pi / 180.0
_RAD2DEG: float = 180.0 / math.pi


# ---------------------------------------------------------------------------
# Enums & models
# ---------------------------------------------------------------------------


class OrbitType(enum.IntEnum):
    """Classification of orbital regime."""

    LEO = 0  # Low Earth Orbit: 200-2000 km
    MEO = 1  # Medium Earth Orbit: 2000-35786 km
    GEO = 2  # Geostationary: ~35786 km
    HEO = 3  # Highly Elliptical Orbit (e.g., Molniya)


class OrbitalElements(BaseModel):
    """Classical Keplerian orbital elements."""

    semi_major_axis_m: float  # a
    eccentricity: float = 0.0  # e
    inclination_deg: float = 0.0  # i
    raan_deg: float = 0.0  # Ω — right ascension of ascending node
    arg_perigee_deg: float = 0.0  # ω — argument of perigee
    true_anomaly_deg: float = 0.0  # ν — initial true anomaly


@dataclass
class SatelliteState:
    """Runtime state for a single satellite."""

    satellite_id: str
    constellation_id: str
    elements: OrbitalElements
    is_active: bool = True
    current_true_anomaly_deg: float = 0.0
    current_raan_deg: float = 0.0
    side: str = "blue"

    def __post_init__(self) -> None:
        if self.current_true_anomaly_deg == 0.0:
            self.current_true_anomaly_deg = self.elements.true_anomaly_deg
        if self.current_raan_deg == 0.0:
            self.current_raan_deg = self.elements.raan_deg


# ---------------------------------------------------------------------------
# OrbitalMechanicsEngine
# ---------------------------------------------------------------------------


class OrbitalMechanicsEngine:
    """Two-body Keplerian propagation with J2 secular perturbations."""

    def orbital_period(self, a: float) -> float:
        """Orbital period in seconds.  T = 2π√(a³/μ)."""
        if a <= 0:
            return 0.0
        return 2.0 * math.pi * math.sqrt(a ** 3 / MU_EARTH)

    def mean_motion(self, a: float) -> float:
        """Mean motion in rad/s.  n = √(μ/a³)."""
        if a <= 0:
            return 0.0
        return math.sqrt(MU_EARTH / a ** 3)

    def solve_kepler(self, M: float, e: float, tol: float = 1e-10) -> float:
        """Solve Kepler's equation M = E - e·sin(E) via Newton-Raphson.

        Parameters
        ----------
        M : float
            Mean anomaly in radians.
        e : float
            Eccentricity.
        tol : float
            Convergence tolerance.

        Returns
        -------
        float
            Eccentric anomaly E in radians.
        """
        # Normalize M to [0, 2π)
        M = M % (2.0 * math.pi)
        # Initial guess
        E = M + e * math.sin(M) if e < 0.8 else math.pi
        for _ in range(50):
            dE = (E - e * math.sin(E) - M) / (1.0 - e * math.cos(E))
            E -= dE
            if abs(dE) < tol:
                break
        return E

    def true_anomaly_from_eccentric(self, E: float, e: float) -> float:
        """Convert eccentric anomaly E to true anomaly ν.

        Uses the half-angle formula:
        tan(ν/2) = √((1+e)/(1-e)) · tan(E/2)
        """
        if e >= 1.0:
            return E  # degenerate
        half_nu = math.atan2(
            math.sqrt(1.0 + e) * math.sin(E / 2.0),
            math.sqrt(1.0 - e) * math.cos(E / 2.0),
        )
        return 2.0 * half_nu

    def propagate(self, sat: SatelliteState, dt_s: float) -> SatelliteState:
        """Advance satellite state by *dt_s* seconds.

        1. Advance mean anomaly: M += n·dt
        2. Solve Kepler → E → true anomaly
        3. J2 secular RAAN precession: dΩ/dt = -3/2·J2·(R_e/a)²·n·cos(i)
        """
        if not sat.is_active or dt_s <= 0.0:
            return sat

        elems = sat.elements
        a = elems.semi_major_axis_m
        e = elems.eccentricity
        i_rad = elems.inclination_deg * _DEG2RAD

        n = self.mean_motion(a)

        # Current true anomaly → eccentric → mean anomaly (reverse)
        nu_rad = sat.current_true_anomaly_deg * _DEG2RAD
        E_current = 2.0 * math.atan2(
            math.sqrt(1.0 - e) * math.sin(nu_rad / 2.0),
            math.sqrt(1.0 + e) * math.cos(nu_rad / 2.0),
        )
        M_current = E_current - e * math.sin(E_current)

        # Advance mean anomaly
        M_new = M_current + n * dt_s

        # Solve Kepler for new eccentric anomaly
        E_new = self.solve_kepler(M_new, e)
        nu_new = self.true_anomaly_from_eccentric(E_new, e)
        nu_new_deg = (nu_new * _RAD2DEG) % 360.0

        # J2 RAAN precession
        if a > 0:
            p = a * (1.0 - e ** 2)
            d_raan = -1.5 * J2 * (R_EARTH / p) ** 2 * n * math.cos(i_rad) * dt_s
            new_raan = (sat.current_raan_deg + d_raan * _RAD2DEG) % 360.0
        else:
            new_raan = sat.current_raan_deg

        sat.current_true_anomaly_deg = nu_new_deg
        sat.current_raan_deg = new_raan
        return sat

    def subsatellite_point(
        self, sat: SatelliteState, sim_time_s: float,
    ) -> tuple[float, float]:
        """Compute subsatellite point (lat_deg, lon_deg).

        Accounts for Earth rotation since sim start (t=0).
        """
        elems = sat.elements
        a = elems.semi_major_axis_m
        e = elems.eccentricity
        i_rad = elems.inclination_deg * _DEG2RAD
        omega_rad = elems.arg_perigee_deg * _DEG2RAD
        nu_rad = sat.current_true_anomaly_deg * _DEG2RAD
        raan_rad = sat.current_raan_deg * _DEG2RAD

        # Argument of latitude
        u = omega_rad + nu_rad

        # Geocentric latitude
        lat_rad = math.asin(math.sin(i_rad) * math.sin(u))

        # Longitude in inertial frame
        if abs(math.cos(lat_rad)) < 1e-12:
            lon_inertial = raan_rad
        else:
            lon_inertial = raan_rad + math.atan2(
                math.cos(i_rad) * math.sin(u),
                math.cos(u),
            )

        # Account for Earth rotation
        lon_rad = lon_inertial - OMEGA_EARTH * sim_time_s

        # Normalize to [-180, 180]
        lat_deg = lat_rad * _RAD2DEG
        lon_deg = ((lon_rad * _RAD2DEG + 180.0) % 360.0) - 180.0

        return (lat_deg, lon_deg)

    def is_visible_from(
        self,
        sat: SatelliteState,
        theater_lat: float,
        theater_lon: float,
        sim_time_s: float,
        min_elevation_deg: float = 5.0,
    ) -> bool:
        """Check geometric visibility of satellite from a ground point.

        Uses the satellite altitude and angular distance to determine if
        the satellite is above the minimum elevation angle.
        """
        if not sat.is_active:
            return False

        elems = sat.elements
        a = elems.semi_major_axis_m
        e = elems.eccentricity
        nu_rad = sat.current_true_anomaly_deg * _DEG2RAD

        # Orbital radius at current true anomaly
        r = a * (1.0 - e ** 2) / (1.0 + e * math.cos(nu_rad))
        altitude = r - R_EARTH
        if altitude <= 0:
            return False

        # Subsatellite point
        sub_lat, sub_lon = self.subsatellite_point(sat, sim_time_s)

        # Great-circle angular distance (radians)
        lat1 = theater_lat * _DEG2RAD
        lat2 = sub_lat * _DEG2RAD
        dlon = (sub_lon - theater_lon) * _DEG2RAD

        cos_d = (math.sin(lat1) * math.sin(lat2)
                 + math.cos(lat1) * math.cos(lat2) * math.cos(dlon))
        cos_d = max(-1.0, min(1.0, cos_d))
        d = math.acos(cos_d)  # central angle

        # Elevation angle from ground point
        # el = atan((cos(d) - R_e/(R_e+h)) / sin(d))
        sin_d = math.sin(d)
        if sin_d < 1e-12:
            # Directly overhead
            return True
        rho = R_EARTH / (R_EARTH + altitude)
        el = math.atan((cos_d - rho) / sin_d)

        return el >= (min_elevation_deg * _DEG2RAD)

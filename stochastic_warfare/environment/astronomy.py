"""Astronomical computations: solar/lunar positions, rise/set, tidal forcing.

All algorithms from Meeus, *Astronomical Algorithms* (2nd ed.).  This module
has no external dependencies beyond the core clock — ephem / astropy are not
required.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from stochastic_warfare.core.clock import SimulationClock

_DEG = math.pi / 180.0
_RAD = 180.0 / math.pi
_J2000 = 2451545.0  # Julian date of J2000.0 epoch


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class CelestialPosition(NamedTuple):
    """Horizontal coordinates of a celestial body."""

    azimuth: float  # radians, 0=north, π/2=east
    elevation: float  # radians, 0=horizon, π/2=zenith
    distance: float  # km (AU converted for Sun)


class TwilightTimes(NamedTuple):
    """Times (fractional hour UTC) of twilight transitions for a date."""

    astronomical_dawn: float | None
    nautical_dawn: float | None
    civil_dawn: float | None
    sunrise: float | None
    sunset: float | None
    civil_dusk: float | None
    nautical_dusk: float | None
    astronomical_dusk: float | None


class LunarPhase(NamedTuple):
    """Current lunar phase information."""

    phase_angle: float  # degrees, 0=new, 180=full
    illumination_fraction: float  # 0.0–1.0
    phase_name: str  # "new", "waxing_crescent", etc.


# ---------------------------------------------------------------------------
# AstronomyEngine
# ---------------------------------------------------------------------------


class AstronomyEngine:
    """Computes solar and lunar positions from simulation time.

    Parameters
    ----------
    clock:
        The simulation clock (provides Julian date and current time).
    """

    def __init__(self, clock: SimulationClock) -> None:
        self._clock = clock

    # ------------------------------------------------------------------
    # Solar position
    # ------------------------------------------------------------------

    def solar_position(self, lat: float, lon: float) -> CelestialPosition:
        """Sun's horizontal position at *lat/lon* for the current sim time."""
        return self.solar_position_at(lat, lon, self._clock.julian_date)

    def solar_position_at(
        self, lat: float, lon: float, jd: float
    ) -> CelestialPosition:
        """Sun's horizontal position at *lat/lon* for a given Julian date."""
        ra, dec, dist_au = _solar_equatorial(jd)
        az, el = _equatorial_to_horizontal(ra, dec, lat, lon, jd)
        return CelestialPosition(az, el, dist_au * 149_597_870.7)

    def twilight_times(
        self, lat: float, lon: float, date: datetime
    ) -> TwilightTimes:
        """Compute sunrise/sunset and twilight times for a date."""
        # Julian date at 0h UT on the given date
        jd0 = _jd_at_midnight(date)

        sunrise = _find_rise_set(jd0, lat, lon, -0.8333, rising=True)
        sunset = _find_rise_set(jd0, lat, lon, -0.8333, rising=False)
        civil_dawn = _find_rise_set(jd0, lat, lon, -6.0, rising=True)
        civil_dusk = _find_rise_set(jd0, lat, lon, -6.0, rising=False)
        nautical_dawn = _find_rise_set(jd0, lat, lon, -12.0, rising=True)
        nautical_dusk = _find_rise_set(jd0, lat, lon, -12.0, rising=False)
        astro_dawn = _find_rise_set(jd0, lat, lon, -18.0, rising=True)
        astro_dusk = _find_rise_set(jd0, lat, lon, -18.0, rising=False)

        return TwilightTimes(
            astronomical_dawn=astro_dawn,
            nautical_dawn=nautical_dawn,
            civil_dawn=civil_dawn,
            sunrise=sunrise,
            sunset=sunset,
            civil_dusk=civil_dusk,
            nautical_dusk=nautical_dusk,
            astronomical_dusk=astro_dusk,
        )

    def day_length_hours(self, lat: float, lon: float) -> float:
        """Hours of daylight for the current sim date."""
        dt = self._clock.current_time
        tt = self.twilight_times(lat, lon, dt)
        if tt.sunrise is None or tt.sunset is None:
            # Polar day or polar night
            jd = self._clock.julian_date
            _, dec, _ = _solar_equatorial(jd)
            # If declination and latitude are same sign → polar day
            if lat * (dec * _RAD) > 0:
                return 24.0
            return 0.0
        length = tt.sunset - tt.sunrise
        if length < 0:
            length += 24.0
        return length

    # ------------------------------------------------------------------
    # Lunar position
    # ------------------------------------------------------------------

    def lunar_position(self, lat: float, lon: float) -> CelestialPosition:
        """Moon's horizontal position at *lat/lon* for the current sim time."""
        jd = self._clock.julian_date
        ra, dec, dist_km = _lunar_equatorial(jd)
        az, el = _equatorial_to_horizontal(ra, dec, lat, lon, jd)
        return CelestialPosition(az, el, dist_km)

    def lunar_phase(self) -> LunarPhase:
        """Current lunar phase."""
        jd = self._clock.julian_date
        # Sun and Moon ecliptic longitudes
        T = (jd - _J2000) / 36525.0
        sun_lon = _solar_ecliptic_longitude(T)

        # Simplified lunar ecliptic longitude
        lp = (218.3165 + 481267.8813 * T) % 360.0
        D = lp - sun_lon  # elongation
        phase_angle = abs(D % 360.0)
        if phase_angle > 180.0:
            phase_angle = 360.0 - phase_angle

        # Convention: phase_angle 0° = new moon, 180° = full moon
        # Illumination: 0 at new (phase_angle=0), 1 at full (phase_angle=180)
        illum = (1 - math.cos(phase_angle * _DEG)) / 2.0
        name = _phase_name(D % 360.0)
        return LunarPhase(phase_angle, illum, name)

    def moonrise_moonset(
        self, lat: float, lon: float, date: datetime
    ) -> tuple[float | None, float | None]:
        """Approximate moonrise and moonset times (hour UTC) for a date."""
        jd0 = _jd_at_midnight(date)
        # Moon rises when elevation ≈ +0.125° (parallax corrected)
        rise = _find_moon_rise_set(jd0, lat, lon, rising=True)
        sset = _find_moon_rise_set(jd0, lat, lon, rising=False)
        return (rise, sset)

    # ------------------------------------------------------------------
    # Tidal forcing
    # ------------------------------------------------------------------

    def tidal_forcing(self) -> float:
        """Relative tidal forcing factor (~0.5 neap to ~1.5 spring).

        Proportional to alignment of Sun and Moon (spring tides at
        full/new moon, neap at quarters).
        """
        phase = self.lunar_phase()
        # phase_angle: 0° = new, 180° = full — both are spring tides
        # cos(0) = 1 (new/spring), cos(90) = 0 (quarter/neap), cos(180) = -1 (full)
        # We want: spring (0° and 180°) = high, neap (90°) = low
        # Use cos(2 * phase_angle) which is +1 at 0° and 180°, -1 at 90°
        return 1.0 + 0.5 * math.cos(2 * phase.phase_angle * _DEG)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {}  # stateless — derives everything from clock

    def set_state(self, state: dict) -> None:
        pass


# ======================================================================
# Internal Meeus algorithms
# ======================================================================


def _solar_ecliptic_longitude(T: float) -> float:
    """Solar geometric ecliptic longitude in degrees (Meeus Ch. 25)."""
    # Mean anomaly
    M = (357.5291 + 35999.0503 * T) % 360.0
    Mr = M * _DEG

    # Equation of center
    C = (1.9146 - 0.004817 * T) * math.sin(Mr) + 0.019993 * math.sin(2 * Mr) + 0.00029 * math.sin(3 * Mr)

    # Sun's geometric ecliptic longitude
    L0 = (280.46646 + 36000.76983 * T) % 360.0
    return (L0 + C) % 360.0


def _solar_equatorial(jd: float) -> tuple[float, float, float]:
    """Solar right ascension (rad), declination (rad), distance (AU)."""
    T = (jd - _J2000) / 36525.0

    lon = _solar_ecliptic_longitude(T)
    M = (357.5291 + 35999.0503 * T) % 360.0
    Mr = M * _DEG

    # Distance
    e = 0.016709 - 0.000042 * T
    R = (1.000001018 * (1 - e * e)) / (1 + e * math.cos(Mr + (lon - (280.46646 + 36000.76983 * T) % 360.0) * _DEG))

    # Obliquity
    eps = (23.4393 - 0.01300 * T) * _DEG

    lon_r = lon * _DEG
    ra = math.atan2(math.cos(eps) * math.sin(lon_r), math.cos(lon_r))
    dec = math.asin(math.sin(eps) * math.sin(lon_r))

    return (ra, dec, R)


def _lunar_equatorial(jd: float) -> tuple[float, float, float]:
    """Simplified lunar RA (rad), Dec (rad), distance (km) — Meeus Ch. 47."""
    T = (jd - _J2000) / 36525.0

    # Fundamental arguments (degrees)
    Lp = (218.3165 + 481267.8813 * T) % 360.0  # mean longitude
    D = (297.8502 + 445267.1115 * T) % 360.0  # mean elongation
    M = (357.5291 + 35999.0503 * T) % 360.0  # sun mean anomaly
    Mp = (134.9634 + 477198.8676 * T) % 360.0  # moon mean anomaly
    F = (93.2720 + 483202.0175 * T) % 360.0  # argument of latitude

    # Convert to radians
    Dr, Mr, Mpr, Fr = D * _DEG, M * _DEG, Mp * _DEG, F * _DEG

    # Simplified longitude and latitude perturbations
    lon_pert = (
        6.289 * math.sin(Mpr)
        - 1.274 * math.sin(2 * Dr - Mpr)
        + 0.658 * math.sin(2 * Dr)
        - 0.214 * math.sin(2 * Mpr)
        - 0.186 * math.sin(Mr)
        - 0.114 * math.sin(2 * Fr)
    )
    lat_pert = (
        5.128 * math.sin(Fr)
        + 0.281 * math.sin(Mpr + Fr)
        - 0.278 * math.sin(Fr - Mpr)
        - 0.173 * math.sin(Fr - 2 * Dr)
    )
    dist_pert = (
        -20.905 * math.cos(Mpr)
        - 3.699 * math.cos(2 * Dr - Mpr)
        - 2.956 * math.cos(2 * Dr)
    )

    ecl_lon = (Lp + lon_pert) * _DEG
    ecl_lat = lat_pert * _DEG
    dist_km = 385000.56 + dist_pert * 1000.0

    # Ecliptic to equatorial
    eps = (23.4393 - 0.01300 * T) * _DEG
    ra = math.atan2(
        math.sin(ecl_lon) * math.cos(eps) - math.tan(ecl_lat) * math.sin(eps),
        math.cos(ecl_lon),
    )
    dec = math.asin(
        math.sin(ecl_lat) * math.cos(eps)
        + math.cos(ecl_lat) * math.sin(eps) * math.sin(ecl_lon)
    )

    return (ra, dec, dist_km)


def _equatorial_to_horizontal(
    ra: float, dec: float, lat: float, lon: float, jd: float
) -> tuple[float, float]:
    """Convert RA/Dec (radians) to azimuth/elevation (radians) — Meeus Ch. 13."""
    # Greenwich mean sidereal time
    T = (jd - _J2000) / 36525.0
    gmst_deg = (280.46061837 + 360.98564736629 * (jd - _J2000) + 0.000387933 * T * T) % 360.0

    # Local hour angle
    H = (gmst_deg + lon) * _DEG - ra

    lat_r = lat * _DEG
    sin_lat = math.sin(lat_r)
    cos_lat = math.cos(lat_r)
    sin_dec = math.sin(dec)
    cos_dec = math.cos(dec)
    sin_H = math.sin(H)
    cos_H = math.cos(H)

    # Elevation
    el = math.asin(sin_lat * sin_dec + cos_lat * cos_dec * cos_H)

    # Azimuth (measured from north, clockwise)
    az = math.atan2(sin_H, cos_H * sin_lat - math.tan(dec) * cos_lat)
    az = (az + math.pi) % (2 * math.pi)

    return (az, el)


def _find_rise_set(
    jd0: float, lat: float, lon: float, depression: float, *, rising: bool
) -> float | None:
    """Find the hour UTC when the Sun reaches *depression* degrees elevation.

    Uses iterative refinement (Meeus Ch. 15 approach).  Returns None if
    the event does not occur (polar day/night).
    """
    # Initial estimate at local noon
    T = (jd0 - _J2000) / 36525.0
    _, dec, _ = _solar_equatorial(jd0 + 0.5)
    lat_r = lat * _DEG
    dep_r = depression * _DEG

    cos_H0 = (math.sin(dep_r) - math.sin(lat_r) * math.sin(dec)) / (
        math.cos(lat_r) * math.cos(dec)
    )

    if cos_H0 < -1.0 or cos_H0 > 1.0:
        return None  # never rises/sets at this depression

    H0 = math.acos(cos_H0) * _RAD  # degrees

    # Solar noon in hours (approximate)
    noon_ut = 12.0 - lon / 15.0

    if rising:
        hour = noon_ut - H0 / 15.0
    else:
        hour = noon_ut + H0 / 15.0

    # One iteration of refinement
    jd_est = jd0 + hour / 24.0
    _, dec2, _ = _solar_equatorial(jd_est)
    cos_H1 = (math.sin(dep_r) - math.sin(lat_r) * math.sin(dec2)) / (
        math.cos(lat_r) * math.cos(dec2)
    )
    if -1.0 <= cos_H1 <= 1.0:
        H1 = math.acos(cos_H1) * _RAD
        if rising:
            hour = noon_ut - H1 / 15.0
        else:
            hour = noon_ut + H1 / 15.0

    # Normalise to 0–24
    return hour % 24.0


def _find_moon_rise_set(
    jd0: float, lat: float, lon: float, *, rising: bool
) -> float | None:
    """Approximate moonrise/moonset by scanning hourly."""
    prev_el: float | None = None
    for h in range(25):
        jd = jd0 + h / 24.0
        ra, dec, _ = _lunar_equatorial(jd)
        _, el = _equatorial_to_horizontal(ra, dec, lat, lon, jd)

        if prev_el is not None:
            threshold = 0.00218  # ~0.125° in radians (parallax correction)
            if rising and prev_el < threshold <= el:
                frac = (threshold - prev_el) / (el - prev_el) if el != prev_el else 0.5
                return (h - 1 + frac) % 24.0
            if not rising and prev_el >= threshold > el:
                frac = (prev_el - threshold) / (prev_el - el) if prev_el != el else 0.5
                return (h - 1 + frac) % 24.0
        prev_el = el
    return None


def _jd_at_midnight(date: datetime) -> float:
    """Julian date at 0h UT on the given date."""
    d = date if date.tzinfo else date.replace(tzinfo=timezone.utc)
    d = d.astimezone(timezone.utc)
    midnight = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    y = midnight.year
    m = midnight.month
    day = midnight.day
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + b - 1524.5


def _phase_name(elongation_deg: float) -> str:
    """Human-readable lunar phase name from elongation (0–360)."""
    d = elongation_deg % 360.0
    if d < 22.5 or d >= 337.5:
        return "new"
    if d < 67.5:
        return "waxing_crescent"
    if d < 112.5:
        return "first_quarter"
    if d < 157.5:
        return "waxing_gibbous"
    if d < 202.5:
        return "full"
    if d < 247.5:
        return "waning_gibbous"
    if d < 292.5:
        return "last_quarter"
    return "waning_crescent"

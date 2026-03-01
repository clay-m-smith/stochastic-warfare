"""Simplified World Magnetic Model for declination and bearing conversion.

Implements a low-order dipole + quadrupole approximation of the WMM.
Secular variation is applied from the model epoch to the target date.
Full WMM coefficient loading can be added later for sub-degree accuracy.
"""

from __future__ import annotations

import math
from datetime import datetime

from stochastic_warfare.core.types import Degrees, Radians


# ---------------------------------------------------------------------------
# Model coefficients (dipole + quadrupole terms, WMM-2020 epoch)
# ---------------------------------------------------------------------------

# Main-field Gauss coefficients at epoch 2020.0 (nT)
_G10 = -29404.8  # dipole axial
_G11 = -1450.9  # dipole equatorial
_H11 = 4652.5  # dipole equatorial
_G20 = -2499.6  # quadrupole
_G21 = 2982.0
_H21 = -2991.6
_G22 = 1677.0
_H22 = -734.6

# Secular variation (nT/yr)
_DG10 = 5.7
_DG11 = 7.4
_DH11 = -25.9
_DG20 = -11.0
_DG21 = -7.0
_DH21 = -30.2
_DG22 = -2.1
_DH22 = -23.1

_EPOCH = 2020.0
_EARTH_RADIUS_KM = 6371.2


# ---------------------------------------------------------------------------
# MagneticModel
# ---------------------------------------------------------------------------


class MagneticModel:
    """Simplified WMM for magnetic declination.

    Parameters
    ----------
    epoch:
        Reference epoch of the model coefficients.
    """

    def __init__(self, epoch: float = _EPOCH) -> None:
        self._epoch = epoch

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_declination(self, lat: float, lon: float, date: datetime) -> Degrees:
        """Magnetic declination at a location and date.

        Parameters
        ----------
        lat, lon:
            WGS-84 geodetic latitude and longitude in degrees.
        date:
            Calendar date (timezone-aware or naive).

        Returns
        -------
        Degrees
            Declination in degrees.  Positive = east of true north.
        """
        dt = self._decimal_year(date) - self._epoch

        # Secular-variation-corrected coefficients
        g10 = _G10 + _DG10 * dt
        g11 = _G11 + _DG11 * dt
        h11 = _H11 + _DH11 * dt
        g20 = _G20 + _DG20 * dt
        g21 = _G21 + _DG21 * dt
        h21 = _H21 + _DH21 * dt
        g22 = _G22 + _DG22 * dt
        h22 = _H22 + _DH22 * dt

        # Geocentric colatitude and longitude in radians
        theta = math.radians(90.0 - lat)
        phi = math.radians(lon)

        ct = math.cos(theta)
        st = math.sin(theta)
        cp = math.cos(phi)
        sp = math.sin(phi)
        c2p = math.cos(2 * phi)
        s2p = math.sin(2 * phi)

        # Associated Legendre functions (Schmidt semi-normalised)
        # P10 = cos(theta), P11 = sin(theta)
        # P20 = 0.5*(3*cos^2-1), P21 = sqrt(3)*sin*cos, P22 = sqrt(3)*sin^2
        p10 = ct
        p11 = st
        p20 = 0.5 * (3.0 * ct * ct - 1.0)
        p21 = math.sqrt(3.0) * st * ct
        p22 = math.sqrt(3.0) * st * st

        # dP/dtheta
        dp10 = -st
        dp11 = ct
        dp20 = -3.0 * st * ct
        dp21 = math.sqrt(3.0) * (ct * ct - st * st)
        dp22 = 2.0 * math.sqrt(3.0) * st * ct

        # Radial ratio (r/a)^(n+2) — at surface, r = a, so ratio = 1
        # For simplicity we ignore altitude variation

        # B_theta (southward component, = -dV/dtheta / r)
        b_theta = -(
            g10 * dp10
            + (g11 * cp + h11 * sp) * dp11
            + g20 * dp20
            + (g21 * cp + h21 * sp) * dp21
            + (g22 * c2p + h22 * s2p) * dp22
        )

        # B_phi (eastward component, = -dV/(r*sin(theta)*dphi))
        if st > 1e-10:
            b_phi = -(1.0 / st) * (
                (-g11 * sp + h11 * cp) * p11
                + (-g21 * sp + h21 * cp) * p21
                + 2.0 * (-g22 * s2p + h22 * c2p) * p22
            )
        else:
            # At the pole, use L'Hôpital / limiting form
            b_phi = -(
                (-g11 * sp + h11 * cp) * dp11
                + (-g21 * sp + h21 * cp) * dp21
                + 2.0 * (-g22 * s2p + h22 * c2p) * dp22
            )

        # Horizontal components (north, east)
        # B_theta is southward, so B_north = -B_theta
        b_north = -b_theta
        b_east = b_phi

        declination = math.degrees(math.atan2(b_east, b_north))
        return declination

    def true_to_magnetic(self, true_bearing: Radians, declination: Degrees) -> Radians:
        """Convert a true bearing to magnetic bearing."""
        return true_bearing - math.radians(declination)

    def magnetic_to_true(self, magnetic_bearing: Radians, declination: Degrees) -> Radians:
        """Convert a magnetic bearing to true bearing."""
        return magnetic_bearing + math.radians(declination)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _decimal_year(dt: datetime) -> float:
        """Convert a datetime to a decimal year."""
        year = dt.year
        start_of_year = datetime(year, 1, 1, tzinfo=dt.tzinfo)
        start_of_next = datetime(year + 1, 1, 1, tzinfo=dt.tzinfo)
        year_length = (start_of_next - start_of_year).total_seconds()
        elapsed = (dt - start_of_year).total_seconds()
        return year + elapsed / year_length

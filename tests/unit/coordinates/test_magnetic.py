"""Tests for coordinates.magnetic — simplified WMM declination model."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from stochastic_warfare.coordinates.magnetic import MagneticModel


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_MODEL = MagneticModel()
_DATE_2020 = datetime(2020, 1, 1, tzinfo=timezone.utc)
_DATE_2025 = datetime(2025, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeclination:
    def test_washington_dc(self) -> None:
        """Washington DC (~38.9N, -77.0W): declination west of true north."""
        dec = _MODEL.get_declination(38.9, -77.0, _DATE_2020)
        assert -20.0 < dec < -5.0

    def test_london(self) -> None:
        """London (~51.5N, -0.1W): declination ~-1 to +1 degrees."""
        dec = _MODEL.get_declination(51.5, -0.1, _DATE_2020)
        assert -5.0 < dec < 5.0

    def test_tokyo(self) -> None:
        """Tokyo (~35.7N, 139.7E): declination ~-7 to -9 degrees (west)."""
        dec = _MODEL.get_declination(35.7, 139.7, _DATE_2020)
        assert -15.0 < dec < 0.0

    def test_sydney(self) -> None:
        """Sydney (~-33.9S, 151.2E): declination east of true north."""
        dec = _MODEL.get_declination(-33.9, 151.2, _DATE_2020)
        assert 0.0 < dec < 20.0

    def test_equator_zero_longitude(self) -> None:
        """Near equator at 0° longitude: declination close to small west."""
        dec = _MODEL.get_declination(0.0, 0.0, _DATE_2020)
        assert -10.0 < dec < 10.0


class TestSecularVariation:
    def test_declination_changes_over_years(self) -> None:
        """Declination at a fixed point should change between 2020 and 2025."""
        d1 = _MODEL.get_declination(45.0, -90.0, _DATE_2020)
        d2 = _MODEL.get_declination(45.0, -90.0, _DATE_2025)
        assert d1 != pytest.approx(d2, abs=0.01)

    def test_change_is_gradual(self) -> None:
        """5 years of secular variation should be < ~5 degrees at mid-latitudes."""
        d1 = _MODEL.get_declination(45.0, -90.0, _DATE_2020)
        d2 = _MODEL.get_declination(45.0, -90.0, _DATE_2025)
        assert abs(d2 - d1) < 5.0


class TestBearingConversion:
    def test_true_to_magnetic_round_trip(self) -> None:
        dec = 10.0  # 10° east
        true_brg = math.radians(90.0)
        mag_brg = _MODEL.true_to_magnetic(true_brg, dec)
        recovered = _MODEL.magnetic_to_true(mag_brg, dec)
        assert recovered == pytest.approx(true_brg, abs=1e-10)

    def test_east_declination_reduces_magnetic(self) -> None:
        """With east declination, magnetic bearing < true bearing."""
        dec = 10.0
        true_brg = math.radians(90.0)
        mag_brg = _MODEL.true_to_magnetic(true_brg, dec)
        assert mag_brg < true_brg

    def test_west_declination_increases_magnetic(self) -> None:
        """With west (negative) declination, magnetic bearing > true bearing."""
        dec = -10.0
        true_brg = math.radians(90.0)
        mag_brg = _MODEL.true_to_magnetic(true_brg, dec)
        assert mag_brg > true_brg

    def test_zero_declination_identity(self) -> None:
        true_brg = math.radians(45.0)
        assert _MODEL.true_to_magnetic(true_brg, 0.0) == pytest.approx(true_brg)
        assert _MODEL.magnetic_to_true(true_brg, 0.0) == pytest.approx(true_brg)

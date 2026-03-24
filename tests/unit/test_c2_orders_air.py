"""Tests for c2/orders/air_orders.py — air orders, ATO, ACO, CAS."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from stochastic_warfare.c2.orders.air_orders import (
    AirMissionType,
    AirspaceControlMeasure,
    AirspaceControlType,
    AtoEntry,
    CasRequest,
    check_airspace_deconfliction,
    create_air_order,
    create_ato_entry,
    create_cas_request,
)
from stochastic_warfare.c2.orders.types import AirOrder, Order, OrderPriority
from stochastic_warfare.core.types import Position

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_TS_END = _TS + timedelta(hours=2)


class TestAirMissionType:
    """AirMissionType enum."""

    def test_mission_values(self) -> None:
        assert AirMissionType.CAS == 0
        assert AirMissionType.SAR == 11
        assert len(AirMissionType) == 12


class TestAirspaceControlType:
    """AirspaceControlType enum."""

    def test_type_values(self) -> None:
        assert AirspaceControlType.RESTRICTED_OPERATING_ZONE == 0
        assert AirspaceControlType.MINIMUM_RISK_ROUTE == 8
        assert len(AirspaceControlType) == 9


class TestCreateAirOrder:
    """Air order factory."""

    def test_create_cas_order(self) -> None:
        o = create_air_order(
            "ao1", "jfacc", "wing1", _TS,
            AirMissionType.CAS,
            callsign="HAWG11",
            altitude_min_m=500.0, altitude_max_m=3000.0,
        )
        assert isinstance(o, AirOrder)
        assert isinstance(o, Order)
        assert o.air_mission_type == "CAS"
        assert o.callsign == "HAWG11"
        assert o.altitude_min_m == 500.0

    def test_create_cap_order(self) -> None:
        o = create_air_order(
            "ao2", "jfacc", "sq1", _TS,
            AirMissionType.CAP,
            time_on_station_s=7200.0,
        )
        assert o.time_on_station_s == 7200.0

    def test_order_is_frozen(self) -> None:
        o = create_air_order("ao1", "jfacc", "wing1", _TS, AirMissionType.STRIKE)
        with pytest.raises(AttributeError):
            o.callsign = "other"  # type: ignore[misc]


class TestAtoEntry:
    """ATO entry creation."""

    def test_create_ato_entry(self) -> None:
        e = create_ato_entry(
            "m001", AirMissionType.CAS, "HAWG11", "a10_1",
            start_time=_TS, end_time=_TS_END,
            target_position=Position(10000, 20000),
            altitude_min_m=500.0, altitude_max_m=3000.0,
            time_on_station_s=3600.0,
        )
        assert isinstance(e, AtoEntry)
        assert e.mission_type == AirMissionType.CAS
        assert e.callsign == "HAWG11"
        assert e.time_on_station_s == 3600.0

    def test_ato_entry_is_frozen(self) -> None:
        e = create_ato_entry(
            "m001", AirMissionType.CAP, "EAGLE01", "f16_1",
            start_time=_TS, end_time=_TS_END,
        )
        with pytest.raises(AttributeError):
            e.callsign = "other"  # type: ignore[misc]


class TestCasRequest:
    """CAS request creation."""

    def test_create_cas_request(self) -> None:
        r = create_cas_request(
            "cas001", "co1", Position(5000, 6000),
            "Enemy armor in the open", _TS,
            friendlies_position=Position(4800, 5800),
        )
        assert isinstance(r, CasRequest)
        assert r.requesting_unit_id == "co1"
        assert r.target_description == "Enemy armor in the open"
        assert r.priority == OrderPriority.IMMEDIATE
        assert r.minimum_safe_distance_m == 500.0

    def test_cas_request_is_frozen(self) -> None:
        r = create_cas_request(
            "cas001", "co1", Position(5000, 6000), "test", _TS,
        )
        with pytest.raises(AttributeError):
            r.target_description = "other"  # type: ignore[misc]

    def test_custom_safe_distance(self) -> None:
        r = create_cas_request(
            "cas001", "co1", Position(5000, 6000), "danger close", _TS,
            minimum_safe_distance_m=200.0,
        )
        assert r.minimum_safe_distance_m == 200.0


class TestAirspaceDeconfliction:
    """Airspace control measure checks."""

    def _make_roz(self) -> AirspaceControlMeasure:
        return AirspaceControlMeasure(
            measure_id="roz1",
            measure_type=AirspaceControlType.RESTRICTED_OPERATING_ZONE,
            center=Position(10000, 20000),
            radius_m=5000.0,
            altitude_min_m=0.0,
            altitude_max_m=5000.0,
            start_time=_TS,
            end_time=_TS_END,
            controlling_unit="arty1",
        )

    def test_inside_roz_detected(self) -> None:
        roz = self._make_roz()
        violations = check_airspace_deconfliction(
            Position(10000, 20000), 1000.0, _TS + timedelta(minutes=30),
            [roz],
        )
        assert len(violations) == 1
        assert violations[0].measure_id == "roz1"

    def test_outside_roz_clear(self) -> None:
        roz = self._make_roz()
        violations = check_airspace_deconfliction(
            Position(50000, 20000), 1000.0, _TS + timedelta(minutes=30),
            [roz],
        )
        assert len(violations) == 0

    def test_above_roz_altitude_clear(self) -> None:
        roz = self._make_roz()
        violations = check_airspace_deconfliction(
            Position(10000, 20000), 6000.0, _TS + timedelta(minutes=30),
            [roz],
        )
        assert len(violations) == 0

    def test_outside_time_window_clear(self) -> None:
        roz = self._make_roz()
        before = _TS - timedelta(hours=1)
        violations = check_airspace_deconfliction(
            Position(10000, 20000), 1000.0, before,
            [roz],
        )
        assert len(violations) == 0

    def test_multiple_measures(self) -> None:
        roz = self._make_roz()
        mez = AirspaceControlMeasure(
            measure_id="mez1",
            measure_type=AirspaceControlType.MISSILE_ENGAGEMENT_ZONE,
            center=Position(10000, 20000),
            radius_m=20000.0,
            altitude_min_m=0.0,
            altitude_max_m=20000.0,
            start_time=_TS,
            end_time=_TS_END,
            controlling_unit="patriot1",
        )
        violations = check_airspace_deconfliction(
            Position(10000, 20000), 1000.0, _TS + timedelta(minutes=30),
            [roz, mez],
        )
        assert len(violations) == 2

    def test_empty_measures_list(self) -> None:
        violations = check_airspace_deconfliction(
            Position(0, 0), 1000.0, _TS, [],
        )
        assert violations == []

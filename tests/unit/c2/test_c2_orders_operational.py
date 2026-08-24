"""Tests for c2/orders/operational.py — operational-level orders."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.c2.orders.operational import (
    OperationalMission,
    create_operational_order,
    get_planning_time,
)
from stochastic_warfare.c2.orders.types import (
    MissionType,
    OperationalOrder,
    Order,
    OrderType,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.organization.echelons import EchelonLevel

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestOperationalMission:
    """OperationalMission enum."""

    def test_mission_values(self) -> None:
        assert OperationalMission.DECISIVE_OPERATION == 0
        assert OperationalMission.AIRBORNE_OPERATION == 11
        assert len(OperationalMission) == 12


class TestPlanningTime:
    """Planning time scales with echelon."""

    def test_brigade_12_hours(self) -> None:
        assert get_planning_time(EchelonLevel.BRIGADE) == pytest.approx(43200.0)

    def test_division_24_hours(self) -> None:
        assert get_planning_time(EchelonLevel.DIVISION) == pytest.approx(86400.0)

    def test_corps_48_hours(self) -> None:
        assert get_planning_time(EchelonLevel.CORPS) == pytest.approx(172800.0)

    def test_planning_time_increases_with_echelon(self) -> None:
        times = [
            get_planning_time(e)
            for e in [EchelonLevel.BRIGADE, EchelonLevel.DIVISION, EchelonLevel.CORPS]
        ]
        assert times == sorted(times)


class TestCreateOperationalOrder:
    """Order factory."""

    def test_create_basic(self) -> None:
        o = create_operational_order(
            "oo1", "div1", "bde1", _TS,
            MissionType.ATTACK, EchelonLevel.DIVISION,
            objective_position=Position(50000, 60000),
        )
        assert isinstance(o, OperationalOrder)
        assert isinstance(o, Order)
        assert o.echelon_level == int(EchelonLevel.DIVISION)

    def test_with_effort_designations(self) -> None:
        o = create_operational_order(
            "oo1", "corps1", "div1", _TS,
            OperationalMission.DECISIVE_OPERATION, EchelonLevel.CORPS,
            main_effort_id="bde1",
            supporting_effort_ids=("bde2", "bde3"),
            reserve_id="bde4",
        )
        assert o.main_effort_id == "bde1"
        assert len(o.supporting_effort_ids) == 2
        assert o.reserve_id == "bde4"

    def test_frago_references_parent(self) -> None:
        o = create_operational_order(
            "frago1", "div1", "bde1", _TS,
            MissionType.WITHDRAW, EchelonLevel.DIVISION,
            order_type=OrderType.FRAGO,
            parent_order_id="opord1",
        )
        assert o.order_type == OrderType.FRAGO
        assert o.parent_order_id == "opord1"

    def test_order_is_frozen(self) -> None:
        o = create_operational_order(
            "oo1", "div1", "bde1", _TS,
            MissionType.DEFEND, EchelonLevel.DIVISION,
        )
        with pytest.raises(AttributeError):
            o.main_effort_id = "other"  # type: ignore[misc]

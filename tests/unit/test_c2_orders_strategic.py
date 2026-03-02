"""Tests for c2/orders/strategic.py — strategic-level orders."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.c2.orders.strategic import (
    StrategicMission,
    create_strategic_order,
    get_planning_time,
)
from stochastic_warfare.c2.orders.types import Order, OrderType, StrategicOrder
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.organization.echelons import EchelonLevel

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestStrategicMission:
    """StrategicMission enum."""

    def test_mission_values(self) -> None:
        assert StrategicMission.MAJOR_OPERATION == 0
        assert StrategicMission.BLOCKADE == 7
        assert len(StrategicMission) == 8


class TestPlanningTime:
    """Strategic planning time."""

    def test_planning_time_seven_days(self) -> None:
        t = get_planning_time(EchelonLevel.THEATER)
        assert t == pytest.approx(604800.0)  # 7 days

    def test_planning_time_greater_than_operational(self) -> None:
        from stochastic_warfare.c2.orders.operational import (
            get_planning_time as op_time,
        )
        assert get_planning_time(EchelonLevel.THEATER) > op_time(EchelonLevel.CORPS)


class TestCreateStrategicOrder:
    """Order factory."""

    def test_create_basic(self) -> None:
        o = create_strategic_order(
            "so1", "theater1", "army1", _TS,
            StrategicMission.CAMPAIGN,
        )
        assert isinstance(o, StrategicOrder)
        assert isinstance(o, Order)
        assert o.echelon_level == int(EchelonLevel.THEATER)

    def test_with_constraints(self) -> None:
        o = create_strategic_order(
            "so1", "theater1", "army1", _TS,
            StrategicMission.FORCE_PROJECTION,
            campaign_phase="Phase II",
            political_constraints=("no_nuclear", "minimize_collateral"),
        )
        assert o.campaign_phase == "Phase II"
        assert len(o.political_constraints) == 2

    def test_order_is_frozen(self) -> None:
        o = create_strategic_order("so1", "t1", "a1", _TS, StrategicMission.CAMPAIGN)
        with pytest.raises(AttributeError):
            o.campaign_phase = "x"  # type: ignore[misc]

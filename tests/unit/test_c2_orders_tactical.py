"""Tests for c2/orders/tactical.py — tactical-level orders."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.c2.orders.tactical import (
    TacticalMission,
    create_tactical_order,
    get_planning_time,
)
from stochastic_warfare.c2.orders.types import (
    MissionType,
    Order,
    OrderType,
    TacticalOrder,
)
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.organization.echelons import EchelonLevel

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestTacticalMission:
    """TacticalMission enum."""

    def test_mission_values(self) -> None:
        assert TacticalMission.ASSAULT == 0
        assert TacticalMission.CONSOLIDATE == 11
        assert len(TacticalMission) == 12


class TestPlanningTime:
    """Planning time scales with echelon."""

    def test_squad_one_minute(self) -> None:
        assert get_planning_time(EchelonLevel.SQUAD) == pytest.approx(60.0)

    def test_platoon_15_minutes(self) -> None:
        assert get_planning_time(EchelonLevel.PLATOON) == pytest.approx(900.0)

    def test_company_one_hour(self) -> None:
        assert get_planning_time(EchelonLevel.COMPANY) == pytest.approx(3600.0)

    def test_battalion_two_hours(self) -> None:
        assert get_planning_time(EchelonLevel.BATTALION) == pytest.approx(7200.0)

    def test_planning_time_increases_with_echelon(self) -> None:
        times = [
            get_planning_time(e)
            for e in [EchelonLevel.SQUAD, EchelonLevel.PLATOON,
                      EchelonLevel.COMPANY, EchelonLevel.BATTALION]
        ]
        assert times == sorted(times)


class TestCreateTacticalOrder:
    """Order factory."""

    def test_create_basic(self) -> None:
        o = create_tactical_order(
            "to1", "co1", "plt1", _TS,
            MissionType.ATTACK, EchelonLevel.COMPANY,
            objective_position=Position(1000, 2000),
        )
        assert isinstance(o, TacticalOrder)
        assert isinstance(o, Order)
        assert o.echelon_level == int(EchelonLevel.COMPANY)

    def test_with_formation_and_waypoints(self) -> None:
        wps = (Position(100, 200), Position(300, 400))
        o = create_tactical_order(
            "to1", "bn1", "co1", _TS,
            TacticalMission.ASSAULT, EchelonLevel.BATTALION,
            formation="line", route_waypoints=wps,
        )
        assert o.formation == "line"
        assert len(o.route_waypoints) == 2

    def test_frago_with_parent(self) -> None:
        o = create_tactical_order(
            "frago1", "co1", "plt1", _TS,
            MissionType.WITHDRAW, EchelonLevel.COMPANY,
            order_type=OrderType.FRAGO,
            parent_order_id="opord1",
        )
        assert o.order_type == OrderType.FRAGO
        assert o.parent_order_id == "opord1"

    def test_order_is_frozen(self) -> None:
        o = create_tactical_order(
            "to1", "co1", "plt1", _TS,
            MissionType.DEFEND, EchelonLevel.COMPANY,
        )
        with pytest.raises(AttributeError):
            o.formation = "wedge"  # type: ignore[misc]

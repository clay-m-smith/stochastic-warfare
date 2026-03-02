"""Tests for c2/orders/naval_orders.py — naval-specific orders."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.c2.orders.naval_orders import (
    NavalMissionType,
    create_naval_order,
)
from stochastic_warfare.c2.orders.types import NavalOrder, Order, OrderType
from stochastic_warfare.core.types import Position

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestNavalMissionType:
    """NavalMissionType enum."""

    def test_mission_values(self) -> None:
        assert NavalMissionType.FORMATION_MOVEMENT == 0
        assert NavalMissionType.UNDERWAY_REPLENISHMENT == 11
        assert len(NavalMissionType) == 12

    @pytest.mark.parametrize("mt", list(NavalMissionType))
    def test_all_missions_are_ints(self, mt: NavalMissionType) -> None:
        assert isinstance(int(mt), int)


class TestCreateNavalOrder:
    """Order factory."""

    def test_create_asw_order(self) -> None:
        o = create_naval_order(
            "no1", "ctf1", "tg1", _TS,
            NavalMissionType.ASW_PROSECUTION,
            objective_position=Position(100000, 200000),
            formation_id="tf_alpha",
        )
        assert isinstance(o, NavalOrder)
        assert isinstance(o, Order)
        assert o.naval_mission_type == "ASW_PROSECUTION"
        assert o.formation_id == "tf_alpha"

    def test_create_strike_order(self) -> None:
        o = create_naval_order(
            "no2", "ctf1", "tu1", _TS,
            NavalMissionType.STRIKE,
            engagement_envelope=150000.0,
        )
        assert o.engagement_envelope == 150000.0

    def test_create_convoy_escort(self) -> None:
        o = create_naval_order(
            "no3", "ctf1", "tg2", _TS,
            NavalMissionType.CONVOY_ESCORT,
        )
        assert o.mission_type == int(NavalMissionType.CONVOY_ESCORT)

    def test_create_blockade(self) -> None:
        o = create_naval_order(
            "no4", "fleet1", "tf1", _TS,
            NavalMissionType.BLOCKADE,
        )
        assert o.naval_mission_type == "BLOCKADE"

    def test_frago_with_parent(self) -> None:
        o = create_naval_order(
            "nf1", "ctf1", "tg1", _TS,
            NavalMissionType.FORMATION_MOVEMENT,
            order_type=OrderType.FRAGO,
            parent_order_id="no1",
        )
        assert o.order_type == OrderType.FRAGO
        assert o.parent_order_id == "no1"

    def test_order_is_frozen(self) -> None:
        o = create_naval_order(
            "no1", "ctf1", "tg1", _TS, NavalMissionType.STRIKE,
        )
        with pytest.raises(AttributeError):
            o.formation_id = "other"  # type: ignore[misc]

    @pytest.mark.parametrize("mission", list(NavalMissionType))
    def test_all_naval_missions_create_valid_order(self, mission: NavalMissionType) -> None:
        o = create_naval_order(f"no_{mission}", "ctf1", "tg1", _TS, mission)
        assert isinstance(o, NavalOrder)
        assert o.naval_mission_type == mission.name

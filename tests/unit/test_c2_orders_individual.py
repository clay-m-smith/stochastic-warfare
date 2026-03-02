"""Tests for c2/orders/individual.py — individual-level orders."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.c2.orders.individual import (
    IndividualAction,
    create_individual_order,
    get_planning_time,
)
from stochastic_warfare.c2.orders.types import IndividualOrder, Order, OrderType
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.organization.echelons import EchelonLevel

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestIndividualAction:
    """IndividualAction enum."""

    def test_action_values(self) -> None:
        assert IndividualAction.MOVE_TO == 0
        assert IndividualAction.MARK_TARGET == 9
        assert len(IndividualAction) == 10


class TestCreateIndividualOrder:
    """Order factory."""

    def test_create_basic(self) -> None:
        o = create_individual_order(
            "io1", "tl1", "sol1", _TS, IndividualAction.MOVE_TO,
            objective_position=Position(100, 200),
        )
        assert isinstance(o, IndividualOrder)
        assert isinstance(o, Order)
        assert o.immediate is True
        assert o.echelon_level == int(EchelonLevel.INDIVIDUAL)
        assert o.mission_type == int(IndividualAction.MOVE_TO)

    def test_order_is_frozen(self) -> None:
        o = create_individual_order("io1", "tl1", "sol1", _TS, IndividualAction.ENGAGE)
        with pytest.raises(AttributeError):
            o.order_id = "x"  # type: ignore[misc]

    def test_default_priority_flash(self) -> None:
        o = create_individual_order("io1", "tl1", "sol1", _TS, IndividualAction.TAKE_COVER)
        from stochastic_warfare.c2.orders.types import OrderPriority
        assert o.priority == OrderPriority.FLASH

    def test_default_order_type_frago(self) -> None:
        o = create_individual_order("io1", "tl1", "sol1", _TS, IndividualAction.CEASE_FIRE)
        assert o.order_type == OrderType.FRAGO


class TestPlanningTime:
    """Planning time for individual orders."""

    def test_planning_time_near_zero(self) -> None:
        t = get_planning_time(EchelonLevel.INDIVIDUAL)
        assert t == pytest.approx(0.5)

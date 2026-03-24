"""Tests for logistics/stockpile.py -- depots, unit inventories, capture, spoilage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    SupplyDepletedEvent,
    SupplyShortageEvent,
)
from stochastic_warfare.logistics.stockpile import (
    DepotType,
    StockpileConfig,
    StockpileManager,
)
from stochastic_warfare.logistics.supply_classes import (
    SupplyClass,
    SupplyInventory,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS_A = Position(0.0, 0.0)
_POS_B = Position(5000.0, 5000.0)


def _make_manager(
    seed: int = 42, config: StockpileConfig | None = None,
) -> tuple[StockpileManager, EventBus]:
    bus = EventBus()
    rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
    mgr = StockpileManager(event_bus=bus, rng=rng, config=config)
    return mgr, bus


def _make_inventory(**items: float) -> SupplyInventory:
    """Create an inventory from keyword args like fuel_diesel=100."""
    inv = SupplyInventory()
    class_map = {
        "ration_mre": int(SupplyClass.CLASS_I),
        "water_potable": int(SupplyClass.CLASS_I),
        "fuel_diesel": int(SupplyClass.CLASS_III),
        "ammo_generic": int(SupplyClass.CLASS_V),
        "medical_kit_basic": int(SupplyClass.CLASS_VIII),
        "spare_parts_ground": int(SupplyClass.CLASS_IX),
    }
    for item_id, qty in items.items():
        cls = class_map.get(item_id, 10)
        inv.add(cls, item_id, qty)
    return inv


# ---------------------------------------------------------------------------
# DepotType enum
# ---------------------------------------------------------------------------


class TestDepotTypeEnum:
    def test_values(self) -> None:
        assert DepotType.SUPPLY_POINT == 0
        assert DepotType.FORWARD_ARMING_REFUELING_POINT == 5

    def test_all_members(self) -> None:
        assert len(DepotType) == 6


# ---------------------------------------------------------------------------
# Depot CRUD
# ---------------------------------------------------------------------------


class TestDepotManagement:
    def test_create_depot(self) -> None:
        mgr, _ = _make_manager()
        depot = mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        assert depot.depot_id == "d1"
        assert depot.side == "blue"

    def test_get_depot(self) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        depot = mgr.get_depot("d1")
        assert depot.depot_id == "d1"

    def test_get_depot_missing_raises(self) -> None:
        mgr, _ = _make_manager()
        with pytest.raises(KeyError):
            mgr.get_depot("nonexistent")

    def test_list_depots_all(self) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        mgr.create_depot("d2", _POS_B, DepotType.DEPOT, "red")
        assert len(mgr.list_depots()) == 2

    def test_list_depots_by_side(self) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        mgr.create_depot("d2", _POS_B, DepotType.DEPOT, "red")
        assert len(mgr.list_depots("blue")) == 1

    def test_create_depot_with_inventory(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=5000.0)
        depot = mgr.create_depot(
            "d1", _POS_A, DepotType.DEPOT, "blue",
            initial_inventory=inv,
        )
        assert depot.inventory.available(int(SupplyClass.CLASS_III), "fuel_diesel") == 5000.0


# ---------------------------------------------------------------------------
# Issue & receive
# ---------------------------------------------------------------------------


class TestIssueReceive:
    def test_issue_full(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=1000.0)
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue", initial_inventory=inv)
        issued = mgr.issue_supplies("d1", {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 500.0}
        })
        assert issued[int(SupplyClass.CLASS_III)]["fuel_diesel"] == 500.0
        depot = mgr.get_depot("d1")
        assert depot.inventory.available(int(SupplyClass.CLASS_III), "fuel_diesel") == 500.0

    def test_issue_partial(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=100.0)
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue", initial_inventory=inv)
        issued = mgr.issue_supplies("d1", {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 500.0}
        })
        assert issued[int(SupplyClass.CLASS_III)]["fuel_diesel"] == 100.0

    def test_issue_empty_stock(self) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        issued = mgr.issue_supplies("d1", {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0}
        })
        assert len(issued) == 0

    def test_receive_supplies(self) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        mgr.receive_supplies("d1", {
            int(SupplyClass.CLASS_I): {"ration_mre": 500.0}
        })
        depot = mgr.get_depot("d1")
        assert depot.inventory.available(int(SupplyClass.CLASS_I), "ration_mre") == 500.0


# ---------------------------------------------------------------------------
# Unit inventory consumption
# ---------------------------------------------------------------------------


class TestUnitConsumption:
    def test_consume_full(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=200.0)
        mgr.register_unit_inventory("u1", inv)
        shortfalls = mgr.consume_unit_supplies("u1", {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0}
        })
        assert len(shortfalls) == 0
        assert inv.available(int(SupplyClass.CLASS_III), "fuel_diesel") == 100.0

    def test_consume_with_shortfall(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=50.0)
        mgr.register_unit_inventory("u1", inv)
        shortfalls = mgr.consume_unit_supplies("u1", {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0}
        })
        assert shortfalls[int(SupplyClass.CLASS_III)]["fuel_diesel"] == pytest.approx(50.0)

    def test_depleted_event(self) -> None:
        mgr, bus = _make_manager()
        events: list[Event] = []
        bus.subscribe(SupplyDepletedEvent, events.append)
        inv = _make_inventory(fuel_diesel=50.0)
        mgr.register_unit_inventory("u1", inv)
        mgr.consume_unit_supplies("u1", {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0}
        }, timestamp=_TS)
        assert len(events) == 1
        assert events[0].unit_id == "u1"

    def test_shortage_event(self) -> None:
        mgr, bus = _make_manager()
        events: list[Event] = []
        bus.subscribe(SupplyShortageEvent, events.append)
        inv = _make_inventory(fuel_diesel=20.0)
        mgr.register_unit_inventory(
            "u1", inv,
            max_supplies={int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0}},
        )
        # Consume to get to 20% (below 25% threshold)
        mgr.consume_unit_supplies("u1", {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 1.0}
        }, timestamp=_TS)
        assert len(events) == 1
        assert events[0].current_fraction < 0.25

    def test_get_unit_inventory(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=100.0)
        mgr.register_unit_inventory("u1", inv)
        assert mgr.get_unit_inventory("u1") is inv

    def test_get_unit_inventory_missing_raises(self) -> None:
        mgr, _ = _make_manager()
        with pytest.raises(KeyError):
            mgr.get_unit_inventory("nonexistent")


# ---------------------------------------------------------------------------
# Supply state (combat power query)
# ---------------------------------------------------------------------------


class TestSupplyState:
    def test_unregistered_unit_returns_one(self) -> None:
        mgr, _ = _make_manager()
        assert mgr.get_supply_state("unknown") == 1.0

    def test_fully_supplied_returns_one(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=100.0, ammo_generic=50.0)
        mgr.register_unit_inventory(
            "u1", inv,
            max_supplies={
                int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0},
                int(SupplyClass.CLASS_V): {"ammo_generic": 50.0},
            },
        )
        assert mgr.get_supply_state("u1") == pytest.approx(1.0)

    def test_half_supplied(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=50.0, ammo_generic=25.0)
        mgr.register_unit_inventory(
            "u1", inv,
            max_supplies={
                int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0},
                int(SupplyClass.CLASS_V): {"ammo_generic": 50.0},
            },
        )
        assert mgr.get_supply_state("u1") == pytest.approx(0.5)

    def test_depleted_returns_zero(self) -> None:
        mgr, _ = _make_manager()
        inv = SupplyInventory()  # empty
        mgr.register_unit_inventory(
            "u1", inv,
            max_supplies={
                int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0},
                int(SupplyClass.CLASS_V): {"ammo_generic": 50.0},
            },
        )
        assert mgr.get_supply_state("u1") == pytest.approx(0.0)

    def test_ammo_weighted_more_than_food(self) -> None:
        mgr, _ = _make_manager()
        # Full ammo, no food → should still have decent supply state
        inv = _make_inventory(ammo_generic=50.0)
        mgr.register_unit_inventory(
            "u1", inv,
            max_supplies={
                int(SupplyClass.CLASS_I): {"ration_mre": 100.0},
                int(SupplyClass.CLASS_V): {"ammo_generic": 50.0},
            },
        )
        state = mgr.get_supply_state("u1")
        # Ammo weight=3, food weight=1. (0*1 + 1*3)/(1+3) = 0.75
        assert state == pytest.approx(0.75)

    def test_no_max_supplies_returns_one(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=100.0)
        mgr.register_unit_inventory("u1", inv)
        assert mgr.get_supply_state("u1") == 1.0


# ---------------------------------------------------------------------------
# Depot capture
# ---------------------------------------------------------------------------


class TestCapture:
    def test_capture_changes_side(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=1000.0)
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "red", initial_inventory=inv)
        mgr.capture_depot("d1", "blue")
        depot = mgr.get_depot("d1")
        assert depot.side == "blue"

    def test_capture_reduces_inventory(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=1000.0)
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "red", initial_inventory=inv)
        mgr.capture_depot("d1", "blue")
        depot = mgr.get_depot("d1")
        assert depot.inventory.available(
            int(SupplyClass.CLASS_III), "fuel_diesel"
        ) == pytest.approx(500.0)

    def test_capture_custom_efficiency(self) -> None:
        cfg = StockpileConfig(capture_efficiency=0.75)
        mgr, _ = _make_manager(config=cfg)
        inv = _make_inventory(fuel_diesel=1000.0)
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "red", initial_inventory=inv)
        mgr.capture_depot("d1", "blue")
        depot = mgr.get_depot("d1")
        assert depot.inventory.available(
            int(SupplyClass.CLASS_III), "fuel_diesel"
        ) == pytest.approx(750.0)


# ---------------------------------------------------------------------------
# State protocol
# ---------------------------------------------------------------------------


class TestStateProtocol:
    def test_state_round_trip(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=500.0)
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue", initial_inventory=inv)
        unit_inv = _make_inventory(ammo_generic=100.0)
        mgr.register_unit_inventory("u1", unit_inv,
                                     max_supplies={int(SupplyClass.CLASS_V): {"ammo_generic": 200.0}})

        state = mgr.get_state()
        mgr2, _ = _make_manager()
        mgr2.set_state(state)

        assert mgr2.get_depot("d1").side == "blue"
        assert mgr2.get_depot("d1").inventory.available(
            int(SupplyClass.CLASS_III), "fuel_diesel"
        ) == 500.0
        assert mgr2.get_unit_inventory("u1").available(
            int(SupplyClass.CLASS_V), "ammo_generic"
        ) == 100.0

    def test_set_state_clears_previous(self) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        mgr.set_state({"depots": {}, "unit_inventories": {}, "unit_max_supplies": {}})
        assert len(mgr.list_depots()) == 0

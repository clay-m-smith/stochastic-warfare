"""Tests for logistics/stockpile.py -- depots, unit inventories, capture, spoilage."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    SupplyDeliveredEvent,
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

    def test_duplicate_depot_rejected_without_overwrite(self) -> None:
        mgr, _ = _make_manager()
        original = mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        with pytest.raises(ValueError, match="Duplicate depot ID"):
            mgr.create_depot("d1", _POS_B, DepotType.DEPOT, "red")
        assert mgr.get_depot("d1") is original

    @pytest.mark.parametrize(
        ("capacity", "throughput"),
        [
            (float("nan"), 1.0),
            (1.0, float("inf")),
            (0.0, 1.0),
            (1.0, -1.0),
        ],
    )
    def test_invalid_depot_limits_rejected(
        self,
        capacity: float,
        throughput: float,
    ) -> None:
        mgr, _ = _make_manager()
        with pytest.raises(ValueError):
            mgr.create_depot(
                "d1", _POS_A, DepotType.DEPOT, "blue",
                capacity_tons=capacity,
                throughput_tons_per_hour=throughput,
            )


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

    def test_exact_class_exhaustion_emits_depleted_transition(self) -> None:
        mgr, bus = _make_manager()
        events: list[Event] = []
        bus.subscribe(SupplyDepletedEvent, events.append)
        inv = _make_inventory(fuel_diesel=50.0)
        mgr.register_unit_inventory("u1", inv)

        mgr.consume_unit_supplies(
            "u1",
            {int(SupplyClass.CLASS_III): {"fuel_diesel": 50.0}},
            timestamp=_TS,
        )

        assert len(events) == 1
        assert events[0].supply_class == int(SupplyClass.CLASS_III)

    def test_already_empty_class_does_not_repeat_depleted_event(self) -> None:
        mgr, bus = _make_manager()
        events: list[Event] = []
        bus.subscribe(SupplyDepletedEvent, events.append)
        inv = _make_inventory(fuel_diesel=10.0)
        mgr.register_unit_inventory("u1", inv)

        for _ in range(2):
            mgr.consume_unit_supplies(
                "u1",
                {int(SupplyClass.CLASS_III): {"fuel_diesel": 20.0}},
                timestamp=_TS,
            )

        assert len(events) == 1

    def test_class_with_other_item_remaining_is_not_depleted(self) -> None:
        mgr, bus = _make_manager()
        events: list[Event] = []
        bus.subscribe(SupplyDepletedEvent, events.append)
        inv = SupplyInventory()
        supply_class = int(SupplyClass.CLASS_III)
        inv.add(supply_class, "fuel_diesel", 10.0)
        inv.add(supply_class, "fuel_avgas", 10.0)
        mgr.register_unit_inventory("u1", inv)

        mgr.consume_unit_supplies(
            "u1",
            {supply_class: {"fuel_diesel": 20.0}},
            timestamp=_TS,
        )

        assert events == []

    def test_final_item_in_class_emits_one_depleted_event(self) -> None:
        mgr, bus = _make_manager()
        events: list[Event] = []
        bus.subscribe(SupplyDepletedEvent, events.append)
        inv = SupplyInventory()
        supply_class = int(SupplyClass.CLASS_III)
        inv.add(supply_class, "fuel_diesel", 10.0)
        inv.add(supply_class, "fuel_avgas", 10.0)
        mgr.register_unit_inventory("u1", inv)

        mgr.consume_unit_supplies(
            "u1",
            {supply_class: {"fuel_diesel": 10.0}},
            timestamp=_TS,
        )
        mgr.consume_unit_supplies(
            "u1",
            {supply_class: {"fuel_avgas": 10.0}},
            timestamp=_TS,
        )

        assert [event.supply_class for event in events] == [supply_class]

    def test_buffered_depleted_events_keep_sorted_class_order(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(ration_mre=1.0, ammo_generic=1.0)
        mgr.register_unit_inventory("u1", inv)
        events: list[Event] = []

        mgr.consume_unit_supplies(
            "u1",
            {
                int(SupplyClass.CLASS_V): {"ammo_generic": 1.0},
                int(SupplyClass.CLASS_I): {"ration_mre": 1.0},
            },
            timestamp=_TS,
            event_sink=events,
        )

        assert [
            event.supply_class
            for event in events
            if isinstance(event, SupplyDepletedEvent)
        ] == [
            int(SupplyClass.CLASS_I),
            int(SupplyClass.CLASS_V),
        ]

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

    def test_duplicate_unit_inventory_rejected_without_overwrite(self) -> None:
        mgr, _ = _make_manager()
        original = _make_inventory(fuel_diesel=100.0)
        mgr.register_unit_inventory("u1", original)
        with pytest.raises(ValueError, match="Duplicate unit inventory"):
            mgr.register_unit_inventory("u1", _make_inventory(fuel_diesel=1.0))
        assert mgr.get_unit_inventory("u1") is original

    def test_inventory_helpers_are_sorted_and_defensive(self) -> None:
        mgr, _ = _make_manager()
        inv = _make_inventory(fuel_diesel=25.0, water_potable=10.0)
        maxima = {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0},
            int(SupplyClass.CLASS_I): {
                "water_potable": 40.0,
                "ration_mre": 20.0,
            },
        }
        mgr.register_unit_inventory("z-unit", inv, maxima)
        mgr.register_unit_inventory("a-unit", SupplyInventory(), {})

        assert mgr.has_unit_inventory("z-unit")
        assert not mgr.has_unit_inventory("missing")
        assert mgr.registered_unit_ids() == ["a-unit", "z-unit"]
        assert mgr.get_unit_deficits("z-unit") == {
            int(SupplyClass.CLASS_I): {
                "ration_mre": 20.0,
                "water_potable": 30.0,
            },
            int(SupplyClass.CLASS_III): {"fuel_diesel": 75.0},
        }

        returned = mgr.get_unit_max_supplies("z-unit")
        returned[int(SupplyClass.CLASS_III)]["fuel_diesel"] = 1.0
        assert (
            mgr.get_unit_max_supplies("z-unit")
            [int(SupplyClass.CLASS_III)]["fuel_diesel"]
            == 100.0
        )


# ---------------------------------------------------------------------------
# Atomic depot-to-unit delivery
# ---------------------------------------------------------------------------


class TestDelivery:
    def test_delivery_caps_native_quantity_by_deficit_stock_and_mass(self) -> None:
        mgr, bus = _make_manager()
        delivered_events: list[SupplyDeliveredEvent] = []
        bus.subscribe(SupplyDeliveredEvent, delivered_events.append)
        depot_inv = _make_inventory(fuel_diesel=1000.0)
        mgr.create_depot(
            "d1", _POS_A, DepotType.DEPOT, "blue",
            initial_inventory=depot_inv,
        )
        unit_inv = _make_inventory(fuel_diesel=100.0)
        mgr.register_unit_inventory(
            "u1", unit_inv,
            {int(SupplyClass.CLASS_III): {"fuel_diesel": 500.0}},
        )

        result = mgr.deliver_to_unit(
            depot_id="d1",
            unit_id="u1",
            supply_class=int(SupplyClass.CLASS_III),
            item_id="fuel_diesel",
            requested_quantity=500.0,
            max_quantity_tons=0.17,
            timestamp=_TS,
            transport_mode=0,
            route_id="r1",
        )

        assert result.quantity == pytest.approx(200.0)
        assert result.quantity_tons == pytest.approx(0.17)
        assert depot_inv.available(
            int(SupplyClass.CLASS_III), "fuel_diesel",
        ) == pytest.approx(800.0)
        assert unit_inv.available(
            int(SupplyClass.CLASS_III), "fuel_diesel",
        ) == pytest.approx(300.0)
        assert len(delivered_events) == 1
        assert delivered_events[0].depot_id == "d1"
        assert delivered_events[0].recipient_id == "u1"
        assert delivered_events[0].route_id == "r1"
        assert delivered_events[0].item_id == "fuel_diesel"
        assert delivered_events[0].quantity == pytest.approx(200.0)
        assert delivered_events[0].quantity_tons == pytest.approx(0.17)

    def test_invalid_delivery_is_rejected_before_mutation(self) -> None:
        mgr, bus = _make_manager()
        delivered_events: list[SupplyDeliveredEvent] = []
        bus.subscribe(SupplyDeliveredEvent, delivered_events.append)
        depot_inv = _make_inventory(fuel_diesel=1000.0)
        unit_inv = SupplyInventory()
        mgr.create_depot(
            "d1", _POS_A, DepotType.DEPOT, "blue",
            initial_inventory=depot_inv,
        )
        mgr.register_unit_inventory(
            "u1", unit_inv,
            {int(SupplyClass.CLASS_III): {"fuel_diesel": 500.0}},
        )
        before = mgr.get_state()

        with pytest.raises(ValueError):
            mgr.deliver_to_unit(
                "d1", "u1", int(SupplyClass.CLASS_III), "fuel_diesel",
                100.0, float("nan"), _TS, 0, "r1",
            )

        assert mgr.get_state() == before
        assert delivered_events == []

    def test_delivery_rejects_uncatalogued_item_without_mutation(self) -> None:
        mgr, _ = _make_manager()
        depot_inv = SupplyInventory()
        depot_inv.add(int(SupplyClass.CLASS_V), "unknown_ammo", 10.0)
        mgr.create_depot(
            "d1", _POS_A, DepotType.DEPOT, "blue",
            initial_inventory=depot_inv,
        )
        mgr.register_unit_inventory(
            "u1", SupplyInventory(),
            {int(SupplyClass.CLASS_V): {"unknown_ammo": 10.0}},
        )
        before = mgr.get_state()

        with pytest.raises(KeyError):
            mgr.deliver_to_unit(
                "d1", "u1", int(SupplyClass.CLASS_V), "unknown_ammo",
                10.0, 1.0, _TS, 0, "r1",
            )
        assert mgr.get_state() == before


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

    def test_json_round_trip_restores_integer_supply_class_keys(self) -> None:
        mgr, _ = _make_manager()
        mgr.register_unit_inventory(
            "u1", _make_inventory(fuel_diesel=25.0),
            {int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0}},
        )
        state = json.loads(json.dumps(mgr.get_state()))

        restored, _ = _make_manager()
        restored.set_state(state)

        assert restored.get_unit_max_supplies("u1") == {
            int(SupplyClass.CLASS_III): {"fuel_diesel": 100.0},
        }
        assert restored.get_supply_state("u1") == pytest.approx(0.25)

    def test_corrupt_state_rejects_atomically(self) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        before = mgr.get_state()
        corrupt = json.loads(json.dumps(before))
        corrupt["depots"]["d1"]["condition"] = 2.0

        with pytest.raises(ValueError):
            mgr.set_state(corrupt)

        assert mgr.get_state() == before

    def test_boolean_depot_type_rejects_atomically(self) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        before = mgr.get_state()
        corrupt = json.loads(json.dumps(before))
        corrupt["depots"]["d1"]["depot_type"] = False

        with pytest.raises(ValueError, match="depot_type"):
            mgr.set_state(corrupt)

        assert mgr.get_state() == before

    @pytest.mark.parametrize("invalid_type", [2.0, "2"])
    def test_coercible_depot_type_rejects_atomically(
        self,
        invalid_type: object,
    ) -> None:
        mgr, _ = _make_manager()
        mgr.create_depot("d1", _POS_A, DepotType.DEPOT, "blue")
        before = mgr.get_state()
        corrupt = json.loads(json.dumps(before))
        corrupt["depots"]["d1"]["depot_type"] = invalid_type

        with pytest.raises(ValueError, match="depot_type"):
            mgr.set_state(corrupt)

        assert mgr.get_state() == before

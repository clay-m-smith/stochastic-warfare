"""Phase 6 integration tests -- end-to-end logistics scenarios."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.rng import RNGManager
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.consumption import (
    ActivityLevel,
    ConsumptionEngine,
)
from stochastic_warfare.logistics.disruption import DisruptionEngine
from stochastic_warfare.logistics.engineering import EngineeringEngine, EngineeringTask
from stochastic_warfare.logistics.maintenance import MaintenanceConfig, MaintenanceEngine
from stochastic_warfare.logistics.medical import (
    MedicalConfig,
    MedicalEngine,
    MedicalFacility,
    MedicalFacilityType,
)
from stochastic_warfare.logistics.naval_logistics import NavalLogisticsEngine
from stochastic_warfare.logistics.stockpile import DepotType, StockpileManager
from stochastic_warfare.logistics.supply_classes import SupplyClass, SupplyInventory
from stochastic_warfare.logistics.supply_network import (
    SupplyNetworkEngine,
    SupplyNode,
    SupplyRoute,
    TransportMode,
)
from stochastic_warfare.logistics.transport import TransportEngine

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_POS_DEPOT = Position(0.0, 0.0)
_POS_UNIT = Position(5000.0, 0.0)
_POS_BEACH = Position(0.0, 5000.0)

CLS_III = int(SupplyClass.CLASS_III)
CLS_V = int(SupplyClass.CLASS_V)
CLS_I = int(SupplyClass.CLASS_I)
CLS_IX = int(SupplyClass.CLASS_IX)


def _make_rng(seed: int = 42) -> np.random.Generator:
    return RNGManager(seed).get_stream(ModuleId.LOGISTICS)


# ---------------------------------------------------------------------------
# Scenario 1: Full supply chain (depot → road → unit)
# ---------------------------------------------------------------------------


class TestFullSupplyChain:
    def test_depot_to_unit_delivery(self) -> None:
        """Depot issues supplies, convoy transports, unit receives."""
        bus = EventBus()
        rng = _make_rng()

        # Create depot with fuel
        stockpile = StockpileManager(event_bus=bus, rng=rng)
        depot_inv = SupplyInventory()
        depot_inv.add(CLS_III, "fuel_diesel", 5000.0)
        stockpile.create_depot("d1", _POS_DEPOT, DepotType.DEPOT, "blue",
                               initial_inventory=depot_inv)

        # Issue from depot
        issued = stockpile.issue_supplies("d1", {CLS_III: {"fuel_diesel": 500.0}})
        assert issued[CLS_III]["fuel_diesel"] == 500.0

        # Transport to unit
        network = SupplyNetworkEngine(event_bus=bus, rng=rng)
        network.add_node(SupplyNode("depot", _POS_DEPOT, "DEPOT"))
        network.add_node(SupplyNode("unit", _POS_UNIT, "UNIT"))
        route = SupplyRoute("r1", "depot", "unit", TransportMode.ROAD,
                            5000.0, 10.0, 1.0)
        network.add_route(route)

        transport = TransportEngine(event_bus=bus, rng=rng)
        transport.dispatch("m1", TransportMode.ROAD, [route], issued,
                           "depot", "unit", timestamp=_TS)
        completed = transport.update(10.0, timestamp=_TS)
        assert len(completed) == 1

        # Register unit inventory and receive
        unit_inv = SupplyInventory()
        stockpile.register_unit_inventory("u1", unit_inv)
        for cls, items in completed[0].cargo.items():
            for item_id, qty in items.items():
                unit_inv.add(cls, item_id, qty)
        assert unit_inv.available(CLS_III, "fuel_diesel") == 500.0


# ---------------------------------------------------------------------------
# Scenario 2: Supply depletion degrades combat power
# ---------------------------------------------------------------------------


class TestSupplyDegradation:
    def test_depleted_supplies_lower_combat_power(self) -> None:
        bus = EventBus()
        rng = _make_rng()

        stockpile = StockpileManager(event_bus=bus, rng=rng)
        inv = SupplyInventory()
        inv.add(CLS_III, "fuel_diesel", 100.0)
        inv.add(CLS_V, "ammo_generic", 50.0)
        stockpile.register_unit_inventory("u1", inv, max_supplies={
            CLS_III: {"fuel_diesel": 100.0},
            CLS_V: {"ammo_generic": 50.0},
        })

        # Full supply → state = 1.0
        assert stockpile.get_supply_state("u1") == pytest.approx(1.0)

        # Consume all fuel
        stockpile.consume_unit_supplies("u1", {CLS_III: {"fuel_diesel": 100.0}})
        state = stockpile.get_supply_state("u1")
        assert state < 1.0

        # Consume all ammo too
        stockpile.consume_unit_supplies("u1", {CLS_V: {"ammo_generic": 50.0}})
        assert stockpile.get_supply_state("u1") == 0.0

    def test_capabilities_supply_state_override(self) -> None:
        from stochastic_warfare.entities.capabilities import CombatPowerCalculator
        from stochastic_warfare.entities.base import Unit
        from stochastic_warfare.entities.personnel import CrewMember, CrewRole

        unit = Unit(
            entity_id="test_unit",
            position=Position(0.0, 0.0),
            personnel=[
                CrewMember(member_id="m1", role=CrewRole.COMMANDER, skill=3, experience=0.5),
                CrewMember(member_id="m2", role=CrewRole.GUNNER, skill=3, experience=0.5),
            ],
        )
        calc = CombatPowerCalculator()

        # Default → supply_state = 1.0
        factors_default = calc.factors(unit)
        assert factors_default.supply_state == 1.0

        # Override → supply_state = 0.5
        factors_low = calc.factors(unit, supply_state_override=0.5)
        assert factors_low.supply_state == 0.5


# ---------------------------------------------------------------------------
# Scenario 3: Maintenance + supply interaction
# ---------------------------------------------------------------------------


class TestMaintenanceSupply:
    def test_breakdown_repair_with_spare_parts(self) -> None:
        bus = EventBus()
        rng = _make_rng()

        cfg = MaintenanceConfig(base_mtbf_hours=0.001, repair_time_hours=1.0)
        maint = MaintenanceEngine(event_bus=bus, rng=rng, config=cfg)
        maint.register_equipment("u1", ["eq1"])

        # Cause breakdown
        breakdowns = maint.update(1.0)
        assert len(breakdowns) > 0

        # Repair with spare parts
        started = maint.start_repair("u1", "eq1", spare_parts_available=5.0)
        assert started is True

        completed = maint.complete_repairs(2.0)
        assert ("u1", "eq1") in completed


# ---------------------------------------------------------------------------
# Scenario 4: Medical evacuation chain
# ---------------------------------------------------------------------------


class TestMedicalChain:
    def test_casualty_through_treatment(self) -> None:
        bus = EventBus()
        rng = _make_rng()
        cfg = MedicalConfig(treatment_hours_minor=0.5)
        medical = MedicalEngine(event_bus=bus, rng=rng, config=cfg)

        facility = MedicalFacility(
            facility_id="aid_1",
            facility_type=MedicalFacilityType.AID_STATION,
            position=_POS_UNIT,
            capacity=10,
        )
        medical.register_facility(facility)

        medical.receive_casualty("u1", "m1", severity=1, facility_id="aid_1")
        medical.update(0.1)  # triage + start
        completed = medical.update(1.0)  # treatment
        assert len(completed) == 1
        assert completed[0].outcome in ("RTD", "PERMANENT_LOSS", "DIED_OF_WOUNDS")


# ---------------------------------------------------------------------------
# Scenario 5: Engineering terrain modification
# ---------------------------------------------------------------------------


class TestEngineeringModification:
    def test_build_bridge_completes(self) -> None:
        bus = EventBus()
        rng = _make_rng()
        from stochastic_warfare.logistics.engineering import EngineeringConfig

        cfg = EngineeringConfig(bridge_build_hours=4.0)
        eng = EngineeringEngine(event_bus=bus, rng=rng, config=cfg)

        from stochastic_warfare.logistics.events import ConstructionCompletedEvent
        events: list[Event] = []
        bus.subscribe(ConstructionCompletedEvent, events.append)

        eng.start_project(EngineeringTask.BUILD_BRIDGE, _POS_UNIT, "eng_1",
                          target_feature_id="bridge_1")
        eng.update(5.0, timestamp=_TS)
        assert len(events) == 1


# ---------------------------------------------------------------------------
# Scenario 6: Naval UNREP
# ---------------------------------------------------------------------------


class TestNavalUNREP:
    def test_unrep_success_and_storm_block(self) -> None:
        bus = EventBus()
        rng = _make_rng()
        naval = NavalLogisticsEngine(event_bus=bus, rng=rng)

        # Success in calm seas
        mission = naval.start_unrep("aoe_1", ["ddg_1"], 100.0, 20.0, sea_state=3)
        assert mission is not None

        # Blocked in heavy seas
        mission2 = naval.start_unrep("aoe_2", ["cg_1"], 100.0, 20.0, sea_state=7)
        assert mission2 is None


# ---------------------------------------------------------------------------
# Scenario 7: Transport interdiction
# ---------------------------------------------------------------------------


class TestTransportInterdiction:
    def test_convoy_survives_or_destroyed(self) -> None:
        bus = EventBus()
        rng = _make_rng()

        disruption = DisruptionEngine(event_bus=bus, rng=rng)
        disruption.apply_interdiction("z1", _POS_UNIT, 10000.0, 0.5)

        # Run 50 transits — some should survive, some not
        survived = 0
        destroyed = 0
        for _ in range(50):
            if disruption.check_transport_interdiction(_POS_UNIT):
                survived += 1
            else:
                destroyed += 1
        assert survived > 0
        assert destroyed > 0


# ---------------------------------------------------------------------------
# Scenario 8: Seasonal route degradation
# ---------------------------------------------------------------------------


class TestSeasonalDegradation:
    def test_mud_degrades_routes(self) -> None:
        bus = EventBus()
        rng = _make_rng()

        network = SupplyNetworkEngine(event_bus=bus, rng=rng)
        network.add_node(SupplyNode("A", _POS_DEPOT, "DEPOT"))
        network.add_node(SupplyNode("B", _POS_UNIT, "UNIT"))
        network.add_route(SupplyRoute(
            "r1", "A", "B", TransportMode.ROAD,
            5000.0, 10.0, 1.0,
        ))

        # Mud season degrades roads
        network.update(10.0, ground_state=2)
        route = network.get_route("r1")
        assert route.condition < 1.0

        # Reduced capacity
        path = network.find_supply_route("A", "B")
        assert path is not None
        cap = network.compute_route_capacity(path)
        assert cap < 10.0


# ---------------------------------------------------------------------------
# Scenario 9: Depot capture
# ---------------------------------------------------------------------------


class TestDepotCapture:
    def test_captured_depot_reduced_inventory(self) -> None:
        bus = EventBus()
        rng = _make_rng()
        stockpile = StockpileManager(event_bus=bus, rng=rng)

        inv = SupplyInventory()
        inv.add(CLS_III, "fuel_diesel", 1000.0)
        stockpile.create_depot("d1", _POS_DEPOT, DepotType.DEPOT, "red",
                               initial_inventory=inv)

        stockpile.capture_depot("d1", "blue")
        depot = stockpile.get_depot("d1")
        assert depot.side == "blue"
        assert depot.inventory.available(CLS_III, "fuel_diesel") == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# Scenario 10: Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    def test_same_seed_identical_supply_flows(self) -> None:
        def run(seed: int) -> tuple[float, float, int]:
            bus = EventBus()
            rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)

            stockpile = StockpileManager(event_bus=bus, rng=rng)
            inv = SupplyInventory()
            inv.add(CLS_III, "fuel_diesel", 1000.0)
            stockpile.create_depot("d1", _POS_DEPOT, DepotType.DEPOT, "blue",
                                   initial_inventory=inv)
            unit_inv = SupplyInventory()
            unit_inv.add(CLS_III, "fuel_diesel", 100.0)
            stockpile.register_unit_inventory("u1", unit_inv, {
                CLS_III: {"fuel_diesel": 200.0}
            })

            consumption = ConsumptionEngine(event_bus=bus, rng=rng)
            result = consumption.compute_consumption(
                10, 2, 50.0, int(ActivityLevel.MARCH), 2.0,
            )

            shortfalls = stockpile.consume_unit_supplies("u1", result.as_dict())
            supply_state = stockpile.get_supply_state("u1")
            remaining = unit_inv.available(CLS_III, "fuel_diesel")

            maint = MaintenanceEngine(event_bus=bus, rng=rng)
            maint.register_equipment("u1", ["eq1", "eq2"])
            breakdowns = maint.update(50.0)

            return (supply_state, remaining, len(breakdowns))

        r1 = run(99)
        r2 = run(99)
        assert r1 == r2

    def test_different_seeds_differ(self) -> None:
        def run(seed: int) -> int:
            bus = EventBus()
            rng = RNGManager(seed).get_stream(ModuleId.LOGISTICS)
            maint = MaintenanceEngine(event_bus=bus, rng=rng)
            maint.register_equipment("u1", [f"eq{i}" for i in range(10)])
            return len(maint.update(200.0))

        # With 10 equipment and 200 hours, different seeds should (usually)
        # produce different breakdown counts
        results = [run(s) for s in range(10)]
        assert len(set(results)) > 1  # at least 2 distinct values

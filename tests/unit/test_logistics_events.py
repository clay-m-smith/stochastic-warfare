"""Tests for logistics/events.py -- all logistics event types."""

from __future__ import annotations

from datetime import datetime, timezone

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    BlockadeEstablishedEvent,
    CasualtyEvacuatedEvent,
    CasualtyTreatedEvent,
    ConstructionCompletedEvent,
    ConstructionStartedEvent,
    ConvoyArrivedEvent,
    ConvoyDestroyedEvent,
    ConvoyDispatchedEvent,
    EquipmentBreakdownEvent,
    InfrastructureRepairedEvent,
    MaintenanceCompletedEvent,
    MaintenanceStartedEvent,
    ObstacleClearedEvent,
    ObstacleEmplacedEvent,
    PortLoadingEvent,
    PrisonerCapturedEvent,
    PrisonerTransferredEvent,
    ReturnToDutyEvent,
    RouteInterdictedEvent,
    RouteDegradedEvent,
    SupplyDeliveredEvent,
    SupplyDepletedEvent,
    SupplyShortageEvent,
    UnrepCompletedEvent,
    UnrepStartedEvent,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_SRC = ModuleId.LOGISTICS
_POS = Position(100.0, 200.0, 0.0)


# ---------------------------------------------------------------------------
# Supply events
# ---------------------------------------------------------------------------


class TestSupplyEvents:
    def test_supply_delivered_fields(self) -> None:
        e = SupplyDeliveredEvent(
            timestamp=_TS, source=_SRC,
            recipient_id="unit_1", supply_class=3, quantity=100.0,
            transport_mode=0,
        )
        assert e.recipient_id == "unit_1"
        assert e.supply_class == 3
        assert e.quantity == 100.0
        assert e.transport_mode == 0

    def test_supply_delivered_is_event(self) -> None:
        e = SupplyDeliveredEvent(
            timestamp=_TS, source=_SRC,
            recipient_id="u", supply_class=1, quantity=1.0, transport_mode=0,
        )
        assert isinstance(e, Event)

    def test_supply_delivered_frozen(self) -> None:
        e = SupplyDeliveredEvent(
            timestamp=_TS, source=_SRC,
            recipient_id="u", supply_class=1, quantity=1.0, transport_mode=0,
        )
        try:
            e.quantity = 99.0  # type: ignore[misc]
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_supply_shortage_fields(self) -> None:
        e = SupplyShortageEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", supply_class=5, current_fraction=0.2,
            hours_remaining=4.0,
        )
        assert e.unit_id == "u1"
        assert e.current_fraction == 0.2
        assert e.hours_remaining == 4.0

    def test_supply_depleted_fields(self) -> None:
        e = SupplyDepletedEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", supply_class=3,
        )
        assert e.unit_id == "u1"
        assert e.supply_class == 3


# ---------------------------------------------------------------------------
# Transport events
# ---------------------------------------------------------------------------


class TestTransportEvents:
    def test_convoy_dispatched(self) -> None:
        e = ConvoyDispatchedEvent(
            timestamp=_TS, source=_SRC,
            mission_id="m1", origin_id="depot_a", destination_id="unit_1",
            transport_mode=0, cargo_tons=5.0,
        )
        assert e.mission_id == "m1"
        assert e.cargo_tons == 5.0

    def test_convoy_arrived(self) -> None:
        e = ConvoyArrivedEvent(
            timestamp=_TS, source=_SRC,
            mission_id="m1", destination_id="unit_1", cargo_tons=5.0,
        )
        assert e.destination_id == "unit_1"

    def test_convoy_destroyed(self) -> None:
        e = ConvoyDestroyedEvent(
            timestamp=_TS, source=_SRC,
            mission_id="m1", position=_POS, cargo_lost_tons=5.0,
            cause="interdiction",
        )
        assert e.position == _POS
        assert e.cause == "interdiction"


# ---------------------------------------------------------------------------
# Maintenance events
# ---------------------------------------------------------------------------


class TestMaintenanceEvents:
    def test_maintenance_started(self) -> None:
        e = MaintenanceStartedEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", equipment_id="eq1", estimated_hours=4.0,
        )
        assert e.estimated_hours == 4.0

    def test_maintenance_completed(self) -> None:
        e = MaintenanceCompletedEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", equipment_id="eq1", condition_restored=0.95,
        )
        assert e.condition_restored == 0.95

    def test_equipment_breakdown(self) -> None:
        e = EquipmentBreakdownEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", equipment_id="eq1",
        )
        assert e.equipment_id == "eq1"


# ---------------------------------------------------------------------------
# Engineering events
# ---------------------------------------------------------------------------


class TestEngineeringEvents:
    def test_construction_started(self) -> None:
        e = ConstructionStartedEvent(
            timestamp=_TS, source=_SRC,
            project_id="p1", task_type=0, position=_POS,
            assigned_unit_id="eng_1",
        )
        assert e.project_id == "p1"
        assert e.assigned_unit_id == "eng_1"

    def test_construction_completed(self) -> None:
        e = ConstructionCompletedEvent(
            timestamp=_TS, source=_SRC,
            project_id="p1", task_type=0, target_feature_id="bridge_1",
        )
        assert e.target_feature_id == "bridge_1"

    def test_infrastructure_repaired(self) -> None:
        e = InfrastructureRepairedEvent(
            timestamp=_TS, source=_SRC,
            feature_id="road_1", condition_restored=0.8,
        )
        assert e.condition_restored == 0.8

    def test_obstacle_emplaced(self) -> None:
        e = ObstacleEmplacedEvent(
            timestamp=_TS, source=_SRC,
            obstacle_id="mine_1", obstacle_type="minefield",
            position=_POS,
        )
        assert e.obstacle_type == "minefield"

    def test_obstacle_cleared(self) -> None:
        e = ObstacleClearedEvent(
            timestamp=_TS, source=_SRC,
            obstacle_id="mine_1",
        )
        assert e.obstacle_id == "mine_1"


# ---------------------------------------------------------------------------
# Medical events
# ---------------------------------------------------------------------------


class TestMedicalEvents:
    def test_casualty_evacuated(self) -> None:
        e = CasualtyEvacuatedEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", member_id="m1",
            from_facility_type=0, to_facility_type=1,
        )
        assert e.from_facility_type == 0
        assert e.to_facility_type == 1

    def test_casualty_treated(self) -> None:
        e = CasualtyTreatedEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", member_id="m1", outcome="RTD",
        )
        assert e.outcome == "RTD"

    def test_return_to_duty(self) -> None:
        e = ReturnToDutyEvent(
            timestamp=_TS, source=_SRC,
            unit_id="u1", member_id="m1",
        )
        assert e.member_id == "m1"


# ---------------------------------------------------------------------------
# POW events
# ---------------------------------------------------------------------------


class TestPOWEvents:
    def test_prisoner_captured(self) -> None:
        e = PrisonerCapturedEvent(
            timestamp=_TS, source=_SRC,
            capturing_unit_id="u1", prisoner_count=12,
            side_captured="red",
        )
        assert e.prisoner_count == 12

    def test_prisoner_transferred(self) -> None:
        e = PrisonerTransferredEvent(
            timestamp=_TS, source=_SRC,
            group_id="pg1", destination_id="camp_1",
        )
        assert e.destination_id == "camp_1"


# ---------------------------------------------------------------------------
# Naval logistics events
# ---------------------------------------------------------------------------


class TestNavalLogisticsEvents:
    def test_unrep_started(self) -> None:
        e = UnrepStartedEvent(
            timestamp=_TS, source=_SRC,
            supply_ship_id="aoe_1",
            receiving_unit_ids=("ddg_1", "cg_1"),
        )
        assert e.supply_ship_id == "aoe_1"
        assert len(e.receiving_unit_ids) == 2

    def test_unrep_completed(self) -> None:
        e = UnrepCompletedEvent(
            timestamp=_TS, source=_SRC,
            supply_ship_id="aoe_1",
            receiving_unit_ids=("ddg_1",),
            fuel_transferred_tons=500.0,
            ammo_transferred_tons=50.0,
        )
        assert e.fuel_transferred_tons == 500.0

    def test_port_loading(self) -> None:
        e = PortLoadingEvent(
            timestamp=_TS, source=_SRC,
            port_id="port_1", ship_ids=("lhd_1",),
            op_type=1, tons_transferred=2000.0,
        )
        assert e.tons_transferred == 2000.0


# ---------------------------------------------------------------------------
# Disruption events
# ---------------------------------------------------------------------------


class TestDisruptionEvents:
    def test_route_interdicted(self) -> None:
        e = RouteInterdictedEvent(
            timestamp=_TS, source=_SRC,
            route_id="r1", position=_POS, severity=0.7,
        )
        assert e.severity == 0.7

    def test_route_degraded(self) -> None:
        e = RouteDegradedEvent(
            timestamp=_TS, source=_SRC,
            route_id="r1", old_condition=0.9, new_condition=0.5,
            cause="seasonal",
        )
        assert e.old_condition == 0.9
        assert e.new_condition == 0.5

    def test_blockade_established(self) -> None:
        e = BlockadeEstablishedEvent(
            timestamp=_TS, source=_SRC,
            blockade_id="b1",
            sea_zone_ids=("zone_a", "zone_b"),
            enforcing_side="blue",
        )
        assert len(e.sea_zone_ids) == 2


# ---------------------------------------------------------------------------
# EventBus integration
# ---------------------------------------------------------------------------


class TestEventBusIntegration:
    def test_publish_subscribe_supply_event(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(SupplyDeliveredEvent, received.append)
        e = SupplyDeliveredEvent(
            timestamp=_TS, source=_SRC,
            recipient_id="u1", supply_class=3, quantity=50.0,
            transport_mode=0,
        )
        bus.publish(e)
        assert len(received) == 1
        assert received[0] is e

    def test_subscribe_base_receives_all(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, received.append)
        bus.publish(SupplyDepletedEvent(
            timestamp=_TS, source=_SRC, unit_id="u1", supply_class=3,
        ))
        bus.publish(ConvoyArrivedEvent(
            timestamp=_TS, source=_SRC,
            mission_id="m1", destination_id="d1", cargo_tons=1.0,
        ))
        assert len(received) == 2

    def test_all_events_have_source_logistics(self) -> None:
        events = [
            SupplyDeliveredEvent(
                timestamp=_TS, source=_SRC,
                recipient_id="u", supply_class=1, quantity=1.0,
                transport_mode=0,
            ),
            MaintenanceStartedEvent(
                timestamp=_TS, source=_SRC,
                unit_id="u", equipment_id="e", estimated_hours=1.0,
            ),
            PrisonerCapturedEvent(
                timestamp=_TS, source=_SRC,
                capturing_unit_id="u", prisoner_count=1,
                side_captured="red",
            ),
        ]
        for e in events:
            assert e.source == ModuleId.LOGISTICS

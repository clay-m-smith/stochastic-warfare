"""Medical, maintenance, and event-feedback behavior."""

from datetime import datetime, timezone

import pytest

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.personnel import CrewMember, InjuryState
from stochastic_warfare.entities.equipment import EquipmentItem
from stochastic_warfare.core.types import Domain, ModuleId, Position
from stochastic_warfare.logistics.events import (
    EquipmentBreakdownEvent,
    MaintenanceCompletedEvent,
    ReturnToDutyEvent,
)
from stochastic_warfare.simulation.calibration import CalibrationSchema
from stochastic_warfare.simulation.engine import SimulationEngine


TS = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)


def _make_crew(member_id="m1", injury=InjuryState.HEALTHY):
    m = CrewMember(member_id=member_id, role=0, skill=3, experience=0.5)
    m.injury = injury
    return m


def _make_equip(eid="e1", operational=True):
    e = EquipmentItem(equipment_id=eid, name="gun", category=0)
    e.operational = operational
    return e


def _make_unit(uid="u1", personnel=None, equipment=None):
    u = Unit(
        entity_id=uid,
        position=Position(0.0, 0.0, 0.0),
        name=uid,
        unit_type="test_unit",
        side="blue",
        domain=Domain.GROUND,
        status=UnitStatus.ACTIVE,
    )
    if personnel is not None:
        u.personnel = personnel
    if equipment is not None:
        u.equipment = equipment
    return u


class TestRestoreCrewMember:
    """Test Unit.restore_crew_member method."""

    def test_rtd_restores_from_serious_wound(self):
        m = _make_crew("m1", InjuryState.SERIOUS_WOUND)
        u = _make_unit(personnel=[m])
        result = u.restore_crew_member("m1")
        assert result is True
        assert m.injury == InjuryState.MINOR_WOUND

    def test_rtd_kia_returns_false(self):
        m = _make_crew("m1", InjuryState.KIA)
        u = _make_unit(personnel=[m])
        result = u.restore_crew_member("m1")
        assert result is False
        assert m.injury == InjuryState.KIA

    def test_rtd_unknown_member_returns_false(self):
        m = _make_crew("m1", InjuryState.SERIOUS_WOUND)
        u = _make_unit(personnel=[m])
        result = u.restore_crew_member("unknown_id")
        assert result is False

    def test_rtd_unknown_unit_no_crash(self):
        u = _make_unit(personnel=[])
        result = u.restore_crew_member("m1")
        assert result is False

    def test_rtd_custom_to_state(self):
        m = _make_crew("m1", InjuryState.CRITICAL)
        u = _make_unit(personnel=[m])
        u.restore_crew_member("m1", to_state=InjuryState.HEALTHY)
        assert m.injury == InjuryState.HEALTHY

    def test_rtd_already_healthy(self):
        m = _make_crew("m1", InjuryState.HEALTHY)
        u = _make_unit(personnel=[m])
        result = u.restore_crew_member("m1", to_state=InjuryState.MINOR_WOUND)
        assert result is True
        assert m.injury == InjuryState.MINOR_WOUND

    def test_multiple_rtd_events(self):
        m1 = _make_crew("m1", InjuryState.SERIOUS_WOUND)
        m2 = _make_crew("m2", InjuryState.CRITICAL)
        u = _make_unit(personnel=[m1, m2])
        u.restore_crew_member("m1")
        u.restore_crew_member("m2")
        assert m1.injury == InjuryState.MINOR_WOUND
        assert m2.injury == InjuryState.MINOR_WOUND


class TestEventFeedbackHandlers:
    """The real EventBus reaches SimulationEngine feedback handlers."""

    @staticmethod
    def _registered_engine(
        unit: Unit,
        *,
        enabled: bool,
    ) -> tuple[SimulationEngine, EventBus]:
        bus = EventBus()
        engine = SimulationEngine.__new__(SimulationEngine)
        engine._ctx = type(
            "EventFeedbackContext",
            (),
            {
                "calibration": CalibrationSchema(
                    enable_event_feedback=enabled,
                ),
                "event_bus": bus,
                "space_engine": None,
                "units_by_side": {"blue": [unit]},
            },
        )()
        engine._register_event_handlers()
        return engine, bus

    def test_enabled_feedback_dispatches_all_registered_event_types(self):
        member = _make_crew("m1", InjuryState.SERIOUS_WOUND)
        broken = _make_equip("break", operational=True)
        repaired = _make_equip("repair", operational=False)
        unit = _make_unit(
            personnel=[member],
            equipment=[broken, repaired],
        )
        _engine, bus = self._registered_engine(unit, enabled=True)

        bus.publish(
            EquipmentBreakdownEvent(
                timestamp=TS,
                source=ModuleId.LOGISTICS,
                unit_id=unit.entity_id,
                equipment_id=broken.equipment_id,
            ),
        )
        bus.publish(
            MaintenanceCompletedEvent(
                timestamp=TS,
                source=ModuleId.LOGISTICS,
                unit_id=unit.entity_id,
                equipment_id=repaired.equipment_id,
                condition_restored=1.0,
            ),
        )
        bus.publish(
            ReturnToDutyEvent(
                timestamp=TS,
                source=ModuleId.LOGISTICS,
                unit_id=unit.entity_id,
                member_id=member.member_id,
            ),
        )

        assert broken.operational is False
        assert repaired.operational is True
        assert member.injury is InjuryState.MINOR_WOUND

    def test_disabled_feedback_leaves_all_event_targets_unchanged(self):
        member = _make_crew("m1", InjuryState.SERIOUS_WOUND)
        broken = _make_equip("break", operational=True)
        repaired = _make_equip("repair", operational=False)
        unit = _make_unit(
            personnel=[member],
            equipment=[broken, repaired],
        )
        _engine, bus = self._registered_engine(unit, enabled=False)

        bus.publish(
            EquipmentBreakdownEvent(
                timestamp=TS,
                source=ModuleId.LOGISTICS,
                unit_id=unit.entity_id,
                equipment_id=broken.equipment_id,
            ),
        )
        bus.publish(
            MaintenanceCompletedEvent(
                timestamp=TS,
                source=ModuleId.LOGISTICS,
                unit_id=unit.entity_id,
                equipment_id=repaired.equipment_id,
                condition_restored=1.0,
            ),
        )
        bus.publish(
            ReturnToDutyEvent(
                timestamp=TS,
                source=ModuleId.LOGISTICS,
                unit_id=unit.entity_id,
                member_id=member.member_id,
            ),
        )

        assert broken.operational is True
        assert repaired.operational is False
        assert member.injury is InjuryState.SERIOUS_WOUND

    def test_degraded_equipment_threshold_exists(self):
        """CalibrationSchema has degraded_equipment_threshold."""
        cal = CalibrationSchema()
        assert hasattr(cal, "degraded_equipment_threshold")
        assert cal.degraded_equipment_threshold == pytest.approx(0.3)

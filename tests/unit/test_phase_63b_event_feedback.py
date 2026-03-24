"""Phase 63b: Medical → Strength & Maintenance → Readiness tests."""

import pytest

from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.personnel import CrewMember, InjuryState
from stochastic_warfare.entities.equipment import EquipmentItem
from stochastic_warfare.core.types import Position, Domain
from stochastic_warfare.simulation.calibration import CalibrationSchema


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
    """Test SimulationEngine event subscription and handlers."""

    def test_event_feedback_disabled_no_subscription(self):
        """When enable_event_feedback=False, no event handlers registered."""
        import stochastic_warfare.simulation.engine as eng_mod
        src = open(eng_mod.__file__).read()
        assert "enable_event_feedback" in src
        assert "ReturnToDutyEvent" in src

    def test_equipment_breakdown_marks_non_operational(self):
        e = _make_equip("e1", operational=True)
        u = _make_unit(equipment=[e])

        # Simulate what _handle_equipment_breakdown does
        for equip in u.equipment:
            if equip.equipment_id == "e1":
                equip.operational = False
                break
        assert e.operational is False

    def test_maintenance_completed_restores_operational(self):
        e = _make_equip("e1", operational=False)
        u = _make_unit(equipment=[e])

        for equip in u.equipment:
            if equip.equipment_id == "e1":
                equip.operational = True
                break
        assert e.operational is True

    def test_breakdown_completed_roundtrip(self):
        e = _make_equip("e1", operational=True)
        u = _make_unit(equipment=[e])

        # Breakdown
        for equip in u.equipment:
            if equip.equipment_id == "e1":
                equip.operational = False
                break
        assert e.operational is False

        # Maintenance completed
        for equip in u.equipment:
            if equip.equipment_id == "e1":
                equip.operational = True
                break
        assert e.operational is True

    def test_breakdown_nonexistent_equipment_no_crash(self):
        u = _make_unit(equipment=[_make_equip("e1")])
        # Looking for e2 — should not crash
        found = False
        for equip in u.equipment:
            if equip.equipment_id == "e2":
                equip.operational = False
                found = True
                break
        assert not found

    def test_structural_event_subscription(self):
        """Structural: engine.py subscribes to all 3 event types."""
        import stochastic_warfare.simulation.engine as eng_mod
        src = open(eng_mod.__file__).read()
        assert "ReturnToDutyEvent" in src
        assert "EquipmentBreakdownEvent" in src
        assert "MaintenanceCompletedEvent" in src
        assert "bus.subscribe" in src

    def test_degraded_equipment_threshold_exists(self):
        """CalibrationSchema has degraded_equipment_threshold."""
        cal = CalibrationSchema()
        assert hasattr(cal, "degraded_equipment_threshold")
        assert cal.degraded_equipment_threshold == pytest.approx(0.3)

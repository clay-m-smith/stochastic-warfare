"""Phase 63 Step S: Structural verification tests."""

import pytest


def _read_source(module_path: str) -> str:
    """Read source file for structural assertions."""
    import importlib
    mod = importlib.import_module(module_path)
    return open(mod.__file__).read()


class TestPhase63Structural:
    """Source-level string assertions to catch regressions."""

    def test_enable_event_feedback_in_calibration(self):
        src = _read_source("stochastic_warfare.simulation.calibration")
        assert "enable_event_feedback" in src

    def test_enable_missile_routing_in_calibration(self):
        src = _read_source("stochastic_warfare.simulation.calibration")
        assert "enable_missile_routing" in src

    def test_enable_c2_friction_in_calibration(self):
        src = _read_source("stochastic_warfare.simulation.calibration")
        assert "enable_c2_friction" in src

    def test_rtd_event_subscription_in_engine(self):
        src = _read_source("stochastic_warfare.simulation.engine")
        assert "ReturnToDutyEvent" in src
        assert "subscribe" in src

    def test_equipment_breakdown_subscription_in_engine(self):
        src = _read_source("stochastic_warfare.simulation.engine")
        assert "EquipmentBreakdownEvent" in src

    def test_maintenance_completed_subscription_in_engine(self):
        src = _read_source("stochastic_warfare.simulation.engine")
        assert "MaintenanceCompletedEvent" in src

    def test_missile_type_handling_in_engagement(self):
        src = _read_source("stochastic_warfare.combat.engagement")
        assert "EngagementType.MISSILE" in src
        # Must be in a handler, not just the enum declaration
        assert "engagement_type == EngagementType.MISSILE" in src

    def test_missile_engine_instantiation_in_scenario(self):
        src = _read_source("stochastic_warfare.simulation.scenario")
        assert "missile_engine" in src
        assert "MissileEngine" in src

    def test_comms_engine_in_get_state(self):
        src = _read_source("stochastic_warfare.simulation.scenario")
        assert '("comms_engine", self.comms_engine)' in src

    def test_detection_engine_in_get_state(self):
        src = _read_source("stochastic_warfare.simulation.scenario")
        assert '("detection_engine", self.detection_engine)' in src

    def test_sensors_not_hardcoded_empty_in_battle_fow(self):
        src = _read_source("stochastic_warfare.simulation.battle")
        # The old hardcoded empty list should be replaced with real sensor lookup
        assert "ctx.unit_sensors.get(_u.entity_id, [])" in src
        assert '"sensors": []' not in src

    def test_enable_c2_friction_in_battle(self):
        src = _read_source("stochastic_warfare.simulation.battle")
        assert "enable_c2_friction" in src

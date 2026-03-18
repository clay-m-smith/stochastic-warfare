"""Phase 63 Step 0: CalibrationSchema infrastructure tests."""

import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestPhase63CalibrationFlags:
    """Verify Phase 63 calibration flags exist with correct defaults."""

    def test_enable_event_feedback_default_false(self):
        cal = CalibrationSchema()
        assert cal.enable_event_feedback is False

    def test_enable_missile_routing_default_false(self):
        cal = CalibrationSchema()
        assert cal.enable_missile_routing is False

    def test_enable_c2_friction_default_false(self):
        cal = CalibrationSchema()
        assert cal.enable_c2_friction is False

    def test_degraded_equipment_threshold_default(self):
        cal = CalibrationSchema()
        assert cal.degraded_equipment_threshold == pytest.approx(0.3)

    def test_backward_compat_default_construction(self):
        """CalibrationSchema() still constructs without any args."""
        cal = CalibrationSchema()
        assert isinstance(cal, CalibrationSchema)

    def test_enable_event_feedback_accepts_true(self):
        cal = CalibrationSchema(enable_event_feedback=True)
        assert cal.enable_event_feedback is True

    def test_enable_missile_routing_accepts_true(self):
        cal = CalibrationSchema(enable_missile_routing=True)
        assert cal.enable_missile_routing is True

    def test_enable_c2_friction_accepts_true(self):
        cal = CalibrationSchema(enable_c2_friction=True)
        assert cal.enable_c2_friction is True

    def test_degraded_equipment_threshold_custom(self):
        cal = CalibrationSchema(degraded_equipment_threshold=0.5)
        assert cal.degraded_equipment_threshold == pytest.approx(0.5)

    def test_enable_fog_of_war_still_defaults_false(self):
        """Pre-existing flag unaffected."""
        cal = CalibrationSchema()
        assert cal.enable_fog_of_war is False

    def test_c2_min_effectiveness_still_defaults(self):
        """Pre-existing c2_min_effectiveness unaffected."""
        cal = CalibrationSchema()
        assert cal.c2_min_effectiveness == pytest.approx(0.3)

    def test_phase62_fields_still_present(self):
        """Phase 62 fields survived Phase 63 additions."""
        cal = CalibrationSchema()
        assert hasattr(cal, "enable_human_factors")
        assert hasattr(cal, "enable_cbrn_environment")
        assert hasattr(cal, "enable_air_combat_environment")

    def test_get_accessor_works(self):
        """Dict-compatible .get() returns Phase 63 fields."""
        cal = CalibrationSchema(enable_event_feedback=True)
        assert cal.get("enable_event_feedback", False) is True
        assert cal.get("enable_missile_routing", True) is False

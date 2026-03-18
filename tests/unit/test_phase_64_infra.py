"""Phase 64 Step 0: CalibrationSchema infrastructure tests."""

import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestPhase64CalibrationFields:
    """Verify Phase 64 calibration fields exist with correct defaults."""

    def test_planning_available_time_s_default(self):
        cal = CalibrationSchema()
        assert cal.planning_available_time_s == pytest.approx(7200.0)

    def test_stratagem_concentration_bonus_default(self):
        cal = CalibrationSchema()
        assert cal.stratagem_concentration_bonus == pytest.approx(0.08)

    def test_stratagem_deception_bonus_default(self):
        cal = CalibrationSchema()
        assert cal.stratagem_deception_bonus == pytest.approx(0.10)

    def test_order_propagation_delay_sigma_default(self):
        cal = CalibrationSchema()
        assert cal.order_propagation_delay_sigma == pytest.approx(0.4)

    def test_order_misinterpretation_base_default(self):
        cal = CalibrationSchema()
        assert cal.order_misinterpretation_base == pytest.approx(0.05)

    def test_backward_compat_default_construction(self):
        """CalibrationSchema() still constructs without any args."""
        cal = CalibrationSchema()
        assert isinstance(cal, CalibrationSchema)

    def test_phase64_fields_accept_custom_overrides(self):
        cal = CalibrationSchema(
            planning_available_time_s=3600.0,
            stratagem_concentration_bonus=0.15,
            stratagem_deception_bonus=0.20,
            order_propagation_delay_sigma=0.6,
            order_misinterpretation_base=0.10,
        )
        assert cal.planning_available_time_s == pytest.approx(3600.0)
        assert cal.stratagem_concentration_bonus == pytest.approx(0.15)
        assert cal.stratagem_deception_bonus == pytest.approx(0.20)
        assert cal.order_propagation_delay_sigma == pytest.approx(0.6)
        assert cal.order_misinterpretation_base == pytest.approx(0.10)

    def test_enable_c2_friction_still_defaults_false(self):
        """Pre-existing flag from Phase 63 unaffected."""
        cal = CalibrationSchema()
        assert cal.enable_c2_friction is False

    def test_c2_min_effectiveness_still_defaults(self):
        """Pre-existing c2_min_effectiveness unaffected."""
        cal = CalibrationSchema()
        assert cal.c2_min_effectiveness == pytest.approx(0.3)

    def test_phase63_fields_still_present(self):
        """Phase 63 fields survived Phase 64 additions."""
        cal = CalibrationSchema()
        assert hasattr(cal, "enable_event_feedback")
        assert hasattr(cal, "enable_missile_routing")
        assert hasattr(cal, "enable_c2_friction")
        assert hasattr(cal, "degraded_equipment_threshold")

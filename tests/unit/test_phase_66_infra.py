"""Phase 66 Step 0: CalibrationSchema infrastructure tests."""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation.calibration import CalibrationSchema


class TestPhase66CalibrationFields:
    """Verify Phase 66 CalibrationSchema additions."""

    def test_enable_unconventional_warfare_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_unconventional_warfare is False

    def test_enable_mine_persistence_default_false(self) -> None:
        cal = CalibrationSchema()
        assert cal.enable_mine_persistence is False

    def test_guerrilla_disengage_threshold_default(self) -> None:
        cal = CalibrationSchema()
        assert cal.guerrilla_disengage_threshold == 0.3

    def test_human_shield_pk_reduction_default(self) -> None:
        cal = CalibrationSchema()
        assert cal.human_shield_pk_reduction == 0.5

    def test_enable_flags_accept_true(self) -> None:
        cal = CalibrationSchema(
            enable_unconventional_warfare=True,
            enable_mine_persistence=True,
        )
        assert cal.enable_unconventional_warfare is True
        assert cal.enable_mine_persistence is True

    def test_backward_compat_phase65_fields_present(self) -> None:
        cal = CalibrationSchema()
        assert hasattr(cal, "enable_space_effects")
        assert hasattr(cal, "enable_c2_friction")
        assert hasattr(cal, "enable_event_feedback")

    def test_no_arg_construction(self) -> None:
        cal = CalibrationSchema()
        assert isinstance(cal, CalibrationSchema)

    def test_get_accessor_new_fields(self) -> None:
        cal = CalibrationSchema(
            enable_unconventional_warfare=True,
            guerrilla_disengage_threshold=0.5,
        )
        assert cal.get("enable_unconventional_warfare", False) is True
        assert cal.get("guerrilla_disengage_threshold", 0.3) == 0.5
        assert cal.get("human_shield_pk_reduction", 0.0) == 0.5

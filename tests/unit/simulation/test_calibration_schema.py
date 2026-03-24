"""Unit tests for CalibrationSchema — edge cases.

Phase 75d: Edge cases NOT covered by test_phase49_calibration_schema.py.
"""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation.calibration import (
    CalibrationSchema,
)


# ===================================================================
# Schema edge cases
# ===================================================================


class TestCalibrationSchemaEdgeCases:
    """Edge cases in CalibrationSchema parsing and validation."""

    def test_dead_key_dropped(self):
        """advance_speed is a dead key — should be silently dropped."""
        cal = CalibrationSchema.model_validate({"advance_speed": 5.0})
        assert not hasattr(cal, "advance_speed")

    def test_morale_prefix_routing(self):
        """morale_base_degrade_rate → morale.base_degrade_rate via .get()."""
        cal = CalibrationSchema()
        assert cal.get("morale_base_degrade_rate") == pytest.approx(0.05)

    def test_side_suffix(self):
        """blue_cohesion → side_overrides['blue'].cohesion."""
        cal = CalibrationSchema.model_validate({
            "side_overrides": {"blue": {"cohesion": 0.9}},
        })
        assert cal.get("blue_cohesion") == pytest.approx(0.9)

    def test_side_prefix(self):
        """target_size_modifier_red → side_overrides['red'].target_size_modifier."""
        cal = CalibrationSchema.model_validate({
            "side_overrides": {"red": {"target_size_modifier": 2.0}},
        })
        assert cal.get("target_size_modifier_red") == pytest.approx(2.0)

    def test_extra_forbid(self):
        """Unknown keys should be rejected."""
        with pytest.raises(Exception):
            CalibrationSchema.model_validate({"totally_unknown_key": 1.0})

    def test_structured_passthrough(self):
        """Direct field access works for known fields."""
        cal = CalibrationSchema(hit_probability_modifier=0.8)
        assert cal.hit_probability_modifier == pytest.approx(0.8)


# ===================================================================
# .get() method
# ===================================================================


class TestCalibrationGet:
    """Dict-compatible .get() accessor."""

    def test_direct_field(self):
        cal = CalibrationSchema(visibility_m=5000.0)
        assert cal.get("visibility_m") == pytest.approx(5000.0)

    def test_morale_prefix(self):
        cal = CalibrationSchema()
        val = cal.get("morale_base_recover_rate")
        assert val == pytest.approx(0.10)

    def test_side_suffix(self):
        cal = CalibrationSchema.model_validate({
            "side_overrides": {"blue": {"cohesion": 0.9}},
        })
        assert cal.get("blue_cohesion") == pytest.approx(0.9)

    def test_none_default(self):
        cal = CalibrationSchema()
        assert cal.get("nonexistent_field", 42.0) == 42.0

    def test_unknown_default(self):
        cal = CalibrationSchema()
        assert cal.get("bogus_key") is None

    def test_enable_flags_all_false(self):
        """All enable_* flags default to False."""
        cal = CalibrationSchema()
        enable_fields = [
            f for f in CalibrationSchema.model_fields
            if f.startswith("enable_") and f != "enable_air_routing"
            and f != "enable_fog_of_war"
        ]
        for field_name in enable_fields:
            assert getattr(cal, field_name) is False, f"{field_name} should default to False"

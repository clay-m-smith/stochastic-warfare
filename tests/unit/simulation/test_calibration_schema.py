"""Unit tests for CalibrationSchema — edge cases.

Phase 75d: Edge cases NOT covered by test_phase49_calibration_schema.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from stochastic_warfare.simulation.calibration import (
    CalibrationSchema,
)


# ===================================================================
# Schema edge cases
# ===================================================================


class TestCalibrationSchemaEdgeCases:
    """Edge cases in CalibrationSchema parsing and validation."""

    def test_dead_key_rejected(self):
        """Retired calibration data must not become an empty patch."""
        with pytest.raises(
            ValueError,
            match="unsupported dead calibration.*advance_speed",
        ):
            CalibrationSchema.model_validate({"advance_speed": 5.0})

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

    @pytest.mark.parametrize(
        "payload",
        (
            {"hit_probability_modifier": float("nan")},
            {"morale": {"base_degrade_rate": float("inf")}},
            {"target_value_weights": {"armor": float("-inf")}},
        ),
    )
    def test_nonfinite_values_rejected_throughout_schema(
        self,
        payload: dict,
    ) -> None:
        """NaN and infinity cannot enter any typed calibration field."""
        with pytest.raises(ValidationError, match="must be finite"):
            CalibrationSchema.model_validate(payload, strict=True)

    @pytest.mark.parametrize(
        "payload",
        (
            {
                "morale": {"base_degrade_rate": 0.1},
                "morale_base_degrade_rate": 0.9,
            },
            {
                "side_overrides": {"blue": {"cohesion": 0.1}},
                "blue_cohesion": 0.9,
            },
            {
                "morale": {"degrade_rate_modifier": 0.1},
                "morale_degrade_rate_modifier": 0.9,
            },
        ),
    )
    def test_semantic_alias_collisions_are_rejected(
        self,
        payload: dict,
    ) -> None:
        """Flat compatibility aliases cannot overwrite canonical paths."""
        with pytest.raises(
            ValidationError,
            match="duplicate semantic calibration path",
        ):
            CalibrationSchema.model_validate(payload, strict=True)

    def test_canonical_nested_morale_modifier_updates_compatibility_mirror(
        self,
    ) -> None:
        """One canonical nested value has identical legacy read behavior."""
        calibration = CalibrationSchema.model_validate(
            {"morale": {"degrade_rate_modifier": 0.4}},
            strict=True,
        )

        assert calibration.morale.degrade_rate_modifier == 0.4
        assert calibration.morale_degrade_rate_modifier == 0.4
        assert (
            calibration.to_flat_dict(["blue"])[
                "morale_degrade_rate_modifier"
            ]
            == 0.4
        )

    def test_semantic_aliases_have_one_canonical_sparse_patch(self) -> None:
        """Equivalent flat/nested inputs serialize to one sparse identity."""
        flat = CalibrationSchema.model_validate(
            {"morale_degrade_rate_modifier": 0.4},
            strict=True,
        )
        nested = CalibrationSchema.model_validate(
            {"morale": {"degrade_rate_modifier": 0.4}},
            strict=True,
        )

        assert flat.to_sparse_patch(mode="json") == (
            nested.to_sparse_patch(mode="json")
        )
        assert CalibrationSchema().to_sparse_patch(mode="json") == {}
        assert CalibrationSchema.model_validate(
            {"morale": {"degrade_rate_modifier": 1.0}},
            strict=True,
        ).to_sparse_patch(mode="json") != {}


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
        # enable_air_routing, enable_fog_of_war, enable_detection_culling
        # default to True — exclude from this check
        _TRUE_DEFAULTS = {"enable_air_routing", "enable_fog_of_war", "enable_detection_culling"}
        enable_fields = [
            f for f in CalibrationSchema.model_fields
            if f.startswith("enable_") and f not in _TRUE_DEFAULTS
        ]
        for field_name in enable_fields:
            assert getattr(cal, field_name) is False, f"{field_name} should default to False"

"""Tests for Phase 86a: CalibrationSchema flat dict optimization."""

from __future__ import annotations

import pytest

from stochastic_warfare.simulation.calibration import (
    CalibrationSchema,
    MoraleCalibration,
    SideCalibration,
)


class TestToFlatDict:
    """Tests for CalibrationSchema.to_flat_dict()."""

    def test_contains_all_top_level_fields(self) -> None:
        """Flat dict contains every non-None top-level field."""
        cal = CalibrationSchema()
        flat = cal.to_flat_dict(["blue", "red"])
        # All boolean flags are non-None — must be present
        assert "enable_air_routing" in flat
        assert flat["enable_air_routing"] is False
        assert "enable_fog_of_war" in flat
        assert "hit_probability_modifier" in flat
        assert flat["hit_probability_modifier"] == 1.0

    def test_nullable_fields_stripped_when_none(self) -> None:
        """Nullable fields (float | None) are absent when None."""
        cal = CalibrationSchema()
        flat = cal.to_flat_dict(["blue", "red"])
        # visibility_m defaults to None
        assert "visibility_m" not in flat
        # roe_level defaults to None
        assert "roe_level" not in flat

    def test_nullable_fields_present_when_set(self) -> None:
        """Nullable fields appear when explicitly set."""
        cal = CalibrationSchema(visibility_m=5000.0, roe_level="WEAPONS_FREE")
        flat = cal.to_flat_dict(["blue", "red"])
        assert flat["visibility_m"] == 5000.0
        assert flat["roe_level"] == "WEAPONS_FREE"

    def test_morale_keys_flattened(self) -> None:
        """Morale sub-object keys appear as morale_ prefixed flat keys."""
        cal = CalibrationSchema(
            morale=MoraleCalibration(base_degrade_rate=0.1, casualty_weight=3.0),
        )
        flat = cal.to_flat_dict(["blue", "red"])
        assert flat["morale_base_degrade_rate"] == 0.1
        assert flat["morale_casualty_weight"] == 3.0
        # All 10 morale keys present
        for key in CalibrationSchema._MORALE_KEY_MAP:
            assert key in flat, f"Missing morale key: {key}"

    def test_side_suffix_keys_generated(self) -> None:
        """Side-suffixed keys generated for both sides."""
        cal = CalibrationSchema(
            side_overrides={"blue": SideCalibration(cohesion=0.9)},
        )
        flat = cal.to_flat_dict(["blue", "red"])
        assert flat["blue_cohesion"] == 0.9
        # Red has no override — falls back to global (no top-level cohesion → None → stripped)
        assert "red_cohesion" not in flat

    def test_side_suffix_fallback_to_global(self) -> None:
        """Side fields fall back to global field when no override."""
        cal = CalibrationSchema(
            hit_probability_modifier=1.5,
            formation_spacing_m=100.0,
        )
        flat = cal.to_flat_dict(["blue", "red"])
        # No side overrides → should get global value
        assert flat["blue_hit_probability_modifier"] == 1.5
        assert flat["red_hit_probability_modifier"] == 1.5
        assert flat["blue_formation_spacing_m"] == 100.0

    def test_side_prefix_keys_generated(self) -> None:
        """Side-prefixed keys (target_size_modifier_{side}) generated."""
        cal = CalibrationSchema(
            target_size_modifier=2.0,
            side_overrides={"red": SideCalibration(target_size_modifier=0.5)},
        )
        flat = cal.to_flat_dict(["blue", "red"])
        # Red has override
        assert flat["target_size_modifier_red"] == 0.5
        # Blue falls back to global
        assert flat["target_size_modifier_blue"] == 2.0

    def test_flat_dict_matches_get_for_all_patterns(self) -> None:
        """Flat dict values match cal.get() for all key patterns."""
        cal = CalibrationSchema(
            hit_probability_modifier=1.3,
            morale=MoraleCalibration(base_degrade_rate=0.08),
            side_overrides={
                "blue": SideCalibration(cohesion=0.95, force_ratio_modifier=2.0),
                "red": SideCalibration(target_size_modifier=0.7),
            },
        )
        flat = cal.to_flat_dict(["blue", "red"])

        # Direct field
        assert flat["hit_probability_modifier"] == cal.get("hit_probability_modifier", 1.0)

        # Morale
        assert flat["morale_base_degrade_rate"] == cal.get("morale_base_degrade_rate", 0.05)

        # Side-suffix
        assert flat["blue_cohesion"] == cal.get("blue_cohesion", 0.7)
        assert flat["blue_force_ratio_modifier"] == cal.get("blue_force_ratio_modifier", 1.0)

        # Side-prefix
        assert flat["target_size_modifier_red"] == cal.get("target_size_modifier_red", 1.0)

        # Fallback — blue has no target_size_modifier override
        assert flat.get("target_size_modifier_blue", 1.0) == cal.get(
            "target_size_modifier_blue", 1.0,
        )

    def test_enable_all_modern_expansion(self) -> None:
        """enable_all_modern sets all modern flags, reflected in flat dict."""
        cal = CalibrationSchema(enable_all_modern=True)
        flat = cal.to_flat_dict(["blue", "red"])
        assert flat["enable_air_routing"] is True
        assert flat["enable_fog_of_war"] is True
        assert flat["enable_seasonal_effects"] is True

    def test_flat_dict_is_plain_dict(self) -> None:
        """Flat dict is a plain dict (not defaultdict or pydantic)."""
        cal = CalibrationSchema()
        flat = cal.to_flat_dict(["blue", "red"])
        assert type(flat) is dict

    def test_nested_objects_removed(self) -> None:
        """Nested morale and side_overrides objects are not in flat dict."""
        cal = CalibrationSchema()
        flat = cal.to_flat_dict(["blue", "red"])
        assert "morale" not in flat
        assert "side_overrides" not in flat

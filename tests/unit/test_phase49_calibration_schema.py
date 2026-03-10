"""Phase 49: CalibrationSchema hardening tests.

Tests cover:
- Schema construction from flat YAML and structured formats
- .get() backward compatibility with all access patterns
- Before-validator edge cases (dead keys, side names, morale)
- Unknown key rejection (extra="forbid")
- Integration: all scenario YAMLs load without error
- Untested calibration paths (dig_in, wave, target_sel, victory, morale, ROE)
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from stochastic_warfare.simulation.calibration import (
    CalibrationSchema,
    MoraleCalibration,
    SideCalibration,
)


# ═══════════════════════════════════════════════════════════════════════════
# Schema construction
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaConstruction:
    """CalibrationSchema construction from flat and structured formats."""

    def test_empty_schema_has_defaults(self):
        cs = CalibrationSchema()
        assert cs.hit_probability_modifier == 1.0
        assert cs.target_size_modifier == 1.0
        assert cs.destruction_threshold == 0.5
        assert cs.dig_in_ticks == 30
        assert cs.wave_interval_s == 300.0
        assert cs.target_selection_mode == "threat_scored"
        assert cs.roe_level is None
        assert cs.morale.base_degrade_rate == 0.05
        assert cs.side_overrides == {}
        assert cs.weapon_assignments == {}
        assert cs.victory_weights is None

    def test_flat_global_scalars(self):
        cs = CalibrationSchema(**{
            "hit_probability_modifier": 1.5,
            "target_size_modifier": 0.8,
            "visibility_m": 800.0,
            "thermal_contrast": 1.5,
            "destruction_threshold": 0.3,
            "disable_threshold": 0.2,
        })
        assert cs.hit_probability_modifier == 1.5
        assert cs.visibility_m == 800.0
        assert cs.destruction_threshold == 0.3

    def test_flat_morale_keys_nested(self):
        cs = CalibrationSchema(**{
            "morale_base_degrade_rate": 0.01,
            "morale_casualty_weight": 0.5,
            "morale_check_interval": 15,
        })
        assert cs.morale.base_degrade_rate == 0.01
        assert cs.morale.casualty_weight == 0.5
        assert cs.morale.check_interval == 15

    def test_flat_side_suffixed(self):
        cs = CalibrationSchema(**{
            "blue_cohesion": 0.9,
            "red_force_ratio_modifier": 2.0,
            "blue_start_x": 100.0,
            "blue_start_y": 500.0,
        })
        assert cs.side_overrides["blue"].cohesion == 0.9
        assert cs.side_overrides["red"].force_ratio_modifier == 2.0
        assert cs.side_overrides["blue"].start_x == 100.0

    def test_flat_side_prefixed(self):
        cs = CalibrationSchema(**{
            "target_size_modifier_red": 0.8,
            "target_size_modifier_british": 3.0,
        })
        assert cs.side_overrides["red"].target_size_modifier == 0.8
        assert cs.side_overrides["british"].target_size_modifier == 3.0

    def test_compound_side_names(self):
        """Side names with underscores parse correctly."""
        cs = CalibrationSchema(**{
            "franco_spanish_cohesion": 0.6,
            "franco_spanish_start_x": 17000.0,
        })
        assert cs.side_overrides["franco_spanish"].cohesion == 0.6
        assert cs.side_overrides["franco_spanish"].start_x == 17000.0

    def test_dead_key_advance_speed_dropped(self):
        cs = CalibrationSchema(**{"advance_speed": 1.0})
        assert not hasattr(cs, "advance_speed")

    def test_structured_format_passthrough(self):
        """Already-structured data (from model_dump/checkpoint) passes through."""
        cs = CalibrationSchema(**{
            "side_overrides": {
                "blue": {"cohesion": 0.9},
            },
            "morale": {"base_degrade_rate": 0.01},
        })
        assert cs.side_overrides["blue"].cohesion == 0.9
        assert cs.morale.base_degrade_rate == 0.01

    def test_model_dump_round_trip(self):
        cs = CalibrationSchema(**{
            "hit_probability_modifier": 1.5,
            "blue_cohesion": 0.9,
            "target_size_modifier_red": 0.8,
            "morale_base_degrade_rate": 0.01,
        })
        d = cs.model_dump()
        cs2 = CalibrationSchema(**d)
        assert cs2.hit_probability_modifier == 1.5
        assert cs2.side_overrides["blue"].cohesion == 0.9
        assert cs2.side_overrides["red"].target_size_modifier == 0.8
        assert cs2.morale.base_degrade_rate == 0.01

    def test_morale_degrade_rate_modifier_dual_path(self):
        """morale_degrade_rate_modifier is BOTH a top-level field AND morale nested."""
        cs = CalibrationSchema(**{"morale_degrade_rate_modifier": 2.0})
        assert cs.morale_degrade_rate_modifier == 2.0
        assert cs.morale.degrade_rate_modifier == 2.0

    def test_weapon_assignments(self):
        cs = CalibrationSchema(**{
            "weapon_assignments": {"M4A1 Carbine": "m4_556mm"},
        })
        assert cs.weapon_assignments["M4A1 Carbine"] == "m4_556mm"

    def test_victory_weights(self):
        cs = CalibrationSchema(**{
            "victory_weights": {"morale": 0.6, "force_ratio": 0.4},
        })
        assert cs.victory_weights is not None
        assert cs.victory_weights["morale"] == 0.6


# ═══════════════════════════════════════════════════════════════════════════
# Unknown key rejection
# ═══════════════════════════════════════════════════════════════════════════


class TestUnknownKeyRejection:
    """extra='forbid' rejects typos and unknown keys at parse time."""

    def test_typo_raises_validation_error(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            CalibrationSchema(**{"hit_probabiilty_modifier": 1.0})

    def test_completely_unknown_key_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            CalibrationSchema(**{"nonexistent_key": 42})

    def test_nested_morale_extra_rejected(self):
        with pytest.raises(ValidationError):
            CalibrationSchema(**{
                "morale": {"fake_morale_field": 0.5},
            })

    def test_nested_side_extra_rejected(self):
        with pytest.raises(ValidationError):
            CalibrationSchema(**{
                "side_overrides": {"blue": {"fake_field": 0.5}},
            })


# ═══════════════════════════════════════════════════════════════════════════
# .get() backward compatibility
# ═══════════════════════════════════════════════════════════════════════════


class TestGetBackwardCompat:
    """.get() mirrors dict interface for all access patterns."""

    @pytest.fixture()
    def cal(self):
        return CalibrationSchema(**{
            "hit_probability_modifier": 1.5,
            "visibility_m": 800.0,
            "morale_degrade_rate_modifier": 2.0,
            "morale_base_degrade_rate": 0.01,
            "morale_check_interval": 15,
            "blue_cohesion": 0.9,
            "red_force_ratio_modifier": 2.0,
            "target_size_modifier_red": 0.8,
            "weapon_assignments": {"M4A1": "m4_556mm"},
            "defensive_sides": ["blue"],
        })

    def test_direct_field(self, cal):
        assert cal.get("hit_probability_modifier", 1.0) == 1.5

    def test_direct_field_default(self, cal):
        assert cal.get("roe_level", "WEAPONS_FREE") == "WEAPONS_FREE"

    def test_morale_prefix(self, cal):
        assert cal.get("morale_base_degrade_rate", 0.05) == 0.01

    def test_morale_check_interval(self, cal):
        assert cal.get("morale_check_interval", 1) == 15

    def test_side_suffixed(self, cal):
        assert cal.get("blue_cohesion", 0.7) == 0.9

    def test_side_suffixed_missing(self, cal):
        assert cal.get("green_cohesion", 0.7) == 0.7

    def test_side_prefixed(self, cal):
        assert cal.get("target_size_modifier_red", 1.0) == 0.8

    def test_side_prefixed_missing(self, cal):
        assert cal.get("target_size_modifier_green", 1.0) == 1.0

    def test_collections(self, cal):
        assert cal.get("weapon_assignments", {}) == {"M4A1": "m4_556mm"}

    def test_none_able_default(self, cal):
        assert cal.get("victory_weights", None) is None

    def test_defensive_sides(self, cal):
        assert cal.get("defensive_sides", []) == ["blue"]

    def test_completely_unknown_key_returns_default(self, cal):
        assert cal.get("nonexistent_key", 42) == 42

    def test_visibility_m_none_returns_default(self):
        cs = CalibrationSchema()
        assert cs.get("visibility_m", 10000.0) == 10000.0

    def test_visibility_m_set_returns_value(self):
        cs = CalibrationSchema(**{"visibility_m": 800.0})
        assert cs.get("visibility_m", 10000.0) == 800.0


# ═══════════════════════════════════════════════════════════════════════════
# __contains__ support
# ═══════════════════════════════════════════════════════════════════════════


class TestContains:
    """__contains__ supports 'key in calibration' checks."""

    def test_direct_field_present(self):
        cs = CalibrationSchema(**{"dig_in_ticks": 20})
        assert "dig_in_ticks" in cs

    def test_direct_field_none_not_present(self):
        cs = CalibrationSchema()
        assert "roe_level" not in cs

    def test_morale_key_present(self):
        cs = CalibrationSchema(**{"morale_base_degrade_rate": 0.01})
        assert "morale_base_degrade_rate" in cs

    def test_side_suffixed_present(self):
        cs = CalibrationSchema(**{"blue_cohesion": 0.9})
        assert "blue_cohesion" in cs

    def test_side_suffixed_absent(self):
        cs = CalibrationSchema()
        assert "green_cohesion" not in cs

    def test_side_prefixed_present(self):
        cs = CalibrationSchema(**{"target_size_modifier_red": 0.8})
        assert "target_size_modifier_red" in cs


# ═══════════════════════════════════════════════════════════════════════════
# Integration: all scenario YAMLs load via CalibrationSchema
# ═══════════════════════════════════════════════════════════════════════════


class TestYAMLIntegration:
    """All scenario YAMLs load through CalibrationSchema without error."""

    @staticmethod
    def _load_scenario_yamls():
        scenarios = []
        for p in Path("data").rglob("scenario.yaml"):
            data = yaml.safe_load(p.read_text())
            cal_raw = data.get("calibration_overrides", {})
            scenarios.append((str(p), cal_raw))
        return scenarios

    def test_all_scenarios_parse(self):
        """Every scenario YAML's calibration_overrides validates."""
        failures = []
        for path, cal_raw in self._load_scenario_yamls():
            try:
                CalibrationSchema(**(cal_raw or {}))
            except Exception as e:
                failures.append(f"{path}: {e}")
        if failures:
            pytest.fail("CalibrationSchema validation failures:\n" +
                        "\n".join(failures))

    def test_advance_speed_absent(self):
        """advance_speed should no longer appear in any scenario YAML."""
        for path, cal_raw in self._load_scenario_yamls():
            if cal_raw and "advance_speed" in cal_raw:
                pytest.fail(f"{path} still has advance_speed")

    def test_no_behavior_rules_in_calibration(self):
        """behavior_rules is a top-level key, not inside calibration."""
        for path, cal_raw in self._load_scenario_yamls():
            if cal_raw and "behavior_rules" in cal_raw:
                pytest.fail(
                    f"{path} has behavior_rules inside calibration_overrides"
                )

    def test_schema_round_trips_all_scenarios(self):
        """model_dump → re-parse produces identical schema for all YAMLs."""
        for path, cal_raw in self._load_scenario_yamls():
            cs = CalibrationSchema(**(cal_raw or {}))
            d = cs.model_dump()
            cs2 = CalibrationSchema(**d)
            assert cs == cs2, f"Round-trip mismatch: {path}"


# ═══════════════════════════════════════════════════════════════════════════
# Config model integration
# ═══════════════════════════════════════════════════════════════════════════


class TestConfigIntegration:
    """CalibrationSchema integrates with CampaignScenarioConfig."""

    def test_campaign_scenario_config_accepts_dict(self):
        """CampaignScenarioConfig auto-validates dict into CalibrationSchema."""
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

        config = CampaignScenarioConfig(
            name="test",
            date="2024-01-01",
            duration_hours=1.0,
            terrain={"width_m": 1000, "height_m": 1000},
            sides=[
                {"side": "blue", "units": [{"unit_type": "test", "count": 1}]},
                {"side": "red", "units": [{"unit_type": "test", "count": 1}]},
            ],
            calibration_overrides={
                "hit_probability_modifier": 1.5,
                "blue_cohesion": 0.9,
            },
        )
        assert isinstance(config.calibration_overrides, CalibrationSchema)
        assert config.calibration_overrides.hit_probability_modifier == 1.5
        assert config.calibration_overrides.get("blue_cohesion", 0.7) == 0.9

    def test_campaign_scenario_config_rejects_bad_key(self):
        """CampaignScenarioConfig rejects unknown calibration keys."""
        from stochastic_warfare.simulation.scenario import CampaignScenarioConfig

        with pytest.raises(ValidationError):
            CampaignScenarioConfig(
                name="test",
                date="2024-01-01",
                duration_hours=1.0,
                terrain={"width_m": 1000, "height_m": 1000},
                sides=[
                    {"side": "blue", "units": [{"unit_type": "test", "count": 1}]},
                    {"side": "red", "units": [{"unit_type": "test", "count": 1}]},
                ],
                calibration_overrides={"typo_key": 1.0},
            )


# ═══════════════════════════════════════════════════════════════════════════
# State persistence
# ═══════════════════════════════════════════════════════════════════════════


class TestStatePersistence:
    """CalibrationSchema survives get_state/set_state round-trip."""

    def test_get_state_produces_dict(self):
        cs = CalibrationSchema(**{
            "hit_probability_modifier": 1.5,
            "blue_cohesion": 0.9,
        })
        d = cs.model_dump()
        assert isinstance(d, dict)
        assert d["hit_probability_modifier"] == 1.5

    def test_set_state_restores_from_dict(self):
        """Simulates set_state restoring from checkpoint dict."""
        original = CalibrationSchema(**{
            "hit_probability_modifier": 1.5,
            "blue_cohesion": 0.9,
            "morale_base_degrade_rate": 0.01,
        })
        state_dict = original.model_dump()
        restored = CalibrationSchema(**state_dict)
        assert restored.get("hit_probability_modifier", 1.0) == 1.5
        assert restored.get("blue_cohesion", 0.7) == 0.9
        assert restored.get("morale_base_degrade_rate", 0.05) == 0.01


# ═══════════════════════════════════════════════════════════════════════════
# Untested calibration paths exercise
# ═══════════════════════════════════════════════════════════════════════════


class TestUntdCalibrPathExercise:
    """Exercise calibration parameters with zero prior test coverage."""

    def test_dig_in_ticks_configurable(self):
        """E2: dig_in_ticks value consumed via .get()."""
        cs = CalibrationSchema(**{"dig_in_ticks": 10, "defensive_sides": ["blue"]})
        assert cs.get("dig_in_ticks", 30) == 10
        assert cs.get("defensive_sides", []) == ["blue"]

    def test_wave_interval_configurable(self):
        """E3: wave_interval_s consumed via .get()."""
        cs = CalibrationSchema(**{"wave_interval_s": 120.0})
        assert cs.get("wave_interval_s", 300.0) == 120.0

    def test_target_selection_mode_options(self):
        """E4: target_selection_mode supports closest and threat_scored."""
        cs_closest = CalibrationSchema(**{"target_selection_mode": "closest"})
        assert cs_closest.get("target_selection_mode", "threat_scored") == "closest"

        cs_default = CalibrationSchema()
        assert cs_default.get("target_selection_mode", "threat_scored") == "threat_scored"

    def test_roe_level_configurable(self):
        """E5: roe_level consumed via .get()."""
        cs = CalibrationSchema(**{"roe_level": "WEAPONS_TIGHT"})
        assert cs.get("roe_level", None) == "WEAPONS_TIGHT"

    def test_morale_weights_configurable(self):
        """E6: Custom morale weights change nested config."""
        cs = CalibrationSchema(**{
            "morale_casualty_weight": 3.0,
            "morale_leadership_weight": 0.5,
            "morale_cohesion_weight": 0.6,
        })
        assert cs.morale.casualty_weight == 3.0
        assert cs.morale.leadership_weight == 0.5
        assert cs.morale.cohesion_weight == 0.6

    def test_victory_weights_configurable(self):
        """E7: victory_weights consumed via .get()."""
        cs = CalibrationSchema(**{
            "victory_weights": {"morale": 0.7, "force_ratio": 0.3},
        })
        weights = cs.get("victory_weights", None)
        assert weights is not None
        assert weights["morale"] == 0.7

    def test_ew_params_configurable(self):
        """EW parameters consumed via .get()."""
        cs = CalibrationSchema(**{
            "jammer_coverage_mult": 1.5,
            "stealth_detection_penalty": 0.2,
            "sigint_detection_bonus": 0.15,
            "sam_suppression_modifier": 1.2,
        })
        assert cs.get("jammer_coverage_mult", 1.0) == 1.5
        assert cs.get("stealth_detection_penalty", 0.0) == 0.2
        assert cs.get("sigint_detection_bonus", 0.0) == 0.15
        assert cs.get("sam_suppression_modifier", 0.0) == 1.2

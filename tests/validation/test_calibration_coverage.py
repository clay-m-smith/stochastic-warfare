"""Phase 57b: Calibration parameter coverage audit.

Verifies every CalibrationSchema field has at least one Python consumer
and is exercised by at least one scenario or test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from stochastic_warfare.simulation.calibration import (
    CalibrationSchema,
    MoraleCalibration,
    SideCalibration,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "stochastic_warfare"
DATA_DIR = PROJECT_ROOT / "data"

# Fields that are structural (containers for nested models, not directly consumed)
_STRUCTURAL_FIELDS = {"morale", "side_overrides"}

# Fields consumed via dynamic f-string construction (not literal string matches).
# e.g. cal.get(f"rout_{_rout_field}") where _rout_field = "cascade_radius_m"
_DYNAMICALLY_CONSUMED_FIELDS = {
    "rout_cascade_radius_m",
    "rout_cascade_base_chance",
    "rout_cascade_shaken_susceptibility",
}

# Fields exercised only via battle.py consumption (cal.get with defaults),
# not yet set in any scenario YAML or test fixture.  Tracked as deficit.
_CONSUMED_BUT_UNEXERCISED_FIELDS = {
    "wind_accuracy_penalty_scale",
    "rain_attenuation_factor",
}

# Fields consumed via the _MORALE_KEY_MAP (flat key -> nested morale field)
_MORALE_FLAT_KEYS = set(CalibrationSchema._MORALE_KEY_MAP.keys())


def _all_py_files() -> list[Path]:
    """All Python source files in the project."""
    return list(SRC_DIR.rglob("*.py"))


def _all_scenario_yamls() -> list[Path]:
    """All scenario YAML files."""
    scenarios = list(DATA_DIR.rglob("scenario.yaml"))
    return [s for s in scenarios if "test_campaign" not in s.parent.name]


def _load_all_calibrations() -> list[dict]:
    """Load calibration_overrides from all scenario YAMLs."""
    cals = []
    for path in _all_scenario_yamls():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        cal = data.get("calibration_overrides", {})
        if cal:
            cals.append(cal)
    return cals


def _source_text() -> str:
    """Concatenated text of all Python source files (for string search)."""
    parts = []
    for p in _all_py_files():
        try:
            parts.append(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n".join(parts)


class TestCalibrationFieldConsumers:
    """Every CalibrationSchema field must be consumed by Python code."""

    @pytest.fixture(scope="class")
    def source(self):
        return _source_text()

    def test_all_fields_have_consumers(self, source):
        """Each CalibrationSchema field is referenced via cal.get() or attribute access."""
        missing = []
        for field_name in CalibrationSchema.model_fields:
            if field_name in _STRUCTURAL_FIELDS:
                continue
            if field_name in _DYNAMICALLY_CONSUMED_FIELDS:
                continue
            # Check for cal.get("field_name" or .field_name or ["field_name"]
            patterns = [
                f'"{field_name}"',
                f"'{field_name}'",
                f".{field_name}",
            ]
            if not any(p in source for p in patterns):
                missing.append(field_name)
        assert not missing, f"CalibrationSchema fields with zero consumers: {missing}"

    def test_morale_subfields_covered(self, source):
        """All MoraleCalibration fields are consumed."""
        missing = []
        for field_name in MoraleCalibration.model_fields:
            # Consumed via morale.field_name or morale_field_name flat key
            patterns = [
                f'"{field_name}"',
                f"'{field_name}'",
                f".{field_name}",
            ]
            if not any(p in source for p in patterns):
                missing.append(field_name)
        assert not missing, f"MoraleCalibration fields with zero consumers: {missing}"

    def test_side_override_fields_covered(self, source):
        """All SideCalibration fields are consumed."""
        missing = []
        for field_name in SideCalibration.model_fields:
            patterns = [
                f'"{field_name}"',
                f"'{field_name}'",
                f".{field_name}",
            ]
            if not any(p in source for p in patterns):
                missing.append(field_name)
        assert not missing, f"SideCalibration fields with zero consumers: {missing}"


class TestCalibrationFieldExercised:
    """Every CalibrationSchema field must be set by at least one scenario or test."""

    @pytest.fixture(scope="class")
    def all_cals(self):
        return _load_all_calibrations()

    @pytest.fixture(scope="class")
    def all_flat_keys(self, all_cals):
        """Union of all keys across all scenario calibration blocks."""
        keys: set[str] = set()
        for cal in all_cals:
            keys.update(cal.keys())
        return keys

    def test_all_fields_exercised(self, all_flat_keys):
        """Each top-level field is set in at least one scenario YAML."""
        # Fields exercised through flat YAML keys that get routed by the validator
        exercised = set(all_flat_keys)

        # Map flat keys to schema fields
        schema_fields_hit: set[str] = set()
        for key in exercised:
            # Direct field
            if key in CalibrationSchema.model_fields:
                schema_fields_hit.add(key)
            # Morale prefix
            if key in CalibrationSchema._MORALE_KEY_MAP:
                schema_fields_hit.add("morale")
            # Side-suffixed ({side}_field)
            for suffix in CalibrationSchema._SIDE_SUFFIX_FIELDS:
                if key.endswith(f"_{suffix}"):
                    schema_fields_hit.add("side_overrides")
                    break
            # Side-prefixed (field_{side})
            for prefix in CalibrationSchema._SIDE_PREFIX_FIELDS:
                if key.startswith(f"{prefix}_"):
                    schema_fields_hit.add("side_overrides")
                    break

        not_exercised = []
        for field_name in CalibrationSchema.model_fields:
            if field_name not in schema_fields_hit:
                not_exercised.append(field_name)

        # These fields may only be exercised in test fixtures, not scenario YAMLs
        # That's acceptable -- we just want to verify they're not completely dead
        if not_exercised:
            # Check test files too
            test_dir = PROJECT_ROOT / "tests"
            test_text = ""
            for p in test_dir.rglob("*.py"):
                try:
                    test_text += p.read_text(encoding="utf-8")
                except Exception:
                    pass
            still_missing = []
            for field in not_exercised:
                if field in _CONSUMED_BUT_UNEXERCISED_FIELDS:
                    continue
                # Check string literals and attribute access patterns
                if (
                    f'"{field}"' not in test_text
                    and f"'{field}'" not in test_text
                    and f".{field}" not in test_text
                    and f"{field}=" not in test_text
                ):
                    still_missing.append(field)
            assert not still_missing, (
                f"CalibrationSchema fields exercised by zero scenarios AND zero tests: "
                f"{still_missing}"
            )


class TestCalibrationIntegrity:
    """Schema integrity and backward compatibility."""

    def test_dead_key_list_minimal(self):
        """_DEAD_KEYS contains only known dead keys."""
        assert CalibrationSchema._DEAD_KEYS == {"advance_speed"}

    def test_schema_round_trip(self):
        """CalibrationSchema serializes and deserializes cleanly."""
        original = CalibrationSchema(
            hit_probability_modifier=1.5,
            destruction_threshold=0.6,
            morale=MoraleCalibration(base_degrade_rate=0.1),
            side_overrides={"blue": SideCalibration(cohesion=0.9)},
        )
        data = original.model_dump()
        restored = CalibrationSchema.model_validate(data)
        assert restored.hit_probability_modifier == 1.5
        assert restored.destruction_threshold == 0.6
        assert restored.morale.base_degrade_rate == 0.1
        assert restored.side_overrides["blue"].cohesion == 0.9

    def test_no_orphan_cal_get_keys(self):
        """No cal.get("key") call uses a key not in the schema."""
        import re

        all_keys: set[str] = set()

        # Collect all cal.get("key") from source
        pattern = re.compile(r'cal\.get\(\s*["\']([a-z_]+)["\']')
        for p in _all_py_files():
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for m in pattern.finditer(text):
                all_keys.add(m.group(1))

        # Also check _cal.get() pattern
        pattern2 = re.compile(r'_cal\.get\(\s*["\']([a-z_]+)["\']')
        for p in _all_py_files():
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for m in pattern2.finditer(text):
                all_keys.add(m.group(1))

        # Build set of valid keys
        valid_keys: set[str] = set(CalibrationSchema.model_fields.keys())
        valid_keys.update(CalibrationSchema._MORALE_KEY_MAP.keys())
        # Side-suffixed: {side}_{field}
        for suffix in CalibrationSchema._SIDE_SUFFIX_FIELDS:
            valid_keys.add(suffix)  # the suffix itself
            # common sides
            for side in ("blue", "red", "green", "orange"):
                valid_keys.add(f"{side}_{suffix}")
        # Side-prefixed: {field}_{side}
        for prefix in CalibrationSchema._SIDE_PREFIX_FIELDS:
            valid_keys.add(prefix)
            for side in ("blue", "red", "green", "orange"):
                valid_keys.add(f"{prefix}_{side}")
        # Dead keys are also valid (silently dropped)
        valid_keys.update(CalibrationSchema._DEAD_KEYS)

        orphans = all_keys - valid_keys
        assert not orphans, f"cal.get() calls with keys not in CalibrationSchema: {orphans}"

    def test_calibration_defaults_match_original(self):
        """Verify CalibrationSchema defaults match pre-schema hardcoded values."""
        defaults = CalibrationSchema()
        # battle.py hardcoded defaults (verified during Phase 49)
        assert defaults.hit_probability_modifier == 1.0
        assert defaults.target_size_modifier == 1.0
        assert defaults.thermal_contrast == 1.0
        assert defaults.destruction_threshold == 0.5
        assert defaults.disable_threshold == 0.3
        assert defaults.formation_spacing_m == 50.0
        assert defaults.morale_degrade_rate_modifier == 1.0
        assert defaults.dig_in_ticks == 30
        assert defaults.wave_interval_s == 300.0
        assert defaults.max_engagers_per_side == 0
        assert defaults.morale.base_degrade_rate == 0.05
        assert defaults.morale.base_recover_rate == 0.10
        assert defaults.morale.casualty_weight == 2.0
        assert defaults.morale.suppression_weight == 1.5

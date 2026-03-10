# Phase 49: Calibration Schema Hardening

## Summary

Replaced the free-form `calibration_overrides: dict[str, Any]` with a typed pydantic `CalibrationSchema` validated at parse time. All ~37 scenario YAMLs migrated from `calibration_overrides:` to `calibration_overrides:` with schema-validated keys. Dead `advance_speed` data removed from 7 historical scenarios. Previously-untested calibration paths (dig_in_ticks, wave_interval_s, target_selection_mode, victory_weights, morale config weights, roe_level) exercised in new test scenarios.

## What Was Built

### 49a: CalibrationSchema Pydantic Model
- **`stochastic_warfare/simulation/calibration.py`** (new) -- Typed `CalibrationSchema` pydantic model with ~60 known keys organized by subsystem. All fields have defaults matching previous hardcoded values. `.get()` method provides backward-compatible dict-like access.

### 49b: Scenario YAML Migration
- All ~37 scenario YAMLs validated against CalibrationSchema at parse time
- Dead `advance_speed` entries removed from 7 historical scenarios
- Calibration audit test updated to use schema-based validation

### 49c: Untested Calibration Path Exercise
- Test scenarios exercising dig_in_ticks, wave_interval_s, target_selection_mode, victory_weights, morale config weights, roe_level, EW params

## Design Decisions

1. **`.get()` method for backward compat**: CalibrationSchema provides `.get(key, default)` so existing `cal.get(...)` call sites work unchanged.
2. **Schema validates at parse time**: Invalid/mistyped keys cause pydantic `ValidationError` at scenario load, not silent pass-through.
3. **`advance_speed` removed, not wired**: Dead data with no Python consumer. Removed rather than inventing a use.

## Tests

51 new tests in `tests/unit/test_phase49_calibration_schema.py`:
- Schema loading, defaults, unknown key rejection
- Scenario YAML migration validation
- Calibration path exercise (dig_in_ticks, wave_interval_s, etc.)
- EW parameter configurability

## Deficits Resolved

- E1: `advance_speed` dead data (removed)
- E2: `dig_in_ticks` untested (exercised)
- E3: `wave_interval_s` untested (exercised)
- E4: `target_selection_mode` untested (exercised)
- E5: `roe_level` sparse coverage (expanded)
- E6: Morale config weights unused (exercised)
- E7: `victory_weights` untested (exercised)
- E10: Calibration audit false pass (fixed)
- Phase 48 deficit: `calibration_overrides` free-form dict (replaced with typed schema)

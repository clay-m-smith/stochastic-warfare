# Phase 11: Core Fidelity Fixes

## Summary

Phase 11 resolves 15 MAJOR and high-impact MODERATE deficits logged during MVP (Phases 0-10) through surgical modifications to ~20 existing source files. No new modules, no architectural changes, no new dependencies. All changes are backward-compatible with default parameters preserving MVP behavior.

**Test count**: 109 tests (9 + 42 + 35 + 23) across 4 test files. Total: 3,818 tests passing (up from 3,782).

## What Was Built

### 11d: AI Fidelity (2 changes, 9 tests)
1. **Echelon hardcode fix** (`decisions.py`): Changed `_decide_brigade_div()` from hardcoded `echelon_level=9` to accept and pass through actual echelon parameter. Brigade now correctly reports echelon=8.
2. **Tactical OODA acceleration** (`ooda.py`, `battle.py`): Added `tactical_acceleration: float = 0.5` to `OODAConfig` and `tactical_mult` parameter to `compute_phase_duration()`/`start_phase()`. Battle manager now advances OODA phases after completions and applies tactical multiplier. Designed as a stacking multiplier for Phase 19 doctrinal school modifiers.

### 11a: Combat Fidelity (5 changes, 36 tests)
1. **Fire rate limiting** (`ammunition.py`, `engagement.py`, `battle.py`): Added `_last_fire_time_s`, `_cooldown_s` (from `rate_of_fire_rpm`) to `WeaponInstance`. `can_fire_timed()`/`record_fire()` gate engagement execution. Cooldown gate in `execute_engagement()` returns `aborted_reason="cooldown"`.
2. **Per-side target_size_modifier** (`battle.py`): Changed from single `target_size_modifier` to per-side lookup via `target_size_modifier_{target_side}` with fallback to uniform value.
3. **Environment coupling** (`air_combat.py`, `air_defense.py`, `naval_surface.py`, `indirect_fire.py`): Added `weather_modifier`/`visibility_km` to air combat, `weather_modifier` to air defense, `sea_state` to naval surface, `wind_speed_mps`/`wind_direction_deg` to indirect fire. Severe weather aborts sorties, sea state degrades salvo exchange, crosswind inflates CEP.
4. **Mach-dependent drag** (`ballistics.py`): Added `_speed_of_sound()`, `_mach_drag_multiplier()` with piecewise regimes (subsonic=1.0, transonic rising to 2.0, supersonic falling). `enable_mach_drag` config flag preserves MVP behavior when False.
5. **Armor type + obliquity** (`damage.py`): Added `ArmorType` enum (RHA/COMPOSITE/REACTIVE/SPACED), `_ARMOR_EFFECTIVENESS` lookup table, ricochet at >75 degrees. `armor_type` parameter defaults to "RHA" for backward compatibility.

### 11b: Detection Fidelity (4 changes, 35 tests)
1. **Sensor FOV filtering** (`sensors.py`, `detection.py`): Added `boresight_offset_deg` to `SensorDefinition`. FOV check in `check_detection()` computes relative bearing from observer heading + boresight offset, filters targets outside FOV half-angle.
2. **Dwell/integration gain** (`detection.py`): Added `_scan_counts` dict tracking (sensor_id, target_id) scan count. SNR boosted by `5*log10(n_scans)`, capped at `max_integration_gain_db` (default 6.0 dB = 4 scans). `reset_scan_counts()` method. State persistence via `get_state()`/`set_state()`.
3. **Geometric sonar bearing** (`sonar.py`): Replaced `bearing = rng.uniform(0, 360)` placeholder with `atan2(dx, dy)` geometric bearing + SNR-dependent Gaussian noise. Both `passive_detection()` and `active_detection()` accept optional `observer_pos`/`target_pos` parameters. Falls back to random bearing when positions not provided.
4. **Mahalanobis gating** (`estimation.py`): Added Mahalanobis distance gate before Kalman update. Computes `d2 = y.T @ S_inv @ y` and rejects if `d2 > gating_threshold_chi2` (default 9.21 = 99% for 2 DOF). `update()` now returns `bool` (True=accepted, False=gated). `enable_gating` config flag.

### 11c: Movement & Logistics Fidelity (4 changes, 23 tests)
1. **Fuel gating** (`movement/engine.py`): Added `fuel_available: float = inf` parameter to `move_unit()`. Zero fuel prevents movement; partial fuel clamps distance to `fuel_available / fuel_rate`. Infantry (max_speed <= 5) unaffected (fuel_rate=0).
2. **Stochastic engineering times** (`logistics/engineering.py`): Added `duration_sigma: float = 0.0` to `EngineeringConfig`. When sigma > 0, `assess_task()` multiplies base duration by `rng.lognormal(0, sigma)`. Default 0.0 preserves MVP deterministic behavior.
3. **Wave attack modeling** (`simulation/battle.py`): Added `wave_assignments: dict[str, int]` and `battle_elapsed_s: float` to `BattleContext`. Wave 0 moves immediately, wave N waits N * wave_interval_s (from calibration, default 300s), wave -1 (reserve) never moves. State persisted.
4. **Stochastic reinforcement arrivals** (`simulation/scenario.py`, `simulation/campaign.py`): Added `arrival_sigma: float = 0.0` to `ReinforcementConfig`. Added `actual_arrival_time_s` to `ReinforcementEntry`, computed via `rng.lognormal(0, sigma)` at setup. `check_reinforcements()` uses actual time. State persisted.

## Design Decisions

1. **Backward compatibility**: All new parameters have defaults matching MVP behavior. `enable_*` config flags for Mach drag and Mahalanobis gating.
2. **DI pattern**: Environmental data passed as parameters (fuel_available, observer_heading_deg, weather_modifier), not imported.
3. **PRNG discipline**: All stochastic additions use `self._rng` (injected Generator).
4. **State protocol**: All new stateful fields included in `get_state()`/`set_state()`.
5. **No new modules or dependencies**: All changes modify existing files.

## Issues & Fixes

- **Existing estimation tests**: Two tests (`test_position_moves_toward_measurement`, `test_multiple_updates_converge`) used measurements far from predicted state that Mahalanobis gating correctly rejects. Fixed by increasing `pos_var` to ensure measurements are within the gate.
- **Integration test fire rate**: `test_multiple_engagements_consume_ammo` fired 5 shots at t=0 — blocked by cooldown after first shot. Fixed by spacing shots 60s apart via `current_time_s`.
- **Temperature/Mach interaction**: `test_cold_reduces_muzzle_velocity` inverted due to Mach-dependent drag interacting with temperature-dependent speed of sound. Fixed by disabling Mach drag in that test to isolate the MV-temperature relationship being tested.

## Known Limitations / Post-MVP Refinements

- **Fuel gating not wired to stockpile in battle.py**: The movement engine accepts `fuel_available` but battle.py does not yet query `ctx.stockpile_manager` for Class III. This wiring is deferred until Phase 12b logistics depth.
- **Wave assignments are manual**: No AI auto-assignment of units to waves. Phase 19 doctrinal AI may generate wave plans.
- **Integration gain caps at 4 scans**: Real radar integration may benefit from more scans. Current cap is conservative.
- **Armor type YAML data**: Existing unit definitions don't specify armor_type. Defaults to "RHA" everywhere.

## Lessons Learned

- **Mach-dependent drag affects temperature tests**: Adding Mach drag changes the relationship between temperature and range because speed of sound is temperature-dependent. Tests isolating MV-temperature effects need to disable Mach drag.
- **Mahalanobis gating threshold of 9.21 (99% for 2 DOF) is tight enough to reject measurements at 3-6 sigma**: This catches scenarios where measurement noise is very high relative to position uncertainty, which is physically correct.
- **Default parameter values matter for backward compatibility**: Setting `duration_sigma=0.2` broke existing deterministic tests. Changed to `0.0` with explicit opt-in.

## Retrospective Cleanup

Post-implementation retrospective identified 7 gaps (2 Medium, 5 Low). All resolved:

### Test Gaps Fixed
1. **Per-side `target_size_modifier` tests** (Medium, +4 tests): Added `TestPerSideTargetSizeModifier` class testing per-side lookup, fallback to uniform, both sides different, and default 1.0.
2. **Naval surface sea state assertion** (Medium): Replaced weak `isinstance(r_rough.hits, int)` with `assert r_rough.offensive_power < r_calm.offensive_power` and defensive_power comparison.
3. **SPACED armor type penetration tests** (Low, +2 tests): Added tests verifying SPACED vs KE (0.9 effectiveness, weaker than RHA) and SPACED vs HEAT (1.3 effectiveness, stronger than RHA).
4. **Conftest fixture migration** (Low): Migrated `test_phase_11b` and `test_phase_11c` from local `_rng()` helpers to shared `make_rng()` from conftest, per project conventions.

### Source Code Quality Fixes
5. **Public `tactical_acceleration` property** (Low): Added `@property` to `OODALoopEngine`. Updated `battle.py` to use `ctx.ooda_engine.tactical_acceleration` instead of accessing private `_config`.
6. **Explicit `air_temp_c` parameter** (Low): Replaced transient `self._current_air_temp_c` instance variable in `ballistics.py` with explicit `air_temp_c` parameter on `_drag_acceleration()`. Temperature now flows through the `derivs()` closure like other condition parameters.
7. **`reset_scan_counts()` wired to battle resolution** (Low): Added call to `DetectionEngine.reset_scan_counts()` in `engine.py` after `resolve_battle()` to prevent integration gain scan counts from bleeding across battles.

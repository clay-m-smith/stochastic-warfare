# Phase 62: Human Factors, CBRN, & Air Combat Environment

**Status**: Complete — 85 tests, 6 new test files, 5 modified source files.

**Goal**: Wire three categories of environmental effects that are computed but never consumed by the simulation loop: human factors (heat/cold/MOPP/altitude), CBRN-environment interaction (rain washout, Arrhenius decay, inversion trapping, UV degradation), and air combat environment (cloud ceiling, icing, density altitude, wind BVR, energy advantage).

**Dependencies**: Phase 61 complete (Maritime, Acoustic, & EM Environment).

## Summary of Changes

### Step 0: CalibrationSchema Infrastructure

3 new enable flags + ~17 rate/factor params added to `CalibrationSchema`:
- `enable_human_factors` — gates heat/cold casualties, expanded MOPP penalties, altitude sickness
- `enable_cbrn_environment` — gates weather-dependent puff decay/amplification
- `enable_air_combat_environment` — gates cloud ceiling, icing, density, wind BVR, energy advantage

All flags default `False` for backward compatibility.

### Step 62a: Heat & Cold Casualties

Two helper functions + environmental casualty block in `execute_tick()`:
- `_compute_wbgt(temperature_c, humidity)` — simplified Wet Bulb Globe Temperature
- `_compute_wind_chill(temperature_c, wind_speed_mps)` — NWS wind chill formula
- Heat stress: WBGT > 28°C → fractional casualties per hour, scaled by MOPP level (3× at MOPP-4) and exertion (1.5× if moving)
- Cold injury: wind chill < -20°C → fractional casualties per hour
- Fractional accumulator dict (`_env_casualty_accum`) on BattleManager carries sub-integer casualties between ticks
- Environmental casualties reduce personnel without triggering morale combat-casualty effects

### Step 62b: MOPP Degradation & Altitude

Expanded MOPP penalties beyond existing detection/speed factors:
- **FOV reduction**: MOPP-4 → detection range × 0.7 (linearly interpolated for MOPP-2 → 0.85)
- **Reload factor**: MOPP-4 → crew_skill ÷ 1.5 (MOPP-2 → ÷ 1.25)
- **Comms degradation**: MOPP-4 → C2 effectiveness × 0.5 (wired into `_compute_c2_effectiveness`)

Altitude sickness:
- Above `altitude_sickness_threshold_m` (2500m): performance degrades at `altitude_sickness_rate` per 100m
- Floor at 50% performance
- `acclimatized` flag on unit halves the penalty
- Applied to both detection range and crew_skill

### Step 62c: CBRN-Environment Interaction

New `DispersalEngine.apply_weather_effects()` method with four physics:
1. **Rain washout**: `mass *= exp(-coeff × precip_rate × dt)` — exponential mass removal
2. **Arrhenius thermal decay**: `k = exp(-Ea/(R·T_K)); mass *= exp(-k × dt)` — temperature-dependent chemical breakdown
3. **Inversion trapping**: stability class E/F → concentration amplification (capped per-tick factor)
4. **UV photo-degradation**: clear daytime (cloud_cover < 0.5) → `mass *= exp(-uv_rate × dt/3600)`

Wired in `CBRNEngine.update()` via keyword-only params. `SimulationEngine` forwards calibration params from `CalibrationSchema`.

### Step 62d: Air Combat Environmental Coupling

Modified `_route_air_engagement()` with 5 environmental effects:
1. **Cloud ceiling gate**: unguided CAS aborted below `cloud_ceiling_min_attack_m` (500m); PGM proceeds
2. **Icing penalties**: icing_risk > 0.5 → missile Pk × (1 - icing_maneuver_penalty), CAS Pk × (1 - icing_power_penalty)
3. **Density altitude**: reduced air density → `missile_pk × min(1, ρ/1.225)`
4. **Wind → BVR range**: wind component along heading modifies effective engagement range
5. **Energy advantage**: `EnergyState` objects passed to `resolve_air_engagement()` for E-M modifier
6. **Icing radar penalty**: icing_risk > 0.5 → radar detection range reduced by `icing_radar_penalty_db` (R^4 equation)

## Files Modified (5)

| File | Changes |
|------|---------|
| `stochastic_warfare/simulation/calibration.py` | 3 enable flags + ~17 rate/factor params |
| `stochastic_warfare/simulation/battle.py` | 2 helper functions, env casualty block, MOPP expansion, altitude sickness, air combat env coupling, icing radar penalty |
| `stochastic_warfare/cbrn/dispersal.py` | 1 new method: `apply_weather_effects()` |
| `stochastic_warfare/cbrn/engine.py` | Extended `update()` with CBRN environment keyword params |
| `stochastic_warfare/simulation/engine.py` | Forward CBRN calibration params to `cbrn_engine.update()` |

## New Test Files (6)

| File | Tests |
|------|-------|
| `tests/unit/test_phase_62_infra.py` | 11 |
| `tests/unit/test_phase_62a_heat_cold.py` | 18 |
| `tests/unit/test_phase_62b_mopp_altitude.py` | 14 |
| `tests/unit/test_phase_62c_cbrn_weather.py` | 10 |
| `tests/unit/test_phase_62d_air_combat_env.py` | 15 |
| `tests/unit/test_phase_62_structural.py` | 17 |

## Deferrals (Planned → Deferred)

1. **Dehydration/water consumption** — logistics concern, needs water supply tracking
2. **Environmental fatigue acceleration** — FatigueManager already has altitude support; temperature-driven fatigue needs fatigue accumulation wiring beyond current scope
3. **MOPP comms → C2 effectiveness chain** — MOPP degrades voice clarity; full chain (comms quality → C2 effectiveness → order execution) deferred to Phase 63
4. **Turbulence → gun accuracy** — no turbulence model in WeatherEngine
5. **Wind shear (altitude-dependent wind)** — wind constant at all altitudes; needs new model
6. **Surface roughness → CBRN mixing height** — would need per-terrain roughness data

## Lessons Learned

- Calibration coverage test (`test_all_fields_have_consumers`) is an excellent regression catch: immediately flagged `icing_radar_penalty_db` as unconsumed before it could become a dead parameter.
- Inversion trapping must be per-tick-limited (not a one-time multiplier) to prevent unbounded mass growth — cap factor at `inversion_multiplier` per application.
- MOPP effects compound: existing detection_factor (Phase 44b) + new FOV reduction (Phase 62b) + new reload factor (Phase 62b) — each layer is independently gated by `enable_human_factors` to prevent double-penalizing when the flag is off.
- The `_route_air_engagement` function is now the largest routing function — cloud ceiling, icing, density, wind, and energy are all per-engagement checks. Future optimization could precompute environmental factors once per tick.

## Postmortem

### 1. Delivered vs Planned

**Scope: On target / slightly over.**

Plan called for ~59 tests across 6 test files. Delivered 85 tests across 6 files — the overshoot is additional edge-case coverage and structural assertions, not scope creep. All planned features delivered:

| Planned | Delivered | Notes |
|---------|-----------|-------|
| 62a heat/cold casualties | Yes | WBGT, wind chill, fractional accumulator, MOPP heat multiplier |
| 62b MOPP expansion + altitude | Yes | FOV, reload, comms, altitude sickness with acclimatization |
| 62c CBRN-environment interaction | Yes | Rain washout, Arrhenius, inversion, UV — all 4 physics |
| 62d Air combat environment | Yes | Cloud ceiling, icing (maneuver+power+radar), density, wind BVR, energy |
| CalibrationSchema infrastructure | Yes | 3 flags + 17 params |

**Dropped**: Environmental fatigue acceleration (planned in 62b) — FatigueManager temperature wiring needs accumulation plumbing beyond scope. Logged as deferral.

**Unplanned additions**: `icing_radar_penalty_db` consumption in detection section (caught by calibration coverage test — was a gap in the original plan).

### 2. Integration Audit

**Fully wired — zero gaps.**

- `apply_weather_effects()` called from `CBRNEngine.update()` with all calibration params forwarded
- `_compute_wbgt()` / `_compute_wind_chill()` called in `execute_tick()` heat/cold block
- All 3 enable flags read from `CalibrationSchema` and gated correctly in battle.py/engine.py
- `_env_casualty_accum` initialized in `__init__`, accumulated per-tick, integer conversion when ≥1.0
- `EnergyState` imported and used in `_route_air_engagement()` for altitude advantage
- All 19 CalibrationSchema params consumed (verified by `test_all_fields_have_consumers`)
- `engine.py` forwards CBRN params via `**_cbrn_kw` dict pattern

No orphaned code. No dead imports. No unreachable paths.

### 3. Test Quality Review

**Quality: High.**

- 85 tests across 6 files (0.63s total runtime — fast)
- Edge cases well-covered: boundary thresholds (28°C heat, -20°C cold), zero-rate cases, MOPP interpolation at 0/2/4, altitude floor at 50%, compound CBRN effects
- Realistic data: actual temperature ranges, Arrhenius activation energy, ISA air density
- Helpers are private (`_compute_wbgt`, `_compute_wind_chill`) — tests validate behavior not implementation
- Structural tests (17) catch regressions fast without scenario runs
- No `@pytest.mark.slow` needed — all tests under 1s

**Gap**: No EnergyState integration test (tests verify helper logic but not the full battle loop path with real AirCombatEngine). Acceptable — EnergyState is tested in Phase 4/58 air combat tests.

### 4. API Surface Check

- `apply_weather_effects()`: Full type hints, keyword-only params via `*`, return type annotated ✓
- `_compute_wbgt()` / `_compute_wind_chill()`: Private prefix, full type hints ✓
- No bare `print()` — uses `get_logger(__name__)` ✓
- No unintended public API additions
- `CBRNEngine.update()` extension: keyword-only params preserve backward compat ✓

### 5. Deficit Discovery

**No TODOs/FIXMEs/HACKs** in Phase 62 code.

**2 hardcoded values** found that should be configurable:
1. MOPP heat trap multiplier (`0.5 per MOPP level`, battle.py ~line 1279) — not in CalibrationSchema
2. Exertion multiplier (`1.5×` for moving units, battle.py ~line 1285) — not in CalibrationSchema

Both are reasonable defaults and low-severity. Logged as accepted limitations — the primary calibration levers (base rates, MOPP factors) already exist. Adding per-tick micro-parameters would bloat the schema for minimal return.

**6 deferrals** already logged in devlog and `devlog/index.md`:
- Dehydration/water consumption
- Environmental fatigue acceleration
- MOPP comms → C2 chain
- Turbulence → gun accuracy
- Wind shear (altitude-dependent wind)
- Surface roughness → CBRN mixing height

### 6. Documentation Freshness

- CLAUDE.md: Phase 62 summary in Block 7 table ✓
- README.md: Test count updated ✓
- docs/index.md: Test count + phase badge updated ✓
- mkdocs.yml: Phase 62 devlog entry added ✓
- devlog/index.md: Phase 62 entry + 6 deferrals added ✓
- development-phases-block7.md: Status ✓ ✓
- MEMORY.md: Current status + Phase 62 lessons ✓
- docs/reference/api.md: Not applicable (no new public API classes)
- docs/concepts/architecture.md: Not applicable (no new modules)

### 7. Performance Sanity

- Phase 62 tests: 85 tests in 0.63s (fast — all unit-level, no scenario runs)
- No performance regression expected — all effects gated by `enable_*=False` defaults
- `_route_air_engagement()` adds 5 per-engagement checks when enabled; negligible cost vs engagement resolution

### 8. Summary

- **Scope**: On target (85 tests vs 59 planned — extra coverage, not scope creep)
- **Quality**: High — clean API, full type hints, realistic test data, edge cases covered
- **Integration**: Fully wired — zero gaps, all CalibrationSchema params consumed
- **Deficits**: 2 minor hardcoded values (accepted limitations), 6 planned deferrals
- **Action items**: None — ready to commit

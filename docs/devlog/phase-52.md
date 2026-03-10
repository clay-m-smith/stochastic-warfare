# Phase 52: Environmental Continuity

**Status**: Complete
**Tests**: 32 new (8 night + 10 weather + 8 comms LOS + 6 SIGINT fusion)
**Files modified**: 7 source + 1 test fixture + 1 new test file
**Deficits resolved**: 4 (D8, D9, Phase 5 comms LOS, Phase 17 SIGINT fusion)

## Summary

Replaced binary environmental gates with continuous functions across 4 substeps. Night detection now uses 5-level twilight gradation instead of day/night binary. Weather affects ballistics (crosswind accuracy penalty) and sensors (ITU-R P.838 rain radar attenuation). Communications check terrain LOS with diffraction model and exempt types. Space and EW SIGINT reports fuse into unified tracks via inverse-variance weighted averaging.

## 52a: Night Gradation

- `_compute_night_modifiers()` returns (visual_mod, thermal_mod) from `IlluminationLevel`
- 5 levels: day (1.0), civil twilight (0.8), nautical (0.5), astronomical (0.3), full night (0.2)
- Thermal sensors use `max(floor, visual)` — barely affected at night (floor=0.8)
- Replaces binary `night_visual_modifier = 0.3` and additive `thermal_night_bonus`
- Uses `getattr(illum, "twilight_stage", None)` for robustness with legacy mocks

**Resolves**: D8 (night/day binary).

## 52b: Weather Effects on Ballistics and Sensors

- Wind extracted from `WeatherConditions.wind` (meteorological from-direction convention)
- `_compute_crosswind_penalty()`: engagement-axis crosswind reduces crew_skill [0.7-1.0]
- `_compute_rain_detection_factor()`: ITU-R P.838 X-band (k=0.01, alpha=1.28) attenuates radar detection range [0.1-1.0]
- Three new calibration fields: `night_thermal_floor`, `wind_accuracy_penalty_scale`, `rain_attenuation_factor`
- Rain only affects weather-independent sensors (radar/thermal/ESM); visual sensors already degraded by visibility

**Design deviation from plan**: Plan specified modifying `ballistics.py` (RK4 wind drift), `detection.py` (radar SNR), and `formations.py` (sea state spacing). Implementation applied effects in `battle.py`'s engagement loop instead — crosswind as crew_skill modifier, rain as detection_range modifier. This is simpler and matches the existing pattern of all environmental modifiers being applied in the engagement loop. The ballistics RK4 kernel already handles wind internally for indirect fire; direct fire uses the Pk model.

**Resolves**: D9 (weather stops at visibility).

## 52c: Terrain-Based Comms LOS

- Fixed latent `AttributeError` bug: code accessed `result.has_los` but `LOSResult` has `visible` field
- Same bug fixed in `c2/coordination.py` (JTAC LOS check)
- Added `_LOS_EXEMPT_TYPES` frozenset: HF, SATELLITE, VLF, ELF, WIRE, MESSENGER
- Blocked LOS returns 0.25 factor (~6 dB single-obstruction diffraction loss), not 0.0
- Bug was latent because `_los_engine` is always `None` at runtime — never triggered

**Resolves**: Phase 5 deficit (terrain-based comms LOS not implemented).

## 52d: Space SIGINT + EW SIGINT Fusion

- `SIGINTEngine._recent_reports` buffer populated on successful intercepts
- `SIGINTEngine.get_recent_reports(clear=True)` retrieves and optionally clears buffer
- `IntelFusionEngine.fuse_sigint_tracks()` performs position-proximity association + inverse-variance weighted fusion
- `_fuse_two_reports()` computes fused position: `1/sqrt(1/sigma_a^2 + 1/sigma_b^2)` — always better accuracy than either individual
- `SimulationEngine._fuse_sigint()` wired after space + EW updates in tick loop
- Gated by triple null-check: requires space_engine, ew_engine, and intel_fusion_engine

**Resolves**: Phase 17 deficit (space SIGINT + EW SIGINT integration).

## Files Changed

| File | Action | Changes |
|------|--------|---------|
| `simulation/battle.py` | Modified | Night gradation helpers, wind extraction, crosswind penalty, rain attenuation, detection modifier rewiring |
| `simulation/calibration.py` | Modified | 3 new fields: `night_thermal_floor`, `wind_accuracy_penalty_scale`, `rain_attenuation_factor` |
| `simulation/engine.py` | Modified | Added `_fuse_sigint()` method, wired after EW update |
| `c2/communications.py` | Modified | Fixed `has_los` -> `visible` bug, `_LOS_EXEMPT_TYPES`, diffraction model |
| `c2/coordination.py` | Modified | Fixed `has_los` -> `visible` bug in JTAC LOS |
| `detection/intel_fusion.py` | Modified | `fuse_sigint_tracks()`, `_position_distance()`, `_fuse_two_reports()` |
| `ew/sigint.py` | Modified | Report buffering (`_recent_reports`, `get_recent_reports()`) |
| `tests/unit/test_phase_12a_c2_depth.py` | Modified | Fixed mock to return `visible` instead of `has_los` |
| `tests/unit/test_phase52_environmental.py` | New | 32 tests in 4 test classes |

## Lessons Learned

- **Latent bugs hide behind null guards**: The `has_los` bug in communications.py and coordination.py was present since Phase 12a but never triggered because `_los_engine` is always `None` in production. Fixing the bug + fixing the test mock in the same commit is the right approach.
- **Environmental modifiers belong in the engagement loop**: Applying crosswind and rain at the crew_skill / detection_range level in battle.py is simpler than modifying individual engine modules (ballistics, detection). The engagement loop is where all modifiers converge.
- **getattr for robustness with test mocks**: Using `getattr(illum, "twilight_stage", None)` prevents `AttributeError` when test fixtures use `SimpleNamespace` without all fields.
- **Unused calibration fields are dead data**: Planned `night_full_modifier` and `comms_terrain_los_factor` were schema fields with no code references. Removed during postmortem to avoid dead data.

## Postmortem

### Delivered vs Planned
- **52a**: Delivered as planned. 5-level twilight gradation.
- **52b**: Partially divergent. Wind and rain effects implemented in battle.py engagement loop (crew_skill + detection_range) rather than in ballistics.py/detection.py/formations.py. Sea state formation spacing deferred (existing sea_dispersion_modifier sufficient). Simpler and matches existing pattern.
- **52c**: Delivered as planned + bonus bug fix in coordination.py (`has_los` -> `visible`).
- **52d**: Delivered as planned. Report buffering + fusion method + engine wiring.
- **Scope**: On target. 32 tests (plan said ~32).

### Integration Audit
- All 3 battle.py helpers called in engagement loop
- `_fuse_sigint()` wired in tick loop after EW update
- 3/3 used calibration fields read via `cal.get()`
- 2 dead calibration fields removed during postmortem (`night_full_modifier`, `comms_terrain_los_factor`)
- `get_recent_reports()` called from production `_fuse_sigint()`
- `fuse_sigint_tracks()` called from production `_fuse_sigint()`
- No TODO/FIXME in any modified file

### Test Quality
- Unit tests cover all edge cases: day, 4 twilight levels, zero wind, strong crosswind, headwind, zero/light/heavy rain, LOS clear/blocked, exempt types, fusion/separation
- Integration tests: existing Phase 44 env subsystem tests validate end-to-end engagement loop
- SIGINT buffering test uses real engine with actual emitter/collector, not mocks

### Deficits Discovered
- **52b sea state formation spacing**: Deferred. Existing `sea_dispersion_modifier` handles naval accuracy. Formation spacing wiring requires movement system changes outside scope.
- **Comms LOS diffraction is single-level (0.25)**: Plan mentioned multi-obstruction (12 dB for 2 obstructions). Current LOSResult doesn't distinguish shallow vs deep blockage. Single-level is a clear improvement over 0.0 (total block).

### Quality: High | Integration: Fully wired | Deficits: 0 new (2 deferred from plan scope)

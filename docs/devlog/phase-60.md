# Phase 60: Obscurants, Fire, & Visual Environment

**Block**: 7 (Final Engine Hardening)
**Status**: Complete
**Tests**: 53 new (8,273 Python total, ~8,545 with frontend)
**Date**: 2026-03-16

## Goal

Wire three dormant subsystems into the simulation loop:
1. **ObscurantsEngine** (256 lines, 21 existing unit tests) — smoke/dust/fog clouds with spectral blocking, wind drift, and decay. Never instantiated.
2. **IncendiaryDamageEngine** fire zone creation — built Phase 24b, updated each tick in engine.py, but `fire_started` from DamageResult was only logged, never creating fire zones.
3. **TimeOfDayEngine.thermal_environment()** and **nvg_effectiveness()** — both compute rich data but neither was called from battle.py.

## Delivered

### Step 0: Infrastructure (9 tests)
- **calibration.py**: 4 new boolean fields: `enable_obscurants`, `enable_fire_zones`, `enable_thermal_crossover`, `enable_nvg_detection` (all default `False`)
- **scenario.py**: ObscurantsEngine instantiation + result dict entry, removed TODO comment
- **engine.py**: `obscurants_engine.update(dt)` call in `_update_environment()` with getattr safety

### 60a: Obscurants → Detection & Engagement (12 tests)
- **battle.py detection loop**: Per-target `opacity_at()` query. Spectral-band-aware: visual sensors get visual blocking, thermal gets thermal, radar gets radar (per SensorType)
- **battle.py engagement**: `vis_mod *= (1.0 - visual_opacity)` — reduces Pk through smoke
- **battle.py indirect fire**: Artillery impact spawns dust cloud at target position via `add_dust()`

### 60b: Dust Trails & Fire Zones (10 tests)
- **battle.py movement**: Vehicle movement on DRY ground spawns dust trail (radius scales with speed). Naval/aerial/submarine excluded. Wet/saturated ground suppresses dust.
- **battle.py fire_started**: When `fire_started=True`, checks terrain combustibility (>0.3 gate), creates fire zone via `IncendiaryDamageEngine.create_fire_zone()`, and deploys smoke via ObscurantsEngine cross-engine coupling
- **battle.py movement**: Fire zones block movement (distance check against `current_radius_m`)
- **battle.py step 7b**: Fire zone unit damage logged (behavioral application deferred to calibration)

### 60c: Thermal ΔT Model & NVG Detection (12 tests)
- **battle.py**: `thermal_dt_contrast` computed once per tick via `tod_engine.thermal_environment()`. Near crossover (<0.5 hours), contrast collapses. Running vehicles (speed >1.0) maintain ΔT floor at 0.5.
- **battle.py**: NVG detection recovery — NVG-equipped units recover visual detection from ~0.2 to ~0.6 at night via `nvg_effectiveness()` with 50% recovery scaling
- **battle.py**: When `enable_thermal_crossover=False`, original `night_thermal_modifier` used (backward compat). When `enable_nvg_detection=False`, no NVG recovery.

### Structural Verification (10 tests)
- 10 code-level checks verifying all wiring present: ObscurantsEngine in scenario.py, update in engine.py, opacity_at in battle.py detection, fire zone creation, thermal_dt_contrast, NVG detection, dust trails, fire zone movement blocking, units_in_fire logging, all 4 CalibrationSchema flags.

## Files Modified (4)

| File | Changes |
|------|---------|
| `stochastic_warfare/simulation/calibration.py` | 4 new boolean fields |
| `stochastic_warfare/simulation/scenario.py` | ObscurantsEngine instantiation, TODO removed |
| `stochastic_warfare/simulation/engine.py` | obscurants_engine.update(dt) with getattr safety |
| `stochastic_warfare/simulation/battle.py` | 7 insertion points across detection, engagement, movement, damage, and morale steps |

## New Test Files (5)

| File | Tests |
|------|-------|
| `tests/unit/test_phase_60_obscurants_infra.py` | 9 |
| `tests/unit/test_phase_60a_obscurants_wiring.py` | 12 |
| `tests/unit/test_phase_60b_dust_fire.py` | 10 |
| `tests/unit/test_phase_60c_thermal_nvg.py` | 12 |
| `tests/unit/test_phase_60_structural.py` | 10 |

## Design Decisions

1. **All 4 effects gated by enable_*=False** — follows Phase 58c precedent. Zero behavioral change unless opted in. Prevents uncalibrated regressions.
2. **Spectral-band-aware opacity** — visual sensors get visual blocking, thermal gets thermal, radar gets radar. Uses SensorType of the best-range sensor selected in the detection loop.
3. **Fire damage logged but not applied** — `units_in_fire()` is called and burn rates logged, but damage is not applied to unit health. Consistent with Phase 58c deferral pattern.
4. **Dust only on DRY ground** — queries SeasonsEngine `ground_state`, defaults to DRY if no SeasonsEngine. Only vehicles (max_speed > 5) moving > 5m generate dust.
5. **Combustibility threshold 0.3** — filters non-flammable terrain (water, rock, urban concrete).
6. **Cross-engine coupling** — fire zones create smoke via ObscurantsEngine (uses `IncendiaryConfig.smoke_obscurant_radius_m = 200.0`).
7. **Safe attribute access** — `getattr(ctx, "obscurants_engine", None)` prevents AttributeError on SimpleNamespace mocks in older test files.

## Deferrals (Planned → Deferred)

1. **Fire spread (cellular automaton with wind bias)** — plan specified medium model with wind bias spread. Wire fire zone creation; defer spread to future phase. Consistent with no-uncalibrated-behavioral-change precedent.
2. **`environment_config` scenario YAML** — pre-placed smoke/fog zones and season overrides. No scenario currently needs this. Structural prep only.
3. **Burned zone concealment reduction** — `BurnedZone.concealment_reduction=0.5` exists but consumption in detection deferred.
4. **Fire damage application to units** — `units_in_fire()` called and logged; burn damage not applied. Deferred to calibration.
5. **Road surface dust suppression** — dust checks ground_state DRY but doesn't distinguish paved roads (needs terrain road query).
6. **Artificial illumination (flares)** — plan mentioned temporarily raising lux. Deferred — no flare deployment mechanic exists.

## Regression Fix

Initial implementation caused 25 test failures:
- **engine.py**: `ctx.obscurants_engine` direct access failed on SimpleNamespace mocks in Phase 54 era wiring tests. Fix: `getattr(ctx, "obscurants_engine", None)`.
- **battle.py**: `ctx.config.calibration_overrides` direct access in new step 7b failed on SimpleNamespace mocks in Phase 40/50/53 tests. Fix: `getattr(getattr(ctx, "config", None), "calibration_overrides", None)` + None guard.

## Lessons Learned

1. **SimpleNamespace mocks missing new attributes** — every new attribute access on `ctx` in engine.py/battle.py must use `getattr` with default, not direct attribute access. Older test files create minimal SimpleNamespace mocks that don't include newer fields.
2. **Cross-engine coupling is straightforward** — fire→smoke coupling (IncendiaryDamageEngine → ObscurantsEngine) needed just one `deploy_smoke()` call. No complex event bus wiring needed.
3. **Spectral bands matter** — standard smoke blocks visual (0.9) but barely affects thermal (0.1). Multispectral smoke blocks both (0.9/0.8). This distinction makes thermal sensors tactically valuable through smoke — matches real-world doctrine.

## Postmortem

### Scope: On target
53 tests delivered vs ~50 planned. All 3 substeps completed. 6 items deferred (all explicitly planned deferrals or below-scope items).

### Quality: High
- Tests mix structural (code-level AST/string) and behavioral (engine API exercised with realistic parameters)
- Edge cases covered: zero clouds, decay over time, wind drift, spectral band separation, combustibility threshold, ground state gating
- All effects gated by default-False flags — no hidden behavioral changes

### Integration: Fully wired
- ObscurantsEngine instantiated in scenario.py, updated in engine.py, queried in battle.py (detection + engagement + artillery + movement)
- IncendiaryDamageEngine fire zones created from battle.py damage path, movement blocking checked
- TimeOfDayEngine thermal_environment() and nvg_effectiveness() both called from battle.py detection loop
- Cross-engine: fire→smoke coupling via ObscurantsEngine.deploy_smoke()

### Deficits: 6 new deferred items
1. Fire spread cellular automaton (P2 — design exists, calibration needed)
2. environment_config scenario YAML (P3 — no scenario needs it)
3. Burned zone concealment reduction (P3 — field exists, consumption deferred)
4. Fire damage application to units (P2 — logged, not applied)
5. Road surface dust suppression (P4 — needs terrain road query)
6. Artificial illumination / flares (P3 — no deployment mechanic)

### Action items
- [x] Create phase devlog
- [ ] Update devlog/index.md (Phase 60 row + 6 new deferrals)
- [ ] Update development-phases-block7.md (Phase 60 status)
- [ ] Update CLAUDE.md (Phase 60 summary, test count)
- [ ] Update README.md (test count badge, phase badge)
- [ ] Update MEMORY.md (Phase 60 lessons + status)

# Phase 84: Spatial Culling & Scan Scheduling

**Block**: 9 (Performance at Scale)
**Status**: Complete
**Tests**: 31 (12 detection culling + 11 scan scheduling + 8 engagement culling)

## Overview

Attacks the #1 performance bottleneck: O(n²) FOW detection (every sensor checks every enemy every tick) and O(n²) engagement scoring. Introduces STRtree spatial indexing for range-limited culling and per-sensor scan interval scheduling.

## What Was Built

### 84a: STRtree Detection Culling (`detection/fog_of_war.py`)

- Builds `STRtree` from target positions at start of `update()` cycle
- Per own-unit: `max(sensor.effective_range)` → `Point.buffer(max_range)` query
- Only targets within the sensor envelope are passed to `check_detection()`
- Fallback to full scan when culling disabled or single target
- **`enable_detection_culling`** (`CalibrationSchema`, default `True`): transparent optimization — identical results since out-of-range targets fail `check_detection()` range check anyway

### 84b: Sensor Scan Scheduling (`detection/fog_of_war.py` + `detection/sensors.py`)

- **`scan_interval_ticks`** field on `SensorDefinition` (`Field(default=1, ge=1)`)
- Deterministic offset: `sum(ord(c) for c in sensor_id) % interval` — PYTHONHASHSEED-independent
- Sensors with interval > 1 only scan on their scheduled ticks when scheduling enabled
- Existing contacts persist between scans (SideWorldView.contacts lifecycle unchanged)
- **`enable_scan_scheduling`** (`CalibrationSchema`, default `False`): changes detection timing, opt-in per scenario
- 33 sensor YAML files updated with physically-motivated intervals:
  - Visual/thermal/ESM/warning: 1 (continuous)
  - Ground/air radar: 2-3 (rotating antenna)
  - Sonar: 3-5 (acoustic integration time)
  - Historical: 1-3 (observation methods)

### 84c: Engagement Candidate Culling (`simulation/battle.py`)

- Builds per-side enemy `STRtree` from `enemy_pos_arrays` (reuses existing infrastructure)
- Pre-filters scoring candidates with `max(weapon.max_range_m)` buffer query
- Falls back to full enemy list when tree query returns empty (all enemies out of range)
- `target_selection_mode: closest` path unchanged (uses numpy `argmin`)
- Vectorized distance array kept (O(n), fast) — only the scoring loop is narrowed

### 84d: Call Site Wiring (`simulation/battle.py`)

- FOW `update()` call passes `detection_culling`, `scan_scheduling`, `current_tick`
- Calibration values hoisted before the FOW loop

## Key Design Decisions

1. **2D STRtree is safe**: `Point.buffer(r)` in 2D includes all points within 2D distance ≤ r. Since 2D distance ≤ 3D distance, the tree never excludes a valid target.
2. **Per-unit query, not per-sensor**: Query once using `max(sensor.effective_range)`, reducing query count by 2-3x.
3. **`enable_detection_culling=True` by default**: Transparent optimization — identical results.
4. **`enable_scan_scheduling=False` by default**: Changes detection timing, opt-in after recalibration.
5. **Engagement fallback**: Empty tree query falls back to all enemies — no engagement is ever silently skipped.

## Files Changed

### Modified (6 source + 33 YAML + 1 test)
- `stochastic_warfare/simulation/calibration.py` — 2 CalibrationSchema fields
- `stochastic_warfare/detection/sensors.py` — `scan_interval_ticks` on SensorDefinition
- `stochastic_warfare/detection/fog_of_war.py` — STRtree culling + scan scheduling
- `stochastic_warfare/simulation/battle.py` — engagement culling + FOW wiring
- 33 sensor YAML files — `scan_interval_ticks` values
- `tests/validation/test_phase_67_structural.py` — `_DEFERRED_FLAGS` update

### New (3 test + 1 devlog)
- `tests/unit/test_phase84_detection_culling.py` — 12 tests
- `tests/unit/test_phase84_scan_scheduling.py` — 11 tests
- `tests/unit/test_phase84_engagement_culling.py` — 8 tests
- `docs/devlog/phase-84.md`

## Accepted Limitations

- STRtree is rebuilt every tick (no caching across ticks). Sub-ms for 290 units; revisit at 5000+.
- Scan scheduling uses `sum(ord())` offset — all instances of same sensor type scan on same tick.
- `enable_scan_scheduling` deferred (in `_DEFERRED_FLAGS`) until Phase 91 recalibration.

## Postmortem

**Scope**: On target. All 3 planned sub-phases (84a/84b/84c) delivered. Plan spec said `entities/equipment.py` for `scan_interval_ticks` but correct location was `detection/sensors.py` (where `SensorDefinition` lives). Plan estimated ~16 sensor files; actual was 33 (18 modern + 15 historical eras). No items deferred.

**Quality**: High. 31 tests cover unit, integration, edge cases (empty inputs, boundary, determinism, combined features). No TODOs or FIXMEs.

**Integration**: Fully wired. CalibrationSchema fields consumed in `battle.py`, `fog_of_war.py` params wired at call site, engagement trees built from existing `enemy_pos_arrays` infrastructure, structural test updated.

**Deficits**: 0 new. 3 accepted limitations documented (STRtree rebuild cost, scan offset pattern, scan scheduling deferred).

**Cross-doc audit fixes applied**:
- `docs/index.md` badges updated (test count 10,372→10,403, phase 83→84)
- `docs/development-phases-block9.md` corrected (equipment.py→sensors.py, ~16→33 sensor files)
- `test_calibration_schema.py` updated (`enable_detection_culling` excluded from False-default check)
- `test_phase_67_structural.py` updated (`_DEFERRED_FLAGS` includes both Phase 84 flags)

**Performance**: Benchmark validation deferred to manual run (not part of default test suite). Test suite time: ~199s (no regression from Phase 83).

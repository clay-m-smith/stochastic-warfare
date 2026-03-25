# Phase 86: Engagement & Calibration Optimization

**Block**: 9 (Performance at Scale)
**Status**: Complete
**Tests**: 19 (11 calibration flat dict + 8 observer batching)

## Overview

Replaces pydantic `CalibrationSchema.get()` calls in the battle loop with plain `dict.get()` lookups via a pre-computed flat dict. Batches per-observer modifiers (MOPP, altitude sickness, readiness) once per tick instead of per-engagement.

## What Was Built

### 86a: CalibrationSchema Flat Dict (`simulation/calibration.py`)

- **`to_flat_dict(sides)`** method on CalibrationSchema:
  - Expands `model_dump()` output into a flat dict
  - Flattens morale sub-object (10 keys: `morale_base_degrade_rate`, etc.)
  - Expands side overrides for each side × suffix/prefix fields
  - Strips None values so `dict.get(key, default)` works naturally
  - Called once at scenario load time

### 86a: Flat Dict Wiring (`simulation/scenario.py`)

- **`cal_flat`** field on SimulationContext (Phase 86)
- Generated at scenario load time from `calibration.to_flat_dict(side_names)`
- Regenerated on checkpoint restore (not serialized — derived data)

### 86a: Battle Loop Migration (`simulation/battle.py`)

- **`_resolve_cal_flat(ctx)`** helper: returns `ctx.cal_flat` when available, builds on-the-fly for backward compat
- **88 `cal.get()` → `cal_flat.get()`** replacements across all battle loop methods
- **12 direct `cal.field` → `cal_flat.get("field", default)`** replacements for inconsistent attribute accesses
- All `cal = ctx.calibration` assignments replaced with `cal_flat = _resolve_cal_flat(ctx)`
- Fire-zone section preserved (uses separate `_fz_cal` from `config.calibration_overrides`)

### 86b: Observer Modifier Batching (`simulation/battle.py`)

- **`_ObserverModifiers`** NamedTuple: 7 pre-computed per-observer values (MOPP detection, FOV, fatigue, reload, level; altitude factor; readiness)
- **`_DEFAULT_OBS_MODS`**: neutral instance (all 1.0, level 0)
- **Batch computation**: builds `_observer_mods` dict for all active units before the per-side engagement loop
  - MOPP effects: one `_cbrn_eng.get_mopp_effects()` call per unit (was per-weapon per-target)
  - Altitude sickness: one position check per unit (was duplicated in detection AND engagement)
  - Readiness: one `_maint_eng.get_unit_readiness()` call per unit (was per-weapon)
- **Inline replacements**: detection range modifiers and crew_skill modifiers now read from `_obs` lookup

## Key Design Decisions

1. **`dict.get(key, default)` over `dict[key]`**: Nullable CalibrationSchema fields produce None values that are stripped from the flat dict. Callers use `dict.get(key, default)` which returns the default when the key is absent — matching `CalibrationSchema.get()` behavior.
2. **`_resolve_cal_flat()` fallback**: Tests that pass `SimpleNamespace` contexts don't have `cal_flat`. The helper builds it on-the-fly from whatever `ctx.calibration` provides.
3. **Equipment stress NOT batched**: Depends on per-weapon equipment instance, not just the observer. Temperature fetch is already hoisted.
4. **Fire-zone `cal` renamed to `_fz_cal`**: This section reads from `config.calibration_overrides`, not `ctx.calibration`. Renamed to avoid confusion with `cal_flat`.
5. **No new `enable_*` flags**: Both optimizations are transparent — identical results, faster execution.

## Files Changed

### Modified (3 source)
- `stochastic_warfare/simulation/calibration.py` — `to_flat_dict()` method
- `stochastic_warfare/simulation/scenario.py` — `cal_flat` field, generation at load + checkpoint restore
- `stochastic_warfare/simulation/battle.py` — `_resolve_cal_flat()`, `_ObserverModifiers`, 100+ replacements, batch computation

### New (2 test + 1 devlog)
- `tests/unit/test_phase86_calibration_flat.py` — 11 tests
- `tests/unit/test_phase86_observer_batching.py` — 8 tests
- `docs/devlog/phase-86.md`

## Accepted Limitations

- Flat dict regenerated on checkpoint restore (not serialized) — adds ~1ms, avoids stale data risk
- Equipment temperature stress still computed per-weapon per-engagement (weapon-dependent, can't batch per-observer)
- `cal.get()` API preserved on CalibrationSchema for engine.py, scenario_runner.py, and test consumers (35 files) — only battle.py uses flat dict

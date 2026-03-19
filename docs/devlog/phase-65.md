# Phase 65: Space & EW Sub-Engine Activation

**Status**: Complete
**Tests**: 43 new (5 test files)
**Source files modified**: 6 (zero new source files)

## Overview

Wires five dormant space engines and two dormant EW engines that were fully implemented internally and instantiated on SimulationContext but whose outputs were never consumed by downstream systems. Fixes two latent bugs in `_fuse_sigint()` that have kept SIGINT fusion dead since Phase 52d. All behavioral changes gated by `enable_space_effects=False` (default). This is Block 7, Phase 8 of 10.

## Bugs Fixed

1. **engine.py `_fuse_sigint()` line 807**: `getattr(ew, "sigint_engine", None)` searched `JammingEngine` for `sigint_engine`. Fixed to `getattr(ctx, "sigint_engine", None)` — `sigint_engine` is a top-level SimulationContext field.

2. **engine.py `_fuse_sigint()` line 804**: `getattr(ctx, "intel_fusion_engine", None)` — attribute never existed on ctx. Fixed to access via `fog_of_war.intel_fusion` property. Both bugs meant SIGINT fusion was dead code since Phase 52d.

3. **ISR reports discarded**: `SpaceISREngine.update()` called `generate_isr_reports()` but discarded the return value. Fixed with `_recent_reports` buffer and `get_recent_reports()` method.

## Implementation

### Step 0: CalibrationSchema + Infrastructure (9 tests)

- `CalibrationSchema.enable_space_effects: bool = False` — gates ISR fusion, early warning, SIGINT intercepts
- `SpaceISREngine._recent_reports` buffer + `get_recent_reports(*, clear=True)` method
- `target_position` and `timestamp` fields added to ISR report dicts
- ISR state persistence updated (`get_state/set_state` include recent_reports)
- `FogOfWarManager.intel_fusion` property — exposes `_intel_fusion` for SIGINT/ISR track injection

### 65a: Space ISR & Early Warning (10 tests)

- **Bug fix 1**: `sigint_engine` accessed from `ctx`, not `ew_engine`
- **Bug fix 2**: fusion engine accessed via `fog_of_war.intel_fusion`, not nonexistent `ctx.intel_fusion_engine`
- `_fuse_sigint()` gated by `enable_space_effects`
- ISR report dict handling (`.get()` for dicts, `getattr` for objects)
- Early warning: `MissileLaunchEvent` subscription in `_register_event_handlers()`
- `_handle_missile_launch()` handler: finds launcher unit, calls `check_launch_detection()` for opposing sides

### 65b: ASAT & SIGINT (10 tests)

- SIGINT collector loading from `ew_config` YAML in `_create_ew_engines()`
- `_run_sigint_intercepts()`: iterates registered collectors, synthesizes `Emitter` from active `JammerInstance`, calls `attempt_intercept()`
- Collector positions updated from unit positions each tick
- `_attempt_asat_engagements()`: structural placeholder (no ASAT weapon YAML exists)
- Call sites wired: `_run_sigint_intercepts()` after `_update_ew()`, before `_fuse_sigint()`

### 65c: ECCM Integration (8 tests)

- ECCM suite loading from `ew_config` YAML in `_create_ew_engines()`
- battle.py: after `snr_penalty_db` computed, query `eccm_engine.get_suite_for_unit()`, subtract `compute_jam_reduction()` before applying `ew_factor`
- Self-gating: no registered suites = 0 dB reduction (no CalibrationSchema flag needed)
- All 4 techniques tested: frequency hopping, spread spectrum, sidelobe blanking, adaptive nulling

### Structural Verification (6 tests)

Source-level string assertions verifying all wiring is present and bug fixes hold.

## Files Modified

| File | Changes |
|------|---------|
| `stochastic_warfare/simulation/calibration.py` | +1 field: `enable_space_effects` |
| `stochastic_warfare/space/isr.py` | `_recent_reports` buffer, `get_recent_reports()`, `target_position`/`timestamp` in reports, state persistence |
| `stochastic_warfare/detection/fog_of_war.py` | `intel_fusion` property |
| `stochastic_warfare/simulation/engine.py` | 2 bug fixes, `_fuse_sigint()` gate + ISR dict adaptation, `_handle_missile_launch()`, `_run_sigint_intercepts()`, `_attempt_asat_engagements()`, early warning EventBus subscription |
| `stochastic_warfare/simulation/battle.py` | ECCM `compute_jam_reduction()` before `ew_factor` |
| `stochastic_warfare/simulation/scenario.py` | SIGINT collector + ECCM suite loading in `_create_ew_engines()` |

## Deferrals

| ID | Item | Reason |
|----|------|--------|
| D1 | SIGINT traffic analysis (`analyze_traffic()`) | Requires intercept history accumulation |
| D2 | BMD interceptor cueing from early warning | Requires BMD units + intercept routing |
| D3 | AI-driven ASAT targeting | Requires commander decision extension |
| D4 | ASAT weapon YAML data | No ASAT weapon definitions — can't exercise ASAT |
| D5 | Adaptive nulling direction calculation | Requires jammer bearing geometry |
| D6 | ISR-to-FOW direct injection | ISR→fusion only; full FOW contact injection separate |
| D7 | Auto-registration of SIGINT collectors from sensors | Complex synthesis from sensor defs |
| D8 | EW decoy deployment in battle loop | `deploy_decoys()` never called from engagement |

## Lessons Learned

- **Dead code since Phase 52d**: Both `_fuse_sigint()` bugs meant the entire SIGINT fusion pipeline was unreachable. Only discovered during systematic namespace tracing.
- **Dict vs object reports**: ISR reports changed from objects to dicts; `_fuse_sigint()` needed dual handling (`isinstance(sr, dict)` check) for forward compatibility.
- **JammerInstance lacks `side`**: Synthesizing `Emitter` from `JammerInstance` requires defensive defaults since jammer has no side attribution.
- **Self-gating pattern**: ECCM needs no CalibrationSchema flag — no registered suites means `get_suite_for_unit()` returns None, zero reduction applied.

## Postmortem

- **Scope**: On target — 43 tests vs ~40 planned
- **Quality**: High — 2 latent bugs fixed, zero regressions, all opt-in gated
- **Integration**: Fully wired for ECCM + SIGINT + early warning; ASAT structural only
- **Deferrals**: 8 items (D1-D8), all reasonable — no ASAT data, traffic analysis is secondary
- **Performance**: No impact — all new code paths gated by `enable_space_effects=False`

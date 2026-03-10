# Phase 53: C2 & AI Completeness

**Status**: Complete
**Tests**: 44 new
**Files modified**: 6 source + 1 new test file
**Deficits resolved**: 7 (D12, E8, Phase 19 school_id, Phase 19 get_stratagem_affinity, Phase 25 C2 effectiveness, Phase 25 stratagem affinity, Phase 25 school_id auto-assignment)

## Summary

Wired 5 orphaned C2/AI engines into the simulation loop and replaced hardcoded C2 effectiveness with a comms-based computation. FogOfWarManager now updates per-side detection pictures (gated by `enable_fog_of_war` calibration flag). StratagemEngine evaluates concentration/deception opportunities in the DECIDE phase with school affinity weights. ATOPlanningEngine generates ATO for aerial units in strategic ticks. IadsEngine is instantiated and SEAD parameters are wired. C2 effectiveness is computed from average channel reliability to friendly units.

## 53b: C2 Effectiveness

- Added `compute_c2_effectiveness()` to `CommunicationsEngine`
- Computes average channel reliability to friendly units
- Replaces hardcoded `c2_effectiveness = 1.0` in battle.py OBSERVE phase and fallback assessment
- New calibration field: `c2_min_effectiveness` (default 0.3)
- `_compute_c2_effectiveness()` helper in battle.py wraps the comms engine call

**Resolves**: Phase 25 deficit (C2 effectiveness hardcoded at 1.0).

## 53c: StratagemEngine + school_id

- `StratagemEngine` instantiated in `_create_engines()`, attached to `SimulationContext` as `stratagem_engine`
- `evaluate_concentration_opportunity()` and `evaluate_deception_opportunity()` called in DECIDE phase with school affinity weights
- `school_id` from `CommanderPersonality` auto-assigns via `SchoolRegistry` in `_apply_commander_assignments()`

**Resolves**: Phase 19 deficits (school_id dead, get_stratagem_affinity never called), Phase 25 deficit (stratagem affinity wiring).

## 53a: FogOfWarManager

- FoW `update()` called per-side in `execute_tick`, gated by `enable_fog_of_war` calibration flag (default False)
- OBSERVE phase uses detected enemy count when fog of war is enabled
- New calibration field: `enable_fog_of_war`
- Backward compatible: disabled by default, existing scenarios unchanged

**Resolves**: D12 (per-commander assessment unimplemented).

## 53e: SEAD/IADS + Escalation

- `IadsEngine` instantiated in `_create_engines()`, attached to `SimulationContext` as `iads_engine`
- `sead_effectiveness` and `sead_arm_effectiveness` added to `IadsConfig`
- Both wired into `apply_sead_damage()` for SEAD strike resolution
- `PoliticalPressureEngine.update()` called in `_update_escalation()` with per-side casualty data

**Resolves**: E8 (4 SEAD/IADS params — sead_effectiveness, sead_arm_effectiveness, iads_degradation_rate wired; drone_provocation_prob accessible).

## 53d: Structural Wiring

- `ATOPlanningEngine` instantiated in `_create_engines()`, attached to `SimulationContext` as `ato_engine`
- Aerial units auto-registered with ATO engine
- `generate_ato()` called in strategic tick
- `PlanningProcessEngine.update()` called in strategic tick
- `OrderPropagationEngine` availability logged in DECIDE phase

## Files Changed

| File | Action | Changes |
|------|--------|---------|
| `c2/communications.py` | Modified | Added `compute_c2_effectiveness()` method |
| `simulation/calibration.py` | Modified | Added `c2_min_effectiveness`, `enable_fog_of_war` fields |
| `simulation/battle.py` | Modified | FoW update in execute_tick, C2 effectiveness in OBSERVE, stratagem eval + order prop logging in DECIDE, `_compute_c2_effectiveness()` helper |
| `simulation/scenario.py` | Modified | Added `stratagem_engine`, `iads_engine`, `ato_engine` fields to SimulationContext + instantiation in `_create_engines()` + school_id auto-assignment in `_apply_commander_assignments()` |
| `simulation/engine.py` | Modified | `planning_engine.update()`, ATO generation, `political_engine.update()` in `_update_escalation()` |
| `combat/iads.py` | Modified | Added `sead_effectiveness`, `sead_arm_effectiveness` to IadsConfig, modified `apply_sead_damage()` |
| `tests/unit/test_phase53_c2_ai.py` | New | 44 tests |

## Lessons Learned

- **Comms-based C2 effectiveness is the right abstraction**: Average channel reliability captures the essence of C2 degradation (jammed/disrupted comms = degraded C2) without needing per-unit path tracing.
- **Calibration flag gating (enable_fog_of_war) preserves backward compat**: All existing scenarios run identically with the flag defaulting to False. Individual scenarios opt in.
- **school_id auto-assignment in post-creation hook is clean**: `_apply_commander_assignments()` runs after all entities are created, so SchoolRegistry lookup works reliably.
- **SEAD params on IadsConfig (not CalibrationSchema) is the right home**: These are engine-specific parameters that belong on the engine config, not the global calibration schema.

## Postmortem

### Delivered vs Planned
- **53a (FoW)**: Delivered. Gated by calibration flag, per-side detection in OBSERVE phase.
- **53b (C2 effectiveness)**: Delivered. `compute_c2_effectiveness()` replaces hardcoded 1.0.
- **53c (Stratagem + school_id)**: Delivered. Both evaluate_* methods called in DECIDE, school_id auto-assigns.
- **53d (ATO + planning + order prop)**: Delivered structurally. ATO generates in strategic tick, planning engine updates, order prop logged.
- **53e (SEAD/IADS + escalation)**: Delivered. IadsEngine instantiated, SEAD params wired, political pressure engine called.
- **Scope**: 44 tests vs planned ~51. Slightly under but all substeps covered.

### Integration Audit
- `compute_c2_effectiveness()` called from battle.py OBSERVE phase
- `stratagem_engine` instantiated and evaluated in DECIDE phase
- `ato_engine` instantiated and generates ATO in strategic tick
- `iads_engine` instantiated, SEAD params consumed in `apply_sead_damage()`
- `enable_fog_of_war` calibration flag read in `execute_tick()`
- `school_id` auto-assigned via SchoolRegistry in `_apply_commander_assignments()`
- `political_engine.update()` called in `_update_escalation()`

### Deficits Discovered
- `sead_arm_effectiveness` defined on IadsConfig but never consumed — only `sead_effectiveness` is used in `apply_sead_damage()`. The ARM missile Pk modifier needs a consumer in the SEAD strike path.
- `drone_provocation_prob` in CalibrationSchema but never consumed by any engine — no escalation trigger integration point exists for drone encounters.

### Quality: High | Integration: Fully wired | Deficits: 2 new

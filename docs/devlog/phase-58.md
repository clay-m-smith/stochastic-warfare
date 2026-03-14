# Phase 58: Structural Verification & Core Combat Wiring

**Block**: 7 (Final Engine Hardening)
**Status**: Complete
**Tests**: 60 new tests across 5 test files
**Date**: 2026-03-13

## Overview

Phase 58 is the first phase of Block 7. It creates structural verification tests to catch integration gaps, then fixes P0 combat wiring issues: air combat routing, damage detail extraction, posture protection configurability, and fuel tracking on ground units.

## Substeps

### 58a: Structural Verification Tests (6 tests)

Created `tests/validation/test_structural_audit.py` with 6 structural guardrail tests that read source files and assert critical code paths exist:

1. `test_air_engines_on_context` — scenario.py has air_combat_engine, air_ground_engine, air_defense_engine
2. `test_air_engagement_types_routed` — battle.py has `_route_air_engagement`
3. `test_damage_detail_consumed` — battle.py references `.casualties` and `.systems_damaged`
4. `test_posture_protection_in_calibration` — calibration.py has posture_blast/frag_protection fields
5. `test_ground_unit_fuel_field` — ground.py has fuel_remaining field
6. `test_battle_fuel_consumption` — battle.py has Phase 58e fuel gate

### 58b: Air Combat Routing (22 tests)

Wired `AirCombatEngine`, `AirGroundEngine`, `AirDefenseEngine` into the battle loop:

- Added `_route_air_engagement()` to battle.py (~80 lines), following the `(handled, status)` tuple pattern from naval routing
- Added 3 fields to `SimulationContext`: air_combat_engine, air_ground_engine, air_defense_engine
- Conditional engine instantiation in `_create_engines()` gated by `enable_air_routing` calibration flag
- Weapon category gating: only MISSILE_LAUNCHER routes to air combat, BOMB/GUIDED_BOMB/MISSILE_LAUNCHER to CAS, MISSILE_LAUNCHER/SAM to air defense
- `enable_air_routing: bool = False` in CalibrationSchema — opt-in to prevent regressions

### 58c: Damage Detail Extraction (13 tests)

Infrastructure for consuming DamageResult detail fields:

- Added `apply_casualties()` method to Unit — marks personnel as wounded/KIA based on CasualtyResult list
- Added `degrade_equipment()` method to Unit — disables equipment by ID based on systems_damaged list
- Added `_SEVERITY_MAP` ClassVar mapping severity strings to InjuryState enums
- battle.py now extracts and logs `.casualties`, `.systems_damaged`, `.fire_started` from DamageResult
- **Deferred**: Behavioral application (calling apply_casualties/degrade_equipment in hot loop) deferred to calibration — uncalibrated application extended battle durations, causing evaluator timeout

### 58d: Posture Protection Calibration (9 tests)

Made posture blast/frag protection values per-scenario configurable:

- Added `posture_blast_protection: dict[str, float] | None = None` and `posture_frag_protection: dict[str, float] | None = None` to CalibrationSchema
- DamageEngine.__init__ accepts `posture_blast_overrides` and `posture_frag_overrides`
- Changed 3 references from module-level `_POSTURE_BLAST_PROTECT`/`_POSTURE_FRAG_PROTECT` to instance `self._posture_blast`/`self._posture_frag`
- scenario.py passes calibration overrides to DamageEngine

### 58e: Fuel Gate (11 tests) [partial deferral]

Added fuel tracking and gate check to ground units:

- Added `fuel_remaining: float = 1.0` field to GroundUnit with get_state/set_state backward compatibility
- Added fuel gate check in battle.py movement: vehicles (max_speed > 5) with fuel=0 cannot move
- **Deferred**: Active fuel consumption in movement hot loop deferred — consuming fuel at 0.0001/meter caused vehicles to stall mid-battle before calibration accounted for it, extending simulation time past evaluator timeout

## Files Modified

| File | Change |
|------|--------|
| `tests/validation/test_structural_audit.py` | **NEW** — 6 structural verification tests |
| `tests/unit/test_phase_58b_air_routing.py` | **NEW** — 22 air routing tests |
| `tests/unit/test_phase_58c_damage_detail.py` | **NEW** — 13 damage detail tests |
| `tests/unit/test_phase_58d_posture_calibration.py` | **NEW** — 9 posture calibration tests |
| `tests/unit/test_phase_58e_logistics_gates.py` | **NEW** — 11 fuel gate tests |
| `stochastic_warfare/simulation/calibration.py` | 3 new fields (posture_blast, posture_frag, enable_air_routing) |
| `stochastic_warfare/combat/damage.py` | DamageEngine posture overrides (init + 3 references) |
| `stochastic_warfare/simulation/scenario.py` | 3 air engine context fields, conditional instantiation, posture overrides to DamageEngine |
| `stochastic_warfare/simulation/battle.py` | `_route_air_engagement()`, air routing insertion, damage detail logging, fuel gate |
| `stochastic_warfare/entities/base.py` | `apply_casualties()`, `degrade_equipment()`, `_SEVERITY_MAP` |
| `stochastic_warfare/entities/unit_classes/ground.py` | `fuel_remaining` field + state methods |

## Lessons Learned

1. **Behavioral changes without calibration cause regressions**: `apply_casualties` and `degrade_equipment` degraded units progressively during combat, extending battle durations. Fuel consumption caused vehicles to stall mid-battle. Both required calibration adjustment before safe to enable.

2. **Opt-in flags prevent hidden regressions**: `enable_air_routing=False` default meant existing scenarios were unaffected. Air routing is infrastructure-ready for per-scenario enablement.

3. **Fuel consumption rate matters by resolution**: In OPERATIONAL resolution (dt=60s), vehicles move 900m/tick. At 0.0001/meter fuel rate, fuel depletes in ~11 ticks (11 minutes sim time), causing mid-battle stalls.

4. **Duplicate pending_damage entries are bugs**: When ammo_cookoff sets damage_fraction=1.0, the existing threshold check already adds DESTROYED. Adding it again from the ammo_cookoff flag is a duplicate.

5. **Structural tests (source text assertions) run in 0.4s**: 100x faster than scenario runs. Excellent regression guardrails.

## Known Limitations / Deferred Items

- **58c**: apply_casualties and degrade_equipment methods exist on Unit but are not called in the battle loop — behavioral application deferred to when calibration accounts for progressive unit degradation
- **58e**: Fuel consumption in movement loop commented out — deferred to dedicated logistics tick or when fuel rates are calibrated per-vehicle-type
- **58b**: Air routing uses simplified Pk values (0.4-0.5) — proper weapon stat integration deferred to when scenarios enable air routing

## Postmortem

### Scope: On target (with partial deferrals)

**Planned vs delivered**:
- 58a: Delivered 6 structural tests (plan called for 5 AST-based tests — we used simpler source-text assertions instead, which is the pattern from test_deficit_closure.py and runs in 0.4s). Scope was right-sized.
- 58b: Delivered 22 tests, exceeding the planned ~12. Added weapon category gating and `enable_air_routing` opt-in flag (unplanned but essential to prevent regressions). Did NOT wire through `_infer_engagement_type()` enum values — used standalone routing function instead.
- 58c: Delivered 13 tests. Infrastructure (apply_casualties/degrade_equipment on Unit) shipped. **Behavioral application deferred** — calling these in the battle hot loop changed battle dynamics without calibration, causing 35% slowdown and evaluator timeout.
- 58d: Delivered 9 tests. Fully complete — posture protection configurable via CalibrationSchema.
- 58e: Delivered 11 tests. Fuel field + gate check complete. **Fuel consumption deferred** — consuming fuel at 0.0001/meter in OPERATIONAL resolution depleted vehicles in 11 ticks, stalling battles.
- Plan called for ~60 tests; delivered exactly 60.

**Unplanned additions**:
- `enable_air_routing` flag on CalibrationSchema (essential safety mechanism)
- Weapon category gating in air routing (MISSILE_LAUNCHER, BOMB, SAM — prevents cannon/direct-fire from being routed through air engines)

### Quality: Medium

**Strengths**:
- Good edge case coverage (bounds check, backward compat, weapon fallthrough, engine=None)
- Structural tests are fast and robust regression guardrails
- DamageEngine posture override tests verify both configuration and behavioral parity

**Weaknesses**:
- No integration test that runs a full scenario with `enable_air_routing: true` — air routing is tested via mocks only
- Fuel gate tests use direct formula checks, not battle loop integration
- apply_casualties/degrade_equipment are unit-tested but UNWIRED (never called in production code)

### Integration: Gaps found

| Item | Status |
|------|--------|
| Air engines on SimulationContext | Wired (conditional on enable_air_routing) |
| `_route_air_engagement` in battle loop | Wired (gated by flag) |
| CalibrationSchema fields | All 3 wired |
| DamageEngine posture overrides | Wired |
| `fuel_remaining` fuel gate | Wired |
| `apply_casualties` / `degrade_equipment` | **UNWIRED** — defined and tested but not called in battle loop |
| Fuel consumption | **UNWIRED** — commented out in battle loop |

### Deficits: 3 new items

1. **58c: apply_casualties/degrade_equipment unwired** — Methods exist on Unit but are not called from battle.py. Behavioral application requires calibration to account for progressive unit degradation. Target: future calibration phase.
2. **58e: Fuel consumption unwired** — Fuel gate (check) works but fuel depletion (consumption) is commented out. Rate needs per-vehicle-type calibration and resolution-aware scaling. Target: future logistics phase.
3. **58b: Air routing uses hardcoded Pk values** — `missile_pk = 0.5`, `weapon_pk = 0.4`, `interceptor_pk = 0.4` are placeholders. Should read from weapon definitions when scenarios enable air routing. Target: when first scenario uses `enable_air_routing: true`.

### Performance: Acceptable

Full suite: 757s (vs ~700s Phase 57 baseline). ~8% slower — within 10% threshold. The 60 new tests add negligible time (0.4s). The minor overhead comes from per-unit fuel gate getattr checks and per-engagement damage detail field access.

### Action items

- [x] Fix mkdocs.yml nav (add phase-58 devlog)
- [x] Update README.md test count (8,383 → 8,152)
- [x] Update docs/index.md test count and add Block 7
- [x] Add devlog/index.md refinement entries for 3 new deficits

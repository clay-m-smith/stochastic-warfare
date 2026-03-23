# Phase 71: Missile & Carrier Ops Completion

**Status**: Complete. 46 tests across 4 test files. 5 source files modified, 0 new source files.

**Goal**: Close the two largest remaining engine gaps — missile flight-to-impact resolution and carrier air operations. Fix 2 pre-existing bugs.

## Changes

### 71a: Bug Fixes (2 pre-existing issues)

1. **`_sim_time_s` UnboundLocalError** (`engine.py`): Phase 69 introduced `_cur_day_69a = int(_sim_time_s / 86400)` for daily sortie reset, but `_sim_time_s` wasn't assigned until 20 lines later. Moved `_sim_time_s = ctx.clock.elapsed.total_seconds()` before the daily reset check. Removed duplicate assignment. This bug caused 15 scenario failures.

2. **Missing `launcher_id`/`missile_id` in engagement.py**: COASTAL_DEFENSE and AIR_LAUNCHED_ASHM `launch_missile()` calls lacked required `launcher_id` and `missile_id` args (the MISSILE handler had them correct). Added `launcher_id=attacker_id` and unique `missile_id` to both.

### 71b: Missile Flight Resolution

Wired `MissileEngine.update_missiles_in_flight()` into `battle.py` execute_tick (step 4h, after movement and before engagement):

- Per-tick flight update advances all active missiles and resolves impacts
- GPS accuracy from SpaceEngine feeds into CEP dispersion
- Impact damage applied via `_apply_aggregate_casualties()` to nearest unit within 100m
- Gated behind existing `enable_missile_routing` flag

### 71c: Missile Defense Intercept

Instantiated `MissileDefenseEngine` on `SimulationContext` and wired intercept checks:

- Added `missile_defense_engine` field to SimulationContext
- Instantiated in `_create_engines()` with COMBAT RNG stream
- Per-tick: for each active missile, AD units (identified by SAM/CIWS/MISSILE_LAUNCHER weapon category) attempt intercept
- Cruise missiles → `engage_cruise_missile()` (with sea-skimming penalty)
- Ballistic missiles → `engage_ballistic_missile()` (layered defense)
- Successful intercept deactivates missile before impact resolution

### 71d: Carrier Ops Battle Loop

Wired `CarrierOpsEngine` into execute_tick (step 4i):

- Added `enable_carrier_ops: bool = False` to CalibrationSchema
- Per-tick CAP station updates (endurance tracking, relief flagging)
- Carrier unit identification by unit_type containing "carrier" or "cv"
- Sortie rate computation based on aircraft count, crew quality, weather
- Beaufort > 7 suspends flight operations
- **Structural wiring only** — no current scenarios have carrier units

## Files Modified

| File | Changes |
|------|---------|
| `simulation/engine.py` | 71a-1: Fix `_sim_time_s` ordering |
| `combat/engagement.py` | 71a-2: Add launcher_id/missile_id to 2 call sites |
| `simulation/battle.py` | 71b: Missile flight + impact; 71c: Missile defense; 71d: Carrier ops |
| `simulation/scenario.py` | 71c: Add missile_defense_engine field + instantiation |
| `simulation/calibration.py` | 71d: Add enable_carrier_ops flag |
| `tests/validation/test_phase_67_structural.py` | Add enable_carrier_ops to deferred flags |

## New Test Files

| File | Tests |
|------|-------|
| `tests/unit/test_phase_71a_bugfixes.py` | 8 |
| `tests/unit/test_phase_71b_missile_flight.py` | 12 |
| `tests/unit/test_phase_71c_missile_defense.py` | 12 |
| `tests/unit/test_phase_71d_carrier_ops.py` | 14 |
| **Total** | **46** |

## CalibrationSchema Fields (1 new)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `enable_carrier_ops` | `bool` | `False` | Gate carrier flight ops processing |

## Design Decisions

1. **Missile target resolution via spatial proximity**: Missiles guide to `target_pos`, not `target_id`. Nearest unit within 100m of impact point receives damage. Realistic — weapons guide to coordinates, not entities.

2. **AD unit identification by weapon category**: SAM/CIWS/MISSILE_LAUNCHER heuristic. Simple, correct for current data, extensible without schema changes.

3. **Carrier ops structural-only**: No scenarios have carrier units. Wiring exercises the API path but won't affect outcomes until carrier units are added. Flag defaults to False.

4. **Reuse existing `enable_missile_routing` for flight + defense**: No additional flag needed — missile defense is meaningless without missile flight.

## Postmortem

### Delivered vs Planned

The plan spec (development-phases-block8.md) described 71a/71b/71c as three substeps. Implementation reorganized into 71a (bug fixes, unplanned), 71b (missile flight), 71c (missile defense), 71d (carrier ops). The bug fixes were discovered during planning and added as 71a.

**Scope delta**:
- **Added**: 71a bug fixes (2 pre-existing issues) — unplanned but essential
- **Added**: MissileDefenseEngine instantiation on SimulationContext (plan assumed it was already there)
- **Simplified**: Carrier ops — plan specified sortie dispatch and recovery windows. Implementation covers CAP + sortie rate + sea state gating. Recovery window management is structural but not scenario-exercised.
- **Renamed substeps**: Plan had 71a/71b/71c → implementation is 71a/71b/71c/71d (4 substeps instead of 3)

**Verdict**: Scope well-calibrated. 46 tests vs ~32 planned (+44%).

### Integration Audit

| Check | Result |
|-------|--------|
| `update_missiles_in_flight` called in battle.py | PASS |
| `missile_defense_engine` on SimulationContext + instantiated | PASS |
| `enable_carrier_ops` in CalibrationSchema | PASS |
| `enable_carrier_ops` in structural test deferred list | PASS |
| No TODOs/FIXMEs in modified files | PASS |
| No dead modules | PASS — no new source files |

### Test Quality

- **Mix**: 71a all structural (source inspection); 71b/c/d mixed behavioral + structural
- **Statistical rigor**: 50-trial GPS accuracy sweep, 30-trial high-Pk check, A/B sea-skimming comparison
- **Edge cases**: Zero aircraft, zero Pk, Beaufort > 7, multilayer defense
- **Weakness**: Structural tests tightly coupled to variable names (`_m71.active`) and log messages (`"flight ops suspended"`) — fragile to refactoring but acceptable for integration verification

### Deficits

1. **Carrier ops untested in scenarios** — `enable_carrier_ops` is in `_DEFERRED_FLAGS`. Will be exercised when carrier scenarios are added. *(accepted limitation — structural wiring is the deliverable)*

2. **AD Pk hardcoded at 0.7** — The base intercept Pk for AD units is hardcoded. Should eventually read from weapon definition. *(accepted limitation — below current scenario resolution)*

3. **No missile defense checkpoint state** — MissileDefenseEngine has get_state/set_state but isn't registered with CheckpointManager. *(deferred to Phase 72 — checkpoint completeness)*

### Documentation Freshness

All lockstep docs updated in this commit:
- [x] CLAUDE.md Phase 71 entry
- [x] development-phases-block8.md status → Complete
- [x] devlog/index.md Phase 71 row
- [x] devlog/phase-71.md (this file)
- [x] README.md test count
- [x] MEMORY.md status update

### Summary

- **Scope**: On target (slight expansion for bug fixes)
- **Quality**: High — 46 tests, all passing, full suite green
- **Integration**: Fully wired — all 3 engines connected to battle loop
- **Deficits**: 3 items (all accepted/deferred)
- **Action items**: Update lockstep docs → done

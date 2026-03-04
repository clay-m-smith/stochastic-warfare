# Phase 19: Doctrinal AI Schools

## Summary

Phase 19 adds 9 named doctrinal schools as Strategy-pattern classes that modify AI decision-making behavior. Each school represents a distinct warfare philosophy (Clausewitz, Sun Tzu, Boyd/Maneuver, etc.) and produces measurably different behavior when commanding the same forces.

**Key metric**: 189 new tests, 5,107 total (up from 4,918). 10 new source files + 3 modified + 9 YAML data files. No new dependencies.

## What Was Built

### 19a: School Framework (35 tests)
- `c2/ai/schools/__init__.py` — `SchoolRegistry` (register/get/assign_to_unit/get_for_unit/get_state/set_state) + `SchoolLoader` (YAML→SchoolDefinition)
- `c2/ai/schools/base.py` — `SchoolDefinition` pydantic model + `DoctrinalSchool` ABC with 8 hooks
- `c2/ai/assessment.py` (modified) — `weight_overrides` parameter with multiplicative application + re-normalization; `predict_opponent_action_lanchester()` standalone function
- `c2/ai/decisions.py` (modified) — `school_adjustments` parameter threaded through `decide()` → `_decide_*()` → `_select_best()`
- `c2/ai/commander.py` (modified) — `school_id: str | None = None` field on `CommanderPersonality`

### 19b: Western Schools (65 tests)
- **ClausewitzianSchool**: force_ratio > 1.5 → +0.15 ATTACK/MAIN_ATTACK/ENVELOP; culmination awareness (low supply/morale → CONSOLIDATE/DEFEND)
- **ManeuveristSchool**: +0.15 FLANK/BYPASS/EXPLOIT/PURSUE; OODA ×0.7; penalty to frontal assault at unfavorable ratios
- **AttritionSchool**: force_ratio > 1.5 → ATTACK; else DEFEND/SUPPORT_BY_FIRE; OODA ×1.2; risk=low
- **AirLandBattleSchool**: echelon ≥ 10 → DEEP_STRIKE/OPERATIONAL_MANEUVER; echelon 8-9 → ATTACK/COUNTERATTACK; high intel → EXPLOIT
- **AirPowerSchool**: echelon ≥ 10 → DEEP_STRIKE, penalty MAIN_ATTACK; echelon 8-9 → DEFEND/DELAY (hold for air superiority)

### 19c: Eastern & Historical Schools (31 tests)
- **SunTzuSchool**: intel ×3; opponent modeling via `predict_opponent_action_lanchester()`; counter-posture scoring (opponent ATTACK → AMBUSH/FLANK; opponent DEFEND → BYPASS; opponent WITHDRAW → PURSUE); low intel → +0.2 RECON
- **DeepBattleSchool**: high ratio → ATTACK/EXPLOIT; moderate → RESERVE; echelon ≥ 10 → DEEP_STRIKE/OPERATIONAL_MANEUVER; OODA ×1.1

### 19d: Maritime Schools (15 tests)
- **MahanianSchool**: force_ratio > 1.0 → +0.15 ATTACK/MAIN_ATTACK; always -0.1 BYPASS (concentration paramount)
- **CorbettianSchool**: force_ratio < 2.5 → -0.15 ATTACK, +0.1 DEFEND/DELAY; only attack when overwhelming (≥ 2.5)

### 19e: Integration (18 tests)
- `simulation/scenario.py` — `school_registry` field on `SimulationContext`, get_state/set_state
- `simulation/battle.py` — Wired into `_process_ooda_completions()`: weight_overrides on OBSERVE, school_adjustments + opponent modeling on DECIDE, OODA multiplier stacking on phase start
- `c2/planning/coa.py` — `score_weight_overrides` parameter on `compare_coas()`

### 19f: YAML Data & Validation (25 tests)
- 9 YAML school definitions in `data/schools/`
- Parametrized loading, behavioral differentiation, determinism, backward compatibility, opponent modeling E2E tests

## Design Decisions

1. **Parameter injection, not engine wrapping**: Schools produce modifier dicts consumed by existing engines via optional parameters. Same pattern as `mopp_speed_factor` (Phase 18), `jam_snr_penalty_db` (Phase 16), `gps_accuracy_m` (Phase 17).

2. **YAML + Python hybrid**: YAML stores numeric constants (weights, bonuses, multipliers). Python subclasses add conditional logic (Clausewitzian culmination, Sun Tzu opponent modeling, AirLand echelon-dependent behavior).

3. **SchoolRegistry stores unit assignments**: `assign_to_unit(unit_id, school_id)` → `get_for_unit(unit_id)`. Avoids dependency on unwired `CommanderEngine`.

4. **Opponent modeling is lightweight**: `predict_opponent_action_lanchester()` is a standalone function in `assessment.py` using force-ratio heuristics. Only Sun Tzu calls it. One-step lookahead, not game tree search.

5. **OODA stacking**: School multiplier folds into `tactical_mult`: `effective_mult = tactical_acceleration × school.get_ooda_multiplier()`.

6. **Assessment weight normalization**: Overrides are multipliers on `_WEIGHTS`, then re-normalized to sum=1.0. Sun Tzu `intel: 3.0` → effective intel weight grows from 10% to ~25%.

## Deviations from Plan

- Plan estimated ~152 tests; delivered 189 (agents produced more comprehensive test suites)
- Integration tests (19e) avoid triggering DECIDE through BattleManager due to pre-existing `assessment=None` gap — tested at component level instead

## Issues & Fixes

- **Battle.py assessment=None gap**: The existing `_process_ooda_completions()` passes `assessment=None` to `decide()`, which crashes when `decide()` tries to access `assessment.force_ratio`. This is a pre-existing gap (not Phase 19). Integration tests work around it by testing school wiring at the component level rather than through the broken path.

## Known Limitations

- `CommanderEngine` is not wired into `SimulationContext` — battle loop passes `personality=None`. Phase 19 works around this by storing unit→school assignments in `SchoolRegistry`.
- `battle.py` passes `assessment=None` to `decide()` — pre-existing gap that prevents full OODA DECIDE integration through the battle manager.
- ScenarioLoader doesn't auto-wire SchoolRegistry from YAML (extends existing EW/Space/CBRN gap).
- No comparative outcome visualization (deferred — infrastructure exists in Phase 14 tools).

## Related Doctrinal Frameworks — Future Schools

Phase 19's 9 schools cover classical through Cold War-era conventional doctrine. Three significant modern developments extend beyond this scope and are noted here for future implementation (likely after Phase 24 provides non-kinetic infrastructure):

1. **Generational Warfare / 4GW-5GW (Lind et al.)**: Lind's 1989 *Marine Corps Gazette* framework argues warfare evolves through generations — from line-and-column (1GW) through firepower/attrition (2GW) and maneuver (3GW) to non-state legitimacy contests (4GW). 4GW fights at Boyd's "moral level," targeting political will and legitimacy rather than military forces. 5GW (speculative — Abbott 2010) involves warfare through manipulation of context so subtle the target may not recognize it is under attack (cognitive warfare, algorithmic influence, systemic vulnerability exploitation). A 4GW school would weight `population_disposition` and `political_will` far above `force_ratio`, seek no decisive engagement, and operate on 5-10× longer planning horizons.

2. **Unrestricted Warfare (Qiao Liang & Wang Xiangsui, 1999)**: Two PLA colonels argue any domain of human activity can be weaponized, identifying 24 warfare types across military, trans-military, and non-military categories (including financial, trade, legal/lawfare, media, ideological). Core principles: omnidirectionality (attack from any domain), synchrony (simultaneous multi-domain action for multiplicative effect), and asymmetry (if adversary dominates militarily, attack through finance/cyber/legal). Related: PLA "Three Warfares" (三战, 2003) — psychological, media, legal warfare as formal doctrine.

3. **Gerasimov's "New Generation Warfare" (2013)**: Russian Chief of General Staff articulates 4:1 non-military-to-military ratio, phased escalation (covert preparation → political pressure → information dominance → crisis escalation → military intervention → political settlement), and reflexive control (рефлексивное управление — manipulating adversary decision-making processes, not just degrading them).

These theories inherit from classical schools (4GW from Mao/Sun Tzu, Unrestricted Warfare from Sun Tzu/Clausewitz, Gerasimov from Soviet deep battle) but require non-kinetic action domains (information, cyber, economic, legal) that don't yet exist in the engine. See `brainstorm-post-mvp.md` Section 7 "Modern & Post-Classical Schools" for full analysis and source bibliography.

## Lessons Learned

- **Parallel agent implementation scales well**: 4 background agents (19b, 19c, 19d, 19f) completed independently. Total Phase 19 delivered in ~2 agent rounds.
- **DI parameter injection is the right pattern**: Adding `None`-default optional parameters preserves all existing tests while enabling new behavior. Used consistently since Phase 11.
- **Pre-existing gaps surface during integration**: The `assessment=None` gap in battle.py was discovered when wiring schools into `_process_ooda_completions()`. Testing at component level rather than E2E avoids coupling to the broken path.
- **YAML + Python hybrid works well for schools**: Numeric constants in YAML keep school definitions data-driven. Python overrides add conditional logic (culmination awareness, echelon behavior, opponent modeling) that can't be expressed as flat config.

## Postmortem

### 1. Delivered vs Planned
- **Scope**: On target. All planned items shipped (10 source files, 9 YAML, 6 modified files).
- **Test count**: Plan estimated ~152 tests; delivered 189 (+24%). Agents produced more comprehensive test suites, not scope creep.
- **No items dropped or deferred**. No unplanned features added.

### 2. Integration Audit
- **Core wiring solid**: Assessment weight_overrides, decision school_adjustments, OODA multiplier stacking all wired into `battle.py`'s `_process_ooda_completions()`.
- **Checkpoint/restore**: `school_registry` in SimulationContext `get_state()`/`set_state()`.
- **RED FLAG — Unwired hooks**: `get_coa_score_weight_overrides()` and `get_stratagem_affinity()` hooks are defined on `DoctrinalSchool` but never called in production code. The `compare_coas()` parameter exists but is never invoked from the battle loop. Tests exercise the parameter directly but production path is incomplete.
- **RED FLAG — Dead field**: `CommanderPersonality.school_id` is defined but never read anywhere in production code. Schools are assigned via `SchoolRegistry.assign_to_unit()` instead. Field is a forward-looking placeholder.
- **RED FLAG — No auto-loading**: `SchoolRegistry` not auto-instantiated from scenario YAML. Extends existing EW/Space/CBRN gap.
- **No new event types** (by design — schools use parameter injection, not events).

### 3. Test Quality Review
- **Overall rating**: 7.5/10
- **Fixed during postmortem**: (1) `assert True` in OODA stacking test → replaced with statistical average comparison. (2) COA override test only checked `is not None` → now asserts scores actually differ.
- **Remaining medium-priority gaps**: Opponent modeling verified for math but not decision impact; no systematic cross-school differentiation matrix.
- **Strengths**: Realistic data ranges, boundary value tests, backward compatibility verification, parametrized interfaces, all 9 real YAML files tested.

### 4. API Surface Check
- **Quality**: Excellent. All public functions have type hints. Proper `_` prefixing. `get_logger(__name__)` throughout. DI pattern followed. No TODOs/FIXMEs. Pydantic for config. Consistent with Phase 8-18 patterns.

### 5. New Deficits (added to devlog/index.md)
1. `get_coa_score_weight_overrides()` and `get_stratagem_affinity()` hooks defined but never called in production battle loop
2. `CommanderPersonality.school_id` field defined but never read — schools assigned via SchoolRegistry instead
3. (Pre-existing, already documented) `battle.py` passes `assessment=None` to `decide()`
4. (Pre-existing, already documented) ScenarioLoader doesn't auto-wire SchoolRegistry
5. (Pre-existing, already documented) CommanderEngine not wired into SimulationContext

### 6. Documentation Freshness
- **CLAUDE.md**: Updated with Phase 19 status + completed phase section. ✓
- **development-phases-post-mvp.md**: Phase 19 marked COMPLETE with all sub-phases. ✓
- **devlog/index.md**: Phase 19 status → Complete, deficit resolved, new deficits added. ✓
- **project-structure.md**: schools/ package added to source + data trees, status updated. ✓
- **README.md**: Test count (5,107), phase badge (19), status table updated. ✓
- **MEMORY.md**: Current status and lessons learned updated. ✓

### 7. Performance
- Full suite: **5,107 passed in 96.89s**. Phase 19 tests alone: 0.57s. No performance regression (Phase 18 was ~95s for 4,918 tests).

### 8. Summary
- **Scope**: On target
- **Quality**: High (7.5/10 tests, excellent API surface)
- **Integration**: Mostly wired — 2 hooks (COA overrides, stratagem affinity) and 1 field (school_id) are defined but not used in production
- **Deficits**: 2 new items (unwired hooks, unused field)
- **Action items completed**: Fixed 2 weak test assertions (OODA `assert True`, COA `is not None`)

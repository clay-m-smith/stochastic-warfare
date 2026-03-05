# Phase 25: Engine Wiring & Integration Sprint

**Status**: Complete
**Tests**: 152 new (6,477 total)
**Block**: 2 (first phase)

## Overview

Wired all post-MVP standalone engines (EW, Space, CBRN, Schools, Commander, Era, Escalation) into ScenarioLoader so a scenario YAML alone produces a fully-connected simulation. Fixed the broken OODA DECIDE path (assessment=None, personality=None). Integrated EW engines into the tick loop. No new engines or mechanics — only wiring.

## Sub-phases

### 25a: ScenarioLoader Auto-Wiring (61 tests)

**Modified**: `simulation/scenario.py`, `c2/ai/schools/__init__.py`

- Added 5 new config blocks to `CampaignScenarioConfig`: `ew_config`, `space_config`, `cbrn_config`, `school_config`, `commander_config`
- Added 4 new fields to `SimulationContext`: `commander_engine`, `eccm_engine`, `sigint_engine`, `ew_decoy_engine`
- Extended `_create_engines()` → `_create_optional_engines()` with 7 sub-methods:
  - `_create_ew_engines()` — JammingEngine, ECCMEngine, SIGINTEngine, EWDecoyEngine
  - `_create_space_engines()` — Full SpaceEngine hierarchy (GPS, ISR, EW, SATCOM, ASAT)
  - `_create_cbrn_engines()` — CBRNEngine + all sub-engines (dispersal, contamination, protection, casualty, decon, nuclear)
  - `_create_school_engines()` — SchoolRegistry with all 9 schools via factory
  - `_create_commander_engine()` — CommanderEngine + profile loading
  - `_create_escalation_engines()` — All 9 escalation/unconventional engines
  - `_create_era_engines()` — WW2, WW1, Napoleonic, Ancient engine sets
- Added `create_school()` factory function to `c2/ai/schools/__init__.py` with `_SCHOOL_ID_TO_CLASS` mapping

### 25d: CommanderEngine Wiring (22 tests)

**Modified**: `simulation/scenario.py`, `simulation/battle.py`

- Added `_apply_commander_assignments()` to ScenarioLoader: side-level defaults first, then per-unit overrides
- Wired `commander_engine.get_ooda_speed_multiplier()` into battle loop OODA phase advancement (stacks with school multiplier)

### 25b: Battle Loop OODA Fix (34 tests)

**Modified**: `simulation/battle.py`

- Added `_cached_assessments` dict to BattleManager (transient, not checkpointed)
- OBSERVE phase now uses real morale (MoraleState → 0.0–1.0 mapping) and real supply (StockpileManager.get_supply_state())
- OBSERVE caches assessment for DECIDE retrieval
- DECIDE retrieves cached assessment + commander personality, builds real assessment_summary for school adjustments
- Added `_get_unit_morale_level()`, `_get_unit_supply_level()`, `_build_assessment_summary()` helper methods
- Opponent modeling now uses real force counts

### 25c: Tick Loop Integration (34 tests)

**Modified**: `simulation/engine.py`, `simulation/battle.py`

- Added `strict_mode` parameter to SimulationEngine (default False)
- Replaced 6 bare `except Exception: pass` blocks with `logger.error(exc_info=True)` + conditional re-raise in strict mode
- Added `_update_ew()` method: calls `ew_engine.update(dt)` and `ew_decoy_engine.update(dt)` when present
- Wired insurgency with real military presence (active unit counts per side) and collateral data (from consequence engine)
- Added MOPP speed factor in `_execute_movement()`: queries CBRN engine `_mopp_levels`, applies `ProtectionEngine.get_mopp_speed_factor()`

## Files Changed

### Modified (5 source files):
1. `stochastic_warfare/simulation/scenario.py` — Config blocks, context fields, engine creation, commander assignments
2. `stochastic_warfare/simulation/battle.py` — Assessment cache, real OODA wiring, MOPP speed, commander OODA mult
3. `stochastic_warfare/simulation/engine.py` — strict_mode, bare except fix, EW update, insurgency data
4. `stochastic_warfare/c2/ai/schools/__init__.py` — SCHOOL_ID_TO_CLASS mapping + create_school() factory
5. `tests/unit/test_phase_19e_integration.py` — Added `commander_engine=None` to mock context

### New (4 test files):
1. `tests/unit/test_phase_25a_scenario_wiring.py` (61 tests)
2. `tests/unit/test_phase_25b_ooda_fix.py` (34 tests)
3. `tests/unit/test_phase_25c_tick_loop.py` (34 tests)
4. `tests/unit/test_phase_25d_commander_wiring.py` (22 tests)

## Key Patterns

- **Null-config = disabled**: Every optional engine gated by `if config.X_config is not None`. Zero cost when disabled.
- **Lazy imports**: All engine imports inside factory methods to avoid circular dependencies.
- **Safe attribute access**: `getattr(ctx, "cbrn_engine", None)` in battle.py for backward compatibility with SimpleNamespace test mocks.
- **Assessment cache is transient**: Not checkpointed — rebuilt each OBSERVE cycle.
- **Strict mode for debugging**: `strict_mode=True` re-raises all engine errors instead of swallowing them.

## Deficits Resolved

| Deficit | Description |
|---------|-------------|
| 1.1 | ScenarioLoader auto-wiring |
| 1.2 | CommanderEngine not on SimulationContext |
| 1.3 | battle.py assessment=None |
| 1.5 | MOPP speed factor never passed |
| 1.6 | Era engines not wired |
| 1.7 | Bare except in engine.py |
| 2.8 | COA weight overrides not called (school adjustments now use real data) |
| 4.13 | Insurgency needs real data |
| 5.1 | EW engines not wired into tick loop |

## Known Limitations

- **Air campaign ATO wiring** (deficit 1.4): Not addressed — would require air campaign engine to expose an ATO planning interface. Deferred to future phase.
- **C2 effectiveness always 1.0**: Assessment c2_effectiveness is still hardcoded; requires comms quality integration.
- **Consequence engine collateral**: `get_collateral_by_region()` may not exist on all ConsequenceEngine implementations — gracefully handled with try/except.
- **Stratagem affinity wiring**: Planned in 25b but not implemented. `get_stratagem_affinity()` is not called during DECIDE phase. Deferred.
- **School_id auto-assignment**: Planned in 25d but not implemented. `CommanderPersonality.school_id` does not auto-assign to SchoolRegistry. Deferred.

## Postmortem

### Scope: On Target (with 2 silently dropped items)

- **151 tests planned, 152 delivered** (1 extra: checkpoint cache clear test added in postmortem)
- **9 deficits resolved** (1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 2.8, 4.13, 5.1)
- **1 deficit deferred with documentation** (1.4 — ATO wiring)
- **2 items silently dropped** (stratagem affinity, school_id auto-assignment) — now documented above

### Quality: High

- All new methods have type hints. No bare `print()`. `get_logger(__name__)` everywhere.
- No TODO/FIXME/HACK in any modified source file.
- Null-config=disabled pattern applied consistently across all 7 engine groups.
- Safe `getattr(ctx, ..., None)` for backward compat — prevented 12 test regressions.

### Integration: Fully Wired (no gaps)

- `create_school()` called from `_create_school_engines()` ✓
- `_update_ew()` called in tick loop via `_update_environment()` ✓
- `_apply_commander_assignments()` called in `load()` step 9 ✓
- ECCM/SIGINT engines are stateless query engines — no `update()` needed (not a gap)
- JammingEngine also stateless — `hasattr` guard correctly skips tick call
- Only EWDecoyEngine has time-dependent state and is correctly ticked

### Deficits: 1 fixed in postmortem, 2 documented, 0 new unresolved

- **Fixed**: `_cached_assessments` not cleared in `set_state()` — added 1-line clear + test
- **Documented**: Stratagem affinity wiring and school_id auto-assignment added to Known Limitations
- **Pre-existing hardcoded values** (target_size=8.5, fuel_rate=10.0, echelon=5, auto_resolve params, insurgency economic_factor=0.5) are all assigned to Phase 26b (Configurable Constants) — not Phase 25 scope

### Test Quality Notes

- **Hardcoded count fragility**: `test_escalation_engine_count` uses `len(result) == 9`, `test_school_registry_created` uses `len(all_schools()) == 9`. Will break when new engines/schools are added. Acceptable for now — these are Phase 25 tests verifying Phase 25 wiring of exactly 9 known items.
- **Private attribute access in tests**: Tests check `engine._config`, `engine._dispersal`, etc. This is necessary for construction-verification tests but creates coupling. Acceptable for wiring tests.
- **All tests fast**: No `@pytest.mark.slow` needed. Full Phase 25 suite runs in <1s.

### Performance: No Regression

- Full suite: 6,477 tests in ~102s (consistent with pre-Phase-25 baseline)
- Phase 25 tests add <1s total

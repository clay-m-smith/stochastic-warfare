# Phase 85: LOD & Aggregation

**Block**: 9 (Performance at Scale)
**Status**: Complete
**Tests**: 30 (18 LOD tiering + 6 integration + 6 aggregation order preservation)

## Overview

Reduces effective unit count by classifying units into resolution tiers (ACTIVE/NEARBY/DISTANT) with different update frequencies. Activates the existing aggregation engine with order preservation through aggregate/disaggregate roundtrips.

## What Was Built

### 85a: Unit Resolution Tiers (`simulation/battle.py`)

- **`UnitLodTier`** IntEnum: ACTIVE=0, NEARBY=1, DISTANT=2
- **`_classify_lod_tiers()`** method on BattleManager:
  - Classifies each unit based on distance to nearest enemy
  - ACTIVE: within 2x max weapon range (engagement zone)
  - NEARBY: within max sensor range (detection zone)
  - DISTANT: beyond sensor range (background zone)
  - Hysteresis: immediate promotion, delayed demotion (3 ticks default)
  - First-time classification assigns raw tier directly (no hysteresis delay)
  - Instant promotion: unit takes damage or detects contact within weapon range
- **Scheduler-based update frequency**:
  - ACTIVE: every tick
  - NEARBY: every 5 ticks (configurable `lod_nearby_interval`)
  - DISTANT: every 20 ticks (configurable `lod_distant_interval`)
- **Battle loop integration** — LOD gates:
  - FOW detection: skips units not in `_lod_full_update`
  - Morale degradation: ACTIVE units only (ROUTING always checked)
  - Supply consumption: gated by `_lod_full_update`
  - Engagement initiation: only full-update units can fire
  - Movement: NOT gated (all tiers move every tick)
- **Checkpoint support**: `_lod_tiers`, `_lod_pending_tiers`, `_lod_pending_counts`, `_lod_promoted` in get_state/set_state

### 85b: Aggregation Order Preservation (`simulation/aggregation.py`)

- **`order_records`** field on `UnitSnapshot`: captures active + pending orders before aggregation
- **`snapshot_unit()`**: reads `ctx.order_execution` records, serializes to list of dicts
- **`disaggregate()`**: restores `OrderExecutionRecord` objects from snapshots
- **`get_state()/set_state()`**: includes `order_records` in serialization

### 85c: CalibrationSchema (`simulation/calibration.py`)

- `enable_lod: bool = False` — opt-in flag (default off for backward compat)
- `lod_nearby_interval: int = 5` — NEARBY update frequency
- `lod_distant_interval: int = 20` — DISTANT update frequency
- `lod_hysteresis_ticks: int = 3` — ticks before tier downgrade

## Key Design Decisions

1. **Movement never gated**: All units move every tick regardless of tier. Skipping movement would cause spatial discontinuities when units transition tiers.
2. **First-time classification skips hysteresis**: New units get their raw tier immediately. Without this, every unit starts as ACTIVE (the default) and must wait 3 ticks to demote, defeating the purpose for initial classification.
3. **Engagement asymmetry**: DISTANT units cannot initiate fire but CAN be targeted. LOD reduces compute for the attacker selection loop, not target selection.
4. **Order preservation via snapshot**: Orders are captured as serialized dicts (not live references) to survive the aggregate→disaggregate roundtrip.
5. **`enable_lod=False` default**: LOD changes simulation behavior (reduced update frequency), so it must be opt-in per scenario after recalibration.

## Files Changed

### Modified (3 source + 1 test)
- `stochastic_warfare/simulation/battle.py` — UnitLodTier enum, _classify_lod_tiers(), LOD gates in battle loop, checkpoint state
- `stochastic_warfare/simulation/calibration.py` — 4 CalibrationSchema fields
- `stochastic_warfare/simulation/aggregation.py` — order_records on UnitSnapshot, snapshot/restore/serialization
- `tests/validation/test_phase_67_structural.py` — `enable_lod` in `_DEFERRED_FLAGS`

### New (3 test + 1 devlog)
- `tests/unit/test_phase85_lod_tiering.py` — 18 tests
- `tests/unit/test_phase85_integration.py` — 6 tests
- `tests/unit/test_phase85_aggregation.py` — 6 tests (order snapshot/serialization)
- `docs/devlog/phase-85.md`

## Accepted Limitations

- `enable_lod` deferred (in `_DEFERRED_FLAGS`) until Phase 91 recalibration.
- LOD tier thresholds are per-unit (max weapon/sensor range), not global. Units with very long-range sensors will have larger NEARBY zones.
- No integration with Phase 85b aggregation in the engine loop yet (`engine.py` wiring deferred to when `enable_aggregation` is exercised).
- 1000-unit benchmark not yet validated (no 1000-unit scenario exists; LOD targeting Golan Heights 290-unit performance).

## Postmortem

- **Scope**: Slightly under — 85a fully delivered, 85b partially (order preservation done, engine.py wiring deferred), 85c deferred. Plan estimated ~30 tests; actual is 30.
- **Quality**: High — unit tests cover tier boundaries, hysteresis, scheduling, promotion, checkpoint roundtrip, backward compat. Integration tests verify LOD gates in engagement/morale/supply paths.
- **Integration**: Partially wired — LOD is integrated into battle.py tick loop. Aggregation order preservation works standalone. Engine.py campaign-tick wiring not done (85b plan item).
- **Deficits**: 2 new items logged — (1) aggregation engine.py wiring deferred, (2) 1000-unit benchmark not validated.
- **Action items**: None blocking. Deferred items tracked in refinement index.
- **Bugs fixed during testing**: (1) first-time tier classification triggered hysteresis, defaulting all new units to ACTIVE for 3 ticks — fixed with `is_new` check; (2) test mock `get_state()` incomplete for `Unit.set_state()` roundtrip — fixed with full state dict including `int()` serialization matching real Unit; (3) engagement test mocks missing `ctx.config` and `ctx.engagement_engine` — added to SimpleNamespace.
- **Plan deviation**: Used numpy distance calculation instead of Phase 84 STRtree for tier classification — simpler and sufficient for the classification step which only needs nearest-enemy distance.

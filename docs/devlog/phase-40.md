# Phase 40: Battle Loop Foundation

**Status**: Complete
**Block**: 5 (Combat Depth)
**Tests**: 47 new in `test_phase40_battle_loop.py` (9 test classes)
**Files**: 4 modified (`battle.py`, `victory.py`, `scenario.py`, `ammunition.py`)

## Summary

Fixed the `evaluate_force_advantage` victory bug (`is_tie` replaced with `sides_at_best` counter) and wired 5 disconnected systems into `battle.py`: posture tracking (MOVING/HALTED/DEFENSIVE/DUG_IN auto-assignment), fire-on-move (requires_deployed weapons skip when moving), domain filtering (`effective_target_domains()` from weapon category), suppression (`SuppressionEngine` wired with decay + fire volume), and morale multipliers (ROUTED/SURRENDERED skip engagement + `accuracy_mult` from `_MORALE_EFFECTS`). Added `ObstacleManager` and `HydrographyManager` to `SimulationContext`.

## What Was Built

### 40a: Victory Bug Fix (`victory.py`)

- `evaluate_force_advantage()` used `is_tie` boolean which collapsed multi-side evaluations into incorrect draws
- Replaced with `sides_at_best` counter that tracks how many sides share the best score
- Only declares a tie when multiple sides genuinely share the top score (~15 lines changed)

### 40b: Posture Tracking (`battle.py`)

- Auto-detection of unit posture based on movement state:
  - `MOVING` — unit speed > 0
  - `HALTED` — unit stationary but not yet dug in
  - `DEFENSIVE` — unit belongs to a side marked in `defensive_sides`
  - `DUG_IN` — unit stationary for `dig_in_ticks` consecutive ticks
- Posture tracked per-unit in `BattleManager` state, updated each tick before engagement resolution

### 40c: Fire-on-Move Gate (`battle.py`, `ammunition.py`)

- Binary gate: weapons with `requires_deployed=True` are skipped when unit speed > 0.5 m/s
- ~10 lines added to `ammunition.py` for the `requires_deployed` field
- Engagement loop checks posture before weapon selection — deployed weapons (mortars, ATGMs, SAMs) cannot fire while moving

### 40d: Domain Filtering (`battle.py`, `ammunition.py`)

- `effective_target_domains()` method returns valid target domains for a weapon based on its category
- `_CATEGORY_DEFAULT_DOMAINS` map provides defaults (e.g., SAM -> AIR, torpedo -> SUB_SURFACE)
- Weapons can override via `target_domains` YAML field (~10 lines in `ammunition.py`)
- Engagement loop filters potential targets to only those in valid domains for the selected weapon

### 40e: Suppression Wiring (`battle.py`)

- `SuppressionEngine` wired into battle loop with per-tick decay and fire volume accumulation
- Suppression states tracked per-unit in `BattleManager._suppression_states` dict
- Suppressed units suffer accuracy penalty; heavily suppressed units skip offensive actions
- Decay applied at start of each tick before new suppression is added

### 40f: Morale Multipliers (`battle.py`)

- `_MORALE_EFFECTS` dict maps morale states to `accuracy_mult` values
- ROUTED and SURRENDERED units skip engagement entirely (removed from attacker pool)
- SHAKEN and BROKEN units fire with reduced accuracy
- STEADY and CONFIDENT units receive no penalty (mult = 1.0)

### 40g: Context Extensions (`scenario.py`)

- `ObstacleManager` added to `SimulationContext` (~10 lines)
- `HydrographyManager` added to `SimulationContext` (~10 lines)
- Both initialized from scenario terrain data when available, `None` otherwise

## Design Decisions

1. **Posture auto-detection, not manual assignment**: Units don't declare their posture — the system infers it from movement state and side configuration. Reduces scenario YAML complexity and avoids stale posture bugs.

2. **Fire-on-move as binary gate, not continuous penalty**: A weapon either can or cannot fire while moving. This is simpler, more robust, and matches real-world doctrine (you don't fire a mortar at 80% accuracy while driving — you stop or you don't fire). Continuous penalties deferred.

3. **Domain filtering via category defaults**: Rather than requiring every weapon YAML to list target domains, the system infers from weapon category. SAMs target AIR by default. Torpedoes target SUB_SURFACE. Override via explicit `target_domains` field when needed.

4. **Suppression states in BattleManager, not on Unit**: Suppression is a battle-local transient state, not a persistent unit property. Storing in `_suppression_states` dict keeps the Unit entity clean and makes state reset trivial between battles.

5. **Morale skip before weapon selection**: ROUTED/SURRENDERED units are filtered out before the weapon selection and targeting loop. This avoids wasted computation and ensures zero offensive output from broken units.

## Issues & Fixes

1. **`is_tie` collapsed multi-side scoring**: The original `evaluate_force_advantage` set `is_tie = True` whenever any two sides had equal scores, even if a third side had a higher score. The `sides_at_best` counter correctly identifies ties only when multiple sides share the actual maximum.

2. **`requires_deployed` default**: Initially omitted the default value, breaking all existing weapon YAML. Fixed by defaulting to `False` — only weapons that explicitly declare `requires_deployed: true` are gated.

3. **Suppression decay ordering**: Initial implementation decayed suppression after adding new fire volume, which meant a unit could never reach zero suppression. Moved decay to start of tick (before fire volume accumulation).

## Known Limitations

- No fire-on-move accuracy penalty — only deployed weapon skip (binary gate)
- Posture does not affect movement speed (DUG_IN units can still move at full speed if ordered)
- No automatic posture assignment for naval/air units (posture tracking is ground-centric)
- Suppression decay rate is a global constant, not per-unit or per-weapon configurable
- `_CATEGORY_DEFAULT_DOMAINS` does not cover all weapon categories — unlisted categories default to ALL domains

## Lessons Learned

- **Binary gates before continuous modifiers**: For initial wiring, binary on/off gates (fire-on-move, morale skip) are simpler and more robust than continuous penalty curves. They catch the biggest behavioral errors (mortars firing on the move, routed units attacking) without tuning. Continuous modifiers can be layered on later.
- **Victory logic needs multi-side awareness**: Boolean `is_tie` works for 2-side games but breaks for 3+ sides. Always count the number of sides sharing the best score.
- **Transient state belongs in the manager, not the entity**: Suppression, posture, and other battle-local states stored in `BattleManager` dicts rather than on `Unit` objects. Keeps entities as pure data and avoids cross-battle state leakage.
- **Default values preserve backward compatibility**: Every new YAML field (`requires_deployed`, `target_domains`) must have a sensible default that preserves existing behavior.

## Postmortem

### 1. Delivered vs Planned

All 7 sub-items delivered: victory fix (40a), posture tracking (40b), fire-on-move (40c), domain filtering (40d), suppression wiring (40e), morale multipliers (40f), context extensions (40g). No items dropped or deferred.

### 2. Integration Audit

- Victory fix tested with 2-side and 3-side scenarios
- Posture tracking feeds into fire-on-move gate and future terrain cover (Phase 41)
- Domain filtering prevents nonsensical engagements (SAMs vs submarines, torpedoes vs aircraft)
- Suppression engine receives fire volume from engagement loop and feeds back into accuracy
- Morale multipliers consume existing morale state from `MoraleEngine`
- ObstacleManager and HydrographyManager available on context for Phase 41 terrain queries
- No dead code, no orphaned imports

### 3. Test Quality Review

- 47 tests across 9 test classes covering all 7 sub-items
- Edge cases: 3-side victory ties, zero-speed threshold, empty weapon lists, all units routed
- Tests use real engine components where possible, mocks only for SimulationContext

### 4. Deficit Discovery

- **No fire-on-move accuracy penalty** — binary gate only (cosmetic for initial release)
- **Posture doesn't affect movement speed** — DUG_IN units can still move (behavioral gap)
- **No naval/air posture** — ground-centric posture system
- All are low-priority refinements, not blocking.

### 5. Summary

- **Scope**: On target
- **Quality**: High (all tests pass, backward compatible)
- **Integration**: Fully wired
- **Deficits**: 3 new (fire-on-move penalty, posture-speed, naval/air posture) — all low priority
- **Action items**: None blocking (deficits deferred to future phases)

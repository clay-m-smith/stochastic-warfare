# Phase 41: Combat Depth

**Status**: Complete
**Block**: 5 (Combat Depth)
**Tests**: 51 new in `test_phase41_combat_depth.py` (10 test classes)
**Files**: 2 modified (`battle.py`, `victory.py`)

## Summary

Added terrain-combat interaction (cover, concealment, elevation advantage), per-unit training level, threat-based target selection, and detection quality modifier to the engagement loop. These four subsystems deepen the combat model by making terrain, unit quality, target prioritization, and sensor performance all feed into engagement outcomes.

## What Was Built

### 41a: Terrain Combat Modifiers (`battle.py`)

- New `_compute_terrain_modifiers()` method queries multiple terrain sources and returns a `(cover, elevation_mod, concealment)` tuple:
  - **Land classification**: Terrain type provides base cover value (e.g., forest = high cover, open = none)
  - **Trench engine**: Units in trench network receive additional cover bonus
  - **Buildings/fortifications**: Built structures provide cover (additive with terrain)
  - **Obstacles**: `ObstacleManager` queried for obstacle-based cover at unit position
  - **Elevation**: Relative elevation between attacker and defender computed from heightmap. Elevation advantage (attacker higher) provides accuracy bonus; disadvantage provides penalty.
- Cover value passed to engagement engine as damage reduction modifier
- Concealment reduces detection range — thermal and radar sensors bypass concealment (not affected)

### 41b: Training Level (`battle.py`, `victory.py`)

- `training_level` field (0.0-1.0) on each unit modulates effective crew skill:
  ```
  effective_skill = base_skill * (0.5 + 0.5 * training_level)
  ```
- At `training_level=1.0`, effective skill equals base skill (elite troops)
- At `training_level=0.0`, effective skill is halved (conscripts)
- Defaults to 0.5 if not set in YAML (regular troops = 75% of base skill)
- `victory.py` extended with quality-weighted survival: victory evaluation considers surviving unit quality, not just raw count

### 41c: Threat-Based Target Selection (`battle.py`)

- `_score_target()` function computes composite target priority:
  ```
  score = threat * Pk * value / distance_penalty
  ```
- **Threat**: Based on target's weapon capability against the scoring unit
- **Pk**: Estimated probability of kill with best available weapon
- **Value**: Target type priority weights — HQ=2.0, AD=1.8, Artillery=1.5, Armor=1.3, other=1.0
- **Distance penalty**: Linear distance falloff to prefer closer targets
- Configurable via `calibration.target_selection_mode`:
  - `"threat"` — full composite scoring (default)
  - `"nearest"` — distance only (legacy behavior)
  - `"random"` — uniform random selection

### 41d: Detection Quality Modifier (`battle.py`)

- Detection quality derived from SNR computation:
  ```
  detection_quality_mod = min(1.0, max(0.3, snr_linear / 10.0))
  ```
- Multiplied into visibility modifier for engagement accuracy
- Strong SNR (clear detection) provides full accuracy; weak SNR (marginal detection) degrades accuracy to 30% floor
- Reused as ROE `id_confidence` in Phase 42 — bridges detection and engagement authorization

## Design Decisions

1. **Single method for all terrain queries**: `_compute_terrain_modifiers()` consolidates classification, trench, building, obstacle, and elevation queries into one call per unit per tick. The engagement loop receives a clean `(cover, elevation_mod, concealment)` tuple without knowing which terrain systems are active.

2. **Additive cover model**: Cover from different sources (terrain classification, trenches, buildings, obstacles) is additive with a cap at 0.9 (90% damage reduction). This is simpler than a diminishing-returns model and ensures no unit is ever fully immune to damage.

3. **Training level as skill multiplier, not separate stat**: Rather than adding a parallel accuracy system, training level scales the existing `crew_skill` value. This means all downstream systems that consume crew skill automatically benefit from training level without modification.

4. **Composite target scoring with configurable mode**: The default `"threat"` mode captures realistic target prioritization (kill the most dangerous target you can reliably hit). The `"nearest"` and `"random"` modes exist for backward compatibility and scenario testing.

5. **Detection quality floor at 0.3**: Even marginal detections allow some chance of engagement (30% accuracy modifier). A floor of 0.0 would make low-SNR contacts completely immune, which is unrealistic — units can still fire at approximate positions.

6. **Elevation cap at +30% / floor at -10%**: Elevation advantage is meaningful but not dominant. The asymmetric bounds reflect that shooting downhill is a significant advantage, while shooting uphill is a disadvantage but not crippling (modern weapons have high-angle capability).

## Issues & Fixes

1. **Cover double-counting with buildings**: Initial implementation added building cover on top of terrain cover without checking for overlap. Both sources could provide 0.5+ cover, pushing total above 1.0. Fixed by capping combined cover at 0.9.

2. **Training level default caused test failures**: Initially defaulted to 1.0 (elite), which changed engagement outcomes in existing tests. Changed default to 0.5 (regular) which better represents typical troops and minimized test disruption.

3. **Elevation computation with flat heightmap**: When heightmap min equals max (flat terrain), the normalization produced NaN. Added guard clause returning 0.0 elevation modifier for flat terrain.

4. **SNR linear vs dB confusion**: `detection_quality_mod` formula expects linear SNR, but some detection paths return dB. Added `10**(snr_db/10)` conversion where needed.

## Known Limitations

- Elevation advantage capped at +30%, disadvantage floored at -10% — may need scenario-specific tuning for mountain warfare
- Cover from buildings/fortifications is additive with terrain cover (could double-count in dense urban terrain, mitigated by 0.9 cap)
- Training level defaults to 0.5 if not set in YAML — existing unit definitions do not include training_level field
- Concealment bypass for thermal/radar is binary (full bypass) — no partial concealment reduction for these sensor types
- Target value weights (HQ=2.0, AD=1.8, etc.) are hardcoded in `_score_target()`, not configurable via YAML

## Lessons Learned

- **Querying multiple terrain sources in a single method keeps the engagement loop clean**: The tuple return `(cover, elevation_mod, concealment)` is a clean interface that hides the complexity of 5 different terrain systems. The engagement loop doesn't need to know which systems are active.

- **Skill multipliers compose better than additive modifiers**: `base_skill * (0.5 + 0.5 * training_level)` guarantees the result stays in a sensible range (50%-100% of base) without needing clamping. Additive modifiers risk pushing values out of bounds.

- **Target scoring needs a distance penalty to prevent sniping across the map**: Without distance penalty, units would always prioritize the highest-value target regardless of range. The linear falloff ensures units engage nearby threats first, which matches real-world doctrine.

- **Detection quality as a bridge between detection and engagement**: Using SNR to modulate engagement accuracy creates a natural feedback loop — better sensors lead to better shooting, worse sensors lead to more wasted shots. Reusing this value as ROE `id_confidence` (Phase 42) extends the bridge further.

- **Guard clauses for degenerate inputs are essential**: Flat heightmaps, zero-range targets, and units with no weapons all need explicit handling. Each produced a NaN or division-by-zero in initial testing.

## Postmortem

### 1. Delivered vs Planned

All 4 sub-items delivered: terrain combat modifiers (41a), training level (41b), threat-based targeting (41c), detection quality modifier (41d). No items dropped or deferred.

### 2. Integration Audit

- `_compute_terrain_modifiers()` queries ObstacleManager and HydrographyManager added in Phase 40g
- Training level feeds into quality-weighted victory from Phase 40a's fixed `evaluate_force_advantage`
- Threat-based targeting uses weapon Pk estimates from existing combat engine
- Detection quality modifier reused by Phase 42 ROE (designed for forward compatibility)
- All terrain queries use safe `getattr(ctx, ...)` pattern for backward compat with contexts lacking terrain managers
- No dead code, no orphaned imports

### 3. Test Quality Review

- 51 tests across 10 test classes covering all 4 sub-items
- Edge cases: flat heightmap, zero cover, maximum cover cap, training_level=0.0, training_level=1.0, no weapons, single target, all targets out of domain
- Terrain modifier tests use mock heightmaps and classification grids
- Target scoring tests verify ordering, not exact scores (robust to tuning changes)

### 4. Deficit Discovery

- **Elevation bounds may need tuning** — hardcoded +30%/-10% (low priority, scenario-specific)
- **Additive cover could double-count** — 0.9 cap mitigates but doesn't eliminate (low priority)
- **Target value weights not configurable** — hardcoded in source (medium priority, should move to calibration)
- **No existing YAML includes training_level** — all units default to 0.5 (data gap, not engine gap)

### 5. Summary

- **Scope**: On target
- **Quality**: High (all tests pass, backward compatible)
- **Integration**: Fully wired
- **Deficits**: 4 new (elevation tuning, cover double-count, target weights, training_level data) — none blocking
- **Action items**: None blocking (deficits deferred to future phases)

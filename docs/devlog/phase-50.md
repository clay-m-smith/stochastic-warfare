# Phase 50: Combat Fidelity Polish

## Summary

Second phase of Block 6. Wired posture to movement speed (D1), added air tactical posture (D3), implemented continuous concealment decay (D4), populated training level data across all 133 unit YAMLs (D14), fixed WW1 barrage fire-on-move penalty (D7), and made target value weights calibration-overridable. 5 deficits resolved. 40 new tests. 4 scenario recalibrations for outcome stability.

## What Was Built

### 50a: Posture Affects Movement Speed
- **`stochastic_warfare/simulation/battle.py`** -- `_POSTURE_SPEED_MULT` constant: MOVING/HALTED=1.0x, DEFENSIVE=0.5x, DUG_IN/FORTIFIED=0.0x
- `_undigging` dict tracks 2-tick un-dig transition: tick 1 resets posture to MOVING and skips movement, tick 2 allows normal movement
- Defensive-side units with DUG_IN/FORTIFIED stay put (no un-dig triggered)

### 50b: Air Unit Posture
- **`stochastic_warfare/entities/unit_classes/aerial.py`** -- `AirPosture` IntEnum: GROUNDED(0), INGRESSING(1), ON_STATION(2), RETURNING(3). Orthogonal to `FlightState` (physical flight phase).
- `air_posture` field on `AerialUnit` with get_state/set_state round-trip and backward compat
- **`stochastic_warfare/simulation/battle.py`** -- Engagement gate skips GROUNDED/RETURNING aircraft. Auto-assignment: GROUNDED aircraft at FlightState.GROUNDED, fuel < 0.2 -> RETURNING, otherwise ON_STATION.
- **`stochastic_warfare/entities/loader.py`** -- Aerial units spawn as AIRBORNE/ON_STATION by default (proper approach vs heuristic)

### 50c: Continuous Concealment
- **`stochastic_warfare/simulation/battle.py`** -- `_concealment_scores` dict tracks persistent per-target concealment
  - Initialized from terrain baseline
  - Decays by `observation_decay_rate` (default 0.05) per tick of sustained observation
  - Moving targets reset to terrain * 0.5 (harder to stay hidden while moving)
  - Thermal/radar sensors get 0.3x concealment effect
  - Engagement blocked when concealment > `engagement_concealment_threshold` (default 0.5)
- **`stochastic_warfare/simulation/calibration.py`** -- 3 new fields: `observation_decay_rate`, `engagement_concealment_threshold`, `target_value_weights`

### 50d: Training Level Data Population
- **133 unit YAML files** -- All files in `data/units/` and `data/eras/*/units/` got `training_level` field
  - Elite (0.9): M1A2, F-22, SAS, Patriot, Iron Beam, French Old Guard
  - Veteran (0.8): Leopard 2A6, F-16C, MQ-9, Roman legionary, Ranger platoon
  - Regular (0.7): Bradley, infantry squads, artillery, T-90A
  - Green (0.6): MiG-29A, J-10A, BMP-2
  - Conscript (0.5): Militia, insurgent, medieval levy
  - Poor (0.3-0.4): Ancient levy, civilian noncombatant

### 50e: Barrage Penalty Fix, Target Weights, Melee Range
- **`stochastic_warfare/simulation/battle.py`** -- Early weapon category computation: indirect fire categories (HOWITZER/MORTAR/ARTILLERY) exempt from fire-on-move penalty
- **`stochastic_warfare/simulation/battle.py`** -- `_score_target()` reads `target_value_weights` from CalibrationSchema. Custom weights override BattleConfig defaults.
- All melee weapons verified to have max_range_m within _MELEE_RANGE_M (10.0m)

## Design Decisions

1. **Posture speed as module-level constant dict**: Simple lookup table indexed by posture IntEnum value. DUG_IN/FORTIFIED at 0.0x means units must un-dig before moving.
2. **2-tick un-dig delay**: Prevents instant DUG_IN -> MOVING -> full speed. Tick 1 transitions posture, tick 2 allows movement. `_undigging` dict cleared after second tick.
3. **AirPosture orthogonal to FlightState**: FlightState = physical (GROUNDED/AIRBORNE/HOVERING), AirPosture = tactical mission (GROUNDED/INGRESSING/ON_STATION/RETURNING). Aircraft can be AIRBORNE but RETURNING.
4. **Loader sets AIRBORNE/ON_STATION at spawn**: Instead of heuristic `is_fast_platform` check, the entity loader initializes aerial units in operational state. This is the proper approach -- unit creation, not battle loop patching.
5. **Persistent concealment decay**: Replaces stateless per-tick terrain recomputation. Targets build up observation over time, making sustained surveillance more effective than one-tick snapshots.
6. **Training level tiers**: Era-appropriate values based on historical training quality. Elite forces (0.9) have 80% higher effective_skill than conscripts (0.5) via formula `base_skill * (0.5 + 0.5 * training_level)`.

## Deviations from Plan

1. Plan called for modifying `movement/engine.py` -- instead applied posture multiplier directly in `battle.py._execute_movement()` since that's where `effective_speed` is computed.
2. Plan listed `HASTY_DEFENSE` posture -- actual Posture enum uses `DEFENSIVE` (value 2). Used existing enum values.
3. Plan called for modifying `detection/detection.py` for concealment -- instead managed concealment state in `battle.py` directly since that's where engagement decisions are made.
4. Air posture backward compat needed entity loader changes (not in plan) -- without this, all existing scenarios' aircraft would be GROUNDED and unable to engage.

## Issues & Fixes

1. **`execute_tick` signature mismatch**: Tests called with wrong arguments. Fixed to match actual 3-arg signature `(ctx, battle, dt)`.
2. **Air posture blocking all aircraft**: Default `air_posture=GROUNDED` + engagement gate = no aircraft engage. Initial heuristic fix (`is_fast_platform`) replaced with proper loader initialization.
3. **4 scenario outcome regressions**: Concealment changes shifted combat dynamics. Recalibrated Somme, Bekaa Valley, Gulf War EW, Taiwan Strait with adjusted force_ratio_modifiers and observation_decay_rates.
4. **4 missing training level YAML files**: Script had wrong unit_type keys. Manually added missing files.

## Scenario Recalibrations

| Scenario | Change | Rationale |
|----------|--------|-----------|
| Somme July 1 | hit_probability 1.5->1.8, destruction_threshold 0.3->0.25, observation_decay_rate 0.02, german_force_ratio_modifier 1.3 | Concealment decay slowed attrition |
| Bekaa Valley 1982 | blue_force_ratio_modifier 1.5, observation_decay_rate 0.03 | Air posture gate reduced engagement rate |
| Gulf War EW 1991 | blue_force_ratio_modifier 1.5, observation_decay_rate 0.03 | Same as Bekaa |
| Taiwan Strait | blue_force_ratio_modifier 1.8, observation_decay_rate 0.02 | Air posture + concealment combined effect |

## Tests

40 new tests in `tests/unit/test_phase50_combat_fidelity.py`:
- `TestPostureMovementSpeed` (8 tests): Speed multiplier constants, DUG_IN skip, un-dig 2-tick transition, defensive side stays, no-posture fallthrough
- `TestAirPosture` (8 tests): Enum values, default GROUNDED, state roundtrip, backward compat, engagement gates, fuel->RETURNING
- `TestContinuousConcealment` (10 tests): Decay rate, threshold, per-tick decay, never below zero, moving target reset, independent scores, thermal 0.3x
- `TestTrainingLevelPopulation` (6 tests): Spot-checks (M1A2=0.9, infantry=0.7, Roman=0.8), backward compat, all-files scan, skill formula
- `TestBarrageTargetWeightsMelee` (8 tests): Indirect fire categories, target value weights, melee range, schema validation

## Known Limitations

- Air posture auto-assignment is simplified (fuel threshold only, no mission-state awareness)
- Concealment decay rate is global, not per-sensor-type
- Training level values are tier-based estimates, not individually researched per unit

## Lessons Learned

1. **Entity loader is the right place for spawn defaults**: Setting air posture at unit creation avoids battle loop heuristics and ensures all code paths see consistent state.
2. **Concealment as persistent state enables new tactics**: Sustained observation, moving to break concealment, thermal sensor advantage -- all emerge from the decay model.
3. **Scenario recalibration is expected when changing combat mechanics**: Every change to engagement gates, concealment, or movement shifts the dynamic. Build recalibration time into the phase.

## Deficits Resolved

- D1: Posture doesn't affect movement speed (DUG_IN=0x, DEFENSIVE=0.5x)
- D3: Air units have no tactical posture (AirPosture enum + engagement gate)
- D4: Binary concealment (persistent decay + engagement threshold)
- D7: WW1 barrage fire-on-move penalty (indirect fire exempt)
- D14: Training level YAML data missing (133 unit files populated)

## Postmortem

### Scope
**On target.** All 5 planned sub-phases delivered (50a-50e). No items dropped. One unplanned addition: entity loader modification for air posture spawn defaults.

### Quality
**High.** 40 tests with good unit/integration balance. Tests cover edge cases (no-posture units, backward compat, fuel threshold). 2 tests scan all YAML files (test_all_unit_files_have_training_level, test_melee_weapons_within_range) -- these are slightly slow but provide important data coverage guarantees.

### Integration
**Fully wired.** All new code exercised by both tests and scenario runs:
- Posture speed multiplier active in `_execute_movement()` for every tick
- Air posture gate active in engagement loop for every aerial unit
- Concealment state updated and queried every engagement evaluation
- Training level read from YAML by existing `effective_skill` formula
- Barrage exemption applies to all indirect fire weapons

### New Deficits
- Air posture auto-assignment simplified (fuel-only, no mission awareness) -- acceptable for current scope
- Concealment decay rate global not per-sensor -- could be refined in future phase
- No new blocking deficits introduced

### Action Items
None. All documentation updated in this commit.

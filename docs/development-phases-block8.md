# Stochastic Warfare -- Block 8 Development Phases (68--82)

## Philosophy

Block 8 is the **depth completion block**. A post-Block-7 audit reveals a new systemic pattern: **structural wiring without behavioral depth**. Block 7 successfully connected 21 `enable_*` flags and 36 environment parameters, but many engines follow a "log but don't act" pattern — results are computed and logged, but never enforce consequences. Gates are checked but not blocking. Orders are issued but execute instantly. Fire zones exist but deal no damage. Historical scenarios produce the right winner via the wrong victory condition.

This block enforces every consequence, closes every deferred integration gap, adds unit test coverage for every combat engine, eliminates O(n^2) performance hot paths, fixes historical scenario semantics, hardens the API for concurrent use, brings the frontend to WCAG 2.1 AA compliance, and establishes CI/CD automation.

**Exit criteria**:
1. Every gate that checks a condition also enforces it (fuel, ammo, readiness, comms)
2. Every computed result is consumed or the computation is removed
3. All P0/P1 deferred items from Block 7 resolved
4. Unit test coverage for all combat engines and simulation core
5. All historical scenarios produce correct outcomes via decisive combat, not `time_expired`
6. Golan Heights runtime under 120s (from 417s)
7. API schemas and frontend components current with engine state
8. API concurrency bugs fixed; batch semaphore, graceful shutdown
9. Frontend WCAG 2.1 AA for all critical paths (forms, navigation, modals)
10. CI/CD runs Python + frontend tests on every push

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block8.md` (design thinking, audit findings, triage), `devlog/index.md` (deficit inventory), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**No new subsystems**: Block 8 modifies `battle.py`, `engine.py`, `run_manager.py`, frontend components, and CI workflows extensively but creates minimal new source files. The work is enforcing consequences in existing systems, not building new ones.

---

## Phase 68: Consequence Enforcement

**Status**: Complete. 67 tests across 7 test files. 3 source files modified, 0 new source files.

**Goal**: Convert the 7 highest-priority "log but don't act" patterns to actual behavioral enforcement, gated behind `enable_*` flags to prevent regressions.

**Dependencies**: Block 7 complete (Phase 67).

### 68a: Fuel Consumption Enforcement

Uncomment fuel consumption in the movement loop and wire per-vehicle-type consumption rates from unit YAML data.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_movement()`:
  - Uncomment fuel consumption line; compute `fuel_consumed = distance_moved * fuel_rate_per_km`
  - `fuel_rate_per_km` sourced from unit YAML `fuel_consumption_rate` field (default 0.1 for ground, 0.5 for air, 0.05 for naval)
  - Gate behind `enable_fuel_consumption` CalibrationSchema flag (default `False`)
  - When `fuel_remaining <= 0`: halt movement, log warning, set unit speed to 0
- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add `enable_fuel_consumption: bool = False`
- **`stochastic_warfare/entities/base.py`** (modified) -- Ensure `fuel_remaining` property is writable (subtract consumed fuel)

**Tests** (~10):
- Unit moves 10km at rate 0.1/km → fuel reduced by 1.0
- Unit at 0 fuel cannot move (speed forced to 0)
- Air unit consumes fuel at 5x ground rate
- `enable_fuel_consumption=False` → no fuel consumed (backward compat)
- Fuel gate does not affect stationary units (DUG_IN)
- Fuel consumption logged per tick

### 68b: Ammo Depletion Gate

Prevent units from firing when ammunition is exhausted.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`:
  - Before weapon fire: check `weapon.current_ammo > 0` (or equivalent rounds field)
  - If depleted: skip engagement, log `"Ammo depleted for %s — holding fire"`, continue to next target
  - Gate behind `enable_ammo_gate: bool = False` in CalibrationSchema
- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add `enable_ammo_gate: bool = False`

**Tests** (~8):
- Unit with 0 rounds cannot fire
- Unit with 1 round fires, then cannot fire next tick
- `enable_ammo_gate=False` → unit fires regardless (backward compat)
- Ammo depletion logged
- Multi-weapon unit: depleted primary switches to secondary

### 68c: Order Delay Enforcement

Convert logged order delay to an actual delay queue where orders wait before execution.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Add `_pending_orders: list[tuple[float, Order]]` queue:
  - On order issue: compute `delay_s` from OrderPropagationEngine, push `(execute_at_tick, order)` to queue
  - Each tick: pop all orders where `current_time >= execute_at_tick`, execute them
  - Gate behind existing `enable_c2_friction` flag
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Order execution reads from delay queue instead of immediate dispatch

**Tests** (~10):
- Order with 30s delay executes after 30s (not immediately)
- Echelon-3 delay shorter than echelon-5 delay
- `enable_c2_friction=False` → orders execute immediately (backward compat)
- Multiple orders queue correctly (FIFO within same execute_at_tick)
- Order delay sigma produces variation between runs (PRNG-driven)

### 68d: Order Misinterpretation

When `was_misinterpreted=True`, modify the order parameters before execution.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- After misinterpretation roll:
  - If `was_misinterpreted`: apply random perturbation to order target position (offset by `misinterpretation_radius_m`, default 500m)
  - For movement orders: shift destination by random offset
  - For engagement orders: shift target area by random offset
  - Gate behind `enable_c2_friction` flag

**Tests** (~6):
- Misinterpreted order has modified target position (not original)
- Perturbation magnitude scales with `order_misinterpretation_base`
- Non-misinterpreted orders unchanged
- Misinterpretation rate matches configured probability over 100 trials

### 68e: Fire Zone Damage

Apply burn damage to units positioned within active fire zones.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_apply_deferred_damage()` (or new `_apply_fire_damage()`):
  - For each active fire zone: find units within zone bounds
  - Apply `fire_damage_per_tick` (default 0.01 damage_fraction per tick) to each unit in zone
  - Posture protection applies (DUG_IN units in foxholes take less fire damage)
  - Gate behind existing `enable_fire_zones` flag

**Tests** (~8):
- Unit in fire zone takes 0.01 damage per tick
- DUG_IN unit in fire zone takes reduced damage (posture protection)
- Unit outside fire zone takes no fire damage
- Fire zone created from `fire_started=True` DamageResult
- Multiple units in same fire zone all take damage

### 68f: Stratagem Expiry

Add duration tracking to active stratagems so they expire after a configurable time.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Track `stratagem_expiry: dict[str, int]` (stratagem_id → expire_tick):
  - On activation: `expire_tick = current_tick + stratagem_duration_ticks` (default 100 ticks)
  - Each tick: remove expired stratagems, revert decision score bonus
  - Add `stratagem_duration_ticks: int = 100` to CalibrationSchema

**Tests** (~6):
- Stratagem active at tick 0 expires at tick 100
- Expired stratagem's decision score bonus removed
- Custom duration from CalibrationSchema respected
- Multiple concurrent stratagems with different expiry times

### 68g: Guerrilla Retreat Movement

When guerrilla disengage triggers, physically move the unit away from the enemy.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- After unconventional engine evaluates disengage:
  - If disengage triggered: compute retreat vector (away from nearest enemy)
  - Move unit `retreat_distance_m` (default 2000m) along retreat vector
  - Gate behind existing `enable_unconventional_warfare` flag

**Tests** (~6):
- Guerrilla unit that disengages moves 2000m away from nearest enemy
- Retreat direction is opposite to nearest enemy bearing
- Non-guerrilla units do not retreat
- Disengage threshold respected (only triggers below threshold)

### Exit Criteria
- All 7 consequence patterns converted from log-only to behavioral enforcement
- Each enforcement gated behind `enable_*` flag (default off for backward compat)
- All existing scenarios produce identical outcomes with flags off
- ~54 new tests

---

## Phase 69: C2 Depth

**Status**: Complete. 41 tests across 5 test files. 7 source files modified, 0 new source files.

**Goal**: Make the C2 chain produce real effects — ATO limits air tempo, planning results influence decisions, deception injects false information, command hierarchy enforced.

**Dependencies**: Phase 68 (order delay queue infrastructure).

### 69a: ATO Sortie Consumption

Wire `sorties_today` incrementing so the sortie gate actually limits air operations.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- After air unit engagement:
  - Increment `sorties_today` on the ATOPlanningEngine entry for the unit's squadron
  - When `sorties_today >= max_sorties`: prevent further air engagements from that squadron
  - Gate behind `enable_air_routing` flag

**Tests** (~8):
- Air unit flies sortie → `sorties_today` incremented
- Squadron at max_sorties → no further air engagements
- Next day (tick reset) → sorties_today reset to 0
- `enable_air_routing=False` → unlimited sorties (backward compat)

### 69b: Planning Result Injection

Connect MDMP planning output to AI decision-making.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- When PlanningProcessEngine completes MDMP:
  - Extract selected COA from planning result
  - Pass COA posture/objective to OODA DECIDE phase as preferred action
  - Planning result overrides default assessment-based decision when available

**Tests** (~8):
- MDMP completion produces COA that influences next DECIDE cycle
- Planning result prefers offensive COA → AI selects attack posture
- No planning result → AI uses default assessment (backward compat)
- Planning time delay respected (MDMP takes configured duration)

### 69c: Deception & FOW Injection

Active stratagems with deception type inject false force dispositions into enemy FOW.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- When deception stratagem active:
  - Inject phantom contacts into enemy FOW tracker (false unit positions)
  - Phantom contacts have configurable signature (size, type)
  - Phantoms persist for stratagem duration, then removed
  - Gate behind `enable_fog_of_war` flag (deception requires FOW)

**Tests** (~8):
- Active deception stratagem → enemy FOW contains phantom contacts
- Phantom contacts have position offset from real units
- Stratagem expiry → phantoms removed from FOW
- AI assessment counts phantoms as real contacts (inflated enemy estimate)
- `enable_fog_of_war=False` → no deception effect

### 69d: Command Hierarchy Enforcement

When CommandEngine is available, enforce authority checks before order execution.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Before order execution:
  - If `command_engine` available: verify issuing unit has authority over receiving unit
  - Unauthorized orders logged and discarded
  - If `command_engine` is None: skip check (backward compat)

**Tests** (~6):
- Order from parent to subordinate → executes
- Order from peer to peer → rejected (no authority)
- Order from subordinate to parent → rejected
- `command_engine=None` → all orders execute (backward compat)

### 69e: Burned Zone Concealment

Wire `BurnedZone.concealment_reduction` into the detection pipeline.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In concealment computation:
  - Query ObscurantsEngine for burned zones at target position
  - Reduce concealment by `BurnedZone.concealment_reduction` (typically 0.5–0.8)
  - Units in burned terrain are easier to detect (no vegetation cover)

**Tests** (~6):
- Unit in burned zone has reduced concealment
- Detection probability increases for targets in burned terrain
- Unburned terrain concealment unchanged

### Exit Criteria
- ATO sortie gate enforced; planning results consumed; deception injects phantoms
- Command hierarchy prevents unauthorized orders
- Burned zones affect detection
- ~36 new tests

---

## Phase 70: Performance Optimization

**Status**: Complete.

**Goal**: Eliminate O(n^2) hot paths in battle.py. Target: Golan Heights from 417s to <120s.

**Dependencies**: Phases 68–69 (behavioral changes stabilized before optimization).

### 70a: STRtree Nearest-Enemy Query

Replace linear `_nearest_enemy_dist()` with spatial index.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Build per-side STRtree once per tick:
  - At tick start: construct `STRtree` from enemy unit positions (proven pattern from rally/rout)
  - Replace `_nearest_enemy_dist()` O(n) loop with `tree.nearest()` O(log n)
  - Cache tree across calls within same tick; invalidate on tick boundary

**Tests** (~6):
- `_nearest_enemy_dist()` returns identical value before/after optimization
- Full scenario produces identical RNG-deterministic outcome
- Performance benchmark: 290-unit scenario < 120s

### 70b: Unit ID Index

Build `entity_id → Unit` dict for O(1) lookups.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- At tick start:
  - Build `_unit_index: dict[str, Unit]` from all active units
  - Replace all linear searches for parent unit, target unit, etc. with dict lookup
  - Used in data link range check, FOW parent lookup, order routing

**Tests** (~4):
- Parent unit lookup returns same result via dict as via linear search
- Dict rebuilt each tick (accounts for unit destruction)

### 70c: Signature & Calibration Caching

Cache per-scenario values that don't change between ticks.

- **`stochastic_warfare/simulation/battle.py`** (modified):
  - Cache `_get_unit_signature()` results at scenario load (signatures don't change)
  - Cache calibration scalar lookups before per-unit loops (`observation_decay_rate`, etc.)
  - Extract engine references (`roe_engine`, `morale_engine`, etc.) to local variables before engagement loop
  - Pre-cache weapon category → EngagementType mapping at scenario load

**Tests** (~6):
- Cached signature matches fresh lookup
- Cached calibration value matches `.get()` result
- Weapon category cache produces correct EngagementType for all weapon types

### 70d: Performance Verification

End-to-end performance benchmarks.

- **`tests/performance/test_battle_perf.py`** (new) -- Timing-based benchmarks:
  - Golan Heights (290 units, 2000 ticks) < 120s
  - 73 Easting (small scenario) < 10s
  - Taiwan Strait (large scenario) < 300s
  - Assert no scenario is >2x slower than Block 7 baseline

**Tests** (~4):
- Golan Heights benchmark (pytest.mark.slow)
- Regression check: identical outcome hashes before/after optimization

### Exit Criteria
- Golan Heights < 120s (measured in CI-like environment)
- All scenario outcomes identical (deterministic replay verified)
- ~20 new tests

---

## Phase 71: Missile & Carrier Ops Completion

**Status**: Complete. 46 tests across 4 test files. 5 source files modified, 0 new source files.

**Goal**: Close the two largest remaining engine gaps — missile flight-to-impact and carrier air operations. Fix 2 pre-existing bugs.

**Dependencies**: Phase 70 (performance baseline established).

### 71a: Bug Fixes

Fix 2 pre-existing issues discovered during implementation planning.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Move `_sim_time_s` assignment before ATO sortie reset; remove duplicate
- **`stochastic_warfare/combat/engagement.py`** (modified) -- Add missing `launcher_id`/`missile_id` args to COASTAL_DEFENSE and AIR_LAUNCHED_ASHM `launch_missile()` calls

**Tests** (8): Source structure verification, arg presence in 3 engagement types

### 71b: Missile Flight Resolution

Wire `MissileEngine.update_missiles_in_flight()` into battle.py execute_tick.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Per-tick flight update after movement:
  - Advance all active missiles, resolve impacts via CEP dispersion
  - GPS accuracy from SpaceEngine feeds into missile CEP
  - Impact damage applied via `_apply_aggregate_casualties()` to nearest unit within 100m
  - Gated behind `enable_missile_routing` flag

**Tests** (12): Flight mechanics, impact resolution, GPS accuracy, battle loop integration

### 71c: Missile Defense Intercept

Instantiate `MissileDefenseEngine` and wire AD intercept into missile flight update.

- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Add `missile_defense_engine` field to SimulationContext + instantiation
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Per-tick: AD units (SAM/CIWS/MISSILE_LAUNCHER) attempt cruise/BMD intercept on active missiles

**Tests** (12): Instantiation, cruise/BMD intercept, sea-skimming penalty, multilayer defense

### 71d: Carrier Ops Battle Loop

Wire `CarrierOpsEngine` into battle loop for CAP management and sortie rate.

- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add `enable_carrier_ops: bool = False`
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Per-tick carrier ops: CAP updates, sortie rate, Beaufort > 7 gate

**Tests** (14): CAP station, sortie rate, sea state, CalibrationSchema field, battle loop integration

### Exit Criteria
- Missile flight-to-impact resolution functional ✓
- Missile defense intercept functional ✓
- Carrier CAP/sortie/recovery cycle operational ✓
- 46 new tests (vs ~32 planned)

---

## Phase 72: Checkpoint & State Completeness

**Status**: **Complete**. 139 tests across 4 test files. 3 modified source files, 0 new.

**Goal**: Make checkpoint/restore produce identical simulation state by registering all engine state with CheckpointManager.

**Dependencies**: Phase 71 (all engines finalized before checkpointing).

### 72a: Engine State Registration

Register all engines with CheckpointManager so their state is saved/restored.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- After engine instantiation:
  - Call `checkpoint_manager.register(engine_name, engine)` for each engine
  - Engines with get_state/set_state: morale, detection, movement, conditions, comms, fog_of_war, weather, time_of_day, seasons, sea_state, ew, space, cbrn, escalation, unconventional
  - Verify all registered engines implement get_state/set_state correctly

**Tests** (~10):
- Checkpoint after 100 ticks includes all engine states
- Restore from checkpoint → engine state matches tick-100 values
- Round-trip: save → restore → continue → identical to uninterrupted run

### 72b: State Round-Trip Verification

Comprehensive tests ensuring checkpoint restore produces deterministic replay.

- **`tests/validation/test_checkpoint_roundtrip.py`** (new) -- Parametrized across scenarios:
  - Run scenario to tick N → checkpoint → continue to tick 2N → record outcome A
  - Run scenario to tick N → checkpoint → restore → continue to tick 2N → record outcome B
  - Assert A == B (identical outcomes)
  - Run scenario straight to tick 2N → record outcome C
  - Assert A == C (checkpoint didn't change behavior)

**Tests** (~12):
- Round-trip for 3 modern scenarios (73 Easting, Falklands, Golan)
- Round-trip for 2 historical scenarios (Trafalgar, Stalingrad)
- Verify morale, detection tracks, supply levels, equipment status all restored
- Verify RNG state continuity through checkpoint

### 72c: Dead State Cleanup

Remove or mark get_state/set_state implementations that serve no purpose.

- **`stochastic_warfare/`** (multiple files) -- Audit all 136 classes with get_state/set_state:
  - Classes registered with checkpoint: verify implementation correctness
  - Classes NOT registered: add `# UNREGISTERED: state managed by parent` comment or register if appropriate
  - Remove empty get_state implementations that return `{}`

**Tests** (~4):
- Structural test: all registered engines have non-empty get_state
- No engine returns empty dict from get_state when it has internal state

### Exit Criteria
- Checkpoint save includes all engine states
- Checkpoint restore produces identical simulation outcomes
- ~26 new tests

---

## Phase 73: Historical Scenario Correctness

**Status**: Complete. ~22 tests (18 structural + 4 validation). 5 scenario YAMLs modified, 1 doc modified, 1 test file modified, 1 new test file.

**Goal**: Make historical scenarios resolve via historically accurate victory conditions, not `time_expired` clock runout.

**Dependencies**: Phase 72 (engine state stable for scenario testing).

### 73a: Somme Victory Condition Fix

Fix the historically inaccurate Somme 1916 outcome.

- **`data/eras/ww1/scenarios/somme_july1/scenario.yaml`** (modified):
  - Change primary victory condition to `territory_control` (British must capture 50% of German positions)
  - German victory on `time_expired` (successful defense of trench line)
  - Remove `force_destroyed` as primary condition (historically neither side was destroyed)
  - Adjust calibration to produce British failure to break through (historical outcome)
- **`tests/validation/test_historical_accuracy.py`** (modified):
  - Change expected Somme outcome: winner=`german`, condition=`time_expired` (successful defense)
  - Add assertion that victory condition type is NOT `force_destroyed`

**Tests** (~4):
- Somme produces German victory via `time_expired` (defense held)
- British forces do NOT capture 50% of German positions
- Victory condition type is `time_expired`, not `force_destroyed`

### 73b: Decisive Combat Resolution

Fix 8 scenarios that resolve via `time_expired` when they should resolve decisively.

- **`data/eras/*/scenarios/*/scenario.yaml`** (multiple modified) -- For each scenario:
  - **Trafalgar**: Reduce starting distance, increase naval combat tempo → `force_destroyed` (22/33 ships)
  - **Agincourt**: Reduce map size to 1km frontage, increase archery lethality → `force_destroyed` or `morale_collapsed`
  - **Salamis**: Narrow strait forces engagement, increase trireme ramming lethality → `force_destroyed`
  - **Cannae**: Reduce starting distance, Hannibal's double envelopment via force positioning → `force_destroyed`
  - **Midway**: Increase carrier vulnerability to dive bombing → `force_destroyed` (4 carriers)
  - **Kursk**: Extend max_ticks or increase attrition rate → `force_destroyed` or `morale_collapsed`
  - **Jutland**: Keep as `time_expired` (historically inconclusive; British strategic victory via fleet-in-being)
  - **Cambrai**: Already `force_destroyed` — verify historical accuracy

**Tests** (~16):
- Each historical scenario produces correct winner AND correct victory condition type
- MC validation (10 seeds, 80% threshold) for each scenario
- Parametrized test: `(scenario, expected_winner, expected_condition_type)`

### 73c: Calibration Documentation

Document the Dupuy CEV rationale for each historical scenario.

- **`data/eras/*/scenarios/*/scenario.yaml`** (multiple modified) -- Add calibration comments:
  - Document source of `force_ratio_modifier` values (Dupuy CEV tables, historical analysis)
  - Reference specific sources (Dupuy TQB, Biddle military effectiveness, historical casualty ratios)
  - Note what the modifier compensates for (training, morale, leadership, technology)
- **`docs/concepts/models.md`** (modified) -- Add section on calibration methodology:
  - Explain Dupuy CEV approach
  - Document per-scenario calibration rationale

**Tests** (~2):
- All scenario YAMLs with `force_ratio_modifier` have a calibration comment
- Models doc updated with calibration section

### Exit Criteria
- Somme victory condition historically accurate
- 7 of 8 `time_expired` scenarios now resolve decisively
- Jutland accepted as `time_expired` (historically correct)
- All 14 historical scenarios MC-validated
- ~22 new tests

---

## Phase 74: Combat Engine Unit Tests

**Status**: Complete — 472 tests across 32 test files + conftest.py.

**Goal**: Add dedicated unit tests for all 33 combat engine files — currently 0% unit test coverage.

**Dependencies**: None (pure test addition, no source changes).

### 74a: Core Combat Engine Tests

Unit tests for the highest-impact combat engines.

- **`tests/unit/combat/test_damage.py`** (new) -- damage.py public API (~20 tests)
- **`tests/unit/combat/test_engagement.py`** (new) -- engagement.py routing and resolution (~15 tests)
- **`tests/unit/combat/test_ammunition.py`** (new) -- ammunition.py consumption, compatibility (~15 tests)
- **`tests/unit/combat/test_ballistics.py`** (new) -- ballistics.py trajectory, drag, penetration (~15 tests)
- **`tests/unit/combat/test_hit_probability.py`** (new) -- hit_probability.py Pk computation (~10 tests)
- **`tests/unit/combat/test_suppression.py`** (new) -- suppression.py effects (~10 tests)

**Tests** (~85):
- DamageEngine: resolve_damage returns correct damage_fraction, casualties, fire_started
- EngagementEngine: route_engagement dispatches to correct domain engine
- AmmunitionEngine: reload, compatibility check, depletion
- BallisticsEngine: RK4 trajectory, DeMarre penetration, Mach drag
- HitProbabilityEngine: range-dependent Pk, modifier stacking
- SuppressionEngine: suppression threshold, recovery rate

### 74b: Domain Combat Engine Tests

Unit tests for domain-specific combat engines.

- **`tests/unit/combat/test_air_combat.py`** (new) -- BVR/WVR, altitude advantage (~12 tests)
- **`tests/unit/combat/test_air_defense.py`** (new) -- SAM engagement envelope, ECM (~10 tests)
- **`tests/unit/combat/test_air_ground.py`** (new) -- CAS/strike, CEP, weather ceiling (~10 tests)
- **`tests/unit/combat/test_naval_surface.py`** (new) -- salvo model, radar-directed fire (~12 tests)
- **`tests/unit/combat/test_naval_subsurface.py`** (new) -- torpedo, ASROC, depth charges (~12 tests)
- **`tests/unit/combat/test_missiles.py`** (new) -- missile flight, guidance, terminal (~10 tests)
- **`tests/unit/combat/test_directed_energy.py`** (new) -- Beer-Lambert, laser/HPM Pk (~8 tests)

**Tests** (~74):
- Each engine's resolve() method tested with representative inputs
- Domain-specific physics verified (salvo equation, Beer-Lambert transmittance, etc.)
- Edge cases: zero range, maximum range, no ammo, disabled weapon

### 74c: Historical & Unconventional Combat Tests

Unit tests for era-specific and unconventional combat engines.

- **`tests/unit/combat/test_melee.py`** (new) -- melee types, reach, flanking (~12 tests)
- **`tests/unit/combat/test_archery.py`** (new) -- volley, ammo per archer, range (~8 tests)
- **`tests/unit/combat/test_volley_fire.py`** (new) -- Binomial volley, formation modifier (~8 tests)
- **`tests/unit/combat/test_barrage.py`** (new) -- fire density, observer correction (~8 tests)
- **`tests/unit/combat/test_siege.py`** (new) -- daily state machine, assault/sally (~8 tests)
- **`tests/unit/combat/test_naval_gunnery.py`** (new) -- bracket firing, radar-directed (~8 tests)
- **`tests/unit/combat/test_naval_mine.py`** (new) -- mine trigger, sweeping, persistence (~8 tests)
- **`tests/unit/combat/test_unconventional.py`** (new) -- IED, guerrilla, human shields (~10 tests)
- **`tests/unit/combat/test_fratricide.py`** (new) -- fratricide probability, range (~6 tests)
- **`tests/unit/combat/test_gas_warfare.py`** (new) -- gas exposure, MOPP, don time (~8 tests)
- **`tests/unit/combat/test_carrier_ops.py`** (new) -- CAP, sortie, recovery (~8 tests)

**Tests** (~84):
- Each era-specific engine tested with era-appropriate inputs
- Unconventional: IED detection/detonation, guerrilla disengage, human shield Pk reduction
- Fratricide: probability scales with friendly proximity and confusion

### Exit Criteria
- All 33 combat engine files have dedicated unit tests
- ~243 new tests across combat domain
- Each engine's public API methods exercised with representative inputs

---

## Phase 75: Simulation Core & Domain Unit Tests

**Status**: Complete (293 tests across 15 test files).

**Goal**: Add unit tests for engine.py, battle.py private methods, and all domain modules (movement, terrain, logistics, simulation support).

**Dependencies**: Phase 74 (combat tests complete; pattern established).

### 75a: Battle.py Method Tests

Extract and test critical battle.py private methods.

- **`tests/unit/simulation/test_battle_methods.py`** (new) -- Test battle.py private methods in isolation:
  - `_route_air_engagement()`: air domain routing logic (~6 tests)
  - `_route_naval_engagement()`: naval domain routing logic (~6 tests)
  - `_compute_terrain_modifiers()`: terrain cover/concealment calculation (~6 tests)
  - `_target_value()` / `_score_target()`: target selection scoring (~8 tests)
  - `_apply_behavior_rules()`: ROE/posture enforcement (~6 tests)
  - `_compute_weather_pk_modifier()`: weather → Pk adjustment (~4 tests)
  - `_compute_night_modifiers()`: night/thermal detection (~4 tests)
  - `_compute_wbgt()` / `_compute_wind_chill()`: environmental helpers (~4 tests)
  - `_apply_aggregate_casualties()`: aggregate casualty mapping (~4 tests)

**Tests** (~48):
- Each method tested with representative inputs and edge cases
- Methods may need to be refactored to accept parameters directly (rather than reading from self) for testability

### 75b: Engine.py Method Tests

Test engine.py private methods.

- **`tests/unit/simulation/test_engine_methods.py`** (new):
  - `_fuse_sigint()`: SIGINT fusion with inverse-variance weighting (~4 tests)
  - `_forces_within_closing_range()`: resolution switching guard (~6 tests)
  - `_update_resolution()`: tick resolution transitions (~4 tests)
  - `_evaluate_victory()`: victory condition checking (~6 tests)
  - Event handlers: `_handle_return_to_duty()`, `_handle_equipment_breakdown()`, `_handle_maintenance_completed()` (~6 tests)

**Tests** (~26):
- SIGINT fusion produces weighted centroid
- Resolution switches at correct distance thresholds
- Event handlers modify unit state correctly

### 75c: Domain Module Tests

Unit tests for environment, detection, movement, morale, logistics modules.

- **`tests/unit/environment/`** (new, ~9 test files) -- Weather, sea state, astronomy, conditions, EM, acoustics, obscurants, seasons, time of day (~50 tests)
- **`tests/unit/terrain/`** (new, ~5 test files) -- Heightmap, LOS, classification, obstacles, infrastructure (~30 tests)
- **`tests/unit/detection/`** (new, ~4 test files) -- Sensors, detection, sonar, estimation (~25 tests)
- **`tests/unit/movement/`** (new, ~4 test files) -- Engine, pathfinding, formation, naval (~25 tests)
- **`tests/unit/morale/`** (new, ~3 test files) -- State, rout, cohesion (~20 tests)
- **`tests/unit/logistics/`** (new, ~4 test files) -- Supply network, maintenance, medical, consumption (~25 tests)

**Tests** (~175):
- Each module's public API tested with representative inputs
- Focus on computational correctness (formulas, physics, state transitions)
- Environmental modules: verify parameter ranges, boundary conditions

### 75d: Supporting Simulation Module Tests

Tests for scenario loader, campaign manager, victory evaluator, etc.

- **`tests/unit/simulation/test_scenario_loader.py`** (new) -- ScenarioLoader validation, era loading (~10 tests)
- **`tests/unit/simulation/test_victory.py`** (new) -- Victory condition evaluation (~10 tests)
- **`tests/unit/simulation/test_calibration.py`** (new) -- CalibrationSchema flattening, side overrides (~8 tests)
- **`tests/unit/simulation/test_metrics.py`** (new) -- Metrics collection (~6 tests)

**Tests** (~34):
- ScenarioLoader correctly loads era-specific data
- Victory evaluator handles all condition types
- CalibrationSchema flattens legacy YAML format correctly

### Exit Criteria
- Battle.py and engine.py private methods tested in isolation
- All domain modules have dedicated unit tests
- ~283 new tests across simulation core and domain modules

---

## Phase 76: API Robustness

**Status**: Complete. 25 tests across 3 test files. 8 source files modified, 0 new source files.

**Goal**: Fix critical concurrency bugs in the API server and harden for reliable multi-user use.

**Dependencies**: None (API layer independent of engine changes).

### 76a: Concurrency Fixes

Fix the 3 critical/high concurrency bugs.

- **`api/run_manager.py`** (modified):
  - Add `async with self._semaphore` to `_execute_batch()` (currently bypasses semaphore)
  - Add semaphore to analysis endpoint thread spawning (compare/sweep)
  - Implement per-client WebSocket queues (multicast pattern): each connected client gets its own queue; progress pushed to all queues; slow client doesn't block others
- **`api/routers/runs.py`** (modified):
  - Move `tempfile.mkdtemp()` to thread pool via `await asyncio.to_thread(tempfile.mkdtemp, ...)`
  - Each WS connection creates own consumer queue

**Tests** (~10):
- Batch of 10 runs doesn't spawn more than `max_concurrent` threads simultaneously
- Slow WS client doesn't block fast WS client
- `tempfile.mkdtemp()` doesn't block event loop (timing assertion)

### 76b: Graceful Shutdown & Reliability

Add signal handling and database hardening.

- **`api/main.py`** (modified):
  - Add SIGTERM/SIGINT handler in lifespan: cancel running tasks, wait up to 5s, close DB
  - Register cleanup callback for all active RunManager tasks
- **`api/database.py`** (modified):
  - Enable WAL mode: `PRAGMA journal_mode=WAL` on connection open
  - Replace bare `except Exception: pass` in migration with `logger.warning()`
  - Add busy timeout: `PRAGMA busy_timeout=5000`
- **`api/routers/scenarios.py`** (modified):
  - Cache `scan_scenarios()` and `scan_units()` results (invalidate on data dir mtime change)

**Tests** (~8):
- WAL mode enabled after connection (PRAGMA query)
- Scenario cache returns same result on repeated calls
- Scenario cache invalidates when data changes

### 76c: Request Safety

Add request body limits and basic health monitoring.

- **`api/schemas.py`** (modified):
  - Add `model_config = ConfigDict(max_str_length=100_000)` to request schemas
  - Add validation: `config_overrides` dict depth limit, max keys
- **`api/routers/meta.py`** (modified):
  - Split into `/health/live` (instant 200) and `/health/ready` (DB + data check)
  - Remove `scan_scenarios()` from health endpoint (expensive)

**Tests** (~6):
- Oversized request body rejected with 422
- `/health/live` returns 200 instantly
- `/health/ready` checks DB connectivity

### Exit Criteria
- Batch execution uses semaphore
- Per-client WS queues prevent slow-client blocking
- Graceful shutdown cancels running tasks
- SQLite WAL mode enabled
- ~24 new tests

---

## Phase 77: Frontend Accessibility

**Status**: **Complete** (36 tests).

**Goal**: WCAG 2.1 AA compliance for all critical user paths — forms, navigation, modals, data display.

**Dependencies**: None (frontend-only changes).

### 77a: Forms & Inputs

Fix all form-related accessibility issues.

- **`frontend/src/pages/editor/GeneralSection.tsx`** (modified) -- Add `id`/`htmlFor` to all input-label pairs
- **`frontend/src/pages/runs/RunConfigPage.tsx`** (modified) -- Add `required`/`aria-required` to required fields
- **`frontend/src/pages/editor/ScenarioEditorPage.tsx`** (modified) -- Add `role="alert"` and `aria-live="assertive"` to validation error container
- **`frontend/src/components/SearchInput.tsx`** (modified) -- Add `aria-label` to search input; add `<title>` to search SVG icon

**Tests** (~8):
- All form inputs have associated labels (automated axe check)
- Validation errors announced via aria-live
- Required fields marked with aria-required

### 77b: Navigation & Focus

Fix navigation, skip links, and focus management.

- **`frontend/src/components/Layout.tsx`** (modified) -- Add skip-to-content link (`sr-only` class)
- **`frontend/src/components/Sidebar.tsx`** (modified) -- Add `aria-label` to status indicator; `role="presentation"` to backdrop; focus returns to trigger on close
- **`frontend/src/pages/units/UnitDetailModal.tsx`** (modified) -- Verify Headless UI focus trap
- **`frontend/src/components/ConfirmDialog.tsx`** (modified) -- Verify focus trap
- **`frontend/src/components/KeyboardShortcutHelp.tsx`** (modified) -- Verify focus trap

**Tests** (~6):
- Skip link present and functional
- Modal focus trapped (Tab doesn't escape)
- Focus returns to trigger element on modal close

### 77c: Interactive Components

Fix buttons, cards, tables, and status indicators.

- **`frontend/src/components/map/PlaybackControls.tsx`** (modified) -- Improve `aria-label` on symbol buttons; add `aria-describedby` linking slider to time display
- **`frontend/src/components/LoadingSpinner.tsx`** (modified) -- Add `role="status"` and `aria-label="Loading"`
- **`frontend/src/components/Card.tsx`** (modified) -- Add `role="button"`, `tabIndex={0}`, `onKeyDown` (Enter/Space)
- **`frontend/src/components/charts/StatisticsTable.tsx`** (modified) -- Add `scope="col"` to all `<th>` elements
- **`frontend/src/pages/analysis/AnalysisPage.tsx`** (modified) -- Add `role="tabpanel"` and `aria-labelledby` to tab content

**Tests** (~8):
- Clickable cards accessible via keyboard (Enter activates)
- Table headers have scope="col"
- LoadingSpinner has role="status"
- Tab panels have correct ARIA relationships

### 77d: Canvas & Charts

Add accessible alternatives to visual-only content.

- **`frontend/src/components/map/TacticalMap.tsx`** (modified) -- Add `role="application"`, `aria-label="Tactical map"`, `aria-describedby` linking to unit summary
- **`frontend/src/components/map/TacticalMap.tsx`** (modified) -- Add offscreen text summary of current frame (unit count, engagement count)
- **`frontend/src/components/charts/PlotlyChart.tsx`** (modified) -- Add expandable `<details>` with data table below each chart
- **`frontend/src/components/charts/ForceStrengthChart.tsx`** (modified) -- Generate accessible data summary

**Tests** (~6):
- Tactical map has role="application" and aria-label
- Chart components have expandable data table alternative
- Screen reader can access unit count from map

### 77e: Color & Motion

Fix color-only indicators and add reduced-motion support.

- **`frontend/src/components/Sidebar.tsx`** (modified) -- Add text label alongside green/red status circle
- **`frontend/src/index.css`** (modified) -- Add `@media (prefers-reduced-motion: reduce)` to disable animations
- **`frontend/src/components/map/MapLegend.tsx`** (modified) -- Add text labels to status/domain icons

**Tests** (~4):
- Status indicator has text alternative (not color-only)
- Reduced motion media query present in CSS

### Exit Criteria
- All critical WCAG 2.1 AA issues resolved (21 critical → 0)
- Forms, navigation, modals, tables all accessible
- Canvas map has semantic alternative
- ~32 new tests (vitest)

---

## Phase 78: P2 Environment Wiring

**Status**: Complete. 49 tests across 5 test files. 8 modified source files. Zero new source files.

**Goal**: Wire remaining P2-priority environment items that improve simulation fidelity.

**Dependencies**: Phase 73 (historical scenarios stable before adding environmental modifiers).

### 78a: Ice Crossing & Vegetation LOS

Wire frozen water traversal and vegetation height LOS blocking.

- **`stochastic_warfare/movement/engine.py`** (modified) -- When `SeasonsEngine.sea_ice_thickness > threshold`:
  - Add temporary traversable edges to pathfinding graph for frozen water cells
  - Movement speed on ice reduced by 50%
- **`stochastic_warfare/terrain/los.py`** (modified) -- DDA raycaster modification:
  - Query vegetation height at each cell; if height > observer height (1.8m default), block LOS
  - Only applies at ground level (air units unaffected)

**Tests** (~10):
- Frozen water cell traversable when ice_thickness > 0.3m
- Movement speed on ice reduced
- Tall vegetation blocks ground-level LOS
- Air units not affected by vegetation LOS blocking

### 78b: Bridge Capacity & Ford Crossing

Wire bridge weight limits and river ford routing.

- **`stochastic_warfare/entities/base.py`** (modified) -- Add `weight_tons: float` field to ground units (from YAML, default by unit type)
- **`stochastic_warfare/movement/engine.py`** (modified):
  - Bridge crossing: check `unit.weight_tons <= bridge.capacity_tons`; overweight units reroute
  - Ford crossing: add ford points as traversable but slow edges in pathfinding graph

**Tests** (~8):
- Heavy tank cannot cross light bridge (reroutes)
- Infantry crosses any bridge
- Ford crossing available but slower than bridge
- Units without weight field use default

### 78c: Fire Spread & Fatigue

Wire fire spread cellular automaton and temperature-driven fatigue.

- **`stochastic_warfare/environment/obscurants.py`** (modified) -- Fire spread model:
  - Each tick: fire zones expand to adjacent cells based on combustibility and wind direction
  - Spread rate proportional to `vegetation_moisture` (inverse) and wind speed
  - Fire exhausts when cell fuel consumed (combustibility → 0)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Environmental fatigue:
  - High WBGT or low wind-chill → gradual fatigue accumulation per unit
  - Fatigued units: reduced movement speed, reduced accuracy

**Tests** (~10):
- Fire spreads to adjacent cell in wind direction
- Fire doesn't spread to water/rock cells
- High combustibility + wind = faster spread
- High WBGT → fatigue accumulation
- Fatigued unit has reduced movement speed

### Exit Criteria
- 6 P2 environment items wired
- ~28 new tests

---

## Phase 79: CI/CD & Packaging

**Status**: **Complete.**

**Goal**: Automated test pipeline, script cleanup, packaging hygiene.

**Dependencies**: None (infrastructure-only).

### 79a: Test Workflow

Create GitHub Actions workflow for automated testing.

- **`.github/workflows/test.yml`** (new):
  - Trigger: push to any branch, pull request to main
  - Matrix: Python 3.12 on ubuntu-latest
  - Steps: checkout, setup Python, `uv sync --extra dev`, `uv run python -m pytest --tb=short -q` (exclude slow)
  - Frontend: setup Node 22, `cd frontend && npm ci && npm test`
  - Cache: uv cache + npm cache

**Tests** (~2):
- Workflow YAML validates (act --dryrun or equivalent)
- Test run completes in <10 minutes

### 79b: Lint Workflow

Create lint workflow for code quality gates.

- **`.github/workflows/lint.yml`** (new):
  - Python: ruff check + ruff format --check
  - Frontend: `cd frontend && npx eslint src/`
  - Trigger: push + PR

### 79c: Script & Fixture Cleanup

Archive stale scripts and clean up test infrastructure.

- **`scripts/archive/`** (new directory) -- Move stale debug scripts: `debug_loader.py`, `debug_scenario.py`, `test_napoleon_quick.py`
- **`.gitignore`** (modified) -- Add `scripts/evaluation_results_*.json`, `scripts/evaluation_stderr_*.log`, `scripts/falk_test.json`
- **`docs.yml`** (modified) -- Replace `pip install` with `uv pip install`
- **`tests/conftest.py`** (modified) -- Remove unused `rng_manager` fixture; mark `sim_clock` as deprecated

### Exit Criteria
- `test.yml` runs Python + frontend tests on push/PR
- `lint.yml` runs ruff + eslint on push/PR
- Stale scripts archived
- Evaluation artifacts gitignored
- ~2 new tests (workflow validation)

---

## Phase 80: API & Frontend Sync

**Status**: Complete.

**Goal**: Bring API schemas and frontend components current with engine state. Fix scenario data issues.

**Dependencies**: Phase 76 (API robustness fixes), Phase 77 (frontend accessibility).

### 80a: API Schema Updates

Add missing fields and documentation to API schemas.

- **`api/schemas.py`** (modified):
  - Add `has_space: bool = False` and `has_dew: bool = False` to `ScenarioSummary`
  - Add docstring to `RunSubmitRequest.config_overrides` documenting CalibrationSchema fields
- **`api/routers/scenarios.py`** (modified):
  - Wire `has_space` and `has_dew` in `_extract_summary()`

**Tests** (~4):
- ScenarioSummary includes has_space for space-enabled scenarios
- ScenarioSummary includes has_dew for DEW-enabled scenarios

### 80b: CalibrationSliders Overhaul

Replace hardcoded 4-slider list with dynamic generation from CalibrationSchema.

- **`frontend/src/pages/editor/CalibrationSliders.tsx`** (modified):
  - Generate slider list from CalibrationSchema field definitions
  - Group: `enable_*` toggles (boolean switches), global scalars (sliders), per-side overrides (keyed sliders)
  - Add section headers for each group (EW/SEAD, Morale, Environment, C2, etc.)
- **`frontend/src/pages/editor/CalibrationSliders.tsx`** (modified):
  - Add `enable_all_modern` toggle that sets all 21 `enable_*` flags to True

**Tests** (~6):
- CalibrationSliders renders all enable_* toggles
- enable_all_modern toggle sets all flags
- Slider changes update config state correctly

### 80c: Scenario Data Fixes

Fix data issues identified in audit.

- **`data/scenarios/eastern_front_1943/scenario.yaml`** (modified) -- Replace WW1 weapons (gewehr_98, lee_enfield, mills_bomb) with WW2 equivalents (kar98k, mg42, stielhandgranate)
- **`data/scenarios/golan_heights/scenario.yaml`** (modified) -- Add explicit `victory_conditions` section
- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add `enable_all_modern: bool = False` meta-flag
- **Calibration exercise scenarios** (new, ~3 YAML files) -- Scenarios that set non-default values for the 16 never-exercised CalibrationSchema fields

**Tests** (~8):
- eastern_front_1943 loads without warnings
- golan_heights has explicit victory conditions
- `enable_all_modern=True` sets all 21 flags
- Calibration exercise scenarios produce valid outcomes

### Exit Criteria
- API schemas current with engine state
- CalibrationSliders expose all 50+ parameters
- Scenario data issues fixed
- 16 CalibrationSchema fields exercised
- ~18 new tests

---

## Phase 81: Recalibration & Validation

**Status**: Complete.

**Goal**: Full recalibration after all behavioral changes from Phases 68–80.

**Dependencies**: All prior phases (behavioral changes must be stable).

### 81a: Modern Scenario Recalibration

Recalibrate all modern scenarios with new enforcement flags enabled.

- **`data/scenarios/*/scenario.yaml`** (multiple modified) -- For each of ~27 modern scenarios:
  - Enable `enable_fuel_consumption`, `enable_ammo_gate`, and other Phase 68–69 flags
  - Adjust calibration overrides as needed to maintain correct outcomes
  - Verify winner and victory condition type

### 81b: Historical Scenario Recalibration

Verify all 14 historical scenarios after Phase 73 corrections.

- **`data/eras/*/scenarios/*/scenario.yaml`** (multiple modified):
  - MC validation: 10 seeds, 80% correct winner threshold
  - Verify victory condition type matches historical outcome
  - Adjust CEV modifiers if needed

### 81c: Performance & Exit Criteria Verification

Full validation against all Block 8 exit criteria.

- **`tests/validation/test_block8_exit.py`** (new):
  - Exit criterion 1: fuel gate test, ammo gate test
  - Exit criterion 2: no unconsumed engine outputs (structural test)
  - Exit criterion 5: historical victory condition types
  - Exit criterion 6: Golan Heights < 120s benchmark
- **Evaluator run**: Full `/evaluate-scenarios` across all scenarios

**Tests** (~20):
- MC validation for all 37+ scenarios
- Performance benchmarks
- Block 8 exit criteria assertions

### Exit Criteria
- All scenarios recalibrated and MC-validated
- All 10 exit criteria pass
- ~20 new tests

---

## Phase 82: Block 8 Postmortem & Documentation

**Status**: Complete.

**Goal**: Update all living documents, run cross-doc audit, capture lessons learned.

**Dependencies**: Phase 81 (all changes finalized).

### 82a: Living Document Updates

Update all project documentation to reflect Block 8 state.

- **`CLAUDE.md`** (modified) -- Update phase count, test count, Block 8 status, phase summary table
- **`README.md`** (modified) -- Update overview, phase count, test count, block status
- **`docs/index.md`** (modified) -- Update landing page statistics
- **`docs/devlog/index.md`** (modified) -- Add Phase 68–82 entries, update deficit dispositions
- **`docs/concepts/architecture.md`** (modified) -- Update if battle.py subsystems extracted
- **`docs/reference/api.md`** (modified) -- Update endpoint list, CalibrationSchema docs
- **`mkdocs.yml`** (modified) -- Add Phase 68–82 devlog entries to nav

### 82b: Phase Devlogs

Write devlogs for each completed phase.

- **`docs/devlog/phase-68.md`** through **`docs/devlog/phase-82.md`** (new) -- Per-phase implementation logs with decisions, tests, lessons

### 82c: Memory & Cross-Doc Audit

Update memory and verify cross-document consistency.

- **`MEMORY.md`** (modified) -- Add Block 8 lessons, update status
- Run `/cross-doc-audit` -- Verify all 19 checks pass
- Run `/postmortem` -- Structured retrospective

### Exit Criteria
- All living documents updated
- Cross-doc audit passes (19/19 checks)
- Phase devlogs written for all 15 phases
- MEMORY.md current

---

## Phase Summary

| Phase | Focus | Tests | Cumulative | Status |
|-------|-------|-------|------------|--------|
| 68 | Consequence Enforcement | 67 | ~8,647 | Complete |
| 69 | C2 Depth | 41 | ~8,688 | Complete |
| 70 | Performance Optimization | 24 | ~8,712 | Complete |
| 71 | Missile & Carrier Ops | 46 | ~8,758 | Complete |
| 72 | Checkpoint & State | 139 | ~8,897 | Complete |
| 73 | Historical Scenario Correctness | ~22 | ~8,919 | Complete |
| 74 | Combat Engine Unit Tests | 472 | ~9,391 | Complete |
| 75 | Simulation Core & Domain Tests | 293 | ~9,684 | Complete |
| 76 | API Robustness | 25 | ~9,709 | Complete |
| 77 | Frontend Accessibility | 36 | ~9,745 | Complete |
| 78 | P2 Environment Wiring | 49 | ~9,794 | Complete |
| 79 | CI/CD & Packaging | 31 | ~9,825 | Complete |
| 80 | API & Frontend Sync | 26 | ~9,851 | Complete |
| 81 | Recalibration & Validation | ~20 | ~9,871 | Complete |
| 82 | Postmortem & Documentation | 0 | ~9,871 | Complete |

**Block 8 total**: ~1,291 new tests across 15 phases.
**Cumulative**: ~9,871 Python tests + ~316 frontend vitest = ~10,187 total.

---

## Module Index: Block 8 Contributions

| Module | Phases | Changes |
|--------|--------|---------|
| `simulation/battle.py` | 68, 69, 70, 71, 78 | Fuel/ammo gates, fire damage, order delay, guerrilla retreat, stratagem expiry, STRtree optimization, caching, carrier ops, fatigue |
| `simulation/engine.py` | 68, 69, 71, 72 | Order delay queue, misinterpretation, planning injection, command hierarchy, missile flight, checkpoint registration |
| `simulation/calibration.py` | 68, 80 | `enable_fuel_consumption`, `enable_ammo_gate`, `stratagem_duration_ticks`, `enable_all_modern` |
| `api/run_manager.py` | 76 | Batch semaphore, per-client WS queues |
| `api/main.py` | 76 | Graceful shutdown signal handling |
| `api/database.py` | 76 | WAL mode, busy timeout, migration logging |
| `api/schemas.py` | 76, 80 | Request size limits, `has_space`, `has_dew` |
| `frontend/src/` | 77, 80 | WCAG 2.1 AA compliance (~20 components), CalibrationSliders overhaul |
| `data/scenarios/` | 73, 80, 81 | Historical victory conditions, weapon fixes, recalibration |
| `data/eras/*/scenarios/` | 73, 81 | Decisive combat resolution, CEV documentation |
| `movement/engine.py` | 78 | Ice crossing, ford routing |
| `terrain/los.py` | 78 | Vegetation height LOS blocking |
| `environment/obscurants.py` | 78 | Fire spread cellular automaton |
| `.github/workflows/` | 79 | test.yml, lint.yml (new) |
| `tests/unit/combat/` | 74 | 24 new test files (~243 tests) |
| `tests/unit/simulation/` | 75 | 6 new test files (~108 tests) |
| `tests/unit/{environment,terrain,detection,movement,morale,logistics}/` | 75 | ~29 new test files (~175 tests) |

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Fuel enforcement breaks all scenarios | High | `enable_fuel_consumption=False` default; staged rollout in Phase 81 |
| Order delay makes AI non-responsive | High | Short default delays; gated behind existing `enable_c2_friction`; tunable per echelon |
| STRtree optimization changes engagement order | Medium | Seed-controlled PRNG; verify identical outcomes before/after |
| Historical scenario recalibration is time-consuming | High | Focus on 9 `time_expired` scenarios; Somme is highest priority |
| Battle.py subsystem extraction introduces regressions | Medium | Extract one at a time; full regression suite after each |
| A11y changes break existing vitest tests | Medium | Run vitest after each component change |
| CI/CD workflows fragile on Windows runners | Medium | Use ubuntu-latest runners; Windows testing via local dev |
| Test writing for 270 files is enormous scope | High | Prioritize critical paths (combat 74, sim core 75); remaining domain tests can continue into future blocks |
| Calibration doesn't converge with enforcement + scenario fixes | Medium | Individual enable flags; staged rollout like Block 7 |
| Missile flight resolution requires significant new logic | Medium | Start with simple kinematic model; terminal phase delegates to existing MissileEngine Pk |

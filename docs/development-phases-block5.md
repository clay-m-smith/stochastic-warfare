# Stochastic Warfare -- Block 5 Development Phases (40--47)

## Philosophy

Block 5 is the **core combat fidelity block**. No new subsystems, no new UI features. The engine has ~40 built-but-disconnected systems -- posture, suppression, terrain cover, ROE, morale multipliers, aggregate fire models, naval combat engines, detection pipeline, logistics engines, weather/night effects, population engines, and strategic/campaign engines. All were built in Phases 1--30 and tested in isolation, but none feed into the tactical engagement loop in `battle.py`.

This block wires everything together, hardens the mathematical models, sources all unsourced constants from literature, fixes scenario data errors, and recalibrates all 42 scenarios against historical outcomes. The result is a defensible simulation where every system interacts realistically, not a collection of isolated engines.

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block5.md` (design thinking, scenario analysis, mathematical model audit), `devlog/index.md` (deficit inventory), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**Engine changes are wiring, not building**: Block 5 modifies `stochastic_warfare/simulation/battle.py` extensively but creates minimal new source files. The work is connecting existing systems, not designing new ones.

---

## Phase 40: Battle Loop Foundation

**Goal**: Fix the `is_tie` victory bug and wire the five lowest-risk disconnected systems into `_execute_engagements()`: posture, fire-on-move, domain filtering, suppression, and morale multipliers. Instantiate terrain managers as prerequisites for Phase 41.

**Status**: **Complete**.

**Dependencies**: Block 4 complete (Phases 37--39).

### 40a: Victory Bug Fix

Fix the `evaluate_force_advantage()` `is_tie` bug that mislabels 15+ scenarios as "Draw".

- **`stochastic_warfare/simulation/victory.py`** (modified) -- In `evaluate_force_advantage()` (line ~600), replace the flawed `is_tie` initialization logic:
  ```python
  # BEFORE (broken):
  is_tie = True
  for side, units in units_by_side.items():
      if survival > best_survival:
          if best_survival >= 0:
              is_tie = False
          best_survival = survival
          best_side = side
      elif survival == best_survival:
          is_tie = True

  # AFTER (fixed):
  sides_at_best = 0
  for side, units in units_by_side.items():
      if survival > best_survival:
          best_survival = survival
          best_side = side
          sides_at_best = 1
      elif survival == best_survival:
          sides_at_best += 1
  is_tie = sides_at_best != 1
  ```

**Tests** (~8):
- Blue 100% vs red 0% → blue wins (not draw), regardless of dict iteration order
- Both sides 50% → tie
- Three-sided: one dominant → winner, two equal best → tie
- Regression: run 73 Easting scenario, verify blue victory (not draw)
- Regression: run Bekaa Valley scenario, verify blue victory (not draw)

### 40b: Wire Posture into Engagements

Connect the existing `GroundUnit.posture` attribute to the engagement engine. Currently `_execute_engagements()` never passes `target_posture`, defaulting every unit to `MOVING`.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`:
  - Extract target unit's posture (or `UnitStatus` equivalent)
  - Pass as `target_posture` parameter to engagement call
  - Auto-assign posture based on unit state:
    - `MOVING` if unit moved this tick (distance > 0)
    - `HALTED` if unit did not move this tick
    - `DEFENSIVE` if unit is on a `defensive_sides` list and halted for >1 tick
    - `DUG_IN` if unit has been defensive longer than `dig_in_time_s` (from unit config, default 300s)
    - `FORTIFIED` reserved for scenario-placed fortifications and obstacle overlays
  - Track per-unit `ticks_stationary` counter for dig-in progression

**Tests** (~10):
- Moving unit has posture MOVING, passes to engagement
- Halted unit (no movement) has posture HALTED
- Defensive unit after threshold time transitions to DUG_IN
- DUG_IN target has reduced hit probability (test via Phit output)
- FORTIFIED target has maximal protection
- Posture resets to MOVING when unit starts moving again
- Backward compat: existing engagements still work when posture logic added

### 40c: Wire Fire-on-Move Penalty

Pass the shooter's current speed to the engagement engine. Currently `shooter_speed_mps` is always 0.0.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`:
  - Compute shooter's movement speed this tick (distance traveled / tick duration, or unit's current `speed` attribute)
  - Pass as `shooter_speed_mps` to engagement call
  - The existing formula in `hit_probability.py` already handles the math: `shoot_pen = max(0.3, 1.0 - 0.25 * (shooter_speed_mps / 10.0))`
- **`stochastic_warfare/entities/unit_classes/ground.py`** (modified) -- Add optional `fire_on_move_penalty_mult` field to unit config (default 1.0). Per-era/unit-type override:
  - Modern MBT with stabilization: 0.8 (reduced penalty)
  - WW2 tank: 1.0 (standard penalty)
  - Musketeer: 3.6 (90% penalty at walking speed ~2.5 m/s → `0.25 * 3.6 * 2.5/10 = 0.225`, so ~23% penalty walking)
  - Artillery: set via separate "must deploy" gate (cannot fire while moving at all)

**Tests** (~6):
- Stationary shooter has no penalty (speed=0 → multiplier=1.0)
- Moving shooter at 10 m/s has 25% penalty
- Moving shooter at 40 m/s has 70% penalty (capped at 0.3)
- Fire-on-move multiplier from unit config applies
- Artillery unit cannot fire while moving (100% penalty or gate)

### 40d: Domain Filtering in Target Selection

Prevent engagement mismatches like tank guns targeting fighter aircraft.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In target selection within `_execute_engagements()`:
  - Before selecting a target, check if the attacker has at least one weapon capable of engaging the target's domain
  - Create weapon-domain compatibility check:
    - `LAND` weapons (tank guns, rifles, ATGMs): can target `LAND` only (exception: some AA-capable weapons)
    - `AIR` weapons (SAMs, AAA): can target `AIR` only (exception: some can target `LAND`)
    - `NAVAL` weapons (torpedoes, anti-ship missiles): can target `NAVAL`/`SUB`
    - Multi-role weapons flagged in YAML (e.g., Vulcan cannon can be AA or ground)
  - Skip incompatible targets; if no compatible targets exist, unit does not engage this tick
- **`stochastic_warfare/combat/weapons.py`** (modified) -- Add `target_domains: list[str]` field to weapon definition (default: inferred from `WeaponCategory`). Data-driven, not hardcoded if/else.
- **Data YAML** (modified) -- Add `target_domains` to weapon definitions where needed (most can be auto-inferred from category)

**Tests** (~10):
- Tank gun (LAND weapon) cannot target AIR unit
- SAM (AIR weapon) targets AIR unit correctly
- Multi-role weapon (Vulcan) can target both AIR and LAND
- Torpedo targets NAVAL/SUB only
- Unit with no compatible targets for nearest enemy skips engagement
- Regression: existing single-domain scenarios unchanged

### 40e: Wire Suppression Engine

Replace hardcoded `suppression_level=0.0` with actual suppression state.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`:
  - Query `ctx.suppression_engine` (if available) for each unit's current suppression level
  - Pass actual `suppression_level` to engagement instead of hardcoded 0.0
  - After each engagement hit, call `suppression_engine.update_suppression()` for the target
  - Suppression decays per tick via `suppression_engine.decay()` at start of engagement phase
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate `SuppressionEngine` and attach to `SimulationContext` (currently not instantiated)

**Tests** (~6):
- Suppressed unit (level=0.8) has reduced accuracy in engagement
- Sustained fire on target increases suppression level
- Suppression decays when fire is lifted
- Zero suppression matches current behavior (backward compat)
- Suppression engine instantiated from scenario loader

### 40f: Wire Morale Multipliers into Engagement

Apply the already-computed morale accuracy multipliers during engagement resolution.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`:
  - Query `ctx.morale_states` for attacker's morale state
  - Look up accuracy multiplier: STEADY=1.0, SHAKEN=0.7, BROKEN=0.3, ROUTED=0.1
  - Apply as `morale_accuracy_mod` to hit probability (multiply Phit by morale multiplier)
  - ROUTED units should not engage at all (already partially handled via status check, but enforce explicitly)
  - SURRENDERED units definitely do not engage

**Tests** (~6):
- STEADY attacker fires at full accuracy
- SHAKEN attacker has 0.7 multiplier on Phit
- BROKEN attacker has 0.3 multiplier
- ROUTED attacker does not engage
- SURRENDERED attacker does not engage

### 40g: Terrain Manager Instantiation

Instantiate the 4 terrain managers that are prerequisites for Phase 41 terrain-combat wiring.

- **`stochastic_warfare/simulation/scenario.py`** (modified) -- In `ScenarioLoader.load()`, instantiate:
  - `InfrastructureManager` from `terrain/infrastructure.py` (buildings, roads, bridges)
  - `ObstacleManager` from `terrain/obstacles.py` (minefields, wire, fortifications via STRtree)
  - `HydrographyManager` from `terrain/hydrography.py` (rivers, water bodies)
  - `PopulationManager` from `terrain/population.py` (settlement density)
  - Attach to `SimulationContext` as `ctx.infrastructure`, `ctx.obstacles`, `ctx.hydrography`, `ctx.terrain_population`
  - Populate from scenario YAML data where available; empty/default otherwise (backward compat)

**Tests** (~6):
- Scenario loader creates InfrastructureManager (even if empty)
- ObstacleManager queryable after load
- HydrographyManager queryable after load
- Existing scenarios load without error with new managers
- Managers attached to SimulationContext

### Exit Criteria
- `evaluate_force_advantage()` returns correct winner for 73 Easting (blue 100%, red 0% → blue victory, not draw)
- Moving units have reduced hit probability vs stationary units
- DUG_IN units have ~40% hit reduction
- Tank guns do not engage fighter aircraft
- Suppressed units fire with reduced accuracy
- SHAKEN units fire with 70% accuracy
- Terrain managers instantiated and queryable
- All existing ~7,833 tests pass unchanged

---

## Phase 41: Combat Depth

**Goal**: Wire terrain data into combat resolution, add force quality/training system, replace closest-enemy targeting with threat-based scoring, and instantiate the detection intelligence pipeline.

**Status**: **Complete**.

**Dependencies**: Phase 40 (posture wiring enables terrain→posture auto-assignment; domain filtering informs target scoring; terrain managers instantiated).

### 41a: Terrain-Combat Interaction

Wire the existing terrain classification system, trenches, buildings, obstacles, and heightmap into `_execute_engagements()`. The data exists and is queryable per-position -- it just needs to be called during engagement.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`, before each engagement:
  - Query `ctx.terrain.classification.properties_at(target_pos)` → `cover`, `concealment`
  - Query `ctx.trenches.query_at(target_pos)` (if trench overlay exists) → `cover_value`
  - Query `ctx.infrastructure.buildings_at(target_pos)` (if instantiated) → building `cover_value`
  - Query `ctx.obstacles.obstacles_at(target_pos)` (if instantiated) → fortification cover
  - Compute elevation delta: `elevation_at(shooter_pos) - elevation_at(target_pos)`
  - Query `ctx.environment.ground_state` at target/attacker positions
  - Compute composite terrain modifier:
    ```python
    effective_cover = max(terrain_cover, trench_cover, building_cover, obstacle_cover)
    terrain_hit_mod = (1.0 - effective_cover)
    elevation_mod = 1.0 + min(0.3, max(-0.1, elevation_delta / 100.0))
    concealment_mod = 1.0 - concealment  # reduces detection range, not Phit directly
    ```
  - Pass `terrain_hit_mod * elevation_mod` as a modifier to engagement Phit
  - Use `concealment_mod` to reduce effective detection range for target acquisition
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Soft ground / mud effects:
  - Query `GroundState` at attacker position
  - If `SATURATED` or `MUD`: reduce cavalry/vehicle charge effectiveness by 40-60%
  - Apply as movement speed cap and charge momentum penalty
  - Affects Agincourt (French knights in mud) and similar scenarios
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Force channeling:
  - Add optional `max_engagers_per_side` to scenario config
  - When set, limit the number of units that can simultaneously engage per tick
  - Affects Salamis (narrow strait), Thermopylae (pass), bridge crossings

**Tests** (~20):
- Target in forest (cover=0.5) has 50% reduced Phit
- Target in urban (cover=0.8) has 80% reduced Phit
- Target in open terrain (cover=0.0) has no reduction
- Target in trench (cover_value=0.85) has 85% reduction
- Building cover_value used when target inside building polygon
- Elevation advantage +10% per 33m
- Elevation disadvantage (shooting uphill) has penalty
- Concealment reduces detection range (target in forest harder to find)
- Mud/saturated ground reduces cavalry charge effectiveness
- Force channeling limits simultaneous engagers
- Cover stacking uses max(), not additive
- Terrain query handles missing managers gracefully (no crash)

### 41b: Force Quality & Training Level

Add a training/quality system that modifies engagement effectiveness beyond raw numbers.

- **`stochastic_warfare/entities/base.py`** or **`entities/unit_classes/ground.py`** (modified) -- Add `training_level: float` field to unit definition (default 0.5, range 0.0--1.0):
  - Elite: 0.9--1.0 (SAS, Israeli armor, Old Guard)
  - Veteran: 0.7--0.9 (experienced regulars)
  - Regular: 0.5--0.7 (standard forces)
  - Green: 0.3--0.5 (militia, raw recruits)
  - Untrained: 0.0--0.3 (civilian, mob)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Apply quality multiplier in engagement:
  - `effective_skill = base_crew_skill * (0.5 + 0.5 * training_level)`
  - Pass `effective_skill` as `crew_skill` to engagement engine
  - Higher quality → faster reload, better accuracy, faster reaction
- **`stochastic_warfare/simulation/victory.py`** (modified) -- Quality-weighted force ratios:
  - Replace raw unit count with `sum(training_level * combat_power)` in force advantage calculation
  - Morale thresholds adjusted by quality (elite units break at higher casualty rates)
- **Data YAML** (modified) -- Add `training_level` to unit definitions for historical scenarios:
  - Israeli armor: 0.9, Syrian armor: 0.5 (Golan)
  - British navy: 0.9, Franco-Spanish: 0.4 (Trafalgar)
  - US forces: 0.85, Iraqi: 0.3 (73 Easting)

**Tests** (~10):
- Elite unit (0.9) has higher effective skill than regular (0.5)
- Quality-weighted force ratio: 10 elite ≈ 18 regular in combat power
- Training level defaults to 0.5 for existing units (backward compat)
- Quality affects victory evaluation (small elite force can beat large green force)
- YAML training_level field loads correctly

### 41c: Threat-Based Target Selection

Replace closest-enemy Euclidean distance with weighted threat scoring.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Replace `np.argmin(dists)` in target selection:
  - Compute score for each potential target:
    ```python
    score = (threat_factor * pk_factor * value_factor) / max(1.0, distance_penalty)
    ```
    where:
    - `threat_factor` = target's ability to damage this unit (weapon range, damage potential vs our armor)
    - `pk_factor` = our probability of hitting at this range (prefer high-Pk shots)
    - `value_factor` = target's tactical value (commander units, artillery, SAM, carriers)
    - `distance_penalty` = range normalized by weapon effective range
  - Select target with highest score (not closest)
  - Configurable via `target_selection_mode: "closest" | "threat_scored"` (default: "threat_scored", "closest" for backward compat)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Commander intent integration:
  - OODA DECIDE phase can set priority target types per unit
  - Priority targets get score bonus (2x multiplier)

**Tests** (~10):
- Threat-scored selection prefers high-threat target over closer low-threat
- Anti-tank weapon prioritizes tanks over infantry
- AA weapon prioritizes aircraft over ground
- Commander intent (priority target type) gets score bonus
- "closest" mode preserves existing behavior for backward compat
- Multiple units don't all target the same enemy (fire distribution)

### 41d: Detection Pipeline Wiring

Instantiate the 4 disconnected detection engines and wire detection quality into engagement.

- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate:
  - `IntelFusionEngine` from `detection/intel_fusion.py`
  - `DeceptionEngine` from `detection/deception.py`
  - `SonarEngine` from `detection/sonar.py` (naval scenarios)
  - `UnderwaterDetectionEngine` from `detection/underwater_detection.py` (submarine scenarios)
  - `IdentificationEngine` from `detection/identification.py`
  - Attach to `SimulationContext`
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Detection quality modulates engagement:
  - Query detection confidence/SNR for target contact
  - Higher SNR → better Pk (precise tracking enables accurate fire)
  - Low SNR (marginal detection) → reduced Pk penalty
  - Target ID confidence stored for Phase 42 ROE integration
  - Formula: `detection_quality_mod = min(1.0, max(0.3, snr_linear / snr_threshold))`

**Tests** (~10):
- IntelFusionEngine instantiated from scenario loader
- SonarEngine instantiated for naval scenarios
- High-SNR detection has no Pk penalty
- Low-SNR (marginal) detection has reduced Pk
- Undetected targets cannot be engaged
- Detection pipeline gracefully handles missing sensors (no crash)

### Exit Criteria
- Terrain cover reduces hit probability (forest ≈ 50%, urban ≈ 80%)
- Elevation advantage provides +10-30% hit bonus
- Mud/saturated ground penalizes cavalry charges
- Elite units outperform regular units beyond just numbers
- Target selection prioritizes threats over proximity
- Detection quality modulates engagement accuracy
- All existing tests pass unchanged

---

## Phase 42: Tactical Behavior

**Goal**: Wire the ROE engine into the battle loop, implement hold-fire / effective range discipline, improve victory conditions with quality-weighting and morale-based victory, and complete morale-suppression feedback loops.

**Status**: **Complete**.

**Dependencies**: Phase 41 (target scoring informs ROE decisions, force quality feeds victory conditions).

### 42a: Hold-Fire & ROE Wiring

Wire the existing `RoeEngine` and add effective range discipline.

- **`stochastic_warfare/combat/weapons.py`** (modified) -- Add `effective_range_m` field to weapon definitions (alongside existing `max_range_m`). Default: 80% of `max_range_m`. Scenario/era-specific overrides:
  - Smoothbore musket: effective 100m, max 200m
  - Longbow: effective 150m, max 250m
  - Modern rifle: effective 400m, max 800m
  - Tank gun: effective 2000m, max 3500m
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Engagement range discipline:
  - Defensive units prefer to hold fire until target crosses `effective_range_m`
  - Configurable per doctrine: `hold_fire_until_effective_range: true` in behavior rules
  - Outside effective range: fire with natural Phit degradation (existing dispersion model handles this)
  - Inside effective range: fire normally
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate `RoeEngine` and attach to `SimulationContext`
- **`stochastic_warfare/simulation/battle.py`** (modified) -- ROE gate before engagement:
  - Call `roe_engine.check_engagement_authorized(attacker, target, roe_level)` before each engagement
  - Respect WEAPONS_HOLD (self-defense only), WEAPONS_TIGHT (positive ID required), WEAPONS_FREE (fire at will)
  - Combine with target ID confidence from Phase 41d: WEAPONS_TIGHT requires identification_confidence > threshold

**Tests** (~12):
- Defensive unit holds fire until target enters effective range
- Offensive unit fires at max range (no hold-fire)
- WEAPONS_HOLD: unit does not fire unless being fired upon
- WEAPONS_TIGHT: unit fires only on positively identified targets
- WEAPONS_FREE: unit fires at all detected targets
- ROE blocks engagement when unauthorized
- Effective range defaults to 80% of max range
- Hold-fire behavior configurable per doctrine/side

### 42b: Victory Condition Improvements

Extend the victory evaluator with quality-weighted assessment and morale-based victory.

- **`stochastic_warfare/simulation/victory.py`** (modified) -- Quality-weighted force advantage:
  - Replace raw `active_count / total_count` with `sum(active_quality) / sum(total_quality)` where quality = `training_level * combat_power`
  - 10 elite units surviving ≈ 18 regular units in force advantage
- **`stochastic_warfare/simulation/victory.py`** (modified) -- Morale-based victory:
  - New victory condition type: `MORALE_COLLAPSE`
  - Triggered when >60% of a side's units are ROUTED or SURRENDERED
  - Morale cascade: adjacent units of a routed side get morale penalty
- **`stochastic_warfare/simulation/victory.py`** (modified) -- Composite time_expired adjudication:
  - Replace simple "who has more active units" with composite score:
    ```python
    score = (0.3 * force_ratio +
             0.3 * territory_score +
             0.2 * casualty_exchange_ratio +
             0.2 * morale_ratio)
    ```
  - Configurable weights in scenario YAML (different battles weight differently)

**Tests** (~10):
- Quality-weighted: 10 elite (0.9) beats 15 regular (0.5) in force advantage
- Morale collapse: >60% routed triggers defeat
- Time_expired: composite score used instead of raw count
- Composite weights configurable per scenario
- Backward compat: default weights match current behavior for existing scenarios

### 42c: Morale-Suppression Feedback

Complete the morale cascade mechanic with suppression feeding into morale degradation.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Suppression feeds morale:
  - After computing suppression levels (from 40e), pass suppression as a factor to morale engine
  - High suppression → faster morale degradation
  - This creates the feedback loop: fire → suppression → morale degradation → accuracy loss → rout
- **`stochastic_warfare/morale/state.py`** (modified) -- Enforce morale effects in combat:
  - Verify SHAKEN (0.7 accuracy) and BROKEN (0.3) multipliers are applied via battle.py engagement modifier (wired in 40f)
  - Add suppression_weight to morale degradation calculation (already exists as config field, verify it's being used with actual suppression values)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Morale cascade:
  - When a unit routs, adjacent units of same side get morale penalty (cascade effect)
  - Cascading rout enables morale-based defeat (42b)

**Tests** (~8):
- Sustained suppression degrades morale faster than unsuppressed
- Morale cascade: one rout triggers adjacent morale checks
- Full feedback loop: fire → suppression → morale break → rout → cascade → defeat
- Morale-based victory triggers when cascade reaches 60% threshold

### Exit Criteria
- ROE engine gates engagements (WEAPONS_HOLD blocks fire except self-defense)
- Defensive units hold fire until effective range
- Victory evaluator uses quality-weighted force ratios
- Morale collapse is a first-class victory condition
- Suppression-morale feedback loop produces realistic rout cascades
- All existing tests pass unchanged

---

## Phase 43: Domain-Specific Resolution

**Goal**: Route engagements to era-appropriate aggregate models (volley fire, massed archery, barrage) and domain-appropriate engines (indirect fire, 5 naval combat engines). Formation-based casualty assessment and simultaneous fire coordination.

**Status**: Complete.

**Dependencies**: Phase 42 (hold-fire discipline required for volley coordination; terrain affects aggregate fire).

### 43a: Era-Aware Engagement Routing

Route pre-modern engagements to their aggregate fire models.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_execute_engagements()`, check `ctx.era`:
  - `Era.ANCIENT_MEDIEVAL`:
    - Ranged weapons → `ctx.archery_engine.fire_volley()` for massed archery
    - Melee range → `ctx.melee_engine.resolve_melee()`
  - `Era.NAPOLEONIC`:
    - Musket/rifle → `ctx.volley_fire_engine.fire_volley()` for volley fire
    - Cavalry charge → `ctx.cavalry_engine.execute_charge()`
    - Artillery → indirect fire routing (43b)
  - `Era.WW1`:
    - Rifle → `ctx.volley_fire_engine.fire_volley()` (modified for bolt-action rate)
    - MG → individual engagement (high rate, sustained suppression)
    - Artillery → `ctx.barrage_engine.execute_barrage()` for creeping barrage
  - `Era.WW2` / `Era.MODERN`:
    - Continue using existing `EngagementEngine.execute_engagement()`
- **Aggregate casualty application**:
  - Aggregate models return total casualties per volley (e.g., 150 muskets × 5% = 7.5 expected casualties)
  - Apply as fractional unit damage: each volley reduces target unit's effective strength
  - Map fractional damage to individual unit destruction events (probabilistic)
- **Simultaneous fire coordination**:
  - Multiple units of same type targeting same enemy fire in coordinated volley
  - Combined Phit computation instead of sequential individual shots

**Tests** (~15):
- Napoleonic musket engagement routes to volley fire engine
- Ancient archery routes to archery engine
- WW1 artillery routes to barrage engine
- Modern engagement routes to standard engagement engine (unchanged)
- Aggregate casualties: 100 archers at 100m produce realistic hit count (~12 per volley)
- Volley fire: 500 muskets at 100m produce ~25 casualties per volley
- Era routing configurable (can override per scenario)
- Backward compat: modern scenarios unaffected

### 43b: Indirect Fire Routing

Route artillery and mortar engagements to the indirect fire engine.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Weapon category routing:
  - If `weapon.category in (ARTILLERY, MORTAR)`: route to `ctx.indirect_fire_engine`
  - Indirect fire uses CEP-based area effect, not direct-fire Pk
  - Minimum engagement range enforced (mortars cannot fire at 10m)
  - Fire mission timing: request → compute → flight time → impact (delay, not instant)
  - Observer correction: accuracy improves over successive fire missions on same target
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate `IndirectFireEngine` and attach to context

**Tests** (~8):
- Artillery engagement routes to indirect fire engine
- Indirect fire uses CEP (area effect, not point target Pk)
- Minimum range enforced
- Observer correction improves accuracy
- Mortar routing works
- Direct-fire weapons still use standard engine

### 43c: Naval Domain Routing

Route naval engagements to the 5 specialized naval engines.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Naval engagement type routing:
  - Surface-to-surface → `NavalSurfaceEngine`
  - Submarine torpedo → `NavalSubsurfaceEngine`
  - WW1/WW2 gun duel → `NavalGunneryEngine` (bracket convergence)
  - Shore bombardment → `NavalGunfireSupportEngine`
  - Mine encounter → `MineWarfareEngine`
  - Determine engagement type from unit domains and weapon categories
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate naval engines for scenarios with naval units:
  - `NavalSurfaceEngine`, `NavalSubsurfaceEngine`, `NavalGunneryEngine`, `NavalGunfireSupportEngine`, `MineWarfareEngine`
  - Attach to `SimulationContext`
  - Only instantiate when scenario has naval units (no overhead for land-only scenarios)

**Tests** (~12):
- Surface naval engagement routes to NavalSurfaceEngine
- Torpedo engagement routes to NavalSubsurfaceEngine
- WW2 gunnery routes to NavalGunneryEngine (bracket convergence)
- Shore bombardment routes correctly
- Land-only scenario does not instantiate naval engines
- Naval engagement produces domain-appropriate results (bracket convergence, not rifle Pk)

### Exit Criteria
- Napoleonic battles produce meaningful casualties via volley fire (not 3 total in 7200 ticks)
- Ancient archery volleys from 100 archers produce realistic attrition
- Artillery uses CEP-based area effect, not direct-fire Pk
- Naval battles use bracket convergence and torpedo mechanics, not generic Pk
- Era routing is data-driven and configurable
- All existing tests pass unchanged

---

## Phase 44: Full Subsystem Integration

**Goal**: Wire ALL remaining disconnected subsystem engines into the simulation loop: CBRN, EW, Space/GPS, weather/night, logistics (8 engines), population (5 engines), strategic/campaign (4 engines), and command authority.

**Status**: **Complete**. 37 tests. Zero new source files — pure instantiation + query wiring.

**Dependencies**: Phase 43 (engagement routing framework enables subsystem modifier injection). Phase 41 (detection pipeline required for command picture).

### 44a: CBRN/EW/Space Integration

Wire the three specialized domain engines into the engagement loop.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- CBRN in engagement:
  - Query `ctx.cbrn_engine` contamination grid at unit position each tick
  - Apply chemical/radiation exposure as damage (use existing CBRN casualty model)
  - Check MOPP level for protection factor
  - Nuclear detonation: apply blast/thermal/radiation damage from `ctx.nuclear_engine` output to all units in radius
- **`stochastic_warfare/simulation/battle.py`** (modified) -- EW in engagement:
  - Query `ctx.ew_engine` for J/S ratio at sensor locations
  - Apply jamming degradation to detection range in target acquisition
  - GPS spoofing affects guided weapon Pk: `pk_mod *= gps_accuracy_factor`
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Space/GPS in engagement:
  - Query `ctx.gps_engine` for current DOP at unit location
  - Apply CEP degradation to guided weapon accuracy
  - SATCOM disruption affects C2 order propagation delay

**Tests** (~15):
- Chemical contamination causes casualties in battle loop
- MOPP protection reduces chemical casualties
- Nuclear blast applies damage to units in radius
- EW jamming degrades detection range
- GPS denial degrades guided weapon accuracy
- SATCOM disruption increases C2 delay

### 44b: Weather & Night Effects

Wire detailed weather and astronomy into engagement resolution.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Weather effects on combat:
  - Query weather engine for current conditions
  - Rain: Pk penalty (light=5%, heavy=15%)
  - Fog: Pk penalty 30%, detection range halved
  - Storm: Pk penalty 40%
  - Sea state: naval gunnery dispersion increases with wave height
  - Wind vector: pass to ballistic trajectory (already in RK4 model)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Night/day effects:
  - Query `ctx.astronomy_engine` for solar elevation and illumination
  - Night (sun below horizon): visual detection range reduced 50-80%
  - Thermal/NVG sensors unaffected or enhanced at night
  - Dawn/dusk: silhouette advantage (backlit targets easier to spot from west at dawn, east at dusk)

**Tests** (~10):
- Rain reduces Pk by configured percentage
- Fog halves detection range
- Night reduces visual detection (not thermal)
- NVG-equipped unit has advantage at night
- Sea state increases naval gunnery dispersion
- Clear day has no weather penalty

### 44c: Logistics Engine Wiring

Call the 8 logistics engines from the simulation loop.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Per-tick logistics calls:
  - `MaintenanceEngine.check_breakdowns()`: equipment can fail (Poisson), temporarily removing units
  - `MedicalEngine.process_casualties()`: wounded units enter M/M/c evacuation queue
  - `EngineeringEngine.update()`: obstacle creation/clearance progress
  - `TransportEngine.route_supplies()`: supply delivery
  - `DisruptionEngine.check_interdiction()`: enemy action on supply routes
  - `NavalLogisticsEngine.update()` / `NavalBasingEngine.update()`: naval supply ops
  - `PrisonerEngine.update()`: prisoner handling
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Supply gates combat capability:
  - Low ammo (< 20%): reduced fire rate (50%)
  - No ammo: cannot fire
  - No fuel: cannot move (immobile)
  - Low supply: morale penalty

**Tests** (~15):
- Maintenance engine causes equipment breakdown
- Broken equipment temporarily unavailable
- Medical engine evacuates wounded
- Low ammo reduces fire rate
- No fuel immobilizes unit
- Supply state affects morale

### 44d: Population & Strategic Engines

Wire population/civilian engines and strategic/campaign engines.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Population engine calls:
  - `CivilianManager.update()`: civilian population tracking
  - `CollateralEngine.assess()`: collateral damage → feeds escalation engine
  - `DisplacementEngine.update()`: refugee flow
  - `CivilianHumintEngine.collect()`: civilian intelligence
  - `InfluenceEngine.update()`: hearts-and-minds
- **`stochastic_warfare/simulation/campaign.py`** (modified) -- Strategic engine calls:
  - `AirCampaignEngine.update()`: air campaign phase management
  - `IadsEngine.update()`: integrated air defense
  - `StrategicBombingEngine.execute()`: strategic target destruction
  - `StrategicTargetingEngine.plan()`: deep strike planning
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate `CommandEngine`:
  - Replace `command_engine=None` with actual instantiation
  - Wire hierarchical authority and command range into OODA timing
  - Units outside command range have degraded initiative (slower OODA cycle)

**Tests** (~15):
- Collateral damage feeds escalation level
- Civilian displacement occurs in COIN scenarios
- Command authority loss degrades subordinate initiative
- Strategic bombing engine called in campaign scenarios
- IADS engine affects air defense in EW scenarios
- Population engines handle empty population gracefully

### Exit Criteria
- Chemical contamination causes tactical casualties
- Nuclear detonation damages units in blast radius
- EW jamming degrades detection and guided weapon accuracy
- Night combat favors thermal-sensor-equipped units
- Weather affects hit probability and detection range
- Equipment breaks down over campaign duration
- Low supply restricts combat capability
- Collateral damage affects escalation
- Command authority loss degrades unit initiative
- All existing tests pass unchanged

---

## Phase 45: Mathematical Model Audit & Hardening

**Goal**: Replace simplified or physics-incorrect mathematical models with appropriate formulations, validate all unsourced constants against military/scientific literature, and move key tuning parameters to configurable pydantic models.

**Status**: **Complete**. 21 new tests (7,565 total Python passing). 11 modified source files + 1 modified test file + 1 new test file.

**Dependencies**: Phases 40--44 (all systems must be wired before formulas can be hardened -- changing a formula in an unwired system has no observable effect).

**Deliverables**: AssessmentConfig pydantic model for configurable thresholds, Hopkinson-Cranz overpressure blast model replacing Gaussian, Weibull maintenance distribution option, `explosive_fill_kg` field on ammo definitions, `moderate_condition_floor` for hit probability bounds, citation comments on 9 source files, exponential threat cost in pathfinding. Sub-phases completed: 45e (Constant Sourcing & Config), 45d (Hit Probability Review), 45b (Morale Constant Validation), 45c (Maintenance Model Review), 45a (Blast Damage Model).

### 45a: Blast Damage Model

Replace the Gaussian blast damage envelope with physics-based overpressure scaling.

- **`stochastic_warfare/combat/damage.py`** (modified) -- Replace `P_kill = exp(-d²/2σ²)` with Hopkinson-Cranz overpressure:
  - `overpressure_psi = K * (scaled_distance)^(-a)` where `scaled_distance = R / W^(1/3)`
  - Regime-dependent exponent: strong shock (a≈2.65), weak shock (a≈1.4)
  - Kill/injury/suppression thresholds from overpressure level (same approach as `cbrn/nuclear.py`, scaled to conventional weapons)
  - Posture protection reduces effective overpressure exposure
  - Source constants from Glasstone & Dolan or Army TM 60A-1-1-31

**Tests** (~6):
- Overpressure decreases with distance (inverse power law, not Gaussian)
- Kill radius matches expected values for common explosive weights
- Posture protection reduces effective overpressure
- Fragmentation still uses separate 1/r² model

### 45b: Morale Constant Validation

Source morale Markov chain constants from military research literature.

- **`stochastic_warfare/morale/state.py`** (modified) -- Research and replace arbitrary constants:
  - Use `/research-military` skill to find: Dupuy "Attrition" WEI/WUV methodology, S.L.A. Marshall "Men Against Fire", NATO STANAG on combat stress, Rowland "The Stress of Battle"
  - Replace `casualty_weight=2.0` with literature-derived value
  - Replace `suppression_weight=1.5` with literature-derived value
  - Replace `leadership_weight=0.3`, `cohesion_weight=0.4` with literature-derived values
  - Add source citations as code comments
  - Validate: Monte Carlo of morale transitions should match published combat participation rates (~15-25% of soldiers actively fire, per Marshall)

**Tests** (~4):
- Updated constants produce morale transition rates consistent with literature
- High-casualty scenario produces rout within expected timeframe
- Morale recovery rates match rehabilitation timelines

### 45c: Maintenance Model Review

Evaluate Weibull distribution as replacement for exponential time-to-failure.

- **`stochastic_warfare/logistics/maintenance.py`** (modified) -- Consider Weibull:
  - Weibull shape parameter k: k<1 = infant mortality, k=1 = exponential (current), k>1 = wear-out
  - Military equipment typically k=1.2--1.8 (gradual wear-out)
  - Source MTBF values from MIL-HDBK-217F reliability prediction
  - If Weibull adoption warranted: replace `1 - exp(-dt/MTBF)` with `1 - exp(-(t/η)^k)` where η = scale, k = shape
  - Make k and η configurable per unit type in YAML

**Tests** (~4):
- Weibull with k=1 matches current exponential behavior
- Weibull with k=1.5 produces increasing failure rate over time
- MTBF from MIL-HDBK matches expected equipment reliability

### 45d: Hit Probability Review

Review multiplicative modifier chain for theoretical soundness.

- **`stochastic_warfare/combat/hit_probability.py`** (modified) -- Audit modifier independence:
  - Current: `Phit = disp × skill × motion × vis × posture × unc × cond`
  - Verify modifiers don't compound to unrealistic values in moderate conditions
  - Consider bounding composite modifier: `max(min_phit, min(max_phit, Phit))`
  - Evaluate if conditional probability formulation is more appropriate for any modifier pair
  - Document theoretical basis for each modifier in code comments

**Tests** (~4):
- Moderate conditions don't produce unrealistically low Phit
- Extreme conditions produce appropriately low Phit
- Min/max bounds prevent degenerate values

### 45e: Constant Sourcing & Configuration

Source the 10 critical unsourced constant groups and make key parameters configurable.

- **`stochastic_warfare/combat/damage.py`** (modified) -- Source armor effectiveness table from military engineering data. Add citations.
- **`stochastic_warfare/combat/damage.py`** (modified) -- Source posture blast/frag protection from military engineering manuals. Add citations.
- **`stochastic_warfare/combat/naval_subsurface.py`** (modified) -- Source torpedo evasion/CM probabilities from naval warfare literature. Add citations.
- **`stochastic_warfare/combat/naval_gunnery.py`** (modified) -- Source bracket convergence and base Pk from WW2 gunnery records. Add citations.
- **`stochastic_warfare/detection/sonar.py`** (modified) -- Source convergence zone depths from oceanographic data (replace hardcoded 55km/110km). Add citations.
- **`stochastic_warfare/c2/ai/assessment.py`** (modified) -- Move ~30 threshold constants to `AssessmentConfig` pydantic model. Source weights from FM 5-0/FM 6-0 if possible. Add citations.
- **`stochastic_warfare/morale/state.py`** (modified) -- Move morale weights to `MoraleConfig` (already partially there). Add source citations.
- **`stochastic_warfare/logistics/maintenance.py`** (modified) -- Source MTBF from MIL-HDBK-217F. Add citations.
- **`stochastic_warfare/escalation/ladder.py`** (modified) -- Source desperation index weights from escalation theory. Add citations.
- **`stochastic_warfare/movement/pathfinding.py`** (modified) -- Replace linear threat cost with exponential: `cost = k * exp(α * (1 - d/radius))`

**Tests** (~10):
- Each sourced constant produces expected behavior in its domain
- Configurable parameters load from YAML overrides
- Default values match previous behavior (backward compat where appropriate)
- Exponential threat avoidance produces steeper cost near threat center

### Exit Criteria
- Blast damage uses overpressure physics, not Gaussian game mechanic
- Morale constants sourced from military research with citations
- All 10 critical constant groups have documented sources
- Key tuning parameters movable to YAML configuration
- All existing tests pass (or updated where formula changes produce different results)

---

## Phase 46: Scenario Data Cleanup & Expansion

**Goal**: Fix faction/unit mismatches in scenario YAML files and create missing era/faction-appropriate unit definitions.

**Status**: **Complete**. 57 new tests (7,622 total Python passing). 21 new YAML data files + 9 modified scenario YAML + 1 new test file + 2 modified test files. Zero new Python source files.

**Dependencies**: Phase 45 (model hardening should precede data cleanup so calibration targets are stable).

**Deliverables**: 6 new unit types (SA-6 Gainful, A-4 Skyhawk, Carthaginian Infantry, Numidian Cavalry, Insurgent Squad, Civilian Noncombatant), 4 new weapons (sa6_3m9, mk12_20mm, ak47, rpg7), 4 new ammo types (3m9_sam, 20mm_mk100, 7_62x39_fmj, pg7_heat), 2 new sensors (1s91_straight_flush, apq94_radar), 5 new signatures (sa6_gainful, a4_skyhawk, carthaginian_infantry, numidian_cavalry, insurgent_squad, civilian_noncombatant). 9 scenarios corrected: Bekaa Valley, Gulf War EW, Falklands San Carlos, Cannae, Eastern Front 1943, COIN Campaign, Hybrid Gray Zone, Srebrenica, Halabja.

### 46a: Adversary Unit Corrections

Fixed 4 scenarios using wrong-faction equipment.

- **46a-1: SA-6 Gainful** (5 new files) -- `sa6_gainful.yaml` (unit), `sa6_3m9.yaml` (weapon), `3m9_sam.yaml` (ammo), `1s91_straight_flush.yaml` (sensor), `sa6_gainful.yaml` (signature). Replaced US Patriot in Bekaa Valley 1982 and Gulf War EW 1991 scenarios.
- **46a-2: A-4 Skyhawk** (5 new files) -- `a4_skyhawk.yaml` (unit), `mk12_20mm.yaml` (weapon), `20mm_mk100.yaml` (ammo), `apq94_radar.yaml` (sensor), `a4_skyhawk.yaml` (signature). Replaced MiG-29A in Falklands San Carlos scenario. A-4 is attack aircraft (not fighter) -- historically correct for Argentine air raids.
- **46a-3: Carthaginian Units** (4 new files) -- `carthaginian_infantry.yaml` + `numidian_cavalry.yaml` (units), `carthaginian_infantry.yaml` + `numidian_cavalry.yaml` (signatures). Reused existing gladius/pilum weapons. Replaced roman_legionary_cohort (on Carthaginian side) and mongol_horse_archer at Cannae. Roman cavalry: `norman_knight_conroi` replaced with `saracen_cavalry` (closer to pre-medieval light cavalry).

### 46b: Era/Faction Infantry

Replaced `us_rifle_squad` proxies in 5 scenarios plus fixed 1 era tag.

- **46b-1: Eastern Front 1943** (0 new files) -- Changed `era: modern` → `era: ww2`. Replaced US units with existing WW2 units: `soviet_rifle_squad` + `t34_85` (blue/Soviet), `wehrmacht_rifle_squad` + `panzer_iv_h` + `tiger_i` (red/German).
- **46b-2: Insurgent Squad** (6 new files) -- `insurgent_squad.yaml` (unit), `ak47.yaml` (weapon), `rpg7.yaml` (weapon), `7_62x39_fmj.yaml` (ammo), `pg7_heat.yaml` (ammo), `insurgent_squad.yaml` (signature). Replaced `us_rifle_squad` in COIN Campaign (red), Hybrid Gray Zone (red), Srebrenica (both sides with display_name overrides). Also replaced `m3a2_bradley` with `t72m` in Srebrenica (Bosnian Serbs used Yugoslav army equipment).
- **46b-3: Civilian Noncombatant** (2 new files) -- `civilian_noncombatant.yaml` (unit, empty equipment list), `civilian_noncombatant.yaml` (signature). Replaced `us_rifle_squad` in Halabja 1988 (blue/Kurdish civilians). Red side uses `insurgent_squad` + `t72m` (Iraqi Republican Guard).

**Tests** (57 in `tests/unit/test_phase_46_data.py`):
- Schema validation: all new units, weapons, ammo, sensors, signatures load via pydantic
- Scenario load: all 9 modified scenarios load as valid YAML with correct structure
- Unit property: SA-6 range, A-4 speed, insurgent weapons, civilian no-weapons, Carthaginian melee
- Faction validation: no wrong-faction units remain in modified scenarios
- Cross-reference: weapon→ammo refs resolve
- 2 existing tests updated (Cannae cavalry check, civilian empty equipment)

### Exit Criteria
- No scenario uses wrong-faction equipment (no US Patriot as Soviet SAM) ✓
- No scenario uses `us_rifle_squad` as a proxy for non-US infantry ✓
- All scenarios use era-appropriate units ✓
- All new unit YAML passes pydantic validation ✓
- All 7,622 tests pass ✓

---

## Phase 47: Full Recalibration & Validation

**Goal**: Systematically calibrate all 42 scenarios against historical outcomes using the fully wired and hardened engine. Establish Monte Carlo confidence intervals and create regression tests.

**Status**: Not started.

**Dependencies**: Phases 40--46 (all engine improvements, model hardening, and data cleanup must be complete).

### 47a: Historical Scenario Calibration

Run each of the 16 historical scenarios through Monte Carlo and calibrate to match documented outcomes.

- For each historical scenario:
  - Run N=100 Monte Carlo iterations
  - Record: winner distribution, casualty ratios, battle duration, victory condition type
  - Compare against documented historical outcome
  - Adjust scenario YAML as needed: terrain features, force quality values, engagement rules, reinforcement timing
  - Document calibration rationale in scenario YAML comments
- **Target outcomes**:
  - Agincourt: English decisive victory (archers + mud dominate)
  - Cannae: Carthaginian decisive (encirclement, Roman rout)
  - Salamis: Greek decisive (strait channeling negates Persian numbers)
  - Trafalgar: British decisive (gunnery superiority, 0 British ships sunk)
  - Austerlitz: French decisive (maneuver, concentrated attack)
  - Waterloo: British victory (defensive hold + Prussian arrival)
  - Somme: German defensive victory (7:1 casualty ratio)
  - Midway: USN decisive (intelligence, carrier vulnerability)
  - Stalingrad: Soviet holds (urban defense, reinforcements)
  - Golan: Israeli victory (hull-down, gunnery, 4.6:1 exchange ratio)
  - 73 Easting: Blue decisive (training superiority)
  - And remaining historical scenarios

### 47b: Contemporary Scenario Validation

Verify modern/contemporary scenarios produce plausible results.

- Run each contemporary scenario through Monte Carlo (N=50)
- Verify: no domain mismatch artifacts, reasonable casualty ratios, plausible victory conditions
- Verify: CBRN/EW/Space effects are observable in results
- Verify: escalation scenarios show escalation progression

### 47c: Regression Test Suite

Create a formal regression test for historical accuracy.

- **`tests/validation/test_historical_accuracy.py`** (new) -- Parametrized test:
  - For each of 16 historical scenarios: run N=20, verify correct winner with p > 0.8
  - Casualty ratio within 2x of historical for key battles
  - This test is `@pytest.mark.slow` (Monte Carlo)

**Tests** (~50):
- 16 historical scenarios × correct winner (parametrized)
- 13 contemporary scenarios × completion without mismatch artifacts
- Casualty ratio validation for key battles (Golan, Somme, 73 Easting)
- Regression: all scenarios complete without error

### Exit Criteria
- All 16 historical scenarios produce correct winner in >80% of Monte Carlo runs
- Casualty ratios within 2x of historical for calibrated battles
- All 42 scenarios complete without error
- Regression test codified in `test_historical_accuracy.py`
- Calibration rationale documented per scenario

---

## File Inventory

### Phase 40 (~8 modified + ~1 new test file)

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | `stochastic_warfare/simulation/victory.py` -- fix is_tie bug | 40a |
| MODIFY | `stochastic_warfare/simulation/battle.py` -- posture, fire-on-move, domain filter, suppression, morale | 40b/c/d/e/f |
| MODIFY | `stochastic_warfare/entities/unit_classes/ground.py` -- fire_on_move_penalty_mult | 40c |
| MODIFY | `stochastic_warfare/combat/weapons.py` -- target_domains field | 40d |
| MODIFY | `stochastic_warfare/simulation/scenario.py` -- instantiate suppression engine, terrain managers | 40e/g |
| NEW | `tests/unit/test_phase_40_foundation.py` | 40a-g |

### Phase 41 (~6 modified + ~1 new test file)

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | `stochastic_warfare/simulation/battle.py` -- terrain queries, quality mod, target scoring, detection quality | 41a/b/c/d |
| MODIFY | `stochastic_warfare/entities/base.py` -- training_level field | 41b |
| MODIFY | `stochastic_warfare/simulation/victory.py` -- quality-weighted force ratio | 41b |
| MODIFY | `stochastic_warfare/simulation/scenario.py` -- detection pipeline instantiation | 41d |
| MODIFY | Data YAML files -- training_level per unit | 41b |
| NEW | `tests/unit/test_phase_41_depth.py` | 41a-d |

### Phase 42 (~6 modified + ~1 new test file)

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | `stochastic_warfare/combat/weapons.py` -- effective_range_m field | 42a |
| MODIFY | `stochastic_warfare/simulation/battle.py` -- ROE gate, hold-fire, morale cascade | 42a/c |
| MODIFY | `stochastic_warfare/simulation/scenario.py` -- instantiate RoeEngine | 42a |
| MODIFY | `stochastic_warfare/simulation/victory.py` -- composite victory, morale collapse | 42b |
| MODIFY | `stochastic_warfare/morale/state.py` -- suppression integration | 42c |
| NEW | `tests/unit/test_phase_42_behavior.py` | 42a-c |

### Phase 43 (~8 modified + ~1 new test file)

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | `stochastic_warfare/simulation/battle.py` -- era routing, indirect fire routing, naval routing | 43a/b/c |
| MODIFY | `stochastic_warfare/simulation/scenario.py` -- instantiate aggregate/indirect/naval engines | 43a/b/c |
| MODIFY | `stochastic_warfare/combat/volley_fire.py` -- integration interface | 43a |
| MODIFY | `stochastic_warfare/combat/archery.py` -- integration interface | 43a |
| MODIFY | `stochastic_warfare/combat/indirect_fire.py` -- integration interface | 43b |
| MODIFY | `stochastic_warfare/combat/naval_surface.py` -- integration interface | 43c |
| MODIFY | `stochastic_warfare/combat/naval_subsurface.py` -- integration interface | 43c |
| NEW | `tests/unit/test_phase_43_routing.py` | 43a-c |

### Phase 44 (~12 modified + ~1 new test file)

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | `stochastic_warfare/simulation/battle.py` -- CBRN/EW/GPS/weather/night in engagement | 44a/b |
| MODIFY | `stochastic_warfare/simulation/engine.py` -- logistics tick calls, population calls | 44c/d |
| MODIFY | `stochastic_warfare/simulation/campaign.py` -- strategic engine calls | 44d |
| MODIFY | `stochastic_warfare/simulation/scenario.py` -- instantiate all remaining engines, CommandEngine | 44a-d |
| MODIFY | `stochastic_warfare/logistics/maintenance.py` -- integration interface | 44c |
| MODIFY | `stochastic_warfare/logistics/medical.py` -- integration interface | 44c |
| MODIFY | `stochastic_warfare/logistics/engineering.py` -- integration interface | 44c |
| MODIFY | `stochastic_warfare/population/civilians.py` -- integration interface | 44d |
| MODIFY | `stochastic_warfare/population/collateral.py` -- integration interface | 44d |
| MODIFY | `stochastic_warfare/c2/command.py` -- integration interface | 44d |
| MODIFY | `stochastic_warfare/combat/air_campaign.py` -- integration interface | 44d |
| NEW | `tests/unit/test_phase_44_integration.py` | 44a-d |

### Phase 45 (11 modified source + 1 modified test + 1 new test file) -- COMPLETE

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | `stochastic_warfare/combat/damage.py` -- Hopkinson-Cranz blast, explosive_fill_kg | 45a |
| MODIFY | `stochastic_warfare/morale/state.py` -- sourced constants, citation comments | 45b |
| MODIFY | `stochastic_warfare/logistics/maintenance.py` -- Weibull option | 45c |
| MODIFY | `stochastic_warfare/combat/hit_probability.py` -- moderate_condition_floor, modifier audit | 45d |
| MODIFY | `stochastic_warfare/combat/naval_subsurface.py` -- sourced constants, citations | 45e |
| MODIFY | `stochastic_warfare/combat/naval_gunnery.py` -- sourced constants, citations | 45e |
| MODIFY | `stochastic_warfare/detection/sonar.py` -- sourced convergence zones, citations | 45e |
| MODIFY | `stochastic_warfare/c2/ai/assessment.py` -- AssessmentConfig pydantic model | 45e |
| MODIFY | `stochastic_warfare/escalation/ladder.py` -- sourced weights, citations | 45e |
| MODIFY | `stochastic_warfare/movement/pathfinding.py` -- exponential threat cost | 45e |
| NEW | `tests/unit/test_phase_45_models.py` | 45a-e |

### Phase 46 (21 new YAML + 9 modified scenario YAML + 1 new test + 2 modified test) -- COMPLETE

| Action | File | Sub-phase |
|--------|------|-----------|
| NEW | `data/units/air_defense/sa6_gainful.yaml` | 46a |
| NEW | `data/weapons/missiles/sa6_3m9.yaml` | 46a |
| NEW | `data/ammunition/missiles/3m9_sam.yaml` | 46a |
| NEW | `data/sensors/1s91_straight_flush.yaml` | 46a |
| NEW | `data/signatures/sa6_gainful.yaml` | 46a |
| NEW | `data/units/air_fixed_wing/a4_skyhawk.yaml` | 46a |
| NEW | `data/weapons/guns/mk12_20mm.yaml` | 46a |
| NEW | `data/ammunition/autocannon/20mm_mk100.yaml` | 46a |
| NEW | `data/sensors/apq94_radar.yaml` | 46a |
| NEW | `data/signatures/a4_skyhawk.yaml` | 46a |
| NEW | `data/eras/ancient_medieval/units/carthaginian_infantry.yaml` | 46a |
| NEW | `data/eras/ancient_medieval/units/numidian_cavalry.yaml` | 46a |
| NEW | `data/eras/ancient_medieval/signatures/carthaginian_infantry.yaml` | 46a |
| NEW | `data/eras/ancient_medieval/signatures/numidian_cavalry.yaml` | 46a |
| NEW | `data/units/infantry/insurgent_squad.yaml` | 46b |
| NEW | `data/weapons/rifles/ak47.yaml` | 46b |
| NEW | `data/weapons/rockets/rpg7.yaml` | 46b |
| NEW | `data/ammunition/small_arms/7_62x39_fmj.yaml` | 46b |
| NEW | `data/ammunition/rockets/pg7_heat.yaml` | 46b |
| NEW | `data/signatures/insurgent_squad.yaml` | 46b |
| NEW | `data/units/civilian_noncombatant.yaml` | 46b |
| NEW | `data/signatures/civilian_noncombatant.yaml` | 46b |
| MODIFY | `data/scenarios/bekaa_valley_1982/scenario.yaml` -- SA-6 replaces Patriot | 46a |
| MODIFY | `data/scenarios/gulf_war_ew_1991/scenario.yaml` -- SA-6 replaces Patriot | 46a |
| MODIFY | `data/scenarios/falklands_san_carlos/scenario.yaml` -- A-4 replaces MiG-29 | 46a |
| MODIFY | `data/eras/ancient_medieval/scenarios/cannae/scenario.yaml` -- Carthaginian units | 46a |
| MODIFY | `data/scenarios/eastern_front_1943/scenario.yaml` -- era: ww2 + WW2 units | 46b |
| MODIFY | `data/scenarios/coin_campaign/scenario.yaml` -- insurgent_squad | 46b |
| MODIFY | `data/scenarios/hybrid_gray_zone/scenario.yaml` -- insurgent_squad | 46b |
| MODIFY | `data/scenarios/srebrenica_1995/scenario.yaml` -- insurgent_squad + t72m | 46b |
| MODIFY | `data/scenarios/halabja_1988/scenario.yaml` -- civilian_noncombatant + insurgent_squad | 46b |
| NEW | `tests/unit/test_phase_46_data.py` | 46a-b |
| MODIFY | `tests/validation/test_phase_23c_ancient_validation.py` -- numidian_cavalry | 46a |
| MODIFY | `tests/integration/test_phase2_integration.py` -- civilian no-equipment | 46b |

### Phase 47 (~42 YAML modified + ~1 new test file)

| Action | File | Sub-phase |
|--------|------|-----------|
| MODIFY | All 42 scenario YAML files -- calibration adjustments | 47a/b |
| NEW | `tests/validation/test_historical_accuracy.py` | 47c |

---

## Test Targets

| Phase | Sub-phase | New Tests | Focus |
|-------|-----------|-----------|-------|
| 40a | Victory bug | ~8 | is_tie fix, regression on 73 Easting/Bekaa |
| 40b | Posture | ~10 | Auto-assignment, DUG_IN protection, dig-in progression |
| 40c | Fire-on-move | ~6 | Speed penalty, stabilization multiplier, artillery gate |
| 40d | Domain filter | ~10 | Weapon-domain compat, multi-role, skip incompatible |
| 40e | Suppression | ~6 | Actual levels, accumulation, decay, backward compat |
| 40f | Morale enforcement | ~6 | SHAKEN/BROKEN/ROUTED multipliers applied |
| 40g | Terrain managers | ~6 | Instantiation, queryable, backward compat |
| 41a | Terrain-combat | ~20 | Cover, concealment, elevation, mud, channeling |
| 41b | Force quality | ~10 | Training level, quality-weighted ratios |
| 41c | Target selection | ~10 | Threat scoring, commander intent, fire distribution |
| 41d | Detection pipeline | ~10 | Instantiation, SNR→Pk modulation |
| 42a | Hold-fire / ROE | ~12 | Effective range, WEAPONS_HOLD/TIGHT/FREE |
| 42b | Victory conditions | ~10 | Quality-weighted, morale collapse, composite |
| 42c | Morale-suppression | ~8 | Feedback loop, cascade, morale defeat |
| 43a | Era routing | ~15 | Volley fire, archery, aggregate casualties |
| 43b | Indirect fire | ~8 | CEP, observer correction, min range |
| 43c | Naval routing | ~12 | 5 engine types, domain detection |
| 44a | CBRN/EW/Space | ~15 | Chemical casualties, jamming, GPS CEP |
| 44b | Weather/night | ~10 | Rain/fog/night effects, thermal advantage |
| 44c | Logistics | ~15 | Breakdowns, evacuation, supply gates |
| 44d | Population/strategic | ~15 | Collateral, command authority, air campaign |
| 45a | Blast model | ~6 | Hopkinson-Cranz, posture protection |
| 45b | Morale constants | ~4 | Literature-sourced values, validation |
| 45c | Maintenance model | ~4 | Weibull, MTBF sourcing |
| 45d | Hit probability | ~4 | Modifier audit, bounds |
| 45e | Constant sourcing | ~10 | 10 groups sourced, configurable, citations |
| 46a-b | Data cleanup | ~30 | New units load, scenarios run, era-appropriate |
| 47a-c | Recalibration | ~50 | Historical accuracy, Monte Carlo, regression |
| | **Total** | **~350** | |

---

## Implementation Order

```
Phase 40 ─── sequential sub-phases ────────────────────────────────────
  40a (is_tie fix) ──> 40b (posture) ──> 40c (fire-on-move)
       40d (domain filter, parallel with 40b/c)
       40e (suppression, parallel with 40b/c)
       40f (morale, after 40e)
       40g (terrain managers, parallel)

Phase 41 ─── depends on 40 ────────────────────────────────────────────
  41a (terrain-combat, depends on 40b+40g)
  41b (force quality, independent)
  41c (target selection, depends on 40d+41b)
  41d (detection pipeline, independent)

Phase 42 ─── depends on 41 ────────────────────────────────────────────
  42a (ROE + hold-fire, depends on 41c)
  42b (victory, depends on 41b)
  42c (morale-suppression, depends on 40e+40f)

Phase 43 ─── depends on 42 ────────────────────────────────────────────
  43a (era routing, depends on 41a+42a)
  43b (indirect fire, depends on 41a)
  43c (naval routing, independent)

Phase 44 ─── depends on 43 ────────────────────────────────────────────
  44a (CBRN/EW/Space, independent)
  44b (weather/night, independent)
  44c (logistics, independent)
  44d (population/strategic/command, depends on 41d)

Phase 45 ─── depends on 44 ────────────────────────────────────────────
  45a-e (all sequential — formula changes + sourcing)

Phase 46 ─── depends on 45 ────────────────────────────────────────────
  46a-b (data cleanup, can partially parallel with 45)

Phase 47 ─── depends on 46 ────────────────────────────────────────────
  47a-c (calibration, strictly last)
```

---

## Deficit Resolution

| Deficit | Origin | Resolved In |
|---------|--------|-------------|
| `is_tie` bug in `evaluate_force_advantage()` | Block 5 analysis | **40a** |
| Posture never passed to engagement engine | Phase 2 | **40b** |
| `shooter_speed_mps` always 0.0 | Phase 4 | **40c** |
| No domain filtering in target selection | Phase 2 | **40d** |
| Suppression hardcoded to 0.0 | Phase 4 | **40e** |
| Morale multipliers not enforced in engagements | Phase 4 | **40f** |
| Terrain managers not instantiated | Phase 1 | **40g** |
| Terrain cover/concealment not used in combat | Phase 1 | **41a** |
| Numerical advantage dominates (no quality) | Phase 2 | **41b** |
| Target selection always closest enemy | Phase 9 | **41c** |
| Detection pipeline not instantiated | Phase 3 | **41d** |
| Target ID confidence never assessed | Phase 3 | **41d** |
| ROE engine never called from battle loop | Phase 5 | **42a** |
| Engagement range = weapon max range | Phase 4 | **42a** |
| Morale effects only used in AI assessment | Phase 4 | **42c** |
| Aggregate models never called from battle loop | Phases 21--23 | **43a** |
| Indirect fire engine not routed | Phase 4 | **43b** |
| Naval engines never called from engagement loop | Phases 4/20 | **43c** |
| CBRN effects don't influence tactical combat | Phases 18/25 | **44a** |
| EW effects don't influence tactical combat | Phases 16/25 | **44a** |
| Space/GPS effects don't influence tactical combat | Phases 17/25 | **44a** |
| Weather effects stop at visibility_m | Phase 1 | **44b** |
| Night/day cycle has no combat effect | Phase 1 | **44b** |
| 7+ logistics engines never called | Phase 6 | **44c** |
| Population/civilian engines never called | Phases 12/24 | **44d** |
| Strategic/campaign engines never called | Phase 12 | **44d** |
| Command authority engine set to None | Phase 5 | **44d** |
| Blast damage uses Gaussian, not overpressure | Phase 4 | **45a** |
| Morale constants have no published sources | Phase 4 | **45b** |
| Maintenance uses exponential, not Weibull | Phase 6 | **45c** |
| Armor effectiveness table unsourced | Phase 4 | **45e** |
| 10 critical constant groups unsourced | Various | **45e** |
| Wrong-faction units in scenarios | Phase 30 | **46a** |
| `us_rifle_squad` used as universal proxy | Phase 30 | **46b** |

**Total**: ~33 deficits targeted for resolution across Block 5.

---

## Verification

```bash
# Phase 40: battle loop foundation
uv run python -m pytest tests/unit/test_phase_40_foundation.py --tb=short -q
uv run python -m pytest tests/ --tb=short -q   # full regression

# Phase 41: combat depth
uv run python -m pytest tests/unit/test_phase_41_depth.py --tb=short -q
uv run python -m pytest tests/ --tb=short -q

# Phase 42: tactical behavior
uv run python -m pytest tests/unit/test_phase_42_behavior.py --tb=short -q
uv run python -m pytest tests/ --tb=short -q

# Phase 43: domain-specific resolution
uv run python -m pytest tests/unit/test_phase_43_routing.py --tb=short -q
uv run python -m pytest tests/ --tb=short -q

# Phase 44: full subsystem integration
uv run python -m pytest tests/unit/test_phase_44_integration.py --tb=short -q
uv run python -m pytest tests/ --tb=short -q

# Phase 45: mathematical model hardening
uv run python -m pytest tests/unit/test_phase_45_models.py --tb=short -q
uv run python -m pytest tests/ --tb=short -q

# Phase 46: scenario data cleanup
uv run python -m pytest tests/unit/test_phase_46_data.py --tb=short -q
uv run python -m pytest tests/ --tb=short -q

# Phase 47: full recalibration + historical accuracy
uv run python -m pytest tests/validation/test_historical_accuracy.py --tb=short -q -m slow
uv run python -m pytest tests/ --tb=short -q   # complete regression

# Verify all 42 scenarios complete
uv run python -c "
from scripts.evaluate_scenarios import run_all_scenarios
results = run_all_scenarios()
for r in results:
    print(f'{r.scenario}: {r.winner} ({r.victory_type})')
"
```

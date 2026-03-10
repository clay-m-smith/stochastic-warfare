# Stochastic Warfare -- Block 6 Development Phases (49--57)

## Philosophy

Block 6 is the **final tightening block**. No new subsystems, no new UI features. The engine has 25+ instantiated-but-never-called engines, 10 dead YAML data fields, 3 fully implemented subsystems that were never even instantiated, a free-form calibration dict that silently swallows mistyped keys, and config fields that zero scenarios exercise. All were built in Phases 1--48 and tested in isolation, but they contribute nothing to simulation outcomes because they're disconnected.

This block wires every orphaned engine, hardens every schema, exercises every calibration parameter, and validates every scenario against historical outcomes. The exit criterion is zero unresolved deficits and zero dead code paths in the simulation core.

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block6.md` (design thinking, deficit inventory, dead engine audit), `devlog/index.md` (deficit inventory), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**Engine changes are wiring, not building**: Block 6 modifies `battle.py`, `engine.py`, `scenario.py`, and `campaign.py` extensively but creates minimal new source files. The work is connecting existing tested systems, not designing new ones.

---

## Phase 49: Calibration Schema Hardening

**Goal**: Replace the free-form `calibration_overrides: dict[str, Any]` with a typed pydantic `CalibrationSchema` validated at parse time. Clean up dead calibration data. Exercise all untested calibration paths in test scenarios.

**Dependencies**: Block 5 complete (Phases 40--48).

### 49a: Define CalibrationSchema Pydantic Model

Create a typed calibration schema that replaces the free-form dict.

- **`stochastic_warfare/simulation/calibration.py`** (new) -- `CalibrationSchema` pydantic model with ~100 known keys organized by subsystem:
  - `CombatCalibration`: `hit_probability_modifier`, `force_ratio_modifier`, `fire_on_move_penalty_mult`, `target_value_weights` (dict[str, float] with defaults HQ=2.0, AD=1.8, etc.), `blast_radius_to_fill_c` (dict[str, float] per munition category)
  - `MovementCalibration`: `advance_speed_mps` (replaces dead `advance_speed`), `dig_in_ticks`, `formation_spacing_m` (per-side prefixed)
  - `EngagementCalibration`: `engagement_range_m`, `min_engagement_range_m`, `thermal_contrast`, `wave_interval_s`, `target_selection_mode` (enum: THREAT_SCORED, NEAREST, RANDOM)
  - `VictoryCalibration`: `victory_weights` (morale/casualty/territory), `force_destroyed_threshold`, `morale_collapsed_threshold`
  - `MoraleCalibration`: `cohesion`, `leadership`, `suppression`, `transition_cooldown`, `rout_cascade_radius_m`, `rout_friendly_count_threshold`, `rout_morale_penalty`
  - `EnvironmentCalibration`: `visibility_km`, `weather_modifier`, `night_detection_modifier`
  - `NavalCalibration`: `torpedo_pk`, `attacker_pk`, `defender_pd_pk`, `engagement_range_nm`
  - `EraCalibration`: era-specific fields gated by era (volley fire params, archery volleys, melee modifiers, etc.)
  - All fields have defaults matching current hardcoded values -- zero behavioral change on migration

- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Replace `calibration_overrides: dict[str, Any] | None = None` with `calibration: CalibrationSchema = CalibrationSchema()`. ScenarioLoader validates at parse time. Invalid keys cause pydantic `ValidationError` at load, not silent pass-through.

**Tests** (~15):
- Schema loads with all defaults -- matches current hardcoded values
- Unknown key in YAML raises ValidationError
- Per-side prefixed fields (e.g., `blue_hit_probability_modifier`) resolve correctly
- Schema round-trips through YAML dump/load
- Era-specific fields ignored when era doesn't match

### 49b: Migrate All Scenario YAMLs

Migrate all ~37 scenario YAMLs from `calibration_overrides: {key: val}` to `calibration:` structured fields.

- **All scenario YAML files** (modified) -- Replace `calibration_overrides:` blocks with `calibration:` structured blocks. Automated migration script validates before/after equivalence.
- **Remove `advance_speed` from 10 scenario YAMLs** -- dead data. Wire `advance_speed_mps` into movement engine if meaningful, or remove entirely.
- **Fix calibration audit test** (`tests/unit/test_phase48_deficit_fixes.py`) -- Replace `_EXTERNAL_KEYS` string-list approach with schema-based validation. Remove false-positive `advance_speed` entry.

**Tests** (~10):
- All 37+ scenarios load without ValidationError
- Scenario output unchanged before/after migration (deterministic diff)
- Previously-dead keys either wired or removed

### 49c: Exercise Untested Calibration Paths

Create test scenarios that exercise every calibration parameter that currently has zero coverage.

- **`data/scenarios/calibration_test/`** (new) -- Synthetic test scenarios designed to exercise:
  - `dig_in_ticks`: scenario with defensive units that should dig in after N ticks
  - `wave_interval_s`: scenario with wave attack timing
  - `target_selection_mode`: scenario testing NEAREST vs THREAT_SCORED selection
  - `victory_weights`: scenario with composite victory scoring (morale + casualty weights)
  - `morale_config` weights: scenario with per-scenario morale tuning (cohesion, leadership, suppression)
  - `roe_level`: expand to 5+ additional scenarios (COIN, peacekeeping, hybrid gray zone)

**Tests** (~20):
- dig_in_ticks: units transition to DUG_IN after configured ticks
- wave_interval_s: engagements occur in waves with configured interval
- target_selection_mode NEAREST: units engage closest target regardless of threat
- target_selection_mode THREAT_SCORED: units engage highest-threat target
- victory_weights: morale-weighted victory differs from casualty-weighted
- morale_config: custom cohesion/leadership values change morale transition rates
- roe_level: WEAPONS_TIGHT prevents engagement below confidence threshold

**Resolves deficits**: E1, E2, E3, E4, E5, E6, E7, E10.

### Exit Criteria
- CalibrationSchema pydantic model validates all scenario YAMLs at parse time
- Zero `dict[str, Any]` calibration access in simulation code
- All 10 `advance_speed` dead data entries removed or wired
- All 7 previously-untested calibration paths exercised in at least one test scenario
- Morale config weights tuned in at least 3 representative scenarios
- ROE set in 7+ scenarios (up from 2)
- All existing tests pass unchanged
- ~45 new tests

---

## Phase 50: Combat Fidelity Polish

**Goal**: Wire posture → movement speed, air posture, continuous concealment, training level data, WW1 barrage penalty fix, configurable target value weights, and melee weapon range verification.

**Dependencies**: Phase 49 (calibration schema for new config fields).

### 50a: Posture Affects Movement Speed

DUG_IN and FORTIFIED units should not be able to move at full speed.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In movement phase, apply posture-based speed multiplier:
  - `MOVING`: 1.0x (no change)
  - `HALTED`: 1.0x (can resume)
  - `HASTY_DEFENSE`: 0.5x
  - `DUG_IN`: 0.0x (must un-dig to move; transition takes 1 tick)
  - `FORTIFIED`: 0.0x (permanent position)
- **`stochastic_warfare/movement/engine.py`** (modified) -- Accept `posture_speed_mult` parameter in `compute_movement()`.

**Tests** (~8):
- DUG_IN unit ordered to move: speed = 0 until posture transitions to MOVING
- HASTY_DEFENSE unit moves at 50% speed
- MOVING unit unaffected
- Transition from DUG_IN → MOVING takes 1 tick delay

**Resolves deficit**: D1.

### 50b: Air Unit Posture

Add air posture states that affect fuel, detection, and weapons availability.

- **`stochastic_warfare/entities/unit_classes/aerial.py`** (modified) -- Add `air_posture` enum: `GROUNDED`, `INGRESSING`, `ON_STATION`, `RETURNING`. Auto-assign based on unit state (distance to objective, fuel level, engagement status).
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Air posture affects:
  - `GROUNDED`: cannot engage, not detectable by radar (only ground sensors)
  - `INGRESSING`: high speed, reduced detection cross-section (aspect angle), limited weapons (no bombs while ingressing)
  - `ON_STATION`: normal engagement, full weapons availability
  - `RETURNING`: no engagement, fuel-critical, increased detection (defensive flight profile)

**Tests** (~8):
- Aircraft transitions GROUNDED → INGRESSING → ON_STATION → RETURNING based on mission state
- GROUNDED aircraft not eligible for air engagement
- INGRESSING aircraft has reduced detection cross-section
- ON_STATION aircraft can use all assigned weapons
- RETURNING aircraft does not engage

**Resolves deficit**: D3.

### 50c: Continuous Concealment

Replace binary hidden/revealed with a concealment score that degrades with sustained observation.

- **`stochastic_warfare/detection/detection.py`** (modified) -- Add `concealment_score` (0.0--1.0) per target track:
  - Initial concealment based on terrain type and unit posture (forest=0.9, urban=0.8, open=0.2)
  - Each tick of sustained detection reduces concealment by `observation_decay_rate` (default 0.05/tick)
  - Concealment modifies detection SNR: `effective_snr = snr - concealment_db` where `concealment_db = concealment_score * max_concealment_db`
  - Engagement authorization requires `concealment_score < engagement_concealment_threshold` (default 0.5)
- **`stochastic_warfare/detection/detection.py`** (modified) -- `DetectionConfig` gets `observation_decay_rate`, `max_concealment_db`, `engagement_concealment_threshold` fields.

**Tests** (~10):
- Unit in forest starts at 0.9 concealment
- Sustained observation reduces concealment by 0.05/tick
- Concealment below threshold allows engagement
- Concealment above threshold blocks engagement
- Moving unit resets concealment to terrain baseline
- Thermal/radar sensors have reduced concealment effect (multiply by 0.3)

**Resolves deficit**: D4.

### 50d: Training Level Data Population

Add `training_level` to unit YAML definitions. The engine code already reads it (battle.py:1822).

- **All unit YAML files** (~60 modified) -- Add `training_level` field:
  - Elite units (M1A2, F-22, SAS): 0.9
  - Veteran units (M1A1, F-15, Paratroopers): 0.8
  - Regular units (Bradley, Riflemen): 0.7
  - Conscript/militia (Insurgent, T-55): 0.5
  - Historical: Per-era defaults (Roman legionary=0.8, medieval levy=0.4, Napoleonic line=0.6)

**Tests** (~6):
- Unit with training_level=0.9 has higher effective_skill than 0.5
- Default training_level (0.5 if missing) matches current behavior
- Historical units have era-appropriate training levels

**Resolves deficit**: D14.

### 50e: WW1 Barrage Penalty Fix, Target Weights, Melee Range

Fix WW1 barrage accuracy, make target value weights configurable, verify melee weapon ranges.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Skip fire-on-move penalty for `BARRAGE` engagement type. Barrage accuracy is pre-planned fire, not aimed fire.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- `_score_target()` reads `target_value_weights` from `CalibrationSchema` instead of hardcoded dict. Default values match current: HQ=2.0, AD=1.8, ARTILLERY=1.5, ARMOR=1.2, INFANTRY=1.0.
- **`data/eras/*/weapons/`** (modified) -- Verify all melee weapons have `max_range_m: 0` or appropriate close-range value. Fix any that would be filtered out by range check.

**Tests** (~8):
- WW1 barrage engagement has no fire-on-move penalty applied
- Modern fire-on-move penalty still applies for non-barrage engagements
- Custom target_value_weights from calibration change target prioritization
- Default target_value_weights match current behavior
- All melee weapons pass range filtering for close combat

**Resolves deficits**: D7, Phase 41 target weights, Phase 43 melee range.

### Exit Criteria
- Posture affects movement speed (DUG_IN = 0.0x, HASTY = 0.5x)
- Air units have 4 posture states affecting engagement eligibility
- Concealment degrades continuously with observation duration
- All unit YAMLs have training_level set
- WW1 barrage exempt from fire-on-move penalty
- Target value weights configurable via calibration schema
- All melee weapons have correct max_range_m
- ~40 new tests

---

## Phase 51: Naval Combat Completeness -- COMPLETE

**Goal**: Wire existing naval engine methods into battle.py routing, implement naval posture, add DEW disable path, wire MineWarfareEngine and DisruptionEngine (blockade).

**Status**: Complete. 37 new tests, 0 regressions. 7 files modified + 1 test file created. 6 deficits resolved (D2, D6, D16, Phase 43 shore bombardment, Phase 6 blockade, Phase 6 VLS).

**Dependencies**: Phase 50 (posture system for naval posture).

### 51a: Wire Naval Engine Methods into Battle Routing

Connect the existing `NavalSubsurfaceEngine` and `NavalSurfaceEngine` methods to `_route_naval_engagement()`.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- `_route_naval_engagement()`:
  - Torpedo engagements → `ctx.naval_subsurface_engine.torpedo_engagement()`
  - Depth charge engagements → `ctx.naval_subsurface_engine.depth_charge_attack()`
  - Anti-ship missile engagements → `ctx.naval_surface_engine` salvo model
  - Naval gunnery → `ctx.naval_gunnery_engine` (WW2+ era) or `ctx.naval_surface_engine` gun method
  - Shore bombardment → verify platform is NAVAL domain before routing (fix Phase 43 bug)
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Verify `NavalSubsurfaceEngine`, `NavalSurfaceEngine`, `NavalGunfireSupportEngine` are set as named attributes on context (not just stored in a list).

**Tests** (~12):
- Torpedo weapon routes to torpedo_engagement()
- Depth charge routes to depth_charge_attack()
- Anti-ship missile routes to salvo model
- Shore bombardment from naval platform → naval gunfire support
- Shore bombardment from land artillery → does NOT route to naval gunfire support
- Naval weapon miss does not cascade to direct-fire fallback
- Backward compat: non-naval engagement unchanged

### 51b: Naval Posture

Implement naval posture affecting vulnerability, detection, and weapons readiness.

- **`stochastic_warfare/entities/unit_classes/naval.py`** (modified) -- Add `naval_posture` enum: `ANCHORED`, `UNDERWAY`, `TRANSIT`, `BATTLE_STATIONS`.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Naval posture effects:
  - `ANCHORED`: 0.0x speed, +50% detection cross-section, weapons limited to self-defense
  - `UNDERWAY`: normal speed, normal detection, normal weapons
  - `TRANSIT`: 1.2x speed, -20% detection (reduced emissions), weapons on standby (delay to engage)
  - `BATTLE_STATIONS`: 0.9x speed, full weapons readiness, +20% detection (all sensors active)
- Auto-assign based on unit state: near enemy → BATTLE_STATIONS, distant transit → TRANSIT, in port → ANCHORED.

**Tests** (~8):
- ANCHORED ship has zero movement speed
- BATTLE_STATIONS ship has full weapons readiness
- TRANSIT ship has engagement delay
- Posture auto-transitions based on enemy proximity

### 51c: DEW Disable Path

Add partial damage for DEW engagements instead of always destroying.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In DEW engagement resolution:
  - Below `dew_config.disable_threshold` (default 0.5): target → DISABLED (combat-ineffective but not destroyed)
  - Above threshold: target → DESTROYED (current behavior)
  - `beam_wavelength_nm` from weapon YAML feeds into Beer-Lambert atmospheric transmittance calculation (currently dead YAML field)

**Tests** (~6):
- DEW engagement below threshold → DISABLED
- DEW engagement above threshold → DESTROYED
- beam_wavelength_nm affects transmittance calculation
- DISABLED unit does not engage but counts for force ratio

**Resolves deficit**: D16.

### 51d: MineWarfareEngine and DisruptionEngine Wiring

Wire mine engagements and blockade mechanics.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Route mine encounters through `MineWarfareEngine`: when a naval unit enters a cell with mines, trigger mine warfare resolution.
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate `DisruptionEngine`, attach to context.
- **`stochastic_warfare/simulation/campaign.py`** (modified) -- Call `DisruptionEngine.check_blockade()` when computing naval supply routes.
- **`stochastic_warfare/logistics/supply_network.py`** (modified) -- When computing route cost for naval supply links, query blockade effectiveness for the zone and reduce throughput.

**Tests** (~10):
- Unit entering mined zone triggers mine engagement
- Mine trigger probability depends on unit signature match
- Blockade reduces supply throughput for blockaded zone
- No blockade → full throughput (backward compat)
- DisruptionEngine state persists through get_state/set_state

### Exit Criteria
- Naval engagements route through specialized engines (torpedo, depth charge, ASM, gunnery)
- Naval units have 4 posture states affecting combat
- DEW has disable/destroy threshold
- Mine encounters trigger mine warfare engine
- Blockade mechanics affect supply network
- beam_wavelength_nm YAML field wired into DEW calculations
- ~36 new tests

**Resolves deficits**: D2, D6, D16, Phase 43 shore bombardment, Phase 6 blockade, Phase 6 VLS.

---

## Phase 52: Environmental Continuity

**Goal**: Replace binary environmental gates with continuous functions. Night gradation, weather → ballistics, terrain-based comms LOS, space/EW SIGINT fusion.

**Dependencies**: Phase 49 (calibration schema for environmental params).

### 52a: Night Gradation

Replace binary day/night detection modifier with continuous function of solar elevation.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Replace binary night gate:
  ```python
  # BEFORE: binary
  if is_night: detection_mod *= 0.5

  # AFTER: continuous from AstronomyEngine solar_elevation_deg
  if solar_elev > 0:       mod = 1.0          # day
  elif solar_elev > -6:    mod = 0.8          # civil twilight
  elif solar_elev > -12:   mod = 0.5          # nautical twilight
  elif solar_elev > -18:   mod = 0.3          # astronomical twilight
  else:                    mod = 0.2          # full night
  # Thermal sensors: mod = max(0.8, mod)  -- thermal barely affected
  ```

**Tests** (~8):
- Solar elevation +10 deg → modifier 1.0
- Solar elevation -3 deg (civil twilight) → modifier 0.8
- Solar elevation -15 deg (astronomical) → modifier 0.3
- Thermal sensor at full night → modifier 0.8 (not 0.2)
- Backward compat: scenarios with no astronomy engine unchanged

**Resolves deficit**: D8.

### 52b: Weather Effects on Ballistics and Sensors

Wire wind drift into ballistic trajectories and precipitation into sensor attenuation.

- **`stochastic_warfare/combat/ballistics.py`** (modified) -- In RK4 trajectory computation, add cross-wind drift term: `dx_wind = wind_speed * sin(wind_dir - heading) * dt`. Wind data from `WeatherEngine.get_conditions()`.
- **`stochastic_warfare/detection/detection.py`** (modified) -- Precipitation attenuation on radar SNR: `rain_atten_db = k * R^alpha * range_km` where k/alpha from ITU-R P.838 lookup by frequency band (X-band k=0.01, Ka-band k=0.1, per mm/hr).
- **`stochastic_warfare/movement/formations.py`** (modified) -- Sea state → naval formation spacing: higher sea state increases minimum formation spacing.

**Tests** (~10):
- Cross-wind drift deflects trajectory proportional to wind speed
- Zero wind → no drift (backward compat)
- Heavy rain (10 mm/hr) at X-band → ~0.1 dB/km additional attenuation
- Clear weather → no rain attenuation
- Sea state 4+ increases naval formation minimum spacing

**Resolves deficit**: D9.

### 52c: Terrain-Based Comms LOS

Radio communications check terrain LOS between transmitter and receiver.

- **`stochastic_warfare/c2/communications.py`** (modified) -- When computing comms reliability:
  - If `los_engine` available on context, call `check_los(tx_pos, rx_pos)`
  - If terrain blocks LOS: apply diffraction loss (~6 dB per obstruction for UHF/VHF)
  - HF skywave comms: exempt from terrain LOS (ionospheric propagation)
  - Satellite comms: exempt from terrain LOS
  - Courier/messenger: already has terrain speed from CourierEngine (no change)
- **`stochastic_warfare/c2/communications.py`** (modified) -- Accept optional `los_engine` parameter. Use `getattr(ctx, "los_engine", None)` pattern.

**Tests** (~8):
- Radio comms through clear LOS → no attenuation
- Radio comms through hill → 6 dB loss
- Radio comms through mountain ridge → 12 dB loss (2 obstructions)
- HF skywave → no terrain attenuation regardless
- SATCOM → no terrain attenuation
- Missing los_engine → no terrain check (backward compat)

### 52d: Space SIGINT + EW SIGINT Fusion

Fuse space-based SIGINT detections with ground-based EW SIGINT into unified target tracks.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- After space engine update and EW engine update, if both SIGINT sources have detections of the same target, fuse into a single track with improved accuracy (weighted average of positions, combined confidence).
- **`stochastic_warfare/detection/intel_fusion.py`** (modified) -- Add `fuse_sigint_tracks()` method accepting space SIGINT and EW SIGINT detection lists.

**Tests** (~6):
- Two SIGINT detections of same target fuse into one track
- Fused track has better position accuracy than either individual
- No space engine → no fusion (backward compat)
- No EW engine → no fusion (backward compat)

### Exit Criteria
- Night detection is continuous function of solar elevation (5 levels)
- Wind drift affects ballistic trajectories
- Precipitation attenuates radar detection
- Radio comms check terrain LOS (with diffraction model)
- Space + EW SIGINT fuse when both available
- ~32 new tests

---

## Phase 53: C2 & AI Completeness

**Goal**: Wire FogOfWarManager (critical), PlanningProcessEngine, OrderPropagationEngine, StratagemEngine, ATOPlanningEngine. Compute C2 effectiveness from comms state. Wire school_id auto-assignment and SEAD/IADS parameters. Wire escalation sub-engines.

**Dependencies**: Phase 52 (comms LOS for C2 effectiveness computation).

### 53a: FogOfWarManager Wiring

The most impactful single wiring target in Block 6.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Each tick, call `ctx.fog_of_war.update_detections(side, detected_units)` with per-side detection results. Query `ctx.fog_of_war.get_known_units(side)` when building assessment.
- **`stochastic_warfare/simulation/engine.py`** (modified) -- After detection phase, call `fog_of_war.update()` to maintain per-side detection pictures.
- **`stochastic_warfare/c2/ai/assessment.py`** (modified) -- `build_assessment()` accepts optional `known_units` parameter. When provided, enemy force estimate uses detected units only, not ground truth. Add uncertainty bounds based on last-seen time.
- **Configuration**: `enable_fog_of_war: bool = False` in scenario config. Disabled by default for backward compat. Enable per scenario.

**Tests** (~15):
- With fog_of_war enabled: commander only sees detected enemies
- With fog_of_war disabled: commander sees all enemies (current behavior)
- Stale detections (not seen for N ticks) degrade in confidence
- Force estimate uncertainty increases with fewer detections
- Assessment differs between sides (each sees different picture)
- Backward compat: existing scenarios unchanged with fog_of_war=False

**Resolves deficit**: D12 (per-commander assessment).

### 53b: C2 Effectiveness Computation

Replace hardcoded 1.0 C2 effectiveness with computed value.

- **`stochastic_warfare/c2/communications.py`** (modified) -- Add `compute_c2_effectiveness(unit_id, hq_id)` method:
  ```python
  eff = base_eff * (1 - hop_penalty * num_hops) * signal_quality * range_factor
  ```
  Where `num_hops` from multi-hop C2 (Phase 12), `signal_quality` from comms reliability, `range_factor` = 1.0 within range, degraded beyond.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Replace `c2_effectiveness = 1.0` with `c2_effectiveness = comms_engine.compute_c2_effectiveness(unit_id, hq_id)`. C2 effectiveness modifies OODA cycle speed and fire coordination.

**Tests** (~8):
- Unit in comms range of HQ → C2 effectiveness ~1.0
- Unit at max range → C2 effectiveness ~0.7
- Unit out of range → C2 effectiveness ~0.3 (degraded autonomous ops)
- Multi-hop relay → penalty per hop
- No comms engine → 1.0 (backward compat)

### 53c: StratagemEngine and School Wiring

Wire the complete 417-line StratagemEngine and school_id auto-assignment.

- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate `StratagemEngine` in `_create_engines()`, attach to context.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- In `_process_ooda_completions()` DECIDE phase:
  - Call `stratagem_engine.evaluate_opportunities(commander, assessment)` to identify applicable stratagems
  - Weight by `school.get_stratagem_affinity()` for commander's doctrinal school
  - Activate highest-scoring stratagem via `stratagem_engine.activate_stratagem()`
- **`stochastic_warfare/c2/ai/commander.py`** (modified) -- In commander initialization, if `school_id` is set, look up school from `SchoolRegistry` and assign. Replace dead `school_id` field with live wiring.

**Tests** (~10):
- StratagemEngine instantiated from scenario loader
- DECIDE phase evaluates stratagem opportunities
- Sun Tzu school prefers DECEPTION stratagem (affinity weight)
- Clausewitz school prefers CONCENTRATION stratagem
- school_id in YAML auto-assigns school to commander
- No school_config → no stratagems evaluated (backward compat)

**Resolves deficits**: Phase 19 school_id, Phase 19 get_stratagem_affinity, Phase 25 stratagem affinity wiring.

### 53d: ATOPlanningEngine, OrderPropagation, PlanningProcess

Wire the three remaining dead C2 engines.

- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate `ATOPlanningEngine`, `OrderPropagationEngine` in `_create_engines()`.
- **`stochastic_warfare/simulation/campaign.py`** (modified) -- Call `ato_engine.generate_ato()` each campaign tick to assign air units to CAS/interdiction/SEAD sorties based on campaign objectives.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Call `order_propagation_engine.propagate_orders()` after DECIDE phase to push orders through chain of command with delay based on C2 effectiveness.
- **`stochastic_warfare/simulation/engine.py`** (modified) -- Call `planning_engine.update()` during campaign tick for MDMP/COA generation.

**Tests** (~10):
- ATO generates air sorties from campaign objectives
- Order propagation introduces delay based on hop count
- Planning engine produces COA candidates
- All three engines have get_state/set_state round-trip
- No campaign context → engines not called (backward compat)

### 53e: SEAD/IADS Parameters and Escalation Sub-Engines

Wire the 4 SEAD/IADS parameters and 3 escalation sub-engines.

- **`stochastic_warfare/combat/iads.py`** (modified) -- Read `sead_effectiveness` from escalation config, apply as suppression modifier on IADS nodes after SEAD strike. `iads_degradation_rate` as health decay per destroyed node. `sead_arm_effectiveness` as Pk modifier for ARM missiles.
- **`stochastic_warfare/escalation/ladder.py`** (modified) -- Read `drone_provocation_prob` from config, use in escalation trigger evaluation for unmanned platform encounters.
- **`stochastic_warfare/simulation/engine.py`** (modified) -- Add update() calls for:
  - `PoliticalPressureEngine.update()` -- evaluate international/domestic pressure effects
  - `UnconventionalWarfareEngine.update()` -- process IED encounters, guerrilla actions
  - `UXOEngine.update()` -- process unexploded ordnance fields

**Tests** (~8):
- SEAD strike reduces IADS node effectiveness by sead_effectiveness factor
- ARM missile Pk modified by sead_arm_effectiveness
- Destroyed IADS node degrades sector health by iads_degradation_rate
- drone_provocation_prob triggers escalation evaluation
- Political pressure accumulates over campaign ticks
- UXO fields processed from submunition failures

**Resolves deficit**: E8 (4 SEAD/IADS params).

### Exit Criteria
- FogOfWarManager queried per tick; per-side detection pictures maintained
- C2 effectiveness computed from comms state (not hardcoded 1.0)
- StratagemEngine evaluates opportunities during DECIDE phase
- school_id auto-assigns doctrinal school to commanders
- ATO generates air sorties from campaign objectives
- Order propagation introduces chain-of-command delay
- All 4 SEAD/IADS parameters consumed from config
- 3 escalation sub-engines called in engine step loop
- ~51 new tests

---

## Phase 54: Era-Specific & Domain Sub-Engine Wiring

**Goal**: Wire the 12 dead era-specific engines into battle/campaign routing. Verify space sub-engine delegation. Create scenarios for dormant config fields. Wire or remove dead YAML data fields. Clean up dead context fields.

**Dependencies**: Phase 53 (C2 engines for courier/order propagation, ATO for strategic bombing).

### 54a: WW2 Era Engines

Wire ConvoyEngine and StrategicBombingEngine into campaign loop.

- **`stochastic_warfare/simulation/campaign.py`** (modified) -- If WW2 era active:
  - Call `convoy_engine.update()` each campaign tick for convoy escort resolution
  - Call `strategic_bombing_engine.update()` for strategic bombing campaign target sets
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Convoy engagements route through ConvoyEngine for wolf-pack / escort interaction.

**Tests** (~8):
- Convoy engine resolves escort effectiveness per campaign tick
- Strategic bombing engine processes target sets with CEP
- Non-WW2 scenario → engines not called

### 54b: WW1 Era Engines

Wire BarrageEngine, GasWarfareEngine, TrenchSystemEngine into battle routing.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- If WW1 era active:
  - Barrage engagement type routes to `barrage_engine` (zone-based fire density) instead of IndirectFireEngine
  - Chemical weapon engagement routes to `gas_warfare_engine` (wraps CBRN pipeline)
  - Trench cover/concealment queries `trench_engine.query_trench_at(position)` for units inside trench lines
- **`stochastic_warfare/simulation/engine.py`** (modified) -- Call `trench_engine.update()` if present.

**Tests** (~10):
- Barrage engagement uses fire density model (rounds/hectare)
- Chemical weapon routes through gas warfare → CBRN pipeline
- Unit inside trench line gets trench cover bonus
- Unit outside trench line gets no bonus
- Non-WW1 scenario → engines not called

### 54c: Napoleonic Era Engines

Wire CavalryEngine, CourierEngine, ForagingEngine into battle/campaign routing.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- If Napoleonic era active:
  - Cavalry melee engagements route through `cavalry_engine` charge state machine
  - Verify CourierEngine wired into order propagation for Napoleonic C2
- **`stochastic_warfare/simulation/campaign.py`** (modified) -- Call `foraging_engine.update()` for supply when Napoleonic era active and supply lines cut.

**Tests** (~8):
- Cavalry charge state machine: approach → charge → melee → pursuit
- Courier C2 dispatch with terrain-dependent speed
- Foraging engine activates when supply lines cut
- Non-Napoleonic scenario → engines not called

### 54d: Ancient/Medieval Era Engines

Wire SiegeEngine, AncientFormationEngine, NavalOarEngine, VisualSignalEngine.

- **`stochastic_warfare/simulation/campaign.py`** (modified) -- If Ancient era active:
  - Call `siege_engine.update()` for daily siege state machine (assault/breach/starve)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- If Ancient era active:
  - Formation effects from `ancient_formation_engine` modify combat (phalanx, testudo, shield wall)
  - Naval movement through `naval_oar_engine` for oar-powered speed/endurance
- **`stochastic_warfare/c2/communications.py`** (modified) -- Route Ancient-era C2 through `visual_signal_engine` for LOS-dependent signal propagation.

**Tests** (~10):
- Siege state machine progresses through daily phases
- Phalanx formation grants frontal protection bonus
- Oar-powered ships have speed/endurance from naval_oar_engine
- Visual signals require LOS between units
- Non-Ancient scenario → engines not called

### 54e: Space Sub-Engine Verification and Scenario Coverage

Verify SpaceEngine delegates to sub-engines. Create scenarios for dormant configs.

- **`stochastic_warfare/space/constellations.py`** (modified) -- Verify `SpaceEngine.update()` delegates to GPS, ISR, Early Warning, SATCOM, ASAT sub-engines. Add explicit delegation calls if missing.
- **`stochastic_warfare/ew/sigint.py`** (modified) -- Verify `SIGINTEngine` is called from engine.py EW step. Add explicit call if missing.
- **`stochastic_warfare/ew/eccm.py`** (modified) -- Verify `ECCMEngine` is called when ECCM counters are active. Add explicit call if missing.
- **New scenarios** -- Create at least 2 scenarios with `space_config` (e.g., GPS denial scenario, satellite ISR scenario). Create at least 2 with `commander_config`. Add `cbrn_config` to 2 more scenarios. Add `school_config` to 2 more scenarios.
- **Add public API methods**: `CBRNEngine.get_mopp_level(unit_id)` replacing private `_mopp_levels` access. `SpaceEngine.get_gps_cep()` replacing nested `space_engine.gps_engine` access.

**Tests** (~10):
- SpaceEngine.update() calls GPS, ISR, Early Warning sub-engines
- SIGINTEngine called from engine.py when ew_config present
- ECCMEngine called when ECCM counters active
- GPS denial scenario reduces accuracy
- Public MOPP level API matches private dict values

### 54f: Dead YAML Fields and Context Cleanup

Wire useful dead YAML fields. Remove unused ones and dead context fields.

- **Weapon fields to wire**:
  - `traverse_deg`, `elevation_min_deg`, `elevation_max_deg` → weapon engagement arc constraint in target selection (can't engage target outside traverse/elevation arc)
  - `beam_wavelength_nm` → already wired in 51c (DEW Beer-Lambert)
- **Ammo fields to wire**:
  - `terminal_maneuver` → hit probability modifier for terminal phase maneuvering munitions
  - `seeker_fov_deg` → engagement cone constraint (seeker can't acquire target outside FOV)
- **Fields to remove or document as data-only**:
  - `propulsion`, `unit_cost_factor`, `weight_kg`, `data_link_range` → mark as data-only (used for scenario design reference, not simulation behavior) with docstring annotation
- **Dead context fields**: Remove `SeasonsEngine`, `ConditionsEngine`, `ObscurantsEngine` declarations from SimulationContext if truly unused. If seasons should affect weather, add a TODO for future work.

**Tests** (~8):
- Weapon outside traverse arc cannot engage target at that bearing
- Weapon below elevation_min cannot engage airborne target
- Terminal maneuver munition has higher hit probability in terminal phase
- Seeker FOV constrains engagement cone
- Removed context fields don't break any tests

### Exit Criteria
- All 12 era-specific engines wired into battle/campaign loop with era gating
- Space sub-engines verified to receive delegation from parent
- SIGINT and ECCM engines called from engine.py
- 6+ new scenarios exercise space_config, commander_config, expanded cbrn_config, school_config
- Dead YAML fields either wired (traverse, elevation, terminal_maneuver, seeker_fov) or documented as data-only
- Dead context fields cleaned up
- Fragile private API access replaced with public methods
- ~54 new tests

---

## Phase 55: Resolution & Scenario Migration

**Goal**: Fix resolution switching time_expired issue, migrate 8 legacy scenarios to campaign format, expand ROE coverage, fix proxy units and data gaps, fix Falklands mechanism.

**Dependencies**: Phases 50--54 (all combat/environmental/C2 changes must be wired before recalibrating).

### 55a: Resolution Switching Fix

Fix the structural issue where long-range battles resolve via time_expired.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Modify resolution switching logic:
  - Keep tactical resolution while any pair of opposing units is within `2 * max_engagement_range` AND at least one engagement has occurred in the last N ticks
  - Allow `force_destroyed` and `morale_collapsed` victory evaluation during strategic ticks (not just tactical)
  - Add `resolution_switching_engagement_range_mult` config (default 2.0) for the range multiplier
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Publish `EngagementOccurredEvent` that the resolution switcher can track.

**Tests** (~8):
- Units starting >50km apart: tactical resolution maintained while closing
- Resolution switches to strategic only after disengagement
- force_destroyed evaluates during strategic ticks
- Existing short-range scenarios unaffected

**Resolves deficits**: E9, D15.

### 55b: Legacy Scenario Migration

Migrate 8 pre-Phase-32 scenarios to campaign format.

- **8 scenario YAML files** (modified) -- Restructure from flat format to campaign format:
  - Add `campaign:` wrapper with `sides`, `objectives`, `victory_conditions`
  - Map existing unit lists to `sides[].forces[].units[]`
  - Add appropriate victory conditions based on scenario description
- **Verify all scenarios loadable** through `POST /api/runs` endpoint.

**Tests** (~8):
- All 8 migrated scenarios load through ScenarioLoader
- All 8 migrated scenarios load through API
- Migrated scenario output matches pre-migration output (same RNG → same result)

### 55c: ROE Expansion, Data Gaps, Proxy Units

Expand ROE coverage, fix data gaps, replace proxy units.

- **ROE expansion** -- Add `roe_level` to 5+ additional scenarios:
  - Korean Peninsula: WEAPONS_TIGHT (ROE escalation scenario)
  - Hybrid Gray Zone: WEAPONS_HOLD (initial, escalates)
  - Bekaa Valley: WEAPONS_FREE (already combat)
  - Falklands campaigns: WEAPONS_TIGHT (maritime ROE)
  - COIN campaign: WEAPONS_TIGHT
- **Data gaps**:
  - A-4 Skyhawk: add bomb weapon (Mk 82 500lb) and weapon_assignment
  - Eastern Front WW2: add weapon_assignments for all units
  - Roman equites: create proper unit definition (not Saracen cavalry proxy)
  - Iraqi Republican Guard: create proper unit definition (not insurgent_squad proxy)
- **Falklands campaign**: Recalibrate so combat engagements drive outcome, not instant morale collapse. Adjust initial morale, engagement ranges, force_destroyed threshold.
- **Rout cascade config**: Add per-scenario rout configuration to calibration schema for scenarios that need non-default cascade behavior.

**Tests** (~10):
- A-4 Skyhawk can deliver bombs in Falklands scenario
- Roman equites has correct ground_type (CAVALRY)
- Iraqi Republican Guard has appropriate training_level and equipment
- Falklands runs >2 ticks with actual engagements
- ROE WEAPONS_TIGHT blocks engagement below confidence threshold

### Exit Criteria
- Resolution switching allows decisive outcomes for long-range battles
- All 8 legacy scenarios loadable through API
- ROE set in 7+ scenarios
- All proxy units replaced with proper definitions
- Falklands campaign resolves via combat, not instant morale collapse
- ~26 new tests

---

## Phase 56: Performance & Logistics

**Goal**: Rally spatial indexing, maintenance → readiness wiring, per-era medical/engineering data, Weibull per-subsystem, VLS reload enforcement.

**Dependencies**: Phase 51 (naval engines for VLS enforcement).

### 56a: Rally Spatial Index

Replace O(n^2) rally cascade with STRtree spatial query.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- In rally mechanic:
  - Build STRtree from friendly unit positions at start of rally phase
  - Query within `rally_radius` instead of iterating all units
  - Same results, O(n log n) instead of O(n^2)

**Tests** (~6):
- Rally with STRtree produces same results as brute force
- Performance: 100 units rally in <1ms (vs ~10ms brute force)
- Edge case: no friendly units within radius → no rally

**Resolves deficit**: D5.

### 56b: Maintenance → Readiness Wiring

Wire maintenance failure events to unit readiness state.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Subscribe to `MaintenanceFailureEvent`:
  - On failure: set unit to MAINTENANCE state (can't engage, 0.3x movement)
  - After `repair_time_s` (from Weibull failure model): restore to OPERATIONAL
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Check unit readiness before engagement: MAINTENANCE state units cannot initiate engagements.

**Tests** (~6):
- Maintenance failure → unit transitions to MAINTENANCE state
- MAINTENANCE unit cannot engage
- After repair time → unit returns to OPERATIONAL
- No maintenance engine → all units OPERATIONAL (backward compat)

**Resolves deficit**: D10.

### 56c: Medical/Engineering Per-Era Data and Weibull Per-Subsystem

Replace hardcoded recovery times with era-appropriate values. Replace global Weibull shape with per-subsystem shapes.

- **`data/eras/*/config.yaml`** (modified) -- Add era-specific medical/engineering times:
  - Modern: CASEVAC 900s (15min), repair 1800s (30min)
  - WW2: stretcher 2700s (45min), repair 3600s (1hr)
  - WW1: trench evacuation 7200s (2hr), repair 7200s
  - Napoleonic: field surgery 14400s (4hr), repair N/A
  - Ancient: camp treatment 86400s (1 day), repair N/A
- **`stochastic_warfare/logistics/maintenance.py`** (modified) -- Accept per-subsystem Weibull shape parameters from unit type YAML:
  - Engine: k=1.2 (infant mortality)
  - Transmission: k=2.0 (wear-out)
  - Electronics: k=1.0 (random)
  - Default: k=1.5 (current value)
- **Unit type YAML** (modified) -- Add `subsystem_reliability` dict to unit definitions that need per-subsystem Weibull.

**Tests** (~8):
- Modern CASEVAC time = 900s
- WW1 trench evacuation time = 7200s
- Engine with k=1.2 has different failure distribution than k=2.0
- Default k=1.5 matches current behavior

**Resolves deficits**: D11, D13.

### 56d: VLS Reload Enforcement

Naval units with VLS launchers can't reload at sea.

- **`stochastic_warfare/entities/unit_classes/naval.py`** (modified) -- Add `vls_cells_remaining: int` field, initialized from weapon definition `magazine_size`.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Before VLS missile engagement: check `vls_cells_remaining > 0`. Decrement on fire. Block engagement when exhausted.
- **Port visit mechanic**: VLS reloads when unit is ANCHORED in friendly port zone for `vls_reload_time_s`.

**Tests** (~6):
- VLS engagement decrements cell count
- Exhausted VLS blocks missile engagement
- Port visit reloads VLS
- Non-VLS naval weapons unaffected

**Resolves deficit**: Phase 6 VLS.

### Exit Criteria
- Rally uses STRtree spatial index (O(n log n))
- Maintenance failures affect unit readiness
- Medical/engineering times era-appropriate
- Weibull shape per-subsystem
- VLS reload enforcement operational
- ~26 new tests

---

## Phase 57: Full Validation & Regression

**Goal**: Validate ALL scenarios against historical outcomes. Exercise ALL calibration parameters. Zero-deficit audit. Full documentation sync.

**Dependencies**: Phases 49--56 (all changes must be wired).

### 57a: Full Scenario Evaluation

Run every scenario and verify correct outcome.

- **All 42+ scenarios** -- Run through engine with 10-run MC per scenario:
  - Verify correct historical winner at >80% rate for each historical scenario
  - Verify modern scenarios reach decisive outcome (not time_expired) at >70% rate
  - Record force ratios, engagement counts, victory conditions triggered
- **Recalibrate as needed** -- Adjust CalibrationSchema parameters where outcomes are wrong. Document calibration rationale in YAML comments.
- **Previously-wrong scenarios** (6 from Block 5 analysis) -- Run 100-run MC on Agincourt, Salamis, Trafalgar, Midway, Stalingrad, Golan. Confirm >80% correct winner rate.

**Tests** (~15):
- Parametrized test: for each scenario, verify correct winner
- Force ratio within historical bounds (±50% of documented ratio)
- No scenario resolves via time_expired when decisive combat expected

### 57b: Calibration Parameter Coverage

Verify every calibration parameter is exercised.

- **`tests/unit/test_calibration_coverage.py`** (new) -- For each field in `CalibrationSchema`:
  - At least one scenario sets a non-default value, OR
  - At least one test scenario exercises the field
- **Dead parameter audit** -- If any CalibrationSchema field has zero consumers in Python code, flag as dead and remove.

**Tests** (~10):
- Every CalibrationSchema field consumed by at least one Python code path
- Every CalibrationSchema field set by at least one scenario or test

### 57c: Zero-Deficit Audit

Close every open item in `devlog/index.md`.

- **Review every unresolved item** -- Mark as:
  - RESOLVED (with phase citation)
  - WON'T FIX (with rationale)
- **No items remain in "unresolved" state** -- Everything has a disposition.
- **Update deficit count** in CLAUDE.md, MEMORY.md, README.md.

### 57d: Documentation Sync and Cross-Doc Audit

Synchronize all documentation.

- **CLAUDE.md** -- Update test counts, phase status, Block 6 summary
- **README.md** -- Update test badge, architecture summary
- **docs/index.md** -- Update badges, block status table
- **docs/devlog/index.md** -- Update all deficit dispositions
- **docs/specs/project-structure.md** -- Verify module list matches implementation
- **mkdocs.yml** -- Add Block 6 phase devlog entries
- **MEMORY.md** -- Update status, lessons learned
- **Run `/cross-doc-audit`** -- All 19 checks must pass

### Exit Criteria
- All 42+ scenarios produce correct historical winner at >80% MC rate
- All CalibrationSchema fields exercised
- Zero unresolved deficits in devlog/index.md
- Cross-doc audit passes all 19 checks
- ~25 new tests
- **Block 6 target: ~8,800+ total tests** (Python + frontend)

---

## Deficit Resolution Map

### Phase 48 Postmortem Deficits (E1--E10)

| ID | Deficit | Resolved In |
|----|---------|-------------|
| E1 | `advance_speed` dead data | Phase 49b |
| E2 | `dig_in_ticks` untested | Phase 49c |
| E3 | `wave_interval_s` untested | Phase 49c |
| E4 | `target_selection_mode` untested | Phase 49c |
| E5 | `roe_level` sparse coverage | Phase 49c + 55c |
| E6 | Morale config weights unused | Phase 49c |
| E7 | `victory_weights` untested | Phase 49c |
| E8 | 4 SEAD/IADS params unwired | Phase 53e |
| E9 | Resolution switching time_expired | Phase 55a |
| E10 | Calibration audit false pass | Phase 49b |

### Formally Deferred Items (D1--D16)

| ID | Deficit | Resolved In |
|----|---------|-------------|
| D1 | Posture → movement speed | Phase 50a |
| D2 | Naval posture undefined | Phase 51b |
| D3 | Air posture undefined | Phase 50b |
| D4 | Binary concealment | Phase 50c |
| D5 | O(n^2) rally cascade | Phase 56a |
| D6 | Phantom naval engines | Phase 51a |
| D7 | WW1 barrage fire-on-move | Phase 50e |
| D8 | Night/day binary | Phase 52a |
| D9 | Weather stops at visibility | Phase 52b |
| D10 | Maintenance registration | Phase 56b |
| D11 | Medical/engineering data sparse | Phase 56c |
| D12 | Per-commander assessment | Phase 53a |
| D13 | Weibull global | Phase 56c |
| D14 | Training data disconnected | Phase 50d |
| D15 | time_expired wins | Phase 55a |
| D16 | DEW always destroys | Phase 51c |

### Persistent Known Limitations (Earlier Phases)

| Deficit | Resolved In |
|---------|-------------|
| Messenger intercept risk | Phase 53 (low priority) |
| ~~Blockade effectiveness~~ | Phase 51d (wired, throughput reduction deferred to Phase 56) |
| VLS reload enforcement | Phase 56d |
| Stratagems not proactively planned | Phase 53c |
| ~~Space SIGINT + EW SIGINT fusion~~ | Phase 52d (**resolved**) |
| school_id dead data | Phase 53c |
| get_stratagem_affinity never called | Phase 53c |
| C2 effectiveness hardcoded 1.0 | Phase 53b |
| ATO wiring | Phase 53d |
| Stratagem affinity wiring | Phase 53c |
| school_id auto-assignment | Phase 53c |
| Proxy units in scenarios | Phase 55c |
| 8 legacy scenarios can't load API | Phase 55b |
| MineWarfareEngine dead | Phase 51d |
| StratagemEngine dead | Phase 53c |
| DisruptionEngine dead | Phase 51d |
| ATOPlanningEngine dead | Phase 53d |
| FogOfWarManager dead | Phase 53a |
| PlanningProcessEngine dead | Phase 53d |
| OrderPropagationEngine dead | Phase 53d |
| Space sub-engines dead | Phase 54e |
| Era-specific engines dead (12) | Phase 54a--d |
| Escalation sub-engines dead (3) | Phase 53e |
| Dead YAML fields (10) | Phase 54f |
| Dead context fields (3) | Phase 54f |
| Fragile private API access | Phase 54e |

---

## Phase Summary

| Phase | Focus | Tests | Cumulative | Status |
|-------|-------|-------|------------|--------|
| 49 | Calibration Schema Hardening | 51 | 8,053 | **Complete** |
| 50 | Combat Fidelity Polish | 40 | 8,093 | **Complete** |
| 51 | Naval Combat Completeness | 37 | 8,130 | **Complete** |
| 52 | Environmental Continuity | 32 | 8,162 | **Complete** |
| 53 | C2 & AI Completeness | ~51 | ~8,212 | Planned |
| 54 | Era & Domain Sub-Engine Wiring | ~54 | ~8,266 | Planned |
| 55 | Resolution & Scenario Migration | ~26 | ~8,292 | Planned |
| 56 | Performance & Logistics | ~26 | ~8,318 | Planned |
| 57 | Full Validation & Regression | ~25 | ~8,343 | Planned |

**Block 6 total**: ~335 new tests across 9 phases.
**Target cumulative**: ~8,600+ Python tests + 272 frontend = ~8,870+ total.

# Stochastic Warfare — Block 2 Development Phases (25–30)

## Philosophy

Block 2 turns individually excellent subsystems into a connected, data-rich whole. No new domains or architectural rewrites. Three priorities: (1) wire all existing engines into the scenario loading and tick loop pipeline, (2) fill missing cross-domain combat interaction paths, (3) populate YAML data packages to enable rich scenario authoring.

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block2.md` (design thinking), `devlog/index.md` (deficit inventory), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**Deficit traceability**: Every open item in `devlog/index.md` Post-MVP Refinement Index is either addressed in a phase below, or explicitly marked as "deferred" or "won't fix" with rationale.

---

## Phase 25: Engine Wiring & Integration Sprint — **COMPLETE** (152 tests, 6,477 total)

**Goal**: Wire all post-MVP standalone engines into ScenarioLoader and the simulation tick loop. Fix the broken OODA DECIDE path. Make a scenario YAML the single source of truth for instantiating a fully-connected simulation.

**Dependencies**: None (builds on all existing engines).

### 25a: ScenarioLoader Auto-Wiring (est. ~60 tests)

Extend `CampaignScenarioConfig` and `ScenarioLoader.load()` to parse and instantiate:

- **`simulation/scenario.py`** (modified) — New config blocks: `ew_config`, `space_config`, `cbrn_config`, `school_config`, `commander_config`. Era engines gated by existing `era` field. Escalation engines gated by existing `escalation_config`.
- **`simulation/scenario.py`** (modified) — `ScenarioLoader.load()` instantiation logic: for each config block present and non-null, instantiate the corresponding engine(s) and assign to SimulationContext fields.
- **Engine instantiation order**: RNGManager streams first, then engines in dependency order (EW before detection, CBRN before movement, commanders before AI decisions).
- **YAML schema additions**: Each config block maps directly to the engine's pydantic Config class. Example: `ew_config: {jam_to_signal_threshold_db: -3.0}` → `EWConfig(jam_to_signal_threshold_db=-3.0)`.

**Resolves deficits**: 1.1 (ScenarioLoader auto-wiring — accumulated across Phases 16–24), 1.6 (era engines not wired), 5.1 (EW engines not wired).

### 25b: Battle Loop OODA Fix (est. ~40 tests)

- **`simulation/battle.py`** (modified) — Build `AssessmentResult` from battle state: friendly/enemy unit lists, force ratios per sector, threat axes from enemy positions, supply state from stockpile manager, morale averages. Pass to `decide()` instead of `None`.
- **`simulation/battle.py`** (modified) — Wire `get_coa_score_weight_overrides()` from SchoolRegistry (if present on context) into COA scoring in `_process_ooda_completions()`.
- **`simulation/battle.py`** (modified) — Wire `get_stratagem_affinity()` into stratagem evaluation during DECIDE phase.
- **`c2/ai/assessment.py`** (modified, if needed) — Ensure `AssessmentResult` has all fields that `decide()` and school weight overrides expect.

**Resolves deficits**: 1.3 (assessment=None), 2.8 (COA weight overrides not called), 1.2 (CommanderEngine not wired — addressed as part of this wiring pass).

### 25c: Tick Loop Integration (est. ~35 tests)

- **`simulation/engine.py`** (modified) — Add conditional calls in tick loop for:
  - EW update (jamming state refresh, SIGINT collection) — after detection, before engagement
  - MOPP speed factor query (contamination state → movement engine parameter)
  - Air campaign → ATO planning cycle integration
  - Insurgency engine wired with real collateral events and aid data from ongoing simulation
- **`simulation/engine.py`** (modified) — Replace bare `except Exception: pass` with:
  - `logger.error()` with traceback
  - Configurable `strict_mode` (default False): if True, re-raise; if False, continue with warning
- **`simulation/battle.py`** (modified) — Pass `mopp_speed_factor` from CBRN contamination state to movement engine in `_execute_movement()`.

**Resolves deficits**: 1.4 (air campaign not wired to ATO), 1.5 (MOPP speed factor never passed), 1.7 (bare except), 4.13 (insurgency needs real data).

### 25d: CommanderEngine Wiring (est. ~25 tests)

- **`simulation/scenario.py`** (modified) — Add `commander_engine` field to SimulationContext. ScenarioLoader creates CommanderProfileLoader, loads profiles, creates CommanderEngine, assigns personalities to units per scenario YAML `commander_assignments` block.
- **`simulation/battle.py`** (modified) — Query `commander_engine.get_personality(unit_id)` for OODA speed, decision noise, risk threshold. Replace all `personality=None` call sites.
- **`c2/ai/commander.py`** (modified, if needed) — `CommanderPersonality.school_id` field → SchoolRegistry auto-assignment when both engines present.

**Resolves deficits**: 1.2 (CommanderEngine not wired).

### Tests: `tests/unit/test_phase_25a_scenario_wiring.py`, `tests/unit/test_phase_25b_ooda_fix.py`, `tests/unit/test_phase_25c_tick_loop.py`, `tests/unit/test_phase_25d_commander_wiring.py`

### Exit Criteria
- A scenario YAML with EW/Space/CBRN/Schools/Era/Escalation config blocks produces a SimulationContext with all corresponding engines instantiated
- `decide()` receives a real AssessmentResult with force ratios and threat data
- COA weight overrides and stratagem affinity hooks are invoked when SchoolRegistry present
- EW engines called each tick, MOPP speed factor passed to movement
- No bare `except Exception: pass` remains in engine.py
- CommanderEngine on SimulationContext; personality queried in battle loop
- All 6,325+ existing tests pass unchanged

---

## Phase 26: Core Polish & Configuration — **COMPLETE** (82 tests, 6,559 total)

**Goal**: Fix PRNG discipline violations, replace all hardcoded magic numbers with configurable pydantic fields, and address remaining core engine quality items.

**Dependencies**: Phase 25 (wiring must work before polishing).

### 26a: PRNG Discipline (25 tests)

Removed all fallback `np.random.default_rng()` from 23 engine constructors across combat (8), detection (7), C2 (3), movement (3), logistics (1), simulation (1). Made `rng` a required parameter (keyword-only via `*,` where needed). Updated 12 existing test files to pass explicit `rng=` arguments.

- `combat/archery.py`, `combat/barrage.py`, `combat/gas_warfare.py`, `combat/melee.py`, `combat/naval_gunnery.py`, `combat/siege.py`, `combat/strategic_bombing.py`, `combat/volley_fire.py`
- `detection/deception.py`, `detection/detection.py`, `detection/estimation.py`, `detection/fog_of_war.py`, `detection/intel_fusion.py`, `detection/sonar.py`, `detection/underwater_detection.py`
- `c2/coordination.py`, `c2/courier.py`, `c2/visual_signals.py`
- `movement/cavalry.py`, `movement/convoy.py`, `movement/naval_oar.py`
- `logistics/foraging.py`
- `simulation/aggregation.py`

**Resolves deficits**: 8.1 (hardcoded fallback RNG seeds).

### 26b: Configurable Constants (34 tests)

Replaced hardcoded magic numbers with pydantic Config fields in 9 source files:

| Module | New Config Field | Default |
|--------|-----------------|---------|
| `cbrn/dispersal.py` | `DispersalConfig.terrain_channel_offset_m`, `terrain_channel_height_m` | 50.0, 5.0 |
| `cbrn/engine.py` | `CBRNConfig.fallback_wind_speed_mps`, `fallback_wind_direction_rad`, `fallback_cloud_cover` | 2.0, 0.0, 0.5 |
| `combat/gas_warfare.py` | `GasWarfareConfig.max_wind_angle_deg` | 60.0 |
| `terrain/trenches.py` | `TrenchConfig.along_angle_threshold_deg`, `crossing_angle_threshold_deg` | 30.0, 60.0 |
| `logistics/foraging.py` | `ForagingConfig.ambush_casualty_rate` | 0.1 |
| `ew/jamming.py` | `JammingConfig.jamming_event_radius_m` | 50000.0 |
| `ew/spoofing.py` | `check_spoof_detection(unit_id="")` parameter | "" |
| `ew/decoys_ew.py` | `EWDecoyConfig.decoy_seeker_effectiveness` dict | {CHAFF→RADAR/ANTI_RAD, FLARE→IR/EO, TOWED→RADAR, DRFM→RADAR/ANTI_RAD} |
| `ew/sigint.py` | `SIGINTConfig.activity_sigmoid_center`, `activity_sigmoid_scale` | 10.0, 10.0 |

J/S sigmoid in `ew/jamming.py` deliberately NOT changed — standard dB power conversion (physics, not tunable).

**Resolves deficits**: 5.6 (GPS spoofing unit_id), 5.7 (EW magic numbers), 7.1 (terrain channeling), 7.2 (weather defaults), 8.2 (gas wind angle), 8.3 (trench angles), 8.4 (foraging ambush).

### 26c: Engine Lifecycle & Cleanup (23 tests)

- **`cbrn/dispersal.py`** — `DispersalConfig.max_puff_age_s` (default 3600.0), `cleanup_aged_puffs()` method.
- **`cbrn/engine.py`** — Wires `cleanup_aged_puffs()` at end of `update()`.
- **`detection/detection.py`** — `DetectionConfig.max_integration_scans` (default 4), caps scan count before computing gain.
- **`entities/unit_classes/ground.py`** — `armor_type: str = "RHA"` field with get_state/set_state (backward-compat default).
- **`entities/loader.py`** — `UnitDefinition.armor_type` field, passed to GroundUnit in `create_unit()`.
- **6 armor YAML files** — m1a1_abrams (COMPOSITE), m1a2 (COMPOSITE), shot_kal (RHA), t55a (RHA), t62 (RHA), t72m (COMPOSITE).

**Resolves deficits**: 7.3 (puff cleanup), 10.4 (integration gain cap), 10.5 (armor type YAML).

### Tests: `tests/unit/test_phase_26a_prng.py` (25), `tests/unit/test_phase_26b_config.py` (34), `tests/unit/test_phase_26c_lifecycle.py` (23)

### Exit Criteria — All Met
- `grep -r "default_rng" stochastic_warfare/` returns zero matches ✓
- All previously hardcoded constants are pydantic Config fields with documented defaults ✓
- CBRN puff cleanup runs each tick, respects max_puff_age_s ✓
- GPS spoofing events carry actual unit_id ✓
- Armor type specified in all armored unit YAML files ✓
- All 6,559 tests pass ✓

---

## Phase 27: Combat System Completeness — **COMPLETE** (139 tests, 6,698 total)

**Goal**: Fill all missing cross-domain engagement paths, enhance the engagement engine with burst fire and submunition scatter, and complete naval combat mechanics.

**Dependencies**: Phase 25 (engine wiring), Phase 26 (PRNG discipline — new code must follow conventions).

### 27a: Cross-Domain Engagement Paths (31 tests)

- **`combat/engagement.py`** (modified) — New engagement types: `COASTAL_DEFENSE = 9`, `AIR_LAUNCHED_ASHM = 10`, `ATGM_VS_ROTARY = 11`. New `route_engagement()` dispatcher, `_resolve_atgm_vs_rotary()`. New config: `atgm_max_altitude_m`, `atgm_range_decay_factor`.
- **`combat/air_ground.py`** (modified) — `AirGroundMission.ASHM = 5`, `execute_ashm()` launch-only method, `AirASHMResult` dataclass.
- **`combat/air_combat.py`** (modified) — `compute_ew_countermeasure_reduction()`, EW engine integration in `resolve_air_engagement()` (optional `ew_decoy_engine`, `jamming_engine` params). New config: `enable_ew_countermeasures`.
- **`combat/air_defense.py`** (modified) — EW integration in `fire_interceptor()` (optional `ew_decoy_engine`, `jamming_engine` params). New config: `enable_ew_countermeasures`.

### 27b: Engagement Engine Enhancements (47 tests)

- **`combat/engagement.py`** (modified) — `execute_burst_engagement()`: N rounds as independent Bernoulli trials, single cooldown, damage per hit. `BurstEngagementResult` dataclass. New config: `enable_burst_fire`, `max_burst_size`. When disabled, caps burst to 1.
- **`combat/damage.py`** (modified) — `resolve_submunition_damage()`: scatter N submunitions (rng.normal per sub), check lethal radius per target, accumulate damage, create UXO field for duds. New config: `enable_submunition_scatter`, `submunition_scatter_sigma_fraction`.
- **`combat/air_combat.py`** (modified) — `apply_countermeasures_multi()`: multiplicative stacking `combined = 1 - product(1 - individual)`. Supports chaff, flare, dircm. New config: `dircm_effectiveness`.
- **`combat/indirect_fire.py`** (modified) — `TOTFirePlan` dataclass, `compute_tot_plan()` (ToF per battery, fire times for simultaneous impact), `execute_tot_mission()` (fires batteries whose fire_time <= current_time). New config: `tot_max_batteries`, `tot_time_of_flight_variation_s`.
- **`combat/air_ground.py`** (modified) — `compute_cas_designation()`: JTAC designation delay enforcement, laser bonus, talk-on latency ramp, comm quality. `CASDesignationResult` dataclass. New config: `jtac_designation_delay_s`, `laser_acquisition_window_s`, `talk_on_latency_s`, `designation_accuracy_bonus`.

### 27c: Naval Combat Completion (31 tests)

- **`combat/naval_surface.py`** (modified) — `naval_gun_engagement()`: radar-directed Pk = base × FC_bonus × FC_quality × range_factor × sea_factor × size_factor, Bernoulli per round. `NavalGunResult` dataclass. New config: `naval_gun_base_pk_per_round`, `naval_gun_fire_control_bonus`, `naval_gun_max_range_m`, `naval_gun_rate_of_fire_rpm`, `naval_gun_damage_per_hit`.
- **`combat/naval_subsurface.py`** (modified) — `asroc_engagement()` (0.9 flight reliability → torpedo phase), `depth_charge_attack()` (pattern scatter, Bernoulli within lethal radius), `resolve_torpedo_countermeasures()` (NIXIE → acoustic CM → evasion layers). `ASROCResult`, `DepthChargeResult`, `TorpedoCountermeasureResult` dataclasses. New config: `asroc_max_range_m`, `asroc_torpedo_pk`, `depth_charge_*`, `nixie_seduction_probability`, `acoustic_cm_confusion_probability`, `enable_torpedo_countermeasures`.
- **`combat/carrier_ops.py`** (modified) — `create_cap_station()`, `update_cap_stations()`, `schedule_recovery_window()`. `CAPStation`, `RecoveryWindow` dataclasses. New config: `cap_aircraft_per_station`, `cap_relief_margin_s`, `recovery_window_duration_s`, `recovery_window_interval_s`.

### 27d: Selective Fidelity Items (30 tests)

- **`combat/barrage.py`** (modified) — Observer correction: `has_observer` + `observer_quality` on BarrageZone, drift reduced by `observer_correction_factor * observer_quality` each update. New config: `observer_correction_factor`, `observer_quality_default`.
- **`combat/melee.py`** (modified) — `compute_cavalry_terrain_modifier()`: slope penalty, soft ground, obstacle abort. `compute_frontage_constraint()`: limits engaged strengths, reserves at `second_rank_effectiveness`. Both integrated into `resolve_melee_round()`. New config: `cavalry_slope_penalty_per_deg`, `cavalry_soft_ground_penalty`, `cavalry_obstacle_abort_threshold`, `cavalry_uphill_casualty_bonus`, `max_frontage_m`, `combatant_spacing_m`, `second_rank_effectiveness`.
- **`combat/gas_warfare.py`** (modified) — `compute_exposure_during_don()`: linear ramp from full exposure (t=0) to zero (t=don_time). `get_effective_mopp_level()`: returns (mopp_level, protection_factor) tuple with ramp.

**Resolves deficits**: 2.10 (no frontage/depth), 2.11 (cavalry terrain), 2.12 (barrage drift), 2.13 (gas mask don time).

### Tests: `tests/unit/test_phase_27d_fidelity.py` (30), `tests/unit/test_phase_27a_cross_domain.py` (31), `tests/unit/test_phase_27c_naval.py` (31), `tests/unit/test_phase_27b_engagement.py` (47)

### Exit Criteria — All Met
- Ground units can engage naval targets via coastal defense missiles ✓
- Air-launched ASHMs fly realistic profiles and face ship point defense ✓
- ATGMs can engage hovering helicopters ✓
- EW jamming effectiveness affects air combat missile Pk ✓
- Burst fire resolves N rounds per engagement ✓
- DPICM submunitions scatter and create UXO fields ✓
- Surface ships can launch ASW weapons against submarines ✓
- Torpedo countermeasures (NIXIE) modeled ✓
- Barrage drift corrects with observer feedback ✓
- Cavalry charge speed affected by terrain ✓
- All 6,698 tests pass ✓

---

## Phase 28: Modern Era Data Package — **COMPLETE** (137 tests, 6,835 total)

**Goal**: Fill all modern era YAML data gaps — adversary forces, missing signatures, ammunition types, sensors, organizations, doctrine templates, and commander profiles.

**Dependencies**: Phase 27 (new engagement paths should exist before writing data for them).

### 28a: Adversary & Allied Units (est. ~25 tests)

New unit YAML + matching signature YAML for each:

**Adversary air** (minimum viable OPFOR):
- MiG-29A Fulcrum (4th gen fighter, Russian)
- Su-27S Flanker (heavy fighter, Russian)
- J-10A Vigorous Dragon (Chinese 4th gen)

**Adversary ground**:
- BTR-80 (Russian APC, complement BMP-1)
- BMP-2 (Russian IFV, upgrade from BMP-1)
- T-90A (modern Russian MBT)

**Adversary naval**:
- Sovremenny-class DDG (Russian, SSN-22 Sunburn ASHMs)
- Kilo-class SSK (Russian diesel-electric sub)

**Adversary air defense**:
- SA-11 Buk (medium-range SAM, brigade level)
- S-300PMU (long-range SAM, strategic)

**Allied/NATO**:
- Leopard 2A6 (German MBT)
- Challenger 2 (British MBT)

**Force multipliers**:
- B-52H Stratofortress (strategic bomber)
- EA-18G Growler (EW aircraft)
- Mi-24V Hind (Russian attack helicopter)
- C-17 Globemaster (strategic airlift)

**Missing unit-level definitions**:
- M109A6 Paladin SP artillery battery (unit exists as weapon platform, needs org-level battery definition)
- ATGM team (Javelin, Kornet)
- Engineer squad/platoon

### 28b: Weapons, Ammunition & Sensors (est. ~20 tests)

**Weapons**:
- AGM-88 HARM (anti-radiation missile — SEAD)
- R-77 (Russian BVRAAM)
- R-73 (Russian WVRAAM)
- 9K38 Igla (Russian MANPAD)
- 2A42 30mm autocannon (BMP-2, Ka-52)
- Javelin ATGM
- 9M133 Kornet ATGM
- ASROC (ASW rocket-torpedo)
- Mk54 lightweight torpedo

**Ammunition**:
- 30mm M789 HEDP (Apache/Bradley)
- 30mm 3UOR6 HEI (Russian 30mm)
- Mk-82 500lb GP bomb
- Mk-84 2000lb GP bomb
- GBU-12 Paveway II (LGB)
- GBU-38 JDAM (GPS-guided)
- M720 60/81mm mortar HE
- M853A1 mortar illumination
- Mk54 lightweight torpedo warhead
- ASROC payload

**Sensors**:
- AN/APG-68 fire control radar (F-16)
- AN/APY-1 maritime patrol radar
- AN/AAQ-33 Sniper targeting pod
- AN/SQR-19 towed sonar array
- UV missile approach warning system

### 28c: Organizations & Doctrine (est. ~15 tests)

**Organization TO&E** (new files in `data/organizations/`):
- US combined arms battalion task force
- US Stryker infantry company
- Russian battalion tactical group (BTG)
- Chinese combined arms brigade
- UK armoured battlegroup
- Generic mechanized infantry company (template)
- Generic tank company (template)

**Doctrine templates** (new files in `data/doctrine/`):
- `pla_active_defense.yaml` — Chinese PLA doctrine
- `idf_preemptive.yaml` — Israeli doctrine (preemptive, short war)
- `airborne_vertical_envelopment.yaml` — Airborne/air assault
- `amphibious_ship_to_shore.yaml` — Amphibious assault doctrine
- `naval_sea_control.yaml` — Naval warfare operational template

**Commander profiles** (new files in `data/commander_profiles/`):
- `joint_campaign.yaml` — Joint/combined arms commander
- `naval_aviation.yaml` — Carrier air wing commander
- `logistics_sustainment.yaml` — Sustainment-focused commander

**Escalation configs** (new files in `data/escalation/`):
- `peer_competitor.yaml` — US-China/US-Russia thresholds
- `conventional_only.yaml` — No WMD escalation
- `nato_article5.yaml` — NATO collective defense thresholds

### 28d: Missing Signatures & Armor Data (est. ~10 tests)

- Fill signature YAML for all existing units lacking them: bmp1, m3a2_bradley, sea_harrier, type22_frigate, t55a, t62
- Add `armor_type` field to all armored unit YAML files (Phase 26c prerequisite complete)
- Create signature YAML for all units added in 28a

### Tests: `tests/unit/test_phase_28_data_loading.py` (YAML validation: all files load, pydantic validates, cross-references resolve)

### Exit Criteria
- At least 3 adversary fighter aircraft in YAML
- At least 2 adversary ground vehicles beyond T-72M
- At least 2 adversary naval platforms
- HARM anti-radiation missile and Russian BVRAAM exist
- Unguided bombs (Mk-82, Mk-84) and guided bombs (GBU-12, GBU-38) exist
- At least 5 organization TO&E files
- All unit YAML files have matching signature files
- All armored units have armor_type specified
- All YAML validates via pydantic

---

## Phase 28.5: Directed Energy Weapons — **COMPLETE** (112 tests, 6,947 total)

**Goal**: Add directed energy weapon modeling (high-energy lasers and high-power microwave) to the modern era simulator. Fills counter-UAS/RAM and counter-swarm gap.

**Dependencies**: Phase 28 (Modern Era Data Package).

### 28.5a: Core DEW Engine + Enum Extensions (57 tests)

- **`combat/directed_energy.py`** (new) — DEWEngine with Beer-Lambert atmospheric transmittance, laser Pk (dwell-time exponential), HPM Pk (inverse-square), engagement execution
- **`combat/ammunition.py`** (modified) — `WeaponCategory.DIRECTED_ENERGY = 12`, `AmmoType.DIRECTED_ENERGY = 14`, 4 new WeaponDefinition fields
- **`combat/damage.py`** (modified) — `DamageType.THERMAL_ENERGY = 5`, `DamageType.ELECTRONIC = 6`
- **`combat/events.py`** (modified) — `DEWEngagementEvent` frozen dataclass

### 28.5b: Engagement Routing & Scenario Wiring (20 tests)

- **`combat/engagement.py`** (modified) — `EngagementType.DEW_LASER = 12`, `DEW_HPM = 13`, routing in `route_engagement()`
- **`entities/unit_classes/air_defense.py`** (modified) — `ADUnitType.DEW = 8`
- **`simulation/scenario.py`** (modified) — `dew_engine` on SimulationContext, `dew_config` on CampaignScenarioConfig, factory method

### 28.5c: YAML Data Package (38 tests)

- 5 weapon YAML (`data/weapons/dew/`): DE-SHORAD 50kW, HELIOS 60kW, Iron Beam 100kW, GLWS Dazzler, PHASER HPM
- 5 ammo YAML (`data/ammunition/dew/`): energy charges + HPM pulse
- 3 unit YAML: DE-SHORAD, Iron Beam, DDG w/ HELIOS
- 5 signature YAML, 2 sensor YAML

---

## Phase 29: Historical Era Data Expansion — **COMPLETE** (164 tests, 7,111 total)

**Goal**: Add naval units to all pre-modern eras, fill remaining unit type gaps, add missing comms/organization data, and enable naval scenarios for each era.

**Dependencies**: Phase 27 (naval combat completion provides engagement paths).

### 29a: WW2 Naval & Missing Types (est. ~25 tests)

**Naval units** (critical gap — Midway uses DD as carrier proxy):
- Essex-class CV (US fleet carrier)
- Shokaku-class CV (IJN fleet carrier)
- Type IXC U-boat (long-range, Atlantic)
- Flower-class corvette (convoy escort)
- LST (landing craft, tank)

**Other missing types**:
- M1 105mm howitzer battery (US artillery)
- sFH 18 150mm battery (German artillery)
- Pak 40 75mm AT gun (German)
- 6-pdr AT gun (British)
- A6M Zero (IJN fighter)
- Bf 109G (weapon YAML for MG151 + MG131)
- P-51D (weapon YAML for M2 .50 cal)

**Comms** (WW2 is the only era without comms):
- `field_telephone_ww2.yaml`
- `radio_scr300_ww2.yaml`

**WW2 aircraft weapon data** (fighters have units but no gun YAML):
- MG151/20 20mm cannon
- M2 Browning .50 cal (aircraft mount)
- Type 99 20mm cannon (IJN)

### 29b: WW1 Expansion (est. ~20 tests)

**Naval units** (Jutland-era):
- Iron Duke-class dreadnought (British)
- König-class dreadnought (German)
- Invincible-class battlecruiser (British)
- G-class torpedo boat destroyer (German)
- U-boat (submarine)

**Other missing types**:
- 18-pdr battery unit (British artillery — weapon exists, no unit)
- 7.7cm FK 96 battery unit (German artillery)
- SPAD XIII (French/Allied fighter)
- Fokker D.VII (German fighter)
- US AEF infantry squad

### 29c: Napoleonic Naval & Expansion (est. ~20 tests)

**Naval units** (Trafalgar-era):
- 74-gun ship of the line (standard battleship)
- First-rate ship of the line (100+ guns, flagships)
- Frigate (32-gun, scout/raider)
- Corvette (escort, dispatch)
- Fire ship

**Other missing types**:
- Dragoon squadron (medium cavalry)
- Austrian line infantry
- Russian line infantry
- Congreve rocket battery
- Pontoon engineer section
- Supply train unit

### 29d: Ancient/Medieval Naval & Expansion (est. ~20 tests)

**Naval units**:
- Greek trireme (Salamis, Actium)
- Roman quinquereme
- Viking longship
- Byzantine dromon
- Medieval cog (transport)
- Mediterranean war galley (Lepanto)

**Other missing types**:
- Byzantine kataphraktoi (heavy cavalry)
- Saracen/Mamluk cavalry
- Mongol commander profile (Genghis Khan / Subutai)
- Dedicated siege engineer unit
- Byzantine infantry (skutatoi)

### Tests: `tests/unit/test_phase_29_era_data.py` (YAML validation per era: loads, validates, cross-references)

### Exit Criteria
- WW2 has at least 2 carrier units and carrier-capable aircraft
- WW1 has at least 3 capital ship types
- Napoleonic era has ship of the line and frigate
- Ancient/Medieval era has trireme and longship
- WW2 has comms subdirectory
- All new unit YAML has matching signature + weapon YAML
- All era YAML validates via pydantic

---

## Phase 30: Scenario & Campaign Library

**Goal**: Build comprehensive scenarios that exercise the full wired engine across all domains and eras. Expand existing scenarios. Add cross-domain joint scenarios.

**Dependencies**: Phases 28–29 (data must exist for scenarios to reference), Phase 25 (wiring must work for scenarios to run).

### 30a: Modern Joint Scenarios (est. ~30 tests)

**New scenarios**:
- `taiwan_strait/scenario.yaml` — Joint air-naval scenario. PLAN amphibious assault vs Taiwan + US carrier strike group. Exercises: naval surface combat, air superiority, ASHM, IADS, escalation dynamics, EW. Requires Phase 28 adversary data.
- `korean_peninsula/scenario.yaml` — Combined arms with massed artillery. Mountainous terrain, logistics-heavy, EW and CBRN threat. Exercises: indirect fire, counter-battery, CBRN defense, logistics under fire.
- `suwalki_gap/scenario.yaml` — NATO vs Russia in Baltic. Mixed terrain (forest, urban, river crossings). Exercises: EW, combined arms, doctrinal school comparison (maneuverist vs deep battle).
- `hybrid_gray_zone/scenario.yaml` — Gerasimov-style hybrid warfare. Insurgency, information operations, SOF, conventional escalation. Exercises: escalation ladder, insurgency engine, SOF operations, political pressure.

### 30b: Historical Naval Scenarios (est. ~25 tests)

**New scenarios** (enabled by Phase 29 naval data):
- `jutland_1916/scenario.yaml` — WW1 grand fleet action. Dreadnought line engagement, battlecruiser screen, torpedo attack. Exercises: WW1 naval + naval gunnery.
- `trafalgar_1805/scenario.yaml` — Napoleonic fleet action. Nelson's two-column attack, breaking the line. Exercises: Napoleonic naval combat, formations, commander personality.
- `salamis_480bc/scenario.yaml` — Ancient naval battle. Greek triremes vs Persian fleet in narrows. Exercises: ancient naval combat, terrain channel effects.
- `stalingrad_1942/scenario.yaml` — WW2 urban combat, logistics crisis, encirclement. Exercises: WW2 engines, supply network disruption, morale collapse.

### 30c: Existing Scenario Expansion (est. ~20 tests)

- **73 Easting** — Expand OOB toward complete historical force composition. Address exchange ratio = infinity (investigate detection asymmetry causing zero blue losses).
- **Falklands** — Add San Carlos beachhead air raids as second scenario variant. Add Goose Green as ground engagement.
- **Golan Heights** — Expand with logistics and C2 propagation for multi-day campaign run.
- **Midway** — Replace fletcher_dd proxy with actual carrier units (from Phase 29a). Add carrier air operations.

### 30d: Validation & Backtesting (est. ~15 tests)

- Run all expanded scenarios through MC harness (Phase 7 pattern)
- Compare simulation outputs against historical data where available
- Document calibration overrides per scenario
- Verify full engine wiring exercised (EW, CBRN, Space subsystems active in relevant scenarios)

### Tests: `tests/validation/test_phase_30_scenarios.py`

### Exit Criteria
- At least 3 new modern joint scenarios running through full wired engine
- At least 3 new historical naval scenarios
- 73 Easting exchange ratio improved (non-infinite)
- Falklands has San Carlos variant
- Midway uses actual carrier units
- MC validation shows reasonable outcome distributions
- All scenarios exercise multiple engine subsystems (not just direct fire)

---

## Deficit Resolution Map

### Resolved by Phase 25
| Deficit | Description |
|---------|------------|
| 1.1 | ScenarioLoader auto-wiring (accumulated Phases 16–24) |
| 1.2 | CommanderEngine not on SimulationContext |
| 1.3 | battle.py assessment=None |
| 1.4 | Air campaign not wired to ATO |
| 1.5 | MOPP speed factor never passed |
| 1.6 | Era engines not wired into _create_engines() |
| 1.7 | Bare except in engine.py |
| 2.8 | COA weight overrides not called |
| 4.13 | Insurgency needs real data |
| 5.1 | EW engines not wired into tick loop |

### Resolved by Phase 26
| Deficit | Description |
|---------|------------|
| 5.6 | GPS spoofing unit_id="" |
| 5.7 | Hardcoded EW magic numbers |
| 7.1 | Hardcoded terrain channeling thresholds |
| 7.2 | Hardcoded fallback weather defaults |
| 7.3 | No puff aging/cleanup |
| 8.1 | Hardcoded fallback RNG seed (42) |
| 8.2 | Gas wind direction tolerance hardcoded |
| 8.3 | Trench direction angles hardcoded |
| 8.4 | Foraging ambush rate hardcoded |
| 10.4 | Integration gain caps at 4 |
| 10.5 | Armor type YAML data missing |

### Resolved by Phase 27
| Deficit | Description |
|---------|------------|
| 2.10 | No frontage/depth in melee |
| 2.11 | Cavalry charge ignores terrain |
| 2.12 | Barrage drift no observer correction |
| 2.13 | Gas mask don time not modeled |

### Resolved by Phase 30
| Deficit | Description |
|---------|------------|
| 2.20 | 73 Easting exchange ratio = infinity |
| 4.3 | Simplified force compositions |
| 4.4 | Falklands Sheffield only |

### Deliberately Deferred (won't fix in Block 2)
| Deficit | Rationale |
|---------|-----------|
| 2.1 | HEAT range-independence — physically correct |
| 2.2 | Carrier deck management — excessive detail |
| 2.3 | COA Lanchester wargaming — adequate for planning |
| 2.4 | Terrain-specific COA — large scope, future block |
| 2.5 | Stratagems proactively planned — future AI enhancement |
| 2.6 | Multi-echelon simultaneous planning — requires architectural rework |
| 2.7 | Reactive estimates — adequate with periodic update |
| 2.9 | Fire zone cellular automaton — center+radius adequate |
| 2.15 | Biological incubation — adequate for sim |
| 2.16 | RDD distributed source — adequate for sim |
| 2.17 | Strategic bombing interdependency — future depth |
| 2.18 | Fighter escort sub-simulation — probability modifier adequate |
| 2.19 | Convoy escort geometry — abstract parameter adequate |
| 3.1–3.6 | Logistics detail items — low impact |
| 4.1 | Messenger terrain traversal — low impact |
| 4.2 | Wave auto-assignment — future AI |
| 4.6–4.12 | Various C2/scenario infrastructure — adequate or low impact |
| 5.2–5.5 | EW fidelity depth (DRFM, TDOA, cooperative jamming, campaign validation) — future EW depth |
| 6.1–6.7 | Space domain depth — future space depth |
| 7.4 | Validation CBRN wiring — component validation sufficient |
| 9.1–9.5 | Terrain pipeline depth — real-world data adequate |
| 10.1–10.3 | Core infrastructure (pickle, threading, coverage) — won't fix / by design |
| 10.6 | Single-threaded loop — required for PRNG determinism |
| 11.1–11.4 | Deferred domains (cyber, 4GW schools, amphibious depth, FM 5-0) — future blocks |

---

## Estimated Test Counts

| Phase | Sub-phases | Est. Tests | Running Total |
|-------|-----------|------------|---------------|
| 25 | 25a–25d | 152 ✓ | 6,477 |
| 26 | 26a–26c | 82 ✓ | 6,559 |
| 27 | 27a–27d | 139 ✓ | 6,698 |
| 28 | 28a–28d | 137 ✓ | 6,835 |
| 29 | 29a–29d | ~85 | ~6,920 |
| 30 | 30a–30d | ~90 | ~7,010 |
| **Total** | | **~685** | **~7,010** |

---

## Verification

```bash
# Per-phase
uv run python -m pytest tests/unit/test_phase_25*.py --tb=short -q
uv run python -m pytest tests/unit/test_phase_26*.py --tb=short -q
uv run python -m pytest tests/unit/test_phase_27*.py --tb=short -q
uv run python -m pytest tests/unit/test_phase_28*.py --tb=short -q
uv run python -m pytest tests/unit/test_phase_29*.py --tb=short -q
uv run python -m pytest tests/validation/test_phase_30*.py --tb=short -q

# Full regression
uv run python -m pytest --tb=short -q
```

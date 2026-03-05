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

## Phase 26: Core Polish & Configuration

**Goal**: Fix PRNG discipline violations, replace all hardcoded magic numbers with configurable pydantic fields, and address remaining core engine quality items.

**Dependencies**: Phase 25 (wiring must work before polishing).

### 26a: PRNG Discipline (est. ~25 tests)

Remove all fallback `np.random.default_rng(42)` in era engines. Every engine that accepts `rng` must require it (no silent fallback). Audit:

- `combat/barrage.py` — WW1 barrage engine
- `combat/gas_warfare.py` — WW1 gas warfare
- `combat/volley_fire.py` — Napoleonic volley fire
- `combat/melee.py` — Napoleonic/Ancient melee
- `combat/archery.py` — Ancient archery
- `combat/siege.py` — Ancient siege
- `combat/naval_gunnery.py` — WW2 bracket firing
- Any others found via grep for `default_rng`

For each: make `rng` a required constructor parameter (no default). Update all call sites to inject RNG from RNGManager streams.

**Resolves deficits**: 8.1 (hardcoded fallback RNG seeds).

### 26b: Configurable Constants (est. ~30 tests)

Replace hardcoded magic numbers with pydantic Config fields:

| Module | Constant | Current Value | New Config Field |
|--------|----------|---------------|-----------------|
| `cbrn/dispersal.py` | Valley/ridge threshold | 5m height, 50m offset | `DisperseConfig.terrain_channel_height_m`, `terrain_channel_offset_m` |
| `cbrn/engine.py` | Fallback weather | wind=2.0, temp=20°C, cloud=0.5 | `CBRNConfig.fallback_wind_mps`, `fallback_temp_c`, `fallback_cloud_cover` |
| `combat/gas_warfare.py` | Wind direction tolerance | 60° | `GasWarfareConfig.max_wind_angle_deg` |
| `combat/barrage.py` | Trench direction angles | 30°/60° | `BarrageConfig.direction_interp_angles` |
| `combat/melee.py` | Foraging ambush rate | 10% | `ForagingConfig.ambush_casualty_rate` |
| `ew/jamming.py` | Jamming event radius | 50km | `JammingConfig.event_radius_km` |
| `ew/gps_spoofing.py` | unit_id="" hardcoded | empty string | Pass actual unit_id through event emission |
| `ew/` modules | Decoy-seeker matrix, traffic sigmoid | various | Config fields on respective pydantic models |

### 26c: Engine Lifecycle & Cleanup (est. ~20 tests)

- **`cbrn/dispersal.py`** (modified) — Add puff aging/cleanup: `max_puff_age_s` config field, `cleanup_aged_puffs()` method called each tick, removes puffs older than threshold.
- **`detection/detection.py`** (modified) — Make integration gain cap configurable: `DetectionConfig.max_integration_scans` (default 4, allow higher).
- **Unit YAML armor type data** — Add `armor_type` field to unit YAML files that lack it (based on real platform data).

**Resolves deficits**: 7.1 (terrain channeling), 7.2 (weather defaults), 7.3 (puff cleanup), 8.2 (gas wind angle), 8.3 (trench angles), 8.4 (foraging ambush), 5.6 (GPS spoofing unit_id), 5.7 (EW magic numbers), 10.4 (integration gain cap), 10.5 (armor type YAML).

### Tests: `tests/unit/test_phase_26a_prng.py`, `tests/unit/test_phase_26b_config.py`, `tests/unit/test_phase_26c_lifecycle.py`

### Exit Criteria
- `grep -r "default_rng" stochastic_warfare/` returns zero matches
- All previously hardcoded constants are pydantic Config fields with documented defaults
- CBRN puff cleanup runs each tick, respects max_puff_age_s
- GPS spoofing events carry actual unit_id
- Armor type specified in all armored unit YAML files
- All 6,400+ tests pass

---

## Phase 27: Combat System Completeness

**Goal**: Fill all missing cross-domain engagement paths, enhance the engagement engine with burst fire and submunition scatter, and complete naval combat mechanics.

**Dependencies**: Phase 25 (engine wiring), Phase 26 (PRNG discipline — new code must follow conventions).

### 27a: Cross-Domain Engagement Paths (est. ~50 tests)

- **`combat/engagement.py`** (modified) — New engagement types: `COASTAL_DEFENSE`, `AIR_LAUNCHED_ASHM`, `ATGM_VS_ROTARY`. Routing logic dispatches to appropriate physics engine.
- **`combat/missiles.py`** (modified) — Accept naval surface targets. Coastal defense ASHM flight profile (boost, cruise, terminal pop-up/sea-skim).
- **`combat/air_ground.py`** (modified) — Air-launched ASHM path: aircraft releases missile → `missiles.py` flight → `naval_surface.py` terminal defense.
- **`combat/air_defense.py`** or **`combat/engagement.py`** (modified) — ATGM engagement against low-altitude rotary-wing targets: range-limited, wire-guided specific Pk model.
- **`combat/air_combat.py`** (modified) — Replace string-based countermeasures with EW engine integration: query `EWEngine.get_jamming_effectiveness()` for radar-guided missiles, apply as Pk reduction.

### 27b: Engagement Engine Enhancements (est. ~45 tests)

- **`combat/engagement.py`** (modified) — Burst fire: read `weapon.burst_size`, fire N rounds per engagement call, accumulate hits via independent Bernoulli trials.
- **`combat/damage.py`** (modified) — DPICM submunition scatter: when AmmoType is DPICM or CLUSTER, scatter submunitions in a circular pattern, compute individual lethal radius hits, auto-call `UXOEngine.create_uxo_field()`.
- **`combat/air_combat.py`** (modified) — Multi-spectral CM stacking: accept list of countermeasure types, each reduces Pk against its target seeker type (chaff→radar, flare→IR, DIRCM→IR/radar).
- **`combat/indirect_fire.py`** (modified) — TOT synchronization: `FireMissionType.TIME_ON_TARGET` coordinates battery fire times to achieve simultaneous impact (compute time-of-flight per battery, stagger fire commands).
- **`combat/air_ground.py`** (modified) — CAS designation model: JTAC designation delay (configurable seconds), laser spot acquisition window, talk-on sequence latency.

### 27c: Naval Combat Completion (est. ~40 tests)

- **`combat/naval_surface.py`** (modified) — Modern naval gun engagement: fire control quality model (not WW2 bracket), Mk45 vs surface target with radar-directed accuracy.
- **`combat/naval_subsurface.py`** (modified) — ASW weapons: surface ship torpedo launch (ASROC/VLA trajectory + lightweight torpedo), depth charge pattern.
- **`combat/naval_subsurface.py`** (modified) — Torpedo countermeasures: NIXIE towed decoy (seduction probability), acoustic CM (confusion probability), evasive maneuver integration.
- **`combat/carrier_ops.py`** (modified) — Carrier air operations: sortie generation rate based on deck cycle time, CAP station management, recovery window scheduling.

### 27d: Selective Fidelity Items (est. ~30 tests)

- **`combat/barrage.py`** (modified) — Observer correction: when forward observer sensor is present, barrage drift corrects toward target (reduce drift rate by observer quality factor) instead of pure random walk.
- **`combat/melee.py`** (modified) — Cavalry terrain effects: slope penalty on charge speed, soft ground penalty, obstacle abort threshold.
- **`combat/melee.py`** (modified) — Frontage constraint: `max_frontage_m` config, excess attackers queue as second rank (reduced effectiveness).
- **`combat/gas_warfare.py`** (modified) — Gas mask don time: `don_time_s` config (default 15s), units exposed at full concentration during don time before MOPP protection applies.

**Resolves deficits**: 2.10 (no frontage/depth), 2.11 (cavalry terrain), 2.12 (barrage drift), 2.13 (gas mask don time).

### Tests: `tests/unit/test_phase_27a_cross_domain.py`, `tests/unit/test_phase_27b_engagement.py`, `tests/unit/test_phase_27c_naval.py`, `tests/unit/test_phase_27d_fidelity.py`

### Exit Criteria
- Ground units can engage naval targets via coastal defense missiles
- Air-launched ASHMs fly realistic profiles and face ship point defense
- ATGMs can engage hovering helicopters
- EW jamming effectiveness affects air combat missile Pk
- Burst fire resolves N rounds per engagement
- DPICM submunitions scatter and create UXO fields
- Surface ships can launch ASW weapons against submarines
- Torpedo countermeasures (NIXIE) modeled
- Barrage drift corrects with observer feedback
- Cavalry charge speed affected by terrain
- All 6,500+ tests pass

---

## Phase 28: Modern Era Data Package

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

## Phase 29: Historical Era Data Expansion

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
| 25 | 25a–25d | 151 ✓ | 6,476 |
| 26 | 26a–26c | ~75 | ~6,560 |
| 27 | 27a–27d | ~165 | ~6,725 |
| 28 | 28a–28d | ~70 | ~6,795 |
| 29 | 29a–29d | ~85 | ~6,880 |
| 30 | 30a–30d | ~90 | ~6,970 |
| **Total** | | **~645** | **~6,970** |

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

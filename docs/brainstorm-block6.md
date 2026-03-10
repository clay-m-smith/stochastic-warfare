# Stochastic Warfare -- Block 6 Brainstorm

## Context

Blocks 1--5 (Phases 0--48) built the complete simulation engine, 5 historical eras, a REST API, a React web application, Docker packaging, and ~8,274 tests (8,002 Python + 272 frontend vitest). 42+ scenarios across 5 eras. The engine has 19+ modules across all combat domains (land/air/naval/sub/space/EW/CBRN/DEW).

Block 5 (Phases 40--48) was the first systematic effort to improve core combat fidelity -- wiring 40+ disconnected subsystems into the battle loop, adding terrain/training/weather/ROE modifiers, recalibrating all scenarios against historical outcomes, and resolving 74+ deficits. The Phase 48 postmortem discovered 10 new deficits (E1--E10) and formally deferred 16 items (D1--D16).

Block 6 is the **final tightening block** -- resolving every known limitation, wiring every orphaned feature, hardening every schema, and validating every scenario. The goal is zero unresolved deficits and zero untested code paths in the simulation core.

---

## Motivation: Complete Deficit Inventory

### Phase 48 Postmortem Deficits (E1--E10)

| ID | Deficit | Severity | Root Cause |
|----|---------|----------|------------|
| E1 | `advance_speed` dead data in 7 scenarios | Medium | No Python code reads this key; calibration audit gives false pass |
| E2 | `dig_in_ticks` consumed but untested | Low | battle.py reads it but zero scenarios set it |
| E3 | `wave_interval_s` consumed but untested | Low | battle.py reads it but zero scenarios set it |
| E4 | `target_selection_mode` untested | Low | Always defaults to `threat_scored`; no scenario overrides |
| E5 | `roe_level` sparse coverage | Low | Only 2 of ~37 scenarios set ROE; COIN/peacekeeping missing |
| E6 | Morale config weights never tuned | Medium | cohesion, leadership, suppression, transition_cooldown unused |
| E7 | `victory_weights` untested | Low | Composite victory scoring never exercised in scenarios |
| E8 | 4 SEAD/IADS params unwired | Medium | sead_effectiveness, sead_arm_effectiveness, iads_degradation_rate, drone_provocation_prob |
| E9 | Resolution switching → time_expired | Medium | Long-range battles spend 275+ ticks closing, then jump to strategic |
| E10 | Calibration audit false pass | Low | `_EXTERNAL_KEYS` includes dead `advance_speed` |

### Formally Deferred Items (D1--D16)

| ID | Deficit | Category |
|----|---------|----------|
| D1 | Posture doesn't affect movement speed | Combat Fidelity |
| D2 | Naval unit posture undefined | Naval |
| D3 | Air unit posture undefined | Combat Fidelity |
| D4 | Binary concealment (no continuous degradation) | Detection |
| D5 | O(n^2) rally cascade | Performance |
| D6 | Phantom naval engines (4 referenced, never instantiated) | Naval |
| D7 | WW1 barrage uses generic fire-on-move penalty | Era Fidelity |
| D8 | Night/day effect binary (no twilight gradation) | Environmental |
| D9 | Weather effects stop at visibility (no wind/precip on ballistics) | Environmental |
| D10 | Maintenance registration incomplete | Logistics |
| D11 | Medical/engineering data sparse (hardcoded times) | Logistics |
| D12 | Per-commander assessment unimplemented (ground truth shared) | AI/C2 |
| D13 | Weibull maintenance global, not per-subsystem | Logistics |
| D14 | Training data in YAML not connected to crew_skill | Combat Fidelity |
| D15 | time_expired wins over combat outcome | Victory |
| D16 | DEW hits always destroy, never disable | Combat Fidelity |

### Persistent Known Limitations from Earlier Phases

| Source | Deficit | Category |
|--------|---------|----------|
| Phase 5 | Messenger comm type has no terrain traversal or intercept risk | C2 |
| Phase 6 | Blockade effectiveness simplified (flat per-ship probability) | Naval |
| Phase 6 | VLS non-reloadable-at-sea enforcement deferred | Naval |
| Phase 8 | Stratagems opportunity-evaluated, not proactively planned | AI |
| Phase 9 | Fixed reinforcement schedule (no stochastic arrivals) | Simulation |
| Phase 16 | Campaign-level EW validation deferred | EW |
| Phase 17 | Space-based SIGINT not integrated with EW SIGINT engine | Space/EW |
| Phase 19 | `CommanderPersonality.school_id` defined but never read | AI |
| Phase 19 | `get_stratagem_affinity()` hook defined but never called | AI |
| Phase 20 | Strategic bombing target regeneration linear (no industrial graph) | WW2 |
| Phase 21 | Trench wire-cutting mechanic not modeled (wire is query-only) | WW1 |
| Phase 25 | C2 effectiveness hardcoded at 1.0 | C2 |
| Phase 25 | Air campaign ATO wiring not addressed | Air |
| Phase 25 | Stratagem affinity wiring not implemented | AI |
| Phase 25 | school_id auto-assignment not implemented | AI |
| Phase 30 | Proxy units in some scenarios (wrong unit types substituted) | Data |
| Phase 37 | 8 legacy scenarios can't load through API | API |

### Fully Implemented but Dead (Instantiated, Never Called)

The deep code audit revealed **25+ engines/managers** that are instantiated in `ScenarioLoader._create_engines()` but **never called** from the battle loop, campaign loop, or engine step loop. These represent thousands of lines of tested, working code that provide zero simulation value because they're disconnected.

#### Tier 1: Core Subsystems (Never Instantiated or Never Called — Highest Impact)

| Subsystem | File | What It Does | Why Dead |
|-----------|------|-------------|----------|
| **StratagemEngine** | `c2/ai/stratagems.py` | 9 stratagem types, eligibility, opportunity eval, EventBus activation | Never instantiated. No caller in OODA/decision loop. |
| **DisruptionEngine (Blockade)** | `logistics/disruption.py` | `apply/check/remove_blockade()`, zone enforcement, state persistence | Never instantiated. Never called from campaign/battle. |
| **ATOPlanningEngine** | `c2/orders/air_orders.py` | `generate_ato()`, aircraft availability, mission queue | Never instantiated. Not in OODA/decision cycles. |
| **FogOfWarManager** | `detection/fog_of_war.py` | Per-side detection picture filtering | Created but **never queried**. All assessments use ground truth. |
| **PlanningProcessEngine** | `c2/planning/process.py` | MDMP/COA generation engine | Instantiated, never called. |
| **OrderPropagationEngine** | `c2/orders/propagation.py` | Order hierarchy propagation through CoC | Stored, never invoked in loop. |
| **MineWarfareEngine** | `combat/naval_mine.py` | Mine trigger, sweep, avoidance | Never routed in battle.py. |

#### Tier 2: Space/EW Sub-Engines (Instantiated inside parent, never individually called)

`SpaceEngine.update()` is called from engine.py, but its sub-engines are never individually invoked:

| Subsystem | File | What It Does | Status |
|-----------|------|-------------|--------|
| **SIGINTEngine** | `ew/sigint.py` | SIGINT geolocation, intercept probability | Instantiated, not called in loop |
| **ECCMEngine** | `ew/eccm.py` | Electronic counter-countermeasures | Instantiated, not called in loop |
| **GPSEngine** | `space/gps.py` | GPS DOP/accuracy computation | Accessed via fragile `space_engine.gps_engine` (private) |
| **SpaceISREngine** | `space/isr.py` | Space-based ISR tasking | Instantiated, not called |
| **EarlyWarningEngine** | `space/early_warning.py` | Missile launch detection | Instantiated, not called |
| **SATCOMEngine** | `space/satcom.py` | Satellite communications | Instantiated, not called |
| **ASATEngine** | `space/asat.py` | Anti-satellite + debris cascade | Instantiated, not called |

#### Tier 3: Escalation/Unconventional (Instantiated, never triggered)

| Subsystem | File | What It Does | Status |
|-----------|------|-------------|--------|
| **PoliticalPressureEngine** | `escalation/political.py` | International/domestic pressure effects | Not called in loop |
| **UnconventionalWarfareEngine** | `combat/unconventional.py` | IED, guerrilla, human shields | Not called |
| **UXOEngine** | `combat/damage.py` | UXO field processing | Not called |

#### Tier 4: Era-Specific Engines (Created conditionally, never called from battle routing)

These are created when their era is active but battle.py never calls them:

| Subsystem | Era | What It Does |
|-----------|-----|-------------|
| **ConvoyEngine** | WW2 | Convoy escort, wolf pack |
| **StrategicBombingEngine** | WW2 | Strategic bombing campaigns, CEP |
| **BarrageEngine** | WW1 | Creeping barrage (zone-based fire density) |
| **GasWarfareEngine** | WW1 | Chemical warfare CBRN adapter |
| **TrenchSystemEngine** | WW1 | Trench spatial overlay queries |
| **CavalryEngine** | Napoleonic | Cavalry charge state machine |
| **CourierEngine** | Napoleonic | Courier C2 dispatch + terrain speed |
| **ForagingEngine** | Napoleonic | Foraging logistics |
| **SiegeEngine** | Ancient | Daily siege state machine |
| **AncientFormationEngine** | Ancient | Formation combat modifiers |
| **NavalOarEngine** | Ancient | Oar-powered naval movement |
| **VisualSignalEngine** | Ancient | Visual signals C2 |

#### Tier 5: Never-Created Context Fields

These are declared in `SimulationContext.__init__` with `= None` but never instantiated by any code path:

| Field | Purpose | Status |
|-------|---------|--------|
| `SeasonsEngine` | Seasonal weather variation | Declared, never created |
| `ConditionsEngine` | Composite environmental conditions | Declared, never created |
| `ObscurantsEngine` | Smoke/obscurant effects | Declared, never created, never referenced |

### Config Fields with Zero Scenario Coverage

| Config | Scenarios Using It | Impact |
|--------|-------------------|--------|
| `space_config` | **0 of 27** modern scenarios | Space subsystem entirely dormant |
| `commander_config` | **0 scenarios** | Commander engine never activated |
| `cbrn_config` | 1 scenario (korean_peninsula) | CBRN barely exercised |
| `school_config` | 1 scenario (suwalki_gap) | Doctrinal schools barely exercised |
| `dew_config` | 1 scenario (taiwan_strait) | DEW barely exercised |

### Dead YAML Data Fields (Loaded, Never Consumed)

10 fields are parsed from YAML into pydantic models but never read during simulation:

| Field | Model | Impact |
|-------|-------|--------|
| `traverse_deg` | WeaponDefinition | Weapon traverse arc — never checked |
| `elevation_min_deg` | WeaponDefinition | Min elevation — never checked |
| `elevation_max_deg` | WeaponDefinition | Max elevation — never checked |
| `beam_wavelength_nm` | WeaponDefinition | DEW wavelength — never used in Beer-Lambert |
| `weight_kg` | WeaponDefinition / EquipmentItem | Weight — only serialized in state, never consulted |
| `terminal_maneuver` | AmmoDefinition | Terminal guidance behavior — never read |
| `propulsion` | AmmoDefinition | Propulsion type — never read |
| `seeker_fov_deg` | AmmoDefinition | Seeker field of view — never queried |
| `unit_cost_factor` | AmmoDefinition | Economic cost — never used |
| `data_link_range` | UnitDefinition (Aerial) | Data link range — never checked |

### Fragile Internal API Access

| Location | Pattern | Risk |
|----------|---------|------|
| battle.py:1348 | `cbrn_engine._mopp_levels` | Private dict access — no public API |
| battle.py:1893 | `space_engine.gps_engine` | Nested optional attribute access |

### Cross-Brainstorm Promises Not Yet Delivered

| Document | Promise | Status |
|----------|---------|--------|
| brainstorm-post-mvp.md | 4GW doctrinal school | Deferred -- Phase 24 infrastructure supports it |
| brainstorm-post-mvp.md | Unrestricted Warfare school | Deferred -- Phase 24 infrastructure supports it |
| brainstorm-post-mvp.md | Gerasimov Hybrid school | Deferred -- Phase 24 infrastructure supports it |
| brainstorm-post-mvp.md | Terrain-based comms LOS | Not implemented -- radio doesn't query terrain LOS |
| brainstorm-post-mvp.md | Dwell/integration gain for detection | Confirmed wired in detection.py (Phase 26c): `enable_integration_gain`, `max_integration_scans=4`, SNR + 5*log10(n_scans) |
| brainstorm.md | Full serialization/replay determinism | Checkpoint pickle fragility unresolved |

### Additional Data Gaps (from Phase 46/47 devlogs)

| Source | Gap | Impact |
|--------|-----|--------|
| Phase 46 | A-4 Skyhawk has cannon only, no bomb weapon | Falklands air attack scenario unrealistic |
| Phase 46 | Eastern Front WW2 missing weapon_assignments | Scenario can't resolve engagements properly |
| Phase 46 | Saracen cavalry proxy for Roman equites (ground_type mismatch) | Unit type semantics wrong |
| Phase 46 | Iraqi Republican Guard as insurgent_squad proxy | Training/equipment mismatch |
| Phase 47 | Falklands campaign resolves via morale collapse (2 ticks, 0 engagements) | Wrong resolution mechanism |
| Phase 42 | Rout cascade uses RoutEngine defaults, no per-scenario config | Can't tune rout behavior |
| Phase 43 | Shore bombardment checks weapon category not platform type | Land artillery can "shore bombard" |
| Phase 45 | `blast_radius_to_fill_c=26.6` calibrated for 155mm HE only | Other munitions use wrong constant |

---

## Gap Analysis by Theme

### Theme 1: Calibration Schema Hardening

**Problem**: `calibration_overrides` is `dict[str, Any]` with no schema validation. This is the root cause of silent parameter drift across 30+ scenarios. Mistyped keys pass without error. The Phase 48 audit found 7 dead keys and 6 untested paths.

**Solution**: Replace the free-form dict with a typed pydantic `CalibrationSchema` model. Each scenario era/domain combination gets validated fields with documented ranges and defaults. The calibration key audit test becomes a schema validation test -- if a key isn't in the schema, it fails at load time, not at audit time.

**Scope**:
- Define `CalibrationSchema` pydantic model with all ~100 known keys organized by subsystem
- Migrate all ~37 scenario YAMLs from `calibration_overrides: {key: val}` to structured fields
- Remove `advance_speed` dead data from 10 scenario YAMLs (verified: 10 files, not 7)
- Fix calibration audit test false positive (E10)
- Exercise untested paths: `dig_in_ticks`, `wave_interval_s`, `target_selection_mode`, `victory_weights`
- Wire morale config weights into at least 3 representative scenarios
- Expand `roe_level` coverage to COIN/peacekeeping/humanitarian scenarios
- Include `target_value_weights` in schema (currently hardcoded in `_score_target()`: HQ=2.0, AD=1.8, ARTILLERY=1.5, etc.)
- Include `blast_radius_to_fill_c` per munition category (currently 26.6 for all, calibrated for 155mm HE)
- Include `rout_cascade_config` (cascade_radius, friendly_count_threshold, rout_morale_penalty)

**Design considerations**:
- Schema must be backward-compatible: fields default to current hardcoded values
- Era-specific fields gated by era (Napoleonic formation_spacing_m irrelevant for modern)
- Schema replaces `dict[str, Any]` in `CampaignScenarioConfig` -- ScenarioLoader validates at parse time
- Calibration audit test simplified to "all schema fields consumed" static check
- Target value weights and blast constants move from hardcoded dicts to schema fields -- consumers read from calibration, not from code

### Theme 2: Naval Combat Completeness

**Problem**: `_route_naval_engagement()` in battle.py references naval engine attributes (`naval_subsurface_engine`, `naval_surface_engine`, `naval_gunnery_engine`, `naval_gunfire_support_engine`) that are never set on the battle manager. All naval weapons fall through to the direct-fire path. The actual naval combat code exists as methods on `NavalSubsurfaceEngine` (torpedo, depth charge, countermeasures) and `NavalSurfaceEngine` (anti-ship missile, naval gunnery) classes from Phases 4 and 27, but these engines are never instantiated in `_create_engines()`. Naval units have no posture concept. DEW hits always destroy, never disable. The `DisruptionEngine` (blockade mechanics) is fully implemented but never instantiated.

**Solution**: Instantiate the existing naval engines and wire their methods into the routing. Implement naval posture. Add DEW disable path. Wire the blockade system.

**Scope**:
- Instantiate `NavalSubsurfaceEngine` and `NavalSurfaceEngine` in `_create_engines()` and set them as attributes on the battle manager
- Wire `_route_naval_engagement()` to call existing methods: `torpedo_engagement()`, `depth_charge_attack()`, anti-ship missile resolution, naval gunnery
- Shore bombardment reachability: verify platform is NAVAL domain before routing to naval gunfire support (currently only checks weapon category)
- Naval posture enum: `ANCHORED`, `UNDERWAY`, `TRANSIT`, `BATTLE_STATIONS` -- affects vulnerability, detection cross-section, weapons readiness
- DEW disable path: below threshold → DISABLED (combat-ineffective), above threshold → DESTROYED. Configurable via `dew_config.disable_threshold` (0.0--1.0)
- Wire `DisruptionEngine` for blockade mechanics: instantiate in scenario loader, call `check_blockade()` from supply network when computing naval supply routes
- Wire `MineWarfareEngine`: route mine encounters through existing mine warfare code in `combat/naval_mine.py` — mine trigger matching, sweep, avoidance
- Validate with Trafalgar, Midway, Jutland, Falklands, Salamis scenarios

**Design considerations**:
- This is primarily a **wiring** task -- the combat code already exists and is tested standalone
- Naval engine methods (`torpedo_engagement()`, `depth_charge_attack()`, etc.) take parameters that battle.py already computes (attacker, defender, weapon, range)
- Naval posture integrates with existing posture system (D1 movement speed effect applies here too)
- Blockade wiring integrates with existing `SupplyNetwork` route computation -- blockaded zones reduce supply flow

### Theme 3: Combat Fidelity Polish

**Problem**: Multiple combat mechanics are simplified beyond what the engine can now support. Posture doesn't affect movement speed. Air units have no posture. Concealment is binary. Training data in YAML is disconnected from crew_skill. WW1 barrage uses the generic fire-on-move penalty designed for modern tanks.

**Solution**: Wire each of these into the existing systems with minimal new code.

**Scope**:
- **D1 -- Posture → movement speed**: DUG_IN/FORTIFIED units get 0.0/0.0 movement multiplier (can't move while dug in). HASTY_DEFENSE gets 0.5x. Straightforward multiplication in movement engine.
- **D3 -- Air posture**: `INGRESSING`, `ON_STATION`, `RETURNING`, `GROUNDED`. Affects fuel consumption rate, detection cross-section, weapons availability. Maps onto existing flight state tracking.
- **D4 -- Continuous concealment**: Replace binary hidden/revealed with concealment score (0.0--1.0) that degrades with observation duration. Each tick of sustained observation reduces concealment by `observation_decay_rate`. Threshold for engagement authorization configurable.
- **D14 -- Training → crew_skill**: Unit YAML `training_level` field (CONSCRIPT=0.6, REGULAR=0.8, VETERAN=1.0, ELITE=1.2) feeds into `crew_skill` multiplier in battle.py. Currently `crew_skill` is computed but training level is never read.
- **D7 -- WW1 barrage penalty**: Creeping barrage accuracy should be independent of movement state -- barrage is pre-planned fire, not aimed fire. Remove fire-on-move penalty for `BARRAGE` engagement type; apply barrage-specific accuracy based on observer correction quality.
- **D16 -- DEW disable**: (handled in Theme 2 above, naval section)
- **Target value weights configurable**: `_score_target()` has hardcoded weights (HQ=2.0, AD=1.8, ARTILLERY=1.5, etc.). Move to configurable YAML or calibration schema so scenarios can tune target prioritization.
- **Melee weapon range filtering**: Weapons with `max_range_m` < target distance are filtered out before melee routing can trigger. Melee weapons need `max_range_m=0` in YAML; verify all melee weapon definitions have correct range.
- **Blast radius per weapon type**: `blast_radius_to_fill_c=26.6` calibrated for 155mm HE. Different munition categories (mortar, naval gun, bomb, rocket) need per-type calibration constants.

**Design considerations**:
- Posture movement speed is a simple multiplier lookup table, not a new system
- Air posture maps onto existing `FlightState` enum if it exists, or extends it
- Concealment score lives on the detection track (Kalman filter state), not on the unit -- pure detection system extension
- Training → crew_skill: verification pass confirmed training_level IS wired in battle.py line 1822 (`effective_skill = base_skill * (0.5 + 0.5 * unit_training)`). The gap is that no unit YAML actually defines `training_level` -- all default to 0.5. Fix is data: add `training_level` to unit YAMLs, not engine code.
- Target value weights: move from hardcoded dict to `CalibrationSchema.target_value_weights` (Theme 1 integration)

### Theme 4: Environmental Continuity

**Problem**: Environmental effects are binary gates rather than continuous modifiers. Night detection is halved or not halved -- no twilight. Weather affects only visibility_km -- no wind drift on ballistics or precipitation on sensors. Sea state affects dispersion but not formation spacing. Comms have no terrain LOS blocking.

**Solution**: Replace binary gates with continuous functions using physically-grounded models.

**Scope**:
- **D8 -- Night gradation**: Solar elevation (already computed by `AstronomyEngine`) drives a continuous detection modifier. Civil twilight (-6 deg) = 0.8x, nautical (-12 deg) = 0.5x, astronomical (-18 deg) = 0.3x, full night = 0.2x (was 0.5x binary). Thermal sensors get reduced penalty (0.8x at night vs 0.2x for visual).
- **D9 -- Weather → ballistics**: Wind speed/direction (already in `WeatherEngine`) applied as cross-wind drift to ballistic trajectories. Precipitation rate reduces sensor effectiveness (rain attenuation on radar: ~0.01 dB/km per mm/hr at X-band, ~0.1 dB/km at Ka-band). Sea state → formation spacing for naval formations.
- **Terrain-based comms LOS**: Radio communications between units check LOS via the existing `LOSEngine`. If terrain blocks the line between transmitter and receiver, signal is attenuated (not blocked -- UHF/VHF diffraction over ridgelines with ~6 dB loss per obstruction). HF skywave unaffected by terrain. Already have all the infrastructure (LOSEngine + CommsEngine) -- just need the bridge.
- **Space-based SIGINT + EW SIGINT integration**: Phase 17 space SIGINT and Phase 16 EW SIGINT operate independently. Fuse detections from both into a single target track when both are available.

**Design considerations**:
- Solar elevation is already computed per tick -- continuous modifier is a lookup, not a computation
- Wind drift on ballistics uses existing `WeatherEngine.get_conditions()` wind vector -- small addition to RK4 ballistic solver
- Comms LOS uses existing LOSEngine infrastructure -- just call `check_los()` between transmitter and receiver positions
- Rain attenuation model well-established (ITU-R P.838); simple power-law fit

### Theme 5: C2 & AI Completeness

**Problem**: The C2/AI subsystem has the largest concentration of dead code in the project. 6 complete engines are instantiated but never called. C2 effectiveness is hardcoded at 1.0. The `FogOfWarManager` — foundation for realistic AI decision-making — is created but never queried, meaning all commanders have perfect omniscient information. Stratagems, ATO planning, and order propagation all exist as complete implementations that sit idle.

**Solution**: Wire each feature into its natural integration point. Prioritize FogOfWarManager (enables fog-of-war assessment) and StratagemEngine (enables doctrinal school differentiation).

**Scope**:
- **FogOfWarManager wiring** (CRITICAL): `detection/fog_of_war.py` is created but **never queried**. Wire it so each side's detection picture is maintained per tick. This is the prerequisite for fog-of-war assessment — without it, all AI uses ground truth.
- **Per-commander assessment (fog of war)**: Once FogOfWarManager is wired, commanders assess enemy strength based on their side's detection picture, not ground truth. Each commander's `BattleAssessment` uses only detected units (filtered through fog of war).
- **PlanningProcessEngine wiring**: `c2/planning/process.py` implements full MDMP/COA generation. Instantiated but never called. Wire into campaign-level planning so commanders generate and evaluate COAs.
- **OrderPropagationEngine wiring**: `c2/orders/propagation.py` implements order hierarchy propagation through the chain of command. Stored but never invoked. Wire so orders from higher echelons propagate through subordinate commands with appropriate delays.
- **C2 effectiveness**: Replace hardcoded 1.0 with computed value from comms health (hop count, signal quality, relay availability). C2 effectiveness already has consumers -- it modifies OODA cycle speed, order propagation delay, and fire coordination quality. The source computation is missing.
- **StratagemEngine wiring**: `c2/ai/stratagems.py` has a complete 417-line StratagemEngine with 9 stratagem types, eligibility checks, opportunity evaluation, and EventBus activation -- but it is **never instantiated**. Instantiate in `_create_engines()`, wire into OODA DECIDE phase so commanders evaluate stratagem opportunities each cycle.
- **Stratagem affinity**: Each doctrinal school defines `get_stratagem_affinity()` returning preference weights for available stratagems. Wire into `_process_ooda_completions()` so commanders weight stratagems by their school preference during DECIDE phase.
- **school_id auto-assignment**: `CommanderPersonality.school_id` field → `SchoolRegistry.get_school(school_id)` lookup during commander initialization. Currently schools are assigned via explicit registry calls; school_id field is dead data.
- **SEAD/IADS parameters (E8)**: Wire `sead_effectiveness` into IADS node suppression, `iads_degradation_rate` into IADS health decay per destroyed node, `sead_arm_effectiveness` into ARM missile Pk modifier, `drone_provocation_prob` into escalation trigger evaluation.
- **ATOPlanningEngine wiring**: `c2/orders/air_orders.py` has a complete ~150-line ATOPlanningEngine with `generate_ato()`, aircraft availability tracking, and mission request queue -- but it is **never instantiated**. Instantiate in `_create_engines()`, wire into campaign-level planning so CAS/interdiction/SEAD sorties are generated from objectives.
- **Escalation sub-engine wiring**: `PoliticalPressureEngine` (international/domestic pressure), `UnconventionalWarfareEngine` (IED/guerrilla/human shields), `UXOEngine` (unexploded ordnance fields) are all instantiated but never called. Wire into engine.py step loop and battle.py as appropriate.
- **Messenger intercept risk**: Modern `MESSENGER` CommType in `c2/communications.py` has no terrain traversal or intercept model. Napoleonic `CourierEngine` has interception probability + terrain speeds -- extend the intercept concept to modern runner/messenger comms (low priority, niche use case).

**Design considerations**:
- **FogOfWarManager is the single most impactful wiring target** -- it transforms AI from omniscient to realistic and enables per-side detection pictures for the tactical map FOW toggle
- C2 effectiveness computation: `eff = base × (1 - hop_penalty × hops) × signal_quality × (1 if within_range else degraded)` -- simple formula using existing data
- StratagemEngine and ATOPlanningEngine are the two largest blocks of dead code -- wiring them is high-value/low-risk since both have existing tests
- PlanningProcessEngine → DecisionEngine pipeline: planning generates COAs, decision evaluates them. Both exist; the pipeline connector is missing.
- School_id wiring is a one-line change in commander initialization
- SEAD/IADS params already have consumers in `combat/iads.py` -- just need to read from escalation config instead of using defaults
- Escalation sub-engines follow the same wiring pattern: instantiate (already done), add update() call in engine.py step loop, add engagement routing if combat-relevant

### Theme 6: Resolution & Scenario Migration

**Problem**: Resolution switching causes long-range battles to resolve via `time_expired` instead of decisive combat. 8 legacy scenarios use pre-Phase-32 YAML format and can't load through the API. ROE is set in only 2 of 37 scenarios.

**Solution**: Fix resolution switching logic, migrate legacy scenarios, and expand ROE coverage.

**Scope**:
- **Resolution switching (E9/D15)**: The core issue is that battles starting >50km apart spend 275+ tactical ticks (5s each, ~23 min sim time) closing distance, then resolution switches to strategic (3600s ticks) when the battle is "stale." But force_destroyed can only trigger during tactical ticks. Fix: allow force_destroyed evaluation during strategic ticks too, or delay resolution switching until units are within engagement range.
- **Legacy scenario migration**: 8 scenarios use Phase 0--7 YAML format (flat structure, no `campaign` wrapper, no `sides` array). Migrate to Phase 32+ campaign format with sides/objectives/victory_conditions. This makes all scenarios loadable through the API.
- **ROE expansion (E5)**: Add `roe_level` to scenarios where it's doctrinally appropriate -- Srebrenica (already has WEAPONS_TIGHT), peacekeeping, COIN, hybrid gray zone, humanitarian. Approximately 5--8 scenarios should have non-default ROE.
- **Proxy unit replacement (Phase 30)**: Replace substituted units (MiG-29 as A-4 Skyhawk, US rifle squad as 2 Para) with proper era-appropriate unit definitions where data exists.
- **Data gap fixes**: A-4 Skyhawk needs bomb weapon (currently cannon-only, unrealistic for Falklands air attack). Eastern Front WW2 needs weapon_assignments. Roman equites unit (Phase 48) uses Saracen cavalry as proxy with wrong ground_type. Iraqi Republican Guard uses insurgent_squad proxy.
- **Falklands campaign mechanism**: Currently resolves via morale collapse in 2 ticks with 0 engagements. Needs calibration so air/naval engagements drive the outcome, not instant morale collapse.
- **Rout cascade per-scenario config**: Rout cascade uses global RoutEngine defaults. Add per-scenario rout configuration (cascade_radius, friendly_count_threshold, rout_morale_penalty) to calibration schema.

**Design considerations**:
- Resolution switching fix must not break scenarios that correctly use strategic resolution (campaign-scale)
- Guard: only keep tactical resolution while any pair of opposing units is within 2x max engagement range
- Legacy migration is pure YAML restructuring -- no engine changes
- ROE expansion requires understanding each scenario's doctrinal context
- Data gaps are pure YAML work (new weapon definitions, weapon_assignments, unit type corrections)

### Theme 7: Performance & Logistics

**Problem**: O(n^2) rally cascade checks all units against all units. Maintenance failures are generated but never reported in UI or affect readiness chains. Medical/engineering times are hardcoded. Weibull failure distribution is global, not per-subsystem.

**Solution**: Targeted optimizations and logistics wiring.

**Scope**:
- **D5 -- Rally spatial index**: Use STRtree (already a project dependency via shapely) to index unit positions. Rally checks query within rally_radius instead of iterating all units. Expected improvement: O(n log n) from O(n^2).
- **D10 -- Maintenance registration**: Wire maintenance failure events to unit readiness state. A unit with a maintenance failure transitions to MAINTENANCE state (can't engage, reduced movement). Existing `MaintenanceEngine.check_failures()` generates events -- need subscriber in battle loop that updates unit status.
- **D11 -- Medical/engineering per-era data**: Replace hardcoded 30s/60s recovery times with era-appropriate values from YAML configs. Modern: 15min CASEVAC, WW2: 45min stretcher, WW1: 2hr trench evacuation, Napoleonic: field surgery hours, Ancient: camp treatment day-scale.
- **D13 -- Weibull per-subsystem**: Replace global shape parameter (k=1.5) with per-subsystem shapes. Engine: k=1.2 (infant mortality dominant), transmission: k=2.0 (wear-out dominant), electronics: k=1.0 (random failure). Lookup from unit type definition YAML.
- **VLS reload enforcement**: Naval units with VLS launchers can't reload at sea. Track remaining VLS cells; when exhausted, missile engagements from that unit are blocked until port visit.
- **DisruptionEngine/Blockade wiring**: (handled in Theme 2 above, naval section — instantiate DisruptionEngine, wire into supply network)

**Design considerations**:
- STRtree for rally is the same pattern used for terrain queries (Phase 13) -- proven approach
- Maintenance → readiness is event-driven (subscribe to MaintenanceFailureEvent, update unit state)
- Per-era medical times are pure data -- add YAML fields to era configs
- Weibull per-subsystem requires new YAML fields on unit type definitions but no engine changes
- VLS enforcement: check `unit.vls_remaining` before allowing missile engagement; decrement on fire

### Theme 8: Era-Specific & Domain Sub-Engine Wiring

**Problem**: 12 era-specific engines and 7 space/EW sub-engines are instantiated when their era or config is active, but never called from the battle loop or engine step loop. Historical scenarios lose their era-specific flavor (cavalry charges, creeping barrages, siege progression, convoy escorts) because these engines sit idle. Space scenarios are entirely dormant (0 scenarios even activate `space_config`).

**Solution**: Wire each era-specific engine into battle.py routing or engine.py step loop. Add scenarios that exercise space_config and commander_config.

**Scope**:

**WW2 era engines**:
- **ConvoyEngine**: Wire into campaign loop for convoy escort / wolf pack scenarios. Already has convoy effectiveness parameter.
- **StrategicBombingEngine**: Wire into campaign loop for strategic bombing target sets. Has CEP-based damage model.

**WW1 era engines**:
- **BarrageEngine**: Wire into battle.py as alternative to IndirectFireEngine for WW1 scenarios. Zone-based fire density model (rounds/hectare), not individual shell tracking.
- **GasWarfareEngine**: Wire into battle.py engagement routing for chemical weapon types. Already wraps CBRN pipeline.
- **TrenchSystemEngine**: Wire into battle.py terrain queries so trench cover/concealment applies to units inside trench lines.

**Napoleonic era engines**:
- **CavalryEngine**: Wire into battle.py melee routing for cavalry charge state machine (approach → charge → melee → pursuit/rout).
- **CourierEngine**: Wire into C2 order propagation for Napoleonic scenarios so orders travel by courier with terrain-dependent speed and interception risk.
- **ForagingEngine**: Wire into logistics consumption for Napoleonic scenarios so units forage when supply lines are cut.

**Ancient/Medieval era engines**:
- **SiegeEngine**: Wire into campaign loop for siege scenarios. Daily state machine (assault/breach/starve).
- **AncientFormationEngine**: Wire into battle.py so ancient formation effects (phalanx, testudo, shield wall) modify combat.
- **NavalOarEngine**: Wire into movement engine for ancient naval scenarios. Oar-powered speed/endurance.
- **VisualSignalEngine**: Wire into C2 for ancient scenarios. Visual signal C2 with LOS requirements.

**Space/EW sub-engines (require scenarios with space_config)**:
- Create at least 2 scenarios with `space_config` to activate the space subsystem
- Create at least 2 scenarios with `commander_config` to activate commander engine
- Expand CBRN, school, and DEW scenario coverage (currently 1 each)
- Verify SpaceEngine.update() properly delegates to sub-engines (GPS, ISR, Early Warning, SATCOM, ASAT)
- Verify SIGINTEngine and ECCMEngine are called from engine.py EW step (may need explicit wiring)

**Dead YAML fields**: Either wire the 10 dead weapon/ammo/unit fields into simulation logic or remove them from pydantic models to avoid confusion. Fields like `traverse_deg`, `elevation_min/max_deg` should constrain weapon engagement arcs. `beam_wavelength_nm` should feed into Beer-Lambert atmospheric transmittance for DEW. `terminal_maneuver` and `seeker_fov_deg` should affect hit probability.

**Dead context fields**: Remove or implement `SeasonsEngine`, `ConditionsEngine`, `ObscurantsEngine`. If seasons affect weather transition probabilities, wire SeasonsEngine → WeatherEngine. If not needed, remove the declarations.

**Fragile API access**: Add public methods `CBRNEngine.get_mopp_level(unit_id)` and `SpaceEngine.get_gps_cep()` to replace private attribute access in battle.py.

**Design considerations**:
- Era engines should follow the existing routing pattern: `if era == X: route_to_engine()` with fallback to default path
- Some era engines (Siege, Convoy, Strategic Bombing) are campaign-loop engines, not battle-loop engines — wire into `CampaignManager`, not `BattleManager`
- Space sub-engine delegation should happen inside `SpaceEngine.update()` — verify the parent already calls sub-engines or add delegation
- Dead YAML field wiring should be prioritized: `traverse_deg` + `elevation_deg` (weapon arc constraints) are high value; `unit_cost_factor` (economic cost) is low value for current scope

### Theme 9: Comprehensive Validation & Regression

**Problem**: After 7 phases of changes, all scenarios must be re-validated against historical outcomes. Calibration paths must be exercised. The deficit inventory must reach zero unresolved items. All documentation must be synchronized.

**Solution**: Final validation pass with regression testing.

**Scope**:
- Run ALL 42+ scenarios through the engine and verify correct winner/outcome
- Create test scenarios that exercise every calibration parameter at least once
- Create test scenarios for each untested feature (dig_in, wave_interval, target_selection_mode, victory_weights)
- Verify all 4 SEAD/IADS parameters are consumed in at least one scenario
- Run MC validation (100+ runs) on the 6 scenarios that were historically wrong (Agincourt, Salamis, Trafalgar, Midway, Stalingrad, Golan) to confirm >80% correct winner rate
- Zero-deficit audit: every item in `devlog/index.md` must be either resolved or explicitly marked won't-fix with rationale
- Full cross-doc audit (19 checks)
- Documentation sync: all docs updated to reflect Block 6 changes

---

## What's Explicitly Out of Scope

These items are architectural decisions or accepted simplifications that don't affect simulation fidelity at the current scale:

| Item | Rationale |
|------|-----------|
| Single-threaded simulation | Required for deterministic PRNG replay |
| SGP4/TLE orbital mechanics | Keplerian sufficient for campaign-scale |
| Individual carrier deck spots | Aggregate model sufficient |
| Cooperative jamming | Single-jammer model sufficient |
| Full compartment flooding model | Campaign-scale abstraction sufficient |
| COA nested simulation wargaming | Lanchester analytical adequate |
| Checkpoint format migration (pickle → JSON) | Functional but fragile; architectural rework |
| Real-time map streaming | Post-hoc replay covers the use case |
| 4GW / Unrestricted Warfare / Gerasimov schools | Require information/cyber domain infrastructure |
| Mobile UI optimization | Desktop-first by design |
| Multi-user authentication | Single-user by design |
| Cross-UTM-zone coordinate handling | All current scenarios fit within a single UTM zone |
| Radio frequency deconfliction | No scenarios exercise frequency interference |
| Supply optimization solver (LP/ILP) | Pull-based nearest-depot adequate for current logistics |
| Strategic bombing industrial interdependency graph | Linear regeneration adequate for campaign-scale |
| Trench wire-cutting mechanic | Wire is a query attribute; cutting is a niche WW1 detail |
| Stochastic reinforcement arrivals | Fixed schedule adequate; Poisson arrivals would complicate scenario design |
| Campaign-level EW validation | Component-level EW validation sufficient |

---

## Dependency Graph

```
Theme 1 (Calibration Schema)  ←── independent, do first
    ↓
Theme 3 (Combat Fidelity)     ←── uses new calibration schema for training/posture params
Theme 4 (Environmental)       ←── uses new calibration schema for weather/night params
    ↓
Theme 2 (Naval Combat)        ←── depends on posture system from Theme 3
Theme 5 (C2 & AI)             ←── depends on detection (fog of war) from Theme 3/4
    ↓
Theme 8 (Era & Domain Wiring) ←── depends on battle routing from Theme 2/3, C2 from Theme 5
    ↓
Theme 6 (Resolution & Scenarios) ←── needs all combat changes wired before recalibrating
Theme 7 (Performance & Logistics) ←── independent, can run parallel with Theme 6
    ↓
Theme 9 (Validation)          ←── must be last: validates everything above
```

---

## Proposed Phase Structure

| Phase | Theme(s) | Focus |
|-------|----------|-------|
| 49 | 1 | Calibration Schema Hardening |
| 50 | 3 | Combat Fidelity Polish |
| 51 | 2 | Naval Combat Completeness |
| 52 | 4 | Environmental Continuity |
| 53 | 5 | C2 & AI Completeness |
| 54 | 8 | Era-Specific & Domain Sub-Engine Wiring |
| 55 | 6 | Resolution & Scenario Migration |
| 56 | 7 | Performance & Logistics |
| 57 | 9 | Full Validation & Regression |

Each phase follows the established pattern: implementation → unit tests → scenario evaluation → deficit audit → documentation sync.

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Calibration schema migration breaks scenarios | Defaults match current values; migration script validates before/after |
| Naval engine instantiation introduces new failures | Engines already tested standalone; integration tests verify routing |
| Continuous concealment changes detection balance | Parameterized decay rate; can tune without code changes |
| Fog-of-war assessment makes AI too conservative | Assessment uncertainty bounds; configurable `enable_fog_of_war` flag to fall back to ground truth |
| Resolution switching fix causes infinite tactical loops | Guard: max tactical ticks per battle (existing max_ticks) still applies |
| O(n^2) → STRtree rally changes cascade timing | Spatial index produces same result set as brute force; unit test verifies |
| Era engine wiring introduces regressions in historical scenarios | All era engines have standalone tests; integration tests verify before/after scenario outcomes |
| FogOfWarManager changes AI behavior globally | Gated by `enable_fog_of_war` config; disabled by default for backward compat; enable per scenario |
| 25+ engine wiring changes create merge conflicts | Phases ordered to minimize overlap; each engine wired in a single commit |
| Dead YAML field removal breaks YAML loading | Fields removed only from pydantic models, not YAML files; existing YAML validated with `extra="ignore"` |

---

## Success Criteria

Block 6 is complete when:

1. **Zero unresolved deficits** in `devlog/index.md` (all resolved or explicitly won't-fix)
2. **All 42+ scenarios** produce correct historical winner at >80% MC rate
3. **All calibration parameters** exercised in at least one test scenario
4. **Naval engines wired** — `NavalSubsurfaceEngine`/`NavalSurfaceEngine` methods routed from `_route_naval_engagement()`
5. **No dead calibration data** in any scenario YAML
6. **Calibration schema validated at parse time** (no more silent key drift)
7. **Environmental effects continuous** (night, weather, concealment)
8. **C2 effectiveness computed** from comms state (not hardcoded 1.0)
9. **FogOfWarManager queried** — per-side detection picture maintained and used for AI assessment
10. **All 8 legacy scenarios** loadable through API
11. **Zero dead engines** — all 25+ instantiated-but-never-called engines wired or explicitly removed
12. **All era-specific engines wired** — era scenarios use their specialized engines (cavalry, barrage, siege, etc.)
13. **Space subsystem exercised** — at least 2 scenarios with `space_config` active
14. **Dead YAML fields resolved** — either wired into simulation or removed from models
15. **Cross-doc audit passes** all 19 checks
16. **~8,800+ total tests** passing (Python + frontend)

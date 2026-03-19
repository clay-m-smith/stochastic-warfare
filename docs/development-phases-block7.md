# Stochastic Warfare -- Block 7 Development Phases (58--67)

## Philosophy

Block 7 is the **final engine hardening block**. A comprehensive audit reveals that Blocks 1--6 suffer from a systemic **build-then-defer-wiring** pattern: engines were built and unit-tested in isolation, but their outputs are never consumed by downstream systems. The result is 36 computed-but-unconsumed environmental parameters, 16 unreachable combat engines, 4 dead EngagementType values, an observational-only event bus, discarded damage detail, ungateed logistics, empty checkpoints, and protective postures that protect nothing.

This block wires every orphaned engine, connects every feedback loop, exercises every environmental parameter, and validates every scenario against historical outcomes. A triage framework (P0--P4) prevents scope creep; structural verification tests prevent future regression.

**Exit criterion**:
1. Every instantiated engine either contributes to simulation outcomes or is removed
2. Every computed parameter consumed by at least one downstream system (verified by automated test)
3. Every published event type has at least one functional subscriber (verified by automated test)
4. Every cross-module feedback loop fully wired or explicitly documented as deferred
5. All scenarios still produce correct historical outcomes after integration

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block7.md` (design thinking, triage tables, environmental audit), `devlog/index.md` (deficit inventory), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**Engine changes are wiring, not building**: Block 7 modifies `battle.py`, `engine.py`, `scenario.py`, and `campaign.py` extensively but creates minimal new source files. The work is connecting existing tested systems, not designing new ones.

---

## Phase 58: Structural Verification & Core Combat Wiring ✓

**Status**: Complete — 60 tests, 5 new test files, 6 modified source files.

**Goal**: Create structural verification tests that prevent future regression, then fix all P0 combat integration bugs -- air combat routing, damage detail extraction, posture protection, and logistics gates.

**Dependencies**: Block 6 complete (Phase 57).

**Partial deferrals**: 58c behavioral application (apply_casualties/degrade_equipment in battle loop) and 58e fuel consumption deferred to calibration — both changed battle dynamics without corresponding calibration adjustment, causing evaluator timeout regressions.

### 58a: Structural Verification Tests

Create automated tests that run continuously from this phase forward. These catch regression before it happens.

- **`tests/validation/test_structural_audit.py`** (new) -- 5 structural verification tests:
  1. `test_no_unconsumed_engine_outputs` -- AST-parse all engine classes, verify every public property/method return value has at least one external consumer (allowlist for P4-triaged items: `shadow_azimuth`, solar/lunar decomposition, `deep_channel_depth`)
  2. `test_no_uncalled_public_methods` -- For every public method on engine classes in `stochastic_warfare/`, verify at least one call site outside its own module and tests
  3. `test_all_event_types_have_subscribers` -- AST-parse for `bus.publish(EventType(...))` and `bus.subscribe(EventType, handler)`, verify every published type has a subscriber beyond Recorder (or is in `OBSERVATION_ONLY_EVENTS` allowlist)
  4. `test_all_engagement_types_routed` -- For each `EngagementType` enum value, verify `_infer_engagement_type()` can produce it AND a handler exists that resolves it
  5. `test_feedback_loops_functional` -- Verify: depleted ammo prevents firing, depleted fuel prevents movement, DUG_IN reduces damage, checkpoint round-trips all module state

**Tests** (~10):
- Each structural test + parametrized variants for edge cases
- Initially some tests will fail (expected -- they document the current gaps). Use `xfail` markers that get removed as subsequent substeps fix the gaps.

### 58b: Air Combat Routing

Wire 3 dead EngagementType values to their purpose-built engines. Currently air engagements route through generic `DIRECT_FIRE` with ground combat Pk.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Update `_infer_engagement_type()`:
  - Attacker AIR + target AIR → `AIR_TO_AIR`
  - Attacker AIR + target GROUND/NAVAL → `AIR_TO_GROUND`
  - Attacker GROUND/NAVAL (AD unit) + target AIR → `SAM`
  - Add routing in `_resolve_engagement()` for each new type:
    - `AIR_TO_AIR` → `AirCombatEngine.resolve()` (BVR missile Pk + WVR guns Pk, altitude/energy advantage)
    - `AIR_TO_GROUND` → `AirGroundEngine.resolve()` (CAS/strike Pk with dive angle, CEP, altitude, weather ceiling)
    - `SAM` → `AirDefenseEngine.resolve()` (missile Pk with engagement envelope, track quality, ECM effects)
- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Ensure `AirCombatEngine`, `AirGroundEngine`, `AirDefenseEngine` are available on `SimulationContext` (verify instantiation path).

**Tests** (~12):
- AIR vs AIR engagement routes through AirCombatEngine (not DIRECT_FIRE)
- AIR vs GROUND engagement routes through AirGroundEngine
- GROUND AD vs AIR engagement routes through AirDefenseEngine
- Each engine produces Pk from its own physics model (not generic range-dependent)
- Domain detection: AIR attacker correctly identified from unit domain
- Backward compat: GROUND vs GROUND still routes through DIRECT_FIRE
- Naval domain combinations (AIR vs NAVAL → AIR_TO_GROUND, NAVAL AD vs AIR → SAM)

### 58c: Damage Detail Extraction

Extract all fields from `DamageResult` instead of discarding everything except `damage_fraction`.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- After `DamageEngine.resolve_damage()`:
  - Extract `casualties` → reduce unit `personnel_count` by casualty count. Track KIA/WIA/MIA separately if available.
  - Extract `systems_damaged` → degrade specific equipment on unit. If weapon destroyed, reduce available weapons. If sensor damaged, reduce detection capability.
  - Extract `fire_started` → if True and terrain combustibility > threshold, create fire zone at target position (hook for Phase 60 fire system; initially just log the event)
  - Extract `ammo_cookoff` → if True, apply secondary explosion damage to units within blast radius of target
  - Extract `penetrated` → if True on armored target, reduce armor protection value for subsequent hits (armor degradation)
- **`stochastic_warfare/entities/`** (modified) -- Add `degrade_equipment(system_id)` and `apply_casualties(count)` methods to unit base class if not present.

**Tests** (~12):
- Unit with 100 personnel hit → personnel count reduced by `casualties` count
- Unit with weapon destroyed → available weapons reduced by 1
- Unit with sensor damaged → detection modifier applied
- Ammo cookoff → nearby unit takes secondary damage
- Armor penetration → subsequent hit has reduced armor protection
- fire_started logged (actual fire zone creation deferred to Phase 60)
- Backward compat: damage_fraction threshold still determines DESTROYED/DISABLED status
- Partial degradation: unit at 40% damage has reduced firepower proportional to casualties

### 58d: Posture Damage Reduction

DUG_IN, DEFENSIVE, and FORTIFIED postures provide damage reduction.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Apply posture protection multiplier on incoming `damage_fraction` before threshold comparison:
  - `MOVING`: 1.0 (no reduction)
  - `HALTED`: 1.0 (no reduction)
  - `DEFENSIVE`: 0.8 (20% reduction -- hasty fighting position)
  - `DUG_IN`: 0.5 (50% reduction -- prepared position)
  - `FORTIFIED`: 0.3 (70% reduction -- hardened position)
  - Formula: `effective_damage = damage_fraction × (1 - posture_protection)`
- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add `posture_protection` dict to `CalibrationSchema`:
  - `posture_protection_defensive: float = 0.2`
  - `posture_protection_dug_in: float = 0.5`
  - `posture_protection_fortified: float = 0.7`
  - Per-scenario tunable (e.g., Stalingrad urban rubble = higher DUG_IN protection)

**Tests** (~10):
- DUG_IN unit takes 50% of damage compared to MOVING unit from identical attack
- DEFENSIVE unit takes 80% damage
- FORTIFIED unit takes 30% damage
- MOVING and HALTED take full damage
- Custom posture_protection values from CalibrationSchema override defaults
- Posture protection stacks with terrain cover (multiplicative, not additive)
- Unit transitioning from DUG_IN to MOVING loses protection immediately
- Posture protection applies to all damage types (direct fire, indirect fire, naval, air)

### 58e: Logistics Gates

Prevent combat actions when resources are depleted. Wire fuel consumption to movement.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Before `weapon.fire()`:
  - Check `weapon.current_ammo > 0` (or `weapon.has_ammo()`)
  - If depleted, skip engagement for this weapon, log `AmmoDepletedEvent`
  - Unit with all weapons depleted cannot engage (but can still move, be targeted)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Before movement execution:
  - Check `unit.fuel > 0` (or equivalent resource check)
  - If depleted, skip movement, log `FuelDepletedEvent`
  - Unit with no fuel can still fire (stationary defense) but cannot advance
- **`stochastic_warfare/movement/engine.py`** (modified) -- After computing movement distance:
  - Consume fuel: `fuel_consumed = distance_m × unit.fuel_consumption_rate`
  - Deduct from unit fuel supply
  - If `fuel_consumption_rate` not defined, default to 0 (backward compat -- no fuel tracking for units without the field)
- **Backward compatibility**: Units without explicit fuel/ammo tracking continue to function normally (infinite supply assumed when field is absent or logistics system inactive).

**Tests** (~12):
- Unit with 0 ammo cannot fire (engagement skipped, event logged)
- Unit with 0 fuel cannot move (movement skipped, event logged)
- Movement consumes fuel proportional to distance
- Unit with 0 fuel can still fire (stationary defense)
- Unit with 0 ammo can still move (retreat, maneuver)
- Unit without fuel_consumption_rate field has infinite fuel (backward compat)
- Unit without ammo tracking fires normally (backward compat)
- Ammo resupply (from logistics) restores firing capability
- Fuel resupply (from logistics) restores movement
- Multiple weapons: unit fires remaining weapons when one is depleted

### Exit Criteria
- 5 structural verification tests running (some xfail initially)
- AIR_TO_AIR, AIR_TO_GROUND, SAM routed to correct engines
- DamageResult fields (casualties, systems_damaged, fire_started, ammo_cookoff, penetrated) all extracted
- DUG_IN provides ~50% damage reduction
- Ammo depletion prevents firing; fuel depletion prevents movement
- All existing tests pass (expect some recalibration after air routing change)
- ~60 new tests

---

## Phase 59: Atmospheric & Ground Environment Wiring ✓

**Status**: Complete — 48 tests, 5 new test files, 6 modified source files.

**Goal**: Wire all computed-but-unconsumed atmospheric and ground parameters. Seasons, weather, and terrain fully contribute to movement, detection, and combat.

**Dependencies**: Phase 58 (structural tests running; damage detail extraction provides fire_started hook).

**Partial deferrals**: Ice crossing, vegetation LOS blocking, bridge capacity, ford crossing, road snow degradation — all require pathfinding/data model changes beyond wiring scope.

### 59a: Seasons → Movement & Infrastructure

Wire SeasonsEngine computed values to movement penalties and infrastructure effects.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Query SeasonsEngine during movement phase:
  - `mud_depth` → speed penalty. Wheeled: `max(0.1, 1 - mud_depth/0.3)`. Tracked: `max(0.3, 1 - mud_depth/0.5)`. Infantry: `max(0.4, 1 - mud_depth/0.4)`. Deep mud (>20cm) immobilizes wheeled vehicles entirely.
  - `snow_depth` → speed penalty. All units: `max(0.4, 1 - snow_depth/0.5)`. Ski troops: `max(0.7, 1 - snow_depth/1.0)`.
  - `sea_ice_thickness` → ice crossing. Infantry: >10cm. Light vehicles: >30cm. Heavy vehicles (>40t): >60cm. Model: Gold formula for ice bearing capacity.
  - `vegetation_density` → speed penalty through forest/jungle. Dense vegetation (>0.8): 0.5x speed for vehicles, 0.7x for infantry.
- **`stochastic_warfare/movement/engine.py`** (modified) -- Accept `ground_condition` parameter with mud/snow/ice modifiers from SeasonsEngine.
- **Road/infrastructure effects**: Snow depth > 15cm degrades unpaved road speed bonus by 50%. Frozen water bodies (ice > vehicle weight threshold) become traversable terrain.

**Tests** (~12):
- Wheeled vehicle in deep mud (20cm): speed ≤ 10% of base
- Tracked vehicle in deep mud: speed ≤ 50%
- Infantry in 30cm snow: speed ≤ 60%
- Ice crossing: infantry crosses at >10cm thickness, vehicle at >30cm, MBT at >60cm
- Dry ground (mud_depth=0): no penalty
- No snow: no penalty
- Road with 20cm snow: speed bonus reduced by 50%
- Frozen river traversable when ice > threshold

### 59b: Seasons → Detection & Concealment

Wire vegetation density and height to detection concealment modifiers.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- During detection phase:
  - `vegetation_density` → visual concealment modifier. In forest terrain: `concealment_bonus = vegetation_density × 0.3` (summer foliage hides, winter bare exposes). Modifier reduces visual detection SNR.
  - `vegetation_height` → LOS check. If vegetation_height > 2m and terrain is forest, ground-level LOS blocked for units without elevated sensors. Vehicles may be partially visible above vegetation.
- **`stochastic_warfare/detection/detection.py`** (modified) -- Accept `seasonal_concealment` modifier in detection calculation.

**Tests** (~8):
- Summer forest (vegetation_density=0.9): +27% visual concealment
- Winter forest (vegetation_density=0.2): +6% concealment
- Open terrain: no vegetation concealment regardless of season
- Tall vegetation blocks ground-level LOS for infantry
- Vehicle partially visible above 3m vegetation

### 59c: Weather → Ballistics & Operations

Wire atmospheric parameters to ballistic calculations and operational gates.

- **`stochastic_warfare/combat/ballistics.py`** (modified) -- Use true air density from pressure + temperature + humidity (ideal gas law: ρ = P/(R_specific × T × (1 + 0.608q))) instead of fixed scale-height model. Query WeatherEngine for current conditions.
- **`stochastic_warfare/combat/ballistics.py`** (modified) -- Temperature lapse rate: ISA −6.5°C/km to tropopause (11km), isothermal above. Affects speed of sound at altitude → Mach number → drag coefficient.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Wind gust operational gates:
  - `wind.gust > 15 m/s`: helicopter landing abort
  - `wind.gust > 20 m/s`: parachute drop abort
  - `wind.gust > 25 m/s`: infantry movement halt, bridge-laying abort
- **Propellant temperature** -- MV modifier: `MV × (1 + 0.001 × (ambient_temp - 21))`. Cold propellant (−20°C) → −4% MV; hot (+50°C) → +3% MV. Source: MIL-STD-1474.

**Tests** (~10):
- Air density at sea level standard: matches existing behavior
- Air density at 3000m altitude: ~30% lower than sea level
- Humidity correction: moist air ~0.5% less dense
- Propellant at −20°C: MV reduced ~4%
- Propellant at +50°C: MV increased ~3%
- Helicopter abort at gust > 15 m/s
- Infantry halt at gust > 25 m/s
- Normal operations at low wind

### 59d: Equipment Temperature Stress & Terrain Features

Wire equipment temperature range stress and terrain obstacle/ford/bridge features.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Query `EquipmentManager.environment_stress(temperature)` each tick. Apply degradation factor to weapon reliability (jam probability multiplier) and electronics failure rate.
- **`stochastic_warfare/movement/engine.py`** (modified) -- Wire terrain features:
  - `Obstacle.traversal_risk` → casualty probability when crossing (e.g., wire obstacles: 5% casualty chance per crossing)
  - `Obstacle.traversal_time_multiplier` → movement delay (wire: 3x, rubble: 2x, water: 4x)
  - `Hydrography.ford_points_near()` → river crossing at ford points with depth/current-dependent time cost
  - `Infrastructure.Bridge.capacity_tons` → gate heavy vehicles (MBT >60t cannot cross 20-ton bridge)

**Tests** (~10):
- Equipment at −40°C (outside rated range): jam probability increased
- Equipment at +55°C: electronics failure rate increased
- Equipment within rated range: no degradation
- Wire obstacle: 3x traversal time + casualty chance
- River crossing at ford: time proportional to depth
- 60-ton MBT blocked by 20-ton bridge
- 20-ton APC allowed on 30-ton bridge

### Exit Criteria
- Mud/snow/ice affect movement speed (wheeled vs tracked differentiation)
- Vegetation density modifies detection concealment
- True air density from ideal gas law used in ballistics
- Wind gusts gate helicopter/parachute operations
- Equipment temperature stress affects reliability
- Terrain obstacles, fords, bridges gate movement
- All existing tests pass
- ~50 new tests

---

## Phase 60: Obscurants, Fire, & Visual Environment ✓

**Status**: Complete — 53 tests, 5 new test files, 4 modified source files.

**Goal**: Instantiate and wire ObscurantsEngine. Create fire zone system from Phase 58 damage detail. Wire thermal environment and NVG detection.

**Dependencies**: Phase 59 (vegetation data for fire); Phase 58 (fire_started extraction from DamageResult).

**Partial deferrals**: Fire spread cellular automaton, environment_config scenario YAML, burned zone concealment reduction, fire damage application, road dust suppression, artificial illumination — all require calibration or data model changes beyond wiring scope.

### 60a: ObscurantsEngine Instantiation & Wiring

Instantiate ObscurantsEngine on SimulationContext and call it each tick. Wire smoke/dust/fog to detection and combat.

- **`stochastic_warfare/simulation/scenario.py`** (modified) -- Instantiate `ObscurantsEngine` on `SimulationContext`. Always present (produces zero opacity when no obscurants deployed).
- **`stochastic_warfare/simulation/engine.py`** (modified) -- Call `obscurants_engine.update(dt, wind)` each tick.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- After artillery/mortar impact, spawn smoke cloud at impact site via `obscurants_engine.deploy_smoke(center, radius)`.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- During detection: query `obscurants_engine.opacity_at(target_pos)` → reduce visual SNR by `visual_opacity`, thermal SNR by `thermal_opacity`. Radar unaffected by standard smoke.
- **`stochastic_warfare/simulation/battle.py`** (modified) -- During engagement: query opacity between attacker and target. Reduce Pk for visual/thermal-guided weapons proportionally.
- **Fog auto-generation**: When WeatherEngine transitions to FOG state, deploy fog patches via ObscurantsEngine. Fog coverage area based on terrain (valley fog, sea fog).

**Tests** (~12):
- ObscurantsEngine instantiated on SimulationContext
- Smoke cloud deployed at artillery impact site
- Smoke drifts with wind (center moves)
- Smoke disperses over time (radius grows as √t)
- Smoke decays (30min half-life)
- Visual detection through smoke: reduced by visual_opacity
- Thermal detection through standard smoke: minimally affected (opacity 0.1)
- Thermal detection through multispectral smoke: significantly reduced (opacity 0.8)
- Radar detection through smoke: unaffected
- Combat Pk reduction through smoke for visual/thermal weapons
- FOG weather triggers fog patch deployment
- No smoke/fog: zero opacity (backward compat)

### 60b: Dust & Fire Zones

Create dust from vehicle movement and fire zones from damage/incendiary effects.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- After movement:
  - If terrain is DRY + non-road + vehicle unit: spawn dust trail via obscurants engine. Dust intensity ∝ speed × vehicle_count. Dust reveals movement (signature enhancement for detection) + degrades LOS for following units.
- **Fire zone system** -- Wire `IncendiaryDamageEngine`:
  - `DamageResult.fire_started` (Phase 58) triggers fire zone creation if terrain `combustibility > 0.3`
  - Fire zones: persistent obstacle that blocks movement, produces smoke (feeds ObscurantsEngine), deals damage to units inside
  - Fire decay: fuel (vegetation) exhaustion reduces fire intensity. Fire-out when fuel depleted.
  - Fire spread (medium model): cellular automaton with wind bias. Spread rate ∝ wind_speed × vegetation_density × (1 − vegetation_moisture). Fire won't spread to wet vegetation (moisture > 0.7).
- **`stochastic_warfare/terrain/classification.py`** (modified) -- Wire `combustibility` field to fire zone ignition probability.

**Tests** (~10):
- Vehicle on dry terrain at speed: dust trail spawned
- Vehicle on road: no dust
- Vehicle on wet terrain: no dust
- Fire zone from fire_started=True on combustible terrain
- Fire zone blocks movement
- Fire zone produces smoke
- Fire spreads downwind to adjacent vegetated cells
- Fire doesn't spread to wet vegetation
- Fire decays when fuel exhausted
- IncendiaryDamageEngine creates fire zone from incendiary weapon impact

### 60c: Thermal Environment & NVG Detection

Wire physics-based thermal detection and NVG night detection recovery.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Replace illumination-based thermal modifier with ΔT model:
  - Query `TimeOfDayEngine.thermal_environment()` for `background_temperature`
  - Thermal detection SNR ∝ `|target_thermal_signature − background_temperature|`
  - At thermal crossover (dawn/dusk, `crossover_in_hours < 0.5`): thermal detection collapses (ΔT → 0 for stationary vehicles)
  - Running engines maintain thermal signature above background (vehicles detectable even at crossover if engine running)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- NVG detection:
  - Query `TimeOfDayEngine.nvg_effectiveness()` during night detection
  - NVG-equipped units recover visual detection modifier from ~0.2 (unaided night) to ~0.6 (NVG-aided)
  - Currently only affects movement speed (0.7x night recovery) — extend to detection range
- **Scenario YAML**: Add `environment_config` support for pre-placed smoke/fog zones and season/ground state overrides.

**Tests** (~10):
- Thermal detection at night: high ΔT → good detection
- Thermal detection at dawn crossover: low ΔT → poor detection
- Thermal detection of running vehicle at crossover: engine heat maintains ΔT
- NVG-equipped unit at night: detection range ~60% of daylight (not ~20%)
- NVG-unequipped unit at night: detection range ~20% of daylight (unchanged)
- Artificial illumination (flare): temporarily raises lux in area
- Pre-placed fog from scenario YAML loads correctly
- Season override from scenario YAML applied

### Exit Criteria
- ObscurantsEngine instantiated, updated each tick, opacity consumed by detection and combat
- Smoke from artillery, dust from movement, fog from weather
- Fire zones from incendiary/damage with wind-driven spread
- Thermal detection uses physics ΔT model with crossover vulnerability
- NVG extends night detection (not just movement)
- Scenario YAML supports environment_config
- ~50 new tests

---

## Phase 61: Maritime, Acoustic, & EM Environment — COMPLETE

**Goal**: Wire all maritime, underwater acoustic, and electromagnetic propagation parameters. Wire CarrierOpsEngine. Wire rain detection factor.

**Result**: 71 tests, 6 modified source files, 5 test files. Sea state ops (Beaufort penalty, tidal current, wave resonance, swell roll), acoustic layers (thermocline, surface duct, CZ), EM propagation (radar horizon, ducting, HF quality, radio horizon, DEW atmosphere). CarrierOpsEngine instantiated (structural only). EMEnvironment populates conditions_engine. All effects gated by enable_*=False.

**Dependencies**: Phase 60 (obscurants system for sea spray interaction).

### 61a: Sea State → Ship Operations

Wire Beaufort scale and wave parameters to ship movement, carrier ops, and small craft.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Sea state operational effects:
  - Beaufort > 3: small craft speed −20% per Beaufort above 3
  - Beaufort > 5: landing craft operations dangerous (10% casualty risk per crossing)
  - Beaufort > 6: helicopter deck landing abort
  - Beaufort > 7: carrier flight ops suspended
- **`stochastic_warfare/movement/engine.py`** (modified) -- Ship movement:
  - `tidal_current_speed/direction` → ship speed adjustment (add/subtract current vector component along course)
  - `wave_period` → if period matches hull natural frequency (±10%), roll amplitude doubles → gunnery dispersion ×1.5
  - Swell direction: `roll_factor = sin²(wave_dir − ship_heading)`. Beam seas maximum roll; following seas minimum.
- **CarrierOpsEngine wiring (P1)**:
  - Register carrier aircraft with ATOPlanningEngine (aircraft availability tracking)
  - Sortie turnaround time enforcement between missions
  - CAP station management: aircraft rotate on/off station based on fuel

**Tests** (~12):
- Small craft speed reduced at Beaufort > 3
- Landing craft casualties at Beaufort > 5
- Helicopter deck landing abort at Beaufort > 6
- Carrier flight ops suspended at Beaufort > 7
- Ship speed adjusted by tidal current (favorable +, adverse −)
- Wave period resonance: gunnery dispersion increased at matching period
- Beam seas: maximum roll factor
- Following seas: minimum roll factor
- CarrierOpsEngine manages aircraft sortie turnaround
- Calm seas: no penalties (backward compat)

### 61b: Acoustic Wiring

Wire computed underwater acoustic parameters to sonar detection.

- **`stochastic_warfare/detection/detection.py`** (modified) -- Sonar detection modifiers:
  - `thermocline_depth`: if target depth > thermocline, add +20 dB transmission loss. Submarine below thermocline very hard to detect from surface sonar.
  - `surface_duct_depth`: if both source and target within surface duct, enhanced detection (+10 dB gain). If target below duct, degraded detection (+15 dB loss).
  - `convergence_zone_ranges`: detection probability spikes at 55km intervals from sonar source. Between CZ ranges, target is in acoustic shadow (detection probability drops to near-zero for passive sonar).
- **`stochastic_warfare/environment/underwater_acoustics.py`** (modified) -- Expose `get_layer_effects(source_depth, target_depth)` API returning layer loss/gain.

**Tests** (~10):
- Submarine below thermocline: detection difficulty increased (+20 dB loss)
- Submarine above thermocline: normal detection
- Both in surface duct: enhanced detection
- Target at convergence zone range (55km): spike in detection probability
- Target between CZ ranges: acoustic shadow, poor detection
- Shallow water (no thermocline): no layer effects

### 61c: EM Propagation Wiring

Wire radar horizon, ducting, atmospheric attenuation, HF propagation, and rain detection factor.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Radar horizon gate:
  - Before radar detection: compute `radar_horizon(antenna_height)` using 4/3 Earth model
  - If target range > radar horizon AND target altitude < horizon altitude at that range, detection blocked
  - Low-flying aircraft below radar horizon invisible to ground radar
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Wire `_compute_rain_detection_factor()`:
  - Already implemented with ITU-R P.838 model — just needs call site
  - Reduce radar detection probability in rain. Heavy rain (25 mm/hr) significantly degrades detection.
- **`stochastic_warfare/c2/communications/`** (modified) -- EM propagation → comms:
  - `hf_propagation_quality()` → HF radio reliability modifier (day: D-layer absorbs → short range; night: F-layer reflects → skip propagation)
  - `atmospheric_attenuation(freq, range, rain_rate)` → comms signal loss for high-frequency systems
  - Radio horizon: same 4/3 Earth model for comms range. Higher antenna = longer radio range.
  - EM ducting: if `ducting_possible`, multiply radar/comms range by duct extension factor (capped at 3×)
- **DEW environment wiring**: Pass `humidity`, `precip_rate` from WeatherEngine to DEW engine at call site in battle.py. DEW already accepts these parameters but battle loop never passes them.

**Tests** (~14):
- Ground radar at 10m height: horizon ~13km
- Low-flying target below horizon: undetected by ground radar
- Target above horizon: detected normally
- Rain detection factor: heavy rain degrades radar detection
- Clear weather: no rain penalty
- HF comms at night: extended range (F-layer reflection)
- HF comms at day: reduced range (D-layer absorption)
- Atmospheric attenuation at X-band in rain: measurable loss
- Radio horizon: aircraft at 10km altitude has long comms range
- EM ducting in warm/humid: radar range extended
- DEW in humid conditions: reduced transmittance
- DEW in rain: further reduced
- DEW in clear/dry: normal transmittance (backward compat)

### Exit Criteria
- Sea state affects ship movement, carrier ops, small craft, gunnery
- Tidal current modifies ship speed
- Underwater acoustic layers (thermocline, surface duct, CZ) affect sonar detection
- Radar horizon gates air defense detection
- Rain detection factor wired (existing ITU-R P.838 implementation)
- HF propagation quality modulates comms reliability
- DEW receives environmental parameters
- CarrierOpsEngine manages sortie turnaround
- ~55 new tests

---

## Phase 62: Human Factors, CBRN, & Air Combat Environment ✓

**Status**: Complete — 85 tests, 6 new test files, 5 modified source files.

**Goal**: Environmental effects on personnel, CBRN-environment interaction, and air domain environmental coupling.

**Dependencies**: Phase 61 (EM propagation for air combat BVR); Phase 59 (temperature data for human factors).

### 62a: Heat & Cold Casualties

Continuous exposure models for environmental casualties.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Per-tick environmental casualty check:
  - **Heat stress**: WBGT = 0.7×T_wet + 0.2×T_globe + 0.1×T_dry (simplified: 0.7×humidity_factor × temperature). If WBGT > 32°C, heat casualty rate = `base_rate × (WBGT − 28)/10 × mopp_multiplier × exertion_level`. MOPP-4 in hot weather: 10-20% casualties per hour.
  - **Cold injury**: Wind chill = 13.12 + 0.6215T − 11.37V^0.16 + 0.3965TV^0.16. If wind_chill < −25°C, cold casualty rate = `base_rate × (|wind_chill| − 20)/20 × exposure_time_factor`.
  - Casualties are non-combat (reduce unit strength, don't trigger morale effects).
- **Opt-in**: Gated by `enable_environmental_casualties: true` in scenario YAML. Default off for backward compat.
- **`stochastic_warfare/simulation/calibration.py`** (modified) -- Add heat/cold casualty rate parameters.

**Tests** (~8):
- WBGT > 32°C: heat casualties accumulate
- WBGT < 28°C: no heat casualties
- MOPP-4 multiplies heat casualty rate
- Wind chill < −25°C: cold casualties accumulate
- Wind chill > −20°C: no cold casualties
- Environmental casualties disabled by default (backward compat)
- Environmental casualties enabled via scenario config

### 62b: MOPP Degradation & Altitude

Expand MOPP beyond speed penalty. Add altitude sickness.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- MOPP effects beyond speed:
  - MOPP-4: FOV reduction → visual detection modifier ×0.7
  - MOPP-4: dexterity → reload time ×1.5 (reduces fire rate)
  - MOPP-4: voice clarity → comms quality ×0.5
  - MOPP-2: half the penalties of MOPP-4
- **Altitude sickness**: Above 2500m, performance degrades:
  - `performance_modifier = max(0.5, 1 − 0.03 × (altitude − 2500)/100)`
  - Affects: movement speed, reload time, accuracy
  - Acclimatized units (config flag) have reduced penalty
- **Environmental fatigue**: Temperature/altitude stress accelerates fatigue accumulation rate.

**Tests** (~8):
- MOPP-4: detection range reduced by 30%
- MOPP-4: fire rate reduced (1.5x reload)
- MOPP-4: comms quality halved
- MOPP-2: half penalties
- MOPP-0: no penalties
- Altitude 3000m: performance at ~85%
- Altitude 4500m: performance at ~50%
- Sea level: no altitude penalty

### 62c: CBRN-Environment Interaction

Wire weather effects on CBRN agent behavior.

- **`stochastic_warfare/cbrn/dispersal.py`** (modified) -- Environmental interactions:
  - **Rain washout**: `concentration × exp(−washout_coeff × rain_rate × dt)`. Washout coefficient ~10⁻⁴ per mm/hr. 30 mm/hr rain removes ~30% of agent in 30 minutes.
  - **Temperature persistence**: Arrhenius kinetics: `decay_rate × exp(−Ea/(R×T))`. Nerve agent half-life: 2hr at 40°C, 8hr at 20°C, 24+hr at 0°C.
  - **Inversion trapping**: If temperature increases with altitude (inversion detected from WeatherEngine), multiply ground-level concentration by trapping_factor (5-10×). Critical for valley/urban releases at night.
  - **UV degradation**: If is_day AND cloud_cover < 0.5, add solar degradation rate to agent decay. Daylight breaks down many chemical agents.

**Tests** (~8):
- Agent in heavy rain: concentration drops ~30% in 30 min
- Agent in dry conditions: no washout
- Agent at 40°C: half-life ~2 hours
- Agent at 0°C: half-life 24+ hours
- Temperature inversion: concentration multiplied by trapping factor
- No inversion: normal dispersal
- UV degradation in clear daytime: accelerated decay
- UV degradation at night/cloudy: no solar effect

### 62d: Air Combat Environmental Coupling

Wire environmental effects to air domain combat.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Air combat environment:
  - **Cloud ceiling gate**: CAS/dive bombing requires `cloud_ceiling > min_attack_altitude`. Below ceiling, visual weapon delivery blocked; PGM/radar-guided still possible.
  - **Icing penalties**: If `icing_risk > 0.5`: wing ice (+15% stall speed → reduced maneuver envelope), engine ice (−10% power), radar dome ice (−3 dB detection signal).
  - **Density altitude**: Thrust/lift reduced at high density altitude. `performance_factor = ρ/ρ₀` for thrust-dependent parameters. Hot+high = reduced climb, longer takeoff.
  - **Wind → BVR range**: `effective_range = base_range × (1 ± wind_component/missile_speed)`. Headwind reduces, tailwind extends missile reach (~10-15% effect).
  - **Altitude energy advantage**: `energy_state = altitude × g + 0.5 × v²`. Higher aircraft has energy_advantage_modifier in engagement (converts potential → kinetic in dive).

**Tests** (~10):
- Cloud ceiling below attack altitude: CAS visual delivery blocked
- Cloud ceiling above: CAS proceeds normally
- PGM delivery below ceiling: still works (not visual-dependent)
- Icing risk > 0.5: performance penalties applied
- No icing: no penalties
- Hot+high density altitude: reduced aircraft performance
- Headwind reduces BVR missile range
- Tailwind extends BVR missile range
- Higher aircraft has energy advantage in engagement
- Same altitude: no energy advantage

### Exit Criteria
- Heat/cold casualties accumulate (opt-in)
- MOPP degrades detection, fire rate, comms (not just speed)
- Altitude sickness above 2500m
- CBRN agents affected by rain washout, temperature persistence, inversion trapping, UV degradation
- Air combat: cloud ceiling, icing, density altitude, wind BVR, energy advantage all wired
- All existing tests pass
- ~45 new tests

---

## Phase 63: Cross-Module Feedback Loops ✓

**Goal**: Wire all P1 cross-module integration gaps -- the feedback loops where one system's output should drive another system's behavior. This phase closes the systemic build-then-defer-wiring pattern.

**Dependencies**: Phase 62 (MOPP comms degradation feeds comms→C2); Phase 58 (damage detail for medical feed).

### 63a: Detection → AI Assessment

Replace ground-truth enemy count in AI with FOW-based detected contacts.

- **`stochastic_warfare/c2/ai/assessment.py`** (modified) -- When `enable_fog_of_war` is True:
  - Read `fow_manager.get_contacts(side)` instead of raw enemy unit list
  - Use detected count (not true count) for force ratio assessment
  - Use estimated strength (with confidence level) for threat evaluation
  - Assessment quality degrades with sensor gaps: fewer detected contacts → underestimate enemy
  - When FOW disabled: behavior unchanged (raw count, backward compat)
- **Enable FOW in modern scenarios**: Set `enable_fog_of_war: true` in calibration for modern scenarios where detection system is exercised (Taiwan, Korea, Suwalki, Gulf War EW).

**Tests** (~8):
- FOW enabled: AI sees detected contacts only (not all enemies)
- FOW enabled + poor sensors: AI underestimates enemy strength
- FOW enabled + good sensors: AI assessment close to ground truth
- FOW disabled: AI sees all enemies (backward compat)
- Detection confidence feeds assessment confidence
- Undetected enemy unit surprises AI assessment

### 63b: Medical → Strength & Maintenance → Readiness

Wire event consumption for medical return-to-duty and equipment maintenance.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Subscribe to events:
  - `ReturnToDutyEvent` → increment unit personnel count (capped at original strength)
  - `CasualtyTreatedEvent` → track treatment pipeline progress
  - `EquipmentBreakdownEvent` → reduce unit weapon/sensor count
  - `MaintenanceCompletedEvent` → restore equipment capability
- **Unit degradation**: Units with >30% equipment broken marked DEGRADED status:
  - Pk reduced proportionally to equipment loss
  - Movement speed reduced 20%
  - Detection capability reduced proportionally to sensor loss

**Tests** (~10):
- RTD event: unit personnel count increases (capped at original)
- Multiple RTD events: count doesn't exceed original strength
- Equipment breakdown: unit weapon count reduced
- Maintenance completed: weapon count restored
- Unit with >30% equipment broken: DEGRADED status applied
- DEGRADED unit: reduced Pk
- DEGRADED unit: reduced movement
- All equipment restored: DEGRADED status cleared
- Medical capacity (M/M/c queue): high casualty volume exceeds treatment capacity

### 63c: Checkpoint State Registration

Register all stateful modules with CheckpointManager so checkpoints actually save module state.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- At simulation initialization, register state providers:
  - `CheckpointManager.register(ModuleId.MORALE, morale_engine.get_state)`
  - `CheckpointManager.register(ModuleId.DETECTION, detection_engine.get_state)`
  - `CheckpointManager.register(ModuleId.LOGISTICS, supply_engine.get_state)` (if present)
  - `CheckpointManager.register(ModuleId.COMBAT, battle_manager.get_state)` (if stateful)
  - `CheckpointManager.register(ModuleId.ENVIRONMENT, weather_engine.get_state)` (weather state)
  - `CheckpointManager.register(ModuleId.C2, ooda_engine.get_state)` (OODA phase per unit)
  - Additional modules as applicable (escalation, etc.)
- **Round-trip verification**: Save → restore → continue produces identical next-tick outcomes compared to uninterrupted run.

**Tests** (~8):
- Checkpoint includes morale state (not just clock/RNG)
- Checkpoint includes detection tracks
- Checkpoint includes weather state
- Checkpoint includes OODA phase
- Round-trip: restored sim produces identical next 10 ticks
- Legacy checkpoints (clock+RNG only) still load (backward compat via JSON fallback)

### 63d: MISSILE Routing & Comms → C2

Wire MISSILE engagement type and comms-loss behavior.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- MISSILE routing:
  - Update `_infer_engagement_type()`: guided missile weapons (ATGM, cruise missile, HARM) → `MISSILE` type
  - Route `MISSILE` → `MissileEngine.resolve()` (flight phase + terminal guidance)
  - Wire `MissileDefenseEngine` → intercept attempt on missile detection
  - Missile flight time creates engagement delay (realistic time-of-flight vs instant DIRECT_FIRE)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Comms → C2:
  - Query comms engine for link quality to unit's commander
  - If quality < `c2_min_effectiveness`: unit reverts to last received orders
  - No new targeting assignments, no posture changes, no disengagement
  - Comms degradation probability feeds into Phase 64 order propagation

**Tests** (~10):
- Guided missile routes through MissileEngine (not DIRECT_FIRE)
- Missile flight time creates delay between launch and impact
- Missile defense intercept attempt on detected missile
- Non-guided weapon still routes as DIRECT_FIRE
- Comms loss: unit fights with last orders (no new targets)
- Comms restored: unit receives new orders
- Comms degraded: intermittent order updates
- c2_min_effectiveness threshold configurable via CalibrationSchema

### Exit Criteria
- AI uses FOW contacts (not ground truth) when FOW enabled
- RTD events restore unit strength
- Equipment breakdown degrades unit capability
- Checkpoint saves all module state (morale, detection, weather, OODA)
- MISSILE type routed to MissileEngine with flight delay
- Comms loss forces units to last received orders
- ~45 new tests

---

## Phase 64: C2 Friction & Command Delay

**Status**: Complete — 60 tests, 6 test files, 4 modified source files.

**Goal**: Wire the three dormant C2 engines to create realistic command friction.

**Dependencies**: Phase 63 (comms → C2 degradation provides comms check for order propagation).

### 64a: Order Propagation & Planning Process

Wire OrderPropagationEngine and PlanningProcessEngine into the OODA cycle.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- OODA cycle integration:
  - When AI commander issues orders (DECIDE phase): route through `OrderPropagationEngine` instead of instant execution
  - Order delay: `base_time(echelon) × type_mult × priority_mult × staff_mult + lognormal_noise`
  - Delayed orders enter queue with scheduled delivery time
  - On delivery: roll for misinterpretation (probability based on staff quality × comms quality)
  - If comms down (Phase 63 check): order fails entirely
- **`stochastic_warfare/simulation/engine.py`** (modified) -- Planning process:
  - When OODA cycle reaches DECIDE: check if planning process underway
  - If not, initiate planning with duration based on echelon and method (INTUITIVE fast, MDMP thorough)
  - Commander cannot issue new orders until planning completes
  - Higher-quality planning (MDMP) produces better COA evaluation scores
- **Opt-in**: Gated by `enable_c2_friction: true` in scenario YAML. Default off.

**Tests** (~12):
- Order delay: platoon-level order arrives in ~5 min; division-level in ~2 hr
- FRAGO (0.33× base time) faster than OPORD (1.0×)
- FLASH priority (0.1×) faster than ROUTINE (1.0×)
- Misinterpretation: order parameters modified when misunderstood
- Comms down: order not delivered
- Planning delay: INTUITIVE (minutes) vs MDMP (hours)
- Commander blocked during planning: no new orders until complete
- C2 friction disabled: instant orders (backward compat)

### 64b: ATO Management & Stratagem Activation

Wire ATOPlanningEngine for air operations and StratagemEngine for combat effects.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- ATO wiring:
  - Register all aerial units with ATOPlanningEngine at scenario start
  - CAS requests from ground commanders route through ATO queue
  - Air missions allocated from available aircraft pool (not unlimited)
  - Turnaround time enforced between sorties
  - ATO published periodically (default 12hr in modern era)
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Stratagem activation:
  - When `evaluate_*_opportunity()` passes eligibility, call `activate_stratagem()`
  - CONCENTRATION: +8% force effectiveness at Schwerpunkt
  - DECEPTION: enemy AI receives false force disposition
  - FEINT: enemy commits reserves to feint axis
  - SURPRISE: first-engagement bonus (no prepared positions)
  - Effects modulate combat modifiers for stratagem duration

**Tests** (~12):
- CAS request queued via ATO
- Aircraft sortie count limits enforced
- Turnaround time prevents immediate re-sortie
- All aircraft allocated: CAS request queued, not immediately served
- Stratagem CONCENTRATION: Pk modifier applied at designated point
- Stratagem DECEPTION: AI assessment receives modified force count
- Stratagem activation logged via event
- Stratagem duration expires: modifier removed
- Environmental coupling: HF quality affects order propagation

### Exit Criteria
- Orders take time (echelon-scaled delay)
- Misinterpretation probability from staff × comms quality
- Planning delays (INTUITIVE vs MDMP) block new orders
- ATO limits air sorties (finite aircraft pool)
- Stratagems produce combat modifiers
- All C2 friction opt-in (default off)
- ~40 new tests

---

## Phase 65: Space & EW Sub-Engine Activation

**Goal**: Wire the five dormant space engines and two dormant EW engines.

**Dependencies**: Phase 63 (FOW manager for ISR/SIGINT feed); Phase 64 (C2 system for early warning cueing).

### 65a: Space ISR & Early Warning

Wire satellite intelligence and ballistic missile detection.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- Space ISR:
  - Call `SpaceISREngine.check_overpass()` each tick
  - On overpass: generate ISR report feeding FogOfWarManager (reveal enemy formations)
  - Cloud cover from WeatherEngine gates optical satellites (SAR unaffected)
- **`stochastic_warfare/simulation/engine.py`** (modified) -- Early warning:
  - When ballistic missile fired: check `EarlyWarningEngine.detect_launch()`
  - 30-90s detection delay based on satellite coverage
  - On detection: publish warning event for air defense interceptors

**Tests** (~10):
- Satellite overpass: enemy formations revealed to FOW
- No satellite: no ISR reports
- Cloud cover blocks optical satellite (SAR still works)
- Ballistic missile launch detected by early warning satellite
- Warning published to air defense system
- Detection delay realistic (30-90s)

### 65b: ASAT & SIGINT

Wire anti-satellite warfare and signals intelligence.

- **`stochastic_warfare/simulation/engine.py`** (modified) -- ASAT:
  - Route ASAT engagements through `ASATEngine`
  - Destroyed satellite removed from ConstellationManager
  - GPS, ISR, SATCOM, early warning degraded by satellite loss
  - Debris cascade (Kessler) can deny orbital bands to both sides
- **`stochastic_warfare/simulation/engine.py`** (modified) -- SIGINT:
  - Call `SIGINTEngine.attempt_intercept()` when enemy units emit (radar on, comms transmission)
  - Successful intercept: geolocation report to FogOfWarManager
  - Traffic analysis: comms surge → enemy massing forces detection

**Tests** (~10):
- ASAT destroys satellite: GPS accuracy degrades for that side
- ASAT destroys ISR satellite: ISR reports stop
- Debris cascade: multiple satellites lost to Kessler effect
- SIGINT intercepts active radar emission: geolocation report generated
- SIGINT intercepts comms: traffic analysis detects force concentration
- SIGINT with jammed receiver: intercept fails

### 65c: ECCM

Wire electronic protection to EW jamming calculations.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- ECCM integration:
  - When EW jamming computed: query `ECCMEngine` for target's ECCM suite
  - Subtract ECCM J/S reduction from jammer effectiveness
  - 4 ECCM techniques: frequency hop, spread spectrum, sidelobe blanking, adaptive nulling
  - Units with advanced ECCM resist jamming better (NATO ECCM vs Soviet-era)
- **`stochastic_warfare/ew/eccm.py`** (modified) -- Expose `get_eccm_reduction(target_unit)` returning J/S reduction in dB.

**Tests** (~8):
- Unit with ECCM: jammer effectiveness reduced
- Unit without ECCM: full jamming effect
- Frequency hopping: partial protection against barrage jammer
- Adaptive nulling: high protection against directional jammer
- ECCM stacking: multiple techniques combine
- Backward compat: no ECCM suite = full jamming (existing behavior)

### Exit Criteria
- SpaceISREngine provides satellite intelligence to FOW
- EarlyWarningEngine detects ballistic missile launches
- ASATEngine enables anti-satellite warfare with debris cascade
- SIGINTEngine detects enemy emissions and geolocates
- ECCMEngine reduces jamming effectiveness for equipped units
- ~40 new tests

### Status: COMPLETE

43 tests across 5 test files. 6 modified source files, zero new source files. 2 latent bugs fixed (`_fuse_sigint()` dead since Phase 52d). 1 CalibrationSchema field (`enable_space_effects`). 8 deferrals (D1-D8: traffic analysis, BMD cueing, ASAT routing/data, nulling direction, ISR→FOW injection, collector auto-registration, decoy deployment).

---

## Phase 66: Unconventional, Naval, & Cleanup

**Goal**: Wire remaining dormant engines, wire P2 engines if schedule permits, clean up dead code.

**Dependencies**: Phase 65 (all major systems wired; this phase handles remaining items).

### 66a: Unconventional Warfare & Mine Warfare

Wire IED, guerrilla tactics, and mine laying/sweeping.

- **`stochastic_warfare/simulation/battle.py`** (modified) -- Unconventional routing:
  - Route INSURGENT/MILITIA unit engagements through `UnconventionalWarfareEngine`
  - IED encounters triggered by movement through insurgent-controlled areas
  - Guerrilla hit-and-run: attack then disengage before response
  - Human shield: reduce Pk when civilian population present
- **`stochastic_warfare/simulation/battle.py`** (modified) -- Mine warfare completion:
  - `lay_mines()` callable by naval units with mine-laying capability
  - Minefield persistence as hazard zones
  - Mine sweeping by minesweeper units
  - Scenario YAML: `environment_config.minefields` for pre-placed minefields

**Tests** (~10):
- INSURGENT unit engagement routes through UnconventionalWarfareEngine
- IED encounter during movement through insurgent area
- Guerrilla: attack + disengage before response
- Human shield: Pk reduced when civilian present
- Mine laying creates hazard zone
- Ship entering minefield: mine encounter check
- Minesweeper clears mines
- Pre-placed minefield from scenario YAML

### 66b: P2 Engines & Cleanup

Wire SiegeEngine, AmphibiousAssaultEngine (if schedule permits). Clean up dead code.

- **SiegeEngine → campaign loop** (P2): If time permits, wire ancient/medieval siege state machine to campaign manager for siege scenarios. Daily resolution (assault, starve, undermine, negotiate).
- **AmphibiousAssaultEngine → naval ops** (P2): Beach assault state machine with sea state interaction. If time deferred.
- **ConditionsEngine**: Instantiate as optional convenience facade. New wiring can use aggregated queries.
- **Dead YAML fields**: Wire `propulsion` → drag model (rocket/turbojet/ramjet propulsion types). Wire `data_link_range` → C2 range gate for UAVs.
- **P4 dead code removal**: Remove `shadow_azimuth` computation, solar/lunar contribution decomposition, `deep_channel_depth`. Add to P4 allowlist in structural tests.
- **SimulationContext stubs**: Remove TODO comments for engines that are now instantiated.

**Tests** (~8):
- SiegeEngine: daily assault/starve tick (if wired)
- Propulsion type affects missile drag model
- Data link range gates UAV C2
- P4 removed code: structural audit allowlist updated
- ConditionsEngine aggregated query returns correct values

### Exit Criteria
- UnconventionalWarfareEngine wired (IED, guerrilla, human shields)
- MineWarfareEngine complete (lay, encounter, sweep)
- Dead code removed or wired
- SimulationContext stubs cleaned
- ~30 new tests

---

## Phase 67: Integration Validation & Recalibration

**Goal**: Validate all scenarios still produce correct outcomes with all new systems active. Run structural verification tests to confirm zero remaining integration gaps. This is the final hardening pass for Block 7.

**Dependencies**: All previous Block 7 phases (58-66).

### 67a: Full Scenario Evaluation

Run all scenarios with all new systems active and recalibrate.

- **Full evaluation**: `uv run python scripts/evaluate_scenarios.py --output scripts/evaluation_results_block7.json`
- **Recalibration**: Expect significant recalibration needed. Air combat routing (Phase 58), posture protection (Phase 58), logistics gates (Phase 58), and environmental effects (Phases 59-62) all change outcomes. Primary calibration levers:
  - `force_ratio_modifier` (Dupuy CEV) per side
  - `hit_probability_modifier` per scenario
  - `posture_protection_*` values per scenario
  - `morale_degrade_rate_modifier` per scenario
- **MC validation**: 80% threshold with N=10 seeds (same as Phase 57)

**Tests** (~15):
- All 37 scenarios complete without error
- MC accuracy ≥ 80% at N=10 seeds
- Victory condition tests: 13 decisive scenarios resolve via force_destroyed or morale_collapsed (not time_expired)
- All scenario YAMLs load without ValidationError

### 67b: Structural Verification Pass

Run all 5 structural verification tests (Phase 58) and confirm zero remaining gaps.

- **Unconsumed parameter audit**: Zero unconsumed parameters (beyond P4 allowlist)
- **Dead method audit**: Zero uncalled public engine methods (beyond test-only methods)
- **Event subscription audit**: All published event types have functional subscribers (or observation-only allowlist)
- **Engagement routing**: All EngagementType values routable and handled
- **Feedback loops**: Ammo→fire, fuel→move, posture→damage, checkpoint→state all functional
- **CalibrationSchema exercised fields**: 16 never-set fields either exercised in scenarios or formally deferred with rationale

**Tests** (~10):
- All 5 structural tests pass (no xfail remaining)
- CalibrationSchema field coverage audit
- All scenarios include all new optional configs with correct defaults

### 67c: Documentation & Postmortem

Synchronize all documentation. Block 7 postmortem.

- **`docs/devlog/phase-{58..67}.md`** -- Phase devlogs
- **`docs/devlog/index.md`** -- Phase entries + any new deficit dispositions
- **`CLAUDE.md`** -- Status, test counts, Block 7 complete
- **`README.md`** -- Badges, body text
- **`docs/index.md`** -- Badges
- **`docs/development-phases-block7.md`** -- Phase statuses
- **`MEMORY.md`** -- Status, lessons
- **`mkdocs.yml`** -- Nav entries for devlogs
- **Cross-doc audit**: All 19 checks pass
- **Block 7 postmortem**: `/postmortem`

**Tests** (~5):
- Cross-doc audit validation tests

### Exit Criteria
- All scenarios produce correct historical outcomes with all new systems active
- MC validation at 80% threshold passes
- All 5 structural verification tests pass (zero xfail)
- Zero unconsumed parameters, zero dead methods, all events subscribed
- All feedback loops verified
- All documentation synchronized
- Block 7 postmortem complete
- ~40 new tests

---

## Phase Summary

| Phase | Focus | Tests | Cumulative | Status |
|-------|-------|-------|------------|--------|
| 58 | Structural Verification & Core Combat Wiring | ~60 | ~8,443 | Planned |
| 59 | Atmospheric & Ground Environment | ~50 | ~8,493 | Planned |
| 60 | Obscurants, Fire, & Visual Environment | ~50 | ~8,543 | Planned |
| 61 | Maritime, Acoustic, & EM Environment | ~55 | ~8,598 | Planned |
| 62 | Human Factors, CBRN, & Air Combat | ~45 | ~8,643 | Planned |
| 63 | Cross-Module Feedback Loops | ~45 | ~8,688 | Planned |
| 64 | C2 Friction & Command Delay | ~40 | ~8,728 | Planned |
| 65 | Space & EW Sub-Engine Activation | ~40 | ~8,768 | Planned |
| 66 | Unconventional, Naval, & Cleanup | ~30 | ~8,798 | Planned |
| 67 | Integration Validation & Recalibration | ~40 | ~8,838 | Planned |

**Block 7 total**: ~455 new tests across 10 phases.
**Projected cumulative**: ~8,838 Python tests + 272 frontend = ~9,110 total.

---

## Module Index: Block 7 Contributions

| Module | Phases | Changes |
|--------|--------|---------|
| `simulation/battle.py` | 58, 59, 60, 61, 62, 63, 65 | Air routing, damage detail, posture protection, logistics gates, environment wiring, obscurant/fire, acoustic/EM/DEW, human factors, CBRN, air combat env, MISSILE routing, comms→C2, ECCM |
| `simulation/engine.py` | 58, 60, 63, 64, 65, 66 | Structural tests, ObscurantsEngine tick, checkpoint registration, C2 friction, space/EW/SIGINT wiring, unconventional routing |
| `simulation/scenario.py` | 58, 60 | Engine availability verification, ObscurantsEngine instantiation |
| `simulation/calibration.py` | 58, 62 | Posture protection fields, heat/cold casualty params |
| `movement/engine.py` | 58, 59 | Fuel consumption, ground condition params, obstacle/ford/bridge |
| `detection/detection.py` | 59, 60, 61 | Seasonal concealment, obscurant opacity, acoustic layers |
| `combat/ballistics.py` | 59 | True air density, lapse rate, propellant temperature |
| `c2/communications/` | 61 | HF propagation, atmospheric attenuation, radio horizon |
| `c2/ai/assessment.py` | 63 | FOW-based contacts instead of ground truth |
| `cbrn/dispersal.py` | 62 | Rain washout, temperature persistence, inversion trapping, UV degradation |
| `environment/obscurants.py` | 60 | Instantiation (existing code, newly wired) |
| `environment/underwater_acoustics.py` | 61 | Layer effects API |
| `ew/eccm.py` | 65 | ECCM reduction API |
| `core/checkpoint.py` | 63 | Module state registration |
| `tests/validation/test_structural_audit.py` | 58, 67 | 5 structural verification tests |

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Air combat routing changes every air engagement | High | Phase 58 (earliest); recalibrate immediately; expect all air-heavy scenarios affected |
| Posture protection makes defenders much harder to destroy | High | Calibrate protection values conservatively; DUG_IN ~50% not ~90% |
| Logistics gates stop combat in scenarios without supply units | High | Gate only when logistics system active (supply units present); degrade gracefully |
| Damage detail extraction produces cascading losses | High | Secondary effects (cookoff, fire) opt-in via CalibrationSchema; disabled by default |
| Environmental corrections change outcomes | High | Phase 67 dedicated to recalibration; run full eval after each phase |
| Scenario recalibration cascade across 37 scenarios | High | Recalibrate one at a time; accept new baselines |
| C2 friction makes AI unable to function | High | Opt-in flag; careful tuning; INTUITIVE method for low echelon |
| Performance degradation from new per-engagement queries | Medium | O(1) lookups with caching; profile after each phase; budget 30% overhead |
| Fire spread model creates runaway terrain destruction | Medium | Spread rate capped; fire decays when fuel exhausted; limited by vegetation moisture |
| Radar horizon gate makes ground radars useless | Medium | Only applies below geometric horizon; most engagements within horizon |

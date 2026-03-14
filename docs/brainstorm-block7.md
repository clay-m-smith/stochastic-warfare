# Block 7: Final Engine Hardening — Integration, Wiring, & Fidelity

## Motivation

Blocks 1–6 built 57 phases of subsystems, from core infrastructure through combat, C2, EW, space, CBRN, four historical eras, a web UI, and full scenario validation. The result is a simulation with ~8,655 tests, 37 validated scenarios, and zero unresolved deficits.

However, a comprehensive audit reveals that the project suffers from a systemic **build-then-defer-wiring** pattern. The consequence is severe:

- **36 environmental parameters** are computed every tick but never consumed by any downstream system
- **16 combat engines** are instantiated but unreachable from the battle loop (including ALL air combat)
- **4 EngagementType enum values** (MISSILE, AIR_TO_AIR, AIR_TO_GROUND, SAM) are declared but never assigned or routed
- **The event bus is observational only** — 73 files publish events, zero functional subscribers react to them
- **Damage detail is discarded** — DamageEngine computes casualties, equipment damage, fires, and ammo cookoff, but only `damage_fraction` is used for a binary DESTROYED/DISABLED check
- **Logistics doesn't gate combat** — units with zero fuel still move, maintenance state doesn't affect readiness
- **Checkpoint infrastructure saves nothing** — 136 classes implement get_state/set_state but none are registered
- **DUG_IN provides zero protection** — only stops movement, doesn't reduce incoming damage
- **Detection → AI uses ground truth** — AI sees raw enemy count, not detected contacts or confidence levels

Block 7 is the **final hardening block**. It comprehensively addresses every integration gap — environment, combat routing, cross-module feedback loops, and dead code — with a triage framework that prevents scope creep and structural verification tests that prevent future regression.

**Block 7 exit criterion**:
1. Every instantiated engine either contributes to simulation outcomes or is removed
2. Every computed parameter is consumed by at least one downstream system (verified by automated test)
3. Every published event type has at least one functional subscriber (verified by automated test)
4. Every cross-module feedback loop is either fully wired or explicitly documented as deferred
5. All scenarios still produce correct historical outcomes after integration

---

## Current State: Engine Wiring Audit

### Fully Wired & Active (contributing to outcomes)

| Engine | Lines | What It Does |
|--------|-------|-------------|
| WeatherEngine | 289 | Markov weather, wind (O-U process), visibility, temperature |
| TimeOfDayEngine | 197 | Solar/lunar illumination, thermal contrast, NVG effectiveness |
| SeasonsEngine | 253 | Ground state (frozen/thawing/wet/dry), mud, snow, vegetation, trafficability |
| FogOfWarManager | 433 | Per-side detection, track lifecycle, COP sharing |
| PoliticalPressureEngine | 268 | Escalation ladder, desperation index, war crimes cascade |
| HeightmapManager | 260 | Elevation, slope, aspect |
| TerrainClassification | 280 | Land cover classes, trafficability lookup |
| LOSEngine | 450 | DDA line-of-sight, viewshed |
| DetectionEngine | 400+ | Unified SNR detection, Kalman tracking |
| CombatEngines (8+) | 3,000+ | All domain combat resolution |
| MoraleEngine | 600+ | Continuous Markov morale, rout, rally |
| MovementEngine | 800+ | A* pathfinding, formations, domain movement |

### Instantiated but Output Ignored

These engines are created and updated each tick, but their computed state is never consumed by downstream systems.

| Engine | Lines | Gap |
|--------|-------|-----|
| SeasonsEngine | 253 | `trafficability`, `mud_depth`, `vegetation_density`, `snow_depth` computed but never queried by movement or detection |
| SeaStateEngine | 218 | Wave height used for gunnery dispersion only; no effect on ship movement, carrier ops, amphibious assault, mine drift |
| EMPropagationEngine | 200+ | GPS accuracy wired; radar horizon, atmospheric attenuation, EM ducting NOT used by detection or comms |

### Instantiated but Never Called

These engines exist on the SimulationContext, have full implementations, but no method is ever invoked from `engine.py` or `battle.py`.

| Engine | Lines | What It Would Add |
|--------|-------|-------------------|
| ObscurantsEngine | 256 | Smoke/dust/fog clouds with drift, dispersion, spectral blocking |
| ConditionsEngine | 249 | Facade aggregating all environment sub-engines (may be redundant) |
| SpaceISREngine | 206 | Satellite overpass detection of formations |
| EarlyWarningEngine | 143 | Ballistic missile launch detection via GEO/HEO satellites |
| ASATEngine | 353 | Anti-satellite warfare, debris cascade (Kessler syndrome) |
| SIGINTEngine | 488 | Radar/comms geolocation, traffic analysis |
| ECCMEngine | 270 | Electronic protection techniques reducing jam effectiveness |
| OrderPropagationEngine | 315 | Order delay (echelon-scaled) + misinterpretation probability |
| PlanningProcessEngine | 564 | MDMP state machine with planning phase delays |
| ATOPlanningEngine | 459 | Air tasking order generation with sortie limits |
| UnconventionalWarfareEngine | 397 | IED, guerrilla hit-and-run, human shields |

### Partially Wired (gate checks but no execution)

| Engine | Lines | Gap |
|--------|-------|-----|
| StratagemEngine | 416 | Eligibility evaluation works; `activate_stratagem()` never called |
| MineWarfareEngine | 541 | `resolve_mine_encounter()` called; `lay_mines()` never called |

### Dead YAML Fields

| Field | Defined In | Consumed? | Notes |
|-------|-----------|-----------|-------|
| `weight_kg` | AmmoDefinition, Equipment | No | No weight-of-fire calculations |
| `propulsion` | AmmoDefinition | No | Rocket/turbojet/ramjet — no propulsion modeling |
| `unit_cost_factor` | AmmoDefinition | No | No logistics cost modeling |
| `data_link_range` | AerialUnit loader | No | UAV data link range never checked |

---

## Cross-Module Integration Gaps (Non-Environment)

These are systemic integration failures that affect every domain, not just environment.

### Event Bus: Observational Only

**73 files** publish events. **2 files** subscribe — the `Recorder` (captures all events for replay) and `scenario_runner` (one generic subscription). Zero modules take functional action based on event receipt.

**Events published but never processed by domain logic:**

| Event | Publisher | Expected Subscriber | Missing Effect |
|-------|-----------|-------------------|----------------|
| `CasualtyTreatedEvent` | MedicalEngine | Unit strength tracker | Treated personnel never return to duty (unit stays depleted) |
| `ReturnToDutyEvent` | MedicalEngine | Unit strength tracker | Same — RTD published but nobody restores personnel |
| `EquipmentBreakdownEvent` | MaintenanceEngine | Unit readiness | Breakdown published but unit continues at full capability |
| `MaintenanceCompletedEvent` | MaintenanceEngine | Unit readiness | Repair published but readiness never restored |
| `SupplyDeliveredEvent` | SupplyEngine | Stockpile tracker | Supply arrives but stockpile may not update consumption state |
| `RouteInterdictedEvent` | DisruptionEngine | Supply routing | Route severed but no reactive rerouting or supply crisis |
| `ConvoyDestroyedEvent` | LogisticsEngine | Supply planning | Convoy loss has no feedback to logistics or C2 |
| `MoraleStateChangeEvent` | MoraleEngine | AI assessment | Morale transition published but AI doesn't adapt tactics |
| `RallyEvent` | RallyEngine | Movement/engagement | Rally published but unit doesn't automatically resume operations |
| `ATOGeneratedEvent` | ATOPlanningEngine | Air ops dispatcher | ATO entries generated but never consumed by air missions |
| `PlanningCompletedEvent` | PlanningProcessEngine | OODA cycle | Planning completes but nobody reads the result |
| `OrderIssuedEvent` | OrderPropagationEngine | Unit execution | Order published but no delayed-execution queue |
| `StratagemActivatedEvent` | StratagemEngine | Combat modifier | Stratagem activates but no modifier applied |

**Root cause**: The EventBus was designed for cross-module communication but modules were built with direct parameter passing instead. Events serve only as audit trail for the recorder.

### Combat Routing: 16 Unreachable Engines

**4 dead EngagementType values:**

| EngagementType | Status | Consequence |
|----------------|--------|-------------|
| `MISSILE` | Never assigned by `_infer_engagement_type()` | Missile flights tracked by MissileEngine but never end in impact |
| `AIR_TO_AIR` | Never assigned | Air-to-air engagements route as DIRECT_FIRE (gun duel physics) |
| `AIR_TO_GROUND` | Never assigned | CAS/strike uses generic engagement, not air-specific Pk model |
| `SAM` | Never assigned | SAM engagements use generic engagement, not AD-specific model |

**16 engines instantiated but unreachable from battle loop:**

| Category | Engines | Lines | Impact |
|----------|---------|-------|--------|
| Air combat | AirCombatEngine, AirDefenseEngine, AirGroundEngine | ~1,200 | Air engagements use wrong physics (ground combat Pk for air duels) |
| Strategic air | AirCampaignEngine, StrategicBombingEngine, StrategicTargetingEngine | ~800 | Strategic air campaigns can't execute |
| Missiles | MissileEngine, MissileDefenseEngine | ~600 | Missile flight/intercept models unused |
| Naval air | CarrierOpsEngine | ~300 | CAP management, recovery windows unused |
| Historical naval | NavalOarEngine | ~200 | Ancient trireme combat uses generic model |
| Damage effects | IncendiaryDamageEngine, UXOEngine | ~400 | Fire zones and UXO contamination never created |
| Unconventional | UnconventionalWarfareEngine | ~400 | IED/guerrilla tactics dead |
| Siege | SiegeEngine | ~300 | Siege mechanics never invoked |
| C2 | VisualSignalsEngine, AmphibiousAssaultEngine | ~400 | Ancient C2 and amphibious assault dead |

### Damage Detail Discarded

`DamageEngine.resolve_damage()` returns a `DamageResult` with:
- `damage_fraction` (0.0–1.0) — **USED**: compared to destruction/disable thresholds
- `casualties` (list of CasualtyResult) — **DISCARDED**: personnel losses never extracted
- `systems_damaged` (list of equipment hits) — **DISCARDED**: equipment never degrades
- `fire_started` (bool) — **DISCARDED**: no fire zone creation
- `ammo_cookoff` (bool) — **DISCARDED**: no secondary explosions
- `penetrated` (bool) — **DISCARDED**: no armor degradation

**Consequence**: A unit is either OPERATIONAL, DISABLED, or DESTROYED. No partial degradation. A tank with 49% damage has full combat power; at 50% it's destroyed. No crew casualties, no degraded systems, no fires.

### Logistics Does Not Gate Combat

| Resource | Tracked? | Consumed? | Gates Action? |
|----------|----------|-----------|---------------|
| Ammunition | Yes | Yes (weapon.fire()) | **NO** — unit fires at 0 ammo |
| Fuel | Yes | No (movement doesn't consume) | **NO** — unit moves at 0 fuel |
| Maintenance/Readiness | Yes | Yes (breakdown events) | **NO** — disabled equipment still functions |
| Medical | Yes | Yes (treatment events) | **NO** — RTD events not consumed |
| Supply routes | Yes | Yes (disruption modeled) | **NO** — severed routes don't create shortages |

**Note**: The third agent's investigation confirmed ammo consumption IS wired via `weapon.fire()`. However, ammo depletion does not prevent firing.

### Checkpoint State Not Saved

`CheckpointManager.register()` exists but is **never called in production code**. Checkpoints contain only clock and RNG state. Module state (morale, detection tracks, supply levels, equipment condition) is not saved. This means checkpoint restore produces a simulation with correct time and RNG but wrong unit states.

### Detection → AI Uses Ground Truth

The AI assessment system receives:
- `contacts = enemy_unit_count` (raw count, not detected count)
- `enemy_power = float(enemies)` (true strength, not estimated)

FogOfWarManager exists and tracks per-side contacts with confidence/age, but this data is **not passed to the AI assessment pipeline**. The AI has perfect information about enemy forces regardless of sensor coverage.

**Exception**: When `enable_fog_of_war` is True (never set by any scenario), contact count comes from FOW tracking. But even then, quality/confidence/error is not conveyed.

### Posture Protection Gap

| Posture | Speed Mult | Damage Reduction | Should Have |
|---------|-----------|-----------------|-------------|
| MOVING | 1.0 | 0% | 0% (correct) |
| HALTED | 1.0 | 0% | 0% (correct) |
| DEFENSIVE | 0.5 | 0% | ~20% (hasty fighting position) |
| DUG_IN | 0.0 | 0% | ~50% (prepared position) |
| FORTIFIED | 0.0 | 0% | ~70% (hardened position) |

DUG_IN/FORTIFIED units take the same casualties as units in the open. The only benefit is speed=0 (they don't move). Terrain `cover` from obstacles provides some protection, but posture itself does not.

### C2 Authority Not Enforced

- **ROE**: Works. Engagement gated by ROE level per target category.
- **Command authority**: Not enforced. Any unit engages any target regardless of command chain.
- **Orders → behavior**: Orders are not consumed. Units don't read orders to modify target selection or movement.
- **Comms loss → independent action**: Comms degradation affects assessment confidence but not engagement rules. A unit with zero comms fights identically to one with perfect comms.

### CalibrationSchema Fields Never Exercised

16 calibration fields have defaults but are never set by any scenario YAML (confirmed via YAML audit):

`disable_threshold`, `dew_disable_threshold`, `dig_in_ticks`, `wave_interval_s`, `target_selection_mode`, `night_thermal_floor`, `wind_accuracy_penalty_scale`, `rain_attenuation_factor`, `c2_min_effectiveness`, `enable_fog_of_war`, `engagement_concealment_threshold`, `target_value_weights`, `gas_casualty_floor`, `gas_protection_scaling`, `subsystem_weibull_shapes`, `victory_weights`

Note: `observation_decay_rate` was previously listed but is set in at least one scenario YAML.

---

## Triage Framework

Every identified gap must be triaged before implementation. This prevents scope creep and ensures we focus on high-impact work.

### Priority Levels

| Priority | Criterion | Action | Examples |
|----------|-----------|--------|----------|
| **P0: Must Wire** | Existing code with clear consumer path; high fidelity impact; missing wiring is a bug | Wire in this block | Rain detection factor (function exists, never called), air combat routing, damage detail extraction, posture protection |
| **P1: Should Wire** | Moderate fidelity impact; straightforward integration; improves realism noticeably | Wire in this block | Seasonal trafficability → movement, obscurants → detection, radar horizon, HF quality → comms |
| **P2: Wire If Time** | Lower fidelity impact; useful but not essential; may require new code beyond simple wiring | Wire if ahead of schedule | Fire spread model, altitude sickness, wave period resonance, biological sonar noise |
| **P3: Defer** | Edge cases, very low impact, or requires significant new architecture | Document and defer to future block | Spin drift, soil CBRN absorption, dynamic cratering, Faraday rotation |
| **P4: Remove** | Computed values with no meaningful consumer; dead code that generates false audit findings | Delete computation | shadow_azimuth (no consumer), deep_channel_depth (niche), solar/lunar decomposition (diagnostic only) |

### Triage: Environment Parameters (36 items)

| Parameter | Priority | Rationale |
|-----------|----------|-----------|
| `_compute_rain_detection_factor()` — function exists, never called | **P0** | Bug — implemented ITU-R P.838 model, zero call sites |
| DEW humidity/precip_rate — params accepted, never passed | **P0** | Bug — physics model exists, call site doesn't pass values |
| SeasonsEngine.mud_depth → movement | **P1** | Rasputitsa, WW1 mud — major historical effect |
| SeasonsEngine.snow_depth → movement | **P1** | Eastern Front, Korean War — major historical effect |
| SeasonsEngine.vegetation_density → detection | **P1** | Seasonal concealment — moderate historical effect |
| SeasonsEngine.sea_ice_thickness → crossing | **P1** | Eastern Front frozen rivers — scenario-specific |
| ObscurantsEngine (full instantiation + wiring) | **P1** | Smoke screens, dust trails — significant tactical effect |
| EMPropagation.radar_horizon → detection | **P1** | Earth curvature on radar — fundamental physics |
| EMPropagation.hf_quality → comms | **P1** | Day/night HF reliability — affects WW2/historical comms |
| EMPropagation.atmospheric_attenuation → radar/comms | **P1** | Rain loss on high-freq systems — moderate effect |
| EMPropagation.ducting → radar range | **P1** | Maritime radar extension — scenario-specific |
| UnderwaterAcoustics.thermocline → sonar | **P1** | ASW layer tactics — fundamental naval effect |
| UnderwaterAcoustics.convergence_zones → sonar | **P1** | 55km detection rings — fundamental ASW |
| SeaState.tidal_current → ship movement | **P1** | Ship routing, mine drift — moderate effect |
| TimeOfDay.background_temp → thermal ΔT detection | **P1** | Thermal crossover vulnerability — real planning factor |
| TimeOfDay.nvg_effectiveness → detection | **P1** | NVG-equipped night detection — moderate effect |
| WeatherEngine.wind.gust → operation gates | **P2** | Helicopter abort, parachute accuracy — niche |
| WeatherEngine.pressure → air density | **P2** | Ideal gas correction — small effect at sea level |
| SeasonsEngine.vegetation_moisture → fire | **P2** | Fire ignition probability — requires fire system |
| SeasonsEngine.wildfire_risk → fire events | **P2** | Spontaneous fire — requires fire system |
| SeasonsEngine.daylight_hours → ops planning | **P2** | Operational tempo — low tactical impact |
| SeaState.wave_period → ship resonance | **P2** | Roll amplitude — niche effect |
| SeaState.beaufort → small craft gate | **P2** | Landing craft operations — scenario-specific |
| UnderwaterAcoustics.surface_duct → sonar | **P2** | In-duct detection — niche ASW |
| Terrain.vegetation_height → LOS | **P2** | Ground-level vegetation block — moderate |
| Terrain.combustibility → fire | **P2** | Fire ignition — requires fire system |
| Obstacles.traversal_risk → casualties | **P2** | Wire crossing casualties — niche |
| Obstacles.traversal_time → movement | **P2** | Obstacle delay — moderate |
| Hydrography.ford_points → crossing | **P2** | River ford routing — scenario-specific |
| Infrastructure.bridge_capacity → weight gate | **P2** | Heavy vehicle bridge limit — niche |
| TimeOfDay.shadow_azimuth | **P4** | No meaningful consumer — remove |
| TimeOfDay.solar/lunar contribution split | **P4** | Diagnostic only — remove computation |
| UnderwaterAcoustics.deep_channel_depth | **P3** | SOFAR channel — very niche |
| Equipment.temperature_range → stress | **P2** | Weapon jam in extreme cold/heat — moderate |
| Infrastructure.Road.speed_factor override | **P3** | Per-road speed — low impact vs hardcoded table |
| Infrastructure.Tunnel routing | **P3** | Tunnel in pathfinding — niche |

### Triage: Combat Integration (16+ items)

| Gap | Priority | Rationale |
|-----|----------|-----------|
| Air combat routing (AIR_TO_AIR, AIR_TO_GROUND, SAM) | **P0** | 3 engines exist with correct physics; currently air duels use ground combat Pk |
| Damage detail extraction (casualties, systems_damaged) | **P0** | DamageEngine computes it; discarding is a bug |
| Posture → damage reduction (DUG_IN/FORTIFIED protection) | **P0** | DUG_IN providing zero protection is a bug |
| MISSILE engagement routing | **P1** | MissileEngine exists; missiles currently route as DIRECT_FIRE or COASTAL_DEFENSE |
| IncendiaryDamageEngine → fire zones | **P1** | Engine exists; fire_started from DamageResult should trigger it |
| CarrierOpsEngine → naval air | **P1** | CAP management, recovery windows — significant for naval scenarios |
| SiegeEngine → campaign loop | **P2** | Ancient/medieval siege — era-specific |
| AmphibiousAssaultEngine → naval ops | **P2** | Beach assault state machine — scenario-specific |
| UXOEngine → post-engagement | **P2** | Submunition contamination — niche |
| NavalOarEngine → ancient naval | **P3** | Ancient trireme propulsion — era-specific niche |
| VisualSignalsEngine → ancient C2 | **P3** | Ancient visual communication — era-specific niche |
| StrategicBombingEngine → WW2 campaign | **P2** | Strategic air campaign — era-specific |
| StrategicTargetingEngine → bombing | **P2** | Target prioritization — paired with StrategicBombing |
| AirCampaignEngine → campaign loop | **P2** | Campaign-level air operations — moderate |
| MissileDefenseEngine → AD | **P2** | Air defense missiles — moderate |

### Triage: Cross-Module Integration

| Gap | Priority | Rationale |
|-----|----------|-----------|
| Fuel consumption → movement gate | **P0** | Fundamental logistics — units at 0 fuel should not move |
| Ammo depletion → firing gate | **P0** | Unit fires at 0 ammo — bug |
| Maintenance/readiness → combat gate | **P1** | Disabled equipment should degrade combat performance |
| Medical RTD → unit strength restoration | **P1** | Treated casualties should return to duty |
| Detection → AI assessment (use FOW contacts, not ground truth) | **P1** | AI has perfect information — defeats purpose of detection system |
| Comms loss → C2 degradation → independent action | **P1** | Comms down should force units to last received orders |
| Checkpoint state registration | **P1** | Checkpoint saves nothing — defeats purpose of checkpoint system |
| Event bus functional subscribers | **P2** | Most events are consumed via direct passing; event subscribers are optional improvement |
| Supply route interdiction → supply shortage | **P2** | Logistics feedback loop — moderate |
| CalibrationSchema exercised in scenarios | **P2** | 16 fields never set — either exercise or remove |

---

## Structural Verification Tests

These tests must be created **before implementation begins** and run continuously to prevent regression.

### Test 1: Unconsumed Parameter Audit

```python
def test_no_unconsumed_engine_outputs():
    """Every engine property computed during simulation is read by at least one consumer."""
    # Instrument all engine classes with property access tracking
    # Run a representative scenario with all systems active
    # Collect set of properties that were written but never read
    # Assert empty set (or only P4-triaged items)
```

**Implementation**: Monkey-patch engine classes with `__getattr__`/`__setattr__` tracking, or use a coverage-like instrumentation approach. Run a modern scenario + one historical scenario to exercise all code paths.

### Test 2: Dead Method Audit

```python
def test_no_uncalled_public_methods():
    """Every public method on every engine class has at least one external caller."""
    # AST-parse all source files
    # Build method definition set (all public methods on engine classes)
    # Build call site set (all method calls across all source files)
    # Assert: definitions ⊆ call sites (minus test-only callers)
```

**Implementation**: Use `ast.parse()` to walk source trees. Flag any public method defined in `stochastic_warfare/` that has zero call sites outside its own module and tests.

### Test 3: Event Subscription Audit

```python
def test_all_event_types_have_subscribers():
    """Every event type published in the simulation has at least one functional subscriber."""
    # AST-parse all source files for bus.publish(EventType(...))
    # AST-parse all source files for bus.subscribe(EventType, handler)
    # Assert: every published type has at least one subscriber (beyond Recorder)
    # OR: published type is in OBSERVATION_ONLY_EVENTS allowlist
```

### Test 4: Engagement Routing Completeness

```python
def test_all_engagement_types_routed():
    """Every EngagementType enum value has a handler in the battle loop."""
    # For each EngagementType value
    # Assert: route_engagement() or _infer_engagement_type() can produce it
    # AND: a handler exists that resolves it
```

### Test 5: Feedback Loop Verification

```python
def test_logistics_gates_combat():
    """Unit with depleted ammo cannot fire; unit with depleted fuel cannot move."""

def test_damage_detail_applied():
    """DamageResult casualties are extracted and reduce unit personnel count."""

def test_posture_protection():
    """DUG_IN unit takes less damage than MOVING unit from same attack."""

def test_checkpoint_state_round_trip():
    """Checkpoint saves and restores all module state, not just clock/RNG."""
```

---

## Theme 1: Environmental Fidelity Gap Analysis (Priority: Highest)

The environment subsystem has rich physics models whose outputs are largely ignored. This section is an exhaustive, domain-by-domain audit of every environmental parameter — what's computed, what's consumed, and what's missing entirely. The goal is "excruciatingly exact" fidelity: every computed value consumed, every real-world effect that matters at campaign/battle scale represented.

### Legend

- **WIRED**: Computed and consumed by downstream combat/movement/detection systems
- **COMPUTED/UNCONSUMED**: Engine calculates the value every tick, but no system reads it
- **DEFINED/UNCALLED**: Method or API exists in source code but is never invoked
- **NOT IMPLEMENTED**: Physics model doesn't exist yet but should for high fidelity

---

### 1.1 Atmospheric Physics

#### Air Density & Pressure

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Air density (altitude-dependent) | WIRED (partial) | Exponential model in ballistics (scale height 8500m). Used for Mach drag. | Also needed for: aircraft engine performance, helicopter lift margin, DEW thermal blooming, unguided rocket range |
| Barometric pressure | NOT IMPLEMENTED | WeatherEngine computes `pressure` field but it's **never consumed** anywhere | Should feed air density via ideal gas law (ρ = P/RT). Affects ballistic drag, acoustic propagation, altimeter accuracy |
| Humidity → air density | NOT IMPLEMENTED | Humidity computed in WeatherEngine, never affects air density | Moist air is ~0.5% less dense than dry air. Small effect but contributes to density altitude calculation |
| Temperature lapse rate | NOT IMPLEMENTED | Ballistics uses constant temperature at all altitudes | ISA lapse rate (−6.5°C/km to tropopause, isothermal above). Affects speed of sound, Mach number, drag coefficient at altitude |
| Density altitude | COMPUTED/UNCONSUMED | `ConditionsEngine.air().density_altitude` computed | Should gate: helicopter operations (high+hot = no-go), aircraft takeoff distance, engine power output |

#### Wind

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Mean wind (speed, direction) | WIRED | Ornstein-Uhlenbeck process, consumed by crosswind penalty, CBRN drift, obscurant drift | — |
| Wind gusts | COMPUTED/UNCONSUMED | `WeatherEngine.wind.gust` computed every tick | Should affect: helicopter operations (gust > threshold = abort landing), bridge-laying operations, parachute drop accuracy, amphibious small craft capsizing |
| Wind shear (altitude-dependent) | NOT IMPLEMENTED | Wind is constant at all altitudes | Real wind varies with altitude (boundary layer). Affects artillery at high angles, parachute drift, aircraft approach. Model: log wind profile or power law |
| High wind halt threshold | NOT IMPLEMENTED | No maximum wind speed for operations | Should force infantry to halt in extreme wind (>25 m/s / ~50 mph), prevent helicopter operations, degrade vehicle stability |
| Turbulence | NOT IMPLEMENTED | Only mean wind modeled | Adds stochastic dispersion to ballistic trajectories, parachute drops, helicopter hover stability. Model: σ_wind as fraction of mean wind |

#### Temperature

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Ambient temperature | WIRED | Diurnal cycle + monthly mean. Fed to ballistics (speed of sound), weather state transitions | — |
| Temperature at altitude | COMPUTED/UNCONSUMED | `WeatherEngine.temperature_at_altitude()` exists | Should drive lapse rate calculations, icing determination, engine performance curves |
| Temperature inversion | NOT IMPLEMENTED | No inversion layer detection | Critical for: CBRN (traps agents below inversion, 10x concentration increase), EM ducting (extends radar range), acoustic propagation (sound channels). Model: detect when temperature increases with altitude |
| Propellant temperature → muzzle velocity | NOT IMPLEMENTED | All rounds assume nominal MV | Cold propellant (−20°C) reduces MV by 2–5%. Hot propellant (+50°C) increases MV by 1–3%. Affects range tables for artillery. Source: MIL-STD-1474 |
| Equipment temperature stress | DEFINED/UNCALLED | `EquipmentItem.temperature_range` defined in YAML, `EquipmentManager.environment_stress()` computes degradation factor | Degradation factor never applied in simulation loop. Should affect: weapon reliability (jams in extreme cold/heat), electronics failure rate, battery capacity |

#### Icing

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Icing risk | COMPUTED/UNCONSUMED | `ConditionsEngine.air().icing_risk` calculated (temperature 0 to −20°C + cloud/precip) | Should affect: aircraft performance (wing ice = lift loss, engine ice = power loss), helicopter blade ice, radar dome ice (degrades signal), weapon system freeze-up |
| Road/runway icing | NOT IMPLEMENTED | No surface ice model | Snow/ice on runways should degrade aircraft operations. Road ice should reduce vehicle traction. Model: surface temperature < 0°C + precipitation = ice |

---

### 1.2 Optical & Visual Environment

#### Illumination & Visibility

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Total illumination (lux) | WIRED | Solar + lunar + cloud cover → detection range modifier | — |
| Twilight stages (5-level) | WIRED | Civil/nautical/astronomical/full night → graduated visual/thermal modifiers | — |
| Weather visibility | WIRED | Weather state → visibility_m → detection range cap | — |
| Solar contribution (decomposed) | COMPUTED/UNCONSUMED | Separated from total lux but only total used | Low value — decomposition is diagnostic data |
| Lunar contribution (decomposed) | COMPUTED/UNCONSUMED | Same as solar | Low value |
| Artificial illumination (flares, searchlights) | DEFINED/UNCALLED | API exists in TimeOfDayEngine (`artificial_contribution`) but never populated | Should allow: flare illumination events (brief high-lux area), searchlight beams, urban ambient light. Model: point source with inverse-square falloff |
| Shadow azimuth | COMPUTED/UNCONSUMED | Computed from solar position, never queried | Could affect: visual detection from specific angles (target in shadow harder to spot from shadow side). Low priority |
| NVG effectiveness | COMPUTED/UNCONSUMED | `TimeOfDayEngine.nvg_effectiveness()` exists | Partially consumed by movement (0.7x night speed recovery with NVG). NOT consumed by detection engine — NVG-equipped units should detect further at night |

#### Thermal Environment

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Thermal contrast | WIRED (partial) | `TimeOfDayEngine.thermal_environment().thermal_contrast` computed. Detection uses illumination-based modifier instead | Should be the primary driver of thermal detection SNR. Vehicles have high thermal contrast at night (engine heat vs cold background), low at dawn/dusk crossover |
| Background temperature | COMPUTED/UNCONSUMED | Computed as ambient + solar heating + surface material | Should feed thermal detection SNR calculation: target_temp − background_temp = ΔT → SNR. Currently uses generic thermal_contrast scalar instead of physics-based ΔT |
| Thermal crossover timing | COMPUTED/UNCONSUMED | `crossover_in_hours` computed — tells how long until thermal signatures blend into background | Should create vulnerability windows: at crossover, thermal detection is near-zero for stationary vehicles. Dawn and dusk crossovers are real-world tactical planning factors |

#### Obscurants (Smoke, Dust, Fog)

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Smoke cloud deployment | DEFINED/UNCALLED | Full API: `deploy_smoke(center, radius, multispectral)` in ObscurantsEngine (256 lines) | Barrages/mortars should spawn smoke at impact. Smoke grenades/pots for deliberate screening. Spectral blocking: visual 0.9, thermal 0.1 (standard) or 0.8 (multispectral), radar 0.0–0.3 |
| Smoke drift & decay | DEFINED/UNCALLED | Wind-driven drift, radial dispersion (r ∝ √t), exponential decay (30min half-life) all implemented | ObscurantsEngine.update() should be called each tick. Currently never instantiated on SimulationContext |
| Dust from vehicle movement | NOT IMPLEMENTED | No dust generation hook in movement | Vehicles on dry terrain (DRY ground_state + non-road) should spawn dust trails. Intensity ∝ speed × vehicle_count. Dust reveals movement (signature enhancement) + degrades following-vehicle LOS |
| Dust from explosions | NOT IMPLEMENTED | Impact detonations don't create dust | HE impacts on dry ground should create short-duration dust clouds at impact site. Affects BDA (can't see if target was hit) |
| Fog auto-generation | DEFINED/UNCALLED | ObscurantsEngine has fog generation when WeatherState.FOG | Never triggered because engine never instantiated. Should auto-create fog patches when weather transitions to FOG. Radiation fog (clear nights), advection fog (warm air over cold water), sea fog |
| Fog dissipation by solar heating | NOT IMPLEMENTED | Fog uses generic exponential decay | Real fog lifts when solar heating warms ground (morning burn-off). Model: fog opacity × (1 − solar_heating_factor) |
| Spectral opacity query | DEFINED/UNCALLED | `opacity_at(pos)` returns per-spectrum opacity (visual, thermal, radar) | Should be queried by: detection engine (degrade SNR by spectrum), combat engine (reduce Pk for visual/thermal-guided weapons), DEW engine (attenuate beam) |
| Pre-placed smoke/fog in scenarios | NOT IMPLEMENTED | No scenario YAML field for initial obscurant placement | Allow `environment_config.smoke_zones` and `fog_zones` for historical accuracy (Austerlitz morning fog, Falklands sea fog, WW1 smoke barrages) |

---

### 1.3 Electromagnetic Environment

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| GPS accuracy | WIRED | EMPropagationEngine → detection/space/EW integration | — |
| GPS spoofing offset | WIRED | EW module → EMPropagation → position error | — |
| GPS jam degradation | WIRED | EW module → EMPropagation → accuracy degradation | — |
| Free-space path loss | COMPUTED/UNCONSUMED | `free_space_path_loss(freq, range)` public API exists, only called internally | Should be used by: communications range calculation, radar detection range, EW intercept range |
| Radar horizon | DEFINED/UNCALLED | `radar_horizon(antenna_height)` computes 4/3 Earth radius geometric horizon | Should gate air defense radar detection range. Currently detection uses fixed `max_range_m` from sensor YAML, ignoring Earth curvature. A ground radar at 10m height has ~13km horizon; at 30m, ~22km. Low-flying aircraft below horizon are invisible to radar |
| Atmospheric attenuation (freq-dependent) | COMPUTED/UNCONSUMED | Computed per frequency band (O₂ absorption peak at 60 GHz, water vapor at 22 GHz) | Should attenuate radar and comms at high frequencies. X-band (10 GHz) loses ~0.01 dB/km dry, ~0.1 dB/km in rain. Ka-band (35 GHz) loses ~0.4 dB/km in rain |
| EM ducting (super-refraction) | COMPUTED/UNCONSUMED | `ducting_possible` and refraction factor computed based on humidity + temperature gradient | Should extend radar and comms range beyond geometric horizon in warm, humid maritime environments (common in Persian Gulf, South China Sea). Factor of 2–3x range extension |
| Duct height | COMPUTED/UNCONSUMED | Computed but never read | Determines which systems benefit from ducting (antenna must be within duct layer) |
| HF propagation quality (day/night) | COMPUTED/UNCONSUMED | `hf_propagation_quality()` computes D-layer absorption (day) vs F-layer reflection (night) | Should modulate HF radio reliability in communications engine. Day: D-layer absorbs → short HF range. Night: F-layer reflects → long HF range (skip propagation). Critical for WW2, some modern scenarios |
| Rain clutter on radar | DEFINED/UNCALLED | `_compute_rain_detection_factor(precip_rate, range)` implemented in battle.py with ITU-R P.838 model but **never called** | Should reduce radar detection probability in rain. Heavy rain (25 mm/hr) creates radar returns that mask targets. Already implemented — just needs a call site |
| Frequency-dependent rain attenuation for comms | NOT IMPLEMENTED | Generic comms model doesn't consider frequency | UHF (300 MHz–3 GHz): negligible rain attenuation. SHF (3–30 GHz): significant. EHF (30–300 GHz): severe. Should vary comms reliability by frequency band in rain |
| Tropospheric ducting for radio | NOT IMPLEMENTED | Only modeled for radar, not comms | Same physics extends radio comms range in certain weather conditions. Common in maritime operations |
| Ionospheric storm effects | NOT IMPLEMENTED | No space weather model | Solar flares and geomagnetic storms degrade HF comms for hours to days. Model: random events with probability ∝ solar cycle |
| Radio horizon (altitude-dependent) | NOT IMPLEMENTED | Only `radar_horizon()` exists for radar | Identical physics applies to radio — higher antenna = longer range. Mobile units at different altitudes have different comms range. Model: same as radar_horizon but for comms |

---

### 1.4 Acoustic Environment

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Sound velocity profile (SVP) | WIRED | Mackenzie equation (T, S, depth) → sonar detection | — |
| Ambient noise (Wenz curves) | WIRED | Beaufort → dB ambient noise → sonar SNR threshold | — |
| Transmission loss | WIRED | Spherical spreading + absorption → sonar range | — |
| Surface duct depth | COMPUTED/UNCONSUMED | Calculated from temperature profile but never used | Sonar trapped in surface duct has enhanced range within duct but cannot detect below it. Submarine can hide below duct. Model: if target_depth > duct_depth, add 20 dB loss |
| Thermocline depth | COMPUTED/UNCONSUMED | Calculated but never used in detection | Layer below which sound bends downward. Submarine below thermocline is very difficult to detect from surface sonar. Critical for ASW tactics |
| Deep sound channel depth | COMPUTED/UNCONSUMED | Calculated but never used | SOFAR channel enables detection at extreme ranges (hundreds of km). Low priority — mostly for fixed sonobuoy networks |
| Convergence zone ranges | COMPUTED/UNCONSUMED | `convergence_zone_ranges(source_depth)` calculates 55km interval CZ detections | Should create detection "rings" at 55km, 110km, 165km from sonar source. Target between zones is in shadow. Fundamental to deep-water ASW |
| Shipping noise | NOT IMPLEMENTED | Only wind-driven Wenz curve ambient noise | Busy shipping lanes increase ambient noise, degrading sonar. Model: proximity to shipping lanes → +5–15 dB ambient noise |
| Biological noise | NOT IMPLEMENTED | No marine life noise model | Whale song, snapping shrimp can mask sonar contacts in certain waters/seasons. Low priority — niche effect |

---

### 1.5 Ground & Terrain Environment

#### Seasonal Ground State

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Ground trafficability (seasonal) | WIRED (partial) | SeasonsEngine → `ground_trafficability` scalar consumed by MovementEngine | Currently uses coarse lookup: FROZEN=0.9, THAWING=0.3, WET=0.6, DRY=1.0, SATURATED=0.2, SNOW=0.5. Wired but should also differentiate wheeled vs tracked (wheeled suffer more in mud) |
| Mud depth | COMPUTED/UNCONSUMED | `SeasonalConditions.mud_depth` accumulated from rain + thaw | Should provide granular speed penalty beyond binary trafficability. Deep mud (>20cm) immobilizes wheeled vehicles entirely. Tracked vehicles at 50% speed. Logistics transport has `mud_speed_fraction=0.5` but battle movement ignores mud depth |
| Snow depth | COMPUTED/UNCONSUMED | `SeasonalConditions.snow_depth` accumulated from snowfall | Deep snow (>30cm) should slow infantry to 40% speed, vehicles to 60%. Snow on roads should degrade road speed bonus. Plowed roads partially recover. Ski troops should have reduced penalty |
| Vegetation density | COMPUTED/UNCONSUMED | Sigmoid of growing-degree-days, 0.0–1.0 | Should modify: visual detection concealment (summer foliage hides, winter bare exposes), movement speed through dense vegetation, fire spread rate |
| Vegetation moisture | COMPUTED/UNCONSUMED | Tracked alongside vegetation density | Should affect: fire spread probability (dry vegetation burns easily, wet doesn't), agent persistence (moist surfaces break down chemical agents faster) |
| Sea ice thickness | COMPUTED/UNCONSUMED | Accumulated from freezing degree-days, latitude > 50° | Should enable: ice crossing for infantry (>10cm), light vehicles (>30cm), heavy vehicles (>60cm). Model: weight-dependent ice failure threshold. Critical for Eastern Front (crossing frozen rivers), Finnish Winter War, Korean War Chosin Reservoir |
| Wildfire risk | COMPUTED/UNCONSUMED | Composite of dryness × heat × wind × low humidity | Should trigger: random wildfire events in high-risk areas, fire spread after incendiary strikes. Feeds fire zone system |
| Daylight hours | COMPUTED/UNCONSUMED | From astronomy day_length_hours | Should affect: operational planning (short winter days = less time for maneuver), fatigue accumulation rate, solar panel power for unmanned systems |
| Rasputitsa (spring mud season) | PARTIALLY IMPLEMENTED | Mud depth mechanics exist but transitions not dramatic enough | Historical spring mud seasons halted entire armies (Eastern Front 1941, 1942, 1943, 1944). Thawing ground + rain should create impassable conditions lasting weeks. Model: THAWING state + rain → SATURATED with mud_depth spike |

#### Terrain Properties

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Vegetation height | COMPUTED/UNCONSUMED | `TerrainProperties.vegetation_height` per land cover class | Should affect: visual detection (tall vegetation conceals vehicles at distance), LOS check (thick vegetation blocks LOS at ground level), helicopter landing clearance |
| Combustibility | COMPUTED/UNCONSUMED | `TerrainProperties.combustibility` per land cover class (e.g., dry_grass=0.9, urban=0.2) | Should feed fire zone creation: incendiary weapons on high-combustibility terrain create fires; on low-combustibility terrain they don't. Currently defined but never read |
| Obstacle traversal risk | DEFINED/UNCALLED | `Obstacle.traversal_risk` defined in obstacle model | Should apply: casualty probability when crossing obstacles (e.g., wire, minefield, rubble). Currently obstacles are binary pass/block |
| Obstacle traversal time | DEFINED/UNCALLED | `Obstacle.traversal_time_multiplier` defined | Should slow units crossing obstacles (wire obstacles = 3x time, rubble = 2x, water = 4x). Currently hardcoded in movement |
| Ford points | DEFINED/UNCALLED | `Hydrography.is_fordable()`, `ford_points_near()` implemented | Should enable river crossing at ford points with depth/current-dependent time cost. Currently river crossing is binary passable/not-passable |
| Bridge capacity | DEFINED/UNCALLED | `Bridge.capacity_tons` defined | Should gate heavy vehicles on bridges (MBT at 60+ tons can't cross a 20-ton bridge). Currently all bridges passable by all units |
| Tunnel routing | DEFINED/UNCALLED | `Tunnel` geometry defined in infrastructure | Should be available in pathfinding for protection from air attack. Currently never routed |
| Road speed factor override | DEFINED/UNCALLED | `Road.speed_factor` field exists | Currently uses hardcoded `_ROAD_SPEED_FACTORS` dict instead of per-road values. Should use road-specific factors (highway vs dirt road vs track) |
| Soil type → dig-in time | NOT IMPLEMENTED | All terrain has same dig-in rate | Sandy soil: fast digging, poor fortification. Rocky soil: slow digging, good fortification. Frozen ground: very slow digging. Clay: moderate. Model: soil_type multiplier on dig_in_ticks |
| Dynamic terrain (cratering) | NOT IMPLEMENTED | Heightmap is static | Heavy artillery should create craters that affect movement and provide cover. Low priority — high implementation cost (pathfinding cache invalidation) |

---

### 1.6 Maritime Environment

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Wave height (Pierson-Moskowitz) | WIRED | Sig. wave height → naval gunnery dispersion, carrier bolter probability, amphibious penalty | — |
| Wave period | COMPUTED/UNCONSUMED | Computed from wave spectrum | Should affect: ship resonance (period matching hull natural frequency = extreme roll), helicopter deck landing difficulty. Model: roll amplitude ∝ 1/(|T_wave − T_hull|) |
| Tide height | WIRED (partial) | Harmonic model (M2/S2/K1/O1), consumed by amphibious calculations | Should also affect: shallow-water navigation (ground contact risk), beach approach timing, submarine depth clearance in littoral waters |
| Tidal current (speed, direction) | COMPUTED/UNCONSUMED | Computed from tidal harmonics but never consumed | Should affect: ship movement speed (with/against current), mine drift (floating mines move with current), submarine station-keeping effort, amphibious assault beach approach vector |
| SST (sea surface temperature) | WIRED (partial) | Fed to underwater acoustics SVP calculation | — |
| Beaufort scale | WIRED (partial) | Drives sonar ambient noise (Wenz curves) | Should also affect: small craft operations (Beaufort > 5 = dangerous for landing craft), deck operations, helicopter landing, radar sea clutter |
| Sea spray/salt fog | NOT IMPLEMENTED | No maritime atmospheric effect | Sea spray in high winds creates: visual obscuration (like fog, reduces visibility to 1–3 km), DEW attenuation (10× worse than clean air — salt crystals scatter laser), radar clutter (close-range noise from spray droplets), corrosion (long-term equipment degradation) |
| Swell direction vs ship heading | NOT IMPLEMENTED | Wave height is scalar, no direction | Beam seas (waves perpendicular to ship) cause maximum roll; head seas cause pitching; following seas are smoothest. Affects gunnery accuracy, helicopter ops, crew fatigue. Model: roll_factor = sin²(wave_dir − ship_heading) |
| Polar ice navigation | NOT IMPLEMENTED | No ice obstacle for ships | Ice fields should block or slow ships without icebreaker capability. Ice thickness from SeasonsEngine.sea_ice_thickness. Only relevant for Arctic/Antarctic scenarios |
| Littoral current effects | NOT IMPLEMENTED | No coastal current model | Near-shore currents affect: mine drift, amphibious approach, submarine navigation. Could use tidal current as proxy in shallow water |

---

### 1.7 CBRN Environment Interaction

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Wind advection of puffs | WIRED | Gaussian puff center moves with wind vector | — |
| Pasquill-Gifford stability class | WIRED | Cloud cover + wind speed + time of day → stability (A–F) | — |
| Terrain channeling | WIRED | Valley concentration (+50%), ridge deflection (×0.5) | — |
| Rain washout of agents | NOT IMPLEMENTED | Rain has no effect on airborne CBRN concentration | Rain scavenges particles and droplets from air. Model: concentration × exp(−washout_coeff × rain_rate × dt). Washout coefficient ~10⁻⁴ per mm/hr for particles. 30 mm/hr rain removes ~30% of agent in 30 minutes |
| Temperature → agent persistence | NOT IMPLEMENTED | Agent decay rate is constant | Nerve agents: half-life 8 hrs at 20°C, 2 hrs at 40°C, 24+ hrs at 0°C. Mustard: persists for days/weeks in cold. Model: decay_rate × exp(−Ea/RT) Arrhenius kinetics |
| UV hydrolysis (sunlight degradation) | NOT IMPLEMENTED | No solar degradation of agents | Direct sunlight breaks down many chemical agents. Agent concentration should decrease faster in daytime CLEAR weather. Model: +solar_degradation when is_day and cloud_cover < 0.5 |
| Temperature inversion trapping | NOT IMPLEMENTED | No inversion detection | Agent trapped below temperature inversion layer reaches 5–10× higher concentration than open-air dispersal. Critical for valley/urban releases at night. Model: if inversion detected, multiply concentration by trapping_factor |
| Surface roughness → mixing height | NOT IMPLEMENTED | Single mixing height for all terrain | Urban terrain has higher surface roughness → lower effective stack height → higher ground-level concentration. Open terrain has lower roughness → better vertical mixing → lower concentration. Model: roughness_length per terrain type |
| Soil absorption of agents | NOT IMPLEMENTED | No ground interaction | Liquid agents pool on ground, creating contact hazard distinct from inhalation. Absorption rate depends on soil porosity. Model: deposition_velocity × concentration → ground_contamination_flux |
| Agent re-aerosolization | NOT IMPLEMENTED | Once deposited, agent is gone | Wind and vehicle traffic can re-aerosolize deposited agents from ground surfaces. Creates secondary hazard hours/days after initial release. Model: re-emission_rate ∝ wind_speed × ground_contamination |

---

### 1.8 Equipment & Materiel Environment Interaction

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Equipment temperature range | DEFINED/UNCALLED | `EquipmentItem.temperature_range = (-40, 50)` defined, `environment_stress()` computes degradation | Degradation factor never applied. Should increase weapon jam rate, electronics failure rate, engine stall probability when temperature outside rated range |
| Propellant temperature → MV | NOT IMPLEMENTED | Constant muzzle velocity | Cold propellant (−20°C): −2 to −5% MV. Hot propellant (+50°C): +1 to +3% MV. Directly affects range. Source: MIL-STD-1474. Model: MV × (1 + temp_coefficient × ΔT) where temp_coefficient ≈ 0.001/°C |
| Lubricant viscosity | NOT IMPLEMENTED | Constant weapon reliability | Cold thickens lubricant → increased malfunction rate. Desert heat thins lubricant → increased wear. Model: reliability_modifier = f(temperature, lubricant_type) |
| Battery capacity at temperature | NOT IMPLEMENTED | Constant electronics availability | Li-ion at −20°C: ~50% capacity. Affects: radio endurance, NVG duration, GPS receiver, UAV flight time. Model: capacity × battery_temp_curve(T) |
| Fuel viscosity/gelling | NOT IMPLEMENTED | Constant fuel availability | Diesel gels at −10 to −20°C without arctic additives. Jet fuel (JP-8) freeze point −47°C. Model: fuel_available = temperature > gel_point |
| Engine performance vs altitude | COMPUTED/UNCONSUMED | `ConditionsEngine.air().density_altitude` exists | Naturally aspirated engines lose ~3% power per 300m altitude. Turbocharged engines less affected. Turbofan thrust decreases linearly above tropopause. Model: power × (1 − altitude_derating × alt/ref_alt) |
| Dust ingestion on engines | NOT IMPLEMENTED | No desert reliability penalty | Sand/dust degrades engine filters → power loss → eventual failure. Desert operations have 3–5× higher maintenance rates. Model: reliability_modifier in dusty terrain |
| Corrosion in maritime environment | NOT IMPLEMENTED | No salt spray effect | Salt air increases equipment failure rate. Extended maritime operations degrade weapons/electronics. Very low priority — long time scale |

---

### 1.9 Human Factors & Environment

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Heat stress / heat casualties | NOT IMPLEMENTED | Temperature has no effect on personnel | WBGT > 32°C (wet-bulb globe temperature) + physical exertion → heat casualties. Model: heat_casualty_rate ∝ f(temperature, humidity, MOPP_level, exertion). MOPP-4 in hot weather can cause 10–20% non-combat casualties per hour |
| Cold injury (frostbite/hypothermia) | NOT IMPLEMENTED | Temperature has no effect on personnel | Wind chill < −25°C with prolonged exposure → cold casualties. Model: cold_casualty_rate ∝ f(wind_chill, exposure_time, clothing_level). Critical for: Chosin Reservoir, Stalingrad, Eastern Front winter |
| Altitude sickness | NOT IMPLEMENTED | No altitude effect on personnel performance | Above 2500m: performance degrades. Above 4000m: incapacitation without acclimatization. Model: performance_modifier = max(0.5, 1 − 0.03 × (altitude − 2500)/100) above 2500m |
| Fatigue from environmental stress | PARTIALLY WIRED | Movement fatigue modeled (speed reduction), not temperature/altitude driven | Temperature extremes and altitude should accelerate fatigue. Model: fatigue_rate × environmental_stress_factor where stress = f(temp_deviation_from_comfort, altitude, MOPP_level) |
| MOPP degradation | PARTIALLY WIRED | MOPP reduces movement speed | Should also reduce: visual detection (hood restricts FOV), manual dexterity (gloves reduce reload speed), communications (mask muffles voice), thermal stress (accelerates heat casualties). Currently only speed reduction |
| Wind chill | NOT IMPLEMENTED | No wind chill calculation | Wind chill = 13.12 + 0.6215T − 11.37V^0.16 + 0.3965TV^0.16. Drives cold injury rate. Model: straightforward formula from T and wind_speed |
| Dehydration in hot environments | NOT IMPLEMENTED | No water consumption model | Hot + dry + high exertion = 1L/hr water consumption. Running out degrades performance → casualties. Mostly a logistics concern, but affects operational tempo |

---

### 1.10 Ballistics Environment Interaction

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Wind deflection on projectile | WIRED | RK4 integrator includes wind velocity vector | — |
| Mach-dependent drag | WIRED | Temperature-dependent speed of sound → Mach → drag multiplier | — |
| Air density at altitude | WIRED (partial) | Exponential atmosphere model used in drag calculation | Should also use pressure and humidity for true density (ideal gas + humidity correction). Currently uses fixed scale-height model |
| Coriolis effect | WIRED (optional) | Earth rotation deflection, gated by flag | — |
| Humidity → drag | NOT IMPLEMENTED | Constant air composition assumed | ~0.5% effect on density; negligible for most weapons, measurable for long-range artillery. Low priority |
| Spin drift (gyroscopic precession) | NOT IMPLEMENTED | No spin-stabilized projectile drift | Rifled projectiles drift ~0.1 mil per 1000m range. Accumulates over long range. Model: drift_angle = spin_drift_constant × range. Low priority — small compared to wind |
| Rain impact on trajectory | NOT IMPLEMENTED | Rain doesn't affect ballistics | Heavy rain creates slight deceleration on slow projectiles (mortar). Negligible for high-velocity rounds. Very low priority |
| DEW thermal blooming | NOT IMPLEMENTED | No self-defocus at high power | High-power laser heats air along beam path → refractive index change → beam spreads. Model: blooming_factor = (1 + power/P_critical × range²/range_ref²). Limits effective DEW range in warm/humid air |
| DEW sea spray attenuation | NOT IMPLEMENTED | No maritime-specific DEW degradation | Sea spray extinction ~10 dB/km vs 0.2 dB/km in clean air. Makes shipboard laser weapons much less effective in high sea states. Model: maritime_extinction = base_extinction + sea_spray_factor(beaufort) |
| DEW dust attenuation | NOT IMPLEMENTED | Dust treated same as rain | Dust is ~10× more attenuating than rain at same precipitation-equivalent. Desert dust storms should severely degrade DEW. Model: dust_extinction = dust_density × mass_extinction_coefficient |
| Rain/fog/dust → DEW atmospheric transmittance | PARTIALLY WIRED | DEW engine accepts humidity/precip_rate parameters | Battle loop **never passes environmental parameters to DEW engine**. The physics model exists — the call site doesn't pass the values |

---

### 1.11 Communications Environment Interaction

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Terrain LOS for comms | WIRED | Diffraction loss (6 dB) when terrain blocks LOS | — |
| Distance path loss | WIRED | Range-dependent link budget | — |
| HF propagation quality | COMPUTED/UNCONSUMED | `EMPropagation.hf_propagation_quality()` computes D-layer/F-layer effects by time of day | Should modulate HF radio reliability. Day: D-layer absorbs → short range only. Night: F-layer reflects → long range (skip propagation). Transforms HF comms from constant-reliability to diurnally-variable |
| Frequency-dependent rain attenuation | NOT IMPLEMENTED | Generic comms model ignores frequency | UHF (300 MHz – 3 GHz): negligible rain loss. SHF (3–30 GHz): 0.1–10 dB/km. EHF (30–300 GHz): severe. SATCOM uplinks (SHF/EHF) should degrade in rain. Model: ITU-R P.838 attenuation per frequency band |
| Radio horizon (altitude-dependent) | NOT IMPLEMENTED | Comms range is fixed | Same 4/3 Earth radius model as radar. Two units at 2m height have ~11 km radio horizon. One at 2m, one at 30m: ~28 km. Mountain-top relay extends dramatically. Model: reuse `radar_horizon()` for comms |
| Altitude → comms range | NOT IMPLEMENTED | No altitude benefit for comms | Higher antenna = longer radio range. Aircraft-to-ground comms have much longer range than ground-to-ground. Should improve comms reliability for airborne C2 nodes |
| Tropospheric ducting for comms | NOT IMPLEMENTED | Only radar ducting modeled | Same physics extends UHF/VHF range in certain weather (warm, humid, maritime). Common in Gulf operations. Model: if ducting_possible, multiply comms_range × duct_extension_factor |

---

### 1.12 Air Combat Environment Interaction

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Weather sortie abort | WIRED | Global weather modifier < 0.3 = abort | — |
| Visibility → WVR Pk | WIRED | < 10 km visibility degrades guns/WVR Pk | — |
| Cloud ceiling | COMPUTED/UNCONSUMED | `ConditionsEngine.air().cloud_ceiling` available | Should gate: CAS operations (need visual contact with ground target), dive bombing (need to see target from altitude), low-level operations (ceiling < 500m forces low-level flight → increased ground fire risk) |
| Icing risk → aircraft performance | COMPUTED/UNCONSUMED | `ConditionsEngine.air().icing_risk` calculated | Wing ice: +15% stall speed, −20% max lift. Engine ice: −10–30% power. Radar dome ice: −3 dB signal loss. Model: if icing_risk > threshold, apply performance penalties + periodic de-ice check |
| Density altitude → performance | COMPUTED/UNCONSUMED | Density altitude calculated | Thin air = longer takeoff, reduced climb rate, lower max speed, reduced helicopter hover ceiling. Model: performance × (ρ/ρ₀) for thrust/lift-dependent parameters |
| Wind → BVR range | NOT IMPLEMENTED | BVR missile range ignores wind | Headwind reduces effective missile range; tailwind extends it. Effect is ~10–15% for strong winds. Model: effective_range = base_range × (1 ± wind_component/missile_speed) |
| Altitude → energy advantage | NOT IMPLEMENTED | Altitude tracked but no energy trading | Higher aircraft has more potential energy → can convert to speed in dive. Lower aircraft must climb (losing speed) to engage. This is fundamental to air combat. Model: energy_state = altitude × g + 0.5 × v² → energy advantage modifier |
| Turbulence → gun accuracy | NOT IMPLEMENTED | Smooth flight assumed | Turbulence degrades gun tracking accuracy. Model: guns_Pk × (1 − turbulence_factor) where turbulence = f(terrain_roughness, wind_speed, altitude_AGL) |

---

### 1.13 Detection Environment Integration Gaps

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Visibility → visual detection | WIRED | Beer-Lambert atmospheric extinction (3.0/visibility) | — |
| Illumination → visual detection | WIRED | Lux multiplier on visual signature | — |
| Thermal contrast → thermal detection | WIRED (indirect) | Uses illumination-based modifier, not physics ΔT | Should use: background_temperature from TimeOfDayEngine vs target thermal signature. ΔT drives thermal detection range. At thermal crossover (dawn/dusk), ΔT → 0 → thermal detection collapses |
| Obscurant opacity → detection | NOT WIRED | ObscurantsEngine has `opacity_at(pos)` but detection never calls it | Should query: visual_opacity and thermal_opacity at target position. Smoke blocks visual (0.9), partially blocks thermal (0.1 standard, 0.8 multispectral), doesn't block radar (0.0) |
| Vegetation density → concealment | NOT WIRED | SeasonsEngine computes, detection ignores | Summer foliage provides concealment (+30% visual signature reduction in forest). Winter bare trees provide much less (+5%). Model: concealment_modifier = base_concealment × vegetation_density |
| Rain → radar detection | NOT WIRED | `_compute_rain_detection_factor()` exists in battle.py but never called | Rain creates radar clutter that masks targets. Already implemented with ITU-R P.838 model. Just needs call site in detection flow |
| Convergence zones → sonar | NOT WIRED | `convergence_zone_ranges()` computed | Should create detection "rings" at 55km intervals. Target between CZ ranges is in acoustic shadow. Within CZ range, detection probability spikes. Fundamental to deep-water ASW |
| Thermocline → sonar | NOT WIRED | Thermocline depth computed | Submarine below thermocline is very hard to detect from surface sonar (+20 dB loss). Surface ship sonar can't reliably detect deep targets. Model: if target_depth > thermocline_depth, add layer_loss to transmission |
| Sea state → radar clutter | NOT IMPLEMENTED | No sea surface clutter model | Radar returns from waves mask surface targets (sea clutter). Higher sea state = worse clutter. Model: clutter_noise ∝ σ₀(beaufort) × resolution_cell_area. Affects both air defense (low-flying targets) and naval radar |
| NVG → night detection | COMPUTED/UNCONSUMED | `nvg_effectiveness()` computed | NVG-equipped units should have enhanced night detection (visual modifier recovery from 0.2 to ~0.6). Currently only affects movement speed (0.7x recovery), not detection range |

---

### 1.14 Logistics & Transport Environment Interaction

| Parameter | Status | Current State | What Should Happen |
|-----------|--------|---------------|-------------------|
| Mud speed fraction | DEFINED/UNCALLED | `transport.py` has `mud_speed_fraction=0.5` | Never applied in battle-loop movement. Should slow logistics convoys by 50% in muddy conditions. Currently only MovementEngine queries ground_trafficability, not transport |
| Snow speed fraction | DEFINED/UNCALLED | `transport.py` has `snow_speed_fraction=0.7` | Same as mud — defined but never applied |
| Airlift weather gate | WIRED | Ceiling < 500m cancels airlift | — |
| Road condition degradation | NOT IMPLEMENTED | Roads have fixed speed bonus | Heavy rain/freeze-thaw should degrade unpaved roads. Paved roads unaffected by weather but blocked by snow/ice until cleared. Model: road_speed = base_speed × weather_condition_factor |
| Supply route terrain effects | NOT IMPLEMENTED | Supply routing uses networkx shortest path with fixed costs | Route costs should reflect current terrain conditions (flooded bridge, muddy road, snow-blocked pass). Dynamic edge costs from SeasonsEngine |
| Aircraft wind limits for cargo | NOT IMPLEMENTED | No crosswind gate for fixed-wing | Crosswind > 15 knots limits transport aircraft operations. Model: abort if crosswind > aircraft_crosswind_limit |

---

### 1.15 Scenario Environment Configuration Gaps

| Parameter | Status | What Should Be Configurable |
|-----------|--------|-----------------------------|
| Starting weather state | PARTIALLY WIRED | `weather_conditions.precipitation` maps to state. Should also allow explicit `weather_state: FOG` |
| Starting time of day | WIRED | `start_time` in scenario YAML sets datetime | — |
| Starting season | NOT CONFIGURABLE | Season derived from date, but SeasonsEngine ground state starts fresh (no prior accumulation) | Should allow: `season_override: {ground_state: SATURATED, mud_depth: 0.3}` for historical accuracy (Passchendaele mud, Eastern Front rasputitsa) |
| Latitude for astronomy | PARTIALLY WIRED | Derived from scenario map center | Should ensure all scenarios have proper latitude for solar/lunar calculations |
| Pre-placed smoke/fog | NOT IMPLEMENTED | No scenario YAML field | `environment_config.obscurants: [{type: FOG, center: [x,y], radius: 5000}]` |
| Pre-placed minefields | NOT IMPLEMENTED | No scenario YAML field | `environment_config.minefields: [{type: CONTACT, center: [x,y], density: 0.01}]` |
| Sea state initialization | NOT WIRED | `sea_state` field in some scenario YAMLs but not passed to SeaStateEngine | Should initialize SeaStateEngine wind/wave conditions from scenario |
| Terrain condition overrides | NOT IMPLEMENTED | All terrain starts at default | Should allow: roads destroyed, bridges blown, areas flooded, terrain pre-cratered |

---

## Theme 2: Core Combat Integration (Priority: Highest — P0 Bugs)

These are not missing features — they are bugs. Existing code computes results that are silently discarded, engagement types are declared but never routed, and fundamental logistics gates are absent.

### 2.1 Air Combat Routing — 3 Engines With Wrong Physics

**Problem**: Air-to-air, air-to-ground, and SAM engagements all route through the generic `DIRECT_FIRE` path, which applies ground combat physics (range-dependent Pk with terrain modifiers). Three purpose-built engines (AirCombatEngine, AirGroundEngine, AirDefenseEngine) with correct domain physics exist but are unreachable because `_infer_engagement_type()` never assigns `AIR_TO_AIR`, `AIR_TO_GROUND`, or `SAM`.

**Fix**: Update `_infer_engagement_type()` to detect attacker/target domain combinations and assign the correct EngagementType. Route each type to its respective engine. This is routing logic only — the engines are fully implemented.

**Impact**: Every air engagement in every scenario changes from ground-combat Pk to proper air combat Pk. Expect significant recalibration.

### 2.2 Damage Detail — Computed Then Discarded

**Problem**: `DamageEngine.resolve_damage()` returns a `DamageResult` with 6 fields. Only `damage_fraction` is read — everything else (casualties, systems_damaged, fire_started, ammo_cookoff, penetrated) is discarded. Units are binary: 100% combat power until destroyed/disabled.

**Fix**: Extract and apply each field. Casualties reduce personnel count. Systems_damaged degrade specific equipment. Fire_started triggers fire zone creation. Ammo_cookoff applies secondary explosion to nearby units. Penetrated degrades armor for subsequent hits.

**Impact**: Graduated degradation replaces binary threshold. A tank with damaged optics has reduced detection. A unit with 30% casualties has reduced firepower. Fires create persistent battlefield obstacles.

### 2.3 Posture Protection — DUG_IN Does Nothing

**Problem**: DUG_IN units take the same casualties as units standing in the open. The only effect is speed=0 (they don't move). Terrain cover provides some protection, but posture itself provides zero damage reduction.

**Fix**: Apply posture damage reduction multiplier: DEFENSIVE ~20%, DUG_IN ~50%, FORTIFIED ~70%. These map to hasty fighting position, prepared position, and hardened position respectively. Values configurable via CalibrationSchema.

**Impact**: Defensive operations become viable. Currently the only winning strategy is attack (defender has no defensive advantage beyond not moving).

### 2.4 Logistics Gates — Units Fight Without Resources

**Problem**: Units with 0 fuel still move. Units with 0 ammo still fire. Movement doesn't consume fuel. Logistics is tracked and reported but never constrains combat.

**Fix**: Check ammo > 0 before `weapon.fire()`. Check fuel > 0 before movement execution. Consume fuel proportional to distance × consumption_rate during movement.

**Impact**: Logistics becomes consequential. Cutting supply lines degrades enemy combat power. Long advances require fuel resupply. Ammo conservation becomes a real concern.

*(All Phase 58 deliverables)*

---

## Theme 3: C2 Friction (Priority: High)

Three C2 engines (~1,400 lines total) are fully implemented but disconnected. Wiring them creates realistic command friction — orders take time, get misunderstood, and planning delays create windows of vulnerability.

### 3.1 Order Propagation — Delay & Misinterpretation

**Current state**: OrderPropagationEngine (315 lines) computes:
- Propagation delay: `base_time(echelon) × type_mult × priority_mult × staff_mult + lognormal_noise`
  - Platoon: ~5 min base, Division: ~2 hr base
  - FRAGO: 0.33x, WARNO: 0.1x, OPORD: 1.0x
  - FLASH priority: 0.1x, ROUTINE: 1.0x
- Misinterpretation probability: `base × (1 − staff_eff) × (1 − comms_quality)`
- Comms availability check (can order physically reach recipient?)

**Wiring needed**:
- When AI commander issues orders (OODA DECIDE phase), route through OrderPropagationEngine instead of instant execution.
- Delayed orders queue with scheduled delivery time.
- On delivery, roll for misinterpretation — misunderstood orders execute with modified parameters (wrong objective, wrong timing).
- If comms are down (comms engine reports no path), order fails entirely.

**Impact**: Creates Clausewitzian friction. Surprise attacks succeed because defenders can't reorganize quickly. Comms degradation (EW jamming, courier intercept) becomes tactically meaningful.

**Design consideration**: Must be opt-in per scenario (`enable_order_propagation: true`) to avoid breaking existing scenarios that assume instant C2.

### 3.2 Planning Process — MDMP Delays

**Current state**: PlanningProcessEngine (564 lines) implements:
- Planning phases: RECEIVING_MISSION → ANALYZING → DEVELOPING_COA → COMPARING → APPROVING → ISSUING_ORDERS
- Method selection: INTUITIVE (fast, low echelon) vs MDMP (slow, thorough, high echelon)
- 1/3-2/3 rule: Commander uses 1/3 of available time for planning, subordinates get 2/3
- Phase durations scaled by method speed multipliers

**Wiring needed**:
- When OODA cycle reaches DECIDE, check if a planning process is already underway.
- If not, initiate planning with duration based on echelon and method.
- Commander cannot issue new orders until planning completes.
- Higher-quality planning (MDMP) produces better COA evaluation scores.

**Impact**: Creates realistic planning tempo. Low-echelon units (company) can react in minutes. Division-level changes take hours. OODA speed becomes a real differentiator between doctrinal schools (Maneuver warfare has faster planning loops).

**Design consideration**: Planning delays interact with order propagation delays — total C2 latency = planning time + propagation time. Must not create unplayable stalls for the AI.

### 3.3 Air Tasking Order Management

**Current state**: ATOPlanningEngine (459 lines) implements:
- Aircraft registration with availability tracking (mission-capable, sortie limits, turnaround times)
- ATO generation from CAS/strike requests with priority ordering
- Sortie counting and reserve management
- Publishes ATOGeneratedEvent

**Wiring needed**:
- Register all aerial units with ATOPlanningEngine at scenario start.
- CAS requests from ground commanders route through ATO queue.
- Air missions allocated from available aircraft pool (not unlimited).
- Turnaround time enforced between sorties.
- ATO published periodically (default every 12 hours in modern era, shorter for close air support).

**Impact**: Air support becomes a finite resource. Multiple requests compete for limited aircraft. Attrition of aircraft reduces future sortie capacity. Creates realistic air campaign pacing.

---

## Theme 4: Stratagem & Unconventional Completion (Priority: High)

### 4.1 Stratagem Activation

**Current state**: StratagemEngine (416 lines) evaluates eligibility for 9 stratagem types but never activates them. `evaluate_concentration_opportunity()` and `evaluate_deception_opportunity()` are called in battle.py but `activate_stratagem()` is not.

**Wiring needed**:
- When eligibility evaluation passes, create a stratagem plan and activate it.
- Each stratagem type produces effects:
  - CONCENTRATION: +8% force effectiveness at Schwerpunkt
  - DECEPTION: Enemy AI receives false force disposition estimates
  - FEINT: Enemy AI commits reserves to feint axis
  - ECONOMY_OF_FORCE: Reduced force can hold secondary sector
  - SURPRISE: First-engagement bonus (defender has no prepared positions)
- Effects modulate combat modifiers for the duration of the stratagem.

**Impact**: AI commanders can employ stratagems as force multipliers. Concentration at the decisive point becomes a real mechanic (Austerlitz, 73 Easting envelopment).

### 4.2 Unconventional Warfare Engine

**Current state**: UnconventionalWarfareEngine (397 lines) implements IED, guerrilla tactics, and human shields. Never called.

**Wiring needed**:
- Route INSURGENT/MILITIA unit engagements through unconventional engine.
- IED encounters triggered by movement through insurgent-controlled areas.
- Guerrilla hit-and-run: attack then disengage before response.
- Human shield mechanics: reduce casualty Pk when civilian population present.

**Impact**: Hybrid Gray Zone scenario becomes meaningful. Insurgency dynamics (Phase 24e) can produce IED events. Afghan/Iraq-style asymmetric warfare.

### 4.3 Mine Warfare Completion

**Current state**: MineWarfareEngine (541 lines) resolves mine encounters but cannot lay mines. Ships can hit pre-placed mines but nobody places them.

**Wiring needed**:
- `lay_mines()` callable by naval units with mine-laying capability.
- Minefield persistence on the map as hazard zones.
- Mine sweeping operations by minesweeper units.
- Scenario YAML support for pre-placed minefields.

**Impact**: Naval blockade scenarios gain teeth. Suez Canal, Persian Gulf, WW2 Channel/Baltic mine warfare.

---

## Theme 5: Space & EW Sub-Engine Activation (Priority: Medium)

Five space engines (~1,400 lines) and two EW engines (~760 lines) are instantiated but never called. These are complete implementations with sophisticated physics models.

### 5.1 Space ISR — Satellite Reconnaissance

**SpaceISREngine** (206 lines): Checks satellite overpasses, resolution-dependent target detection (vehicle <0.5m, company <5m, battalion <15m), cloud cover blocks optical but not SAR.

**Wiring**: Call `check_overpass()` each tick. On overpass, generate ISR reports that feed into FogOfWarManager (reveal enemy formations to the side with satellite access). Cloud cover from WeatherEngine gates optical sensors.

**Impact**: Strategic-level intelligence. Side with satellite advantage sees enemy disposition updates every ~90 minutes. GPS-denied environments (EW jamming) degrade positioning.

### 5.2 Early Warning — BMD Cueing

**EarlyWarningEngine** (143 lines): Detects ballistic missile launches via GEO/HEO early warning satellites. 30-90s detection delay, computes usable warning time.

**Wiring**: When a ballistic missile is fired (engagement type BALLISTIC_MISSILE), check if early warning satellites detect the launch. If detected, publish warning event that can trigger air defense interceptors.

**Impact**: Nuclear/ballistic missile scenarios gain defensive layer. Korean Peninsula (THAAD defense) and space scenarios become more realistic.

### 5.3 ASAT — Anti-Satellite Warfare

**ASATEngine** (353 lines): 4 ASAT weapon types (kinetic kill, co-orbital, ground laser dazzle, ground laser destruct). Debris cascade (Kessler syndrome). Kinetic Pk model.

**Wiring**: Route ASAT engagements through ASATEngine. Destroyed satellites removed from ConstellationManager (affects GPS, ISR, SATCOM, early warning). Debris cascade can degrade entire orbital bands.

**Impact**: Space warfare becomes consequential. Destroying enemy GPS constellation degrades their precision weapons. Kessler cascade can deny LEO to both sides.

### 5.4 SIGINT — Signals Intelligence

**SIGINTEngine** (488 lines): ELINT (radar parameter capture), COMINT (comms intercept), traffic analysis. AOA/TDOA geolocation. Intercept probability from SNR.

**Wiring**: Call `attempt_intercept()` when enemy units emit (radar, comms). Successful intercepts produce geolocation reports feeding FogOfWarManager. Traffic analysis reveals activity levels (enemy massing forces detectable via comms surge).

**Impact**: EW-capable forces can passively detect enemy radars and comms. SEAD targeting improves (find the SAM radar, then shoot HARM at it). Intelligence fusion between SIGINT + Space ISR + ground sensors.

### 5.5 ECCM — Electronic Protection

**ECCMEngine** (270 lines): 4 ECCM techniques (frequency hop, spread spectrum, sidelobe blanking, adaptive nulling) with J/S reduction calculations.

**Wiring**: When EW jamming is computed, query ECCMEngine for target's ECCM suite. Subtract ECCM reduction from jammer J/S ratio. Units with good ECCM resist jamming better.

**Impact**: Creates asymmetry between advanced forces (NATO ECCM vs Soviet-era radar) and legacy systems. EW scenarios become more nuanced (not just "jammer wins").

---

## Theme 6: Cross-Module Feedback Loops (Priority: High)

These are the systemic integration gaps where one module's output should drive another module's behavior but currently doesn't. The build-then-defer pattern created modules that publish state changes as events but no module subscribes to act on them.

### 6.1 Detection → AI Assessment

**Problem**: AI assessment receives `enemy_unit_count` (raw ground truth) instead of querying FogOfWarManager for detected contacts with confidence levels. A side with zero sensors sees enemies perfectly.

**Fix**: When FOW is enabled, AI assessment reads `fow_manager.get_contacts(side)` — gets detected count, estimated strength, confidence. Assessment quality degrades with poor sensor coverage (fewer contacts, lower confidence → worse decisions). When FOW is disabled, behavior unchanged (backward compatible).

### 6.2 Medical → Unit Strength

**Problem**: MedicalEngine publishes `CasualtyTreatedEvent` and `ReturnToDutyEvent` but nobody subscribes. Treated casualties never return to duty — units stay permanently depleted.

**Fix**: Subscribe to RTD events. On receipt, increment unit personnel count (capped at original strength). Medical capacity (M/M/c queue) gates throughput — more medical assets = faster RTD.

### 6.3 Maintenance → Readiness

**Problem**: MaintenanceEngine publishes `EquipmentBreakdownEvent` and `MaintenanceCompletedEvent`. Nobody subscribes. Broken equipment continues functioning.

**Fix**: Subscribe to breakdown events. Reduce unit weapon/sensor count based on equipment lost. Subscribe to maintenance completed events. Restore capability. Units with >30% equipment broken marked DEGRADED (reduced Pk, reduced movement).

### 6.4 Checkpoint State Registration

**Problem**: `CheckpointManager.register()` is never called in production. Checkpoints save only clock + RNG state. Restoring a checkpoint produces correct time with wrong morale, wrong detection tracks, wrong supply levels, wrong equipment condition.

**Fix**: Register all stateful modules: morale state, detection tracks, supply levels, equipment condition, weather state, OODA phase, escalation level. Verify round-trip: save → restore → continue produces identical outcomes.

### 6.5 MISSILE Engagement Routing

**Problem**: `MISSILE` EngagementType is declared but never assigned by `_infer_engagement_type()`. MissileEngine computes flight phases and terminal guidance but is never invoked. Missiles route as DIRECT_FIRE (instant hit, wrong physics).

**Fix**: Assign MISSILE type for guided missile engagements (ATGM, HARM, cruise missile). Route through MissileEngine. Wire MissileDefenseEngine for intercept attempts. Flight time creates engagement delay (realistic missile time-of-flight).

### 6.6 Comms → C2 Degradation

**Problem**: Comms degradation (from EW jamming, terrain blockage, range limits) affects assessment confidence score but doesn't constrain what units can do. A unit with zero comms fights identically to one with perfect comms.

**Fix**: Below `c2_min_effectiveness` threshold, unit reverts to last received orders. No new targeting assignments, no posture changes, no disengagement. Creates realistic "comms loss = fight in place" behavior. Feeds Phase 64's order propagation failure probability.

*(All Phase 63 deliverables)*

---

## Theme 7: Code Cleanup & Dead Field Resolution (Priority: Low)

### 7.1 ConditionsEngine Disposition

**Current state**: 249-line facade that aggregates all environment sub-engines into domain-specific query methods (`land()`, `air()`, `maritime()`, `acoustic()`, `electromagnetic()`). Never instantiated.

**Recommendation**: Instantiate as optional convenience facade. Don't refactor existing code. New Block 7 wiring can use it where aggregated queries are cleaner.

### 7.2 Dead YAML Field Resolution

| Field | Action | Rationale |
|-------|--------|-----------|
| `weight_kg` | Keep, document as "data-only" | Useful for scenario documentation; future weight-of-fire calculations |
| `propulsion` | Wire to drag model | Rocket/turbojet/ramjet propulsion types should affect missile kinematics and altitude performance |
| `unit_cost_factor` | Keep, document as "data-only" | Future logistics cost modeling |
| `data_link_range` | Wire to C2 | UAV data link range should gate C2 effectiveness beyond range |

### 7.3 SimulationContext Stubs

### 7.4 P4 Dead Code Removal

Remove computed values with no meaningful consumer to clean up false audit findings:
- `TimeOfDayEngine.shadow_azimuth` — no consumer, not useful at simulation scale
- `TimeOfDayEngine` solar/lunar contribution decomposition — diagnostic data, only total lux matters
- `UnderwaterAcoustics.deep_channel_depth` — SOFAR channel is extremely niche (fixed sonobuoy networks only)

*(All Phase 66 deliverables)*

Remove TODO comments for engines that are instantiated (SeasonsEngine, ObscurantsEngine, ConditionsEngine).

---

## Comprehensive Inventory: Computed But Unconsumed Parameters

This is the definitive list of values that environment engines calculate every tick but that no downstream system reads. Each of these represents wasted computation and missing fidelity.

| Engine | Parameter | Consumers That Should Use It |
|--------|-----------|------------------------------|
| **SeasonsEngine** | `mud_depth` | MovementEngine (wheeled penalty), logistics transport |
| **SeasonsEngine** | `snow_depth` | MovementEngine (all-unit penalty), infrastructure (road degradation) |
| **SeasonsEngine** | `vegetation_density` | DetectionEngine (seasonal concealment), fire spread probability |
| **SeasonsEngine** | `vegetation_moisture` | Fire zone creation (wet = no ignition), CBRN agent persistence |
| **SeasonsEngine** | `sea_ice_thickness` | MovementEngine (ice crossing), naval movement (ice navigation) |
| **SeasonsEngine** | `wildfire_risk` | Fire zone system (spontaneous ignition probability) |
| **SeasonsEngine** | `daylight_hours` | Operational planning, fatigue rate |
| **SeaStateEngine** | `wave_period` | Ship resonance roll, helicopter deck landing |
| **SeaStateEngine** | `tidal_current_speed` | Ship movement, mine drift, submarine station-keeping |
| **SeaStateEngine** | `tidal_current_direction` | Same as speed |
| **SeaStateEngine** | `beaufort_scale` | Small craft operations gate, deck operations gate, sea clutter |
| **UnderwaterAcoustics** | `surface_duct_depth` | Sonar detection (in-duct enhancement, below-duct shadow) |
| **UnderwaterAcoustics** | `thermocline_depth` | Sonar detection (+20 dB loss for targets below layer) |
| **UnderwaterAcoustics** | `deep_channel_depth` | SOFAR channel long-range detection |
| **UnderwaterAcoustics** | `convergence_zone_ranges` | Sonar detection rings at 55km intervals |
| **EMPropagation** | `radar_horizon()` | Air defense detection range gate (Earth curvature) |
| **EMPropagation** | `free_space_path_loss()` | Comms range, radar range, EW intercept range |
| **EMPropagation** | `atmospheric_attenuation()` | Radar/comms degradation in rain/humidity |
| **EMPropagation** | `ducting_possible` + `duct_height` | Radar/comms range extension in warm humid maritime |
| **EMPropagation** | `hf_propagation_quality()` | HF radio reliability (day/night D-layer/F-layer) |
| **WeatherEngine** | `wind.gust` | Helicopter ops, bridge-laying, parachute drops, amphibious small craft |
| **WeatherEngine** | `pressure` | Air density (ideal gas), altimeter accuracy |
| **TimeOfDay** | `background_temperature` | Thermal detection SNR (target vs background ΔT) |
| **TimeOfDay** | `crossover_in_hours` | Thermal detection vulnerability window (ΔT → 0) |
| **TimeOfDay** | `shadow_azimuth` | Visual detection angle dependency |
| **TimeOfDay** | `nvg_effectiveness()` | Night detection range for NVG-equipped units |
| **Terrain** | `vegetation_height` | LOS check (ground-level vegetation blocks), helicopter clearance |
| **Terrain** | `combustibility` | Fire zone ignition probability |
| **Obstacles** | `traversal_risk` | Casualty probability during crossing |
| **Obstacles** | `traversal_time_multiplier` | Movement delay through obstacles |
| **Hydrography** | `is_fordable()`, `ford_points_near()` | River crossing at ford points with time cost |
| **Infrastructure** | `Bridge.capacity_tons` | Heavy vehicle weight gate |
| **Infrastructure** | `Road.speed_factor` override | Per-road speed instead of hardcoded table |
| **Equipment** | `temperature_range` + `environment_stress()` | Weapon jam rate, electronics failure rate |
| **Battle.py** | `_compute_rain_detection_factor()` | Radar detection probability in rain (ITU-R P.838) — **function exists, never called** |
| **DEW Engine** | humidity/precip_rate parameters | Atmospheric transmittance — **accepts params, battle loop never passes them** |

**Total: 36 unconsumed parameters across 11 engines. ~4,500 lines of computation producing values nobody reads.**

---

## Proposed Phase Structure

### Phase 58: Structural Verification & Core Combat Wiring

**Focus**: Create structural verification tests that prevent future regression, then fix all P0 combat integration bugs — air combat routing, damage detail extraction, posture protection, and logistics gates. These are the highest-impact items: existing code that should work but doesn't.

**Why first**: Structural tests must exist *before* wiring begins so that every subsequent phase runs against automated audits. P0 combat items affect every engagement and are the most impactful single changes in this block.

**Deliverables**:

*Structural Verification Tests (run continuously from here forward):*
- **Unconsumed parameter audit**: Instrument engine classes, run representative scenario, assert no property written but never read (allowlist for P4 items)
- **Dead method audit**: AST-parse all source files, verify every public engine method has at least one external caller (beyond tests)
- **Event subscription audit**: Verify every published event type has at least one functional subscriber (beyond Recorder) or is in OBSERVATION_ONLY allowlist
- **Engagement routing completeness**: Every EngagementType enum value is assignable by `_infer_engagement_type()` and has a resolution handler
- **Feedback loop verification**: Depleted ammo prevents firing, depleted fuel prevents movement, DUG_IN reduces damage, checkpoint round-trips all state

*Air Combat Routing (P0):*
- Wire `AIR_TO_AIR` EngagementType → AirCombatEngine (BVR + WVR physics, not ground combat Pk)
- Wire `AIR_TO_GROUND` EngagementType → AirGroundEngine (CAS/strike Pk model with altitude, dive angle, CEP)
- Wire `SAM` EngagementType → AirDefenseEngine (missile Pk with engagement envelope, ECM effects)
- Update `_infer_engagement_type()` to assign these types based on attacker/target domain (AIR vs GROUND/NAVAL)

*Damage Detail Extraction (P0):*
- Extract `DamageResult.casualties` → reduce unit personnel count (not just damage_fraction threshold)
- Extract `DamageResult.systems_damaged` → degrade specific equipment on unit (weapon destroyed, sensor damaged)
- Extract `DamageResult.fire_started` → trigger fire zone creation at target position (feeds Phase 60 fire system)
- Extract `DamageResult.ammo_cookoff` → secondary explosion damage to nearby units
- Extract `DamageResult.penetrated` → armor degradation (reduced protection on subsequent hits)

*Posture Protection (P0):*
- `DEFENSIVE` → ~20% damage reduction (hasty fighting position)
- `DUG_IN` → ~50% damage reduction (prepared position)
- `FORTIFIED` → ~70% damage reduction (hardened position)
- Protection applied as multiplier on incoming damage_fraction before threshold comparison
- CalibrationSchema fields for posture protection values (per-scenario tuning)

*Logistics Gates (P0):*
- Ammo depletion → weapon cannot fire (check remaining rounds before `weapon.fire()`)
- Fuel depletion → unit cannot move (check fuel > 0 before movement execution)
- Fuel consumption by movement (distance × consumption_rate → fuel drawdown)

**Tests**: ~55-65

### Phase 59: Atmospheric & Ground Environment Wiring

**Focus**: Wire all computed-but-unconsumed atmospheric and ground parameters. Make seasons, weather, and terrain fully contribute to movement, detection, and combat.

**Deliverables**:
- **Seasons → Movement**: Mud depth penalty (wheeled vs tracked differentiation), snow depth penalty, ice crossing (weight-dependent), vegetation speed penalty through dense terrain
- **Seasons → Detection**: Vegetation density as seasonal concealment modifier, vegetation height for ground-level LOS
- **Seasons → Infrastructure**: Snow depth degrades road speed bonus, frozen water bodies traversable
- **Weather → Ballistics**: Pressure + humidity → true air density (ideal gas law correction), temperature lapse rate at altitude
- **Weather → Operations**: Wind gust threshold for helicopter/parachute/bridge-laying abort, high wind halt for infantry
- **Equipment → Reliability**: Wire temperature_range stress → weapon jam rate, electronics failure
- **Terrain → Movement**: Wire obstacle traversal_risk and traversal_time, ford crossing with depth/current, bridge capacity gate
- **Propellant temperature**: MV modifier from ambient temperature (MIL-STD-1474)

**Tests**: ~45-55

### Phase 60: Obscurants, Fire, & Visual Environment

**Focus**: Instantiate and wire ObscurantsEngine. Create fire zone system linked to Phase 58's damage detail extraction (fire_started). Wire all visual/thermal environment parameters.

**Deliverables**:
- **ObscurantsEngine instantiation**: Create on SimulationContext, call update() each tick
- **Smoke from combat**: Artillery/mortar impacts spawn smoke clouds, drift with wind, decay (30min half-life)
- **Dust from movement**: Vehicles on dry terrain spawn dust trails (signature enhancement + LOS degradation)
- **Fog auto-generation**: Weather FOG state triggers ObscurantsEngine fog deployment
- **Smoke/fog → Detection**: `opacity_at(pos)` degrades visual/thermal detection SNR per spectral blocking table
- **Smoke/fog → Combat**: Obscurant between attacker/target reduces Pk for visual/thermal-guided weapons
- **Thermal environment wiring**: Background temperature + target temp → true ΔT for thermal detection. Crossover vulnerability windows
- **NVG → detection**: NVG-equipped units get night detection range recovery (not just movement)
- **Fire zones**: Wire IncendiaryDamageEngine (P1). fire_started from DamageResult (Phase 58) triggers fire zone creation. Fire produces smoke (feeds ObscurantsEngine). Fire blocks movement. Fire decays when fuel (vegetation) exhausted
- **Combustibility wiring**: Terrain combustibility gates fire ignition probability
- **Scenario YAML**: `environment_config` for pre-placed smoke/fog zones, season/ground state overrides
- **Artificial illumination**: Flare events that temporarily raise illumination in area

**Tests**: ~45-55

### Phase 61: Maritime, Acoustic, & EM Environment

**Focus**: Wire all maritime, underwater acoustic, and electromagnetic propagation parameters. Wire CarrierOpsEngine (P1) for naval air operations.

**Deliverables**:
- **Sea state → ship movement**: Beaufort-dependent speed penalty (small craft more affected)
- **Sea state → carrier ops**: Launch/recovery gate by Beaufort scale
- **CarrierOpsEngine wiring (P1)**: CAP station management, recovery windows, sortie tracking for carrier-based aircraft
- **Sea state → small craft**: Amphibious landing craft casualty risk + speed penalty in high seas
- **Sea state → radar**: Sea clutter model masking surface targets
- **Swell direction**: Roll factor from wave direction vs ship heading
- **Tidal current → movement**: Ship speed adjustment (with/against), mine drift, submarine station-keeping
- **Wave period → ship resonance**: Roll amplitude when wave period matches hull natural frequency
- **Acoustic wiring**: Surface duct detection enhancement/shadow, thermocline layer loss (+20 dB), convergence zone detection rings at 55km intervals
- **Radar horizon**: Gate air defense detection by 4/3 Earth curvature model
- **EM ducting**: Extend radar range in warm/humid maritime conditions
- **Atmospheric attenuation**: Frequency-dependent rain loss for radar and comms
- **HF propagation**: Wire hf_quality → comms reliability (day/night D-layer/F-layer)
- **Radio horizon**: Altitude-dependent comms range using same 4/3 Earth model
- **DEW wiring**: Pass humidity/precip_rate/dust to DEW engine (call site fix), sea spray attenuation, dust distinction from rain
- **Rain detection**: Wire existing `_compute_rain_detection_factor()` call site in battle loop

**Tests**: ~50-60

### Phase 62: Human Factors, CBRN, & Air Combat Environment

**Focus**: Environmental effects on personnel, CBRN-environment interaction, and air domain environmental coupling.

**Deliverables**:
- **Heat stress**: WBGT model for heat casualties (temperature × humidity × MOPP level × exertion)
- **Cold injury**: Wind chill formula + exposure time → cold casualty rate
- **MOPP degradation**: Beyond speed — reduce FOV (detection), dexterity (reload speed), voice clarity (comms quality)
- **Altitude sickness**: Performance degradation above 2500m
- **Environmental fatigue**: Temperature/altitude stress accelerates fatigue accumulation
- **CBRN rain washout**: Precipitation scavenges airborne agents (exponential washout)
- **CBRN temperature persistence**: Arrhenius agent decay rate (nerve agent half-life 2hr at 40°C vs 24hr at 0°C)
- **CBRN inversion trapping**: Temperature inversion detection → 5-10x concentration multiplier
- **CBRN UV degradation**: Solar radiation breaks down agents in daylight
- **Air combat: cloud ceiling gate**: CAS/dive bombing requires visual contact below ceiling
- **Air combat: icing penalties**: Wing ice, engine ice, radar dome ice degradation
- **Air combat: density altitude**: Engine thrust/lift penalties at high altitude + hot temperature
- **Air combat: wind → BVR range**: Headwind/tailwind modifies missile effective range
- **Air combat: altitude energy advantage**: Higher aircraft gets energy_state modifier in engagement

**Tests**: ~40-50

### Phase 63: Cross-Module Feedback Loops

**Focus**: Wire all P1 cross-module integration gaps — the feedback loops where one system's output should drive another system's behavior but currently doesn't. This phase closes the systemic build-then-defer-wiring pattern.

**Deliverables**:

*Detection → AI (P1):*
- AI assessment reads FOW contacts (detected count, estimated strength, confidence) instead of ground truth enemy count
- When `enable_fog_of_war` is True, AI assessment quality degrades with sensor coverage gaps
- When FOW is disabled, behavior is unchanged (backward compatible)

*Medical → Strength (P1):*
- `ReturnToDutyEvent` consumption: treated casualties restore to unit personnel count
- `CasualtyTreatedEvent` consumption: track treatment pipeline (triage → treatment → RTD)
- Medical capacity limits (M/M/c queue) gate RTD throughput

*Maintenance → Readiness (P1):*
- `EquipmentBreakdownEvent` consumption: broken equipment reduces unit combat power (weapon count, sensor availability)
- `MaintenanceCompletedEvent` consumption: repaired equipment restores capability
- Maintenance state feeds readiness: units with >30% equipment broken are DEGRADED (reduced Pk, reduced movement)

*Checkpoint State Registration (P1):*
- Register all stateful modules with CheckpointManager: morale state, detection tracks, supply levels, equipment condition, weather state, OODA phase, escalation level
- Checkpoint round-trip test: save → restore → continue produces identical outcomes to uninterrupted run
- Prioritize modules with expensive state (detection tracks, PRNG streams, morale matrices)

*MISSILE Engagement Routing (P1):*
- Wire `MISSILE` EngagementType → MissileEngine (flight phase + terminal guidance)
- Wire MissileDefenseEngine → intercept attempts (launch-on-detect or launch-on-warning)
- Missile flight time creates engagement delay (not instant hit like DIRECT_FIRE)

*Comms → C2 (P1):*
- Comms loss (from EW jamming, terrain LOS, range) degrades C2 effectiveness below `c2_min_effectiveness`
- Units with zero comms revert to last received orders (no new targeting, no posture changes)
- Comms degradation feeds order propagation failure probability (Phase 64)

**Tests**: ~40-50

### Phase 64: C2 Friction & Command Delay

**Focus**: Wire the three dormant C2 engines to create realistic command friction. Builds on Phase 63's comms → C2 degradation wiring.

**Deliverables**:
- OrderPropagationEngine → OODA cycle (order delay + misinterpretation + comms check)
- PlanningProcessEngine → OODA DECIDE phase (planning duration before order issue)
- ATOPlanningEngine → air operations (sortie management, CAS request queue)
- StratagemEngine full activation (9 stratagem types with combat effects)
- C2 friction opt-in flag (`enable_c2_friction: true` in scenario YAML)
- Environmental coupling: comms weather degradation → order propagation failure
- Environmental coupling: HF day/night quality → comms reliability → C2 latency

**Tests**: ~35-45

### Phase 65: Space & EW Sub-Engine Activation

**Focus**: Wire the five dormant space engines and two dormant EW engines.

**Deliverables**:
- SpaceISREngine → FogOfWarManager (satellite ISR passes reveal formations)
- EarlyWarningEngine → air defense (BMD cueing from early warning satellites)
- ASATEngine → space warfare (satellite destruction, debris cascade, constellation degradation)
- SIGINTEngine → FogOfWarManager (emitter geolocation, traffic analysis)
- ECCMEngine → EW jamming loop (ECCM J/S reduction)
- Space sub-engine delegation verified end-to-end

**Tests**: ~35-45

### Phase 66: Unconventional, Naval, & Cleanup

**Focus**: Wire remaining dormant engines and clean up dead code.

**Deliverables**:
- UnconventionalWarfareEngine → battle routing (IED, guerrilla, human shields)
- MineWarfareEngine completion (mine laying, minefield persistence, sweeping, scenario YAML minefields)
- SiegeEngine → campaign loop (P2 — ancient/medieval siege mechanics)
- AmphibiousAssaultEngine → naval ops (P2 — beach assault state machine)
- ConditionsEngine instantiation (optional facade)
- Dead YAML field resolution (wire `propulsion` → drag model, `data_link_range` → C2 range gate)
- P4 dead code removal (shadow_azimuth computation, solar/lunar decomposition, deep_channel_depth)
- SimulationContext stub cleanup

**Tests**: ~30-35

### Phase 67: Integration Validation & Recalibration

**Focus**: Validate all scenarios still produce correct outcomes with all new systems active. Run structural verification tests to confirm zero remaining gaps. This is the final hardening pass.

**Deliverables**:
- Full scenario evaluation with all new systems active
- Recalibration of affected scenarios (expect significant recalibration — air combat routing, posture protection, logistics gates, and environmental effects all change outcomes)
- MC validation at 80% threshold with N=10 seeds
- Structural verification test results:
  - Zero unconsumed parameters (beyond P4 allowlist)
  - Zero uncalled public engine methods (beyond test-only methods)
  - All event types have functional subscribers (or are in observation-only allowlist)
  - All EngagementType values routable and handled
  - All feedback loops functional (ammo→fire, fuel→move, posture→damage, checkpoint→state)
- CalibrationSchema exercised fields audit (17 never-set fields either exercised in scenarios or removed)
- Regression test suite for all new environmental and combat effects
- Cross-doc audit and documentation sync
- Block 7 postmortem

**Tests**: ~35-45

---

## Test Count Estimate

| Phase | Focus | Tests | Cumulative (Python) |
|-------|-------|-------|---------------------|
| 58 | Structural Verification & Core Combat Wiring | ~60 | ~8,443 |
| 59 | Atmospheric & Ground Environment | ~50 | ~8,493 |
| 60 | Obscurants, Fire, & Visual Environment | ~50 | ~8,543 |
| 61 | Maritime, Acoustic, & EM Environment | ~55 | ~8,598 |
| 62 | Human Factors, CBRN, & Air Combat | ~45 | ~8,643 |
| 63 | Cross-Module Feedback Loops | ~45 | ~8,688 |
| 64 | C2 Friction & Command Delay | ~40 | ~8,728 |
| 65 | Space & EW Sub-Engine Activation | ~40 | ~8,768 |
| 66 | Unconventional, Naval, & Cleanup | ~30 | ~8,798 |
| 67 | Integration Validation & Recalibration | ~40 | ~8,838 |
| **Block 7 total** | | **~455** | **~8,838** |

---

## Design Decisions Needed

### 1. Opt-in vs Default for New Systems

**Question**: Should C2 friction, obscurants, space effects, etc. be on by default or opt-in per scenario?

**Recommendation**:
- **Default-on**: All environmental effects (seasons, obscurants, sea state, EM propagation, atmospheric corrections). These are passive modifiers — when conditions are benign (clear weather, no smoke, dry ground), they produce unity multipliers and don't change outcomes. When conditions are adverse, they add realism.
- **Opt-in**: C2 friction (`enable_c2_friction: true`). Dramatically changes battle pacing; existing scenarios assume instant C2.
- **Opt-in**: Human factors casualties (heat/cold stress). Can produce unexpected casualties in historical scenarios not calibrated for them.
- **Gated by config presence**: Space/EW sub-engines (only active when `space_config` or `ew_config` present).

### 2. ConditionsEngine: Wire or Remove?

**Recommendation**: Instantiate as optional convenience facade. Don't refactor existing code. Use for new Block 7 wiring where aggregated queries are cleaner.

### 3. Fire Spread Model Complexity

**Options**:
- **Simple**: Fire zones persist, don't spread. Decays when fuel exhausted.
- **Medium**: Fire spreads to adjacent vegetated cells at rate proportional to wind and vegetation density. Cellular automaton with wind bias.
- **Complex**: Full wildfire model with firebreaks, slope effects, spotting (ember transport).

**Recommendation**: Start with **medium** — the cellular automaton with wind bias captures the key dynamic (fire moves downwind through dry vegetation) without the complexity of spotting/embers. The SeasonsEngine already computes vegetation_density and vegetation_moisture per cell; the WeatherEngine provides wind. The pieces are there.

### 4. Performance Budget

New environmental queries (obscurant opacity, seasonal trafficability, EM propagation, atmospheric corrections) add per-engagement computation. Current tick time is ~50-100ms.

**Recommendation**: Budget 30% overhead (15-30ms per tick). Profile after each phase. Key mitigations:
- Environmental queries should be O(1) lookups with spatial caching (STRtree for obscurants, grid cache for seasons)
- Radar horizon is constant per antenna height — cache per unit
- EM ducting is constant per weather state — cache per tick
- Thermal crossover timing changes slowly — cache per hour
- Ice/mud/snow depth changes slowly — cache per tick

### 5. Backward Compatibility

All new systems must be backward-compatible. Existing scenarios that don't specify `environment_config`, `enable_c2_friction`, `space_config`, etc. should behave identically to Block 6.

**Mechanism**: Default values on all new config fields that produce unity modifiers (1.0 multiplier, 0.0 additive). New engines gated by config presence. ObscurantsEngine produces zero opacity when no smoke/dust/fog deployed. SeasonsEngine trafficability defaults to 1.0 when not explicitly set. Atmospheric corrections should produce negligible changes at sea level standard conditions.

### 6. Thermal Detection Model

**Question**: Should thermal detection switch from illumination-based modifier to physics-based ΔT model?

**Recommendation**: Yes. The ΔT model (target_temperature − background_temperature) is physically correct and uses values already computed by TimeOfDayEngine. The illumination-based modifier is a proxy that doesn't capture thermal crossover (dawn/dusk vulnerability windows where ΔT → 0 and thermal detection collapses). This is a real-world planning factor that should be represented.

### 7. Casualty Models for Environmental Effects

**Question**: Should heat/cold casualties use simple threshold models or continuous exposure models?

**Recommendation**: Continuous exposure. Heat casualties accumulate with WBGT × time × exertion_level. Cold casualties accumulate with wind_chill × exposure_time. Both produce casualties at a rate, not a threshold — this matches military medical data (heat/cold casualties are a function of cumulative exposure, not instant onset).

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Air combat routing changes every air engagement | High | Phase 58 (earliest); recalibrate immediately; expect all air-heavy scenarios affected |
| Posture protection makes defenders much harder to destroy | High | Calibrate protection values conservatively; DUG_IN ~50% not ~90% |
| Logistics gates stop combat in scenarios without supply units | High | Gate only when logistics system is active (supply units present); degrade gracefully |
| Damage detail extraction produces unexpected cascading losses | High | Secondary effects (fire, cookoff) opt-in via CalibrationSchema; disabled by default |
| Environmental corrections change outcomes in existing scenarios | High | Phase 67 dedicated to recalibration; run full eval after each environmental phase |
| Seasonal trafficability breaks movement in all scenarios | High | Default trafficability=1.0 for benign conditions; only penalizes mud/snow/saturated |
| Obscurant smoke from barrages degrades all engagement Pk | Medium | Smoke only at impact area, not global; 30min half-life; spectral: radar unaffected |
| Thermal ΔT model changes detection balance | Medium | Calibrate ΔT ranges to match existing detection behavior at nominal conditions |
| C2 friction makes AI unable to function | High | Opt-in flag; careful tuning of delay durations; INTUITIVE method for low echelon |
| Heat/cold casualty model produces unexpected losses | Medium | Opt-in flag for human factors; threshold calibrated to historical data |
| Radar horizon gate makes many ground radars useless | Medium | Only applies to detecting targets below geometric horizon; most engagements within horizon |
| Fire spread model creates runaway terrain destruction | Medium | Spread rate capped; fire decays when fuel exhausted; limited by vegetation moisture |
| EM ducting extends detection unrealistically | Low | Only activates in specific weather; factor capped at 3× range extension |
| Space sub-engines add per-tick overhead | Low | Gate by space_config presence; skip when null |
| Scenario recalibration cascade across 37 scenarios | High | Recalibrate one at a time; accept new baselines; environmental realism justifies changes |
| Performance degradation from 36 new per-engagement queries | Medium | O(1) lookups with caching; profile after each phase; budget 30% overhead |
| ECCM wiring changes EW balance in gulf_war_ew_1991 | Medium | Verify scenario still produces correct winner; recalibrate if needed |

---

## Research Sources

### Atmospheric Physics
- **ISA (International Standard Atmosphere)**: Lapse rate, tropopause, pressure-altitude relationship
- **MIL-STD-1474**: Propellant temperature effects on muzzle velocity
- **ITU-R P.838**: Specific rain attenuation model (dB/km vs rain rate and frequency)
- **ITU-R P.676**: Atmospheric gaseous attenuation (O₂ at 60 GHz, H₂O at 22 GHz)
- **Pasquill-Gifford**: Atmospheric stability classification and dispersion parameters

### Thermal & Optical
- **FLIR Systems**: Thermal contrast and NETD (Noise Equivalent Temperature Difference) modeling
- **MIL-HDBK-141**: Electro-optical systems atmospheric propagation
- **FM 3-11.50 / ATP 3-11.50**: Smoke/obscurant employment doctrine
- **Mie scattering theory**: Particulate (dust/fog/smoke) attenuation of optical/IR beams

### Maritime & Acoustic
- **Pierson-Moskowitz**: Wave spectrum (already implemented)
- **Mackenzie equation**: Sound velocity profile (already implemented)
- **Urick**: Underwater acoustic propagation — convergence zones, shadow zones, surface duct
- **NATO STANAG 1008**: Sea state definitions and operational limits
- **Beaufort scale**: Operational limits for small craft, carrier operations, helicopter deck landing

### Electromagnetic Propagation
- **ITU-R P.453**: Radio refractive index of the atmosphere (ducting conditions)
- **ITU-R P.526**: Propagation by diffraction (terrain LOS)
- **Bean & Dutton**: Radio refractivity (4/3 Earth model, super-refraction)

### Terrain & Ground
- **US Army FM 5-33**: Terrain Analysis — trafficability by soil type and moisture
- **NATO AEP-55**: Vehicle mobility in snow, mud, sand
- **Ice thickness bearing capacity**: Gold formula for ice crossing loads

### Human Factors
- **TB MED 507**: Heat stress control and heat casualty management (WBGT model)
- **AR 40-501 / FM 4-25.12**: Cold injury prevention (wind chill, frostbite times)
- **IAM Report 313**: Altitude effects on human performance

### C2 Friction
- **Clausewitz**: Fog of war and friction as fundamental warfare concepts
- **Boyd**: OODA loop timing as competitive advantage
- **US Army FM 5-0**: The Operations Process — MDMP phases and timing
- **van Creveld**: Command in War — communications delay as historical constant

### Space Warfare
- **Kessler & Cour-Palais (1978)**: Collision frequency and cascade model
- **DoD Space Policy**: Orbital regime definitions and satellite vulnerability
- **SBIRS/DSP**: Early warning satellite detection timelines

### CBRN-Environment Interaction
- **FM 3-11**: Chemical agent persistence tables (temperature/humidity dependent)
- **Seinfeld & Pandis**: Atmospheric Chemistry — washout coefficients for particulate scavenging
- **Arrhenius kinetics**: Temperature-dependent agent degradation rates

---

## Dependencies on Block 8 (Scenario Expansion)

Block 7 creates the infrastructure that Block 8's scenarios will exercise:

| Block 7 Feature | Block 8 Scenario Need |
|------------------|-----------------------|
| Seasonal trafficability (mud/snow/ice) | Eastern Front (rasputitsa), Napoleonic Russia, Korean Winter, Finnish Winter War, Bulge |
| Smoke/obscurants | D-Day smoke screens, WW1 gas+smoke, Napoleonic battery smoke, 73 Easting dust |
| Dust from movement | North Africa (El Alamein), Gulf War desert, 73 Easting, Golan Heights |
| Fire zones + spread | Tokyo firebombing, Dresden, incendiary tactics, scorched earth |
| Sea state → operations | Falklands storms, D-Day Channel weather, Midway, Jutland |
| Radar horizon + EM ducting | Maritime radar scenarios, Persian Gulf ducting, air defense engagement ranges |
| Thermal ΔT + crossover | Dawn/dusk attack scenarios (Golan 1973, Yom Kippur), night operations |
| HF propagation day/night | WW2 naval (night comms skip), Atlantic convoy |
| Rain → radar + DEW | Gulf War (clear weather advantage), Falklands (frequent rain) |
| Heat/cold casualties | Chosin Reservoir, Stalingrad winter, North Africa summer, Vietnam humidity |
| CBRN rain washout + persistence | Halabja (hot, dry = persistent), WW1 gas (rain washout), Cold War scenarios |
| Acoustic layers (thermocline/CZ) | Atlantic ASW, Pacific submarine warfare, Falklands naval |
| C2 friction (order delays) | Any multi-echelon scenario (Kursk, Normandy, Bulge, Waterloo) |
| ATO sortie management | Air-centric scenarios (Bekaa Valley, Gulf War air campaign) |
| Stratagems | Austerlitz (concentration + deception), 73 Easting (envelopment), Cannae |
| Space ISR/ASAT | Modern near-peer (Taiwan, Korea, Suwalki with space denial) |
| SIGINT/ECCM | Cold War EW scenarios, Gulf War SEAD, Bekaa Valley |
| Mine warfare | Dardanelles, Persian Gulf, Baltic WW2, Falklands |
| Unconventional | Afghanistan, Iraq, Vietnam, Peninsular War guerrilla |
| Bridge capacity + fording | Rhine crossing, Arnhem, Remagen, Napoleonic river crossings |
| Ice crossing | Eastern Front (Don, Volga), Finnish Winter War, Chosin Reservoir |
| Density altitude | Afghan mountain warfare, Chosin Reservoir, Andes |
| Fog scenarios | Austerlitz morning fog, Falklands sea fog, English Channel |
| Air combat routing (proper Pk) | Every air-heavy scenario: Bekaa Valley, Gulf War, Korea, Taiwan, Midway, Battle of Britain |
| Posture protection (DUG_IN/FORTIFIED) | Every defensive scenario: Kursk, Stalingrad, Chosin, Verdun, trench warfare, sieges |
| Damage degradation (partial losses) | All scenarios benefit from graduated degradation vs binary destroy/disable |
| Logistics gates (fuel/ammo) | Operational-scale: Bulge (fuel crisis), North Africa (supply lines), Barbarossa (overextension) |
| Detection → FOW-based AI | Near-peer with contested sensor coverage: Taiwan, Suwalki, Korea, naval scenarios |
| Medical RTD + maintenance | Attrition scenarios: Stalingrad, Verdun, WW1 trench, Korean War |
| Checkpoint state | Any scenario requiring save/restore (campaign-length scenarios, multi-day operations) |
| MISSILE routing | Any guided missile scenario: Gulf War HARM, Taiwan anti-ship, Korean BMD |

# Phase 4: Combat Resolution & Morale

**Status**: Complete
**Date**: 2026-03-01

---

## Summary

Phase 4 implements the combat resolution and morale systems — the core of what makes this a wargame. Units can now engage each other across every domain: direct fire (kinetic rounds, HEAT), indirect fire (tube and rocket artillery), surface-to-surface missiles (TBMs, cruise missiles, SSMs), air-to-air (BVR/WVR/guns), air-to-ground (CAS, SEAD/DEAD), air defense (SAMs with shoot-look-shoot, EMCON), missile defense (layered BMD, cruise missile defense, C-RAM), naval surface (Wayne Hughes salvo model), naval subsurface (torpedo engagements, evasion), mine warfare, naval gunfire support, amphibious assault, and carrier operations. Combat outcomes feed into a 5-state Markov morale model that drives rout cascades, surrender, and rally mechanics.

**Test count**: 634 new tests -> 1,721 total (1,087 Phase 0-3 + 634 Phase 4).

## What Was Built

### Step 1: Direct Fire & Fundamentals (7 modules)

**`combat/engagement.py`** — Engagement orchestrator. Sequences the kill chain: target selection, range determination, weapon-ammo pairing, hit probability, damage assessment. Delegates to physics (ballistics), probability (hit_probability), and effects (damage) engines. Publishes `EngagementEvent` to EventBus for morale/intel subscribers.

**`combat/ballistics.py`** — Projectile trajectory computation via RK4 numerical integration. Models drag (simplified constant Cd), Coriolis deflection (latitude-dependent), wind drift, and propellant temperature effects on muzzle velocity. Computes time of flight, impact angle, and terminal velocity.

**`combat/hit_probability.py`** — P(hit) computation from weapon accuracy, range, crew skill, target motion (crossing rate penalty), target size, environmental modifiers (visibility, wind), and posture (hull-down, defilade). Returns probability used as Bernoulli trial parameter.

**`combat/damage.py`** — Terminal effects engine. DeMarre penetration model for kinetic energy rounds (penetration proportional to projectile mass, velocity squared, and caliber). HEAT penetration is range-independent (shaped charge jet). Behind-armor effects: spalling, fire, crew casualties. Hull/equipment damage tracking.

**`combat/suppression.py`** — Suppression from incoming fire volume and caliber. Exponential time decay. Spatial spreading from impact point. Suppressed units suffer accuracy, speed, and morale penalties. Stacks with existing suppression up to a cap.

**`combat/ammunition.py`** — Weapon and ammunition separated: a weapon can fire multiple ammo types (e.g., M1A2 fires M829 APFSDS, M830 HEAT-MP, M1028 canister). Ammo consumption tracking per type. High-value munitions (missiles, guided rounds) individually tracked. Magazine/rack management.

**`combat/fratricide.py`** — IFF uncertainty model. Fratricide probability increases when identification confidence is low (from Phase 3 detection pipeline), engagement range is long, and environmental conditions degrade identification. Deconfliction checks against known friendly positions.

### Step 2: Indirect Fire & Deep Fires (1 module)

**`combat/indirect_fire.py`** — Tube artillery fire missions (adjust fire, fire for effect, final protective fires) with CEP-based dispersion. Rocket artillery (MLRS/HIMARS) with pod-based ammunition, wider dispersal patterns, and shoot-and-scoot timing. GMLRS precision guidance reduces CEP to near-zero. Counterbattery fire: radar-detected launch point as target. Gaussian blast attenuation model: P_kill = exp(-d^2 / (2 * sigma^2)) where sigma derives from warhead lethality radius. Ammo selection: HE, DPICM, smoke, illumination, FASCAM.

### Step 3: Surface-to-Surface Missiles (1 module)

**`combat/missiles.py`** — Kill chain phases: detect -> localize -> authorize -> launch -> flight -> terminal. TBM ballistic trajectory (boost-midcourse-reentry), land-attack cruise missiles (terrain-following flight profile), coastal defense SSMs (sea-skimming terminal). Flight time from range and missile speed profile. Terminal hit probability with countermeasure degradation. TEL reload cycle timing. Missile inventory tracking (links to future logistics).

### Step 4: Air Combat & Air-Ground (2 modules)

**`combat/air_combat.py`** — Beyond Visual Range (BVR): missile Pk from range, aspect, countermeasures (chaff/flare/ECM), target maneuver. Within Visual Range (WVR): merge dynamics simplified to Pk roll with energy advantage modifier. Gun engagement at close range with tracking solution quality. Missile expenditure tracking. Engagement geometry: head-on, beam, tail aspect.

**`combat/air_ground.py`** — Close Air Support (CAS): weapon delivery accuracy modified by FAC/JTAC guidance, weather, target marking. SEAD (Suppression of Enemy Air Defenses): anti-radiation missile homing on radar emissions — only effective when radar is radiating. DEAD (Destruction of Enemy Air Defenses): direct attack on AD sites. Air interdiction: strike missions against fixed/mobile targets with BDA assessment.

### Step 5: Air Defense & Missile Defense (2 modules)

**`combat/air_defense.py`** — 3D engagement envelope (min/max range, min/max altitude). Shoot-look-shoot doctrine: fire, assess via radar, fire again if miss. EMCON states (RADIATE/STANDBY/SILENT) — silent AD invisible to SEAD but cannot engage. Engagement capacity: simultaneous target limit. IAMD shared mechanics: common track management, weapon-target pairing, engagement authority. SAM Pk from range within envelope, target speed, countermeasures, crew skill.

**`combat/missile_defense.py`** — Extends air_defense core with BMD-specific mechanics. Layered defense: upper tier (THAAD/SM-3 exoatmospheric), lower tier (Patriot PAC-3 endoatmospheric). Cruise missile defense. C-RAM (Iron Dome, Phalanx CIWS): very short range, high rate of fire, optimized for rockets/artillery/mortars. Interceptor inventory tracking with sustainability concerns. Salvo sizing based on threat assessment and inventory.

### Step 6: Naval Combat (6 modules)

**`combat/naval_surface.py`** — Wayne Hughes salvo model for anti-ship missile exchange: offensive power (missiles launched x Pk) vs defensive power (interceptors x Pk_intercept) + staying power (hits to sink). Naval gunfire: range-dependent accuracy, rate of fire, caliber effects. Point defense (CIWS, SeaRAM) as last-ditch layer. Chaff and decoy deployment. Ship damage model: mission kill vs mobility kill vs sinking. Damage control: crew-dependent repair rate, flooding progression (abstracted).

**`combat/naval_subsurface.py`** — Torpedo engagement: launch from bearing/range, torpedo speed and endurance, wire-guided correction, terminal homing. Evasion: decoys (noisemakers, Nixie), maneuvering (knuckle turn), depth change. Submarine-launched missile (SLCM) missions. Probability-based torpedo hit model accounting for evasion quality, torpedo type, and water conditions.

**`combat/naval_mine.py`** — Mine types: contact, magnetic influence, acoustic influence, pressure, combination. Laying operations (surface, submarine, air-delivered). Sweeping (mechanical, influence). Hunting (sonar-based detection and neutralization). Risk-based transit: P(detonation) per mine based on ship signature vs mine trigger threshold.

**`combat/naval_gunfire_support.py`** — Shore bombardment fire missions. Fire support coordination: naval surface fire zone (NSFZ), fire support coordination line (FSCL). Accuracy model: range-dependent CEP with spotter correction. Target types: fixed fortifications, area suppression, troop concentrations.

**`combat/amphibious_assault.py`** — Beach assault resolution. Shore defense fire against approaching landing craft. Attrition during ship-to-shore movement. Beach obstacle clearance. Buildup phase: combat power ashore vs defender strength. Integrates with Phase 2 amphibious movement phases.

**`combat/carrier_ops.py`** — Sortie generation rate from deck cycle time, aircraft availability, and crew readiness. Combat Air Patrol (CAP) station management. Strike package launch and recovery. Deck cycle abstraction: spot, launch, recover, rearm/refuel (no individual aircraft spot tracking). Aircraft attrition and replacement from air wing inventory.

### Step 7: Morale System (6 modules)

**`morale/state.py`** — 5-state Markov machine: STEADY -> SHAKEN -> BROKEN -> ROUTED -> SURRENDERED. 5x5 transition matrix with modifiers from casualties (recent and cumulative), suppression level, force ratio (local), leadership quality, cohesion, fatigue, and surprise. Transitions evaluated per tick. Recovery possible (SHAKEN->STEADY, BROKEN->SHAKEN) with leadership and rally modifiers.

**`morale/cohesion.py`** — Unit cohesion from shared experience, time together, casualties absorbed, nearby friendly units, parent unit status. Cohesion modifies the morale transition matrix: high cohesion resists breakdown, low cohesion accelerates it. Isolation penalty when no friendly units within cohesion radius.

**`morale/stress.py`** — Stress accumulation as random walk with drift: combat exposure, incoming fire, casualties witnessed, sleep deprivation, environmental hardship (cold, heat, altitude). Stress recovery during rest periods. Stress level feeds into morale transition modifiers and hit probability degradation.

**`morale/experience.py`** — Training level (GREEN/TRAINED/VETERAN/ELITE) as baseline. Combat experience learning curve: diminishing returns, fastest learning in first engagements. Experience gain from successful engagements, observation, and surviving combat. Experience modifies hit probability, suppression resistance, and morale resilience.

**`morale/psychology.py`** — PSYOP effects: leaflet drops, loudspeaker broadcasts, social media (modern conflicts). Effectiveness roll modified by target morale state, isolation, supply status, and cultural factors. Surrender inducement when conditions are met. Civilian reaction model for stability operations.

**`morale/rout.py`** — Rout cascade: when a unit routs, adjacent units receive a morale penalty proportional to the routing unit's size and proximity. Rally mechanics: leadership check to halt rout at rally point. Surrender: units in SURRENDERED state become POW candidates (links to future logistics/prisoners module). Rout movement: away from threat, ignoring formation.

### Step 8: Support Files & Integration (3 files)

**`combat/__init__.py`** — Package init with public API exports.

**`combat/events.py`** — EventBus event classes: `EngagementEvent`, `HitEvent`, `DamageEvent`, `KillEvent`, `SuppressionEvent`, `AmmunitionExpendedEvent`, `MissileFlightEvent`, `AirDefenseEngagementEvent`, `NavalSalvoEvent`, `TorpedoEvent`, `MineDetonationEvent`.

**`morale/events.py`** — EventBus event classes: `MoraleChangedEvent`, `RoutEvent`, `RallyEvent`, `SurrenderEvent`, `CohesionChangedEvent`, `StressEvent`.

### YAML Data Files (47 files)

**24 weapon definitions** (`data/weapons/`): m256_120mm (M1A2 main gun), m240_coax (coaxial MG), m2_50cal (heavy MG), m242_25mm (Bradley chain gun), m109_155mm (Paladin howitzer), m777_155mm (towed howitzer), mlrs_227mm (MLRS launcher), himars_227mm (HIMARS launcher), mk45_5in (naval gun), mk15_ciws (Phalanx CIWS), mk41_vls (vertical launch system), mk32_torpedo (torpedo tube), m61_vulcan (F-16 gun), aim120_amraam (BVR AAA missile), aim9x_sidewinder (WVR AAA missile), agm65_maverick (air-to-ground missile), agm88_harm (anti-radiation missile), agm84_harpoon (anti-ship missile), gbu12_paveway (laser-guided bomb), bgm109_tomahawk (cruise missile), rim161_sm3 (BMD interceptor), rim162_essm (ship self-defense), pac3_mse (Patriot interceptor), mk48_torpedo (heavyweight torpedo).

**23 ammunition definitions** (`data/ammunition/`): m829a4_apfsds, m830a1_heat, m1028_canister, m855_556nato, m33_50bmg, m795_155mm_he, m549a1_155mm_rap, m864_155mm_dpicm, m483a1_155mm_dpicm, m825_155mm_smoke, m485_155mm_illum, m31_gmlrs, m30_gmlrs_dpicm, mk82_500lb, mk84_2000lb, mk48_adcap_torpedo, mk46_lightweight_torpedo, rim7_seasparrow, tamir_iron_dome, atacms_block1a, srbm_scud, jdam_gbu31, pgm_excalibur.

### Visualization

**`scripts/visualize/combat_viz.py`** — Engagement outcome distributions, suppression zones, artillery impact patterns (CEP ellipses), missile flight profiles, air defense engagement envelopes, naval salvo exchange outcomes, morale state transitions over time.

## Design Decisions

1. **Engagement module as orchestrator**: `engagement.py` sequences the kill chain but delegates all physics to `ballistics.py`, all probability to `hit_probability.py`, and all effects to `damage.py`. This keeps each module focused and testable in isolation.

2. **Wayne Hughes salvo model for naval missile exchange**: The salvo model (offensive power vs defensive power vs staying power) is the standard analytical framework for modern naval surface combat. It naturally captures the alpha-strike nature of missile warfare and the importance of defense-in-depth.

3. **Morale decoupled via EventBus**: Combat modules publish events (casualties, suppression, kills); morale modules subscribe. No direct import from combat to morale or vice versa. This preserves the dependency graph: combat and morale are peers, not parent-child.

4. **Weapon + ammo separated**: A weapon definition specifies mechanical properties (rate of fire, accuracy, range). Ammunition definitions specify terminal effects (penetration, blast radius, fragmentation). A weapon references compatible ammo types. This mirrors real-world logistics and allows realistic ammo selection.

5. **IAMD shared mechanics**: `air_defense.py` provides the core engagement loop (detect, track, engage, assess) used by all air/missile defense. `missile_defense.py` extends this with BMD-specific mechanics (exo/endo-atmospheric interception, salvo sizing) and C-RAM (high-rate-of-fire point defense). No code duplication between AD and BMD.

6. **All randomness via np.random.Generator**: Every stochastic outcome (hit/miss, penetration, suppression, morale transition, blast damage, torpedo evasion) uses `RNGManager.get_stream(ModuleId)`. Deterministic replay from seed verified across all combat domains.

7. **DeMarre for kinetic penetration**: The DeMarre formula (penetration ~ mass * velocity^2 / caliber) is the standard simplified model for armor penetration by kinetic energy projectiles. It captures the essential physics without requiring finite element analysis.

8. **Gaussian blast attenuation**: P_kill = exp(-d^2 / (2 * sigma^2)) provides a physically reasonable model for blast/fragmentation lethality that drops off smoothly with distance. Sigma derived from warhead characteristics.

9. **Morale as Markov chain**: The 5-state model (STEADY/SHAKEN/BROKEN/ROUTED/SURRENDERED) captures the key behavioral transitions observed in combat. Transition probabilities are modified by tactical context, not hard-coded — this allows calibration against historical data in Phase 8.

10. **Kill chain timing for missiles**: Missiles are not instantaneous. The detect-localize-authorize-launch-flight-terminal chain introduces realistic delays that matter for time-sensitive targets and defensive response windows.

## Deviations from Plan

- Phase 4 was originally scoped as combat only (4a-4e), with morale as part of Phase 5. The development phases document was updated to include morale (4f) in Phase 4 since morale is tightly coupled to combat outcomes and cannot be meaningfully tested without the combat event stream.
- Test count (634) slightly below the aggressive plan estimate, but all exit criteria met and all combat domains functional.

## Key Physics

- **Ballistic trajectory**: RK4 integration of equations of motion with constant Cd drag, Coriolis force (2 * omega * v * sin(lat)), and wind vector addition. Propellant temperature modifies muzzle velocity by ~1 m/s per degree C.
- **DeMarre penetration**: P = k * m * v^2 / (d * sigma_armor) where k is a form factor, m is projectile mass, v is impact velocity, d is caliber, sigma_armor is armor quality factor.
- **HEAT penetration**: Penetration = liner_diameter * standoff_factor. Range-independent (shaped charge jet velocity >> projectile velocity).
- **Blast attenuation**: P_kill = exp(-d^2 / (2 * sigma^2)). For DPICM: individual submunition lethal radii with random scatter across target area.
- **Radar range equation (from Phase 3)**: Drives detection ranges for fire control radars, AD radars, and counterbattery radars.
- **Wayne Hughes salvo model**: Damage = (alpha * A_missiles * P_hit - beta * B_interceptors * P_intercept) / staying_power. Negative damage clamped to zero.
- **Torpedo Pk**: Base Pk modified by evasion quality (decoys, maneuver), water conditions (thermocline hiding), and torpedo type (wire-guided vs autonomous).
- **Suppression**: S = sum(caliber_factor * rounds) with exponential decay tau and spatial Gaussian falloff from impact point.
- **Morale transitions**: P(transition) from 5x5 Markov matrix, modified per-tick by: casualties_factor * suppression_factor * force_ratio_factor * leadership_factor * cohesion_factor * fatigue_factor * surprise_factor.

## Issues & Fixes

| Issue | Resolution |
|-------|-----------|
| Morale dependency direction unclear | Decoupled via EventBus — combat publishes, morale subscribes, no circular imports |
| IAMD code duplication between AD and BMD | Extracted shared engagement loop into `air_defense.py`, `missile_defense.py` extends it |
| Weapon-ammo coupling too tight in initial design | Separated into independent YAML definitions with compatibility references |
| Blast damage double-counting for area weapons | Unified Gaussian attenuation model, each target evaluated once per detonation |
| Rout cascade infinite loop risk | Cascade depth limit and visited-unit set prevent re-triggering |
| Torpedo engagement needed submarine depth | Threaded depth from Phase 2 `SubmarineMovementEngine` state into engagement context |
| Carrier sortie rate unrealistic without deck constraints | Added deck cycle time, simultaneous operations limit, and crew fatigue |

## Known Limitations / Post-MVP Refinements

These are deliberate simplifications made during initial implementation. All are functional but could benefit from refinement after MVP is complete.

1. **Ballistic trajectory uses simplified drag model (no Mach-dependent Cd curve)**: The constant-Cd approximation is reasonable for subsonic/low-supersonic projectiles but diverges at transonic speeds where Cd varies significantly. A Mach-dependent Cd lookup table would improve accuracy for long-range artillery and high-velocity rounds.

2. **Penetration model is DeMarre approximation -- not full finite element**: DeMarre captures the essential scaling (mass, velocity squared, caliber) but doesn't model obliquity effects, composite armor, reactive armor, or spaced armor in detail. Sufficient for aggregate combat resolution but not for detailed armor-vs-projectile analysis.

3. **HEAT penetration is range-independent**: This is a reasonable simplification for shaped charge warheads where jet velocity far exceeds projectile velocity. In reality, standoff distance optimization and precursor charges (ERA defeat) introduce minor range dependencies. Not significant at simulation resolution.

4. **Submarine evasion uses simplified probability model**: Evasion outcome is a single Bernoulli trial with Pk modified by evasion actions, rather than a physics-based torpedo-vs-submarine pursuit simulation. Adequate for campaign-level resolution but lacks the fidelity for detailed submarine tactical analysis.

5. **Mine warfare trigger model doesn't account for detailed ship magnetic/acoustic signatures**: Mine triggering uses a simplified threshold comparison against ship displacement class rather than modeling the full magnetic/acoustic/pressure signature interaction. The Phase 3 signature profiles could be extended to provide mine-relevant signatures.

6. **Carrier ops deck management is abstracted**: No individual aircraft spot tracking on the flight deck. Sortie generation uses aggregate rates from deck cycle time and aircraft availability. A detailed deck model would track individual aircraft positions, fuel/arm status, and spot conflicts.

7. **Morale Markov transitions use single-step discrete chain (not continuous-time)**: Transitions are evaluated once per tick. A continuous-time Markov chain would allow transitions at sub-tick resolution, which matters when tick duration is large. The current model is correct for fine-grained ticks.

8. **Psychology/PSYOP model is simplified effectiveness roll**: PSYOP effectiveness is a single modified Bernoulli trial rather than a multi-stage influence model with message crafting, delivery, reception, and behavioral change. Sufficient for representing PSYOP as a force modifier but not for detailed information operations analysis.

9. **Naval damage control doesn't model individual compartment flooding progression**: Ship damage uses an aggregate hull integrity model with crew-dependent repair rate. A compartment-based flooding model (progressive flooding, counterflooding, damage control teams) would provide higher fidelity for capital ship engagements.

10. **Air combat doesn't model detailed flight dynamics or energy-maneuverability**: WVR combat uses a simplified Pk roll with energy advantage modifier rather than modeling specific fighter maneuvers (BFM), turn rates, energy states, or corner velocities. The BVR model (missile Pk from range/aspect/countermeasures) is more detailed since BVR is the dominant modern air combat mode.

11. **Environment→combat coupling is partial**: Only three combat modules consume environmental conditions: `hit_probability` (visibility), `ballistics` (wind, temperature, latitude), and `air_ground` (weather_penalty, night). The remaining combat modules (`air_combat`, `air_defense`, `naval_surface`, `indirect_fire`) accept conditions parameters but either don't use them or don't accept them at all. Sea state should affect naval point defense, radar propagation should affect air defense range, and wind should affect indirect fire CEP. Integration tests for the existing couplings were added post-Phase 4; remaining couplings should be wired when the simulation loop (Phase 7) brings all modules together.

## Modules Created

| Module | Subphase | Purpose |
|--------|----------|---------|
| `combat/__init__.py` | — | Package init, public API exports |
| `combat/events.py` | — | Combat EventBus event classes |
| `combat/engagement.py` | 4a | Engagement orchestrator, kill chain sequencing |
| `combat/ballistics.py` | 4a | Projectile trajectory (RK4), drag, Coriolis, wind |
| `combat/hit_probability.py` | 4a | P(hit) from weapon, range, skill, conditions |
| `combat/damage.py` | 4a | Terminal effects, DeMarre penetration, HEAT, blast |
| `combat/suppression.py` | 4a | Fire volume suppression with decay and spreading |
| `combat/ammunition.py` | 4a | Weapon-ammo pairing, consumption, magazine tracking |
| `combat/fratricide.py` | 4a | IFF uncertainty, deconfliction |
| `combat/indirect_fire.py` | 4b | Tube and rocket artillery fire missions |
| `combat/missiles.py` | 4c | TBM, cruise, SSM kill chain and flight |
| `combat/air_combat.py` | 4d | BVR, WVR, gun air-to-air engagements |
| `combat/air_ground.py` | 4d | CAS, SEAD/DEAD, air interdiction |
| `combat/air_defense.py` | 4d | SAM/AAA, shoot-look-shoot, EMCON, IAMD core |
| `combat/missile_defense.py` | 4d | Layered BMD, cruise missile defense, C-RAM |
| `combat/naval_surface.py` | 4e | Wayne Hughes salvo model, naval gunfire, point defense |
| `combat/naval_subsurface.py` | 4e | Torpedo engagements, evasion, SLCM |
| `combat/naval_mine.py` | 4e | Mine laying, sweeping, hunting, transit risk |
| `combat/naval_gunfire_support.py` | 4e | Shore bombardment, fire support coordination |
| `combat/amphibious_assault.py` | 4e | Beach assault resolution, shore defense |
| `combat/carrier_ops.py` | 4e | Sortie generation, CAP, deck cycle |
| `morale/__init__.py` | — | Package init |
| `morale/events.py` | — | Morale EventBus event classes |
| `morale/state.py` | 4f | 5-state Markov morale machine |
| `morale/cohesion.py` | 4f | Unit cohesion, nearby friendlies, isolation |
| `morale/stress.py` | 4f | Stress/fatigue random walk with drift |
| `morale/experience.py` | 4f | Training level, combat experience learning curve |
| `morale/psychology.py` | 4f | PSYOP effects, surrender inducement |
| `morale/rout.py` | 4f | Rout cascade, rally, surrender, POW generation |

## File Count Summary

| Category | Files |
|----------|-------|
| Source modules (combat) | 19 |
| Source modules (morale) | 6 |
| Support files (__init__, events) | 3 |
| YAML data files (weapons) | 24 |
| YAML data files (ammunition) | 23 |
| Test files | ~25 (unit + integration) |
| Visualization | 1 |
| **Total** | **~101** |

## Test Coverage

1,721 tests total, all passing:
- Phase 0-3: 1,087 tests (unchanged)
- Phase 4 unit tests: ~600 across 25 test files
  - Step 1 (direct fire fundamentals): ~140 tests (engagement, ballistics, hit_probability, damage, suppression, ammunition, fratricide)
  - Step 2 (indirect fire): ~55 tests (tube artillery, rocket artillery, GMLRS precision, counterbattery, blast model)
  - Step 3 (missiles): ~45 tests (TBM trajectory, cruise missile flight, SSM, kill chain timing, inventory)
  - Step 4 (air combat/air-ground): ~65 tests (BVR, WVR, gun, CAS, SEAD, DEAD, air interdiction)
  - Step 5 (air defense/missile defense): ~60 tests (SAM envelope, shoot-look-shoot, EMCON, BMD layers, C-RAM, interceptor inventory)
  - Step 6 (naval combat): ~115 tests (salvo model, naval gunfire, torpedo, evasion, mines, NGFS, amphibious, carrier ops)
  - Step 7 (morale): ~120 tests (Markov transitions, cohesion, stress, experience, psychology, rout cascade, rally, surrender)
- Phase 4 integration: ~34 tests (combined arms, naval task force engagement, air-ground coordination, morale under fire, deterministic replay, checkpoint/restore)

## Exit Criteria Verification

1. **Direct fire**: Engagement orchestrator resolves kinetic/HEAT rounds with ballistic trajectory, hit probability, and penetration model ✅
2. **Indirect fire (tube)**: Artillery fire missions with CEP dispersion, adjust/FFE, counterbattery ✅
3. **Indirect fire (rocket)**: MLRS/HIMARS with pod-based ammo, GMLRS precision, shoot-and-scoot ✅
4. **Missiles**: TBM/cruise/SSM with kill chain phases and flight time modeling ✅
5. **Air-to-air**: BVR and WVR engagements with missile Pk and countermeasures ✅
6. **Air-to-ground**: CAS with JTAC, SEAD/DEAD with ARM homing, air interdiction ✅
7. **Air defense**: 3D engagement envelope, shoot-look-shoot, EMCON states ✅
8. **Missile defense**: Layered BMD (upper/lower tier), C-RAM, interceptor inventory ✅
9. **Naval surface**: Wayne Hughes salvo model, naval gunfire, point defense, damage control ✅
10. **Naval subsurface**: Torpedo engagement and evasion, SLCM ✅
11. **Mine warfare**: Laying, sweeping, hunting, risk-based transit ✅
12. **Amphibious**: Beach assault with shore defense attrition ✅
13. **Carrier ops**: Sortie generation, CAP, deck cycle ✅
14. **NGFS**: Shore bombardment with fire support coordination ✅
15. **Suppression**: Fire volume drives suppression with decay ✅
16. **Fratricide**: IFF uncertainty produces friendly fire when identification is low ✅
17. **Morale**: 5-state Markov with contextual modifiers ✅
18. **Rout cascade**: Routing units degrade adjacent unit morale ✅
19. **Ammo consumption**: By type, missiles individually tracked ✅
20. **Combined arms**: Multiple combat domains interact correctly ✅
21. **Deterministic replay from seed** ✅
22. **All modules state round-trip** ✅

## Lessons Learned

- **Engagement orchestration is key**: Keeping `engagement.py` as a thin orchestrator that delegates to specialized modules prevents monolithic combat code. Each physics/probability/damage module can be tested and tuned independently.
- **Wayne Hughes salvo model scales well**: The offensive/defensive/staying power framework handles everything from small corvette actions to carrier strike group engagements by parameterizing the missile counts and Pk values.
- **Morale decoupling via EventBus works cleanly**: Publishing combat events and letting morale subscribe eliminates circular dependencies. The morale system doesn't need to know about weapon types or physics — it only cares about outcomes (casualties, suppression, kills).
- **YAML weapon/ammo separation pays off**: Being able to mix weapon-ammo combinations (e.g., same 155mm howitzer firing HE, DPICM, smoke, illumination, or Excalibur) without code changes makes scenario authoring much more flexible.
- **Rout cascade needs depth limiting**: Without a visited-set and depth limit, cascading morale checks can theoretically loop through a dense formation. The fix is straightforward (BFS with visited set) but the failure mode is subtle.
- **Kill chain timing matters**: Missiles that take minutes to reach their target create windows for defensive response. Modeling this explicitly (rather than instant resolution) is essential for realistic IAMD and naval combat.

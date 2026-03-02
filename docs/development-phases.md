# Stochastic Warfare — Development Phases

## Philosophy
Build the nuts and bolts first. Every phase produces runnable, testable code. Validation via basic Python visualization (matplotlib) throughout. No UI work until the engine is solid. Naval warfare is integrated across phases, not deferred.

**Cross-document alignment**: This document must stay synchronized with `specs/project-structure.md` (module definitions), `brainstorm.md` (architecture decisions), and `devlog/` (implementation record). Every module file in project-structure.md must appear in exactly one phase below. Run `/update-docs` after any structural change.

---

## Phase 0: Project Scaffolding ✅
**Goal**: Establish the project skeleton, tooling, and foundational infrastructure.

**Modules built**:
- `core/types.py` — shared types, enums (ModuleId, TickResolution), physical constants
- `core/logging.py` — centralized logging framework
- `core/rng.py` — central RNG manager (seeded numpy Generators, per-subsystem stream forking)
- `core/clock.py` — calendar-aware simulation clock (UTC, Julian date via Meeus)
- `core/events.py` — typed pub-sub event bus for inter-module communication
- `core/config.py` — YAML config loading with pydantic validation
- `core/checkpoint.py` — state serialization, checkpoint/restore
- `coordinates/transforms.py` — geodetic ↔ UTM ↔ ENU conversions via pyproj
- `coordinates/spatial.py` — distance, bearing, point_at utilities
- `entities/base.py` — minimal base entity class (stub for Phase 2)

**Also**: `pyproject.toml`, package structure, pytest framework, uv-managed venv

**Exit Criteria**: Can instantiate the simulation framework, create a seeded RNG, load a YAML config, tick a clock with calendar queries (Julian date), publish/subscribe events, transform coordinates (geodetic ↔ ENU round-trip), and serialize/restore full state. All tests pass. Deterministic replay verified.

---

## Phase 1: Terrain, Environment & Spatial Foundation ✅
**Goal**: Build the world the simulation operates in — both the static physical terrain and the dynamic environmental conditions that vary with time, date, and geography.

### 1a: Core Terrain
- `terrain/heightmap.py` — DEM loading, elevation queries, slope, aspect
- `terrain/classification.py` — land cover, soil type, trafficability, concealment vs cover
- `terrain/los.py` — line-of-sight and line-of-fire computation (terrain + structures)
- `terrain/strategic_map.py` — graph-based strategic terrain (nodes + edges, including maritime routes)

### 1b: Extended Terrain Layers
- `terrain/hydrography.py` — rivers (depth, current, ford points), lakes, flooding, watersheds
- `terrain/infrastructure.py` — roads, bridges, rail, buildings, utilities, tunnels, airfields
- `terrain/obstacles.py` — natural (ravines, cliffs) and man-made (minefields, barriers, wire, ditches, fortifications)
- `terrain/population.py` — civilian population density, disposition (friendly/neutral/hostile)
- `terrain/bathymetry.py` — ocean/sea floor depth, bottom type, navigation hazards (reefs/shoals)
- `terrain/maritime_geography.py` — coastline, ports, straits, chokepoints, sea lanes, anchorages

### 1c: Environment Foundation
- `environment/astronomy.py` — solar/lunar position, rise/set, twilight, phase, tidal forcing (Meeus algorithms)
- `environment/time_of_day.py` — illumination model (sun + moon + cloud + artificial), thermal crossover, NVG effectiveness, shadow modeling
- `environment/weather.py` — weather state and stochastic transitions (precip, wind, temp, cloud, humidity, pressure), conditioned on climate zone/geography/season
- `environment/seasons.py` — ground state (frozen/mud/dry), vegetation cycle, snow cover, sea ice, wildfire risk
- `environment/obscurants.py` — smoke, dust, fog (radiation/advection/sea), multi-spectral blocking properties, drift
- `environment/sea_state.py` — wave height/period, tidal model (astronomical + local harmonics), tidal currents, storm surge, SST, ocean currents
- `environment/underwater_acoustics.py` — sound velocity profile, thermoclines, convergence zones, bottom bounce, ambient noise
- `environment/electromagnetic.py` — RF propagation (HF sky wave, VHF LOS, radar ducting, evaporation ducts), ionospheric conditions, GPS accuracy
- `environment/conditions.py` — unified condition queries compositing all modifiers for land, air, and maritime consumers

### 1d: Remaining Coordinate Utilities
- `coordinates/magnetic.py` — magnetic declination (WMM), true ↔ magnetic bearing conversion

**Visualization**: elevation heatmaps, LOS plots, weather state, illumination timeline, tidal curves

**Exit Criteria**: Can load terrain (elevation + classification + infrastructure + hydrography + bathymetry), compute LOS between two points, calculate movement costs. Environment initializes from scenario date/time/location: astronomical positions correct, weather evolves stochastically, illumination model produces day/night/twilight cycle, tidal model produces realistic curves, conditions module composites modifiers for all consumers. Multi-scale terrain representations interoperable. All reproducible from seed.

---

## Phase 2: Entities, Organization & Movement
**Goal**: Define what simulation entities ARE, how they're organized, and how they move.

### 2a: Entity System
- `entities/personnel.py` — crew/individual modeling: roles, skills, experience, casualties
- `entities/equipment.py` — equipment state: degradation, maintenance, breakdown probability, environmental hardening
- `entities/unit_classes/ground.py` — armor, infantry, mechanized, artillery
- `entities/unit_classes/aerial.py` — fixed-wing and rotary-wing (including UAV/drone subtypes with data link dependency)
- `entities/unit_classes/air_defense.py` — SAM, AAA, MANPADS, radar (land and shipborne)
- `entities/unit_classes/naval.py` — surface combatants, submarines, amphibious, mine warfare, auxiliary
- `entities/unit_classes/support.py` — logistics vehicles, HQ, engineers, comms, medical
- `entities/loader.py` — YAML → pydantic → unit instance factory
- `entities/capabilities.py` — combat power assessment: weighted factors, force ratios, readiness

### 2b: Organization
- `entities/organization/hierarchy.py` — configurable echelon hierarchy (nation/era-agnostic)
- `entities/organization/echelons.py` — echelon type definitions (fire team through theater)
- `entities/organization/task_org.py` — dynamic task organization: attach/detach, OPCON/TACON
- `entities/organization/staff.py` — staff functions (S1-S6) as capabilities affecting C2
- `entities/organization/orbat.py` — order of battle loading, TO&E definitions
- `entities/organization/special_org.py` — SOF, irregular/insurgent (cell/network), coalition/joint

### 2c: Movement
- `movement/engine.py` — movement execution (terrain speed, stochastic deviation, load effects)
- `movement/pathfinding.py` — A* route planning (terrain, obstacle, threat-aware)
- `movement/fatigue.py` — fatigue/sleep deprivation accumulation, recovery
- `movement/formation.py` — formation movement, spacing, coherence
- `movement/obstacles.py` — obstacle interaction: breaching, bridging, clearing, bypassing
- `movement/mount_dismount.py` — mounted/dismounted transitions, embark/debark
- `movement/naval_movement.py` — ship speed-fuel curves, formation steaming, turning circles, draft constraints
- `movement/submarine_movement.py` — depth management, speed-noise tradeoff, snorkel, periscope depth
- `movement/amphibious_movement.py` — ship-to-shore movement, beach approach, landing craft
- `movement/airborne.py` — parachute drop, helicopter insertion, DZ/LZ selection, assembly

**Visualization**: unit positions on terrain, movement paths, formation display, organizational hierarchy tree

**Exit Criteria**: Can load unit definitions from YAML, create organizational hierarchies with task organization, place units on terrain, and execute movement across all domains (ground, aerial, naval, submarine, amphibious, airborne). Movement respects terrain, weather, fatigue, formation, and obstacles. Pathfinding avoids threats and minimizes cost. Equipment degrades with use. Personnel have skills and roles. All state serializable and reproducible from seed.

---

## Phase 3: Detection & Intelligence
**Goal**: Units become aware of each other through realistic sensor models across all domains.

- `detection/sensors.py` — sensor models: visual, thermal, radar, acoustic, seismic, sonar (parameterized via YAML)
- `detection/signatures.py` — unit signature profiles: visual, thermal, RCS, acoustic, EM emission
- `detection/detection.py` — SNR-based detection probability engine (Pd, Pfa, ROC curves)
- `detection/identification.py` — detection → classification → identification pipeline, confidence levels
- `detection/estimation.py` — Kalman/particle filter state estimation (per-side belief state)
- `detection/intel_fusion.py` — multi-source fusion (SIGINT, HUMINT, IMINT, sensor data), satellite overflight schedules
- `detection/deception.py` — decoys, feints, false signals, camouflage effectiveness
- `detection/sonar.py` — active/passive sonar, towed array, hull-mounted, sonobuoy, dipping sonar
- `detection/underwater_detection.py` — submarine detection: acoustic propagation, MAD, wake detection, periscope detection
- `detection/fog_of_war.py` — per-side world view manager (land, air, and maritime)

**Visualization**: detection probability maps, belief state vs ground truth overlay, sensor coverage, sonar propagation

**Exit Criteria**: Units detect each other probabilistically based on range, terrain, sensor type, signature, and environmental conditions (weather, illumination, thermal contrast, acoustic propagation, radar ducting). Detection → classification → identification pipeline produces confidence levels. Each side maintains a noisy, decaying belief state via Kalman filtering. Multi-source intel fusion combines sensor data with SIGINT/HUMINT/IMINT. Deception degrades enemy belief accuracy. Sonar models produce realistic submarine detection in varying acoustic environments. All reproducible from seed.

---

## Phase 4: Combat Resolution
**Goal**: Units engage and the simulation resolves outcomes across all combat domains.

### 4a: Direct Fire & Fundamentals
- `combat/engagement.py` — engagement sequencing, target selection, range determination
- `combat/ballistics.py` — projectile physics: trajectory, drag, wind, Coriolis (long range)
- `combat/hit_probability.py` — P(hit): range, weapon, skill, target motion, conditions
- `combat/damage.py` — terminal effects: lethality, armor penetration, behind-armor effects
- `combat/suppression.py` — fire volume → suppression state
- `combat/ammunition.py` — ammo types, consumption, selection (missiles individually tracked)
- `combat/fratricide.py` — IFF uncertainty, deconfliction, identification errors

### 4b: Indirect Fire & Deep Fires
- `combat/indirect_fire.py` — tube artillery (fire missions, counterbattery, ammo selection) AND rocket artillery (MLRS dispersal, pod-based ammo, GMLRS precision, shoot-and-scoot)

### 4c: Surface-to-Surface Missiles
- `combat/missiles.py` — TBMs, land-attack cruise missiles, coastal defense SSMs, kill chain modeling, missile logistics

### 4d: Air Combat, Air Defense & Missile Defense
- `combat/air_combat.py` — air-to-air BVR and WVR, missile Pk, countermeasures
- `combat/air_ground.py` — CAS, SEAD/DEAD, air interdiction
- `combat/air_defense.py` — SAM/AAA envelopes (3D), shoot-look-shoot, EMCON, IAMD shared mechanics
- `combat/missile_defense.py` — BMD (Patriot/THAAD/Aegis), cruise missile defense, C-RAM (Iron Dome/Phalanx)

### 4e: Naval Combat
- `combat/naval_surface.py` — anti-ship missile (salvo model), naval gunfire, torpedo, point defense, chaff, ship damage/DC
- `combat/naval_subsurface.py` — torpedo engagements, submarine-launched missiles, evasion
- `combat/naval_mine.py` — mine types, laying, sweeping, hunting, risk-based transit
- `combat/naval_gunfire_support.py` — shore bombardment, fire support coordination
- `combat/amphibious_assault.py` — beach assault resolution, shore defenses
- `combat/carrier_ops.py` — sortie generation, deck cycle, CAP management

### 4f: Morale & Human Factors
- `morale/state.py` — Markov state machine (steady/shaken/broken/routed/surrendered)
- `morale/cohesion.py` — unit cohesion, nearby friendlies, leadership, unit history
- `morale/stress.py` — stress/fatigue/sleep deprivation (random walk with drift)
- `morale/experience.py` — training level, combat experience learning curve
- `morale/psychology.py` — PSYOP effects, propaganda, surrender inducement, civilian reaction
- `morale/rout.py` — rout, rally, surrender mechanics, POW generation

**Visualization**: engagement outcomes, suppression zones, morale heatmaps, artillery impact areas, missile flight paths, air defense coverage, naval engagement tracks

**Exit Criteria**: Forces can engage across all domains — direct fire, indirect fire (tube and rocket artillery), surface-to-surface missiles (TBM, cruise, coastal defense), air-to-air, air-to-ground, air defense, missile defense (BMD + C-RAM), and naval (surface, subsurface, mine, amphibious, carrier ops). Ballistic physics model produces realistic trajectories. Kill chain timing constrains missile responsiveness. Suppression and morale resolve stochastically with Markov transitions. Fratricide occurs when identification confidence is low. Ammo (including missiles) consumed by type. Combined arms matter. All reproducible from seed.

---

## Phase 5: C2 Infrastructure
**Goal**: Orders flow through a chain of command with realistic delays, degradation, and constraints. The plumbing — not the brains.

**Rationale for split**: The original Phase 5 had 27 modules (larger than Phase 4's 25). Phase 4 showed that >20 modules per phase creates API mismatch risk when parallelizing. AI decision-making (now Phase 8) also benefits from seeing logistics state (Phase 6), so deferring AI until after logistics gives it richer inputs.

### 5a: Command Authority & Communications
- `c2/command.py` — command authority, relationships (OPCON/TACON/ADCON/support), succession
- `c2/communications.py` — comms reliability, bandwidth, degradation, EMCON, means (radio/wire/messenger/data link)
- `c2/naval_c2.py` — fleet organization (TF/TG/TU), naval data links, submarine comms (VLF/ELF)

### 5b: Orders System
- `c2/orders/types.py` — order type hierarchy: OPORD, FRAGO, WARNO
- `c2/orders/individual.py` — individual/fire team orders: move to, engage, take cover, suppress, breach
- `c2/orders/tactical.py` — squad through battalion: assault, defend, ambush, patrol, recon
- `c2/orders/operational.py` — brigade through corps: main effort, reserve commit, deep ops
- `c2/orders/strategic.py` — theater/campaign: force allocation, strategic objectives, political constraints
- `c2/orders/naval_orders.py` — formation orders, ASW prosecution, strike assignment, convoy routing, blockade
- `c2/orders/air_orders.py` — ATO, ACO, SPINS, strike packages, CAS integration, CAP assignments
- `c2/orders/propagation.py` — order transmission: delays, degradation, misinterpretation probability
- `c2/orders/execution.py` — order execution tracking: compliance, adaptation, deviation reporting

### 5c: ROE, Coordination & Mission Command
- `c2/roe.py` — rules of engagement, escalation, political constraints, law of armed conflict
- `c2/coordination.py` — fire support coordination (FSCL/CFL/NFA/RFA, HPTL/AGM, missile flight corridors), airspace deconfliction, boundaries
- `c2/mission_command.py` — commander's intent, mission-type orders, subordinate initiative/adaptation

**Visualization**: command hierarchy tree, order propagation timeline, C2 link status

**Exit Criteria**: Orders propagate through chain of command at all echelons (individual through strategic, plus naval and air) with realistic delays and degradation. Communication means have distinct reliability/speed/intercept profiles. ROE constrains engagements. Fire support and airspace coordination function. C2 disruption (HQ destruction) degrades unit effectiveness with succession mechanics. All reproducible from seed.

---

## Phase 6: Logistics & Supply
**Goal**: Sustaining the force — armies need beans, bullets, fuel, and maintenance.

### 6a: Supply Network & Consumption
- `logistics/supply_network.py` — supply chain graph (networkx), leverages terrain infrastructure
- `logistics/supply_classes.py` — military supply classification (Class I-X), ammo types, fuel types
- `logistics/consumption.py` — per-unit consumption models (ammo by type, fuel by activity, environmentally variable)

### 6b: Transport & Stockpiles
- `logistics/transport.py` — truck convoys, airlift, aerial resupply/airdrop, rail
- `logistics/stockpile.py` — depot and stockpile management, captured supplies/equipment

### 6c: Maintenance, Engineering & Medical
- `logistics/maintenance.py` — equipment maintenance cycles, repair, breakdown probability, spare parts
- `logistics/engineering.py` — bridging, road building, fortification, obstacle emplacement/clearing
- `logistics/medical.py` — casualty evacuation chain, triage queueing, treatment, return-to-duty
- `logistics/prisoners.py` — POW handling, processing, resource cost

### 6d: Naval Logistics
- `logistics/naval_logistics.py` — UNREP/RAS, port operations, sealift, LOTS
- `logistics/naval_basing.py` — naval bases, FOBs, anchorage, port capacity/throughput

### 6e: Disruption & Special Topics
- `logistics/disruption.py` — interdiction, route destruction, sabotage, blockade, seasonal route degradation
- Missile/guided munition logistics: TEL reload cycles, VLS non-reloadable at sea, interceptor inventory sustainability (tracked via supply_classes + consumption)

**Visualization**: supply network graph, stockpile levels, flow rates, bottleneck identification, route status, naval logistics overlay

**Exit Criteria**: Units consume supplies by class (ammo by type, fuel, food/water, medical, spare parts) with environmentally variable rates. Supply flows through a network from depots to front-line units via transport modes (truck, air, rail, sea). Route throughput depends on terrain infrastructure and seasonal conditions. Equipment requires maintenance; deferred maintenance increases breakdown probability. Engineering units build/repair infrastructure and emplace/clear obstacles. Medical system evacuates and treats casualties. Naval logistics (UNREP, port ops, sealift) sustain fleet operations. Interdiction disrupts supply. Units degrade when supplies run out. All reproducible from seed.

---

## Phase 7: Engagement Validation
**Goal**: Prove the combat model produces realistic results BEFORE building AI on top of it. Early validation catches calibration issues while fixes are cheap.

**Rationale**: With Phases 0-6 complete, we have terrain, weather, entities, movement, detection, combat, morale, C2 plumbing, and logistics — everything needed to run realistic engagement-level scenarios without AI commanders. Validating now means the AI (Phase 8) is built on a proven combat foundation.

### 7a: Validation Infrastructure
- `validation/scenario_runner.py` — lightweight runner: loads terrain + forces + objectives, wires modules, executes time steps
- `validation/monte_carlo.py` — Monte Carlo harness: run N iterations with different seeds, collect statistics
- `validation/metrics.py` — engagement-level metrics: casualty exchange ratios, duration, ammunition expenditure, territorial outcomes
- `validation/historical_data.py` — structured historical data loader (JSON/YAML format for engagement parameters)

### 7b: Engagement Scenario Packs
Build 2-3 scenario packs from well-documented historical engagements:

1. **73 Easting (1991)** — US armor vs Iraqi armor in open desert. Tests: direct fire, hit probability at range, DeMarre penetration, crew quality asymmetry, morale collapse. Well-documented casualty ratios and engagement duration.
2. **Falklands — naval engagements (1982)** — Exocet ASM vs Type 42 destroyers, Argentine air attacks on the task force. Tests: Wayne Hughes salvo model, air defense (Sea Dart/Sea Wolf), ship damage/DC, sortie generation. Well-documented ship losses and missile expenditure.
3. **Golan Heights (1973)** — Israeli defense against Syrian armor. Tests: defensive position advantage, combined arms (tanks + ATGMs + artillery), force ratio survivability, morale under pressure. Well-documented force ratios and casualty exchanges.

### 7c: Calibration
- Compare Monte Carlo distributions against historical outcomes
- Identify parameters that need tuning (hit probability modifiers, damage scaling, morale transition rates)
- Document model deficiencies by domain with severity rating
- Adjust combat parameters to produce statistically plausible outcomes

**Visualization**: Monte Carlo outcome distributions, casualty ratio histograms, engagement timeline comparisons, parameter sensitivity plots

**Exit Criteria**: All 2-3 engagement scenarios produce casualty exchange ratios within 2x of historical outcomes across 1000-run Monte Carlo. Major model deficiencies documented with severity. Combat parameter calibration applied. Validation infrastructure reusable for Phase 10.

---

## Phase 8: AI & Planning
**Goal**: AI commanders make echelon-appropriate decisions informed by doctrine and personality. The brains.

**Rationale for position**: AI decision-making is the most conceptually complex phase. By this point, the AI has access to: combat state (Phase 4), detection/intel (Phase 3), morale state (Phase 4), C2 plumbing (Phase 5), logistics state (Phase 6), AND validated combat parameters (Phase 7). Building AI last among the domain modules ensures it reasons about real, calibrated data rather than untested approximations.

### 8a: AI Decision-Making
- `c2/ai/ooda.py` — OODA loop implementation (observe-orient-decide-act cycle with time costs)
- `c2/ai/commander.py` — commander personality model: risk tolerance, aggression, initiative, experience
- `c2/ai/assessment.py` — situation assessment: combat power, terrain, supply, morale, intel, environment
- `c2/ai/decisions.py` — echelon-appropriate decision logic (individual through strategic)
- `c2/ai/adaptation.py` — reacting to changed situations, plan adjustment, opportunity exploitation
- `c2/ai/doctrine.py` — doctrinal templates per nation/era (offensive, defensive, retrograde, stability, enabling)
- `c2/ai/stratagems.py` — deception plans, economy of force, concentration, surprise, tempo control

### 8b: Planning Process
- `c2/planning/process.py` — configurable planning (MDMP, rapid planning, intuitive decision)
- `c2/planning/mission_analysis.py` — specified/implied tasks, constraints, risk assessment
- `c2/planning/coa.py` — COA development, analysis (wargaming), comparison, selection
- `c2/planning/estimates.py` — running estimates: personnel, intel, operations, logistics, comms
- `c2/planning/phases.py` — operation phasing: shaping, decisive, exploitation, transition

**Note on scope**: `c2/ai/doctrine.py` and `c2/ai/commander.py` provide the *framework* for doctrinal and personality-driven AI. Named doctrinal schools (Clausewitzian AI, Sun Tzu AI, etc.) as described in brainstorm.md are deferred to Future Phases — they build ON TOP of this framework.

**Visualization**: OODA cycle timing, situation assessment overlay, COA comparison matrix, planning process flow

**Exit Criteria**: AI commanders make echelon-appropriate decisions via OODA cycle, informed by doctrine templates and personality. Planning process produces COAs from mission analysis with wargaming. Commanders adapt to changing situations. Situation assessment integrates combat, logistics, intel, morale, and terrain. All reproducible from seed.

---

## Phase 9: Simulation Orchestration & Integration
**Goal**: All systems work together. The master simulation loop ties everything into coherent multi-scale campaigns.

- `simulation/engine.py` — master simulation loop (hybrid tick + event), tick sequencing (environment first, then domain modules)
- `simulation/campaign.py` — campaign-level management, strategic AI, reinforcement pipeline
- `simulation/battle.py` — tactical battle resolution manager
- `simulation/scenario.py` — scenario loading, setup, initialization (terrain + forces + objectives + environment)
- `simulation/victory.py` — victory conditions, war termination criteria, objective evaluation
- `simulation/recorder.py` — event/state recording for replay and analysis
- `simulation/metrics.py` — simulation output metrics, statistical aggregation, analysis hooks

**Also in this phase**: multi-scale transitions (strategic graph ↔ tactical grid ↔ unit continuous), force aggregation/disaggregation, complete env→combat wiring for all domains, full checkpoint/replay validation across all modules

**Visualization**: comprehensive multi-scale display, campaign overview, drill-down to tactical engagements

**Exit Criteria**: Can define and run a complete multi-day campaign scenario with: full tactical resolution of all engagements, logistics flowing, intel updating, C2 functioning with AI commanders, environment evolving, and all domain modules interacting correctly. Victory conditions evaluate. Campaign-level AI makes strategic decisions. Scenario can be checkpointed, restored, and replayed identically from seed. Recorder captures full event history. Metrics provide statistical summaries.

---

## Phase 10: Full Campaign Validation & Backtesting
**Goal**: Prove the complete simulation produces realistic campaign-level results.

Building on Phase 7's engagement-level validation infrastructure and calibration:

- Expand scenario packs to full campaign duration (multi-day operations with logistics, C2, reinforcement)
- Add campaign-level metrics: logistics throughput, C2 effectiveness, operational tempo, culminating points
- Run Monte Carlo validation campaigns with AI commanders
- Compare campaign-level outcomes against historical analysis
- Validate AI decision quality (does it make defensible choices given the situation?)
- Performance profiling and optimization for campaign-length runs

**Exit Criteria**: Simulation produces statistically plausible outcomes for at least 2-3 historical scenarios at campaign scale across domains (land and naval). AI commanders make contextually appropriate decisions. Model deficiencies documented with severity. Performance acceptable for campaign-length runs.

---

## Future Phases (Post-MVP)
These are explicitly deferred until the core engine is validated:
- Full UI (separate language/framework)
- Electronic warfare — full EW module (interface points already defined in combat/ and detection/, see project-structure.md)
- Cyber operations
- NBC/CBRN effects (interface points already defined, see project-structure.md)
- Named doctrinal AI schools (Clausewitzian, Sun Tzu, maneuverist, etc.) — builds on the c2/ai/doctrine.py framework from Phase 8
- Multi-player / networked simulation
- Earlier era support (WW2, Napoleonic, etc.)
- Modding and scenario editor tools
- Performance optimization (Cython, GPU acceleration)

---

## Module-to-Phase Index

Every non-`__init__` module file from `project-structure.md` and its phase assignment:

| Module | Phase |
|--------|-------|
| `core/types.py` | 0 |
| `core/logging.py` | 0 |
| `core/rng.py` | 0 |
| `core/clock.py` | 0 |
| `core/events.py` | 0 |
| `core/config.py` | 0 |
| `core/checkpoint.py` | 0 |
| `coordinates/transforms.py` | 0 |
| `coordinates/spatial.py` | 0 |
| `coordinates/magnetic.py` | 1d |
| `terrain/heightmap.py` | 1a |
| `terrain/classification.py` | 1a |
| `terrain/los.py` | 1a |
| `terrain/strategic_map.py` | 1a |
| `terrain/hydrography.py` | 1b |
| `terrain/infrastructure.py` | 1b |
| `terrain/obstacles.py` | 1b |
| `terrain/population.py` | 1b |
| `terrain/bathymetry.py` | 1b |
| `terrain/maritime_geography.py` | 1b |
| `environment/astronomy.py` | 1c |
| `environment/time_of_day.py` | 1c |
| `environment/weather.py` | 1c |
| `environment/seasons.py` | 1c |
| `environment/obscurants.py` | 1c |
| `environment/sea_state.py` | 1c |
| `environment/underwater_acoustics.py` | 1c |
| `environment/electromagnetic.py` | 1c |
| `environment/conditions.py` | 1c |
| `entities/base.py` | 0 (stub), 2a (full) |
| `entities/events.py` | 2a |
| `entities/personnel.py` | 2a |
| `entities/equipment.py` | 2a |
| `entities/unit_classes/ground.py` | 2a |
| `entities/unit_classes/aerial.py` | 2a |
| `entities/unit_classes/air_defense.py` | 2a |
| `entities/unit_classes/naval.py` | 2a |
| `entities/unit_classes/support.py` | 2a |
| `entities/loader.py` | 2a |
| `entities/capabilities.py` | 2a |
| `entities/organization/hierarchy.py` | 2b |
| `entities/organization/echelons.py` | 2b |
| `entities/organization/task_org.py` | 2b |
| `entities/organization/staff.py` | 2b |
| `entities/organization/orbat.py` | 2b |
| `entities/organization/special_org.py` | 2b |
| `entities/organization/events.py` | 2b |
| `movement/events.py` | 2c |
| `movement/engine.py` | 2c |
| `movement/pathfinding.py` | 2c |
| `movement/fatigue.py` | 2c |
| `movement/formation.py` | 2c |
| `movement/obstacles.py` | 2c |
| `movement/mount_dismount.py` | 2c |
| `movement/naval_movement.py` | 2c |
| `movement/submarine_movement.py` | 2c |
| `movement/amphibious_movement.py` | 2c |
| `movement/airborne.py` | 2c |
| `detection/events.py` | 3 |
| `detection/sensors.py` | 3 |
| `detection/signatures.py` | 3 |
| `detection/detection.py` | 3 |
| `detection/identification.py` | 3 |
| `detection/estimation.py` | 3 |
| `detection/intel_fusion.py` | 3 |
| `detection/deception.py` | 3 |
| `detection/sonar.py` | 3 |
| `detection/underwater_detection.py` | 3 |
| `detection/fog_of_war.py` | 3 |
| `combat/events.py` | 4a |
| `combat/engagement.py` | 4a |
| `combat/ballistics.py` | 4a |
| `combat/hit_probability.py` | 4a |
| `combat/damage.py` | 4a |
| `combat/suppression.py` | 4a |
| `combat/ammunition.py` | 4a |
| `combat/fratricide.py` | 4a |
| `combat/indirect_fire.py` | 4b |
| `combat/missiles.py` | 4c |
| `combat/air_combat.py` | 4d |
| `combat/air_ground.py` | 4d |
| `combat/air_defense.py` | 4d |
| `combat/missile_defense.py` | 4d |
| `combat/naval_surface.py` | 4e |
| `combat/naval_subsurface.py` | 4e |
| `combat/naval_mine.py` | 4e |
| `combat/naval_gunfire_support.py` | 4e |
| `combat/amphibious_assault.py` | 4e |
| `combat/carrier_ops.py` | 4e |
| `morale/events.py` | 4f |
| `morale/state.py` | 4f |
| `morale/cohesion.py` | 4f |
| `morale/stress.py` | 4f |
| `morale/experience.py` | 4f |
| `morale/psychology.py` | 4f |
| `morale/rout.py` | 4f |
| `c2/events.py` | 5a |
| `c2/command.py` | 5a |
| `c2/communications.py` | 5a |
| `c2/naval_c2.py` | 5a |
| `c2/orders/types.py` | 5b |
| `c2/orders/individual.py` | 5b |
| `c2/orders/tactical.py` | 5b |
| `c2/orders/operational.py` | 5b |
| `c2/orders/strategic.py` | 5b |
| `c2/orders/naval_orders.py` | 5b |
| `c2/orders/air_orders.py` | 5b |
| `c2/orders/propagation.py` | 5b |
| `c2/orders/execution.py` | 5b |
| `c2/roe.py` | 5c |
| `c2/coordination.py` | 5c |
| `c2/mission_command.py` | 5c |
| `logistics/supply_network.py` | 6a |
| `logistics/supply_classes.py` | 6a |
| `logistics/consumption.py` | 6a |
| `logistics/transport.py` | 6b |
| `logistics/stockpile.py` | 6b |
| `logistics/maintenance.py` | 6c |
| `logistics/engineering.py` | 6c |
| `logistics/medical.py` | 6c |
| `logistics/prisoners.py` | 6c |
| `logistics/naval_logistics.py` | 6d |
| `logistics/naval_basing.py` | 6d |
| `logistics/disruption.py` | 6e |
| `validation/scenario_runner.py` | 7a |
| `validation/monte_carlo.py` | 7a |
| `validation/metrics.py` | 7a |
| `validation/historical_data.py` | 7a |
| `c2/ai/ooda.py` | 8a |
| `c2/ai/commander.py` | 8a |
| `c2/ai/assessment.py` | 8a |
| `c2/ai/decisions.py` | 8a |
| `c2/ai/adaptation.py` | 8a |
| `c2/ai/doctrine.py` | 8a |
| `c2/ai/stratagems.py` | 8a |
| `c2/planning/process.py` | 8b |
| `c2/planning/mission_analysis.py` | 8b |
| `c2/planning/coa.py` | 8b |
| `c2/planning/estimates.py` | 8b |
| `c2/planning/phases.py` | 8b |
| `simulation/engine.py` | 9 |
| `simulation/campaign.py` | 9 |
| `simulation/battle.py` | 9 |
| `simulation/scenario.py` | 9 |
| `simulation/victory.py` | 9 |
| `simulation/recorder.py` | 9 |
| `simulation/metrics.py` | 9 |

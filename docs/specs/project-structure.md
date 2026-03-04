# Project Structure & Module Decomposition
**Status**: Complete (Phase 20)
**Last Updated**: 2026-03-04

---

## Package Tree

```
stochastic-warfare/
├── pyproject.toml                    # Build config, dependencies, metadata
├── README.md
├── .claude/
│   ├── settings.json                 # Project hooks
│   └── skills/                       # Claude skills (17 total)
├── docs/
│   ├── brainstorm.md                 # Architecture decisions & rationale
│   ├── development-phases.md         # Development roadmap
│   ├── skills-and-hooks.md           # Dev infrastructure docs
│   └── specs/                        # Per-module specifications
│       └── project-structure.md      # (this document)
├── data/
│   ├── units/                        # YAML unit type definitions
│   │   ├── armor/                    # M1A2, T-72, Leopard 2, etc.
│   │   ├── infantry/                 # Rifle squad, mechanized, etc.
│   │   ├── artillery/                # M109, MLRS, mortar teams, etc.
│   │   ├── air_fixed_wing/           # F-16, A-10, Su-27, etc.
│   │   ├── air_rotary_wing/          # AH-64, UH-60, Mi-24, etc.
│   │   ├── air_defense/              # Patriot, S-300, MANPADS, etc.
│   │   ├── missiles/                 # SSM launchers: MLRS/HIMARS, Iskander, Tomahawk TEL, coastal defense (Bastion, NSM)
│   │   ├── support/                  # Engineers, logistics vehicles, HQ, comms, medical
│   │   ├── naval_surface/            # Destroyers, frigates, cruisers, carriers, patrol craft
│   │   ├── naval_subsurface/         # Attack submarines, ballistic missile submarines
│   │   ├── naval_amphibious/         # LHD, LPD, LST, landing craft, marines
│   │   ├── naval_mine_warfare/       # Minesweepers, minelayers, mine hunters
│   │   └── naval_auxiliary/          # Oilers, supply ships, hospital ships, salvage
│   ├── weapons/                      # Weapon system definitions (referenced by units)
│   ├── ammunition/                   # Ammunition type definitions (AP, HE, HEAT, smoke, illum, guided, rockets, missiles)
│   ├── sensors/                      # Sensor type definitions (referenced by units)
│   ├── signatures/                   # Unit signature profiles (visual, thermal, RCS, acoustic, EM)
│   ├── comms/                        # Communication equipment definitions (SINCGARS, Harris HF, Link 16, SATCOM, etc.)
│   ├── ew/                           # EW equipment definitions [Phase 16]
│   │   ├── jammers/                 # Jammer definitions (AN/ALQ-99, AN/TLQ-32, Krasukha-4, AN/SLQ-32, AN/ALQ-131, R-330Zh)
│   │   ├── eccm_suites/            # ECCM suite definitions (US fighter, US destroyer, Soviet SAM, Patriot)
│   │   └── sigint_collectors/      # SIGINT collector definitions (RC-135, ground station)
│   ├── space/                        # Space & satellite definitions [Phase 17]
│   │   ├── constellations/          # Constellation definitions (GPS NAVSTAR, GLONASS, Milstar, WGS, Keyhole, Lacrosse, SBIRS, Molniya, SIGINT LEO)
│   │   └── asat_weapons/           # ASAT weapon definitions (SM-3 Block IIA, Nudol, ground laser)
│   ├── cbrn/                         # CBRN agent & weapon definitions [Phase 18]
│   │   ├── agents/                  # Agent definitions (VX, sarin, mustard, chlorine, hydrogen_cyanide, anthrax, cs137)
│   │   ├── nuclear/                 # Nuclear weapon definitions (10kT, 100kT, 1MT)
│   │   └── delivery/               # Delivery system definitions (artillery shell, aerial bomb, SCUD warhead)
│   ├── logistics/                    # Logistics data definitions
│   │   ├── supply_items/            # Supply item definitions by NATO class (I, III, IV, VIII, IX)
│   │   ├── transport_profiles/      # Transport vehicle profiles (truck, C-130, rail, sealift)
│   │   └── medical_facilities/      # Medical facility definitions (aid station, field hospital)
│   ├── organizations/                # TO&E definitions per nation/era
│   │   ├── us_modern/               # US Army/USMC/Navy modern structure
│   │   ├── russian_modern/          # Russian ground/naval/air structure
│   │   ├── chinese_modern/          # PLA structure
│   │   ├── nato_generic/            # Generic NATO-standard allied force structure
│   │   ├── irregular/               # Insurgent, militia, guerrilla organizational templates
│   │   └── historical/              # WW2, Napoleonic, etc. (future era support)
│   ├── doctrine/                     # Doctrinal templates per nation/era/domain
│   │   ├── us/                      # US doctrine: FM 3-0 operations framework, mission command
│   │   ├── russian/                 # Russian doctrine: deep operations, correlation of forces
│   │   ├── nato/                    # NATO doctrinal procedures
│   │   └── generic/                 # Era/domain-generic tactical patterns
│   ├── schools/                      # Doctrinal school definitions [Phase 19]
│   │   └── (9 files)                # clausewitzian, maneuverist, attrition, airland_battle, air_power, sun_tzu, deep_battle, maritime_mahanian, maritime_corbettian
│   ├── commander_profiles/           # Commander personality archetypes (risk tolerance, style, preferences)
│   ├── maritime/                     # Maritime-specific data: port facilities, sea lanes, chokepoints, bathymetry reference
│   ├── eras/                         # Era-specific data packages [Phase 20+]
│   │   └── ww2/                     # WW2 era data
│   │       ├── units/               # 15 unit definitions (5 armor, 3 infantry, 4 air, 3 naval)
│   │       ├── weapons/             # 8 weapon definitions (tank guns, MGs, torpedo, naval guns)
│   │       ├── ammunition/          # 13 ammo definitions (AP/HE variants, torpedo, naval)
│   │       ├── sensors/             # 4 sensor definitions (eyeball, radar, naval radar, hydrophone)
│   │       ├── signatures/          # 15 signature profiles (one per unit, zeroed thermal)
│   │       ├── doctrine/            # 4 doctrine templates (blitzkrieg, soviet_deep_ops, british_deliberate, us_combined_arms_ww2)
│   │       ├── commanders/          # 3 commander profiles (Patton, Montgomery, Zhukov types)
│   │       └── scenarios/           # 3 validation scenarios (Kursk, Midway, Normandy Bocage)
│   └── scenarios/                    # Complete scenario packages
│       ├── example_scenario/
│       │   ├── scenario.yaml         # Master scenario config: start date/time (UTC), duration, initial weather, time zone
│       │   ├── terrain/              # Terrain data: elevation, classification, soil, vegetation, infrastructure
│       │   ├── infrastructure/       # Road/rail/bridge networks, building data, utilities
│       │   ├── population/           # Civilian population data and disposition
│       │   ├── maritime/             # Bathymetry, ports, sea lanes, acoustic environment profiles, tidal harmonic constituents
│       │   ├── environment/          # Climate zone, prevailing weather patterns, seasonal parameters, magnetic declination grid
│       │   ├── forces/               # OOB and initial dispositions per side (land, air, naval)
│       │   └── objectives/           # Victory conditions and ROE
│       ├── 73_easting/              # Phase 7: 73 Easting validation scenario
│       ├── falklands_naval/         # Phase 7: Falklands naval validation scenario
│       ├── golan_heights/           # Phase 7: Golan Heights validation scenario
│       ├── test_campaign/           # Phase 9: Minimal campaign test (2 sides, 1 objective, 24h)
│       ├── test_campaign_multi/     # Phase 9: Multiple engagement points (2 objectives, 48h)
│       ├── test_campaign_reinforce/ # Phase 9: Reinforcement schedule test (3 waves)
│       ├── test_campaign_logistics/ # Phase 9: Supply chain emphasis (multiple depots, 72h)
│       ├── golan_campaign/         # Phase 10: Golan Heights 4-day campaign validation
│       ├── falklands_campaign/     # Phase 10: Falklands San Carlos 5-day campaign validation
│       ├── bekaa_valley_1982/     # Phase 16: Bekaa Valley SEAD validation (Israeli EW vs Syrian SAMs)
│       ├── gulf_war_ew_1991/      # Phase 16: Gulf War EW campaign validation (Coalition vs Iraqi IADS)
│       ├── space_gps_denial/      # Phase 17: PGM accuracy comparison (full GPS vs degraded vs denied)
│       ├── space_isr_gap/         # Phase 17: Satellite overpass gap exploitation validation
│       ├── space_asat_escalation/ # Phase 17: Kinetic ASAT cascading constellation degradation
│       ├── cbrn_chemical_defense/ # Phase 18: Chemical attack on defended position (dispersal, MOPP, casualties)
│       └── cbrn_nuclear_tactical/ # Phase 18: Tactical nuclear weapon blast/EMP/fallout validation
├── tests/
│   ├── conftest.py                   # Shared fixtures (rng, event_bus, sim_clock) + helpers
│   ├── unit/                         # Fast, isolated unit tests
│   ├── integration/                  # Multi-module integration tests
│   ├── benchmarks/                   # Performance benchmarks + determinism verification [Phase 13]
│   └── validation/                   # Historical backtest scenarios
├── scripts/
│   └── visualize/                    # Matplotlib visualization utilities
└── stochastic_warfare/               # ===== MAIN PACKAGE =====
    ├── __init__.py
    ├── core/                         # Foundational infrastructure
    │   ├── __init__.py
    │   ├── rng.py                    # Central RNG manager, stream forking
    │   ├── clock.py                  # Simulation clock, tick management, calendar-aware (real date/time, UTC)
    │   ├── events.py                 # Event system (MRO-based publish dispatch, within-tick event queue)
    │   ├── config.py                 # YAML config loading, pydantic base models
    │   ├── checkpoint.py             # State serialization, checkpoint/restore
    │   ├── logging.py                # Project logging setup
    │   ├── types.py                  # Shared type definitions, enums, constants
    │   └── numba_utils.py           # Numba JIT decorators with pure-Python fallback (@optional_jit) [Phase 13b]
    ├── coordinates/                  # Coordinate systems & transforms
    │   ├── __init__.py
    │   ├── transforms.py             # Geodetic ↔ UTM ↔ ENU conversions
    │   ├── spatial.py                # Spatial queries, distance, bearing
    │   └── magnetic.py              # Magnetic declination model (WMM), compass navigation corrections
    ├── terrain/                      # Terrain representation & analysis
    │   ├── __init__.py
    │   ├── heightmap.py              # DEM loading, elevation queries (scalar + batch), slope, aspect
    │   ├── classification.py         # Land cover, soil type, trafficability, concealment vs cover
    │   ├── hydrography.py            # Rivers (depth, current, ford points), lakes, flooding, watersheds
    │   ├── infrastructure.py         # Roads, bridges, rail, buildings (type, height, construction), utilities, tunnels
    │   ├── obstacles.py              # Natural (ravines, cliffs) and man-made (minefields, barriers, wire, ditches)
    │   ├── population.py             # Civilian population density, disposition (friendly/neutral/hostile)
    │   ├── los.py                    # Line-of-sight (vectorized ray march + scalar fallback for buildings)
    │   ├── bathymetry.py             # Ocean/sea floor depth, bottom type (affects sonar, mine placement)
    │   ├── maritime_geography.py     # Coastline, ports, harbors, straits, chokepoints, sea lanes, anchorages
    │   ├── strategic_map.py          # Graph-based strategic terrain (nodes + edges — includes sea zones and maritime routes)
    │   ├── data_pipeline.py          # Real-world terrain: tile management, caching, unified loader (Phase 15)
    │   ├── real_heightmap.py         # SRTM/ASTER GeoTIFF → Heightmap loader (Phase 15)
    │   ├── real_classification.py    # Copernicus land cover → TerrainClassification (Phase 15)
    │   ├── real_infrastructure.py    # OSM GeoJSON → InfrastructureManager (Phase 15)
    │   └── real_bathymetry.py        # GEBCO NetCDF → Bathymetry (Phase 15)
    ├── environment/                  # Weather, time-of-day, dynamic conditions, obscurants
    │   ├── __init__.py
    │   ├── weather.py                # Weather state, transitions, precipitation, wind, temperature
    │   ├── time_of_day.py            # Day/night cycle, lighting, lunar illumination, thermal crossover
    │   ├── obscurants.py             # Smoke, dust, fog — dynamic visibility reduction (deployed or natural)
    │   ├── seasons.py                # Seasonal effects: ground state (frozen/mud), vegetation density, sea ice
    │   ├── sea_state.py              # Wave height/period, swell, sea surface temperature, currents, tides
    │   ├── underwater_acoustics.py   # Sound velocity profile, thermoclines, convergence zones, bottom bounce, ambient noise
    │   ├── astronomy.py             # Solar/lunar orbital mechanics: position, phase, rise/set, twilight, tidal forcing
    │   ├── electromagnetic.py       # RF propagation, ionospheric conditions, atmospheric refraction, radar ducting
    │   └── conditions.py             # Unified condition queries (composites all modifiers for land, air, AND maritime consumers)
    ├── entities/                     # Units and organizational structures
    │   ├── __init__.py
    │   ├── base.py                   # Base entity class, common state/interface
    │   ├── events.py                 # Entity-level events (personnel casualties, equipment breakdown)
    │   ├── personnel.py              # Crew/individual modeling: roles, skills, experience, casualties
    │   ├── equipment.py              # Equipment state: degradation, maintenance, breakdown probability
    │   ├── unit_classes/             # Unit class hierarchy (behavior definitions)
    │   │   ├── __init__.py
    │   │   ├── ground.py             # Ground unit base (armor, infantry, mechanized, artillery)
    │   │   ├── aerial.py             # Aerial unit base: fixed-wing (fighter, attack, bomber, recon, transport) and rotary-wing (attack, utility, recon)
    │   │   ├── air_defense.py        # Air defense unit base (SAM, AAA, MANPADS, radar — land and shipborne)
    │   │   ├── naval.py              # Naval unit base: surface combatants, submarines, amphibious, mine warfare, auxiliary
    │   │   └── support.py            # Support units (logistics vehicles, HQ, engineers, comms, medical)
    │   ├── loader.py                 # YAML → pydantic → unit instance factory
    │   ├── organization/             # Force structure, OOB, task organization
    │   │   ├── __init__.py
    │   │   ├── hierarchy.py          # Configurable echelon hierarchy (nation/era-agnostic tree structure)
    │   │   ├── echelons.py           # Echelon type definitions: fire team through theater/front, configurable per nation
    │   │   ├── task_org.py           # Dynamic task organization: attach/detach, cross-attachment, combined arms TF
    │   │   ├── staff.py              # Staff functions (S1-S6/G1-G6/J1-J6) as functional capabilities affecting C2 performance
    │   │   ├── orbat.py              # Order of battle loading, TO&E (table of org & equipment) definitions
    │   │   ├── special_org.py        # Non-standard organizations: SOF, irregular/insurgent (cell/network), coalition/joint
    │   │   └── events.py            # Organization events (task org changes)
    │   └── capabilities.py           # Combat power assessment: weighted factors, force ratios, readiness computation
    ├── movement/                     # Movement & pathfinding
    │   ├── __init__.py
    │   ├── events.py                 # Movement events (waypoint reached, formation change, mount/dismount)
    │   ├── engine.py                 # Movement execution (terrain speed, deviation, load effects)
    │   ├── pathfinding.py            # A* and route planning (terrain, obstacle, threat-aware)
    │   ├── fatigue.py                # Fatigue accumulation model, sleep deprivation, recovery
    │   ├── formation.py              # Formation movement, spacing, coherence
    │   ├── obstacles.py              # Obstacle interaction: breaching, bridging, clearing, bypassing
    │   ├── mount_dismount.py         # Mount/dismount mechanics for mechanized infantry, embark/debark
    │   ├── naval_movement.py         # Ship movement: speed-fuel curves, formation steaming, turning circles, draft constraints
    │   ├── submarine_movement.py     # Submarine depth management, speed-noise tradeoff, snorkel, periscope depth
    │   ├── amphibious_movement.py    # Ship-to-shore movement, beach approach, over-the-horizon assault, landing craft
    │   ├── airborne.py              # Airborne/air assault: parachute drop, helicopter insertion, DZ/LZ selection, assembly
    │   └── convoy.py                # WW2 convoy operations: formation, speed limiting, stragglers, wolf pack, depth charge [Phase 20b]
    ├── detection/                    # Intelligence, sensors, & fog of war
    │   ├── __init__.py
    │   ├── events.py                 # Detection events (contact gained/lost, track update, ID change)
    │   ├── sensors.py                # Sensor models (visual, thermal, radar, acoustic, seismic); cached sensor_type
    │   ├── signatures.py             # Unit signature profiles: visual, thermal, radar cross-section, acoustic, EM emission
    │   ├── detection.py              # SNR-based detection probability engine (Pd, Pfa, ROC)
    │   ├── identification.py         # Classification & ID confidence (detected → classified → identified)
    │   ├── estimation.py             # Kalman filter state estimation (pre-alloc H/I₄ matrices, belief state)
    │   ├── intel_fusion.py           # Multi-source intelligence fusion (SIGINT, HUMINT, IMINT, sensor data)
    │   ├── deception.py              # Decoys, feints, false signals, camouflage effectiveness
    │   ├── sonar.py                  # Sonar models: active/passive, towed array, hull-mounted, sonobuoy, dipping
    │   ├── underwater_detection.py   # Submarine detection: acoustic propagation through environment, MAD, wake detection, periscope detection
    │   └── fog_of_war.py             # Fog of war manager (per-side world view — land, air, AND maritime)
    ├── combat/                       # Combat resolution
    │   ├── __init__.py
    │   ├── events.py                 # Combat events (engagement, hit, kill, fratricide, suppression)
    │   ├── engagement.py             # Engagement sequencing, target selection, range determination
    │   ├── ballistics.py             # Projectile physics: trajectory, drag, wind, Coriolis (long range)
    │   ├── hit_probability.py        # P(hit) model: range, weapon, skill, target motion, conditions
    │   ├── damage.py                 # Terminal effects: lethality, armor penetration, behind-armor effects
    │   ├── suppression.py            # Suppression mechanics: volume of fire → suppression state
    │   ├── indirect_fire.py          # Artillery & rocket artillery: fire missions, adjustment, counterbattery, area effects, MLRS dispersal
    │   ├── missiles.py               # Surface-to-surface missiles: TBMs, cruise missiles, coastal defense SSMs, kill chain
    │   ├── missile_defense.py        # BMD, cruise missile defense, C-RAM/short-range air defense vs rockets & artillery
    │   ├── air_combat.py             # Air-to-air engagement model, BVR and WVR
    │   ├── air_ground.py             # CAS, SEAD/DEAD, close air support integration with ground
    │   ├── air_defense.py            # SAM/AAA engagement envelopes, shoot-look-shoot, EMCON
    │   ├── ammunition.py             # Ammo types (AP, HE, HEAT, smoke, illum), consumption, selection
    │   ├── naval_surface.py          # Surface warfare: anti-ship missiles, naval gunfire, torpedo attack, point defense
    │   ├── naval_subsurface.py       # Submarine warfare: torpedo engagements, submarine-launched missiles, evasion
    │   ├── naval_mine.py             # Mine warfare: mine laying, sweeping, hunting, mine types (contact, influence, smart)
    │   ├── naval_gunfire_support.py  # Shore bombardment, naval fire support for ground forces
    │   ├── amphibious_assault.py     # Beach assault resolution, shore defenses, landing operations
    │   ├── carrier_ops.py            # Carrier flight operations, sortie generation rate, deck cycle, CAP management
    │   ├── fratricide.py             # Friendly fire: IFF uncertainty, deconfliction, identification errors
    │   ├── iads.py                   # IADS sector model: radar handoff chain, SEAD degradation, sector health [Phase 12f]
    │   ├── air_campaign.py           # Air campaign management: sortie capacity, pilot fatigue, weather days, attrition [Phase 12f]
    │   ├── strategic_targeting.py    # Strategic targeting: TPL generation, BDA cycle, target-effect chains [Phase 12f]
    │   ├── naval_gunnery.py          # WW2 naval gunnery: bracket firing, fire control quality, 2D Gaussian dispersion [Phase 20b]
    │   └── strategic_bombing.py      # WW2 strategic bombing: CEP area damage, flak, fighter escort, target regeneration [Phase 20b]
    ├── morale/                       # Morale & human factors
    │   ├── __init__.py
    │   ├── events.py                 # Morale events (state change, rout, rally, surrender)
    │   ├── state.py                  # Morale state machine (Markov transitions): steady/shaken/broken/routed/surrendered
    │   ├── cohesion.py               # Unit cohesion, nearby friendlies, leadership, unit history/reputation
    │   ├── stress.py                 # Stress/fatigue/sleep deprivation accumulation (random walk with drift)
    │   ├── experience.py             # Training level, combat experience learning curve, skill progression
    │   ├── psychology.py             # PSYOP effects, propaganda, surrender inducement, civilian reaction
    │   └── rout.py                   # Rout, rally, surrender mechanics, POW generation
    ├── c2/                           # Command & Control (Phase 5: plumbing; Phase 8: AI/planning)
    │   ├── __init__.py
    │   ├── events.py                 # C2 events (command status, succession, comms, orders, ROE, coordination, initiative)
    │   ├── command.py                # Command authority, command relationships (OPCON, TACON, ADCON, support)
    │   ├── orders/                   # Order system
    │   │   ├── __init__.py
    │   │   ├── types.py              # Order type hierarchy: OPORD, FRAGO, WARNO, and domain-specific orders
    │   │   ├── individual.py         # Individual/fire team level: move to, engage, take cover, suppress, breach
    │   │   ├── tactical.py           # Squad through battalion: assault, defend, ambush, patrol, recon, screen, guard
    │   │   ├── operational.py        # Brigade through corps: main effort, reserve commit, phase lines, deep ops, shaping
    │   │   ├── strategic.py          # Theater/campaign: force allocation, strategic objectives, political constraints, alliance
    │   │   ├── naval_orders.py       # Naval-specific: formation orders, ASW prosecution, strike assignment, convoy routing, blockade
    │   │   ├── air_orders.py         # Air-specific: ATO (Air Tasking Order), ACO, SPINS, strike packages, CAP assignments
    │   │   ├── propagation.py        # Order transmission: delays, degradation, misinterpretation probability
    │   │   └── execution.py          # Order execution tracking: compliance, adaptation, deviation reporting
    │   ├── planning/                 # Planning process [PHASE 8b]
    │   │   ├── __init__.py
    │   │   ├── process.py            # MDMP state machine (INTUITIVE/DIRECTIVE/RAPID/MDMP), 1/3-2/3 rule
    │   │   ├── mission_analysis.py   # Mission analysis: specified/implied/essential tasks, risks, constraints, key terrain
    │   │   ├── coa.py                # COA development, Lanchester wargaming, weighted comparison, softmax selection
    │   │   ├── estimates.py          # Running estimates (5 types), periodic update, significant change events
    │   │   └── phases.py             # Condition-based operational phasing with branches and sequels
    │   ├── communications.py         # Comms reliability, bandwidth, degradation, EMCON, means (radio/wire/messenger/data link)
    │   ├── roe.py                    # Rules of engagement, escalation, political constraints, law of armed conflict
    │   ├── coordination.py           # Fire support coord, airspace deconfliction, boundaries, sea-land-air integration
    │   ├── naval_c2.py              # Fleet org (TF/TG/TU), naval data links, submarine comms (VLF/ELF)
    │   ├── mission_command.py        # Commander's intent, mission-type orders, subordinate initiative/adaptation
    │   ├── joint_ops.py             # Joint task force command: service coordination, liaison, coalition caveats [Phase 12a]
    │   └── ai/                       # AI decision-making [PHASE 8a]
    │       ├── __init__.py
    │       ├── ooda.py               # OODA loop timer/FSM (echelon-scaled, log-normal friction)
    │       ├── commander.py          # YAML personality profiles (aggression, caution, flexibility, experience, decision_speed)
    │       ├── assessment.py         # 7-factor situation assessment (force ratio, terrain, supply, morale, intel, env, C2)
    │       ├── decisions.py          # 5 echelon-specific decision functions (individual through corps+)
    │       ├── adaptation.py         # 7-trigger plan adaptation (casualties, force ratio, supply, morale, opportunity, surprise, C2)
    │       ├── doctrine.py           # YAML doctrine templates (US, Russian, NATO, generic) with action/echelon filtering
    │       ├── stratagems.py         # 6 stratagem types with echelon+experience gating (deception, concentration, surprise, etc.)
    │       └── schools/              # Doctrinal AI schools — Strategy pattern [Phase 19]
    │           ├── __init__.py       # SchoolRegistry + SchoolLoader
    │           ├── base.py           # SchoolDefinition pydantic model + DoctrinalSchool ABC (8 hooks)
    │           ├── clausewitzian.py  # Center-of-gravity, decisive engagement, culmination awareness
    │           ├── maneuverist.py    # Tempo/OODA ×0.7, bypass, indirect approach
    │           ├── attrition.py      # Exchange ratio, fire superiority, deliberate operations
    │           ├── airland_battle.py # Echelon-dependent deep/close, sensor-to-shooter
    │           ├── air_power.py      # Five Rings, air superiority prerequisite
    │           ├── sun_tzu.py        # Intel ×3, opponent modeling, counter-posture scoring
    │           ├── deep_battle.py    # Echeloned assault, reserve management, operational depth
    │           └── maritime.py       # MahanianSchool + CorbettianSchool
    ├── logistics/                    # Supply & logistics
    │   ├── __init__.py
    │   ├── events.py                 # Logistics events (supply delivery/shortage/depletion, convoy, maintenance, engineering, medical, POW, naval, disruption)
    │   ├── supply_network.py         # Supply chain graph (networkx), leverages terrain infrastructure
    │   ├── supply_classes.py         # Military supply classification (Class I-X), ammo types, fuel types
    │   ├── consumption.py            # Per-unit consumption models (ammo by type, fuel by activity, food, water)
    │   ├── transport.py              # Transport units, convoys, airlift, aerial resupply/airdrop
    │   ├── stockpile.py              # Depot and stockpile management, captured supplies/equipment
    │   ├── maintenance.py            # Equipment maintenance cycles, repair, breakdown probability, spare parts
    │   ├── engineering.py            # Engineer operations: bridging, road building, fortification, obstacle emplacement/clearing
    │   ├── medical.py                # Casualty evacuation chain, triage queueing, treatment, return-to-duty
    │   ├── prisoners.py              # POW handling, processing, resource cost of prisoner management
    │   ├── naval_logistics.py         # Underway replenishment (UNREP/RAS), port operations, sealift, LOTS
    │   ├── naval_basing.py           # Naval bases, forward operating bases, anchorage, port capacity/throughput
    │   ├── disruption.py             # Interdiction, route destruction, sabotage, blockade
    │   └── production.py             # Supply regeneration: production facilities, infrastructure-coupled output [Phase 12b]
    ├── population/                    # Civilian population & COIN [Phase 12e]
    │   ├── __init__.py
    │   ├── events.py                 # Population events (displacement, collateral, disposition, HUMINT tip)
    │   ├── civilians.py              # Civilian entity manager: regions, disposition, displacement tracking
    │   ├── displacement.py           # Refugee displacement: combat-driven movement, transport penalty
    │   ├── collateral.py             # Collateral damage tracking, escalation threshold
    │   ├── humint.py                 # Civilian HUMINT: Poisson tip generation, disposition-dependent flow
    │   └── influence.py              # Population disposition dynamics: Markov chain transitions
    ├── validation/                    # Engagement + campaign validation (Phase 7, 10)
    │   ├── __init__.py
    │   ├── historical_data.py         # Historical engagement data models + YAML loader
    │   ├── metrics.py                 # Engagement-level metric extraction from simulation results
    │   ├── scenario_runner.py         # Lightweight tick-loop orchestrator for validation scenarios
    │   ├── monte_carlo.py             # Monte Carlo harness: engagement + campaign, N iterations, statistics
    │   ├── campaign_data.py           # Campaign-level historical data models, AIExpectation, CampaignDataLoader
    │   ├── campaign_runner.py         # Campaign runner wrapping ScenarioLoader + SimulationEngine
    │   ├── campaign_metrics.py        # Campaign-level metric extraction (units destroyed, exchange ratio, etc.)
    │   ├── ai_validation.py           # AI decision quality analysis from recorder events
    │   └── performance.py             # cProfile + tracemalloc campaign performance profiling
    ├── tools/                         # Developer tooling — MCP server, analysis, visualization [Phase 14]
    │   ├── __init__.py
    │   ├── serializers.py             # JSON serialization for numpy, datetime, enum, Position
    │   ├── result_store.py            # In-memory LRU cache for run results
    │   ├── mcp_server.py              # FastMCP server with 7 tools (run, query, MC, compare, list, modify)
    │   ├── mcp_resources.py           # MCP resource providers (scenarios, units, results)
    │   ├── _run_helpers.py            # Shared batch scenario runner for analysis tools
    │   ├── narrative.py               # Battle narrative generation from events (registry-based formatters)
    │   ├── tempo_analysis.py          # Operational tempo FFT + OODA cycle extraction
    │   ├── comparison.py              # A/B statistical comparison (Mann-Whitney U)
    │   ├── sensitivity.py             # Parameter sweep analysis
    │   ├── charts.py                  # 6 reusable chart functions (force, engagement, supply, morale, MC)
    │   └── replay.py                  # Animated battle replay (FuncAnimation)
    ├── ew/                            # Electronic Warfare [Phase 16]
    │   ├── __init__.py
    │   ├── events.py                  # EW events (7 types: jamming, spoofing, intercept, decoy, ECCM, emitter, spectrum)
    │   ├── spectrum.py                # EM spectrum manager: frequency allocation, conflict detection, bandwidth overlap
    │   ├── emitters.py                # Emitter registry: active emitters with type/freq/side queries
    │   ├── jamming.py                 # Jamming models: J/S ratio, burn-through range, radar SNR penalty, comms jam factor
    │   ├── spoofing.py                # GPS spoofing: zones, position offset, INS cross-check detection, PGM offset
    │   ├── decoys_ew.py               # Electronic decoys: chaff/flare/towed decoy/DRFM deployment, missile diversion
    │   ├── eccm.py                    # ECCM: frequency hopping, spread spectrum, sidelobe blanking, adaptive nulling
    │   └── sigint.py                  # SIGINT: intercept probability, AOA/TDOA geolocation, traffic analysis
    ├── space/                         # Space & Satellite Domain [Phase 17]
    │   ├── __init__.py
    │   ├── events.py                  # Space events (SatelliteOverpass, GPSDegraded, SATCOMWindow, ASATEngagement, ConstellationDegraded)
    │   ├── orbits.py                  # Simplified Keplerian orbital mechanics: period, ground track, J2 precession
    │   ├── constellations.py          # Constellation manager: satellite groups, coverage windows, health tracking
    │   ├── gps.py                     # GPS accuracy model: DOP from visible satellites, INS drift, CEP scaling
    │   ├── isr.py                     # Space-based ISR: imaging satellites, resolution thresholds, cloud blocking
    │   ├── early_warning.py           # Missile early warning: GEO/HEO IR detection, BMD Pk bonus
    │   ├── satcom.py                  # SATCOM availability: coverage windows, bandwidth capacity, reliability
    │   └── asat.py                    # Anti-satellite warfare: kinetic KKV, laser dazzle/destruct, Poisson debris cascade
    ├── cbrn/                          # CBRN Effects [Phase 18]
    │   ├── __init__.py
    │   ├── events.py                  # CBRN events (contamination, exposure, decontamination, nuclear, MOPP, casualty)
    │   ├── agents.py                  # CBRN agent definitions: nerve/blister/choking/blood/biological/radiological, LCt50/LD50
    │   ├── dispersal.py               # Pasquill-Gifford atmospheric dispersal: Gaussian puff/plume, wind advection, stability classes
    │   ├── contamination.py           # Contamination grid overlay: concentration tracking, decay, evaporation, washout, absorption
    │   ├── protection.py              # MOPP levels 0-4: movement/detection/fatigue degradation, equipment effectiveness
    │   ├── casualties.py              # Probit dose-response model: dosage accumulation, incapacitation, lethality
    │   ├── decontamination.py         # 3-tier decon: hasty (60%), deliberate (95%), thorough (99%), equipment requirements
    │   ├── nuclear.py                 # Nuclear effects: Hopkinson-Cranz blast, thermal fluence, radiation, EMP, fallout, craters
    │   └── engine.py                  # CBRNEngine orchestrator: per-tick dispersal, contamination, exposure, MOPP management
    └── simulation/                   # Top-level simulation orchestration
        ├── __init__.py
        ├── engine.py                 # Master simulation loop (hybrid tick + event)
        ├── campaign.py               # Campaign-level management, strategic AI, reinforcement pipeline
        ├── battle.py                 # Tactical battle resolution manager
        ├── scenario.py               # Scenario loading, setup, initialization
        ├── victory.py                # Victory conditions, war termination criteria, objective evaluation
        ├── recorder.py               # Event/state recording for replay & analysis
        ├── metrics.py                # Simulation output metrics, statistical aggregation, analysis hooks
        └── aggregation.py           # Force aggregation/disaggregation engine for campaign-scale [Phase 13a]
```

---

## Module Responsibilities & Boundaries

### core/
**Owns**: Infrastructure that every other module depends on. No domain logic.
- RNG manager is the single source of truth for all randomness
- Clock is the single source of truth for simulation time
  - **Calendar-aware**: the clock tracks real calendar date and time, not just an abstract tick counter. Scenario start defines a specific date/time (e.g., "1991-02-24T04:00:00Z"). Every tick advances real calendar time. This is critical because seasons, astronomical positions, tidal states, weather patterns, and daylight hours are ALL date-dependent.
  - **UTC internally**: all simulation time in UTC. Time zone conversions for display only (via coordinates module — longitude determines local solar time).
  - **Julian date computation**: exposes Julian date for astronomical calculations (environment/astronomy.py consumes this directly).
  - **Calendar-driven triggers**: exposes queries like "what month is it?" that environment modules use for seasonal transitions, storm season windows, monsoon timing, etc.
- Config provides the pattern for all YAML loading
- Checkpoint handles all serialization (modules register their state)
- **Era framework** (`era.py`): Era enum (MODERN/WW2/WW1/NAPOLEONIC/ANCIENT_MEDIEVAL), EraConfig pydantic model (disabled modules, available sensor types, physics overrides, tick resolution overrides), pre-defined era configs, `get_era_config()` factory [Phase 20]

**Depends on**: Nothing (leaf dependency)

### coordinates/
**Owns**: All coordinate math. The only module that knows about geodetic ↔ projected transforms.
- Everything else works in meters (ENU/UTM)
- Geodetic only enters/exits through this module
- **Magnetic declination** (`magnetic.py`): implements the World Magnetic Model (WMM) or IGRF. Given a position and date, returns magnetic declination (the angle between true north and magnetic north). This varies by location AND changes over time (secular variation). Critical for: compass navigation accuracy (land navigation, naval bearing), compass-based sensor alignment, magnetic influence mine triggers. Exposes: `get_declination(lat, lon, date) → degrees`, `true_to_magnetic(bearing, declination)`, `magnetic_to_true(bearing, declination)`.
- **Geoid model**: MSL (mean sea level) vs ellipsoidal height distinction. A 30m elevation from a DEM is relative to the geoid; GPS gives ellipsoidal height. The difference (geoid undulation) varies by ~±100m globally. Matters for: precise altitude computations, artillery elevation corrections, aircraft altimeter calibration. Typically use EGM2008 or similar.
- **Latitude exposure**: provides latitude for any simulation position — consumed by environment/astronomy (day length, solar elevation depend on latitude), environment/seasons (hemisphere determination), combat/ballistics (Coriolis magnitude depends on latitude).

**Depends on**: core/ (types)

### terrain/
**Owns**: The static physical world. Elevation, land cover, soil, hydrology, LOS, strategic geography, built environment, obstacles, civilian population.
- Provides query interfaces: "what's the elevation at (x,y)?", "can A see B?", "what's the base movement cost from A to B?", "what infrastructure exists here?", "what is the population density/disposition?", "is this river fordable?", "what obstacles are at this location?"
- **Classification** includes soil type (affects digging speed, vehicle trafficability differently than land cover alone), concealment vs cover distinction (a wheat field conceals but doesn't protect; a stone wall protects but may not conceal)
- **Hydrography**: rivers (width, depth, current, fordable points, bridge locations), lakes, flooding potential, seasonal water level variation
- **Urban/suburban/rural** is a spectrum modeled through classification layers (density, building types, construction material — concrete vs wood affects protection) + infrastructure data (road networks, bridges, utilities, tunnels/subway) + population data
- **Infrastructure** (roads, bridges, rail, buildings, utilities, **airfields**): functions as both terrain features (cover, movement bonuses, LOS obstruction) AND as logistical assets (road networks feed into logistics/supply_network, existing depots/warehouses can be leveraged or targeted). Airfields: runway length, surface (paved/unpaved/grass), condition, parking/dispersal areas, fuel/ammo storage, maintenance facilities, ATC — determines what aircraft types can operate, sortie rate, and vulnerability to attack. Airfield damage degrades or prevents air operations until repaired.
- **Obstacles**: both natural (ravines, cliffs, dense forest) and man-made (minefields, wire, barriers, ditches, fortifications). Obstacle state can change (emplaced by engineers, breached/cleared by engineers)
- **Civilian population**: density and disposition (friendly, neutral, hostile) affect operations — friendly populations provide intel and support (HUMINT), hostile populations create insurgency risk, all populations constrain ROE and create moral/ethical considerations. Disposition can shift due to events (bombardment, aid, occupation behavior)
- **Bathymetry**: ocean/sea floor depth and bottom composition. Depth affects submarine operations (operating depth, crush depth), mine placement viability, and sonar propagation (bottom bounce). Bottom type (sand, mud, rock) affects mine warfare and anchoring. **Navigation hazards**: reefs, shoals, wrecks, and shallow water areas constrain ship movement — draft-dependent (a destroyer draws 6m, a carrier draws 12m, a supertanker draws 20m+). Charted vs uncharted waters affect navigation risk.
- **Maritime geography**: coastline, ports/harbors (capacity, draft limitations, crane capacity), straits and chokepoints (Hormuz, Malacca, GIUK gap), sea lanes, anchorages, territorial waters, exclusive economic zones. These feed into strategic map as maritime nodes and edges.
- **Littoral zone**: the critical land-sea interface. Beach gradient and composition (affects amphibious landing viability), tidal flats, coastal defenses, port approach channels.
- **Altitude zones**: tree line, snow line (seasonal — driven by environment/seasons), alpine meadow, permanent ice. These are derived from elevation + latitude + season. Above tree line: no forest concealment, high winds, reduced oxygen. These boundaries shift seasonally.
- **Microclimate terrain features**: valleys that channel wind and collect cold air (radiation fog traps), passes that funnel wind (increased wind speed at gaps/saddles), south-facing slopes (northern hemisphere) that receive more solar heating than north-facing (affects snow melt, vegetation, thermal signature). These feed into environment/ for localized condition modification.
- **Vegetation combustibility**: land cover classification includes fuel load and moisture state (from environment/seasons). Dry grassland, dry forest, and urban areas with wooden construction are fire-susceptible. Fires spread as a function of wind, slope (fire moves uphill faster), and fuel continuity — modeled as a cellular automaton or similar spatial process. Fire events destroy concealment, create obscurants, deny terrain, and damage infrastructure.
- Does NOT own unit positions (that's entities/)
- Natural terrain (elevation, soil, hydrology, bathymetry) is read-only. Infrastructure and obstacles CAN be modified by events (bridge destruction, minefield emplacement/clearing, road cratering, fortification construction, port damage). Population disposition shifts in response to events. Vegetation can be destroyed by fire (combat event or natural), which is a semi-permanent terrain modification (regrowth is slow, outside simulation timescale for most scenarios).

**Depends on**: core/, coordinates/

### environment/
**Owns**: Dynamic environmental conditions. Weather, day/night, seasons, obscurants, astronomical phenomena, electromagnetic propagation, and their effects on all other systems. Every environmental condition is grounded in physical models driven by real date, time, and geographic position — nothing is hand-waved or hardcoded by season name.

#### Astronomical Foundation (astronomy.py) — THE ROOT OF TIME-DEPENDENT PHENOMENA
The astronomical model drives nearly everything else in this module. It computes from first principles using orbital mechanics (Jean Meeus algorithms or VSOP87/ELP2000):
- **Solar position**: azimuth and elevation for any date/time/latitude/longitude. This drives: day/night, twilight, solar heating, glare, shadow direction, thermal crossover timing. Solar elevation at a specific azimuth determines whether the sun blinds a gunner, sensor, or pilot from a particular direction.
- **Sunrise, sunset, and twilight**: computed from solar geometry, not looked up from tables. Three twilight stages matter: civil twilight (horizon visible, outdoor activities possible without artificial light), nautical twilight (horizon indistinct, stars visible for navigation), astronomical twilight (full darkness). Each has military significance — nautical twilight is historically the transition point for night operations.
- **Day length**: varies by latitude and date. At 60°N in June, ~19 hours of daylight; in December, ~6 hours. At the equator, ~12 hours year-round. This directly drives operational planning — how many hours of daylight for offensive operations, how long the night for infiltration.
- **Lunar position and phase**: computed from orbital mechanics. Moon phase (new → waxing crescent → first quarter → waxing gibbous → full → waning gibbous → third quarter → waning crescent → new) determines: nighttime illumination level (0-100% illumination fraction), tidal forcing amplitude, and visibility for night operations without artificial illumination.
- **Moonrise/moonset**: the moon is not always up at night. A waning crescent rises in the pre-dawn hours — meaning the first half of the night is dark even with a partial moon. Moonrise/set times are computed and feed directly into the illumination model.
- **Tidal astronomical forcing**: the gravitational pull of sun and moon drives ocean tides. **Spring tides** occur at new and full moon (sun and moon aligned — maximum tidal range). **Neap tides** occur at first and third quarter (sun and moon perpendicular — minimum range). This astronomical forcing is the INPUT to the tidal model in `sea_state.py`, which combines it with local geography to produce actual tide heights and timing. Historically critical: D-Day required specific tidal conditions at Normandy; the Inchon landing exploited extreme tidal range.
- **Solar/lunar eclipses**: rare events computed from orbital geometry. Solar eclipse briefly darkens the battlefield; lunar eclipse eliminates moonlight. Unlikely to occur in most scenarios but the model should handle them correctly when they do.
- **Celestial navigation availability**: for forces without GPS or when GPS is jammed — star visibility (function of cloud cover, light pollution, twilight state) determines whether celestial navigation fixes are possible. More relevant for naval and special operations.

#### Weather (weather.py)
- Weather evolves over simulation time via stochastic transitions: precipitation type and intensity, wind speed/direction/gusts, temperature, cloud cover (layer heights and types), humidity, barometric pressure, dew point
- **Prevailing weather patterns**: driven by geographic position, season, and climate zone. The weather transition model is conditioned on geography — a maritime tropical location has fundamentally different weather statistics than a continental subarctic one. Monsoon regions have distinct wet/dry season transitions tied to calendar date. Storm seasons (Atlantic hurricane: Jun-Nov, Western Pacific typhoon: year-round peak Jul-Nov) are geographic and seasonal.
- **Altitude effects**: temperature lapse rate (~6.5°C/km standard atmosphere), pressure decreases with altitude (~12% per 1000m). Atmospheric density decreases with altitude. These affect: ballistic trajectories (less drag at altitude), aircraft/helicopter performance ceiling, personnel performance (hypoxia above ~2500m degrades cognitive and physical capability without acclimatization), engine performance (normally-aspirated engines lose power; turbines are affected differently), explosive blast radius (larger at altitude due to lower ambient pressure).
- **Diurnal temperature cycle**: desert/continental climates can swing 30°C+ between day and night; maritime climates may swing only 5°C. This drives: thermal crossover timing, fog formation (radiation fog in valleys at dawn), ground frost, equipment thermal stress.
- **Atmospheric refraction**: temperature and humidity gradients near the surface bend light and radar. Standard refraction extends visual and radar horizon by ~8% beyond geometric. **Anomalous propagation** (ducting): temperature inversions create waveguide-like ducts that can extend radar detection to extreme ranges or create radar holes. Super-refraction in hot climates over cool water. Sub-refraction in cold air over warm water. This is a critical and often overlooked variable in detection modeling.
- **Radar ducting**: surface ducts, elevated ducts, evaporation ducts (common over warm seas). Duct height and strength from meteorological conditions. Affects radar, communications, and ESM detection ranges — can dramatically extend OR reduce effective ranges depending on geometry.
- **Atmospheric density**: computed from temperature, pressure, and humidity. Directly affects: projectile drag (ballistic trajectories), aircraft performance (lift, engine thrust), helicopter maximum altitude, sound propagation speed, explosive effects.

#### Seasons (seasons.py)
- **Hemisphere-aware**: the season is derived from the calendar date AND the hemisphere. The simulation computes latitude from position (via coordinates/) and determines: Northern Hemisphere → Dec/Jan/Feb = winter, Jun/Jul/Aug = summer. Southern Hemisphere → reversed. This is computed, never hardcoded.
- **Climate zone model**: latitude + altitude + continental position + proximity to water bodies → climate classification (tropical, subtropical, temperate, continental, subarctic, arctic, arid, semi-arid, mediterranean, monsoon). The climate zone conditions the weather transition model — it defines the statistical envelope that weather varies within.
- **Ground state transitions**: frozen ground (trafficable by heavy vehicles, easy to dig in some conditions), thaw/mud season (**rasputitsa** — the seasonal road destruction that halted armies in Russia), dry/hard ground, waterlogged/saturated. Transitions driven by temperature history (accumulated freezing/thawing degree-days), precipitation, and soil type (from terrain/classification). Mud depth and vehicle trafficability are continuous variables, not binary.
- **Vegetation cycle**: deciduous foliage provides concealment in summer, not winter. Grass height affects infantry concealment. Crop cycles (planted fields vs harvested stubble) change terrain properties. Vegetation moisture content affects combustibility — dry season fire risk.
- **Snow cover**: accumulation and melt driven by temperature and precipitation. Snow depth affects: infantry movement speed, vehicle trafficability (tracked vs wheeled differ), visual signature (vehicles contrast against snow unless whitewashed), thermal signature (cold background makes warm objects stand out), sound propagation (snow absorbs sound — reduces acoustic detection range).
- **Sea ice**: formation driven by sustained below-freezing sea surface temperature. Ice thickness determines navigability (thin ice: icebreaker required, thick ice: impassable except by specially designed vessels, very thick ice: may support vehicles). Affects: port access, submarine operations (limited surfacing, under-ice navigation), naval routes (Northern Sea Route seasonal availability).
- **Daylight hours**: driven by astronomy.py solar calculations. Feeds into operational planning — available daylight for visual operations, duration of night for night operations.
- **Wildfire risk**: dry vegetation + high temperature + low humidity + wind → fire danger rating. Fires (from bombardment, incendiary weapons, or natural causes) can spread through vegetation — rate and direction driven by wind, terrain slope, fuel moisture. Fires create obscurants (smoke), destroy concealment, and deny terrain.

#### Time of Day (time_of_day.py)
- Fed by astronomy.py for exact solar and lunar positions
- **Illumination model**: actual ambient light level is a continuous function of: sun elevation (daylight brightness varies from horizon to zenith), cloud cover (diffuses and reduces solar illumination), moon elevation + phase + cloud cover (nighttime illumination spans 3 orders of magnitude from full moon clear sky to new moon overcast), artificial illumination (flares, searchlights, urban light, fires), terrain shadowing (sun/moon behind a ridge)
- **Thermal environment**: solar heating drives surface temperature throughout the day. Objects (vehicles, buildings, terrain) absorb solar radiation and radiate infrared. **Thermal crossover** occurs twice daily — at dawn and dusk when object temperatures equal background temperature, making thermal sensors temporarily ineffective. The exact timing depends on object thermal mass, surface properties, and local weather. Desert environments have earlier/sharper crossover than humid environments.
- **NVG effectiveness model**: image intensification devices amplify available ambient light. Their effectiveness is a function of: ambient light level (from illumination model above), atmospheric clarity (fog/rain scatter light, reducing contrast), terrain (open terrain reflects more moonlight than forest canopy). In very low light (new moon, heavy overcast, under forest canopy), NVGs may provide minimal advantage. Under a full moon in open terrain, NVGs provide near-daylight capability. This feeds detection/sensors.py thermal and visual models.
- **Shadow modeling**: sun azimuth and elevation + terrain + structures → shadow geometry. Shadows affect: visual concealment (hide in shadows), thermal signature (shadowed surfaces cool faster), solar panel/heating effects. Shadow length and direction change throughout the day.
- **UV/IR background**: time-of-day and weather conditions affect the UV and IR background against which sensors must discriminate targets. Dawn/dusk sky backgrounds differ from midday. Overcast vs clear sky creates different IR backgrounds.

#### Obscurants (obscurants.py)
- Smoke (deployed or from fires/combat), dust (from vehicle movement, artillery impacts, wind), fog (radiation fog, advection fog, sea fog — each with distinct formation conditions) — each has distinct opacity, spectral properties (blocks visual but thermal may penetrate, or vice versa), duration, and drift characteristics
- Wind model drives smoke/dust drift direction and dispersion rate
- **Fire-generated obscurants**: fires from combat (burning vehicles, structures, vegetation) produce smoke that persists and drifts. Large fires (urban, forest) can produce smoke screens that affect operations across wide areas. Smoke composition affects spectral blocking properties.
- **Multi-spectral effects**: smoke grenades block visual but many are transparent to thermal. Purpose-designed multi-spectral smoke blocks both. Dust is generally opaque across spectra. Fog attenuates both visual and thermal (water droplets absorb IR). These distinctions matter for sensor selection.

#### Sea State (sea_state.py)
- Wave height, period, and swell driven by wind model (duration + fetch + wind speed → sea state via Beaufort/Douglas scale or Pierson-Moskowitz spectrum)
- **Tides**: the astronomical forcing from `astronomy.py` (lunar/solar gravitational) combines with **local tidal characteristics** defined per-location in scenario data (tidal harmonic constituents — amplitude and phase for M2, S2, K1, O1, etc. — or simplified as tidal range and phase offset). This produces realistic tide height curves that vary by location. The English Channel has 10m+ tidal range; the Mediterranean has negligible tides. Tidal timing shifts ~50 minutes per day due to lunar orbital period.
- **Tidal currents**: in straits, channels, and estuaries, tidal flow creates significant currents (up to several knots in locations like the Strait of Messina). Current direction reverses with tide. These affect: small craft navigation, mine drift, amphibious approach timing, submarine operations, swimmer delivery.
- **Storm surge**: weather-driven (barometric pressure drop + onshore wind) superimposed on astronomical tide. Can raise water levels meters above predicted — affects coastal flooding, port operations, beach exposure for amphibious ops.
- **Sea surface temperature**: seasonal variation, coastal upwelling patterns. Affects: evaporation duct formation (radar propagation), fog generation, underwater acoustic environment (surface layer temperature feeds SVP).
- **Ocean currents**: permanent/semi-permanent currents (Gulf Stream, Kuroshio) as geographic data + seasonal variation. Affect ship fuel consumption, drift of disabled vessels, mine drift, swimmer delivery, pollution/contamination drift.

#### Underwater Acoustics (underwater_acoustics.py)
- Sound velocity profile varies with temperature (from sea_state/seasons), salinity, and depth. This is the FOUNDATION of submarine warfare.
- Thermoclines create acoustic shadow zones that submarines exploit for concealment
- Convergence zones enable long-range detection at specific ranges (~30nm intervals)
- Bottom bounce paths in shallow water. Surface duct propagation.
- **Ambient noise**: from biologics (whale/shrimp — varies by location and season), shipping density, weather (rain, wave action), ice cracking, seismic. Ambient noise sets the noise floor against which sonar must discriminate targets.
- **Seasonal variation**: in many ocean basins, the thermocline structure changes seasonally — summer thermocline is shallow and strong (good for submarines hiding, bad for surface ASW), winter mixing deepens the layer (harder for submarines to hide). The acoustic environment at the same location can vary dramatically between January and July.
- Stochastic modeling is critical: ray tracing through noisy SVP profiles, range-dependent propagation loss with stochastic scattering

#### Electromagnetic Environment (electromagnetic.py)
- **Radio frequency propagation**: different frequency bands propagate differently, and propagation varies with atmospheric conditions.
  - **HF (3-30 MHz)**: ground wave (limited range, terrain-dependent) and **sky wave** (reflected by ionosphere — range varies enormously with ionospheric conditions, which depend on solar activity, time of day, season, and latitude). At night, the ionosphere lowers and HF propagation can extend to thousands of km. Solar flares can disrupt HF entirely. This is THE long-range communications band in denied/degraded environments.
  - **VHF/UHF (30 MHz - 3 GHz)**: primarily line-of-sight. Range limited by terrain, antenna height, and atmospheric refraction. The workhorse of tactical radio.
  - **SHF/EHF (3-30+ GHz)**: highly directional, high bandwidth, more affected by precipitation (rain fade). Used for satellite communications, point-to-point links, some radars.
- **Ionospheric conditions**: driven by solar activity (11-year solar cycle, with scenario date determining approximate cycle position), time of day (D-layer absorption during daytime, F-layer reflection at night), season, latitude (auroral zone disruptions). Affects HF radio range and reliability, HF direction finding (SIGINT), over-the-horizon radar. Scenario can specify solar activity level or derive it from date.
- **GPS accuracy**: standard accuracy ~5-10m, degrades with ionospheric scintillation (aurora, solar storms), intentional jamming (modeled in detection/), atmospheric conditions. Differential GPS corrections not available in all theaters. GPS-denied operations force fallback to INS, celestial nav, or terrain association.
- **Atmospheric attenuation by frequency**: rain, fog, and humidity absorb/scatter radio energy. 60 GHz oxygen absorption line. Water vapor absorption at 22 GHz. These affect specific radar and communication bands differently. The electromagnetic environment is as variable as the weather — because it's largely DRIVEN by weather.
- Feeds into: c2/communications (radio reliability), detection/sensors (radar performance), detection/sonar (active sonar relates to acoustic not EM, but ESM/radar detection does), combat/air_defense (radar performance), c2/naval_c2 (data link performance).

#### Conditions (conditions.py)
- Provides composite condition modifiers that other modules query: visibility multiplier (from illumination + obscurants + weather), trafficability modifier (from ground state + weather + season), detection range modifier per sensor type (from atmospheric conditions + illumination + clutter), thermal contrast (from thermal model), wind vector (for ballistics + smoke drift), sea state grade, acoustic propagation conditions, RF propagation conditions, NVG effectiveness, GPS accuracy.
- Covering land, air, AND maritime domains.
- Separates static terrain (doesn't change) from dynamic conditions (change each tick, driven by real astronomical/meteorological physics).

**Depends on**: core/ (clock for date/time, rng for weather/sea state transitions), coordinates/ (latitude/longitude for astronomical calculations, magnetic declination)

### entities/
**Owns**: What things ARE. Unit types, stats, organization, force structure, personnel, equipment state, combat power assessment.
- Defines the class hierarchy and common interfaces
- Loads unit definitions from YAML
- **Personnel modeling**: individual crew/soldiers within a unit have roles, skill levels, experience, injury state. Losing a gunner is different from losing a driver. Experience grows through combat exposure (learning curve).
- **Equipment state**: vehicles/weapons degrade through use (not just combat damage). Maintenance cycles, mechanical breakdown probability (stochastic), barrel wear, track life. Equipment has operational readiness as a continuous variable.
- **Naval unit modeling**: ships are complex multi-system platforms. Hull integrity, propulsion plant status, individual weapon mount/sensor operability, damage control capacity, magazine state, fuel bunker state, flight deck status (carriers). A ship can be mission-killed (key systems destroyed) without being sunk. Submarines add: hull integrity vs depth, battery state (diesel-electric), reactor status (nuclear), noise signature as a function of speed and equipment state.
- **Crew complement**: naval vessels have large crews with specialized roles (bridge, engineering, weapons, damage control, aviation). Crew casualties degrade specific capabilities based on which department is affected.
- **Environmental equipment**: units carry or can be equipped with environment-interacting gear — NVGs (effectiveness from environment/conditions), thermal sights (affected by thermal crossover timing), NBC/CBRN protective gear (protection vs performance degradation — MOPP levels reduce combat effectiveness), cold weather gear (prevents cold casualties but adds weight), desert equipment (water purification, sun protection). Equipment loadout affects unit signatures and capabilities in environmental context.
- **Power and energy**: modern military equipment depends on electrical power — radios, GPS, NVGs, thermal sights, computing, EW systems. Battery state, generator fuel consumption, and solar charging (from environment/astronomy solar state) constrain electronic capability. A unit whose batteries are dead loses communications, navigation, and advanced sensor capability — reverts to pre-electronic baseline.
- **Environmental hardening**: equipment rated for temperature ranges, humidity, sand/dust, salt spray. Operations outside rated conditions accelerate degradation and increase breakdown probability. Arctic operations without winterized equipment destroy equipment rapidly. Desert sand degrades air filters, optics, and moving parts.
- **UAVs/drones**: a defining feature of modern warfare, modeled as aerial unit subtypes (fixed-wing or rotary) with distinct characteristics. Key differences from manned aircraft: extended loiter time (hours vs minutes on station), smaller signatures, lower cost (expendable in some cases), requires **data link** to operator/ground control station (data link has range, bandwidth, latency, and jamming vulnerability — feeds into c2/communications and environment/electromagnetic). Categories: reconnaissance/surveillance (long loiter, sensors, persistent ISR), armed/strike (Hellfire-class weapons, precision engagement), loitering munitions/kamikaze (one-way, expendable, blur line between drone and guided weapon), cargo/resupply (emerging capability). UAV data link dependency means they are uniquely vulnerable to communications disruption — jamming or link loss may result in return-to-base, loiter, or loss of aircraft depending on autonomy mode. YAML-parameterized like all other units.

#### Organization Subsystem (entities/organization/)
The organizational model must be **nation-agnostic and era-agnostic** — it provides a configurable framework, not a hardcoded structure.
- **Configurable echelon hierarchy**: the organizational tree is defined in YAML data, not code. A US Army structure (fire team → squad → platoon → company → battalion → brigade → division → corps → army) and a Russian structure (otdelenie → vzvod → rota → battalion → polk → brigada/division → army → front) are both valid configurations of the same tree framework. So is a Napoleonic corps system or a Roman legion.
- **Echelon properties**: each echelon level has configurable properties — span of control (how many subordinates), staff functions available (a battalion has S1-S4; a division has G1-G6 plus specialized staff), planning capacity (higher echelons can plan more complex operations), organic support (what's embedded vs attached).
- **Task organization (CRITICAL)**: the organizational tree is DYNAMIC during simulation. Units can be attached/detached temporarily. A tank company can be attached to an infantry battalion, creating a combined-arms task force. Cross-attachment is fundamental to modern warfare. The system tracks: parent unit (permanent), current command relationship, and type of command authority (OPCON, TACON, ADCON, support — each grants different levels of control).
- **Command relationships**: OPCON (operational control — full authority to direct forces), TACON (tactical control — limited to specific mission), ADCON (administrative control — logistics and personnel), support (direct, general, mutual, close). These determine what orders a commander can give to attached units.
- **Staff functions**: S1/G1/J1 (Personnel) through S6/G6/J6 (Communications) are not just labels — they represent functional capabilities. A unit whose S2 (Intelligence) section is destroyed loses intel processing capacity. A unit whose S4 (Logistics) is degraded has slower supply distribution. Staff function effectiveness is a continuous variable.
- **TO&E vs actual**: Table of Organization & Equipment defines what a unit SHOULD have. Actual state reflects losses, attachments, and degradation. The gap between TO&E and actual drives combat effectiveness calculations.
- **Special organizations**: SOF units (different C2 paradigm — typically report to theater-level, operate independently or in small teams), irregular/insurgent forces (cell-based or network structure, no fixed hierarchy, distributed decision-making), coalition/joint organizations (multi-service or multi-national with interoperability constraints).
- **Combat power assessment**: weighted computation of a unit's effective combat capability considering: personnel strength, equipment readiness, training/experience, morale, supply state, leadership quality, fatigue, and current task organization. This is what AI commanders use to make force allocation decisions.

- Does NOT own what units DO (movement, combat, etc. are separate modules that act on entities)

**Depends on**: core/

### movement/
**Owns**: How things move. Pathfinding, speed calculation, deviation, fatigue, obstacle interaction, mounting/dismounting.
- Queries terrain for movement costs (including soil, slope, obstacles, infrastructure), environment for condition modifiers (mud, snow, visibility, ground state, ice)
- Modifies entity positions and fatigue state
- **Load effects**: infantry carrying capacity affects speed; vehicle load affects fuel consumption and mobility
- **Obstacle interaction**: minefields (risk of loss during transit), barriers (must breach or bypass), rivers (ford, swim, bridge, or ferry — each with different time, risk, and equipment requirements)
- **Mount/dismount**: mechanized infantry transitions between mounted (fast, protected, limited weapons) and dismounted (slow, flexible, vulnerable to vehicles). Transition takes time and creates vulnerability window.
- **Sleep deprivation**: extended operations without rest degrade movement efficiency, increase stochastic deviation, compound with fatigue
- **Altitude effects**: personnel performance degrades above ~2500m without acclimatization — movement speed, stamina, cognitive function all decrease. Vehicle engines (especially normally-aspirated) lose power at altitude. Helicopter ceiling is altitude and temperature dependent (density altitude computation from environment/weather). Acclimatization is a process over days — sudden deployment from sea level to high altitude incurs maximum penalty.
- **Temperature extremes**: extreme cold increases fuel consumption (engines need warming, heating), causes frostbite casualties (from environment/weather temperature + wind chill + exposure time — queries entity cold weather equipment), makes metal brittle (equipment breakdowns). Extreme heat causes heat casualties (from temperature + humidity + exertion level + hydration state), overheats engines, softens asphalt (road damage under tracked vehicles in desert heat).
- **Night movement**: movement speed and navigation accuracy degrade in darkness. Degradation magnitude is a function of actual illumination level (from environment/time_of_day), NVG availability (from entities/equipment), terrain familiarity, and unit training level. Movement through complex terrain (forest, urban, mountains) is far more degraded by darkness than movement on roads. NVGs restore most capability in open terrain under moonlight but provide diminished advantage under heavy canopy or total overcast.
- **Seasonal ground conditions**: spring thaw (**rasputitsa**) turns unpaved roads and cross-country terrain to impassable mud for wheeled vehicles, severely degrades tracked vehicle speed. Frozen ground in winter makes cross-country movement faster than summer in some terrain. Snow depth above ~30cm significantly slows dismounted movement; above ~1m requires snowshoes/skis. These come from environment/seasons ground state computations.
- **Tidal effects on movement**: amphibious beach approach timing is constrained by tidal state (from environment/sea_state). Rising tide covers beach obstacles, limits beach width. Falling tide exposes obstacles but extends the beach approach distance. Tidal currents in approach channels affect landing craft navigation. Tidal windows may dictate H-hour for amphibious operations.
- **Naval movement**: ship speed constrained by hull design, propulsion plant, sea state, and fuel economy. Fuel consumption scales roughly with cube of speed (critical for campaign-level endurance planning). Formation steaming, turning circles, draft constraints in shallow water. Station-keeping in task force formations.
- **Submarine movement**: depth management (operating depth vs crush depth), speed-noise tradeoff (faster = louder = more detectable), snorkel operations (diesel-electric must snort to recharge — vulnerable), periscope depth operations, under-ice navigation. Submarine movement is fundamentally a stealth problem — every movement decision trades mobility against detectability.
- **Amphibious movement**: ship-to-shore movement phases. Loading/unloading at ports, transit to amphibious objective area, ship-to-shore via landing craft/helo/LCAC, beach landing, over-the-horizon assault. Each phase has distinct speed, vulnerability, and environmental constraints (sea state, tide, beach gradient, shore defenses).
- **Aerial movement and weather**: ALL air operations are heavily weather-constrained. Cloud ceiling determines minimum safe altitude (below ceiling = terrain collision risk, above ceiling = loss of ground reference for CAS). Visibility affects low-level flight and visual target acquisition. Icing (from temperature + moisture at altitude, from environment/weather) is dangerous to aircraft and can be mission-prohibitive. Crosswind limits constrain runway operations. Density altitude (from temperature + pressure + humidity + field elevation) determines maximum takeoff weight — hot and high airfields dramatically reduce cargo/ordnance capacity. Thunderstorms, heavy precipitation, and severe turbulence prohibit flight through affected areas. Helicopter operations are additionally constrained by: wind speed (hover/landing limits), brownout/whiteout from rotor wash in dust/snow, and NVG conditions for night flight. The weather window for air operations is a critical planning factor — an armored advance may be timed to coincide with good flying weather that enables CAS coverage.
- **Airborne and air assault operations**: parachute drops and helicopter insertions are distinct movement modalities with unique constraints. Parachute operations: wind speed/direction (from environment/weather) determines jump accuracy — drop scatter modeled stochastically around intended drop zone. Drop altitude affects scatter radius and jump time. Assembly after landing takes time and is a vulnerability window — units are dispersed and combat-ineffective until assembled. DZ suitability depends on terrain (open, flat, free of obstacles). Heavy equipment drops (vehicles, artillery) have higher failure rates. Helicopter insertion (air assault): LZ selection considers enemy threat, terrain, helicopter approach/departure routes. Landing zone capacity limits simultaneous helicopter landings. Brownout/whiteout from rotor wash (from environment/conditions — dust/snow). Fast-rope and rappel operations for LZs too constrained for landing. Both modes represent air-to-ground transition — comparable in complexity to amphibious ship-to-shore movement.
- **Hydrological movement effects**: river depth and current are not static — they vary with precipitation history (from environment/weather) and season (from environment/seasons). Heavy sustained rain raises river levels, makes fords impassable, and can flood low-lying terrain. Spring snowmelt in mountainous terrain causes seasonal flooding downstream. Dry season reduces river obstacles. The movement model queries terrain/hydrography for current water levels (which are modified by environment/ precipitation accumulation), not just static river data.

**Depends on**: core/, terrain/, environment/, entities/

### detection/
**Owns**: How things perceive. Sensor models, signatures, detection, classification, identification, state estimation, intelligence fusion, deception, fog of war.
- Queries terrain for LOS and concealment, environment for visibility/weather/thermal modifiers
- Reads entity signature profiles (visual, thermal, radar cross-section, acoustic, EM emission) and sensor stats
- **Detection → Classification → Identification pipeline**: detecting something exists is different from knowing what it is. A radar blip (detected) → probably a vehicle (classified) → likely a T-72 (identified). Each step has its own probability model. Misclassification feeds fratricide risk.
- **Multi-source intelligence fusion**: combines sensor data, SIGINT (radio intercepts, radar emissions, direction finding), HUMINT (civilian reports, patrols, agent networks), IMINT (recon flights, UAV persistent surveillance, satellite imagery) into a unified belief state. Different INT sources have different reliability, latency, and coverage. **Satellite intelligence**: satellite overflight schedules mean coverage is periodic, not continuous — a LEO imaging satellite passes over a given area for minutes, perhaps twice daily. Coverage gaps are exploitable. Satellite imagery has resolution limits and weather dependence (cloud cover blocks optical/IR). SIGINT satellites provide broader but less precise coverage. Satellite constellation and schedule defined in scenario data; intel_fusion models the temporal availability.
- **Deception**: decoys (visual, thermal, radar), feints (real units acting deceptively), false radio traffic, camouflage effectiveness. Deception degrades enemy's belief state accuracy.
- **Information decay**: intelligence ages and becomes less reliable. Last known position diverges from actual position over time (modeled as growing uncertainty ellipse).
- **Sonar modeling**: fundamentally different from radar/visual detection. Active sonar (reveals your position while searching), passive sonar (listens — stealthy but range/bearing-only). Towed array sonar (long-range passive, but constrains maneuver). Hull-mounted sonar. Sonobuoy fields (dropped by aircraft). Dipping sonar (helicopter ASW). Performance dominated by underwater acoustic environment (thermoclines, convergence zones, ambient noise) — highly stochastic.
- **Underwater detection**: submarine detection is the hardest detection problem in the simulation. Combines sonar, magnetic anomaly detection (MAD — very short range), wake detection (satellite — experimental), periscope detection (radar/visual — only when at periscope depth). Probability of detection varies enormously with acoustic conditions, submarine noise signature, and depth.
- **Maritime surface detection**: ship radar (surface search, air search), ESM (electronic support measures — passive detection of radar/radio emissions), visual lookout, AIS/transponder (commercial/cooperative). Radar horizon limits surface detection range. Sea clutter degrades radar detection in high sea states.
- **Atmospheric refraction and ducting effects**: detection ranges are NOT fixed numbers — they vary with atmospheric conditions from environment/electromagnetic. Radar ducting can extend surface radar detection to 2-3x normal range, or create blind zones where targets are undetectable. Evaporation duct (common in warm seas) particularly affects low-altitude/surface targets. The detection model queries environment/conditions for current propagation conditions and adjusts detection envelopes accordingly. This can create situations where a target is detected at extreme range due to ducting, then LOST as geometry changes — realistic and historically significant.
- **Solar/lunar glare**: optical/visual sensors have degraded performance when looking toward the sun or a bright moon. Engagement from the sun side is a classic aerial tactic (and also matters for ship lookouts and ground observation). The glare zone is computed from solar/lunar azimuth and elevation (from environment/astronomy).
- **NVG/thermal sensor modeling**: image intensifier (NVG) effectiveness varies with ambient light level (from environment/time_of_day illumination model). Under full moon, clear sky: NVGs provide excellent visibility. Under new moon, overcast, under canopy: NVGs provide minimal advantage — may need to fall back to IR illuminators (which are detectable by opponent's NVGs). Thermal (IR) sensors are affected by thermal crossover (twice daily — from environment/time_of_day), weather (rain/fog attenuate IR), and background clutter (hot desert terrain reduces thermal contrast of vehicles).
- **Land acoustic detection**: sound ranging (triangulation of artillery/mortar fire from sound arrival times — historically important, still used), seismic sensors (ground vibration from vehicles/personnel — range depends on soil type from terrain/classification, ambient seismic noise from weather/traffic), acoustic gunshot detection. Performance varies with wind (sound refracts with wind gradients), temperature (sound speed varies ~0.6 m/s per °C), and ambient noise (from environment/conditions).
- **Radar clutter**: surface clutter varies with terrain type (forest, urban, water, desert produce different radar returns) AND environmental conditions (sea clutter increases with sea state, ground clutter varies with moisture/vegetation, rain produces volume clutter). Clutter competes with target returns — detection probability degrades when target signal-to-clutter ratio is low. Moving target indication (MTI) and Doppler processing help discriminate targets from clutter but fail against stationary or slow-moving targets.
- Maintains per-side belief states (separate from ground truth) — including underwater picture

**Depends on**: core/, terrain/, environment/, entities/

### combat/
**Owns**: How things fight. All engagement types — direct fire, indirect fire (tube and rocket artillery), surface-to-surface missiles (TBM, cruise, coastal defense), missile defense, air-to-air, air-to-ground, ground-to-air. Hit probability, ballistic physics, damage, suppression, ammunition management, fratricide.
- Uses detection (specifically identification confidence) to determine who can engage whom and with what certainty of target identity
- Queries environment for condition effects on combat (wind on ballistics, visibility on engagement range, thermal contrast)
- Queries c2/roe for engagement authorization and constraints
- **Ballistic physics**: projectile trajectory modeling including drag (function of atmospheric density from environment/weather — altitude and temperature affect air density, which affects drag coefficient), wind deflection (from environment/weather wind vector), Coriolis effect (at long range — magnitude depends on latitude from coordinates/ and projectile flight time), temperature effects on propellant (muzzle velocity varies ~1 fps per °F of propellant temperature), barrel wear (from entities/equipment degradation). Not just P(hit) tables — actual physics-based modeling where warranted by fidelity requirements.
- **Indirect fire** (`indirect_fire.py`): covers BOTH tube artillery and rocket artillery, which have fundamentally different characteristics.
  - **Tube artillery** (howitzers, guns, mortars): fire missions (adjust fire, fire for effect, time-on-target, coordinated illumination), counterbattery radar (AN/TPQ-36/37 — detects incoming rounds, backtraces to firing position) and response, ammunition selection (HE, smoke, illumination, ICM/DPICM, precision-guided — Excalibur, Copperhead, Krasnopol). Fire mission processing time from request to rounds-on-target. Barrel wear and propellant temperature effects on accuracy.
  - **Rocket artillery** (MLRS, HIMARS, BM-21 Grad, Smerch, etc.): distinct from tube artillery in key ways — fires in volleys/salvos from pod-based launchers (6/12 rockets per pod), large beaten zone for area fires (dispersal pattern modeled stochastically around aim point), rapid reload requires ammunition resupply vehicle, shoot-and-scoot doctrine (must displace quickly after firing to avoid counterbattery). Rocket types: unguided area-fire rockets (classic MLRS — large dispersion, area saturation), precision-guided rockets (GMLRS — GPS/INS, ~1m CEP, single-target precision), extended-range variants (ER-GMLRS). Rocket artillery ammo logistics differ from tube — pod-based, heavier per round, different resupply cycle.
  - **Counterbattery**: radar detection of incoming projectiles → backtrack trajectory to firing position → counterbattery fire mission. Time from detection to response is critical. Counterbattery radar coverage is limited and can be targeted. Shoot-and-scoot timing vs counterbattery response time is a key tactical dynamic.
- **Surface-to-surface missiles** (`missiles.py`): a distinct combat category spanning multiple mission types, all sharing: launch platform, flight profile, guidance system, terminal effects, and vulnerability to missile defense.
  - **Theater ballistic missiles (TBMs)**: short-range (Scud, Tochka — <300km), medium-range (Iskander, DF-15 — 300-1000km), intermediate-range (DF-21, DF-26 — 1000-5000km). Ballistic trajectory (boost-coast-reentry), flight time minutes, limited accuracy (older systems CEP hundreds of meters; modern systems CEP <10m with terminal guidance). Warhead types: conventional HE, submunition, penetrator. Launch detection by satellite IR sensors (boost phase) → trajectory estimation → warning to target area → missile defense engagement.
  - **Land-attack cruise missiles** (Tomahawk, Kalibr, JASSM, Storm Shadow): terrain-following flight profile (low altitude, terrain masking), subsonic or supersonic, GPS/INS/TERCOM/DSMAC guidance, long range (hundreds to thousands of km), high accuracy (CEP <3m). Launch from ships, submarines, aircraft, or ground TELs. Flight time hours at subsonic speeds — pre-planned targets, not responsive to fleeting opportunities. Vulnerable to air defense along flight path (especially terminal phase).
  - **Ground-launched anti-ship missiles** (coastal defense): shore-based anti-ship missile batteries (Bastion/P-800 Oniks, NSM, Harpoon shore battery, HY-2 Silkworm). Area denial of sea approaches. Engagement model similar to ship-launched AShM but with land-based targeting (shore radar, UAV cueing, OTH-T). Survivability from concealment, dispersal, and shoot-and-scoot on mobile TELs.
  - **Kill chain**: all missile engagements follow a targeting cycle — detection/cueing (sensor or intel) → target localization → launch authorization (C2/ROE) → launch → missile flight (guidance updates if applicable) → terminal engagement. Time-sensitive targeting compresses this cycle. For TBMs, the "Scud hunt" problem (finding mobile TELs before they launch) is a classic targeting challenge. For cruise missiles, pre-planned targeting uses intelligence preparation. Kill chain latency is a critical constraint — minutes for responsive fires, hours/days for deliberate strike planning.
  - **Missile logistics**: missiles are expensive, low-density munitions. Limited inventories per launcher. Reload time significant (TBM reload: hours; cruise missile VLS cells: cannot reload at sea). Missile expenditure is a strategic resource management problem, not just tactical.
- **Missile defense** (`missile_defense.py`): defense against rockets, artillery, mortars, cruise missiles, and ballistic missiles — each requiring different intercept approaches.
  - **Ballistic missile defense (BMD)**: layered defense — upper tier (THAAD, SM-3/Aegis BMD — exoatmospheric or high-endoatmospheric intercept), lower tier (Patriot PAC-3, S-400/S-300 — terminal phase intercept). Detection via dedicated BMD radars (AN/TPY-2, SPY-1 in BMD mode) or satellite early warning. Engagement timeline is very compressed (minutes from launch detection to impact). Shoot-assess-shoot doctrine. Pk per interceptor is NOT 100% — layered defense uses multiple engagement opportunities to raise cumulative Pk. Decoys and countermeasures complicate discrimination.
  - **Cruise missile defense**: defense against low-flying, terrain-masking cruise missiles. Detection is the hard problem (low RCS, terrain clutter, short detection range due to radar horizon). Intercepted by fighters (CAP/alert aircraft), SAMs, and point defense (CIWS, SeaRAM, Pantsir). Overlapping sensor coverage critical — a single radar may not detect a cruise missile until very short range.
  - **Counter-rocket, artillery, mortar (C-RAM)**: Iron Dome (rocket/short-range missile intercept), C-RAM/Phalanx (CIWS adapted for land use — last-ditch defense of point targets), future directed-energy weapons. Threat discrimination: C-RAM systems must rapidly determine if incoming rounds will hit a defended area (trajectory prediction) vs land harmlessly — engages only threatening rounds to conserve interceptors. Interceptor inventory is limited and expensive.
  - **Integrated Air and Missile Defense (IAMD)**: modern air defense integrates anti-aircraft and anti-missile missions. An S-400 battery can engage aircraft, cruise missiles, and (to a degree) ballistic missiles. A Patriot battery can engage aircraft and TBMs. Sensor netting shares tracks across the IAMD network. Engagement authority and weapon-target pairing are C2 decisions. This means air defense and missile defense share `combat/air_defense.py` for common engagement mechanics, with `missile_defense.py` handling the BMD-specific intercept physics (exoatmospheric kinematics, discrimination, layered defense planning).
- **Air combat**: air-to-air BVR (beyond visual range) and WVR (within visual range) engagement models, missile Pk, countermeasures
- **Air-ground integration**: CAS request/approval workflow through C2, SEAD/DEAD against air defense networks, close air support deconfliction
- **Air defense**: SAM/AAA engagement envelopes (3D), shoot-look-shoot doctrine, EMCON states (radar on/off tradeoff between detection and self-protection). Shares engagement mechanics with missile_defense.py for IAMD (Integrated Air and Missile Defense) — same platforms engage both aircraft and missiles.
- **Ammunition**: distinct types (AP, HE, HEAT, DPICM, smoke, illumination, guided projectiles, rockets, missiles) with different effects. Units select appropriate type. Ammo is consumed by type, not as a generic pool. Missiles and guided rockets are individually tracked (low inventory, high cost); conventional rounds tracked by quantity per type.
- Fratricide: when identification confidence is low, friendly fire risk is computed. Poor visibility, intermixed forces, complex urban terrain all increase risk.
- Urban combat modifiers: close engagement ranges, building-to-building, verticality, civilian presence constraints
- **Weather effects on guided weapons**: GPS-guided munitions degrade with GPS accuracy (from environment/electromagnetic — ionospheric conditions, jamming). IR-guided weapons (Maverick, Sidewinder heat-seeking) are affected by thermal contrast (from environment/time_of_day) and IR-blocking weather (rain, fog, humidity). Laser-guided weapons require laser designation through clear air — fog, rain, smoke, and dust degrade laser propagation. Radar-guided weapons affected by sea/ground clutter conditions.
- **Fire and incendiary effects**: fire as a weapon (incendiary munitions, flamethrowers, napalm) and as a combat side-effect (tracers igniting dry vegetation, burning vehicles/structures). Fire spread modeled through terrain/vegetation combustibility model. Fires create: obscurants (smoke), thermal signatures (visible to sensors), terrain denial, infrastructure destruction, civilian casualties (if populated area). Historically significant — firebombing, forest fires from bombardment, urban conflagrations.
- **Altitude effects on explosives**: blast radius increases at altitude (lower ambient pressure). Fragment lethality pattern changes. Airburst vs ground burst effects vary with atmospheric density. This matters for mountain warfare and high-altitude engagements.
- **Electronic warfare effects** (future expansion point — interface specified here): EW touches multiple modules simultaneously and is critical for modern-era fidelity. **Radar jamming**: degrades air defense radar performance (combat/air_defense — Pk reduction, tracking errors, false targets), degrades surveillance radar (detection/ — increased noise floor, reduced detection range). Jamming is itself detectable (detection/sensors — jammer as EM emitter, bearing-only). **Communications jamming**: degrades radio reliability (c2/communications — message loss, delay), forces EMCON or alternative comms means. **GPS jamming/spoofing**: degrades navigation accuracy (movement/ — increased position error), degrades GPS-guided weapon accuracy (combat/ — CEP increase), forces fallback navigation (INS, celestial, map). **IR/laser countermeasures**: DIRCM against IR-guided missiles, laser warning receivers. **Chaff/flares**: decoys against radar and IR-guided weapons (already partially covered in combat/naval_surface and combat/air_combat). EW resources (jammers, EW aircraft, ground EW units) are limited and must be allocated by C2. EW effectiveness varies with environment/electromagnetic conditions. Full EW module or deep integration into detection/ and c2/ is deferred, but these interface points ensure the architecture accommodates it.
- **NBC/CBRN effects** (future expansion point): nuclear weapon effects (blast overpressure as function of yield and range, thermal radiation, initial nuclear radiation, residual radiation/fallout — fallout drift driven by wind model from environment/weather, mushroom cloud height as function of yield and atmospheric conditions), chemical weapon dispersion (agent persistence varies with temperature, wind, humidity — Sarin vs VX vs mustard have very different persistence profiles), biological agent spread. Contamination zones persist as dynamic terrain overlays. MOPP gear from entities/equipment provides protection at cost of combat effectiveness. Marked as future expansion but the interface points are specified here.
- **Naval surface warfare**: anti-ship missile engagement (salvo model — Wayne Hughes), naval gunfire (gun engagement ranges, shell types), torpedo attack on surface ships. Point defense systems (CIWS, SeaRAM). Chaff and decoy deployment. Ship damage model: flooding, fire, structural damage, mission kill vs sinking. Damage control as an active process that consumes crew and time.
- **Submarine warfare**: torpedo engagements (wire-guided, acoustic homing, wake homing), submarine-launched anti-ship missiles (must come to launch depth), submarine-launched cruise/ballistic missiles. Evasion tactics (decoys, noisemakers, depth changes, knuckle turns). Counter-torpedo defense.
- **Mine warfare**: mine types (contact, magnetic influence, acoustic influence, pressure, combination, smart/rising mines). Mine laying (surface, submarine, aircraft). Mine countermeasures: sweeping (simulating signatures to detonate), hunting (sonar detection + disposal), clearance diving. Mine danger areas and risk-based transit models.
- **Naval gunfire support**: shore bombardment supporting ground forces. Accuracy degrades with range and lack of spotting. Coordination through C2/fire support coordination.
- **Amphibious assault resolution**: the land-sea interface combat problem. Shore defense engagement of landing craft, naval fire support suppression of defenses, air support, beach obstacles, assault wave timing. The most complex multi-domain integration in the simulation.
- **Carrier operations**: sortie generation rate (function of deck crew, aircraft availability, weather), deck cycle time (launch/recovery windows), combat air patrol (CAP) management, strike package assembly, aircraft turnaround (rearm, refuel, repair). Flight deck damage cripples air capability.
- Feeds results to morale, logistics/medical, terrain (infrastructure damage) via event bus

**Depends on**: core/, terrain/, environment/, entities/, detection/

### morale/
**Owns**: Human factors. Morale state, cohesion, stress, experience, psychology, rout/rally/surrender.
- Reads combat results (casualties, suppression, fratricide) as inputs via event bus
- Modifies entity effectiveness and can trigger rout or surrender
- Reads entity organization for leadership/cohesion checks
- **Experience/training**: individual and unit training level is a continuous variable affecting combat effectiveness across all systems. Combat experience follows a learning curve — green troops perform worse than veterans, but the gap narrows with exposure.
- **Unit history and reputation**: units with distinguished combat records have higher baseline morale; units that have been repeatedly mauled carry institutional trauma
- **Sleep deprivation**: compounds with stress; extended ops without rest degrade decision-making, increase stress accumulation rate
- **PSYOP**: psychological operations (loudspeaker, leaflet, information warfare) affect enemy morale and civilian disposition. Can induce surrender or erode will to fight.
- **Surrender**: distinct from rout — surrendered units generate POWs that logistics must handle. Mass surrender events are possible under extreme conditions.
- **Leadership**: loss of leaders (killed, wounded, captured) has cascading morale effects through the unit. Quality of replacement leaders matters.
- **Environmental morale effects**: extreme cold, extreme heat, persistent rain, and darkness all erode morale over time as stressors. Extended operations in harsh environments (desert, arctic, jungle, high altitude) compound fatigue and stress. Conversely, improving conditions (moving from exposed positions to shelter, seasonal warming, sunrise after a long night engagement) can provide modest morale recovery. Isolation (small units cut off, submarines on extended patrol, remote outposts) is a distinct psychological stressor.

**Depends on**: core/, entities/, environment/ (for environmental stress modifiers)

### c2/
**Owns**: The entire command and control layer. Command authority, orders at every echelon, planning processes, communications, ROE, coordination, mission command, and AI decision-making. Split across two phases: **Phase 5** builds the C2 plumbing (orders, comms, ROE, coordination, succession — the mechanism), **Phase 8** builds the AI brain (OODA, planning, doctrine, commander personality — the decision-maker).

#### Command Authority (c2/command.py)
- **Command relationships** map to entities/organization task_org: OPCON, TACON, ADCON, support relationships determine what authority a commander has over attached/subordinate units
- **Succession**: when a commander is lost, succession rules apply per the organizational SOP. Replacement leader quality draws from personnel pool. C2 disruption creates a decision vacuum — units default to last orders or local initiative (based on mission command doctrine) until succession resolves.
- **Commander's intent**: the guiding statement that enables subordinate adaptation. More detailed intent → less subordinate freedom. Mission-type orders (Auftragstaktik) vs detailed orders (Befehlstaktik) — this is CONFIGURABLE per nation/doctrine. German/US doctrine emphasizes mission command; Soviet doctrine emphasized detailed control from above.

#### Orders System (c2/orders/)
Orders exist at every echelon with fundamentally different character:
- **Individual/fire team**: move to point, engage target, take cover, suppress position, throw grenade, breach door, first aid. These are near-instantaneous, shouted or signaled.
- **Squad/platoon (tactical)**: assault objective, establish defense, set ambush, execute patrol route, perform recon, break contact, bound forward, establish support-by-fire. Minutes to issue.
- **Company/battalion (tactical)**: attack, defend, delay, withdraw, passage of lines, relief in place, screen, guard, cover, movement to contact, reconnaissance in force. 30 min to hours of planning.
- **Brigade/division (operational)**: designate main effort, commit reserve, establish phase lines/boundaries, deep operations, shaping operations, set conditions for decisive operation. Hours to a day of planning.
- **Corps/army (operational-strategic)**: operational maneuver, theater force allocation, major logistics decisions, operational pause/culmination assessment. Days of planning.
- **Campaign/theater (strategic)**: force allocation across theaters, strategic objectives, political-military guidance, alliance management, war termination criteria. Weeks of planning.
- **Naval-specific**: formation orders, ASW prosecution orders, strike package assignment, convoy routing orders, blockade station assignment, amphibious operation orders, fleet movements. Naval orders often cover vast distances and long timeframes.
- **Air-specific** (`air_orders.py`): air operations follow a distinct C2 cycle that doesn't map to the ground echelon model. The **Air Tasking Order (ATO)** is a theater-wide 24-72 hour document scheduling all sorties — missions, aircraft, targets, timing, refueling, ordnance loads. The **Airspace Control Order (ACO)** deconflicts airspace (corridors, restricted zones, transit routes). **SPINS** (Special Instructions) cover ROE, IFF procedures, and communications. ATO changes flow as FRAGOs. CAS requests from ground forces must be integrated into the ATO cycle or handled as immediate/preplanned requests through the air support operations center (ASOC). Strike package assembly, tanker scheduling, and CAP rotation are all planned at theater level. This planning cycle creates a tempo constraint — air power cannot instantly respond to every ground request; there is a planning lag unless dedicated CAS aircraft are on station.
- **Order format**: OPORD (complete operation order with 5 paragraphs: situation, mission, execution, sustainment, C2), FRAGO (fragmentary order — changes to existing OPORD), WARNO (warning order — advance notice). The format scales with echelon — a squad leader gives a verbal brief; a division issues a written OPORD with annexes.
- **Order propagation**: orders take TIME to transmit down the chain. A corps order must be received, interpreted, translated into subordinate orders at division, then brigade, then battalion, etc. Each echelon adds planning time and interpretation delay. Orders can be degraded, delayed, or misunderstood in transmission — stochastic propagation model.
- **Order execution tracking**: units report compliance/status back up the chain (also subject to delay and degradation). Commanders track execution against plan. Deviation beyond threshold triggers reassessment.

#### Planning Process (c2/planning/) — *Phase 8b*
- **Configurable planning model**: MDMP (Military Decision Making Process — US), Soviet-style directive planning, rapid/abbreviated planning for time-constrained situations, intuitive decision-making for small units. Selected per doctrine and echelon.
- **Mission analysis**: determine specified tasks, implied tasks, constraints, restated mission, commander's critical information requirements (CCIR). This step feeds the AI's understanding of what needs to happen.
- **Course of action (COA) development and analysis**: the AI develops multiple possible plans, then wargames them (yes, wargaming WITHIN the wargame — using simplified models to predict outcomes). COA comparison selects the best option.
- **Running estimates**: each staff section maintains a continuous estimate of the situation in their domain (intel estimate, logistics estimate, personnel estimate, comms estimate). These are continuously updated and inform decision-making. A logistics estimate that shows fuel running out in 48 hours constrains operational planning.
- **Operational phasing**: operations are divided into phases (shaping, decisive, exploitation, transition). Phase transitions are triggered by conditions, not just time. The planning system pre-plans branch and sequel operations.
- **Planning horizon**: higher echelons plan further ahead. A platoon leader plans the next 30 minutes; a corps commander plans 72-96 hours ahead. The AI planning depth matches echelon.

#### Communications (c2/communications.py)
- Bandwidth-limited, can be degraded by terrain, weather, distance, jamming
- EMCON states (radio silence tradeoff — emitting reveals position)
- **Communication means**: radio (fast, broadcast, interceptable), wire/fiber (secure, terrain-dependent), messenger (slow, unreliable, unjammable), data link (high bandwidth, digital, technology-dependent). Each has speed, reliability, capacity, and intercept risk characteristics.
- **Submarine communications**: VLF/ELF (one-way to submarine, extremely low bandwidth — essentially "come to periscope depth for orders"), satellite at periscope depth (vulnerability window), trailing wire antenna. This fundamentally shapes submarine autonomy.
- **Naval data links**: Link 11, Link 16 with bandwidth and latency. Enable distributed maritime awareness but can be jammed or exploited.

#### ROE, Coordination, Mission Command
- **ROE (c2/roe.py)**: constrains what units are permitted to engage, escalation rules, civilian protection requirements, law of armed conflict compliance. Political constraints may override military optimality. ROE can differ by unit, by theater, by target type. ROE violations generate events that affect political dimension.
- **Coordination (c2/coordination.py)**: fire support coordination (FSCL, CFL, no-fire areas, restricted fire areas, target lists — high-payoff target list / attack guidance matrix), airspace coordination (air corridors, transit routes, restricted operating zones, missile flight corridors for TBM/cruise missile deconfliction), boundary management (lateral, rear), sea-land-air integration (composite warfare commander, amphibious force coordination). Deep fires coordination: targets beyond FSCL are service-coordinated (air or missile), targets short of FSCL require ground force coordination. Failure of coordination → fratricide or missed opportunities.
- **Mission command (c2/mission_command.py)**: commander's intent enables subordinates to adapt to changing conditions without waiting for new orders. Degree of subordinate initiative is configurable by doctrine — high in US/German tradition, lower in Soviet/Russian tradition. When communications are cut, units operating under mission command can continue to function; units operating under detailed control may freeze.

#### AI Decision-Making (c2/ai/) — *Phase 8a*
- **OODA loop (ooda.py)**: Observe (from detection/intel), Orient (situation assessment considering doctrine, experience, cultural factors), Decide (COA selection), Act (order generation). Loop speed varies by echelon, commander quality, and staff capability. Faster OODA → tempo advantage.
- **Commander personality (commander.py)**: AI commanders are not all the same. Personality model includes: risk tolerance (cautious ↔ aggressive), initiative level (waits for orders ↔ acts independently), preferred doctrine (attritionist ↔ maneuverist), decisiveness, adaptability. Loaded from YAML profiles. This creates realistic variation — some commanders exploit opportunities aggressively, others consolidate carefully.
- **Situation assessment (assessment.py)**: evaluates relative combat power (from entities/capabilities), terrain advantage, supply state, morale state, intel confidence, operational tempo, AND environmental conditions (weather forecast, daylight remaining, tidal windows, seasonal ground state, visibility forecast). Environmental assessment is integral — a commander deciding whether to attack considers whether there's enough daylight remaining, whether weather will support air operations, whether the ground will support armored maneuver. This is the "Orient" phase of OODA — synthesizing all available information into an actionable picture.
- **Decision logic (decisions.py)**: echelon-appropriate decision-making from individual (shoot/don't shoot, take cover or advance) through strategic (commit reserves, change main effort, request reinforcements). Decisions are stochastic — the model produces probability-weighted options, then selects with noise reflecting commander quality and information uncertainty.
- **Adaptation (adaptation.py)**: reacting when the plan meets reality. Detecting that the situation has changed (surprise contact, unexpected resistance, opportunity), assessing whether the current plan is still viable, deciding whether to adapt or continue, generating a new plan if needed. This is where Clausewitzian friction becomes a C2 problem — how fast can the command system adapt?
- **Doctrine (doctrine.py)**: codified tactical/operational patterns per nation and era. Offensive operations (movement to contact, attack — hasty/deliberate, exploitation, pursuit), defensive (area defense, mobile defense, retrograde — delay/withdrawal/retirement), stability (security ops — screen/guard/cover, area security), enabling (passage of lines, relief in place, river crossing, airborne/air assault, amphibious). Doctrinal templates define the sequence of actions, not the specific decisions — they're the playbook, not the game plan.
- **Stratagems (stratagems.py)**: higher-order concepts that operate above tactical doctrine. Deception plans (coordinated with detection/deception.py for execution), feints and demonstrations, economy of force (accepting risk in one area to mass elsewhere), concentration (massing combat power at the decisive point), surprise (achieving it and reacting to it), tempo control (dictating the pace of operations to keep the enemy off balance). These are the domain of experienced commanders and represent the art of war that transcends mechanical doctrine.

#### Doctrinal Schools (c2/ai/schools/) — *Phase 19*
- **School framework (base.py)**: `SchoolDefinition` pydantic model for YAML-loaded school parameters (assessment_weight_overrides, preferred/avoided_actions, ooda_multiplier, coa_score_weight_overrides, risk_tolerance, stratagem_affinity, opponent_modeling). `DoctrinalSchool` ABC with 8 hooks producing modifier dicts consumed by existing engines via DI parameters.
- **Registry (__init__.py)**: `SchoolRegistry` maps school_id → instance and unit_id → school_id. `SchoolLoader` reads YAML definitions from `data/schools/`. State protocol support.
- **Western schools**: `ClausewitzianSchool` (center-of-gravity, decisive engagement, culmination awareness), `ManeuveristSchool` (tempo/OODA ×0.7, bypass, indirect), `AttritionSchool` (exchange ratio, fire superiority, deliberate), `AirLandBattleSchool` (echelon-dependent deep/close, sensor-to-shooter), `AirPowerSchool` (Five Rings, air superiority prerequisite)
- **Eastern schools**: `SunTzuSchool` (intel ×3, opponent modeling via Lanchester lookahead, counter-posture scoring), `DeepBattleSchool` (echeloned assault, reserve management, operational-depth strikes)
- **Maritime schools**: `MahanianSchool` (fleet concentration, decisive naval battle), `CorbettianSchool` (fleet-in-being, sea denial, selective engagement)

**Depends on**: core/, entities/, detection/, environment/ (AI assessment queries environmental conditions for operational planning)

### logistics/
**Owns**: Sustaining the force. Supply network, supply classification, consumption, transport, stockpiles, maintenance, engineering, medical evacuation, POW handling, disruption.
- Reads entity consumption rates (by supply class, by activity level)
- Modifies entity supply state (ammo by type, fuel, food, water, medical supplies, spare parts)
- **Military supply classes**: Class I (food/water), Class III (fuel), Class V (ammo by type), Class VIII (medical), Class IX (spare parts), etc. Each has distinct consumption patterns, transport requirements, and criticality. **Consumption rates are environmentally variable**: Class I water consumption doubles or triples in extreme heat (from environment/weather temperature + humidity); Class III fuel consumption increases dramatically in cold weather (engine warming, heating) and in mud/snow conditions (higher resistance); Class VIII medical supply consumption increases with environmental casualties (heat, cold, altitude — not just combat casualties).
- Queries terrain/strategic map for route throughput, environment for weather disruption
- **Leverages terrain infrastructure**: road/rail networks determine supply route capacity (paved road vs dirt track vs cross-country), existing civilian infrastructure (warehouses, fuel depots, hospitals) can be utilized — urban/suburban areas provide denser logistics infrastructure than rural
- **Transport modes**: truck convoys (road-dependent, degraded by seasonal road conditions — rasputitsa renders unpaved routes impassable), airlift (weather-dependent — ceiling, visibility, icing conditions from environment/weather determine flyability; density altitude limits cargo capacity at hot/high airfields), aerial resupply/airdrop (for cut-off units — wind affects drop accuracy), rail (high capacity, infrastructure-dependent, vulnerable to interdiction but highest throughput per effort). Each mode has capacity, speed, vulnerability, and infrastructure requirements. Transport mode viability is environmentally conditional — a supply route that works in summer may be impassable in spring thaw.
- **Maintenance**: equipment requires periodic maintenance, not just combat repair. Breakdown probability increases with operational hours/miles. Maintenance requires spare parts (Class IX), time, and maintenance personnel. Deferred maintenance compounds breakdown risk.
- **Engineering**: bridging (temporary bridges enabling river crossing), road building/repair, fortification construction, obstacle emplacement and clearing, minefield laying and breaching. Engineer units are a limited resource.
- **Medical system**: casualty evacuation chain (point of injury → aid station → field hospital → rear hospital), triage queueing model (priority by severity), treatment capacity affects casualty outcomes (KIA vs return-to-duty vs permanent loss). Overwhelmed medical facilities degrade outcomes.
- **POW handling**: captured enemy and surrendered units require processing, guarding, feeding, transport to rear. Consumes logistics resources.
- **Captured supplies/equipment**: battlefield recovery of enemy supplies and abandoned equipment
- **Missile and guided munition logistics**: missiles and precision-guided munitions are high-value, low-density items with distinct logistics patterns. TBMs require specialized transporter-erector-launchers (TELs) and reload vehicles. Cruise missile VLS cells on ships cannot be reloaded at sea (must return to port). MLRS/HIMARS pods require dedicated ammunition resupply vehicles. Guided munition inventories are finite and strategically significant — a campaign may exhaust precision stocks, forcing reversion to unguided fires. Missile supply is tracked individually, not by weight/volume like conventional ammo. Interceptor inventory (Patriot, SM-3, Iron Dome) is a critical constraint on missile defense sustainability.
- **Naval logistics**: fundamentally different from land logistics — ships carry their own supplies but in finite quantities, and resupply at sea is complex and vulnerable.
  - **Underway replenishment (UNREP/RAS)**: transfer of fuel, ammunition, stores, and personnel between ships at sea while underway. Requires specific ship types (oilers, supply ships), favorable sea state, and time alongside. Vulnerable during the evolution.
  - **Port operations**: loading/unloading at port. Port throughput limited by crane capacity, berth availability, draft depth, and port infrastructure quality. Damaged ports operate at reduced capacity.
  - **Sealift**: strategic transport of forces and supplies by sea. High capacity but slow. Vulnerable to submarine and air interdiction — convoy protection is a major naval mission.
  - **Logistics over-the-shore (LOTS)**: supplying ground forces across a beach without a port. Low throughput, weather-dependent, requires specialized equipment. Used when ports are unavailable or destroyed.
  - **Naval basing**: forward operating bases, anchorages, naval base capacity (dry dock, repair, ammunition handling). Distance to base affects station time and operational tempo.
  - **Ship fuel consumption**: varies dramatically with speed (roughly cubic relationship). Endurance planning is a critical constraint — a task force's range is limited by its shortest-legged ship. Fuel state drives operational decisions.
  - **Blockade**: naval interdiction of enemy maritime trade and supply lines. Effectiveness depends on force disposition, geography, and intelligence.
- **Water procurement**: Class I water can be sourced locally if terrain/hydrography provides freshwater sources (rivers, wells, lakes — from terrain/hydrography). Water quality varies. Arid terrain forces full water supply from rear, massively increasing logistics burden. Desalination capability (naval assets, engineer equipment) can supplement in coastal areas.
- **Cold weather logistics**: extreme cold requires: fuel for vehicle warming and troop heating (dramatically increases Class III consumption), winterization kits for vehicles, cold weather clothing and shelter, anti-freeze for water systems, special lubricants. Failure to supply cold weather items → cold casualties (frostbite, hypothermia) that consume Class VIII medical supplies and evacuate manpower. The Winter War, Stalingrad, Chosin Reservoir — cold weather logistics failures have decided campaigns.
- **Hot weather logistics**: extreme heat requires: increased water (up to 10+ liters/person/day in desert operations vs 3-4 in temperate), electrolyte supplements, refrigeration for Class I perishables and Class VIII medications (some medications degrade above 30°C), cooling systems. Heat casualties consume medical resources and evacuate manpower.
- **Seasonal route degradation**: road and route conditions are NOT static — they change with environment/seasons ground state. A supply route planning model that assumes summer road conditions will catastrophically fail in spring mud season. The logistics planner must account for seasonal route capacity variation.
- Can be disrupted by combat (interdiction via event bus), sabotage (hostile population), naval blockade, submarine interdiction of sea lines of communication (SLOCs), and environmental factors (seasonal route loss, weather grounding of airlift, storms closing ports, sea ice blocking maritime routes)
- Friendly vs adversarial population disposition affects local logistics (friendly → local support/labor; hostile → sabotage risk)

**Depends on**: core/, terrain/, environment/, entities/

### simulation/
**Owns**: Orchestration. The master loop, campaign/battle management, scenario setup, victory conditions, metrics, recording.
- Calls into all other modules in the correct sequence each tick. **Tick sequence matters**: environment must update before domain modules query conditions — the tick begins with clock advance, then environment state update (astronomical positions, weather evolution, tidal state, illumination, conditions compositing), THEN movement/detection/combat/etc. execute against current conditions.
- Manages scale transitions (campaign ↔ battle)
- **Scenario initialization**: loads scenario date/time, computes initial astronomical state (where is the sun? what's the moon phase? what's the tidal state?), initializes weather from scenario starting conditions, establishes seasonal ground state, sets up the full environmental context before any unit acts.
- **Victory conditions**: objective-based, attrition-based, time-based, political — configurable per scenario. War termination criteria for campaigns.
- **Reinforcement pipeline**: at campaign level, manages the generation and arrival of reinforcements (units training and deploying over time)
- **Metrics and analysis**: statistical aggregation of simulation outputs (casualty rates, exchange ratios, supply consumption rates, environmental casualties, supply consumption by category, detection performance vs conditions, etc.) for post-run analysis. Environmental conditions logged alongside events for correlation analysis (e.g., "detection rates during ducting conditions" or "casualty rates during night vs day").
- Does NOT contain domain logic — only sequencing and coordination

**Depends on**: Everything (top of the dependency tree)

---

## Dependency Graph

```
                       simulation/
                   /    |    |    \     \      \
                  /     |    |     \     \      \
                c2/  combat/ logistics/ movement/ morale/
               / |     |        |        |        |
              /  |     |        |        |        |
        detection/     |        |        |        |
           |    \      |        |        |        |
           |     \     |        |        |        |
        terrain/ entities/ environment/           |
              \      |       /    |              /
               \     |      /     |             /
                \    |     /   coordinates/    /
                 \   |    /       |           /
                  \  |   /        |          /
                      core/
```

Arrows point downward (dependency direction). `environment/` depends on `core/` AND `coordinates/` (needs latitude for astronomical calculations). All domain modules (movement, detection, combat, logistics, c2, morale) consume `environment/` for condition modifiers.

A module may only import from modules below it in this graph. No circular dependencies.

---

## Key Design Rules

1. **No circular imports**: Dependency flows strictly downward per the graph above.
2. **Modules communicate through interfaces, not internals**: Each module exposes a clean public API in its `__init__.py`. Internal implementation details are private.
3. **Domain logic lives in domain modules, not in simulation/**: The `simulation/` module orchestrates but never computes. If you're writing an `if` statement about combat in `simulation/engine.py`, it belongs in `combat/` instead.
4. **Entities are data, modules are behavior**: `entities/` defines what a tank IS (stats, state). `movement/` defines how a tank MOVES. `combat/` defines how a tank FIGHTS. This separation allows the same entity to be acted on by multiple systems cleanly.
5. **All stochastic behavior goes through core/rng.py**: No module creates its own RNG. All request a stream from the central manager.
6. **All time goes through core/clock.py**: No module tracks its own time. All query the simulation clock.
7. **All config goes through core/config.py patterns**: No ad-hoc config parsing. YAML → pydantic → validated config objects.
8. **Terrain is mostly read-only during simulation**: Natural terrain (elevation, land cover) is loaded once at scenario start and does not change. Infrastructure (bridges, roads, buildings) CAN be modified by combat events via the event bus (e.g., `BridgeDestroyedEvent`), but only as discrete state changes — never continuous mutation. Population disposition may shift in response to events (bombardment → hostile shift).
9. **Rolling documentation**: All design documents (brainstorm, specs, phase plans, this document) are living documents. Any design decision made during implementation that has ramifications beyond the immediate module MUST be propagated back to all affected documents. Use `/update-docs` to maintain consistency. No document is "finished" — they evolve with the project. If a spec is superseded, mark it as such with rationale rather than deleting.

---

## Inter-Module Communication: Event Bus

Modules communicate laterally through a **typed event bus** in `core/events.py`, not by importing each other directly. This preserves the downward-only dependency graph while allowing information to flow between peer modules.

- Modules **publish** typed events (e.g., `CasualtyEvent`, `DetectionEvent`, `SupplyDepletedEvent`)
- Modules **subscribe** to event types they care about
- The event bus lives in `core/`, so all modules can access it without creating lateral dependencies
- `simulation/recorder.py` subscribes to ALL events — gives replay recording for free
- Event dispatch is synchronous and deterministic (ordered by simulation clock, then by registered priority)

**Examples:**
- `combat/` publishes `CasualtyEvent` → `morale/` subscribes (morale impact), `logistics/medical` subscribes (casualty evacuation), `entities/` subscribes (personnel state update)
- `combat/` publishes `LeaderKilledEvent` → `morale/` subscribes (cascading morale impact), `c2/hierarchy` subscribes (succession), `entities/` subscribes (personnel update)
- `detection/` publishes `DetectionEvent` → `c2/` subscribes, updates situational awareness
- `detection/` publishes `IdentificationEvent` → `combat/` subscribes (engagement authorization), `c2/` subscribes (target classification update)
- `combat/` publishes `InterdictionEvent` → `logistics/` subscribes, disrupts supply route
- `combat/` publishes `InfrastructureDestroyedEvent` → `terrain/` subscribes (bridge out), `logistics/` subscribes (route recalculation)
- `combat/` publishes `CivilianCasualtyEvent` → `terrain/population` subscribes (disposition shift), `c2/` subscribes (ROE review), `morale/` subscribes (moral injury)
- `combat/` publishes `FratricideEvent` → `morale/` subscribes (severe morale impact), `c2/` subscribes (deconfliction review)
- `combat/` publishes `SurrenderEvent` → `logistics/prisoners` subscribes (POW processing), `morale/` subscribes (contagion check on nearby units)
- `logistics/maintenance` publishes `EquipmentBreakdownEvent` → `entities/` subscribes (readiness degradation), `c2/` subscribes (combat power assessment update)
- `morale/` publishes `RoutEvent` → `movement/` subscribes (involuntary retreat movement), `c2/` subscribes (adjust plan), neighboring units subscribe (morale contagion check)
- `environment/` publishes `WeatherChangeEvent` → `movement/`, `detection/`, `combat/`, `logistics/` all subscribe (update condition modifiers)
- `environment/` publishes `SeaStateChangeEvent` → `movement/naval`, `combat/naval`, `detection/sonar`, `logistics/naval` subscribe (maritime condition update)
- `environment/` publishes `IlluminationChangeEvent` → `detection/` subscribes (NVG/visual sensor effectiveness), `movement/` subscribes (night movement penalty), `c2/` subscribes (operational planning)
- `environment/` publishes `ThermalCrossoverEvent` → `detection/` subscribes (thermal sensor degradation window)
- `environment/` publishes `TidalStateChangeEvent` → `movement/amphibious` subscribes (landing timing, beach exposure computation from tidal height + terrain/beach gradient), `logistics/naval` subscribes (port access — draft clearance), `movement/naval` subscribes (tidal current effects on navigation)
- `environment/` publishes `SeasonTransitionEvent` → `terrain/` subscribes (ground state, vegetation, snow cover), `movement/` subscribes (trafficability), `logistics/` subscribes (route capacity), `detection/` subscribes (concealment)
- `environment/` publishes `PropagationConditionChangeEvent` → `detection/` subscribes (radar ducting, anomalous propagation), `c2/communications` subscribes (HF propagation, data link performance)
- `environment/` publishes `FireSpreadEvent` → `terrain/` subscribes (vegetation destruction, concealment loss), `movement/` subscribes (terrain denial), `detection/` subscribes (thermal/visual signature), `logistics/` subscribes (route obstruction)
- `environment/` publishes `SeaIceEvent` → `movement/naval` subscribes (route availability), `logistics/naval` subscribes (port access), `detection/sonar` subscribes (ambient noise)
- `combat/naval_subsurface` publishes `TorpedoImpactEvent` → `entities/` subscribes (hull damage, flooding), `morale/` subscribes
- `combat/naval_surface` publishes `ShipSunkEvent` → `logistics/` subscribes (loss of supply/transport capacity), `morale/` subscribes, `c2/` subscribes (task force reorganization)
- `combat/naval_mine` publishes `MineStrikeEvent` → `entities/` subscribes (damage assessment), `movement/` subscribes (area avoidance update), `logistics/` subscribes (route rerouting)
- `combat/amphibious_assault` publishes `BeachSecuredEvent` → `logistics/` subscribes (LOTS can begin), `movement/` subscribes (shore access opened)
- `detection/sonar` publishes `SubmarineContactEvent` → `c2/naval_c2` subscribes (ASW prosecution decision), `combat/` subscribes (engagement authorization)
- `c2/orders` publishes `OrderIssuedEvent` → `simulation/recorder` subscribes (order log), relevant domain modules subscribe (execute order)
- `c2/orders` publishes `OrderMisunderstoodEvent` → `simulation/recorder` subscribes (friction log), `c2/ai/adaptation` subscribes (detect execution deviation)
- `entities/organization/task_org` publishes `TaskOrgChangeEvent` → `c2/` subscribes (update command relationships), `logistics/` subscribes (update supply routing)
- `c2/ai` publishes `PlanChangeEvent` → `c2/orders` subscribes (generate new orders), `simulation/recorder` subscribes
- `c2/communications` publishes `CommsLostEvent` → `c2/mission_command` subscribes (switch to last intent), `morale/` subscribes (isolation stress)
- `movement/` publishes `DustPlumeEvent` → `detection/` subscribes (visual signature — dust plumes from vehicle movement visible for miles in arid/dry terrain), `environment/obscurants` subscribes (local visibility reduction from dust)
- `environment/weather` publishes `PrecipitationEvent` → `terrain/hydrography` subscribes (river level change, flooding potential), `movement/` subscribes (mud, snow accumulation), `logistics/` subscribes (route degradation)
- `entities/equipment` publishes `PowerDepletedEvent` → `detection/` subscribes (sensor capability loss), `c2/communications` subscribes (comms capability loss), `movement/` subscribes (navigation degradation)

## Data Cross-Referencing (YAML Definitions)

Unit YAML files reference weapons, ammunition, sensors, signatures, and doctrine by ID. The resolution chain:

1. Unit YAML lists `weapons: [m256_120mm, m2_50cal]` by ID
2. Weapon YAML lists `compatible_ammo: [m829a3_apfsds, m830a1_heat, m1028_canister]` by ID
3. Unit YAML lists `sensors: [commanders_sight_thermal]`, resolved against `data/sensors/`
4. Unit YAML lists `signature_profile: m1a2_signature`, resolved against `data/signatures/`
5. AI doctrine templates resolved against `data/doctrine/`
6. `entities/loader.py` resolves ALL references recursively, building fully assembled objects

This means:
- A single weapon definition (e.g., `m256_120mm.yaml`) can be referenced by multiple unit types
- Ammunition definitions are shared across weapons of the same caliber/type
- Signature profiles can be shared (variants of the same vehicle) or unique
- Changing any shared definition propagates to all referencing entities
- `entities/loader.py` is responsible for the full resolution and validation — if any ID doesn't resolve, it fails at load time, not mid-simulation
- Circular references are detected and rejected at load time

---

## Open Questions for Future Specs
- Exact public API signatures for each module (defined per-module in `/spec`)
- Plugin/extension architecture for modding support
- Parallel simulation support (multiple independent battles running concurrently)
- Electronic warfare: jamming, SIGINT, EW effects on comms and sensors — needs its own module or deep integration into detection/ and c2/communications. Priority for modern era fidelity.
- Cyber operations: disruption of C2 networks, sensor spoofing — future scope
- Maritime acoustic propagation fidelity: ray tracing vs simplified layer models for sonar — tradeoff between accuracy and computational cost
- Carrier air wing management granularity: individual aircraft tracking vs squadron-level abstraction
- Amphibious operations: how granular is the ship-to-shore interface? Individual landing craft or wave-level?
- NBC/CBRN: nuclear, biological, chemical weapon effects and contamination zone modeling
- Civilian interaction depth: how granular does population modeling get? (aggregate density vs individual civilian agents)
- Urban combat (MOUT) specifics: building-clearing mechanics, floor-by-floor resolution vs abstracted urban modifiers
- Coalition/alliance modeling: multiple allied forces with different ROE, equipment, doctrine, C2 interoperability
- Information warfare / strategic communications: media effects, public opinion, information operations
- Asymmetric warfare: insurgency, IED, guerrilla tactics — may need distinct modeling approaches beyond conventional force-on-force
- Rear area security: LOC protection, partisan activity, force protection
- Astronomical algorithm precision: Meeus (sufficient for military sim — arcminute accuracy) vs VSOP87/DE ephemeris (arcsecond accuracy — overkill?). Meeus is self-contained Python; VSOP87 would need external data files.
- Tidal harmonic data source: per-scenario manual specification vs integration with tidal prediction databases (NOAA CO-OPS, UK Admiralty). For historical backtesting, actual tidal data from historical records may be available.
- Weather model fidelity: stochastic Markov transitions (simpler, faster) vs mesoscale weather modeling (physically accurate but computationally expensive). Likely Markov conditioned on climate zone/season for v1.
- Fire spread modeling: cellular automaton on terrain grid (computationally manageable) vs continuous fire front propagation (higher fidelity). Fire is a secondary effect — cellular automaton likely sufficient initially.
- Ionospheric model fidelity: simplified solar-activity-conditioned tables vs IRI (International Reference Ionosphere) model. IRI is more accurate but complex. For HF propagation, this matters significantly.
- Environmental casualty models: validated data for heat/cold casualty rates as functions of exposure, equipment, hydration, acclimatization — may need /research-military for historical data (WW2 arctic, desert campaigns, Korean War winter)

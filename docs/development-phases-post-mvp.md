# Stochastic Warfare — Post-MVP Development Phases

## Philosophy
Same as MVP: every phase produces runnable, testable code. Validation via matplotlib. No UI until engine fidelity justifies it. Phases 11–12 fix known deficits and deepen existing systems (including civilian population). Phases 13–14 optimize and tool up. Phases 15–19 add new domains. Phases 20–23 expand to historical eras. Phase 24 adds unconventional warfare and escalation modeling.

**Cross-document alignment**: This document must stay synchronized with `brainstorm-post-mvp.md` (design thinking), `devlog/index.md` (deficit inventory), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**Deficit traceability**: Every item in `devlog/index.md` Post-MVP Refinement Index must be assigned to a phase below or explicitly marked as "won't fix" with rationale.

---

## Phase 11: Core Fidelity Fixes — **COMPLETE**
**Goal**: Fix MAJOR and high-impact MODERATE deficits that change simulation outcomes without requiring architectural rework.

**Status**: Complete. 109 tests (9 + 42 + 35 + 23) across 4 test files. Total: 3,818 tests passing (up from 3,782). 15 changes across ~20 existing source files + retrospective cleanup (3 source fixes, 6 new tests, 2 test file migrations). No new modules, no new dependencies. All changes backward-compatible with default parameters preserving MVP behavior. Devlog: [`devlog/phase-11.md`](devlog/phase-11.md).

### 11a: Combat Fidelity (5 changes, 42 tests)
- `combat/ammunition.py` (modified) — Fire rate limiting: `_last_fire_time_s`, `_cooldown_s` (from `rate_of_fire_rpm`) on `WeaponInstance`. `can_fire_timed()`/`record_fire()` gate engagement.
- `combat/engagement.py` (modified) — `current_time_s` param, cooldown gate returns `aborted_reason="cooldown"`.
- `simulation/battle.py` (modified) — Per-side `target_size_modifier_{target_side}` with fallback to uniform value.
- `combat/air_combat.py`, `air_defense.py`, `naval_surface.py`, `indirect_fire.py` (modified) — Environment coupling: weather_modifier, visibility_km, sea_state, wind_speed/direction params.
- `combat/ballistics.py` (modified) — Mach-dependent drag: `_speed_of_sound()`, `_mach_drag_multiplier()` with piecewise regimes. `enable_mach_drag` config flag.
- `combat/damage.py` (modified) — `ArmorType` enum (RHA/COMPOSITE/REACTIVE/SPACED), effectiveness lookup, ricochet at >75°.

### 11b: Detection Fidelity (4 changes, 35 tests)
- `detection/sensors.py` (modified) — `boresight_offset_deg` field on `SensorDefinition`.
- `detection/detection.py` (modified) — FOV check against observer heading + boresight offset. Dwell/integration gain: `_scan_counts` dict, SNR + 5·log10(n_scans), capped at `max_integration_gain_db` (6.0 dB).
- `detection/sonar.py` (modified) — Geometric bearing via `atan2(dx, dy)` + SNR-dependent Gaussian noise. Both `passive_detection()` and `active_detection()`.
- `detection/estimation.py` (modified) — Mahalanobis gating: `d² = y.T @ S_inv @ y`, reject if > `gating_threshold_chi2` (9.21 = 99% for 2 DOF). `update()` returns `bool`.

### 11c: Movement & Logistics Fidelity (4 changes, 23 tests)
- `movement/engine.py` (modified) — Fuel gating: `fuel_available` param, zero fuel stops movement, partial fuel clamps distance. Infantry unaffected.
- `logistics/engineering.py` (modified) — Stochastic engineering times: `duration_sigma` config, log-normal variation when sigma > 0. Default 0.0 preserves MVP.
- `simulation/battle.py` (modified) — Wave attack modeling: `wave_assignments` dict (0=immediate, N=delayed, -1=reserve), `battle_elapsed_s` tracking.
- `simulation/scenario.py` + `campaign.py` (modified) — Stochastic reinforcement arrivals: `arrival_sigma` config, `actual_arrival_time_s` computed via log-normal at setup.

### 11d: AI Fidelity (2 changes, 9 tests)
- `c2/ai/decisions.py` (modified) — Pass actual echelon through `_decide_brigade_div()` instead of hardcoded 9.
- `c2/ai/ooda.py` + `simulation/battle.py` (modified) — `tactical_acceleration` config (default 0.5), `tactical_mult` param on `compute_phase_duration()`/`start_phase()`. Stacks with future Phase 19 doctrinal modifiers.

**Exit Criteria**: All met. Fire rate limiting gates engagement timing. Sensor FOV rejects out-of-arc targets. Mach-dependent drag changes transonic/supersonic trajectories. Stochastic reinforcement arrivals vary across seeds. All 3,818 tests pass. Deterministic replay verified.

---

## Phase 12: Deep Systems Rework
**Goal**: Fix MODERATE deficits requiring deeper refactoring — multi-hop C2, multi-echelon logistics, and enhanced domain models.

### 12a: C2 Depth
- `c2/communications.py` (modify) — Multi-hop message propagation: build relay chain from issuer to recipient through hierarchy. Each hop has independent P(success) and delay.
- `c2/communications.py` (modify) — Terrain-based comms LOS: check terrain/los.py between transmitter and receiver for VHF/UHF (line-of-sight radio). HF/satellite unaffected.
- `c2/communications.py` (modify) — Network degradation model: data link bandwidth saturation under high message volume, priority-based message queuing, graceful degradation (latency increase before message loss) rather than binary up/down.
- `c2/coordination.py` (modify) — Arbitrary polyline FSCL: replace east-west line with Shapely LineString. Point-in-polygon test for fire zone.
- `c2/orders/air_orders.py` (modify) — ATO planning cycle: generate ATO from air tasking request queue, allocate sorties to missions, enforce cycle timing. Builds on Phase 8's air planning structures (ATO/ACO/CAS) which currently define structure without generation logic.
- `c2/coordination.py` (modify) — JTAC/FAC observer model: CAS requires observer with LOS to target. Observer reports target location with error.
- `c2/coordination.py` (modify) — JIPTL (Joint Integrated Prioritized Target List) generation: collect target nominations from subordinate units, prioritize by commander intent + doctrinal weighting, allocate to available shooters (air, artillery, missile). Cycles at operational tick rate.
- `c2/joint_ops.py` — Joint task force command model: JTF command entity with component commands (JFLCC, JFACC, JFMCC). Inter-service coordination delays (service-specific communication equipment + liaison officer quality). Interoperability penalties: cross-service orders suffer additional propagation delay (×1.5) and misinterpretation probability (×2.0) unless liaison present. Coalition partner caveats — configurable per-nation restrictions on what operations a coalition unit will participate in.
- `detection/fog_of_war.py` (modify) — Network-centric shared situational awareness: units connected via tactical data link (Link 16, FBCB2) share contact tracks laterally, building a Common Operational Picture (COP). Contact tracks propagated via data link inherit the originator's track quality (position error, classification confidence) degraded by link latency. Units without data link maintain independent fog-of-war only. Network disruption (link failure, jamming) fragments the shared picture.

### 12b: Logistics Depth
- `logistics/supply_network.py` (modify) — Multi-echelon supply chain: depot → MSR → BSA → unit. Each echelon has capacity and throughput limits.
- `logistics/supply_network.py` (modify) — Supply optimization: minimum-cost flow (networkx) replacing nearest-depot pull. Respects capacity constraints.
- `logistics/supply_network.py` (modify) — Infrastructure-coupled transport: road/rail quality from terrain infrastructure modulates transport speed and capacity. Paved roads = faster, rail = high-capacity, destroyed bridges = route severed. Prepares for Phase 15 real-world infrastructure integration.
- `logistics/supply_network.py` (modify) — Supply chain resilience: automatic alternate route discovery when primary route severed (bridge destroyed, road interdicted). Rerouting delay proportional to detour distance. Network redundancy metric per supply node (single point of failure detection).
- `logistics/production.py` — Supply regeneration at depots: configurable production rate per supply class (ammo/day, fuel/day). Production capacity tied to strategic infrastructure nodes (factory, refinery, port). Infrastructure damage (from strategic air campaign or sabotage, Phase 12f/24) reduces production rate proportionally. Essential for campaigns longer than 3–5 days — without regeneration, depots deplete and campaigns hit artificial supply ceilings.
- `logistics/transport.py` (modify) — Escort effects: convoy P(survival) modified by escort strength vs threat level along route.
- `logistics/medical.py` (modify) — Erlang service distribution: replace exponential with Erlang-k for more realistic treatment time variance.

### 12c: Combat Depth
- `combat/air_combat.py` (modify) — Energy-maneuverability basics: track energy state (altitude + speed → specific energy). Advantage from energy differential.
- `combat/naval_surface.py` (modify) — Compartment flooding model: damage creates flooding zone, progressive list with counter-flooding. Capsize at threshold.
- `combat/naval_subsurface.py` (modify) — Submarine evasion: geometric model with bearing rate, speed differential, thermocline crossing.
- `combat/naval_subsurface.py` (modify) — Submarine campaign operations: patrol area assignment (geographic zones, chokepoints, convoy routes), patrol effectiveness model (detection probability per unit time scales with area size and submarine sensor suite), ASW campaign coordination (surface ships + helicopters + submarines + maritime patrol aircraft as coordinated hunter-killer groups with shared sonar data).
- `combat/naval_mine.py` (modify) — Ship signature interaction: mine trigger probability from acoustic/magnetic/pressure signature match.
- `combat/naval_mine.py` (modify) — Mine warfare operations: mine-laying orders (by naval aircraft, surface ships, submarines — delivery method determines placement accuracy and rate), MCM (mine countermeasures) task type with sweep/hunt modes (mechanical sweep for contact mines, influence sweep for magnetic/acoustic, mine hunting with sonar classification), mine persistence model (battery life, corrosion, deactivation), minefield routing effects (forced detours through cleared channels, congestion penalties).
- `combat/amphibious_assault.py` (modify) — Amphibious operations depth: landing craft capacity model (number of craft × load capacity × turnaround time = throughput), beach unloading rate (varies by beach gradient, obstacles, enemy fire), tidal window constraints (landing timing keyed to Phase 1 tidal model — spring vs neap tide affects beach approach depth), contested landing enhancements (shore defense suppression requirement from naval gunfire, mine/obstacle clearing phase before first wave, casualty evacuation via ship).

### 12d: Morale & Psychology Depth
- `morale/state.py` (modify) — Continuous-time Markov: transition rates instead of probabilities. `P(transition in dt) = 1 - exp(-λ·dt)`.
- `morale/psychology.py` (modify) — Enhanced PSYOP: message type × target susceptibility × delivery method. Replace flat effectiveness roll.

### 12e: Civilian Population & COIN
- `population/__init__.py` — Package init
- `population/civilians.py` — Civilian entity manager: density by cell (from terrain/population.py), disposition (friendly/neutral/hostile/mixed), displacement tracking. Not combat entities — a terrain-like overlay affecting other systems.
- `population/displacement.py` — Refugee movement: combat drives displacement along road networks. Refugees block LOCs and slow military movement. Refugee camps as logistics burden.
- `population/collateral.py` — Collateral damage tracking: civilian casualties from indirect fire, air strikes, CBRN. Feeds into ROE escalation and political constraints.
- `population/humint.py` — Civilian HUMINT: friendly population generates detection events for enemy units (with noise/delay). Hostile population warns enemy of friendly movement. Modulated by disposition.
- `population/influence.py` — Population disposition dynamics: Markov chain with transition rates driven by military actions (collateral damage −, aid +, PSYOP, presence patrols). Disposition affects HUMINT flow, logistics access, and morale.
- `c2/roe.py` (modify) — ROE escalation triggers: collateral damage threshold → automatic ROE tightening (WEAPONS_FREE → TIGHT → HOLD).

**YAML data**: Population disposition profiles per region type (urban, suburban, rural, hostile territory).

### 12f: Strategic Air Campaigns & IADS
- `combat/iads.py` — Integrated Air Defense System model: multiple air defense systems (early warning radars, acquisition radars, SAMs, AAA, MANPADS) organized into sectors with layered engagement zones (long-range SAM → medium-range SAM → short-range AAA/MANPADS). Radar handoff: early warning radar acquires track → passes to acquisition radar → engagement radar locks → SAM launches. Kill chain timing per handoff stage. Shared radar coverage — destruction of an early warning radar blinds all SAMs in its sector until backup acquisition. IADS command node: destruction degrades coordination (SAMs revert to autonomous engagement with reduced effectiveness). SEAD degradation: each ARM/strike against IADS nodes reduces sector coverage and coordination quality. IADS health metric per sector.
- `combat/air_campaign.py` — Air campaign management: sustained sortie rate model (available aircraft × sortie rate × mission duration = daily sortie capacity). Pilot fatigue tracking (missions/day limit, crew rest requirement). Weather days (poor weather cancels sorties proportional to ceiling/visibility — instrument-capable aircraft less affected). Aircraft availability (maintenance cycle reduces fleet size by ~20-30%, combat losses reduce permanently). Attrition-replacement dynamics (aircraft losses vs depot-level repair vs new production). Campaign phases: air superiority → SEAD → interdiction → CAS (Warden/AirLand Battle sequential or parallel based on doctrine).
- `combat/strategic_targeting.py` — Strategic target system: Target Priority List (TPL) generation from commander intent + doctrinal school priorities (Phase 19). Target types: airfield, bridge, power plant, C2 node, logistics hub, factory, port, fuel depot, ammunition depot. Target-effect chain: destroy target → cascading operational effect (bridge → supply route severed, airfield → reduced enemy sortie rate, power plant → C2 degradation in area, fuel depot → supply crisis for nearby units). Bomb Damage Assessment (BDA) cycle: strike → BDA sortie/ISR pass → damage estimate (with accuracy noise — historical tendency to overestimate damage) → re-strike decision. Target regeneration: damaged targets repair over time (bridge repair faster than factory rebuild), infrastructure repair units accelerate restoration.
- `terrain/infrastructure.py` (modify) — Strategic infrastructure nodes: bridges, power plants, airfields, ports, factories as targetable entities with health state (operational/damaged/destroyed), repair timers, and cascading effects on logistics and C2 when damaged. Connects to logistics/production.py for factory damage → reduced supply regeneration.

**YAML data**: IADS sector configurations, strategic target databases per scenario, aircraft availability profiles.

**Exit Criteria**: C2 orders propagate through multi-hop relay chains with accumulated delay and loss probability. Data link-connected units share contact tracks laterally (COP). Joint ops coordination delays are measurable between services. JIPTL allocates targets to available shooters. Supply flows through echeloned network with capacity constraints and regenerates at production rate. Supply chain reroutes when primary route is severed. Air combat energy state affects engagement outcomes. IADS coordinates multi-system defense with radar handoff; SEAD degrades IADS sector health. Strategic targeting destroys infrastructure with cascading logistics/C2 effects. Air campaign sortie rate is constrained by aircraft availability and pilot fatigue. BDA cycle introduces assessment noise. Naval damage includes progressive flooding. Submarine patrols cover assigned zones; ASW hunter-killer groups coordinate. Mine-laying and MCM operations function. Amphibious landing throughput limited by craft capacity and tidal windows. Multi-hop C2 causes order delay in Golan Heights campaign (historically accurate). Civilian collateral triggers ROE tightening. Friendly population provides actionable HUMINT. Refugee movement slows LOC throughput. All existing tests pass. Deterministic replay verified.

---

## Phase 13: Performance Optimization
**Goal**: Achieve 5x speedup on campaign-scale simulations through algorithmic optimization, compiled extensions, and parallelism.

### 13a: Algorithmic Optimization
- `terrain/infrastructure.py` (modify) — STRtree spatial index for building/road queries. Replace brute-force iteration.
- `terrain/los.py` (modify) — Multi-tick LOS cache: invalidate only cells where units moved. Track dirty cells per tick.
- `terrain/los.py` (modify) — Viewshed vectorization: batch multiple observer LOS checks using numpy broadcasting.
- `detection/estimation.py` (modify) — Cache Kalman F/Q matrices for fixed dt. Only recompute on tick duration change.
- `simulation/engine.py` (modify) — Force aggregation: aggregate distant units into formation-level entities at strategic resolution. Disaggregate when entering tactical battle.
- `simulation/battle.py` (modify) — Auto-resolve option: Lanchester-based quick resolution for battles below interest threshold.

### 13b: Compiled Extensions
- `core/numba_utils.py` — Numba JIT decorators with pure-Python fallback. `@optional_jit` wrapper.
- `combat/ballistics.py` (modify) — Numba JIT for RK4 trajectory integration inner loop.
- `terrain/los.py` (modify) — Numba JIT for DDA raycasting inner loop.
- `movement/pathfinding.py` (modify) — Numba JIT for A* cell cost computation.

**Also**: `pyproject.toml` — add `numba` as optional dependency (`uv sync --extra perf`)

### 13c: Parallelism
- `simulation/engine.py` (modify) — Thread-pool for per-side computations within a tick (detection, morale, logistics). Requires PRNG stream partitioning.
- `validation/monte_carlo.py` (modify) — Extend campaign MC parallelism. Verify deterministic replay with per-worker seed streams.

**Visualization**: Benchmark comparison charts (before/after per phase).

**Exit Criteria**: 73 Easting full run <0.5s (from ~2s). Golan Heights campaign <3s (from ~15s). 100-iteration MC on 4 cores <25s (from ~120s). STRtree LOS with buildings 10x faster than brute-force. Numba-accelerated RK4 5x faster than pure Python. All results identical to pre-optimization (bit-for-bit deterministic). Deterministic replay verified.

---

## Phase 14: Tooling & Developer Experience
**Goal**: Build developer tools, analysis utilities, and MCP server for LLM-assisted simulation.

### 14a: MCP Server
- `tools/mcp_server.py` — MCP server exposing simulation as tools: `run_scenario`, `query_state`, `run_monte_carlo`, `compare_results`, `list_scenarios`, `list_units`, `modify_parameter`
- `tools/mcp_resources.py` — MCP resource providers for scenario files, unit definitions, results

### 14b: Analysis Tools
- `tools/sensitivity.py` — Parameter sweep: vary one parameter across range, run N iterations each, plot outcome distribution
- `tools/comparison.py` — A/B scenario comparison with Mann-Whitney U test for statistical significance
- `tools/narrative.py` — Natural language generation from RecordedEvents: tick-by-tick battle narrative
- `tools/tempo_analysis.py` — Operational tempo analysis: FFT of engagement/event frequency over time, tempo comparison between sides, OODA cycle timing distributions. Implements the spectral analysis concept from the original brainstorm.

### 14c: Visualization
- `tools/replay.py` — Animated battle replay via matplotlib FuncAnimation: unit positions, engagement lines, detection arcs per tick
- `tools/charts.py` — Standard chart library: force strength timeline, engagement network graph, supply flow diagram

### 14d: Claude Skills
- `/scenario` skill — Interactive scenario creation/editing via structured prompts
- `/compare` skill — Run two configurations and summarize differences
- `/what-if` skill — Quick parameter sensitivity wrapper
- `/timeline` skill — Generate narrative from a completed simulation run
- `/orbat` skill — Interactive order of battle builder
- `/calibrate` skill — Auto-tune calibration overrides to match historical data

**Exit Criteria**: MCP server responds to all tool calls with correct results. Sensitivity analysis produces parameter sweep plots. A/B comparison returns p-values. Battle replay animation renders 73 Easting. All new skills functional. No regression in existing tests.

---

## Phase 15: Real-World Terrain & Data Pipeline
**Goal**: Import real-world elevation, land cover, infrastructure, and bathymetry data for scenario creation on actual geography.

### 15a: Elevation Pipeline
- `terrain/data_pipeline.py` — Coordinate-based tile fetcher: bounding box → tile list → download/cache. Format detection (GeoTIFF/HGT/NetCDF).
- `terrain/real_heightmap.py` — SRTM/ASTER GeoTIFF → heightmap grid. Projection handling via pyproj. Bilinear resampling to simulation grid resolution.

### 15b: Classification & Infrastructure
- `terrain/real_classification.py` — Copernicus Land Cover → classification enum grid. Nearest-neighbor resampling.
- `terrain/real_infrastructure.py` — OSM PBF → Shapely geometries for roads (LineString), buildings (Polygon), bridges (Point + attributes), rivers (LineString). STRtree indexed.

### 15c: Maritime Data
- `terrain/real_bathymetry.py` — GEBCO NetCDF → bathymetry grid. Coordinate transform to simulation ENU.

### 15d: Integration
- `terrain/data_pipeline.py` (extend) — Unified `load_real_terrain(bbox, resolution)` API returning complete terrain context.
- `simulation/scenario.py` (modify) — Scenario YAML `terrain_source: real` option with bounding box coordinates.
- `logistics/supply_network.py` (modify) — Wire real infrastructure data into supply routing: road quality affects transport speed, rail lines provide high-capacity routes, bridge destruction severs routes. Builds on Phase 12b infrastructure-coupled transport.

**Also**: `pyproject.toml` — add `rasterio`, `xarray` as optional dependencies (`uv sync --extra terrain`). Download scripts in `scripts/download_terrain.py`.

**Visualization**: Side-by-side comparison of synthetic vs real terrain for 73 Easting location.

**Exit Criteria**: Can load 10km×10km real terrain tile for 73 Easting (29°N, 46°E) with elevation, classification, roads. Resolution matches simulation grid. Bathymetry loads for Falklands scenario area. Fallback to synthetic when data unavailable. Cached tiles load in <1s. 73 Easting on real terrain produces results within validation tolerance. Deterministic replay verified.

---

## Phase 16: Electronic Warfare
**Goal**: Full EW domain — jamming, ECCM, SIGINT, electronic decoys — modulating existing detection and C2 systems.

### 16a: Spectrum & Emitters
- `ew/__init__.py` — Package init
- `ew/spectrum.py` — EM spectrum manager: frequency band definitions, allocation tracking, spectral conflict detection
- `ew/emitters.py` — Emitter registry: all active emitters (radars, radios, jammers) with frequency, power, location, waveform type. EventBus integration for emitter state changes.

### 16b: Electronic Attack
- `ew/jamming.py` — Jamming models: noise, barrage, spot, sweep, deceptive. J/S ratio calculation. Effect on sensor SNR (feeds into detection/detection.py `jam_factor`). Effect on comms reliability (feeds into c2/communications.py).
- `ew/spoofing.py` — GPS spoofing: distinct from jamming — spoofing provides false position data rather than denying signal. Spoofed GPS introduces systematic position error (configurable offset vector) rather than increased noise. Affects PGM guidance (munitions fly to wrong coordinates), navigation (units drift off course), and timing (GPS timing-dependent systems desynchronize). Detection probability based on receiver sophistication (military M-code receivers more resistant than civilian). Distinguishing spoofing from jamming requires cross-checking with INS — detection delay before switch to INS-only mode.
- `ew/decoys_ew.py` — Electronic decoys: expanded chaff/flare models (from detection/deception.py), towed decoys, DRFM (digital RF memory) repeaters.

### 16c: Electronic Protection
- `ew/eccm.py` — Frequency hopping: reduces jam effectiveness by bandwidth ratio. Spread spectrum. Sidelobe blanking. Adaptive nulling (antenna pattern adjustment).

### 16d: Electronic Support
- `ew/sigint.py` — Signal intercept: P(intercept) from receiver sensitivity, bandwidth overlap, emitter power. Geolocation via TDOA (time-difference-of-arrival) and AOA (angle-of-arrival). Traffic analysis (message volume → unit activity inference).

**YAML data**: Jammer definitions (ground, airborne, naval), EW suite definitions per platform.

**Validation scenarios**:
- `data/scenarios/bekaa_valley_1982.yaml` — Israeli SEAD vs Syrian SAM network. Drones provoke radar emissions, SIGINT geolocates SAMs, ARMs suppress radars, strike aircraft exploit gaps. Validates full EA/EP/ES chain.
- `data/scenarios/gulf_war_ew_1991.yaml` — Coalition EW campaign vs Iraqi IADS. Validates large-scale SEAD, GPS jamming effects, HARM employment.

**GPS/SATCOM jamming note**: Phase 16 implements GPS/SATCOM jamming by degrading the static `gps_accuracy` parameter in `environment/electromagnetic.py` and SATCOM reliability in `c2/communications.py`. Phase 17 (Space) later replaces these static parameters with dynamic orbital-driven values. The EW jamming mechanism remains the same — it modulates whatever the current GPS accuracy source provides (static in Phase 16, orbital in Phase 17+).

**Exit Criteria**: Jamming reduces radar detection range by calculated J/S ratio. ECCM (frequency hopping) partially restores detection. SIGINT geolocates active emitters within accuracy bounds. Comms jamming increases message loss rate. EW decoys divert incoming missiles. GPS jamming degrades PGM accuracy via `gps_accuracy` parameter. GPS spoofing introduces systematic position error distinct from jamming noise — spoofed PGMs miss by offset vector, not random scatter. Military receivers (M-code) resist spoofing better than civilian. Bekaa Valley scenario produces Israeli air superiority when EW employed vs high losses without. All effects feed through existing parameters (no parallel combat system). Deterministic replay verified.

---

## Phase 17: Space & Satellite Domain
**Goal**: Model space-based assets (GPS, SATCOM, ISR, early warning) as force multipliers that modulate existing systems, and anti-satellite warfare that degrades them.

**Prerequisite**: Depends on environment/electromagnetic.py (gps_accuracy), c2/communications.py (SATCOM), detection/intel_fusion.py (IMINT), combat/missiles.py (CEP/guidance). All exist. EW (Phase 16) provides GPS/SATCOM jamming via the static `gps_accuracy` parameter — Phase 17 replaces that static value with a dynamic orbital-driven model. EW jamming mechanism is unchanged (it modulates whatever GPS accuracy source exists). Phase 17 works without Phase 16 via manual degradation inputs.

### 17a: Orbital Mechanics & Constellation Management
- `space/__init__.py` — Package init
- `space/orbits.py` — Simplified Keplerian orbit propagation: period `T = 2π√(a³/μ)`, ground track computation via rotation + inclination, J2 nodal precession for sun-synchronous orbits. Kepler equation solver (Newton-Raphson). NOT full SGP4/TLE — sufficient for campaign-scale "when does satellite see theater?"
- `space/constellations.py` — Constellation manager: define satellite groups (GPS 24-slot MEO, GLONASS 24-slot MEO, imaging LEO, SIGINT LEO/HEO, early warning GEO/HEO, SATCOM GEO). Compute coverage windows over theater bounding box. Track constellation health (degraded satellite count). EventBus integration for constellation state changes.
- `space/events.py` — Space domain events: SatelliteOverpassEvent, GPSDegradedEvent, SATCOMWindowEvent, ASATEngagementEvent, ConstellationDegradedEvent.

### 17b: GPS Dependency & Navigation Warfare
- `space/gps.py` — GPS accuracy model: visible satellite count over theater → DOP (dilution of precision) → position error `σ = DOP × σ_range`. INS drift model for GPS-denied: `σ(t) = σ₀ + drift_rate × t`. Wire into `environment/electromagnetic.py` gps_accuracy parameter and `combat/missiles.py` CEP for GPS-guided munitions. JDAM-class weapons degrade from ~13m CEP (GPS) to ~30m+ (INS-only).

### 17c: Space-Based ISR & Early Warning
- `space/isr.py` — Space-based ISR: imaging satellites generate detection events during overpass windows. Resolution determines minimum detectable unit size (vehicle vs battalion). Revisit time from orbital period + ground track drift. Cloud cover blocks optical satellites (not SAR). Feeds into `detection/intel_fusion.py` as IntelSourceType.IMINT with satellite-specific accuracy and delay.
- `space/early_warning.py` — Missile early warning: GEO/HEO IR satellites detect missile launches (IR bloom). Detection time = coverage check + processing delay (30-90s). Wire into `combat/missile_defense.py` early warning time parameter. No coverage = no early warning (fall back to ground radar with shorter range).

### 17d: SATCOM Dependency & Anti-Satellite Warfare
- `space/satcom.py` — SATCOM dependency model: satellite coverage windows determine SATCOM availability for beyond-LOS communications. Bandwidth capacity limits per theater. Degradation feeds into `c2/communications.py` reliability for SATCOM-type equipment. No coverage window = SATCOM unavailable.
- `space/asat.py` — Anti-satellite warfare: direct-ascent kinetic kill vehicle (Pk from intercept geometry, closing velocity, warhead lethal radius), co-orbital rendezvous intercept, ground-based laser dazzling (temporary blinding vs permanent). Debris generation: each kinetic kill produces N fragments (Poisson), each with per-orbit collision probability for satellites at similar altitude (Kessler cascade risk). Satellite loss → constellation degradation → cascading effects on GPS accuracy, ISR coverage, SATCOM availability, and early warning.

### 17e: Integration & Validation
- `simulation/engine.py` (modify) — Wire SpaceEngine into SimulationContext. Update constellation state at strategic tick rate. Pass GPS accuracy and SATCOM availability to downstream modules.
- `simulation/scenario.py` (modify) — Scenario YAML `space_config` section for constellation definitions and initial state. `space_config: null` for backward compatibility.

**YAML data** (~14 files): GPS constellation (24 satellites), GLONASS constellation (24 satellites), 2 SATCOM constellation definitions (GEO military, GEO commercial), 3 imaging satellite definitions (optical LEO, SAR LEO, SIGINT HEO), 2 early warning satellite definitions (GEO IR, HEO Molniya), 2 ASAT weapon definitions (direct-ascent KKV, ground-based laser), 3 validation scenario files.

**Validation scenarios**:
- `data/scenarios/space_gps_denial.yaml` — PGM accuracy comparison: full GPS vs degraded (3 satellites visible) vs denied (INS-only). Validate CEP against published tables.
- `data/scenarios/space_isr_gap.yaml` — Red force exploits imaging satellite gap to reposition undetected. Validate overpass timing accuracy.
- `data/scenarios/space_asat_escalation.yaml` — Kinetic ASAT degrades GPS constellation from 24→18 satellites. Validate cascading DOP increase and PGM accuracy degradation.

**Exit Criteria**: GPS denial increases PGM CEP by correct factor (~2-3x for partial, ~10x for full denial). Satellite overpass timing matches simplified Keplerian prediction within ±5min. SATCOM unavailability degrades comms reliability for SATCOM-dependent units. ASAT engagement produces constellation degradation with correct cascading effects. ISR satellites generate detection events during overpass windows only. All effects feed through existing parameters (no parallel systems). Backward compatible when `space_config: null`. No new dependencies. Deterministic replay verified.

---

## Phase 18: NBC/CBRN Effects
**Goal**: Chemical, biological, radiological, and nuclear effects — contamination, protection, casualties, decontamination.

**Prerequisite**: Depends on environment/weather.py (wind for dispersal) and morale/stress.py (CBRN stress). Both exist.

### 18a: Agent Definitions & Dispersal
- `cbrn/__init__.py` — Package init
- `cbrn/agents.py` — Agent type definitions: nerve, blister, choking, blood, biological, radiological. Per-agent: persistence, lethality (LCt50/LD50), detection threshold, decon difficulty.
- `cbrn/dispersal.py` — Gaussian puff/plume atmospheric dispersion. Pasquill-Gifford stability classes from weather state. Wind advection, turbulent diffusion. Terrain channeling (valleys concentrate, ridges deflect).

### 18b: Contamination & Protection
- `cbrn/contamination.py` — Grid overlay: concentration per cell per agent, decay over time. Weather-dependent evaporation (temperature, wind), washout (rain). Terrain absorption (soil type from classification.py).
- `cbrn/protection.py` — MOPP levels 0–4: movement penalty (0%/5%/10%/20%/30%), detection penalty (0%/0%/10%/20%/30%), fatigue multiplier (1.0/1.1/1.2/1.4/1.6), heat stress in warm weather. Equipment effectiveness vs agent type.

### 18c: Casualties & Decontamination
- `cbrn/casualties.py` — Dose-response: dosage = Σ(concentration × exposure_time). Probit model for incapacitation and lethality. Feeds into medical pipeline.
- `cbrn/decontamination.py` — Decon operations: hasty (5min, 60% effective), deliberate (30min, 95%), thorough (2hr, 99%). Equipment requirements. Generates contaminated waste.

### 18d: Nuclear Effects
- `cbrn/nuclear.py` — Blast: overpressure from Hopkinson-Cranz scaling `ΔP = f(R/W^(1/3))`. Thermal radiation: burn radius by yield. Initial nuclear radiation: rem dosage by range. EMP: disables unshielded electronics in radius. Fallout: wind-driven plume using dispersal.py.

**YAML data**: Agent definitions (VX, sarin, mustard, chlorine, anthrax), delivery system definitions (artillery shell, aerial bomb, SCUD warhead).

**Visualization**: Contamination plume overlay on terrain, MOPP degradation charts.

**Validation scenarios**:
- `data/scenarios/cbrn_chemical_defense.yaml` — Chemical attack on a defended position (synthetic scenario based on documented agent types and Pasquill-Gifford meteorological conditions). Validates dispersal, MOPP response, casualty generation, terrain denial.
- `data/scenarios/cbrn_nuclear_tactical.yaml` — Tactical nuclear weapon against a massed formation. Validates blast radii, EMP, fallout plume. Compare casualty radii against FM 3-11 standardized yield/range tables.

**Exit Criteria**: Chemical strike creates contamination zone that persists and drifts with wind. Units in zone take casualties based on protection level. MOPP-4 reduces combat effectiveness to ~60%. Decontamination clears zones over time. Nuclear blast produces correct casualty radii for given yield. Chemical defense scenario produces historically plausible casualty rates. All effects feed through existing damage, morale, and movement systems. Deterministic replay verified.

---

## Phase 19: Doctrinal AI Schools
**Goal**: Named doctrinal schools enabling comparative analysis of different warfare philosophies.

**Prerequisite**: Depends on Phase 8 AI infrastructure (OODA, commander, doctrine, assessment, decisions, adaptation, stratagems). All exist.

### 19a: School Framework
- `c2/ai/schools/__init__.py` — Package init, school registry
- `c2/ai/schools/base.py` — Abstract base: `DoctrinalSchool` with hooks for assessment weighting, COA preference, risk modulation, decision triggers, stratagem affinity, opponent modeling
- `c2/ai/assessment.py` (modify) — Add opponent belief state and `predict_opponent_action()` method. Schools override to model opponent likely decisions. Sun Tzu school uses this heavily; Attrition school ignores it. One-step lookahead using existing Lanchester wargaming.

### 19b: Western Schools
- `c2/ai/schools/clausewitzian.py` — Center-of-gravity targeting, decisive engagement seeking, culmination point awareness, Schwerpunkt (main effort) selection
- `c2/ai/schools/maneuverist.py` — Tempo-driven OODA acceleration (×0.7 stacking with Phase 11d resolution multiplier), gap exploitation preference, C2/logistics targeting, bypass strongpoints, indirect approach
- `c2/ai/schools/attrition.py` — Exchange ratio optimization, fire superiority preference, deliberate attack, set-piece battle, massed fires
- `c2/ai/schools/airland_battle.py` — Simultaneous deep/close/rear operations, sensor-to-shooter kill chain emphasis, aggressive initiative delegation, FSCL-forward deep fires synchronized with close fight, AirLand Battle doctrine (Starry/DePuy)
- `c2/ai/schools/air_power.py` — Five Rings strategic targeting (Warden: leadership → organics → infrastructure → population → fielded forces), air superiority as prerequisite, strategic paralysis through parallel attack, interdiction preference over close support (Douhet/Warden)

### 19c: Eastern & Historical Schools
- `c2/ai/schools/sun_tzu.py` — Intel-first assessment (3× intel weight), deception planning, indirect approach, avoid strength/exploit weakness, "winning without fighting" via morale collapse
- `c2/ai/schools/deep_battle.py` — Echeloned assault (first echelon → second echelon → exploitation), operational-depth strikes, reserve management, simultaneous action across depth

### 19d: Maritime Schools
- `c2/ai/schools/maritime.py` — Mahanian (fleet concentration, decisive naval battle, sea control) vs Corbettian (fleet-in-being, commerce raiding, sea denial, limited war). School selection from commander YAML.

**YAML data**: 9 school definition files (clausewitzian, maneuverist, attrition, airland_battle, air_power, sun_tzu, deep_battle, maritime_mahanian, maritime_corbettian) with assessment weights, preferred/avoided actions, risk tolerances, stratagem affinities, opponent modeling parameters.

**Visualization**: Comparative outcome charts — same scenario run with different schools.

**Exit Criteria**: Each school produces measurably different behavior on the same scenario. Clausewitzian AI concentrates force; Sun Tzu AI emphasizes recon and deception; Maneuverist AI achieves faster OODA cycles; Attrition AI seeks favorable exchange ratios; Deep Battle AI echelons attacks; AirLand Battle AI synchronizes deep fires with close fight; Air Power AI prioritizes air superiority before ground commitment; Sun Tzu AI uses opponent modeling for deception planning. School differences are statistically significant across 100 MC runs. All schools produce valid (non-degenerate) outcomes. Deterministic replay verified.

---

## Phase 20: WW2 Era
**Goal**: World War 2 data package + engine extensions for pre-guided-munition, radar-emerging, propeller-aircraft warfare. Also establishes the **era framework** used by all subsequent era phases.

### 20a: Era Framework & Unit Data
- `core/era.py` — Era configuration system: `EraConfig` defining which simulation subsystems are active/inactive per era. Era enum (MODERN, WW2, WW1, NAPOLEONIC, ANCIENT_MEDIEVAL). Module disable list per era (e.g., ANCIENT_MEDIEVAL disables `detection/sensors.py` radar/thermal/sonar, `c2/communications.py` radio/data link, `ew/*`, `space/*`). Era-specific physics constants (Mach-dependent drag tables per era, propellant types, armor materials). Era-specific `TickResolution` defaults (Napoleonic tactical ticks may be longer than modern). Scenario YAML `era: ww2` field selects era config. `era: modern` is default and matches all existing behavior.
- `simulation/engine.py` (modify) — Query `EraConfig` to skip disabled subsystems during tick processing. No era config → all subsystems active (backward compatible).
- Unit & weapon data:
- `data/eras/ww2/units/` — 15+ unit definitions: Sherman M4A3, T-34/85, Tiger I, Panther, Panzer IV, M1 Garand squad, Wehrmacht rifle squad, Soviet rifle squad, Bf-109G, P-51D, Spitfire IX, B-17G, Type VIIC U-boat, Fletcher DD, Iowa BB
- `data/eras/ww2/weapons/` — Period weapons: 75mm M3, 88mm KwK 36, 76mm F-34, .50 cal M2, MG42, Mk 14 torpedo, 5"/38 naval gun, 16"/50 naval gun
- `data/eras/ww2/ammunition/` — AP, HE, APCR, APCBC rounds for each caliber
- `data/eras/ww2/sensors/` — Mk 1 eyeball (dominant), SCR-584 gun-laying radar, Type 271 naval radar, hydrophones
- `data/eras/ww2/signatures/` — Visual/acoustic signatures (no thermal, no radar cross-section for ground units)

### 20b: Engine Extensions
- `combat/naval_gunnery.py` — WW2 naval fire control: bracket firing, spotting correction, fire control computer (mechanical). Range-dependent dispersion pattern.
- `movement/convoy.py` — Convoy mechanics: formation types (column, broad front), escort positions, U-boat wolf pack attack sequence, depth charge patterns.
- `combat/strategic_bombing.py` — Area bombing model: CEP-based damage to target areas. Bomber stream, fighter escort, flak defense.

### 20c: Doctrine & Commanders
- `data/eras/ww2/doctrine/` — Blitzkrieg, Soviet deep operations, British deliberate attack, US combined arms
- `data/eras/ww2/commanders/` — Aggressive (Patton archetype), methodical (Montgomery archetype), operational art (Zhukov archetype)

### 20d: Validation Scenarios
- `data/eras/ww2/scenarios/kursk.yaml` — Prokhorovka tank battle (5th Guards Tank vs II SS Panzer)
- `data/eras/ww2/scenarios/midway.yaml` — Carrier battle (4 IJN carriers vs 3 USN carriers)
- `data/eras/ww2/scenarios/normandy_bocage.yaml` — Hedgerow fighting (infantry-centric, close terrain)

**Exit Criteria**: Era framework correctly disables irrelevant subsystems for WW2 era (no GPS, no thermal sights, no data links, no PGMs). WW2 scenarios load and run with period-appropriate unit definitions. Tank combat produces historically plausible exchange ratios (Tiger vs Sherman ~3:1 at range, closer at short range). Naval gunnery model produces bracket-and-hit patterns. No guided munitions used. Radar detection limited to period capabilities. Era config for MODERN era produces identical results to no-era-config (backward compatible). Validation against Kursk historical data within tolerance. Deterministic replay verified.

---

## Phase 21: WW1 Era
**Goal**: World War 1 data package + trench warfare, chemical weapons (requires Phase 18 CBRN), and pre-radio C2.

**Prerequisite**: Phase 18 (CBRN) for chemical weapon effects.

### 21a: Unit & Weapon Data
- `data/eras/ww1/units/` — British infantry platoon, German Sturmtruppen, French poilu squad, Mark IV tank, A7V, cavalry troop
- `data/eras/ww1/weapons/` — Lee-Enfield, Gewehr 98, Maxim MG08, Lewis gun, 18-pounder, 77mm FK 96, 21cm Mörser, Mills bomb
- `data/eras/ww1/sensors/` — Binoculars, sound ranging, flash spotting, observation balloon, aircraft recon

### 21b: Engine Extensions
- `terrain/trenches.py` — Trench system terrain type: fire trench, communication trench, support trench. Traverses. Cover values. Trench raiding mechanics.
- `combat/barrage.py` — Creeping barrage model: timed lift schedule, rolling curtain, units advance behind barrage line. Counter-battery fire.
- `combat/gas_warfare.py` — Gas delivery (cylinder release, artillery shell) → CBRN dispersal module. Gas mask effectiveness. Wind dependency critical.

### 21c: Validation Scenarios
- `data/eras/ww1/scenarios/somme_july1.yaml` — First day of the Somme (infantry assault against prepared defenses)
- `data/eras/ww1/scenarios/cambrai.yaml` — First massed tank attack with combined arms

**Exit Criteria**: Trench warfare produces WW1-characteristic casualty rates (attacker losses >> defender in frontal assault). Creeping barrage timing affects assault success rate. Chemical weapons create contamination zones requiring MOPP response. Pre-radio C2 shows massive order delays (hours, not minutes). Validation against Somme Day 1 casualty data within tolerance. Deterministic replay verified.

---

## Phase 22: Napoleonic Era
**Goal**: Napoleonic data package + black powder weapons, formation combat, cavalry, and courier C2.

### 22a: Unit & Weapon Data
- `data/eras/napoleonic/units/` — Line infantry battalion, light infantry, grenadier company, hussar squadron, cuirassier squadron, lancer squadron, horse artillery battery, foot artillery battery, Imperial Guard
- `data/eras/napoleonic/weapons/` — Smoothbore musket (Brown Bess, Charleville), Baker rifle, 6-pounder, 12-pounder, howitzer, cavalry saber, lance, bayonet

### 22b: Engine Extensions
- `combat/volley_fire.py` — Massed musket fire: volley by rank, rolling fire. Range-dependent hit probability (50m effective for smoothbore). Smoke generation per volley.
- `combat/melee.py` — Contact combat: bayonet charge, cavalry charge impact, saber vs infantry. Morale check on contact (receiving charge). Frontage and depth matter.
- `movement/cavalry.py` — Charge mechanics: approach → trot → gallop → impact. Fatigue from charge. Pursuit after rout. Screening and reconnaissance.
- `movement/formation_napoleonic.py` — Line (firepower), column (movement/shock), square (anti-cavalry), skirmish (light infantry). Formation change takes time.
- `c2/courier.py` — Physical messenger: travel time based on distance and terrain, interception risk, message loss. ADC system.
- `logistics/foraging.py` — Living off the land: forage radius, terrain productivity, season effects, army size vs land capacity (Napoleonic logistics).

### 22c: Validation Scenarios
- `data/eras/napoleonic/scenarios/austerlitz.yaml` — Pratzen Heights (combined arms, maneuver, decisive point)
- `data/eras/napoleonic/scenarios/waterloo.yaml` — Infantry squares vs cavalry charges, artillery preparation, Guard commitment

**Exit Criteria**: Musket volley fire produces period-appropriate casualty rates (~2-5% per volley at 100m). Cavalry charges break infantry not in square. Square formation stops cavalry but is vulnerable to artillery. Courier C2 produces hour-scale delays. Formation changes take minutes. Validation against Waterloo phase timing within tolerance. Deterministic replay verified.

---

## Phase 23: Ancient & Medieval Era
**Goal**: Pre-gunpowder data package + melee-dominant combat, siege warfare, and visual/audible C2.

### 23a: Unit & Weapon Data
- `data/eras/ancient_medieval/units/` — Roman legionary cohort, Greek hoplite phalanx, English longbowman company, Norman knight conroi, Swiss pike block, Mongol horse archer tumen, Viking huscarl warband
- `data/eras/ancient_medieval/weapons/` — Gladius, pilum, sarissa, longbow, crossbow, lance, sword, mace, pike, catapult, trebuchet, ballista, battering ram
- `data/eras/ancient_medieval/sensors/` — Mounted scouts, watchtower, ship lookout (no technology-based detection)

### 23b: Engine Extensions
- `combat/melee.py` (extend) — Formation-based melee: phalanx (deep formation, push), shield wall (frontage-limited), pike block (reach advantage). Weapon reach matters (pike > sword > dagger).
- `combat/siege.py` — Siege mechanics: wall breach (ram, mine, trebuchet), escalade, siege tower, boiling oil, sally. Starvation timeline. Relief force mechanics.
- `movement/naval_oar.py` — Galley propulsion: rowing speed, fatigue, ramming approach. Boarding action (melee on water).
- `c2/visual_signals.py` — Visual/audible C2: banner visibility (LOS + distance), horn range, runner speed. C2 radius ~500m for visual, ~200m for voice.

### 23c: Validation Scenarios
- `data/eras/ancient_medieval/scenarios/cannae.yaml` — Double envelopment (Hannibal vs Varro, 216 BC)
- `data/eras/ancient_medieval/scenarios/agincourt.yaml` — Longbow vs armored cavalry on constricted terrain (1415)
- `data/eras/ancient_medieval/scenarios/hastings.yaml` — Shield wall vs combined arms (infantry + cavalry + archers, 1066)

**Exit Criteria**: Melee combat produces historically plausible results (Cannae envelopment destroys Roman center, Agincourt longbow devastates French cavalry). Formation type dominates combat outcomes. Siege timeline matches historical durations (weeks to months). Visual C2 limits coordination to local commander's line of sight. Morale/rout cascades are primary battle-ending mechanism. Deterministic replay verified.

---

## Phase 24: Unconventional & Prohibited Warfare
**Goal**: Model escalation dynamics, prohibited weapons employment, unconventional/irregular warfare mechanics, war crimes consequences, and insurgency/COIN feedback loops. Adds the "full spectrum" of conflict that conventional-only modeling cannot capture.

**Prerequisites**: Phase 12e (civilian population — displacement, collateral, HUMINT, influence dynamics), Phase 18 (CBRN effects — chemical/biological/nuclear weapon effects). Benefits from Phase 16 (EW — counter-IED jamming), Phase 19 (doctrinal schools — school-specific escalation tendencies).

### 24a: Escalation Model & Political Pressure
- `escalation/__init__.py` — Package init
- `escalation/ladder.py` — Escalation state machine (0–10 scale from conventional through strategic nuclear). Threshold-driven transitions based on composite desperation index (casualties × supply crisis × morale collapse × stalemate duration). Commander personality modulates thresholds (`doctrine_violation_tolerance`, `escalation_awareness`). Hysteresis — easier to escalate than de-escalate.
- `escalation/political.py` — Political pressure model: international pressure (0–1, driven by war crimes + civilian casualties + prohibited weapon use + media visibility) and domestic pressure (0–1, driven by own casualties + stalemate + propaganda). Effects: international pressure → allied supply constraints → coalition fracture → forced ROE changes → war termination pressure. Domestic pressure → ROE loosening authorized → escalation authorized → conscription → leadership change risk.
- `escalation/consequences.py` — War crimes consequence engine: multi-domain cascading effects. Own-force morale penalty (guilt/PTSD stress), enemy morale hardening (justified anger/resolve), civilian hostility increase (insurgency recruitment), political pressure delta. Feedback loops: escalation spiral (mutual retaliation), COIN cycle (collateral → hostility → recruitment → IED → aggressive response → more collateral), coalition fracture cascade.
- `escalation/events.py` — `EscalationLevelChangeEvent`, `WarCrimeRecordedEvent`, `PoliticalPressureChangeEvent`, `CoalitionFractureEvent`, `ProhibitedWeaponEmployedEvent`, `CivilianAtrocityEvent`, `PrisonerMistreatmentEvent`, `ScorechedEarthEvent`

### 24b: Prohibited Weapons Data & Compliance
- `combat/ammunition.py` (modify) — Add `prohibited_under_treaties: list[str]` field to `AmmoDefinition` (default empty). Add `compliance_check: bool` flag. Add new `AmmoType` values: `CLUSTER`, `INCENDIARY_WEAPON`, `ANTI_PERSONNEL_MINE`, `EXPANDING`. Existing ammo YAML unchanged (empty treaty list = conventional).
- `combat/damage.py` (modify) — Activate `DamageType.INCENDIARY` damage path with fire spread model (wind-driven, terrain-fuel-dependent cellular automaton on terrain grid). Add UXO persistence model for cluster submunitions (area denial post-attack, civilian casualty generation). White phosphorus dual-use: incendiary + obscurant.
- `combat/engagement.py` (modify) — Pre-engagement compliance check: query ROE + escalation level + treaty flags. If prohibited weapon not authorized at current escalation level → select alternative ammo or abort. If authorized → log `ProhibitedWeaponEmployedEvent` → trigger consequence cascade.
- `c2/roe.py` (modify) — Treaty compliance gate in `check_engagement_authorized()`. Violation severity escalation for prohibited weapons (higher severity than standard ROE violations). Political-pressure-driven ROE modulation (international pressure → forced tightening, domestic pressure → authorized loosening).
- YAML data (~10 files): prohibited weapon/ammo definitions (Mk 20 Rockeye cluster bomb, BLU-97 DPICM submunition with UXO, M18A1 Claymore AP mine, PMN-2 AP mine, Mk 77 napalm bomb, white phosphorus shell, expanding bullet, BL-755 cluster bomb, SCUD-C chemical warhead, FAE thermobaric bomb with incendiary secondary)

### 24c: Unconventional Warfare Mechanics
- `movement/obstacles.py` (modify) — Add `ObstacleType.IED` (command-wire, pressure-plate, remote-detonated, vehicle-borne subtypes) and `ObstacleType.BOOBY_TRAP`. IED placement driven by population-hostility × cell-traffic × insurgent-cell-presence. Detection probability: engineering unit capability × speed tradeoff. Remote-detonated IEDs jammable by EW (Phase 16 forward-compatible).
- `entities/organization/special_org.py` (modify) — Add `OrgType.INSURGENT` (ideological loyalty, cell-based organization, population network), `OrgType.MILITIA` (tribal/territorial loyalty, unreliable outside home territory, local terrain bonus), `OrgType.PMC` (contract-based loyalty, payment-dependent, professional equipment). Trait definitions for each.
- `combat/unconventional.py` — IED engagement model (blast damage via existing damage system, psychological stress spike to entire unit, route denial effect). Guerrilla hit-and-run doctrine (engage with local superiority, disengage immediately, disappear into population in populated areas). Ambush site selection (terrain chokepoints, dead ground, pattern-of-life exploitation). Human shield mechanics (civilian proximity exploitation → forces enemy ROE to WEAPONS_HOLD; engagement through shields → massive civilian casualties → consequence cascade).
- `logistics/prisoners.py` (modify) — Treatment tracking: `TreatmentLevel` enum (STANDARD/MISTREATED/TORTURED). Interrogation stress model: intelligence extraction yields HUMINT source events with configurable delay + noise. High stress → faster yield but lower reliability (more noise). Treatment level affects: enemy surrender willingness (mistreatment → enemy fights harder), own-force morale (guilt penalty if discovered), political consequences (documented mistreatment → international pressure spike).
- `c2/ai/sof_ops.py` — SOF operations module: behind-lines infiltration (reduced detection signature), HVT targeting (target specific commanders → command succession cascade), direct action (surgical strikes on C2/logistics/air defense), unconventional warfare (train/equip indigenous forces → force multiplication), sabotage campaigns (infrastructure targeting → logistics disruption, bridge → route severance, power → C2 degradation, fuel depot → supply crisis).
- YAML data (~12 files): 6 doctrine templates (guerrilla_hit_and_run, insurgency_campaign, coin_population_centric, coin_kinetic, pmc_security, scorched_earth_denial), 4 IED/mine definitions (command_wire_ied, pressure_plate_ied, vbied, remote_ied), 2 SOF unit definitions (sf_oda, ranger_platoon)

### 24d: AI Escalation Logic
- `c2/ai/commander.py` (modify) — Add personality traits: `doctrine_violation_tolerance` (0.0–1.0, threshold multiplier for escalation — high = escalates at lower desperation), `collateral_tolerance` (0.0–1.0, willingness to accept civilian casualties for military gain), `escalation_awareness` (0.0–1.0, awareness of consequence costs — high = inhibits escalation). These modulate all escalation decisions.
- `c2/ai/decisions.py` (modify) — Add escalation action types to echelon-appropriate enums: `EMPLOY_PROHIBITED_WEAPON`, `AUTHORIZE_ESCALATION`, `ORDER_SCORCHED_EARTH`, `EMPLOY_CHEMICAL` (gated by escalation level + personality + desperation). Only accessible when `escalation_config` is active and desperation exceeds personality-modulated threshold.
- `c2/ai/adaptation.py` (modify) — Add 2 new triggers: `MILITARY_STALEMATE` (front line static for configurable duration) and `POLITICAL_PRESSURE` (domestic or international pressure exceeds threshold). Add `ESCALATE_FORCE` action response (evaluate whether escalation is warranted given desperation index + consequences). Add `DE_ESCALATE` action for high `escalation_awareness` commanders when consequences outweigh benefits.
- `c2/ai/stratagems.py` (modify) — Add 3 new stratagem types: `SABOTAGE_CAMPAIGN` (target enemy infrastructure/logistics via SOF or insurgent cells — gated by `doctrine_violation_tolerance` for civilian infrastructure), `TERROR` (deliberate targeting of civilian population to break enemy will — highest `doctrine_violation_tolerance` threshold, maximum consequences), `SCORCHED_EARTH` (deny terrain/resources to advancing enemy — destruction of own infrastructure/agriculture). Each gated by commander personality and escalation level.
- `c2/ai/assessment.py` (modify) — Add desperation index computation: weighted composite of `casualties_sustained/initial_strength`, `1 - supply_state`, `1 - avg_morale_score`, `stalemate_duration_normalized`, and `political_pressure_from_below`. Weights configurable per scenario. Desperation index feeds into escalation ladder transition logic. Add escalation consequence estimation: commanders with high `escalation_awareness` predict consequence costs before deciding.
- YAML data (~6 files): 4 commander profiles (ruthless_authoritarian — high violation tolerance/low awareness, desperate_defender — moderate tolerance/moderate awareness, insurgent_leader — high tolerance for unconventional/low for chemical, pmc_operator — contract-bounded/zero escalation beyond contract scope), 2 escalation threshold configs (cold_war_nuclear — high thresholds for chemical/nuclear, failed_state — low thresholds across board)

### 24e: Insurgency & COIN Integration
- `population/insurgency.py` — Insurgency dynamics engine: multi-stage Markov chain (neutral civilian → sympathizer → active supporter → insurgent cell member → armed combatant). Transition rates driven by radicalization factors (collateral damage +, economic deprivation +, grievance +, family casualty +) and de-radicalization factors (economic opportunity −, governance quality −, military protection −, PSYOP −). Cell formation when sufficient supporters in area. Cell capabilities: sabotage, IED emplacement, ambush, intelligence gathering for enemy, assassination. Cell activation from dormant (intelligence) to active (operations) based on orders/opportunity/trigger events. Cell network discovery via HUMINT, SIGINT (Phase 16), pattern analysis.
- `population/civilians.py` (modify) — Wire radicalization path from `population/influence.py` disposition dynamics. Collateral damage events → hostile disposition shift → `population/insurgency.py` recruitment pipeline. Military aid/protection → friendly disposition shift → HUMINT generation + reduced recruitment. Economic activity modeling (simplified): employment rate affects radicalization baseline.
- `logistics/disruption.py` (modify) — Add insurgent cell operations as disruption source type. Population-hostility-scaled sabotage targeting: cells target infrastructure proportional to hostility and military presence. IED emplacement events generated by active cells on high-traffic routes. Sabotage campaigns coordinated across cells when insurgency reaches organizational threshold.

### 24f: Integration & Validation
- `simulation/engine.py` (modify) — Wire `EscalationEngine` into `SimulationContext` (optional, `None` for conventional scenarios). Update per strategic tick: compute desperation indices per side, evaluate escalation transitions, apply political pressure deltas, process consequence events. Insert after strategic AI tick, before engagement detection.
- `simulation/scenario.py` (modify) — Add `escalation_config` section to scenario YAML schema. `escalation_config: null` (default) → no escalation engine, conventional warfare only. Full backward compatibility with all existing scenarios. Config includes: escalation ladder weights, political pressure parameters, consequence magnitudes, insurgency parameters.
- `simulation/victory.py` (modify) — Negotiated war termination: add `VictoryConditionType.CEASEFIRE` and `VictoryConditionType.ARMISTICE`. Triggered when political pressure (international or domestic) on one or both sides exceeds configurable threshold AND military stalemate duration exceeds minimum. Ceasefire freezes all combat (detection continues, logistics continues, no new engagements). Armistice ends simulation with negotiated outcome. Terms determined by territorial control + force correlation at time of termination. This closes the loop from Phase 24a's political pressure model to war ending — historically, most wars end by negotiation, not annihilation.
- `escalation/war_termination.py` — War termination logic: when `P_int > ceasefire_threshold` for any side, evaluate willingness to negotiate based on: current territorial control vs objectives, force correlation trend (improving → less willing, declining → more willing), domestic political pressure, coalition partner pressure. Both sides must cross negotiation threshold simultaneously for ceasefire to trigger. Asymmetric termination: one side capitulates when desperation_index + political_pressure exceeds fight_on_threshold (unconditional surrender path).
- 4 validation scenarios:
  - `data/scenarios/halabja_1988.yaml` — Iraqi chemical escalation against Kurdish town. Validates: chemical employment decision logic (desperation-driven), CBRN dispersal/casualty effects (Phase 18), political consequence model.
  - `data/scenarios/srebrenica_1995.yaml` — Bosnian Serb protected zone violation. Validates: ROE failure under constraint, escalation to prohibited methods, command paralysis, political consequence surge.
  - `data/scenarios/eastern_front_1943.yaml` — German-Soviet mutual escalation (Kursk sector). Validates: escalation spiral dynamics, scorched earth, partisan warfare, existential threat suppression of domestic pressure.
  - `data/scenarios/coin_campaign.yaml` — Modern COIN composite scenario. Validates: IED campaign, insurgency recruitment pipeline, kinetic vs population-centric approach comparison, coalition ROE constraints.

**YAML data total**: ~10 prohibited weapons + ~12 unconventional + ~6 AI profiles/configs + 4 scenarios = **~32 new YAML data files**.

**Exit Criteria**: Escalation ladder transitions driven by desperation index and commander personality. Chemical weapon employment decision occurs at Level 5 when desperation exceeds commander threshold. Political pressure rises from war crimes/civilian casualties and modulates allied support + ROE. Consequence cascade produces own-force morale penalty + enemy hardening + civilian hostility increase. IED emplacement scales with population hostility. Guerrilla units execute hit-and-run doctrine. Insurgency recruitment pipeline responds to collateral damage (more collateral → more insurgents). COIN approach comparison shows kinetic approach produces short-term gains but long-term insurgency growth vs population-centric approach showing opposite. Prohibited weapon compliance check gates engagement. SOF operations produce disproportionate effects (HVT targeting → command chain disruption, sabotage → logistics degradation). Negotiated war termination triggers when political pressure + stalemate exceed thresholds on both sides. Ceasefire freezes combat while maintaining logistics/detection. All effects modulate existing systems (no parallel combat resolution). Backward compatible when `escalation_config: null`. No new dependencies. Deterministic replay verified.

---

## Deficit-to-Phase Mapping

Every item from `devlog/index.md` Post-MVP Refinement Index assigned to a phase:

| Deficit | Origin | Assigned Phase |
|---------|--------|---------------|
| Checkpoint pickle fragility | Phase 0 | Won't fix (use `get_state()`/`set_state()` JSON for cross-version portability) |
| ~~Track association nearest-neighbor gating~~ | Phase 3 | ~~11b~~ **Resolved** |
| Environment data threading | Phase 3 | Won't fix (DI pattern is correct; caller responsibility is intentional) |
| ~~Passive sonar bearing placeholder~~ | Phase 3 | ~~11b~~ **Resolved** |
| ~~Sensor FOV filtering~~ | Phase 3 | ~~11b~~ **Resolved** |
| ~~Single-scan detection (no dwell/integration)~~ | Phase 3 | ~~11b~~ **Resolved** |
| Test coverage gap (Phase 3) | Phase 3 | Won't fix (coverage adequate for implemented features) |
| ~~Ballistic drag simplified~~ | Phase 4 | ~~11a~~ **Resolved** |
| ~~DeMarre penetration (no obliquity/composite/reactive)~~ | Phase 4 | ~~11a~~ **Resolved** |
| HEAT penetration range-independent | Phase 4 | Won't fix (physically correct for shaped charges) |
| Submarine evasion simplified | Phase 4 | 12c |
| Mine trigger lacks ship signature | Phase 4 | 12c |
| Carrier ops deck management abstracted | Phase 4 | Deferred (future carrier ops expansion) |
| Morale Markov discrete-time | Phase 4 | 12d |
| PSYOP simplified effectiveness | Phase 4 | 12d |
| Naval damage control abstracted | Phase 4 | 12c |
| Air combat lacks energy-maneuverability | Phase 4 | 12c |
| ~~Environment→combat coupling partial~~ | Phase 4 | ~~11a~~ **Resolved** |
| No multi-hop C2 propagation | Phase 5 | 12a |
| No terrain-based comms LOS | Phase 5 | 12a |
| Simplified FSCL | Phase 5 | 12a |
| No ATO planning cycle | Phase 5 | 12a |
| No JTAC/FAC observer | Phase 5 | 12a |
| Messenger no terrain traversal | Phase 5 | Deferred (low impact) |
| No supply optimization solver | Phase 6 | 12b |
| No multi-echelon supply chain | Phase 6 | 12b |
| Simplified transport vulnerability | Phase 6 | 12b |
| Medical M/M/c approximate | Phase 6 | 12b |
| ~~Engineering times deterministic~~ | Phase 6 | ~~11c~~ **Resolved** |
| ~~No fuel gating on movement~~ | Phase 6 | ~~11c~~ **Resolved** |
| Blockade effectiveness simplified | Phase 6 | Deferred (low impact) |
| Captured supply flat 50% | Phase 6 | Deferred (low impact) |
| No local water procurement | Phase 6 | Deferred (low impact) |
| No ammunition production | Phase 6 | Deferred (low impact) |
| VLS non-reloadable-at-sea deferred | Phase 6 | Deferred (low impact) |
| 73 Easting exchange_ratio = inf | Phase 7 | 11a (fire rate limiting implemented; re-validate to check if blue takes losses) |
| ~~No fire rate limiting~~ | Phase 7 | ~~11a~~ **Resolved** |
| ~~Uniform target_size_modifier~~ | Phase 7 | ~~11a~~ **Resolved** |
| ~~No wave attack modeling~~ | Phase 7 | ~~11c~~ **Resolved** |
| Pre-scripted behavior only | Phase 7 | Resolved (Phase 8 added AI) |
| Falklands simplified | Phase 7 | Deferred (expand scenario in future) |
| Synthetic terrain | Phase 7 | 15 |
| No logistics in validation | Phase 7 | Deferred (short engagements don't need it) |
| No C2 propagation in validation | Phase 7 | Deferred (direct behavior adequate for engagement-level) |
| Simplified force compositions | Phase 7 | Deferred (expand OOB data over time) |
| Named doctrinal schools deferred | Phase 8 | 19 |
| COA wargaming analytical | Phase 8 | Deferred (Lanchester adequate for planning level) |
| No terrain-specific COA generation | Phase 8 | Deferred (terrain-aware COA is aspirational) |
| Implied task tables simplified | Phase 8 | Deferred (adequate for current scope) |
| No multi-echelon simultaneous planning | Phase 8 | Deferred (independent planning is realistic — commanders don't synchronize thought) |
| Estimates update periodically | Phase 8 | Deferred (periodic update adequate; reactive would be expensive) |
| Stratagems opportunity-evaluated | Phase 8 | Deferred (proactive stratagem planning is aspirational) |
| ~~Brigade decision hardcodes echelon_level=9~~ | Phase 8 | ~~11d~~ **Resolved** |
| No force aggregation/disaggregation | Phase 9 | 13a |
| Single-threaded simulation | Phase 9 | 13c |
| No auto-resolve | Phase 9 | 13a |
| Simplified strategic movement | Phase 9 | Deferred (operational pathfinding is future scope) |
| ~~Fixed reinforcement schedule~~ | Phase 9 | ~~11c~~ **Resolved** |
| No naval campaign management | Phase 9 | Deferred (expand with naval scenarios) |
| Synthetic terrain | Phase 9 | 15 |
| LOS cache per-tick only | Phase 9 | 13a |
| No weather evolution beyond WeatherEngine.step() | Phase 9 | Deferred (step() is adequate) |
| Viewshed vectorization deferred | Phase 9 | 13a |
| STRtree for infrastructure deferred | Phase 9 | 13a |
| ~~No fire rate limiting (Phase 10 inherited)~~ | Phase 10 | ~~11a~~ **Resolved** |
| ~~No wave attack modeling (Phase 10 inherited)~~ | Phase 10 | ~~11c~~ **Resolved** |
| ~~Campaign AI coarseness~~ | Phase 10 | ~~11d~~ **Resolved** |
| Simplified force compositions (Phase 10) | Phase 10 | Deferred |
| Synthetic terrain (Phase 10) | Phase 10 | 15 |
| ~~Fixed reinforcement schedule (Phase 10)~~ | Phase 10 | ~~11c~~ **Resolved** |
| No force aggregation/disaggregation (Phase 10) | Phase 10 | 13a |
| AI expectation matching approximate | Phase 10 | Deferred (adequate for validation) |
| Campaign metrics proxy territory | Phase 10 | Deferred (spatial control requires Phase 15 real terrain) |
| Fuel gating not wired to stockpile in battle.py | Phase 11 | 12b (logistics depth) |
| Wave assignments are manual (no AI auto-assignment) | Phase 11 | 19 (doctrinal AI) |
| Integration gain caps at 4 scans | Phase 11 | Deferred (conservative cap adequate) |
| Armor type YAML data missing | Phase 11 | Deferred (expand unit definitions over time) |

---

## Module-to-Phase Index (Post-MVP)

New modules introduced in Phases 11–24:

| Module | Phase |
|--------|-------|
| `population/civilians.py` | 12e |
| `population/displacement.py` | 12e |
| `population/collateral.py` | 12e |
| `population/humint.py` | 12e |
| `population/influence.py` | 12e |
| `core/numba_utils.py` | 13b |
| `tools/tempo_analysis.py` | 14b |
| `terrain/data_pipeline.py` | 15a |
| `terrain/real_heightmap.py` | 15a |
| `terrain/real_classification.py` | 15b |
| `terrain/real_infrastructure.py` | 15b |
| `terrain/real_bathymetry.py` | 15c |
| `terrain/trenches.py` | 21b |
| `ew/spectrum.py` | 16a |
| `ew/emitters.py` | 16a |
| `ew/jamming.py` | 16b |
| `ew/decoys_ew.py` | 16b |
| `ew/eccm.py` | 16c |
| `ew/sigint.py` | 16d |
| `space/orbits.py` | 17a |
| `space/constellations.py` | 17a |
| `space/events.py` | 17a |
| `space/gps.py` | 17b |
| `space/isr.py` | 17c |
| `space/early_warning.py` | 17c |
| `space/satcom.py` | 17d |
| `space/asat.py` | 17d |
| `cbrn/agents.py` | 18a |
| `cbrn/dispersal.py` | 18a |
| `cbrn/contamination.py` | 18b |
| `cbrn/protection.py` | 18b |
| `cbrn/casualties.py` | 18c |
| `cbrn/decontamination.py` | 18c |
| `cbrn/nuclear.py` | 18d |
| `c2/ai/schools/base.py` | 19a |
| `c2/ai/schools/clausewitzian.py` | 19b |
| `c2/ai/schools/maneuverist.py` | 19b |
| `c2/ai/schools/attrition.py` | 19b |
| `c2/ai/schools/airland_battle.py` | 19b |
| `c2/ai/schools/air_power.py` | 19b |
| `c2/ai/schools/sun_tzu.py` | 19c |
| `c2/ai/schools/deep_battle.py` | 19c |
| `c2/ai/schools/maritime.py` | 19d |
| `combat/naval_gunnery.py` | 20b |
| `combat/strategic_bombing.py` | 20b |
| `combat/volley_fire.py` | 22b |
| `combat/melee.py` | 22b |
| `combat/barrage.py` | 21b |
| `combat/gas_warfare.py` | 21b |
| `combat/siege.py` | 23b |
| `movement/convoy.py` | 20b |
| `movement/cavalry.py` | 22b |
| `movement/formation_napoleonic.py` | 22b |
| `movement/naval_oar.py` | 23b |
| `logistics/foraging.py` | 22b |
| `c2/courier.py` | 22b |
| `c2/visual_signals.py` | 23b |
| `tools/mcp_server.py` | 14a |
| `tools/mcp_resources.py` | 14a |
| `tools/sensitivity.py` | 14b |
| `tools/comparison.py` | 14b |
| `tools/narrative.py` | 14b |
| `tools/replay.py` | 14c |
| `tools/charts.py` | 14c |
| `c2/joint_ops.py` | 12a |
| `logistics/production.py` | 12b |
| `combat/iads.py` | 12f |
| `combat/air_campaign.py` | 12f |
| `combat/strategic_targeting.py` | 12f |
| `ew/spoofing.py` | 16b |
| `core/era.py` | 20a |
| `escalation/war_termination.py` | 24f |
| `escalation/ladder.py` | 24a |
| `escalation/political.py` | 24a |
| `escalation/consequences.py` | 24a |
| `escalation/events.py` | 24a |
| `combat/unconventional.py` | 24c |
| `c2/ai/sof_ops.py` | 24c |
| `population/insurgency.py` | 24e |

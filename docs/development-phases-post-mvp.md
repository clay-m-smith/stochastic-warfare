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

## Phase 12: Deep Systems Rework — **COMPLETE**
**Goal**: Fix MODERATE deficits requiring deeper refactoring — multi-hop C2, multi-echelon logistics, and enhanced domain models. Add civilian population and strategic air campaigns/IADS.

**Status**: Complete. 259 tests (30 + 53 + 22 + 66 + 41 + 47) across 6 test files. Total: 4,077 tests passing (up from 3,818). 12 new source files + ~25 modified. No new dependencies. All changes backward-compatible with default parameters preserving MVP behavior. Devlog: [`devlog/phase-12.md`](devlog/phase-12.md).

### 12d: Morale & Psychology Depth (2 changes, 30 tests)
- `morale/state.py` (modified) — Continuous-time Markov: `use_continuous_time` config flag, `compute_continuous_transition_probs()` using `P = 1 - exp(-λ·dt)`, `dt` parameter on `check_transition()`, `transition_cooldown_s` enforcement.
- `morale/psychology.py`, `morale/events.py` (modified) — Enhanced PSYOP: `apply_psyop_enhanced()` with message_type × susceptibility × delivery scoring. `PsyopAppliedEvent` published on EventBus.

### 12a: C2 Depth (9 changes, 53 tests)
- `c2/communications.py` (modified) — Multi-hop message propagation via hierarchy LCA, terrain-based comms LOS via LOSEngine, network degradation with congestion model.
- `c2/coordination.py` (modified) — Arbitrary polyline FSCL (Shapely LineString), JTAC/FAC observer with LOS + position error, JIPTL generation with greedy allocation.
- `c2/joint_ops.py` (new) — JointOpsEngine: service branch coordination modifiers (×1.5 delay, ×2.0 misinterpret cross-service), liaison reduction, coalition caveats.
- `detection/fog_of_war.py` (modified) — Network-centric COP: data link sharing of contact tracks with quality degradation.
- `c2/orders/air_orders.py` (modified) — ATOPlanningEngine: sortie allocation by priority (DCA/CAP → JIPTL → CAS).

### 12b: Logistics Depth (5 changes, 22 tests)
- `logistics/supply_network.py` (modified) — Multi-echelon supply with capacity constraints, infrastructure coupling, min-cost flow, alternate routing, route severing.
- `logistics/production.py` (new) — Supply regeneration: ProductionEngine with facility registration, infrastructure-coupled production rate.
- `logistics/transport.py` (modified) — Escort effects on convoy survival probability.
- `logistics/medical.py` (modified) — Erlang-k service distribution (k=1 default = exponential = MVP).
- `simulation/battle.py` (modified) — Fuel gating wired to stockpile_manager for Class III.

### 12c: Combat Depth (5 changes, 66 tests)
- `combat/air_combat.py` (modified) — Energy-maneuverability: EnergyState dataclass, specific_energy advantage modifying Pk.
- `combat/naval_surface.py` (modified) — Compartment flooding: progressive flooding through bulkheads, counter-flooding, capsize detection.
- `combat/naval_subsurface.py` (modified) — Geometric evasion (bearing rate + thermocline), patrol operations (area coverage + Poisson contacts).
- `combat/naval_mine.py` (modified) — Ship signature trigger matching, MCM sweep modes, mine persistence, minefield density.
- `combat/amphibious_assault.py` (modified) — Landing craft throughput, tidal window gating.

### 12e: Civilian Population & COIN (7 new files + 1 modified, 41 tests)
- `core/types.py` (modified) — Added `ModuleId.POPULATION` and `ModuleId.AIR_CAMPAIGN`.
- `population/__init__.py`, `population/events.py` (new) — Package init + 4 event dataclasses.
- `population/civilians.py` (new) — CivilianManager: regions, spatial disposition queries, displacement/collateral tracking.
- `population/displacement.py` (new) — DisplacementEngine: combat-driven displacement with transport penalty.
- `population/collateral.py` (new) — CollateralEngine: cumulative tracking with escalation threshold.
- `population/humint.py` (new) — CivilianHumintEngine: Poisson tip generation, disposition-dependent flow direction.
- `population/influence.py` (new) — InfluenceEngine: Markov chain disposition transitions (collateral/aid/psyop drivers).
- `c2/roe.py` (modified) — `evaluate_escalation()`: collateral threshold → automatic ROE tightening (FREE→TIGHT→HOLD).

### 12f: Strategic Air Campaigns & IADS (3 new files + 1 modified, 47 tests)
- `combat/iads.py` (new) — IadsEngine: IADS sectors with radar handoff chain, sector health (radar × SAM × command), SEAD degradation.
- `combat/air_campaign.py` (new) — AirCampaignEngine: sortie capacity, pilot fatigue, weather days, attrition/regeneration. CampaignPhase enum.
- `combat/strategic_targeting.py` (new) — StrategicTargetingEngine: TPL generation, strike cascading to infrastructure/supply, BDA with lognormal ×3 overestimate bias, target regeneration.
- `terrain/infrastructure.py` (modified) — HealthState enum, PowerPlant/Factory/Port/SupplyDepot models, `get_feature_condition()`, unified `_all_stores()` iteration.

**Exit Criteria**: All met. Multi-hop C2 propagates with accumulated delay/loss. COP shares contacts laterally. Joint ops coordination delays measurable. JIPTL allocates targets to shooters. Supply flows through echeloned network. Route severing triggers rerouting. Energy state affects air combat. IADS radar handoff + SEAD degradation functional. Strategic targeting cascades to infrastructure. Air campaign sortie rate constrained by availability/fatigue. BDA overestimates damage. Compartment flooding + capsize. Submarine patrol + geometric evasion. Mine signature matching + MCM. Landing craft throughput + tidal windows. Civilian collateral triggers ROE tightening. HUMINT from friendly population. Refugee displacement penalizes transport. All 4,077 tests pass. Deterministic replay verified.

---

## Phase 13: Performance Optimization — **COMPLETE**
**Goal**: Achieve 5x speedup on campaign-scale simulations through algorithmic optimization, compiled extensions, and parallelism.

**Status**: Complete (+ postmortem cleanup). 142 tests + 28 postmortem across 14 test files + 7 benchmark tests + 11 determinism tests. Total: 4,247 tests passing (up from 4,077). 2 new source files (`simulation/aggregation.py`, `core/numba_utils.py`) + ~10 modified source files. Optional `numba` dependency added (`uv sync --extra perf`). All changes backward-compatible with `enable_*` config flags. Postmortem wired aggregation engine into `SimulationContext` + engine strategic tick, and selective LOS invalidation into engine dirty-cell tracking. Devlog: [`devlog/phase-13.md`](devlog/phase-13.md).

### 13a: Algorithmic Optimization (7 sub-phases, 99 tests)
- `terrain/infrastructure.py` (modified) — STRtree spatial index for building/road/airfield queries. `roads_near()`, `nearest_road()`, `buildings_at()`, `buildings_near()`, `airfields_near()` rewritten to use `shapely.STRtree`. 14 tests.
- `terrain/los.py` (modified) — Multi-tick LOS cache: `invalidate_cells(dirty_cells)` selective invalidation based on grid-cell coordinates. 11 tests.
- `terrain/los.py` (modified) — Viewshed vectorization: `visible_area()` uses numpy broadcasting for distance filtering, skipping out-of-range cells. 8 tests.
- `detection/estimation.py` (modified) — Kalman F/Q matrix caching: `_cached_dt`, `_cached_F`, `_cached_Q` fields. Only recomputes on dt change. 6 tests.
- `simulation/battle.py` (modified) — Auto-resolve: `auto_resolve()` method with Lanchester attrition (10 steps, exponent 0.5, morale/supply factors). `AutoResolveResult` dataclass. `auto_resolve_enabled`/`auto_resolve_max_units` config. 17 tests.
- `simulation/aggregation.py` (new) — Force aggregation/disaggregation: `AggregationEngine` with `snapshot_unit()`, `aggregate()`, `disaggregate()`, `check_aggregation_candidates()`, `check_disaggregation_triggers()`, `get_state()`/`set_state()`. `UnitSnapshot`, `AggregateUnit`, `AggregationConfig` data structures. 27 tests.
- `simulation/engine.py` (modified) — Selective LOS cache invalidation wiring, auto-resolve integration. Postmortem: aggregation engine wired into strategic tick, `_compute_battle_positions()` + `_snapshot_unit_cells()` helpers, `enable_selective_los_invalidation` config flag, dirty-cell tracking around movement.
- `simulation/scenario.py` (modified, postmortem) — `aggregation_engine` field on `SimulationContext`, `get_state()`/`set_state()` support, `AggregationEngine` instantiation in `ScenarioLoader._create_engines()`.
- `tests/benchmarks/test_phase13_benchmarks.py` (new) — 7 baseline benchmark tests (spatial query, Kalman predict, LOS check, pathfinding, RK4 trajectory, MC, viewshed).

### 13b: Compiled Extensions (4 sub-phases, 42 tests)
- `core/numba_utils.py` (new) — `NUMBA_AVAILABLE` flag, `optional_jit` decorator with pure-Python fallback. 5 tests.
- `combat/ballistics.py` (modified) — `@optional_jit` on `_speed_of_sound()`, `_mach_drag_multiplier()`. New `_derivs_kernel()` and `_rk4_trajectory_kernel()` JIT functions. `compute_trajectory()` delegates to kernel. 18 tests.
- `terrain/los.py` (modified) — `@optional_jit` on `_los_terrain_kernel()` for DDA raycasting inner loop. `_check_los_terrain_jit()` method on LOSEngine. 8 tests.
- `movement/pathfinding.py` (modified) — `_compute_difficulty_grid()` pre-computes cell difficulty into numpy array. `find_path()` uses array lookup instead of per-cell dict cache. 11 tests.

**Also**: `pyproject.toml` — `perf = ["numba>=0.59"]` optional dependency group. `benchmark` marker excluded by default.

### 13c: Parallelism & Verification (2 sub-phases, 17 tests)
- `validation/monte_carlo.py` (modified) — `submit()` + `as_completed()` pattern replacing `executor.map()`. Results sorted by seed for deterministic ordering. 6 tests.
- `tests/benchmarks/test_phase13_determinism.py` (new) — 11 determinism verification tests: LOS cache selective vs full clear, Kalman cache, RK4 trajectory, aggregation round-trip, auto-resolve PRNG isolation, viewshed consistency.

**Exit Criteria**: All met. STRtree replaces brute-force spatial queries. Multi-tick LOS cache retains entries for stationary units. Viewshed uses vectorized distance filtering. Kalman F/Q matrices cached per dt. Auto-resolve available for minor battles. Force aggregation/disaggregation preserves all subsystem state. Numba JIT kernels for RK4 and DDA with pure-Python fallback. A* uses pre-computed difficulty grid. MC uses as_completed pattern. All results bit-for-bit deterministic (verified by 11 determinism tests). All 4,219 tests pass. Deterministic replay verified.

---

## Phase 14: Tooling & Developer Experience — **COMPLETE**
**Goal**: Build developer tools, analysis utilities, and MCP server for LLM-assisted simulation.

**Status**: Complete (+ postmortem). 125 tests across 7 test files. Total: 4,372 tests passing. 12 new source files + 7 skill files. Optional dependency: `mcp[cli]>=1.2.0` (via `--extra mcp`). Devlog: [`devlog/phase-14.md`](devlog/phase-14.md).

### 14a: MCP Server (36 tests)
- `tools/__init__.py` — Package init
- `tools/serializers.py` — JSON serialization for simulation objects (numpy, datetime, enum, Position, inf/nan, dataclasses, pydantic models)
- `tools/result_store.py` — In-memory LRU cache (max 20) for cross-tool result referencing
- `tools/mcp_server.py` — FastMCP server with 7 tools: `run_scenario`, `query_state`, `run_monte_carlo`, `compare_results`, `list_scenarios`, `list_units`, `modify_parameter`. stdio transport. `asyncio.to_thread()` for blocking sim calls.
- `tools/mcp_resources.py` — 3 resource providers: `scenario://{name}/config`, `unit://{category}/{type}`, `result://{run_id}`

### 14b: Analysis Tools (63 tests)
- `tools/narrative.py` — Registry-based template system (~15 formatters), `generate_narrative()` with side/type/tick filtering, `format_narrative()` with full/summary/timeline styles
- `tools/tempo_analysis.py` — FFT spectral analysis of event frequency by 5 categories (Combat, Detection, C2, Morale, Movement), OODA cycle timing extraction, 3-panel plot
- `tools/comparison.py` — A/B statistical comparison with Mann-Whitney U test, rank-biserial effect size, formatted table output
- `tools/sensitivity.py` — Parameter sweep with same seed sequence per point, errorbar plot output
- `tools/_run_helpers.py` — Shared batch runner (temp YAML pattern from CampaignRunner)

### 14c: Visualization (26 tests)
- `tools/charts.py` — 6 chart functions: `force_strength_chart`, `engagement_network`, `supply_flow_diagram`, `engagement_timeline`, `morale_progression`, `mc_distribution_grid`
- `tools/replay.py` — Animated battle replay via FuncAnimation: `extract_replay_frames`, `create_replay` (side-colored scatter, engagement lines, destroyed markers), `save_replay` (GIF/MP4)

### 14d: Claude Skills (7 new skills)
- `/scenario` — Interactive scenario creation/editing walkthrough
- `/compare` — Run two configs and summarize with statistical interpretation
- `/what-if` — Quick parameter sensitivity from natural language questions
- `/timeline` — Generate narrative from simulation run
- `/orbat` — Interactive order of battle builder
- `/calibrate` — Auto-tune calibration overrides to match historical metrics
- `/postmortem` — Structured phase retrospective (8-step process: scope, integration, tests, API, deficits, docs, perf, summary)

**Exit Criteria**: MCP server responds to all tool calls with correct results. Sensitivity analysis produces parameter sweep plots. A/B comparison returns p-values. Battle replay animation renders 73 Easting. All new skills functional. No regression in existing tests.

---

## Phase 15: Real-World Terrain & Data Pipeline — **COMPLETE**
**Goal**: Import real-world elevation, land cover, infrastructure, and bathymetry data for scenario creation on actual geography.

**Status**: Complete. 91 tests across 4 test files. Total: 4,463 tests passing (up from 4,372). 5 new source files + 1 modified + 1 download script. Optional dependencies: `rasterio>=1.3`, `xarray>=2024.1` (via `--extra terrain`). All changes backward-compatible — `terrain_source` defaults to `"procedural"`. Devlog: [`devlog/phase-15.md`](devlog/phase-15.md).

### 15a: Elevation Pipeline (35 tests)
- `terrain/data_pipeline.py` (new) — `BoundingBox`/`TerrainDataConfig` pydantic models, `srtm_tiles_for_bbox()`, deterministic cache key (SHA-256), mtime-based cache validation, `check_data_available()`, `load_real_terrain()` unified entry point, `RealTerrainContext` dataclass.
- `terrain/real_heightmap.py` (new) — SRTM .hgt raw reader (int16 big-endian), GeoTIFF reader (rasterio), multi-tile merge, no-data fill (median/nearest/zero with threshold), bbox cropping, geodetic→ENU bilinear interpolation, `load_srtm_heightmap()` producing standard `Heightmap`.

### 15b: Classification & Infrastructure (29 tests)
- `terrain/real_classification.py` (new) — 23-entry Copernicus→LandCover mapping, 15-entry LandCover→SoilType derivation, window-read + nearest-neighbor resample, `load_copernicus_classification()` producing standard `TerrainClassification`.
- `terrain/real_infrastructure.py` (new) — GeoJSON input (no C++ toolchain needed), 18-entry highway→RoadType mapping, road/bridge/building/railway extraction, geodetic→ENU coordinate conversion, `load_osm_infrastructure()` producing standard `InfrastructureManager`.

### 15c: Maritime Data (12 tests)
- `terrain/real_bathymetry.py` (new) — GEBCO NetCDF reader (xarray), elevation negation (positive-up → positive-depth), land cell clamping, depth→BottomType heuristic (SAND/GRAVEL/MUD/CLAY by depth), vectorized classification, bilinear resample, `load_gebco_bathymetry()` producing standard `Bathymetry`.

### 15d: Integration (15 tests)
- `simulation/scenario.py` (modified) — `TerrainConfig` + `terrain_source`/`data_dir`/`cache_dir` fields, `_build_real_terrain()` dispatch, bbox computation from lat/lon + width/height, `SimulationContext` + `classification`/`infrastructure_manager`/`bathymetry` optional fields.
- `scripts/download_terrain.py` (new) — CLI script: SRTM tile download instructions, Copernicus instructions, OSM Overpass API→GeoJSON, GEBCO instructions.

**Also**: `pyproject.toml` — `terrain = ["rasterio>=1.3", "xarray>=2024.1"]` optional dependency group. `terrain` marker excluded by default in `addopts`.

**Exit Criteria**: All met. Synthetic GeoTIFF/HGT/GeoJSON/NetCDF load correctly into standard terrain objects. Downstream code (LOS, movement, combat, logistics) works unchanged. Cache roundtrip verified. Fallback to procedural when `terrain_source="procedural"` (default). Deterministic replay verified. All 4,463 tests pass.

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
| ~~Submarine evasion simplified~~ | Phase 4 | ~~12c~~ **Resolved** |
| ~~Mine trigger lacks ship signature~~ | Phase 4 | ~~12c~~ **Resolved** |
| Carrier ops deck management abstracted | Phase 4 | Deferred (future carrier ops expansion) |
| ~~Morale Markov discrete-time~~ | Phase 4 | ~~12d~~ **Resolved** |
| ~~PSYOP simplified effectiveness~~ | Phase 4 | ~~12d~~ **Resolved** |
| ~~Naval damage control abstracted~~ | Phase 4 | ~~12c~~ **Resolved** |
| ~~Air combat lacks energy-maneuverability~~ | Phase 4 | ~~12c~~ **Resolved** |
| ~~Environment→combat coupling partial~~ | Phase 4 | ~~11a~~ **Resolved** |
| ~~No multi-hop C2 propagation~~ | Phase 5 | ~~12a~~ **Resolved** |
| ~~No terrain-based comms LOS~~ | Phase 5 | ~~12a~~ **Resolved** |
| ~~Simplified FSCL~~ | Phase 5 | ~~12a~~ **Resolved** |
| ~~No ATO planning cycle~~ | Phase 5 | ~~12a~~ **Resolved** |
| ~~No JTAC/FAC observer~~ | Phase 5 | ~~12a~~ **Resolved** |
| Messenger no terrain traversal | Phase 5 | Deferred (low impact) |
| ~~No supply optimization solver~~ | Phase 6 | ~~12b~~ **Resolved** |
| ~~No multi-echelon supply chain~~ | Phase 6 | ~~12b~~ **Resolved** |
| ~~Simplified transport vulnerability~~ | Phase 6 | ~~12b~~ **Resolved** |
| ~~Medical M/M/c approximate~~ | Phase 6 | ~~12b~~ **Resolved** |
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
| ~~No force aggregation/disaggregation~~ | Phase 9 | ~~13a~~ **Resolved** (postmortem wired into engine) |
| Single-threaded simulation | Phase 9 | 13c |
| ~~No auto-resolve~~ | Phase 9 | ~~13a~~ **Resolved** (13a-6) |
| Simplified strategic movement | Phase 9 | Deferred (operational pathfinding is future scope) |
| ~~Fixed reinforcement schedule~~ | Phase 9 | ~~11c~~ **Resolved** |
| No naval campaign management | Phase 9 | Deferred (expand with naval scenarios) |
| Synthetic terrain | Phase 9 | 15 |
| ~~LOS cache per-tick only~~ | Phase 9 | ~~13a~~ **Resolved** (postmortem wired selective invalidation) |
| No weather evolution beyond WeatherEngine.step() | Phase 9 | Deferred (step() is adequate) |
| ~~Viewshed vectorization deferred~~ | Phase 9 | ~~13a~~ **Resolved** (13a-5) |
| ~~STRtree for infrastructure deferred~~ | Phase 9 | ~~13a~~ **Resolved** (13a-2) |
| ~~No fire rate limiting (Phase 10 inherited)~~ | Phase 10 | ~~11a~~ **Resolved** |
| ~~No wave attack modeling (Phase 10 inherited)~~ | Phase 10 | ~~11c~~ **Resolved** |
| ~~Campaign AI coarseness~~ | Phase 10 | ~~11d~~ **Resolved** |
| Simplified force compositions (Phase 10) | Phase 10 | Deferred |
| Synthetic terrain (Phase 10) | Phase 10 | 15 |
| ~~Fixed reinforcement schedule (Phase 10)~~ | Phase 10 | ~~11c~~ **Resolved** |
| ~~No force aggregation/disaggregation (Phase 10)~~ | Phase 10 | ~~13a~~ **Resolved** (postmortem wired into engine) |
| AI expectation matching approximate | Phase 10 | Deferred (adequate for validation) |
| Campaign metrics proxy territory | Phase 10 | Deferred (spatial control requires Phase 15 real terrain) |
| ~~Fuel gating not wired to stockpile in battle.py~~ | Phase 11 | ~~12b~~ **Resolved** |
| Wave assignments are manual (no AI auto-assignment) | Phase 11 | 19 (doctrinal AI) |
| Integration gain caps at 4 scans | Phase 11 | Deferred (conservative cap adequate) |
| Armor type YAML data missing | Phase 11 | Deferred (expand unit definitions over time) |

---

## Module-to-Phase Index (Post-MVP)

New modules introduced in Phases 11–24:

| Module | Phase |
|--------|-------|
| `population/__init__.py` | 12e |
| `population/events.py` | 12e |
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
| `tools/__init__.py` | 14a |
| `tools/serializers.py` | 14a |
| `tools/result_store.py` | 14a |
| `tools/mcp_server.py` | 14a |
| `tools/mcp_resources.py` | 14a |
| `tools/narrative.py` | 14b |
| `tools/tempo_analysis.py` | 14b |
| `tools/comparison.py` | 14b |
| `tools/sensitivity.py` | 14b |
| `tools/_run_helpers.py` | 14b |
| `tools/charts.py` | 14c |
| `tools/replay.py` | 14c |
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

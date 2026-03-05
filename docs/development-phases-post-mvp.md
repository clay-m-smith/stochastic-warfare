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

## Phase 16: Electronic Warfare — **COMPLETE**
**Goal**: Full EW domain — jamming, ECCM, SIGINT, electronic decoys — modulating existing detection and C2 systems.

**Status**: Complete. 144 tests (22 + 40 + 20 + 25 + 13 + 24) across 6 test files + 1 existing test modified. Total: 4,614 tests passing (up from 4,469). 8 new source files + 5 modified + 14 YAML data files + 2 scenario packs. No new dependencies. All changes backward-compatible with `enable_ew` config flags (default False) and default parameter values (0.0/5.0). Postmortem fixed EMEnvironment checkpoint bug and 4 test quality issues. Devlog: [`devlog/phase-16.md`](devlog/phase-16.md).

### 16a: Spectrum & Emitters (3 new files, 22 tests)
- `ew/__init__.py` (new) — Package init
- `ew/events.py` (new) — 7 EW event types (jamming, spoofing, intercept, decoy, ECCM, emitter, spectrum)
- `ew/spectrum.py` (new) — EM spectrum manager: frequency allocation, conflict detection, bandwidth overlap
- `ew/emitters.py` (new) — Emitter registry: all active emitters with type/freq/side queries

### 16b: Electronic Attack (3 new files, 40 tests)
- `ew/jamming.py` (new) — J/S ratio calculation, burn-through range, radar SNR penalty, comms jam factor. Schleher/Adamy physics. Stand-off and self-screening jamming geometry.
- `ew/spoofing.py` (new) — GPS spoofing zones, configurable position offset, INS cross-check detection, PGM offset. Receiver-type resistance (civilian/P-code/M-code).
- `ew/decoys_ew.py` (new) — Chaff/flare/towed decoy/DRFM deployment, missile diversion probability, degradation over time.

### 16c: Electronic Protection (1 new file, 20 tests)
- `ew/eccm.py` (new) — 4 ECCM technique types: frequency hopping (bandwidth ratio reduction), spread spectrum (processing gain), sidelobe blanking, adaptive nulling. Additive dB reduction model.

### 16d: Electronic Support (1 new file, 25 tests)
- `ew/sigint.py` (new) — Intercept probability from receiver sensitivity/bandwidth overlap/emitter power. AOA geolocation with Cramer-Rao bound. TDOA geolocation. Traffic analysis.

### 16e: Integration (5 modified files, 12 tests)
- `detection/detection.py` (modified) — Added `jam_snr_penalty_db` parameter for EW jamming integration.
- `environment/electromagnetic.py` (modified) — Added GPS degradation hooks for spoofing/jamming.
- `combat/air_ground.py` (modified) — Added `gps_accuracy_m` parameter to weapon delivery for PGM degradation.
- `simulation/scenario.py` (modified) — Added `ew_engine` field to `SimulationContext`.
- `core/types.py` (modified) — Added `ModuleId.EW` enum value.

### 16f: Validation (14 YAML data files + 2 scenarios, 24 tests)
- **Jammer YAMLs** (6 files): AN/ALQ-99, AN/TLQ-32, Krasukha-4, AN/SLQ-32, AN/ALQ-131, R-330Zh
- **ECCM suite YAMLs** (4 files): US fighter, US destroyer, Soviet SAM, Patriot
- **SIGINT collector YAMLs** (2 files): RC-135, ground station
- **Validation scenarios** (2 packs): Bekaa Valley 1982 (Israeli SEAD vs Syrian SAM network), Gulf War EW 1991 (Coalition EW campaign vs Iraqi IADS)

**GPS jamming note**: Phase 16 implements GPS jamming by degrading the static `gps_accuracy` parameter in `environment/electromagnetic.py`. The `JammingEngine.compute_comms_jam_factor()` method computes comms jamming effects but wiring into `c2/communications.py` is deferred to the engine integration step. Phase 17 (Space) later replaces the static GPS parameter with dynamic orbital-driven values. The EW jamming mechanism remains the same — it modulates whatever the current GPS accuracy source provides (static in Phase 16, orbital in Phase 17+).

**Exit Criteria**: All met. Jamming reduces radar detection range by calculated J/S ratio. ECCM (frequency hopping) partially restores detection. SIGINT geolocates active emitters within accuracy bounds. Comms jamming increases message loss rate. EW decoys divert incoming missiles. GPS jamming degrades PGM accuracy via `gps_accuracy` parameter. GPS spoofing introduces systematic position error distinct from jamming noise — spoofed PGMs miss by offset vector, not random scatter. Military receivers (M-code) resist spoofing better than civilian. Bekaa Valley scenario produces Israeli air superiority when EW employed vs high losses without. All effects feed through existing parameters (no parallel combat system). Deterministic replay verified. All 4,469 existing tests unaffected.

---

## Phase 17: Space & Satellite Domain — **COMPLETE**
**Goal**: Model space-based assets (GPS, SATCOM, ISR, early warning) as force multipliers that modulate existing systems, and anti-satellite warfare that degrades them.

**Status**: Complete. 149 tests across 6 test files + 1 existing test modified. Total: 4,763 tests passing (up from 4,614). 9 new source files + 7 modified + 12 YAML data files + 3 validation scenarios. No new dependencies. All changes backward-compatible with `enable_space` config flag (default False) and default parameter values. Devlog: [`devlog/phase-17.md`](devlog/phase-17.md).

**Prerequisite**: Depends on environment/electromagnetic.py (gps_accuracy), c2/communications.py (SATCOM), detection/intel_fusion.py (IMINT), combat/missiles.py (CEP/guidance). All exist. EW (Phase 16) provides GPS/SATCOM jamming via the static `gps_accuracy` parameter — Phase 17 replaces that static value with a dynamic orbital-driven model. EW jamming mechanism is unchanged (it modulates whatever GPS accuracy source exists). Phase 17 works without Phase 16 via manual degradation inputs.

### 17a: Orbital Mechanics & Constellation Management (3 new files)
- `space/__init__.py` (new) — Package init
- `space/events.py` (new) — Space domain events: SatelliteOverpassEvent, GPSDegradedEvent, SATCOMWindowEvent, ASATEngagementEvent, ConstellationDegradedEvent
- `space/orbits.py` (new) — Simplified Keplerian orbit propagation: period `T = 2pi*sqrt(a^3/mu)`, ground track computation via rotation + inclination, J2 nodal precession for sun-synchronous orbits. Kepler equation solver (Newton-Raphson). NOT full SGP4/TLE — sufficient for campaign-scale "when does satellite see theater?"
- `space/constellations.py` (new) — Constellation manager: define satellite groups (GPS 24-slot MEO, GLONASS 24-slot MEO, imaging LEO, SIGINT LEO/HEO, early warning GEO/HEO, SATCOM GEO). Compute coverage windows over theater bounding box. Track constellation health (degraded satellite count). EventBus integration for constellation state changes.

### 17b: GPS Dependency & Navigation Warfare (1 new file)
- `space/gps.py` (new) — GPS accuracy model: visible satellite count over theater → DOP (dilution of precision) → position error `sigma = DOP * sigma_range`. INS drift model for GPS-denied: `sigma(t) = sigma_0 + drift_rate * t`. Wired into `environment/electromagnetic.py` gps_accuracy parameter and `combat/missiles.py` CEP for GPS-guided munitions. JDAM-class weapons degrade from ~13m CEP (GPS) to ~30m+ (INS-only).

### 17c: Space-Based ISR & Early Warning (2 new files)
- `space/isr.py` (new) — Space-based ISR: imaging satellites generate detection events during overpass windows. Resolution determines minimum detectable unit size (vehicle vs battalion). Revisit time from orbital period + ground track drift. Cloud cover blocks optical satellites (not SAR).
- `space/early_warning.py` (new) — Missile early warning: GEO/HEO IR satellites detect missile launches (IR bloom). Detection time = coverage check + processing delay (30-90s). Wired into `combat/missile_defense.py` early warning time parameter. No coverage = no early warning (fall back to ground radar with shorter range).

### 17d: SATCOM Dependency & Anti-Satellite Warfare (2 new files)
- `space/satcom.py` (new) — SATCOM dependency model: satellite coverage windows determine SATCOM availability for beyond-LOS communications. Bandwidth capacity limits per theater. Degradation feeds into `c2/communications.py` reliability for SATCOM-type equipment. No coverage window = SATCOM unavailable.
- `space/asat.py` (new) — Anti-satellite warfare: direct-ascent kinetic kill vehicle (Pk from intercept geometry), ground-based laser dazzling (temporary blinding) and laser destruct (permanent). Debris generation: each kinetic kill produces N fragments (Poisson), each with per-orbit collision probability for satellites at similar altitude (Kessler cascade risk). Satellite loss → constellation degradation → cascading effects on GPS accuracy, ISR coverage, SATCOM availability, and early warning.

### 17e: Integration (7 modified files)
- `core/types.py` (modified) — Added `ModuleId.SPACE` enum value
- `environment/electromagnetic.py` (modified) — Added `constellation_accuracy_m` for dynamic GPS accuracy from orbital model
- `combat/missile_defense.py` (modified) — Added `early_warning_time_s` parameter for space-based early warning
- `combat/missiles.py` (modified) — Added `gps_accuracy_m` parameter for GPS-guided weapon CEP scaling
- `c2/communications.py` (modified) — Added `satcom_reliability_factor` for SATCOM availability modulation
- `simulation/scenario.py` (modified) — Added `space_engine` field to SimulationContext
- `simulation/engine.py` (modified) — Added `space_engine.update()` call in simulation tick loop

### 17f: YAML Data & Validation Scenarios
- **Constellation YAMLs** (9 files): GPS NAVSTAR, GLONASS, Milstar SATCOM, WGS SATCOM, Keyhole optical, Lacrosse SAR, SBIRS early warning, Molniya early warning, SIGINT LEO
- **ASAT weapon YAMLs** (3 files): SM-3 Block IIA, Nudol ASAT, ground-based laser
- **Validation scenarios** (3 packs): space_gps_denial (PGM accuracy: full GPS vs degraded vs denied), space_isr_gap (exploit imaging satellite gap), space_asat_escalation (kinetic ASAT cascading DOP increase)

**Exit Criteria**: All met. GPS denial increases PGM CEP by correct factor (~2-3x for partial, ~10x for full denial). Satellite overpass timing matches simplified Keplerian prediction within +/-5min. SATCOM unavailability degrades comms reliability for SATCOM-dependent units. ASAT engagement produces constellation degradation with correct cascading effects. ISR satellites generate detection events during overpass windows only. All effects feed through existing parameters (no parallel systems). Backward compatible when `enable_space = False`. No new dependencies. Deterministic replay verified.

---

## Phase 18: NBC/CBRN Effects — **COMPLETE**
**Goal**: Chemical, biological, radiological, and nuclear effects — contamination, protection, casualties, decontamination.

**Status**: Complete. 155 tests (28+32+25+30+18+22) across 6 test files. Total: 4,918 tests passing (up from 4,763). 10 new source files in `cbrn/` + 6 modified existing files + 15 YAML data files + 2 validation scenarios. No new dependencies. All effects backward-compatible via `enable_cbrn` flag and default parameter values. Devlog: [`devlog/phase-18.md`](devlog/phase-18.md).

**Prerequisite**: Depends on environment/weather.py (wind for dispersal) and morale/stress.py (CBRN stress). Both exist.

### 18a: Agent Definitions & Dispersal (28 tests)
- `cbrn/__init__.py` (new) — Package init
- `cbrn/events.py` (new) — CBRN event types (contamination, exposure, decontamination, nuclear detonation, MOPP change, casualty)
- `cbrn/agents.py` (new) — Agent type definitions: nerve, blister, choking, blood, biological, radiological. Per-agent: persistence, lethality (LCt50/LD50), detection threshold, decon difficulty. YAML-driven with pydantic validation.
- `cbrn/dispersal.py` (new) — Gaussian puff/plume atmospheric dispersion. Pasquill-Gifford stability classes from weather state. Wind advection, turbulent diffusion. Terrain channeling (valleys concentrate, ridges deflect).

### 18b: Contamination & Protection (32 tests)
- `cbrn/contamination.py` (new) — Grid overlay: concentration per cell per agent, decay over time. Weather-dependent evaporation (temperature, wind), washout (rain). Terrain absorption (soil type from classification.py).
- `cbrn/protection.py` (new) — MOPP levels 0–4: movement penalty (0%/5%/10%/20%/30%), detection penalty (0%/0%/10%/20%/30%), fatigue multiplier (1.0/1.1/1.2/1.4/1.6), heat stress in warm weather. Equipment effectiveness vs agent type.

### 18c: Casualties & Decontamination (25 tests)
- `cbrn/casualties.py` (new) — Dose-response: dosage = Σ(concentration × exposure_time). Probit model for incapacitation and lethality. Feeds into medical pipeline.
- `cbrn/decontamination.py` (new) — Decon operations: hasty (5min, 60% effective), deliberate (30min, 95%), thorough (2hr, 99%). Equipment requirements. Generates contaminated waste.

### 18d: Nuclear Effects (30 tests)
- `cbrn/nuclear.py` (new) — Blast: overpressure from Hopkinson-Cranz scaling `ΔP = f(R/W^(1/3))`. Thermal radiation: burn radius by yield. Initial nuclear radiation: rem dosage by range. EMP: disables unshielded electronics in radius. Fallout: wind-driven plume using dispersal.py. Terrain modification (craters).

### 18e: Engine Integration (18 tests)
- `cbrn/engine.py` (new) — CBRNEngine orchestrator: per-tick dispersal update, contamination decay, exposure tracking, MOPP management
- `core/types.py` (modified) — Added `ModuleId.CBRN`
- `simulation/scenario.py` (modified) — Added `cbrn_engine` to SimulationContext
- `simulation/engine.py` (modified) — Added CBRN tick processing
- `movement/engine.py` (modified) — Added `mopp_speed_factor` for MOPP movement degradation
- `morale/state.py` (modified) — Added `cbrn_stress` modifier for CBRN morale effects

### 18f: Validation (22 tests)
- `data/scenarios/cbrn_chemical_defense.yaml` — Chemical attack on a defended position. Validates dispersal, MOPP response, casualty generation, terrain denial.
- `data/scenarios/cbrn_nuclear_tactical.yaml` — Tactical nuclear weapon against a massed formation. Validates blast radii, EMP, fallout plume.

**YAML data** (15 files): 7 agent definitions (VX, sarin, mustard, chlorine, hydrogen_cyanide, anthrax, cs137), 3 nuclear weapon definitions (10kT, 100kT, 1MT), 3 delivery system definitions (artillery shell, aerial bomb, SCUD warhead), 2 validation scenarios.

**Key features**: Pasquill-Gifford atmospheric dispersal, contamination grid overlay, MOPP levels with speed/detection/fatigue degradation, probit dose-response casualties, 3-tier decontamination, Hopkinson-Cranz nuclear blast, thermal fluence, initial radiation, EMP, fallout plumes, terrain modification (craters). All effects backward-compatible via `enable_cbrn` flag and default parameter values. Deterministic replay from seed.

**Exit Criteria**: Chemical strike creates contamination zone that persists and drifts with wind. Units in zone take casualties based on protection level. MOPP-4 reduces combat effectiveness to ~60%. Decontamination clears zones over time. Nuclear blast produces correct casualty radii for given yield. Chemical defense scenario produces historically plausible casualty rates. All effects feed through existing damage, morale, and movement systems. Deterministic replay verified.

---

## Phase 19: Doctrinal AI Schools — **COMPLETE**
**Goal**: Named doctrinal schools enabling comparative analysis of different warfare philosophies.

**Status**: Complete. 189 tests (35+65+31+15+18+25) across 6 test files. Total: 5,107 tests passing (up from 4,918). 10 new source files in `c2/ai/schools/` + 3 modified existing files + 9 YAML data files. No new dependencies. All changes backward-compatible via `None` default parameters. Devlog: [`devlog/phase-19.md`](devlog/phase-19.md).

**Prerequisite**: Depends on Phase 8 AI infrastructure (OODA, commander, doctrine, assessment, decisions, adaptation, stratagems). All exist.

### 19a: School Framework (35 tests)
- `c2/ai/schools/__init__.py` (new) — Package init, `SchoolRegistry` (register/get/assign_to_unit/get_for_unit/get_state/set_state), `SchoolLoader` (YAML loader following DoctrineTemplateLoader pattern)
- `c2/ai/schools/base.py` (new) — `SchoolDefinition` pydantic model (assessment_weight_overrides, preferred/avoided_actions, ooda_multiplier, coa_score_weight_overrides, risk_tolerance, stratagem_affinity, opponent_modeling_enabled/weight), `DoctrinalSchool` ABC with 8 hooks (get_assessment_weight_overrides, get_decision_score_adjustments, get_ooda_multiplier, get_coa_score_weight_overrides, get_risk_tolerance_override, get_stratagem_affinity, predict_opponent_action, adjust_scores_for_opponent)
- `c2/ai/assessment.py` (modified) — Added `weight_overrides: dict[str, float] | None = None` parameter to `assess()`, multiplicative weight application with re-normalization. Added `predict_opponent_action_lanchester()` standalone function for force-ratio-based opponent action prediction.
- `c2/ai/decisions.py` (modified) — Added `school_adjustments: dict[str, float] | None = None` parameter threaded through `decide()`, all 5 `_decide_*()` methods, and `_select_best()`. Applied between doctrine filtering and noise injection.
- `c2/ai/commander.py` (modified) — Added `school_id: str | None = None` field to `CommanderPersonality`.

### 19b: Western Schools (65 tests)
- `c2/ai/schools/clausewitzian.py` (new) — Center-of-gravity targeting, decisive engagement seeking (force_ratio > 1.5 → +0.15 ATTACK/MAIN_ATTACK/ENVELOP), culmination awareness (low supply/morale → CONSOLIDATE/DEFEND)
- `c2/ai/schools/maneuverist.py` (new) — Tempo-driven OODA acceleration (×0.7 stacking with Phase 11d tactical_mult), bypass strongpoints (+0.15 FLANK/BYPASS/EXPLOIT/PURSUE), penalizes frontal assault at unfavorable ratios
- `c2/ai/schools/attrition.py` (new) — Exchange ratio optimization, fire superiority preference (force_ratio > 1.5 → ATTACK; else DEFEND/SUPPORT_BY_FIRE), ooda_multiplier=1.2, risk_tolerance=low
- `c2/ai/schools/airland_battle.py` (new) — Echelon-dependent behavior (corps+ → DEEP_STRIKE/OPERATIONAL_MANEUVER; brigade/div → ATTACK/COUNTERATTACK), sensor-to-shooter emphasis (high intel → EXPLOIT)
- `c2/ai/schools/air_power.py` (new) — Five Rings strategic targeting (corps+ → DEEP_STRIKE, penalty to MAIN_ATTACK; brigade/div → DEFEND/DELAY until air superiority), intel weight 2.0×

### 19c: Eastern & Historical Schools (31 tests)
- `c2/ai/schools/sun_tzu.py` (new) — Intel-first assessment (3× intel weight), opponent modeling via `predict_opponent_action_lanchester()`, counter-posture scoring (opponent ATTACK → favor AMBUSH/FLANK, opponent DEFEND → favor BYPASS), low intel → strong RECON bonus, deception/surprise stratagem affinity
- `c2/ai/schools/deep_battle.py` (new) — Echeloned assault (high ratio → ATTACK/EXPLOIT, moderate → RESERVE for exploitation echelon), corps+ deep strikes (DEEP_STRIKE/OPERATIONAL_MANEUVER), ooda_multiplier=1.1

### 19d: Maritime Schools (15 tests)
- `c2/ai/schools/maritime.py` (new) — `MahanianSchool` (fleet concentration, decisive naval battle: force_ratio > 1.0 → +0.15 ATTACK/MAIN_ATTACK, always penalizes BYPASS) and `CorbettianSchool` (fleet-in-being, sea denial: avoids decisive battle unless overwhelming force_ratio ≥ 2.5, favors DEFEND/DELAY)

### 19e: Integration (18 tests)
- `simulation/scenario.py` (modified) — Added `school_registry: Any = None` to `SimulationContext`, included in `get_state()`/`set_state()`
- `simulation/battle.py` (modified) — Wired schools into `_process_ooda_completions()`: weight_overrides on OBSERVE, school_adjustments + opponent modeling on DECIDE, OODA multiplier stacking on phase start
- `c2/planning/coa.py` (modified) — Added `score_weight_overrides: dict[str, float] | None = None` to `compare_coas()`

### 19f: YAML Data & Validation (25 tests)
- **School YAMLs** (9 files): clausewitzian, maneuverist, attrition, airland_battle, air_power, sun_tzu, deep_battle, maritime_mahanian, maritime_corbettian
- Parametrized YAML loading tests, behavioral differentiation tests (same assessment → different school actions), determinism verification, backward compatibility, opponent modeling end-to-end, COA weight distribution comparison

**Key design decisions**: Schools produce modifier dicts consumed by existing engines via optional parameters (same DI pattern as `mopp_speed_factor`, `jam_snr_penalty_db`, `gps_accuracy_m`). YAML stores numeric constants; Python subclasses add conditional logic. `SchoolRegistry` stores unit→school assignments (avoids dependency on unwired `CommanderEngine`). Opponent modeling is lightweight one-step Lanchester lookahead (Sun Tzu only). OODA stacking: `effective_mult = tactical_acceleration × school.get_ooda_multiplier()`. Assessment weight overrides are multiplicative then re-normalized to sum=1.0.

**Exit Criteria**: All met. Each school produces measurably different behavior — Clausewitzian concentrates force, Sun Tzu emphasizes recon/deception with opponent modeling, Maneuverist achieves faster OODA (0.7× multiplier), Attrition seeks favorable exchange ratios, Deep Battle echelons attacks with reserve management, AirLand Battle synchronizes deep/close by echelon, Air Power prioritizes air superiority, Mahanian concentrates fleet, Corbettian preserves fleet-in-being. All schools produce valid outcomes. All 5,107 tests pass. Deterministic replay verified.

---

## Phase 20: WW2 Era — **COMPLETE**
**Goal**: World War 2 data package + engine extensions for pre-guided-munition, radar-emerging, propeller-aircraft warfare. Also establishes the **era framework** used by all subsequent era phases.

**Status**: Complete. 137 tests across 4 sub-phases. Total: 5,244 tests passing (up from 5,107). 4 new source files + 3 modified existing files + ~60 YAML data files. No new dependencies. All changes backward-compatible — `era: modern` is default and matches all existing behavior. Devlog: [`devlog/phase-20.md`](devlog/phase-20.md).

### 20a: Era Framework & Unit Data
- `core/era.py` (new) — Era configuration system: `EraConfig` defining which simulation subsystems are active/inactive per era. Era enum (MODERN, WW2, WW1, NAPOLEONIC, ANCIENT_MEDIEVAL). Module disable list per era (e.g., ANCIENT_MEDIEVAL disables `detection/sensors.py` radar/thermal/sonar, `c2/communications.py` radio/data link, `ew/*`, `space/*`). Era-specific physics constants (Mach-dependent drag tables per era, propellant types, armor materials). Era-specific `TickResolution` defaults (Napoleonic tactical ticks may be longer than modern). Scenario YAML `era: ww2` field selects era config. `era: modern` is default and matches all existing behavior.
- `simulation/scenario.py` (modified) — Added `era` field, `era_config` loading, era-aware scenario loading, WW2 engine fields wired into `SimulationContext`.
- **Unit YAML data** (15 files): Sherman M4A3, T-34/85, Tiger I, Panther, Panzer IV, M1 Garand squad, Wehrmacht rifle squad, Soviet rifle squad, Bf-109G, P-51D, Spitfire IX, B-17G, Type VIIC U-boat, Fletcher DD, Iowa BB
- **Weapon YAML data** (8 files): 75mm M3, 88mm KwK 36, 76mm F-34, .50 cal M2, MG42, Mk 14 torpedo, 5"/38 naval gun, 16"/50 naval gun
- **Ammunition YAML data** (13 files): AP, HE, APCR, APCBC rounds for each caliber
- **Sensor YAML data** (4 files): Mk 1 eyeball (dominant), SCR-584 gun-laying radar, Type 271 naval radar, hydrophones
- **Signature YAML data** (15 files): Visual/acoustic signatures (no thermal, no radar cross-section for ground units)

### 20b: Engine Extensions
- `combat/naval_gunnery.py` (new) — WW2 naval fire control: bracket firing, spotting correction, fire control computer (mechanical). Range-dependent dispersion pattern.
- `movement/convoy.py` (new) — Convoy mechanics: formation types (column, broad front), escort positions, U-boat wolf pack attack sequence, depth charge patterns.
- `combat/strategic_bombing.py` (new) — Area bombing model: CEP-based damage to target areas. Bomber stream, fighter escort, flak defense.

### 20c: Doctrine & Commanders
- **Doctrine YAML data** (4 files): Blitzkrieg, Soviet deep operations, British deliberate attack, US combined arms
- **Commander YAML data** (3 files): Aggressive (Patton archetype), methodical (Montgomery archetype), operational art (Zhukov archetype)

### 20d: Validation Scenarios
- **Scenario YAML data** (3 files):
  - `data/eras/ww2/scenarios/kursk.yaml` — Prokhorovka tank battle (5th Guards Tank vs II SS Panzer)
  - `data/eras/ww2/scenarios/midway.yaml` — Carrier battle (4 IJN carriers vs 3 USN carriers)
  - `data/eras/ww2/scenarios/normandy_bocage.yaml` — Hedgerow fighting (infantry-centric, close terrain)

**YAML data total** (~60 files): 15 units + 8 weapons + 13 ammo + 4 sensors + 15 signatures + 4 doctrines + 3 commanders + 3 scenarios = ~65 YAML data files.

**Key features**: Era framework correctly disables irrelevant subsystems for WW2 era (no GPS, no thermal sights, no data links, no PGMs). WW2 scenarios load and run with period-appropriate unit definitions. Naval gunnery model produces bracket-and-hit patterns with spotting correction. Convoy mechanics model escort formations and wolf pack attacks. Strategic bombing uses CEP-based area damage with bomber stream, fighter escort, and flak defense. No guided munitions used. Radar detection limited to period capabilities. Era config for MODERN era produces identical results to no-era-config (backward compatible). Deterministic replay verified.

**Exit Criteria**: All met. Era framework correctly disables irrelevant subsystems for WW2 era. WW2 scenarios load and run with period-appropriate unit definitions. Tank combat produces historically plausible exchange ratios. Naval gunnery model produces bracket-and-hit patterns. No guided munitions used. Radar detection limited to period capabilities. Era config for MODERN era produces identical results to no-era-config (backward compatible). Validation against Kursk historical data within tolerance. All 5,244 tests pass. Deterministic replay verified.

---

## Phase 21: WW1 Era — **COMPLETE**
**Goal**: World War 1 data package + trench warfare, chemical weapons (via Phase 18 CBRN), and pre-radio C2.

**Status**: Complete. 182 new tests (87 era config/data + 67 engine extensions + 28 validation). 5,426 total tests passing. 3 new source files + 4 modified + ~45 YAML data files. No new dependencies.

### 21a: Era Config + Unit & Weapon Data (87 tests)
- `core/era.py` — WW1_ERA_CONFIG: disables EW/space/GPS/thermal/data links/PGM, enables CBRN, VISUAL-only sensors, c2_delay_multiplier=5.0
- `simulation/scenario.py` — 3 new SimulationContext fields (trench_engine, barrage_engine, gas_warfare_engine), trench_warfare terrain type
- `data/eras/ww1/units/` — 6 units: British infantry platoon, German Sturmtruppen, French poilu squad, Mark IV tank, A7V, cavalry troop
- `data/eras/ww1/weapons/` — 8 weapons: Lee-Enfield, Gewehr 98, Maxim MG08, Lewis gun, 18-pdr, 77mm FK 96, 21cm Mörser, Mills bomb
- `data/eras/ww1/ammunition/` — 10 ammo types: .303 ball/AP, 7.92mm S Patrone, 18-pdr shrapnel/HE, 77mm HE/shrapnel/gas, 21cm HE, Mills bomb frag
- `data/eras/ww1/sensors/` — 5 sensors: binoculars, sound ranging, flash spotting, observation balloon, aircraft recon (all VISUAL)
- `data/eras/ww1/signatures/` — 6 profiles (one per unit, zeroed thermal/radar/EM)
- `data/eras/ww1/doctrine/` — 3 doctrines: british_trench_warfare, german_sturmtaktik, french_attaque_outrance
- `data/eras/ww1/commanders/` — 3 commanders: haig_attritional, ludendorff_storm, foch_unified
- `data/eras/ww1/comms/` — 2 comms: field_telephone_ww1 (WIRE, 2s latency), runner_messenger_ww1 (MESSENGER, 600s latency)

### 21b: Engine Extensions (67 tests)
- `terrain/trenches.py` — TrenchSystemEngine: shapely LineString + STRtree spatial indexing. TrenchType enum (FIRE, SUPPORT, COMMUNICATION, SAP). Cover values per type (0.85/0.70/0.50/0.60) scaled by condition. Movement factors (along=0.5, crossing=0.3, no-man's-land=0.2). Bombardment degrades condition. No-man's-land zones. State persistence.
- `combat/barrage.py` — BarrageEngine: aggregate fire density model. BarrageType (STANDING, CREEPING, BOX, COUNTER_BATTERY). Suppression/casualty rates per round/hectare. Creeping advance (50 m/min). 2-D Gaussian drift. Friendly fire zone. Dugout protection. Trench degradation integration. State persistence.
- `combat/gas_warfare.py` — GasWarfareEngine: thin adapter wrapping CBRN pipeline. GasDeliveryMethod (CYLINDER_RELEASE, ARTILLERY_SHELL, PROJECTOR). GasMaskType→MOPP mapping (NONE→0, IMPROVISED_CLOTH→1, PH_HELMET→2, SBR→3). Wind favorability check. Cylinder release creates multiple puffs along front. State persistence.
- `data/cbrn/agents/phosgene.yaml` — CG choking agent (LCt50=3200, non-persistent)
- `data/cbrn/delivery/` — cylinder_release.yaml, livens_projector.yaml
- `validation/historical_data.py` + `scenario_runner.py` — trench_warfare terrain type support

### 21c: Validation Scenarios (28 tests)
- `data/eras/ww1/scenarios/somme_july1/scenario.yaml` — Somme Day 1 (July 1, 1916): 5 British platoons vs 5 German positions, trench_warfare terrain, haig_attritional commander, documented ~7:1 casualty ratio
- `data/eras/ww1/scenarios/cambrai/scenario.yaml` — Cambrai (Nov 20, 1917): 3 infantry + 4 Mark IV tanks vs 3 German positions, first massed tank attack, documented 8km advance + 30% mechanical losses

**Key design decisions**: CBRN stays enabled (WW1 chemical warfare). Trenches as spatial overlay (not heightmap). Barrage as aggregate density model (not shell-by-shell). Gas warfare wraps existing CBRN pipeline. C2 delays via comms YAML + physics_overrides multiplier. Nuclear gating structural (no nuclear YAML, cbrn_nuclear_enabled=False in physics_overrides).

**Exit Criteria**: All met. Trench cover values differentiate fire/support/comm trenches. Creeping barrage advances at 50 m/min and affects timing safety. Gas mask types map to MOPP levels for CBRN protection. Dugout protection reduces barrage casualties. C2 delay multiplier set to 5.0x. All 5,426 tests pass. Deterministic replay verified.

Devlog: [devlog/phase-21.md](devlog/phase-21.md)

---

## Phase 22: Napoleonic Era — **COMPLETE**
**Goal**: Napoleonic data package + black powder weapons, formation combat, cavalry, and courier C2.

**Status**: Complete. 233 tests (102 + 98 + 33) across 3 test files. Total: 5,659 tests passing (up from 5,426). 6 new source files + 2 modified + ~53 YAML data files. No new dependencies. Follows Phase 20-21 era framework pattern. Devlog: [`devlog/phase-22.md`](devlog/phase-22.md).

### 22a: Era Config + Data (102 tests)
- `core/era.py` (modified) — `NAPOLEONIC_ERA_CONFIG`: disables ew, space, cbrn, gps, thermal_sights, data_links, pgm. VISUAL-only sensors. `c2_delay_multiplier=8.0`.
- `simulation/scenario.py` (modified) — 6 new `SimulationContext` fields: `volley_fire_engine`, `melee_engine`, `cavalry_engine`, `formation_napoleonic_engine`, `courier_engine`, `foraging_engine`. All in state persistence.
- **~53 YAML data files**: 10 units (french_line_infantry, french_light_infantry, french_old_guard, british_line_infantry, british_rifle_company, cuirassier_squadron, hussar_squadron, lancer_squadron, horse_artillery_battery, foot_artillery_battery), 9 weapons (brown_bess, charleville_1777, baker_rifle, 6pdr_cannon, 12pdr_cannon, howitzer_napoleonic, cavalry_saber, lance, bayonet), 9 ammo, 3 sensors, 10 signatures, 3 doctrines, 3 commanders, 2 comms, 2 scenarios.

### 22b: Engine Extensions (98 tests)
- `combat/volley_fire.py` (new, ~230 lines) — Massed musket fire aggregate model. Binomial casualties from range table interpolation × formation × smoke × volley type. Canister sub-model.
- `combat/melee.py` (new, ~210 lines) — Contact combat. Pre-contact morale check (cavalry shock lowers defender threshold). Force ratio × base rate × formation modifier. Pursuit casualties.
- `movement/cavalry.py` (new, ~250 lines) — Charge state machine: WALK→TROT→GALLOP→CHARGE→IMPACT→PURSUIT→RALLY. Distance-driven phase transitions. Fatigue accumulation.
- `movement/formation_napoleonic.py` (new, ~220 lines) — LINE/COLUMN/SQUARE/SKIRMISH. Firepower fraction, speed, cavalry/artillery vulnerability per formation. Worst-of-both during transitions.
- `c2/courier.py` (new, ~230 lines) — Physical messenger dispatch. Terrain-dependent speed. Interception risk per km. Drum/bugle range limit. Courier pool per HQ.
- `logistics/foraging.py` (new, ~200 lines) — Zone-based terrain productivity × seasonal modifier × remaining fraction. Depletion/recovery. Ambush risk per foraging mission.

### 22c: Validation Scenarios (33 tests)
- `data/eras/napoleonic/scenarios/austerlitz/scenario.yaml` — Pratzen Heights (12km×8km, combined arms, maneuver, decisive point)
- `data/eras/napoleonic/scenarios/waterloo/scenario.yaml` — Mont-Saint-Jean (6km×4km, infantry squares vs cavalry charges, Guard commitment)

**Exit Criteria**: All met. Musket volley 2-5% casualty at 100m (avg ~25 from 500 muskets). Cavalry breaks infantry not in square (LINE breaks; SQUARE holds). Square vulnerable to artillery (artillery_vulnerability=2.0). Courier C2 hour-scale delays (~33 min for 10km). Formation changes 30-120s. Deterministic replay verified.

---

## Phase 23: Ancient & Medieval Era — **COMPLETE**
**Goal**: Pre-gunpowder data package + melee-dominant combat, siege warfare, and visual/audible C2.

**Status**: Complete. 321 tests (167 + 112 + 42) across 3 test files. Total: 5,980 tests passing (up from 5,659). 5 new source files + 4 modified + ~49 YAML data files. No new dependencies. Follows Phase 20-22 era framework pattern. Devlog: [`devlog/phase-23.md`](devlog/phase-23.md).

### 23a: Era Config + Data (167 tests)
- `core/era.py` (modified) — `ANCIENT_MEDIEVAL_ERA_CONFIG`: disables ew, space, cbrn, gps, thermal_sights, data_links, pgm. VISUAL-only sensors. `c2_delay_multiplier=12.0`.
- `simulation/scenario.py` (modified) — 5 new `SimulationContext` fields: `archery_engine`, `siege_engine`, `formation_ancient_engine`, `naval_oar_engine`, `visual_signals_engine`. All in state persistence. `open_field` terrain type added.
- `validation/historical_data.py` + `scenario_runner.py` (modified) — `open_field` terrain type support.
- **~49 YAML data files**: 7 units (roman_legionary_cohort, greek_hoplite_phalanx, english_longbowman, norman_knight_conroi, swiss_pike_block, mongol_horse_archer, viking_huscarl), 13 weapons (gladius, pilum, sarissa, longbow, crossbow, lance_medieval, sword_medieval, mace, pike, catapult, trebuchet, ballista, battering_ram), 8 ammo, 3 sensors, 7 signatures, 3 doctrines, 3 commanders, 2 comms.

### 23b: Engine Extensions (112 tests)
- `combat/archery.py` (new, ~300 lines) — Massed archery aggregate model. MissileType (LONGBOW/CROSSBOW/COMPOSITE_BOW/JAVELIN/SLING). ArmorType (NONE/LIGHT/MAIL/PLATE). Binomial casualties from per-missile-type Phit range tables. Armor reduction. Formation vulnerability modifier. Per-archer ammo tracking (24 arrows, depletes per volley).
- `combat/melee.py` (extended) — 3 new MeleeType values (PIKE_PUSH=4, SHIELD_WALL=5, MOUNTED_CHARGE=6). Reach advantage modifier (1.3, round 1 only). Flanking casualty multiplier (2.5). Pike push attrition, shield wall defense bonus, mounted charge casualty rate. Backward compatible.
- `movement/formation_ancient.py` (new, ~350 lines) — 7 formation types (PHALANX/SHIELD_WALL/PIKE_BLOCK/WEDGE/SKIRMISH/TESTUDO/COLUMN). Melee power, defense, speed, archery/cavalry/flanking vulnerability modifiers. Worst-of-both during transitions.
- `combat/siege.py` (new, ~350 lines) — Campaign-scale daily state machine (ENCIRCLEMENT→BOMBARDMENT→BREACH→ASSAULT→FALLEN/RELIEF/ABANDONED). Wall HP (trebuchet 50/day, ram 30, catapult 20, mine 40). Breach at 30% remaining. Starvation timeline. Sally sorties. Relief force mechanics.
- `movement/naval_oar.py` (new, ~220 lines) — Fatigue-based rowing (cruise/battle/ramming speeds). Exhaustion threshold halves speed. Ram damage = base + speed_factor × approach_speed. Boarding transition to melee.
- `c2/visual_signals.py` (new, ~290 lines) — Synchronous presence-based C2. Banner (1000m, LOS, instant, fidelity 0.7). Horn (500m, no LOS, instant, fidelity 0.5). Runner (async, 3 m/s, fidelity 1.0). Fire beacon (10km, LOS, binary only).

### 23c: Validation Scenarios (42 tests)
- `data/eras/ancient_medieval/scenarios/cannae/scenario.yaml` — Cannae (216 BC): double envelopment, 85% Roman / 8% Carthaginian casualties
- `data/eras/ancient_medieval/scenarios/agincourt/scenario.yaml` — Agincourt (1415): longbow vs armored cavalry, 50% French / 5% English casualties
- `data/eras/ancient_medieval/scenarios/hastings/scenario.yaml` — Hastings (1066): shield wall vs combined arms, 50% Saxon / 30% Norman casualties

**Key design decisions**: Archery as aggregate Binomial model (same pattern as Napoleonic volley fire). Melee extension, not replacement — existing Napoleonic types unchanged. Separate formation_ancient.py (7 types mechanically distinct from Napoleonic). Siege as daily state machine (campaign-scale, not tick-level). Visual signals as synchronous presence-based C2 (vs Napoleonic asynchronous courier). Ammo tracks volleys remaining per archer (not total arrows).

**Exit Criteria**: All met. Longbow produces significant casualties at 100m. Plate armor reduces archery effectiveness. TESTUDO near-immune to archery (0.1 vulnerability). PHALANX extremely vulnerable to flanking (2.0). Pike blocks stop cavalry (0.2 vulnerability). Reach advantage on round 1 only. Flanked units take 2.5x casualties. 2 trebuchets breach walls in ~7 days. Banner works at 1000m with LOS. All effects modulate existing systems. Backward compatible. Deterministic replay verified.

---

## Phase 24: Unconventional & Prohibited Warfare — **COMPLETE**
**Goal**: Model escalation dynamics, prohibited weapons employment, unconventional/irregular warfare mechanics, war crimes consequences, and insurgency/COIN feedback loops. Adds the "full spectrum" of conflict that conventional-only modeling cannot capture.

**Status**: Complete. 345 tests (75 + 56 + 59 + 62 + 46 + 47) across 6 test files. Total: 6,325 tests passing (up from 5,980). 9 new source files + ~18 modified. ~32 YAML data files. No new dependencies. All changes backward-compatible — `escalation_config` defaults to `None`, new enum values appended, new commander traits have defaults. Devlog: [`devlog/phase-24.md`](devlog/phase-24.md).

**Prerequisites**: Phase 12e (civilian population — displacement, collateral, HUMINT, influence dynamics), Phase 18 (CBRN effects — chemical/biological/nuclear weapon effects). Benefits from Phase 16 (EW — counter-IED jamming), Phase 19 (doctrinal schools — school-specific escalation tendencies).

**Doctrinal school expansion**: Phase 24's non-kinetic infrastructure (escalation, political pressure, information operations, insurgency dynamics) enables future doctrinal AI schools not implementable in Phase 19: **4GW/Generational Warfare** (Lind — legitimacy contest, population-centric, moral-level warfare), **Unrestricted Warfare** (Qiao/Wang — 24-type multi-domain combination warfare, synchrony, asymmetry), **Gerasimov Hybrid** (4:1 non-military ratio, phased escalation, reflexive control). See `brainstorm-post-mvp.md` Section 7 "Modern & Post-Classical Schools" for full analysis.

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
| EW engines not wired into simulation engine tick loop | Phase 16 | Deferred (integration phase — wire into engine when EW scenarios run full campaigns) |
| No DRFM detailed waveform modeling | Phase 16 | Deferred (simplified effectiveness parameter adequate) |
| TDOA geolocation simplified centroid-shift | Phase 16 | Deferred (full TDOA solver is low priority) |
| No cooperative jamming between platforms | Phase 16 | Deferred (individual jammer aggregation adequate) |
| Campaign-level EW validation deferred | Phase 16 | Deferred (component-level physics validated; campaign integration deferred) |
| Simplified Keplerian orbits (no SGP4/TLE) | Phase 17 | Deferred (campaign-scale accuracy sufficient) |
| No detailed satellite bus modeling | Phase 17 | Deferred (power/thermal/attitude not needed for force-multiplier effects) |
| No space-based SIGINT integration with EW SIGINT | Phase 17 | Deferred (wire into Phase 16 SIGINT engine in future) |
| Debris cascade model is statistical | Phase 17 | Deferred (individual fragment tracking is excessive fidelity) |
| No satellite maneuvering or fuel limits | Phase 17 | Deferred (station-keeping not needed at campaign scale) |
| No space weather effects | Phase 17 | Deferred (solar flares/radiation belts are rare events) |
| EMEnvironment GPS accuracy not per-side | Phase 17 | Deferred (uses worst-case aggregation; per-side EM requires architectural changes) |
| ScenarioLoader doesn't auto-wire EW/Space/CBRN engines | Phase 16/17/18 | Deferred (all three require manual wiring; future integration pass needed) |
| MOPP speed factor never passed from battle loop to movement | Phase 18 | Deferred (parameter exists but unused at runtime) |
| Hardcoded terrain channeling thresholds in dispersal | Phase 18 | Deferred (5m valley/ridge detection; configurable thresholds not critical) |
| Hardcoded fallback weather defaults in CBRN engine | Phase 18 | Deferred (wind=2.0, temp=20°C when weather engine unavailable) |
| No automatic puff aging/cleanup in dispersal engine | Phase 18 | Deferred (caller must remove aged puffs; unbounded growth possible in long campaigns) |

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
| `simulation/aggregation.py` | 13a |
| `core/numba_utils.py` | 13b |
| `tools/tempo_analysis.py` | 14b |
| `terrain/data_pipeline.py` | 15a |
| `terrain/real_heightmap.py` | 15a |
| `terrain/real_classification.py` | 15b |
| `terrain/real_infrastructure.py` | 15b |
| `terrain/real_bathymetry.py` | 15c |
| `terrain/trenches.py` | 21b |
| `ew/__init__.py` | 16a |
| `ew/events.py` | 16a |
| `ew/spectrum.py` | 16a |
| `ew/emitters.py` | 16a |
| `ew/jamming.py` | 16b |
| `ew/decoys_ew.py` | 16b |
| `ew/eccm.py` | 16c |
| `ew/sigint.py` | 16d |
| `space/__init__.py` | 17a |
| `space/events.py` | 17a |
| `space/orbits.py` | 17a |
| `space/constellations.py` | 17a |
| `space/gps.py` | 17b |
| `space/isr.py` | 17c |
| `space/early_warning.py` | 17c |
| `space/satcom.py` | 17d |
| `space/asat.py` | 17d |
| `cbrn/__init__.py` | 18a |
| `cbrn/events.py` | 18a |
| `cbrn/agents.py` | 18a |
| `cbrn/dispersal.py` | 18a |
| `cbrn/contamination.py` | 18b |
| `cbrn/protection.py` | 18b |
| `cbrn/casualties.py` | 18c |
| `cbrn/decontamination.py` | 18c |
| `cbrn/nuclear.py` | 18d |
| `cbrn/engine.py` | 18e |
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

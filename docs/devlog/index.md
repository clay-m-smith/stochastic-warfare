# Development Log

Rolling record of implementation decisions, changes, and lessons learned across all phases of Stochastic Warfare development.

## Phases

| Phase | Focus | Status | Log |
|-------|-------|--------|-----|
| 0 | Project Scaffolding | **Complete** | [phase-0.md](phase-0.md) |
| 1 | Terrain & Environment Foundation | **Complete** | [phase-1.md](phase-1.md) |
| 2 | Entity System & Movement | **Complete** | [phase-2.md](phase-2.md) |
| 3 | Detection & Intelligence | **Complete** | [phase-3.md](phase-3.md) |
| 4 | Combat Resolution & Morale | **Complete** | [phase-4.md](phase-4.md) |
| 5 | C2 Infrastructure | **Complete** | [phase-5.md](phase-5.md) |
| 6 | Logistics & Supply | **Complete** | [phase-6.md](phase-6.md) |
| 7 | Engagement Validation | **Complete** | [phase-7.md](phase-7.md) |
| 8 | AI & Planning | **Complete** | [phase-8.md](phase-8.md) |
| 9 | Simulation Orchestration | **Complete** | [phase-9.md](phase-9.md) |
| 10 | Campaign Validation | **Complete** | [phase-10.md](phase-10.md) |
| | | | |
| 11 | Core Fidelity Fixes | **Complete** | [phase-11.md](phase-11.md) |
| 12 | Deep Systems Rework | **Complete** | [phase-12.md](phase-12.md) |
| 13 | Performance Optimization | **Complete** | [phase-13.md](phase-13.md) |
| 14 | Tooling & Developer Experience | **Complete** | [phase-14.md](phase-14.md) |
| 15 | Real-World Terrain & Data Pipeline | **Complete** | [phase-15.md](phase-15.md) |
| 16 | Electronic Warfare | **Complete** | [phase-16.md](phase-16.md) |
| 17 | Space & Satellite Domain | **Complete** | [phase-17.md](phase-17.md) |
| 18 | NBC/CBRN Effects | **Complete** | [phase-18.md](phase-18.md) |
| 19 | Doctrinal AI Schools | **Complete** | [phase-19.md](phase-19.md) |
| 20 | WW2 Era | **Complete** | [phase-20.md](phase-20.md) |
| 21 | WW1 Era | **Complete** | [phase-21.md](phase-21.md) |
| 22 | Napoleonic Era | **Complete** | [phase-22.md](phase-22.md) |
| 23 | Ancient & Medieval Era | **Complete** | [phase-23.md](phase-23.md) |
| 24 | Unconventional & Prohibited Warfare | **Complete** | [phase-24.md](phase-24.md) |
| | | | |
| 25 | Engine Wiring & Integration Sprint | **Complete** | [phase-25.md](phase-25.md) |
| 26 | Core Polish & Configuration | **Complete** | [phase-26.md](phase-26.md) |
| 27 | Combat System Completeness | **Complete** | [phase-27.md](phase-27.md) |
| 28 | Modern Era Data Package | **Complete** | [phase-28.md](phase-28.md) |
| 28.5 | Directed Energy Weapons | **Complete** | [phase-28.5.md](phase-28.5.md) |
| 29 | Historical Era Data Expansion | **Complete** | [phase-29.md](phase-29.md) |
| 30 | Scenario & Campaign Library | **Complete** | [phase-30.md](phase-30.md) |
| | | | |
| 31 | Documentation Site (GitHub Pages) | **Complete** | [phase-31.md](phase-31.md) |
| 32 | API & Service Foundation | **Complete** | [phase-32.md](phase-32.md) |
| 33 | Frontend Foundation & Scenario Browser | **Complete** | [phase-33.md](phase-33.md) |
| 34 | Run Results & Analysis Dashboard | **Complete** | [phase-34.md](phase-34.md) |
| 35 | Tactical Map & Spatial Visualization | **Complete** | [phase-35.md](phase-35.md) |
| 36 | Scenario Tweaker & Polish | **Complete** | [phase-36.md](phase-36.md) |
| | | | |
| 37 | Integration Fixes & E2E Validation | **Complete** | [phase-37.md](phase-37.md) |
| 38 | Map & Chart Enhancements | **Complete** | [phase-38.md](phase-38.md) |
| 39 | Quality, Performance & Packaging | **Complete** | [phase-39.md](phase-39.md) |
| | | | |
| 40 | Battle Loop Foundation | **Complete** | [phase-40.md](phase-40.md) |
| 41 | Combat Depth | **Complete** | [phase-41.md](phase-41.md) |
| 42 | Tactical Behavior | **Complete** | [phase-42.md](phase-42.md) |

## Post-MVP Refinement Index

Known limitations and deferred improvements logged during implementation. Review these after MVP is functional.

| Phase | Item | Section |
|-------|------|---------|
| 0 | Checkpoint format longevity (pickle fragility) | [phase-0.md — Open Questions](phase-0.md#open-questions) |
| 3 | ~~Track-to-target association needs nearest-neighbor gating~~ *(resolved Phase 11b)* | [phase-3.md — Known Limitations](phase-3.md#known-limitations-post-mvp-refinements) |
| 3 | Environment data threading (caller responsibility) | [phase-3.md — Known Limitations](phase-3.md#known-limitations-post-mvp-refinements) |
| 3 | ~~Passive sonar bearing is placeholder (random, not geometric)~~ *(resolved Phase 11b)* | [phase-3.md — Known Limitations](phase-3.md#known-limitations-post-mvp-refinements) |
| 3 | ~~No sensor FOV filtering against observer heading~~ *(resolved Phase 11b)* | [phase-3.md — Known Limitations](phase-3.md#known-limitations-post-mvp-refinements) |
| 3 | ~~Single-scan detection (no dwell/integration gain)~~ *(resolved Phase 11b)* | [phase-3.md — Known Limitations](phase-3.md#known-limitations-post-mvp-refinements) |
| 3 | Test coverage gap (296→334 vs planned 455; backfilled C2-facing APIs) | [phase-3.md — Known Limitations](phase-3.md#known-limitations-post-mvp-refinements) |
| 4 | ~~Ballistic trajectory uses simplified drag (no Mach-dependent Cd)~~ *(resolved Phase 11a)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | ~~DeMarre penetration approximation (no obliquity, composite, reactive armor)~~ *(resolved Phase 11a)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | HEAT penetration is range-independent | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | ~~Submarine evasion simplified probability model~~ *(resolved Phase 12c)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | ~~Mine trigger model lacks detailed ship signature interaction~~ *(resolved Phase 12c)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | Carrier ops deck management abstracted (no individual spot tracking) | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | ~~Morale Markov is discrete-time (not continuous-time)~~ *(resolved Phase 12d)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | ~~PSYOP model is simplified effectiveness roll~~ *(resolved Phase 12d)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | ~~Naval damage control lacks compartment flooding model~~ *(resolved Phase 12c)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | ~~Air combat lacks detailed flight dynamics / energy-maneuverability~~ *(resolved Phase 12c)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 4 | ~~Environment→combat coupling partial: air_combat, air_defense, naval_surface, indirect_fire lack env coupling~~ *(resolved Phase 11a)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations-post-mvp-refinements) |
| 5 | ~~No multi-hop propagation (single hop issuer→recipient only)~~ *(resolved Phase 12a)* | [phase-5.md — Known Limitations](phase-5.md#known-limitations-deferred-items) |
| 5 | ~~No terrain-based LOS check for communications~~ *(resolved Phase 12a)* | [phase-5.md — Known Limitations](phase-5.md#known-limitations-deferred-items) |
| 5 | ~~Simplified FSCL (east-west line, not arbitrary polyline)~~ *(resolved Phase 12a)* | [phase-5.md — Known Limitations](phase-5.md#known-limitations-deferred-items) |
| 5 | ~~No ATO planning cycle (structures only, generation deferred to Phase 9/Future)~~ *(resolved Phase 12a)* | [phase-5.md — Known Limitations](phase-5.md#known-limitations-deferred-items) |
| 5 | ~~No JTAC/FAC observer model for CAS~~ *(resolved Phase 12a)* | [phase-5.md — Known Limitations](phase-5.md#known-limitations-deferred-items) |
| 5 | Messenger comm type has no terrain traversal or intercept risk | [phase-5.md — Known Limitations](phase-5.md#known-limitations-deferred-items) |
| 6 | ~~No supply optimization solver (pull-based nearest depot only)~~ *(resolved Phase 12b)* | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | ~~No multi-echelon supply chain (direct depot-to-unit)~~ *(resolved Phase 12b)* | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | ~~Simplified transport vulnerability (no escort effects)~~ *(resolved Phase 12b)* | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | ~~Medical M/M/c queueing approximate (exponential service)~~ *(resolved Phase 12b)* | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | ~~Engineering times deterministic (no stochastic variation)~~ *(resolved Phase 11c)* | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | ~~No fuel gating on movement (tracked but not enforced)~~ *(resolved Phase 11c)* | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Blockade effectiveness simplified (flat per-ship probability) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Captured supply efficiency flat 50% (no compatibility check) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No local water procurement (always from rear depots) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No ammunition production (scenario-defined depots only) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | VLS non-reloadable-at-sea enforcement deferred to naval combat integration | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 7 | ~~73 Easting exchange_ratio = inf (detection asymmetry prevents blue losses)~~ *(resolved Phase 30 — calibration tuning: visibility 800m, red engagement 1500m, thermal_contrast 1.5)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | ~~No fire rate limiting (units fire once per tick regardless of ROF)~~ *(resolved Phase 11a)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | ~~Uniform target_size_modifier (applies to both sides equally)~~ *(resolved Phase 11a)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | ~~No wave attack modeling (all units advance simultaneously)~~ *(resolved Phase 11c)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | Pre-scripted behavior only (no tactical AI, deferred to Phase 8) | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | ~~Falklands simplified — Sheffield attack only, no San Carlos raids~~ *(resolved Phase 30 — added San Carlos air raids + Goose Green ground scenarios)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | ~~Synthetic terrain (programmatic heightmaps, not real topographic data)~~ *(resolved Phase 15 — real-world terrain pipeline)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | No logistics in validation scenarios (short engagements) | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | No C2 propagation in validation (direct behavior, no order chain) | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 7 | ~~Simplified force compositions (representative samples, not complete OOB)~~ *(resolved Phase 30 — expanded 73 Easting OOB, diverse modern/historical scenarios)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations-post-mvp-refinements) |
| 8 | ~~Named doctrinal schools (Clausewitzian AI, Sun Tzu AI) deferred to Future Phases~~ *(resolved Phase 19)* | [phase-8.md — Known Limitations](phase-8.md#known-limitations-post-mvp-refinements) |
| 8 | COA wargaming is analytical (Lanchester), not full nested simulation | [phase-8.md — Known Limitations](phase-8.md#known-limitations-post-mvp-refinements) |
| 8 | No terrain-specific COA generation (e.g., no river crossing planning detail) | [phase-8.md — Known Limitations](phase-8.md#known-limitations-post-mvp-refinements) |
| 8 | Implied task tables are simplified (not full FM 5-0 comprehensive list) | [phase-8.md — Known Limitations](phase-8.md#known-limitations-post-mvp-refinements) |
| 8 | No multi-echelon simultaneous planning (each commander plans independently) | [phase-8.md — Known Limitations](phase-8.md#known-limitations-post-mvp-refinements) |
| 8 | Estimates update periodically, not reactively to every event | [phase-8.md — Known Limitations](phase-8.md#known-limitations-post-mvp-refinements) |
| 8 | Stratagems are opportunity-evaluated, not proactively planned in COA | [phase-8.md — Known Limitations](phase-8.md#known-limitations-post-mvp-refinements) |
| 8 | ~~Brigade echelon decision hardcodes echelon_level=9 in result (cosmetic)~~ *(resolved Phase 11d)* | [phase-8.md — Known Limitations](phase-8.md#known-limitations-post-mvp-refinements) |
| 9 | ~~No force aggregation/disaggregation — all units at individual resolution~~ *(resolved Phase 13 postmortem)* | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | Single-threaded simulation loop (required for deterministic PRNG replay) | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | ~~No auto-resolve — every engagement runs full tactical resolution~~ *(resolved Phase 13a-6)* | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | Simplified strategic movement (no detailed operational pathfinding) | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | Fixed reinforcement schedule (no Poisson/stochastic arrivals) | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | No naval campaign management (structurally supported but untested) | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | ~~Synthetic terrain only (programmatic heightmaps, not real topographic data)~~ *(resolved Phase 15 — real-world terrain pipeline)* | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | ~~LOS cache is per-tick only (cleared each tick after movement)~~ *(resolved Phase 13 postmortem — selective invalidation wired)* | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | No weather evolution mid-campaign beyond WeatherEngine.step() | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | ~~Viewshed vectorization deferred (lower priority)~~ *(resolved Phase 13a-5)* | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 9 | ~~STRtree for infrastructure spatial queries still deferred~~ *(resolved Phase 13a-2)* | [phase-9.md — Known Limitations](phase-9.md#known-limitations-post-mvp-refinements) |
| 10 | No fire rate limiting — units fire once per tick regardless of ROF (inherited) | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 10 | No wave attack modeling — all red units advance simultaneously (inherited) | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 10 | Campaign AI decisions coarse — OODA at echelon timing, may not produce tactical posture changes in short runs | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 10 | ~~Simplified force compositions — representative samples, not complete historical OOB~~ *(resolved Phase 30 — expanded OOBs, diverse modern/historical scenarios)* | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 10 | ~~Synthetic terrain — programmatic heightmaps, not real topographic data~~ *(resolved Phase 15 — real-world terrain pipeline)* | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 10 | Fixed reinforcement schedule — deterministic arrival, no stochastic variation | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 10 | ~~No force aggregation/disaggregation — all units individually tracked~~ *(resolved Phase 13 postmortem)* | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 10 | AI expectation matching approximate — string-based posture detection | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 10 | Campaign metrics proxy territory control via survival fraction not spatial | [phase-10.md — Known Limitations](phase-10.md#known-limitations-post-mvp-refinements) |
| 11 | ~~Fuel gating not wired to stockpile in battle.py~~ *(resolved Phase 12b)* | [phase-11.md — Known Limitations](phase-11.md#known-limitations-post-mvp-refinements) |
| 11 | Wave assignments are manual (no AI auto-assignment) | [phase-11.md — Known Limitations](phase-11.md#known-limitations-post-mvp-refinements) |
| 11 | ~~Integration gain caps at 4 scans~~ *(resolved Phase 26c — configurable max_integration_scans)* | [phase-11.md — Known Limitations](phase-11.md#known-limitations-post-mvp-refinements) |
| 11 | ~~Armor type YAML data missing~~ *(resolved Phase 26c — armor_type field + 6 YAML files)* | [phase-11.md — Known Limitations](phase-11.md#known-limitations-post-mvp-refinements) |
| 16 | ~~EW engines not yet wired into simulation engine tick loop~~ *(resolved Phase 25c)* | [phase-16.md — Known Limitations](phase-16.md#known-limitations-future-work) |
| 16 | No DRFM detailed waveform modeling (simplified effectiveness parameter) | [phase-16.md — Known Limitations](phase-16.md#known-limitations-future-work) |
| 16 | TDOA geolocation uses simplified centroid-shift algorithm | [phase-16.md — Known Limitations](phase-16.md#known-limitations-future-work) |
| 16 | No cooperative jamming between multiple platforms | [phase-16.md — Known Limitations](phase-16.md#known-limitations-future-work) |
| 16 | Campaign-level EW validation deferred (component-level only) | [phase-16.md — Known Limitations](phase-16.md#known-limitations-future-work) |
| 17 | Simplified Keplerian orbits (no SGP4/TLE, no atmospheric drag for LEO decay) | [phase-17.md — Known Limitations](phase-17.md#known-limitations-future-work) |
| 17 | No detailed satellite bus modeling (power, thermal, attitude control) | [phase-17.md — Known Limitations](phase-17.md#known-limitations-future-work) |
| 17 | No space-based SIGINT integration with Phase 16 SIGINT engine | [phase-17.md — Known Limitations](phase-17.md#known-limitations-future-work) |
| 17 | Debris cascade model is statistical (no individual fragment tracking) | [phase-17.md — Known Limitations](phase-17.md#known-limitations-future-work) |
| 17 | No satellite maneuvering or station-keeping fuel limits | [phase-17.md — Known Limitations](phase-17.md#known-limitations-future-work) |
| 17 | No space weather effects (solar flares, radiation belt variations) | [phase-17.md — Known Limitations](phase-17.md#known-limitations-future-work) |
| 17 | EMEnvironment GPS accuracy is not per-side (uses worst-case aggregation) | [phase-17.md — Postmortem](phase-17.md#postmortem) |
| 16/17 | ~~ScenarioLoader doesn't auto-wire EWEngine or SpaceEngine from YAML~~ *(resolved Phase 25a)* | [phase-17.md — Postmortem](phase-17.md#postmortem) |
| 16/17/18 | ~~ScenarioLoader doesn't auto-wire CBRNEngine from YAML~~ *(resolved Phase 25a)* | [phase-18.md — Postmortem](phase-18.md#postmortem) |
| 18 | ~~`mopp_speed_factor` parameter exists in movement engine but never passed from battle loop~~ *(resolved Phase 25c)* | [phase-18.md — Postmortem](phase-18.md#postmortem) |
| 18 | ~~Hardcoded terrain channeling thresholds in dispersal (5m valley/ridge, 50m offset)~~ *(resolved Phase 26b — DispersalConfig fields)* | [phase-18.md — Postmortem](phase-18.md#postmortem) |
| 18 | ~~Hardcoded fallback weather defaults in CBRN engine (wind=2.0, temp=20°C, cloud=0.5)~~ *(resolved Phase 26b — CBRNConfig fields)* | [phase-18.md — Postmortem](phase-18.md#postmortem) |
| 18 | ~~No automatic puff aging/cleanup mechanism in dispersal engine~~ *(resolved Phase 26c — cleanup_aged_puffs() + max_puff_age_s)* | [phase-18.md — Postmortem](phase-18.md#postmortem) |
| 19 | ~~CommanderEngine not wired into SimulationContext~~ *(resolved Phase 25d)* | [phase-19.md — Known Limitations](phase-19.md#known-limitations) |
| 19 | ~~battle.py passes assessment=None to decide()~~ *(resolved Phase 25b)* | [phase-19.md — Known Limitations](phase-19.md#known-limitations) |
| 16/17/18/19 | ~~ScenarioLoader doesn't auto-wire SchoolRegistry from YAML~~ *(resolved Phase 25a)* | [phase-19.md — Known Limitations](phase-19.md#known-limitations) |
| 19 | ~~`get_coa_score_weight_overrides()` hook not called in battle loop~~ *(resolved Phase 25b)* / `get_stratagem_affinity()` still deferred | [phase-19.md — Postmortem](phase-19.md#postmortem) |
| 19 | `CommanderPersonality.school_id` field defined but never read — schools assigned via SchoolRegistry instead | [phase-19.md — Postmortem](phase-19.md#postmortem) |
| 20 | Convoy engine does not model individual escort positions (abstract effectiveness parameter) | [phase-20.md — Known Limitations](phase-20.md#known-limitations) |
| 20 | Strategic bombing target regeneration is linear (no industrial interdependency graph) | [phase-20.md — Known Limitations](phase-20.md#known-limitations) |
| 20 | Fighter escort in strategic bombing is probability modifier, not full air combat sub-simulation | [phase-20.md — Known Limitations](phase-20.md#known-limitations) |
| 16/17/18/19/20 | ~~ScenarioLoader doesn't auto-wire era-specific engines from YAML~~ *(resolved Phase 25a)* | [phase-20.md — Postmortem](phase-20.md#postmortem) |
| 21 | ~~Barrage drift is purely random walk — no systematic correction for observer feedback~~ *(resolved Phase 27d — observer correction)* | [phase-21.md — Known Limitations](phase-21.md#known-limitations) |
| 21 | ~~Gas warfare engine does not model gas mask don time delay (units gain instant protection)~~ *(resolved Phase 27d — compute_exposure_during_don + get_effective_mopp_level)* | [phase-21.md — Known Limitations](phase-21.md#known-limitations) |
| 21 | Trench system has no wire-cutting mechanic (wire is a query attribute only, not a movement blocker) | [phase-21.md — Known Limitations](phase-21.md#known-limitations) |
| 16/17/18/19/20/21 | ~~ScenarioLoader doesn't auto-wire WW1 engines from YAML~~ *(resolved Phase 25a)* | [phase-21.md — Known Limitations](phase-21.md#known-limitations) |
| 21 | ~~Gas warfare wind direction tolerance (60°) hardcoded — should be configurable in GasWarfareConfig~~ *(resolved Phase 26b — GasWarfareConfig.max_wind_angle_deg)* | [phase-21.md — Postmortem](phase-21.md#postmortem) |
| 21 | ~~Barrage/gas engines use hardcoded fallback RNG seed (42) when no RNG injected~~ *(resolved Phase 26a — rng required on all 23 engines)* | [phase-21.md — Postmortem](phase-21.md#postmortem) |
| 16/17/18/19/20/21/22 | ~~ScenarioLoader doesn't auto-wire Napoleonic engines from YAML~~ *(resolved Phase 25a)* | [phase-22.md — Known Limitations](phase-22.md#known-limitations) |
| 22 | ~~Cavalry charge ignores terrain effects (speed not modified by slope or obstacles)~~ *(resolved Phase 27d — compute_cavalry_terrain_modifier)* | [phase-22.md — Known Limitations](phase-22.md#known-limitations) |
| 22 | ~~No frontage/depth in melee — simplified to force ratio × formation modifier~~ *(resolved Phase 27d — compute_frontage_constraint)* | [phase-22.md — Known Limitations](phase-22.md#known-limitations) |
| 22 | ~~Foraging ambush casualty rate hardcoded at 10% — should be configurable in ForagingConfig~~ *(resolved Phase 26b — ForagingConfig.ambush_casualty_rate)* | [phase-22.md — Known Limitations](phase-22.md#known-limitations) |
| 22 | ~~Volley/melee/cavalry/courier/foraging engines use hardcoded fallback RNG seed (42) when no RNG injected~~ *(resolved Phase 26a — rng required on all 23 engines)* | [phase-22.md — Known Limitations](phase-22.md#known-limitations) |
| 16/17/18/19/20/21/22/23 | ~~ScenarioLoader doesn't auto-wire Ancient/Medieval engines from YAML~~ *(resolved Phase 25a)* | [phase-23.md — Postmortem](phase-23.md#postmortem) |
| 28.5 | ~~DEWEngagementEvent has zero subscribers in production code (events published but never consumed)~~ *(closed Phase 37 — SimulationRecorder subscribes to base Event)* | [phase-28.5.md — Postmortem](phase-28.5.md#postmortem) |
| 28.5 | ~~dew_engine not used in simulation/engine.py or simulation/battle.py tick loops (wired in scenario only)~~ *(resolved Phase 37 — battle.py routes DEW via route_engagement)* | [phase-28.5.md — Postmortem](phase-28.5.md#postmortem) |
| 28.5 | No scenario YAML references dew_config (engine can be created but no scenarios exercise it) | [phase-28.5.md — Postmortem](phase-28.5.md#postmortem) |
| 28.5 | ADUnitType.DEW not handled in air defense engagement logic (enum exists but no routing) | [phase-28.5.md — Postmortem](phase-28.5.md#postmortem) |
| 28.5 | ~~route_engagement() not called from battle.py (uses execute_engagement directly) — DEW routing untested in loop~~ *(resolved Phase 37 — battle.py calls route_engagement for all engagements)* | [phase-28.5.md — Postmortem](phase-28.5.md#postmortem) |
| 32 | ~~`config_overrides` accepted and stored but not applied to engine (calibration_overrides not injected before ScenarioLoader.load)~~ *(resolved Phase 37 — deep merge before load)* | [phase-32.md — Postmortem](phase-32.md#postmortem) |
| 32 | ~~`GET /api/meta/terrain-types` returns hardcoded list instead of deriving from TerrainConfig or data~~ *(resolved Phase 39d — uses LandCover enum)* | [phase-32.md — Postmortem](phase-32.md#postmortem) |
| 34 | ~~`useBatchProgress` hook has no dedicated test file~~ *(resolved Phase 39a — 4 dedicated tests)* | [phase-34.md — Postmortem](phase-34.md#postmortem) |
| 34 | ~~RunDetailPage tests don't cover cancelled/error run states~~ *(resolved Phase 39a — 2 tests)* | [phase-34.md — Postmortem](phase-34.md#postmortem) |
| 34 | ~~Analysis API responses untyped (`Record<string, unknown>`) — compare/sweep return free-form dicts~~ *(resolved Phase 39a — typed CompareResult/SweepResult)* | [phase-34.md — Postmortem](phase-34.md#postmortem) |
| 34 | ~~Hardcoded morale state names and event type strings in eventProcessing.ts~~ *(resolved Phase 39a — exported constants ENGAGEMENT_EVENTS, MORALE_EVENTS)* | [phase-34.md — Postmortem](phase-34.md#postmortem) |
| 34 | ~~Force time series reconstruction assumes no reinforcements (only counts destructions)~~ *(resolved Phase 37 — handles ReinforcementArrivedEvent)* | [phase-34.md — Postmortem](phase-34.md#postmortem) |
| 35 | Frame data uses compact keys in storage but API expands to full names — slight redundancy | [phase-35.md — Known Limitations](phase-35.md#known-limitations) |
| 35 | `terrain_json` and `frames_json` stored as TEXT blobs — no indexing, large runs may produce 2MB+ frames | [phase-35.md — Known Limitations](phase-35.md#known-limitations) |
| 35 | ~~`useViewportControls` hook has no dedicated test file (exercised indirectly via TacticalMap)~~ *(resolved Phase 39a — 4 dedicated tests)* | [phase-35.md — Known Limitations](phase-35.md#known-limitations) |
| 35 | ~~Only `ForceStrengthChart` shows the tick sync marker line — other charts don't~~ *(resolved Phase 38c — all 4 charts show tick sync + bidirectional click)* | [phase-35.md — Known Limitations](phase-35.md#known-limitations) |
| 35 | ~~Frame capture interval is not configurable~~ *(resolved Phase 39b — RunSubmitRequest.frame_interval)* | [phase-35.md — Known Limitations](phase-35.md#known-limitations) |
| 35 | No keyboard shortcuts for playback (deferred to Phase 36) | [phase-35.md — Known Limitations](phase-35.md#known-limitations) |
| 37 | 8 legacy-format scenarios can't load through API (missing campaign schema fields) | [phase-37.md — Known Limitations](phase-37.md#known-limitations) |
| 37 | DEW hit in battle loop always results in destruction (no partial damage/disable) | [phase-37.md — Known Limitations](phase-37.md#known-limitations) |
| 38 | Plotly charts don't use `plotly_dark` template when dark mode is active (cosmetic) | [phase-38.md — Known Limitations](phase-38.md#known-limitations) |
| 38 | No separate dark terrain color palette (elevation shading brightness modulation covers the need) | [phase-38.md — Known Limitations](phase-38.md#known-limitations) |
| 40 | No fire-on-move accuracy penalty (only deployed weapon skip) | [phase-40.md — Known Limitations](phase-40.md#known-limitations) |
| 40 | Posture doesn't affect movement speed | [phase-40.md — Known Limitations](phase-40.md#known-limitations) |
| 41 | Cover from buildings/fortifications additive with terrain cover (potential double-count) | [phase-41.md — Known Limitations](phase-41.md#known-limitations) |
| 42 | Suwalki Gap and Taiwan Strait stall at max_ticks — need additional victory conditions | [phase-42.md — Known Limitations](phase-42.md#known-limitations) |
| 42 | Rally radius (500m) and friendly count threshold hardcoded, not configurable | [phase-42.md — Known Limitations](phase-42.md#known-limitations) |
| 42 | No per-scenario ROE configuration in existing scenario YAMLs | [phase-42.md — Known Limitations](phase-42.md#known-limitations) |

## Conventions

- Each phase file is a **living document** — updated as work happens, not just at the end.
- Sections within a phase: Summary, What Was Built, Design Decisions, Deviations from Plan, Issues & Fixes, Open Questions, Known Limitations, Lessons Learned.
- When a decision in one phase affects another, note it and cross-reference.
- **Known Limitations / Post-MVP Refinements**: every phase should document deliberate simplifications. The index table above aggregates them for easy review.
- **Post-MVP phases (11+)**: Same devlog conventions apply. Create `phase-{N}.md` when work begins. Update the table above from "Planned" → "In Progress" → "**Complete**" with link. New limitations discovered during post-MVP work must be added to both the phase devlog AND the refinement index above, AND the deficit-to-phase mapping in `development-phases-post-mvp.md`.
- **Deficit resolution**: When a post-MVP phase resolves a deficit from the index above, mark it with a strikethrough and note which phase resolved it. Update the deficit-to-phase mapping in `development-phases-post-mvp.md` accordingly.

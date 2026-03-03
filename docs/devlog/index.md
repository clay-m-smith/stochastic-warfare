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
| 12 | Deep Systems Rework | Planned | — |
| 13 | Performance Optimization | Planned | — |
| 14 | Tooling & Developer Experience | Planned | — |
| 15 | Real-World Terrain & Data Pipeline | Planned | — |
| 16 | Electronic Warfare | Planned | — |
| 17 | Space & Satellite Domain | Planned | — |
| 18 | NBC/CBRN Effects | Planned | — |
| 19 | Doctrinal AI Schools | Planned | — |
| 20 | WW2 Era | Planned | — |
| 21 | WW1 Era | Planned | — |
| 22 | Napoleonic Era | Planned | — |
| 23 | Ancient & Medieval Era | Planned | — |
| 24 | Unconventional & Prohibited Warfare | Planned | — |

## Post-MVP Refinement Index

Known limitations and deferred improvements logged during implementation. Review these after MVP is functional.

| Phase | Item | Section |
|-------|------|---------|
| 0 | Checkpoint format longevity (pickle fragility) | [phase-0.md — Open Questions](phase-0.md#open-questions) |
| 3 | ~~Track-to-target association needs nearest-neighbor gating~~ *(resolved Phase 11b)* | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | Environment data threading (caller responsibility) | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | ~~Passive sonar bearing is placeholder (random, not geometric)~~ *(resolved Phase 11b)* | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | ~~No sensor FOV filtering against observer heading~~ *(resolved Phase 11b)* | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | ~~Single-scan detection (no dwell/integration gain)~~ *(resolved Phase 11b)* | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | Test coverage gap (296→334 vs planned 455; backfilled C2-facing APIs) | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 4 | ~~Ballistic trajectory uses simplified drag (no Mach-dependent Cd)~~ *(resolved Phase 11a)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | ~~DeMarre penetration approximation (no obliquity, composite, reactive armor)~~ *(resolved Phase 11a)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | HEAT penetration is range-independent | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Submarine evasion simplified probability model | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Mine trigger model lacks detailed ship signature interaction | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Carrier ops deck management abstracted (no individual spot tracking) | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Morale Markov is discrete-time (not continuous-time) | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | PSYOP model is simplified effectiveness roll | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Naval damage control lacks compartment flooding model | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Air combat lacks detailed flight dynamics / energy-maneuverability | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | ~~Environment→combat coupling partial: air_combat, air_defense, naval_surface, indirect_fire lack env coupling~~ *(resolved Phase 11a)* | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 5 | No multi-hop propagation (single hop issuer→recipient only) | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | No terrain-based LOS check for communications | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | Simplified FSCL (east-west line, not arbitrary polyline) | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | No ATO planning cycle (structures only, generation deferred to Phase 9/Future) | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | No JTAC/FAC observer model for CAS | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | Messenger comm type has no terrain traversal or intercept risk | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 6 | No supply optimization solver (pull-based nearest depot only) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No multi-echelon supply chain (direct depot-to-unit) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Simplified transport vulnerability (no escort effects) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Medical M/M/c queueing approximate (exponential service) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | ~~Engineering times deterministic (no stochastic variation)~~ *(resolved Phase 11c)* | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | ~~No fuel gating on movement (tracked but not enforced)~~ *(resolved Phase 11c)* | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Blockade effectiveness simplified (flat per-ship probability) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Captured supply efficiency flat 50% (no compatibility check) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No local water procurement (always from rear depots) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No ammunition production (scenario-defined depots only) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | VLS non-reloadable-at-sea enforcement deferred to naval combat integration | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 7 | 73 Easting exchange_ratio = inf (detection asymmetry prevents blue losses) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | ~~No fire rate limiting (units fire once per tick regardless of ROF)~~ *(resolved Phase 11a)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | ~~Uniform target_size_modifier (applies to both sides equally)~~ *(resolved Phase 11a)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | ~~No wave attack modeling (all units advance simultaneously)~~ *(resolved Phase 11c)* | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Pre-scripted behavior only (no tactical AI, deferred to Phase 8) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Falklands simplified — Sheffield attack only, no San Carlos raids | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Synthetic terrain (programmatic heightmaps, not real topographic data) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | No logistics in validation scenarios (short engagements) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | No C2 propagation in validation (direct behavior, no order chain) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Simplified force compositions (representative samples, not complete OOB) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 8 | Named doctrinal schools (Clausewitzian AI, Sun Tzu AI) deferred to Future Phases | [phase-8.md — Known Limitations](phase-8.md#known-limitations--post-mvp-refinements) |
| 8 | COA wargaming is analytical (Lanchester), not full nested simulation | [phase-8.md — Known Limitations](phase-8.md#known-limitations--post-mvp-refinements) |
| 8 | No terrain-specific COA generation (e.g., no river crossing planning detail) | [phase-8.md — Known Limitations](phase-8.md#known-limitations--post-mvp-refinements) |
| 8 | Implied task tables are simplified (not full FM 5-0 comprehensive list) | [phase-8.md — Known Limitations](phase-8.md#known-limitations--post-mvp-refinements) |
| 8 | No multi-echelon simultaneous planning (each commander plans independently) | [phase-8.md — Known Limitations](phase-8.md#known-limitations--post-mvp-refinements) |
| 8 | Estimates update periodically, not reactively to every event | [phase-8.md — Known Limitations](phase-8.md#known-limitations--post-mvp-refinements) |
| 8 | Stratagems are opportunity-evaluated, not proactively planned in COA | [phase-8.md — Known Limitations](phase-8.md#known-limitations--post-mvp-refinements) |
| 8 | ~~Brigade echelon decision hardcodes echelon_level=9 in result (cosmetic)~~ *(resolved Phase 11d)* | [phase-8.md — Known Limitations](phase-8.md#known-limitations--post-mvp-refinements) |
| 9 | No force aggregation/disaggregation — all units at individual resolution | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | Single-threaded simulation loop (required for deterministic PRNG replay) | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | No auto-resolve — every engagement runs full tactical resolution | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | Simplified strategic movement (no detailed operational pathfinding) | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | Fixed reinforcement schedule (no Poisson/stochastic arrivals) | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | No naval campaign management (structurally supported but untested) | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | Synthetic terrain only (programmatic heightmaps, not real topographic data) | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | LOS cache is per-tick only (cleared each tick after movement) | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | No weather evolution mid-campaign beyond WeatherEngine.step() | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | Viewshed vectorization deferred (lower priority) | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 9 | STRtree for infrastructure spatial queries still deferred | [phase-9.md — Known Limitations](phase-9.md#known-limitations--post-mvp-refinements) |
| 10 | No fire rate limiting — units fire once per tick regardless of ROF (inherited) | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |
| 10 | No wave attack modeling — all red units advance simultaneously (inherited) | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |
| 10 | Campaign AI decisions coarse — OODA at echelon timing, may not produce tactical posture changes in short runs | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |
| 10 | Simplified force compositions — representative samples, not complete historical OOB | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |
| 10 | Synthetic terrain — programmatic heightmaps, not real topographic data | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |
| 10 | Fixed reinforcement schedule — deterministic arrival, no stochastic variation | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |
| 10 | No force aggregation/disaggregation — all units individually tracked | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |
| 10 | AI expectation matching approximate — string-based posture detection | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |
| 10 | Campaign metrics proxy territory control via survival fraction not spatial | [phase-10.md — Known Limitations](phase-10.md#known-limitations--post-mvp-refinements) |

## Conventions

- Each phase file is a **living document** — updated as work happens, not just at the end.
- Sections within a phase: Summary, What Was Built, Design Decisions, Deviations from Plan, Issues & Fixes, Open Questions, Known Limitations, Lessons Learned.
- When a decision in one phase affects another, note it and cross-reference.
- **Known Limitations / Post-MVP Refinements**: every phase should document deliberate simplifications. The index table above aggregates them for easy review.
- **Post-MVP phases (11+)**: Same devlog conventions apply. Create `phase-{N}.md` when work begins. Update the table above from "Planned" → "In Progress" → "**Complete**" with link. New limitations discovered during post-MVP work must be added to both the phase devlog AND the refinement index above, AND the deficit-to-phase mapping in `development-phases-post-mvp.md`.
- **Deficit resolution**: When a post-MVP phase resolves a deficit from the index above, mark it with a strikethrough and note which phase resolved it. Update the deficit-to-phase mapping in `development-phases-post-mvp.md` accordingly.

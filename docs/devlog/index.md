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
| 8 | AI & Planning | Not started | — |
| 9 | Simulation Orchestration | Not started | — |
| 10 | Campaign Validation | Not started | — |

## Post-MVP Refinement Index

Known limitations and deferred improvements logged during implementation. Review these after MVP is functional.

| Phase | Item | Section |
|-------|------|---------|
| 0 | Checkpoint format longevity (pickle fragility) | [phase-0.md — Open Questions](phase-0.md#open-questions) |
| 3 | Track-to-target association needs nearest-neighbor gating | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | Environment data threading (caller responsibility) | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | Passive sonar bearing is placeholder (random, not geometric) | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | No sensor FOV filtering against observer heading | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | Single-scan detection (no dwell/integration gain) | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 3 | Test coverage gap (296→334 vs planned 455; backfilled C2-facing APIs) | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |
| 4 | Ballistic trajectory uses simplified drag (no Mach-dependent Cd) | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | DeMarre penetration approximation (no obliquity, composite, reactive armor) | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | HEAT penetration is range-independent | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Submarine evasion simplified probability model | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Mine trigger model lacks detailed ship signature interaction | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Carrier ops deck management abstracted (no individual spot tracking) | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Morale Markov is discrete-time (not continuous-time) | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | PSYOP model is simplified effectiveness roll | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Naval damage control lacks compartment flooding model | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Air combat lacks detailed flight dynamics / energy-maneuverability | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 4 | Environment→combat coupling partial: only hit_probability (visibility), ballistics (wind/temp), air_ground (weather/night) wired; air_combat, air_defense, naval_surface, indirect_fire lack env coupling | [phase-4.md — Known Limitations](phase-4.md#known-limitations--post-mvp-refinements) |
| 5 | No multi-hop propagation (single hop issuer→recipient only) | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | No terrain-based LOS check for communications | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | Simplified FSCL (east-west line, not arbitrary polyline) | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | No ATO planning cycle (structures only, generation deferred to Phase 8) | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | No JTAC/FAC observer model for CAS | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 5 | Messenger comm type has no terrain traversal or intercept risk | [phase-5.md — Known Limitations](phase-5.md#known-limitations--deferred-items) |
| 6 | No supply optimization solver (pull-based nearest depot only) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No multi-echelon supply chain (direct depot-to-unit) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Simplified transport vulnerability (no escort effects) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Medical M/M/c queueing approximate (exponential service) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Engineering times deterministic (no stochastic variation) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No fuel gating on movement (tracked but not enforced) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Blockade effectiveness simplified (flat per-ship probability) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | Captured supply efficiency flat 50% (no compatibility check) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No local water procurement (always from rear depots) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | No ammunition production (scenario-defined depots only) | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 6 | VLS non-reloadable-at-sea enforcement deferred to naval combat integration | [phase-6.md — Known Limitations](phase-6.md#known-limitations) |
| 7 | 73 Easting exchange_ratio = inf (detection asymmetry prevents blue losses) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | No fire rate limiting (units fire once per tick regardless of ROF) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Uniform target_size_modifier (applies to both sides equally) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | No wave attack modeling (all units advance simultaneously) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Pre-scripted behavior only (no tactical AI, deferred to Phase 8) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Falklands simplified — Sheffield attack only, no San Carlos raids | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Synthetic terrain (programmatic heightmaps, not real topographic data) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | No logistics in validation scenarios (short engagements) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | No C2 propagation in validation (direct behavior, no order chain) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |
| 7 | Simplified force compositions (representative samples, not complete OOB) | [phase-7.md — Known Limitations](phase-7.md#known-limitations--post-mvp-refinements) |

## Conventions

- Each phase file is a **living document** — updated as work happens, not just at the end.
- Sections within a phase: Summary, What Was Built, Design Decisions, Deviations from Plan, Issues & Fixes, Open Questions, Known Limitations, Lessons Learned.
- When a decision in one phase affects another, note it and cross-reference.
- **Known Limitations / Post-MVP Refinements**: every phase should document deliberate simplifications. The index table above aggregates them for easy review.

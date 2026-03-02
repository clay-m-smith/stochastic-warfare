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
| 5 | C2 Infrastructure | Not started | — |
| 6 | Logistics & Supply | Not started | — |
| 7 | Engagement Validation | Not started | — |
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

## Conventions

- Each phase file is a **living document** — updated as work happens, not just at the end.
- Sections within a phase: Summary, What Was Built, Design Decisions, Deviations from Plan, Issues & Fixes, Open Questions, Known Limitations, Lessons Learned.
- When a decision in one phase affects another, note it and cross-reference.
- **Known Limitations / Post-MVP Refinements**: every phase should document deliberate simplifications. The index table above aggregates them for easy review.

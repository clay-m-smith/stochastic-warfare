# Development Log

Rolling record of implementation decisions, changes, and lessons learned across all phases of Stochastic Warfare development.

## Phases

| Phase | Focus | Status | Log |
|-------|-------|--------|-----|
| 0 | Project Scaffolding | **Complete** | [phase-0.md](phase-0.md) |
| 1 | Terrain & Environment Foundation | **Complete** | [phase-1.md](phase-1.md) |
| 2 | Entity System & Movement | **Complete** | [phase-2.md](phase-2.md) |
| 3 | Detection & Intelligence | **Complete** | [phase-3.md](phase-3.md) |
| 4 | Combat Resolution | Not started | — |
| 5 | Morale & C2 | Not started | — |
| 6 | Logistics | Not started | — |
| 7 | Simulation Orchestration | Not started | — |
| 8 | Validation & Tuning | Not started | — |

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
| 3 | Test coverage gap (296 vs planned 455) | [phase-3.md — Known Limitations](phase-3.md#known-limitations--post-mvp-refinements) |

## Conventions

- Each phase file is a **living document** — updated as work happens, not just at the end.
- Sections within a phase: Summary, What Was Built, Design Decisions, Deviations from Plan, Issues & Fixes, Open Questions, Known Limitations, Lessons Learned.
- When a decision in one phase affects another, note it and cross-reference.
- **Known Limitations / Post-MVP Refinements**: every phase should document deliberate simplifications. The index table above aggregates them for easy review.

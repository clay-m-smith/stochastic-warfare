# Stochastic Warfare

**High-fidelity stochastic wargame simulator** -- multi-scale, multi-domain, multi-era.

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-partitioned_validation-blue)
![Phase](https://img.shields.io/badge/phase-117_COMPLETE-brightgreen)

---

## What Is This?

Stochastic Warfare combines a headless Python simulation engine, FastAPI
service, and React web application. It models warfare across multiple scales --
from individual unit engagements through tactical battles, operational
battlefields, and multi-day strategic campaigns. Outcomes use stochastic and
signal-processing-inspired models including Markov chains, Monte Carlo methods,
Kalman filters, Poisson processes, queueing theory, and SNR-based detection.

## Key Capabilities

- **Multi-scale simulation** -- strategic (hours), operational (minutes), and tactical (seconds) resolution with automatic scale switching
- **Multi-domain warfare** -- ground, air, and naval combat plus gated GPS,
  SATCOM, ISR, early warning, direct-ascent kinetic ASAT, electronic warfare,
  cyber, and CBRN effects; unsupported co-orbital/laser ASAT assets fail
  explicitly
- **Multi-era coverage** -- Modern (Cold War--present), WW2, WW1, Napoleonic, and Ancient/Medieval eras with era-specific mechanics
- **Stochastic models throughout** -- 10+ mathematical models (Markov, Monte Carlo, Kalman, Poisson, queueing, Lanchester, Wayne Hughes salvo, Boyd OODA, Beer-Lambert DEW)
- **AI commanders** -- 9 doctrinal schools with OODA decision cycles when
  scenarios provide strict all-side commander profiles and valid school
  assignments
- **Historical scenario catalog** -- source-backed scenario metadata,
  current-engine regressions, and a typed claim ledger plus production
  outcome-envelope runner; the current ledger exposes zero
  production-validated scenarios

## Architecture at a Glance

The engine is composed of 12 top-level modules with a strict one-way dependency graph:

```
core -> coordinates -> terrain -> environment -> entities -> movement
  -> detection -> combat -> morale -> c2 -> logistics -> simulation
```

Dependencies flow downward only. Entities hold data; modules implement behavior (ECS-like separation). All randomness flows through per-module PRNG streams for deterministic reproducibility.

## Getting Started

### Prerequisites

- **Python >= 3.12** (pinned to 3.12.10 via `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** -- used exclusively for package management

### Quick Setup

```bash
uv sync --locked --extra dev --extra api --extra terrain --extra mcp
uv run --no-sync python scripts/validate_test_partitions.py \
  --output artifacts/partition-audit/manifest.json
uv run --no-sync python scripts/run_pytest_partition.py standard \
  --manifest artifacts/standard/manifest.json \
  --junit artifacts/standard/junit.xml --forbid-skips \
  --timeout-seconds 2700
```

The authoritative Python union is the audited, disjoint set `standard`,
`slow-only`, `benchmark-only`, `slow-benchmark`, `api`, and `e2e`. PR/main CI
runs the audit plus `standard`, `api`, `e2e`, and the overlapping `terrain`
dependency profile. Weekly/manual CI runs the three marker partitions in
deterministic shards. `benchmark-policy` is also an overlapping focused
profile, not a seventh partition. Phase 115 routes routine 73 Easting through
a strict version-4 non-timing workload transition while retaining version-3
runtime-input normalization. `transition_qualified` proves only the exact
classified workload/semantic handoff and is not a speed, default-morale, or
historical-fidelity result. Phase 116 has promoted the clean Phase 115 endpoint
and ordinary version-4 paired gating has resumed; Golan remains manual.

The Phase 116 closure audit enumerates exactly 12,459 nodes:
`standard` 11,953, `slow-only` 110, `benchmark-only` 87, `slow-benchmark` 5,
API 263, and E2E 41. All 11,953 standard nodes and every complete benchmark
partition/profile passed; data, determinism, scenario, static, documentation,
cross-document, and postmortem gates also passed. The owner accepted contended
long-run evidence only with an explicit qualification: capped API/E2E and slow
runs, pending clean-start Khafji reproduction, and inconclusive final timing
dispersion are not called passes. Debecka's 4/10 result remained a signal;
Phase 117 records that current-engine regression evidence while keeping its
historical claim unsupported. Hosted CI remains the final independent environment control. Phase
116 is complete and REM-029 is closed. Exact evidence is in the
[Phase 116 devlog](devlog/phase-116.md).

Phase 117 completed the REM-030 claim inventory, typed study plan,
`SimulationRuntimeFactory`-owned execution route, joint-coverage evaluator,
digest-bearing artifact, accepted-evidence gate, and conservative API/UI
status surface. The retained 73 Easting study is a completed `FAIL`: 0/20 runs
jointly met its declared envelope, its one-sided lower confidence bound is
0.0, and it is not promotion-eligible. The catalog therefore remains at zero
production-validated scenarios. See the
[contract](specs/historical-outcome-envelope-integrity.md) and
[artifact](evidence/phase-117/73-easting-phase117.json).

See the [Getting Started Guide](guide/getting-started.md) for a complete tutorial including running your first scenario.

## Explore the Documentation

| Section | What You'll Find |
|---------|-----------------|
| [Getting Started](guide/getting-started.md) | Installation, first scenario run, understanding output |
| [Web UI Guide](guide/web-ui.md) | Running the web application, browsing scenarios, viewing results, editing configs |
| [Scenario Library](guide/scenarios.md) | Complete scenario catalog, YAML format reference |
| [Architecture](concepts/architecture.md) | Module design, simulation loop, spatial model, engine wiring |
| [Mathematical Models](concepts/models.md) | All 10 stochastic models with formulas and worked examples |
| [API Reference](reference/api.md) | Key classes, methods, configuration, usage patterns |
| [Era Reference](reference/eras.md) | All 5 eras with mechanics, units, and scenarios |
| [Units & Equipment](reference/units.md) | Unit data model, modern + historical unit catalogs |

## Project Status

| Block | Phases | Focus | Status |
|-------|--------|-------|--------|
| MVP | 0--10 | Core engine (terrain through campaign validation) | **Complete** |
| Post-MVP | 11--24 | Fidelity, EW, Space, CBRN, AI schools, 4 historical eras, unconventional warfare | **Complete** |
| Block 2 | 25--30 | Integration, polish, data expansion, scenarios | **Complete** |
| Block 3 | 31--36 | Documentation site, API, frontend, visualization | **Complete** |
| Block 4 | 37--39 | Integration fixes, map enhancements, packaging | **Complete** |
| Block 5 | 40--48 | Core combat fidelity — battle loop wiring, terrain interaction, ROE, composite victory, deficit resolution | **Complete** |
| Block 6 | 49--57 | Final tightening — calibration hardening, combat polish, engine wiring, validation | **Complete** |
| Block 7 | 58--67 | Final engine hardening — structural verification, environment wiring, engine integration | **Complete** |
| Block 8 | 68--82 | Consequence enforcement, scenario expansion, postmortem & documentation | **Complete** |
| Block 9 | 83--91 | Performance at scale — profiling, spatial culling, LOD, parallelism | **Complete** |
| Block 10 | 92--97 | UI depth & engine exposure — analytics, frame enrichment, metadata | **Complete** |
| Block 11 | 98--104 | Current-engine regression scenarios and deployment polish | **Complete** |
| Block 12 | 105--114 | Integrity remediation against production-path evidence | **Complete** |
| Block 13 | 115--127 | Integrity follow-ups | **Active** |
| Block 14 | 128--130 | Targeting authorization, topology, and selection follow-ups | **Planned** |
| Block 15 | 131 | Sensor covariance and predictive-tracking integrity | **Planned** |
| Block 16 | 132 | Scripted scenario action integrity | **Planned** |
| Block 17 | 133 | Active deception checkpoint integrity | **Planned** |
| Block 18 | 134 | 73 Easting source-synchronous engagement fidelity | **Planned** |
| Block 19 | 135--137 | Package-bound accepted-evidence attestation, Web UI semantics, and Escalation/DEW configuration integrity | **Planned** |

Phases 105 through 117 and Block 12 are complete. Phase 116 implements the
strict format-116 roster-backed ordinary-contact, fusion-alias,
bounded-witness, targeting, and DETECTION RNG continuation contract, and
REM-029 is closed. Its long-run evidence carries an explicit owner-approved
contention qualification. See the
[Phase 116 devlog](devlog/phase-116.md), the
[contact-continuation specification](specs/fog-of-war-contact-continuation.md), and the
[remediation backlog](remediation-backlog.md) for exact evidence and known
coverage boundaries. The YAML data catalog defines units, weapons, ammunition
types, sensors, signatures, doctrines, commanders, formation templates, and
modern plus historical scenarios across five eras.

Block 13 is active with Phase 117 / REM-030 complete and closed. Its production
historical-validation boundary retains a truthful failed study and no claim
has been promoted. Phase 118 is next and has not started. Phase 115 also records REM-041 through
REM-043 for the planned Block 14 follow-ups rather than absorbing them into its
claim.
REM-044 separately assigns sourced sensor covariance and atomic predictive
tracking to Phase 131 in planned Block 15.
REM-045 assigns typed, fail-closed, exact-once Fallujah scripted actions to
Phase 132 in planned Block 16; Phase 115's 200-second current regression does
not reach the first authored action at H+7.
REM-046 assigns complete active/inactive decoy state, signature topology, and
single-owner DETECTION RNG continuation to Phase 133 in planned Block 17;
Phase 116 rejects non-pristine deception state instead of accepting loss.
REM-047 assigns the frozen 73 Easting engagement-fidelity miss to Phase 134 in
planned Block 18. REM-048 assigns build-time/no-`.git` accepted-evidence
attestation to Phase 135 in planned Block 19. Phase 117's local evidence proves
only the packaged-loader boundary for the current zero-accepted catalog; the
hosted image smoke is configured and pending the phase push.
REM-049 assigns the remaining replay/export/editor/analysis Web UI semantic
integrity boundary to Phase 136 in Block 19; REM-041 continues to own complete
authorized side-safe FOW exposure.
REM-050 assigns strict consumed Escalation/DEW configuration and a real
configured DEW engagement to Phase 137 in Block 19; current escalation tuning
is discarded and DEW block presence is not outcome evidence.
The changed 73 Easting loadout/configuration identity was handled by the strict
version-4 non-timing transition contract; it is not a paired performance pass.
Phase 116 subsequently promoted that clean endpoint to the ordinary paired
reference.

## License

[PolyForm Noncommercial License 1.0.0](https://github.com/clay-m-smith/stochastic-warfare/blob/main/LICENSE.md) -- free for personal, academic, and research use. Commercial/institutional use requires a separate license (claymsmith1@gmail.com).

# Stochastic Warfare

**High-fidelity stochastic wargame simulator** -- multi-scale, multi-domain, multi-era.

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-partitioned_validation-blue)
![Phase](https://img.shields.io/badge/phase-115_COMPLETE-brightgreen)

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
- **Historical scenario catalog** -- source-backed scenario metadata and
  current-engine regressions; catalog-wide historical validity remains queued
  under [REM-030](remediation-backlog.md)

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
  --manifest artifacts/partition-audit/manifest.json \
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
classified workload/semantic handoff; the next phase must promote the clean
Phase 115 endpoint before ordinary paired gating resumes. It is not a speed,
default-morale, or historical-fidelity result. Golan remains manual.

The Phase 115 closure audit enumerates exactly 12,248 nodes:
`standard` 11,743, `slow-only` 110, `benchmark-only` 87, `slow-benchmark` 4,
API 263, and E2E 41. All 11,743 standard nodes and every complete benchmark
profile passed; data, determinism, scenario, frontend, static, and
documentation gates also passed. The owner accepted contended slow/API/E2E
evidence only with an explicit qualification: capped runs are not called
passes, the exact real database/API persistence witness passed on the host,
and Debecka's 4/10 result remains assigned to REM-030. Hosted CI remains the
final independent environment control. Phase 115 is complete and REM-028 is
closed. Exact evidence is in the [Phase 115 devlog](devlog/phase-115.md).

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
| Block 11 | 98--104 | Golden scenarios and deployment polish | **Complete** |
| Block 12 | 105--114 | Integrity remediation against production-path evidence | **Complete** |
| Block 13 | 115--127 | Integrity follow-ups | **Active** |
| Block 14 | 128--130 | Targeting authorization, topology, and selection follow-ups | **Planned** |
| Block 15 | 131 | Sensor covariance and predictive-tracking integrity | **Planned** |
| Block 16 | 132 | Scripted scenario action integrity | **Planned** |

Phases 105 through 115 and Block 12 are complete. Phase 115 implements the
strict sensing-aware targeting and format-115 checkpoint/exposure contract,
and REM-028 is closed. Its long-run evidence carries an explicit owner-approved
contention qualification. See the
[Phase 115 devlog](devlog/phase-115.md), the
[targeting specification](specs/sensing-aware-tactical-standoff.md), and the
[remediation backlog](remediation-backlog.md) for exact evidence and known
coverage boundaries. The YAML data catalog defines units, weapons, ammunition
types, sensors, signatures, doctrines, commanders, formation templates, and
modern plus historical scenarios across five eras.

Block 13 is active with Phase 116 / REM-029 next and unstarted. Phase 115 also
records REM-041 through REM-043 for the planned Block 14 follow-ups rather than
absorbing them into its claim.
REM-044 separately assigns sourced sensor covariance and atomic predictive
tracking to Phase 131 in planned Block 15.
REM-045 assigns typed, fail-closed, exact-once Fallujah scripted actions to
Phase 132 in planned Block 16; Phase 115's 200-second current regression does
not reach the first authored action at H+7.
The changed 73 Easting loadout/configuration identity is handled by the strict
version-4 non-timing transition contract; it cannot be reported as a paired
performance pass and must be promoted from the clean Phase 115 commit before
the next phase closes.

## License

[PolyForm Noncommercial License 1.0.0](https://github.com/clay-m-smith/stochastic-warfare/blob/main/LICENSE.md) -- free for personal, academic, and research use. Commercial/institutional use requires a separate license (claymsmith1@gmail.com).

# Stochastic Warfare

**High-fidelity stochastic wargame simulator** -- multi-scale, multi-domain, multi-era.

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-partitioned_validation-blue)
![Phase](https://img.shields.io/badge/phase-114_COMPLETE-brightgreen)

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
  --manifest artifacts/standard/manifest.json \
  --junit artifacts/standard/junit.xml --forbid-skips \
  --timeout-seconds 2700
```

The authoritative Python union is the audited, disjoint set `standard`,
`slow-only`, `benchmark-only`, `slow-benchmark`, `api`, and `e2e`. PR/main CI
runs the audit plus `standard`, `api`, `e2e`, and the overlapping `terrain`
dependency profile. Weekly/manual CI runs the three marker partitions in
deterministic shards. `benchmark-policy` is also an overlapping focused
profile, not a seventh partition. The routine 73 Easting paired gate uses the
version-3 typed, morale-neutral control-plane workload; it is not evidence for
default morale behavior or historical fidelity. Golan remains manual.

The Phase 114 closure audit enumerates exactly 11,903 nodes:
`standard` 11,445, `slow-only` 109, `benchmark-only` 62, `slow-benchmark` 4,
API 242, and E2E 41. All 11,903 passed with zero failures/errors/skips and six
declared warnings. The API partition ran on the host because this sandbox
currently loses an `aiosqlite` worker-thread wakeup before schema creation;
identical focused and full host runs passed, and hosted CI remains the final
environment control. The owner accepted the dispersed timing result only as
contention-qualified evidence and deferred clean confirmation until all cores
are free; no uncontended pass is claimed. Phase 114 and Block 12 are complete,
and REM-018 is closed. Exact evidence is in the [Phase 114 devlog](devlog/phase-114.md).

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
| Block 13 | 115--127 | Queued integrity follow-ups | **Planned** |

Phases 105 through 114 and Block 12 are complete. Phase 114 implements the
strict effective era-runtime and format-114 checkpoint contract, and REM-018
is closed. Its timing result carries an explicit owner-approved contention
qualification. See the
[Phase 114 devlog](devlog/phase-114.md), the
[era override specification](specs/era-override-execution.md), and the
[remediation backlog](remediation-backlog.md) for exact evidence and known
coverage boundaries. The YAML data catalog defines units, weapons, ammunition
types, sensors, signatures, doctrines, commanders, formation templates, and
modern plus historical scenarios across five eras.

## License

[PolyForm Noncommercial License 1.0.0](https://github.com/clay-m-smith/stochastic-warfare/blob/main/LICENSE.md) -- free for personal, academic, and research use. Commercial/institutional use requires a separate license (claymsmith1@gmail.com).

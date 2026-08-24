# Stochastic Warfare

**High-fidelity stochastic wargame simulator** -- multi-scale, multi-domain, multi-era.

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-partitioned_validation-blue)
![Engineering](https://img.shields.io/badge/engineering-consolidation_COMPLETE-green)

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

The engine's foundational packages follow a one-way dependency spine:

```
core -> coordinates -> terrain -> environment -> entities -> movement
  -> detection -> combat -> morale -> c2 -> logistics -> simulation
```

Dependencies flow toward orchestration; specialized domain packages join
through typed owners, and application adapters do not become runtime owners.
Entities hold data while domain modules implement behavior. Stochastic
decisions use `RNGManager`-owned conventional module streams or typed
identity-addressed indexed authority when execution order must not select a
different result.

## Getting Started

### Prerequisites

- **Python >= 3.12** (pinned to 3.12.10 via `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** -- used exclusively for package management

### Quick Setup

```bash
uv sync --locked --extra dev --extra api --extra terrain --extra mcp
uv run --no-sync stochastic-warfare run test_campaign \
  --seed 112 --max-ticks 1

uv run --no-sync python scripts/validate_test_partitions.py \
  --output artifacts/partition-audit/manifest.json
uv run --no-sync python scripts/run_pytest_partition.py standard \
  --audit-manifest artifacts/partition-audit/manifest.json \
  --manifest artifacts/standard/manifest.json \
  --junit artifacts/standard/junit.xml --forbid-skips \
  --timeout-seconds 2700
```

The authoritative Python test union is the audited, disjoint set `standard`,
`slow-only`, `benchmark-only`, `slow-benchmark`, `api`, and `e2e`. Routine CI
reuses one revision-bound collection manifest. Slow and benchmark partitions
and the 73 Easting paired comparison run nightly; Golan, historical studies,
calibration, and heavyweight profiling require explicit evidence workflows.
Generated reports stay below ignored `artifacts/`.

The contract-preserving consolidation before Phase 119 completed on
2026-08-23. It reorganized tests by subsystem, removed source-string and
delivery proxies, narrowed metadata scope, defined supported package artifacts,
and split large facades behind typed interfaces. It did not reinterpret
historical or performance evidence. Its status transition is valid only for a
revision whose final exact frozen-revision release gate is green.

See the [Getting Started Guide](guide/getting-started.md) for a complete tutorial,
or the [consolidation contract](specs/tiered-modular-monolith.md) for engineering
scope and proof obligations.

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

## Engineering Status

Phases 0 through 118 are complete; Phase 119 has not started. The current
consolidation is an engineering program between phases, not a simulation-model
phase. Its purpose is to make the repository easier to navigate and validate
without changing calibration, stochastic authority, or accepted outcomes.

| Track | Status | Source of truth |
|---|---|---|
| Tiered modular-monolith consolidation | **Complete** | [Postmortem](devlog/consolidation-tiered-modular-monolith.md#postmortem) |
| Current remediation sequence (Phases 119--127) | **Planned** | [Block 13 roadmap](development-phases-block13.md) |
| Later remediation blocks | **Planned** | [Backlog](remediation-backlog.md) |
| Completed phase history | **Retained** | [Phase index](devlog/index.md) |

Two negative evidence boundaries remain especially important:

- Phase 117 retained a completed 73 Easting study `FAIL`; no catalog scenario is
  promoted as production-validated. See the
  [historical outcome contract](specs/historical-outcome-envelope-integrity.md).
- Phase 118 validated detection culling, SoA selection, and parallel per-side
  detection, while scan scheduling and non-default LOD remain explicitly
  unsupported. Its transactional FOW path also retains a measured +25.906%
  workload-specific runtime regression assigned to REM-055. See the
  [performance integrity contract](specs/performance-flag-semantic-integrity.md).

The consolidation closed REM-052 and REM-053 through their canonical FOW
update and single-snapshot checkpoint boundaries. REM-055 remains open and
queued; the closure does not claim recovery of its measured runtime cost.

The communications models likewise do not imply a loaded production network:
REM-036 owns typed unit/link topology and end-to-end order delivery. The current
runtime fails safely when an endpoint is absent; it does not manufacture a
communications capability. All current limitations and their required proofs
are tracked in the [remediation backlog](remediation-backlog.md).

## License

[PolyForm Noncommercial License 1.0.0](https://github.com/clay-m-smith/stochastic-warfare/blob/main/LICENSE.md) -- free for personal, academic, and research use. Commercial/institutional use requires a separate license (claymsmith1@gmail.com).

# Stochastic Warfare

**High-fidelity stochastic wargame simulator** -- multi-scale, multi-domain, multi-era.

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-10%2C958_passing-brightgreen)
![Phase](https://img.shields.io/badge/phase-111_COMPLETE-brightgreen)

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
- **AI commanders** -- 9 doctrinal schools (Clausewitz, Maneuver, Attrition, AirLand Battle, Air Power, Sun Tzu, Deep Battle, Mahanian, Corbettian) with OODA decision cycles
- **Validated against history** -- 73 Easting, Falklands Naval, Golan Heights engagements and campaigns with Monte Carlo statistical comparison

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
uv sync --extra dev    # creates .venv, installs all deps including pytest/matplotlib
uv run python -m pytest --tb=short -q   # run the default-selected suite
```

The default selection excludes the `slow`, `benchmark`, `terrain`, `api`, and
`e2e` markers and ignores `tests/api` and `tests/e2e`. Run those boundaries
explicitly with the needed extras and `-o addopts=`; REM-013 tracks their
routine CI disclosure.

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
| Block 12 | 105--114 | Integrity remediation against production-path evidence | **In progress** |

Phases 105 through 111 are complete, including REM-012 time-on-target
production execution. Phase 112 is next and has not started.

Fresh Phase 111 completion baseline: **10,958 default-selected Python tests
passed** (21 skipped, 348 deselected, 6 warnings). The frontend was not rerun
because Phase 111 changed no frontend contract; its last verified Phase 108
baseline remains 418 tests.
See the
[remediation backlog](remediation-backlog.md) for current evidence and known
coverage boundaries. The YAML data catalog defines units, weapons, ammunition
types, sensors, signatures, doctrines, commanders, formation templates, and
modern plus historical scenarios across five eras.

## License

[PolyForm Noncommercial License 1.0.0](https://github.com/clay-m-smith/stochastic-warfare/blob/main/LICENSE.md) -- free for personal, academic, and research use. Commercial/institutional use requires a separate license (claymsmith1@gmail.com).

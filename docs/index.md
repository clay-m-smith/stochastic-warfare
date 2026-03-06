# Stochastic Warfare

**High-fidelity stochastic wargame simulator** -- multi-scale, multi-domain, multi-era.

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-7%2C384_passing-brightgreen)
![Phase](https://img.shields.io/badge/phase-32_Block--3_IN--PROGRESS-blue)

---

## What Is This?

Stochastic Warfare is a headless Python simulation engine that models warfare across multiple scales -- from individual unit engagements up through tactical battles, operational battlefields, and multi-day strategic campaigns. Every outcome is driven by stochastic and signal-processing-inspired models: Markov chains, Monte Carlo methods, Kalman filters, Poisson processes, queueing theory, and SNR-based detection theory.

## Key Capabilities

- **Multi-scale simulation** -- strategic (hours), operational (minutes), and tactical (seconds) resolution with automatic scale switching
- **Multi-domain warfare** -- ground, air, naval (surface + subsurface), space, electronic warfare, cyber, and CBRN effects fully integrated
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
uv run python -m pytest --tb=short -q   # run the test suite
```

See the [Getting Started Guide](guide/getting-started.md) for a complete tutorial including running your first scenario.

## Explore the Documentation

| Section | What You'll Find |
|---------|-----------------|
| [Getting Started](guide/getting-started.md) | Installation, first scenario run, understanding output |
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
| Block 3 | 31--36 | Documentation site, API, frontend, visualization | In Progress |

**7,384 tests** across ~210 test files. **~700 YAML data files** defining 125 units, 51 weapons, 63 ammunition types, sensors, signatures, 21 doctrines, 13 commanders, and 41 scenarios.

## License

[PolyForm Noncommercial License 1.0.0](https://github.com/clay-m-smith/stochastic-warfare/blob/main/LICENSE.md) -- free for personal, academic, and research use. Commercial/institutional use requires a separate license (claymsmith1@gmail.com).

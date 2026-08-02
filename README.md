# Stochastic Warfare

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-partitioned_validation-blue)
![Phase](https://img.shields.io/badge/phase-116_COMPLETE-brightgreen)

High-fidelity, high-resolution wargame simulator with a headless Python engine,
FastAPI service, and React frontend. Models warfare across multiple scales —
from individual engagements through tactical battles, operational battlefields,
and multi-day strategic campaigns — with stochastic and
signal-processing-inspired models throughout.

The simulator covers the modern era (Cold War to present) as its prototype
period and treats maritime warfare as a fully integrated domain alongside land
and air operations, not a deferred add-on. It includes source-backed historical
scenario data and current-engine regression tooling. A catalog-wide historical
validity claim requires the queued production-path work in
[REM-030](docs/remediation-backlog.md).

Core mathematical models include Markov chains (morale state transitions, weather), Monte Carlo methods (engagement and campaign outcome analysis), Kalman filters (enemy state estimation from noisy sensor data), Poisson processes (equipment breakdown), log-normal uncertainty (reinforcement arrival time), queueing theory (medical evacuation, supply bottlenecks), and SNR-based detection theory (unified across visual, thermal, radar, and acoustic sensors).

## Getting Started

### Prerequisites

- **Python >= 3.12** (pinned to 3.12.10 via `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** — used exclusively for package management (never bare `pip`)

### Setup

```bash
uv sync --extra dev    # creates .venv, installs all deps including pytest/matplotlib
```

### Running Tests

```bash
uv sync --locked --extra dev --extra api --extra terrain --extra mcp
uv run --no-sync python scripts/validate_test_partitions.py \
  --output artifacts/partition-audit/manifest.json
uv run --no-sync python scripts/run_pytest_partition.py standard \
  --manifest artifacts/partition-audit/manifest.json \
  --junit artifacts/standard/junit.xml --forbid-skips \
  --timeout-seconds 2700
```

The authoritative Python test union has six audited, pairwise-disjoint
partitions: `standard`, `slow-only`, `benchmark-only`, `slow-benchmark`, `api`,
and `e2e`. PR/main CI audits the union and runs `standard`, `api`, `e2e`, and
the overlapping `terrain` dependency profile. Weekly/manual CI runs the three
marker partitions in deterministic module-affine shards. `terrain` and
`benchmark-policy` are overlapping dependency/policy profiles, not extra union
members. During Phase 115, routine 73 Easting uses the strict version-4
non-timing workload-transition contract over unchanged version-3 runtime-input
normalization. `transition_qualified` proves only the exact classified
workload/semantic handoff; it is not a performance pass. Phase 116 has promoted
the clean Phase 115 endpoint and ordinary version-4 paired gating has resumed;
Golan remains a manual paired benchmark. All
Python commands use `uv run` so the project environment is selected without
manual activation.

The Phase 116 closure audit enumerates exactly 12,459 nodes in that disjoint
union: `standard` 11,953, `slow-only` 110, `benchmark-only` 87,
`slow-benchmark` 5, API 263, and E2E 41. All 11,953 standard nodes and every
complete benchmark partition/profile passed; data, determinism, scenario,
static, documentation, cross-document, and postmortem gates also passed. The
owner accepted contended long-run evidence with an explicit qualification:
API/E2E and two slow shards reached their containment limits, Khafji's clean
reproduction remained pending, and final paired timing dispersion was
inconclusive; none is called a pass. Debecka's 4/10 result remains a REM-030
signal rather than being tuned away. Hosted CI is the final independent
environment control. Exact commands, counts, warnings, exclusions, and
artifacts are in the [Phase 116 devlog](docs/devlog/phase-116.md).

Block 13 is active. Phase 115's sensing-aware tactical-standoff and format-115
targeting implementation is complete, and REM-028 is closed. Phase 116 /
REM-029 is complete and closed with format-116 ordinary-contact continuation.
Phase 117 / REM-030 is next and remains unstarted.
Phase 115's authorization,
mount/director-topology, and availability-aware-selection findings are tracked
separately as REM-041 through REM-043 in planned Block 14. The
sensor-covariance/predictive-tracking limitation surfaced by stable FOW track
reuse is REM-044 in planned Block 15.
The legacy Fallujah scripted-action lifecycle is REM-045 in planned Block 16;
declaration/reference loading is not dispatch/effect or exact-once continuation
evidence.
Active/inactive decoy checkpoint integrity is REM-046 in planned Block 17;
Phase 116 rejects non-pristine deception state rather than restoring an
incomplete signature or duplicate DETECTION RNG owner.
The intentional 73 Easting workload-identity change was handled by a strict
non-timing transition qualification, not by timing unequal workloads; Phase
116 subsequently promoted the clean endpoint to the ordinary paired gate.

## Quick Start (Web UI)

**Development mode** (two terminals):
```bash
bash scripts/dev.sh   # or .\scripts\dev.ps1 on Windows
# Open http://localhost:5173
```

**Production mode** (single command):
```bash
cd frontend && npm run build && cd ..
uv run python -m api
# Open http://localhost:8000
```

**Docker**:
```bash
docker build \
  --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" \
  -t stochastic-warfare .
docker run -p 8000:8000 stochastic-warfare
```

`SOURCE_REVISION` is a required, builder-supplied 40-character lowercase commit
attribution. Build from a clean checkout so that attribution names the source
being staged. Source checkouts remain Git-first: runtime preparation records
`HEAD`, whether the tree is dirty, and a content-sensitive worktree fingerprint,
and it never substitutes an image identity for an established but unverifiable
Git worktree.

Images intentionally contain no `.git` directory. After the locked Python
environment is installed, the build writes
`stochastic_warfare/_build_identity.json` with `SOURCE_REVISION` and a digest
of a strict manifest covering `stochastic_warfare/`, `api/`, `pyproject.toml`,
and `uv.lock`. Production runtime preparation recomputes that manifest, so a
missing or malformed identity, a source edit, or an unsupported source entry
fails closed. Scenario and catalog files are verified separately by the
runtime data revision. The Docker workflow supplies `GITHUB_SHA`, builds on
pull requests to `main`, pushes to `main`, and manual dispatches, then asserts
that `.git` is absent and runs a production-runtime identity smoke inside the
image.

## Architecture

### Module Dependency Chain

The engine is composed of 12 top-level modules with a strict one-way dependency graph:

```
core → coordinates → terrain → environment → entities → movement → detection → combat → morale → c2 → logistics → simulation
```

Dependencies flow downward only. Terrain never imports environment; environment may read terrain. Entities hold data while modules implement behavior (ECS-like separation).

### Simulation Loop

Hybrid tick-based + event-driven. The outer loop advances discrete ticks at variable resolution depending on scale:

| Scale | Tick Resolution | Manager |
|-------|----------------|---------|
| Strategic | 3,600s (1 hour) | `CampaignManager` |
| Operational | 300s (5 min) | `CampaignManager` |
| Tactical | 5s | `BattleManager` |

Events fire within ticks for fine-grained interactions (damage application, morale cascades, order propagation).

### Spatial Model

Layered hybrid across scales:

- **Graph** (strategic) — networkx supply networks, LOC routing
- **Grid** (operational/tactical) — raster terrain, LOS raycasting, pathfinding
- **Continuous** (unit-level) — ENU meter coordinates, precise engagement geometry

All raster grids share the convention: `Grid[0,0]` = SW corner, row increases northward, col increases eastward.

### Key Stochastic Models

| Model | Module | Purpose |
|-------|--------|---------|
| Markov chains | `morale/state`, `environment/weather` | State transitions (morale 5-state, weather evolution) |
| Monte Carlo | `validation/monte_carlo` | Engagement and campaign outcome distributions |
| Kalman filter | `detection/estimation` | 4-state enemy position/velocity tracking |
| Poisson processes | `logistics/maintenance` | Equipment breakdown (`1 - exp(-dt/MTBF)`) |
| Queueing theory (M/M/c) | `logistics/medical` | Priority-based medical evacuation |
| SNR detection (erfc) | `detection/detection` | Unified Pd across all sensor types |
| Lanchester attrition | `c2/planning/coa` | Analytical COA wargaming |
| Wayne Hughes salvo | `combat/naval_surface` | Missile exchange with leaker dynamics |
| Boyd OODA | `c2/ai/ooda` | Commander decision cycle as FSM |
| Log-normal delays | `c2/communications`, `logistics/transport` | Clausewitzian friction in C2 and supply |
| Beer-Lambert law | `combat/directed_energy` | Laser atmospheric transmittance for DEW |

For full architectural rationale, see [`docs/brainstorm.md`](docs/brainstorm.md).

## Project Structure

```
api/                      # REST API service layer [Phase 32]
  routers/                # FastAPI route handlers (scenarios, units, runs, analysis, meta)

frontend/                 # React frontend (Vite + TypeScript + Tailwind) [Phase 33]
  src/
    api/                  # Typed API client
    components/           # Shared components (Layout, Badge, Card, etc.)
    hooks/                # TanStack Query hooks
    pages/                # Scenario browser, unit catalog, runs, analysis
    lib/                  # Utility functions (format, era, domain)
    types/                # TypeScript interfaces mirroring api/schemas.py

stochastic_warfare/       # simulation engine
  core/                   # types, logging, RNG, clock, events, config, checkpoint
  coordinates/            # geodetic/UTM/ENU transforms, magnetic declination
  terrain/                # heightmap, classification, bathymetry, LOS, infrastructure
  environment/            # weather, astronomy, sea state, acoustics, EM propagation
  entities/               # unit definitions, equipment, organization, hierarchy
  movement/               # pathfinding, fatigue, formations, naval/air/amphibious
  detection/              # sensors, signatures, sonar, estimation, fog of war
  combat/                 # ballistics, damage, missiles, naval, air combat, IADS, strategic targeting
  morale/                 # state transitions, cohesion, stress, psychology, rout
  c2/                     # command, communications, ROE, orders, joint ops, mission command
    ai/                   # OODA, commander AI, doctrine, assessment, decisions, doctrinal schools
    planning/             # MDMP, mission analysis, COA generation, estimates
  logistics/              # supply, transport, maintenance, medical, engineering, production
  population/             # civilian regions, displacement, collateral, HUMINT, influence, insurgency
  escalation/             # escalation ladder, political pressure, consequences, war termination
  simulation/             # scenario loading, battle/campaign managers, engine
  validation/             # historical data, Monte Carlo, campaign validation
  ew/                     # electronic warfare: jamming, spoofing, ECCM, SIGINT, decoys
  space/                  # space & satellite: GPS, SATCOM, ISR, early warning, ASAT
  cbrn/                   # CBRN effects: agents, dispersal, contamination, protection, nuclear
  tools/                  # MCP server, analysis (narrative, tempo, comparison, sensitivity), visualization

data/                     # YAML data catalog
  units/                  # ground, air, naval, and support unit definitions
  weapons/                # guns, artillery, missiles, torpedoes, and other weapons
  ammunition/             # ammunition definitions
  sensors/                # sensor definitions
  signatures/             # signature profiles
  comms/                  # communication equipment definitions
  ew/                     # jammers, ECCM suites, SIGINT collectors, and decoys
  space/                  # constellations and ASAT definitions
  cbrn/                   # agents, nuclear weapons, and delivery systems
  organizations/          # TO&E definitions
  commander_profiles/     # commander personality profiles
  doctrine/               # national and generic doctrine templates
  schools/                # doctrinal school definitions
  logistics/
    supply_items/         # supply item definitions
    transport_profiles/   # transport profiles
    medical_facilities/   # medical facility definitions
  eras/                    # Era-specific data packages (WW2, WW1, Napoleonic, Ancient/Medieval)
  scenarios/              # modern, test, and historical-era scenario definitions

tests/                    # six audited disjoint Python test partitions
docs/                     # specs, brainstorm, devlog, development phases
```

For the full package tree and module decomposition, see [`docs/specs/project-structure.md`](docs/specs/project-structure.md).

## Development Status

Phases 105 through 116 and Block 12 are complete. Phase 116 implements one
typed, runtime-owned format-116 boundary for exact roster-backed ordinary
fog-of-war contact, fusion-alias, bounded-witness, targeting, and DETECTION RNG
continuation; REM-029 is closed. Its long-run evidence carries the explicit
owner-approved contention qualification above. See the
[Phase 116 devlog](docs/devlog/phase-116.md), the
[contact-continuation specification](docs/specs/fog-of-war-contact-continuation.md), the
[remediation backlog](docs/remediation-backlog.md), and the phase roadmaps for
the exact evidence and remaining boundaries. Block 13 remains active with
Phase 117 / REM-030 next and unstarted.

| Phase | Focus | Tests | Status |
|-------|-------|-------|--------|
| 0 | Project Scaffolding | 97 | Complete |
| 1 | Terrain & Environment Foundation | 270 | Complete |
| 2 | Entity System & Movement | 424 | Complete |
| 3 | Detection & Intelligence | 296 | Complete |
| 4 | Combat Resolution & Morale | 634 | Complete |
| 5 | C2 Infrastructure | 345 | Complete |
| 6 | Logistics & Supply | 336 | Complete |
| 7 | Engagement Validation | 188 | Complete |
| 8 | AI & Planning | 575 | Complete |
| 9 | Simulation Orchestration | 372 | Complete |
| 10 | Campaign Validation | 196 | Complete |
| 11 | Core Fidelity Fixes | 109 | Complete |
| 12 | Deep Systems Rework | 259 | Complete |
| 13 | Performance Optimization | 170 | Complete |
| 14 | Tooling & Developer Experience | 125 | Complete |
| 15 | Real-World Terrain & Data Pipeline | 97 | Complete |
| 16 | Electronic Warfare | 143 | Complete |
| 17 | Space & Satellite Domain | 149 | Complete |
| 18 | CBRN Effects | 155 | Complete |
| 19 | Doctrinal AI Schools | 189 | Complete |
| 20 | WW2 Era | 137 | Complete |
| 21 | WW1 Era | 182 | Complete |
| 22 | Napoleonic Era | 233 | Complete |
| 23 | Ancient & Medieval Era | 321 | Complete |
| 24 | Unconventional & Prohibited Warfare | 345 | Complete |
| 25 | Engine Wiring & Integration (Block 2) | 152 | Complete |
| 26 | Core Polish & Configuration (Block 2) | 82 | Complete |
| 27 | Combat System Completeness (Block 2) | 139 | Complete |
| 28 | Modern Era Data Package (Block 2) | 137 | Complete |
| 28.5 | Directed Energy Weapons (Block 2) | 112 | Complete |
| 29 | Historical Era Data Expansion (Block 2) | 164 | Complete |
| 30 | Scenario & Campaign Library (Block 2) | 196 | Complete |
| 31 | Documentation Site (Block 3) | 0 | Complete |
| 32 | API & Service Foundation (Block 3) | 77 | Complete |
| 33 | Frontend Foundation & Scenario Browser (Block 3) | 62 | Complete |
| 34 | Run Results & Analysis Dashboard (Block 3) | 65 | Complete |
| 35 | Tactical Map & Spatial Visualization (Block 3) | 71 | Complete |
| 36 | Scenario Tweaker & Polish (Block 3) | 59 | Complete |
| 37 | Integration Fixes & E2E Validation (Block 4) | 70 | Complete |
| 38 | Map & Chart Enhancements (Block 4) | 35 | Complete |
| 39 | Quality, Performance & Packaging (Block 4) | 22 | Complete |
| 40 | Battle Loop Foundation (Block 5) | 47 | **Complete** |
| 41 | Combat Depth (Block 5) | 51 | **Complete** |
| 42 | Tactical Behavior (Block 5) | 26 | **Complete** |
| 43 | Domain-Specific Resolution (Block 5) | 45 | **Complete** |
| 44 | Environmental & Subsystem Integration (Block 5) | 37 | **Complete** |
| 45 | Mathematical Model Audit & Hardening (Block 5) | 21 | **Complete** |
| 46 | Scenario Data Cleanup & Expansion (Block 5) | 57 | **Complete** |
| 47 | Full Recalibration & Validation (Block 5) | 38 | **Complete** |
| 48 | Block 5 Deficit Resolution (Block 5) | 34 | **Complete** |
| 49 | Calibration Schema Hardening (Block 6) | 51 | **Complete** |
| 50 | Combat Fidelity Polish (Block 6) | 40 | **Complete** |
| 51 | Naval Combat Completeness (Block 6) | 37 | **Complete** |
| 52 | Environmental Continuity (Block 6) | 32 | **Complete** |
| 53 | C2 & AI Completeness (Block 6) | 44 | **Complete** |
| 54 | Era-Specific & Domain Sub-Engine Wiring (Block 6) | 53 | **Complete** |
| 55 | Resolution & Scenario Migration (Block 6) | 43 | **Complete** |
| 56 | Performance & Logistics (Block 6) | 39 | **Complete** |
| 57 | Full Validation & Regression (Block 6) | 51 | **Complete** |
| 58 | Structural Verification & Core Combat Wiring (Block 7) | 60 | **Complete** |
| 59 | Atmospheric & Ground Environment Wiring (Block 7) | 48 | **Complete** |
| 60 | Obscurants, Fire, & Visual Environment (Block 7) | 53 | **Complete** |
| 61 | Maritime, Acoustic, & EM Environment (Block 7) | 71 | **Complete** |
| 62 | Human Factors, CBRN, & Air Combat Environment (Block 7) | 85 | **Complete** |
| 63 | Cross-Module Feedback Loops (Block 7) | 74 | **Complete** |
| 64 | C2 Friction & Command Delay (Block 7) | 60 | **Complete** |
| 65 | Space & EW Sub-Engine Activation (Block 7) | 43 | **Complete** |
| 66 | Unconventional, Naval, & Cleanup (Block 7) | 50 | **Complete** |
| 67 | Integration Validation & Recalibration (Block 7) | ~30 | **Complete** |
| 68 | Consequence Enforcement (Block 8) | 67 | **Complete** |
| 69 | C2 Depth (Block 8) | 41 | **Complete** |
| 70 | Performance Optimization (Block 8) | 24 | **Complete** |
| 71 | Missile & Carrier Ops Completion (Block 8) | 46 | **Complete** |
| 72 | Checkpoint & State Completeness (Block 8) | 139 | **Complete** |
| 73 | Historical Scenario Correctness (Block 8) | ~22 | **Complete** |
| 74 | Combat Engine Unit Tests (Block 8) | 472 | **Complete** |
| 75 | Simulation Core & Domain Unit Tests (Block 8) | 293 | **Complete** |
| 76 | API Robustness (Block 8) | 25 | **Complete** |
| 77 | Frontend Accessibility (Block 8) | 36 | **Complete** |
| 78 | P2 Environment Wiring (Block 8) | 49 | **Complete** |
| 79 | CI/CD & Packaging (Block 8) | 31 | **Complete** |
| 80 | API & Frontend Sync (Block 8) | 26 | **Complete** |
| 81 | Recalibration & Validation (Block 8) | ~20 | **Complete** |
| 82 | Postmortem & Documentation (Block 8) | 0 | **Complete** |
| 83 | Profiling Infrastructure (Block 9) | 13 | **Complete** |
| 84 | Spatial Culling & Scan Scheduling (Block 9) | 31 | **Complete** |
| 85 | LOD & Aggregation (Block 9) | 30 | **Complete** |
| 86 | Engagement & Calibration Optimization (Block 9) | 19 | **Complete** |
| 87 | Expanded Numba JIT (Block 9) | 40 | **Complete** |
| 88 | SoA Data Layer (Block 9) | 43 | **Complete** |
| 89 | Per-Side Parallelism (Block 9) | 21 | **Complete** |
| 90 | Validation & Benchmarking (Block 9) | ~20 | **Complete** |
| 91 | Scenario Recalibration & Regression (Block 9) | ~20 | **Complete** |
| 92 | API Analytics & Frame Enrichment (Block 10) | 20 | **Complete** |
| 93 | Results Dashboard Depth (Block 10) | 14 | **Complete** |
| 94 | Tactical Map Enrichment (Block 10) | 42 | **Complete** |
| 95 | Calibration & Scenario Editor Depth (Block 10) | 24 | **Complete** |
| 96 | Analysis & Event Interaction (Block 10) | 13 | **Complete** |
| 97 | Data Catalog & Block 10 Validation (Block 10) | 7 | **Complete** |
| 98 | Shared Prework — Gap Audit, Envelope Helpers, Depth Framework (Block 11) | 26 | **Complete** |
| 99 | Debecka Pass (2003) (Block 11) | 8 | **Complete** |
| 100 | Khafji (1991) (Block 11) | 7 | **Complete** |
| 101 | Fallujah Phase Line Fran (2004) (Block 11) | 13 | **Complete** |
| 102 | Bint Jbeil + INS Hanit Vignette (2006) (Block 11) | 15 | **Complete** |
| 103 | Block 11 Polish — OOB + engine gap tightening | 17 | **Complete** |
| 104 | Configurable Deployment Modes (Block 11 polish) | 21 | **Complete** |
| 105 | Checkpoint State Integrity (Block 12) | 23 | **Complete** |
| 106 | API Execution Integrity (Block 12) | 25 | **Complete** |
| 107 | Scenario Configuration Wiring (Block 12) | 103 | **Complete** |
| 108 | Logistics Runtime Wiring (Block 12) | 115 | **Complete** |
| 109 | Equipment Mapping Integrity (Block 12) | 322 | **Complete** |
| 110 | ASAT Production Integration (Block 12) | 50 (49 focused + 1 API) | **Complete** |
| 111 | Time-on-Target Execution (Block 12) | 165 (162 focused + 3 API) | **Complete** |
| 112 | Validation & Documentation Trust (Block 12) | 11,752 audited union; 97 terrain profile | **Complete** |
| 113 | Morale State Ownership (Block 12) | 11,824 audited passes; 6 declared warnings | **Complete** |
| 114 | Era Override Execution (Block 12) | 11,903 audited closure passes; 6 declared warnings | **Complete** |
| 115 | Sensing-Aware Tactical Standoff (Block 13) | 11,743 standard passes plus accepted qualified broad evidence | **Complete** |
| 116 | Fog-of-War Contact Continuation (Block 13) | 11,953 standard passes plus accepted qualified broad evidence | **Complete** |

The Phase 112 row remains historical repository-wide closure evidence, not a
count of newly added tests. The Phase 113 row is its historical closure union;
the Phase 114 row reports its exact closure union. For the full phase
roadmap, see
[`docs/development-phases.md`](docs/development-phases.md) (MVP),
[`docs/development-phases-post-mvp.md`](docs/development-phases-post-mvp.md)
(post-MVP), and `docs/development-phases-block{N}.md` for Blocks 2–17. The live
integrity issue inventory is in
[`docs/remediation-backlog.md`](docs/remediation-backlog.md). For per-phase
implementation logs, see [`docs/devlog/`](docs/devlog/).

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `numpy` | Array math, PRNG (`np.random.Generator`), vectorized operations |
| `scipy` | Statistical distributions, special functions (erfc), integration |
| `pydantic` | Configuration validation, YAML schema enforcement |
| `pyproj` | Geodetic/UTM/ENU coordinate transforms |
| `pyyaml` | YAML data file loading (units, weapons, scenarios) |
| `shapely` | Vector geometry (roads, rivers, coastlines, obstacles) |
| `networkx` | Supply network graphs, strategic map routing |

Optional: `numba` (JIT acceleration, `--extra perf`), `rasterio`/`xarray` (real terrain, `--extra terrain`), `mcp[cli]` (MCP server, `--extra mcp`), `mkdocs-material` (docs site, `--extra docs`), `fastapi`/`uvicorn`/`aiosqlite` (REST API, `--extra api`). Dev: `pytest`, `pytest-cov`, `matplotlib`, `httpx`, `pytest-asyncio`

## REST API

The project includes a FastAPI-based REST API for running simulations, browsing scenarios/units, and accessing results programmatically.

```bash
uv sync --extra api              # install API dependencies
uv run uvicorn api.main:app      # start the API server
# OpenAPI docs at http://localhost:8000/api/docs
```

Key endpoints: `GET /api/scenarios`, `GET /api/units`, `POST /api/runs`
(submit simulation), `GET /api/runs/{id}` (poll results),
`WS /api/runs/{id}/progress` (live progress), `POST /api/runs/batch`
(Monte Carlo), `POST /api/analysis/compare` (same-scenario A/B calibration
comparison), `POST /api/analysis/sweep` (sensitivity analysis), and
`POST /api/analysis/doctrine-compare` (doctrinal policy comparison). Analysis
results retain ordered raw metric vectors, seeds, and runtime provenance;
comparisons use common-seed paired differences.

## Frontend Development

The React frontend lives in `frontend/` and connects to the API via Vite's dev proxy. See the [Web UI Guide](docs/guide/web-ui.md) for a full walkthrough of the web application.

```bash
# Terminal 1: API server
uv sync --extra api
uv run uvicorn api.main:app --reload

# Terminal 2: Frontend dev server
cd frontend && npm install && npm run dev
# Open http://localhost:5173
```

Frontend commands:
- `npm run dev` — Vite dev server at localhost:5173
- `npm run build` — Production build (TypeScript + Vite)
- `npm test` — Run Vitest tests (no API server required)
- `npm run lint` — ESLint

## Documentation

**Documentation site**: [clay-m-smith.github.io/stochastic-warfare](https://clay-m-smith.github.io/stochastic-warfare) -- full docs with getting started guide, web UI guide, scenario library, architecture overview, mathematical models, API reference, and era reference.

| Document | Purpose |
|----------|---------|
| [`docs/brainstorm.md`](docs/brainstorm.md) | Architecture decisions, domain decomposition, rationale |
| [`docs/development-phases.md`](docs/development-phases.md) | Phase roadmap (0–10 + future), module-to-phase index |
| [`docs/development-phases-block3.md`](docs/development-phases-block3.md) | Block 3 UX/UI phase roadmap (31–36) |
| [`docs/specs/project-structure.md`](docs/specs/project-structure.md) | Full package tree, module decomposition, dependency graph |
| [`docs/devlog/`](docs/devlog/) | Per-phase implementation logs (`index.md` tracks status) |
| [`docs/skills-and-hooks.md`](docs/skills-and-hooks.md) | Dev infrastructure (Codex/Claude skills, hooks, research tiers) |
| [`docs/specs/`](docs/specs/) | Per-module specifications (written before implementation) |
| [`CODEX.md`](CODEX.md) / [`AGENTS.md`](AGENTS.md) | Canonical agent workflow, phase gates, and durable coding conventions |
| [`CLAUDE.md`](CLAUDE.md) | Legacy Claude-provider context kept aligned where rules overlap |

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). You are free to use, modify, and share the software for personal, academic, and research purposes. Commercial and institutional use requires a separate license — contact **claymsmith1@gmail.com** for inquiries.

## Contributing

This project does not accept external contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Key Conventions

For reference, the engine follows these conventions (see [`CODEX.md`](CODEX.md)
for the canonical workflow and complete durable rule set):

- **PRNG discipline** — all randomness via `RNGManager.get_stream(ModuleId)` returning `np.random.Generator`. No bare `random` module, no `np.random` module-level calls.
- **Deterministic iteration** — no `set()` or unordered dict driving simulation logic.
- **ECS separation** — entities hold data, modules implement behavior.
- **Package management** — `uv` exclusively. Never bare `pip install`.
- **Coordinate system** — ENU meters internally. Geodetic only for import/export/display.
- **Logging** — `from stochastic_warfare.core.logging import get_logger` — no bare `print()` in sim core.
- **Config** — pydantic `BaseModel` for all configuration classes.
- **Unit definitions** — data-driven YAML validated by pydantic. Engine defines behaviors, YAML parameterizes instances.

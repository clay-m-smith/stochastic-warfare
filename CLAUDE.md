# Stochastic Warfare — Claude Code Instructions

## Project Overview
High-fidelity, high-resolution wargame simulator. Multi-scale (campaign →
battlefield → battle → unit level) with stochastic/signal-processing-inspired
models, a headless Python engine, FastAPI service, and React frontend. Modern
warfare is the primary data package, with four historical-era packages and
integrated maritime warfare.

**Current status**: Phases 105 through 115 and Block 12 are complete. Phase
115's typed sensing-aware targeting and format-115 checkpoint/exposure
contract passes documentation, cross-document review, and postmortem; REM-028
is closed. The owner accepted its contended long-run evidence only with an
explicit qualification; capped slow/API/E2E runs are not called passes. See
`docs/devlog/phase-115.md`,
`docs/specs/sensing-aware-tactical-standoff.md`, and
`docs/remediation-backlog.md` for the exact evidence, closure gates, and
unresolved follow-ups.

Block 13 is active with Phase 116 / REM-029 next and unstarted. REM-041 through
REM-043 are assigned to planned Block 14.
REM-044 is assigned to planned Block 15 for sourced sensor covariance and an
atomic predictive-tracking transaction.
REM-045 assigns the legacy Fallujah scripted-action lifecycle to planned Block
16 / Phase 132; declaration/reference loading is not authoritative dispatch,
effect, or exact-once continuation evidence.
Phase 115's 73 Easting workload-identity change uses a strict non-timing
transition qualification; the clean endpoint must be promoted before the next
phase closes and is never called a performance pass.

## Python & Package Management
**Requires Python >=3.12** (pinned to 3.12.10 via `.python-version`).

**Use `uv` exclusively.** Never use bare `pip install`. Always use `uv add`, `uv sync`, etc. Direct `pip` may target system Python instead of the project venv.

Setup from scratch:
```bash
uv sync --extra dev    # creates .venv, installs all deps including pytest/matplotlib
```

Use `uv run` to execute all Python commands — this automatically uses the correct venv without manual activation:
```bash
uv run python --version
```

Do NOT use `source .venv/Scripts/activate` — use `uv run` instead.

## Running Tests
```bash
uv sync --locked --extra dev --extra api --extra terrain --extra mcp
uv run --no-sync python scripts/validate_test_partitions.py \
  --output artifacts/partition-audit/manifest.json
uv run --no-sync python scripts/run_pytest_partition.py standard \
  --manifest artifacts/partition-audit/manifest.json \
  --junit artifacts/standard/junit.xml --forbid-skips \
  --timeout-seconds 2700
```

The authoritative Python suite is the exact audited union of `standard`,
`slow-only`, `benchmark-only`, `slow-benchmark`, `api`, and `e2e`. PR/main CI
runs the audit, `standard`, `api`, `e2e`, and the overlapping `terrain`
dependency profile. Weekly/manual CI runs the three marker partitions in
deterministic module-affine shards. `benchmark-policy` is also an overlapping
focused profile, not a seventh partition. Phase 115 routes routine 73 Easting
through a strict version-4 non-timing workload transition while retaining
version-3 runtime-input normalization. `transition_qualified` proves only the
exact classified workload/semantic handoff; the next phase must promote the
clean Phase 115 endpoint before ordinary paired gating resumes. It is not a
speed, default-morale, or historical-fidelity result; Golan remains manual.

The Phase 115 closure audit enumerates exactly 12,248 nodes:
`standard` 11,743, `slow-only` 110, `benchmark-only` 87, `slow-benchmark` 4,
API 263, and E2E 41. All 11,743 standard nodes and every complete benchmark
profile passed, alongside data, determinism, scenario, frontend, static, and
documentation gates. The Phase 115 devlog records the exact qualified
slow/API/E2E results, the passing focused production API witness, transition
artifact, warnings, exclusions, and remaining deficits. Phase 115 is complete
and REM-028 is closed.

## Architecture

### 12 Modules (strict dependency graph)
`core` → `coordinates` → `terrain` → `environment` → `entities` → `movement` → `detection` → `combat` → `morale` → `c2` → `logistics` → `simulation`

Dependencies flow downward. Terrain never imports environment. Environment may read terrain (one-way). Entities are data, modules are behavior (ECS-like separation).

### Simulation Loop
Hybrid — tick-based outer loop (variable resolution per scale) + event-driven within ticks.

### Spatial Model
Layered hybrid — graph (strategic), grid (operational/tactical), continuous (unit-level). All raster grids share: Grid[0,0] = SW corner, row increases northward, col increases eastward.

### Key Dependencies
`numpy`, `scipy`, `pydantic`, `pyproj`, `shapely`, `networkx` (+ `pytest`, `pytest-cov`, `matplotlib`, `httpx`, `pytest-asyncio` for dev). Optional: `numba` (perf), `mcp[cli]` (mcp), `rasterio`/`xarray` (terrain), `mkdocs-material` (docs), `fastapi`/`uvicorn`/`aiosqlite`/`pydantic-settings` (api).

## Project Conventions
- **PRNG discipline**: No `np.random` module-level calls. All randomness via `RNGManager.get_stream(ModuleId)` → `np.random.Generator`. No bare `random` module.
- **Deterministic iteration**: No `set()` or unordered dict driving simulation logic.
- **State protocol**: Checkpoint-participating runtime owners implement the
  coordinated `get_state() -> dict` and `set_state(dict) -> None` contract.
- **Coordinate system**: ENU meters internally. Geodetic only for import/export/display. `pyproj` for transforms.
- **Dependencies flow downward**: terrain modules never import environment; environment may read terrain.
- **Entities are data, modules are behavior** (ECS-like separation).
- **No global singletons**: RNGManager, EventBus, Clock are explicitly instantiated and passed.
- **Config**: pydantic BaseModel for all configuration classes.
- **Unit definitions**: Data-driven YAML configs validated by pydantic. Engine defines behaviors, YAML parameterizes instances.
- **Source provenance**: Checkouts use the Git commit plus a content-sensitive
  dirty-tree fingerprint and never fall back from an unverifiable Git worktree.
  No-`.git` production images require explicit `SOURCE_REVISION` and a verified
  generated application-source manifest; missing, malformed, or tampered
  packaged source fails closed.
- **Logging**: `from stochastic_warfare.core.logging import get_logger; logger = get_logger(__name__)` — no bare `print()` in sim core.
- **Type hints**: Required on all public API functions.

## Frontend (Phase 33+)
- **Stack**: Vite + React 18 + TypeScript 5.7 + Tailwind v3 + TanStack Query v5 + React Router v6 + Plotly.js
- **Package manager**: npm (not pnpm). Lives in `frontend/` at repo root.
- **Dev server**: `cd frontend && npm run dev` — Vite at localhost:5173, proxies `/api` to localhost:8000
- **Tests**: `npm test` — vitest + RTL + jsdom. All tests mock `fetch`, no API server required.
- **Build**: `npm run build` — TypeScript check + Vite production bundle
- **API client**: Hand-written fetch wrappers and response types in `src/api/`.
  Runtime request validation and generated OpenAPI in `api/schemas.py` are
  authoritative for dynamic configuration payloads.
- **State management**: TanStack Query only. No Redux/Zustand. UI state via local state or URL search params.
- **Charts**: Plotly.js via `react-plotly.js` + `plotly.js-dist-min`. Lazy-loaded via `React.lazy`. Mock `PlotlyChart` wrapper in tests.

## Testing
- **Shared fixtures**: `tests/conftest.py` provides `rng`, `event_bus`, `sim_clock`, `rng_manager` fixtures + `make_rng()`, `make_clock()`, `make_stream()` helpers. Use for all new test files (Phase 8+).
- Existing test files have their own local helpers — no need to migrate.

## Development Process
- **MVP phases** (0–10): defined in `docs/development-phases.md`. All complete.
- **Post-MVP phases** (11–24): defined in `docs/development-phases-post-mvp.md`. Design thinking in `docs/brainstorm-post-mvp.md`.
- Devlog: `docs/devlog/` — one markdown file per phase, living documents. Update the relevant phase log when completing work.
- Run `/cross-doc-audit` after completing phases or changing architecture
- Run `/validate-conventions` after writing simulation core code
- All design docs are **living documents** — propagate implementation decisions back to all affected docs via `/update-docs`
- **Phase closure**: Update the current roadmap, phase devlog,
  `docs/devlog/index.md`, remediation backlog, public status pages, and affected
  reference/architecture documents. `CODEX.md` defines the Codex closure gates.

## Available Skills

Claude routes remain under `.claude/skills/`. Maintained Codex ports live under
`.agents/skills/`; `CODEX.md` and `AGENTS.md` define their phase-gate order and
production-evidence requirements.

| Skill | Purpose |
|-------|---------|
| `/research-military` | Military doctrine, historical data, theorist/philosopher writings (tiered sources) |
| `/research-models` | Mathematical, stochastic, signal processing modeling approaches (tiered sources) |
| `/validate-conventions` | Check code against PRNG, determinism, coordinate, logging conventions |
| `/update-docs` | Propagate design decisions to brainstorm, specs, memory (MVP + post-MVP) |
| `/spec` | Draft/update module specification before implementation |
| `/backtest` | Structure validation against historical engagement data |
| `/audit-determinism` | Deep PRNG discipline audit — trace all stochastic paths |
| `/design-review` | Review module design against military theory and architecture |
| `/cross-doc-audit` | Verify alignment across all docs (MVP + post-MVP + user-facing, 19 checks) |
| `/simplify` | Review changed code for reuse, quality, and efficiency |
| `/profile` | Performance profiling — cProfile analysis, hotspot identification, benchmarking |
| `/scenario` | Interactive scenario creation/editing walkthrough (with mandatory equipment mapping validation) |
| `/validate-data` | Validate unit/scenario YAML data integrity — equipment maps, sensor presence, unit type refs |
| `/compare` | Run two configs and summarize with statistical comparison |
| `/what-if` | Quick parameter sensitivity from natural language questions |
| `/timeline` | Generate battle narrative from simulation run |
| `/orbat` | Interactive order of battle builder |
| `/calibrate` | Auto-tune calibration overrides to match historical data |
| `/postmortem` | Structured retrospective after completing a phase — catches integration gaps, deficits, test quality issues |
| `/evaluate-scenarios` | Run all scenarios, compare against baseline, report improvements/regressions |

## Documentation Map
| Document | Purpose |
|----------|---------|
| `docs/brainstorm.md` | Architecture decisions, domain decomposition, rationale |
| `docs/brainstorm-post-mvp.md` | Post-MVP design thinking (deficits, EW, Space, CBRN, eras, tooling, unconventional warfare, strategic air campaigns/IADS) |
| `docs/development-phases.md` | MVP phase roadmap (0–10), module-to-phase index |
| `docs/development-phases-post-mvp.md` | Post-MVP phase roadmap (11–24), deficit-to-phase mapping |
| `docs/development-phases-block2.md` | Block 2 phase roadmap (25–30), integration & hardening |
| `docs/brainstorm-block3.md` | Block 3 design thinking (docs site, API, UI, tactical map) |
| `docs/development-phases-block3.md` | Block 3 phase roadmap (31–36), UX/UI pivot |
| `docs/brainstorm-block4.md` | Block 4 design thinking (integration gaps, polish, packaging) |
| `docs/development-phases-block4.md` | Block 4 phase roadmap (37–39), tightening & deployment |
| `docs/brainstorm-block5.md` | Block 5 design thinking (core combat fidelity, scenario analysis) |
| `docs/development-phases-block5.md` | Block 5 phase roadmap (40–48), battle loop wiring + deficit resolution |
| `docs/brainstorm-block6.md` | Block 6 design thinking (final tightening, deficit inventory, dead engine audit) |
| `docs/development-phases-block6.md` | Block 6 phase roadmap (49–57), calibration hardening + combat polish + engine wiring |
| `docs/brainstorm-block7.md` | Block 7 design thinking (build-then-defer-wiring audit, environmental params, unreachable engines) |
| `docs/development-phases-block7.md` | Block 7 phase roadmap (58–67), structural verification + environment wiring + engine integration |
| `docs/brainstorm-block8.md` | Block 8 design thinking (consequence enforcement, scenario expansion) |
| `docs/development-phases-block8.md` | Block 8 phase roadmap (68–82), consequence enforcement + scenario expansion |
| `docs/brainstorm-block9.md` | Block 9 design thinking (performance at scale, 9 themes) |
| `docs/development-phases-block9.md` | Block 9 phase roadmap (83–91), performance at scale |
| `docs/brainstorm-block10.md` | Block 10 design thinking (UI depth & engine exposure) |
| `docs/development-phases-block10.md` | Block 10 phase roadmap (92–97), UI depth |
| `docs/brainstorm-block11.md` | Block 11 design thinking (golden scenarios, engine validation through UI) |
| `docs/development-phases-block11.md` | Block 11 roadmap and polish history (98–104) |
| `docs/development-phases-block12.md` | Block 12 phase roadmap (105–114), integrity remediation |
| `docs/development-phases-block13.md` | Block 13 roadmap (115–127), active integrity follow-ups |
| `docs/development-phases-block14.md` | Block 14 roadmap (128–130), targeting authorization/topology/selection follow-ups |
| `docs/development-phases-block15.md` | Block 15 roadmap (131), sensor covariance and predictive-tracking follow-up |
| `docs/development-phases-block16.md` | Block 16 roadmap (132), scripted scenario action-integrity follow-up |
| `docs/remediation-backlog.md` | Audited implementation gaps and completion evidence |
| `docs/specs/project-structure.md` | Full package tree, module decomposition, dependency graph |
| `docs/devlog/` | Per-phase implementation logs (`index.md` tracks status) |
| `docs/skills-and-hooks.md` | Dev infrastructure documentation |
| `docs/specs/` | Per-module specifications (written before implementation) |
| `README.md` | Project overview, setup, architecture summary, status |
| `mkdocs.yml` | MkDocs site configuration (Phase 31) |
| `docs/index.md` | Docs site landing page (Phase 31) |
| `docs/guide/` | User-facing guides (getting started, web UI, scenarios) |
| `docs/concepts/` | Architecture overview, mathematical models (Phase 31) |
| `docs/reference/` | API reference, eras, units & equipment (Phase 31) |

## Phase Roadmap

All phase details are in `docs/devlog/` (one file per phase). Per-phase tables in `docs/development-phases*.md`.

| Block | Phases | Focus | Tests |
|-------|--------|-------|-------|
| MVP (1) | 0–10 | Core engine: terrain, entities, movement, detection, combat, morale, C2, logistics, simulation, validation | 3,737 |
| Post-MVP | 11–24 | Fidelity fixes, performance, tooling, terrain pipeline, EW, Space, CBRN, doctrinal AI, 4 historical eras, unconventional warfare | 2,588 |
| Block 2 | 25–30 | Engine wiring, polish, combat completeness, data packages (modern + historical), DEW, scenario library | 982 |
| Block 3 | 31–36 | MkDocs site, FastAPI + SQLite, React frontend, Plotly charts, tactical map, scenario editor | 334 |
| Block 4 | 37–39 | Integration fixes, map/chart enhancements, dark mode, Docker, single-command startup | 127 |
| Block 5 | 40–48 | Battle loop wiring, combat depth, domain routing, environmental integration, recalibration, deficit resolution | 374 |
| Block 6 | 49–57 | CalibrationSchema, combat polish, naval completeness, C2/AI wiring, era engines, validation, zero-deficit audit | 390 |
| Block 7 | 58–67 | Structural verification, environment wiring (atmosphere/maritime/CBRN/human factors), feedback loops, 21 enable_* flags | ~594 |
| Block 8 | 68–82 | Consequence enforcement, C2 depth, perf optimization, missile/carrier ops, test coverage, CI/CD, accessibility | ~1,291 |
| Block 9 | 83–91 | Profiling, spatial culling, LOD, Numba JIT, SoA data layer, per-side parallelism, benchmarking | ~279 |
| Block 10 | 92–97 | UI depth: analytics endpoints, dashboard charts, map overlays, calibration editor, event filtering, data catalogs | ~120 |
| Block 11 | 98–104 | Golden scenarios plus OOB, engine, and deployment polish | ~107 |
| Block 12 | 105–114 | Production-path integrity remediation; complete | 11,903 audited closure passes; 6 classified warnings |
| Block 13 | 115–127 | Active sensing, checkpoint, historical-validation, performance-semantics, concealment, surrender/POW, event-time, battle-topology, C2, CBRN-action, medical, maintenance, and validation-era follow-ups | Active |
| Block 14 | 128–130 | Targeting exposure authorization, authored mount/director topology, and availability-aware threat selection | Planned |
| Block 15 | 131 | Sourced sensor measurement covariance and atomic predictive tracking | Planned |
| Block 16 | 132 | Typed, fail-closed, exact-once scripted scenario actions | Planned |

### Block 11 Detail (COMPLETE)

| Phase | Status | Focus |
|-------|--------|-------|
| 98 | Complete | Shared prework — gap audit (4 OOB briefs), envelope helpers (6 fns + 26 tests), calibration template, depth checklist template |
| 99 | Complete | Debecka Pass (2003) — 12 new YAMLs (6 units + 3 weapons + 5 ammo), scenario YAML, 8 regression tests. **Engine fixes**: LIGHT_INFANTRY exempt from seeker FOV (Javelin fires), `"Ordnance Stations"` / `"CSRL Rotary Launcher"` mapped to bomb_rack_generic (CAS bombs emit EngagementEvents). 1 accepted limitation (Peshmerga squad granularity). |
| 100 | Complete | Khafji (1991) — 37 new YAMLs (14 units + 13 weapons + 10 ammo), scenario YAML with hybrid tick resolution + full OOB (233 units), 7 regression tests. Engine fixes: 16"/50 cross-era availability + NAVAL_GUN target_domains override for shore bombardment. 5 accepted limitations (naval-gunfire EngagementEvent, Iraqi artillery unit, SA-7/Spirit 03, AGM-65, full-OOB performance). |
| 101 | Complete | Fallujah Phase Line Fran (2004) — 29 new YAMLs (14 units + 7 weapons + 7 ammo + 1 HBIED device), 333-unit scenario (198 blue + 135 red at full Al-Fajr scale), **2 new scenario-level config fields** (`initial_ieds` + `scripted_events`) plus four legacy handlers. Phase 115 confirmed the current run ends before the first due action and that load/reference checks do not prove typed, lifecycle-safe, exact-once effects; REM-045 / Phase 132 owns that follow-up. Engine fixes: `hbied` subtype (non-jammable), `INCENDIARY_WEAPON` fire behavior, and `unconventional_engine` auto-creation for authored initial IEDs. 13 phase-era tests (6 fast + 7 @slow). |
| 102 | Complete | Bint Jbeil + INS Hanit (2006) — 19 new YAMLs (11 units + 4 weapons + 4 ammo) via 3 parallel authoring agents. Two scenarios: Bint Jbeil (249 units, IDF Golani/Paratrooper/Armor vs Hezbollah, phase-era `DRAW_SCENARIO`) + INS Hanit vignette (3 units, Sa'ar 5 vs C-802 Noor, phase-era `HISTORICAL_WINNERS.blue`). These labels preserve Block 11 intent/current regression behavior; they are not catalog-wide historical-validation evidence, which is queued under REM-030. 15 tests (9 fast + 6 @slow). **Zero engine fixes** — all new classes fit existing schemas (CORVETTE naval_type, NAVAL_GUN category, RADAR_ACTIVE guidance all existed). Block 11 COMPLETE. |
| 103 | Complete | Block 11 Polish — OOB + engine gap tightening. 3 new Iraqi artillery carrier units (2S1, 2S3, FROG-7), 10 weapon/sensor map additions, AGM-65 added to F-16C, FAE retagged INCENDIARY_WEAPON, `_publish_air_engagement_event` helper wired to 3 `_route_air_engagement` sites (AGM-65/AMRAAM/Hellfire/SAM now surface in /analytics/engagements chart), 4 `_publish_naval_engagement_event` sites added (torpedo, depth charge, ASHM, ASROC). 17 new tests. Resolves Phase 100 limitations #2 + #3 (partial) + #4. |
| 104 | Complete | Configurable Deployment Modes — new `stochastic_warfare/simulation/deployment.py` with 5 modes (legacy / bounding_box / clustered / doctrinal / manual) + `DeploymentMode` + `GroupKey` enums + `DeploymentBox` + `DeploymentConfig` pydantic models. Per-unit `position: [x, y]` YAML override works in any mode. 6 formation templates in `data/formations/` (brigade_attack, brigade_defense, battalion_urban_defense, marine_urban_assault, mechanized_thrust, naval_patrol_station). All 4 Block 11 golden scenarios retrofitted (104b): Debecka→bounding_box, Khafji/Fallujah/Bint Jbeil→doctrinal (Hanit stays legacy). Tick-0 side separation: Debecka 0m→1292m, Fallujah 5m→1104m, Bint Jbeil 5m→2625m (Khafji already OK at 5050m+). Direction-aware `_deploy_doctrinal` auto-flips offset_y_frac when opposing box is at lower y. 33 new Phase 104 tests including all-golden regression guard. |

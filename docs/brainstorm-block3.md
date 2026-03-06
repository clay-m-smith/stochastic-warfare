# Stochastic Warfare — Block 3 Brainstorm

## Context

Blocks 1–2 (Phases 0–30) built the complete simulation engine: 19 modules, 5 historical eras, multi-domain coverage (land/air/naval/sub/space/EW/CBRN), full engine wiring, and a comprehensive scenario library. 7,307 tests. The engine is headless Python — no user-facing interface beyond raw Python scripting, matplotlib validation plots, and a 7-tool MCP server for Claude.

Block 3 pivots from engine development to user experience. The goal: make the simulation usable by someone who doesn't read source code — starting with a public documentation site and building through a full web application.

## Why Block 3

The engine is technically complete. Continued engine-only work has diminishing returns:
- More data (units, scenarios) doesn't change what the system can do
- AI tuning and performance optimization are hard to validate without interactive feedback
- Engine bugs surface faster through interactive use than through unit tests

The biggest gap is not fidelity — it's accessibility. A comprehensive simulation that nobody can use is an impressive library that nobody reads.

Block 3 turns the engine into a product.

---

## What Already Exists

### Visualization (Phase 14 — `stochastic_warfare/tools/`)

Six matplotlib chart functions, all returning `Figure` objects:

| Function | Output |
|----------|--------|
| `force_strength_chart()` | Stacked area chart of active units over time |
| `engagement_network()` | NetworkX directed graph (attacker → target) |
| `supply_flow_diagram()` | Supply level timeline with depletion markers |
| `engagement_timeline()` | Scatter: tick × range, colored by hit/miss |
| `morale_progression()` | Step plot of morale state changes per unit |
| `mc_distribution_grid()` | Histogram grid of Monte Carlo metric distributions |

All charts are static. No interactivity (zoom, hover, filter, click).

### Analysis (Phase 14 — `stochastic_warfare/tools/`)

| Module | What It Does |
|--------|-------------|
| `narrative.py` | Event → text formatter. 15 built-in event types. Three styles: full, summary, timeline. |
| `tempo_analysis.py` | FFT spectral decomposition of event cadence. OODA cycle timing extraction. 3-panel figure. |
| `comparison.py` | A/B config comparison via Mann-Whitney U test. Effect size calculation. |
| `sensitivity.py` | Parameter sweep with errorbar plots. |

### Animation (Phase 14 — `stochastic_warfare/tools/replay.py`)

Matplotlib `FuncAnimation` replay from simulation snapshots. Unit scatter plots + engagement lines. Exports to GIF or MP4. No interactivity — watch-only.

### MCP Server (Phase 14 — `stochastic_warfare/tools/mcp_server.py`)

Seven tools for Claude integration:

| Tool | Purpose |
|------|---------|
| `run_scenario` | Execute scenario, cache result |
| `query_state` | Query cached result (summary, units, events, snapshots) |
| `run_monte_carlo` | Batch execution with statistics |
| `compare_results` | Side-by-side cached run comparison |
| `list_scenarios` | Enumerate available scenarios |
| `list_units` | Query unit definitions |
| `modify_parameter` | Baseline + modified run with delta |

Three MCP resources: `scenario://`, `unit://`, `result://`.

### Run Infrastructure

| Component | Role |
|-----------|------|
| `ResultStore` | LRU cache (20 runs) |
| `_run_helpers.py` | Batch execution, metric extraction |
| `serializers.py` | numpy/datetime/enum → JSON |

### Engine API

```python
# Current programmatic flow
loader = ScenarioLoader(data_dir)
ctx = loader.load("data/scenarios/taiwan_strait/scenario.yaml", seed=42)
engine = SimulationEngine(ctx, config=EngineConfig(max_ticks=1000))
result = engine.run()  # SimulationRunResult
```

Key classes: `ScenarioLoader`, `SimulationEngine`, `SimulationContext`, `EngineConfig`, `SimulationRecorder`, `SimulationRunResult`, `VictoryEvaluator`.

---

## Priority 0: Documentation Site

### The Problem

The project has extensive documentation — architecture brainstorms, phase plans, specifications, devlogs — but it all lives as raw markdown files in `docs/`. A first-time visitor to the GitHub repo sees the README and has to navigate the file tree to find anything else. There's no searchable, navigable documentation site.

With the repo going public, the project needs a professional public face that showcases what's been built and makes the documentation discoverable.

### Design Decision

**MkDocs + Material for MkDocs**, deployed to GitHub Pages via GitHub Actions.

Why MkDocs over alternatives:
- **Jekyll** (GitHub's default): Ruby-based, limited theme options, no built-in search. MkDocs is Python-native (fits the project).
- **Docusaurus**: React-based, heavier, designed for product docs with versioning. Overkill for a project docs site.
- **Sphinx**: Python-native but designed for API reference docs (autodoc). The project docs are conceptual/architectural, not API reference.
- **Hugo**: Fast but Go-based, less Python ecosystem alignment.

Material for MkDocs is the gold standard theme: built-in search, code highlighting, responsive design, admonitions, navigation tabs. The existing `docs/` markdown renders with zero modification.

Key principle: **no content duplication**. The site builds from the same markdown files used during development. The only new content is a landing page (`docs/index.md`) tailored for public visitors.

---

## Priority 1: API & Service Layer

### The Problem

The engine has no clean boundary for external consumption. The MCP server is Claude-facing. Running a scenario programmatically requires importing 5+ classes, understanding their initialization order, and managing state manually. There's no async execution, no progress reporting, no persistent result storage, and no REST endpoint.

### Design Decisions

**1.1 FastAPI as the service framework**

FastAPI provides async support, automatic OpenAPI docs, pydantic integration (already the project's validation layer), WebSocket support, and dependency injection. It's the natural fit for a pydantic-heavy Python project.

Alternatives considered:
- **Flask**: Lighter but lacks native async, OpenAPI, and pydantic integration
- **Django**: Too opinionated, ORM overhead for a stateless simulation
- **Streamlit/Gradio**: Rapid prototyping but limited to their widget model, poor for custom UIs
- **Raw websockets**: Too low-level for a multi-endpoint service

**1.2 Async execution with background tasks**

Simulation runs take seconds to minutes. The API must:
- Accept a run request and return a job ID immediately
- Execute the simulation in a background thread/process
- Stream progress updates via WebSocket
- Store results for later retrieval

Pattern: POST `/runs` → 202 Accepted + `run_id` → GET `/runs/{run_id}` for result → WS `/runs/{run_id}/progress` for live updates.

**1.3 Result persistence**

The in-memory `ResultStore` (20 runs, LRU eviction) is insufficient for a service. Options:

| Storage | Pros | Cons |
|---------|------|------|
| SQLite | Zero-config, file-based, good for single-user | No concurrent writes |
| PostgreSQL | Concurrent, production-grade | External dependency, deployment complexity |
| File-based JSON | Simple, human-readable | No querying, no indexing |

**Recommendation**: SQLite for initial implementation. Single-user desktop use case. Migrate to PostgreSQL only if multi-user becomes a requirement.

Store: run metadata (scenario, seed, config, timestamps), summary results (victory, force counts), and optionally full event logs (compressed JSON blob).

**1.4 API surface**

Core endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/scenarios` | List available scenarios |
| GET | `/scenarios/{name}` | Scenario detail (config, forces, terrain) |
| POST | `/runs` | Start a simulation run |
| GET | `/runs` | List past runs |
| GET | `/runs/{id}` | Run result detail |
| DELETE | `/runs/{id}` | Delete run |
| WS | `/runs/{id}/progress` | Live progress stream |
| POST | `/runs/batch` | Monte Carlo batch execution |
| GET | `/units` | List unit definitions |
| GET | `/units/{type}` | Unit detail |
| POST | `/compare` | A/B comparison |
| POST | `/sweep` | Sensitivity sweep |

**1.5 MCP server coexistence**

The MCP server stays. It serves a different audience (Claude integration). The REST API serves the web UI. Both use the same underlying engine. Shared code lives in `tools/` — the API layer calls the same functions the MCP server does.

---

## Priority 2: Scenario Builder

### The Problem

Scenario configuration is YAML editing. A user needs to know the schema (`CampaignScenarioConfig`), available unit types (scan `data/units/`), valid doctrine templates, terrain types, and optional config blocks. There's no validation feedback until `ScenarioLoader.load()` runs.

### Design Decisions

**2.1 Web-based scenario editor**

A form-based UI for scenario configuration:
- **Terrain panel**: Map size, cell size, terrain type selector (with preview), features
- **Force composer**: Side tabs (blue/red), unit palette (searchable catalog from `data/units/`), drag-and-drop or click-to-add with count controls
- **Configuration panels**: Duration, weather, objectives, victory conditions, optional engine configs (EW, CBRN, escalation, schools)
- **YAML preview**: Live-updating YAML output as the user builds the scenario
- **Validation**: Real-time pydantic validation with inline error display

**2.2 Unit catalog**

The API serves unit definitions from `data/units/` with metadata:
- Domain (ground, air, naval, submarine)
- Era compatibility
- Key stats (speed, armor, weapons)
- Signature cross-reference

The UI renders these as browsable cards with search and filtering.

**2.3 Template scenarios**

The 30+ existing scenarios serve as templates. Users can clone an existing scenario and modify it rather than building from scratch. This lowers the learning curve significantly.

---

## Priority 3: Results Dashboard

### The Problem

Post-run analysis requires Python scripting: import chart functions, extract data from `SimulationRecorder`, call visualization functions, save figures. There's no integrated view of a run's outcomes.

### Design Decisions

**3.1 Run results page**

After a run completes, display:
- **Summary card**: Scenario name, duration, victor, seed, tick count
- **Force strength over time**: The existing `force_strength_chart()` rendered interactively
- **Engagement timeline**: The existing `engagement_timeline()` with hover details
- **Narrative**: The existing `narrative.py` output formatted as a scrollable timeline
- **Morale progression**: Per-unit morale state changes
- **Supply status**: Supply levels with depletion warnings

**3.2 Interactive charts**

Replace matplotlib static figures with interactive web charts. Options:

| Library | Pros | Cons |
|---------|------|------|
| Plotly | Rich interactivity, Python + JS, good defaults | Heavy bundle size |
| Chart.js | Lightweight, pure JS, widely supported | Less Python integration |
| D3.js | Maximum flexibility | Steep learning curve, low-level |
| ECharts | Good performance, rich chart types | Less Python ecosystem |
| Recharts | React-native, composable | React-only |

**Recommendation**: Plotly for initial implementation. Has both Python (`plotly.py`) and JS (`plotly.js`) libraries. Can generate JSON chart specs server-side and render client-side. Upgrade path to custom D3 visualizations for the tactical map later.

**3.3 Monte Carlo results**

Batch run results show:
- Distribution histograms (existing `mc_distribution_grid()` pattern)
- Summary statistics table (mean, median, p5/p95, std)
- Historical reference lines where available
- Convergence indicator (running mean stabilization)

**3.4 Comparison view**

Side-by-side comparison of two runs or two configurations:
- Existing `comparison.py` Mann-Whitney U statistics
- Paired charts (force strength A vs B, metric distributions)
- Effect size visualization

---

## Priority 4: Tactical Map

### The Problem

The simulation has rich spatial data — unit positions, engagement ranges, terrain grids, LOS, movement paths — but no spatial visualization. The `replay.py` animation is a minimal scatter plot. No terrain rendering, no unit icons, no engagement arcs, no zoom/pan.

### Design Decisions

**4.1 2D tactical map**

A top-down map view showing:
- **Terrain**: Grid cells colored by terrain type (desert, forest, urban, water)
- **Units**: Icons/markers colored by side, sized by unit type, with labels
- **Engagements**: Lines/arcs between attacker and target, colored by result
- **Movement trails**: Fading trails showing recent unit movement
- **Objectives**: Highlighted zones with status indicators
- **FOW toggle**: Option to show only one side's known contacts vs omniscient view

**4.2 Playback controls**

- Tick-by-tick step forward/backward
- Play/pause with adjustable speed
- Scrub bar for jumping to specific tick
- Event markers on the scrub bar (engagement clusters, morale breaks)

**4.3 Technology**

| Approach | Pros | Cons |
|----------|------|------|
| HTML5 Canvas | Fast rendering, good for thousands of units | Manual hit-testing, no DOM events |
| SVG | DOM events, CSS styling, easy interactivity | Slow with many elements |
| Leaflet/MapLibre | Mature map library, layers, popups | Designed for geo maps, overhead for game-like grids |
| Pixi.js/Konva | GPU-accelerated 2D, game-oriented | Additional dependency, learning curve |

**Recommendation**: Start with HTML5 Canvas for the base terrain + unit rendering (performance), with a thin SVG overlay for interactive elements (engagement arcs, selection). This hybrid approach handles both large unit counts and click/hover interactions.

For geo-referenced scenarios (real-world terrain from Phase 15), Leaflet/MapLibre becomes relevant later — but the initial implementation should work with the abstract grid model.

---

## Technology Stack

### Backend
- **FastAPI** — async REST API + WebSocket
- **SQLite** (via `aiosqlite` or raw `sqlite3`) — result persistence
- **Uvicorn** — ASGI server
- **Existing engine** — `stochastic_warfare.*` imports unchanged

### Frontend
- **React** (via Vite) — component-based UI
- **TypeScript** — type safety for API contracts
- **Plotly.js** — interactive charts
- **HTML5 Canvas** — tactical map rendering
- **TanStack Query** — data fetching and caching
- **Tailwind CSS** — utility-first styling

### Alternative: Python-Only Path

If a JS frontend is out of scope or too heavy for initial delivery:

- **Textual** — Terminal UI (TUI) with rich widgets, runs in any terminal
- **Panel/Bokeh** — Python dashboarding with interactive plots, no JS required
- **NiceGUI** — Python web UI framework, minimal JS

The Python-only path gets something usable faster but with less polish and customizability. The React path is more work upfront but produces a production-grade interface.

**Recommendation**: Start with the React path. The API layer is needed regardless (it's the clean boundary between engine and consumer), and once the API exists, the frontend technology is a separate concern that can be swapped.

---

## What Does NOT Change

- **Simulation engine is unchanged** — zero modifications to `stochastic_warfare/` core modules
- **YAML data files unchanged** — scenarios, units, weapons all stay as-is
- **MCP server stays** — Claude integration is a separate concern from user-facing UI
- **Test suite unchanged** — 7,307 existing tests continue to pass
- **Single-threaded simulation** — deterministic replay is preserved; async is at the API layer, not the engine layer
- **`uv` for Python packages** — backend dependencies managed via `uv add`

### New Dependencies

| Package | Purpose | Layer |
|---------|---------|-------|
| `mkdocs-material` | Documentation site generator + theme | Docs |
| `fastapi` | REST API framework | Backend |
| `uvicorn` | ASGI server | Backend |
| `aiosqlite` | Async SQLite | Backend |
| `websockets` | WebSocket support (FastAPI builtin) | Backend |
| `plotly` | Interactive chart generation | Backend/Frontend |
| `react` | Component UI framework | Frontend |
| `typescript` | Type safety | Frontend |
| `vite` | Frontend build tool | Frontend |
| `tailwindcss` | CSS framework | Frontend |

Frontend dependencies managed via `npm`/`pnpm` in a separate `frontend/` directory. Backend dependencies via `uv add`. Docs dependencies via `uv add --extra docs`.

---

## Success Criteria for Block 3

1. **A professional documentation site is live** — searchable, navigable, auto-deployed on push
2. **A user can configure, run, and analyze a scenario entirely through a web browser** — no Python scripting required
3. **The API layer is a clean, documented boundary** — OpenAPI spec auto-generated, any frontend can consume it
4. **Existing visualization outputs are preserved and enhanced** — every matplotlib chart has an interactive web equivalent
5. **The tactical map shows unit positions, engagements, and terrain** — with post-hoc playback controls
6. **Performance is acceptable for interactive use** — scenario setup < 1s, run progress updates at least every 2s, chart rendering < 500ms
7. **Engine bugs discovered during UI work are fixed** — not deferred to a future block
8. **The engine remains untouched** — no modifications to simulation core for UI accommodation (adapt at the API layer instead)

---

## Design Decisions (Resolved)

1. **Single-user desktop tool.** No authentication, no sessions, no multi-user isolation. The API serves one user running the server locally. Multi-user is a future concern if distribution ever becomes a priority.

2. **Post-hoc replay first.** The tactical map replays completed runs with full scrubbing. Real-time streaming is deferred — Python tick performance may not support smooth live rendering, and post-hoc replay covers the core use case. The WebSocket progress channel provides summary stats (tick count, active units) during execution, not full spatial data.

3. **Browse and tweak existing scenarios.** Users clone an existing scenario and modify forces, parameters, and config toggles. Creating scenarios from scratch is not a UI concern — the Claude Code CLI skills (`/scenario`, `/orbat`) handle that workflow far more effectively. The UI focuses on exploring and running the existing 30+ scenario library.

4. **Pure web, no desktop wrapper.** Run `uvicorn` + open a browser. No Tauri, no Electron. The audience can run a Python server. Desktop packaging is a distribution concern for a future block if needed.

5. **React + TypeScript from the start.** Long-term stability over speed-to-first-page. The tactical map (Phase 35) is fundamentally a Canvas problem that Python UI frameworks handle poorly. React+TS provides the right ceiling even if early phases don't exercise its full capabilities. The API layer (Phase 32) is needed regardless of frontend technology.

# Stochastic Warfare — Block 3 Development Phases (31–36)

## Philosophy

Block 3 turns the headless simulation engine into an interactive product. Five priorities: (1) establish a professional public documentation site, (2) build a clean API boundary between the engine and any consumer, (3) make scenario configuration visual, (4) make results explorable, (5) make the spatial simulation visible.

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block3.md` (design thinking), `devlog/index.md` (deficit inventory), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

**Engine stability**: Zero modifications to `stochastic_warfare/` simulation core modules. All adaptation happens at the API layer. Engine bugs discovered during UI work are fixed in the engine and counted as Block 3 work, but architectural changes are not.

---

## Phase 31: Documentation Site (GitHub Pages) — COMPLETE

**Goal**: Deploy a professional documentation site at `clay-m-smith.github.io/stochastic-warfare` using MkDocs + Material for MkDocs. Renders the existing `docs/` markdown as a navigable, searchable site. Adds comprehensive user-facing documentation (Getting Started, Scenario Library, Architecture, Mathematical Models, API Reference, Era Reference, Units & Equipment).

**Dependencies**: None (builds on existing docs/).

**Delivered**: `mkdocs.yml` + `.github/workflows/docs.yml` + 8 new user-facing docs + `docs/index.md` landing page. `pyproject.toml` `docs` extra. Zero engine changes, zero new tests.

### 31a: MkDocs Configuration

- **`mkdocs.yml`** (new) — Site configuration:
  - Site name, description, author, repo URL
  - Material theme with color scheme, navigation, search
  - Nav structure mapping existing docs to site sections:
    - **Home** — README.md (or a custom index.md)
    - **Architecture** — brainstorm.md, brainstorm-post-mvp.md, brainstorm-block2.md, brainstorm-block3.md
    - **Development Phases** — development-phases.md, development-phases-post-mvp.md, development-phases-block2.md, development-phases-block3.md
    - **Specifications** — docs/specs/*.md
    - **Devlog** — docs/devlog/index.md, per-phase logs
    - **Skills & Hooks** — docs/skills-and-hooks.md
  - Plugins: search (built-in)
  - Markdown extensions: tables, code highlighting, admonitions, task lists
- **`docs/index.md`** (new) — Landing page for the docs site. Project overview, quick links to key sections, getting started summary. Distinct from README.md (which targets GitHub visitors), this targets docs site visitors.

### 31b: Site Content & Navigation

- **Review and organize existing docs for public consumption**:
  - Ensure all docs render cleanly in MkDocs (fix any relative links, image paths)
  - Add front matter or section headers where needed for navigation clarity
  - Create a concise landing page (`docs/index.md`) with:
    - What the project is (1-paragraph summary)
    - Key capabilities (multi-scale, multi-era, multi-domain, stochastic models)
    - Architecture overview (module dependency chain diagram)
    - Quick links: Getting Started, Architecture, Phases, Devlog
  - Verify code blocks, tables, and diagrams render correctly in Material theme

### 31c: GitHub Actions Deployment

- **`.github/workflows/docs.yml`** (new) — GitHub Actions workflow:
  - Triggers on push to `main` (paths: `docs/**`, `mkdocs.yml`, `README.md`)
  - Sets up Python, installs `mkdocs-material`
  - Runs `mkdocs build --strict` (catches broken links)
  - Deploys to `gh-pages` branch via `mkdocs gh-deploy`
- **GitHub repo settings**:
  - Enable GitHub Pages, source: `gh-pages` branch
  - Custom domain (optional, deferred)

### New Dependencies

```toml
[project.optional-dependencies]
docs = ["mkdocs-material>=9.5"]
```

### Exit Criteria
- `mkdocs serve` renders the full docs site locally with working navigation and search
- GitHub Actions deploys to `gh-pages` on push to main
- Site is live at `clay-m-smith.github.io/stochastic-warfare`
- All existing docs render correctly (tables, code blocks, links)
- Landing page provides a clear project overview for first-time visitors
- No content duplication — site builds from existing `docs/` files

---

## Phase 32: API & Service Foundation — COMPLETE

**Goal**: Build a FastAPI service layer wrapping the simulation engine. Async run execution, WebSocket progress streaming, persistent result storage, and a documented REST API that any frontend can consume.

**Dependencies**: None (builds on existing engine and tools/).

**Delivered**: `api/` package (13 source files) — FastAPI app, SQLite persistence (aiosqlite), RunManager with step-based progress streaming, 23 REST endpoints + 2 WebSocket endpoints. `pyproject.toml` `api` extra. 77 new tests. Zero engine changes.

### 32a: Core API Scaffolding

Set up the FastAPI application structure, configuration, and basic endpoints.

- **`api/`** package (new) — API layer lives alongside `stochastic_warfare/`, not inside it
  - `api/main.py` — FastAPI app factory, CORS config, lifespan events
  - `api/config.py` — API configuration (pydantic Settings: host, port, db_path, max_concurrent_runs, cors_origins)
  - `api/dependencies.py` — Dependency injection (ScenarioLoader, ResultStore, RunManager)
- **Scenario endpoints**:
  - `GET /api/scenarios` — List all scenarios (name, path, era, duration, side count). Scans `data/scenarios/` and `data/eras/*/scenarios/`.
  - `GET /api/scenarios/{name}` — Full scenario config as JSON (CampaignScenarioConfig serialized). Includes force summary, terrain, duration, optional configs present.
- **Unit catalog endpoints**:
  - `GET /api/units` — List unit definitions with filters (domain, era, category). Returns name, domain, key stats.
  - `GET /api/units/{type}` — Full unit definition as JSON.
- **Health & metadata**:
  - `GET /api/health` — Service status, engine version, scenario count, total tests
  - `GET /api/meta/eras` — Available eras
  - `GET /api/meta/doctrines` — Available doctrine templates
  - `GET /api/meta/terrain-types` — Available terrain types

### 32b: Run Execution & Persistence

Async simulation execution with SQLite result storage.

- **`api/run_manager.py`** (new) — `RunManager` class:
  - `submit(scenario_path, config_overrides, seed) -> run_id` — queue a run
  - `get_status(run_id) -> RunStatus` — PENDING / RUNNING / COMPLETED / FAILED
  - `get_result(run_id) -> RunResult` — full result after completion
  - `cancel(run_id)` — cancel a running simulation (best-effort)
  - `list_runs(limit, offset, scenario_filter) -> list[RunSummary]`
  - Background execution via `asyncio.to_thread()` (simulation is CPU-bound, runs in thread pool)
- **`api/database.py`** (new) — SQLite schema and access layer:
  - `runs` table: id, scenario_name, scenario_path, seed, config_json, status, created_at, started_at, completed_at, result_json, error_message
  - Async access via `aiosqlite`
- **Run endpoints**:
  - `POST /api/runs` — Submit run → 202 Accepted + `{run_id, status: "pending"}`
  - `GET /api/runs` — List runs (paginated, filterable by scenario/status)
  - `GET /api/runs/{id}` — Run detail: status, config, result (if complete), timing
  - `DELETE /api/runs/{id}` — Delete run record
- **Result detail endpoints**:
  - `GET /api/runs/{id}/forces` — Force strength time series
  - `GET /api/runs/{id}/events` — Event log (paginated, filterable by type)
  - `GET /api/runs/{id}/narrative` — Generated narrative text (uses existing `narrative.py`)
  - `GET /api/runs/{id}/snapshots` — State snapshots (tick-indexed)

### 32c: WebSocket Progress & Batch Runs

Live progress streaming and Monte Carlo batch execution.

- **WebSocket endpoint**:
  - `WS /api/runs/{id}/progress` — Stream tick updates: `{tick, elapsed_s, active_units, events_this_tick}`. Closes when run completes.
  - Progress callback injected into engine via `SimulationRecorder` event hooks
- **Batch endpoints**:
  - `POST /api/runs/batch` — Monte Carlo batch: `{scenario, num_iterations, base_seed, max_ticks}` → batch_id
  - `GET /api/runs/batch/{id}` — Batch status + aggregated statistics
  - `WS /api/runs/batch/{id}/progress` — Stream per-iteration completion
- **Analysis endpoints** (wrapping existing tools):
  - `POST /api/analysis/compare` — A/B comparison (wraps `comparison.py`)
  - `POST /api/analysis/sweep` — Parameter sensitivity (wraps `sensitivity.py`)
  - `GET /api/analysis/tempo/{run_id}` — Tempo analysis (wraps `tempo_analysis.py`)

### 32d: Testing & Documentation

- API tests via `httpx.AsyncClient` (FastAPI test client)
- WebSocket tests via `websockets` test client
- OpenAPI spec auto-generated and served at `/api/docs` (Swagger UI) and `/api/redoc`
- API configuration via environment variables and/or `.env` file

### New Dependencies

```toml
[project.optional-dependencies]
api = ["fastapi>=0.115", "uvicorn[standard]>=0.34", "aiosqlite>=0.20"]
```

### Exit Criteria
- `GET /api/scenarios` returns all 30+ scenarios with metadata
- `POST /api/runs` accepts a scenario, returns run_id, runs in background
- `GET /api/runs/{id}` returns complete result after run finishes
- WebSocket streams tick-level progress during execution
- SQLite stores run history across server restarts
- `POST /api/runs/batch` executes Monte Carlo batch with statistics
- OpenAPI spec serves at `/api/docs`
- All existing 7,307 engine tests pass unchanged

---

## Phase 33: Frontend Foundation & Scenario Browser — COMPLETE

**Goal**: Stand up the React frontend application with routing, layout, and the first functional page: a scenario browser that lets users explore and select scenarios.

**Dependencies**: Phase 32 (API must serve scenario and unit data).

**Delivered**: `frontend/` directory (~50 new files) — Vite + React 18 + TypeScript 5.7, Tailwind v3, TanStack Query v5, React Router v6, Headless UI v2. Scenario browser (list + detail), unit catalog with detail modal, run config + run list pages, 10 shared components. 58 vitest tests. Zero engine/API changes.

### 33a: Frontend Scaffolding

- **`frontend/`** directory (new, separate from Python package):
  - Vite + React + TypeScript project
  - Tailwind CSS configuration
  - TanStack Query for API data fetching
  - React Router for navigation
  - API client generated from OpenAPI spec (or hand-written typed client)
- **Layout**:
  - App shell: sidebar navigation + main content area
  - Pages: Scenarios, Runs, Analysis (initially stubs)
  - Responsive layout (works at 1280px+ desktop, degrades gracefully)

### 33b: Scenario Browser

- **Scenario list page**:
  - Card grid of available scenarios
  - Each card: name, era badge, duration, force count summary, terrain type
  - Filter by era (Modern, WW2, WW1, Napoleonic, Ancient)
  - Search by name
  - Sort by name, duration, era
- **Scenario detail page**:
  - Full configuration display (terrain, weather, objectives, victory conditions)
  - Force composition table per side (unit type, count, stats)
  - Optional config indicators (EW, CBRN, escalation, schools — present/absent badges)
  - Documented outcomes (if available)
  - "Run This Scenario" button → navigates to run configuration

### 33c: Unit Catalog

- **Unit browser page**:
  - Searchable, filterable catalog of all unit definitions
  - Filter by domain (ground, air, naval, submarine), era
  - Unit cards with key stats (speed, armor, detection range, weapons)
  - Unit detail modal/page with full specification

### 33d: Run Configuration

- **Pre-run configuration page**:
  - Selected scenario displayed at top
  - Editable parameters: seed, max_ticks, calibration overrides
  - Optional config toggles (enable/disable EW, CBRN, escalation)
  - "Start Run" button → POST to API → redirect to run status page

### Exit Criteria
- Frontend builds and serves via Vite dev server
- Scenario list page shows all scenarios from API
- Scenario detail page shows full configuration
- Unit catalog is browsable and searchable
- Run configuration page can submit a run to the API
- Navigation between pages works via React Router

---

## Phase 34: Run Results & Analysis Dashboard — COMPLETE

**Goal**: Display simulation results interactively. Replace static matplotlib charts with web-based interactive visualizations. Build the post-run analysis experience.

**Dependencies**: Phase 32 (run results API), Phase 33 (frontend framework).

**Delivered**: ~45 new files — RunDetailPage with live WebSocket progress, 5 Plotly chart types (force strength, engagement timeline, morale, event activity, comparison), narrative view with side/style filters, Analysis page with Batch MC / A/B Compare / Sensitivity Sweep tabs. `react-plotly.js` + `plotly.js-dist-min` dependencies. 65 new vitest tests (127 total). Zero engine/API changes.

### 34a: Run Status & History

- **Run list page**:
  - Table of past runs: scenario, seed, status, duration, victor, timestamp
  - Status badges: pending (gray), running (blue), completed (green), failed (red)
  - Click to view run detail
  - Delete runs
- **Live run tracking**:
  - WebSocket connection to `/runs/{id}/progress`
  - Progress bar showing tick advancement
  - Live event count and active unit count
  - Auto-transition to results when complete

### 34b: Interactive Charts

Replace matplotlib with Plotly.js (or equivalent) interactive charts:

- **Force strength chart**: Interactive area chart with hover tooltips, legend toggle per side, zoom/pan
- **Engagement timeline**: Interactive scatter with hover showing attacker, target, weapon, result, range
- **Morale progression**: Interactive step chart with unit filtering
- **Supply flow**: Interactive line chart with threshold annotations
- **Engagement network**: Interactive graph (Plotly network or vis.js) with node click → unit detail

Data served from API endpoints (`/runs/{id}/forces`, `/runs/{id}/events`). Chart rendering is client-side from JSON data.

### 34c: Narrative View

- **Battle narrative panel**:
  - Scrollable timeline of events formatted by `narrative.py`
  - Filter by event type (combat, detection, C2, morale, movement)
  - Filter by side
  - Style toggle: full / summary / timeline
  - Click event → highlight corresponding tick in charts

### 34d: Monte Carlo & Comparison

- **MC results page**:
  - Histogram grid of metric distributions (exchange ratio, force destroyed, duration)
  - Summary statistics table
  - Historical reference lines (where documented_outcomes exist)
  - Convergence plot (running mean by iteration)
- **A/B comparison page**:
  - Side-by-side force strength charts
  - Statistical comparison table (Mann-Whitney U, p-value, effect size)
  - Parameter diff highlighting
- **Sensitivity sweep page**:
  - Errorbar chart of metric vs parameter value
  - Interactive: hover for individual run values

### Exit Criteria
- Completed runs display interactive force strength, engagement timeline, and morale charts
- Live run tracking shows progress via WebSocket
- Battle narrative renders with filtering
- MC batch results show distribution histograms and statistics
- A/B comparison shows side-by-side charts with statistical testing
- All charts support zoom, hover, and legend filtering

---

## Phase 35: Tactical Map & Spatial Visualization

**Goal**: Build a 2D tactical map showing unit positions, terrain, engagements, and movement over time. Add playback controls for stepping through a completed simulation tick by tick (post-hoc replay).

**Dependencies**: Phase 34 (results infrastructure and charting), Phase 32 (snapshot data API).

### 35a: Map Renderer

- **Canvas-based map component**:
  - Terrain grid rendering (cells colored by terrain type: desert/tan, forest/green, urban/gray, water/blue, mountain/brown)
  - Grid coordinates and scale bar
  - Zoom (mouse wheel) and pan (drag)
  - Viewport culling (only render visible cells)
  - Resolution-adaptive: show grid lines at high zoom, solid fills at low zoom

### 35b: Unit Layer

- **Unit rendering**:
  - Side-colored markers (blue/red) at unit positions
  - Unit type icons or symbols (NATO APP-6 style if feasible, otherwise simple shapes: tank=diamond, infantry=circle, aircraft=triangle, ship=pentagon)
  - Unit labels (toggleable)
  - Selection: click unit → sidebar shows unit detail (type, health, morale, ammo, position)
  - Active vs destroyed visual distinction (opacity/cross-out)

### 35c: Engagement & Movement Overlays

- **Engagement arcs**: Lines from attacker to target on engagement events, colored by result (red=hit, gray=miss), fade over time
- **Movement trails**: Fading polylines showing recent unit movement paths
- **Objective zones**: Highlighted circles/polygons at objective positions with capture status
- **Detection ranges**: Optional semi-transparent circles showing sensor ranges (toggleable)
- **FOW toggle**: Show only one side's known contacts vs omniscient view

### 35d: Playback Controls

- **Timeline scrubber**: Horizontal bar spanning all ticks, draggable cursor
- **Transport controls**: Play, pause, step forward, step backward, speed control (1x, 2x, 5x, 10x)
- **Event markers**: Engagement clusters marked on the scrub bar
- **Sync with charts**: Moving the playback cursor updates the vertical reference line on force strength and engagement timeline charts
- **Tick info panel**: Current tick number, simulation time, active units per side

### Exit Criteria
- Terrain grid renders with type-appropriate colors
- Units display at correct positions with side coloring
- Engagements show as attacker-target arcs
- Movement trails visible
- Playback controls step through ticks
- Zoom/pan works smoothly at 200+ units
- Map syncs with charts (scrubber position)

---

## Phase 36: Scenario Tweaker & Polish

**Goal**: Add clone-and-tweak scenario editing. Polish the full application: keyboard shortcuts, responsive refinements, error handling, export capabilities. Full scenario creation from scratch is not a UI concern — the Claude Code CLI skills (`/scenario`, `/orbat`) handle that workflow.

**Dependencies**: Phase 33 (scenario browser provides read-only foundation), Phase 35 (map component for terrain preview).

### 36a: Scenario Tweaker

- **Clone and modify existing scenarios**:
  - Clone scenario → editable copy with auto-generated name
  - Modify forces: adjust unit counts, add/remove unit types from catalog
  - Modify duration, weather conditions
  - Toggle optional configs (EW, CBRN, escalation, schools)
  - Adjust calibration overrides (sliders for key parameters)
  - Real-time pydantic validation with inline error display
- **YAML preview**:
  - Side panel showing live YAML as the user tweaks
  - Copy-to-clipboard
  - Save to disk (via API endpoint that writes to `data/scenarios/`)
- **Unit picker**:
  - Searchable dropdown sourced from unit catalog API
  - Shows key stats (domain, speed, armor) inline
  - Era-filtered (only show era-compatible units)

### 36b: Terrain Preview

- **Mini-map in scenario tweaker**:
  - Renders terrain grid based on selected terrain type and dimensions
  - Shows objective positions
  - Visual feedback when terrain type or dimensions change

### 36c: Export & Reporting

- **Run report export**:
  - PDF: Summary + charts + narrative + key statistics
  - CSV: Event log, force strength time series, MC metrics
  - JSON: Full run result for programmatic consumption
  - Image: Individual charts as PNG/SVG
- **Scenario export**:
  - Download scenario as YAML file

### 36d: Polish

- **Error handling**: Graceful error states for failed runs, API errors, WebSocket disconnects
- **Loading states**: Skeleton screens for data fetching
- **Keyboard shortcuts**: Space (play/pause), arrow keys (step), number keys (speed)
- **URL routing**: Deep-linkable pages (scenario detail, run result, comparison)
- **Responsive tweaks**: Sidebar collapse on narrow screens
- **Performance**: Lazy loading for large event logs, virtualized lists

### Exit Criteria
- Users can clone and modify existing scenarios (force counts, params, config toggles)
- YAML preview updates in real-time during editing
- Terrain preview shows grid with objectives
- Run reports exportable as PDF/CSV
- Keyboard shortcuts work for playback
- Error states handled gracefully throughout

---

## Project Structure (New Directories)

```
docs/index.md               # NEW — docs site landing page
mkdocs.yml                  # NEW — MkDocs configuration
.github/workflows/docs.yml  # NEW — GitHub Actions for docs deployment

api/                        # FastAPI backend (NEW — Phase 32)
  main.py                   # App factory, CORS, lifespan
  config.py                 # API configuration (pydantic Settings)
  dependencies.py           # Dependency injection
  run_manager.py            # Async run execution + state management
  database.py               # SQLite schema + access layer
  routers/                  # Route modules
    scenarios.py            # /api/scenarios endpoints
    runs.py                 # /api/runs endpoints
    units.py                # /api/units endpoints
    analysis.py             # /api/analysis endpoints
    meta.py                 # /api/meta endpoints

frontend/                   # React frontend (NEW — Phase 33)
  package.json              # npm/pnpm dependencies
  vite.config.ts            # Build configuration
  tsconfig.json             # TypeScript configuration
  tailwind.config.js        # Tailwind CSS configuration
  src/
    App.tsx                 # Root component + routing
    api/                    # API client (typed, from OpenAPI)
    components/             # Shared components (layout, cards, charts)
    pages/                  # Page components
      Scenarios/            # Scenario browser + detail
      Runs/                 # Run list + detail + live tracking
      Analysis/             # MC, comparison, sweep, tempo
      Map/                  # Tactical map + playback
      Editor/               # Scenario tweaker
    hooks/                  # Custom React hooks (useRun, useWebSocket, etc.)
    types/                  # TypeScript type definitions

stochastic_warfare/         # UNCHANGED — simulation engine
data/                       # UNCHANGED — YAML data files
tests/                      # Existing engine tests UNCHANGED
tests/api/                  # NEW — API integration tests
```

---

## Estimated Scope

| Phase | Focus | Key Deliverables |
|-------|-------|-----------------|
| 31 | Documentation Site | MkDocs + Material theme, GitHub Actions deployment, 8 user-facing docs, docs site live at GitHub Pages. **COMPLETE** |
| 32 | API & Service Foundation | FastAPI app, async runs, SQLite persistence, WebSocket progress, batch/MC/analysis endpoints, OpenAPI docs. **COMPLETE** |
| 33 | Frontend Foundation & Scenario Browser | React app, scenario list/detail, unit catalog, run configuration page. 62 vitest tests. **COMPLETE** |
| 34 | Run Results & Analysis Dashboard | Interactive charts (Plotly), narrative view, MC results, A/B comparison, live run tracking. 65 vitest tests. **COMPLETE** |
| 35 | Tactical Map & Spatial Visualization | Canvas terrain renderer, unit positions, engagement arcs, movement trails, playback controls, chart sync. 71 new tests. **COMPLETE** |
| 36 | Scenario Tweaker & Polish | Clone-and-tweak editor, terrain preview, JSON/CSV/YAML export, print report, keyboard shortcuts, responsive sidebar, WS reconnect. ~59 new tests. **COMPLETE** |

**Implementation order**: 31 → 32 → 33 → 34 → 35 → 36. Phase 31 (docs site) is independent and should ship first — it gives the newly-public repo a professional face. Phase 32 (API) is the foundation for all UI work. Phases 33–34 can potentially overlap (scenario browser doesn't depend on charting, and vice versa). Phase 35 (map) depends on snapshot data from Phase 32 and the frontend from Phase 33. Phase 36 (tweaker + polish) is the capstone.

---

## Verification

```bash
# Docs site (local preview)
uv run mkdocs serve                      # preview at localhost:8000

# API tests
uv run python -m pytest tests/api/ --tb=short -q

# Frontend (from frontend/ directory)
npm run build        # TypeScript compilation + bundle
npm run test         # Component tests (vitest)
npm run lint         # ESLint
npm run typecheck    # tsc --noEmit

# Full engine regression (must still pass)
uv run python -m pytest --tb=short -q

# Run the full stack locally
uv run uvicorn api.main:app --reload        # API server on :8000
cd frontend && npm run dev                   # Vite dev server on :5173
```

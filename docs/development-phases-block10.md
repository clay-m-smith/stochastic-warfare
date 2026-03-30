# Stochastic Warfare -- Block 10 Development Phases (92--97)

## Philosophy

Block 10 is the **UI depth & engine exposure block**. The engine has 60+ domain engines, 32 behavioral flags, 68 calibration parameters, 9 doctrinal schools, and 100+ event types — but the web UI, built in Block 3 (Phases 31–36) and partially synced in Phase 80, exposes a fraction of this capability. Block 10 surfaces existing data through existing APIs to existing UI components. Where the API lacks a necessary endpoint or data field, we add it — but the simulation logic remains unchanged.

**Design principle**: Zero new engine capabilities. Every feature surfaces existing data.

**Exit criteria**:
1. Per-run analytics endpoints return structured casualty/suppression/morale/engagement data
2. Tactical map displays morale, posture, and health overlays for units
3. CalibrationSliders expose per-side overrides and expanded morale parameters
4. Doctrine and commander selectors functional in scenario editor
5. Event filtering by type/side/tick range operational
6. Weapon and doctrine catalog pages functional
7. All 40 scenarios produce correct winners (no engine regressions)
8. All existing tests pass + new frontend/API tests

**Cross-document alignment**: This document must stay synchronized with `brainstorm-block10.md` (design thinking), `devlog/index.md` (phase status), and `specs/project-structure.md` (module definitions). Run `/cross-doc-audit` after any structural change.

---

## Phase 92: API Analytics & Frame Enrichment

**Status**: Complete.

**Goal**: Build the backend foundation for rich diagnostics — analytics endpoints over event data, enriched replay frames with unit state, and metadata endpoints for doctrine/commander browsing.

**Dependencies**: Block 9 complete (Phase 91).

### 92a: Per-Run Analytics Endpoints

Add server-side aggregation endpoints that parse a run's `events_json` into structured summaries. No new database columns — compute on read from existing event data.

- **`api/routers/analytics.py`** (new) -- Analytics router:
  - `GET /runs/{run_id}/analytics/casualties` -- Casualty breakdown:
    - Group by: weapon type, engine type, side, or tick (query param `group_by`)
    - Returns: `{groups: [{label: str, count: int, side: str}], total: int}`
    - Source events: `EngagementEvent` (outcome=hit), `DamageEvent`, `UnitDestroyedEvent`
  - `GET /runs/{run_id}/analytics/suppression` -- Suppression summary:
    - Returns: `{peak_suppressed: int, peak_tick: int, rout_cascades: int, timeline: [{tick, count}]}`
    - Source events: `SuppressionEvent`, rout cascade events
  - `GET /runs/{run_id}/analytics/morale` -- Morale state distribution:
    - Returns: `{timeline: [{tick, confident: int, shaken: int, broken: int, routed: int}]}`
    - Source events: `MoraleStateChangeEvent`, initial unit states
  - `GET /runs/{run_id}/analytics/engagements` -- Engagement summary:
    - Returns: `{by_type: [{type: str, count: int, hit_rate: float}], total: int, avg_range_m: float}`
    - Source events: `EngagementEvent`
  - `GET /runs/{run_id}/analytics/summary` -- Combined summary (all of the above in one call):
    - Returns: `{casualties: {...}, suppression: {...}, morale: {...}, engagements: {...}}`
    - Convenience endpoint to avoid 4 separate requests
- **`api/schemas.py`** (modified) -- Add response models:
  - `CasualtyAnalytics`, `SuppressionAnalytics`, `MoraleAnalytics`, `EngagementAnalytics`, `AnalyticsSummary`

**Tests** (~12):
- Each analytics endpoint returns correct structure for a completed run
- Empty run (no events) returns zero-value defaults, not errors
- Filtering by side works (only blue casualties, only red engagements)
- Run not found → 404
- Run still in progress → 409

### 92b: Replay Frame Enrichment

Extend `MapUnitFrame` with unit state fields so the tactical map can visualize morale, posture, health, fuel, ammo, and suppression.

- **`api/schemas.py`** (modified) -- Add fields to `MapUnitFrame`:
  - `morale: int = 0` (0=CONFIDENT, 1=SHAKEN, 2=BROKEN, 3=ROUTED, 4=RALLIED)
  - `posture: str = ""` (MOVING, DEFENSIVE, DUG_IN, ASSAULT, or air/naval posture)
  - `health: float = 1.0` (0.0–1.0, fraction of full health)
  - `fuel_pct: float = 1.0` (0.0–1.0)
  - `ammo_pct: float = 1.0` (0.0–1.0)
  - `suppression: int = 0` (0–4, suppression level)
  - `engaged: bool = False` (unit fired or was targeted this tick)
- **`api/routers/runs.py`** (modified) -- In frame recording code:
  - Read `unit.morale_state`, `unit.posture`, `unit.health_fraction`, fuel/ammo ratios, suppression level
  - Populate new `MapUnitFrame` fields during frame capture
  - Backward compatible: old runs without enriched frames use default values

**Tests** (~6):
- Enriched frames contain all new fields with valid ranges
- Old runs without enriched data load correctly (defaults)
- Morale values map to correct enum integers
- Fuel/ammo percentages clamped to 0.0–1.0

### 92c: Metadata Endpoints

Add browsing endpoints for doctrine schools, commander profiles, and weapons. These enable the scenario editor to offer dropdowns instead of requiring YAML knowledge.

- **`api/routers/meta.py`** (modified) -- Add endpoints:
  - `GET /meta/schools` → `[{name: str, description: str, key_traits: list[str]}]`
    - Reads `data/schools/*.yaml` or hardcoded from engine's school registry
  - `GET /meta/commanders` → `[{name: str, display_name: str, era: str, traits: dict}]`
    - Reads `data/commander_profiles/*.yaml`
  - `GET /meta/doctrines` → `[{name: str, display_name: str, era: str}]`
    - Reads `data/doctrine/*.yaml`
  - `GET /meta/weapons` → `[{weapon_id: str, display_name: str, domain: str, category: str, max_range_m: float}]`
    - Reads `data/**/weapons/*.yaml`
  - `GET /meta/weapons/{id}` → full weapon definition
- **`api/schemas.py`** (modified) -- Add response models:
  - `SchoolInfo`, `CommanderInfo`, `DoctrineInfo`, `WeaponSummary`, `WeaponDetail`

**Tests** (~8):
- Schools endpoint returns 9 entries
- Commanders endpoint returns entries with trait fields
- Weapons endpoint returns entries with range/domain
- Weapon detail returns full spec
- Unknown weapon ID → 404

### Exit Criteria
- All 5 analytics endpoints return correct data for completed runs
- MapUnitFrame contains morale/posture/health/fuel/ammo/suppression fields
- Schools, commanders, doctrines, and weapons endpoints return browseable data
- No engine changes — API only

---

## Phase 93: Results Dashboard Depth

**Status**: Complete.

**Goal**: Build frontend components that consume the Phase 92 analytics endpoints, transforming the run results page from "what happened" to "why it happened."

**Dependencies**: Phase 92 (analytics endpoints).

### 93a: API Client & Types

Wire the new analytics endpoints into the frontend API client and TypeScript type system.

- **`frontend/src/api/analytics.ts`** (new) -- API client functions:
  - `fetchCasualtyAnalytics(runId, groupBy?)` → `CasualtyAnalytics`
  - `fetchSuppressionAnalytics(runId)` → `SuppressionAnalytics`
  - `fetchMoraleAnalytics(runId)` → `MoraleAnalytics`
  - `fetchEngagementAnalytics(runId)` → `EngagementAnalytics`
  - `fetchAnalyticsSummary(runId)` → `AnalyticsSummary`
- **`frontend/src/types/analytics.ts`** (new) -- TypeScript interfaces matching API response models

**Tests** (~4):
- API client functions construct correct URLs
- Type guards validate response shapes
- Error handling for 404/409 responses

### 93b: Casualty & Engagement Charts

Add Plotly chart components for casualty breakdown and engagement analysis.

- **`frontend/src/components/charts/CasualtyBreakdownChart.tsx`** (new):
  - Stacked bar chart: X axis = tick buckets or weapon types, Y axis = casualty count, color = side
  - Group-by toggle: by weapon type / by tick / by engine type
  - Uses `fetchCasualtyAnalytics` with TanStack Query
- **`frontend/src/components/charts/EngagementSummaryChart.tsx`** (new):
  - Horizontal bar chart: engagement types ranked by count
  - Hit rate annotation per type (e.g., "Direct Fire: 847 engagements, 23% hit rate")
  - Uses `fetchEngagementAnalytics`
- **`frontend/src/pages/runs/tabs/ChartsTab.tsx`** (modified):
  - Add casualty and engagement charts below existing force strength and morale charts

**Tests** (~6):
- CasualtyBreakdownChart renders with mock data
- EngagementSummaryChart renders with mock data
- Charts handle empty analytics (no events) gracefully
- Group-by toggle updates chart data

### 93c: Suppression & Morale Panels

Add visualization components for suppression metrics and morale state distribution.

- **`frontend/src/components/charts/SuppressionChart.tsx`** (new):
  - Line chart: suppressed unit count over ticks
  - Annotations for peak suppression tick and rout cascade events
  - Uses `fetchSuppressionAnalytics`
- **`frontend/src/components/charts/MoraleDistributionChart.tsx`** (new):
  - Stacked area chart: morale state distribution (confident/shaken/broken/routed) over ticks
  - Shows the "morale wave" — how morale cascades through the force
  - Uses `fetchMoraleAnalytics`
- **`frontend/src/pages/runs/tabs/ChartsTab.tsx`** (modified):
  - Add suppression and morale distribution charts

**Tests** (~4):
- SuppressionChart renders with peak annotation
- MoraleDistributionChart renders stacked areas
- Both handle zero-event runs

### 93d: Analytics Summary Card

Add a summary card to the results overview tab showing key diagnostic metrics at a glance.

- **`frontend/src/pages/runs/tabs/ResultsTab.tsx`** (modified):
  - Add analytics summary section below victory result:
    - Total engagements, hit rate, peak suppressed, dominant weapon type, morale collapse point
  - Uses `fetchAnalyticsSummary` (single request for all metrics)
  - Render as `StatCard` grid (reuse existing component)

**Tests** (~3):
- Summary card renders all metric fields
- Handles missing analytics gracefully
- Loading state while analytics compute

### Exit Criteria
- 4 new chart components rendering in the charts tab
- Analytics summary card on results tab
- All charts handle empty/loading/error states
- Mock-based tests pass (no API server required)

---

## Phase 94: Tactical Map Enrichment

**Status**: Complete.

**Goal**: Enhance the tactical map to visualize unit state using the enriched frame data from Phase 92. Transform the map from a position tracker into a battlefield status display.

**Dependencies**: Phase 92 (enriched frames).

### 94a: Morale & Health Overlays

Add morale-based color coding and health bars to unit markers on the tactical map.

- **`frontend/src/components/map/UnitMarker.ts`** or equivalent drawing code (modified):
  - Unit fill color determined by `morale` field:
    - 0 (CONFIDENT) → side color (existing blue/red)
    - 1 (SHAKEN) → yellow tint
    - 2 (BROKEN) → orange tint
    - 3 (ROUTED) → red (both sides)
    - 4 (RALLIED) → green tint
  - Health bar: thin horizontal bar below marker, width proportional to `health` (1.0 = full width, 0.0 = zero), color gradient green→red
- **`frontend/src/components/map/MapControls.tsx`** or equivalent (modified):
  - Add toggle: "Show morale" (default on)
  - Add toggle: "Show health" (default on)

**Tests** (~4):
- Morale colors applied correctly for each state
- Health bar width scales with health value
- Toggles control overlay visibility
- Backward compat: frames without morale/health use defaults

### 94b: Posture & Suppression Indicators

Add posture icons and suppression visual effects.

- **`frontend/src/components/map/`** (modified):
  - Posture indicator: small icon or letter overlay on unit marker
    - MOVING → no indicator (default)
    - DEFENSIVE → shield icon or "D"
    - DUG_IN → shovel icon or "E" (entrenched)
    - ASSAULT → arrow icon or "A"
    - ON_STATION → crosshair or "S" (aircraft)
    - ANCHORED → anchor icon (naval)
  - Suppression effect: opacity reduction proportional to suppression level
    - Level 0 → full opacity
    - Level 4 → 30% opacity (nearly transparent)
  - Add toggles: "Show posture" (default off), "Show suppression" (default on)

**Tests** (~4):
- Posture indicators render for each posture type
- Suppression opacity scales correctly
- Toggles control visibility

### 94c: Logistics & Engagement Indicators

Add fuel/ammo bars and engagement flash effects.

- **`frontend/src/components/map/`** (modified):
  - Fuel/ammo bars: two thin vertical bars to the right of unit marker
    - Fuel (blue bar), Ammo (orange bar)
    - Height proportional to percentage (1.0 = full, 0.0 = empty)
    - Show warning color (red) when below 20%
  - Engagement flash: brief highlight (expanding ring) on units where `engaged=true`
    - Auto-fades over 500ms (animation frame)
  - Add toggle: "Show logistics" (default off — visual clutter at scale)

**Tests** (~3):
- Fuel/ammo bars render with correct heights
- Warning color triggers below threshold
- Engagement flash renders and auto-fades

### 94d: Enhanced Unit Detail Sidebar

Expand the unit detail sidebar (shown on unit click) with the enriched frame data.

- **`frontend/src/components/map/UnitDetailSidebar.tsx`** or equivalent (modified):
  - Show current morale state (text + color badge)
  - Show posture (text + icon)
  - Show health bar (percentage + visual bar)
  - Show fuel/ammo percentages
  - Show suppression level (0–4 with description)
  - Show engagement status (idle / engaging / under fire)
  - Show unit type, domain, side (existing)

**Tests** (~3):
- Sidebar renders all enriched fields
- Missing fields show "N/A" or defaults
- Sidebar updates when clicking different units

### 94e: Map Legend

Add a legend panel explaining all visual indicators.

- **`frontend/src/components/map/MapLegend.tsx`** (new):
  - Collapsible panel in corner of map
  - Sections: Side colors, Morale colors, Posture icons, Health bar, Fuel/Ammo bars, Suppression opacity
  - Only shows sections for currently-enabled overlays

**Tests** (~2):
- Legend renders all sections
- Legend updates when overlays are toggled

### Exit Criteria
- Morale color coding visible on unit markers
- Health bars visible below units
- Posture icons visible (when toggled on)
- Suppression opacity effect working
- Unit detail sidebar shows all enriched state
- Map legend explains all overlays
- Performance: <16ms frame render at 300 units with all overlays enabled

---

## Phase 95: Calibration & Scenario Editor Depth

**Status**: Complete.

**Goal**: Expose hidden calibration parameters and scenario configuration options in the editor UI. Highest-value additions: per-side calibration, doctrine/commander pickers, and expanded morale tuning.

**Dependencies**: Phase 92 (metadata endpoints for schools/commanders/doctrines).

### 95a: Per-Side Calibration Panel

Add a per-side calibration section to CalibrationSliders. Users select a side (blue/red) and adjust per-side parameters.

- **`frontend/src/pages/editor/CalibrationSliders.tsx`** (modified):
  - New collapsible section: "Per-Side Overrides"
  - Side tab selector: Blue | Red
  - Per-side sliders:
    - `cohesion` (0.0–1.0, step 0.05, default 0.7)
    - `force_ratio_modifier` (0.1–5.0, step 0.1, default 1.0)
    - `hit_probability_modifier` (0.1–3.0, step 0.1, default 1.0)
    - `target_size_modifier` (0.1–3.0, step 0.1, default 1.0)
  - Maps to `config_overrides.side_overrides.{blue|red}.{key}` in YAML
  - Label each slider with the side name for clarity
- **`frontend/src/types/editor.ts`** (modified):
  - Add `SET_SIDE_CALIBRATION` action type to `EditorAction` union
  - Reducer handles nested `side_overrides` path

**Tests** (~5):
- Per-side sliders render with default values
- Changing blue cohesion dispatches correct action with nested path
- Side tab switches between blue/red parameter sets
- Config diff shows per-side changes
- YAML preview includes side_overrides structure

### 95b: Expanded Morale & Rout Cascade Sliders

Add the missing morale sub-fields and rout cascade parameters to CalibrationSliders.

- **`frontend/src/pages/editor/CalibrationSliders.tsx`** (modified):
  - Expand existing "Morale" section with additional sliders:
    - `morale_base_degrade_rate` (0.001–0.1, step 0.001, default 0.05)
    - `morale_casualty_weight` (0.1–5.0, step 0.1, default 2.0)
    - `morale_force_ratio_weight` (0.0–2.0, step 0.1, default 0.5)
    - `morale_check_interval` (5–60, step 5, default 15)
  - New collapsible section: "Rout Cascade"
    - `rout_cascade_radius_m` (100–5000, step 100, default 200)
    - `rout_cascade_base_chance` (0.01–0.5, step 0.01, default 0.05)

**Tests** (~3):
- Morale sub-field sliders render and dispatch correctly
- Rout cascade sliders render and dispatch correctly
- Default values match CalibrationSchema defaults

### 95c: Doctrine & Commander Pickers

Add dropdown selectors for doctrinal school and commander profile in the scenario editor.

- **`frontend/src/pages/editor/DoctrinePicker.tsx`** (new):
  - Per-side dropdown (Blue school / Red school) populated from `GET /meta/schools`
  - School description text shown below dropdown when selected
  - Maps to `config.schools_config.blue_school` / `.red_school`
  - "None" option to disable doctrinal AI for a side
- **`frontend/src/pages/editor/CommanderPicker.tsx`** (new):
  - Per-side dropdown populated from `GET /meta/commanders`
  - Trait preview card: shows aggression, caution, initiative values
  - Maps to `config.commander_config.side_defaults.blue` / `.red`
  - Era-aware filtering: only show commanders available for the scenario's era
- **`frontend/src/pages/editor/ScenarioEditorPage.tsx`** (modified):
  - Add DoctrinePicker and CommanderPicker sections after force editor
- **`frontend/src/api/meta.ts`** (new or modified):
  - `fetchSchools()`, `fetchCommanders()`, `fetchDoctrines()` API client functions
- **`frontend/src/types/editor.ts`** (modified):
  - Add `SET_SCHOOL` and `SET_COMMANDER` action types

**Tests** (~6):
- DoctrinePicker renders 9 school options + "None"
- CommanderPicker renders commander list with trait preview
- Selecting a school dispatches correct action
- Selecting a commander dispatches correct action
- YAML preview includes schools_config and commander_config
- Era filtering limits commander options

### 95d: Victory Weights Editor

Add sliders for victory condition weights.

- **`frontend/src/pages/editor/VictoryWeightsEditor.tsx`** (new):
  - Sliders for `victory_weights.force_ratio` (0.0–1.0, default 1.0), `.morale_ratio` (0.0–1.0, default 0.0), `.casualty_exchange` (0.0–1.0, default 0.0)
  - Display normalized percentages (e.g., 0.6/0.3/0.1 → 60%/30%/10%)
  - Warning message when all weights are zero
  - Maps to `config.calibration_overrides.victory_weights`
- **`frontend/src/pages/editor/ScenarioEditorPage.tsx`** (modified):
  - Add VictoryWeightsEditor section

**Tests** (~3):
- Sliders render with default weights
- Changing weights updates normalized display
- Config diff shows victory_weights changes

### Exit Criteria
- Per-side calibration panel functional with 4 sliders per side
- Expanded morale section with 4 additional sliders
- Rout cascade section with 2 sliders
- Doctrine picker with 9 schools per side
- Commander picker with trait preview and era filtering
- Victory weights editor with normalized display
- All changes reflected in YAML preview and config diff

---

## Phase 96: Analysis & Event Interaction

**Status**: Complete.

**Goal**: Enhance the analysis page with doctrine comparison and the events tab with filtering and engagement detail. Transform raw event data into interactive, explorable diagnostics.

**Dependencies**: Phase 92 (analytics endpoints), Phase 93 (chart patterns established).

### 96a: Event Filtering & Search

Add client-side filtering to the events tab. Events are already loaded in the frontend — filtering is pure client-side logic, no API changes.

- **`frontend/src/pages/runs/tabs/EventsTab.tsx`** (modified):
  - Filter bar at top:
    - Event type multi-select dropdown (populated from unique event_types in data)
    - Side filter: All / Blue / Red
    - Tick range slider (min tick – max tick)
    - Text search: filter by unit ID, unit type, or event data content
  - Filtered count display: "Showing 342 of 10,847 events"
  - Clear filters button
  - Filters applied before virtualized list rendering (no performance impact — filter is O(n), list is virtual)

**Tests** (~5):
- Type filter reduces displayed events
- Side filter shows only matching events
- Tick range slider limits displayed range
- Text search matches unit IDs
- Clear filters restores full list
- Filtered count updates correctly

### 96b: Engagement Detail Panel

Add a detail panel that appears when clicking an engagement event in the events list. Shows the full engagement resolution chain.

- **`frontend/src/components/EngagementDetailPanel.tsx`** (new):
  - Panel slides in from side (or modal) showing:
    - Attacker: unit type, side, position
    - Target: unit type, side, position
    - Weapon: name, ammo type, range
    - Resolution: Pk, modifiers applied (list), hit/miss outcome
    - Damage: damage type, severity, subsystem affected
    - Environmental factors: weather modifier, concealment, terrain, posture protection
  - Data sourced from event's `data` dict (already contains these fields)
  - Close button returns to event list
- **`frontend/src/pages/runs/tabs/EventsTab.tsx`** (modified):
  - Engagement events in list are clickable
  - Click opens EngagementDetailPanel with that event's data

**Tests** (~4):
- Panel renders all engagement fields
- Panel opens on event click
- Panel handles missing fields gracefully
- Close button dismisses panel

### 96c: Doctrine Comparison Analysis

Add a new analysis type: run the same scenario with different doctrinal schools and compare outcomes.

- **`frontend/src/pages/analysis/DoctrineComparePanel.tsx`** (new):
  - Scenario selector (existing pattern from ComparePanel)
  - Side to vary: Blue / Red / Both
  - Schools to include: multi-select checkbox list (9 schools)
  - Iterations per school (slider: 5–50, default 10)
  - Submit triggers batch runs via API
  - Results: grouped bar chart (school × win rate, casualties, duration)
  - Heatmap variant: school × metric matrix with color intensity
- **`api/routers/analysis.py`** (modified):
  - `POST /analysis/doctrine-compare` endpoint:
    - Input: scenario, side, schools list, iterations
    - Runs N schools × I iterations (serial or parallel via batch infrastructure)
    - Returns: per-school aggregate metrics
    - Uses existing `run_comparison` infrastructure with school config overrides
- **`api/schemas.py`** (modified):
  - `DoctrineCompareRequest`, `DoctrineCompareResult`
- **`frontend/src/pages/analysis/AnalysisPage.tsx`** (modified):
  - Add "Doctrine Comparison" tab alongside existing Compare/Sweep/Batch

**Tests** (~6):
- API endpoint accepts request and returns structured results
- Frontend panel renders school selection
- Results chart renders with mock data
- Handles single-school case (baseline only)
- Progress indication while batch runs execute
- Error handling for failed runs

### Exit Criteria
- Event filtering functional with type/side/tick/text filters
- Engagement detail panel shows full resolution chain on click
- Doctrine comparison analysis runs and displays results
- All new components handle loading/empty/error states

---

## Phase 97: Data Catalog & Block 10 Validation

**Status**: Not started.

**Goal**: Add weapon and doctrine browsing pages (extending the existing unit catalog pattern), then validate all Block 10 changes with regression testing and documentation.

**Dependencies**: Phase 92 (metadata endpoints).

### 97a: Weapon Catalog Page

Add a weapon browsing page following the existing unit catalog pattern.

- **`frontend/src/pages/weapons/WeaponCatalogPage.tsx`** (new):
  - Table: weapon name, domain, category, max range, ROF
  - Filters: domain dropdown, category dropdown, text search
  - Sortable columns
  - Uses `fetchWeapons()` from meta API
- **`frontend/src/pages/weapons/WeaponDetailModal.tsx`** (new):
  - Modal with full weapon spec (ranges, accuracy, burst size, compatible ammo)
  - Compatible units list (which units carry this weapon)
  - Uses `fetchWeaponDetail(id)`
- **`frontend/src/pages/weapons/WeaponCard.tsx`** (new):
  - Card component for grid view (optional toggle between table/grid)
- **`frontend/src/components/Layout.tsx`** (modified):
  - Add "Weapons" to navigation sidebar
- **App router** (modified):
  - Add `/weapons` route

**Tests** (~5):
- Catalog page renders weapon list
- Filters reduce displayed weapons
- Detail modal opens on weapon click
- Empty state shown when no weapons match filters
- Navigation link present in sidebar

### 97b: Doctrine Catalog Page

Add a doctrine browsing page.

- **`frontend/src/pages/doctrines/DoctrineCatalogPage.tsx`** (new):
  - Card grid: doctrine name, description, era tags
  - Click → detail view with:
    - Philosophy summary
    - Weight table (if available from YAML)
    - Scenarios using this doctrine
  - Filter by era
  - Uses `fetchDoctrines()` from meta API
- **`frontend/src/components/Layout.tsx`** (modified):
  - Add "Doctrines" to navigation sidebar under a "Data" group (alongside Units, Weapons)
- **App router** (modified):
  - Add `/doctrines` route

**Tests** (~4):
- Catalog page renders doctrine list
- Detail view shows philosophy and weights
- Era filter limits displayed doctrines
- Navigation link present

### 97c: Block 10 Regression Validation

Verify that all Block 10 changes haven't broken the engine or existing UI.

- **Engine regression**: Run the evaluator on all 40 scenarios — all must produce correct winners
  - No engine changes were made, so this is a safety check
- **API regression**: Run existing API test suite — all endpoints still function correctly
- **Frontend regression**: Run vitest suite — all existing tests pass
- **Cross-browser**: Manual verification on Chrome, Firefox, Edge
- **Accessibility**: Verify new components have proper aria labels, keyboard navigation, focus management
- **Performance**: Map rendering at 300 units with all new overlays enabled — verify <16ms per frame

**Tests** (~6):
- Evaluator regression (40 scenarios, correct winners)
- New analytics endpoints integration test (submit run, wait, query analytics)
- New metadata endpoints return non-empty data
- Frame enrichment produces valid field ranges

### 97d: Documentation & Lockstep

Update all living documents to reflect Block 10 completion.

- **CLAUDE.md**: Add Block 10 phases, update test counts, update status
- **README.md**: Update phase badge, test count, Block 10 status
- **docs/index.md**: Update landing page status, test count
- **devlog/index.md**: Add Phase 92–97 entries
- **devlog/phase-92.md through phase-97.md**: Create devlog entries
- **development-phases-block10.md**: Mark all phases Complete
- **mkdocs.yml**: Add new devlog entries to nav
- **MEMORY.md**: Update current status, block summary
- **docs/reference/api.md**: Add analytics, metadata, and enriched frame documentation
- **docs/guide/scenarios.md**: Note doctrine/commander picker availability

### Exit Criteria
- Weapon catalog page functional with filtering and detail modals
- Doctrine catalog page functional with era filtering
- All 40 scenarios produce correct winners (evaluator regression)
- All existing tests pass (Python + vitest)
- Documentation updated across all living documents
- Block 10 COMPLETE

---

## Module-to-Phase Index

### API Files

| File | Phase | Action |
|------|-------|--------|
| `api/routers/analytics.py` | 92a | New |
| `api/routers/meta.py` | 92c | Modified |
| `api/routers/runs.py` | 92b | Modified |
| `api/routers/analysis.py` | 96c | Modified |
| `api/schemas.py` | 92a, 92b, 92c, 96c | Modified |

### Frontend Files

| File | Phase | Action |
|------|-------|--------|
| `frontend/src/api/analytics.ts` | 93a | New |
| `frontend/src/api/meta.ts` | 95c | New |
| `frontend/src/types/analytics.ts` | 93a | New |
| `frontend/src/types/editor.ts` | 95a, 95c | Modified |
| `frontend/src/components/charts/CasualtyBreakdownChart.tsx` | 93b | New |
| `frontend/src/components/charts/EngagementSummaryChart.tsx` | 93b | New |
| `frontend/src/components/charts/SuppressionChart.tsx` | 93c | New |
| `frontend/src/components/charts/MoraleDistributionChart.tsx` | 93c | New |
| `frontend/src/components/map/MapLegend.tsx` | 94e | New |
| `frontend/src/components/EngagementDetailPanel.tsx` | 96b | New |
| `frontend/src/pages/editor/CalibrationSliders.tsx` | 95a, 95b | Modified |
| `frontend/src/pages/editor/DoctrinePicker.tsx` | 95c | New |
| `frontend/src/pages/editor/CommanderPicker.tsx` | 95c | New |
| `frontend/src/pages/editor/VictoryWeightsEditor.tsx` | 95d | New |
| `frontend/src/pages/editor/ScenarioEditorPage.tsx` | 95c, 95d | Modified |
| `frontend/src/pages/runs/tabs/ChartsTab.tsx` | 93b, 93c | Modified |
| `frontend/src/pages/runs/tabs/ResultsTab.tsx` | 93d | Modified |
| `frontend/src/pages/runs/tabs/EventsTab.tsx` | 96a, 96b | Modified |
| `frontend/src/pages/analysis/AnalysisPage.tsx` | 96c | Modified |
| `frontend/src/pages/analysis/DoctrineComparePanel.tsx` | 96c | New |
| `frontend/src/pages/weapons/WeaponCatalogPage.tsx` | 97a | New |
| `frontend/src/pages/weapons/WeaponDetailModal.tsx` | 97a | New |
| `frontend/src/pages/weapons/WeaponCard.tsx` | 97a | New |
| `frontend/src/pages/doctrines/DoctrineCatalogPage.tsx` | 97b | New |
| `frontend/src/components/Layout.tsx` | 97a, 97b | Modified |
| `frontend/src/components/map/*` | 94a–94d | Modified |

### Documentation Files

| File | Phase | Action |
|------|-------|--------|
| `docs/brainstorm-block10.md` | Pre-block | New |
| `docs/development-phases-block10.md` | Pre-block | New |
| `docs/devlog/phase-92.md` through `phase-97.md` | 97d | New |
| `CLAUDE.md` | 97d | Modified |
| `README.md` | 97d | Modified |
| `docs/index.md` | 97d | Modified |
| `docs/devlog/index.md` | 97d | Modified |
| `mkdocs.yml` | 97d | Modified |
| `MEMORY.md` | 97d | Modified |
| `docs/reference/api.md` | 97d | Modified |

### Test Estimates

| Phase | New Tests | Modified Tests |
|-------|-----------|----------------|
| 92 | ~26 | 0 |
| 93 | ~17 | 0 |
| 94 | ~16 | 0 |
| 95 | ~17 | 0 |
| 96 | ~15 | 0 |
| 97 | ~15 | 0 |
| **Total** | **~106** | **0** |

# Web UI Guide

This guide covers the Stochastic Warfare web application -- how to start it, browse scenarios, run simulations, explore results, edit scenarios, and export data.

---

## Prerequisites

- **Python >= 3.12** with `uv` installed
- **Node.js >= 18** (v22 recommended)
- API dependencies: `uv sync --extra api`
- Frontend dependencies: `cd frontend && npm install`

## Starting the Application

The web app consists of two servers: a Python API backend and a React frontend.

```bash
# Terminal 1: Start the API server
uv sync --extra api
uv run uvicorn api.main:app --reload    # http://localhost:8000

# Terminal 2: Start the frontend dev server
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Open **http://localhost:5173** in your browser. The frontend proxies all `/api` requests to the backend automatically.

!!! tip
    The API server must be running for the frontend to load data. If you see "Connecting..." in the sidebar, check that the API server is running on port 8000.

---

## Navigation

The sidebar provides access to four main sections:

| Section | What It Shows |
|---------|--------------|
| **Scenarios** | Browse and search all available scenarios |
| **Units** | Catalog of all unit definitions across eras |
| **Runs** | Simulation run history and live tracking |
| **Analysis** | Batch Monte Carlo, A/B comparison, sensitivity sweeps |

The sidebar shows a connection indicator (green dot = connected) and counts of available scenarios and units. On mobile screens, the sidebar collapses into a hamburger menu.

### Dark Mode

A theme toggle button in the sidebar footer switches between light and dark mode. The preference is saved to `localStorage` and persists across sessions. Dark mode applies to all pages, components, and the tactical map.

---

## Scenario Browser

### List View

The default page shows all scenarios as cards. Each card displays:

- Scenario name and era badge (color-coded)
- Duration and force count
- Optional subsystem badges (EW, CBRN, Escalation, Schools, Space, DEW)

**Filtering and search:**

- **Search** -- type in the search box to filter by name
- **Era filter** -- click era tabs to show only scenarios from a specific era
- **Sort** -- sort by name, duration, or era

### Detail View

Click a scenario card to see its full configuration:

- **Terrain** -- dimensions, cell size, terrain type
- **Weather** -- visibility, wind, temperature, cloud cover
- **Forces** -- per-side unit composition tables with counts and key stats
- **Objectives** -- positions and assigned sides
- **Victory conditions** -- what triggers the end of the simulation
- **Optional configs** -- which subsystems are enabled (shown as colored badges)
- **Documented outcomes** -- historical reference data (for validated scenarios)

**Actions on the detail page:**

| Button | What It Does |
|--------|-------------|
| **Run This Scenario** | Navigate to the run configuration page |
| **Download YAML** | Download the scenario configuration as a YAML file |
| **Clone & Tweak** | Open the scenario editor with a copy of this scenario |

---

## Unit Catalog

The unit catalog page lists all unit definitions with key statistics.

**Filtering:**

- **Search** -- filter by unit name or type
- **Domain** -- ground, air, naval surface, naval subsurface
- **Era** -- Modern, WW2, WW1, Napoleonic, Ancient/Medieval

Click a unit to open a detail modal showing the full specification: weapons, sensors, communications, armor, speed, and signature profile.

---

## Running Simulations

### Submitting a Run

From a scenario detail page, click **Run This Scenario** to reach the run configuration page. Configure:

- **Seed** -- random seed for reproducibility (default: 42)
- **Max ticks** -- safety limit to prevent runaway simulations

Click **Start Run** to submit. You'll be redirected to the run detail page.

### Live Progress

While a simulation is running, the run detail page shows live progress via WebSocket:

- **Progress bar** -- tick advancement toward completion
- **Active units** -- per-side count of surviving units
- **Events** -- running count of simulation events
- **Connection status** -- green (connected), yellow (reconnecting), red (failed)

If the WebSocket connection drops, the app automatically attempts reconnection with exponential backoff (up to 3 attempts). If reconnection fails, it falls back to polling the API.

### Run History

The **Runs** page shows all past and current runs in a table:

- Scenario name, seed, status, duration, victor, timestamp
- Status badges: pending (gray), running (blue), completed (green), failed (red)
- Click any row to view the run detail

---

## Run Results

After a simulation completes, the run detail page shows results across several tabs.

### Overview

- **Victory result** -- which side won and by what condition
- **Timing** -- simulation ticks, wall-clock duration
- **Force summary** -- surviving units per side

### Charts

Five interactive Plotly charts, all supporting zoom, pan, hover tooltips, and legend filtering:

| Chart | What It Shows |
|-------|--------------|
| **Force Strength** | Stacked area chart of active units over time per side |
| **Engagement Timeline** | Scatter plot of engagements (tick vs range), colored by hit/miss |
| **Morale Progression** | Step chart of morale state changes |
| **Event Activity** | Histogram of events per tick (operational tempo) |
| **Comparison** | Side-by-side metrics (when comparing two runs) |

**Tick sync**: When the tactical map is playing back at a specific tick, all four charts show a vertical reference line at that tick. Clicking any data point on a chart sets the `?tick=N` URL parameter, which the map reads to jump to that tick -- bidirectional sync between charts and map.

### Narrative

A text narrative of the battle, generated from simulation events. Controls:

- **Side filter** -- show events for one side or all
- **Style** -- full (detailed), summary (key events only), or timeline (chronological list)

### Map

The tactical map tab shows a 2D spatial visualization of the simulation. See [Tactical Map](#tactical-map) below for details.

### Export

The export menu (dropdown in the page header) provides:

| Option | Format | Contents |
|--------|--------|----------|
| **Export JSON** | `.json` | Full run result data |
| **Export Events CSV** | `.csv` | Complete event log with columns for tick, type, side, details |
| **Download Narrative** | `.txt` | Battle narrative text |
| **Print Report** | Browser print | Print-optimized summary with forces, narrative, and key statistics |

All downloads are generated client-side (no server round-trip).

---

## Scenario Editor (Clone & Tweak)

The scenario editor lets you modify an existing scenario and run it with your changes. Access it via the **Clone & Tweak** button on any scenario detail page.

### Layout

Two-column layout:

- **Left column** -- form sections for editing (scrollable)
- **Right column** -- live YAML preview + terrain preview (sticky)

### Editing Sections

**General** -- name, duration (hours), era, date

**Terrain** -- width, height, cell size, base elevation, terrain type (10 options: flat desert, forest, urban, mixed, rolling hills, mountain, coastal, arctic, jungle, swamp)

**Weather** -- visibility, wind speed, wind direction, temperature, cloud cover

**Forces** -- per-side panels with:

- Unit list showing type, count, and controls (+/- buttons, remove)
- **Add Unit** button opens the unit picker modal
- Experience level slider (0.0--1.0)
- Morale selector

**Unit Picker** -- modal with search, domain filter tabs, and era filtering. Click a unit to add it to the current side.

**Config Toggles** -- enable/disable optional subsystems:

| Toggle | Subsystem |
|--------|-----------|
| EW | Electronic Warfare (jamming, spoofing, ECCM) |
| CBRN | Chemical, Biological, Radiological, Nuclear effects |
| Escalation | Escalation ladder and political pressure |
| Schools | Doctrinal AI schools |
| Space | Space and satellite systems |
| DEW | Directed energy weapons |

Enabling a toggle adds sensible default configuration. Disabling removes the config entirely.

**Calibration Sliders** -- fine-tune simulation parameters:

| Slider | Range | Default | Effect |
|--------|-------|---------|--------|
| Hit Probability Modifier | 0.1--3.0 | 1.0 | Scales all hit probabilities |
| Target Size Modifier | 0.1--3.0 | 1.0 | Scales target detection signatures |
| Morale Degrade Rate | 0.1--5.0 | 1.0 | Scales morale degradation speed |
| Thermal Contrast | 0.1--5.0 | 1.0 | Scales thermal sensor effectiveness |

### YAML Preview

The right panel shows the live YAML representation of your edited configuration. It updates in real-time as you make changes. Use the **Copy** button to copy the YAML to your clipboard.

### Terrain Preview

Below the YAML preview, a small canvas shows an approximate terrain visualization: terrain type color fill, objective circles, and dimension labels.

### Actions

| Button | What It Does |
|--------|-------------|
| **Validate** | Sends configuration to the API for pydantic validation; shows errors if invalid |
| **Run This Config** | Validates and submits the configuration; navigates to the run detail page |
| **Download YAML** | Downloads the edited configuration as a YAML file |

---

## Tactical Map

The tactical map provides a 2D spatial visualization of a completed simulation run. Access it from the **Map** tab on any completed run, or click the fullscreen button to open it in a dedicated page.

### Terrain

The map renders the terrain grid with cells colored by land cover type (desert/tan, forest/green, urban/gray, water/blue, mountain/brown). Objective zones are shown as highlighted circles. When elevation data is available, cells are brightness-modulated -- higher elevations appear slightly brighter, lower elevations slightly darker -- giving a visual sense of terrain relief.

### Units

Units are displayed as side-colored markers (blue/red) with domain-specific shapes:

- **Diamond** -- armor
- **Circle** -- infantry
- **Triangle** -- aircraft
- **Pentagon** -- naval

Destroyed units are shown with reduced opacity and a red X overlay. Click a unit to see details in the sidebar (type, health, morale, ammunition, position).

### Overlays

- **Engagement arcs** -- lines from attacker to target, colored by result (hit/miss). Arcs fade smoothly over a 10-tick window instead of appearing/disappearing instantly.
- **Movement trails** -- fading polylines showing recent unit paths
- **Sensor circles** -- when the "Sensors" toggle is on and a unit is selected, a dashed semi-transparent circle shows the unit's maximum sensor range

### Map Controls

The control bar above the map provides several toggles:

| Toggle | Effect |
|--------|--------|
| **Labels** | Show/hide unit ID labels |
| **Destroyed** | Show/hide destroyed units |
| **Engagements** | Show/hide engagement arcs |
| **Trails** | Show/hide movement trails |
| **Sensors** | Show/hide sensor range circle for the selected unit |
| **FOW** | Enable Fog of War view (see below) |
| **Fit** | Reset zoom to fit all units |

Mouse world coordinates (easting/northing) are displayed when hovering over the map.

### Fog of War (FOW)

The FOW toggle enables a "what does this side see?" view. When active:

1. A side selector dropdown appears (e.g., Blue / Red)
2. Only units that the selected side has detected are visible -- undetected enemy units are hidden entirely
3. Friendly units (same side as selected) are always shown

This uses the simulation's actual detection data from the `FogOfWarManager`, showing what each side believed at each tick. The FOW toggle is disabled for runs that don't have detection data (e.g., older runs or scenarios without fog of war).

### Playback Controls

The map includes a timeline scrubber and transport controls for stepping through the simulation:

| Control | Action |
|---------|--------|
| Play/Pause | Start or stop automatic playback |
| Step Forward | Advance one tick |
| Step Backward | Go back one tick |
| Speed 1x/2x/5x/10x | Set playback speed |
| Timeline Scrubber | Drag to jump to any tick |

### Zoom and Pan

- **Mouse wheel** -- zoom in/out
- **Click and drag** -- pan the viewport

---

## Keyboard Shortcuts

Keyboard shortcuts are available on the tactical map and fullscreen map pages. Press **?** to see the shortcut help modal.

| Key | Action |
|-----|--------|
| `Space` | Play / pause playback |
| `Right Arrow` | Step forward one tick |
| `Left Arrow` | Step backward one tick |
| `1` | Set playback speed to 1x |
| `2` | Set playback speed to 2x |
| `3` | Set playback speed to 5x |
| `4` | Set playback speed to 10x |
| `?` | Show keyboard shortcut help |

Shortcuts are disabled when typing in input fields, text areas, or select elements.

---

## Analysis

The Analysis page provides three tools for statistical analysis of simulation results.

### Batch Monte Carlo

Run multiple iterations of the same scenario with different seeds to build statistical distributions:

1. Select a scenario
2. Set the number of iterations and base seed
3. Click **Run Batch**
4. View results: metric histograms, summary statistics, convergence plots

### A/B Comparison

Compare two different configurations side by side:

1. Select two scenarios (or the same scenario with different parameters)
2. Set seeds and iteration counts
3. View: side-by-side force strength charts, Mann-Whitney U test results, effect sizes

### Sensitivity Sweep

Test how a single parameter affects outcomes:

1. Select a scenario and parameter to sweep
2. Set the range and number of steps
3. View: errorbar chart of metric vs parameter value

---

## API Server Configuration

The API server is configured via environment variables (prefix `SW_API_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SW_API_HOST` | `127.0.0.1` | Bind address |
| `SW_API_PORT` | `8000` | Port |
| `SW_API_DB_PATH` | `data/api_runs.db` | SQLite database path |
| `SW_API_MAX_CONCURRENT_RUNS` | `4` | Max parallel simulation runs |
| `SW_API_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |

Run history is stored in the SQLite database and persists across server restarts.

---

## Production Build

To build the frontend for production deployment:

```bash
cd frontend
npm run build     # TypeScript check + Vite production bundle
```

The built files are output to `frontend/dist/` and can be served by any static file server. In production, configure the static server to proxy `/api` requests to the Python API server.

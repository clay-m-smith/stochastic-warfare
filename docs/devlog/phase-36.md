# Phase 36: Scenario Tweaker & Polish

**Status**: Complete
**Date**: 2026-03-06
**Tests**: ~59 new (13 Python + 46 vitest), ~7,705 total (7,474 Python + 231 vitest)

## Overview

Final phase of Block 3. Adds clone-and-tweak scenario editing, export capabilities, keyboard shortcuts, and application polish. Zero simulation engine changes.

## Sub-phases

### 36a: Scenario Tweaker
- Backend: `POST /api/scenarios/validate` (pydantic CampaignScenarioConfig validation), `POST /api/runs/from-config` (inline config → temp YAML → RunManager)
- Frontend: `useScenarioEditor` reducer hook (11 action types), ScenarioEditorPage (two-column layout), GeneralSection, TerrainSection, WeatherSection, ForceEditor, UnitPicker modal, ConfigToggles (6 optional systems), CalibrationSliders (4 params), YamlPreview
- Route: `/scenarios/:name/edit`, "Clone & Tweak" button on ScenarioDetailPage

### 36b: Terrain Preview
- TerrainPreview canvas component showing terrain type color fill, objective circles, dimension labels
- `terrainTypeColors.ts` — 10 terrain type string → color mappings

### 36c: Export & Reporting
- `useExport` hook: downloadJSON, downloadCSV, downloadYAML (client-side Blob + invisible anchor), printReport (navigate)
- `ExportMenu` component (Headless UI Menu dropdown)
- `PrintReportPage` — print-optimized layout with summary, forces, narrative. Auto-triggers `window.print()`
- `eventsToCsvRows` in format.ts
- "Download YAML" button on ScenarioDetailPage
- Export menu on RunDetailPage (JSON, CSV, narrative txt, print)

### 36d: Polish
- `useKeyboardShortcuts` hook — global keydown listener, skips inputs/textareas
- `KeyboardShortcutHelp` modal (Headless UI Dialog)
- Map keyboard shortcuts: Space (play/pause), Arrow keys (step), 1-4 (speed)
- Responsive sidebar: mobile hamburger + overlay, desktop always-visible
- `ErrorMessage` variant prop: `error` | `warning` | `connection`
- WebSocket reconnect: exponential backoff (1s/2s/4s), max 3 attempts, `connectionState` enum
- `RunProgressPanel`: connection state display, polling fallback on WS failure

## Dependencies
- New npm: `js-yaml` + `@types/js-yaml`

## File Inventory

### Backend (3 modified + 1 new test)
- `api/schemas.py` — 3 new models (RunFromConfigRequest, ValidateConfigRequest, ValidateConfigResponse)
- `api/routers/scenarios.py` — POST /validate endpoint
- `api/routers/runs.py` — POST /from-config endpoint
- `tests/api/test_scenario_editor.py` — 13 tests

### Frontend (~20 new + ~12 modified)
- 12 new page/component files in `src/pages/editor/`
- 3 new lib/hook files (yamlExport, useExport, useKeyboardShortcuts)
- 3 new component files (ExportMenu, KeyboardShortcutHelp, PrintReportPage)
- 1 new types file (editor.ts), 1 new API client (editor.ts)
- Modified: App.tsx, Layout.tsx, Sidebar.tsx, ErrorMessage.tsx, RunDetailPage.tsx, ScenarioDetailPage.tsx, RunProgressPanel.tsx, TacticalMap.tsx, useWebSocket.ts, format.ts

### Test Files (11 new)
- 6 frontend test files for 36a (editor, API, hooks, pages)
- 1 frontend test for 36b (TerrainPreview)
- 2 frontend tests for 36c (useExport, ExportMenu)
- 2 frontend tests for 36d (useKeyboardShortcuts, KeyboardShortcutHelp)

## Design Decisions
1. **Inline config via temp YAML**: `POST /from-config` writes to `tempfile.mkdtemp()`, avoids filesystem persistence of custom scenarios
2. **Client-side YAML download**: `js-yaml` serializes config dict, browser download via Blob — no backend write endpoint
3. **No PDF library**: `window.print()` with print-optimized CSS, Plotly charts excluded from print
4. **Validation via backend**: Single source of truth using pydantic CampaignScenarioConfig
5. **Keyboard shortcuts skip inputs**: Global keydown, checks `e.target.tagName`
6. **WS reconnect with backoff**: 3 attempts max, falls back to polling

## Lessons Learned
- **`@headlessui/react` v2 requires ResizeObserver**: Test environments need `vi.stubGlobal('ResizeObserver', ...)` for Menu components
- **JSX in test files needs `.tsx` extension**: vitest with esbuild won't transform JSX in `.ts` files
- **`structuredClone` for state init**: Prevents shared reference bugs in reducer initializer
- **Canvas mock strategy carries forward**: Same pattern from Phase 35 — mock `getContext` with property setters for style props

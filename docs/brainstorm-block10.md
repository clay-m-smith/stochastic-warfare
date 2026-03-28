# Block 10: UI Depth & Engine Exposure

## Motivation

Blocks 1–9 delivered 91 phases of engine capability: 60+ domain engines, 32 `enable_*` behavioral flags, 68 calibration parameters, 9 doctrinal schools, 5 historical eras, 100+ event types, and 40 validated scenarios across ~10,638 tests. The engine is comprehensive, historically validated, and performant for scenarios up to ~300 units.

The web UI, however, was built in Block 3 (Phases 31–36) when the engine had ~40% of its current features. Phase 80 (Block 8) added `enable_all_modern` and expanded CalibrationSliders, but this was a partial sync. The gap between what the engine computes and what the UI exposes is now the primary bottleneck for usability.

### Current UI Capabilities

| Page | What It Shows | What's Missing |
|------|---------------|----------------|
| **Scenario Browser** | List, era filter, domain badges | No weapon/doctrine/commander browsing |
| **Scenario Editor** | Forces, weather, terrain, 29 toggles + ~30 sliders | Per-side calibration, victory weights, weapon assignments, doctrine/commander pickers |
| **Run Config** | Scenario, seed, max_ticks, config overrides | No per-engine toggle panel, no halt conditions |
| **Results** | Force strength, engagement count, morale curves, event list, narrative | No per-weapon casualties, no suppression metrics, no engine attribution, no C2/EW diagnostics |
| **Tactical Map** | Terrain, unit positions, engagement arcs, FOW, sensor ranges | No morale/posture/suppression overlays, no fuel/ammo bars, no threat rings, no heat maps |
| **Analysis** | A/B compare, parameter sweep, tempo FFT | No doctrine comparison, no engine impact matrix, no per-run diagnostics |
| **Unit Catalog** | Unit type, domain, category, speed, crew | No weapon detail, no sensor matrix, no signature breakdown |

### The Exposure Gap

The engine records rich event data during simulation — every engagement includes the resolving engine, Pk modifiers, hit/miss outcome, damage type, weapon used, and environmental factors applied. This data flows through the EventBus, gets captured by the recorder, stored as JSON in SQLite, and returned via the API's `events_json` field. But the frontend displays it as a flat, unsearchable list of raw event objects.

Similarly, the tactical map receives per-frame unit data (`MapUnitFrame`) with only 9 fields (id, side, x, y, domain, status, heading, type, sensor_range). The engine knows each unit's morale state, posture, fuel level, ammo count, suppression level, and health — but none of this reaches the map.

The CalibrationSliders expose 29 toggles and ~30 numeric sliders out of 68 total CalibrationSchema fields. Missing: per-side overrides (cohesion, force_ratio_modifier, target_size_modifier per side), victory condition weights, weapon assignment overrides, target value weights, rout cascade parameters, and subsystem Weibull shapes.

### Design Principle

Block 10 adds **zero new engine capabilities**. Every feature in this block surfaces existing data through existing APIs to existing UI components. Where the API lacks a necessary endpoint or data field, we add it — but the simulation logic remains unchanged. This is the UI equivalent of Block 9's "make existing capabilities faster" philosophy: **make existing capabilities visible**.

---

## Theme 1: Diagnostic Analytics — Surfacing Hidden Data

**Problem**: The engine publishes 100+ event types through the EventBus during simulation. `EngagementEvent` carries the weapon used, target type, Pk modifiers, and outcome. `DamageEvent` carries damage type and severity. `SuppressionEvent` carries suppression level change. But the API returns all events as a flat JSON array, and the frontend renders them as a scrollable list with no aggregation, filtering, or visualization.

The result: users can see that "blue won in 185 ticks" but cannot answer "which weapon type caused the most casualties?" or "how many units were suppressed at peak?" or "did C2 friction affect engagement rates?"

**Solution**: Server-side analytics endpoints that aggregate event data into structured summaries. The raw events are already stored — we just need to compute views over them.

### Proposed Analytics Endpoints

| Endpoint | Input | Output | Source Events |
|----------|-------|--------|---------------|
| `GET /runs/{id}/analytics/casualties` | side, group_by (weapon/engine/tick) | Stacked counts | `EngagementEvent`, `DamageEvent`, `UnitDestroyedEvent` |
| `GET /runs/{id}/analytics/suppression` | — | Peak count, timeline, rout cascades | `SuppressionEvent`, `MoraleStateChangeEvent` |
| `GET /runs/{id}/analytics/morale` | — | State distribution per tick | `MoraleStateChangeEvent` |
| `GET /runs/{id}/analytics/c2` | — | Order delays, misinterpretations, planning time | C2 friction events |
| `GET /runs/{id}/analytics/engagements` | — | Count by engine/type, hit rate, avg Pk | `EngagementEvent` |

### Trade-offs

**Option A: Compute on read** — Parse `events_json` on each analytics request. Simple, no schema changes. Slow for large event sets (100K+ events).

**Option B: Compute on write** — When a run completes, compute all analytics summaries and store them as separate columns. Fast reads, but adds post-processing step and storage.

**Option C: Materialized views** — Compute on first read, cache result. Best of both: no write overhead, fast subsequent reads.

### Recommendation

**Option A** for initial implementation — the event JSON is already loaded for the events endpoint, and analytical aggregation is O(n) over events. If performance becomes an issue (>1s for 100K events), migrate to Option C with a `run_analytics_json` column.

---

## Theme 2: Replay Frame Enrichment

**Problem**: `MapUnitFrame` contains 9 fields: `id`, `side`, `x`, `y`, `domain`, `status`, `heading`, `type`, `sensor_range`. The tactical map can show unit positions and movement, but cannot visualize morale, posture, fuel, ammo, suppression, or health — all of which the engine tracks per unit per tick.

The frame recording code (in the API run execution) constructs `MapUnitFrame` from Unit objects during simulation. Enriching it requires reading additional Unit attributes during frame capture.

**Solution**: Extend `MapUnitFrame` with additional optional fields. Keep backward compatibility — old frames without these fields still render correctly.

### Proposed Fields

| Field | Type | Source | Map Visualization |
|-------|------|--------|-------------------|
| `morale` | `int` (0=CONFIDENT..4=ROUTED) | `unit.morale_state` | Color gradient (green→red) |
| `posture` | `str` | `unit.posture` (MOVING/DEFENSIVE/DUG_IN/ASSAULT) | Icon overlay |
| `health` | `float` (0.0–1.0) | `unit.health_fraction` | Opacity or health bar |
| `fuel_pct` | `float` (0.0–1.0) | `unit.fuel_remaining / unit.fuel_capacity` | Fuel bar |
| `ammo_pct` | `float` (0.0–1.0) | `unit.ammo_fraction` | Ammo bar |
| `suppression` | `int` (0–4) | `unit.suppression_level` | Pulsing/fading indicator |
| `engaged` | `bool` | Unit fired or was targeted this tick | Engagement highlight |

### Concerns

- **Frame size**: Adding 7 fields per unit per frame increases `frames_json` storage. At 300 units × 200 frames × 7 extra floats/ints, this is ~400KB additional — negligible vs current frame sizes.
- **Backward compatibility**: Old runs won't have enriched frames. Frontend must handle missing fields gracefully (default values).
- **Frame interval**: The existing `frame_interval` parameter controls how often frames are captured. Enrichment doesn't change this — same frames, richer data.

### Recommendation

Add all 7 fields to `MapUnitFrame`. Use `float = 0.0` / `int = 0` / `bool = False` defaults for backward compatibility. Update the frame recording code in the API run execution to read these attributes from Unit objects.

---

## Theme 3: Tactical Map Depth

**Problem**: The tactical map (Phase 35) renders terrain, unit markers (domain-specific shapes), engagement arcs, movement trails, sensor range circles, and FOW overlay. It's effective for spatial awareness but doesn't convey unit state — all units of the same side look identical regardless of their morale, posture, fuel level, or combat readiness.

**Solution**: Layer additional visual indicators onto the existing map renderer using the enriched frame data from Theme 2.

### Proposed Overlays

| Overlay | Visual | Toggle | Priority |
|---------|--------|--------|----------|
| **Morale gradient** | Unit fill color: green (CONFIDENT) → yellow (SHAKEN) → orange (BROKEN) → red (ROUTED) | `Show morale` checkbox | High |
| **Posture icon** | Small icon overlay: shield (DEFENSIVE), shovel (DUG_IN), arrow (ASSAULT), crosshair (ON_STATION) | `Show posture` checkbox | High |
| **Health bar** | Thin horizontal bar below unit marker (green→red, shrinks with damage) | `Show health` checkbox | High |
| **Fuel/ammo** | Two thin vertical bars beside unit marker (blue=fuel, orange=ammo) | `Show logistics` checkbox | Medium |
| **Suppression pulse** | Semi-transparent expanding ring for suppressed units (opacity = suppression level) | `Show suppression` checkbox | Medium |
| **Engagement flash** | Brief highlight on units that fired this tick | Auto (no toggle) | Low |

### Map Interaction Enhancements

| Feature | Description | Priority |
|---------|-------------|----------|
| **Unit filter** | Dropdown: All / Side / Domain / Status | High |
| **Click-to-detail** | Click unit → sidebar shows full state (morale, posture, fuel, ammo, weapons, target) | Already exists (basic) |
| **Heat map mode** | Toggle: engagement density, cumulative casualties, or time-spent heatmap | Medium |
| **Time slider** | Scrub to any tick without sequential playback | Medium |
| **Mini-map** | Inset overview for large battlefields | Low |

### Concerns

- **Canvas performance**: Adding overlays increases draw calls per frame. Benchmark at 300 units with all overlays enabled. If >16ms per frame, use layer caching (separate off-screen canvases per overlay type).
- **Visual clutter**: Too many overlays at once becomes unreadable. Default to morale + health only; others opt-in via toggles.
- **Legend**: Need a map legend panel explaining colors, icons, and bar meanings.

### Recommendation

Implement morale gradient, posture icons, and health bars first (highest information density, lowest visual clutter). Fuel/ammo and suppression as opt-in toggles. Heat map as a stretch goal. Time slider is high value but requires replay frame indexing changes.

---

## Theme 4: Calibration Surface Completeness

**Problem**: CalibrationSliders (Phase 80) exposes 29 boolean toggles and ~30 numeric sliders out of 68 CalibrationSchema fields. Several important calibration axes are edit-YAML-only:

| Hidden Parameter | Impact | Why It Matters |
|-----------------|--------|----------------|
| Per-side force_ratio_modifier | Dupuy CEV — the single most influential combat scalar | Users can't model asymmetric quality |
| Per-side cohesion | Unit cohesion affects morale cascade rate | Users can't model elite vs conscript |
| Per-side target_size_modifier | Side-specific detectability | Users can't model stealth vs conventional |
| Victory weights | Relative importance of casualties vs morale vs territory | Users can't tune victory conditions |
| Weapon assignments | Override which weapon a unit uses | Users can't model weapon substitution |
| Rout cascade params | Radius, base chance, shaken susceptibility | Users can't tune panic spread |
| Morale nested fields | 8 sub-fields (casualty_weight, suppression_weight, etc.) | Users can't tune individual morale drivers |

**Solution**: Extend CalibrationSliders with additional sections for per-side overrides, victory weights, and expanded morale tuning.

### Proposed UI Sections

**Per-Side Calibration** (new collapsible section):
- Side selector: blue / red
- Sliders: cohesion (0.0–1.0), force_ratio_modifier (0.1–5.0), hit_probability_modifier (0.1–3.0), target_size_modifier (0.1–3.0)
- These map to `side_overrides` in CalibrationSchema

**Victory Weights** (new section):
- Sliders for `victory_weights.casualties`, `victory_weights.morale`, `victory_weights.territory`
- Normalized display (show effective % after normalization)

**Morale Detail** (expand existing Morale section):
- Add sliders for `morale_base_degrade_rate` (0.001–0.1), `morale_casualty_weight` (0.1–5.0), `morale_force_ratio_weight` (0.0–2.0), `morale_check_interval` (5–60)
- These are already CalibrationSchema fields, just not in the slider UI

**Rout Cascade** (new section):
- Sliders: `rout_cascade_radius_m` (100–5000), `rout_cascade_base_chance` (0.01–0.5)

### Trade-offs

- **Complexity**: More sliders = more cognitive load. Mitigated by collapsible sections (existing pattern) and grouping by domain.
- **Per-side overrides**: Requires a side selector UI element, adding interaction complexity. Could use a tab (Blue | Red) or inline labels.
- **Validation**: Some combinations are pathological (e.g., force_ratio_modifier 5.0 for both sides). Could add warning badges for extreme values.

### Recommendation

Add per-side calibration, expanded morale, and rout cascade sections. Victory weights are valuable but require API-side normalization logic — defer if complex. Weapon assignment overrides require a table UI (unit_type → weapon_id mapping) — consider for a later phase.

---

## Theme 5: Scenario Configuration Depth

**Problem**: The scenario editor (Phase 36) lets users clone-and-tweak scenarios: modify forces, weather, terrain type, and calibration sliders. But several engine configuration axes have no UI at all:

| Config Area | Current UI | Engine Support |
|-------------|-----------|----------------|
| Doctrine/schools | None | 9 schools (Clausewitz, Maneuver, Attrition, AirLand, Air Power, Sun Tzu, Deep Battle, Mahanian, Corbettian) |
| Commander profile | None | 30+ named profiles with personality traits |
| Escalation | Boolean toggle only | 11-level ladder with desperation index, political pressure, consequences |
| EW config | Boolean toggle only | Jammer specs, SIGINT collectors, ECCM suites |
| Space config | Boolean toggle only | Constellation coverage, GPS spoofing, ASAT parameters |
| CBRN | Boolean toggle only | Agent type, dispersal model, protection levels |

Users who want to explore "what happens if I switch from Clausewitz to Maneuver doctrine?" must manually edit YAML. This is the single most requested exploration axis based on the engine's design emphasis on doctrinal AI.

**Solution**: Add dropdown selectors for doctrine and commander profiles in the scenario editor. These map to `schools_config` and `commander_config` in the scenario YAML.

### Proposed UI Elements

**Doctrine Panel** (new section in editor):
- Side selector: blue / red
- School dropdown: list of 9 schools + "none"
- Description text: 2-line summary of school philosophy when selected
- This maps to `schools_config.blue_school` / `schools_config.red_school` in YAML

**Commander Panel** (new section):
- Side selector: blue / red
- Commander dropdown: list of available profiles filtered by era
- Trait preview: show key personality traits (aggression, caution, initiative)
- This maps to `commander_config.side_defaults.blue` / `.red` in YAML

### API Changes

Need endpoints to list available doctrine schools and commander profiles:
- `GET /meta/schools` → list of school names + descriptions
- `GET /meta/commanders` → list of commander profiles with traits
- `GET /meta/doctrines` → list of doctrine templates

### Trade-offs

- **EW/Space/CBRN/Escalation**: Full config editors for these are complex (jammer frequency ranges, orbital parameters, agent types). Defer to future work — the boolean toggles are sufficient for now.
- **Doctrine descriptions**: Need brief, accurate descriptions of each school's behavior for the dropdown. Source from existing `data/schools/*.yaml` metadata.
- **Commander filtering by era**: Not all commanders are available in all eras. The API should filter by era.

### Recommendation

Implement doctrine and commander pickers first — highest user value, cleanest API surface. EW/Space/CBRN config editors are substantial scope and should be deferred to a future block.

---

## Theme 6: Analysis & Event Depth

**Problem**: The Analysis page offers A/B comparison (run two configs, compare outcomes), parameter sweep (vary one parameter, plot outcomes), and tempo FFT (engagement frequency analysis). These are powerful but generic. Missing: doctrine-specific analysis, per-run diagnostics, and interactive event exploration.

### Doctrine Comparison Analysis

**Concept**: Run the same scenario with each of the 9 doctrinal schools and compare outcomes. Natural A/B but across N configurations.

- Input: scenario, sides to vary (blue/red/both), iterations per school
- Output: matrix of school × outcome (win rate, casualties, duration, engagement rate)
- Visualization: heatmap or grouped bar chart

This is the engine's most distinctive analytical capability — no other wargame simulator offers systematic doctrine comparison with 9 named schools.

### Engine Impact Matrix

**Concept**: Toggle individual `enable_*` flags and measure outcome delta. "What does EW actually do in this scenario?"

- Input: scenario, list of flags to test, iterations
- Output: per-flag outcome change (win rate Δ, casualty Δ, duration Δ)
- Visualization: bar chart of impact per flag

### Per-Run Engagement Details

**Concept**: Click on an engagement event in the events tab → see full detail: attacker, target, weapon, range, Pk, modifiers applied (weather, concealment, posture, terrain), outcome, damage.

Currently the events tab shows a flat list with event_type, source, and raw data dict. Adding a detail panel that unpacks the event data into a readable card would transform the debugging experience.

### Event Filtering

The events tab lists all events chronologically. With 10K+ events per run, finding specific events requires scrolling. Add:
- Filter by event_type (dropdown/multi-select)
- Filter by side (blue/red)
- Filter by tick range (slider)
- Search by unit ID or type

### Trade-offs

- **Doctrine comparison requires N×I simulation runs** (9 schools × 10 iterations = 90 runs). Even a 30-second scenario takes 45 minutes. Need to handle as async batch job with progress reporting.
- **Engine impact matrix**: Similar computational cost (32 flags × 10 iterations = 320 runs). May need to limit to a subset of commonly-toggled flags.
- **Event filtering**: The events are already loaded client-side (virtualized list). Filtering can be pure frontend — no API change needed.

### Recommendation

Implement event filtering and engagement detail panel first (pure frontend, immediate value). Doctrine comparison as a new analysis type using the existing batch infrastructure. Engine impact matrix as stretch goal (high compute cost).

---

## Theme 7: Data Catalog Expansion

**Problem**: The unit catalog (Phase 33) lists units with basic metadata (type, domain, category, speed, crew) and a detail modal showing the raw YAML definition. There is no browsing capability for:

- **Weapons**: 56 YAML files across 10 categories (artillery, bombs, DEW, guns, missiles, etc.)
- **Sensors**: 18 YAML files (radar, sonar, ESM, thermal, MAWS)
- **Doctrine templates**: 27 YAML files (NATO, US, Russian, Chinese, IDF, unconventional, airborne, naval)
- **Commander profiles**: 30+ YAML files with personality traits
- **Ammunition**: 125+ YAML files

Users exploring the simulation want to understand the data driving it: "What weapons does a Leopard 2A6 carry? What's the range of the APG-68 radar? How does the Maneuverist doctrine differ from Attrition?"

**Solution**: Extend the data browsing pages with weapon, sensor, and doctrine catalogs. Reuse the existing unit catalog pattern (list + filter + detail modal).

### Proposed Pages

| Page | Data Source | List Fields | Detail Fields |
|------|------------|-------------|---------------|
| Weapon Catalog | `data/**/weapons/*.yaml` | Name, domain, category, max range, ROF | Full spec, compatible ammo, compatible units |
| Sensor Catalog | `data/**/sensors/*.yaml` | Name, type, max range, scan interval | Detection curves, frequency range, modes |
| Doctrine Catalog | `data/doctrine/*.yaml` | Name, philosophy, era | Full weight table, posture preferences, COA modifiers |
| Commander Catalog | `data/commander_profiles/*.yaml` | Name, personality summary | Aggression, caution, initiative, doctrine affiliation |

### API Endpoints

- `GET /weapons` → list of weapon summaries
- `GET /weapons/{id}` → full weapon detail
- `GET /sensors` → list of sensor summaries
- `GET /sensors/{id}` → full sensor detail
- `GET /doctrines` → list of doctrine summaries
- `GET /commanders` → list of commander summaries

### Trade-offs

- **API scope**: 4 new router files with 8 endpoints. Follows the existing `units.py` pattern.
- **Data loading**: Weapon/sensor YAML is already loaded by `ScenarioLoader` and entity factories. The API needs standalone loaders for browsing outside of a simulation context.
- **Cross-referencing**: "Which units carry this weapon?" requires reverse lookups across unit YAML. Could be computed on startup and cached.

### Recommendation

Start with weapon and doctrine catalogs — highest user interest. Sensor and commander catalogs follow naturally using the same pattern. Ammunition is low-priority (derivative of weapon data, rarely browsed independently).

---

## Implementation Strategy

### Block Scope

6 phases, backend-first then frontend:

1. **API Analytics & Frame Enrichment** — New analytics endpoints + enriched MapUnitFrame + metadata endpoints
2. **Results Dashboard Depth** — Frontend charts consuming analytics data
3. **Tactical Map Enrichment** — Map overlays using enriched frame data
4. **Calibration & Config Depth** — Per-side overrides, doctrine/commander pickers, expanded morale
5. **Analysis & Event Interaction** — Event filtering, engagement detail, doctrine comparison
6. **Data Catalog & Validation** — Weapon/doctrine browsing + block regression

### What's NOT in Block 10

- **New engine subsystems** — Zero simulation logic changes
- **EW/Space/CBRN config editors** — Too complex for UI-only block; boolean toggles sufficient
- **3D visualization** — Future block (WebGL terrain, unit models)
- **Real-time multiplayer** — Architecture doesn't support it; not in scope
- **Mobile responsiveness** — Desktop-first; responsive layouts are a stretch goal
- **Scenario creation from scratch** — Clone-and-tweak is sufficient; full creation is future work

### Exit Criteria

1. All 40 scenarios produce correct winners (no engine regressions)
2. Per-run analytics endpoints return structured casualty/suppression/morale/engagement data
3. Tactical map displays morale, posture, and health overlays
4. CalibrationSliders expose per-side overrides and expanded morale parameters
5. Doctrine and commander selectors functional in scenario editor
6. Event filtering by type/side/tick range operational
7. Weapon and doctrine catalog pages functional
8. All existing tests pass + new frontend/API tests
9. Cross-browser validation (Chrome, Firefox, Edge)

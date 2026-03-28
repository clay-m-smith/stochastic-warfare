# Phase 94: Tactical Map Enrichment

**Block 10** — UI Depth & Engine Exposure
**Status**: Complete

## What Was Built

Phase 94 transforms the tactical map from a position tracker into a battlefield status display by visualizing the 7 enriched frame fields added in Phase 92 (morale, posture, health, fuel_pct, ammo_pct, suppression, engaged).

### 94a: Morale & Health Overlays
- **Morale color coding**: Unit fill color overrides based on morale state — STEADY (side color), SHAKEN (yellow), BROKEN (orange), ROUTED (red), SURRENDERED (gray). Toggleable via "Morale" checkbox (default OFF).
- **Health bars**: Thin horizontal bar below each unit marker, width proportional to health (0.0–1.0). Color: green (>50%), yellow (20–50%), red (<20%). Toggleable via "Health" checkbox (default ON).

### 94b: Posture & Suppression Indicators
- **Posture indicators**: Single-letter abbreviation near unit marker (D=Defensive, F=Fortified, A=Assault, S=On Station, B=Battle Stations, H=Halted, etc.). White outline for contrast on any terrain. Toggleable via "Posture" checkbox (default OFF).
- **Suppression opacity**: Unit opacity scaled by suppression level — None (100%), Light (85%), Moderate (65%), Heavy (45%), Pinned (30%). Multiplicative with status opacity. Toggleable via "Suppression" checkbox (default ON).

### 94c: Logistics & Engagement Indicators
- **Fuel/ammo bars**: Two thin vertical bars right of unit marker — blue (fuel), orange (ammo). Height proportional to percentage. Turns red when <20%. Toggleable via "Logistics" checkbox (default OFF).
- **Engagement flash**: Gold ring around units with `engaged=true`. Always-on (no toggle). Fades naturally as engaged flag toggles off in subsequent ticks.

### 94d: Enhanced Unit Detail Sidebar
- All 7 enriched fields displayed when clicking a unit: Morale (color-coded name), Posture (raw string), Health/Fuel/Ammo (percentage), Suppression (descriptive name: None/Light/Moderate/Heavy/Pinned), Engaged (Yes/No).
- Conditionally rendered — old runs without enriched data show no extra rows.

### 94e: Map Legend Enhancement
- 5 conditional legend sections that appear only when the corresponding overlay is enabled:
  - Morale: 5 color swatches (Steady through Surrendered)
  - Health: gradient bar (red→yellow→green)
  - Posture: abbreviation legend (6 entries)
  - Suppression: 5 opacity-level swatches
  - Logistics: fuel (blue), ammo (orange), low (red) indicators

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `frontend/src/types/map.ts` | Modified | +7 optional fields on MapUnitFrame |
| `frontend/src/lib/unitRendering.ts` | Modified | OverlayOptions interface, MORALE_COLORS/POSTURE_ABBREV constants, 4 draw functions (drawHealthBar, drawPostureIndicator, drawLogisticsBars, drawEngagementFlash), modified drawUnit signature |
| `frontend/src/components/map/TacticalMap.tsx` | Modified | 5 toggle states, overlays useMemo, drawUnit call, props wiring to MapControls + MapLegend |
| `frontend/src/components/map/MapControls.tsx` | Modified | 10 new props (5 show + 5 toggle), 5 Toggle components with separator |
| `frontend/src/components/map/UnitDetailSidebar.tsx` | Modified | MORALE_NAMES, MORALE_TEXT_COLORS, SUPPRESSION_NAMES lookup maps, enriched field rows with ColorRow helper |
| `frontend/src/components/map/MapLegend.tsx` | Modified | OverlayOptions prop, 5 conditional legend sections |
| `frontend/src/__tests__/lib/unitRendering.overlay.test.ts` | New | 16 tests |
| `frontend/src/__tests__/components/map/MapControls.overlay.test.tsx` | New | 5 tests |
| `frontend/src/__tests__/components/map/UnitDetailSidebar.enriched.test.tsx` | New | 7 tests |
| `frontend/src/__tests__/components/map/MapLegend.overlay.test.tsx` | New | 7 tests |
| `frontend/src/__tests__/components/map/MapControls.test.tsx` | Modified | +10 overlay props to defaultProps |

## Design Decisions

1. **Optional overlay param on drawUnit**: 7th arg is optional — all existing callers unaffected. Backward compatible by design.
2. **Toggle defaults**: Health (ON) and Suppression (ON) are the most informative overlays with low visual clutter. Morale/Posture/Logistics default OFF to keep the map clean until user opts in.
3. **Engagement flash always-on**: No toggle needed — the `engaged` flag is transient (only true during engagement ticks), so the flash appears briefly and naturally fades.
4. **White stroke outline on posture text**: Ensures readability on any terrain background (light or dark) since canvas rendering doesn't have CSS dark mode.
5. **Logistics bars right of marker**: Avoids visual collision with health bar (below) and posture indicator (upper-right).

## Test Summary

- **42 new frontend tests** across 4 test files (including 7 edge case tests added during postmortem)
- **1 existing test file updated** (MapControls.test.tsx — new overlay props)
- **372 total frontend tests** (was 330)
- Zero Python test changes (no backend modifications)

## Known Limitations

- Canvas drawing doesn't automatically adapt to dark mode — posture text uses white outline which works on both light and dark terrain but isn't theme-aware.
- Frame interpolation doesn't lerp health/fuel/ammo values — they snap to source frame values. Visual difference is negligible at typical frame intervals.
- Overlay drawing adds ~2,700 canvas calls at 300 units with all overlays enabled — well under the 16ms budget.

## Postmortem

### 1. Delivered vs Planned
All 5 sub-tasks (94a–94e) delivered as planned. Minor deviations:
- **Morale toggle default**: Changed from ON (plan) to OFF (delivery) — keeps map cleaner, justified design improvement.
- **Posture abbreviations**: Plan used "E" for entrenched; delivery uses "F" for fortified/DUG_IN. Broader coverage (14 posture types vs 5 in plan).
- No items dropped or deferred.
- Unplanned additions: MORALE_NAMES/SUPPRESSION_NAMES lookup maps, ColorRow helper — improves code quality, no scope creep.

**Verdict**: Scope well-calibrated.

### 2. Integration Audit
- **OverlayOptions**: Exported from unitRendering.ts, imported by TacticalMap.tsx and MapLegend.tsx. Fully wired.
- **Drawing functions**: All 4 (drawHealthBar, drawPostureIndicator, drawLogisticsBars, drawEngagementFlash) called from drawUnit with proper null-coalescing guards.
- **MapUnitFrame enriched fields**: All 7 consumed by unitRendering.ts (canvas) and UnitDetailSidebar.tsx (HTML).
- **Toggle states**: All 5 defined in TacticalMap, wired to MapControls (10 props), passed to drawUnit via memoized overlays object, and to MapLegend.
- **Dead exports**: None. MORALE_COLORS and POSTURE_ABBREV exported for tests and legend consistency.

**Verdict**: Fully integrated.

### 3. Test Quality
- **42 tests** across 4 files covering rendering functions, component rendering, and backward compat.
- **Edge cases added during postmortem**: health boundary values (0.0, 0.2, 0.5), morale=0 (STEADY — no override), destroyed unit overlay gate, suppression extremes (0=full opacity, 4=pinned).
- **Backward compat**: Explicitly tested — drawUnit without overlays arg, sidebar with no enriched fields.
- **Gap**: No integration tests between TacticalMap+MapControls+rendering (component-level isolation tests only). Acceptable for Phase 94 scope.

### 4. API Surface
- All exported functions have TypeScript type hints (OverlayOptions interface, function signatures).
- No bare `print()` or `console.log()` in production code.
- Drawing functions are intentionally public (exported for testing and potential reuse).

### 5. Deficits
No new deficits. Known limitations (dark mode canvas, frame interpolation snapping) are documented and accepted.

### 6. Documentation Freshness
- CLAUDE.md: Phase 94 entry added with test count 42.
- README.md: Badge updated to phase-94, test count to 10,694.
- docs/index.md: Badge and test count updated.
- devlog/index.md: Phase 94 row added.
- development-phases-block10.md: Status set to Complete.
- mkdocs.yml: Phase 94 devlog entry added.
- MEMORY.md: Current status updated.

### 7. Performance
- Python tests: 186.95s (no change — zero backend modifications).
- Frontend tests: 15.39s (was ~15s — negligible change).

### 8. Summary
- **Scope**: On target
- **Quality**: High
- **Integration**: Fully wired
- **Deficits**: 0 new items
- **Action items**: None — ready to commit

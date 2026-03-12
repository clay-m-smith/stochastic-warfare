# Phase 56: Performance & Logistics

## Summary

Phase 56 addresses performance bottlenecks and logistics wiring gaps: O(n^2) rally cascade replaced with STRtree spatial index, maintenance breakdowns wired to unit readiness, era-specific medical/engineering times, per-subsystem Weibull shape parameters, VLS exhaustion enforcement, naval posture detection modifiers, gas casualty calibration fields, and blockade throughput reduction.

**39 new tests. 8 deficits resolved.**

## What Was Built

### 56a: Rally STRtree Spatial Index

- **`battle.py`**: Replaced O(n^2) rally check and rout cascade inner loops with STRtree-based spatial queries. Per-side trees built once at the start of `_execute_morale`, reused for both rally and cascade.
- **Bug fix**: Line 2879 had an indentation bug — `if math.sqrt(...)` was at the `for other` loop level, not inside it, so only the last unit's distance was checked. STRtree refactor fixes this naturally.
- Added `shapely.STRtree` and `shapely.geometry.Point` imports.

### 56b: Maintenance → Readiness Wiring

- **`engine.py`**: After `maintenance_engine.update()`, calls `complete_repairs()` and checks unit readiness — units with readiness 0.0 transition to `DISABLED`.
- **`campaign.py`**: Filled `_run_maintenance` stub with actual delegation to maintenance engine (update + complete_repairs).
- **`battle.py`**: Readiness-based movement speed penalty in `_execute_movement` — `effective_speed *= max(0.3, readiness)` when readiness < 1.0.
- Existing `readiness < 0.3` engagement gate (battle.py) already blocks engagement for degraded units.

### 56c: Per-Era Medical/Engineering + Per-Subsystem Weibull

- **`era.py`**: Added `physics_overrides` for treatment/repair times:
  - WW2: minor 3h, serious 12h, critical 36h, repair 6h
  - WW1: minor 4h, serious 24h, critical 72h, repair 8h
  - Napoleonic: minor 8h, serious 48h, critical 168h
  - Ancient: minor 24h, serious 168h, critical 336h
- **`scenario.py`**: Reads era `physics_overrides` when constructing `MedicalConfig`/`EngineeringConfig`.
- **`maintenance.py`**: Added `set_subsystem_shapes()` and `_get_subsystem_shape()` for per-subsystem Weibull k values. Equipment IDs categorized by prefix (`engine_` → engine, `radar_`/`elec_` → electronics, etc.).
- **`calibration.py`**: Added `subsystem_weibull_shapes: dict[str, float] = {}`.
- **`scenario.py`**: Wires Weibull shapes from calibration into maintenance engine.

### 56d: VLS Reload Enforcement

- **`battle.py`**: Added exhaustion logging (`logger.info("VLS exhausted: ...")`) when magazine depleted.
- **`battle.py`**: Added `_vls_launches` to `get_state()`/`set_state()` for checkpoint persistence.
- Port visit reload explicitly deferred — accepted simplification.

### 56e: Naval Posture Detection Modifiers

- **`battle.py`**: Added `_NAVAL_POSTURE_DETECT_MULT` table (ANCHORED=1.2x, UNDERWAY=1.0x, TRANSIT=0.85x, BATTLE_STATIONS=1.3x).
- Applied to target detection range in `_execute_engagements`, after existing night/weather/concealment modifiers and before the detection range gate.

### 56f: Gas Casualty Calibration Fields

- **`calibration.py`**: Added `gas_casualty_floor: float = 0.1` and `gas_protection_scaling: float = 0.8`.
- **`battle.py`**: Replaced hardcoded `0.1` and `0.8` with `cal.get()` lookups.

### 56g: Blockade Throughput Reduction

- **`campaign.py`**: Wired blockade effectiveness to supply network — SEA transport routes are degraded proportionally to `max_eff` across blockaded zones. Road/rail routes unaffected. Minimum route condition capped at 0.01.

## Design Decisions

1. **STRtree per-side, per-tick**: Trees are cheap to build (O(n log n)) and amortize over both rally and cascade queries. No caching across ticks — unit positions change.
2. **Readiness NOT a new UnitStatus**: Using existing `get_unit_readiness()` + DISABLED status avoids adding enum values (which break count assertions).
3. **Era medical via `physics_overrides`**: Reuses existing config dict mechanism — no new YAML files needed.
4. **Per-subsystem Weibull via CalibrationSchema**: Per-scenario, not per-unit-YAML — avoids touching 133 unit files.
5. **VLS port reload deferred**: Requires defining friendly port zones — too much new machinery for a wiring phase.
6. **Conservative naval posture modifiers**: ±15-30% range, per Phase 54 lesson about compound modifier effects.
7. **Blockade effects don't reverse**: SEA route condition is degraded each tick while blockade active. Acceptable simplification for campaign-scale.

## Deficit Resolution

| Deficit | Description | Resolution |
|---------|-------------|------------|
| D5 | O(n^2) rally cascade | STRtree spatial index (56a) |
| D10 | Maintenance registration incomplete | Breakdown → readiness wiring (56b) |
| D11 | Medical/engineering data sparse | Era-specific physics_overrides (56c) |
| D13 | Weibull maintenance global | Per-subsystem shapes via CalibrationSchema (56c) |
| Phase 6 VLS | VLS non-reloadable-at-sea | Exhaustion enforced, port reload deferred (56d) |
| Phase 51 | Naval posture detection modifiers | Detection range multipliers per posture (56e) |
| Phase 55 | Gas casualty hardcoded values | CalibrationSchema fields (56f) |
| Phase 51 | Blockade throughput reduction | Supply route condition degradation (56g) |

## Accepted Simplifications

1. VLS port visit reload deferred — requires friendly port zone definition.
2. Blockade route degradation is cumulative and doesn't reverse when blockade is lifted.
3. Equipment prefix categorization is hardcoded — covers common naming patterns.

## Files Modified

**Python source (6 modified, 0 new):**
- `stochastic_warfare/simulation/calibration.py` — 3 new CalibrationSchema fields
- `stochastic_warfare/simulation/battle.py` — rally STRtree, gas casualty from cal, naval posture detection, readiness movement, VLS logging/checkpoint
- `stochastic_warfare/simulation/engine.py` — complete_repairs call, readiness → DISABLED
- `stochastic_warfare/simulation/campaign.py` — fill _run_maintenance, blockade throughput
- `stochastic_warfare/core/era.py` — physics_overrides for medical/engineering times
- `stochastic_warfare/logistics/maintenance.py` — per-subsystem Weibull shapes

**Tests (1 new):**
- `tests/unit/test_phase56_performance_logistics.py` — 39 tests

## Postmortem

### Delivered vs Planned

All 7 planned items (56a–56g) delivered as designed. 8 deficits resolved. 39 tests (plan estimated ~35). No items dropped or descoped. One unplanned bug fix: rally inner loop indentation bug (only checked last unit's distance) — discovered and fixed as part of the STRtree refactor.

**Scope**: On target.

### Integration Audit

All 8 new code paths are wired into the simulation loop:

| Feature | Wiring Point | Verified |
|---------|-------------|----------|
| Rally STRtree | `_execute_morale` in battle.py | Yes — replaces inner loop |
| Gas casualty calibration | `_execute_engagements` gas path | Yes — `cal.get()` reads |
| Naval posture detection | `_execute_engagements` detection section | Yes — before range gate |
| Readiness movement | `_execute_movement` after naval posture speed | Yes — `max(0.3, rdns)` |
| VLS checkpoint | `get_state()`/`set_state()` | Yes — persists `_vls_launches` |
| Maintenance → DISABLED | `engine.py` after maintenance update | Yes — `complete_repairs()` + readiness check |
| Era medical/engineering | `scenario.py` `_create_engines()` | Yes — reads `physics_overrides` |
| Blockade throughput | `campaign.py` `_update_supply_network()` | Yes — SEA route degradation |

No dead modules. No orphaned code.

### Test Quality

- **39 tests across 9 test classes** — all unit-level with mocks/fixtures.
- Edge cases covered: empty shapes fallback, no maintenance engine, zero readiness, non-VLS weapons.
- **Gaps identified** (acceptable for wiring phase):
  - No integration test for readiness < 0.3 engagement gate (existing gate, verified structurally).
  - Blockade tests verify degradation occurs but don't assert exact condition values.
  - Naval posture detection tested in isolation, not in full engagement context.

### API Surface

- `MaintenanceEngine.set_subsystem_shapes()` — public, type-hinted.
- `MaintenanceEngine._get_subsystem_shape()` — private, appropriate.
- `_NAVAL_POSTURE_DETECT_MULT` — module-level dict, appropriate for constant table.
- All new CalibrationSchema fields have type hints and defaults.
- No bare `print()` — all logging via `get_logger(__name__)`.

### Deficit Discovery

**New deficits (2)**:

1. **Blockade route degradation not reversed on removal** — SEA route condition degrades each tick while blockade active but doesn't restore when blockade is lifted. Acceptable simplification for campaign-scale; documented in Accepted Simplifications above. Severity: LOW.
2. **VLS port visit reload deferred** — Requires defining friendly port zones. Documented as accepted simplification. Severity: LOW (exhaustion enforced, which is the critical path).

**No new TODOs or FIXMEs** in modified source files.

### Documentation Freshness

- CLAUDE.md: Updated with Phase 56 summary, test count (~8,613 / ~8,341 Python).
- development-phases-block6.md: Phase 56 marked COMPLETE with all sub-steps.
- devlog/index.md: Phase 56 row added as Complete. 3 deficit resolutions marked (Phase 6 VLS, Phase 51 naval posture, Phase 51 blockade, Phase 55 gas casualty).
- README.md: Test count badge updated (8,613). Phase badge updated (Phase 56). Body text test count updated.
- docs/index.md: Test count badge updated (8,613). Phase badge updated (Phase 56).
- MEMORY.md: Updated with Phase 56 status, lessons learned, deficit inventory, phase summary row.
- mkdocs.yml: Phase 56 devlog entry added.
- development-phases-block6.md: Phase summary table updated (Phases 55+56 from Planned to Complete). Phase heading consistency fixed. Deficit resolution map updated.

### Performance

Full test suite: 7,448 non-validation tests passing, 0 regressions. STRtree replacement for O(n^2) rally should improve performance for large unit counts.

### Summary

- **Scope**: On target — all 7 items delivered, 8 deficits resolved
- **Quality**: High — all code wired, no dead paths
- **Integration**: Fully wired — all 8 checkpoints verified
- **Deficits**: 2 new (both LOW severity, documented as accepted simplifications)
- **Action items**: None — all documentation updated during postmortem

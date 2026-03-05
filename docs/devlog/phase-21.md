# Phase 21: WW1 Era — Devlog

**Status**: Complete
**Tests**: 182 (87 era config/data + 67 engine extensions + 28 validation)
**Total**: 5,426 (5,244 prior + 182 new)

## Summary

WW1 era config + data package (~45 YAML files) + 3 engine extensions (trench systems, creeping barrage, gas warfare) + 2 validation scenarios (Somme Day 1, Cambrai). Follows Phase 20 era framework pattern exactly.

## What Was Built

### 21a: Era Config + Data (87 tests)

**Source changes:**
- `core/era.py` — Added `WW1_ERA_CONFIG` constant: disables EW/space/GPS/thermal sights/data links/PGM. CBRN stays **enabled** (chemical warfare). VISUAL-only sensors. `c2_delay_multiplier=5.0`, `cbrn_nuclear_enabled=False` in physics_overrides.
- `simulation/scenario.py` — 3 new `SimulationContext` fields (`trench_engine`, `barrage_engine`, `gas_warfare_engine`), all default `None`. `trench_warfare` added to `TerrainConfig` allowed types. State persistence includes new engines.
- `validation/historical_data.py` — `trench_warfare` added to `TerrainSpec` allowed types.
- `validation/scenario_runner.py` — `trench_warfare` dispatches to `build_flat_desert` (trenches are a separate overlay).

**YAML data (40 files):**
- 6 units: british_infantry_platoon, german_sturmtruppen, french_poilu_squad, mark_iv_tank, a7v, cavalry_troop
- 8 weapons: lee_enfield, gewehr_98, maxim_mg08, lewis_gun, 18pdr_field_gun, 77mm_fk96, 21cm_morser, mills_bomb
- 10 ammo: .303 ball/AP, 7.92mm S Patrone, 18-pdr shrapnel/HE, 77mm HE/shrapnel/gas, 21cm HE, Mills bomb frag
- 5 sensors: binoculars, sound_ranging, flash_spotting, observation_balloon, aircraft_recon (all VISUAL)
- 6 signatures: one per unit, zeroed thermal/radar/EM
- 3 doctrines: british_trench_warfare (defensive), german_sturmtaktik (offensive/infiltration), french_attaque_outrance (offensive/high-risk)
- 3 commanders: haig_attritional, ludendorff_storm, foch_unified
- 2 comms: field_telephone_ww1 (WIRE, 2s latency), runner_messenger_ww1 (MESSENGER, 600s latency)

### 21b: Engine Extensions (67 tests)

**`terrain/trenches.py`** (~260 lines):
- `TrenchType(IntEnum)`: FIRE_TRENCH, SUPPORT_TRENCH, COMMUNICATION_TRENCH, SAP
- `TrenchConfig(BaseModel)`: cover values per type (0.85/0.70/0.50/0.60), movement factors (along=0.5, crossing=0.3, NML=0.2)
- `TrenchSegment(BaseModel)`: trench_id, type, side, points, width, condition, wire, dugout
- `TrenchSystemEngine`: STRtree spatial indexing. `query_trench()`, `cover_value_at()`, `movement_factor_at()` (with heading-based along/crossing interpolation), `is_no_mans_land()`, `apply_bombardment()`. State persistence.

**`combat/barrage.py`** (~270 lines):
- `BarrageType(IntEnum)`: STANDING, CREEPING, BOX, COUNTER_BATTERY
- `BarrageConfig(BaseModel)`: suppression/casualty rates per round/hectare, creeping advance (0.833 m/s = 50 m/min), drift sigma, friendly fire zone, dugout protection
- `BarrageEngine`: `create_barrage()`, `update()` (advance + drift + trench degradation), `compute_effects()`, `check_friendly_fire()`, `is_safe_to_advance()`. State persistence.

**`combat/gas_warfare.py`** (~200 lines):
- `GasDeliveryMethod(IntEnum)`: CYLINDER_RELEASE, ARTILLERY_SHELL, PROJECTOR
- `GasMaskType(IntEnum)`: NONE→MOPP 0, IMPROVISED_CLOTH→1, PH_HELMET→2, SBR→3
- `GasWarfareEngine`: wraps CBRN pipeline. `check_wind_favorable()`, `execute_cylinder_release()` (multiple puffs along front), `execute_gas_bombardment()` (randomized shell impacts), `execute_projector_salvo()`, mask→MOPP mapping. State persistence.

**CBRN data (3 files):**
- `data/cbrn/agents/phosgene.yaml`: CG choking agent, LCt50=3200
- `data/cbrn/delivery/cylinder_release.yaml`, `livens_projector.yaml`

### 21c: Validation Scenarios (28 tests)

- **Somme Day 1** (July 1, 1916): 10km×3km, 5 British platoons vs 5 German positions, trench_warfare terrain. Documented ~7:1 attacker:defender casualty ratio.
- **Cambrai** (November 20, 1917): 8km×5km, 3 infantry + 4 Mark IV tanks vs 3 German positions. First massed tank attack. Documented 8km advance, ~30% tank mechanical losses.

## Design Decisions

1. **CBRN enabled, nuclear disabled structurally**: No nuclear weapons YAML + `cbrn_nuclear_enabled: False` in physics_overrides. No code changes needed — existing CBRN pipeline works for chemical warfare.

2. **Trenches as spatial overlay**: Shapely LineString + STRtree, not heightmap modification. Trench depth is below cell resolution. Cover and movement are query functions, not grid modifications.

3. **Barrage as aggregate model**: Fire density (rounds/hectare) determines probabilities, not individual shell trajectories. A WW1 barrage involves thousands of shells — aggregate is both more realistic and more efficient.

4. **Gas warfare wraps CBRN**: Thin adapter. All dispersal, contamination, and casualty effects delegated to existing pipeline. Only delivery mechanics and mask→MOPP mapping are new.

5. **C2 delays via existing infrastructure**: `CommType.WIRE` and `MESSENGER` already exist. WW1 comms YAML with long latencies + `c2_delay_multiplier=5.0` physics override.

## Issues & Fixes

- **Phase 20 test mutation**: `test_phase_20a_era_framework.py::test_register_custom_era` registered a custom WW1 config with CBRN disabled, which persisted in the module-level `_ERA_REGISTRY` dict and polluted subsequent tests in the full suite. Fixed by using a non-conflicting era name (`ww1_custom_test`).

- **Signature model access**: Tests used dict subscript (`profile.visual["cross_section_m2"]`) but `VisualSignature` is a pydantic BaseModel (attribute access: `profile.visual.cross_section_m2`).

- **Spatial overlap in trench tests**: Communication trench endpoint overlapped support trench at (250, 200), causing STRtree to return the wrong trench. Fixed by querying at a non-overlapping x-coordinate.

## Known Limitations

- Barrage drift is purely random walk — no systematic correction for forward observer feedback
- Gas warfare engine does not model gas mask don time delay (units gain instant protection)
- Trench wire is a query attribute only, not a movement blocker (no wire-cutting mechanic)
- ScenarioLoader doesn't auto-wire WW1 engines from YAML (extends existing Phase 16-20 gap)
- No sap/mining mechanic (SAP trench type exists but no underground warfare model)
- Barrage fire density is constant over the zone (no gradient from center to edge)

## Lessons Learned

- **Module-level mutable state in tests is fragile**: Any test that mutates a module-level dict (`_ERA_REGISTRY`) must either restore the original or use a non-conflicting key. This was not caught in Phase 20 because WW1 wasn't yet a real registry entry.
- **Era data pattern scales well**: Adding WW1 followed the exact Phase 20 pattern. YAML files, era config, and engine extensions are fully independent of each other until wired in SimulationContext.
- **Aggregate models are the right abstraction for WW1**: Individual-shell ballistics for a 7-day barrage (millions of shells) would be computationally infeasible. Aggregate fire density captures the key dynamics (suppression, casualties, trench degradation) efficiently.

## Postmortem

### 1. Delivered vs Planned

**Plan**: WW1 era config + ~42 YAML data files + 3 engine extensions + 2 validation scenarios. ~160 tests estimated.

**Delivered**: WW1 era config + 43 YAML data files + 3 engine extensions + 2 validation scenarios. 182 tests actual.

| Item | Planned | Delivered | Notes |
|------|---------|-----------|-------|
| YAML data files | ~42 | 43 | On target (+3 CBRN data) |
| Source files (new) | 3 | 3 | trenches, barrage, gas_warfare |
| Source files (modified) | 4 | 5 | +1 Phase 20 test fix |
| Tests | ~160 | 182 | 87 + 67 + 28 |
| Test files | 3 | 3 | 21a, 21b, 21c |

**Unplanned**: Phase 20 test fix (`test_register_custom_era` → `ww1_custom_test` key). Not in plan but required for full suite to pass.

**Verdict**: Scope well-calibrated. Slight overdelivery on tests (+14%). No scope cuts.

### 2. Integration Audit

| Check | Status | Notes |
|-------|--------|-------|
| `terrain/trenches.py` imported by production code? | **NO** | Only by tests |
| `combat/barrage.py` imported by production code? | **NO** | Only by tests |
| `combat/gas_warfare.py` imported by production code? | **NO** | Only by tests |
| Wired into `simulation/engine.py`? | **NO** | Not referenced |
| Wired into `simulation/battle.py`? | **NO** | Not referenced |
| Exported from `terrain/__init__.py`? | **NO** | Not listed |
| Exported from `combat/__init__.py`? | **NO** | Not listed |
| `SimulationContext` fields used by `ScenarioLoader`? | **NO** | Fields exist but never populated |
| `trench_warfare` terrain type in validators? | YES | historical_data.py + scenario.py |
| New CBRN agents loadable? | YES | phosgene.yaml follows existing schema |
| New comms types loadable? | YES | WIRE + MESSENGER CommTypes already existed |

**Verdict**: Engines are **orphaned modules** — standalone, tested in isolation, but not wired into the simulation pipeline. This matches the established pattern from Phases 16–20 (EW, Space, CBRN, Schools, WW2 engines all have the same gap). The `ScenarioLoader` auto-wiring deficit is tracked in `devlog/index.md` and continues to accumulate across phases.

### 3. Test Quality Review

| Aspect | Assessment |
|--------|------------|
| **Unit vs integration** | 87 data tests (YAML loading + config validation), 67 engine tests (spatial queries, barrage physics, gas delivery), 28 validation tests (scenario loading + cross-engine integration). Good mix. |
| **Realistic data** | Tests use historically-grounded parameters (trench cover 0.85, creeping barrage 50 m/min, phosgene LCt50 3200). |
| **Edge cases** | Covered: empty trench system, out-of-trench queries, bombardment at zero/full intensity, no-wind gas release, expired barrages, friendly fire zones. |
| **State roundtrip** | All 3 engines have `get_state()`/`set_state()` roundtrip tests. Deterministic replay tested for barrage and gas bombardment. |
| **Implementation vs behavior** | Tests focus on behavior (cover values, movement factors, suppression probability) not internal structure. |
| **Performance marks** | No `@pytest.mark.slow` needed — all 182 tests complete in <2s. |

**Verdict**: High quality. Good coverage of edge cases and cross-engine interactions. Validation tests exercise realistic multi-engine scenarios (trench + barrage + gas).

### 4. API Surface Check

| File | Type hints | Private naming | Logger | TODOs |
|------|-----------|----------------|--------|-------|
| `terrain/trenches.py` | All public ✓ | `_rebuild_index()` correct ✓ | `get_logger(__name__)` ✓ | None |
| `combat/barrage.py` | All public ✓ | All appropriate ✓ | `get_logger(__name__)` ✓ | None |
| `combat/gas_warfare.py` | All public ✓ | All appropriate ✓ | `get_logger(__name__)` ✓ | None |

**Minor issues found**:
- `barrage.py` and `gas_warfare.py`: fallback `np.random.default_rng(42)` when no RNG passed — hardcoded seed could mask test bugs. Low risk since tests always inject RNG.
- `trenches.py`: direction interpolation angles (30°/60°) hardcoded, not in `TrenchConfig`. Low impact — tuning these would be unusual.
- `gas_warfare.py`: wind direction tolerance (60°) hardcoded, not in `GasWarfareConfig`. Medium impact — controls gas release viability.

**Verdict**: Clean APIs. All public functions typed. Logging correct. No bare print. Minor hardcoded constants noted as deficits.

### 5. Deficit Discovery

**New deficits** (already logged in Known Limitations above + devlog/index.md):
1. Barrage drift — random walk only, no observer correction feedback
2. Gas mask don time — instant protection (no delay)
3. Trench wire — query attribute only, no movement blocking/wire-cutting
4. ScenarioLoader auto-wiring gap — extends Phase 16-20 pattern
5. No sap/mining mechanic — SAP type exists but no underground model
6. Barrage fire density — constant over zone, no center-to-edge gradient

**Additional deficits found during postmortem**:
7. Wind direction tolerance (60°) hardcoded in `gas_warfare.py` — should be configurable
8. Barrage/gas RNG fallback uses hardcoded seed 42 — should warn or raise

**Assignment**: Deficits 1–6 already tracked. Deficits 7–8 are minor and don't warrant a dedicated phase — could be addressed in Phase 22 (Napoleonic) or a future cleanup pass.

### 6. Documentation Freshness

| Document | Accurate? | Notes |
|----------|-----------|-------|
| CLAUDE.md | YES | Phase 21 summary added, test count 5,426 |
| README.md | YES | Badge shows 5,426, phase table has Phase 21 |
| `development-phases-post-mvp.md` | YES | Phase 21 marked COMPLETE |
| `devlog/index.md` | YES | Phase 21 status + 4 deficit entries |
| `specs/project-structure.md` | YES | WW1 era directory tree + new modules listed |
| MEMORY.md | YES | Current status updated |
| Test count matches `pytest --co`? | YES | 5,426 collected, 5,426 passed |

**Verdict**: All docs in sync. Test count verified.

### 7. Performance Sanity

| Metric | Phase 20 | Phase 21 | Delta |
|--------|----------|----------|-------|
| Test count | 5,244 | 5,426 | +182 |
| Suite time | ~95s | ~99s | +4s (+4.2%) |

Within normal bounds (<10% threshold). No heavy tests introduced.

### 8. Summary

- **Scope**: On target — all planned items delivered, slight test overdelivery
- **Quality**: High — clean APIs, good test coverage, historically-grounded parameters
- **Integration**: **Gaps found** — 3 engines are orphaned (not wired into simulation pipeline). This extends the established Phase 16-20 pattern and is tracked as a known deficit.
- **Deficits**: 6 existing + 2 new minor (hardcoded wind tolerance, RNG fallback seed)
- **Action items**: None blocking — all deficits are tracked and consistent with the established pattern of deferring ScenarioLoader auto-wiring

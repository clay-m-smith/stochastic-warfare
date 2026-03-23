# Block 8: Depth Completion & Fidelity Hardening

## Motivation

Blocks 1–7 built 67 phases of subsystems: core infrastructure, combat, C2, EW, space, CBRN, four historical eras, a web UI, doctrinal AI, unconventional warfare, and full environmental wiring. The result is a simulation with ~9,249 tests, 37 validated scenarios, and zero unresolved critical deficits.

Block 7 closed the **build-then-defer-wiring** pattern by connecting 21 `enable_*` flags and exercising 36 environment parameters. However, a comprehensive post-Block-7 audit reveals a new pattern: **structural wiring without behavioral depth**. Many engines are instantiated and called, but their outputs are logged rather than acted upon. Gates are checked but consequences are not enforced. The simulation has broad coverage but shallow execution in several critical areas.

Block 8 is the **depth completion block**. It focuses on nine themes:

1. **Enforcing consequences** — gates that log but don't block, damage that's computed but discarded, orders that are issued but never executed
2. **Closing deferred integration gaps** — 52 formally deferred items from Phases 58–66, prioritized by fidelity impact
3. **Test depth** — 239/270 source files (88.5%) have no dedicated unit tests; combat domain is 100% untested at the unit level
4. **Performance** — O(n^2) hot paths in battle.py dominate runtime for large scenarios (Golan Heights 417s)
5. **API/frontend drift** — CalibrationSliders only expose 4 of 50+ parameters; API schemas missing Space/DEW badges
6. **Historical scenario correctness** — 9/14 historical scenarios resolve via `time_expired` not decisive combat; Somme outcome is historically wrong; calibration is empirical not principled
7. **API robustness** — critical concurrency bugs (batch bypasses semaphore, blocking async handlers), no auth/rate limiting, no graceful shutdown
8. **Frontend accessibility** — 51 a11y issues (21 critical, 18 major, 12 minor); Canvas map inaccessible, missing ARIA labels, no focus traps, color-only indicators
9. **CI/CD & packaging** — only docs deployment workflow exists; no automated test pipeline, no lint, stale debug scripts

**Block 8 exit criteria**:
1. Every gate that checks a condition also enforces it (fuel, ammo, readiness, comms)
2. Every computed result is consumed or the computation is removed
3. All P0/P1 deferred items from Block 7 are resolved
4. Unit test coverage for all combat engines and simulation core
5. All historical scenarios produce correct outcomes via decisive combat, not `time_expired`
6. Golan Heights runtime under 120s (from 417s)
7. API schemas and frontend components current with engine state
8. API concurrency bugs fixed; batch semaphore, graceful shutdown
9. Frontend WCAG 2.1 AA for all critical paths (forms, navigation, modals)
10. CI/CD runs Python + frontend tests on every push

---

## Current State: Post-Block-7 Audit

### Theme 1: Consequences Not Enforced

The simulation computes many things correctly but doesn't act on them. This is the highest-priority category.

#### 1.1 Order Delay Computed but Not Enforced

**Files**: `c2/orders/propagation.py`, `simulation/battle.py`
**Status**: OrderPropagationEngine computes echelon-scaled delay and misinterpretation probability. Both values are logged. Orders execute immediately regardless.

| What's Computed | What Happens | What Should Happen |
|-----------------|--------------|-------------------|
| `delay_s` (echelon-scaled) | Logged | Order queued; executes after delay |
| `was_misinterpreted` (probability roll) | Logged | Order params modified (wrong target, wrong position) |

**Impact**: High — order delay is fundamental to military simulation. Without it, forces react instantaneously regardless of C2 depth.

#### 1.2 Fuel Consumption Commented Out

**Files**: `simulation/engine.py`, `simulation/battle.py`
**Status**: Fuel gate checks `if fuel_remaining > 0` before movement. But fuel is never consumed — the consumption line is commented out pending per-vehicle-type calibration.

**Impact**: High — units have infinite fuel. Logistics network exists but fuel flow is cosmetic.

#### 1.3 ATO Sorties Never Consumed

**Files**: `c2/planning/ato.py`, `simulation/battle.py`
**Status**: ATOPlanningEngine generates sortie entries. `sorties_today` is never incremented. The sortie gate (`if sorties_today >= max_sorties`) never triggers.

**Impact**: Medium — air campaign tempo is unconstrained. ATO exists structurally but provides no limiting function.

#### 1.4 Stratagem Duration Never Expires

**Files**: `c2/ai/stratagems.py`, `simulation/battle.py`
**Status**: `activate_stratagem()` activates stratagems with a decision score boost. Active stratagems accumulate indefinitely — no expiry, no duration tracking.

**Impact**: Low-Medium — stratagems should be temporary tactical advantages, not permanent buffs.

#### 1.5 Planning Result Not Injected

**Files**: `c2/planning/process.py`, `simulation/battle.py`
**Status**: PlanningProcessEngine runs MDMP auto-advancement. But COA development and wargaming results are not consumed — planning auto-advances without influencing AI decisions.

**Impact**: Medium — planning is time-consuming but produces no output that changes behavior.

#### 1.6 Fire Damage Not Applied

**Files**: `simulation/battle.py`, `combat/incendiary.py`
**Status**: `units_in_fire()` is called and logged. Burn damage is not applied to units in fire zones. Fire zones are created from `fire_started` results but units pass through them unharmed.

**Impact**: Medium — fire zones are visual artifacts with no combat effect.

#### 1.7 Guerrilla Retreat Not Executed

**Files**: `combat/unconventional.py`, `simulation/battle.py`
**Status**: Guerrilla disengage is evaluated (threshold check). If disengage triggers, it's logged but the unit doesn't physically move away.

**Impact**: Low — guerrilla tactics are partially cosmetic.

#### 1.8 Burned Zone Concealment Not Consumed

**Files**: `environment/obscurants.py`, `simulation/battle.py`
**Status**: `BurnedZone.concealment_reduction` is computed but never read by detection engine.

**Impact**: Low — burned terrain should reduce concealment (no vegetation).

---

### Theme 2: Deferred Integration Gaps (52 Items from Phases 58–66)

Items grouped by priority tier. Full inventory in Block 7 phase devlogs.

#### P0: Critical Infrastructure (3 items)

| ID | Gap | Source Phase | Impact |
|----|-----|-------------|--------|
| P0-1 | Fuel consumption → movement (commented out) | 58 | Units have infinite fuel |
| P0-2 | Ammo depletion → firing gate | 58 | Units fire at 0 ammo (weapon.fire() consumes but doesn't gate) |
| P0-3 | Checkpoint state registration | 63 | Checkpoint restore produces wrong unit states (only clock+RNG saved) |

#### P1: Should Wire (11 items)

| ID | Gap | Source Phase | Impact |
|----|-----|-------------|--------|
| P1-1 | Order delay enforcement queue | 64 | Orders execute instantly regardless of C2 depth |
| P1-2 | Misinterpretation parameter modification | 64 | `was_misinterpreted` logged but order unchanged |
| P1-3 | ATO entry consumption | 64 | Sortie limits never enforced |
| P1-4 | Stratagem duration and expiry | 64 | Active stratagems never expire |
| P1-5 | Planning result injection | 64 | MDMP runs but output unused |
| P1-6 | CarrierOpsEngine full battle loop wiring | 61 | CAP/sortie/recovery not dispatched |
| P1-7 | Fire damage application | 60 | Units in fire zones take no damage |
| P1-8 | MissileEngine per-tick update | 63 | Missile launch ships but no flight-to-impact |
| P1-9 | MissileDefenseEngine intercept | 63 | Missile-as-contact detection deferred |
| P1-10 | Deception effect on enemy AI | 64 | No false force disposition injected into FOW |
| P1-11 | CommandEngine full hierarchy wiring | 64 | Authority check skipped when command_engine=None |

#### P2: Wire If Time (28 items)

**Environment** (8):
- Ice crossing pathfinding (59), vegetation height LOS blocking (59), bridge capacity enforcement (59), ford crossing routing (59), road snow degradation (59), fire spread cellular automaton (60), sea spray/salt fog obscurant (61), SHF/EHF rain attenuation for comms (61)

**Human Factors** (4):
- Dehydration/water consumption (62), environmental fatigue acceleration (62), MOPP comms → C2 effectiveness (62), turbulence → gun accuracy (62)

**Combat** (5):
- SiegeEngine → campaign loop (66), AmphibiousAssaultEngine beach assault (66), mine sweeping all types (66), guerrilla retreat movement (66), population center spatial lookup (66)

**C2/AI** (4):
- IED auto-emplacement by insurgent AI (66), echelon_level=5 hardcoded (64), mission_type=0 hardcoded (64), economy-of-force unit selection (64)

**Infrastructure** (4):
- Hull natural period per ship class (61), ionospheric storm effects (61), wind shear altitude-dependent (62), surface roughness → CBRN mixing height (62)

**Code Quality** (3):
- ConditionsEngine replacing EMEnvironment (66), P4 dead code removal (66), SimulationContext TODO cleanup (66)

#### P3: Defer (8 items)

- Spin drift, soil CBRN absorption, dynamic cratering, Faraday rotation, tunnel routing, deep channel SOFAR, submarine oar-powered (already implemented Phase 23), visual signals ancient C2 (already implemented Phase 23)

---

### Theme 3: Test Coverage Gaps

#### 3.1 Unit Test Coverage by Module

| Module | Source Files | Files with Tests | Coverage |
|--------|-------------|------------------|----------|
| combat | 33 | 0 | 0% |
| terrain | 16 | 0 | 0% |
| movement | 16 | 0 | 0% |
| logistics | 15 | 0 | 0% |
| detection | 11 | 0 | 0% |
| c2 | 40 | 21 | 52% |
| environment | 9 | 0 | 0% |
| simulation | 9 | 2 | 22% |
| cbrn | 9 | 0 | 0% |
| space | 8 | 0 | 0% |
| ew | 8 | 0 | 0% |
| population | 7 | 0 | 0% |
| morale | 7 | 0 | 0% |
| entities | 18 | 0 | 0% |
| escalation | 5 | 0 | 0% |
| coordinates | 3 | 0 | 0% |
| core | 9 | 8 | 89% |
| **Total** | **270** | **31** | **11%** |

**Note**: The 190+ integration tests exercise these modules indirectly. But no isolated unit tests exist for combat engines, terrain, movement, logistics, detection, environment, or CBRN modules. Bugs in individual functions are only caught when they propagate to scenario-level failures.

#### 3.2 Critical Untested Code Paths

**simulation/battle.py** (4,258 lines, 47 methods):
- `_route_air_engagement()` — 58 lines of critical routing logic
- `_route_naval_engagement()` — domain-specific routing
- `_compute_terrain_modifiers()` — terrain penalty calculation
- `_target_value()` / `_score_target()` — target selection scoring
- `_apply_behavior_rules()` — ROE/posture enforcement
- All environmental modifier chains (weather, night, rain, wind chill, WBGT)
- `_apply_aggregate_casualties()` — aggregate casualty mapping

**simulation/engine.py** (1,301 lines, 30 methods):
- `_fuse_sigint()` — SIGINT fusion logic
- `_attempt_asat_engagements()` — ASAT engagement
- `_forces_within_closing_range()` — resolution switching guard

**combat/ directory** (33 files, ~8,000+ lines):
- Every combat engine class (damage, ammunition, ballistics, missiles, naval, air, melee, siege, etc.)
- Zero dedicated unit tests for any of them

#### 3.3 Scenario Data Issues

| Issue | File | Severity |
|-------|------|----------|
| WW1 weapons in WW2 scenario | `data/scenarios/eastern_front_1943/scenario.yaml` | Medium — gewehr_98, lee_enfield, mills_bomb are WW1 |
| Missing victory_conditions | `data/scenarios/golan_heights/scenario.yaml` | Low — defaults handle it |
| insurgent_squad has no sensors | `data/units/infantry/insurgent_squad.yaml` | Low — likely intentional |

#### 3.4 Unused Test Infrastructure

| Item | Status |
|------|--------|
| `rng_manager` fixture in conftest.py | Never used — tests construct RNGManager inline |
| `sim_clock` fixture in conftest.py | Used once — tests prefer `make_clock()` helper |
| `make_stream()` helper in conftest.py | Used once |

---

## YAML Field Audit: Dead or Unconsumed

| Field | Defined In | Consumed? | Action |
|-------|-----------|-----------|--------|
| `weight_kg` | AmmoDefinition, Equipment | Partial — used in explosive yield but not weight-of-fire or logistics weight | Audit consumers |
| `propulsion` | AmmoDefinition | Wired Phase 66 — drag reduction for rocket/turbojet/ramjet | Resolved |
| `data_link_range` | AerialUnit loader | Wired Phase 66 — UAV gate | Resolved |
| `unit_cost_factor` | AmmoDefinition | No — no logistics cost modeling | Remove or wire |

---

## CalibrationSchema Audit: Fields Never Set by Any Scenario

These 16 fields exist in CalibrationSchema with defaults but are never overridden in any scenario YAML. They are consumed by code (the defaults work), but no scenario exercises non-default values.

| Field | Default | Consumer |
|-------|---------|----------|
| `disable_threshold` | 0.3 | battle.py — unit disable check |
| `dew_disable_threshold` | 0.5 | battle.py — DEW disable check |
| `dig_in_ticks` | 30 | battle.py — dig-in posture timing |
| `wave_interval_s` | 300.0 | battle.py — wave attack timing |
| `target_selection_mode` | "threat_scored" | battle.py — target scoring |
| `night_thermal_floor` | 0.8 | battle.py — night vision floor |
| `wind_accuracy_penalty_scale` | 0.03 | battle.py — crosswind penalty |
| `rain_attenuation_factor` | 1.0 | battle.py — rain radar loss |
| `c2_min_effectiveness` | 0.3 | battle.py — C2 floor |
| `engagement_concealment_threshold` | 0.5 | battle.py — concealment gate |
| `target_value_weights` | None | battle.py — target scoring weights |
| `gas_casualty_floor` | 0.1 | battle.py — gas casualty floor |
| `gas_protection_scaling` | 0.8 | battle.py — MOPP scaling |
| `subsystem_weibull_shapes` | {} | logistics — Weibull maintenance |
| `victory_weights` | None | victory — composite scoring |
| `enable_fog_of_war` | False | engine/battle — FOW toggle |

**Recommendation**: Create scenarios that exercise non-default values, OR remove the field if no scenario would ever need it.

---

## Architecture Observations

### The "Log But Don't Act" Pattern

Block 7 successfully wired engines to be instantiated and called. But many follow a pattern:

```python
# Compute a result
result = engine.evaluate(unit, conditions)
logger.debug("Result: %s", result)
# ... but never use result to modify behavior
```

This pattern exists in:
- Order propagation (delay computed, logged, ignored)
- Stratagem activation (activated, logged, never expires)
- Fire zones (units detected in zones, logged, no damage)
- Guerrilla disengage (threshold checked, logged, no movement)
- ASAT engagements (structural placeholder, no weapon data)
- ATO sortie tracking (entries generated, never consumed)

**Root cause**: Block 7's approach was opt-in flags + structural wiring to prevent regressions. The "log but don't act" pattern was the correct intermediate step. Block 8 should convert these from logging to action.

### The Calibration Gap

Many behavioral changes were deferred in Block 7 because "calibration doesn't account for the new modifier." This is a valid concern — adding a fuel consumption rate without knowing per-vehicle-type values would produce incorrect outcomes. But the deferral creates a chicken-and-egg problem: you can't calibrate what you can't measure.

**Recommendation**: Implement with conservative defaults and `enable_*` flags. Calibrate in a dedicated recalibration phase at the end of Block 8.

### Battle.py Complexity

`battle.py` is 4,258 lines with 47 methods. It is the single most critical file in the simulation — every engagement, every modifier, every routing decision passes through it. Yet it has only 42 unit tests (most testing setup, not behavior).

**Recommendation**: Extract well-defined subsystems into dedicated modules:
- Target selection/scoring → `combat/targeting.py`
- Environmental modifier chains → `combat/environment_modifiers.py`
- Engagement routing → `combat/routing.py`
- Aggregate casualty/suppression → `combat/aggregation.py`

This would make each component independently testable.

### enable_* Flag Proliferation

21 `enable_*` flags in CalibrationSchema. Each must be set `True` in every scenario YAML to activate its system. This creates a maintenance burden — new scenarios must remember to set all 21 flags.

**Recommendation**: Consider an `enable_all_modern` meta-flag that sets all modern-era flags. Historical scenarios would still set individual flags appropriate to their era.

*(Phase structure follows after all theme audits below.)*

---

## Theme 4: Performance Hot Paths

### 4.1 O(n) Nearest-Enemy Search in Tight Loop (CRITICAL)

**File**: `simulation/battle.py:864-874`

```python
def _nearest_enemy_dist(unit_pos, enemies):
    best = float("inf")
    for e in enemies:
        dx = e.position.easting - ux
        dy = e.position.northing - uy
        d = math.sqrt(dx * dx + dy * dy)
        if d < best:
            best = d
    return best
```

Called **per unit per tick** in the engagement loop. For Golan Heights (290 units), this means ~250 O(n) searches = 62,500 distance calculations per tick. Across ~2,000 ticks = ~125 million distance calculations.

**Fix**: Build STRtree once per tick, query nearest neighbor in O(log n). Expected speedup: 4-5x for large scenarios.

### 4.2 Data Link Parent Unit Linear Search (HIGH)

**File**: `simulation/battle.py:2658-2661`

Each UAV engagement does a linear search through all same-side units to find parent by entity_id.

**Fix**: Pre-build `unit_id → unit` dict once per tick.

### 4.3 FOW Update O(n^2) Nested Loop (HIGH)

**File**: `simulation/battle.py:1111-1134`

For each friendly unit, iterates all enemy units to build signature data. 125 x 125 = 15,625 signature lookups per tick when `enable_fog_of_war=True`.

**Fix**: Cache signature profiles at scenario load time rather than per-tick lookup.

### 4.4 Repeated Engine getattr in Per-Unit Loop (MEDIUM)

**File**: `simulation/battle.py:2621-2900`

99 `getattr(ctx, "X_engine", None)` calls in battle.py, many inside per-unit loops. Engine references should be extracted to local variables before the loop.

### 4.5 Calibration Value Lookups in Inner Loop (MEDIUM)

**File**: `simulation/battle.py:2758-2772`

`cal.get("observation_decay_rate", 0.05)` called per target per tick. Should be cached once per tick.

### 4.6 String-Based Engagement Routing (LOW-MEDIUM)

**File**: `simulation/battle.py:3050-3090`

Weapon category parsed to string and compared per weapon per engagement. Should be pre-cached during scenario load.

### Performance Summary

| Item | Severity | Est. Impact | Fix Complexity |
|------|----------|-------------|----------------|
| Nearest-enemy STRtree | CRITICAL | 4-5x speedup | Low (proven pattern in rally/rout) |
| unit_id→unit dict | HIGH | 1.5x for UAV scenarios | Trivial |
| FOW signature caching | HIGH | 2x when FOW enabled | Low |
| Engine ref extraction | MEDIUM | 1.2x | Trivial |
| Calibration caching | MEDIUM | 1.1x | Trivial |
| Weapon category cache | LOW-MEDIUM | 1.1x | Low |

**Golan Heights target**: 417s → <120s via STRtree + dict cache + ref extraction.

---

## Theme 5: API & Frontend Drift

### 5.1 CalibrationSliders Significantly Outdated (MEDIUM)

**File**: `frontend/src/pages/editor/CalibrationSliders.tsx`

Only 4 sliders exposed: `hit_probability_modifier`, `target_size_modifier`, `morale_degrade_rate_modifier`, `thermal_contrast`. Engine now has 21 `enable_*` boolean flags and ~50 calibration parameters.

**Fix**: Generate sliders dynamically from CalibrationSchema. Add `enable_*` toggles section.

### 5.2 Missing ScenarioSummary Fields (MEDIUM)

**File**: `api/schemas.py:16-28`

`ScenarioSummary` is missing `has_space` and `has_dew` boolean fields. Frontend `ConfigBadges.tsx` references `space_config` and `dew_config` but the summary API doesn't expose them.

**Fix**: Add `has_space: bool = False` and `has_dew: bool = False` to ScenarioSummary. Wire in `_extract_summary()`.

### 5.3 RunSubmitRequest Lacks Structured Override Documentation (LOW)

**File**: `api/schemas.py:78-85`

`config_overrides` is `dict[str, Any]` with no documentation of what keys are valid. Users can't discover CalibrationSchema fields from the API.

**Fix**: Add docstring or create sub-models for calibration_overrides structure. Consider an OpenAPI schema endpoint.

### 5.4 Morale Calibration Terminology Outdated (LOW)

**File**: `frontend/src/pages/editor/CalibrationSliders.tsx:12`

Slider uses flat key `morale_degrade_rate_modifier` which is auto-flattened by CalibrationSchema's before-validator. Works, but terminology is inconsistent with nested schema.

---

## Code Quality Audit Results

A comprehensive code quality audit found **zero critical issues**:

| Check | Result |
|-------|--------|
| Bare `print()` in source | PASS — zero instances |
| Bare `random` module | PASS — zero imports |
| Bare `np.random` module calls | PASS — all via RNGManager |
| Non-deterministic `set()` iteration | PASS — 79 usages, all safe (membership/set-ops only) |
| Type hints on public API | PASS — 100% coverage sampled |
| Circular imports | PASS — dependency graph clean |
| Mutable default arguments | PASS — zero instances |
| Exception swallowing | PASS — zero `except: pass` patterns |
| `type: ignore` comments | PASS — 11 instances, all justified |
| Duplicate code blocks | PASS — no 10+ line duplicates |
| Magic numbers without comments | PASS — all documented or in config |

**battle.py at 4,258 lines** is the only file flagged for potential decomposition. 24 files exceed 500 lines but all are cohesive within their domain.

---

## Documentation Site Audit Results

All user-facing documentation is **accurate and current** as of Phase 67 completion:

| Document | Status |
|----------|--------|
| `docs/index.md` | Current — correct test counts, phase counts, feature lists |
| `docs/guide/getting-started.md` | Current — setup instructions verified |
| `docs/guide/scenarios.md` | Current — all scenarios documented |
| `docs/concepts/architecture.md` | Current — module graph correct |
| `docs/concepts/models.md` | Current — all 10 models documented |
| `docs/reference/api.md` | Current — all endpoints listed |
| `docs/reference/eras.md` | Current — all 5 eras covered |
| `docs/reference/units.md` | Current — all unit types listed |
| `README.md` | Current — overview, phases, features all correct |
| `mkdocs.yml` | Current — nav includes all 67 phase devlogs |

No stale information found. Living document discipline has been maintained.

---

## Theme 6: Historical Scenario Correctness

### 6.1 Outcome Accuracy

14 historical era scenarios evaluated. 13/14 produce the historically correct winner, but resolution quality is poor:

| Scenario | Era | Sim Winner | Victory Condition | Historical Accuracy |
|----------|-----|-----------|-------------------|---------------------|
| Agincourt 1415 | Ancient/Medieval | english | time_expired | Correct winner, wrong condition — should be decisive |
| Cannae 216 BC | Ancient/Medieval | carthaginian | time_expired | Correct winner, wrong condition |
| Hastings 1066 | Ancient/Medieval | norman | force_destroyed | Correct |
| Salamis 480 BC | Ancient/Medieval | greek | time_expired | Correct winner, wrong condition |
| Austerlitz 1805 | Napoleonic | french | force_destroyed | Correct |
| Trafalgar 1805 | Napoleonic | british | time_expired | Correct winner, wrong condition — historically decisive (22 ships sunk/captured) |
| Waterloo 1815 | Napoleonic | british | force_destroyed | Correct |
| Cambrai 1917 | WW1 | british | force_destroyed | Correct |
| Jutland 1916 | WW1 | british | time_expired | Acceptable — tactically inconclusive, British strategic victory |
| **Somme 1916** | WW1 | **german** | **force_destroyed** | **WRONG** — historically a failed British offensive/stalemate, not a German decisive victory |
| Kursk 1943 | WW2 | soviet | time_expired | Acceptable — Soviet strategic victory |
| Midway 1942 | WW2 | usn | time_expired | Correct winner, wrong condition — historically decisive (4 carriers sunk) |
| Normandy 1944 | WW2 | us | force_destroyed | Correct |
| Stalingrad 1942 | WW2 | soviet | force_destroyed | Correct |

### 6.2 Systemic Issues

**9/14 scenarios resolve via `time_expired`** instead of decisive combat. Root causes:
- Maps too large for combat resolution within tick budget (Jutland: 100km x 80km)
- Units start too far apart to engage within max_ticks
- Era-specific combat resolution too slow (archery/volley fire attrition rate)

**Somme semantics wrong**: Scenario treats it as "destroy the enemy" but historically it was "British try to break German trench line and fail." Victory condition should be `territory_control` (British must capture positions), with German victory on `time_expired` (successful defense).

**Calibration is empirically tuned, not principled**: All scenarios use per-side `force_ratio_modifier` (Dupuy CEV) calibrated to produce the correct winner. Example: Trafalgar uses 2.5x British modifier despite British numerical inferiority. This produces correct results but is theoretically circular — the calibration IS the outcome.

### 6.3 Era Engine Verification

All 4 era frameworks have their specialized engines instantiated and routed:
- **WW1**: BarrageEngine, VolleyFireEngine, MeleeEngine, TrenchSystemEngine — all routed in battle.py:3628-3675
- **Napoleonic**: VolleyFireEngine, MeleeEngine, CavalryEngine, NapoleonicFormationEngine — routed in battle.py:3454-3525
- **Ancient/Medieval**: ArcheryEngine, MeleeEngine, SiegeEngine, AncientFormationEngine — routed in battle.py:3546-3691
- **WW2**: NavalGunneryEngine, NavalSurfaceEngine, NavalSubsurfaceEngine — routed in battle.py:328-497

No scenarios are "modern combat with historical names" — era-specific engines ARE being invoked.

---

## Theme 7: API Server Robustness

### 7.1 Critical Concurrency Bugs

| Issue | File | Severity |
|-------|------|----------|
| Batch execution bypasses semaphore — unlimited thread spawning | `api/run_manager.py:477` | CRITICAL |
| `POST /runs/from-config` calls `tempfile.mkdtemp()` in async handler — blocks event loop | `api/routers/runs.py:81` | CRITICAL |
| Multiple WS clients share single queue — slow client blocks all, full queue silently drops progress | `api/run_manager.py:47,114` | HIGH |
| Analysis endpoints (`compare`/`sweep`) spawn unbounded threads via `asyncio.to_thread()` | `api/routers/analysis.py:42,67` | HIGH |
| No graceful shutdown — running simulations become zombies on SIGTERM | `api/main.py:18-35` | HIGH |
| WebSocket server restart loses all in-flight run state (in-memory only) | `api/run_manager.py:29-31` | HIGH |

### 7.2 Security & Robustness Gaps

| Issue | Severity |
|-------|----------|
| No rate limiting on any endpoint | MEDIUM |
| No authentication or authorization | MEDIUM |
| No request body size limits — DoS via large config dicts | MEDIUM |
| Events endpoint loads up to 50,000 events into memory | MEDIUM |
| Scenario scanning re-reads all YAML on every `/scenarios` request (no caching) | MEDIUM |
| SQLite has no WAL mode — `database is locked` under concurrent writes | MEDIUM |
| Silent column migration failures (`ALTER TABLE` wrapped in bare `except Exception: pass`) | LOW |
| Health endpoint doesn't check DB, active tasks, or memory usage | LOW |

### 7.3 What Works Well

- Semaphore-based concurrency limiting for single runs (max_concurrent=4)
- Thread pool executor for blocking simulation code
- Proper cleanup in finally blocks (no memory leaks on normal runs)
- Client disconnection handled in WebSocket handlers
- Input validation via pydantic schemas on most endpoints

---

## Theme 8: Frontend Accessibility

### 8.1 Critical Issues (21)

| Issue | File | Impact |
|-------|------|--------|
| Canvas tactical map has no accessible alternative | `TacticalMap.tsx:413-424` | Screen readers see nothing |
| SVG icons missing `aria-label` on interactive elements | `SearchInput.tsx`, `ExportMenu.tsx`, `MapLegend.tsx` | Icons convey meaning without text |
| Form inputs not explicitly associated with labels (no `htmlFor`/`id`) | `GeneralSection.tsx:20-68` | Assistive tech can't connect label to input |
| Validation errors not announced (no `role="alert"`, `aria-live`) | `ScenarioEditorPage.tsx:91-100` | Screen readers miss dynamic errors |
| Modal focus traps not verified | `UnitDetailModal.tsx`, `ConfirmDialog.tsx` | Users can tab to background elements |
| No skip-to-content link | `Layout.tsx:10-29` | Keyboard users must tab through entire nav |
| Color-only status indicators (green/red circles) | `Sidebar.tsx:48-54` | Color-blind users can't distinguish status |
| Plotly charts have no text alternative | All chart components | Data inaccessible to screen readers |
| Playback buttons use unicode symbols without labels | `PlaybackControls.tsx:38-63` | `<<`, `>>`, `||` not screen-reader friendly |
| Canvas unit selection requires mouse click only | `TacticalMap.tsx:349-367` | No keyboard alternative |
| Loading spinner has no accessible status | `LoadingSpinner.tsx` | No `role="status"` or `aria-label` |

### 8.2 Major Issues (18)

- Dark mode color contrast unverified (potential WCAG AA violations)
- Keyboard shortcuts not documented for screen readers
- Small touch targets in map controls at 200% zoom (<44x44px)
- Table headers missing `scope="col"` attribute
- Clickable Card component has `onClick` but no `role="button"` or keyboard handler
- Tab panels missing `role="tabpanel"` and `aria-labelledby`
- Required form fields not marked with `required` attribute
- No `prefers-reduced-motion` support for animations

### 8.3 Minor Issues (12)

- Inconsistent `aria-label` presence across buttons
- StatCard uses `<dt>`/`<dd>` without wrapping `<dl>`
- Heading hierarchy may skip levels in some pages
- Virtualized lists may break keyboard navigation

---

## Theme 9: CI/CD & Packaging

### 9.1 CI/CD Gaps

| What Exists | What's Missing |
|-------------|----------------|
| `docs.yml` — MkDocs deployment on push to main | `test.yml` — Python pytest suite (9,000+ tests) |
| Manual dispatch for docs rebuild | `frontend-test.yml` — vitest (272 tests) |
| | `lint.yml` — Python + TypeScript linting |
| | `build.yml` — Docker build verification |
| | Automated test reporting on PRs |

**Impact**: All 9,249 tests run only locally. No CI gate prevents merging broken code.

### 9.2 Scripts Directory Hygiene

| Category | Files | Status |
|----------|-------|--------|
| Core utilities | `evaluate_scenarios.py`, `check_scenarios.py`, `check_yaml.py`, `download_terrain.py` | Active, maintained |
| Debug scripts | `debug_loader.py`, `debug_scenario.py`, `test_napoleon_quick.py` | Stale — hardcoded paths, minimal use |
| Recent debug | `debug_taiwan*.py` (7 files), `test_taiwan_*.py` (3 files) | Active development artifacts |
| Dev launchers | `dev.sh`, `dev.ps1` | Active, uses `uv` correctly |
| Evaluation artifacts | 15 `evaluation_results_v*.json` + 17 `evaluation_stderr_v*.log` | Should be `.gitignored` |

### 9.3 Packaging

| Component | Status |
|-----------|--------|
| `pyproject.toml` | Current — 7 required, 6 optional extras, proper constraints |
| `uv.lock` | Current — 95 packages, last updated Mar 5 |
| `Dockerfile` | Current — multi-stage, uses uv, handles frontend build |
| `frontend/package.json` | Current — React 18, Vite 6, TypeScript 5.7, all LTS |
| `.python-version` | 3.12.10 pinned |
| `LICENSE.md` | PolyForm Noncommercial 1.0.0 (modified) — matches CLAUDE.md |
| `CONTRIBUTING.md` | "No external contributions" — clear |
| `docs.yml` CI workflow uses bare `pip install` | Should use `uv` for consistency |

---

## Revised Phase Structure (15 Phases)

### Phase 68: Consequence Enforcement

**Focus**: Convert "log but don't act" patterns to behavioral enforcement.

**Scope**:
- P0-1: Fuel consumption enforcement (per-vehicle-type rates from YAML, movement gate)
- P0-2: Ammo depletion gate (prevent firing at 0 rounds)
- P1-1: Order delay enforcement queue (delayed execution, echelon-scaled)
- P1-2: Order misinterpretation (parameter modification on misinterp roll)
- P1-7: Fire zone damage application (units in fire take burn damage per tick)
- P1-4: Stratagem duration/expiry (time-limited tactical advantages)
- 1.7: Guerrilla retreat movement (disengage → physical withdrawal)

**Tests**: Unit tests for each enforcement path. Integration tests verifying scenarios still produce correct outcomes with enforcement active.

### Phase 69: C2 Depth

**Focus**: Make the C2 chain produce real effects.

**Scope**:
- P1-3: ATO sortie consumption (sorties_today incremented, gate enforced)
- P1-5: Planning result injection (MDMP results influence AI decisions)
- P1-10: Deception effect on enemy AI (false disposition into FOW)
- P1-11: CommandEngine hierarchy enforcement (authority checks when engine available)
- 1.8: Burned zone concealment reduction in detection
- Order delay integration testing (cross-phase with Phase 68)

**Tests**: C2 chain integration tests, AI behavior tests with deception, authority enforcement tests.

### Phase 70: Performance Optimization

**Focus**: Eliminate O(n^2) hot paths in battle.py.

**Scope**:
- Replace `_nearest_enemy_dist()` with STRtree nearest-neighbor query
- Build `unit_id → unit` dict per tick for parent lookups
- Cache signature profiles at scenario load for FOW
- Extract engine references to local variables before per-unit loops
- Cache calibration values before inner loops
- Pre-cache weapon category parsing at scenario load
- Benchmark: Golan Heights from 417s to <120s target

**Tests**: Performance regression tests with timing assertions. Correctness tests verifying identical outcomes before/after optimization.

### Phase 71: Missile & Carrier Ops Completion

**Focus**: Close the two largest remaining engine gaps.

**Scope**:
- P1-8: MissileEngine per-tick flight update (launch → flight → terminal → impact)
- P1-9: MissileDefenseEngine intercept (missile-as-contact detection, engagement)
- P1-6: CarrierOpsEngine full battle loop wiring (CAP dispatch, sortie management, recovery windows)
- MISSILE engagement type routing in battle.py

**Tests**: Missile flight/intercept tests, carrier ops cycle tests, naval scenario validation.

### Phase 72: Checkpoint & State Completeness

**Focus**: Make checkpoint/restore actually work.

**Scope**:
- P0-3: Register all engine state with CheckpointManager
- Verify get_state/set_state round-trip for all engines
- Test checkpoint mid-battle → restore → resume produces identical outcomes
- Remove or mark unused get_state/set_state implementations

**Tests**: Checkpoint round-trip tests, deterministic replay verification.

### Phase 73: Historical Scenario Correctness

**Focus**: Make historical scenarios resolve via decisive combat with historically accurate victory conditions.

**Scope**:
- Fix Somme 1916: change to `territory_control` victory condition (British must capture German positions); German win on `time_expired` (successful defense), not `force_destroyed`
- Audit all 9 `time_expired` scenarios: adjust map sizes, starting distances, tick budgets, or combat tempo so battles resolve decisively
- Trafalgar: should resolve via `force_destroyed` (22 of 33 ships historically sunk/captured), not `time_expired`
- Agincourt: should resolve via `force_destroyed` or `morale_collapsed` (decisive English victory)
- Salamis: should resolve via `force_destroyed` (Persian fleet destroyed)
- Midway: should resolve via `force_destroyed` (4 Japanese carriers sunk)
- Cannae: should resolve via `force_destroyed` (Roman army annihilated)
- Kursk: should resolve via `force_destroyed` or territorial (Soviet counteroffensive succeeded)
- Review calibration methodology: document Dupuy CEV rationale for each scenario rather than pure empirical fitting

**Tests**: MC validation for all 14 historical scenarios. Victory condition type assertions (not just winner).

### Phase 74: Combat Engine Unit Tests

**Focus**: Add dedicated unit tests for all combat engines.

**Scope**:
- Unit tests for all 33 combat engine files
- Focus on public API methods and critical private methods
- Target: damage.py, ammunition.py, ballistics.py, missiles.py, naval_surface.py, air_combat.py, air_defense.py, air_ground.py, melee.py, siege.py, unconventional.py, directed_energy.py, engagement.py, suppression.py, hit_probability.py, fratricide.py, gas_warfare.py, carrier_ops.py, archery.py, volley_fire.py, barrage.py, naval_gunnery.py, naval_mine.py, naval_subsurface.py

**Tests**: Target 300+ new unit tests across combat domain.

### Phase 75: Simulation Core & Domain Unit Tests

**Focus**: Unit tests for engine.py, battle.py, and domain modules.

**Scope**:
- Unit tests for all private methods in battle.py (47 methods)
- Unit tests for all private methods in engine.py (30 methods)
- Extract battle.py subsystems for testability (targeting, routing, env modifiers)
- Tests for environment (9), terrain (16), detection (11), movement (16), morale (7), logistics (15) modules
- Tests for scenario.py, campaign.py, victory.py, metrics.py, recorder.py, aggregation.py, calibration.py

**Tests**: Target 500+ new unit tests across simulation core and domain modules.

### Phase 76: API Robustness

**Focus**: Fix critical concurrency bugs and harden the API for reliable use.

**Scope**:
- Fix batch execution semaphore bypass (add `async with self._semaphore` to `_execute_batch`)
- Move `tempfile.mkdtemp()` to thread pool (`asyncio.to_thread`)
- Add semaphore to analysis endpoints (compare/sweep)
- Implement per-client WS queues (multicast pattern instead of shared queue)
- Add graceful shutdown signal handling (cancel running tasks, drain, close DB)
- Enable SQLite WAL mode
- Add request body size limits to pydantic schemas
- Add scenario/unit caching (avoid YAML re-read on every request)
- Split health endpoint into liveness + readiness
- Fix silent column migration failure (log warning instead of bare except)

**Tests**: Concurrent request tests, WebSocket disconnect tests, shutdown tests.

### Phase 77: Frontend Accessibility

**Focus**: WCAG 2.1 AA compliance for all critical user paths.

**Scope**:
- Canvas tactical map: add `role="application"`, `aria-label`, semantic unit table alternative
- Add missing ARIA labels to all SVG icons, buttons, form inputs
- Wire `htmlFor`/`id` on all form label-input pairs
- Add `role="alert"` and `aria-live` to validation error containers
- Verify Headless UI focus traps in all modals (UnitDetailModal, ConfirmDialog, KeyboardShortcutHelp)
- Add skip-to-content link in Layout.tsx
- Replace color-only indicators with icon+text alternatives
- Add `role="status"` and `aria-label` to LoadingSpinner
- Add `scope="col"` to all table headers
- Add `role="button"` + keyboard handler to clickable Card component
- Add `role="tabpanel"` + `aria-labelledby` to analysis tab panels
- Add `required`/`aria-required` to required form fields
- Add `prefers-reduced-motion` media query support
- Add Plotly chart data table alternatives (expandable `<details>` below each chart)
- Keyboard navigation for tactical map unit selection

**Tests**: Automated axe/Lighthouse a11y tests, keyboard navigation integration tests.

### Phase 78: P2 Environment Wiring

**Focus**: Wire remaining P2 environment items that improve fidelity.

**Scope**:
- Ice crossing pathfinding (frozen water traversal)
- Vegetation height LOS blocking (tall vegetation blocks ground-level LOS)
- Bridge capacity enforcement (unit weight field, capacity gate)
- Ford crossing routing (river ford in pathfinding)
- Fire spread cellular automaton (wind-biased cell-to-cell spread)
- Environmental fatigue acceleration (temperature-driven fatigue)

**Tests**: Environment integration tests, pathfinding tests with new constraints.

### Phase 79: CI/CD & Packaging

**Focus**: Automated test pipeline, script cleanup, packaging hygiene.

**Scope**:
- Create `.github/workflows/test.yml`: Python pytest (fast, exclude slow), frontend vitest, on push + PR
- Create `.github/workflows/lint.yml`: Python ruff/mypy, frontend ESLint, on push + PR
- Create `.github/workflows/build.yml`: Docker build verification, on PR
- Update `docs.yml` to use `uv pip install` instead of bare `pip`
- Archive stale debug scripts to `scripts/archive/`
- Add evaluation artifacts (`scripts/evaluation_results_*.json`, `scripts/evaluation_stderr_*.log`) to `.gitignore`
- Clean up unused test fixtures (rng_manager, sim_clock in conftest.py)

**Tests**: CI pipeline self-tests (verify workflows run correctly).

### Phase 80: API & Frontend Sync

**Focus**: Bring API schemas and frontend components current with engine state.

**Scope**:
- Add `has_space`, `has_dew` to ScenarioSummary API schema
- Generate CalibrationSliders dynamically from CalibrationSchema (all 50+ params + 21 enable_* toggles)
- Add `enable_all_modern` meta-flag to CalibrationSchema
- Document config_overrides structure in RunSubmitRequest
- Fix eastern_front_1943 weapon assignments (WW1 → WW2)
- Add victory_conditions to golan_heights scenario
- Create scenarios exercising all 16 never-set CalibrationSchema fields
- Remove dead YAML field (unit_cost_factor) or wire it
- Exercise non-default calibration values to verify behavior

**Tests**: API contract tests, frontend component tests, calibration coverage tests.

### Phase 81: Recalibration & Validation

**Focus**: Full recalibration after all behavioral changes, final validation.

**Scope**:
- Recalibrate all 37+ scenarios with new enforcement (fuel, ammo, orders, fire)
- Recalibrate all 14 historical scenarios after Phase 73 corrections
- MC validation with tightened thresholds (80%, 10 seeds)
- Performance profiling — verify Golan Heights <120s
- Cross-doc audit — update all docs for Block 8 changes
- Block 8 exit criteria verification (all 10 criteria)

**Tests**: Regression suite, MC validation, performance benchmarks.

### Phase 82: Block 8 Postmortem & Documentation

**Focus**: Update all living documents, cross-doc audit, deficit inventory.

**Scope**:
- Update CLAUDE.md with Block 8 status
- Update README.md with new test counts, phase counts
- Update docs site (index.md, architecture, models, API reference)
- Update devlog/index.md with new deficit dispositions
- Run `/cross-doc-audit` — verify all 19 checks pass
- Phase devlogs for Phases 68–82
- Update MEMORY.md with Block 8 lessons

**Tests**: Cross-doc audit assertions.

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Fuel enforcement breaks all scenarios | High | Conservative default rates; `enable_fuel_consumption` flag |
| Order delay makes AI non-responsive | Medium | Short default delays; tunable per echelon |
| Battle.py refactoring introduces regressions | Medium | Extract one subsystem at a time; full regression after each |
| STRtree optimization changes engagement order | Low | Seed-controlled RNG means deterministic despite spatial index |
| Historical scenario recalibration is time-consuming | High | Focus on the 9 `time_expired` scenarios; Somme is highest priority |
| A11y changes break existing vitest tests | Medium | Run vitest after each component change |
| CI/CD workflows are fragile on Windows runners | Medium | Use ubuntu-latest runners; Windows testing via local dev |
| API robustness changes affect frontend contract | Low | API schemas are typed; frontend tests catch breakage |
| Test writing for 270 files is enormous scope | High | Prioritize critical paths (combat, battle.py, engine.py) in 74-75; domain tests can continue into future blocks |
| Calibration doesn't converge with enforcement + scenario fixes | Medium | Individual enable flags; staged rollout like Block 7 |

---

## Summary

| Category | Items | Priority | Phase(s) |
|----------|-------|----------|----------|
| Consequences not enforced | 8 | P0–P1 | 68, 69 |
| Deferred P0 infrastructure | 3 | P0 | 68, 72 |
| Deferred P1 integration | 11 | P1 | 68, 69, 71 |
| Performance hot paths | 6 | High | 70 |
| Historical scenario correctness | 14 scenarios | High | 73 |
| Combat engine unit tests | 33 files | Medium | 74 |
| Simulation core unit tests | 9+ files | Medium | 75 |
| API concurrency bugs | 6 critical/high | Medium | 76 |
| Frontend accessibility | 51 issues | Medium | 77 |
| Deferred P2 wiring | 28 | P2 | 78 |
| CI/CD pipeline | 3 missing workflows | Medium | 79 |
| API/frontend drift | 4 | Medium | 80 |
| CalibrationSchema exercise | 16 fields | Low | 80 |
| Scenario data issues | 3 | Low | 80 |
| Recalibration | 37+ scenarios | Required | 81 |
| Documentation sync | All docs | Required | 82 |
| Code quality issues | 0 | N/A (clean) | — |
| Docs site staleness | 0 | N/A (current) | — |

**Block 8 scope**: Phases 68–82 (15 phases). No new subsystems, no new engines, no new eras. Convert structural wiring to behavioral enforcement, add test depth, fix historical scenarios, improve performance, harden API, accessibility compliance, CI/CD automation, and full recalibration.

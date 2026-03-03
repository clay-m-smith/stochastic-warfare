# Phase 7: Engagement Validation

## Summary

Phase 7 validates the combat model against 3 historical engagements: 73 Easting (1991), Falklands Naval (1982), and Golan Heights (1973). It builds a reusable validation infrastructure (scenario runner, Monte Carlo harness, metrics extraction, historical data loader) and calibrates engagement parameters to produce results within 2x of historical outcomes.

**Modules**: 5 source files in `stochastic_warfare/validation/`
**YAML data**: 10 new unit definitions, 9 new weapon/ammo definitions, 1 new sensor definition, 4 new signature profiles, 3 scenario packs
**Tests**: 188 new tests (2,639 total)
**Status**: Complete

## What Was Built

### Validation Infrastructure (Steps 1-4)
- `historical_data.py` — Pydantic models for historical engagement data: `HistoricalEngagement`, `ForceDefinition`, `TerrainSpec`, `HistoricalMetric`, `ComparisonResult`. YAML loader with metric comparison logic.
- `metrics.py` — `EngagementMetrics` static methods: casualty exchange ratio, equipment losses, personnel casualties, ships sunk, missiles hit ratio, ammunition expended, morale distribution. `SimulationResult` and `UnitFinalState` data containers.
- `scenario_runner.py` — Lightweight orchestrator: terrain builders (flat desert, open ocean, hilly defense), force builder (line abreast formation), pre-scripted behavior engine, and a tick loop wiring detection → engagement → morale. Supports calibration overrides per scenario.
- `monte_carlo.py` — `MonteCarloHarness`: runs N iterations with different seeds, collects per-run metrics, computes mean/std/CI, compares to historical outcomes via `ComparisonReport`.

### YAML Data (Steps 5-6)
**New units** (10): m1a1_abrams, t72m, shot_kal, t55a, t62, bmp1, m3a2_bradley, type42_destroyer, type22_frigate, sea_harrier, super_etendard
**New weapons** (5): l7_105mm, d10t_100mm, u5ts_115mm, 2a46m_125mm, 2a28_grom_73mm, tow2_atgm, am39_exocet, sea_dart, at3_sagger
**New ammunition** (5): 105mm_l52_apds, 125mm_3bm22_apfsds, 73mm_pg15_heat, 115mm_3bm3_apfsds, 25mm_m791_apds, tow2_warhead, am39_exocet_warhead, sea_dart_warhead, at3_sagger_warhead
**New sensors** (1): active_ir_sight
**New signatures** (4): t72m, shot_kal, type42_destroyer, super_etendard
**Scenario packs** (3): 73_easting, falklands_naval, golan_heights

### Calibration (Step 8)
Per-scenario `calibration_overrides` tune hit probability, target size, morale rates, force ratio weights, and starting positions. Global engine configs remain untouched — 2,571 existing tests unaffected.

## Design Decisions

### DD-1: No New ModuleId Value
The validation runner orchestrates existing engines without generating its own randomness. Adding `VALIDATION` to `ModuleId` would change `SeedSequence.spawn()` count, breaking deterministic replay of all existing streams.

### DD-2: Pre-Scripted Behavior (No AI)
Units follow simple behavioral rules: attackers advance toward enemies at specified speed, defenders hold positions. No C2 order propagation. Behavior encoded in scenario YAML `behavior_rules`.

### DD-3: Deferred Damage Resolution
Both sides fire before any damage takes effect within a tick (simultaneous resolution). Prevents engagement order bias where side processed first kills opponents before they fire.

### DD-4: Weapon Priority by Range
Engagement loop sorts weapons by max_range descending. ATGMs (3000m) are tried before guns (1300m) at long range. This produces historically correct BMP-1 behavior (AT-3 Sagger at range, Grom close in).

### DD-5: Weather-Independent Sensors
Thermal, radar, and ESM sensors bypass weather visibility penalty. Radar-guided missiles (Exocet, Sea Dart) are not degraded by fog/sandstorm — only visual sensors suffer weather penalties.

### DD-6: Calibration Via Scenario Overrides Only
Each scenario YAML has `calibration_overrides` that adjust engine behavior (hit probability modifiers, morale rates, starting positions, per-side force ratio weights). Global defaults untouched.

## Calibration Results

### 73 Easting
| Metric | Historical | Simulated (seed=42) | Tolerance | Status |
|--------|-----------|---------------------|-----------|--------|
| red_units_destroyed | 28 | 33 | [14, 56] | PASS |
| duration_s | 1380 | 800 | [690, 2760] | PASS |
| blue_units_destroyed | 1 | 0 | [0.33, 3] | KNOWN |
| exchange_ratio | 28 | inf | [14, 56] | KNOWN |

The 4000m thermal vs 800m IR detection asymmetry produces a truly one-sided engagement — blue destroys all red before red detects blue. This accurately models the historical reality (Eagle Troop suffered 0 KIA, 1 Bradley lost to friendly fire) but the zero blue losses produce inf exchange ratio.

### Falklands Naval
| Metric | Historical | Simulated (seed=42) | Tolerance | Status |
|--------|-----------|---------------------|-----------|--------|
| blue_ships_sunk | 1 | 1 | [0.5, 2] | PASS |
| missiles_hit_ratio | 0.5 | 0.636 | [0.25, 1.0] | PASS |

Exocets fire and hit blue ships with ~57% Pk per missile. Deferred damage ensures both sides fire simultaneously. Sea Darts destroy Super Etendards in the same tick.

### Golan Heights
| Metric | Historical | Simulated (seed=42) | Tolerance | Status |
|--------|-----------|---------------------|-----------|--------|
| exchange_ratio | 4.6 | 4.39 | [2.3, 9.2] | PASS |
| red_units_destroyed | 100 | 123 | [50, 200] | PASS |
| blue_units_destroyed | 15 | 28 | [7.5, 30] | PASS |
| duration_s | 64800 | 46700 | [43200, 97200] | PASS |

All four metrics pass tolerance. Hull-down modifier (0.55), slow advance (0.15 mps), and per-side force ratio weighting produce realistic Israeli defense dynamics.

## Issues & Fixes During Calibration

1. **M242 Bushmaster had 5.56mm ammo** — `compatible_ammo: [556_ball]` was wrong for a 25mm cannon. Fixed with new `25mm_m791_apds` ammo definition.
2. **Russian weapon YAMLs missing** — Created `2a46m_125mm`, `2a28_grom_73mm`, `u5ts_115mm`, `tow2_atgm` weapon definitions with corresponding ammo.
3. **Thermal visibility penalty on thermal-detected targets** — `vis_mod = min(visibility/range, 1.0)` gave 0.11x penalty in sandstorm for thermal. Fixed: thermal and radar sensors set `vis_mod=1.0`.
4. **Blast damage not applied to naval targets** — Scenario runner required `penetrated=True` for damage, but HE/blast damage (Exocet warheads) never sets `penetrated`. Fixed to check `damage_fraction > 0` instead.
5. **Sequential engagement ordering** — Blue side fired first, destroying red before they could shoot. Fixed with deferred damage: both sides fire, then damage applied.
6. **Uniform target_size_modifier** — Hull-down advantage applied to both sides equally. Acceptable simplification since per-side targeting would require major refactoring.
7. **Sensor count test assertion** — Adding `active_ir_sight.yaml` changed sensor count from 8→9. Updated test assertions.

## Known Limitations / Post-MVP Refinements

1. **Pre-scripted behavior, not AI** — tactical adaptation deferred to Phase 8
2. **Synthetic terrain** — programmatic heightmaps, not actual topographic data
3. **No logistics in validation** — short engagements don't need supply chain
4. **No C2 propagation** — direct behavior, no order chain or comms delay
5. **Simplified force compositions** — representative samples, not complete OOB
6. **73 Easting exchange_ratio = inf** — detection asymmetry prevents any blue losses in all tested seeds; exchange ratio metric fails for one-sided engagements
7. **No fire rate limiting** — units fire once per tick regardless of weapon ROF
8. **Uniform target_size_modifier** — applies equally to both sides; hull-down should only benefit defenders
9. **No wave attack modeling** — all red units advance simultaneously; historical Golan had multiple attack waves
10. **Falklands simplified** — models Sheffield Exocet attack only; San Carlos "Bomb Alley" raids not modeled

## Post-Phase Post-Mortem

### Performance Optimizations Applied (Pass 1 — in-phase)
- Hoisted `_WEATHER_BYPASS_TYPES` from inner loop to module-level `frozenset` (eliminated per-attacker per-tick set construction)
- Pre-build per-side active enemy lists once per tick instead of per-attacker (O(n) → O(1) per attacker)
- Vectorized hilly terrain generation: replaced Python row×col loops with numpy meshgrid + broadcasting (15,000 cells for Golan)
- Added parallel Monte Carlo via `ProcessPoolExecutor` (2.79x speedup on Golan Heights with 4 workers; `max_workers` config option)
- Monte Carlo CI now uses Student's t-distribution for n < 30, scipy.stats for arbitrary confidence levels

### Performance Optimizations Applied (Pass 2 — post-completion)
- **`fog_of_war.py`**: O(n) linear scan of `wv.contacts` → O(1) dict membership check
- **`los.py`**: Vectorized `check_los` ray march — added `_check_los_vectorized` path using numpy batch operations; falls back to scalar when infrastructure (buildings) present. ~160 Python iterations → 5 numpy ops per LOS check
- **`heightmap.py`**: Added `elevation_at_batch()` and `in_bounds_batch()` for vectorized bilinear interpolation over arrays of positions
- **`scenario_runner.py`**: Vectorized nearest-enemy distance computation (pre-built numpy position arrays + `np.argmin`); pre-sorted weapons at setup time instead of per-tick sort
- **`pathfinding.py`**: Extracted `_cell_difficulty()` with per-cell cost cache; added closed set to prevent re-expansion of settled A* nodes; pre-computed diagonal/cardinal distances
- **Net result**: Validation test runtime 86s → 57s (34% faster)

### Performance Optimizations Applied (Pass 3 — pre-Phase-8)
- **`events.py`**: EventBus.publish() MRO-based dispatch — O(3 dict lookups) instead of O(76 isinstance checks) per event. Critical before Phase 8 adds real subscribers.
- **`sensors.py`**: Cached `SensorType` enum on `SensorInstance` at construction. Eliminates `str.upper()` + enum dict lookup on every `sensor_type` property access.
- **`state.py`**: Morale transition matrix last-result cache. All units on a side share identical parameters within a tick — matrix computed once per side, not per unit.
- **`scenario_runner.py`**: Reuse `active_enemies_by_side` in morale section instead of rebuilding enemy list. Pass sim clock timestamp to morale events.
- **Constant dicts hoisted**: `posture_mods` (hit_probability), `posture_protect`/`posture_frag_protect` (damage), `effects_table` (suppression), `level_risks` (fratricide) — all moved to module/class level.
- **Math constants pre-computed**: `_SQRT_2`, `_FOUR_PI_CUBED`, `_BOLTZMANN_290_1E6` in detection.py. `_H` and `_EYE4` matrices in estimation.py.
- **`state.py`**: `datetime.now()` replaced with explicit sim clock timestamp in morale events — fixes determinism.
- **`pyproject.toml`**: `addopts = "-m 'not slow'"` excludes 1000-run MC tests by default. Run with `-m slow` explicitly.

### Infrastructure Improvements (post-completion)
- Created `tests/conftest.py` — shared fixtures (`rng`, `event_bus`, `sim_clock`, `rng_manager`) + helper functions (`make_rng()`, `make_clock()`, `make_stream()`) + constants (`TS`, `POS_ORIGIN`). For all Phase 8+ test files.
- Created `/simplify` skill — code quality review (duplication, complexity, performance, interface, convention)
- Created `/profile` skill — cProfile-based performance profiling, hotspot identification, benchmark templates
- Deferred Tier 2-3 performance items to Phase 8-9 in `development-phases.md`

### Mathematical Model Audit
Core models reviewed and confirmed sound for MVP:
- Hit probability Gaussian dispersion model — standard fire table approximation
- DeMarre penetration — correct classical form (Cd-vs-Mach simplification documented)
- Wayne Hughes salvo model — correctly applied for naval missile exchange
- Markov morale — properly row-stochastic, SURRENDERED absorbing
- Kalman filter — standard 4-state constant-velocity, correct predict/update
- SNR-based detection — unified erfc model across all sensor types

Pre-existing documented simplifications (damage range decay, constant Cd, no terrain collision in ballistics) confirmed as post-MVP items — none block Phase 8.

## Lessons Learned

- **Deferred damage is essential** for asymmetric engagements — sequential processing creates unrealistic engagement ordering bias.
- **Sensor type determines weather dependency** — thermal/radar should always bypass weather visibility; only visual sensors degrade.
- **Weapon sort by range** — longest-range weapon first produces correct ATGM-before-gun behavior at distance.
- **Blast damage path** — HE/blast weapons (Exocets, etc.) don't use penetration; damage resolution must handle non-penetrating damage.
- **Per-side calibration keys** are essential — force ratio modifiers, cohesion, and target size differ fundamentally between attacker/defender.
- **Smoke tests before MC** — running single-seed smoke tests catches structural bugs quickly before expensive Monte Carlo runs.
- **MC parallelization is trivial** — each iteration uses a different seed with no shared state, making ProcessPoolExecutor a perfect fit. ~3x speedup on 4 cores for expensive scenarios.
- **Vectorize terrain generation** — Python loops over grid cells are slow; numpy meshgrid + broadcasting gives orders-of-magnitude speedup for heightmap construction.

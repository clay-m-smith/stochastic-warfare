# Phase 26: Core Polish & Configuration

## Summary

Quality-focused phase: removed PRNG fallbacks from all engine constructors, replaced hardcoded magic numbers with configurable pydantic fields, added engine lifecycle improvements. No new engines or domains. Resolved 11 deficits.

**Tests**: 82 new (25 + 34 + 23), 6,559 total.

## What Was Built

### 26a: PRNG Discipline (25 tests)

Removed `np.random.default_rng()` fallback from 23 engine constructors. Made `rng` a required parameter using keyword-only syntax (`*,`) where needed to avoid Python's "required after optional" constraint.

**23 source files modified** (combat/8, detection/7, C2/3, movement/3, logistics/1, simulation/1):
- `combat/archery.py`, `barrage.py`, `gas_warfare.py`, `melee.py`, `naval_gunnery.py`, `siege.py`, `strategic_bombing.py`, `volley_fire.py`
- `detection/deception.py`, `detection.py`, `estimation.py`, `fog_of_war.py`, `intel_fusion.py`, `sonar.py`, `underwater_detection.py`
- `c2/coordination.py`, `courier.py`, `visual_signals.py`
- `movement/cavalry.py`, `convoy.py`, `naval_oar.py`
- `logistics/foraging.py`
- `simulation/aggregation.py`

**12 test files updated** to pass explicit `rng=` arguments.

Special cases:
- `fog_of_war.py` and `intel_fusion.py` create sub-engines internally — needed `rng=rng` passed through
- 3 files didn't need `*,` because `rng` was already in valid position (estimation.py, deception.py, coordination.py)

### 26b: Configurable Constants (34 tests)

Replaced hardcoded magic numbers with pydantic Config fields in 9 source files:

| File | Config Field | Default |
|------|-------------|---------|
| `cbrn/dispersal.py` | `DispersalConfig.terrain_channel_offset_m`, `terrain_channel_height_m` | 50.0, 5.0 |
| `cbrn/engine.py` | `CBRNConfig.fallback_wind_speed_mps`, `fallback_wind_direction_rad`, `fallback_cloud_cover` | 2.0, 0.0, 0.5 |
| `combat/gas_warfare.py` | `GasWarfareConfig.max_wind_angle_deg` | 60.0 |
| `terrain/trenches.py` | `TrenchConfig.along_angle_threshold_deg`, `crossing_angle_threshold_deg` | 30.0, 60.0 |
| `logistics/foraging.py` | `ForagingConfig.ambush_casualty_rate` | 0.1 |
| `ew/jamming.py` | `JammingConfig.jamming_event_radius_m` | 50000.0 |
| `ew/spoofing.py` | `check_spoof_detection(unit_id="")` parameter | "" |
| `ew/decoys_ew.py` | `EWDecoyConfig.decoy_seeker_effectiveness` (dict replacing if/elif) | {0:{0:0.7,3:0.3}, 1:{1:0.8,2:0.2}, 2:{0:0.8}, 3:{0:0.6,3:0.5}} |
| `ew/sigint.py` | `SIGINTConfig.activity_sigmoid_center`, `activity_sigmoid_scale` | 10.0, 10.0 |

**Deliberately NOT changed**: J/S sigmoid `1/(1 + 10^(-js/20))` in `ew/jamming.py` — standard dB power conversion (physics, not a tunable parameter).

### 26c: Engine Lifecycle (23 tests)

- **Puff cleanup**: `DispersalConfig.max_puff_age_s` (default 3600.0), `cleanup_aged_puffs()` method, wired in `CBRNEngine.update()`
- **Integration scan cap**: `DetectionConfig.max_integration_scans` (default 4), caps raw scan count before computing gain_db
- **Armor type**: `GroundUnit.armor_type: str = "RHA"` field with get_state/set_state (backward-compat), `UnitDefinition.armor_type`, passed through `create_unit()`
- **6 armor YAML files**: m1a1_abrams (COMPOSITE), m1a2 (COMPOSITE), shot_kal (RHA), t55a (RHA), t62 (RHA), t72m (COMPOSITE)

## Design Decisions

1. **Keyword-only `rng` via `*,`**: Instead of reordering parameters (which would break existing callers), used `*,` to make `rng` keyword-only. This allows it to appear after optional parameters while being required.

2. **Tests use `np.random.default_rng(0)` directly**: The exit criterion was zero `default_rng` in `stochastic_warfare/` source, not in tests. Tests can use any seed.

3. **Dict-based decoy matrix**: Replaced if/elif chain with nested dict lookup `matrix.get(int(decoy_type), {}).get(int(seeker_type), 0.0)`. More configurable, same behavior.

4. **Trench interpolation formula**: `t = (diff - along) / (crossing - along)` instead of hardcoded 30/60 — generalizes to any angle pair.

5. **Puff boundary condition**: `age_s < max_puff_age_s` (strict less-than) — puff at exactly max age is removed.

## Deficits Resolved

| Deficit | Description |
|---------|-------------|
| 5.6 | GPS spoofing unit_id="" hardcoded |
| 5.7 | Hardcoded EW magic numbers |
| 7.1 | Hardcoded terrain channeling thresholds |
| 7.2 | Hardcoded fallback weather defaults |
| 7.3 | No puff aging/cleanup |
| 8.1 | Hardcoded fallback RNG seed (42) |
| 8.2 | Gas wind direction tolerance hardcoded |
| 8.3 | Trench direction angles hardcoded |
| 8.4 | Foraging ambush rate hardcoded |
| 10.4 | Integration gain caps at 4 |
| 10.5 | Armor type YAML data missing |

## Known Limitations

None introduced. All changes are backward-compatible (config fields default to original hardcoded values).

## Lessons Learned

- **Keyword-only `*,` is the cleanest fix**: When a required param must follow optional ones, `*,` is better than reordering (preserves API surface) or adding a sentinel default (hides bugs).
- **Sub-engine construction chains matter**: Making `rng` required on DetectionEngine/StateEstimator cascades to FogOfWarManager/IntelFusionEngine which create those sub-engines internally. Must audit callers-of-callers.
- **12 test files needed updating**: Phase 26a had the highest test churn of any sub-phase. `AggregationEngine` alone appeared in 3 test files with ~50 total call sites.
- **Config field naming should match source code context**: `jamming_event_radius_m` vs `event_radius_km` — use the same unit (meters) as the source code to avoid conversion bugs.

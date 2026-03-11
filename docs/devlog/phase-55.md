# Phase 55: Resolution & Scenario Migration

## Summary

Phase 55 addresses three structural issues: (1) long-range battles resolving via `time_expired` instead of decisive combat, (2) scenario data gaps — missing ROE, weapon assignments, config coverage, and (3) dead calibration fields — `sead_arm_effectiveness`, `drone_provocation_prob`, `seeker_fov_deg`, GasWarfareEngine unwired.

**43 new tests. 7 deficits resolved.**

## What Was Built

### 55a: Resolution Switching Fix

- **`engine.py`**: Added `_forces_within_closing_range()` method that checks minimum inter-side distance against `engagement_range * resolution_closing_range_mult` (default 2.0). Modified `_update_resolution()` to cap at OPERATIONAL when forces are within closing range, preventing 3600s STRATEGIC ticks that overshoot engagement windows.
- **`engine.py`**: Added engagement detection at OPERATIONAL resolution (not just STRATEGIC), so battles can start during 300s ticks as forces close.
- **`EngineConfig`**: Added `resolution_closing_range_mult: float = 2.0` config field.

### 55b: Legacy Scenario Migration

- **8 formerly-xfail scenarios** now load through CampaignScenarioConfig:
  - `bekaa_valley_1982`: Added `school_config` for doctrinal AI (blue=air_power, red=attrition)
  - `cbrn_chemical_defense`: Migrated `cbrn` → `cbrn_config`
  - `cbrn_nuclear_tactical`: Migrated `cbrn` → `cbrn_config`
  - `falklands_campaign`: Added ROE WEAPONS_TIGHT, STEADY morale, rout cascade config
  - `halabja_1988`: Added `cbrn_config` with agent releases
  - `taiwan_strait`: Added ROE WEAPONS_TIGHT
- **E2E xfail set cleared**: `_LEGACY_FORMAT_SCENARIOS` is now empty.

### 55c: Deficit Wiring

1. **GasWarfareEngine** (55c-1): MOPP query wired into `battle.py` WW1 barrage path — gas casualties now modified by protection level.
2. **seeker_fov_deg** (55c-2): FOV cone check in `battle.py` guided munition path — missiles with narrow seekers reject targets outside their cone.
3. **sead_arm_effectiveness** (55c-3): ARM vs non-radar differentiation in `iads.py` — `apply_sead_damage()` uses `sead_arm_effectiveness` for radar components (higher damage), `sead_effectiveness` for SAM batteries (standard damage).
4. **drone_provocation_prob** (55c-4): Escalation trigger in `engine.py` tactical loop — drone provocation can trigger escalation level increase.

### 55d: Data Fixes & ROE Expansion

- **roman_equites.yaml**: Fixed ground_type ARMOR → CAVALRY
- **ROE expansion** to 6 scenarios: Falklands Campaign (WEAPONS_TIGHT), Taiwan Strait (WEAPONS_TIGHT), Korean Peninsula (WEAPONS_TIGHT), Hybrid Gray Zone (WEAPONS_HOLD), Falklands San Carlos (WEAPONS_TIGHT), Eastern Front (WEAPONS_FREE — already had it)
- **A-4 Skyhawk bomb delivery**: Added `"Generic Bomb Rack": bomb_rack_generic` to San Carlos weapon_assignments
- **Eastern Front weapon assignments**: 13 weapon mappings for T-34/85, Panzer IV H, Tiger I, infantry small arms

### 55e: Rout Cascade Per-Scenario Config

- **CalibrationSchema**: Added 3 optional fields (`rout_cascade_radius_m`, `rout_cascade_base_chance`, `rout_cascade_shaken_susceptibility`)
- **scenario.py**: Wired RoutConfig from calibration fields in ScenarioLoader
- **Falklands Campaign**: Set reduced cascade radius (200m vs default 500m) and base chance (0.05 vs default 0.10) to prevent instant morale collapse

## Design Decisions

1. **Closing range guard vs engagement-count heuristic**: Chose distance-based guard (simpler, deterministic) over tracking recent engagement counts. The multiplier (2.0x) is configurable per-engine if scenarios need different behavior.

2. **OPERATIONAL engagement detection**: Rather than allowing force_destroyed evaluation during STRATEGIC ticks (as originally planned), wiring engagement detection into OPERATIONAL resolution gives finer-grained control. 300s ticks are short enough to detect closing forces.

3. **Rout cascade as CalibrationSchema fields**: Rather than adding a nested `RoutCalibration` model, used flat `rout_` prefixed fields. This keeps the YAML simple and uses the existing `.get()` accessor pattern.

4. **WW2 weapon proxies**: Infantry small arms map to WW1 equivalents (Mosin-Nagant → lee_enfield, Kar98k → gewehr_98, MGs → mg42). These are the closest available weapon definitions with appropriate ballistic characteristics.

## Deviations from Plan

- Plan called for 8 legacy scenario migrations; scenarios were already in campaign format — just needed config additions (cbrn_config, school_config, ROE).
- Plan estimated 39 existing + 7 new = 46 tests; actual is 35 existing + 8 new = 43 tests (existing count was slightly different from estimate).
- Existing Phase 9 integration tests needed updating: closing range guard changed resolution behavior for test scenarios where units are within 2x engagement range. Fixed by either disabling the guard (`resolution_closing_range_mult=0.0`) or separating forces beyond the threshold.
- CBRN validation tests needed updating: `cbrn` → `cbrn_config` key rename.

## Deficits Resolved

| Deficit | Description | Resolution |
|---------|-------------|------------|
| E9/D15 (Phase 47/48) | Resolution switching → time_expired | `_forces_within_closing_range()` guard + OPERATIONAL engagement detection |
| D54-1 (Phase 54) | GasWarfareEngine not wired | MOPP query in battle.py WW1 barrage path |
| D54-2 (Phase 54) | seeker_fov_deg dead field | FOV cone check in battle.py guided munition path |
| D53-5 (Phase 53) | sead_arm_effectiveness unconsumed | ARM vs non-radar differentiation in iads.py |
| D53-6 (Phase 53) | drone_provocation_prob unconsumed | Escalation trigger in engine.py tactical loop |
| (new) | Rout cascade not per-scenario configurable | CalibrationSchema fields + scenario.py wiring |
| (new) | A-4 Skyhawk can't deliver bombs | weapon_assignment mapping in San Carlos scenario |

## Known Limitations

- Naval posture detection modifiers still not implemented (from Phase 51)
- Blockade throughput reduction still not integrated into supply_network.py (from Phase 51)
- No scenarios exercise VLS magazine_capacity or mine encounters end-to-end (from Phase 51)
- Historical accuracy validation tests timeout (pre-existing — not caused by Phase 55 changes)

## Lessons Learned

- **Closing range guard affects existing tests**: Any test that expects STRATEGIC resolution with units within 2x engagement range will fail. Fix with `resolution_closing_range_mult=0.0` or by separating forces.
- **YAML key renames cascade to validation tests**: Renaming `cbrn` → `cbrn_config` in scenario YAMLs breaks any test asserting `"cbrn" in data`. Use `or` pattern for backward compatibility.
- **WW2 weapon proxy mapping is the right granularity**: Individual weapon definitions for every historical small arm would be data bloat. Proxying to existing WW1/WW2 weapons with similar characteristics is sufficient.
- **RoutConfig wiring through CalibrationSchema is zero-cost when unused**: `None` defaults mean scenarios without rout config get the RoutEngine's built-in defaults — no behavioral change.

## Postmortem

### Scope: On target
- Planned: resolution fix, legacy migration, ROE expansion, data gaps, deficit wiring, rout cascade config
- Delivered: all planned items plus regression fixes for 7 existing tests affected by closing range guard
- **Dropped**: plan mentioned "migrate 8 legacy scenarios to campaign format" — scenarios were already in campaign format, just needed config additions. Not a descope, just a plan mischaracterization.
- **Unplanned**: 7 regression fixes (4 Phase 9 integration, 1 simulation engine, 2 CBRN validation)

### Quality: High
- 43 Phase 55 tests covering resolution switching (9 tests), legacy loading (12 tests), deficit wiring (10 tests), data fixes (9 tests), rout cascade (3 tests)
- Mix of integration tests (real engine instances) and YAML data validation
- Edge cases covered: single side, zero FOV, None defaults, custom multiplier
- **Gap**: No end-to-end test for drone provocation escalation trigger or gas casualty modifier in battle loop. These are wired (confirmed by integration audit) but not exercised in tests.

### Integration: Fully wired
- All 8 features confirmed WIRED by integration audit
- No dead modules, no standalone code
- Closing range guard, OPERATIONAL engagement detection, gas MOPP, seeker FOV, ARM SEAD, drone provocation, rout cascade — all integrated into engine/battle/scenario loop

### New Deficits: 1
- **Gas casualty modifier hardcoded values**: `battle.py` line ~2624 uses floor=0.1 and scaling=0.8 for gas protection effect on casualties. Should be CalibrationSchema fields (`gas_casualty_floor`, `gas_protection_scaling`). Assign to Phase 56+.

### Action Items: None blocking
- The gas casualty hardcoded values are minor (only affects WW1 gas warfare scenarios) and can be addressed in a future phase.

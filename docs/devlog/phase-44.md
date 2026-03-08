# Phase 44 — Environmental & Subsystem Integration

## Summary

Wired 30+ previously built-but-disconnected environment, CBRN, EW, GPS, logistics, and population engines into the battle loop. Zero new source files — all engines already existed. This is pure instantiation + query wiring.

## Sub-phases

### 44a: Weather & Night Effects (12 tests)
- **scenario.py**: Instantiate WeatherEngine, AstronomyEngine, TimeOfDayEngine, SeaStateEngine in `_create_engines()`. Parse `weather_conditions.precipitation` from scenario YAML. Merge `weather_conditions.visibility_m` into calibration when not explicitly overridden.
- **engine.py**: Fix weather engine call from `step(clock)` → `update(dt)` (the `hasattr(engine, "step")` guard silently skipped it). Same fix for SeaStateEngine (`update(dt_seconds)`). TimeOfDayEngine is query-only — removed per-tick call entirely.
- **battle.py**: Weather Pk modifier table (8 states, 0.55–1.0). Weather visibility caps detection range when worse than calibration. Night visual detection ×0.3, thermal sensors get +thermal_contrast bonus. Sea state Beaufort >4 increases naval target dispersion.

### 44b: CBRN/EW/Space Effects (9 tests)
- **battle.py**: CBRN MOPP detection degradation and fatigue penalty via `cbrn_engine.get_mopp_effects()`. EW jamming degrades radar detection quality via `ew_engine.compute_radar_snr_penalty()` (only for weather_independent sensors). GPS CEP factor degrades crew_skill for GPS-guided weapons via `gps_engine.compute_gps_accuracy()` + `compute_cep_factor()`.

### 44c: Logistics Engine Wiring (10 tests)
- **scenario.py**: Instantiate MedicalEngine and EngineeringEngine in `_create_engines()`. Add `medical_engine`, `engineering_engine` fields to SimulationContext. Add `maintenance_engine` to get_state/set_state (was missing).
- **engine.py**: Call `maintenance_engine.update(dt_hours, temperature_c, timestamp)` per tick, feeding weather temperature. Call `medical_engine.update(dt_hours, timestamp)` per tick.
- **battle.py**: Equipment readiness gate — readiness <0.3 skips engagement, 0.3–1.0 scales crew_skill (min 0.5).

### 44d: Population Engine Wiring (6 tests)
- **scenario.py**: Conditionally instantiate CivilianManager + CollateralEngine when `escalation_config` is present. Add `collateral_engine` field to SimulationContext.
- **engine.py**: Placeholder for collateral update in escalation cycle (CollateralEngine is event-driven via `record_damage()`, no per-tick update needed).

## Files Modified

| File | Changes |
|------|---------|
| `simulation/scenario.py` | `_parse_weather_state()` helper, env/med/eng/pop engine instantiation, clock parameter, get_state/set_state additions (~80 LOC) |
| `simulation/engine.py` | Fixed weather/sea_state update calls, added maintenance/medical updates, collateral placeholder (~40 LOC) |
| `simulation/battle.py` | Weather Pk table + modifier, night/thermal modifiers, sea state dispersion, CBRN MOPP, EW jamming, GPS CEP, readiness gate (~120 LOC) |
| 3 existing test files | Updated mocks for new weather/tod API (step→update, query-only) |

## New Test File

`tests/unit/test_phase44_env_subsystem.py` — 37 tests

## Key Decisions

1. **Weather modifiers computed once per tick**: Query weather/illumination/sea state outside the per-unit loop. These don't change within a single tick.
2. **Min of calibration vs weather visibility**: `visibility_m = min(calibration_vis, weather_vis)`. Scenarios with explicit `calibration_overrides.visibility_m` override weather; otherwise weather engine provides the value.
3. **Night detection = 0.3 (70% penalty)**: Conservative — night without NVG/thermal severely limits detection. Thermal sensors bypass via `_WEATHER_BYPASS_TYPES`. Thermal gets small bonus at night (+thermal_contrast × 0.3, capped at +0.2).
4. **EW jamming as detection quality degradation**: `detection_quality_mod *= ew_factor`. Cascades into vis_mod and ROE id_confidence.
5. **GPS CEP as crew_skill degradation**: No direct CEP parameter in `route_engagement()`, so degrade `crew_skill` as proxy.
6. **Engine update method fix**: `engine.py` used `hasattr(engine, "step")` guards that silently skipped engines whose method was named `update`. Fixed all environment engine calls.
7. **Readiness < 0.3 skips engagement**: Below 30% readiness, unit is combat-ineffective. Between 30-100%, readiness scales crew_skill (capped at 0.5 min).
8. **TimeOfDayEngine is query-only**: No per-tick update needed. Removed the call entirely rather than keeping a no-op.

## Descoped

- **Campaign-scale logistics**: TransportEngine, DisruptionEngine, NavalLogisticsEngine, NavalBasingEngine, PrisonerEngine. Deferred.
- **CommandEngine**: Requires HierarchyTree + TaskOrgManager setup. Complex instantiation. Deferred.
- **Population sub-engines**: DisplacementEngine, CivilianHumintEngine, InfluenceEngine. Deferred.
- **Strategic air/IADS**: AirCampaignEngine, IadsEngine, StrategicBombingEngine. Campaign-scale. Deferred.

## Known Limitations

- **Weather Pk modifier is simple table lookup**: Does not account for weapon type (e.g., guided missiles less affected by rain than visual-range weapons).
- **Night modifier is binary (day/night)**: No twilight gradation for visual sensors — twilight treated as night.
- **Maintenance readiness requires equipment registration**: Without explicit `register_equipment()` calls (not done in ScenarioLoader), `get_unit_readiness()` always returns 1.0. Full logistics wiring deferred.
- **Medical/engineering engines instantiated but have no scenario data**: No facilities/projects registered. They run per-tick but produce no effects until scenario YAML includes medical/engineering data.

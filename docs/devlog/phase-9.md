# Phase 9: Simulation Orchestration — Devlog

## Summary

Phase 9 implements the top-level simulation orchestrator — the master loop that ties all 8 prior phases into coherent multi-scale campaign simulations. This is the first time the simulation can run end-to-end: scenario load → environment evolving → AI commanders deciding → orders propagating → units moving → detection → combat → morale → logistics → victory evaluation.

**Test count**: 372 new tests (3,586 total: 3,214 prior + 372 Phase 9)
**Source files**: 8 modules in `stochastic_warfare/simulation/`
**YAML data**: 4 new campaign scenario files
**Dependencies**: None new

## What Was Built

### Source Modules (8 files)

| Module | Purpose | Tests |
|--------|---------|-------|
| `simulation/__init__.py` | Package init | — |
| `simulation/scenario.py` | Pydantic campaign YAML schema, SimulationContext, ScenarioLoader | 78 |
| `simulation/victory.py` | VictoryEvaluator with 5 condition types, ObjectiveState tracking | 55 |
| `simulation/recorder.py` | SimulationRecorder subscribing to EventBus, state snapshots | 37 |
| `simulation/metrics.py` | CampaignMetrics static analysis (time series, summaries) | 35 |
| `simulation/battle.py` | BattleManager: tactical loop, engagement detection, deferred damage | 42 |
| `simulation/campaign.py` | CampaignManager: strategic ticks, reinforcements, supply | 23 |
| `simulation/engine.py` | SimulationEngine: master loop, resolution switching, checkpoint | 62 |

### Integration Tests
- `tests/integration/test_phase9_integration.py` — 40 tests covering full end-to-end scenarios

### YAML Scenario Files (4 new)
| File | Purpose |
|------|---------|
| `data/scenarios/test_campaign/scenario.yaml` | Minimal: 2 sides, 1 objective, 24h |
| `data/scenarios/test_campaign_multi/scenario.yaml` | Multiple engagement points, 2 objectives, 48h |
| `data/scenarios/test_campaign_reinforce/scenario.yaml` | 3 reinforcement waves, 24h |
| `data/scenarios/test_campaign_logistics/scenario.yaml` | Supply chain emphasis, multiple depots, 72h |

### Performance Optimizations
- **LOS result caching**: Per-tick cache in `terrain/los.py` keyed on `(obs_row, obs_col, tgt_row, tgt_col, obs_height_cm, tgt_height_cm)`. Cleared at tick start via `clear_los_cache()`.
- **Pathfinding threat cost caching**: Per-`find_path()` call threat cost cache complements existing terrain difficulty cache.
- **Engine integration**: LOS cache cleared at start of each tick in `SimulationEngine.step()`.

## Design Decisions

### DD-1: No New ModuleId Value
Same reasoning as Phases 7-8. `RNGManager._initialize()` spawns `len(ModuleId)` child SeedSequences. Adding values changes spawn count, breaking deterministic replay. The orchestrator coordinates; domain modules provide randomness. Campaign manager reuses `ModuleId.CORE`.

### DD-2: Shared SimulationContext (No Sub-Simulation)
No sub-simulation spawn. The engine shares one master clock and switches tick resolution. Data flows through the shared `SimulationContext` — no boundary serialization needed. This keeps deterministic replay simple and avoids RNG stream splitting complexity.

### DD-3: Tick Resolution via Clock
`TickResolution` enum (STRATEGIC/OPERATIONAL/TACTICAL) with automatic switching:
- STRATEGIC (3600s): No forces in contact
- OPERATIONAL (300s): Transitional after battle concludes
- TACTICAL (5s): Active engagements in progress

Switching is automatic based on `BattleManager.active_battles`.

### DD-4: ScenarioLoader Reuses Phase 7 Patterns
`ScenarioLoader` delegates force building and weapon/sensor assignment to existing `validation/scenario_runner.py` functions (`build_terrain`, `build_forces`, `_assign_weapons`, `_assign_sensors`). This avoids duplicating complex wiring logic.

### DD-5: No Domain Logic in simulation/
Strictly enforced. `simulation/` contains only: sequencing (which module updates in what order), data routing (passing outputs from one module as inputs to the next), resolution management, and state collection.

### DD-6: Recorder Subscribes to Event Base Class
MRO dispatch ensures all event subtypes are captured. Recording is always on during a run; filtering is post-processing.

### DD-7: Fixed Reinforcement Schedule
Scenario YAML defines exact arrival times. The campaign manager checks the schedule each tick and spawns arriving units via `UnitLoader`. Poisson random arrivals deferred.

## Deviations from Plan

1. **Test counts differ from plan estimates**: Plan estimated ~370 tests, achieved 372. Close match.
2. **LOSEngine wired into SimulationContext**: Performance optimization agent added `los_engine` field to SimulationContext and wired it in ScenarioLoader — not in original plan but essential for LOS caching integration.
3. **Viewshed vectorization deferred**: Plan marked this as lower priority; confirmed as such during implementation.
4. **STRtree still deferred**: Infrastructure spatial queries continue using brute-force. Profile data needed to justify complexity.
5. **Force aggregation/disaggregation deferred**: Original development-phases.md scope included this. Not attempted — all units remain at individual resolution. Documented as known limitation #1.
6. **Multi-scale spatial transitions deferred**: Original scope mentioned strategic graph ↔ tactical grid ↔ unit continuous transitions. Implementation uses temporal resolution switching (tick duration) only, not spatial scale transitions. The single shared `SimulationContext` operates at one spatial resolution.
7. **Campaign loop profiling deferred**: Full cProfile-based optimization deferred to Phase 10 when real campaign scenarios provide meaningful workloads.

## Issues & Fixes

1. **Heightmap.data private attribute**: Tests referenced `hm.data.shape` but Heightmap stores data as `_data`. Fixed by using `hm.shape` (public property).
2. **ScenarioRunner import in _create_engines**: Referenced `ScenarioRunner._build_morale_config()` without importing. Fixed with local import.
3. **1-hour campaign with 3600s tick**: Test `step_returns_false_when_not_over` failed because first tick reached time limit. Fixed by using 24-hour campaign.

## Known Limitations / Post-MVP Refinements

1. **No force aggregation/disaggregation** — all units at individual resolution, no strategic "force blobs"
2. **Single-threaded simulation loop** — required for deterministic PRNG replay
3. **No auto-resolve option** — every engagement runs full tactical resolution
4. **Simplified strategic movement** — units move without detailed operational pathfinding
5. **Fixed reinforcement schedule** — no Poisson/stochastic arrivals
6. **No naval campaign management** — structurally supported but not tested with naval scenarios
7. **Synthetic terrain only** — programmatic heightmaps, not real topographic data
8. **LOS cache is per-tick only** — cleared each tick after movement, no multi-tick memoization
9. **No weather evolution mid-campaign** beyond what `WeatherEngine.step()` provides when wired
10. **Viewshed vectorization deferred** — lower priority per plan
11. **STRtree for infrastructure spatial queries still deferred** — waiting for profiling data

## Lessons Learned

- **ScenarioLoader is the most complex single function**: Wiring 11 domain modules requires careful import ordering and parameter threading. Reusing Phase 7 patterns (`build_forces`, `build_terrain`) prevented significant duplication.
- **Resolution switching is simple once clock supports it**: `SimulationClock.set_tick_duration()` was already in Phase 0. The engine just calls it when battle state changes.
- **Mock contexts are essential for fast unit tests**: Full `ScenarioLoader.load()` takes ~0.5s (YAML parsing, terrain generation). Mock `SimulationContext` with only needed fields makes engine tests run in <0.3s total.
- **Deferred damage pattern carries forward**: Battle manager's tactical loop reuses the same deferred damage pattern from Phase 7's scenario runner.
- **Victory evaluator must update objectives before checking conditions**: Calling `update_objective_control()` before `evaluate()` ensures territory control reflects current unit positions.
- **Per-tick LOS caching requires engine integration**: The cache must be cleared at tick start (after movement), which means the engine must know about the LOS engine — added `los_engine` field to SimulationContext.
- **Background agents work well for independent tasks**: Integration tests and performance optimization ran in parallel with no conflicts.

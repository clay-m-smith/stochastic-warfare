# Phase 10: Full Campaign Validation & Backtesting

## Summary

Phase 10 validates the complete simulation engine at campaign scale against documented historical outcomes. Unlike Phase 7 (which validated individual engagements with pre-scripted behavior), Phase 10 runs multi-day campaigns with AI commanders, logistics, C2, reinforcements — all 11 domain modules interacting through the Phase 9 `SimulationEngine`.

Two historical campaigns validated:
1. **Golan Heights (Oct 6-10, 1973)** — 4-day land campaign with Israeli defense → reinforcement → counterattack
2. **Falklands San Carlos (May 21-25, 1982)** — 5-day naval air defense campaign with Argentine air raids

Test count: 196 new tests. Running total: 3,782 tests.

## What Was Built

### New Source Modules (5)
| Module | Purpose |
|--------|---------|
| `validation/campaign_data.py` | `HistoricalCampaign` model + `AIExpectation` + `CampaignDataLoader` |
| `validation/campaign_runner.py` | `CampaignRunner` wrapping `ScenarioLoader` + `SimulationEngine` |
| `validation/campaign_metrics.py` | Campaign-level metric extraction (`CampaignValidationMetrics`) |
| `validation/ai_validation.py` | AI decision quality analysis (`AIDecisionValidator`) |
| `validation/performance.py` | cProfile + tracemalloc profiling (`PerformanceProfiler`) |

### Modified Source Files (2)
| File | Change |
|------|--------|
| `validation/monte_carlo.py` | Added `CampaignMonteCarloHarness` + `_run_campaign_iteration()` |
| `validation/__init__.py` | Updated docstring to cover campaign validation |

### New YAML Scenario Files (2)
| File | Scenario |
|------|----------|
| `data/scenarios/golan_campaign/scenario.yaml` | 4-day Golan Heights campaign |
| `data/scenarios/falklands_campaign/scenario.yaml` | 5-day Falklands San Carlos campaign |

### New Test Files (9)
| File | Tests |
|------|-------|
| `tests/validation/test_campaign_data.py` | 33 |
| `tests/validation/test_campaign_runner.py` | 26 |
| `tests/validation/test_campaign_metrics.py` | 32 |
| `tests/validation/test_campaign_mc.py` | 10 |
| `tests/validation/test_ai_validation.py` | 31 |
| `tests/validation/test_performance.py` | 10 |
| `tests/validation/test_golan_campaign.py` | 24 (+5 slow) |
| `tests/validation/test_falklands_campaign.py` | 21 (+2 slow) |
| `tests/integration/test_phase10_integration.py` | 9 |
| `tests/validation/test_campaign_performance.py` | 0 (+10 slow) |

## Design Decisions

### DD-1: HistoricalCampaign wraps CampaignScenarioConfig fields
Mirrors the Phase 7 pattern where `HistoricalEngagement` wraps engagement fields plus `documented_outcomes`. `CampaignDataLoader.to_scenario_config()` strips validation-only fields and produces a config suitable for `ScenarioLoader.load()`.

### DD-2: CampaignRunner wraps ScenarioLoader + SimulationEngine
Single `run()` call: converts HistoricalCampaign → temp YAML → ScenarioLoader.load() → SimulationEngine.run() → CampaignRunResult. All domain wiring stays in ScenarioLoader (DRY).

### DD-3: Separate campaign_metrics.py
Campaign metrics (units destroyed, exchange ratio, campaign duration, territory control) are distinct from engagement metrics. Follows the same static-method design as `EngagementMetrics`.

### DD-4: CampaignMonteCarloHarness extends monte_carlo.py
Reuses `MonteCarloConfig`, `RunResult`, `MonteCarloResult`, `ComparisonReport`. `_run_campaign_iteration()` is a top-level picklable function (same pattern as `_run_single_iteration()`).

### DD-5: AI decision validation via recorder events
`AIDecisionValidator` scans `RecordedEvent` entries for AI event types (OODAPhaseChangeEvent, DecisionMadeEvent, etc.) and matches actions against expected postures with configurable tolerance.

### DD-6: Two historical campaigns (Golan + Falklands)
Covers land and naval domains. Golan tests reinforcements, defense→offense transition, morale cascade. Falklands tests naval C2, air defense, multiple engagement waves.

### DD-7: Wider tolerances for campaign-level comparison
Default `tolerance_factor=3.0` for campaign documented_outcomes vs 2.0 for engagement-level.

## Deviations from Plan

- Test count came in at 196 vs planned ~290. The plan over-estimated per-module test counts; actual tests are more focused and avoid redundancy.
- No separate `test_campaign_performance.py` non-slow tests — all performance tests are `@pytest.mark.slow` as they require real campaign runs.
- The integration test `test_reasonable_historical_passes` needed adjustment: with `max_ticks=10`, campaign duration is ~3600s, requiring a historical value of 3600 (not 86400) for the tolerance test.

## Known Limitations / Post-MVP Refinements

| Severity | Limitation |
|----------|------------|
| MAJOR | No fire rate limiting — units fire once per tick regardless of ROF (inherited from Phase 7) |
| MAJOR | No wave attack modeling — all red units advance simultaneously (inherited from Phase 7) |
| MAJOR | Campaign AI decisions are coarse — OODA cycle operates at echelon timing scales, may not produce tactical-level posture changes within short MC runs |
| MINOR | Simplified force compositions — representative unit samples, not complete historical OOB |
| MINOR | Synthetic terrain — programmatic heightmaps, not real topographic data |
| MINOR | Fixed reinforcement schedule — deterministic arrival times, no stochastic variation |
| MINOR | No force aggregation/disaggregation — all units individually tracked (performance concern for large campaigns) |
| MINOR | AI expectation matching is approximate — posture detection based on action string matching, not deep behavioral analysis |
| MINOR | Campaign metrics proxy territory control via unit survival fraction rather than spatial objective control |
| COSMETIC | `_decide_brigade_div` hardcodes `echelon_level=9` in result (inherited from Phase 8) |

## Lessons Learned

- **CampaignRunner temp YAML pattern works well**: Writing a temp YAML for ScenarioLoader avoids building a separate config→context path. The overhead is negligible.
- **Small tick limits (max_ticks=5-20) make fast unit tests possible**: Campaign tests complete in <0.5s by limiting ticks while still exercising the full wiring.
- **Monte Carlo at campaign level reuses all engagement MC infrastructure**: `MonteCarloResult.compare_to_historical()` works unchanged because both harnesses produce `RunResult` with `dict[str, float]` metrics.
- **AI decision extraction depends on event generation**: With very few ticks, AI modules may not complete an OODA cycle, producing zero decisions. Tests must account for this.
- **Tolerance factor of 3.0 is essential for campaign-level comparison**: Multi-day campaigns with AI commander variability and stochastic reinforcement effects produce wide outcome distributions.

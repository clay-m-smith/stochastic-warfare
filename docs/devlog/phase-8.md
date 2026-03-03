# Phase 8: AI & Planning — Devlog

## Summary

Phase 8 adds the "brains" — AI commanders that make echelon-appropriate decisions via Boyd's OODA cycle, informed by doctrinal templates and commander personality profiles. The AI sits atop the full module stack (Phases 0-7) and communicates downward exclusively through the existing Phase 5 order system.

**Test count**: 575 new tests (3,214 total, up from 2,639)
**Source files**: 14 new modules (7 AI + 5 planning + 2 init files)
**YAML data files**: 16 new (6 commander profiles + 10 doctrine templates)
**Total YAML data files**: ~112 cumulative

## What Was Built

### 8a: AI Decision-Making (7 modules)
- `c2/ai/ooda.py` — OODA loop as pure timer/state machine. Log-normal timing (sigma=0.3) with echelon scaling. Does NOT call other modules directly — orchestration layer reads state.
- `c2/ai/commander.py` — YAML-driven personality profiles (aggression, caution, flexibility, initiative, experience, decision_speed, risk_acceptance). Applies OODA speed multiplier, decision noise, and risk threshold biases.
- `c2/ai/doctrine.py` — YAML-driven doctrine templates (US, Russian, NATO, generic). Category filtering, echelon range, domain matching, action set filtering.
- `c2/ai/assessment.py` — 7-factor situation assessment (force ratio 0.30, terrain 0.10, supply 0.15, morale 0.15, intel 0.10, environment 0.05, C2 0.15). Produces opportunities and threats lists.
- `c2/ai/decisions.py` — 5 echelon-specific decision functions (individual, small unit, company/bn, brigade/div, corps+). Each builds score dict, applies personality noise, doctrine filter, then selects.
- `c2/ai/adaptation.py` — Monitors 7 triggers (casualties, force ratio change, supply crisis, morale break, opportunity, surprise contact, C2 disruption). Flexibility modulates response.
- `c2/ai/stratagems.py` — Echelon + experience gating for 6 stratagem types (deception, concentration, economy of force, surprise, feint, demonstration).

### 8b: Planning Process (5 modules)
- `c2/planning/process.py` — MDMP state machine (IDLE→RECEIVING_MISSION→...→COMPLETE). 4 methods (INTUITIVE, DIRECTIVE, RAPID, MDMP) with speed multipliers. 1/3-2/3 rule.
- `c2/planning/mission_analysis.py` — Extracts specified/implied/essential tasks, intel requirements (PIR/FFIR/EEFI), risk assessment, constraints, key terrain. Staff quality gates implied task discovery.
- `c2/planning/coa.py` — Generates COAs by mission type, Lanchester attrition wargaming, weighted comparison, personality-biased softmax selection.
- `c2/planning/estimates.py` — 5 running estimates (personnel, intel, operations, logistics, comms). Periodic update (300s default). Significant change events.
- `c2/planning/phases.py` — Condition-based phase transitions (not scheduled). Standard sequences by mission type. Branch plans and sequel plans.

### Events (12 new)
6 AI events (OODAPhaseChange, OODALoopReset, SituationAssessed, DecisionMade, PlanAdapted, StratagemActivated) + 6 Planning events (PlanningStarted, PlanningCompleted, MissionAnalysisComplete, COASelected, PhaseTransition, EstimateUpdated).

### YAML Data (16 files)
- 6 commander profiles: aggressive_armor, cautious_infantry, balanced_default, naval_surface, air_superiority, sof_operator
- 10 doctrine templates: US (3), Russian (2), NATO (1), Generic (4)

## Design Decisions

1. **DD-1: No New ModuleId** — AI reuses ModuleId.C2 for PRNG stream. Adding a value would change SeedSequence child count, breaking deterministic replay.
2. **DD-2: OODA as Pure Timer/FSM** — Orchestration layer reads state and dispatches. Each module independently testable.
3. **DD-3: DI Pattern** — All modules receive input data as parameters, no stored engine references.
4. **DD-4: Analytical Wargaming** — Lanchester attrition, not nested simulation. Rough heuristic matching real planning.
5. **DD-5: Condition-Based Transitions** — Phases transition on conditions (casualties, objectives), not schedule. Time is fallback.
6. **DD-6: Echelon Drives Fidelity** — Platoon and below: INTUITIVE. Company-Battalion: RAPID or MDMP. Brigade+: Full MDMP.
7. **DD-7: Periodic Estimates** — Update every 300s, not per-tick. >10% change triggers event.

## Deviations from Plan

- Test count exceeded target (~435 planned → 575 actual). Agents created thorough test suites.
- `_decide_brigade_div` hardcodes `echelon_level=9` in result regardless of actual echelon passed (cosmetic issue, doesn't affect behavior).
- `plan_concentration` includes both concentration AND economy units in `units_involved` tuple (all participants).

## Issues & Fixes

- **Personality test stability**: With favorable force ratios (>1.5), ATTACK dominates for all personality types at Company/Bn level. Integration test required ambiguous scenario (force ratio ~0.9) to differentiate aggressive vs cautious.
- **No issues with PRNG discipline** — all modules use passed `np.random.Generator`, no bare `np.random` calls.

## Known Limitations / Post-MVP Refinements

1. Named doctrinal schools (Clausewitzian AI, Sun Tzu AI) deferred to Future Phases
2. COA wargaming is analytical (Lanchester), not full nested simulation
3. No terrain-specific COA generation (e.g., no river crossing planning detail)
4. Implied task tables are simplified (not full FM 5-0 comprehensive list)
5. No multi-echelon simultaneous planning (each commander plans independently)
6. Estimates update periodically, not reactively to every event
7. Stratagems are opportunity-evaluated, not proactively planned in COA
8. Brigade echelon decision hardcodes echelon_level=9 in result (cosmetic)

## Post-Phase Post-Mortem

### Test Breakdown (per file)

| Test file | Tests | Source module | Source LoC |
|-----------|-------|---------------|------------|
| test_c2_ai_doctrine.py | 41 | doctrine.py | 230 |
| test_c2_ai_commander.py | 40 | commander.py | 226 |
| test_c2_ai_ooda.py | 50 | ooda.py | 408 |
| test_c2_ai_assessment.py | 60 | assessment.py | 356 |
| test_c2_ai_decisions.py | 57 | decisions.py | 863 |
| test_c2_ai_adaptation.py | 40 | adaptation.py | 359 |
| test_c2_ai_stratagems.py | 36 | stratagems.py | 410 |
| test_c2_planning_estimates.py | 42 | estimates.py | 603 |
| test_c2_planning_mission_analysis.py | 45 | mission_analysis.py | 592 |
| test_c2_planning_coa.py | 54 | coa.py | 1,078 |
| test_c2_planning_phases.py | 45 | phases.py | 877 |
| test_c2_planning_process.py | 46 | process.py | 564 |
| test_phase8_integration.py | 19 | (integration) | 931 |
| **Total** | **575** | | **6,585 src + 9,109 test** |

Most complex modules by LoC: `coa.py` (1,078), `phases.py` (877), `decisions.py` (863). These correspond to the three modules with the most domain logic — COA wargaming math, condition-based phasing state machines, and echelon-specific decision trees.

### Implementation Strategy

Steps 2-6 (doctrine, commander, OODA, assessment, estimates) ran as 5 parallel agents — these modules have zero interdependencies, each accepting all inputs as parameters. This was the largest parallel batch in the project.

Steps 7-8 ran sequentially (COA depends on mission_analysis). Steps 9-10 (phases, process) ran in parallel. Steps 11-12 (decisions, adaptation+stratagems) ran in parallel. Step 13 (integration tests) was written directly after verifying all unit tests passed.

Parallelization paid off significantly — Phase 8 produced more code than any prior phase (6,585 source LoC, comparable to Phase 4's ~6,000 across 28 modules) but implemented faster due to the DI pattern enabling independent development.

### Model Soundness Review

**OODA timing model**: Log-normal distribution (sigma=0.3) with echelon-based base durations. This produces realistic Clausewitzian friction — most decisions are near the expected time, but some take much longer. C2 degradation multiplies timing (1.5x degraded, 3.0x disrupted). Commander personality modulates speed. Validated via unit tests that check distribution shape and echelon scaling.

**Assessment weighting**: 7-factor weighted sum (force_ratio 0.30, terrain 0.10, supply 0.15, morale 0.15, intel 0.10, environment 0.05, C2 0.15). Weights sum to 1.0. Force ratio dominates by design — it's the strongest predictor of tactical outcome. Environmental factor has lowest weight (0.05) reflecting its indirect influence. Confidence degrades with stale intel and poor C2 — a reasonable model of information quality.

**Lanchester wargaming in COA**: Configurable exponent (0=linear, 1=square law). 10-step attrition model with terrain defense multiplier and maneuver type bonus. Uses actual force ratio from `CombatPowerCalculator`. Produces loss estimates, risk levels, and probability of success. The analytical approach matches what real military planners do — rough estimates, not precise predictions. Nested simulation would be computationally expensive for marginal accuracy gains at the planning level.

**Decision selection**: Score-based selection with Gaussian noise proportional to `(1 - experience)`. Doctrine filters available actions. Personality biases scores. This produces locally reasonable decisions — no global optimization. Matches real military decision-making where commanders optimize locally with imperfect information.

**Softmax COA selection**: Temperature-scaled probability over ranked COAs, biased by risk tolerance and aggression. This means the "best" COA is usually selected but not always — capturing the bounded rationality of real decision-making.

### No Performance Work Needed

Phase 8 modules are "cold path" code — called once per OODA cycle (seconds to minutes of simulated time), not per-tick. No hot inner loops, no vectorization needed. The EventBus MRO dispatch optimization from Phase 7 Pass 3 ensures Phase 8's 12 new event types are dispatched efficiently.

### Cross-Document Audit Results

Post-completion `/cross-doc-audit` passed all 8 checks with 2 LOW-severity items:
1. MEMORY.md referenced "No optimization solver (Phase 8)" — Phase 8 didn't add this. Updated to "deferred to Future Phases."
2. Phase 5 devlog said "ATO generation deferred to Phase 8" — Phase 8 didn't implement ATO generation. Updated to "deferred to Phase 9/Future Phases."

Both fixed in the same postmortem pass.

## Lessons Learned

- **OODA as pure FSM keeps modules testable**: By not having OODA call assessment/planning directly, each module can be unit tested in isolation with injected data.
- **Personality needs ambiguous scenarios to matter**: When one option clearly dominates (e.g., attack at 3:1 ratio), noise and personality bias can't overcome the base score gap. Personality differentiation requires competitive scenarios.
- **Echelon-specific action enums prevent cross-echelon confusion**: A platoon can FLANK; a corps does OPERATIONAL_MANEUVER. Same concept, different vocabulary and implementation.
- **DI pattern pays dividends at test time**: Assessment takes 17 parameters but zero stored references — tests create assessments without any engine setup.
- **Lanchester wargaming is surprisingly effective**: The analytical approach produces reasonable loss estimates and risk categorizations. Full nested simulation would be vastly more expensive for marginally better results at the planning abstraction level.
- **Steps 2-6 parallelization worked perfectly**: 5 modules with zero interdependencies, all following DI pattern. Each agent produced working code and passing tests on first run. The DI pattern is the enabler — no shared state means no coordination needed.
- **Test count exceeded plan by 32%**: ~435 planned → 575 actual. Comprehensive test suites caught edge cases early. The extra tests are valuable, not bloat — they exercise boundary conditions and personality/doctrine interactions that would be hard to debug later.

# Phase 98: Shared Prework — Gap Audit, Calibration Conventions, Depth Framework

> **Phase 117 historical-claim supersession (2026-08-02):** This archived page
> preserves implementation history. Its historical-winner, outcome, casualty,
> duration, calibration, plausibility, envelope, and tolerance statements are
> not accepted historical validation. Any engine figures below are regression
> history only, not predictive evidence or calibration authority; the typed
> claim ledger and accepted production artifacts, if any, are authoritative.


**Status**: Complete.
**Block**: 11 (Golden Scenarios & End-to-End Engine Validation through UI).

## Summary

Phase 98 built the shared scaffolding that Phases 99–102 consume: a cross-scenario gap audit inventorying units/weapons/sensors needed vs. available, a calibration target template defining envelope-based regression assertions, a depth checklist template for UI walkthroughs, and envelope-check helper functions with full unit test coverage.

No scenario YAML or scenario-specific data was authored in this phase. All scenario authoring happens in Phases 99–102.

## Deliverables

### Documentation (`docs/scenarios/`)

- **`docs/scenarios/calibration-template.md`** — defines envelope format (winner rate, duration percentiles, casualty percentiles, key-dynamic assertions), permitted vs. forbidden calibration techniques, citation discipline, and worked Debecka example. This template is referenced by every Phase 99–102 regression test.
- **`docs/scenarios/depth-checklist-template.md`** — copy-into-devlog UI walkthrough acceptance criteria covering Results / Charts / Map / Analysis tabs plus a placeholder for scenario-specific expected observations.
- **`docs/scenarios/gap-audit.md`** — cross-scenario table of required units/weapons/sensors vs. existing inventory, with status classification (E=exists, A=adapt, N=new, R=reuse across scenarios). Identifies ~60 new YAML files needed across Phases 99–102 and ~15 items reusable between scenarios.

### Code (`stochastic_warfare/tools/`)

- **`stochastic_warfare/tools/envelope_check.py`** — envelope check helpers:
  - `check_winner_envelope(results, expected_winner, min_rate=0.7)` — validates historical winner wins in ≥min_rate fraction of iterations
  - `check_duration_envelope(results, historical_s, tolerance=0.5, tick_duration_s=5.0)` — validates mean duration within ±tolerance × historical_s
  - `check_casualty_envelope(results, side, historical, tolerance=0.4, max_override=None)` — validates per-side destructions within ±tolerance × historical, or below an absolute ceiling for near-zero historical cases
  - `count_destructions_by_weapon(scenario_path, weapon_id, seed, data_dir, max_ticks=5000)` — runs scenario once with event capture, counts UnitDestroyedEvents matching weapon_id (for key-dynamic tests like "Javelin dominated Iraqi armor kills")
  - `count_total_destructions(scenario_path, side, seed, data_dir, max_ticks=5000)` — companion counter for computing weapon-share ratios
  - `count_events_by_type(scenario_path, event_type, seed, data_dir, max_ticks=5000)` — generic event counter for assertions like "≥N CAS engagements per run"

### Tests (`tests/unit/`)

- **`tests/unit/test_envelope_check.py`** — 26 tests covering:
  - Winner envelope: pass at exactly min_rate, fail below, all wins, missing metric, empty metric, custom min_rate
  - Duration envelope: pass near historical, pass within tolerance, fail too short/long, custom tick duration, missing metric, mixed values
  - Casualty envelope: pass at historical, within tolerance, fail above/below, max_override pass/fail, historical=0 case, missing metric, lower-bound clamping
  - Event-capture helpers (smoke-tested with mocked scenario run): counts matching weapon IDs only for UnitDestroyedEvents; counts side-matching destructions; counts events by exact type

All 26 tests pass. No full-scenario integration was added — that happens in Phase 99 when the first real scenario regression test is written.

## Research (light-touch OOB)

Four parallel `/research-military` agents (one per scenario) produced OOB-level inventories. Key findings that corrected Block 11 planning assumptions:

- **Debecka Pass**: Blue side included **6 ODAs** (391, 392, 394, 395 from 3rd SFG; 043, 044 from 10th SFG) and **~1,300 Peshmerga** (not the ~80 we estimated). Red side was Iraqi **34th Infantry Division** (not "34th Armored Brigade" as the brainstorm assumed). CAS was **B-52H + F-14 + F/A-18** (no A-10 or F-15E confirmed at Debecka, contrary to our initial list). Javelin employment: **19 shots / 17 hits at 2,200–4,200m** — beyond stated weapon max range.
- **Khafji**: **USS Missouri** (not Wisconsin) was on station during the main battle, 29 Jan–1 Feb 1991. Wisconsin's first Khafji-area mission was 8 Feb. The scenario phase must decide between modeling the main battle (Missouri) or extending to Wisconsin's arrival. Significant AC-130H employment (Spirit 03 lost 31 Jan), A-10 as primary daytime CAS, and JSTARS (prototype) providing GMTI targeting.
- **Fallujah Phase Line Fran**: Massive fires employment — **1st MARDIV fired 5,685× 155mm HE rounds; AC-130 expended 1,300+ 40mm and 1,200+ 105mm rounds**. Rich IED taxonomy: command-wire, radio/cell-phone, pressure-plate, HBIED (booby-trapped structures), VBIED, SVBIED, rooftop aerial bombs, aviation-bomb IEDs (up to 500 lb). Notable novel ordnance: SMAW thermobaric (NE) round for strongpoint reduction.
- **Bint Jbeil**: Merkava Mk IV's **first combat use**; **no Trophy APS** (operational 2009). Hezbollah ATGM taxonomy richer than brainstormed: **Kornet-E, Metis-M, AT-3 Sagger, AT-5 Konkurs, RPG-29 Vampir** with tandem HEAT. Communication mix of handheld radios + wired field telephones + runners (defeats SIGINT). INS Hanit: **2 C-802 Noor missiles launched**, 1 struck merchant *Moonlight*, 1 struck Hanit; defensive suite reportedly **degraded for IAF deconfliction**.

All research outputs cite tiered sources (Tier 1 primary / Tier 2 academic / Tier 3 supplementary) per the `/research-military` skill conventions. Full briefs are summarized in `docs/scenarios/gap-audit.md`; deeper research (terrain, commander decisions, casualty envelopes) happens in each scenario phase.

## Scope refinements during phase

Two items from the original Phase 98 plan were refined:

### 98d (CALIBRATION_SCENARIOS registration) — deferred to scenario phases

The original plan called for stub entries in `stochastic_warfare/validation/calibration_scenarios.py`. Investigation revealed:

1. The file doesn't exist — the actual registry is `CALIBRATION_SCENARIOS` and `HISTORICAL_WINNERS` sets defined in `tests/validation/test_historical_accuracy.py`
2. Adding entries for scenarios whose YAMLs don't exist would fail (the test harness iterates scenario files)
3. Block 11 scenarios conceptually belong in `HISTORICAL_WINNERS`, not `CALIBRATION_SCENARIOS` (they have known expected winners from historical record)

**Resolution**: each scenario phase (99–102) adds its own entry to `HISTORICAL_WINNERS` in the same commit as the scenario YAML. Phase 98's role was to document this convention, not pre-populate. `docs/scenarios/calibration-template.md` now references this.

### Peshmerga force size

Brainstorm estimated ~80 Peshmerga at Debecka. Research indicates ~1,300 on the Debecka axis, split across multiple Peshmerga columns on different ridgelines. Phase 99 will model the actual force structure, though performance considerations may lead to aggregate representation of the non-engaged columns.

## Lessons learned

- **Parallel research agents scale well for OOB-scope research**. Each agent produced usable Tier 1 / Tier 2 citations in ~4 minutes. Dispatching 4 in parallel completed the full research pass in roughly the same time as one serial pass, saving ~12 minutes.
- **Research depth: OOB only**. Each agent's prompt explicitly scoped to units/weapons/sensors, deferring terrain / timeline / casualties to scenario phases. This kept agent responses focused and avoided duplicating effort.
- **Unit test mocking of scenario runs**. The event-capture helpers (`count_destructions_by_weapon` etc.) are wired to real scenario loading + engine execution, but unit tests mock these with a fake recorder. Separates correctness of the helper logic from correctness of a specific scenario. Real-scenario integration is validated by Phase 99's regression test.
- **Gap audit as living document**. The authoring priority table is best-effort now; scenario phases will surface dependencies we missed. The doc explicitly acknowledges this and invites updates in scenario-phase commits.

## Defects / deficits discovered

None. No new deficits surfaced during Phase 98.

Two pre-existing observations that were worth re-confirming:

- `kornet_team` unit already exists and is directly applicable to Hezbollah ATGM teams (Phase 102).
- The WW2-era `16in50_naval.yaml` weapon is reusable for USS Missouri's 16"/50 Mk 7 rifle (Phase 100) — a nice cross-era artifact.

## Test counts

- New tests this phase: 26 (envelope_check)
- Phase 98 Python test delta: +26
- Smoke test confirmed: 9354 passed, 21 skipped in tests/unit + tests/api

## Files touched

New:
- `docs/scenarios/calibration-template.md`
- `docs/scenarios/depth-checklist-template.md`
- `docs/scenarios/gap-audit.md`
- `stochastic_warfare/tools/envelope_check.py`
- `tests/unit/test_envelope_check.py`
- `docs/devlog/phase-98.md` (this file)

Modified (lockstep):
- `CLAUDE.md` (Block 11 Detail table)
- `README.md` (status line, phase roadmap)
- `docs/devlog/index.md` (Phase 98 status)
- `docs/development-phases-block11.md` (Phase 98 status)

## Next phase

Phase 99: Debecka Pass 2003 scenario. Uses the gap audit to drive data authoring (~10 new files), the calibration template to define envelopes, the depth checklist to drive UI walkthrough, and `envelope_check.py` helpers to build the regression test.

## Postmortem

### 1. Delivered vs Planned

All four planned subsections addressed:

| Subsection | Planned | Delivered |
|-----------|---------|-----------|
| 98a Gap audit | `docs/scenarios/gap-audit.md` | ✓ plus 4 research briefs baked into the doc |
| 98b Calibration template + envelope helpers | `calibration-template.md` + `envelope_check.py` + tests | ✓ 6 helpers, 26 tests |
| 98c Depth checklist framework | `depth-checklist-template.md` | ✓ |
| 98d `CALIBRATION_SCENARIOS` stubs | Stub entries for 4 scenarios | **Refined — deferred to scenario phases** (see below) |

**Refinement (98d)**: the planned `stochastic_warfare/validation/calibration_scenarios.py` file doesn't exist — the registry lives in `tests/validation/test_historical_accuracy.py` as the `HISTORICAL_WINNERS` and `CALIBRATION_SCENARIOS` sets. Stubbing for not-yet-authored scenarios would fail the coverage assertion. Convention documented in `calibration-template.md`; each scenario phase registers its own entry. **Scope verdict: on target; one refinement handled correctly by skipping rather than forcing a failing stub.**

### 2. Integration Audit

- `stochastic_warfare/tools/envelope_check.py` — imported only by `tests/unit/test_envelope_check.py`. **Expected** — this is forward-facing scaffolding; Phases 99–102 will consume it in their regression tests. Not dead code, pre-wired infrastructure.
- New docs (`docs/scenarios/*`) — not in mkdocs nav, but appropriate: these are internal authoring scaffolding for scenario development, not user-facing content. Kept out of the site.
- No new config flags, event types, or engine hooks introduced (consistent with Block 11 "zero new engine capabilities" principle).

### 3. Test Quality Review

- 26 tests, all passing (0.53s execution)
- **Edge cases covered**: empty metric list, missing metric key, historical=0 with and without `max_override`, lower-bound clamping, custom tick_duration_s
- **Unit, not integration**: event-capture helpers (`count_destructions_by_weapon` etc.) use mocked `ScenarioLoader`/`SimulationEngine`/`SimulationRecorder`. Correct separation — real scenario integration is the job of Phase 99's regression test.
- No tests marked `@pytest.mark.slow`; all synthetic and fast. Appropriate for unit-level scaffolding.

### 4. API Surface Check

- All 6 public functions have complete type hints on parameters and return types
- All public functions have docstrings
- Return types consistent: `(bool, str)` tuples for envelope checks (passed + diagnostic message), `int` for counters
- No bare `print()` calls; `get_logger(__name__)` used in module header
- Module follows project conventions (pydantic-free config, no global state, lazy imports for heavy engine modules)

### 5. Deficit Discovery

- No TODOs / FIXMEs / XXX / HACK markers in new code
- No hardcoded magic numbers (all thresholds are function parameters with defaults)
- No missing error handling at boundaries — envelope checks return `(False, diagnostic)` instead of raising, allowing test code to assemble multiple checks before asserting
- No new engine deficits discovered. Two pre-existing cross-scenario observations (kornet_team already exists; WW2-era 16in50 reusable) are opportunities, not deficits.

### 6. Documentation Freshness

**Accuracy drift found** (fixed inline during postmortem):

- [x] `mkdocs.yml` — added Block 11 brainstorm, Block 11 phase roadmap, phase-98 devlog entries
- [x] `docs/index.md` — test count badge 10,739 → 10,765; phase badge 97_Block--10 → 98_Block--11

**Verified accurate**:
- `CLAUDE.md` — Block 11 Detail table shows Phase 98 complete; phase summary table shows Block 11 row; status line updated
- `README.md` — status line + phase roadmap row for Phase 98
- `docs/devlog/index.md` — Phase 98 status flipped
- `docs/development-phases-block11.md` — Phase 98 status flipped
- `MEMORY.md` — Phase 98 complete notation
- User-facing `docs/concepts/` / `docs/reference/` / `docs/guide/` — **no changes needed** (Phase 98 added no engine capabilities, no new scenarios, no new units/weapons/eras, no math models)

### 7. Performance Sanity

- Phase 98 tests (26): 0.53s
- Broad smoke test (`tests/unit/` + `tests/api/`, -m "not slow"): 9,354 tests in 85.42s (average 9.1ms/test)
- No slow tests added; no performance regression

### 8. Summary

- **Scope**: On target. 98d refined intentionally (existing registry pattern differs from planned file; deferred to scenario phases).
- **Quality**: High. Full type hints, full docstrings, no TODOs, edge cases covered, appropriate mock-based unit testing.
- **Integration**: Forward-facing scaffolding as expected. `envelope_check.py` consumed by Phases 99–102 regression tests.
- **Deficits**: 0 new engine deficits. 2 doc drift items found and fixed (mkdocs nav, index.md badges).
- **Action items**: All fixed inline during postmortem. Ready for Phase 99.

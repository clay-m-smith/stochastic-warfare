# Block 11: Golden Scenarios & End-to-End Engine Validation

> **Phase 112 integrity supersession (2026-07-30):** This brainstorming page
> preserves Block 11's contemporaneous design inventory, counts, calibration
> plans, and scenario claims. They are development history, not current
> historical-validation evidence. A historical name, source citation,
> calibrated input, golden-scenario label, or current-engine regression does not
> establish a provenance-bearing, held-out production outcome-envelope verdict.
> REM-030/Phase 117 owns the replacement catalog-wide contract and the
> disposition of every retained claim.

## Motivation

Blocks 1–10 delivered 97 phases of engine capability and UI polish: 60+ domain engines, 32 `enable_*` behavioral flags, 68 calibration parameters, 9 doctrinal schools, 5 historical eras, 100+ event types, ~10,323 backend tests + 416 frontend tests, and 40+ validated scenarios covering every era we support.

The existing scenario library, however, skews toward **narrow test cases**. 73 Easting is a pure tank duel. Agincourt exercises archery and melee but no modern systems. Midway tests naval aviation but no ground forces. Bekaa Valley exercises air-to-air but no surface combat. Each was designed to validate a specific engine, not to showcase cross-system depth.

The result: when walking through the UI, a user sees the engine exercise ~30–40% of its capabilities per scenario. Morale overlays render but no rout cascades fire. Fuel bars appear on the map but nothing ever runs out. The Casualties-by-Weapon chart shows one or two rows. The doctrine-comparison analysis shows identical outcomes across schools because the scenarios are too simple to distinguish tactics.

Block 11 closes this gap by building a **golden scenario suite** — four historically-grounded modern-era engagements, each chosen to exercise a distinct and broad cross-section of the engine's capability stack, each calibrated to reproduce the statistical envelope of its real-world outcome, and each walked through the UI end-to-end to confirm the rendered depth matches what the engine computes.

### Why "Golden"

A *golden scenario* serves four purposes simultaneously:

1. **UI demonstration** — every visual system (map overlays, charts, analysis panels) has meaningful data to display
2. **Engine regression** — a failed `enable_*` wiring or calibration drift surfaces as an outcome shift on a known-good scenario
3. **Calibration anchor** — historical outcomes give us a reference distribution to validate against when tuning behavior
4. **Development onboarding** — a new contributor can run one scenario and see most of the engine in action

### Design Principle

Block 11 adds **zero new engine capabilities** (same discipline as Block 10). Every scenario uses existing systems. Where a scenario needs a unit/weapon/sensor YAML we don't have, we author it from real-world data and slot it into existing loaders. Where the engine lacks fidelity to model a specific historical dynamic (e.g., Hezbollah's cognitive edge from ISR infiltration), we **document the gap as an accepted limitation** in the phase devlog rather than hand-tune calibration overrides to paper over it.

---

## Theme 1: Scenario Selection — Coverage vs. Cost

**Problem**: The engine has ~60 domain engines. No single real-world battle exercises all of them. An artillery-only duel tests firing solutions and suppression but no maneuver. A symmetric tank battle tests armor and gunnery but no urban terrain. Picking scenarios is a coverage-maximization problem.

**Solution**: Four scenarios selected so that, taken together, they fire every major engine at least once. Each scenario targets a distinct engine cluster while sharing some baseline systems (direct fire, morale, C2) with the others. Overlap is intentional — different engagements exercise the same engine under different conditions (e.g., both Debecka and Khafji exercise CAS, but Debecka against a mechanized thrust and Khafji against infantry).

### Scenario Selection Matrix

| Scenario | Year | Scale | Primary Engines Exercised |
|----------|------|-------|---------------------------|
| **Debecka Pass** | 2003 | 31 SF + 80 Peshmerga vs. 1 Iraqi mech battalion | ATGM (Javelin), CAS routing, air defense, C2 friction, blue-on-blue, morale cascade |
| **Khafji** | 1991 | 2 Iraqi divisions vs. Saudi/USMC/Qatari + CAS | Naval gunfire (USS Wisconsin), multi-domain C2, night combat, large-scale surrender/morale cascade |
| **Fallujah Phase Line Fran** | 2004 | 1 MARDIV sector vs. entrenched insurgents | Urban terrain, IEDs, booby traps (UW module), AC-130, fire zones, obscurants |
| **Bint Jbeil** | 2006 | Golani Brigade vs. Hezbollah | ATGM-heavy defense vs. MBT (Kornet vs. Merkava), urban, limited EW, reserve mobilization; paired with INS Hanit C-802 strike as naval vignette |

### Coverage Matrix (Engines × Scenarios)

Check marks indicate expected engine activation during a typical run. Blank cells indicate the engine is loaded but not meaningfully exercised.

| Engine | Debecka | Khafji | Fallujah | Bint Jbeil |
|--------|---------|--------|----------|------------|
| Direct fire (ballistic) | ✓ | ✓ | ✓ | ✓ |
| ATGM / guided munition | ✓ | | ✓ | ✓ |
| Indirect fire (artillery/mortar) | ✓ | ✓ | ✓ | ✓ |
| CAS (air-to-ground) | ✓ | ✓ | ✓ | ✓ |
| Air defense | ✓ | | | |
| Air-to-air | | | | |
| Naval gunfire | | ✓ | | |
| Naval missile | | | | ✓ |
| Submarine | | | | |
| Mine warfare | | | | |
| EW / jamming | | | | ✓ |
| Space / GPS | ✓ | | ✓ | ✓ |
| CBRN | | | | |
| Morale / rout | ✓ | ✓ | ✓ | ✓ |
| Suppression | ✓ | ✓ | ✓ | ✓ |
| C2 friction / ATO | ✓ | ✓ | ✓ | |
| Doctrinal AI | ✓ | ✓ | ✓ | ✓ |
| Unconventional warfare | | | ✓ | ✓ |
| Environmental (weather) | ✓ | ✓ | ✓ | ✓ |
| Human factors (heat/cold) | | | ✓ | |
| Logistics / supply | | ✓ | ✓ | |
| Posture (DUG_IN etc.) | ✓ | ✓ | ✓ | ✓ |
| Fire zones / incendiary | | | ✓ | |
| Obscurants | ✓ | | ✓ | |
| Carrier operations | | | | |
| Formation effects | | | | |

**Gaps intentionally unaddressed by Block 11**: A2A combat, submarine warfare, mine warfare, CBRN, carrier operations, formation-era mechanics (Napoleonic/WW1 squares and trenches). These are covered by existing historical scenarios (Midway for carrier ops, Agincourt for formations) and don't need a modern-era companion.

---

## Theme 2: Calibration Targets — Statistical Plausibility, Not Point Replication

**Problem**: Historical outcomes are a single realization. 73 Easting happened once, with one weather state, one set of commander decisions, one set of dice rolls on every exchange. Matching our 10-run Monte Carlo distribution to that single point is both under-specified (many distributions pass through it) and over-determined (we could force a match by tuning Pk values arbitrarily).

**Solution**: Define **envelopes** rather than point targets. For each scenario, bracket the historically-plausible outcome range based on contemporaneous after-action reports, unit strength returns, and post-hoc scholarship. A 10-iteration MC run should produce:

- Winner distribution: the historically-observed winner wins ≥ 70% of iterations
- Duration: 10th–90th percentile spans the historical duration ± 50%
- Casualties: 10th–90th percentile brackets the historical figure ± 40%
- Key dynamics visible: e.g., Debecka should show Javelin as dominant weapon; Khafji should show Iraqi surrenders; Fallujah should show IED-caused casualties

Where the engine cannot reproduce a historically-observed dynamic (e.g., Debecka's JDAM friendly-fire incident is a specific narrative event, not a probabilistic one), we **document the miss** in the devlog and do not calibrate around it.

### Calibration Approach

Use the existing `/calibrate` skill:
1. Initial run with default modern-era calibration (`enable_all_modern`)
2. Measure outcome distribution vs. envelope
3. Identify dominant miss (e.g., wrong winner, duration too long)
4. Apply **minimum-invasive** override (commander CEV, ROE, weapon_assignments before tuning Pk)
5. Re-run, re-measure
6. Stop when envelope is met OR further overrides would start contradicting history

**Forbidden calibration techniques**:
- Tuning per-weapon Pk to force a specific outcome (constitutes overfitting to a single realization)
- Disabling engines to simplify the scenario (undermines the depth goal)
- Setting `force_ratio_modifier` to implausible values (e.g., > 3.0 for symmetric-era forces)

**Permitted calibration techniques**:
- Commander profile CEV within Dupuy-documented ranges (0.8–2.5)
- ROE setting (`WEAPONS_FREE` vs. `WEAPONS_TIGHT` based on historical record)
- Initial morale state per side (documented AARs)
- Training level overrides per side (documented from unit histories)
- Doctrine school assignment (explicit in some scenarios — e.g., Fallujah Marines ran combined_arms)
- Weather, terrain, and time-of-day from historical record

---

## Theme 3: Data Authoring — Real-World Provenance

**Problem**: Every new unit/weapon YAML we add becomes part of the catalog that gets loaded for every scenario, era check, and doctrine comparison. A sloppy authoring job introduces equipment drift, sensor gaps, or broken cross-references. The Phase 24 experience (data-driven YAML validated by pydantic) set the discipline we need to maintain.

**Solution**: Each new unit/weapon file must cite its real-world source in a YAML comment block at the top of the file. Sources must be drawn from the `/research-military` tiered source list:

- **Tier 1 (required for primary sources)**: Official OOB documents, unit histories, manufacturer specifications, declassified AARs
- **Tier 2 (acceptable for cross-reference)**: Peer-reviewed military history journals, Jane's publications, IISS Military Balance
- **Tier 3 (supplementary only)**: Reputable secondary sources (Bing West, Williamson Murray, USMC History Division reports)

**Excluded**: Blogs, Wikipedia unsourced sections, forum posts, encyclopedic summaries without primary citations.

Example header:

```yaml
# Source: FM 3-22.37, Table 1-1 (Javelin weapon characteristics)
# Cross-ref: Wong, Combat Studies Institute, "A Different Kind of War" p. 94 (Debecka employment)
unit_type: us_sf_team
...
```

### Gap Audit Strategy

Before authoring, compare each scenario's required unit/weapon set against `data/units/`, `data/weapons/`, `data/sensors/`. Produce a gap list. Author the gap list in one pass before any scenario YAML is written — this avoids the "scenario needs X, author X, discover X needs Y, author Y" thrash pattern.

Expected gaps (preliminary, to be confirmed during Phase 98):

| Scenario | Likely Missing |
|----------|----------------|
| Debecka Pass | US SF team unit, Peshmerga irregular infantry, T-55 variant details, possibly F-14D |
| Khafji | USS Wisconsin with 16" guns, Saudi V-150 APC, possibly LAV-25 variant |
| Fallujah | AC-130U gunship, Marine rifle squad (urban kit variant), IED device definitions, AT4 disposable launcher |
| Bint Jbeil | Merkava Mk IV, AT-14 Kornet, C-802 Noor, possibly INS Hanit |

---

## Theme 4: UI Walkthrough — Depth Checklist as Acceptance Criteria

**Problem**: Running a scenario and "looking at the UI" is a soft test. A Charts tab that renders zeroes for suppression is a failure, but easy to miss if we only verify the chart component didn't crash. Block 10 surfaced this explicitly (Casualties by Weapon rendered empty because weapon_id wasn't propagating).

**Solution**: Per scenario, define a **depth checklist** — the specific UI elements that MUST display non-trivial data for the scenario to be considered successfully exercised. This checklist goes in the scenario's devlog entry and is checked off during the Phase 5 walkthrough.

### Depth Checklist Template

For each scenario, the devlog walk-through verifies:

**Results tab**:
- Dominant Weapon shows a specific weapon (not `"auto_resolve"` or `"combat_damage"`)
- Hit Rate, Total Engagements, Total Casualties all > 0
- Peak Suppressed and Rout Cascades populate if scenario expects them

**Charts tab**:
- Force Strength: both sides show non-trivial losses
- Engagement Timeline: visible clusters, not a flat line
- Event Activity: multi-modal distribution
- Morale Curve: shifts visible for losing side
- Casualties by Weapon: multiple bars, distinguishable weapons
- Engagements by Type: multiple rows
- Suppression: non-zero peaks if scenario expects them
- Morale Distribution: state transitions visible

**Map tab**:
- All 5 overlay toggles produce visible changes
- Engagement flashes animate during playback
- Unit click-through shows all 7 enriched fields populated
- Map legend sections appear/hide based on toggles

**Analysis tab**:
- Event filter (side, tick range, search) correctly subsets
- Engagement detail modal shows weapon, range, hit result
- Doctrine compare (where applicable): distinguishable outcomes across schools

**Scenario-specific** (examples):
- Debecka: Javelin appears in Casualties by Weapon; CAS events visible in timeline
- Khafji: Naval engagement events from Wisconsin; Iraqi morale cascade visible
- Fallujah: IED events in filtered list; urban terrain modifier in engagement details
- Bint Jbeil: Kornet kills of Merkava visible; optional vignette: INS Hanit struck

---

## Theme 5: Political and Historical Sensitivity

**Problem**: Modern-era scenarios touch live political controversies. Bint Jbeil is the clearest — Hezbollah vs. IDF engagements remain a contested narrative space. Fallujah's civilian casualty figures and use of white phosphorous (which our engine models via incendiary_engine) carry political weight.

**Solution**: Three guardrails.

1. **Scope clarity**: Golden scenarios model **tactical engagements**, not strategic narratives. We don't evaluate who should have won or whether an operation was justified. We measure whether the engine reproduces plausible outcomes given documented OOB and conditions.
2. **Source discipline**: Rely on after-action reports, unit histories, and peer-reviewed military analysis. Avoid contemporaneous news coverage and advocacy-framed sources.
3. **Language**: Scenario names use geographic/operational terminology (`bint_jbeil_2006`, not `hezbollah_ambush`). Unit labels use formal OOB designations. Commentary in devlogs is descriptive, not evaluative.

Where a scenario's political charge is high enough that sensitivity exceeds analytic value, we drop it. Bint Jbeil stays because its technical interest (Kornet-vs-Merkava, reserve mobilization morale effects, naval missile vulnerability) is substantial and documentable. An alternative — e.g., modern Donbas engagements — would be more technically interesting but less defensibly neutral at this stage.

---

## Theme 6: Regression Test Integration

**Problem**: A golden scenario that drifts silently is worse than no golden scenario — it suggests coverage we don't have. Block 7's structural-test pattern proved that bounded assertions catch regressions 100× faster than full validation runs.

**Solution**: Each golden scenario gets a bounded regression test in `tests/validation/`:

```python
@pytest.mark.slow  # or not, depending on run time
def test_debecka_pass_envelope():
    """Verify Debecka Pass outcome distribution stays within historical envelope."""
    results = run_scenario_batch("data/scenarios/debecka_pass/scenario.yaml",
                                  num_iterations=10, base_seed=42, ...)

    # Winner distribution
    blue_wins = sum(results["win_blue"])
    assert blue_wins >= 7, f"Expected blue to win ≥7/10 iterations, got {blue_wins}"

    # Casualty envelope
    iraqi_destroyed = sum(results["red_destroyed"]) / 10
    assert 15 <= iraqi_destroyed <= 40, f"Iraqi casualties outside envelope: {iraqi_destroyed}"

    # Key dynamic
    sf_casualties = sum(results["blue_destroyed"]) / 10
    assert sf_casualties <= 3, f"SF casualties too high (historical: 0): {sf_casualties}"

    # Depth check — weapon distribution
    # (runs a single iteration with event capture, checks weapon_id distribution)
    javelin_kills = count_destructions_by_weapon(scenario, weapon="javelin_cmdl")
    assert javelin_kills >= 5, "Javelin should dominate Iraqi armor kills"
```

These tests run under the existing pytest harness. The "slow" marker keeps them out of the fast loop but accessible via `pytest -m slow`.

---

## Trade-offs and Open Questions

**Scope**: Four scenarios is ambitious. Each requires research, authoring, calibration, regression, and UI walkthrough. Realistic estimate: ~1–2 weeks per scenario for a thorough job. If time pressure, drop to three (keep Debecka, Khafji, Fallujah; defer Bint Jbeil).

**Shared authoring**: Some unit definitions will overlap (e.g., US infantry appears in both Debecka and Fallujah). The gap audit in Phase 98 must deduplicate to avoid inconsistent definitions.

**Calibration portability**: A calibration override tuned for Debecka might conflict with Khafji's needs. Each scenario carries its own `calibration_overrides` block; no global defaults changed during Block 11.

**New deficits expected**: Authoring real scenarios exposes new engine gaps. When a gap is identified, log it in `devlog/index.md`'s deficit section, categorize it (resolved in-block / deferred / accepted limitation), and continue. Block 11 is **not** a bug-fix block — engine fidelity gains from Block 11 come in follow-on blocks if warranted.

**Frontend chart rendering**: Some scenarios may expose chart-rendering issues like the Casualties by Weapon bug discovered while testing 73 Easting. Budget a small buffer per phase for frontend patches.

---

## Summary

Block 11 builds a suite of four historically-grounded modern-era scenarios that collectively exercise ~70% of the engine's capability surface, each calibrated to match a documented outcome envelope, each validated by a regression test, and each walked through the UI with an explicit depth checklist. The goal is not to add engine capability but to **make existing capability visible, usable, and regression-tested** through concrete, realistic use cases.

Exit criteria:
1. Four scenario YAMLs produce winners matching historical record in ≥70% of 10-iteration MC
2. Each scenario exercises its targeted engine cluster per the coverage matrix
3. All four scenarios have passing regression tests
4. Each scenario's UI walkthrough checklist is complete
5. New unit/weapon YAMLs have cited sources
6. No engine regressions on existing 40+ scenarios

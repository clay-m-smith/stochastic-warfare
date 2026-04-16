# Block 11 Scenario Depth Checklist Template

This template documents the UI walkthrough acceptance criteria for a Block 11 golden scenario. Each scenario phase (99–102) copies this template into its devlog entry, pre-fills the **Scenario-specific expected observations** section from research, and checks off items during the walkthrough.

The goal: running the scenario through the UI should *visibly* exercise the engines called out in `brainstorm-block11.md`'s coverage matrix. A chart that renders with zero data or an overlay toggle that produces no visible effect is a **defect**, not an acceptable outcome.

---

## How to use

1. Copy this file into `docs/devlog/phase-{N}.md` under a **UI Walkthrough** section
2. Fill in the "Scenario-specific expected observations" section with details from the scenario's research brief
3. Run the scenario through the UI
4. Check items off as verified. For any unchecked items at phase end, either:
   - File the gap as a follow-up issue and proceed (minor cosmetic), OR
   - Block phase completion (engine or data defect)
5. Include the completed checklist in the phase commit

---

## Results tab

- [ ] **Dominant Weapon** card shows a specific weapon ID (not `combat_damage`, `auto_resolve`, or blank)
- [ ] **Hit Rate** card shows a non-zero percentage
- [ ] **Total Engagements** card > 0
- [ ] **Total Casualties** card > 0
- [ ] **Peak Suppressed** card non-zero *if scenario expects suppression*
- [ ] **Rout Cascades** card non-zero *if scenario expects morale collapse*
- [ ] Run summary (winner, duration, seed) displays correctly

## Charts tab

- [ ] **Force Strength** chart: both sides show non-trivial loss curves
- [ ] **Engagement Timeline** chart: visible clusters, not a flat line
- [ ] **Event Activity** chart: multi-modal distribution (not a single spike)
- [ ] **Morale Curve** chart: state shifts visible for losing side
- [ ] **Casualties by Weapon** chart: multiple bars, distinguishable weapon IDs
  - *(Regression guard: this chart should not render empty. If it does, the weapon_id propagation is broken.)*
- [ ] **Engagements by Type** chart: multiple rows by engagement type / weapon category
- [ ] **Suppression** chart: non-zero peaks *if scenario expects suppression*
- [ ] **Morale Distribution** chart: state transitions visible over time
- [ ] Tick-sync cursor functions (click a time point, other charts highlight; map jumps to that tick)

## Map tab

- [ ] Unit positions render correctly at T=0 and at a mid-run tick
- [ ] **Morale overlay** toggle visibly changes unit coloring
- [ ] **Health bars** overlay toggle shows bars above damaged units
- [ ] **Posture icons** overlay toggle shows posture markers
- [ ] **Suppression opacity** overlay toggle changes unit opacity during suppressed periods
- [ ] **Logistics bars** overlay toggle shows fuel/ammo indicators *(if logistics exercised)*
- [ ] **Engagement flash** animation fires during playback
- [ ] Click-through on a unit shows all 7 enriched sidebar fields populated (morale/posture/health/fuel/ammo/suppression/engaged)
- [ ] Map legend sections appear/hide based on overlay toggle state
- [ ] Terrain renders (elevation shading, water, urban areas, roads as applicable)
- [ ] Playback controls (play, pause, speed, scrub) function

## Analysis tab

- [ ] **Event filter** (side, tick range, search) correctly subsets the event list
- [ ] Click an engagement event → **Engagement Detail Modal** opens with: attacker, target, weapon, ammo, range, hit result, damage type
- [ ] **Doctrine Compare** tab: if scenario defines multiple doctrinal schools, comparison produces distinguishable outcomes
- [ ] **A/B comparison** tab: functional for scenario overrides
- [ ] **Sensitivity sweep** tab: can sweep a calibration parameter

## Scenario-specific expected observations

*Fill this section from the research brief and brainstorm coverage matrix. Examples below.*

### Expected engine activations (from coverage matrix)

- Engine X should fire ≥ N times
- Engine Y should produce ≥ N events
- Engine Z should not fire (not expected in this scenario)

### Expected event-type presence

- `<EventType>`: expected count range, notable data fields to spot-check
- ...

### Expected weapon signatures

- `<weapon_id>`: should dominate Casualties by Weapon chart
- ...

### Expected map observations

- Specific unit cluster at tick N
- Engagement flash pattern (e.g., sustained along ridgeline)
- Posture shift (e.g., Iraqi units go from MOVING → STATIC after first engagement)

### Expected chart patterns

- Morale curve: red side shows progressive decline starting tick N
- Suppression chart: peak at tick M when CAS arrives
- Force strength: sharp red drop during window [M, M+Δ]

---

## Known limitations to acknowledge (not defects)

*List any scenario-specific gaps where the engine cannot reproduce a historical dynamic. These are not failures of this phase — they are deferred to a future block.*

Example:
- Hezbollah's ISR edge from civilian cellular monitoring — not modeled; we document as an accepted limitation
- Debecka's specific JDAM friendly-fire event — single-realization narrative, not attempted probabilistically

---

## Frontend defects discovered

*If any chart, overlay, or interaction produces incorrect output during the walkthrough, file a bullet with reproduction steps. These become fixes in subsequent commits — not block phase completion unless scenario is unrunnable.*

Example:
- [fixed] Casualties by Weapon chart rendered empty despite non-zero data — root cause: `layoutOverrides` xaxis override on categorical chart (pre-Block-11 bug fixes commit)

---

## Sign-off

- Phase: __
- Scenario: __
- UI walkthrough completed: __ (date)
- All non-deferred items checked: __ (yes/no)
- Frontend defects filed: __ (count)
- Engine deficits filed: __ (count)

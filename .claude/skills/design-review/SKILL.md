---
name: design-review
description: Review a module's design against military theory foundations and project architecture decisions. Ensures implementation stays grounded in established doctrine and our design principles.
allowed-tools: Read, Grep, Glob, WebSearch, WebFetch
context: fork
agent: general-purpose
---

# Design Review — Military Theory & Architecture Compliance

You are reviewing a module's design in the Stochastic Warfare project to ensure it is grounded in established military theory and consistent with the project's architectural decisions.

## Target
$ARGUMENTS

## Review Process

### 1. Read the Module
- Read the module's spec (`docs/specs/<module>.md`) and implementation
- Understand what it models and how

### 2. Cross-Reference Architecture Decisions
Read `docs/brainstorm.md` and verify:
- [ ] Consistent with the hybrid simulation loop (tick + event-driven)
- [ ] Uses the correct spatial model for its scale (graph/grid/continuous)
- [ ] Coordinates in ENU/UTM, not geodetic
- [ ] Unit parameters are data-driven (YAML), not hardcoded
- [ ] Full tactical resolution — no fidelity shortcuts
- [ ] PRNG discipline maintained
- [ ] State is serializable for checkpointing

### 3. Military Theory Validation
For the domain this module covers, check against relevant theorists:

**Combat/Engagement:**
- Does it reflect Lanchester's mathematical foundations?
- Does Clausewitzian friction manifest as stochastic variance in execution?
- Are combined arms interactions modeled per Fuller's principles?

**Movement/Maneuver:**
- Does the model allow for Liddell Hart's indirect approach?
- Can Jominian concepts (interior lines, concentration) emerge from the mechanics?

**C2/Decision-Making:**
- Is there a recognizable OODA loop (Boyd)?
- Do order propagation delays create realistic C2 friction?

**Intelligence/Recon:**
- Is Sun Tzu's emphasis on intelligence reflected in the detection model?
- Does deception have mechanical support?

**Logistics:**
- Are LOCs modeled as Jomini described?
- Can logistics be disrupted (interdiction)?

**Morale:**
- Is Clausewitz's moral forces concept present?
- Does du Picq's/Marshall's work on combat motivation inform the model?

**Air Power:**
- Does Douhet's command-of-the-air concept have mechanical expression?
- Is Warden's five-rings targeting theory supportable?

### 4. Emergent Behavior Check
- Can realistic tactical/operational patterns emerge from the mechanics?
- Can the model produce historically observed phenomena (suppression, envelopment, rout, breakthrough)?
- Are there degenerate cases where the model produces unrealistic behavior?

## Output Format

```
DESIGN REVIEW: <module>
================================================

ARCHITECTURE COMPLIANCE:
  [PASS/FAIL/N/A] Each architecture decision check

MILITARY THEORY ALIGNMENT:
  [ALIGNED/PARTIAL/MISSING/N/A] Each relevant theorist check
  Notes on what's well-modeled and what's missing

EMERGENT BEHAVIOR ASSESSMENT:
  What patterns this design can/cannot produce

RECOMMENDATIONS:
  Prioritized list of design improvements

VERDICT: APPROVED / APPROVED WITH NOTES / NEEDS REVISION
```

## Important
- Not every theorist is relevant to every module — mark N/A where appropriate
- The goal is not academic perfection but ensuring the simulation captures the right dynamics
- Flag cases where theory conflicts with practical implementation constraints — these are trade-offs to document, not failures

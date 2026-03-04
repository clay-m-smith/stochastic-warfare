# Stochastic Warfare — Claude Skills & Hooks

## Custom Skills

### /research-military
- Searches for and synthesizes military doctrine, historical data, theorist writings, and philosophical/ethical works relevant to the current subsystem being developed
- Scope explicitly includes philosophers, ethicists, and political theorists (Thucydides, Machiavelli, Grotius, Walzer, etc.) — not limited to military thinkers
- **Constrained to approved sources** (see Research Source Tiers below)
- Output: summary of relevant findings with full citations and source tier classification
- Example: when implementing the morale system, invoke to survey Clausewitz on friction, du Picq on combat motivation, S.L.A. Marshall on fire ratios, modern RAND studies on unit cohesion
- Example: when implementing ROE, invoke to survey Walzer on just war constraints, Grotius on proportionality, relevant Geneva Convention provisions

### /research-models
- Focused on mathematical, stochastic, and signal processing modeling approaches
- **Constrained to approved sources** (see Research Source Tiers below)
- Output: summary of modeling approaches with mathematical formulations, assumptions, limitations, and citations
- Example: when building the detection system, survey detection theory (Neyman-Pearson), ROC curves, SNR-based Pd models from radar/signal processing literature

### /validate-conventions
- Reviews code against project-specific rules:
  - No bare `random` module imports or calls (all RNG through seeded numpy Generators)
  - Deterministic iteration order (no `set()` or unordered dict driving sim logic)
  - PRNG stream discipline (subsystems use their own forked streams)
  - Proper coordinate system usage (ENU/UTM internally, geodetic only at boundaries)
  - Logging framework usage (no bare `print()` in sim core)
  - Type hints on public API functions
- Reports violations with file, line, and suggested fix

### /update-docs
- When a design decision is made or a module is completed, updates the relevant documentation:
  - `docs/brainstorm.md` — architecture decisions (MVP)
  - `docs/brainstorm-post-mvp.md` — design thinking (post-MVP domains)
  - `docs/development-phases-post-mvp.md` — phase status + deficit mapping (post-MVP)
  - `docs/specs/<module>.md` — module specifications
  - `docs/devlog/index.md` — phase status + deficit inventory
  - Memory files — stable patterns and conventions
- Enforces post-MVP lockstep: completing Phase 11+ requires updating CLAUDE.md, project-structure.md, development-phases-post-mvp.md, devlog/index.md, phase devlog, README.md, and MEMORY.md together
- New deficits discovered during post-MVP work must be added to both devlog/index.md AND the deficit-to-phase mapping
- Keeps documentation in sync with implementation

### /spec
- Drafts or updates a module specification before implementation begins
- Forces definition of: inputs, outputs, interfaces, stochastic models used, relevant military theory, dependencies on other modules
- Output written to `docs/specs/<module_name>.md`
- Becomes the contract that implementation must satisfy

### /backtest
- Structures a comparison between simulation output and historical engagement data
- Defines: metrics to compare, acceptable tolerances, data sources, divergence analysis
- Example: simulate a scenario modeled on 73 Easting, compare attrition curves, engagement timelines, and movement rates against historical record

### /audit-determinism
- Deep verification of PRNG discipline in a module
- Traces all stochastic paths to verify: seeded generators used, no cross-stream contamination, deterministic iteration, no timing-dependent behavior
- Reports any path that could break replay fidelity
- More thorough than /validate-conventions — this is structural analysis, not pattern matching

### /design-review
- Reviews a module's design against established military theory and project architectural decisions
- Checks: does this morale model capture Clausewitzian friction? Does the C2 system implement OODA-like cycles? Does the logistics model respect Jominian LOC principles?
- Keeps implementation honest against the theoretical foundations we've committed to

### /cross-doc-audit
- Audits alignment across all documentation layers — MVP AND post-MVP:
  - MVP: development-phases.md, project-structure.md, brainstorm.md, devlog, MEMORY.md, README.md
  - Post-MVP: development-phases-post-mvp.md, brainstorm-post-mvp.md, devlog/index.md deficit inventory
- 13 checks: original 9 (module coverage, phase content match, dependency ordering, exit criteria coverage, contradictions, brainstorm traceability, devlog completeness, memory freshness, README currency) + 4 post-MVP checks (deficit traceability, cross-document alignment, module coverage, devlog completeness)
- Output: PASS/FAIL per check with severity (CRITICAL/HIGH/MEDIUM/LOW)
- Run after completing phases, adding modules, or changing architecture

### /simplify
- Reviews changed code for reuse, quality, and efficiency
- Six checks: duplication detection, complexity reduction, performance patterns, interface quality, test quality, convention compliance
- Flags issues by severity (HIGH/MEDIUM/LOW) with concrete fix suggestions
- Run after completing significant implementations or before committing phase work

### /profile
- Identifies performance hotspots via cProfile analysis
- Classifies hotspots: algorithmic, Python overhead, allocation, redundant computation, I/O
- Estimates impact and implementation effort for each optimization
- Provides benchmark script template for standardized measurement
- Run when scenarios are slow or before/after optimization work

### /scenario (Phase 14)
- Interactive walkthrough for creating or editing campaign scenario YAML files
- Guides user through sides, units, terrain, objectives, victory conditions, and calibration
- Validates against `CampaignScenarioConfig` schema and runs smoke test
- Outputs complete scenario YAML to `data/scenarios/{name}/scenario.yaml`

### /compare (Phase 14)
- Runs two scenario configurations and statistically compares outcomes
- Uses `tools/comparison.py` with Mann-Whitney U test
- Interprets p-values and effect sizes in military context
- Outputs formatted comparison table

### /what-if (Phase 14)
- Quick parameter sensitivity analysis from natural language questions
- Identifies parameter and range from user's question
- Uses `tools/sensitivity.py` for sweep, generates errorbar plot
- Summarizes sensitivity level and key inflection points

### /timeline (Phase 14)
- Runs a scenario and generates human-readable battle narrative
- Uses `tools/narrative.py` with full/summary/timeline styles
- Structures output as Opening/Main Battle/Conclusion phases

### /orbat (Phase 14)
- Interactive order of battle builder
- Lists available unit types, guides through echelon hierarchy
- Generates `sides` section of scenario YAML
- Validates unit types, commander profiles, and doctrine templates

### /calibrate (Phase 14)
- Auto-tunes calibration overrides to match historical metrics
- Sweeps influential parameters via `tools/sensitivity.py`
- Uses binary search refinement to narrow to target value
- Validates with statistical test against historical data

### /postmortem (Phase 14)
- Structured retrospective to run after completing each implementation phase
- 8-step process: delivered vs planned, integration audit, test quality review, API surface check, deficit discovery, documentation freshness, performance sanity, summary
- Catches integration gaps, dead modules, missing wiring, undocumented limitations
- Updates phase devlog with findings and action items

---

## Hooks

### Pre-Edit Python Hook (sim core)
- **Trigger**: before any `.py` file in the simulation core is modified
- **Checks**:
  - No bare `import random` or `random.random()` / `random.choice()` etc.
  - No `set()` iteration or unordered dict iteration driving simulation logic
  - No bare `print()` (use logging framework)
  - Type hints present on public API functions
- **Action**: warn and flag violations before edit is accepted

### YAML Validation Hook
- **Trigger**: when a unit definition YAML is created or modified
- **Checks**: validates against the pydantic schema for that unit class
- **Action**: report schema violations immediately (missing required fields, out-of-range values, type errors)

### Spec-Before-Code Hook
- **Trigger**: when creating a new module/package directory under the sim core
- **Checks**: corresponding spec document exists in `docs/specs/`
- **Action**: warn if no spec exists — enforces specify-before-implement discipline

### Research Source Hook
- **Trigger**: applied within /research-military and /research-models skills
- **Checks**: all cited sources classified by tier; any source outside approved tiers is flagged
- **Action**: flag unapproved sources with warning; never present unverified sources without explicit disclaimer

---

## Research Source Tiers

### Tier 1 — Primary / Authoritative
- Military field manuals and doctrine (FM, ATP, JP, ADP, NATO STANAGs)
- RAND Corporation, CNA, IDA, and other FFRDC publications
- Official military histories (U.S. Army Center of Military History, Naval History and Heritage Command, etc.)
- Original theorist texts (public domain or established translations)
- Government technical reports (DTIC, NIST, DoD publications)

### Tier 2 — Academic / Peer-Reviewed
- IEEE, arxiv (with peer-reviewed status noted), JSTOR, Google Scholar
- Established academic publishers (Springer, Cambridge UP, Oxford UP, Wiley)
- Operations Research journals (Military Operations Research Society, INFORMS)
- Signal processing, control theory, and applied mathematics textbooks
- Defense-focused academic journals (Journal of Defense Modeling and Simulation, Naval Research Logistics)

### Tier 3 — Validated Reference
- Jane's Information Group (defense reference data)
- Established military history publishers (Osprey, Stackpole, Casemate)
- Well-sourced encyclopedia articles (as starting points to find primary sources — never terminal)
- Congressional Research Service reports
- Reputable defense analysis outlets (War on the Rocks, RUSI, IISS)

### Excluded
- Unverified blogs, personal websites, forums
- Unsourced claims from any origin
- Gaming wikis, hobbyist wargame forums (inspiration only, never for parameterization)
- Social media posts, YouTube commentary
- Any source that cannot provide a verifiable citation chain

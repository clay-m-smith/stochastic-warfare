# Stochastic Warfare — Repository Skills & Hooks

The phase workflows are available on both supported agent surfaces:

- Codex discovers the maintained repository routes in `.agents/skills/`;
  invoke them as `$skill-name`.
- Claude Code retains the legacy routes in `.claude/skills/`; invoke them as
  `/skill-name`.

`CODEX.md` defines where each Codex skill belongs in the phase workflow. The
Codex ports preserve the useful domain procedures while replacing
Claude-specific tool metadata, `$ARGUMENTS` placeholders, and stale completion
rules with the current production-path evidence contract.

## Codex Phase Routing

| Phase gate | Codex skills |
|---|---|
| Define | `$spec`; add `$research-military`, `$research-models`, and `$design-review` when their evidence domains apply |
| Implement | Task-specific routes such as `$scenario` and `$orbat` |
| Validate | `$validate-conventions`, `$audit-determinism`, `$validate-data`, and `$profile` when applicable |
| Prove outcomes | `$evaluate-scenarios`, `$backtest`, `$compare`, `$what-if`, `$calibrate`, and `$timeline` when applicable |
| Review | `$simplify` for production-code phase diffs |
| Close | `$update-docs` → `$cross-doc-audit` → `$postmortem` → verified phase commit |

The route details and applicability rules in `CODEX.md` are authoritative.
Skills augment that contract; they do not replace production-path behavioral
evidence. `tests/unit/test_repository_skills.py` verifies that every legacy
Claude route has a discoverable Codex port with portable frontmatter and
matching UI metadata.

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
  - `CODEX.md` and `AGENTS.md` — durable repository workflow when it changes
  - `docs/remediation-backlog.md` — current implementation gaps and evidence
  - **User-facing docs** (Phase 31+) — `docs/index.md`, `docs/guide/`, `docs/concepts/`, `docs/reference/`, `mkdocs.yml`
- Discovers the current block roadmap instead of assuming the original
  post-MVP document owns later phases
- Updates only affected documents, using fresh verification for status and test
  counts
- New deficits are recorded in the remediation backlog and assigned to a
  roadmap phase
- **User-facing doc rules** (Phase 31+): new modules update architecture.md; new scenarios update scenarios.md + eras.md; new units update units.md; API changes update api.md; new devlogs require mkdocs.yml nav entry; test count changes update index.md
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
- Audits alignment across all documentation layers — every discovered block
  roadmap, current specifications, remediation evidence, and user-facing docs:
  - Internal: CODEX.md, development-phases*.md, project-structure.md, brainstorm docs, phase devlogs, remediation backlog, README.md
  - Historical provider context: CLAUDE.md, checked for alignment but never used
    as behavioral authority
  - User-facing (Phase 31+): index.md, guide/, concepts/, reference/, mkdocs.yml
- Verifies capability and status claims against source and fresh command
  evidence rather than repeated documentation text
- Output: PASS/FAIL/N/A per applicable check with severity and exact evidence
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

### /scenario (Phase 14, updated)
- Interactive walkthrough for creating or editing campaign scenario YAML files
- Guides user through sides, units, terrain, objectives, victory conditions, and calibration
- Verifies all equipment against authoritative definitions and traces mapping
  semantics into the production loader; never adds an unrelated proxy mapping
  or invented default merely to satisfy a validator
- Runs `scripts/validate_scenario_data.py --file`, verifies exact roster and
  loadouts through the production factory/session boundary, and exercises
  required behavior through a bounded `RuntimeSession`
- Treats mapping presence and aggregate armed/sensored counts as structural
  diagnostics, not outcome evidence
- Validates against `CampaignScenarioConfig` schema
- Outputs complete scenario YAML to `data/scenarios/{name}/scenario.yaml`

### /compare (Phase 14)
- Prepares one source scenario and compares two strict sparse calibration
  variants with the same ordered seeds and metrics
- Uses `tools/comparison.py` for exact common-seed paired differences, paired
  superiority, exact sign-test p-values, and Holm family correction
- Retains both raw metric vectors plus source/config, code/data/catalog,
  doctrine/loadout, roster, assignment, seed, and terminal-run provenance
- Rejects unsupported metrics, incomplete/nonfinite runs, roster drift, or
  ineffective runtime preflight instead of producing summary-only output

### /what-if (Phase 14)
- Quick parameter sensitivity analysis from natural language questions
- Identifies parameter and range from user's question
- Requires a real `CalibrationSchema` field, finite duplicate-free values, at
  least two iterations per point, and an explicit schema-valid scenario
- Uses the production factory/session route through `tools/sensitivity.py`,
  retaining each point's raw vectors and provenance
- Summarizes sensitivity and inflection points only after the configured field
  is proven wired and outcome-affecting

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
- Sweeps wired influential parameters through the production analysis boundary
- Uses binary search refinement to narrow to target value
- Requires a frozen source-backed backtest envelope, predeclared tolerances,
  held-out validation seeds, and exact production provenance
- Phase 112 implements REM-017's shared analysis boundary; the remediation
  status changes only after the final phase gate. That boundary does not itself
  validate history. Catalog-wide historical-envelope evidence remains queued
  under REM-030

### /validate-data
- Validates unit YAML and scenario YAML data integrity
- Catches equipment name → weapon/sensor ID mapping drift, missing sensor entries, invalid unit type references, broken ScenarioLoader loads
- Runs `scripts/validate_scenario_data.py` (standalone validation script)
- Diagnoses mapping, schema, loader, and runtime attachment defects without
  guessing substitutions or generic defaults
- **Run after**: adding new units, weapons, scenarios, or modifying equipment entries
- The simplified-runner maps are static diagnostics; production evidence comes
  from `SimulationRuntimeFactory -> PreparedScenario -> RuntimeSession`, exact
  affected loadouts, and behavioral execution

### /evaluate-scenarios (Phase 42)
- Runs all scenarios through simulation engine and compares against previous baseline
- Reports winner changes, casualty deltas, condition changes, new/resolved issues
- Classifies changes as improvements, regressions, stalls, or neutral
- Saves new baseline for future comparisons
- Records explicit seed/revision/catalog provenance and requires investigation
  before promoting a baseline
- Uses a real engine path but does not by itself prove API wiring,
  reinforcement registration, deterministic replay, or stochastic fidelity
- **Run after**: completing any phase that modifies battle loop, engagement resolution, or victory evaluation
- Key files: `scripts/evaluate_scenarios.py`, `scripts/evaluation_results_v*.json`

### /postmortem (Phase 14)
- Structured retrospective to run after completing each implementation phase
- Gates phase closure against the completion evidence matrix, production-path
  tests, negative controls, relevant excluded suites, final diff, and
  adversarial review
- Catches integration gaps, dead modules, missing wiring, undocumented limitations
- Adds newly found gaps to the remediation backlog, updates the phase devlog,
  and permits the coherent phase commit only after all applicable gates pass

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
- **Trigger**: when a unit definition or scenario YAML is created or modified
- **Checks**:
  - Validates against the pydantic schema for that unit class (id field, numeric types, probability ranges)
  - **Equipment category validation**: all `category` values must be valid `EquipmentCategory` enum values (WEAPON, SENSOR, PROPULSION, PROTECTION, COMMUNICATION, NAVIGATION, UTILITY, POWER — NOT "TOOL")
  - **Sensor presence check**: warns if unit YAML has no `category: SENSOR` equipment entry
  - **Equipment name sanity**: flags obviously malformed weapon equipment names
  - **Scenario unit_type validation**: flags `unit_type` values that look like display names instead of valid IDs
- **Action**: block write if structural issues found; warn on missing sensors

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

# Phase Postmortem

Structured retrospective to run after completing each implementation phase. Catches integration gaps, dead code, missing wiring, test quality issues, and documentation drift before moving on.

## Trigger
Run after completing a phase — before the commit, after tests pass and docs are updated.

## Process

### 1. Delivered vs Planned
Compare what was actually delivered against the plan:
- Read the phase section in `docs/development-phases-post-mvp.md` (or `development-phases.md` for MVP)
- Read the phase devlog in `docs/devlog/phase-{N}.md`
- List any planned items that were **dropped, deferred, or descoped**
- List any **unplanned items** that were added
- Verdict: was the scope well-calibrated?

### 2. Integration Audit
Check that new code is actually wired into the system, not just standalone:
- For each new module: is it imported/used by at least one other module or test?
- For new engine features: are they exercised in `simulation/engine.py` or `simulation/battle.py`?
- For new config flags: do they appear in any scenario YAML or test?
- For new event types: does something publish them AND something subscribe?
- For new skills: are they listed in CLAUDE.md's skill table AND `docs/skills-and-hooks.md`?
- **Red flag**: Any source file that exists but is never imported (dead module)

### 3. Test Quality Review
Spot-check test coverage quality (not just count):
- Are there integration tests that exercise cross-module paths, or only unit tests?
- Do tests use realistic data or only trivial/mock data?
- Are edge cases covered (empty inputs, error paths, boundary values)?
- Are any tests testing implementation details rather than behavior?
- Do slow/heavy tests have appropriate marks (`@pytest.mark.slow`)?

### 4. API Surface Check
Review public APIs of new modules:
- Are type hints on all public functions?
- Are there any functions that are public but should be private (`_` prefix)?
- Do function signatures follow project conventions (DI pattern, no global state)?
- Is `get_logger(__name__)` used (no bare `print()`)?

### 5. Deficit Discovery
Look for new limitations or known issues introduced by this phase:
- Any TODOs or FIXMEs in the new code?
- Any hardcoded values that should be configurable?
- Any known simplifications or shortcuts?
- Any missing error handling at system boundaries?
- **For each deficit found**: add to `docs/devlog/index.md` refinement index AND assign to a future phase in `development-phases-post-mvp.md`

### 6. Documentation Freshness
Verify the lockstep docs are accurate (not just updated — *accurate*):
- Does CLAUDE.md's phase summary match what was actually built?
- Does the module-to-phase index include ALL new files?
- Does MEMORY.md reflect key learnings (not just copy-paste from devlog)?
- Does README.md test count match `pytest --co -q | tail -1`?
- Are all new skills in both CLAUDE.md skill table AND skills-and-hooks.md?
- **User-facing docs staleness check** (if the phase changed any of the following):
  - New modules/engines → is `docs/concepts/architecture.md` updated?
  - Changed class signatures → is `docs/reference/api.md` still accurate?
  - New scenarios → are `docs/guide/scenarios.md` and `docs/reference/eras.md` updated?
  - New units/weapons/doctrines → is `docs/reference/units.md` updated?
  - New era mechanics → is `docs/reference/eras.md` updated?
  - New math models → is `docs/concepts/models.md` updated?
  - Test count changed → is `docs/index.md` updated?
  - New devlog file → is `mkdocs.yml` nav updated?

### 7. Performance Sanity
Quick check that the phase didn't introduce performance issues:
- Run `uv run python -m pytest --tb=short -q` — note total time
- Compare to previous phase total time (from devlog or memory)
- If >10% slower, investigate which new tests are heavy

### 8. Summary
Write a brief postmortem summary:
- **Scope**: On target / Under / Over
- **Quality**: High / Medium / Needs work
- **Integration**: Fully wired / Gaps found
- **Deficits**: N new items (list them)
- **Action items**: What needs to happen before moving on

## Output
Update the phase devlog with a `## Postmortem` section containing the findings. If action items exist, implement them before committing.

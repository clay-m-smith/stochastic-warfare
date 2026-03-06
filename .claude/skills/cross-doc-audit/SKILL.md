---
name: cross-doc-audit
description: Audit alignment across all documentation layers — MVP docs, post-MVP docs, AND user-facing docs site (index.md, guide/, concepts/, reference/, mkdocs.yml). 19 checks covering module coverage, phase content, deficits, API accuracy, scenario catalogs, era/unit references, and MkDocs nav completeness. Run after completing a phase, adding modules, or changing architecture.
allowed-tools: Read, Grep, Glob, Agent, Write, Edit, Bash
---

# Cross-Document Consistency Audit

You are auditing the design documents of the Stochastic Warfare project for internal consistency.

## Trigger
Run this audit:
- After completing any development phase
- After adding new modules to `project-structure.md`
- After making architecture decisions that affect multiple documents
- When the user asks to verify documentation alignment
- Periodically as a health check during development

## Documents to Audit

### MVP Documents
| Document | Path | Role |
|----------|------|------|
| Development Phases | `docs/development-phases.md` | WHAT gets built WHEN (Phases 0–10) |
| Project Structure | `docs/specs/project-structure.md` | WHAT exists and HOW it works |
| Brainstorm | `docs/brainstorm.md` | WHY decisions were made |
| Dev Log | `docs/devlog/phase-*.md` | WHAT actually happened |
| Memory | `.claude/memory/MEMORY.md` | Cross-session context |
| README | `README.md` | Public-facing project summary |

### Post-MVP Documents
| Document | Path | Role |
|----------|------|------|
| Post-MVP Phases | `docs/development-phases-post-mvp.md` | WHAT gets built WHEN (Phases 11–22) |
| Post-MVP Brainstorm | `docs/brainstorm-post-mvp.md` | Design thinking for post-MVP domains |
| Devlog Index | `docs/devlog/index.md` | Phase status tracking + deficit inventory |

### User-Facing Documentation (MkDocs Site)
| Document | Path | Role |
|----------|------|------|
| Site Landing Page | `docs/index.md` | Project overview, capabilities, status for docs site visitors |
| Getting Started | `docs/guide/getting-started.md` | Installation, first scenario, code examples |
| Scenario Library | `docs/guide/scenarios.md` | Scenario catalog, YAML format reference |
| Architecture | `docs/concepts/architecture.md` | Public-facing architecture explanation |
| Math Models | `docs/concepts/models.md` | 10 stochastic models with formulas |
| API Reference | `docs/reference/api.md` | Key class signatures, usage patterns |
| Era Reference | `docs/reference/eras.md` | 5 eras: mechanics, units, scenarios |
| Units & Equipment | `docs/reference/units.md` | Unit/weapon/ammo schemas and catalogs |
| MkDocs Config | `mkdocs.yml` | Site navigation structure |

## Checks to Perform (in order)

### 1. Module Coverage
For every module file in project-structure.md's package tree, verify it appears in the Module-to-Phase Index at the bottom of development-phases.md. Report any orphaned modules.

### 2. Phase Content Match
For every phase in development-phases.md, verify every module listed in that phase's bullet points also appears in project-structure.md's package tree. Report any phantom modules (listed in phases but not in structure).

### 3. Dependency Ordering
Using the dependency graph in project-structure.md, verify that development-phases.md builds modules in valid dependency order. A phase must not require modules from a later phase.

### 4. Exit Criteria Coverage
For each phase, verify the exit criteria test ALL capabilities that phase promises to deliver. Flag any phase where deliverables exceed what the exit criteria test.

### 5. Contradictions
Find any direct contradictions between documents:
- Something "deferred" in one doc but "in scope" in another
- Feature described differently in two docs
- Module responsibilities that conflict

### 6. Brainstorm Traceability
Verify that every major system/feature in brainstorm.md has a home in project-structure.md. Verify modeling concepts are annotated with their implementation module.

### 7. Devlog Completeness
For each completed phase, verify the devlog entry exists and covers: what was built, design decisions, deviations from plan, issues/fixes.

### 8. Memory Freshness
Verify MEMORY.md reflects current project status (correct phase, key decisions up to date).

### 9. README Currency
Verify README.md is consistent with CLAUDE.md and development-phases.md:
- Python version requirement matches
- Test count matches current total
- Phase table status matches (all phases listed, correct completion status)
- Architecture summary (module dependency chain, simulation loop, spatial model) matches CLAUDE.md
- Key dependencies table matches actual `pyproject.toml` runtime deps

### 10. Post-MVP Deficit Traceability
Every item in `devlog/index.md` Post-MVP Refinement Index must appear in the Deficit-to-Phase Mapping table in `development-phases-post-mvp.md`. Each must be assigned to a phase number, "Deferred" with rationale, "Won't fix" with rationale, or "Resolved" with phase reference. Report orphaned deficits.

### 11. Post-MVP Cross-Document Alignment
Verify alignment between `brainstorm-post-mvp.md` and `development-phases-post-mvp.md`:
- Every domain/capability discussed in the brainstorm has a corresponding phase in the roadmap
- Module lists in phase definitions match the brainstorm's proposed modules
- No contradictions between brainstorm design thinking and phase exit criteria
- Phase prerequisites are consistent (e.g., Phase 20 WW1 requires Phase 17 CBRN)

### 12. Post-MVP Module Coverage
For every module in the Post-MVP Module-to-Phase Index in `development-phases-post-mvp.md`, verify it appears in a phase's bullet list. Report orphaned modules. (Mirrors Check 1 for post-MVP scope.)

### 13. Post-MVP Devlog Completeness
For each completed post-MVP phase (11+), verify a devlog entry exists at `docs/devlog/phase-{N}.md` and covers: what was built, design decisions, deviations from plan, issues/fixes, known limitations. Verify the devlog index table in `docs/devlog/index.md` has the correct status for each post-MVP phase.

### 14. User-Facing Docs — Status & Counts
Verify `docs/index.md` reflects current project status:
- Test count matches actual test count from README.md and CLAUDE.md
- Phase/block completion status matches (same as README)
- YAML/unit/scenario counts are not stale (compare against actual file counts in `data/`)
- Badge text matches README badges

### 15. User-Facing Docs — Architecture Accuracy
Verify `docs/concepts/architecture.md` is consistent with CLAUDE.md and `docs/brainstorm.md`:
- Module dependency chain matches (12 modules in same order)
- Tick resolution table matches (strategic/operational/tactical seconds)
- Additional domain module table lists all current domain packages
- Optional subsystem list is complete (every null-config-gated engine)
- Era table includes all eras with correct date ranges

### 16. User-Facing Docs — API Accuracy
Verify `docs/reference/api.md` class signatures match actual source code:
- Spot-check constructor signatures for `ScenarioLoader`, `SimulationEngine`, `EngineConfig`, `SimulationRecorder`, `VictoryEvaluator`, `MonteCarloHarness` against source files
- Verify `EngineConfig` fields and defaults match actual pydantic model
- Verify `VictoryResult` fields match actual dataclass
- Verify code examples in usage patterns are syntactically valid

### 17. User-Facing Docs — Scenario Catalog Completeness
Verify `docs/guide/scenarios.md` lists all scenarios:
- Count scenario YAML files in `data/scenarios/*/scenario.yaml` and `data/eras/*/scenarios/*/scenario.yaml`
- Compare against the scenario tables in the guide
- Flag any scenarios not listed or any listed scenarios that don't exist
- Verify era scenario counts in `docs/reference/eras.md` match actual era scenario directories

### 18. User-Facing Docs — Era & Unit Accuracy
Verify `docs/reference/eras.md` and `docs/reference/units.md`:
- Era-specific mechanics described match the engine extensions that exist in source
- Unit catalogs are not missing major unit types (spot-check against `data/units/` and `data/eras/*/units/`)
- Doctrine template table lists all doctrines in `data/doctrine/`
- Commander profile table lists all profiles in `data/commander_profiles/`

### 19. MkDocs Nav Completeness
Verify `mkdocs.yml` nav includes all docs:
- Every `.md` file in `docs/` is either in the nav or intentionally excluded
- All devlog phase files listed match actual files in `docs/devlog/`
- Build `mkdocs build --strict` passes with no "pages exist but not in nav" warnings

## Output Format

For each check, report:
- **PASS** or **FAIL** with specific items
- For FAILs: the exact documents and lines that are misaligned
- Severity: CRITICAL (blocks development), HIGH (significant gap), MEDIUM (should fix), LOW (cosmetic)

## After the Audit

If issues are found:
1. Present the findings to the user
2. Ask which issues to fix now vs defer
3. Fix approved issues across all affected documents
4. Update the devlog with the audit results and fixes applied

$ARGUMENTS

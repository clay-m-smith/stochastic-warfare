---
name: cross-doc-audit
description: Audit alignment between development-phases.md, project-structure.md, brainstorm.md, and the devlog. Run after completing a phase, adding modules, or changing architecture. Catches contradictions, missing phase assignments, and stale documentation.
allowed-tools: Read, Grep, Glob, Agent, Write, Edit
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

| Document | Path | Role |
|----------|------|------|
| Development Phases | `docs/development-phases.md` | WHAT gets built WHEN |
| Project Structure | `docs/specs/project-structure.md` | WHAT exists and HOW it works |
| Brainstorm | `docs/brainstorm.md` | WHY decisions were made |
| Dev Log | `docs/devlog/phase-*.md` | WHAT actually happened |
| Memory | `.claude/memory/MEMORY.md` | Cross-session context |

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

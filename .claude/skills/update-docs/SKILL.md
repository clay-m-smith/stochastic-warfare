---
name: update-docs
description: Update project documentation to reflect new design decisions, completed modules, or changed architecture. Keeps brainstorm docs, specs, and memory in sync with implementation.
allowed-tools: Read, Grep, Glob, Edit, Write
---

# Documentation Updater

You are updating documentation for the Stochastic Warfare project to keep it in sync with development.

## Task
$ARGUMENTS

## Documentation Locations

| Document | Path | Purpose |
|----------|------|---------|
| Brainstorm | `docs/brainstorm.md` | Architecture decisions, domain decomposition, design rationale |
| Module Specs | `docs/specs/<module>.md` | Per-module specifications (inputs, outputs, interfaces, models) |
| Project Structure | `docs/specs/project-structure.md` | Module tree, responsibilities, dependency graph |
| Dev Phases | `docs/development-phases.md` | Development roadmap, phase tracking, module-to-phase index |
| Dev Log | `docs/devlog/phase-*.md` | Rolling per-phase implementation log |
| Skills & Hooks | `docs/skills-and-hooks.md` | Development infrastructure documentation |
| Memory | `.claude/memory/MEMORY.md` | Cross-session persistent context (keep under 200 lines) |
| Detailed Memory | `.claude/memory/<topic>.md` | Topic-specific detailed notes |

**Related skill**: `/cross-doc-audit` — run after major changes to verify alignment across all documents.

## Rules
1. **Never duplicate information** — if something is in brainstorm.md, don't repeat it in memory. Cross-reference instead.
2. **Memory must stay concise** — MEMORY.md is loaded every session; keep it under 200 lines. Move details to topic files.
3. **Decisions go in brainstorm.md** — any architecture or design decision with rationale.
4. **Specs are contracts** — once a spec is written and implementation matches, only update if the interface actually changes.
5. **Mark what changed** — when updating, briefly note what was added/changed and why.
6. **Don't remove history** — if a decision is superseded, mark it as such rather than deleting. Context for past decisions is valuable.

## Process
1. Read the current state of the relevant document(s)
2. Identify what needs to be added, updated, or cross-referenced
3. Make the edits
4. Verify consistency across documents (no contradictions)
5. Report what was changed

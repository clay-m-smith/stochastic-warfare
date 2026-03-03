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

### MVP Documents
| Document | Path | Purpose |
|----------|------|---------|
| Brainstorm | `docs/brainstorm.md` | Architecture decisions, domain decomposition, design rationale |
| Module Specs | `docs/specs/<module>.md` | Per-module specifications (inputs, outputs, interfaces, models) |
| Project Structure | `docs/specs/project-structure.md` | Module tree, responsibilities, dependency graph |
| Dev Phases | `docs/development-phases.md` | MVP development roadmap (Phases 0–10), module-to-phase index |
| Dev Log | `docs/devlog/phase-*.md` | Rolling per-phase implementation log |
| Skills & Hooks | `docs/skills-and-hooks.md` | Development infrastructure documentation |
| Memory | `.claude/memory/MEMORY.md` | Cross-session persistent context (keep under 200 lines) |
| Detailed Memory | `.claude/memory/<topic>.md` | Topic-specific detailed notes |

### Post-MVP Documents
| Document | Path | Purpose |
|----------|------|---------|
| Post-MVP Brainstorm | `docs/brainstorm-post-mvp.md` | Design thinking for post-MVP domains (EW, CBRN, eras, tooling) |
| Post-MVP Phases | `docs/development-phases-post-mvp.md` | Post-MVP roadmap (Phases 11–22), deficit-to-phase mapping |
| Devlog Index | `docs/devlog/index.md` | Phase status tracking + deficit inventory (covers all phases) |

**Related skill**: `/cross-doc-audit` — run after major changes to verify alignment across all documents.

## Rules
1. **Never duplicate information** — if something is in brainstorm.md, don't repeat it in memory. Cross-reference instead.
2. **Memory must stay concise** — MEMORY.md is loaded every session; keep it under 200 lines. Move details to topic files.
3. **Decisions go in brainstorm.md** — any architecture or design decision with rationale. Post-MVP design thinking goes in `brainstorm-post-mvp.md`.
4. **Specs are contracts** — once a spec is written and implementation matches, only update if the interface actually changes.
5. **Mark what changed** — when updating, briefly note what was added/changed and why.
6. **Don't remove history** — if a decision is superseded, mark it as such rather than deleting. Context for past decisions is valuable.
7. **Post-MVP lockstep** — when completing a post-MVP phase (11+), ALL of the following must be updated together: CLAUDE.md, project-structure.md, `development-phases-post-mvp.md` (phase status + module index), `devlog/index.md` (phase status + any new refinement entries), phase devlog (`docs/devlog/phase-{N}.md`), README.md, MEMORY.md. The deficit-to-phase mapping in `development-phases-post-mvp.md` must also be updated if any deficits are resolved.
8. **New deficits feed back** — any limitation discovered during post-MVP implementation must be added to `devlog/index.md` AND assigned to a phase in the deficit-to-phase mapping in `development-phases-post-mvp.md`.

## Process
1. Read the current state of the relevant document(s)
2. Identify what needs to be added, updated, or cross-referenced
3. Make the edits
4. Verify consistency across documents (no contradictions)
5. Report what was changed

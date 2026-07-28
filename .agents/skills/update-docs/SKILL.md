---
name: update-docs
description: "Synchronize documentation with verified behavior. Use after changes to contracts, architecture, APIs, data, scenarios, phase status, remediation status, or public capabilities and before closing a numbered phase."
---

# Update Project Documentation

Follow the documentation routing and evidence rules in `CODEX.md`. Update
documents from verified production behavior, not from historical claims or
structural checks.

## Determine the Required Documents

1. Discover the applicable roadmap from `docs/development-phases*.md`; do not
   assume the change belongs to the original MVP or post-MVP files.
2. Read the current phase devlog, remediation entry, specification, affected
   source, tests, and existing user documentation.
3. Identify every public or internal claim changed by the verified behavior.
4. Preserve historical records. Mark superseded decisions or status explicitly
   instead of rewriting history.

Use `CODEX.md`'s documentation map to route changes. Common phase-close updates
include:

- the relevant specification for a changed contract;
- architecture and project-structure pages for wiring or module changes;
- API schemas, client types, and API reference for boundary changes;
- scenario, era, unit, or equipment references for data changes;
- the phase devlog and `docs/devlog/index.md`;
- `docs/remediation-backlog.md` for newly surfaced or closed gaps;
- `README.md` and `docs/index.md` for verified public capability or status
  changes;
- `mkdocs.yml` for new site pages.

Treat `CLAUDE.md` as legacy provider context. Align overlapping durable rules
only when it is intentionally maintained; never use it as behavioral evidence.
Do not create or update provider memory files.

## Reconcile Claims

- Use a fresh command result for status and test-count changes. Never use test
  collection, a stale results file, or another agent's summary as a passing
  count.
- State exclusions, skips, warnings, and residual limitations next to the
  affected claim.
- Do not mark a phase or remediation item complete until every applicable
  completion stage has evidence.
- Cross-reference a single authoritative explanation instead of duplicating
  large status, design, or limitation sections.
- Keep public examples consistent with current signatures and typed schemas.

## Validate

Review the documentation diff against the source and original requirements.
Check links, phase numbers, status tables, navigation, and direct
contradictions. Run:

```powershell
uv run --extra docs mkdocs build --strict
git diff --check
```

Use `$cross-doc-audit` after the edits. Report exact validation results and any
claims that remain intentionally unverified.

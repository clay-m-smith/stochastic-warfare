---
name: cross-doc-audit
description: "Audit documentation against implementation and current evidence. Use after a phase, architecture or API change, data/catalog update, documentation rewrite, or when status and capability claims may have drifted."
---

# Audit Documentation Consistency

Follow `CODEX.md`. Perform this audit read-only unless the user or current
implementation task separately authorizes remediation.

## Build the Audit Inventory

1. Discover all roadmaps with
   `rg --files docs -g 'development-phases*.md'`.
2. Identify the current block and phase from its roadmap,
   `docs/devlog/index.md`, and the phase devlog.
3. Include `CODEX.md`, `docs/remediation-backlog.md`, specifications,
   architecture pages, README, the MkDocs site, API reference, and affected
   catalogs.
4. Treat production source, typed schemas, data files, and fresh command
   results as evidence. Treat legacy provider context and repeated
   documentation claims as items to verify.

## Perform the Checks

Report `PASS`, `FAIL`, or `N/A` with a written reason for each applicable area:

1. **Roadmap and devlog alignment**: planned scope, status, phase index,
   deviations, and known limitations agree.
2. **Remediation traceability**: every surfaced gap has an owner/status and
   closed items link to sufficient evidence.
3. **Contract accuracy**: specifications match typed interfaces, validation,
   failure semantics, state, and persistence.
4. **Production evidence**: declared, loaded, wired, enabled, exercised,
   outcome-affecting, and persisted/exposed claims are supported at every
   applicable stage.
5. **Architecture accuracy**: dependency direction, production path, module
   ownership, optional gates, and stateful dependencies match source.
6. **API accuracy**: documented signatures, models, defaults, response fields,
   examples, and frontend types match the real boundary.
7. **Data and catalog accuracy**: scenario, era, unit, equipment, doctrine,
   commander, and organization listings match actual files and semantics.
8. **Public status accuracy**: capability, phase, test, scenario, and catalog
   claims have fresh evidence and disclose exclusions and limitations.
9. **Navigation and links**: new pages are routed correctly, referenced files
   exist, and internal links resolve.
10. **Provider-context alignment**: intentionally maintained legacy guidance
    does not contradict `CODEX.md`.

Do not accept imports, constructors, source-string searches, mocks, no-crash
runs, or matching documentation text as behavioral proof.

For a claimed current test count, run the applicable fresh test command or mark
the count unverified. Do not substitute `--collect-only`. Run the strict
documentation build:

```powershell
uv run --extra docs mkdocs build --strict
```

## Report Findings

For every failure, provide severity, exact file and line, the conflicting
evidence, and the smallest coherent remediation. Separate:

- phase blockers;
- tracked limitations;
- stale or misleading public claims;
- cosmetic cleanup.

Do not edit files as part of a read-only audit. Hand authorized fixes to
`$update-docs`, then rerun the failed checks against the resulting diff.

---
name: spec
description: "Define or revise an implementation contract. Use before changing a module, API, configuration field, simulation behavior, numbered phase, or defect remediation when requirements and proof obligations must be explicit."
---

# Define the Contract

Follow `CODEX.md` as the repository-wide authority. Keep this skill focused on
turning a requested change into an implementable, testable contract.

## Establish Context

1. Identify the current numbered phase, if any, by inspecting the applicable
   `docs/development-phases*.md` file and `docs/devlog/phase-*.md`.
2. Read the relevant remediation entry, existing specification, architecture
   page, public documentation, production code, and tests.
3. Trace the behavior through the real production path. Record disagreements
   between documentation, tests, and implementation.
4. Resolve requirements from repository evidence and user intent. Ask the user
   only when a missing decision would materially change the contract.

## Write the Specification

Update the existing contract or create `docs/specs/<topic>.md` when the change
needs a durable specification. For a narrowly scoped remediation, keep the
authoritative requirements in the remediation entry and cross-reference them
from the phase devlog rather than creating a redundant document.

Address these sections:

- **Purpose and scope**: State the observable capability and affected boundary.
- **Requirements**: Use precise types, units, ranges, ordering, and timing.
- **Acceptance criteria**: Describe externally observable pass conditions.
- **Non-goals**: Name adjacent behavior that remains unchanged.
- **Interfaces and dependencies**: Identify inputs, outputs, callers, and
  stateful dependencies.
- **Production trace**: Trace declared, loaded, wired, enabled, exercised,
  outcome-affecting, and persisted/exposed stages. Give a written reason for
  every `N/A`.
- **State and persistence**: Identify all mutable state, object-identity
  requirements, checkpoint behavior, and compatibility boundaries.
- **Configuration and failures**: Define defaults, validation, disabled
  behavior, corrupt input behavior, and atomicity requirements.
- **Stochastic and military basis**: Name RNG streams, distributions,
  assumptions, authoritative sources, and calibration requirements when
  applicable.
- **Verification plan**: Specify the initial failing behavioral proof,
  production-path tests, negative controls, deterministic replay, checkpoint,
  scenario, statistical, API, frontend, data, documentation, and performance
  checks that apply.
- **Open decisions**: Separate unresolved decisions from accepted limitations.

## Review the Contract

Check that each acceptance criterion has a planned behavioral proof and that no
structural check is presented as integration or outcome evidence. Do not mark a
specification implemented or a phase complete during this step.

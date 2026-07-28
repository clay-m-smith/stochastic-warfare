# Repository Agent Instructions

Read and follow `CODEX.md` completely before inspecting, changing, testing, or
reporting on this repository. `CODEX.md` is the canonical repository guidance.

Repository workflow skills are versioned under `.agents/skills/`. For every
numbered phase, follow the skill gates in `CODEX.md`; invoke Codex skills as
`$skill-name` and read the selected `SKILL.md` completely before acting.

The phase-closing sequence is `$update-docs`, `$cross-doc-audit`, then
`$postmortem`, followed by the verified phase commit. Use `$simplify` before
closure whenever production code changed, plus every conditional validation
route that applies to the phase. A skill report is not evidence until its
claims are checked against the production path and fresh command results.

Any nested `AGENTS.md` augments these instructions for its subtree; it does not
override repository invariants without an explicit explanation.

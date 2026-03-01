---
name: spec
description: Draft or update a module specification before implementation. Use before writing any new simulation module. Enforces specify-before-implement discipline.
allowed-tools: Read, Grep, Glob, Edit, Write, WebSearch, WebFetch
---

# Module Specification Writer

You are writing a specification for a simulation module in the Stochastic Warfare project. Specs are written BEFORE implementation and serve as the contract that code must satisfy.

## Module
$ARGUMENTS

## Specification Template

Write the spec to `docs/specs/<module_name>.md` using this structure:

```markdown
# Module: <Name>
**Status**: Draft | Under Review | Approved | Implemented
**Last Updated**: <date>

## Purpose
What this module does and why it exists. 1-3 sentences.

## Simulation Scale
Which scale(s) this module operates at: Strategic / Operational / Tactical / Unit

## Interfaces

### Inputs
- What data this module receives, from where, in what format
- Include types and units (meters, seconds, probability [0,1], etc.)

### Outputs
- What data this module produces, for whom, in what format

### Dependencies
- Other modules this depends on
- External libraries required

## Stochastic Models
- What random processes are used and why
- Distribution types, parameters, and how they're estimated
- PRNG stream requirements (which subsystem stream)

## Military Theory Basis
- Which theoretical frameworks inform this module's design
- Citations to doctrine, theorist works, or academic sources

## State
- What state this module maintains between ticks
- Serialization requirements for checkpointing

## Configuration
- What YAML-configurable parameters this module exposes
- Default values and valid ranges

## Validation Criteria
- How do we know this module is working correctly?
- Historical data to backtest against (if applicable)
- Edge cases and boundary conditions

## Open Questions
- Unresolved design decisions
- Areas needing further research
```

## Rules
1. Every field must be addressed — use "N/A" or "TBD" if genuinely not applicable or not yet known
2. Be specific about types, units, and ranges — vague specs produce vague implementations
3. Cross-reference the architecture decisions in `docs/brainstorm.md` for consistency
4. Reference relevant military theory from the theorist foundations section
5. If research is needed before the spec can be completed, say so explicitly and describe what's needed

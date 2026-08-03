---
name: orbat
description: "Design sourced military force structures. Use when creating or editing a scenario force composition, TO&E definition, command hierarchy, attachment plan, or historical order of battle."
---

# Build an Order of Battle

Follow `CODEX.md` and distinguish data definitions from behavior that is proven
to be wired into the production simulation.

## Choose the Artifact

Determine which output the request requires:

- **Scenario composition**: Author the flattened `sides[].units` representation
  accepted by `SideConfig`.
- **TO&E definition**: Author a hierarchical `TOEDefinition` under
  `data/organizations/` for loading through the organization loader.
- **Runtime hierarchy or attachments**: Specify the required organization-tree
  or task-organization behavior and trace how it reaches the production engine.

Do not imply that a flattened scenario unit count preserves echelon hierarchy,
reporting relationships, or attachments.

## Establish the Force

1. Identify side, era, branch, echelon, mission, time period, and requested
   fidelity.
2. Inspect existing unit and organization catalogs before selecting types.
3. Resolve every unit identifier from the actual unit data and verify the
   required equipment exists.
4. Resolve modern commander profiles from `data/commander_profiles/`, historical
   commanders from the applicable era catalog, and doctrine from the matching
   doctrine catalog.
5. Use authoritative organizational tables, doctrine, or historical sources
   for real formations. Record citations, date/version, substitutions, and
   uncertainty. Clearly label hypothetical force structures.
6. Include command, logistics, reconnaissance, air defense, fires, and support
   elements when the mission or source requires them. Do not add them merely to
   make a force appear balanced.
7. Consult `docs/remediation-backlog.md` before claiming that morale, depots,
   reinforcements, commander profiles, doctrine, or other scenario fields
   change runtime outcomes.

## Validate the Result

For a TO&E artifact, load it through the actual organization loader and assert
the expected parent-child structure, counts, identifiers, and attachment
semantics.

For scenario composition, validate the scenario data and use `ScenarioLoader`
only for focused configuration diagnostics. Verify the comparable instantiated
roster and loadouts through `SimulationRuntimeFactory.prepare`, an explicit
prepared variant, and `PreparedScenario.build`. Run a bounded `RuntimeSession`
by either calling `run_to_completion()`, or driving `step()` until terminal and
then calling `finalize()`, when the requested hierarchy or composition is
supposed to affect simulation behavior.

Add negative coverage for invalid unit references, malformed hierarchy, or
unsupported configuration. Update the relevant unit, scenario, organization,
and phase documentation after validation. Report sourcing assumptions and
runtime limitations with the output.

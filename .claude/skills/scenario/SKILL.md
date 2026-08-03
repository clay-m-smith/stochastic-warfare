---
name: scenario
description: "Create or edit campaign scenario YAML and prove its production behavior. Use for new scenarios, scenario configuration changes, validation fixtures, deployments, objectives, victory conditions, or scenario outcome work."
---

# Author a Campaign Scenario

Follow `CODEX.md`, especially its production-path, data-integrity, and
outcome-evidence rules.

## Define the Scenario

1. Inspect the relevant `CampaignScenarioConfig` and nested Pydantic models in
   `stochastic_warfare/simulation/scenario.py`.
2. Inspect comparable scenario YAML and the applicable era catalogs before
   proposing values.
3. Establish the setting, date, era, duration, sides, force composition,
   terrain, deployment, objectives, victory conditions, and enabled optional
   behavior from user intent and available evidence.
4. Ask only for material choices that cannot be recovered safely from the
   repository or supplied sources.

## Select Valid Data

- Resolve every `unit_type` from the exact `unit_type:` field in an existing
  unit definition. Never invent an identifier from a display name.
- Resolve modern commander profiles from `data/commander_profiles/` and
  historical profiles from the applicable `data/eras/<era>/commanders/`
  catalog.
- Resolve doctrine from `data/doctrine/` or the applicable era catalog.
- Inspect every selected unit's equipment. Preserve the real semantics of each
  weapon and sensor; do not substitute an unrelated proxy or add a generic
  sensor merely to satisfy a count.
- If loadout mappings are involved, trace their current use from
  `ScenarioLoader` into the production runtime. Treat mapping presence,
  simplified-runner execution, and non-empty loadout counts as structural
  diagnostics rather than outcome proof.
- Check `docs/remediation-backlog.md` before claiming that a declared scenario
  field affects runtime behavior. State any known wiring limitation explicitly.
- Cite authoritative sources for historical force composition and material
  military assumptions. Label hypothetical scenarios and assumptions clearly.

## Write and Validate

Place modern scenarios under `data/scenarios/<name>/scenario.yaml` and
era-owned scenarios under the applicable era scenario catalog. Match the
current typed schema exactly and reject unsupported fields instead of silently
approximating them.

Run the file-specific data validator:

```powershell
uv run python scripts/validate_scenario_data.py --file <scenario-path>
```

Use `ScenarioLoader` only for focused configuration/load diagnostics. Prove
comparable behavior through `SimulationRuntimeFactory.prepare`, select the
explicit prepared variant, and call `PreparedScenario.build` to obtain a
bounded `RuntimeSession`. Verify exact unit types, counts, concrete classes,
positions, loadouts, configured runtime state, and preparation identities; do
not stop at a no-crash load.

Either call `run_to_completion()`, or drive `step()` until terminal and then
call `finalize()`. Assert the required state transitions, events, resource
changes, or victory outcome and include a contrasting or disabled control.
Repeat through fresh factory-owned sessions with the same seed when determinism
is applicable. Run checkpoint and comparison evaluation when the scenario
exercises mutable or stochastic behavior covered by those contracts.

Run the catalog-wide validator and relevant scenario evaluation before
completion:

```powershell
uv run python scripts/validate_scenario_data.py
uv run python scripts/evaluate_scenarios.py --scenario <scenario-id>
```

Update scenario, era, unit, and phase documentation only after the production
evidence is green. Report exact commands, exclusions, assumptions, and known
runtime limitations.

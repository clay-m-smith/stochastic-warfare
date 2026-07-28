---
name: validate-data
description: Validate scenario, unit, weapon, ammunition, sensor, era, and equipment-mapping data through static checks and the production ScenarioLoader. Use after changing YAML catalogs, scenarios, unit equipment, mapping tables, or typed data schemas, and before committing any data-affecting phase.
---

# Validate Data

Validate the paths named by the user or changed in the current phase. Use
`CODEX.md` for data semantics and evidence requirements. Validation may diagnose
problems, but it must never invent a plausible mapping, sensor, weapon, unit, or
parameter merely to make a check pass.

## Establish Scope

1. Inspect `git status --short` and the phase diff.
2. List the changed scenario, unit, weapon, ammunition, sensor, era, schema, and
   mapping files.
3. Trace each changed value through its typed schema and the production
   `ScenarioLoader`.
4. Identify which units and scenarios must expose or exercise the data.

## Validate During Iteration

For each changed YAML file, run:

```powershell
uv run python scripts/validate_scenario_data.py --file <changed-yaml>
```

Read all errors and warnings. A zero exit code with warnings is not the same as
a warning-free validation.

For an equipment name or definition:

1. Locate the authoritative YAML definition and stable ID with `rg`.
2. Verify domain, era, category, capabilities, assignments, ammunition, and
   sensor/weapon compatibility.
3. Verify exact loader behavior and runtime attachment for the affected unit.
4. Reject unsupported or ambiguous data explicitly.

Do not map to the "closest" definition. Do not add a generic eye, binocular,
weapon, timestamp, position, or other default without an explicit modeled
requirement and traceable source.

## Understand the Existing Validator

`scripts/validate_scenario_data.py` provides two useful but distinct checks:

- static checks against `_WEAPON_NAME_MAP` and `_SENSOR_NAME_MAP` in the
  simplified `stochastic_warfare/validation/scenario_runner.py`;
- load checks through the production
  `stochastic_warfare.simulation.scenario.ScenarioLoader`.

Passing a simplified-runner mapping check does not prove production wiring.
The current load checks require non-empty sides and aggregate armed/sensored
forces; they do not prove every affected unit received the semantically correct
runtime equipment.

For changes to literal mapping tables, also detect duplicate keys that Python
would otherwise overwrite:

```powershell
uv run ruff check stochastic_warfare/validation/scenario_runner.py --select F601
```

## Run the Full Data Gates

After focused fixes, run:

```powershell
uv run python scripts/validate_scenario_data.py
uv run python -m pytest tests/validation/test_phase_30_scenarios.py::TestScenarioFullLoad -q --tb=short -o addopts=
```

Add focused production-path tests that assert the affected units' exact weapon,
ammunition, sensor, equipment, configuration, and runtime behavior. Include
negative tests for unknown, misspelled, incompatible, or incomplete data.

When data can alter combat, movement, detection, victory, or another scenario
outcome, also use `$evaluate-scenarios` and the relevant deterministic,
checkpoint, comparison, or Monte Carlo checks from `CODEX.md`.

## Diagnose Without Papering Over

When validation fails:

- trace the intended semantic identity from authoritative project data and
  cited sources;
- determine whether the defect is in YAML, schema, loader, mapping, or runtime
  wiring;
- change only the layer that is actually wrong;
- verify both the affected item and a negative control;
- report any remaining warnings or uncovered units.

Do not weaken validators or expected outcomes merely to accept current data.

## Report

Report:

- files and data identities checked;
- exact commands, exit codes, error and warning counts;
- evidence for declared, loaded, wired, enabled, exercised,
  outcome-affecting, and persisted/exposed stages;
- scenarios and excluded suites not run;
- unresolved semantic assumptions or limitations.

Only call data integrity complete when the applicable production stages have
behavioral evidence.

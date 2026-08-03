---
name: validate-data
description: Validate scenario, unit, weapon, ammunition, sensor, era, and equipment-mapping data through strict catalog checks, RuntimeLoadoutBuilder, and the production ScenarioLoader. Use after changing YAML catalogs, scenarios, unit equipment, mapping registries, or typed data schemas, and before committing any data-affecting phase.
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
3. Trace each changed value through its typed schema, the production
   `RuntimeLoadoutBuilder`, and `ScenarioLoader`.
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

`scripts/validate_scenario_data.py` uses the current production-owned data
boundaries:

- `EQUIPMENT_MAPPING_REGISTRY` and `EquipmentMappingRegistry` reject duplicate
  keys and enforce exact mapping identity and target semantics;
- `RuntimeLoadoutBuilder` resolves every reachable unit definition against the
  effective base-plus-era weapon, ammunition, and sensor catalogs;
- full-catalog coverage reports every unmapped authored key and stale registry
  key; and
- `ScenarioLoader` loads the affected scenarios through the same catalog and
  loadout composition used by runtime preparation.

Passing registry or load checks proves strict data construction, not that an
attachment changes a production outcome. For mapping changes, run the focused
unit and integration contracts as well:

```powershell
uv run python -m pytest tests/unit/test_phase_109_equipment_mapping.py tests/integration/test_phase_109_equipment_mapping.py -q
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

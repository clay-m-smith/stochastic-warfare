---
name: validate-data
description: Validate unit YAML and scenario YAML data integrity. Catches equipment name drift, missing sensor mappings, invalid unit type references, and broken ScenarioLoader loads. Run after adding or modifying units, weapons, or scenarios.
allowed-tools: Read, Grep, Glob, Bash
---

# Data Integrity Validator

Validates that all unit YAML files and scenario YAML files are internally consistent and will load correctly through ScenarioLoader with armed and sensored units.

## Trigger
Run this validation:
- After adding new unit YAML files
- After adding new scenario YAML files
- After modifying equipment entries in unit YAML
- After adding new weapon or ammo YAML files
- After modifying `_WEAPON_NAME_MAP` or `_SENSOR_NAME_MAP` in `scenario_runner.py`
- When the user asks to validate data integrity
- As a pre-commit sanity check for data changes

## Arguments
$ARGUMENTS

If arguments specify a file path, validate only that file. Otherwise validate everything.

## Process

### 1. Run Validation Script
```bash
uv run python scripts/validate_scenario_data.py
```

Or for a single file:
```bash
uv run python scripts/validate_scenario_data.py --file $ARGUMENTS
```

### 2. If Errors Found, Diagnose and Fix

#### Equipment name not in `_WEAPON_NAME_MAP`
The unit YAML has a `category: WEAPON` equipment entry whose `name` doesn't have a mapping to a weapon definition ID.

**Fix**: Add the mapping to `_WEAPON_NAME_MAP` in `stochastic_warfare/validation/scenario_runner.py` (line ~951).

To find the correct weapon ID:
```bash
# List available weapon definitions
ls data/weapons/*.yaml data/eras/*/weapons/*.yaml 2>/dev/null
# Check the weapon ID inside a file
head -5 data/weapons/<candidate>.yaml
```

Map the equipment name to the closest matching weapon definition ID.

#### Equipment name not in `_SENSOR_NAME_MAP`
Same as above but for `category: SENSOR` equipment.

**Fix**: Add the mapping to `_SENSOR_NAME_MAP` in `stochastic_warfare/validation/scenario_runner.py` (line ~1192).

Available sensor definitions:
```bash
ls data/sensors/*.yaml data/eras/*/sensors/*.yaml 2>/dev/null
```

#### Unit has no SENSOR equipment
The unit YAML has no equipment entry with `category: SENSOR`.

**Fix**: Add a default sensor appropriate to the era:
- Modern/WW2: `{name: "Mk 1 Eyeball", category: SENSOR, weight_kg: 0.0, reliability: 1.0}`
- WW1: `{name: "Field Binoculars", category: SENSOR, weight_kg: 0.5, reliability: 0.99}`
- Napoleonic/Ancient: `{name: "Naked Eye Observation", category: SENSOR, weight_kg: 0.0, reliability: 1.0}`

#### Scenario references non-existent unit_type
The scenario YAML references a `unit_type` that doesn't match any unit YAML's `unit_type` field.

**Fix**: Either create the missing unit YAML or change the scenario to reference an existing unit type. Check available types:
```bash
grep -rh "^unit_type:" data/units/ data/eras/*/units/ 2>/dev/null | sort -u
```

#### Invalid equipment category
A unit YAML uses a `category` value that isn't a valid `EquipmentCategory` enum value.

Valid values: WEAPON, SENSOR, PROPULSION, PROTECTION, COMMUNICATION, NAVIGATION, UTILITY, POWER.
Common mistake: `TOOL` should be `UTILITY`.

### 3. Verify Fix
After fixing, re-run validation:
```bash
uv run python scripts/validate_scenario_data.py
```

### 4. Run Full Load Test
```bash
uv run python -m pytest tests/validation/test_phase_30_scenarios.py::TestScenarioFullLoad -x --tb=short -q
```

All scenarios must pass with armed > 0 and sensored > 0.

## Key Files
| File | Purpose |
|------|---------|
| `scripts/validate_scenario_data.py` | Standalone validation script |
| `stochastic_warfare/validation/scenario_runner.py:951` | `_WEAPON_NAME_MAP` — equipment name → weapon ID |
| `stochastic_warfare/validation/scenario_runner.py:1192` | `_SENSOR_NAME_MAP` — equipment name → sensor ID |
| `stochastic_warfare/entities/equipment.py:15` | `EquipmentCategory` enum |
| `tests/validation/test_phase_30_scenarios.py:729` | `TestScenarioFullLoad` parametrized test |

# Scenario Builder

Interactive walkthrough for creating or editing campaign scenario YAML files.

## Trigger
Use when the user wants to:
- Create a new scenario from scratch
- Edit an existing scenario configuration
- Set up a scenario for testing or validation

## Process

### 1. Gather Requirements
Ask the user for:
- **Scenario name**: Directory name for the scenario
- **Setting**: Geographic region, time period, conflict type
- **Era**: Which era (modern, ww2, ww1, napoleonic, ancient_medieval) — determines available units and weapons
- **Duration**: Campaign length in hours
- **Sides**: Names, unit compositions, experience levels
- **Objectives**: Territory control points, key terrain
- **Victory conditions**: Which conditions to use (territory_control, force_destroyed, time_expired, morale_collapsed, supply_exhausted)

### 2. Select Units
List available unit types from the appropriate era directory using the Glob tool:
- Modern: `data/units/**/*.yaml`
- Historical: `data/eras/{era}/units/**/*.yaml`

For each side:
- Suggest unit types appropriate to the scenario setting
- **CRITICAL**: Verify each `unit_type` value matches exactly a `unit_type:` field in an actual unit YAML file. Do NOT invent unit type names.
- Ask for unit counts
- Set experience levels and morale
- Select commander profile from `data/commanders/` or `data/eras/{era}/commanders/`
- Select doctrine template from `data/doctrine/` or `data/eras/{era}/doctrine/`

### 3. Validate Equipment Mappings (MANDATORY)
Before generating YAML, verify that every unit type selected has proper equipment-to-weapon/sensor mappings:

1. **Read each unit YAML** and check its `equipment:` entries
2. **For each `category: WEAPON` entry**: Verify the `name` exists as a key in `_WEAPON_NAME_MAP` in `stochastic_warfare/validation/scenario_runner.py` (line ~951). If not, either:
   - Add the mapping to `_WEAPON_NAME_MAP` (preferred)
   - Add a `weapon_assignments` entry in the scenario's `calibration_overrides`
3. **For each `category: SENSOR` entry**: Verify the `name` exists as a key in `_SENSOR_NAME_MAP` in `stochastic_warfare/validation/scenario_runner.py` (line ~1192). If not, add the mapping.
4. **If a unit has NO `category: SENSOR` equipment**: Add a default sensor entry appropriate to the era:
   - Modern: `{name: "Mk 1 Eyeball", category: SENSOR, weight_kg: 0.0, reliability: 1.0}`
   - WW2: `{name: "Mk 1 Eyeball", category: SENSOR, weight_kg: 0.0, reliability: 1.0}`
   - WW1: `{name: "Field Binoculars", category: SENSOR, weight_kg: 0.5, reliability: 0.99}`
   - Napoleonic/Ancient: `{name: "Naked Eye Observation", category: SENSOR, weight_kg: 0.0, reliability: 1.0}`
5. **Verify `category` values** are valid `EquipmentCategory` enum values: WEAPON, SENSOR, PROPULSION, PROTECTION, COMMUNICATION, NAVIGATION, UTILITY, POWER. (NOT "TOOL" — use UTILITY instead.)

### 4. Configure Terrain
Options:
- `flat_desert` — open terrain, good for armor
- `open_ocean` — naval scenarios
- `hilly_defense` — defensive terrain with elevation

Set dimensions (width_m, height_m), cell size, and terrain features.

### 5. Set Calibration
Ask about calibration overrides:
- `hit_probability_modifier` (default 1.0)
- `target_size_modifier` (default 1.0)
- `weapon_assignments` — map equipment names to weapon IDs for any weapons not covered by `_WEAPON_NAME_MAP`
- Any scenario-specific adjustments

### 6. Generate YAML
Write the complete scenario YAML to `data/scenarios/{name}/scenario.yaml` following the `CampaignScenarioConfig` schema.

Required fields: `name`, `date`, `duration_hours`, `era`, `terrain`, `sides`, `objectives`, `victory_conditions`.
Each side needs: `side` (name), `units` (list of `{unit_type, count}`), `experience_level`, `morale_initial`.

### 7. Validate (MANDATORY — DO NOT SKIP)
Run the validation script to catch data integrity issues:
```bash
uv run python scripts/validate_scenario_data.py --file data/scenarios/{name}/scenario.yaml
```

If errors are found, fix them before proceeding. Common fixes:
- **WEAPON not in _WEAPON_NAME_MAP**: Add the mapping to `scenario_runner.py`
- **SENSOR not in _SENSOR_NAME_MAP**: Add the mapping to `scenario_runner.py`
- **unit_type not found**: Check spelling matches the YAML file exactly
- **no SENSOR equipment**: Add a default sensor to the unit YAML

Then run the full load test:
```bash
uv run python -c "from stochastic_warfare.simulation.scenario import ScenarioLoader; ctx = ScenarioLoader('data').load('data/scenarios/{name}/scenario.yaml', seed=42); print(f'Units: {sum(len(u) for u in ctx.units_by_side.values())}'); print(f'Armed: {sum(1 for ws in ctx.unit_weapons.values() if ws)}'); print(f'Sensored: {sum(1 for ss in ctx.unit_sensors.values() if ss)}')"
```

Verify armed > 0 and sensored > 0.

### 8. Run Tests
```bash
uv run python -m pytest tests/validation/test_phase_30_scenarios.py::TestScenarioFullLoad -x --tb=short -q
```

All scenarios (including the new one) must pass.

## Reference
- Schema: `stochastic_warfare/simulation/scenario.py` → `CampaignScenarioConfig`
- Weapon map: `stochastic_warfare/validation/scenario_runner.py` → `_WEAPON_NAME_MAP`
- Sensor map: `stochastic_warfare/validation/scenario_runner.py` → `_SENSOR_NAME_MAP`
- Validation script: `scripts/validate_scenario_data.py`
- Examples: `data/scenarios/test_campaign/scenario.yaml`, `data/scenarios/73_easting/scenario.yaml`
- Unit types: `data/units/**/*.yaml`, `data/eras/{era}/units/**/*.yaml`
- Commander profiles: `data/commanders/*.yaml`, `data/eras/{era}/commanders/*.yaml`
- Doctrine templates: `data/doctrine/*.yaml`, `data/eras/{era}/doctrine/*.yaml`
- Equipment categories: WEAPON, SENSOR, PROPULSION, PROTECTION, COMMUNICATION, NAVIGATION, UTILITY, POWER

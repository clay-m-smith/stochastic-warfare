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
- **Duration**: Campaign length in hours
- **Sides**: Names, unit compositions, experience levels
- **Objectives**: Territory control points, key terrain
- **Victory conditions**: Which conditions to use (territory_control, force_destroyed, time_expired, morale_collapsed, supply_exhausted)

### 2. Select Units
List available unit types from `data/units/` using the Glob tool. For each side:
- Suggest unit types appropriate to the scenario setting
- Ask for unit counts
- Set experience levels and morale
- Select commander profile from `data/commanders/`
- Select doctrine template from `data/doctrine/`

### 3. Configure Terrain
Options:
- `flat_desert` — open terrain, good for armor
- `open_ocean` — naval scenarios
- `hilly_defense` — defensive terrain with elevation

Set dimensions (width_m, height_m), cell size, and terrain features.

### 4. Set Calibration
Ask about calibration overrides:
- `hit_probability_modifier` (default 1.0)
- `target_size_modifier` (default 1.0)
- Any scenario-specific adjustments

### 5. Generate YAML
Write the complete scenario YAML to `data/scenarios/{name}/scenario.yaml` following the `CampaignScenarioConfig` schema.

### 6. Validate
- Parse the YAML with pydantic validation
- Run a quick smoke test: `uv run python -c "from stochastic_warfare.simulation.scenario import ScenarioLoader; ScenarioLoader('data').load('data/scenarios/{name}/scenario.yaml')"`

## Reference
- Schema: `stochastic_warfare/simulation/scenario.py` → `CampaignScenarioConfig`
- Examples: `data/scenarios/test_campaign/scenario.yaml`, `data/scenarios/73_easting/scenario.yaml`
- Unit types: `data/units/**/*.yaml`
- Commander profiles: `data/commanders/*.yaml`
- Doctrine templates: `data/doctrine/*.yaml`

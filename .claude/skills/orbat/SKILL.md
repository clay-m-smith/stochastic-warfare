# Order of Battle Builder

Interactive builder for constructing military organization (Order of Battle / ORBAT).

## Trigger
Use when the user wants to:
- Build a force structure for a scenario
- Create a TO&E (Table of Organization & Equipment) definition
- Design an ORBAT for a specific side

## Process

### 1. Select Force Structure
Ask the user for:
- **Side name**: e.g., "blue", "red", "opfor"
- **Echelon level**: What size force? (Squad → Platoon → Company → Battalion → Brigade → Division → Corps)
- **Branch**: Infantry, Armor, Mechanized, Artillery, Air Defense, Naval, Air, SOF

### 2. List Available Unit Types
Use Glob to show available unit definitions:
```
data/units/ground/*.yaml     — Ground units (M1A2, T-72, rifle squad, etc.)
data/units/aerial/*.yaml     — Aircraft (F-16C, AH-64D, MQ-9, etc.)
data/units/air_defense/*.yaml — AD systems (Patriot, etc.)
data/units/naval/*.yaml      — Ships (DDG-51, SSN-688, LHD-1, etc.)
data/units/support/*.yaml    — Support vehicles (HEMTT, etc.)
```

Show key stats for each: display_name, domain, max_speed, crew size.

### 3. Build Hierarchy
For each echelon, guide the user through:
- How many subordinate units of each type
- Command structure (who reports to whom)
- Attachment/detachment of supporting units

Example company structure:
```
Tank Company (3x platoons)
├── HQ Section: 2x M1A2
├── 1st Platoon: 4x M1A2
├── 2nd Platoon: 4x M1A2
└── 3rd Platoon: 4x M1A2
```

### 4. Configure Side Settings
For the whole side:
- **Experience level**: 0.0–1.0 (0.5 = average)
- **Initial morale**: STEADY (default)
- **Commander profile**: Select from `data/commanders/*.yaml`
- **Doctrine template**: Select from `data/doctrine/*.yaml`

### 5. Output
Generate the `sides` section of a scenario YAML:
```yaml
sides:
  - side: "blue"
    units:
      - unit_type: "m1a2"
        count: 14
      - unit_type: "m109a6"
        count: 6
    experience_level: 0.8
    morale_initial: "STEADY"
    commander_profile: "aggressive_armor"
    doctrine_template: "us_combined_arms"
    depots:
      - depot_id: "blue_fob"
        position: [500, 5000]
        capacity_tons: 500
```

### 6. Validate
Check that:
- All unit_type values exist in `data/units/`
- Commander profile exists
- Doctrine template exists
- Force composition makes military sense (warn if no logistics, no air defense, etc.)

## Reference
- Unit definitions: `data/units/**/*.yaml`
- TO&E definitions: `data/organizations/*.yaml`
- Commander profiles: `data/commanders/*.yaml`
- Doctrine templates: `data/doctrine/*.yaml`
- Schema: `stochastic_warfare/simulation/scenario.py` → `SideConfig`

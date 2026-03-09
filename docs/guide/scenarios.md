# Scenario Library

This page catalogs all available scenarios and documents the YAML format for creating or modifying them.

---

## How Scenarios Work

The simulation pipeline:

```
YAML file -> pydantic validation -> ScenarioLoader -> SimulationContext -> SimulationEngine
```

1. A scenario YAML defines terrain, forces, objectives, victory conditions, and optional subsystems
2. `ScenarioLoader` validates the YAML, loads all referenced definitions, and wires engines
3. `SimulationEngine` runs the simulation using the fully-wired context

## Scenario YAML Format

### Identity Fields

```yaml
name: "73 Easting - Eagle Troop Engagement"
date: "1991-02-26T16:18:00Z"       # ISO 8601 date (historical scenarios)
duration_hours: 0.5                  # max scenario duration
era: modern                          # modern | ww2 | ww1 | napoleonic | ancient_medieval
```

### Terrain

```yaml
terrain:
  width_m: 6000                     # east-west extent in meters
  height_m: 4000                    # north-south extent in meters
  cell_size_m: 50.0                 # raster cell resolution
  base_elevation_m: 200.0           # base ground elevation
  terrain_type: flat_desert          # terrain preset
```

### Weather

```yaml
weather_conditions:
  visibility_m: 800
  wind_speed_mps: 8.0
  wind_direction_deg: 270
  temperature_c: 18.0
  precipitation: none                # none | light_rain | heavy_rain | snow | fog
  cloud_cover: 0.3                   # 0.0 to 1.0
  humidity: 0.25
  sea_state: 3                       # 0-9 (naval scenarios)
```

### Forces (Campaign Format)

Modern scenarios use the campaign `sides` format:

```yaml
sides:
  - side: blue
    units:
      - unit_type: m1a2              # references data/units/armor/m1a2_abrams.yaml
        count: 9
      - unit_type: m3a2_bradley
        count: 12
    experience_level: 0.8            # 0.0 to 1.0
    morale_initial: STEADY           # CONFIDENT | STEADY | SHAKEN | BROKEN | ROUTED
    commander_profile: aggressive    # references data/commander_profiles/
    doctrine_template: us_fm3_0      # references data/doctrine/
    depots:
      - depot_id: fob_alpha
        position: [500, 2000]
        capacity_tons: 2000
        throughput_tons_per_hour: 50.0
```

### Objectives and Victory Conditions

```yaml
objectives:
  - objective_id: obj_alpha
    position: [3000, 2000]
    radius_m: 500
    assigned_side: blue

victory_conditions:
  - side: blue
    condition_type: territory         # all assigned objectives controlled
  - side: red
    condition_type: force_destroyed   # opponent loses 70%+ forces
  - condition_type: time_expired      # scenario duration exceeded
```

**Victory condition types**: `territory`, `force_destroyed`, `morale_collapsed`, `supply_exhausted`, `time_expired`, `ceasefire`, `capitulation`.

### Reinforcements

```yaml
reinforcements:
  - side: blue
    arrival_time_s: 3600             # arrive at 1 hour
    units:
      - unit_type: rifle_squad
        count: 4
```

### Calibration Overrides

Fine-tune simulation parameters for historical accuracy:

```yaml
calibration_overrides:
  hit_probability_modifier: 1.0
  target_size_modifier: 1.0
  thermal_contrast: 1.5
  morale_degrade_rate_modifier: 0.3
  blue_cohesion: 0.9
  red_cohesion: 0.5
```

### Optional Subsystems

Include these blocks to enable optional engines:

```yaml
ew_config:                           # Electronic Warfare
  enable_jamming: true
  enable_spoofing: true

space_config:                        # Space & Satellite
  gps_constellation: gps_navstar
  enable_asat: false

cbrn_config:                         # CBRN Effects
  enable_chemical: true
  enable_nuclear: false

escalation_config:                   # Escalation Ladder
  initial_level: 3
  max_level: 7

school_config:                       # Doctrinal AI Schools
  blue: maneuverist
  red: attrition

dew_config:                          # Directed Energy Weapons
  enable_laser: true
```

Omitting a config block disables that subsystem entirely (zero performance cost).

### Documented Outcomes

For validated historical scenarios, include reference data:

```yaml
documented_outcomes:
  - name: exchange_ratio
    value: 28.0
    tolerance_factor: 2.0
    unit: "red:blue destroyed"
    source: "McMaster, Eagles in the Desert"
    source_quality: 1
    notes: "Eagle Troop only"
```

---

## Modern Scenarios (27 total)

### Engagement Scenarios

| Scenario | Description | Duration | Key Features |
|----------|-------------|----------|--------------|
| **73 Easting** | Eagle Troop vs Iraqi armor, 1991 | 30 min | Desert, thermal advantage, validated |
| **Falklands Naval** | Sheffield vs Exocet attack, 1982 | 1 hr | Naval, missile exchange |
| **Golan Heights** | Israeli defense vs Syrian armor, 1973 | 6 hr | Prepared defense, force ratio |
| **Bekaa Valley 1982** | Israeli SEAD vs Syrian IADS | 2 hr | EW, SEAD, air defense |
| **Gulf War EW 1991** | Coalition EW campaign | 4 hr | Full EW spectrum |

### Campaign Scenarios

| Scenario | Description | Duration | Key Features |
|----------|-------------|----------|--------------|
| **Falklands Campaign** | Full Falklands War campaign | Multi-day | Naval, amphibious, air |
| **Falklands San Carlos** | San Carlos air raids | 8 hr | Air defense, naval |
| **Falklands Goose Green** | 2 PARA assault | 12 hr | Infantry, combined arms |
| **Golan Campaign** | Full Yom Kippur War Golan sector | Multi-day | Defensive campaign |
| **Taiwan Strait** | Carrier strike vs amphibious assault | 72 hr | Air-naval, EW, escalation |
| **Korean Peninsula** | Combined arms defense | 48 hr | CBRN, combined arms |
| **Suwalki Gap** | NATO defense of Baltic corridor | 72 hr | EW, doctrinal schools |
| **Hybrid Gray Zone** | SOF, insurgency, escalation | 168 hr | Unconventional, escalation |

### Special Scenarios

| Scenario | Description | Duration | Key Features |
|----------|-------------|----------|--------------|
| **Space GPS Denial** | GPS jamming/spoofing effects | 4 hr | Space, EW |
| **Space ISR Gap** | Satellite coverage gaps | 24 hr | Space ISR |
| **Space ASAT Escalation** | Anti-satellite warfare | 48 hr | ASAT, debris, escalation |
| **CBRN Chemical Defense** | Chemical attack and protection | 4 hr | CBRN, MOPP |
| **CBRN Nuclear Tactical** | Tactical nuclear exchange | 2 hr | Nuclear, EMP, fallout |
| **Halabja 1988** | Chemical attack on civilians | 4 hr | CBRN, civilian population |
| **Srebrenica 1995** | Escalation and war crimes | 72 hr | Escalation, consequences |
| **Eastern Front 1943** | WWII Eastern Front | 72 hr | Large-scale combined arms |
| **COIN Campaign** | Counterinsurgency operations | 720 hr | Insurgency, SOF, population |

### Test Scenarios

| Scenario | Purpose |
|----------|---------|
| **test_scenario** | Minimal scenario for unit testing |
| **test_campaign** | Basic campaign loop testing |
| **test_campaign_multi** | Multi-battle campaign testing |
| **test_campaign_reinforce** | Reinforcement arrival testing |
| **test_campaign_logistics** | Logistics system testing |

---

## Historical Era Scenarios (14 total)

### WW2

| Scenario | Date | Description |
|----------|------|-------------|
| **Kursk** | 1943 | Largest tank battle in history |
| **Normandy Bocage** | 1944 | Hedgerow fighting |
| **Stalingrad** | 1942 | Urban combat |
| **Midway** | 1942 | Carrier battle |

### WW1

| Scenario | Date | Description |
|----------|------|-------------|
| **Somme July 1** | 1916 | First day of the Somme |
| **Cambrai** | 1917 | First mass tank assault |
| **Jutland** | 1916 | Dreadnought fleet action |

### Napoleonic

| Scenario | Date | Description |
|----------|------|-------------|
| **Austerlitz** | 1805 | Napoleon's masterpiece |
| **Waterloo** | 1815 | Coalition defeat of Napoleon |
| **Trafalgar** | 1805 | Nelson vs Franco-Spanish fleet |

### Ancient & Medieval

| Scenario | Date | Description |
|----------|------|-------------|
| **Cannae** | 216 BC | Hannibal's double envelopment |
| **Salamis** | 480 BC | Greek trireme victory |
| **Hastings** | 1066 | Norman conquest of England |
| **Agincourt** | 1415 | English longbow vs French knights |

---

## Creating Custom Scenarios

### Using the Web UI (Clone & Tweak)

The easiest way to create a custom scenario is through the web UI's scenario editor:

1. Browse to any scenario's detail page
2. Click **Clone & Tweak** to open the editor with a copy of that scenario
3. Modify forces (add/remove units, adjust counts), terrain, weather, duration, and calibration
4. Toggle optional subsystems (EW, CBRN, Escalation, Schools, Space, DEW)
5. Use the live YAML preview to verify your changes
6. Click **Validate** to check for errors, then **Run This Config** to execute

The editor validates your configuration against the engine's pydantic schema and shows inline errors. You can also click **Download YAML** to save your custom scenario to disk.

See the [Web UI Guide](web-ui.md#scenario-editor-clone-tweak) for a detailed walkthrough.

### Using the CLI Skill

The `/scenario` CLI skill provides an interactive walkthrough for creating new scenarios from scratch. It handles YAML formatting and validation automatically.

### Manual YAML Editing

1. Copy an existing scenario as a template
2. Modify forces, terrain, objectives, and victory conditions
3. Validate against the pydantic schema by loading with `ScenarioLoader`:

```python
from pathlib import Path
from stochastic_warfare.simulation.scenario import ScenarioLoader

loader = ScenarioLoader(Path("data"))
try:
    ctx = loader.load(Path("my_scenario.yaml"))
    print("Valid scenario!")
except Exception as e:
    print(f"Validation error: {e}")
```

### Tips

- Unit types must match YAML filenames in `data/units/` (or `data/eras/{era}/units/`)
- Terrain dimensions should be appropriate for the engagement scale
- Victory conditions need at least one terminal condition to end the simulation
- Calibration overrides can compensate for known modeling gaps
- Optional subsystem configs can be omitted entirely to disable them

# Scenario Library

This page catalogs all available scenarios and documents the YAML format for creating or modifying them.

---

## How Scenarios Work

The simulation pipeline:

```
YAML or typed config -> SimulationRuntimeFactory -> PreparedScenario
                     -> ScenarioLoader -> SimulationEngine -> RuntimeSession
```

1. A scenario YAML defines terrain, forces, objectives, victory conditions, and optional subsystems
2. `SimulationRuntimeFactory` validates and freezes source/config/data/era identity
3. `PreparedScenario.build()` uses `ScenarioLoader` to load definitions and wire engines
4. `RuntimeSession` advances the resulting `SimulationEngine`

## Scenario YAML Format

### Identity Fields

```yaml
name: "73 Easting - Eagle Troop Engagement"
date: "1991-02-26T16:18:00Z"       # ISO 8601 date (historical scenarios)
duration_hours: 0.5                  # max scenario duration
era: modern                          # modern | ww2 | ww1 | napoleonic | ancient_medieval
```

The production factory resolves the named registered era before constructing
any RNG, clock, terrain, force, or engine. It freezes the selected `EraConfig`
and one effective runtime contract into the prepared scenario, so later
registry replacement cannot alter an already prepared run. A new preparation
resolves and captures the replacement.

### Tick Cadence and Era Contracts

```yaml
tick_resolution:
  strategic_s: 3600.0
  operational_s: 300.0
  tactical_s: 5.0
```

Scenario-authored `tick_resolution` values and the alternative uniform
`tick_duration_seconds` shorthand accept non-boolean integers or floats,
normalize them to floats, and require a finite positive value exactly
representable at microsecond precision. The resulting cadence must be
executable through the scenario's declared calendar horizon. The uniform
shorthand sets all three resolutions and cannot be combined with a selected
era that declares a sparse tick override.

Custom registered eras may sparsely override the three cadence values and the
medical minor/serious/critical treatment or maintenance repair duration. Those
are typed registry declarations, not arbitrary scenario YAML dictionaries.
Unlike scenario cadence inputs, every authored era-override value must be an
actual strict float (`5.0`, not integer `5`). Unknown keys and the former
unsupported C2/nuclear fields reject. Built-in era presets currently declare
no cadence or physics numbers because the historical values previously stored
there were unsourced.

One resolved contract constructs the clock, engine interval cadence, medical
and maintenance configs; participates in runtime/API fingerprints; and
persists in checkpoint format 114. It does not automatically admit battle
casualties, create facilities, register equipment for maintenance, initiate
repairs/spares, construct communications equipment topology, or schedule a
nuclear action. See the [era reference](../reference/eras.md) and
[Phase 114 contract](../specs/era-override-execution.md).

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
    morale_initial: STEADY           # STEADY | SHAKEN | BROKEN | ROUTED | SURRENDERED
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
    type: territory

victory_conditions:
  - type: territory_control
    side: blue
    params:
      required_fraction: 1.0
  - type: force_destroyed
    side: blue
    params:
      threshold: 0.7
  - type: time_expired
    side: red
    params:
      max_duration_s: 1800
```

**Victory condition types**: `territory_control`, `force_destroyed`,
`time_expired`, `morale_collapsed`, `supply_exhausted`, `ceasefire`,
`armistice`, and `attrition_ratio`.

### Reinforcements

```yaml
reinforcements:
  - side: blue
    arrival_time_s: 3600             # arrive at 1 hour
    arrival_sigma: 0.15              # optional log-normal timing uncertainty
    position: [500, 2000, 0]         # ENU metres; altitude is optional
    units:
      - unit_type: rifle_squad
        count: 4
```

The production engine installs this schedule automatically. Due waves are
checked at every simulation resolution, and each arriving unit receives the
same declared weapon and sensor loadout as an initial unit. A wave is atomic:
an invalid or failed unit leaves the whole wave pending for retry.

Per-unit reinforcement `overrides` are not currently a typed runtime contract
and are rejected. Define a distinct unit-catalog entry when a wave needs a
different loadout or entity configuration.

### Logistics

Production logistics is opt-in. Omission and `enabled: false` are equivalent;
legacy `sides[].depots` metadata remains valid but does not create stock,
invent unit capacity, or connect a supply network.

An enabled excerpt declares the depot state on its owning side and the runtime
profiles/routes at the scenario root:

```yaml
sides:
  - side: blue
    units:
      - unit_type: m1a2
        count: 4
    depots:
      - depot_id: blue_main
        position: [500, 2000, 0]       # finite ENU metres
        depot_type: DEPOT              # exact DepotType name
        condition: 1.0
        capacity_tons: 1000
        throughput_tons_per_hour: 100
        initial_inventory:
          - supply_class: CLASS_I      # exact SupplyClass name
            item_id: water_potable     # data/logistics/supply_items catalog ID
            quantity: 20000            # item-native quantity

logistics:
  enabled: true
  update_interval_seconds: 3600
  unit_profiles:
    - side: blue
      unit_type: m1a2
      initial_inventory:
        - {supply_class: CLASS_I, item_id: water_potable, quantity: 20}
      maximum_inventory:
        - {supply_class: CLASS_I, item_id: water_potable, quantity: 100}
      idle_consumption_per_hour:
        - {supply_class: CLASS_I, item_id: water_potable, quantity: 5}
  route_templates:
    - route_id: blue_main_armor
      side: blue
      depot_id: blue_main
      unit_types: [m1a2]
      transport_mode: ROAD             # exact TransportMode name
      transport_speed_kph: 40
      capacity_tons_per_hour: 100
      condition: 1.0
```

The enabled schema forbids unknown fields. Every initial and reinforcement unit
type needs exactly one same-side profile. Items must exist in the effective
supply catalog and match their declared class; maxima must cover initial and
idle entries. Depot IDs are globally unique, explicit inventory may be empty,
and declared inventory mass cannot exceed capacity. Route templates expand to
same-side direct depot-to-unit routes only.

At every crossed fixed-time boundary, the engine updates route state, performs
deterministic mass/throughput/condition-bounded resupply, then debits the exact
eligible idle rate. Only active units that stayed stationary and out of battle
for the interval receive that rate. March/combat demand and synchronization
with live fuel tanks or weapon magazines are not yet part of this contract.
Delivery events and full topology/cadence state are exposed through the normal
event and checkpoint boundaries.

### Scheduled Time-on-Target Fire

Preplanned time-on-target missions are opt-in under the strict
`indirect_fire` block. A populated mission also requires one positive
whole-second `tick_duration_seconds`; every derived fire time and common impact
must align exactly to that cadence.

Plausible misspellings or misplaced feature keys fail validation instead of
silently selecting the disabled default. This includes snake/camel/compact
forms such as `indrect_fire`, `timeOnTargetMissions`, `totPlan`,
`enableTimeOnTarget`, and `enable_tot`; unrelated historical root metadata
remains compatible.

```yaml
tick_duration_seconds: 5

indirect_fire:
  enable_time_on_target: true
  time_on_target_missions:
    - mission_id: blue_validation_tot
      target_unit_id: red_hemtt_0000
      target_position:                 # internal ENU metres
        easting: 22000
        northing: 10000
        altitude: 0
      impact_time_s: 120               # seconds from scenario start
      rounds_per_battery: 1
      batteries:
        - unit_id: blue_m109a6_0000
          source_equipment_index: 0    # exact Phase 109 attachment
          weapon_id: m284_155mm
          ammo_id: m982_excalibur
          time_of_flight_s: 60         # authored fire-control hang time
        - unit_id: blue_m109a6_0001
          source_equipment_index: 0
          weapon_id: m284_155mm
          ammo_id: m982_excalibur
          time_of_flight_s: 55
```

Mission IDs are unique, and battery unit IDs are unique within each mission;
each mission has one to six batteries. Battery and target IDs name exact
initial-roster units, and the source index must identify the declared weapon
attachment on that unit. The round count cannot exceed the attachment's
represented-system multiplier. The loader rejects friendly targets,
unsupported categories or target domains, incompatible or nonlethal
ammunition, impossible range/time data, aggregate magazine overbooking, and
schedules that violate the attachment's quantity-aware firing rate.

At runtime, each battery gets one scheduled fire attempt. A successful fire
consumes its exact live magazine, advances cooldown and maintenance state, and
stores its generated impacts. Inactive, moving, displaced, inoperable,
depleted, or cooling-down batteries produce explicit terminal rejection
reasons instead of retries. All fired batteries resolve against the target's
then-current position at the common impact time. The recorder and
`GET /api/runs/{run_id}/events` expose one `TimeOnTargetMissionEvent` with the
ordered battery results, mission outcome, impact counts, target effect, and
before/after status.

The authored `time_of_flight_s` is a whole-second fire-direction input, not a
simulated firing-table solution. The production path currently supports tube
artillery/mortars with positive-radius lethal rounds, not rocket artillery,
smoke, or illumination. It also cannot authenticate a later live-magazine
increase as a reload because live Class V replenishment has no persisted
production provenance; such checkpoint state rejects rather than being
guessed valid.

### Calibration Overrides

Calibration overrides change the current model configuration. They can support
a predeclared, source-backed fitting study, but a fitted value or a passing
regression seed does not by itself establish historical accuracy. Independent
production outcome-envelope validation remains tracked by
[REM-030](../remediation-backlog.md#rem-030-catalog-wide-historical-outcome-claims-lack-production-validation).

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

Optional EW, space, and CBRN suites require an explicit true enable flag:

```yaml
ew_config:                           # Electronic Warfare
  enable_ew: true
  enable_jamming: true
  enable_spoofing: true

space_config:                        # Space & Satellite
  enable_space: true
  constellation_ids:
    - gps_navstar
  enable_asat: false

cbrn_config:                         # CBRN Effects
  enable_cbrn: true
  update_interval_s: 10.0
  auto_mopp_response: true

escalation_config:                   # Escalation Ladder
  initial_level: 3
  max_level: 7

school_config:                       # Doctrinal AI Schools
  blue: maneuverist
  red: attrition

dew_config:                          # Directed Energy Weapons
  enable_laser: true
```

Omitting a block, omitting its suite enable flag, or setting that flag to
`false` leaves the suite absent from runtime and checkpoints. The registered
era selected by `era` can also forbid `ew`, `space`, or `cbrn`; explicitly
enabling a forbidden suite is a load error. Era gates additionally reject
forbidden GPS/PGM guidance, thermal sensors, finite data links, and sensor
types outside the era allowlist.

Constructing an enabled CBRN suite does not schedule a chemical, biological,
radiological, or nuclear action. Typed production action/owner/delivery/target
topology remains
[REM-037](../remediation-backlog.md#rem-037-cbrn-has-no-typed-scheduled-action-boundary).

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

## Modern Scenarios (38 total)

### Engagement Scenarios

| Scenario | Description | Duration | Key Features |
|----------|-------------|----------|--------------|
| **73 Easting** | Eagle Troop vs Iraqi armor, 1991 | 30 min | Desert, thermal advantage, validated |
| **Debecka Pass** | US SF + Peshmerga vs Iraqi 1st Mech, 2003 | 4 hr | Javelin ATGM, CAS, ridgeline defense, golden-scenario (Block 11) |
| **Khafji** | Iraqi III Corps vs Saudi/Qatari/USMC/coalition air + USS Missouri, 1991 | 72 hr | Full-OOB 233 units, hybrid tick resolution, naval gunfire, AC-130, multi-domain, golden-scenario (Block 11) |
| **Fallujah Phase Line Fran** | USMC RCT-1/RCT-7 + Army TF 2-7 CAV vs insurgent defenders, 2004 | 120 hr | Urban combat, HBIED pre-emplacement, WP shake-and-bake, AC-130U, scripted events (mosque seizure, armored thrust), golden-scenario (Block 11) |
| **Bint Jbeil 2006** | IDF Golani/Paratrooper/Armor + Egoz SOF vs Hezbollah tank hunters, 2006 | 240 hr | ATGM-vs-MBT (Kornet + RPG-29 vs Merkava Mk III/IV), urban hills, reserve-mobilization morale gap, contested outcome (DRAW_SCENARIO), golden-scenario (Block 11) |
| **INS Hanit 2006** | Sa'ar 5 corvette vs Hezbollah coastal C-802 Noor ASCM strike, 2006 | 2 hr | Naval ASCM engagement, degraded-ECM posture, sea-skimming cruise missile, Barak-1 PD SAM, golden-scenario (Block 11) |
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
| **Taiwan Strait** | Carrier strike vs amphibious assault | 24 hr | Air-naval, EW, escalation |
| **Korean Peninsula** | Combined arms defense | 96 hr | CBRN, combined arms |
| **Suwalki Gap** | NATO defense of Baltic corridor | 72 hr | EW, doctrinal schools |
| **Hybrid Gray Zone** | SOF, insurgency, escalation | 168 hr | Unconventional, escalation |

### Special Scenarios

| Scenario | Description | Duration | Key Features |
|----------|-------------|----------|--------------|
| **Space GPS Denial** | GPS jamming/spoofing effects | 4 hr | Space, EW |
| **Space ISR Gap** | Satellite coverage gaps | 24 hr | Space ISR |
| **Space ASAT Escalation** | Hypothetical catalog-backed exact-target direct-ascent strike | 12 hr | Finite ASAT asset, debris, enabled/disabled control |
| **CBRN Chemical Defense** | Chemical attack and protection | 4 hr | CBRN, MOPP |
| **CBRN Nuclear Tactical** | Nuclear-action validation fixture | 2 hr | CBRN suite loads, but the authored scheduled detonation has no production consumer (REM-037) |
| **Halabja 1988** | Chemical attack on civilians | 4 hr | CBRN, civilian population |
| **Srebrenica 1995** | Escalation and war crimes | 72 hr | Escalation, consequences |
| **Eastern Front 1943** | WWII Eastern Front | 72 hr | Large-scale combined arms |
| **COIN Campaign** | Counterinsurgency operations | 720 hr | Insurgency, SOF, population |

### Calibration & Exercise Scenarios

| Scenario | Description | Duration | Key Features |
|----------|-------------|----------|--------------|
| **Calibration Arctic** | Cold weather engagement exercise | 4 hr | Ice crossing, environmental fatigue, cold weather |
| **Calibration Urban CBRN** | Urban CBRN defense exercise | 4 hr | CBRN, MOPP, urban terrain, environmental fatigue |
| **Calibration Air-Ground** | Combined air-ground exercise | 4 hr | Air routing, fuel consumption, ammo gate |

### Test Scenarios

| Scenario | Purpose |
|----------|---------|
| **test_scenario** | Minimal scenario for unit testing |
| **test_campaign** | Basic campaign loop testing |
| **test_campaign_multi** | Multi-battle campaign testing |
| **test_campaign_reinforce** | Reinforcement arrival testing |
| **test_campaign_logistics** | Phase 108 enabled logistics topology, cadence, resupply, and idle-demand fixture |
| **time_on_target_validation** | Phase 111 exact two-battery scheduled-fire, resource, target-effect, event/API, and checkpoint fixture |

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

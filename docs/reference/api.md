# API Reference

This page documents both the REST API for web-based access and the Python API for direct programmatic use.

---

## REST API

The project includes a FastAPI-based REST API for running simulations, browsing scenarios/units, and accessing results over HTTP.

### Setup

```bash
uv sync --extra api              # install API dependencies
uv run uvicorn api.main:app      # start at http://localhost:8000
```

OpenAPI docs are available at `/api/docs` (Swagger UI) and `/api/redoc`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Service health check (version, scenario/unit counts) |
| GET | `/api/meta/eras` | Available eras with disabled modules |
| GET | `/api/meta/doctrines` | Doctrine templates |
| GET | `/api/meta/terrain-types` | Terrain type list |
| GET | `/api/scenarios` | List all scenarios (base + era) |
| GET | `/api/scenarios/{name}` | Full scenario config as JSON |
| POST | `/api/scenarios/validate` | Validate a scenario config against pydantic schema |
| GET | `/api/units?domain=&era=&category=` | List units with optional filters |
| GET | `/api/units/{type}` | Full unit definition |
| POST | `/api/runs` | Submit simulation run (202 Accepted) |
| POST | `/api/runs/from-config` | Submit run from inline config dict (no saved scenario required) |
| GET | `/api/runs?limit=&offset=&scenario=&status=` | List runs (paginated) |
| GET | `/api/runs/{id}` | Run detail with result |
| DELETE | `/api/runs/{id}` | Delete run record |
| GET | `/api/runs/{id}/forces` | Side force states |
| GET | `/api/runs/{id}/events?offset=&limit=&event_type=` | Paginated event log |
| GET | `/api/runs/{id}/narrative?side=&style=&max_ticks=` | Battle narrative text |
| GET | `/api/runs/{id}/snapshots` | State snapshots |
| GET | `/api/runs/{id}/terrain` | Terrain grid data (land cover, objectives, extent) |
| GET | `/api/runs/{id}/frames?start_tick=&end_tick=` | Unit position replay frames |
| WS | `/api/runs/{id}/progress` | Live tick-level progress stream |
| POST | `/api/runs/batch` | Monte Carlo batch run |
| GET | `/api/runs/batch/{id}` | Batch status and aggregated metrics |
| WS | `/api/runs/batch/{id}/progress` | Batch iteration progress |
| POST | `/api/analysis/compare` | A/B configuration comparison |
| POST | `/api/analysis/sweep` | Parameter sensitivity sweep |
| GET | `/api/analysis/tempo/{id}` | Operational tempo analysis |

### Configuration

All settings are overridable via environment variables with the `SW_API_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `SW_API_HOST` | `127.0.0.1` | Bind address |
| `SW_API_PORT` | `8000` | Port |
| `SW_API_DB_PATH` | `data/api_runs.db` | SQLite database path |
| `SW_API_MAX_CONCURRENT_RUNS` | `4` | Max parallel simulation runs |
| `SW_API_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |

---

## Python API

The following classes are in the `stochastic_warfare` package for direct programmatic use.

---

## Core Simulation Classes

### ScenarioLoader

```python
from stochastic_warfare.simulation.scenario import ScenarioLoader
```

Factory that loads a scenario YAML and creates a fully-wired `SimulationContext`.

**Constructor:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `data_dir` | `Path` | Root data directory containing `units/`, `weapons/`, `sensors/`, etc. |

**Methods:**

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `load()` | `scenario_path: Path, seed: int = 42` | `SimulationContext` | Parse YAML, load all definitions, wire all engines, return context |

**Example:**

```python
from pathlib import Path
from stochastic_warfare.simulation.scenario import ScenarioLoader

loader = ScenarioLoader(Path("data"))
ctx = loader.load(Path("data/scenarios/73_easting/scenario.yaml"), seed=42)
```

The loader automatically:

- Validates the YAML against `CampaignScenarioConfig`
- Loads unit, weapon, ammo, sensor, and signature definitions
- Creates terrain, environment, detection, combat, movement, morale, C2, and logistics engines
- Wires optional subsystems (EW, Space, CBRN, Schools, Escalation, DEW) if configured
- Loads era-specific data and engines if an era is specified

---

### SimulationEngine

```python
from stochastic_warfare.simulation.engine import SimulationEngine
```

Top-level simulation orchestrator. Manages the master tick loop, automatic resolution switching, and campaign/battle management.

**Constructor:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ctx` | `SimulationContext` | required | Fully-wired context from `ScenarioLoader` |
| `config` | `EngineConfig \| None` | `None` | Engine tuning parameters |
| `campaign_config` | `CampaignConfig \| None` | `None` | Campaign manager parameters |
| `battle_config` | `BattleConfig \| None` | `None` | Battle manager parameters |
| `victory_evaluator` | `VictoryEvaluator \| None` | `None` | Victory condition checker |
| `recorder` | `SimulationRecorder \| None` | `None` | Event recorder |
| `strict_mode` | `bool` | `False` | Re-raise engine errors instead of logging (useful for debugging) |

**Methods:**

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `run()` | -- | `SimulationRunResult` | Run to completion (victory or max ticks) |
| `step()` | -- | `bool` | Execute one tick. Returns `True` if simulation should continue |

**Example:**

```python
from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig

engine = SimulationEngine(
    ctx,
    config=EngineConfig(max_ticks=10_000),
    victory_evaluator=victory,
    recorder=recorder,
)
result = engine.run()
```

---

### EngineConfig

```python
from stochastic_warfare.simulation.engine import EngineConfig
```

Pydantic model for engine tuning parameters.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `checkpoint_interval_ticks` | `int` | `0` | Ticks between auto-checkpoints. 0 disables. |
| `max_ticks` | `int` | `1_000_000` | Safety limit -- stop after this many ticks |
| `snapshot_interval_ticks` | `int` | `100` | Ticks between recorder state snapshots |
| `enable_selective_los_invalidation` | `bool` | `False` | Use selective cell invalidation for LOS cache |
| `resolution_closing_range_mult` | `float` | `2.0` | Multiplier on engagement range for closing-range guard (prevents STRATEGIC overshoot) |

---

### SimulationRunResult

```python
from stochastic_warfare.simulation.engine import SimulationRunResult
```

Dataclass returned by `SimulationEngine.run()`.

| Field | Type | Description |
|-------|------|-------------|
| `ticks_executed` | `int` | Total simulation ticks completed |
| `duration_s` | `float` | Wall-clock execution time in seconds |
| `victory_result` | `VictoryResult` | Who won, how, and when |
| `campaign_summary` | `Any` | Campaign-level statistics (or `None`) |

---

### SimulationRecorder

```python
from stochastic_warfare.simulation.recorder import SimulationRecorder
```

Records all simulation events for post-run analysis. Subscribes to the `EventBus` and captures events by type.

**Constructor:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event_bus` | `EventBus` | required | Event bus to subscribe to |
| `config` | `RecorderConfig \| None` | `None` | Optional recorder configuration |

**Key Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `start()` | -- | Begin recording |
| `stop()` | -- | Stop recording |
| `events()` | `list` | All recorded events |
| `events_of_type(event_type_name)` | `list` | Events filtered by type |
| `snapshots()` | `list[dict]` | State snapshots (captured at `snapshot_interval_ticks`) |

---

### VictoryEvaluator

```python
from stochastic_warfare.simulation.victory import VictoryEvaluator
```

Evaluates victory conditions each tick. Supports multiple condition types.

**Constructor:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `objectives` | `list[ObjectiveState]` | Spatial objectives on the map |
| `conditions` | `list[VictoryConditionConfig]` | Active victory conditions per side |
| `event_bus` | `EventBus` | For publishing victory events |
| `config` | `VictoryEvaluatorConfig \| None` | Tunable thresholds |
| `max_duration_s` | `float` | Scenario time limit in seconds (0.0 = no limit) |

**Victory Condition Types:**

| Type | Triggers When |
|------|--------------|
| `territory` | Side controls all assigned objectives |
| `force_destroyed` | Opponent loses > 70% of forces (configurable) |
| `morale_collapsed` | Opponent has > 60% units routed/surrendered |
| `supply_exhausted` | Opponent's average supply < 20% |
| `time_expired` | Scenario duration exceeded -- uses composite scoring |
| `ceasefire` | Negotiated war termination (escalation system) |
| `capitulation` | Unilateral surrender at extreme desperation |

**Composite Victory Scoring (time_expired):**

When a scenario reaches its time limit, `evaluate_force_advantage()` determines the winner using a composite score:

```python
VictoryEvaluator.evaluate_force_advantage(
    units_by_side,
    morale_states=ctx.morale_states,       # dict of unit_id -> MoraleState
    weights={"force_ratio": 1.0,           # quality-weighted survival
             "morale_ratio": 0.3,          # 1 - (routed_count / total)
             "casualty_exchange": 0.2},    # survival as proxy
)
```

When called without `weights` (or with `None`), defaults to force-ratio-only scoring for backward compatibility.

### VictoryResult

| Field | Type | Description |
|-------|------|-------------|
| `game_over` | `bool` | Whether a terminal condition was reached |
| `winning_side` | `str` | Side name (e.g., "blue", "red") |
| `condition_type` | `str` | What triggered victory |
| `message` | `str` | Human-readable description |
| `tick` | `int` | Tick at which victory was declared |

---

## Validation Classes

### MonteCarloHarness

```python
from stochastic_warfare.validation.monte_carlo import MonteCarloHarness
```

Runs multiple independent simulation iterations for statistical analysis.

**Constructor:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `runner` | `ScenarioRunner` | required | Scenario runner for each iteration |
| `config` | `MonteCarloConfig \| None` | `None` | Batch run configuration |

**Methods:**

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `run()` | `engagement: HistoricalEngagement, blue_side: str = "blue", red_side: str = "red"` | `MonteCarloResult` | Execute all iterations and return aggregate statistics |

### MonteCarloConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `num_iterations` | `int` | `100` | Number of independent runs |
| `max_workers` | `int` | `1` | Parallel workers (>1 uses ProcessPoolExecutor) |
| `base_seed` | `int` | `42` | Base seed for per-iteration PRNG streams |
| `confidence_level` | `float` | `0.95` | Default confidence level for intervals |

### MonteCarloResult

**Key Methods:**

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `mean()` | `metric: str` | `float` | Mean value across runs |
| `median()` | `metric: str` | `float` | Median value |
| `std()` | `metric: str` | `float` | Standard deviation |
| `percentile()` | `metric: str, p: float` | `float` | Percentile (0-100) |
| `confidence_interval()` | `metric: str, level: float = 0.95` | `tuple[float, float]` | Confidence interval |
| `compare_to_historical()` | `historical: list[HistoricalMetric]` | `ComparisonReport` | Compare against reference data |
| `distribution()` | `metric: str` | `list[float]` | Raw values across all runs |

| Property | Type | Description |
|----------|------|-------------|
| `num_runs` | `int` | Number of completed runs |
| `runs` | `list[RunResult]` | Per-iteration results |

---

## Infrastructure Classes

### RNGManager

```python
from stochastic_warfare.core.rng import RNGManager
```

Central PRNG management. Creates independent per-module random number generator streams from a single seed.

**Constructor:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `seed` | `int` | Master seed for reproducibility |

**Methods:**

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `get_stream()` | `module_id: ModuleId` | `np.random.Generator` | Independent PRNG stream for a module |

**PRNG Discipline:**

- Every module gets its own stream via `get_stream(ModuleId.COMBAT)`, `get_stream(ModuleId.DETECTION)`, etc.
- Streams are independent -- adding randomness in one module doesn't affect others
- Same seed always produces the same sequence per module

---

### EventBus

```python
from stochastic_warfare.core.events import EventBus
```

Publish/subscribe event system. Decouples modules -- combat publishes damage events, morale subscribes without combat knowing about morale.

**Key Methods:**

| Method | Parameters | Description |
|--------|-----------|-------------|
| `subscribe()` | `event_type: type, handler: Callable` | Register handler for event type |
| `publish()` | `event: Event` | Dispatch event to all subscribers |

Events use class hierarchy for type matching -- subscribing to a base class receives all subclass events.

---

### SimulationClock

```python
from stochastic_warfare.core.clock import SimulationClock
```

Manages simulation time with variable-resolution ticks.

**Key Methods:**

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `tick()` | -- | -- | Advance by one tick at current resolution |
| `current_time_s()` | -- | `float` | Current simulation time in seconds |
| `current_tick()` | -- | `int` | Current tick number |
| `set_resolution()` | `seconds: float` | -- | Change tick resolution |

---

## Configuration Stack

### CampaignScenarioConfig

The top-level pydantic model for scenario YAML files. Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Scenario display name |
| `date` | `str` | Historical date (if applicable) |
| `duration_s` | `float` | Maximum scenario duration in seconds |
| `era` | `str \| None` | Era name (modern, ww2, ww1, napoleonic, ancient_medieval) |
| `terrain` | `TerrainConfig` | Terrain dimensions, type, features |
| `sides` | `list[SideConfig]` | Force composition per side |
| `objectives` | `list[ObjectiveConfig]` | Spatial objectives |
| `victory_conditions` | `list[VictoryConditionConfig]` | Win conditions |
| `reinforcements` | `list[ReinforcementConfig]` | Scheduled arrivals |
| `calibration_overrides` | `CalibrationSchema \| None` | Typed calibration overrides (see below) |
| `ew_config` | `dict \| None` | Electronic warfare configuration |
| `space_config` | `dict \| None` | Space/satellite configuration |
| `cbrn_config` | `dict \| None` | CBRN effects configuration |
| `escalation_config` | `dict \| None` | Escalation ladder configuration |
| `school_config` | `dict \| None` | Doctrinal school assignments |
| `dew_config` | `dict \| None` | Directed energy weapon configuration |
| `documented_outcomes` | `dict \| None` | Historical reference data for validation |

---

### CalibrationSchema

```python
from stochastic_warfare.simulation.calibration import CalibrationSchema
```

Pydantic model (`extra="forbid"`) for all scenario tuning parameters. Replaces free-form `dict` overrides — mistyped keys are caught at parse time. Key fields organized by domain:

**Combat & Engagement:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hit_probability_modifier` | `dict[str, float]` | `{}` | Per-side Pk multiplier (e.g. `{"blue": 1.2}`) |
| `force_ratio_modifier` | `dict[str, float]` | `{}` | Per-side Dupuy CEV (e.g. `{"blue": 2.0}`) |
| `target_selection_mode` | `str` | `"nearest"` | Target selection: `"nearest"`, `"threat"`, `"weakest"` |
| `enable_burst_fire` | `bool` | `False` | Enable burst fire engagement model |
| `enable_air_routing` | `bool` | `False` | Enable air combat routing via AirCombatEngine |

**Environmental Coupling (Phase 58--62):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_human_factors` | `bool` | `False` | Heat/cold casualties, expanded MOPP, altitude sickness |
| `heat_casualty_base_rate` | `float` | `0.02` | Fraction/hr above WBGT threshold |
| `cold_casualty_base_rate` | `float` | `0.015` | Fraction/hr below wind chill threshold |
| `mopp_fov_reduction_4` | `float` | `0.7` | Detection range multiplier at MOPP-4 |
| `mopp_reload_factor_4` | `float` | `1.5` | Reload time multiplier at MOPP-4 |
| `mopp_comms_factor_4` | `float` | `0.5` | Comms quality multiplier at MOPP-4 |
| `altitude_sickness_threshold_m` | `float` | `2500.0` | Altitude above which sickness applies |
| `altitude_sickness_rate` | `float` | `0.03` | Performance loss per 100m above threshold |
| `enable_cbrn_environment` | `bool` | `False` | Weather effects on CBRN agent dispersal |
| `cbrn_washout_coefficient` | `float` | `1e-4` | Rain washout rate per mm/hr |
| `cbrn_arrhenius_ea` | `float` | `50000.0` | Activation energy (J/mol) for thermal decay |
| `cbrn_inversion_multiplier` | `float` | `8.0` | Concentration boost during temperature inversion |
| `cbrn_uv_degradation_rate` | `float` | `0.1` | UV photo-degradation rate per hour |
| `enable_air_combat_environment` | `bool` | `False` | Cloud ceiling, icing, density altitude, wind BVR |
| `cloud_ceiling_min_attack_m` | `float` | `500.0` | Minimum ceiling for visual CAS delivery |
| `icing_maneuver_penalty` | `float` | `0.15` | Stall speed increase fraction from icing |
| `icing_power_penalty` | `float` | `0.10` | Engine power reduction from icing |
| `icing_radar_penalty_db` | `float` | `3.0` | Radar detection loss in dB from radome ice |
| `wind_bvr_missile_speed_mps` | `float` | `1000.0` | Reference missile speed for wind range modifier |

**Consequence Enforcement & Ops (Phase 68--71):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_fuel_consumption` | `bool` | `False` | Consume fuel proportional to distance moved |
| `enable_ammo_gate` | `bool` | `False` | Skip engagement when magazine exhausted |
| `enable_missile_routing` | `bool` | `False` | Missile flight resolution + defense intercept |
| `enable_carrier_ops` | `bool` | `False` | Carrier CAP/sortie rate/sea state gating |
| `enable_command_hierarchy` | `bool` | `False` | Enforce command hierarchy for order propagation |
| `fire_damage_per_tick` | `float` | `0.01` | Base fire zone damage fraction per tick |
| `stratagem_duration_ticks` | `int` | `100` | Ticks before active stratagems expire |
| `retreat_distance_m` | `float` | `2000.0` | Distance guerrilla units retreat after disengage |
| `misinterpretation_radius_m` | `float` | `500.0` | Position offset for misinterpreted orders |

**Environment Wiring (Phase 78):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_ice_crossing` | `bool` | `False` | Units on ice move at 50% speed |
| `enable_bridge_capacity` | `bool` | `False` | Bridges enforce weight limits |
| `enable_environmental_fatigue` | `bool` | `False` | Heat/cold stress from WBGT/wind-chill degrades performance |

**LOD Tuning (Phase 85):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_lod` | `bool` | `False` | Enable level-of-detail unit resolution tiering (ACTIVE/NEARBY/DISTANT) |
| `lod_nearby_interval` | `int` | `5` | Update frequency (ticks) for NEARBY-tier units |
| `lod_distant_interval` | `int` | `20` | Update frequency (ticks) for DISTANT-tier units |
| `lod_hysteresis_ticks` | `int` | `3` | Ticks before downgrade from higher tier (immediate promotion) |

**Meta-Flags (Phase 80):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_all_modern` | `bool` | `False` | Activates all 21 non-deferred `enable_*` flags at once (convenience meta-flag) |

All `enable_*` flags default to `False` for backward compatibility. Enable them in scenario YAML to activate the corresponding effects. The `enable_all_modern` meta-flag is available for frontend convenience but per-scenario selective flags are preferred for performance.

---

## Usage Patterns

### Basic Single Run

```python
from pathlib import Path
from stochastic_warfare.simulation.scenario import ScenarioLoader
from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.victory import VictoryEvaluator

loader = ScenarioLoader(Path("data"))
ctx = loader.load(Path("data/scenarios/73_easting/scenario.yaml"), seed=42)

recorder = SimulationRecorder(ctx.event_bus)
victory = VictoryEvaluator(
    objectives=ctx.objectives,
    conditions=ctx.victory_conditions,
    event_bus=ctx.event_bus,
    max_duration_s=ctx.scenario_config.duration_s,
)

engine = SimulationEngine(ctx, config=EngineConfig(max_ticks=10_000),
                          victory_evaluator=victory, recorder=recorder)
result = engine.run()
print(f"{result.victory_result.winning_side} wins by {result.victory_result.condition_type}")
```

### Monte Carlo Batch

```python
from stochastic_warfare.validation.scenario_runner import ScenarioRunner
from stochastic_warfare.validation.monte_carlo import MonteCarloHarness, MonteCarloConfig
from stochastic_warfare.validation.historical_data import HistoricalEngagement

runner = ScenarioRunner(data_dir=Path("data"))
harness = MonteCarloHarness(runner, config=MonteCarloConfig(num_iterations=100))

engagement = HistoricalEngagement.load(Path("data/scenarios/73_easting/scenario.yaml"))
mc_result = harness.run(engagement)
print(f"Mean exchange ratio: {mc_result.mean('exchange_ratio'):.1f}")
```

### Step-by-Step Execution

```python
engine = SimulationEngine(ctx, config=EngineConfig(max_ticks=10_000),
                         victory_evaluator=victory, recorder=recorder)

# Run tick by tick for custom control
while engine.step():
    tick = ctx.clock.current_tick()
    if tick % 100 == 0:
        print(f"Tick {tick}: {len(recorder.events())} events so far")
```

### Checkpoint and Restore

All stateful classes support `get_state()` / `set_state()`:

```python
# Save state at tick 500
state = engine.get_state()

# Continue running...
result = engine.run()

# Restore to tick 500 and try different parameters
engine.set_state(state)
```

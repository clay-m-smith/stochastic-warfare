# Getting Started

This guide walks you through installing Stochastic Warfare, running your first scenario, and understanding the output.

## Prerequisites

- **Python >= 3.12** (pinned to 3.12.10 via `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** -- the project uses `uv` exclusively for package management. Never use bare `pip install`.

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/clay-m-smith/stochastic-warfare.git
cd stochastic-warfare
uv sync --extra dev    # creates .venv, installs all deps
```

Verify the installation:

```bash
uv run python -c "import stochastic_warfare; print('OK')"
```

### Optional Dependencies

| Extra | Install Command | Purpose |
|-------|----------------|---------|
| `perf` | `uv sync --extra perf` | Numba JIT acceleration for hot loops |
| `terrain` | `uv sync --extra terrain` | Real-world terrain data (rasterio, xarray) |
| `mcp` | `uv sync --extra mcp` | MCP server for Claude integration |
| `api` | `uv sync --extra api` | REST API server (FastAPI, SQLite) |
| `docs` | `uv sync --extra docs` | MkDocs documentation site |

## Running the Test Suite

```bash
uv run python -m pytest --tb=short -q           # standard suite (~10,200 tests)
uv run python -m pytest -m slow --tb=short -q   # 1000-run Monte Carlo only
```

All commands use `uv run` to ensure the correct virtual environment is used.

## Running Your First Scenario

The engine runs scenarios defined in YAML files. Here's how to load and execute one programmatically:

### Step 1: Load a Scenario

```python
from pathlib import Path
from stochastic_warfare.simulation.scenario import ScenarioLoader

# Point to the data directory containing unit/weapon/sensor definitions
data_dir = Path("data")
loader = ScenarioLoader(data_dir)

# Load a scenario YAML -- this creates a fully-wired SimulationContext
scenario_path = data_dir / "scenarios" / "73_easting" / "scenario.yaml"
ctx = loader.load(scenario_path, seed=42)
```

The `ScenarioLoader.load()` method:

1. Parses the scenario YAML
2. Loads all referenced unit, weapon, sensor, and signature definitions
3. Creates terrain, environment, and all domain engines
4. Wires optional subsystems (EW, Space, CBRN, escalation, doctrinal schools) if configured
5. Returns a `SimulationContext` with everything ready to run

### Step 2: Configure and Run the Engine

```python
from stochastic_warfare.simulation.engine import SimulationEngine, EngineConfig
from stochastic_warfare.simulation.recorder import SimulationRecorder
from stochastic_warfare.simulation.victory import VictoryEvaluator

# Configure the engine
config = EngineConfig(
    max_ticks=10_000,              # safety limit
    snapshot_interval_ticks=100,   # state snapshots every 100 ticks
)

# Set up event recording and victory evaluation
recorder = SimulationRecorder(ctx.event_bus)
victory = VictoryEvaluator(
    objectives=ctx.objectives,
    conditions=ctx.victory_conditions,
    event_bus=ctx.event_bus,
    max_duration_s=ctx.scenario_config.duration_s,
)

# Create and run the engine
engine = SimulationEngine(
    ctx,
    config=config,
    victory_evaluator=victory,
    recorder=recorder,
)
result = engine.run()
```

### Step 3: Read the Results

```python
# Check who won
print(f"Game over: {result.victory_result.game_over}")
print(f"Winner: {result.victory_result.winning_side}")
print(f"Condition: {result.victory_result.condition_type}")
print(f"Ticks executed: {result.ticks_executed}")
print(f"Wall-clock time: {result.duration_s:.1f}s")

# Access recorded events
events = recorder.events()
print(f"Total events recorded: {len(events)}")
```

## Understanding Output

### SimulationRunResult

The `run()` method returns a `SimulationRunResult` with:

| Field | Type | Description |
|-------|------|-------------|
| `ticks_executed` | `int` | Total simulation ticks completed |
| `duration_s` | `float` | Wall-clock execution time in seconds |
| `victory_result` | `VictoryResult` | Who won, how, and when |
| `campaign_summary` | `Any` | Campaign-level statistics (if applicable) |

### VictoryResult

| Field | Type | Description |
|-------|------|-------------|
| `game_over` | `bool` | Whether a terminal condition was reached |
| `winning_side` | `str` | Side name (e.g., "blue", "red") |
| `condition_type` | `str` | What triggered victory (e.g., "force_destroyed", "territory", "time_expired") |
| `message` | `str` | Human-readable description |
| `tick` | `int` | Tick at which victory was declared |

### Events

The `SimulationRecorder` captures all simulation events -- combat engagements, detections, morale changes, C2 orders, logistics deliveries, and more. Each event includes a tick number, event type, and domain-specific payload.

## Running Monte Carlo Batches

For statistical validation, run multiple iterations with different seeds:

```python
from stochastic_warfare.validation.scenario_runner import ScenarioRunner
from stochastic_warfare.validation.monte_carlo import MonteCarloHarness, MonteCarloConfig
from stochastic_warfare.validation.historical_data import HistoricalEngagement

# Create a scenario runner (handles loading and executing scenarios)
runner = ScenarioRunner(data_dir=data_dir)

# Configure Monte Carlo parameters
mc_config = MonteCarloConfig(num_iterations=100)

# Create the harness and run
harness = MonteCarloHarness(runner, config=mc_config)
engagement = HistoricalEngagement.load(scenario_path)
mc_result = harness.run(engagement)

# Aggregate statistics
print(f"Mean exchange ratio: {mc_result.mean('exchange_ratio'):.1f}")
print(f"95% CI: {mc_result.confidence_interval('exchange_ratio')}")
```

## Using the Web UI

If you prefer a graphical interface over Python scripting, the project includes a full web application for browsing scenarios, running simulations, viewing interactive results, and editing configurations.

### Quick Start

```bash
# Terminal 1: API server
uv sync --extra api
uv run uvicorn api.main:app --reload

# Terminal 2: Frontend dev server
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** to access the web UI. From there you can:

- **Browse scenarios** -- filter by era, search by name, view full configurations
- **Run simulations** -- submit runs, watch live progress via WebSocket
- **View results** -- interactive Plotly charts, battle narrative, tactical map with playback
- **Clone & Tweak** -- modify any scenario's forces, terrain, weather, and calibration, then run your custom configuration
- **Export** -- download results as JSON, CSV, YAML, or print a formatted report

See the [Web UI Guide](web-ui.md) for a complete walkthrough.

## Next Steps

- **[Web UI Guide](web-ui.md)** -- complete walkthrough of the web application
- **[Scenario Library](scenarios.md)** -- browse all available scenarios and learn the YAML format
- **[Architecture Overview](../concepts/architecture.md)** -- understand the module design and simulation loop
- **[Mathematical Models](../concepts/models.md)** -- deep dive into the 10 stochastic models
- **[API Reference](../reference/api.md)** -- REST API and Python API documentation
- **[Era Reference](../reference/eras.md)** -- explore all 5 historical eras

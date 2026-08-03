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
uv sync --locked --extra dev --extra api --extra terrain --extra mcp
uv run --no-sync python scripts/validate_test_partitions.py \
  --output artifacts/partition-audit/manifest.json
uv run --no-sync python scripts/run_pytest_partition.py standard \
  --manifest artifacts/standard/manifest.json \
  --junit artifacts/standard/junit.xml --forbid-skips \
  --timeout-seconds 2700
```

The authoritative suite is the exact audited union of six disjoint partitions:
`standard`, `slow-only`, `benchmark-only`, `slow-benchmark`, `api`, and `e2e`.
PR/main CI runs the audit plus `standard`, `api`, `e2e`, and the overlapping
`terrain` dependency profile. Weekly/manual CI runs the three marker
partitions in deterministic module-affine shards. `benchmark-policy` is another
overlapping focused profile, not a seventh partition.

All commands use `uv run` to ensure the correct virtual environment is used.

## Running Your First Scenario

The engine runs scenarios defined in YAML files. Production consumers construct
and execute them through one typed runtime-owned boundary.

### Step 1: Prepare a Scenario

```python
from pathlib import Path
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)

data_dir = Path("data")
scenario_path = data_dir / "scenarios" / "73_easting" / "scenario.yaml"
prepared = SimulationRuntimeFactory().prepare(
    scenario_path,
    data_root=data_dir,
    variants=(AnalysisVariant(variant_id="baseline"),),
)
```

`SimulationRuntimeFactory.prepare()`:

1. Parses the scenario YAML
2. Applies each strict typed variant independently without changing the source
3. Captures source, code, data, catalog, doctrine, loadout, and roster identity
4. Returns an immutable `PreparedScenario`

Use `prepare_config()` instead when the source is already a typed
`CampaignScenarioConfig`; it does not serialize through a temporary file.

### Step 2: Build and Run a Session

```python
session = prepared.build(
    "baseline",
    seed=42,
    max_ticks=10_000,
    record_events=True,
)
result = session.run_to_completion()
```

`PreparedScenario.build()` performs exact side/roster/loadout and assignment
checks, constructs victory and recording through the production boundary, and
returns a fresh `RuntimeSession`. `run_to_completion()` rejects a non-terminal
result.

### Step 3: Read the Results

```python
# Check who won
print(f"Game over: {result.victory_result.game_over}")
print(f"Winner: {result.victory_result.winning_side}")
print(f"Condition: {result.victory_result.condition_type}")
print(f"Ticks executed: {result.ticks_executed}")
print(f"Logical simulated duration: {result.duration_s:.1f}s")

# Access recorded events
assert session.recorder is not None
events = session.recorder.events
print(f"Total events recorded: {len(events)}")
```

## Understanding Output

### SimulationRunResult

`RuntimeSession.run_to_completion()` returns a `SimulationRunResult` with:

| Field | Type | Description |
|-------|------|-------------|
| `ticks_executed` | `int` | Total simulation ticks completed |
| `duration_s` | `float` | Logical simulated elapsed seconds |
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

For production-path statistical analysis, use the shared runtime-owned batch,
comparison, sweep, or doctrine-comparison routes exposed by the Python analysis
tools and REST API. They preserve ordered raw metric vectors, exact seeds,
source/config fingerprints, and runtime provenance.

```python
from stochastic_warfare.tools._run_helpers import run_scenario_batch

batch = run_scenario_batch(
    str(scenario_path),
    overrides={},
    num_iterations=100,
    base_seed=42,
    max_ticks=10_000,
    metric_names=["exchange_ratio"],
    data_dir=data_dir,
)
print(batch.statistics_dict()["exchange_ratio"]["mean"])
print(batch.metric_values("exchange_ratio"))
```

A seeded distribution characterizes current production behavior; it is not by
itself historical validation. A historical verdict requires a predeclared,
source-backed outcome envelope and held-out production runs. Phase 117 provides
that strict boundary through the claim ledger, typed study plan, production
runtime factory, retained observation receipts and vectors, joint-coverage
evaluation, and digest-bearing artifact. The catalog currently exposes zero
production-validated scenarios.

### Running a Historical Outcome-Envelope Study

Use the checked-in runner for a declared study; send exploratory output to a
new evidence path so the stable artifact is not overwritten:

```bash
uv run --no-sync python scripts/run_historical_backtest.py \
  --plan data/validation/historical_studies/73_easting_phase117.yaml \
  --output docs/evidence/local/73-easting.json
```

The route loads and audits the complete historical-claim ledger, validates the
typed plan, prepares every seed through `SimulationRuntimeFactory`, retains
exact metric observations and terminal evidence, evaluates joint coverage, and
atomically reloads the written artifact. `PASS` and `FAIL` are completed study
verdicts. `ERROR` means execution failed after starting and cannot be promoted;
an invalid plan rejects before a study artifact is produced. A passing local
file is still not accepted evidence: promotion additionally requires a clean,
predeclared, source-backed, independent study and exact committed
ledger/artifact/Git bindings.

The retained Phase 117 73 Easting artifact is `FAIL`, with 0/20 joint successes
and a one-sided lower confidence bound of 0.0. It is not promotion-eligible, so
73 Easting remains unsupported for historical validation. See the
[study contract](../specs/historical-outcome-envelope-integrity.md) and
[retained artifact](../evidence/phase-117/73-easting-phase117.json).

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
- **[Era Reference](../reference/eras.md)** -- explore the modern era and four historical eras

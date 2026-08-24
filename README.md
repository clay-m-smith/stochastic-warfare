# Stochastic Warfare

![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![Tests](https://img.shields.io/badge/tests-partitioned_validation-blue)

Deterministic, data-driven, multi-scale wargame simulator with a headless
Python engine, FastAPI service, and React frontend.

The complete guides, architecture, specifications, and scenario catalog are
published in the
[documentation site](https://clay-m-smith.github.io/stochastic-warfare).

## Requirements

- Python 3.12 or newer (the repository pins 3.12.10 in `.python-version`)
- [uv](https://docs.astral.sh/uv/) for Python environments and packages
- Node.js and npm when running or building the frontend
- Docker only when building the container image

## Install

For a source checkout:

```bash
git clone https://github.com/clay-m-smith/stochastic-warfare.git
cd stochastic-warfare
uv sync --locked --extra dev --extra api
npm --prefix frontend ci
```

Verify the Python installation:

```bash
uv run --no-sync python -c "import stochastic_warfare; print('OK')"
```

The checkout, container image, and locally built wheel/sdist are supported
application layouts. The wheel bundles the authoritative YAML catalog and the
headless CLI, but not the React frontend. API and MCP dependencies remain
opt-in extras; this repository does not claim that a wheel is published to a
package index.

## Run a Headless Scenario

Run a catalog scenario through the production runtime:

```bash
uv run --no-sync stochastic-warfare run test_campaign \
  --seed 112 --max-ticks 1
```

An installed distribution exposes the same command as
`stochastic-warfare`; `python -m stochastic_warfare` is equivalent. A bare
scenario name is resolved in the selected catalog. An explicit absolute path,
or a relative path containing a directory component, names a user-authorized
scenario file; relative explicit paths use the invocation working directory.

For programmatic construction:

```python
from pathlib import Path

from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)

prepared = SimulationRuntimeFactory().prepare(
    Path("data/scenarios/test_campaign/scenario.yaml"),
    Path("data"),
    (AnalysisVariant(variant_id="quickstart"),),
)
session = prepared.build("quickstart", seed=112, max_ticks=1)
result = session.run_to_completion()
print(result.victory_result)
```

See the [Getting Started guide](docs/guide/getting-started.md) for longer runs,
recorded events, batch execution, and historical backtesting.

## Run the Web Application

The development launcher starts both the API and Vite servers:

```bash
# macOS/Linux
bash scripts/dev.sh

# Windows PowerShell
.\scripts\dev.ps1
```

Open <http://localhost:5173>.

To run the services separately:

```bash
# Terminal 1
uv run --no-sync uvicorn api.main:app --reload

# Terminal 2
npm --prefix frontend run dev
```

The API documentation is available at <http://localhost:8000/api/docs>.

To build the frontend and serve the local application from one process:

```bash
npm --prefix frontend run build
uv run --no-sync python -m api
```

Open <http://localhost:8000>.

## Run with Docker

Build from a clean checkout so `SOURCE_REVISION` identifies the staged source:

```bash
docker build \
  --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" \
  -t stochastic-warfare .

docker run --rm \
  -e SW_API_HOST=0.0.0.0 \
  -p 8000:8000 \
  stochastic-warfare
```

Open <http://localhost:8000>.

## Validate the Repository

Install every dependency profile used by the main Python validation path:

```bash
uv sync --locked --extra dev --extra api --extra terrain --extra mcp
```

Audit the test universe, then run the standard disjoint partition:

```bash
uv run --no-sync python scripts/validate_test_partitions.py \
  --output artifacts/partition-audit/manifest.json

uv run --no-sync python scripts/run_pytest_partition.py standard \
  --audit-manifest artifacts/partition-audit/manifest.json \
  --manifest artifacts/standard/manifest.json \
  --junit artifacts/standard/junit.xml \
  --forbid-skips \
  --timeout-seconds 2700
```

The remaining audited partitions and conditional validation routes are defined
in [CODEX.md](CODEX.md). Check repository data, source-local evidence
annotations, generated OpenAPI transport types, static analysis, and the
frontend with:

```bash
uv run --no-sync python scripts/validate_scenario_data.py
uv run --no-sync python scripts/validate_test_evidence.py
uv run --no-sync python scripts/generate_openapi_types.py --check
uv run --no-sync ruff check stochastic_warfare/ api/ tests/ scripts/
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Documentation

Build or serve the documentation locally:

```bash
uv sync --locked --extra docs
uv run --no-sync mkdocs build --strict
uv run --no-sync mkdocs serve
```

- [Getting Started](docs/guide/getting-started.md)
- [Web UI Guide](docs/guide/web-ui.md)
- [Architecture](docs/concepts/architecture.md)
- [Scenario Library](docs/guide/scenarios.md)

## License

Stochastic Warfare is licensed under the
[PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial and institutional
use requires a separate license; contact **claymsmith1@gmail.com**.

## Contributing

This project does not accept external contributions. See
[CONTRIBUTING.md](CONTRIBUTING.md) for details.

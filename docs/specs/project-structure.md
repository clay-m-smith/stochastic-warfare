# Project Structure and Ownership

**Status:** Living reference; tiered modular-monolith consolidation completed
2026-08-23

**Current release status:** Phases 0--118 complete; Phase 119 not started

**Last updated:** 2026-08-23

## Purpose

This page describes current repository ownership. Phase-numbered plans and
devlogs explain how the project arrived here; they are not the source of truth
for imports, package contents, test locations, or CI routing. The consolidation
keeps one deterministic modular monolith and makes its internal boundaries
explicit.

## Repository tiers

```text
runtime kernel   stochastic_warfare/core and domain packages
application      simulation facades, CLI, API, MCP, catalogs, web client
verification     durable unit, contract, integration, API, E2E, benchmark tests
engineering      scripts, current specs, roadmap, remediation backlog
archive          ignored local artifacts and immutable historical narratives
```

Runtime code, authoritative catalogs, checkpoint/RNG ownership, API contracts,
and provenance validation remain in one source revision. Splitting them into
independently versioned services or repositories is not part of this program.

## Top-level layout

```text
stochastic-warfare/
├── stochastic_warfare/       Python product package and packaged resources
├── api/                      FastAPI application boundary
├── frontend/                 React/TypeScript client; build output is optional
├── data/                     Checkout authoritative YAML catalog
├── tests/                    Durable verification taxonomy
├── scripts/                  Engineering and validation entry points
├── docs/                     Current guides/specs plus historical narratives
├── .agents/skills/           Canonical repository skill sources
├── .claude/skills/           Generated regular-file skill projection
├── .github/workflows/        CI routing and release checks
├── build_hooks.py            Wheel/sdist content and identity policy
├── pyproject.toml            Package, dependency, lint, and test configuration
├── uv.lock                   Locked Python environment
├── CODEX.md                  Canonical repository workflow
└── README.md                 Public entry point
```

## Package and application boundary

`stochastic_warfare.application_paths.ApplicationPaths` owns resource
discovery. Its immutable modes are:

- `checkout`: use the repository catalog;
- `package`: use catalog YAML bundled beneath
  `stochastic_warfare/resources/data/`; and
- `external`: use an explicitly configured authoritative catalog root.

Mutable database and artifact paths are resolved separately. Installed modes
default to the user state directory; checkout mode retains repository-local
development defaults. Configuration is available through
`STOCHASTIC_WARFARE_*` variables and the corresponding `SW_API_*` settings.
Catalog names resolve through the selected catalog. An explicit absolute path,
or a relative path containing a path component, names a user-authorized file;
relative explicit paths resolve from the invocation working directory.

The wheel contains the product package, console entry point, and YAML catalog.
It excludes tests, documentation history, raw evidence, engineering scripts,
and the frontend build. The sdist follows the same explicit source allowlist.
The frontend may be supplied separately to the API. No current documentation
claim implies a published PyPI release.

Product entry points are:

```text
stochastic-warfare run <catalog-name-or-path>
python -m stochastic_warfare run <catalog-name-or-path>
python -m api
```

All production run entry points construct sessions through
`SimulationRuntimeFactory`; strict execution is the default and the product CLI
does not publish degraded results.

## Runtime dependency direction

```text
core primitives and typed contracts
        ↓
domain engines and immutable catalogs
        ↓
simulation owners and compatibility facades
        ↓
runtime factory / CLI / API / MCP / analysis tools
        ↓
frontend transport consumers
```

Lower tiers do not import the API, frontend, CLI, or engineering scripts.
Public compatibility facades may retain established imports while delegating
state and behavior to focused owners.

## Simulation ownership

### Scenario construction

`stochastic_warfare.simulation.scenario` is the compatibility facade. The
current owners are:

| Module | Ownership |
|---|---|
| `scenario_config.py` | Typed authored scenario configuration |
| `runtime_context.py` | `SimulationContext` composition and runtime indices |
| `context_checkpoint.py` | Context checkpoint planning and atomic commit |
| `scenario_loader.py` | Catalog loading and subsystem wiring |

Scenario loading converts authored `CalibrationSchema` into recursively
immutable `ResolvedCalibration`. `ctx.cal_flat` is read-only; compatibility
conversion returns a detached dictionary.

### Runtime loadouts

`stochastic_warfare.simulation.loadouts` is the compatibility facade. Ownership
is split among:

| Module | Ownership |
|---|---|
| `loadout_contracts.py` | Frozen identifiers, requests, and resolved products |
| `loadout_registry.py` | Catalog lookup and mapping validation |
| `runtime_attachments.py` | Typed runtime attachment construction |
| `loadout_builder.py` | Initial, reinforcement, and restore orchestration |

The same retained builder and registry identity serve initial units,
reinforcements, and checkpoint reconstruction.

### Battle execution

`BattleManager` remains the compatibility facade and sequencing owner. Focused
executors own OODA, movement, engagement, and checkpoint work. Their frozen
request contracts accept only least-privilege typed runtime views from
`battle_executor_contracts.py`; they do not accept `SimulationContext` or
`Any`. Live `Unit` identities and explicitly named mutable domain owners are
passed only where that executor is authorized to mutate them.

The battle facade preserves established tick ordering, RNG stream ownership,
event order, and serialized behavior. A legacy fog-of-war mutation entry point
now fails with `UnsupportedLegacyFogOfWarUpdateError`. A single current
targeting/FOW snapshot is shared across the relevant tick consumers. The
accepted consolidation postmortem closes REM-052 and REM-053 on those two
boundaries; their planned Phases 139 and 140 are retired before start.

### Strict and degraded execution

`RuntimeExecutionMode.STRICT` is the default. A runtime-wide failure owner is
bound into nested communications, indirect-fire, space, recorder, and committed
event paths. Strict failures propagate. Explicit degraded mode records an
ordered `SuppressedRuntimeFailure` with sequence, tick, logical time,
subsystem, operation, exception type, and message.

`SimulationRunResult.authoritative` and `RuntimeProvenance.authoritative` are
true only for strict execution with no suppressed failures. Degraded runtimes
cannot create or restore authoritative checkpoints. Recorder compatibility
flags do not supersede the bound runtime policy; any pre-binding integrity loss
prevents later authoritative use.

### Checkpoint ownership

`ContextCheckpointSnapshot` is the single context-level snapshot product.
Checkpoint participants have a typed disposition: atomic owner, legacy clone
owner, or explicitly stateless. Planning is non-mutating, commit is all-or-
nothing, and restoration reuses the selected scenario/loadout owners. See
[Checkpoint State](checkpoint-state.md).

## API, frontend, MCP, and legacy boundaries

FastAPI's production `create_app().openapi()` document is the transport-shape
authority. `scripts/generate_openapi_types.py` deterministically writes
`frontend/src/types/openapi.generated.ts`; `--check` is the drift gate.
Generated aliases cover transport shapes. Handwritten TypeScript retains
semantic refinements and discriminated runtime validation.

MCP resources use `ApplicationPaths`, expose path-free normalized resource
identifiers, reject symlinks and catalog-root escape, and retain only a bounded
process-local result store. MCP is an application adapter, not a second runtime
or evidence authority.

Compatibility-only scenario-runner and Monte Carlo helpers live under
`stochastic_warfare.legacy.validation`; legacy pickle support is similarly
quarantined. These modules cannot issue current production or historical
acceptance claims.

## Test ownership

Active Python tests use durable product ownership:

```text
tests/unit/<domain>/
tests/integration/<capability>/
tests/contracts/{configuration,serialization,determinism,repository_policy}/
tests/api/
tests/e2e/
tests/benchmarks/
```

Phase numbers are historical provenance, not active file ownership. Evidence
requirements live beside test definitions as source annotations and compact
typed receipts. Exact collected-node ledgers and large generated blobs are not
maintained on the main branch.

The six pairwise-disjoint execution partitions are `standard`, `slow-only`,
`benchmark-only`, `slow-benchmark`, `api`, and `e2e`. Public documentation
relies on their relational completeness and disjointness, not a permanent node
count. The compact consolidation log retains the dated execution receipt.
`scripts/validate_test_partitions.py` produces the revision-bound manifest used
by every shard; `scripts/run_pytest_partition.py` refuses a stale or mismatched
manifest.

## CI routing

| Workflow | Current authority |
|---|---|
| `test.yml` | Partition audit plus standard, API, E2E, data, OpenAPI-drift, and relevant terrain gates |
| `extended-tests.yml` | Daily generated matrix for slow and benchmark partitions from the same audit |
| `benchmark.yml` | Policy gate on PR/main; 73 Easting paired work on nightly or explicit dispatch; Golan is manual |
| `build.yml` | Container identity, no-`.git` source verification, packaged catalog, and bounded runtime smoke |
| `lint.yml` | Python and frontend static checks |
| `docs.yml` | Link validation and strict MkDocs build |

The current terrain gate targets the heightmap, classification/infrastructure,
bathymetry, and pipeline-integration modules in `tests/unit/terrain/`.
Historical backtests, calibration, and production profiling remain explicit
evidence workflows rather than ordinary unit-test shards.

## Documentation and evidence

Current guides, concepts, references, specs, roadmap/backlog, and this ownership
page are maintained when behavior changes. Closed phase plans and historical
devlog bodies are immutable records. Cross-document claim validation may index
them, but current wording does not silently rewrite history.

Large run artifacts and raw profiles belong under ignored `artifacts/` or on
the separately retained full-evidence branch. Main retains only compact
contracts, source-local evidence annotations, and small typed receipts needed
to verify current claims. See
[Validation and Documentation Trust](validation-and-documentation-trust.md).

## Skills and generated projections

`.agents/skills/` is the canonical checked-in skill source. The repository sync
tool validates the `.claude/skills/` projection by default and rewrites it only
with an explicit `--write`. Project hooks route matching tasks to repository
skills; a skill report becomes evidence only after its claims are checked
against the production path and fresh command output.

## Current consolidation state

The tiered modular-monolith program is **Complete** as of 2026-08-23 under its
accepted postmortem. Phase 119 has not started. REM-052 and REM-053 are closed,
their planned Phases 139 and 140 are retired before start, and REM-055 is
closed by the accepted Phase 142 postmortem after an explicitly owner-approved
bounded partial-recovery decision and fresh native-policy pass. The
consolidation status transition is valid only for a revision whose final exact
frozen-revision release gate is green; failure revokes it and forbids the
consolidation commit. See the
[consolidation contract](tiered-modular-monolith.md),
[remediation backlog](../remediation-backlog.md), and
[compact engineering log](../devlog/consolidation-tiered-modular-monolith.md).

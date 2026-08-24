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
| GET | `/api/health/live` | Process liveness probe |
| GET | `/api/health/ready` | Dependency and catalog readiness probe |
| GET | `/api/meta/eras` | Available eras with disabled modules |
| GET | `/api/meta/doctrines` | Doctrine templates |
| GET | `/api/meta/terrain-types` | Terrain type list |
| GET | `/api/meta/performance-flags` | Canonical governed-flag classifications, current support dispositions, and retained v7 evidence identity |
| GET | `/api/scenarios` | List all scenarios (base + era), each with typed historical-validation status |
| GET | `/api/scenarios/{name}` | Public scenario config, force summary, and typed historical-validation status |
| POST | `/api/scenarios/validate` | Validate a scenario config against pydantic schema |
| GET | `/api/units?domain=&era=&category=` | List units with optional filters |
| GET | `/api/units/{type}` | Full unit definition |
| POST | `/api/runs` | Submit simulation run (202 Accepted) |
| POST | `/api/runs/from-config` | Submit run from inline config dict (no saved scenario required) |
| GET | `/api/runs?limit=&offset=&scenario=&status=` | List runs (paginated) |
| GET | `/api/runs/{id}` | Run detail with result |
| DELETE | `/api/runs/{id}` | Delete run record |
| GET | `/api/runs/{id}/forces` | Side force states |
| GET | `/api/runs/{id}/events?offset=&limit=&event_type=&side=&tick_min=&tick_max=&search=` | Filterable paginated event log |
| GET | `/api/runs/{id}/narrative?side=&style=&max_ticks=` | Battle narrative text |
| GET | `/api/runs/{id}/snapshots` | State snapshots |
| GET | `/api/runs/{id}/terrain` | Terrain grid data (land cover, objectives, extent) |
| GET | `/api/runs/{id}/frames?start_tick=&end_tick=&scope=&side=` | Unit position replay frames with explicit targeting exposure scope |
| WS | `/api/runs/{id}/progress` | Live tick-level progress stream |
| POST | `/api/runs/batch` | Monte Carlo batch run |
| GET | `/api/runs/batch/{id}` | Batch status and aggregated metrics |
| WS | `/api/runs/batch/{id}/progress` | Batch iteration progress |
| GET | `/api/runs/{id}/analytics/casualties?group_by=&side=` | Casualty breakdown by weapon/side/tick |
| GET | `/api/runs/{id}/analytics/suppression` | Suppression timeline, peak count, rout cascades |
| GET | `/api/runs/{id}/analytics/morale` | Morale state distribution by tick |
| GET | `/api/runs/{id}/analytics/engagements` | Engagement summary with hit rates by type |
| GET | `/api/runs/{id}/analytics/summary` | Combined analytics (all 4 above) |
| GET | `/api/meta/schools` | Base/global doctrinal schools with OODA multiplier |
| GET | `/api/meta/commanders` | Base/global commander profiles with personality traits; era-specific profiles remain omitted (REM-049) |
| GET | `/api/meta/weapons` | Weapon catalog (all eras) |
| GET | `/api/meta/weapons/{id}` | Full weapon definition |
| POST | `/api/analysis/compare` | A/B configuration comparison |
| POST | `/api/analysis/sweep` | Parameter sensitivity sweep |
| POST | `/api/analysis/doctrine-compare` | Common-seed doctrinal-policy comparison |
| GET | `/api/analysis/tempo/{id}` | Operational tempo analysis |

### Performance-flag support contract

`GET /api/meta/performance-flags` returns the immutable registry in canonical
order. Each row contains `flag`, `classification`, `support_disposition`,
`required_meaning`, `evidence_plan_id`,
`evidence_manifest_artifact_sha256`, and `retained_shard_status`.

The retained plan is `phase118-performance-semantics-v7`. It completed all 96
pairs / 396 attempts and independently reloaded as an eligible terminal
`FAIL` under `EXTERNALLY_CONTENDED`; the immutable manifest artifact SHA-256
is `bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`.
Detection culling, SoA selection, and parallel detection are
`supported_exact_validated` with retained `PASS`. Scan scheduling and LOD are
`unsupported_failed_semantic_validation` with retained `FAIL`.

Run, inline-scenario, comparison, and sensitivity request boundaries reject a
retired flag enabled or any nondefault LOD tuning value with HTTP 422 before a
run/batch row or background task is created. The same fail-closed disposition
applies to scenario YAML, direct analysis/runtime construction, live owner
drift, and current-checkpoint restore. The v7 result and its externally
contended qualification support no speed claim. The accepted
qualified-negative postmortem closed Phase 118 / REM-031. The terminal v6
`ERROR` remains negative evidence at
`branch=evidence/full; path=docs/evidence/phase-118/v6-terminal/` (manifest
artifact SHA-256
`eb8e12f147c14ee4e83e7f5e80e4b1e50aa2bfe847d5e5e681b2462f7850051a`), and
the v7 `FAIL` remains at
`branch=evidence/full; path=docs/evidence/phase-118/v7-terminal/` (manifest
artifact SHA-256
`bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`).
Those locators currently name a local, unpublished branch pending a separate
evidence-remote or Git LFS decision. Ordinary `main` validation neither fetches
nor reinterprets either study.

### Scenario historical-validation contract

Both scenario endpoints require a `historical_validation` object loaded from
the canonical repository claim ledger. The API audits the ledger self-digest,
every API-published scenario claim's exact locator/content digest, the current
semantic matched-span inventory, and all accepted evidence before returning
catalog data. It does not derive a verdict from scenario YAML metadata.

| Summary field | Type | Meaning |
|---|---|---|
| `aggregate_disposition` | `production_validated \| current_engine_regression_only \| unsupported` | Conservative whole-scenario status |
| `claims` | `HistoricalValidationClaim[]` | Ordered inventoried claim statuses |
| `accepted_claim_ids` | `string[]` | Exact claims backed by accepted production evidence |
| `current_engine_regression_evidence` | `boolean` | Whether regression evidence exists; never a validation verdict |
| `ledger_sha256` | `string` | Canonical ledger identity used for the response |

Each claim supplies `claim_id`, `disposition`, `reason_codes`, `limitation`,
`intended_use`, `metric_scope`, `event_scope`,
`current_engine_regression_evidence`, `accepted_study_id`, and
`accepted_artifact_path`. The claim-level regression flag records only whether
that exact claim has current-engine regression evidence. An aggregate is
`production_validated` only when all
of its claims are production-validated members of one accepted study/use/event
family. Any unsupported claim makes the aggregate unsupported; otherwise a
regression-only claim makes it `current_engine_regression_only`.

Paths without an exact repository ledger identity receive a synthetic
`unsupported` claim with reason `missing_ledger_identity`; no absolute source
path is exposed. `GET /api/scenarios/{name}` removes legacy
`documented_outcomes` and `sources` from `config`. Those fields are catalog
history, not a public evidence surface. The current ledger contains zero
production-validated scenarios, and the retained Phase 117 73 Easting study is
a completed `FAIL` rather than accepted evidence.

### Frame targeting exposure

Completed runs store the paired targeting projections introduced with format
115 at each captured map frame. Format 118 adds the strict root discriminator
`targeting_exposure_schema_version=118`, a required runtime-owned
`fog_of_war_enabled` mode, a required-nullable
`observer_track_support` field to each privileged targeting decision and the
`FOW_OBSERVER_TRACK_SUPPORT` contact-source value. A non-null support record is
exact engine evidence: it identifies the reporting side, observer, source
equipment index, sensor, one of the seven supported fire-control-radar roles,
and target; binds the exact fusion track; and exposes observation/native-
deadline chronology plus the projected position, velocity, and 4x4 covariance.
It is not a historical sensor-accuracy claim.

The support field remains required-nullable so immutable format-118 evidence
and the dormant scan-deferral algorithm decode strictly. Current supported
production cannot emit a non-null support because scan scheduling and LOD
activation are rejected after the terminal semantic `FAIL`; REM-054 / Phase
141 owns restoring a supported production-reachable emission path.

- `scope=PRIVILEGED_ENGINE` returns exact engine/evaluator evidence, including
  ground-truth target and source-attachment identity and, when used, the full
  observer-track support record. It is the current default when `scope` is
  omitted and rejects a `side` parameter.
- `scope=SIDE_FOW&side=<side-id>` returns only that side's frame roster and
  opaque current owner-side track evidence. Track IDs are target-independent,
  side-local ordinals allocated in canonical first-detection order; hidden
  target/entity and attachment identity is omitted. A supported decision may
  expose `contact_source=FOW_OBSERVER_TRACK_SUPPORT` and its opaque
  `target_track_id`, but never the nested support identity, target ID, source
  index, sensor ID/role, covariance, or observation/native-deadline chronology.
  The stored payload's exact `viewer_side` must match the requested side,
  including for an empty side. Missing `side` returns 422; a side absent from
  the captured projection returns 409.

Targeting-decision ordinals in `SIDE_FOW` are separately recomputed from zero
per battle and viewer side; they are not the privileged all-sides picture
ordinal and therefore do not reveal how many opposing shooters sort ahead of
the viewer. One atomic stored-frame decoder validates the privileged decisions
and outcomes, root roster, complete set of side views and side rosters, and
every root target-to-track association before either API scope or replay
returns. It re-derives and compares every public decision and revalidation
field against the privileged source plus the root-only association. An
internally valid but altered standoff, logical time, disposition, support
track, or outcome is rejected rather than trusted as stored public data. A
frame that declares SIDE_FOW unavailable must have empty side and association
envelopes; a current FOW frame must contain exactly one view for every root-
roster side. The strict root FOW mode must equal both SIDE_FOW availability
and every nonempty decision interval, so an empty FOW interval cannot be
downgraded merely by clearing its side envelopes. Current capture rejects a
nonboolean effective runtime mode instead of coercing it.

The stored root frame carries a privileged-only exact target-to-track
association map so the decoder can prove that each opaque track identifier is
the same contact used by the engine decision. Missing associations or same-side
track rebinding reject; this map is never returned in `SIDE_FOW`, replay, or
frontend payloads.

Tick-range filters are applied only after every stored frame has passed the
shared strict decoder. A malformed stored tick therefore returns 409 instead
of bypassing validation or escaping as a server error; standalone replay also
validates every tick before sorting.

The stored-frame boundary accepts exactly one older decision topology: all
nonempty decisions in a pre-118 frame may uniformly omit only
`observer_track_support`, which is re-emitted as explicit `null`. A complete
unversioned Phase 115--117 paired frame remains readable even when its decision
list is empty, but every scope, availability, side view, root roster, and
association must validate. A bare unversioned empty privileged frame is
unsupported because it is indistinguishable from a stripped current frame.
Mixed current and pre-118 decisions, a deleted marker that leaves the
current-only FOW mode, any other missing/extra decision field, or a legacy
decision that claims `FOW_OBSERVER_TRACK_SUPPORT` rejects. Live runtime and
checkpoint decoders remain format-118 strict. These checks establish internal
semantic consistency; stored frames are not cryptographically authenticated.

The route does not yet authenticate the caller or derive an authorized side.
Consequently these query parameters are evidence-projection controls, not an
access-control boundary, and the privileged default is unsuitable as a
player-safe default. REM-041 / Phase 128 owns server-side caller authorization
and safe frontend/API defaults. Client-side FOW filtering cannot substitute
for that work. Legacy frames that stored only the privileged projection cannot
be used to synthesize a side projection.

### Analysis evidence contract

Batch, comparison, sweep, and doctrine-comparison execution all use the
production runtime boundary described below. A completed batch includes exact
ordered raw metric vectors and provenance for the scenario/data roots,
variant, ordered metrics, base seed and seed sequence, maximum ticks,
source/config fingerprints, authored and loaded rosters, code/worktree and data
revisions, catalog/doctrine/loadout fingerprints, initial assignments, and
per-run terminal/runtime records.

`POST /api/analysis/compare` compares two sparse calibration overlays of the
same prepared scenario with common seeds. For every metric it returns the
paired sample counts (`n_total`, `n_nonzero`, positive, negative, tied), mean
and median paired differences, paired superiority, raw exact-sign p-value,
Holm-adjusted p-value, alpha, and family-wise significance. It also retains
both exact raw vectors and both batch provenance envelopes.

`POST /api/analysis/sweep` requires a real `CalibrationSchema` field plus
finite, duplicate-free values and at least two iterations per point. Every
point includes its raw values and complete batch provenance.

`POST /api/analysis/doctrine-compare` requires at least two distinct policies
and schools, the same exact side set in every variant, and identical sparse
calibration patches. Each variant retains assignment-aware runtime provenance.
Doctrine comparison has an explicit FastAPI response model; compare and sweep
currently return validated serialized JSON dictionaries rather than declared
OpenAPI response models.

An unknown scenario returns HTTP 404. Schema, catalog, roster, metric,
calibration, assignment, or runtime-preflight failures return HTTP 422 rather
than plausible empty results.

### Run submission contract

`POST /api/runs` accepts a bare sparse `CalibrationSchema` overlay:

| Field | Type | Default | Contract |
|---|---|---|---|
| `scenario` | `str` | required | Saved scenario name resolved under the configured data directory |
| `seed` | `int` | `42` | Deterministic run seed |
| `max_ticks` | `int` | `10_000` | Inclusive range 1--1,000,000 |
| `config_overrides` | `CalibrationSchema` | `{}` | Strict sparse calibration overlay described below |
| `frame_interval` | `int \| None` | `None` | Optional replay-frame cadence; supplied values are clamped to at least one tick |

```json
{
  "scenario": "test_campaign",
  "seed": 42,
  "max_ticks": 100,
  "config_overrides": {
    "roe_level": "WEAPONS_HOLD",
    "morale": {
      "base_degrade_rate": 0.02
    },
    "side_overrides": {
      "blue": {
        "cohesion": 0.9
      }
    }
  }
}
```

Do not wrap the overlay in `calibration_overrides`, and do not submit arbitrary
top-level scenario fields. Unknown/dead keys, coercible wrong JSON types,
unsupported enum values, and references to sides absent from the scenario
return HTTP 422 before a run row or task is created.

Mappings merge recursively over the scenario's existing calibration; scalar
and list values replace their predecessors. Missing fields preserve the
scenario value. The source YAML is never modified, and the canonical sparse
overlay is returned as `config_overrides` in run detail.

A 202 response means the pending row is durable and the manager owns the
background task. Deleting an active run first requests cooperative cancellation
and waits for terminal persistence. During app shutdown, new submissions are
rejected and the database remains open until run and batch workers stop.

### Configuration

All settings are overridable via environment variables with the `SW_API_`
prefix. Paths are resolved once by `ApplicationPaths`; immutable inputs and
mutable outputs have separate owners.

| Variable | Default | Description |
|----------|---------|-------------|
| `SW_API_HOST` | `127.0.0.1` | Bind address |
| `SW_API_PORT` | `8000` | Port |
| `SW_API_DB_PATH` | Checkout: `data/api_runs.db`; installed/external: user state directory | SQLite database path (`:memory:` is supported) |
| `SW_API_MAX_CONCURRENT_RUNS` | `4` | Max parallel simulation runs; must be at least 1 |
| `SW_API_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |
| `SW_API_DATA_DIR` | Discovered checkout or packaged catalog | Explicit authoritative catalog root |
| `SW_API_FRONTEND_DIR` | Checkout `frontend/dist` when present; otherwise none | Optional built SPA directory |
| `SW_API_ARTIFACT_DIR` | Checkout `artifacts/`; installed/external: user state directory | Mutable run-artifact root |
| `SW_API_MAX_STORED_EVENTS` | `50000` | Maximum stored events per run |
| `SW_API_DEFAULT_MAX_TICKS` | `10000` | Default run tick limit |

The lower-level `STOCHASTIC_WARFARE_DATA_ROOT`,
`STOCHASTIC_WARFARE_DB_PATH`, `STOCHASTIC_WARFARE_FRONTEND_ROOT`,
`STOCHASTIC_WARFARE_ARTIFACT_ROOT`, and `STOCHASTIC_WARFARE_STATE_ROOT`
variables provide the same application-resource boundary outside the API.
Explicit API settings take precedence.

### Product CLI and resource paths

The installed `stochastic-warfare` command and
`python -m stochastic_warfare` expose the same strict production entry point:

```bash
stochastic-warfare run test_campaign --seed 42 --max-ticks 10000
```

A bare scenario name resolves through the selected catalog. An absolute path,
or a relative reference containing a path component, is an explicitly
authorized file; relative explicit paths resolve from the invocation working
directory. `ApplicationPaths` otherwise discovers checkout, packaged, or
explicit-external resources without assuming that working directory. The
wheel contains the YAML catalog and CLI but not the built frontend.

### OpenAPI transport types

FastAPI's production `create_app().openapi()` document is the transport-shape
authority for the tracked TypeScript output:

```bash
uv run --no-sync python scripts/generate_openapi_types.py
uv run --no-sync python scripts/generate_openapi_types.py --check
```

`frontend/src/types/openapi.generated.ts` contains generated transport aliases.
Handwritten TypeScript remains responsible for semantic refinements and
discriminated runtime validation; generated shapes do not replace those
checks. CI uses `--check` as the drift gate.

---

## Python API

The following classes are in the `stochastic_warfare` package for direct programmatic use.

---

## Core Simulation Classes

### SimulationRuntimeFactory, PreparedScenario, and RuntimeSession

```python
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    PreparedScenario,
    RuntimeSession,
    SimulationRuntimeFactory,
)
```

This is the authoritative construction boundary for production consumers.
`prepare()` reads one YAML source once; `prepare_config()` accepts an already
typed `CampaignScenarioConfig` without temporary serialization. Both apply
strict independent `AnalysisVariant` values and return a `PreparedScenario`.
Preparation resolves and captures the selected registry entry and frozen
effective `EraRuntimeContract` before runtime RNG construction. Repeated builds
use that captured identity even if a custom registry entry is later replaced;
a new preparation observes the replacement.

| Method | Returns | Contract |
|---|---|---|
| `SimulationRuntimeFactory.prepare(path, data_root, variants)` | `PreparedScenario` | Parse one YAML source and capture source/code/data plus effective era identity |
| `SimulationRuntimeFactory.prepare_config(source_config, data_root, variants, source_label=...)` | `PreparedScenario` | Prepare a typed source directly and resolve its era contract |
| `PreparedScenario.build(variant, seed, max_ticks, ..., record_events=False, execution_mode=None)` | `RuntimeSession` | Eagerly validate exact sides, roster, loadouts, profiles, doctrine, captured era contract, and provenance; omitted mode resolves to strict failure handling |
| `RuntimeSession.run_to_completion()` | `SimulationRunResult` | Run until a public terminal result or reject |
| `RuntimeSession.step()` | `bool` | Advance one tick; `True` means the session is terminal and `False` means it can continue |
| `RuntimeSession.finalize()` | `SimulationRunResult` | Return the result only after `step()` reports terminal |
| `RuntimeSession.performance_execution_receipt()` | `PerformanceExecutionReceipt` | Cross-bind authored, typed, flattened, and committed flag owners, then return the committed typed receipt for supported effective flags and controlled production work |
| `RuntimeSession.fow_indexed_interval_record()` | `FOWIndexedIntervalRecord \| None` | Return the latest committed raw identity-addressed FOW decision record |
| `RuntimeSession.provenance()` | `RuntimeProvenance` | Capture code/data/catalog/doctrine/loadout identity, initial/arriving assignments, execution mode, ordered suppressed failures, and acceptance authority |

```python
from pathlib import Path

factory = SimulationRuntimeFactory()
prepared = factory.prepare(
    Path("data/scenarios/73_easting/scenario.yaml"),
    data_root=Path("data"),
    variants=(AnalysisVariant(variant_id="baseline"),),
)
session = prepared.build(
    "baseline",
    seed=42,
    max_ticks=10_000,
    record_events=True,
)
result = session.run_to_completion()
```

The boundary rejects an empty authored side, duplicate variant or loaded unit
ID, changed source/data/worktree identity, roster cardinality drift, and
incomplete or semantically incompatible runtime loadouts. It also rejects an
unknown era when preparing, ambiguous uniform-plus-era cadence, an
unexecutable calendar horizon, and any mismatch among the captured scenario,
era config, effective contract, or source identities before runtime
construction. Replacing a registry entry after preparation neither invalidates
nor changes an existing `PreparedScenario`; its builds use the captured
isolated values. A new preparation resolves and captures the replacement. The
boundary also constructs the production victory evaluator and optional
recorder, avoiding private consumer-specific construction.

#### Code-revision provenance

`RuntimeProvenance.code_revision` always comes from the imported runtime code,
not from the scenario or catalog path. In a source checkout, the exact owning
Git root returns `HEAD`, the dirty-tree state, and a content-sensitive
fingerprint that includes tracked and untracked changes. Clean attribution
first binds the package, API, root-import, Python-startup, and repository-script
closure to `HEAD` by path, index state, executable mode, and raw bytes. Dirty
attribution binds the complete index path/flag/mode/blob set plus an exact raw
runtime-source digest, status, binary diff, and untracked-file identity. Stable
file reads and two equal complete captures are required before publication.
Hidden index flags, ignored import shadows, symlinks, and non-regular sources
reject. An exact-root Git worktree that cannot be verified fails closed.

For an immutable application, Git is accepted only when its root equals the
build-identity application root. An enclosing deployment checkout and a nested
partial repository cannot override the complete artifact identity, and the
imported runtime must be inside the identity-owned `stochastic_warfare/` tree.
This lets a wheel run safely from an ignored virtual environment inside another
Git repository without inheriting that repository's commit. Immutable package
identity and source-manifest verification likewise require two equal stable
captures before returning provenance.

Production images contain no `.git` directory. Their build must supply
`SOURCE_REVISION` as exactly 40 lowercase hexadecimal characters and generates
`stochastic_warfare/_build_identity.json` only after the locked Python
environment has been installed. Docker's schema-1 identity covers all files
beneath `stochastic_warfare/` and `api/` plus `pyproject.toml` and `uv.lock`.
Wheel schema 2 covers the installed `stochastic_warfare/` and `api/` trees,
including bundled catalog resources, without claiming checkout-only files.
Runtime preparation recomputes the selected manifest. Missing, malformed,
symlinked, non-regular, or modified packaged source is rejected before session
construction; a verified artifact reports `dirty=False`. Bundled catalog bytes
also receive independent data/catalog revisions. An external catalog changes
those data fields but not code attribution.

The repository Docker workflow covers pull requests to `main`, pushes to
`main`, and manual dispatch. Its configured image smoke asserts that `.git` is
absent, executes a bounded production session, and verifies the supplied
commit and clean code-revision result. It also checks that docs and tests are
absent, verifies the full ledger receipt and projects its scenario sources
through `load_packaged_scenario_catalog()`, audits every API-published scenario
claim, and verifies the expected
unsupported/current-engine-regression status for 73 Easting. Phase 117's local
packaged-loader tests exercise the same ledger boundary. The Phase 117 push
prerequisite is satisfied at `84cf4c4`, but no successful hosted image result
is recorded in the repository; the smoke remains unverified pending a
successful workflow run.
The current ledger has zero accepted artifacts, so neither check proves future
nonempty accepted-evidence support in a no-`.git` image. REM-048 / Phase 135
owns the build-time attestation and package receipt required for that case.

---

### ScenarioLoader

```python
from stochastic_warfare.simulation.scenario import ScenarioLoader
```

Compatibility facade over the lower-level `simulation.scenario_loader` owner.
It loads scenario YAML and creates a fully wired `SimulationContext`. Direct
subsystem work may use it, but production
consumers that claim comparable run/analysis evidence use
`SimulationRuntimeFactory` and `RuntimeSession`.

**Constructor:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `data_dir` | `Path` | Root data directory containing `units/`, `weapons/`, `sensors/`, etc. |

**Methods:**

```python
ScenarioLoader.load(
    scenario_path: Path,
    seed: int = 42,
    *,
    calibration_overrides: Mapping[str, Any] | CalibrationSchema | None = None,
    scenario_config: CampaignScenarioConfig | None = None,
    doctrine_side_assignments: tuple[DoctrineSideAssignment, ...] | None = None,
    era_config: EraConfig | None = None,
    era_runtime_contract: EraRuntimeContract | None = None,
) -> SimulationContext
```

`scenario_config` and `calibration_overrides` are mutually exclusive.
`era_config` and `era_runtime_contract` are a paired boundary: callers must
supply both or neither. A direct load omits both and resolves the registered
era plus its effective contract before constructing `RNGManager`. A prepared
factory build supplies both captured values; the loader revalidates their exact
agreement with the captured scenario without consulting the live registry.
`doctrine_side_assignments`, when supplied, is normalized to a tuple and must
contain only typed `DoctrineSideAssignment` values for known scenario sides.

**Example:**

```python
from pathlib import Path
from stochastic_warfare.simulation.scenario import ScenarioLoader

loader = ScenarioLoader(Path("data"))
ctx = loader.load(Path("data/scenarios/73_easting/scenario.yaml"), seed=42)
```

The loader automatically:

- Validates the YAML against `CampaignScenarioConfig`
- Resolves the selected registry entry and effective contract at this lower
  boundary when both era objects are omitted, or verifies the paired captured
  `EraConfig` and `EraRuntimeContract` supplied by `PreparedScenario`
- Validates and merges a sparse calibration overlay without modifying YAML, or
  accepts a mutually exclusive prevalidated effective config
- Loads unit, weapon, ammo, sensor, and signature definitions
- Preflights reachable initial and reinforcement equipment through the typed
  registry, then retains one `RuntimeLoadoutBuilder` for initial, arriving, and
  checkpoint-reconstructed loadouts
- Resolves declared time-on-target missions against exact initial-roster
  runtime attachments before constructing the indirect-fire engine
- Creates terrain, environment, detection, combat, movement, morale, C2, and logistics engines
- Wires Schools, Escalation, and DEW when their configuration enables them
- Constructs EW, Space, and CBRN suites only when enabled and permitted by the
  validated effective era; contradictory enabled blocks fail loading
- Enforces the effective era's GPS, thermal-sight, data-link, PGM, and sensor
  allowlist gates while building the runtime
- Constructs the clock, engine cadence, medical config, and maintenance config
  from the same strict effective era contract

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
| `strict_mode` | `bool \| None` | `None` | Legacy compatibility selector; `True` means strict and `False` explicitly requests degraded mode |
| `execution_mode` | `RuntimeExecutionMode \| None` | `None` (resolves to `STRICT`) | Typed runtime failure policy; must agree with `strict_mode` if both are supplied |

**Methods:**

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `run()` | -- | `SimulationRunResult` | Run to completion (victory or max ticks) |
| `step()` | -- | `bool` | Execute one tick. Returns `True` when terminal and `False` while execution can continue |

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

Strict mode is the production default: subsystem, subscriber, committed-event,
and recorder-integrity failures propagate. Degraded mode records each
suppressed failure in deterministic sequence with tick, logical time,
subsystem, operation, exception type, and message. A degraded runtime cannot
create or restore an authoritative checkpoint. Standalone recorder
compatibility flags do not override the engine's bound failure policy.

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
| `duration_s` | `float` | Logical simulated elapsed seconds |
| `victory_result` | `VictoryResult` | Who won, how, and when |
| `campaign_summary` | `Any` | Campaign-level statistics (or `None`) |
| `execution_mode` | `RuntimeExecutionMode` | Effective strict or degraded policy |
| `suppressed_failures` | `tuple[SuppressedRuntimeFailure, ...]` | Ordered degraded-mode failure evidence |
| `authoritative` | `bool` | `True` only for strict results with no suppressed failures |

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

**Key methods and properties:**

| Member | Returns | Description |
|--------|---------|-------------|
| `start()` | -- | Begin recording |
| `stop()` | -- | Stop recording |
| `events` | `list` | Copy of all recorded events (property) |
| `events_of_type(event_type_name)` | `list` | Events filtered by type |
| `snapshots` | `list[dict]` | Copy of state snapshots (property; captured at `snapshot_interval_ticks`) |

When bound to a runtime, recorder overflow and extraction failures use the
engine's strict/degraded authority. The committed state transition and event
publication remain ordered; degraded subscriber failures are collected only
after all subscribers have had the deterministic chance to observe the event.

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
| `territory_control` | Side controls all assigned objectives |
| `force_destroyed` | Opponent loses > 70% of forces (configurable) |
| `morale_collapsed` | Opponent has > 60% units routed/surrendered |
| `supply_exhausted` | Opponent's average supply < 20% |
| `time_expired` | Scenario duration exceeded -- uses composite scoring |
| `ceasefire` | Negotiated war termination (escalation system) |
| `armistice` | Negotiated armistice |
| `attrition_ratio` | Configured force-loss ratio is reached |

**Composite Victory Scoring (time_expired):**

When a scenario reaches its time limit, `evaluate_force_advantage()` determines the winner using a composite score:

```python
VictoryEvaluator.evaluate_force_advantage(
    units_by_side,
    morale_states=ctx.morale_states,       # read-only Mapping[str, MoraleState]
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

### Historical claim and backtest boundary

```python
from stochastic_warfare.validation.historical_backtest import (
    HistoricalBacktestRunner,
    HistoricalClaimLedgerLoader,
    HistoricalStudyLoader,
    create_completed_artifact,
    evaluate_joint_coverage,
    load_historical_artifact,
    write_historical_artifact,
)
```

This is the production historical-outcome evidence boundary. It is distinct
from the legacy comparison helpers below.

| API | Contract |
|---|---|
| `HistoricalClaimLedgerLoader(root).load(path)` | Verify the ledger self-digest, exact claim locator/content binding, semantic matched-span review inventory, and accepted evidence |
| `HistoricalClaimLedgerLoader(root).load_scenario_catalog(path)` | Load the full checkout ledger while source-auditing every API-published scenario claim |
| `HistoricalClaimLedgerLoader(root).load_packaged_scenario_catalog(path)` | Verify the full packaged ledger receipt before projecting its scenario-only review/claim set; the current no-docs/no-tests package supports the zero-accepted ledger and fails closed on a future accepted reference until REM-048 |
| `HistoricalStudyLoader(root).load(path)` | Validate the typed source lineage, claim/metric scopes, event boundaries, seeds, runtime inputs, and acceptance policy |
| `HistoricalBacktestRunner(prepared, plan).run()` | Build every seed from one `PreparedScenario`, retain typed terminal/metric receipts and ordered vectors, then return the exact evaluation and eligibility reasons |
| `evaluate_joint_coverage(...)` | Form the per-seed conjunction of all gating metrics and apply the exact one-sided Clopper--Pearson lower bound |
| `create_completed_artifact(...)` | Construct a digest-bearing completed `PASS` or `FAIL` artifact |
| `create_error_artifact(...)` | Record a post-start operational `ERROR` without inventing an evaluation or verdict |
| `write_historical_artifact(path, artifact)` | Write atomically, fsync, and reload-verify the exact artifact |
| `load_historical_artifact(path)` | Strictly parse and revalidate schema, digests, identities, evaluation, and eligibility |

`PASS` is necessary but not sufficient for promotion. Accepted evidence also
requires a clean, immutably predeclared, source-backed independent study,
exact metric bindings, committed ledger/artifact identities, compatible Git
ancestry, and unchanged runtime source/data identities. `FAIL` is completed
negative evidence. `ERROR` is not a verdict and is never promotable. An invalid
plan rejects before an artifact is produced.

The repository runner is `scripts/run_historical_backtest.py`; generated output
belongs under ignored `artifacts/evidence/phase-117/`. The retained 73 Easting
result is `FAIL` with 0/20 joint successes, lower confidence bound 0.0, and no
promotion eligibility. Its artifact SHA-256 is
`57bfe7d89575e721d9cee30c213505c760da3cede642624c7ed7532051e524f4`,
and its local, unpublished locator is
`branch=evidence/full; path=docs/evidence/phase-117/73-easting-phase117.json`,
pending a separate evidence-remote or Git LFS decision. See the
[contract](../specs/historical-outcome-envelope-integrity.md).

### MonteCarloHarness

```python
from stochastic_warfare.legacy.validation.monte_carlo import MonteCarloHarness
```

Runs multiple independent iterations through the quarantined legacy validation
interface. It remains available for compatibility, but its `ScenarioRunner`
path is not
the authoritative evidence boundary for production batch, comparison, sweep,
doctrine, or historical-validation claims. Use `SimulationRuntimeFactory` and
the shared analysis helpers for current-engine distribution claims, and the
typed historical backtest boundary above for historical verdicts.

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
| `compare_to_historical()` | `historical: list[HistoricalMetric]` | `ComparisonReport` | Legacy reference diagnostic only; cannot issue a production historical verdict |
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

Central stochastic authority. It creates independent conventional per-module
generators and owns the typed identity-addressed FOW allocation/commit
lifecycle used when parallel completion order must not select a different
decision.

**Constructor:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `seed` | `int` | Master seed for reproducibility |

**Methods:**

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `get_stream()` | `module_id: ModuleId` | `np.random.Generator` | Independent PRNG stream for a module |
| `begin_fow_detection_interval()` | `engine_tick, reporting_sides, module=DETECTION` | `FOWIndexedAllocation` | Begin one strict ordered-side indexed decision transaction |
| `prepare_fow_detection_interval_commit()` | `allocation` | `FOWIndexedCommitPlan` | Stage the canonical transcript record without publication |
| `commit_fow_detection_interval()` | `allocation` | `FOWIndexedIntervalRecord` | Validate and publish a complete indexed interval |
| `abort_fow_detection_interval()` | `allocation` | `None` | Poison and abort an incomplete indexed interval |

**PRNG Discipline:**

- Each conventional `ModuleId` gets its own stream via
  `get_stream(ModuleId.COMBAT)`, `get_stream(ModuleId.DETECTION)`, etc.
- Streams are independent -- adding randomness in one module doesn't affect others
- Indexed FOW values bind to strict semantic identities and a canonical
  transcript rather than worker draw order
- Same seed, code/data/configuration, and runtime topology reproduce the same
  conventional streams and indexed decisions

---

### EventBus

```python
from stochastic_warfare.core.events import EventBus
```

Publish/subscribe event system for recorder and subsystem consumers. Production
morale inputs are coordinated directly by the simulation battle path; morale
does not currently subscribe to combat events and instead publishes committed
transition events for downstream consumers.

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

**Key properties and methods:**

| Member | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `current_time` | -- | `datetime` | Current logical UTC time (property) |
| `elapsed` | -- | `timedelta` | Logical elapsed time (property) |
| `tick_count` | -- | `int` | Number of ticks advanced (property) |
| `tick_duration` | -- | `timedelta` | Current tick duration (property) |
| `advance()` | -- | `datetime` | Advance one tick and return the new logical time |
| `set_tick_duration()` | `duration: timedelta` | -- | Change tick duration |

---

## Configuration Stack

### CampaignScenarioConfig

The top-level pydantic model for scenario YAML files. Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Scenario display name |
| `date` | `str` | Historical date (if applicable) |
| `duration_hours` | `float` | Strict finite positive scenario duration in hours |
| `era` | `str` | Registered era name; defaults to `modern` |
| `tick_duration_seconds` | `float \| None` | Fixed scenario cadence; declared time-on-target missions require a positive whole-second value |
| `terrain` | `TerrainConfig` | Terrain dimensions, type, features |
| `sides` | `list[SideConfig]` | Force composition per side |
| `objectives` | `list[ObjectiveConfig]` | Spatial objectives |
| `victory_conditions` | `list[VictoryConditionConfig]` | Win conditions |
| `reinforcements` | `list[ReinforcementConfig]` | Scheduled arrivals |
| `calibration_overrides` | `CalibrationSchema` | Typed calibration overrides (see below) |
| `ew_config` | `dict \| None` | Electronic warfare configuration |
| `space_config` | `SpaceConfig \| None` | Strict selected constellations, space services, finite ASAT assets, and scheduled exact-target orders |
| `cbrn_config` | `dict \| None` | CBRN effects configuration |
| `escalation_config` | `dict \| None` | Presence enables default escalation/unconventional engines; authored tuning is not consumed (REM-050) |
| `school_config` | `SchoolScenarioConfig \| None` | Strict exact `unit_assignments`; legacy side/default proxy keys reject |
| `commander_config` | `CommanderScenarioConfig \| None` | Commander tuning plus exact initial/future per-unit profile assignments |
| `dew_config` | `dict \| None` | Presence enables DEW; values are validated as `DEWConfig` tuning when the runtime constructs the engine |
| `indirect_fire` | `IndirectFireScenarioConfig` | Strict gate and exact preplanned time-on-target missions |

Commander declaration is all-side or absent. Behavior is active only when
every scenario side supplies a catalog-backed `commander_profile`; when every
side omits it and `commander_config` is absent, no commander engine is created.
Partial profiles, or any `commander_config` with blank side profiles, reject.
`commander_config.assignments` and `school_config.unit_assignments` may target
exact planned initial or reinforcement IDs; unknown units, profiles, or
schools fail eagerly before unit construction. Initial and arriving units are
registered with commander, OODA, school, movement, morale, loadout, and
logistics owners transactionally, and their assignment state participates in
checkpoint continuation.

`SchoolScenarioConfig` rejects unknown fields. In particular,
`enable_schools`, `blue`/`red`, and `blue_school`/`red_school` are not side
assignment authorities. Typed per-side doctrine policies belong to analysis
variants and remain separate from source-scenario exact unit assignments.

---

### SpaceConfig and ASAT events

`SpaceConfig` rejects unknown fields and owns `enable_space`,
`constellation_ids`, `imint_fusion_constellation_ids`, `enable_asat`,
`asat_assets`, and `asat_orders`. Fusion constellation IDs must be a subset of
the selected topology and resolve to supported optical/SAR imaging
constellations. A nonempty fusion selection also requires
`calibration_overrides.enable_space_effects: true`. Other definitions fail
explicitly.
Each asset has a unique `asset_id`, exact catalog `weapon_id`, owning scenario
side, and finite `rounds_available`. Each order has a unique `order_id`, exact
asset and satellite IDs, and a finite `execute_at_s` within the scenario
duration. Production supports catalog definitions of type
`DIRECT_ASCENT_KKV`; co-orbital and laser ASAT assets fail explicitly.

The generic run-events endpoint exposes each due action as
`ASATEngagementEvent`. Its data includes order/asset/weapon IDs,
`attacker_side`, target satellite/constellation IDs, scheduled and execution
times, `launched`, `pk`, `hit`, exact `outcome`/`reason`, debris generated,
rounds remaining, and before/after constellation counts. A successful hit
records `ConstellationDegradedEvent` first. The existing `event_type` and
`side` filters select these events without a specialized endpoint.

Selected IMINT constellations create immutable owner-scoped `SpaceISRReport`
values with exact observation/availability times and uncertainty, a terminal
`IntelDeliveryReceipt` ledger with report digest and resulting track, and one
`IMINTTrackAssociation` per owner/target. Generation and delayed delivery are
transactional and checkpointed. This typed internal state is not a claim of
ordinary REST/UI event exposure or direct injection into generic fog-of-war
contacts. Format 116 independently restores nonempty roster-backed
`SideWorldView.contacts`; it does not convert Space ISR receipts into those
contacts.

---

### IndirectFireScenarioConfig and time-on-target events

`IndirectFireScenarioConfig` rejects unknown fields and owns
`enable_time_on_target` plus an ordered `time_on_target_missions` list. Each
mission declares a unique ID, exact initial target unit, finite ENU target
point, whole-second common impact time, positive rounds per battery, and one to
six exact batteries. A battery identifies its initial unit,
`source_equipment_index`, weapon, ammunition, and authored whole-second
fire-control time of flight.

`ScenarioLoader` resolves those declarations against the production
`RuntimeLoadouts` product. Identity, side, weapon category/domain,
ammunition lethality/compatibility, range, aggregate inventory,
quantity-aware cooldown, and fixed-cadence failures are explicit load errors.
For `POST /api/runs/from-config`, malformed nested schema fields return HTTP
422; roster/catalog semantic failures can occur in the accepted background
run and are then exposed as terminal `failed` run detail.

The generic events endpoint exposes each terminal mission as
`TimeOnTargetMissionEvent`:

```text
GET /api/runs/{id}/events?event_type=TimeOnTargetMissionEvent&side=blue
```

Its data includes mission/attacker/target identity, target point, scheduled and
processing times, ordered exact-attachment battery results, generated and
near-target impact counts, `outcome` (`completed`, `partial`, or `rejected`),
`target_effect`, and before/after target status. Fired batteries expose their
round and impact counts; rejected batteries expose one of
`battery_inactive`, `battery_moving`, `battery_displaced`,
`weapon_inoperable`, `insufficient_ammunition`, or `weapon_cooldown`. The
normal `side` filter matches `attacker_side`; no specialized endpoint is
required.

The supported boundary uses authored whole-second times of flight and
positive-radius lethal tube-artillery/mortar ammunition. Rocket-artillery time
on target, automatic firing-table solutions, and live-magazine reload
provenance are not supported.

---

### CalibrationSchema

```python
from stochastic_warfare.simulation.calibration import CalibrationSchema
```

Pydantic model (`extra="forbid"`) for authored scenario tuning parameters.
Scenario loading resolves it once into recursively immutable
`ResolvedCalibration`; `ctx.cal_flat` is a read-only compatibility view and
`to_flat_dict()` returns a detached dictionary. Mistyped authored keys are
caught at parse time. Key fields are organized by domain:

**Combat & Engagement:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hit_probability_modifier` | `float` | `1.0` | Global hit-probability multiplier |
| `side_overrides` | `dict[str, SideCalibration]` | `{}` | Per-side cohesion, force ratio, deployment, hit probability, and target-size fields |
| `defensive_sides` | `list[str]` | `[]` | Scenario sides that hold defensive posture |
| `target_selection_mode` | `"closest" \| "nearest" \| "threat_scored"` | `"threat_scored"` | Closest-target selection (`nearest` is an alias) or threat scoring |
| `roe_level` | `"WEAPONS_HOLD" \| "WEAPONS_TIGHT" \| "WEAPONS_FREE" \| None` | `None` | Scenario-wide initial rules of engagement |
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
| `wind_bvr_missile_speed_mps` | `float` | `1000.0` | Reference missile speed used to normalize closing-axis wind; crosswind has no signed range contribution |

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

Guerrilla retreat is supported when the unconventional engine reports zero
blend probability. If a positive populated-area result reaches the battle
guard, `UnsupportedGuerrillaBlendError` is raised before retreat, status,
morale, events, or COMBAT/MORALE RNG state changes; it is never translated to
`ROUTING`. This is a direct fail-closed guard, not a production-loaded positive
path: the factory context exposes `population_manager`, while the current
battle lookup has no matching density-query contract and therefore cannot
recognize a populated area. REM-032/Phase 119 owns that lookup and the future
non-morale concealment lifecycle.

**Environment Wiring (Phase 78):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_ice_crossing` | `bool` | `False` | Units on ice move at 50% speed |
| `enable_bridge_capacity` | `bool` | `False` | Bridges enforce weight limits |
| `enable_environmental_fatigue` | `bool` | `False` | Heat/cold stress from WBGT/wind-chill degrades performance |

**LOD compatibility fields (retired from tuning):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_lod` | `bool` | `False` | Must remain `False`; the sensing-only approximation is explicitly unsupported after failed semantic validation |
| `lod_nearby_interval` | `int` | `5` | Compatibility value must remain exactly `5` |
| `lod_distant_interval` | `int` | `20` | Compatibility value must remain exactly `20` |
| `lod_hysteresis_ticks` | `int` | `3` | Compatibility value must remain exactly `3` |

**Performance semantic classifications (Phase 118):**

| Field | Default | Classification | Current support | Retained v7 verdict |
|-------|---------|----------------|-----------------|---------------------|
| `enable_detection_culling` | `True` | Semantics-preserving execution optimization | `supported_exact_validated` | `PASS` |
| `enable_scan_scheduling` | `False` | Model-fidelity approximation | `unsupported_failed_semantic_validation` | `FAIL` |
| `enable_lod` | `False` | Model-fidelity approximation (sensing cadence only) | `unsupported_failed_semantic_validation` | `FAIL` |
| `enable_soa` | `False` | Semantics-preserving execution optimization | `supported_exact_validated` | `PASS` |
| `enable_parallel_detection` | `False` | Semantics-preserving execution optimization | `supported_exact_validated` | `PASS` |

The runtime receipt proves which branch executed and how much work it admitted,
deferred, selected, or dispatched. These classifications are semantic
contracts, not historical calibration or speed evidence. The immutable
schema-2 v7 study completed all 96 pairs / 396 attempts and independently
reloaded as a terminal `FAIL` under `EXTERNALLY_CONTENDED`, with manifest
artifact SHA-256
`bf9e00ce4a7774af29b5657c49bbbe4481b407a966d9922e48970022f5c6ad86`.
Current YAML, API, comparison/sensitivity, live runtime, and current-checkpoint
boundaries reject either unsupported flag enabled and reject nondefault LOD
compatibility values. Authored configuration, typed calibration, flattened
calibration, and the committed receipt must agree before work or receipt
exposure. Use `GET /api/meta/performance-flags` for the canonical registry and
retained evidence identity. The accepted qualified-negative postmortem closed
Phase 118 / REM-031; REM-055 / Phase 142 tracks the separately measured
transactional-FOW runtime regression without changing this API contract.

**Targeting Integrity (Phase 115):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_sensing_aware_standoff` | `bool` | `True` | Require a current usable sensing/fire-control solution before automatic tactical standoff; explicit `False` authorizes zero automatic standoff rather than restoring catalog-range holding |

**Flat Dict Optimization (Phase 86):**

`CalibrationSchema.to_flat_dict(sides)` returns a detached compatibility
dictionary. Scenario loading converts the effective schema to immutable
`ResolvedCalibration`, including its recursively frozen flat view, so callers
cannot mutate the live calibration owner through `ctx.cal_flat`.

**Meta-Flags (Phase 80):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_all_modern` | `bool` | `False` | Activates all 21 non-deferred `enable_*` flags at once (convenience meta-flag) |

The legacy opt-in consequence `enable_*` flags default to `False` for backward
compatibility. `enable_sensing_aware_standoff` is deliberately strict and
defaults to `True`; explicit `False` does not restore the defective fallback.
Enable other optional effects in scenario YAML as needed. The
`enable_all_modern` meta-flag is available for frontend convenience, but
per-scenario selective flags are preferred for performance.

---

## Usage Patterns

### Basic Single Run

```python
from pathlib import Path
from stochastic_warfare.simulation.runtime import (
    AnalysisVariant,
    SimulationRuntimeFactory,
)

prepared = SimulationRuntimeFactory().prepare(
    Path("data/scenarios/73_easting/scenario.yaml"),
    data_root=Path("data"),
    variants=(AnalysisVariant(variant_id="baseline"),),
)
session = prepared.build(
    "baseline",
    seed=42,
    max_ticks=10_000,
    record_events=True,
)
result = session.run_to_completion()
print(f"{result.victory_result.winning_side} wins by {result.victory_result.condition_type}")
```

### Monte Carlo Batch

```python
from stochastic_warfare.tools._run_helpers import run_scenario_batch

batch = run_scenario_batch(
    "data/scenarios/73_easting/scenario.yaml",
    overrides={},
    num_iterations=100,
    base_seed=42,
    max_ticks=10_000,
    metric_names=["exchange_ratio"],
    data_dir=Path("data"),
)
print(batch.statistics_dict()["exchange_ratio"]["mean"])
print(batch.metric_values("exchange_ratio"))
```

This characterizes the current production distribution. Historical validation
additionally requires a predeclared source-backed envelope and held-out
production evidence. Phase 117 provides that separate typed study, runner,
joint-evaluation, artifact, and promotion boundary; ordinary batch output does
not become a historical verdict.

### Step-by-Step Execution

```python
session = prepared.build(
    "baseline",
    seed=42,
    max_ticks=10_000,
    record_events=True,
)

# RuntimeSession.step() returns True at terminal.
while not session.step():
    tick = session.context.clock.tick_count
    if tick % 100 == 0:
        assert session.recorder is not None
        print(f"Tick {tick}: {len(session.recorder.events)} events so far")

result = session.finalize()
```

### Checkpoint and Restore

Current checkpoint-participating runtime owners support the coordinated
`get_state()` / `set_state()` contract:

```python
# Advance a fresh branch runtime to a nonterminal checkpoint.
branch = prepared.build(
    "baseline",
    seed=42,
    max_ticks=10_000,
    record_events=True,
)
if branch.step():
    raise RuntimeError("scenario became terminal before the branch checkpoint")
state = branch.engine.get_state()

# Construct a fresh compatible runtime from the same prepared source.
restored = prepared.build(
    "baseline",
    seed=42,
    max_ticks=10_000,
    record_events=True,
)
restored.engine.set_state(state)

# Continue from the deterministic branch point.
result = restored.run_to_completion()
```

Current-format checkpoints require an exact effective scenario configuration,
era contract, and runtime topology. An incompatible restore fails before
mutating the target. See the
[checkpoint state contract](../specs/checkpoint-state.md) for the canonical
schema and bounded legacy-migration rules.

The current engine checkpoint schema is version 118. In addition to force,
loadout, logistics, space/ASAT, and time-on-target state, it preserves one
`morale_runtime` envelope, one fully effective `era_runtime_contract`, and one
strict tactical-targeting interval/picture/decision/revalidation envelope. One
strict fog-of-war envelope retains complete roster-backed ordinary side views,
bounded current observer witnesses, fusion state, exact contact-to-fusion track
object identity, and the cross-validated DETECTION RNG mirror. Current FOW
targeting decisions keep their exact consumability only when that contact,
witness, interval, roster, and loadout evidence agrees.
Format 118 additionally preserves the performance execution receipt, sensing
cadence, FOW observer topology, detection scan counts, and the complete
`RNGManager`-owned indexed FOW transcript. Cross-owner completeness, interval,
entry, cadence, and effective-flag disagreements reject before mutation.
The private publication plan is exact-owner-, content-, type-, shape-, and
alias-bound. Disabled runtimes may retain explicitly allocated empty side views
and non-FOW Space tracks, while ordinary contacts/witnesses/FOW IDs reject.
Dynamic registration may checkpoint durable FOW state between targeting
intervals and refreshes it on the next engine step.
`SimulationContext.morale_states` remains a stable read-only
`Mapping[str, MoraleState]` for runtime and frame consumers, but it is not a
second checkpoint store; `RNGManager` alone persists the MORALE generator.
Commander/OODA assignments, bounded movement diagnostics, and typed Space ISR
pending reports, delivery receipts, and owner/target IMINT associations remain
included. Current-format restore is atomic and validates exact topology,
status/route consistency, chronology, owner/RNG bindings, selected era
identity, and clock/current-resolution agreement. Explicit version 116 and
every other non-current version reject.

Phase 112's typed Space ISR proof uses an explicit empty ordinary-contact
topology, including publicly allocated empty views. Phase 116 separately
implements nonempty roster-backed FOW continuation.
Active/inactive deception and custom/populated COP/data-link state remain
unsupported checkpoint boundaries under REM-046 and REM-036 and reject rather
than being silently discarded.

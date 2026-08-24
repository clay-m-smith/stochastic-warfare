# Tiered Modular Monolith Consolidation

**Contract status:** Accepted for implementation on 2026-08-22

**Implementation status:** Complete on 2026-08-23

**Release condition:** The Complete status is valid only for an exact frozen
revision that passes the release gate recorded in the
[consolidation log](../devlog/consolidation-tiered-modular-monolith.md#release-condition)

**Owner decision:** Retain one deterministic modular monolith; separate large
generated evidence, not the engine and its authoritative catalogs.

**Execution boundary:** This program precedes Phase 119. Its accepted
postmortem closes REM-052 and REM-053 and retires their planned Phases 139 and
140 before start. Other remediation ordering and numbering remain unchanged.

## Purpose

Stochastic Warfare has a sound domain-package dependency direction, but its
active test suite, validation metadata, documentation history, packaging, and
largest runtime coordinators have accumulated by development phase rather than
by durable ownership. This contract turns the repository into a tiered modular
monolith without weakening deterministic execution, checkpoint compatibility,
historical-claim integrity, or production-path proof.

The program has four ordered goals:

1. repair verified runtime safety defects before structural movement;
2. make tests and validation evidence belong to stable subsystem contracts;
3. make the checkout, container, Python distribution, API, frontend, and
   evidence boundaries explicit and independently testable; and
4. split oversized coordinators behind compatibility facades while preserving
   tick order, RNG ownership, state identity, and serialized behavior.

## Current baseline

The accepted starting inventory is the clean `main` revision
`0265e54fa125d5258223c5b224b8de56eb6254a9`. It established:

- a large, exact six-partition Python suite whose active paths and evidence
  metadata were substantially organized by implementation phase;
- a phase-history corpus large enough to obscure current product guidance;
- a checkout and Docker image that contain the full application, but a Python
  wheel that omits authoritative catalogs/frontend/build identity and an sdist
  that includes nearly the complete repository; and
- `BattleManager`, `SimulationContext`/`ScenarioLoader`, FOW, loadout, and
  equipment-mapping owners whose size and mixed responsibilities impede safe
  change.

The detailed current inventory belongs only in the compact consolidation log.
Tests prove relational completeness and zero unresolved deficits rather than
asserting permanent cardinalities.

## Closure state

The 2026-08-23 postmortem accepted the implementation with scope on target,
high quality, fully proven integration, and no new deficits. The exact evidence,
qualifications, exclusions, and transactional rule are recorded once in the
[consolidation log](../devlog/consolidation-tiered-modular-monolith.md#postmortem).
The Complete transition is revoked and no commit is permitted for a revision
whose final single-revision release gate fails.

## Repository tiers

The repository remains one source revision with these logical tiers:

```text
runtime kernel       core/domain packages and deterministic owner interfaces
application          simulation facade, API, MCP, CLI, catalog and web bundle
verification         unit, contract, integration, API, E2E and benchmark tests
engineering          scripts, specifications, current remediation truth
archive              ignored artifacts and the append-only evidence history
```

Engine code, authoritative catalogs, runtime factory, checkpoint/RNG owners,
API contracts, provenance validation, the lockfile, and system tests stay in
the same Git revision until a separately approved composite release-manifest
contract can prove equivalence across revisions. A microservice or engine/data
multi-repository split is a non-goal.

## Requirements

### R1. Strict authoritative execution

- `PreparedScenario.build()` and every production runtime consumer must fail
  on an enabled subsystem exception by default.
- API, MCP, analysis, scenario evaluation, campaign validation, historical
  validation, and accepted-claim verification must use strict execution.
- A non-strict interactive mode may remain only as an explicitly named
  degraded mode. It must publish every suppressed subsystem failure in typed
  result/provenance state and must never produce acceptance evidence.
- Rejection must preserve the original exception and must not publish a
  successful terminal result.

### R2. Deferred OODA decisions

- A successfully propagated decision with positive delay must become a typed,
  independently polled deferred decision owned by the C2/battle boundary.
- Maturity is based only on logical simulation time. It consumes no additional
  RNG draw and executes exactly once.
- Planning initiation, propagation, delay maturity, misinterpretation, decision
  execution, and OODA phase advancement must not strand a unit in an expired
  phase.
- The complete deferred queue, including due time and typed effect, must survive
  checkpoint/restore and produce the same continuation as an uninterrupted run.

### R3. Movement and position correctness

- Tidal-current projection must use the current unit's resolved movement vector
  after that vector exists. No unit may consume another unit's local vector.
- Enabled aligned, opposed, cross-current, first-unit, multi-unit, and disabled
  behavior must be observed through the production movement executor.
- Position misinterpretation must update the exact addressed live unit through
  a typed unit index or `SimulationContext` owner; no unresolved local name is
  permitted.
- Broad exception handling may not conceal programming errors in either path.
- A discovered air-combat defect is repaired in the same correctness tranche:
  `AirCombatEngine.resolve_air_engagement()` accepts an explicit finite,
  positive effective BVR range modifier whose default is `1.0`. The production
  air-combat route supplies the modifier derived from enabled headwind or
  tailwind conditions, and the engine applies it only to BVR range
  eligibility/resolution. Enabled headwind and tailwind plus disabled and
  default-compatibility controls must be behavioral. This input adds no RNG
  draw, mutable state, event-order change, or checkpoint field.
- A discovered sonar-culling defect is repaired in the same correctness
  tranche: when acoustic layers are enabled, the engagement prefilter uses a
  deterministic conservative bound covering the largest supported positive
  surface-duct and convergence-zone multiplier. The existing acoustic resolver
  remains the exact eligibility gate, so thermocline and convergence-zone
  shadow penalties, disabled behavior, and non-sonar behavior are unchanged.
  Production tests must cover positive duct/CZ acquisition, negative and
  disabled controls, candidate order, and same-seed RNG continuation. This
  repair adds no RNG draw, event-order change, mutable state, or checkpoint
  field.

### R4. Static safety floor

- Undefined names (`F821`) are repository errors. Annotation-only references
  must use `TYPE_CHECKING`, real imports, or narrowly justified per-line
  suppression rather than a global ignore.
- Global lint exemptions for unused imports/locals are removed or replaced by
  scoped compatibility suppressions as the affected code is migrated.
- Complexity and dead-code reports are review inputs. They do not by themselves
  authorize deletion or behavior claims.

### R5. Durable test ownership

Active tests are organized by product boundary, not implementation phase:

```text
tests/unit/<domain>/
tests/integration/{runtime,checkpoint,targeting,scenarios}/
tests/contracts/{configuration,serialization,determinism,repository_policy}/
tests/api/
tests/e2e/
tests/benchmarks/
```

- Phase work may use temporary tests while in progress, but postmortem must
  classify each as **promote**, **merge**, **retire**, or **archive**.
- Active test filenames and directories must not use a phase number as their
  ownership identity after promotion.
- Production-path behavior, negative/disabled controls, unique regressions,
  RNG topology, serial/parallel equality, checkpoint continuation and
  atomicity, and public API/recorder exposure are preserved.
- Source-string, import-presence, non-null, copied-formula, archive-layout, and
  phase-delivery checks cannot replace behavioral proof. They are retired only
  after their durable obligation is mapped to equivalent or stronger evidence.
- Shared builders remain domain-specific and transparent; there is no universal
  fixture that hides runtime construction or stochastic authority.

### R6. Test-evidence classification

- Test quality classification is attached to a stable test definition or
  contract ID, not every expanded pytest node ID.
- Parameterization must not duplicate identical metadata entries.
- The validator rejects newly introduced weak/no-direct tests unless they carry
  an explicit reviewed structural/invariant classification.
- A structural classification never upgrades a test into behavioral closure
  evidence.
- Immutable Phase 112 delivery inventories move to archive/history; current
  collection must not depend on a historic phase-start commit.
- Collection must not read large exact-node ledgers merely to add markers.

### R7. CI tiers

- **Pull request:** lint/static/data/docs, standard contracts, API, E2E, and
  dependency-profile tests relevant to the change.
- **Main:** full standard/API/E2E/terrain and container/product smoke.
- **Nightly:** slow-only, benchmark-only, and slow-benchmark partitions.
- **Manual/release evidence:** historical backtests, held-out studies,
  calibration, and heavyweight paired comparisons.
- A published failed study is not rerun as “held-out” acceptance evidence on
  every pull request. Its artifact schema/evaluator use synthetic or explicitly
  diagnostic inputs in routine CI.
- One revision-bound collection manifest is reused by execution jobs when
  exact-node evidence is required. Generated matrices replace hand-authored
  shard repetition.
- The six authoritative partitions remain exact, non-empty, and disjoint until
  a later explicit partition contract replaces them.

### R8. Documentation and claim scope

- Public navigation contains current guides, concepts, reference, and supported
  capability contracts. Engineering navigation contains specifications,
  current backlog, roadmaps, and retained devlogs.
- Historical phase documents become immutable history after closure. They are
  not perpetual current-truth surfaces and need not be edited for unrelated
  future changes.
- Main retains a compact phase index and open remediation truth. Detailed
  closed narratives may be consolidated into block retrospectives while exact
  originals remain in archive history.
- Historical-claim scanning covers current public claims, API/frontend public
  surfaces, scenario YAML, and explicit claim-bearing tests. It does not hash
  unrelated prose across every devlog, skill mirror, or test file.
- The current strict ledger is schema 2 / claim-source scanner 3. Its closed
  source kinds and semantic-span digests reject missing, stale, ambiguous, or
  extra reviewed dispositions.
- Review identity binds the exact matched claim span or stable claim locator,
  not the whole source file. The ledger digest is computed by validation rather
  than stored as a self-referential maintenance field where possible.
- Integrity remains fail-closed: every discovered current claim has one typed
  disposition, stale locators reject, and storage never upgrades a verdict.

### R9. Evidence and generated output

- Generated vectors, JUnit, traces, profiles, manifests, and raw studies remain
  below ignored `artifacts/` during normal work.
- Full retained evidence lives in an append-only `evidence/full` history on a
  separate evidence remote, LFS-backed store, or documented object store.
- Main retains only compact typed receipts, immutable locators, digests,
  verdicts, qualifications, and reproducibility inputs.
- The evidence history absorbs main only; main never merges archive commits.
- Runtime validation on main must not require the evidence remote to be
  fetched.

### R10. Supported application artifacts and resource paths

- Until isolated package tests pass, source checkout and the Docker image are
  the supported runnable application artifacts; the Python wheel is not
  described as standalone.
- A typed `ApplicationPaths`/resource resolver owns catalog root, scenario
  root, historical-claim receipt, database, frontend bundle, and generated
  artifact locations. API, MCP, CLI, validation, and Docker inject or derive
  this owner rather than assuming the current working directory.
- Installed package resources use `importlib.resources` or an explicitly
  configured external catalog root. Missing resources reject with a precise
  error.
- Repository-only tools never infer that their output belongs under tracked
  documentation.

### R11. Product CLI and version authority

- The application exposes one typed headless entry point:
  `stochastic-warfare run ...` and `python -m stochastic_warfare`.
- The CLI runs scenarios only through
  `SimulationRuntimeFactory -> PreparedScenario -> RuntimeSession`.
- Repository validation, calibration, and evidence commands remain separate
  tools and cannot be confused with the user runner.
- Python package version has one source of truth. Runtime packages read
  installed distribution metadata; frontend versioning is explicitly bound or
  explicitly independent.

### R12. Truthful wheel and sdist

- Base installation must not advertise entry points whose dependencies are
  absent. API and MCP entry points are provided by their appropriate extras or
  distributions.
- Wheel and sdist contents use explicit allowlists. The wheel contains every
  resource required by its declared capability; the sdist excludes tests,
  frontend sources, docs, workflows, agent metadata, and generated evidence
  unless deliberately required to build the declared artifact.
- Isolated no-Git installation tests prove import, CLI help, declared resource
  behavior, API-extra startup, build identity, and one bounded production
  scenario under the supported catalog contract.
- Setuptools SCM is configured as the actual version/file authority or removed.

### R13. API/frontend contract

- FastAPI OpenAPI is the shape authority for transport DTOs.
- Frontend transport types are generated from, or mechanically checked against,
  the exact OpenAPI document in CI.
- Semantic frontend validators remain handwritten where they enforce more than
  transport shape.
- The generic `api` package may move to `stochastic_warfare_api` only behind a
  compatibility import/entry-point period and an explicit package-identity
  migration.

### R14. Authoritative and legacy tools

- Production, API, analysis, and historical acceptance use the runtime factory
  and session boundary.
- The simplified `ScenarioRunner`, legacy Monte Carlo/historical-data helpers,
  old visualizers, and trusted-local pickle conversion are quarantined under an
  explicit `legacy`/`examples`/migration namespace or removed after their useful
  DTOs and callers are migrated.
- Unsafe pickle restore is never a production checkpoint path. Strict JSON is
  the runtime checkpoint authority.

### R15. Mechanical module boundaries

The first structural split preserves imports and behavior with compatibility
re-exports:

```text
simulation/scenario_config.py
simulation/runtime_context.py
simulation/context_checkpoint.py
simulation/scenario_loader.py
simulation/loadout_contracts.py
simulation/loadout_registry.py
simulation/runtime_attachments.py
simulation/loadout_builder.py
```

- `simulation/scenario.py` and `simulation/loadouts.py` remain temporary public
  compatibility facades.
- Moving a definition does not change its field names, serialization, object
  identity, import compatibility, or checkpoint shape.
- A typed checkpoint-owner protocol replaces deep-copy/set-state probing one
  owner at a time; legacy owners remain explicitly classified until migrated.
- Mutable `cal_flat` compatibility is replaced incrementally by an immutable
  typed `ResolvedCalibration` compiled once at load time.

### R16. Battle facade and subsystem executors

- `BattleManager` remains the deterministic interval transaction facade called
  by `SimulationEngine`.
- OODA completion, movement, engagement, and battle-checkpoint behavior move to
  injected typed executors in that order.
- Executors receive frozen, least-privilege typed runtime views and explicit
  immutable inputs rather than `SimulationContext`, `Any`, private-attribute
  reach-through, or configuration mutation mid-tick. Live `Unit` identities
  and explicitly named mutable domain owners are allowed only where the
  executor contract authorizes them.
- Existing owner interfaces are used where available; missing operations expose
  immutable snapshots or typed commands.
- Extraction must preserve exact tick order, candidate order, RNG stream and
  indexed-decision identity, event order, object aliases, receipt contents,
  checkpoint bytes where the format is unchanged, and continuation behavior.
- Duplicate FOW update ownership and repeated checkpoint staging are removed
  through the typed transaction/snapshot owner; integrity fingerprints and
  atomic publication remain intact.
- Performance-sensitive extraction requires matched production profiling.
  Correctness checks may be reorganized, but REM-055's measured regression is
  not declared recovered without persistent matched evidence.

### R17. Canonical repository skills

- `.agents/skills` is the single tracked source for repository workflow skill
  instructions and Codex UI metadata.
- Provider views such as `.claude/skills` are generated, byte-identical
  projections rather than independently edited instructions. They remain
  regular files because runtime provenance correctly rejects source symlinks;
  Git deduplicates their identical blobs.
- Repository-policy tests require the exact route set, safe in-repository
  targets, byte identity through each projection, and complete provider
  metadata.
- Adding or removing a workflow skill is one canonical change followed by a
  projection refresh. A stale, symlinked, external, or broken provider view
  rejects validation.

## Acceptance criteria

The consolidation is complete only when all of the following are true:

1. Strict authoritative paths fail on injected enabled-subsystem faults, while
   any explicit degraded mode exposes typed failure evidence.
2. Production OODA delay/misinterpretation behavior executes exactly once,
   advances the phase, and continues identically after checkpoint restore.
3. Production movement proves correct first/multi-vessel current behavior and
   contains no unresolved F821 finding.
4. Repository lint enables F821 with only narrow documented suppressions.
5. No active test path is owned by a phase number; the six partition union is
   exact and all promoted contracts remain represented.
6. Test collection does not load exact expanded-node classification ledgers;
   the weak-test validator has no unreviewed current candidate.
7. Routine PR CI performs no held-out study and does not duplicate collection
   or immutable evidence work unnecessarily; main/nightly/manual tiers each
   have a verified non-empty contract.
8. Public docs no longer publish the full engineering history in their primary
   navigation, and current claim validation has zero unreviewed, stale,
   mismatched, or ambiguous dispositions without whole-history hash churn.
9. Main tracks no generated evidence; every retained external archive locator
   is immutable and digest-bound.
10. Supported checkout/container/package modes are truthful. Wheel and sdist
    allowlists plus isolated-install tests pass.
11. The headless CLI and API/MCP resource paths work outside the repository
    current working directory through the production runtime.
12. Frontend transport types have a passing OpenAPI drift check.
13. Legacy validation/pickle paths are absent from authoritative entry points
    and clearly quarantined or removed.
14. Scenario/loadout compatibility facades preserve public imports and strict
    checkpoint behavior while real ownership resides in smaller modules.
15. `BattleManager` delegates OODA, movement, engagement, and checkpoint work
    to typed executors with deterministic production, replay, and checkpoint
    equivalence.
16. A final `$profile` demonstrates the post-consolidation runtime cost; no
    speed improvement is claimed unless matched evidence supports it.
17. All applicable standard, API, E2E, slow, benchmark, terrain, data, docs,
    frontend, packaging, scenario, determinism, checkpoint, and postmortem gates
    pass with exclusions stated exactly.

## Migration invariants

- Test relocation is lossless before consolidation. Deletion requires an
  obligation map naming the stronger retained proof.
- Mechanical module moves precede interface redesign.
- Compatibility facades are removed only after repository and downstream
  callers migrate.
- No extraction changes checkpoint format implicitly. Any format change needs
  its own typed migration and fresh continuation proof.
- No extraction changes RNG allocation, event order, or iteration order as an
  incidental cleanup.
- No current historical `FAIL` or performance regression is reinterpreted as a
  pass.
- Large generated evidence remains external throughout the migration.
- Every tranche leaves the tree in a coherent, testable state and records its
  remaining compatibility surface.

## Verification plan

### Safety tranche

- Initial red production tests for strict caller behavior, OODA maturity,
  position misinterpretation, and first/multi-vessel tidal movement.
- Negative disabled controls and injected subsystem failures.
- Fresh and in-place checkpoint continuation for the deferred OODA queue.
- Focused deterministic RNG/event comparison.
- F821 lint with global ignore removed.

### Test and CI tranche

- Before/after definition and partition manifests retained under `artifacts/`.
- Exact obligation mapping for every removed or merged test.
- Fresh six-partition collection audit, evidence validator, and repository
  policy tests.
- Workflow parse/contract tests proving the four tiers and absence of held-out
  PR execution.

### Documentation and claim tranche

- Synthetic positive/negative claim discovery, stale-locator, changed-span,
  and unrelated-prose controls.
- Full historical-claim and scenario-data validation.
- Strict public and engineering documentation builds plus link controls.

### Packaging and interface tranche

- Wheel/sdist content allowlists and isolated no-Git installs.
- Base, API, MCP, and explicit external-catalog profiles.
- Headless CLI production scenario smoke.
- OpenAPI generation/drift tests and frontend build/test/lint.

### Module and executor tranches

- Public import compatibility tests.
- Exact state/checkpoint round trip and uninterrupted/restored continuation.
- Production scenario regression and deterministic replay.
- API/recorder equivalence.
- Matched profiles around performance-sensitive transactions.

### Closure

- `$validate-conventions`, `$audit-determinism`, `$evaluate-scenarios`, and
  `$profile` apply.
- `$validate-data` applies if any catalog/schema source changes.
- `$simplify`, `$update-docs`, `$cross-doc-audit`, and `$postmortem` are
  mandatory before the consolidation is described as complete.

## Non-goals

- Rewriting the simulation engine.
- Splitting engine and catalogs across independent revisions now.
- Introducing microservices.
- Changing military models, calibration, scenario outcomes, RNG distributions,
  or checkpoint schema merely to make extraction easier.
- Deleting tests based only on line count, coverage percentage, age, or phase
  number.
- Treating generated OpenAPI types as a replacement for semantic frontend
  validation.
- Fetching full evidence at runtime.
- Claiming Phase 118's performance regression is recovered without matched
  production evidence.

## Open operational decisions

- The URL and retention provider for the separate evidence remote are external
  deployment choices. Until supplied, the local append-only `evidence/full`
  branch remains unpublished and main records that qualification.
- Independent package releases are deferred. A future uv workspace requires a
  composite release-manifest design review before engine/catalog separation.
- Exact compatibility-facade removal dates are chosen from real downstream
  caller evidence, not a calendar deadline.

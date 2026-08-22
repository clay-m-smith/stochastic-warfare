# Stochastic Warfare - Repository Instructions

This file contains durable engineering rules. Read it completely before changing
the repository.

Historical phase documents and "complete" labels describe intent and prior
claims; they are not proof that behavior is implemented. Establish current
behavior from the production path and behavioral evidence.

Keep phase history, current test counts, and individual defects out of this file.
Track them in `docs/remediation-backlog.md`.

## Project and Architecture

Stochastic Warfare is a deterministic, data-driven, multi-scale wargame
simulator with a Python engine, FastAPI service, and React frontend.

The production consumer path is:

`scenario YAML or typed CampaignScenarioConfig -> SimulationRuntimeFactory.prepare / prepare_config -> PreparedScenario.build -> RuntimeSession.step / run_to_completion / finalize -> SimulationEngine -> CampaignManager / BattleManager -> Recorder / Victory -> API / analysis / frontend`

`ScenarioLoader` remains the lower-level simulation wiring boundary used by
the factory. Production consumers that claim comparable runtime execution use
the typed factory/session boundary so source preparation, variants, roster,
loadouts, victory construction, and provenance are not reimplemented.

The core dependency direction is:

`core -> coordinates -> terrain -> environment -> entities -> movement -> detection -> combat -> morale -> c2 -> logistics -> simulation`

Dependencies flow one way. Entities hold state; engines implement behavior.

`stochastic_warfare/validation/scenario_runner.py` is a separate simplified
simulator. A test that exercises it does not prove that the production
`SimulationEngine` path behaves correctly.

## Non-Negotiable Invariants

- Python requires 3.12 or newer. Use `uv` and `uv run`; never use bare `pip`.
- All stochastic behavior uses `RNGManager`-owned seeded authority: either an
  injected `numpy.random.Generator` from `get_stream(ModuleId)` or a typed,
  identity-addressed indexed decision allocated and committed through
  `RNGManager` when draw order must not depend on parallel scheduling.
- Never use Python's `random` module or module-level `np.random` calls in
  simulation logic.
- Iteration that affects simulation state or event order must be deterministic.
- Simulation logic uses the logical simulation clock, not wall-clock time.
- Internal spatial calculations use ENU meters. Geodetic coordinates are
  boundary formats only.
- Entities are data; subsystem engines own behavior.
- Stateful dependencies are explicitly constructed and injected. Do not add
  global engine singletons.
- Configuration and data inputs use typed Pydantic models. Unsupported or
  misspelled inputs must fail explicitly instead of silently falling back.
- Unit, equipment, and scenario YAML remain data-driven. Equipment mappings
  must preserve the equipment's actual semantics.
- Authoritative runtime source identity is Git-first. A checkout records its
  commit and content-sensitive dirty-tree identity and must not fall back from
  a broken Git worktree. A no-`.git` production package requires a verified
  generated application-source identity; Docker builds supply an explicit
  `SOURCE_REVISION`, and missing, malformed, or tampered package source fails
  closed.
- Simulation-core logging uses the project logging framework, not `print()`.
- Public APIs require type hints.
- Every affected stateful component must serialize and restore its complete
  mutable state through `get_state()` and `set_state()`.
- An optional feature must have verified enabled and disabled behavior.
  Instantiation alone is not enablement.
- Military and mathematical parameters require traceable authoritative or
  peer-reviewed sources. Record citations and material assumptions near the
  model or in its specification.

## Start of Work

Before editing:

1. Read this file and the relevant specification, architecture page, phase log,
   and remediation entry.
2. Run `git status --short` and inspect existing diffs in files you may touch.
3. Preserve all user and unrelated changes.
4. Trace the requested behavior through the real production path.
5. Write exact requirements, acceptance criteria, non-goals, and negative
   behavior.
6. Identify the applicable completion stages below.
7. Reproduce the defect with a behavioral test when practical.

If documentation, tests, and production behavior disagree, record the
discrepancy. Do not silently choose the easiest interpretation when it
materially changes the result.

## Phase Skill Routes

Repository-scoped Codex skills live in `.agents/skills/` and are invoked as
`$skill-name`. Read a selected skill completely before acting. A skill defines
a repeatable route; its output is not completion evidence until the coordinating
agent verifies the resulting source, tests, and diff.

Use these gates for every numbered implementation phase:

| Gate | Required routes |
|---|---|
| Define | Use `$spec` before changing a behavioral contract. Add `$research-military`, `$research-models`, and `$design-review` when doctrine, historical claims, mathematics, or architecture are material. |
| Implement | Follow the relevant task route. Use `$scenario` and `$orbat` for scenario/OOB work rather than editing data ad hoc. |
| Validate | Use `$validate-conventions` after simulation-core changes, `$audit-determinism` after stochastic/state-order changes, and `$validate-data` after data changes. Use `$profile` for performance-sensitive work. |
| Prove outcomes | Use `$evaluate-scenarios` when battle behavior or scenario data can change outcomes. Use `$backtest`, `$compare`, `$what-if`, or `$calibrate` for historical or statistical claims; use `$timeline` when narrative/AAR exposure is part of the requirement. |
| Review | Use `$simplify` for a phase's production-code diff before closure. Re-run the relevant behavioral tests after any review fix. |
| Close | Use `$update-docs`, then `$cross-doc-audit`, then `$postmortem`. Resolve or track every finding before marking the phase complete and committing it. |

Skill use is conditional where the table says "when" or "for." Do not run a
route as ceremony when its evidence category is genuinely inapplicable; record
the reason in the phase log. Conversely, do not skip an applicable route merely
because focused tests are green.

## Completion Evidence Matrix

For a feature, configuration field, or subsystem, verify each applicable stage:

| Stage | Required evidence |
|---|---|
| Declared | Typed schema, interface, or data definition exists; invalid input is rejected |
| Loaded | The real production loader carries the configured value into runtime state |
| Wired | The production engine or manager consumes it in the real execution loop |
| Enabled | Gates, era rules, and configuration activate it; disabled behavior is also verified |
| Exercised | A production-path test reaches the behavior under realistic preconditions |
| Outcome-affecting | Enabling or changing it creates a controlled, observable state, event, or result difference |
| Persisted/exposed | Affected state survives checkpoint/restore and reaches recorder, API, or UI surfaces where required |

Mark a stage `N/A` only with a written reason. "Implemented" or "complete"
means every applicable stage has evidence.

Imports, constructors, attribute presence, source-string searches, log messages,
mocked calls, and no-crash runs are structural evidence only. They cannot by
themselves establish wiring, exercise, or outcome effects.

## Evidence-Based Implementation Workflow

For each independently verifiable issue:

1. Define requirements and non-goals.
2. Trace declared -> loaded -> wired -> enabled -> exercised ->
   outcome-affecting -> persisted/exposed.
3. Add a failing behavioral test against the production path.
4. Implement the smallest coherent fix.
5. Run focused unit and integration tests.
6. Run a representative production scenario.
7. Run deterministic replay and checkpoint tests when mutable or stochastic
   state changes.
8. Run Monte Carlo or comparison testing when the change can alter stochastic
   outcomes.
9. Run relevant API, frontend, data, lint, documentation, and performance
   checks.
10. Review the final diff against the original requirements.
11. Update specifications, user documentation, devlog, and remediation status
    only after validation.
12. When a numbered phase satisfies the Definition of Done, create one coherent
    phase commit before beginning the next phase.
13. Report exact commands, results, exclusions, and residual limitations.

The repository owner has requested a commit after each completed phase. This is
standing authorization for verified phase commits containing only that phase's
work. It is not authorization to include unrelated changes or to push.

Do not weaken acceptance thresholds after a result misses them without explicit
approval and a documented modeling rationale.

## Evidence Storage

Generated run evidence -- including raw result vectors, shard bundles, JUnit,
traces, profiles, and archive manifests -- belongs under the ignored
`artifacts/` tree and must not be committed to `main`. Main may retain
reproducibility inputs, curated validation and test ledgers, behavioral
fixtures, and compact verdict or provenance summaries.

Full retained publications belong in evidence-only commits on `evidence/full`
or in an explicitly documented external evidence store. The evidence branch
absorbs `main`; `main` never absorbs archive commits. Do not rebase or
force-push retained evidence history. Prefer a separate evidence remote or
Git LFS for publication: an ordinary branch on the main remote is fetched by a
normal full clone even when it is not checked out. Record the archive locator,
immutable ref, path, digest, verdict, and qualifications in the applicable
phase devlog. Main validation must not require the archive to be fetched, and
an artifact's storage location never upgrades its eligibility or verdict.

## Checkpoint Verification

A checkpoint test must do more than assert that keys exist:

1. Run to time `T` and capture all mutable state and RNG state.
2. Advance far enough to mutate units and subsystem state.
3. Restore the checkpoint, preferably into a fresh runtime object where the
   contract permits.
4. Compare the complete restored state with the time-`T` snapshot.
5. Continue from the restored checkpoint and prove the same events, state
   transitions, and outcome occur as in an uninterrupted control run.

Include unit state, morale, inventories, engine queues, clocks, victory state,
recorder state, and enabled subsystem state whenever applicable.

## No Papering Over

Do not:

- Replace unsupported behavior with a semantically unrelated placeholder.
- Use hardcoded dummy timestamps, coordinates, targets, weapons, or outcomes in
  production paths.
- Leave empty implementations, unconditional success returns, or log-only
  handlers while claiming completion.
- Swallow exceptions to make tests pass.
- Treat direct calls to a subsystem as proof that the production loop invokes
  it.
- Treat an instantiated engine as a wired engine.
- Test only schema merging when the requirement is changed simulation behavior.
- Modify expected results merely to match current output.
- Describe skipped manual, slow, API, E2E, terrain, or benchmark validation as
  passed.
- Mark a phase or issue complete while an applicable completion stage is
  unverified.

Abstract methods and intentional no-op implementations are permitted only when
the contract explicitly requires them and tests prove the intended no-op
semantics.

If full implementation is out of scope, fail explicitly or document a tracked
limitation. Do not silently approximate it.

## Test Commands and Hidden Coverage

Install the locked superset needed by the authoritative collection audit:

```powershell
uv sync --locked --extra dev --extra api --extra terrain --extra mcp
```

The Python suite is the exact union of six audited, pairwise-disjoint
partitions:

| Partition | Authoritative selector |
|---|---|
| `standard` | `tests`, `not slow and not benchmark`, excluding `tests/api` and `tests/e2e` |
| `slow-only` | `tests`, `slow and not benchmark`, excluding `tests/api` and `tests/e2e` |
| `benchmark-only` | `tests`, `benchmark and not slow`, excluding `tests/api` and `tests/e2e` |
| `slow-benchmark` | `tests`, `slow and benchmark`, excluding `tests/api` and `tests/e2e` |
| `api` | `tests/api` |
| `e2e` | `tests/e2e` |

Audit the exact union, then run a named partition through the fail-closed
runner:

```powershell
uv run --no-sync python scripts/validate_test_partitions.py --output artifacts/partition-audit/manifest.json
uv run --no-sync python scripts/run_pytest_partition.py standard --manifest artifacts/standard/manifest.json --junit artifacts/standard/junit.xml --forbid-skips --timeout-seconds 2700
```

PR/main CI runs the audit plus `standard`, `api`, `e2e`, and the `terrain`
dependency profile. Weekly/manual extended CI runs `slow-only` in 15 shards,
`benchmark-only` in three shards, and `slow-benchmark` in one shard. Sharding
is deterministic and module-affine. `terrain` (the four Phase 15 terrain
files) and `benchmark-policy` are intentionally overlapping dependency/policy
profiles, not additional members of the disjoint union. The 73 Easting paired
benchmark is routine; Golan is manual.

Raw `pytest` marker commands are diagnostics only. They must not be reported as
the authoritative partition evidence because `slow` and `benchmark` overlap.
API, terrain, and documentation checks may require their corresponding
optional extras.

Static checks:

```powershell
uv run --no-sync ruff check stochastic_warfare/ api/ tests/ scripts/
```

Data changes:

```powershell
uv run python scripts/validate_scenario_data.py
uv run python scripts/validate_scenario_data.py --file <changed-yaml>
```

Scenario-affecting engine changes:

```powershell
uv run python scripts/evaluate_scenarios.py --scenario <scenario-id>
```

Frontend commands run from `frontend/`:

```powershell
npm test
npm run lint
npm run build
```

Documentation:

```powershell
uv sync --extra docs
uv run mkdocs build --strict
```

Use focused tests during iteration. Before completion, run every relevant
boundary suite. In the final report, name suites not run and why.

## Test Quality

Prefer assertions about observable state transitions, events, resource
consumption, routing, winner, casualties, timing, persistence, and deterministic
replay.

Every defect fix should normally include a test that fails before the fix.
Include a negative or disabled control when it distinguishes real behavior from
unconditional behavior.

Structural tests are useful diagnostics, but they are never sufficient proof of
behavioral completion.

Historical validation must retain predeclared metrics and tolerances.
Calibration changes must identify the source, sensitivity, seeds, and effect on
other scenarios.

## Documentation

Specifications define contracts; devlogs record work; the remediation backlog
records unresolved truth; user-facing guides describe verified behavior.

Update the relevant documents together:

- New or changed contracts: `docs/specs/`
- Architecture or wiring: `docs/concepts/architecture.md` and
  `docs/specs/project-structure.md`
- API behavior: API schema/client types and `docs/reference/api.md`
- Scenario fields or behavior: `docs/guide/scenarios.md`
- Era, unit, or equipment data: the relevant reference catalog
- New documentation pages: `mkdocs.yml`
- Work performed and limitations: relevant devlog and `docs/devlog/index.md`
- Current remediation status: `docs/remediation-backlog.md`
- Public setup or capability claims: `README.md` and `docs/index.md`

Do not update status or test-count claims from collection output, stale result
files, or agent reports. Use a fresh command result. Do not write "complete"
while required validation is pending.

`CLAUDE.md` is legacy provider-specific context and may contain stale status
claims. Do not treat it as behavioral evidence. Keep overlapping durable rules
aligned when intentionally maintaining both files.

## Worktree and Delegation Safety

- Run `git status --short` before work, before integrating delegated work, and
  before handoff.
- Shared agents use the same filesystem. Assign disjoint files or tightly
  bounded scopes.
- Do not reset, checkout, clean, stash, delete, overwrite, commit, or push user
  work unless explicitly authorized.
- Never assume an untracked or modified file belongs to you.
- Re-read files after another agent finishes; their edits are already present in
  the shared worktree.
- Inspect every delegated diff and run verification yourself. An agent's report
  is not evidence.
- Do not begin dependent work until the preceding agent checkpoint is verified.

For every delegated checkpoint, require:

- requirements addressed;
- files changed;
- exact test commands and results;
- applicable completion-matrix stages;
- unresolved limitations or assumptions.

The coordinating agent then reviews the diff, runs `git diff --check`, reruns
focused tests, checks for unrelated changes, and only then accepts the
checkpoint.

## Definition of Done

Work is done only when:

- all acceptance criteria and applicable completion stages have evidence;
- production-path behavioral tests pass;
- disabled and failure behavior is covered;
- deterministic replay and checkpoint integrity remain valid where applicable;
- relevant lint, data, API, frontend, docs, scenario, slow, or performance
  checks pass;
- documentation and remediation state match reality;
- all skipped validation and residual limitations are explicitly reported;
- the final diff contains no unexplained or unrelated changes;
- a completed numbered phase is recorded in one coherent git commit.

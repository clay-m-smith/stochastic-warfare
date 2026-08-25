# Phase 142 - Transactional FOW Runtime-Cost Integrity

**Status:** Complete

**Remediation:** REM-055

**Started:** 2026-08-24

**Completed:** 2026-08-25

**Contract:** [Performance-Flag Semantic Integrity](../specs/performance-flag-semantic-integrity.md)

## Objective

Recover the gross production runtime regression introduced by Phase 118's
transactional fog-of-war update without weakening failure atomicity,
owner-bound mutation detection, canonical indexed-RNG identity, deterministic
parallel publication, correlation-safe fusion, observer-support continuation,
receipts, or checkpoint reconciliation.

This is an execution optimization. It does not revise the detection model,
re-enable scan scheduling or LOD, tune scenario/catalog inputs, or establish a
universal throughput claim.

## Start gate and production trace

Phase 142 starts from clean commit
`941590261a5ae7d8066884805fdf66556b6d5f59`. The production target is the
factory-built `benchmark_battalion` scenario at seed 42 for exactly ten ticks
and 50 logical seconds, with strict mode and event recording, fog of war,
detection culling, SoA selection, and parallel detection enabled, and scan
scheduling and LOD disabled.

The measured path is:

`SimulationRuntimeFactory.prepare -> PreparedScenario.build -> RuntimeSession
-> SimulationEngine.run -> BattleManager.prepare_tactical_interval ->
BattleManager._update_interval_fog_of_war -> FogOfWarManager transaction`

The runtime-cost defect has no separate enable/disable stage. Declared,
loaded, wired, exercised, and outcome-measured stages already exist; Phase 142
must add accepted persistent optimization evidence while preserving every
existing outcome and persistence boundary.

## Acceptance contract and threshold history

The repository owner approved the original contract on 2026-08-24 before any
hot-path source change:

- discard one warm-up per revision;
- execute five same-host interleaved matched pairs in the order `B/C`, `C/B`,
  `B/C`, `C/B`, `B/C` using fresh production sessions;
- initially require the median of candidate/reference paired timing ratios to
  be at most `0.80`;
- require each revision's relative sample range to be at most `0.05`;
- require candidate peak Python allocation memory under the matched
  `tracemalloc` measurement to be at most `1.05` times the baseline;
- compare call profiles independently; cumulative descendants are diagnostic
  and are not added as savings;
- require exact semantic-envelope, ordered-event, complete checkpoint-byte,
  conventional-RNG-state, indexed-transcript, receipt, and fresh-runtime
  continuation equality; and
- reject any source, scenario, dependency, environment, or workload drift.

The `0.80` timing limit approximately reverses the original `1.259063` Phase
118 slowdown. On the phase-start host it corresponded to a provisional median
ceiling of 49.576 seconds against the measured 61.969-second baseline.

The threshold history is retained rather than rewritten. After implementation
and review, the owner explicitly accepted bounded partial recovery and revised
the limit first to `0.86`. The formal `0.86` run failed at
`0.8635476449973133`, despite passing dispersion, memory, exact deterministic
equality, fresh-runtime continuation, and drift gates. After observing that
result, the owner explicitly accepted `0.87` as the final partial-recovery
limit on 2026-08-25. The decision artifact SHA-256 is
`da9b3fe5260dee81f65cd84fb72fa0b426ec5c194231e2eb33ea265be40a3bd2`.
A fresh harness encoded `0.87` before execution and repeated the complete
workflow. The earlier results were neither cherry-picked nor silently
relabeled. Historical absolute seconds remain host-specific; the matched
ratios decide each recorded gate.

## Phase-start environment and evidence

- OS/kernel: Linux 7.1.6-1-cachyos, x86-64
- CPU: AMD Ryzen AI MAX+ 395, 16 cores / 32 threads
- Python: CPython 3.12.10
- thread limits: one for OMP, OpenBLAS, MKL, NumExpr, vecLib, and BLIS
- dependency lock SHA-256:
  `bbc6b45cfc270d08baa09d3d568a6b84d0f936a6ee9c874cb49c9d8813c5ad39`
- scenario SHA-256:
  `26699027374b89454f69f924e2a1f75cf8c97d2026b25725591ca352851586e6`

After one discarded warm-up, three phase-start timing samples were
61.886042, 61.969439, and 62.173692 seconds: median 61.969439 seconds and
relative range 0.004642. Every run produced the same 1,000-unit, ten-tick,
blue `max_ticks` result, event digest, checkpoint bytes, and conventional RNG
state. The phase-start `tracemalloc` peak was 33.398545 MiB; its instrumented
wall time is not part of the timing comparison.

The phase-start cProfile recorded 518,194,574 calls and 139.311824 seconds of
profiled function time. `_update_interval_fog_of_war()` enclosed 23.116
seconds. Independently observed transactional costs included 3.620 seconds in
200 full update-plan fingerprints, 2.957 seconds in transaction prevalidation,
2.126 seconds in prepared-commit validation, 2.004 seconds in commit
preparation, and repeated scan-count snapshot/staging/validation. The targeting
loop remains the dominant absolute hotspot but is not attributed to REM-055.

Raw phase-start evidence is outside the worktree under
`/tmp/sw-rem055-baseline.apEoF8/`: timing JSON SHA-256
`4173e090ed955cceb7a3ccb06c3424ee702c433f809a75c5b68afb99df61b549`,
profile JSON SHA-256
`63342c551e7ee9ee17bd5ba9bb45938d864a0dbf06f83356f375fff7b91b4f8e`,
profile SHA-256
`78b5a3be2af1bd908f60f4efa0b13c484edf26703a26987e40943251f363a536`,
and memory JSON SHA-256
`e5384dd1b009f8777e39b9f5f556f4ad283c590e89ab0a334d2a1620daed65df`.
These local artifacts are reproducibility evidence, not a permanent archive.

## Requirements and non-goals

The implementation may remove only causally measured redundant work. The
outer all-owner validation immediately before publication remains mandatory.
Mutation between staging and that boundary must still fail without publishing
any FOW, cadence, indexed-RNG, battle, targeting, or receipt state. Retained
plans must not alias committed state. Serial and threaded execution must
produce identical canonical plans, RNG transcripts, events, and checkpoints.

The phase does not change HTTP API or frontend schemas, typed configuration,
format-118 checkpoint semantics, equipment or scenario data, physical sensor
behavior, targeting policy, scan/LOD support status, or REM-051/REM-054 scope.
Any post-observation threshold revision requires explicit owner approval, a
retained decision record, and a fresh native-policy run; Phase 142 used exactly
that process for the final `0.87` limit.

## Verification plan

1. Add behavioral regressions for every eliminated validation/copy boundary,
   including a mutation injected after FOW staging but before outer commit.
2. Run focused FOW atomicity, tamper, observer-support, serial/parallel,
   indexed-RNG, receipt, replay, and fresh-runtime checkpoint continuation
   tests.
3. Run the frozen matched timing, call-profile, and peak-memory comparison and
   independently validate the retained receipt.
4. Run the production scenario evaluator against the accepted pre-phase
   semantic baseline, plus applicable standard, slow, benchmark, API, E2E,
   data, lint, documentation, determinism, convention, and packaging gates.
5. Apply `$simplify`, `$update-docs`, `$cross-doc-audit`, and `$postmortem`;
   close REM-055 and Phase 142 only if every required gate passes.

## Implementation and closure

### Production implementation

Phase 142 retains the public FOW transaction contract while moving
authoritative mutation through manager-private, single-use workspaces. Side
graphs detach once, move through prevalidation and preparation, and publish
through bounded commits. Public plans and outcomes retain stable defensive
projections; stale diagnostic previews retire; abort poisons the workspace;
and retained update, cadence, publication, commit, witness-clear, and restore
plans do not alias committed state.

The optimized path reuses validated scan-count, cadence, fusion, indexed-RNG,
geometry, and spatial-query representations without weakening the final
all-owner seal. Exact-builtin scan counts use a private raw binding while
accepted anomalous subclasses retain the full canonical validation path.
Fusion preserves the complete order-sensitive candidate ledger but constructs
and submits only the canonical prepared representative for each exact group.
Indexed FOW decisions retain a compact issuance-time identity snapshot and
reject same-object post-issuance mutation. Cadence and composite restore
payloads are completely prepared before the first owner swap.

Public witness and observer-support getters remain graph-defensive. Trusted
Battle/FOW consumers use private read-only projections only within the owning
call and detach evidence retained afterward. Canonical per-target detection
geometry, cadence-plan attachment identities, vectorized target construction,
and vectorized STRtree queries remove repeated hot-loop allocation without
changing sensor physics, target selection, RNG allocation, or receipt order.

Terminal-gate and grouped-detector experiments that regressed the measured
workload were fully reverted. They contribute no final behavior or performance
claim.

### Simplification and integrity review

`$simplify` found one material closure defect after the optimization froze:
ordinary Pydantic equality at public plan boundaries could accept equal-valued
nested scalar type substitutions such as `True` for receipt integer `1`.
The final tree recursively validates exact receipt graph types and values and
uses strict type or identity checks for generation, side, fusion metadata,
opaque seals, and scan fingerprints. New adversarial tests prove rejection
without publishing FOW, cadence, indexed-RNG, targeting, or receipt state.
Independent re-review returned clean.

`$audit-determinism` and `$validate-conventions` returned clean. Canonical
observer, target, attachment, fusion, scan, side, and commit order remains
unchanged; indexed decisions retain their exact identity lanes; conventional
RNG state remains stable; and no public API, checkpoint schema, coordinate,
clock, logging, data, model, or policy contract changed.

### Accepted performance receipt

The formal `0.86` result remains a recorded failure. Its result SHA-256 is
`7b9922ae048f02278f8d8731423f9573e68ed8b453ef46aa9e6dedf487062180`.
After the owner approved `0.87`, a new versioned external harness first passed
construction-only readiness, then ran one discarded warm-up per revision,
five alternating fresh-process pairs, separate matched `tracemalloc`, and
fresh-runtime continuation. The readiness artifact SHA-256 is
`093c0491d7d4b58af15b553d142011420f9e07e3ba8053d8288e37823a946e0a`;
the terminal result SHA-256 is
`6fac6f1f370302d247d1a00ad56af5e269622c85d81c90fbed4c5fbe2397578c`.

| Measure | Baseline | Candidate | Accepted boundary |
|---|---:|---:|---:|
| Median wall time | 59.892654 s | 51.839189 s | Diagnostic absolute values only |
| Relative sample range | 0.013218 | 0.016081 | Each <= 0.05 |
| Median paired candidate/baseline ratio | - | 0.861173 | <= 0.87 |
| Peak Python allocation | 35,237,923 B | 33,490,734 B | Ratio 0.950417 <= 1.05 |

The five paired ratios were `0.857463`, `0.859370`, `0.861173`, `0.866019`,
and `0.875246`. Their median represents about 13.88% recovery on this exact
matched workload. It does not meet the original `0.80` target and is not a
universal throughput claim.

### Final source-bound call profile

A final one-run cProfile used the same profile driver (SHA-256
`a73a84e4f1976f7dfad07f2949931c2a5e98967d9d6fe52c557a8fdbb224d889`)
and execution policy as the phase-start profile. The six changed production
files byte-matched the accepted performance artifact's
`original_source_after` manifest identity
`05f6fea1bfe098b21cb35d45a63af29160dd2d01e7ccf176913ef1b6f1c61562`:
`indexed_rng.py` `44550a9d...130744`,
`cadence.py` `4b86c4cd...fc5ed`, `detection.py` `1d7271b4...d610a`,
`fog_of_war.py` `37bc609c...38225`, `intel_fusion.py`
`88150001...99915`, and `battle.py` `c1be3698...d114`. The run reproduced
the accepted semantic, checkpoint, and full-RNG digests exactly.

| Profile measure | Phase start | Final tree |
|---|---:|---:|
| Total calls | 518,194,574 | 473,385,421 |
| Primitive calls | 514,939,857 | 472,791,132 |
| Profiled function time | 139.311824 s | 126.639694 s |
| `_update_interval_fog_of_war()` cumulative | 23.116448 s | 9.683666 s |
| `_update_plan_fingerprint()` | 200 calls / 3.620372 s | 40 calls / 0.837962 s |
| `_interval_plan_fingerprint()` | 120 calls / 1.904136 s | 30 calls / 0.619557 s |
| `_stage_live_update_baseline()` | 10 calls / 1.067930 s | 10 calls / 0.327441 s |
| `prevalidate_update_transaction()` | 10 calls / 2.956961 s | 10 calls / 0.300160 s |
| `prepare_update_commit()` | 10 calls / 2.004109 s | 10 calls / 0.769159 s |
| `validate_prepared_update_commit()` | 20 calls / 2.125770 s | 10 calls / 0.569130 s |

The final raw profile JSON SHA-256 is
`ca2c9ce5eb9a21d566be8b7a42880cbe7226fad15ecb91e1962e5161d60138e6`;
the `.prof` SHA-256 is
`ac876ecb856fdc2316962576e41b22b223f941be3bf22cdcb3e385ecf86a0e21`.
These are diagnostic single-profile measurements, not timing acceptance.
Cumulative descendants overlap and must not be added; the matched five-pair
wall-time receipt remains the performance gate.

### Semantic and continuation evidence

Baseline and candidate produced the same 1,000-unit, ten-tick, 50-second blue
`max_ticks` result, 283 ordered events, complete checkpoint bytes,
conventional and indexed RNG state, execution receipt, and fresh-runtime
continuation. Compact identities are:

- semantic projection:
  `53018be90e5f8090270d714f96d844058d14edc314dd70b7bf7601d857958693`;
- ordered events:
  `08d0886584e1e1dc556f3d1e5cf94aa9b70e9600d7124ec9631e584fb9d3d8b2`;
- final checkpoint:
  `73967e2e8953ec5f9b02a20b490c361a337e217422e0bc845813535c8c6e0408`;
- conventional RNG state:
  `b31627f846618ac74ac05506933f850b96de7c2769eef64a4b099dc6f45db0f0`;
- full RNG state:
  `7f15301eb10193f0f40151e7b12165732a558dd3384ea8e50b4908c70edf972e`;
- indexed FOW state:
  `ff81dc96a0f4b7d47f9028e6bcd7b3d1cd051fbb8c345455fdc689f52442cc33`;
  and
- performance execution receipt:
  `5b6cd85d03669f85d47551095347af6743dd34cd52d475304c191b41301b8bbf`.

The source, scenario, dependency, environment, and workload drift gates all
passed. The scenario SHA-256 remained
`26699027374b89454f69f924e2a1f75cf8c97d2026b25725591ca352851586e6`;
the dependency-lock SHA-256 remained
`bbc6b45cfc270d08baa09d3d568a6b84d0f936a6ee9c874cb49c9d8813c5ad39`.

### Bounded scenario evidence

The final production evaluator ran only the bounded
`calibration_urban_cbrn` scenario. It completed successfully through tactical
execution: 14 constructed units, 82 ticks / 820 logical seconds, red
`force_destroyed` victory, three blue units destroyed, 84 events, and no
diagnostic issues. This is one current-engine scenario regression, not a
scenario-library sweep, historical validation, distributional proof, or
universal behavior claim. The evaluator artifact SHA-256 is
`d5281c6c789613f814ce0d22d7faccda748191a5a25c886cb53b3e715b22ce87`.

### Partition and static evidence

The revision-bound audit enumerated 13,015 node IDs across six exact,
pairwise-disjoint partitions. Its SHA-256 is
`5b01af839bc7a958a4776f79e547f132e5ed9fb4981248ce233855ebcd1971c0`;
it binds commit `941590261a5ae7d8066884805fdf66556b6d5f59` and worktree
fingerprint
`4076edb13031898ac3b351bdfcc5951232926de874e14bf81e27dc48355cecbc`.

| Partition | Result | Warnings / skips |
|---|---:|---:|
| Standard | 12,387 passed | 6 / 0 |
| Slow-only, 15 shards | 108 passed | 0 / 0 |
| Benchmark-only, 3 shards | 128 passed | 0 / 0 |
| Slow benchmark | 7 passed | 0 / 0 |
| API | 344 passed | 0 / 0 |
| E2E | 41 passed | 0 / 0 |
| **Exact union** | **13,015 passed** | **6 / 0** |

The six standard warnings are the known planning-process UTC deprecation,
empty-chart legend, and replay-animation cleanup warnings. The first standard
attempt reached 12,385 passes but its two packaging fixtures could not resolve
`setuptools>=77` from a fresh offline cache. A diagnostic offline build passed
with the established warmed cache; the exact full standard rerun then passed
12,387/12,387. Initial sandboxed API/E2E attempts reached their operational
timeouts without terminal receipts; fresh sequential runs outside the sandbox
passed 344/344 and 41/41. Neither diagnostic attempt is counted as test
evidence.

The exact partition receipt binds the pre-closure-documentation worktree
fingerprint. Subsequent repository changes were limited to `docs/` and
`CLAUDE.md`. A final whole-manifest comparison checked all 2,384
non-documentation files against the accepted performance artifact's source
manifest and found zero mismatches; both filtered manifests have SHA-256
`e4787e4a2a0771a48778f378100df2bb3dfb873b67213197b1fd9ad2eb2285d5`.
The postmortem accepts this explicit split
evidence boundary: behavioral receipts apply to that unchanged production and
test tree, while the documentation, link, provider-projection, and static
checks apply to the final closure text. The original test fingerprint is not
relabeled as a final-documentation fingerprint.

Repository Ruff, changed-file format, isolated compilation, and diff checks
passed before documentation closure. Strict documentation and link validation
are rerun on this final text before the cross-document audit.

### Limitations and closure status

The accepted receipt applies only to the declared host, dependency lock,
scenario, seed, ten-tick workload, and execution policy. Absolute seconds are
not portable. The original `0.80` recovery target and interim `0.86` target
remain misses; further throughput work belongs to a later dedicated
optimization pass.

Phase 142 does not revise detection or targeting models, scenario/catalog
data, or public support policy. Scan scheduling and sensing-only LOD remain
rejected in production; REM-054 / Phase 141 remains not started. The targeting
loop remains the dominant absolute hotspot but is not attributed to REM-055
without separate evidence.

Raw evidence remains under ignored local artifact storage rather than main.
The implementation, performance, scenario, partition, convention,
determinism, simplification, documentation, cross-document, and postmortem
gates are complete. REM-055 is closed by the accepted postmortem below.

## Postmortem

**Verdict:** ACCEPT

**Scope:** On target. Phase 142 reduced the measured transactional FOW cost
while preserving atomic publication, exact tamper rejection, deterministic
RNG and ordering, receipts, retained-handle isolation, and checkpoint
continuation. It did not change detection or targeting models, scenario or
catalog data, public schemas, checkpoint format, scan scheduling, or LOD
support.

**Delivery changes:** The original `0.80` target and interim `0.86` target were
not met. The owner explicitly approved `0.87` as a bounded partial-recovery
limit, and a fresh native-policy run passed at `0.861173`. Terminal-gate and
grouped-detector experiments that regressed the workload were reverted. The
fusion optimization retained the complete order-sensitive ledger instead of
the rejected count-only design. Unplanned integrity work closed retained-plan
and public-projection aliases, cadence and restore publication aliases,
composite-restore atomicity, raw-scan anomaly handling, indexed-identity
mutation, and exact-type receipt and handle tampering.

**Quality and integration:** High and fully proven for the applicable stages.
The final production diff has no new stub, placeholder, unconditional-success,
production print, wall-clock RNG, or obsolete experiment path. Battle drives
the owner-bound FOW transaction through side execution, prevalidation,
preparation, final all-owner validation, and bounded commit. Enabled,
disabled, serial, threaded, malformed, tamper, abort, restore, and continuation
paths have behavioral regressions. Public outcomes, receipts, witnesses,
supports, RNG transcript, ordered events, and checkpoint bytes remain exact.

**Validation:** The accepted paired performance receipt recorded a `0.861173`
median ratio, compliant dispersion, a `0.950417` memory ratio, and exact
semantic, event, receipt, RNG, checkpoint, and fresh-runtime continuation
identity. The source-bound call profile reduced total calls from 518,194,574
to 473,385,421 and the non-additive FOW enclosure from 23.116448 to 9.683666
seconds. The exact six-partition union passed 13,015/13,015 nodes with six
known warnings and zero skips, failures, errors, xfails, or xpasses. Sixty-one
new behavioral regression functions are included in that accepted standard
partition. The bounded production scenario passed, and Ruff, formatting,
compilation, diff, strict MkDocs, link, provider-projection, determinism,
convention, simplification, and cross-document gates passed.

The partition receipt intentionally binds the unchanged production and test
tree before closure-documentation edits. A complete comparison of 2,384
non-documentation manifest entries found zero mismatch; final documentation
gates bind the closure text separately. Monte Carlo calibration, backtesting,
terrain/data validation, and frontend model validation were not applicable
because this phase changed no model, data, terrain, or frontend contract.

**New deficits and actions:** None. The missed `0.80` full-recovery target is
an explicit accepted limitation, not a concealed pass. Further throughput
work requires a separately scoped, predeclared optimization phase. REM-054 and
Phase 141 remain unchanged and not started. No action remains before the
coherent Phase 142 commit.

# Historical Outcome-Envelope Integrity

**Status:** Accepted; Phase 117 complete and REM-030 closed

**Owner:** Phase 117 / REM-030

## Purpose and authority

Phase 117 replaces unqualified catalog outcome metadata, legacy-runner
comparisons, and winner tables presented as historical accuracy with one
typed, fail-closed production backtest contract. The authoritative execution
path is:

```text
HistoricalStudyLoader -> HistoricalStudyPlan
  -> SimulationRuntimeFactory.prepare -> HistoricalBacktestRunner
  -> per-session typed observation boundary and metric extractors
  -> evaluate_joint_coverage -> JointCoverageEvaluation
  -> create_completed_artifact/create_error_artifact
  -> atomic, reload-validated JSON artifact
```

`SimulationRuntimeFactory` remains the only scenario/runtime construction
authority. Historical source data, acceptance policy, and claim dispositions
are validation inputs; they are not simulation configuration and are never
passed through `HistoricalDataLoader`, `ScenarioRunner`, or
`CampaignDataLoader.to_scenario_config()`.

At the Phase 117 baseline there are zero production-validated historical
claims. The 46-scenario seed-42 table is current-engine regression evidence.
All 31 shipped `documented_outcomes` collections, comprising 83 metrics, are
unsupported as historical validation. Phase closure does not require turning
any of them into a pass. An honest `FAIL` artifact and an explicit unsupported
disposition are valid outcomes; widening an envelope, changing a seed set, or
tuning physical performance after seeing results is not.

## Evidence foundations

The contract applies validation only for a declared intended use and retains
the evidence needed to assess limitations. This follows the Department of
Defense VV&A distinction summarized by the U.S. Government Accountability
Office: validation evaluates how well a model and its data represent reality
for an intended use, and the process and limitations must be documented.

For stochastic coverage, Phase 117 uses an exact one-sided binomial lower
confidence bound. The method follows the exact binomial construction in the
NIST/SEMATECH e-Handbook. One run succeeds only when its complete ordered tuple
of gating observations is in range. The resulting binomial interval therefore
estimates joint, not marginal, modeled coverage; it does not combine separate
per-metric intervals or claim that one observed battle defines a real-world
outcome distribution. The source ranges and the statistical acceptance policy
remain separate evidence: a historian or source supports each observed range,
while the study author must independently justify the minimum modeled joint
coverage, confidence, and sample size for the intended use.

The real Phase 117 red uses the shipped 73 Easting scenario and the U.S. Army
Armor Branch account on page 98 of *ARMOR*, October--December 2015. That
account identifies 28 Iraqi tanks and 16 personnel carriers destroyed, no
American losses, and 23 minutes for the Eagle Troop action. The plan treats
the winner as diagnostic only. It gates separately on the exact tank and
personnel-carrier component losses, plus American-vehicle loss and natural
duration. Keeping the two Iraqi components separate prevents a wrong vehicle
composition from satisfying the source envelope merely because its aggregate
count is 44.

The catalog's Debecka metadata is a separate concrete source mismatch. The
U.S. Army Special Operations History Office account on page 84 of *Veritas*,
volume 1, number 1 records a two-and-a-half-hour crossroads fight and five
T-55s, three armored personnel carriers, and eight cargo vehicles destroyed.
The current four-hour/modal-ten metadata and its Javelin-share proxy therefore
remain unsupported; Phase 117 does not widen either into agreement.

## Claim-disposition ledger

One strict, versioned ledger owns the repository-wide classification. Each
entry has a stable claim ID, exact repository path, claim surface, normalized
content digest, disposition, reason codes, and optional accepted study/artifact
references. The only dispositions are:

- `production_validated`: a clean-revision, source-backed, held-out production
  artifact passes every gating metric and has been explicitly accepted;
- `current_engine_regression_only`: the evidence freezes current production
  behavior without comparing it to a historical truth claim; or
- `unsupported`: sources, metric semantics, production extraction, held-out
  evidence, or a passing artifact are absent or inadequate.

The ledger inventories, at minimum:

1. every shipped scenario `documented_outcomes` collection and each contained
   metric name;
2. scenario prose that implies historical consistency without such a
   collection;
3. the explicitly designated current-engine historical-accuracy contract and
   its canonical 46-scenario regression snapshot;
4. every current public documentation, API, and frontend production statement
   that presents a historical or validation claim; and
5. materially current workflow statements that control historical evidence or
   claim validation.

Scanner version 3 makes the current-truth boundary explicit. It audits API
Python, non-test frontend production source, shipped scenario YAML, current
GitHub workflows, README, the current index/guides/concepts/reference/specs,
the remediation backlog, and the one explicit current-engine historical
snapshot contract. Generic tests, frontend fixtures, devlogs, brainstorms,
phase histories, provider mirrors, TypeScript declaration files (`*.d.ts`),
build output, dependencies, caches, and the ledger itself are outside that
boundary. Generated TypeScript shipped by the frontend remains production
source and is scanned; its mechanically derived claim vocabulary can receive a
typed mirror/reference exclusion rather than a duplicate claim.
Historical phase records remain immutable history rather than perpetual
present-tense claim surfaces. Status tokens remain separator-flexible and
camel-case aware, so forms such as `historically validated`,
`historical-validation`, and `HISTORICAL_WINNERS` cannot evade the audit
through spelling alone.

The live ledger is schema version 2 with scanner version 3. Schema-1/scanner-2
ledgers are rejected rather than silently interpreted under the narrower
current-truth boundary. No compatibility reader is retained because the
repository has zero accepted artifacts whose promotion depends on that legacy
review schema; retained failed studies keep their immutable execution-ledger
digest without becoming current claim inventory.

Each discovered source identity is either bound to every compatible exact
claim ID or retained as an explicit reviewed nonclaim with a reason. A review
binds the rule and digest of each normalized sentence-like context that
actually matched, plus the number of sources carrying that exact semantic
identity. It does not bind unrelated file bytes or a repository path. An
unrelated sentence or paragraph edit, or a path move, therefore leaves review
identity stable, while changed claim wording or value, a new matching span,
removal of a reviewed span, or a duplicate copy fails closed as an unreviewed,
stale, or occurrence-mismatched identity. Exact claim locators and content
digests remain independently required; the scanner is still a conservative
discovery mechanism, not an occurrence-complete natural-language proof.

Scenario collections retain their legacy metadata only as catalog history.
The ledger digest must match the normalized collection exactly, so edits,
additions, removals, duplicate names, or an uninventoried collection fail data
validation. No legacy loader or comparator may promote that metadata to a
historical verdict.

An absent ledger entry is `unsupported`; it never inherits validation from a
name, a “golden” label, metadata presence, or another scenario's result.
Repository closure uses the full source-auditing loader. The packaged API uses
the same strict ledger and self-digest while source-auditing every claim it can
publish for a scenario; documentation, tests, and frontend source are not
copied into the production image. Local Phase 117 evidence proves the packaged
loader boundary for the current zero-accepted ledger; a hosted no-`.git` image
smoke is configured and becomes independent image evidence only after the
phase commit is pushed and its workflow passes. A future accepted artifact still needs
the build-time/no-`.git` attestation assigned to REM-048 / Phase 135; until
then, a nonempty accepted reference in an image rejects rather than silently
losing repository verification. An external or renamed API data root cannot
inherit a repository claim and therefore receives a synthetic `unsupported`
summary.

## Typed study plan

Every production backtest is declared in a strict YAML plan before candidate
outputs are inspected. Unknown fields, duplicate IDs, duplicate metrics,
non-finite values, unordered or repeated seeds, and ambiguous units reject.
Study and claim IDs share one lowercase `[a-z0-9._-]+` stable-ID validator.
Seed intervals use bounded arithmetic for count and overlap checks rather than
materializing attacker-sized collections, and one study may execute at most
1,000 held-out production runs.
The plan contains:

- schema version and stable study ID;
- exact scenario path and data root;
- intended use and explicit non-predictive limitations;
- source references with stable URL, full citation, quality tier, locator,
  access date, supported assertion, and conflict notes;
- known calibration/training inputs and seed ranges;
- one contiguous, explicit held-out seed interval disjoint from every declared
  training or diagnostic seed interval;
- exact maximum ticks and an empty analysis override patch;
- confidence and minimum joint stochastic coverage;
- ordered gating metrics and ordered diagnostic metrics; and
- artifact policy, including whether a clean code revision is mandatory.

The runner refuses a nonempty calibration patch. Authored scenario calibration
remains part of the hashed scenario input, but the study must disclose its
known source/training lineage and whether any proposed validation source was
used to author or tune the scenario. Held-out RNG seeds do not make reused
historical evidence independent. A declared `unknown` or `reused` source
lineage can support an `unsupported` red artifact but can never promote a claim
to `production_validated`. A missing declaration or overlapping seed lineage
is schema-invalid and cannot execute.

The Phase 117 bootstrap plan is created and executed within the repository's
one-commit phase rule. It therefore records the clean Phase 116 design-base
revision plus a frozen plan digest in the devlog before execution. It is not
eligible for validation promotion. Later promotion studies require the plan to
exist at a clean, immutable predeclaration revision before held-out execution.

## Closed metric-extractor vocabulary

A metric plan names one closed extractor ID rather than an arbitrary Python
callable or expression. Phase 117 supports only the production metrics needed
for the real red and existing analysis boundary:

- `terminal_side_destroyed_count.v1` for one exact side and an exact ordered
  set of authored unit types;
- `terminal_side_active_count.v1` with the same scope;
- `time_to_natural_terminal_seconds.v1`, derived from the public runtime
  duration and explicitly marked right-censored at a study cutoff;
- `terminal_winner_indicator.v1`, diagnostic unless accompanied by at least
  one independent outcome metric; and
- `terminal_exchange_ratio.v1` only when its numerator, denominator, zero-case
  rule, side IDs, and unit scope are explicit.

Each plan records the extractor's output unit, source unit, scale/offset if a
lossless unit conversion is needed, side, statuses, included unit types, and
event boundary. Preparation checks the exact typed scenario roster. A source
claim in vehicles cannot silently consume personnel, aggregate formations,
ships, aircraft, or generic unit-record counts. A metric absent from the
closed vocabulary is an explicit unsupported error, not zero.

The historical and production event boundaries must be comparable. Terminal
state cannot stand in for a mid-battle count, and scenario duration cannot
stand in for a source's differently bounded campaign segment. The plan owns
one source-synchronous observation boundary shared by all gating extractors.
The Phase 117 plan observes at exactly 1,380 seconds, corresponding to the
source's 23-minute Eagle Troop action. The runner stops at that boundary when
the scenario remains active; a natural public terminal result before the
boundary is retained with its exact time and terminal cause. Unit-status
observations are the state at the earlier natural termination or at the exact
cutoff. The duration extractor is a typed
`time_to_natural_terminal_seconds.v1`: an observation stopped only by the
study cutoff is right-censored and is out-of-range for the duration gate rather
than being reported as a 1,380-second natural completion. This makes all four
source quantities represented by four typed metrics one synchronized joint
observation without treating a study cutoff as a battle outcome.

Every run must produce every ordered metric exactly once and either a natural
public terminal result or an explicit cutoff-censored public result. Partial
vectors, missing metrics, non-finite values, roster drift, provenance drift,
or a no-crash run reject the study.

The prepared code/data identity is rechecked after execution and observation
of every held-out run, including the final run, before that run is retained;
again after complete evidence construction; and again immediately before
artifact publication. Drift at any of those boundaries produces a durable
typed `ERROR` with the completed prefix allowed by that stage. It can never
produce or preserve a `PASS`/`FAIL` study verdict.

## Statistical acceptance rule

For gating metric `j` and held-out run `i`, the typed extractor produces the
finite value `x[j,i]`. Its source-backed inclusive range is `[a[j], b[j]]` in
the same declared unit. Define one joint success per run:

```text
z[i] = 1 when every gating metric j is uncensored and
           a[j] <= x[j,i] <= b[j], otherwise 0
k     = sum_i z[i]
n     = number of held-out seeds
alpha = 1 - confidence
LCB   = 0                              when k = 0
        BetaInverse(alpha, k, n-k+1)   otherwise
```

Each metric retains its exact in-range vector for diagnosis, but there is one
joint gating verdict. The study passes only when `LCB >= minimum_coverage`.
Diagnostic metrics retain their full vectors and descriptive outcomes but
cannot rescue or fail the study.

Plan validation computes the best possible bound with `k=n` and rejects a
seed count that could not possibly reach the declared coverage/confidence.
Phase 117's 73 Easting red predeclares 20 held-out seeds, 95 percent confidence,
80 percent minimum joint coverage, and four jointly evaluated gating metrics:
28 Iraqi tanks, 16 Iraqi personnel carriers, zero American scoped vehicles,
and the natural 1,380-second duration.
The policy serves the narrow integrity-screen intended use: a repository claim
of repeated historical-outcome consistency must reproduce the complete sourced
episode signature in at least four of five modeled trials at the declared
confidence, not merely select one favorable seed or match independent metric
marginals. With 20 runs this exact rule is deliberately stringent: 20/20 joint
successes yield a lower bound of 0.860891659332 and are required; 19/20 yield
0.783893835793 and are insufficient. It is a repository acceptance
criterion, not a source-derived historical frequency or an estimate of the
real battle's probability. These thresholds are frozen before the run. A later
study must use its own justified, predeclared policy; it may not inherit these
numbers merely because they exist.

## Production execution and artifact

The runner prepares the scenario once with an empty `AnalysisVariant`, then
executes one fresh `RuntimeSession` per held-out seed through a
`HistoricalBacktestRunner`. That runner is factory-owned in the same sense as
the production analysis runner: it accepts only a `PreparedScenario`, builds
fresh sessions, and cannot construct a context, engine, force, or loadout
itself. Typed extractors execute inside its per-session loop before the session
is discarded. It retains the existing batch evidence contract:

- exact ordered raw metric vectors and derived statistics;
- scenario path, data root, variant, seed interval, and maximum ticks;
- source/config fingerprints and authored/loaded rosters;
- code revision, dirty flag, and worktree fingerprint;
- data, catalog, doctrine, loadout, and assignment fingerprints; and
- one public terminal outcome and runtime provenance record per seed.

The historical artifact adds the complete plan snapshot and digest, source
references, typed extractor definitions, per-run in-range booleans, `k`, `n`,
exact joint lower bound, per-metric diagnostic summaries, overall verdict,
disposition eligibility, explicit effective-era identity and era-contract
digests, extractor observation receipts, and explicit rejection/limitation
reasons. Canonical JSON serialization is deterministic. Writing is atomic, and
reloading must reproduce and validate the payload digest before publication.
Every persisted claim, plan, artifact, execution-ledger, source, and
accepted-evidence path is one canonical repository-relative POSIX path.
Absolute or platform-specific paths, empty or dot paths/components, parent
traversal, noncanonical spellings, and symlink components are rejected.
Publication never resolves an output alias to its referent, so a failed or
malicious alias cannot overwrite another evidence file.

The repository runner writes generated output beneath the ignored
`artifacts/evidence/phase-117/` tree by default. Raw vectors and terminal
publications do not enter `main`; an owner-retained publication is copied
byte-for-byte into an evidence-only commit and cited by branch,
repository-relative path, digest, verdict, and qualifications. Storage does not alter
eligibility. In particular, the current accepted-evidence loader contract still
requires its canonical artifact path and committed Git identities, so an
off-main archival copy cannot populate `accepted_evidence` or promote a claim.
The current ledger has no accepted evidence; REM-048 / Phase 135 remains
responsible for any future package-bound accepted-evidence attestation.

Each observation receipt identifies the seed, side, exact unit ID and authored
unit type considered by scoped extractors, observed status, observation time,
boundary/censoring state, and source/config/provenance identities. Artifact
validation recomputes metric vectors, per-run range vectors, joint successes,
statistics, and the verdict from those receipts. A caller cannot replace a
summary vector without also supplying a complete, internally consistent receipt
set whose identities match the run evidence.

A schema-invalid plan, missing required declaration, duplicate or overlapping
seed interval, unsupported extractor, or impossible statistical policy rejects
before execution and emits no artifact. A valid plan declares source-lineage
status as exactly `independent`, `reused`, or `unknown`; `reused` and `unknown`
may execute but are promotion-ineligible. Once execution of a valid plan has
started, runtime construction, extraction, provenance, or completeness failures
emit a typed `ERROR` artifact with no metric or study verdict, the failure
stage, and the evidence completed before the fault. An `ERROR` artifact cannot
be promoted or interpreted as a failed historical outcome. The writer never
publishes a truncated or internally invalid payload.

A dirty artifact is useful candidate evidence and can establish a failure, but
it cannot support `production_validated`. Promotion requires a clean artifact
whose commit, data, source, configuration, plan, and ledger identities match
the accepted tree. The accepted claim must bind its complete metric scope to
exact gating-metric identities, and each catalog outcome must embed the exact
typed gating contract, unit, and a finite source-range value. The artifact
must name the canonical execution-ledger path and digest; every artifact claim
binding must match that ledger as committed at the execution revision. Git
verification proves that the predeclaration revision precedes the execution
revision, the execution revision precedes accepted `HEAD`, and no historical
runner, application source, dependency declaration, or lockfile drifted after
execution. A fresh clean factory preparation must then reproduce the exact
source/config, data/catalog, doctrine, loadout, era, typed-roster, and
assignment identities. Common artifact verification is cached only within one
ledger load; every claim's metric and binding semantics remain independently
checked.

That repository acceptance proof depends on Git and on the canonical artifact
and plan files. The production Docker image intentionally omits `.git` and
`docs/`. Phase 117 locally verifies the packaged zero-accepted loader and
configures a hosted image smoke; only a passing post-push workflow establishes
the actual no-`.git` image result. Either result is limited to conservative
exposure of the current ledger with zero accepted claims. REM-048 / Phase 135
owns a build-time attestation and package-bound receipt before a future
nonempty accepted claim may be advertised from a no-`.git` image.

The Phase 117 real artifact is a verified `FAIL`: all 20 held-out runs recorded
zero scoped Iraqi tanks, zero scoped Iraqi personnel carriers, and
cutoff-censored duration, so joint coverage was 0/20 with lower bound 0.0. The
American-loss gate was in range for all 20.
This leaves 73 Easting `unsupported`; a clean hosted reproduction binds the
final phase commit without converting the failure into a pass. The retained
artifact SHA-256 is
`57bfe7d89575e721d9cee30c213505c760da3cede642624c7ed7532051e524f4`,
with locator
`branch=evidence/full; path=docs/evidence/phase-117/73-easting-phase117.json`.
That evidence branch is currently local and unpublished pending a separate
evidence-remote or Git LFS decision.

The real plan also declares that its Army outcome source informed the shipped
scenario's legacy metadata. Even a hypothetical `PASS` would therefore remain
ineligible for `production_validated`; its value is a transparent same-event
backtest of the new contract. The actual quantitative miss supplies the real
production red.

## Public/API behavior

The scenario API publishes typed claim summaries, not an unqualified scenario
validation badge. Each summary contains the stable claim ID, disposition,
reason codes, intended use, exact metric/event scope, whether current-engine
regression evidence exists, and any accepted study/artifact reference. It must
not expose raw `documented_outcomes` inside the authoritative
`ScenarioDetail.config` object. Unknown or missing ledger identity is returned
as one synthetic `unsupported` claim summary. The same fail-closed behavior
applies to scenarios loaded from an external configured data root; absolute
host paths are not exposed in the synthetic response.

For list filtering and compact display only, the API also publishes a
conservative aggregate: `unsupported` if there are no inventoried claims or any
claim is unsupported; otherwise `current_engine_regression_only` if any claim
has that disposition; and `production_validated` only when every nonempty claim
set is accepted for the same intended use and scope family. The aggregate never
widens an individual claim and the accepted claim IDs remain visible beside it.

The frontend calls the Block 11 set regression references, not historically
calibrated or validated golden scenarios. Scenario detail displays the typed
disposition and limitation. It does not render legacy outcome metadata as a
verdict table.

Public docs distinguish all three dispositions, name zero currently validated
scenarios, and link the source-backed failed study as integrity evidence rather
than historical accuracy.

## Legacy comparison fail-closed behavior

`HistoricalDataLoader`, `ScenarioRunner`, `HistoricalMetric`, and the legacy
Monte Carlo report remain compatibility/diagnostic code only. Their module,
type, and method documentation must say so.

- An empty comparison report never passes.
- Missing, partial, empty, or non-finite run vectors reject rather than being
  filtered or converted to zero.
- Duplicate historical metric names reject.
- The legacy report exposes per-metric diagnostics but no boolean historical
  validation verdict.
- Tests using the legacy runner are classified `unsupported`; factory-backed
  projections without the new plan/artifact remain
  `current_engine_regression_only`.

The hard-coded modern-era propagation defect in `HistoricalCampaign` and the
legacy conversion path remains REM-040 / Phase 127. Phase 117 neither uses that
path nor claims to repair it.

## Failure and negative behavior

The implementation must fail closed according to the pre-run rejection versus
post-start typed-`ERROR` split above for:

- duplicate YAML keys, claim IDs, source IDs, metric IDs, metric names, or
  seeds;
- missing source locators, source assertions, units, ranges, event boundaries,
  training-lineage declarations, or held-out-lineage declarations;
- a source range with non-finite/reversed bounds or an invented multiplicative
  tolerance;
- unsupported extractor IDs, side IDs, statuses, unit types, conversions, or
  source/runtime unit mismatches;
- winner-only gating;
- training/held-out overlap or a sample too small for the declared policy;
- scenario, config, roster, code, data, catalog, doctrine, loadout, assignment,
  or plan identity drift;
- missing/partial/non-finite raw vectors, incomplete observation receipts, or
  inconsistent statistics;
- omitted effective-era identity, changed era-contract digests, incomplete
  extractor receipts, or recorder truncation for any recorder-backed extractor;
- symlinked ledger, claim, plan, artifact input, artifact output, or parent path;
- an invented terminal cause or a historical receipt vocabulary that omits a
  valid production cause such as `ceasefire` or `armistice`;
- a clean-validation claim backed by a dirty or failing artifact; and
- a ledger claim whose normalized content digest no longer matches its source.

Changing one raw vector across an envelope boundary must change the metric and
overall verdict. Changing a diagnostic winner alone must not rescue a failing
loss or duration metric. Reordering seeds, metrics, or claim entries must
either be represented in the digest or reject, never silently normalize away
an authored contract change.

## Completion evidence matrix

| Stage | Required Phase 117 evidence |
| --- | --- |
| Declared | Strict ledger, plan, source, extractor, verdict, and artifact schemas reject all malformed controls above. |
| Loaded | The ledger and 73 Easting plan load through their public strict loaders with exact digests and predeclared seeds. |
| Wired | The study reaches `SimulationRuntimeFactory`, `HistoricalBacktestRunner`, the closed extractors, evaluator, serializer, and artifact validator. |
| Enabled | Historical validation has no feature toggle; a plan is explicit opt-in. A no-plan/unknown-ledger control remains unsupported. |
| Exercised | Twenty fresh held-out 73 Easting sessions produce complete production vectors and a real source-backed `FAIL`. |
| Outcome-affecting | Gating-vector boundary mutations change the verdict; diagnostic winner changes cannot conceal a gating miss. |
| Persisted/exposed | A reload-validated JSON artifact and digest persist the evidence; API/frontend expose the exact catalog disposition. |

Checkpoint persistence is `N/A`: the backtest owns no mutable simulation state
and executes complete fresh sessions. Each runtime's checkpoint contract
remains unchanged. A feature enable/disable pair is `N/A`: historical
conformity is not an optional simulation mechanic; plan/no-plan and
gating/diagnostic controls are the applicable negatives.

## Non-goals and retained limitations

- Phase 117 does not tune scenario, weapon, sensor, morale, victory, or physical
  performance data.
- It does not claim predictive validation, accreditation, or fitness for an
  operational decision.
- It does not manufacture a passing scenario or treat the evaluator's 46 rows
  as historical truth.
- It does not add arbitrary event-expression execution, plugin extractors, or
  user-supplied Python.
- It does not repair REM-040's legacy era propagation, REM-045's scripted-event
  execution, REM-047's 73 Easting source-synchronous engagement-fidelity miss,
  REM-048's future package-bound accepted-evidence attestation, or other queued
  fidelity deficits.
- Exact one-battle backtesting remains limited by historical measurement,
  scenario abstraction, force representation, and the fact that one observed
  battle does not define a full real-world probability distribution.

## Phase 117 acceptance (satisfied)

Phase 117 closed only after:

1. the exact 31 collections / 83 metrics and every identified test/public
   claim have an auditable ledger disposition;
2. zero unsupported or regression-only claims are described as historically
   validated or predictive;
3. the typed production study and artifact contracts pass focused malformed,
   pass-control, fail-control, determinism, and reload validation;
4. the frozen 73 Easting plan produces complete held-out production vectors
   and a durable source-backed `FAIL` artifact without tuning;
5. the Debecka mismatch and every unsupported extractor remain explicit;
6. legacy comparison code cannot emit a boolean historical pass;
7. API/frontend/docs expose the truthful classification;
8. a non-modern production preparation/execution control proves that exact era
   identity and era-contract digests reach study evidence without the lossy
   legacy campaign conversion;
9. the repository `$backtest` skill names the factory-owned study/artifact
   route rather than the superseded direct context/engine helpers; and
10. applicable backtest, data, scenario, determinism, convention, broader,
   documentation, cross-document, and postmortem gates pass before the one
   coherent Phase 117 commit.

## Sources

- U.S. Government Accountability Office, *Defense Transportation: Study
  Limitations Raise Questions about the Adequacy and Completeness of the
  Mobility Capabilities Study and Report*, GAO-06-938 (2006), especially the
  documented VV&A and data-limitation criteria:
  <https://www.gao.gov/assets/a251585.html>.
- U.S. Government Accountability Office, *Defense Transportation: DOD Has
  Taken Actions to Incorporate Lessons Learned in Its Movement Analyses, but
  Additional Actions Are Needed*, GAO-05-659R (2005), pp. 4--5:
  <https://www.gao.gov/assets/gao-05-659r.pdf>.
- NIST/SEMATECH, *e-Handbook of Statistical Methods*, “Exact intervals for
  small numbers of failures and/or small sample sizes”:
  <https://itl.nist.gov/div898/handbook/prc/section2/prc241.htm>.
- Headquarters, Department of the Army, *ARMOR*, PB 17-15-4,
  October--December 2015, p. 98:
  <https://www.benning.army.mil/armor/eARMOR/content/issues/2015/OCT_DEC/ARMOR_October-December2015Edition.pdf>.
- Nathan S. Lowrey, “The Battle for Debecka Crossroads,” *Veritas*, vol. 1,
  no. 1 (2005), pp. 79--85, especially p. 84, U.S. Army Special Operations
  History Office:
  <https://arsof-history.org/articles/pdf/v1n1_debecka_crossroads.pdf>.

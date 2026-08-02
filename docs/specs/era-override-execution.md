# Era Override Execution

Status: **Implemented and behaviorally validated; Phase 114 complete and
REM-018 closed**. The owner-approved performance result remains explicitly
contention-qualified; no uncontended wall-clock pass is claimed.

Phase 115 advances the current engine checkpoint from format 114 to format 115
for tactical-targeting state. It preserves the exact Phase 114
`era_runtime_contract` and clock/resolution owner unchanged. Phase 116 then
advances the current format to 116 for fog-of-war contact continuation while
preserving that era boundary. The format-114 language below records the
historical Phase 114 acceptance boundary.

This specification is the Phase 114 / REM-018 contract. It replaces
executable-looking era metadata with one typed runtime-owned resolution
boundary. A value is supported only when a production-loaded runtime can
exercise the affected clock or engine behavior and checkpoint the exact
effective contract.

## Purpose and scope

Phase 114 must:

- replace arbitrary `physics_overrides` and `tick_resolution_overrides`
  dictionaries with strict typed declarations;
- resolve the selected registry entry and all supported values once, before
  RNG, clock, terrain, force, or domain-engine construction;
- make supported values change the intended logical clock or loader-created
  engine behavior;
- preserve authored/default effective parameter values exactly when overrides
  are omitted, apart from the deliberate correction of duplicate strategic
  maintenance advancement;
- persist and compare the fully effective runtime contract before checkpoint
  mutation; and
- reject metadata whose intended production prerequisites do not exist rather
  than exposing another structural-only capability.

This phase does not invent historical values. The checked-in legacy physics
numbers have no traceable military source, so no shipped era preset may make
them outcome-affecting.

## Typed declarations

`EraPhysicsOverrides` is a frozen, `extra="forbid"` Pydantic model. Its only
supported keys are:

| Key | Type and constraint | Production owner |
| --- | --- | --- |
| `treatment_hours_minor` | strict finite float greater than zero | `MedicalEngine` / `MedicalConfig` |
| `treatment_hours_serious` | strict finite float greater than zero | `MedicalEngine` / `MedicalConfig` |
| `treatment_hours_critical` | strict finite float greater than zero | `MedicalEngine` / `MedicalConfig` |
| `repair_time_hours` | strict finite float greater than zero | `MaintenanceEngine` / `MaintenanceConfig` |

`EraTickResolutionOverrides` is likewise frozen and forbids extra fields. Its
only supported keys are `strategic_s`, `operational_s`, and `tactical_s`; each
is a strict finite float greater than zero that is exactly representable at
the simulation clock's microsecond precision and within Python's executable
calendar domain. Values that would quantize, overflow `timedelta`, or exceed
the full `datetime` domain are errors even though they are positive and
finite.

For both models, omission is distinct from a declared value. Explicit `null`,
booleans, numeric strings, zero, negative values, NaN, infinity, misspellings,
and unknown keys are errors. Registration must revalidate mutated input through
the same strict schema and store an isolated copy.

The former `c2_delay_multiplier` and `cbrn_nuclear_enabled` keys are not
supported by Phase 114. They must be removed from the shipped presets and any
attempt to declare them must fail with the offending key in the validation
error. Production C2 has no loaded or unit-bound communications topology, and
scheduled nuclear declarations have no production consumer. Direct
`compute_delay()` or `detonate_nuclear()` calls would not repair those missing
stages. Their production work belongs to explicit follow-up remediations.

## Effective runtime contract

One frozen `EraRuntimeContract` owns the resolved values used by production.
It contains:

- the selected registry identifier from `CampaignScenarioConfig.era`;
- the `EraConfig.era` label, retained separately because custom registry names
  may use a standard era label;
- all three effective tick durations;
- all three effective medical treatment durations; and
- the effective maintenance repair duration.

The contract materializes destination defaults for omitted physics fields and
then overlays the sparse typed declarations. It materializes the scenario's
authored `tick_resolution` and then overlays sparse era tick declarations.
This makes the checkpoint describe behavior, not merely the metadata that was
intended to produce it.

`tick_duration_seconds` is the existing explicit uniform-cadence shorthand.
A scenario using that shorthand with a nonempty era tick override is
ambiguous and must fail before runtime construction. With no era tick
override, the shorthand continues to set all three effective resolutions to
the declared duration. With no shorthand, a sparse era override changes only
its named resolution and preserves the other authored scenario values.

Resolution happens immediately after scenario validation and before the first
RNG manager, event bus, clock, terrain, loader, or entity is constructed. A
failure therefore consumes no simulation RNG state and commits no runtime
objects.

Resolution also preflights the parsed scenario start plus the declared
duration and one maximum effective interval. Both factory preparation and a
direct loader reject a calendar horizon that cannot execute before creating
an RNG manager. This scenario-specific check closes the narrower case where a
duration fits `timedelta` and the global calendar span but cannot advance from
the authored start date.

`CampaignScenarioConfig` validates only a normalized, nonempty, trimmed era
identifier. Registry existence is resolved at exactly two runtime boundaries:
the authoritative `SimulationRuntimeFactory` while preparing each immutable
variant, and a direct lower-level `ScenarioLoader.load()`. Both resolutions
occur before RNG or runtime construction and reject an unknown identifier.

`PreparedScenario.build` revalidates captured scenario data without a registry
bypass or registry lookup, requires its normalized era ID to equal the captured
contract's selected registry ID, and injects isolated serialized `EraConfig`
and contract values. `ScenarioLoader` recomputes and verifies their agreement
from those captured values without consulting the registry. This keeps
repeated builds of one prepared source stable if a custom registry entry is
later replaced; a new preparation resolves the replacement.

The prepared variant's `config_fingerprint` covers the scenario config,
doctrine assignments, isolated era config, and effective runtime contract.
Runs with behaviorally different era inputs therefore cannot share analysis or
API provenance merely because their scenario YAML is identical.

The runtime separately captures and compares the exact source inputs used to
resolve that contract: selected registry ID, all three authored scenario tick
values, and the optional uniform shorthand. A later mutation is rejected even
when an era overlay shadows the changed authored field and leaves the effective
duration numerically unchanged. The scenario start and declared duration are
likewise captured because they define the executable clock horizon.

The contract is passed explicitly into the domain-engine construction
boundary. Helpers must not rediscover it through `getattr`, read source
metadata independently, or route a value through a semantically unrelated
configuration object. In particular, `repair_time_hours` configures
`MaintenanceEngine`, never `EngineeringConfig`.

## Observable behavior

### Tick resolution

`SimulationClock` and `SimulationEngine` both consume the contract's effective
tick values. Before each interval the engine validates the current clock and
domain-consumer bindings, selects one `interval_resolution`, sets its contract
duration, and uses that same `dt` and endpoint timestamp for every subsystem
executed in the interval. State discovered during an interval may determine
the next interval's resolution but may not relabel or execute new-resolution
work using the completed interval's duration. Initial contact and closing
range are classified before the first advance.

Production proofs must exercise the natural resolution paths:

- separated forces remain strategic and advance by `strategic_s`;
- closing forces classify or transition to operational and the bound interval
  advances and executes with `operational_s`; and
- forces in contact start tactical and advance by `tactical_s`.

Reading a configuration field or a private `_tick_durations` mapping is not
acceptance evidence.

### Medical treatment

A runtime built through `SimulationRuntimeFactory.prepare/prepare_config ->
PreparedScenario.build -> RuntimeSession` may be given a real
`MedicalFacility` and casualty through the engine's public
registration/admission methods. Only `RuntimeSession.step()` may advance
treatment in the authoritative acceptance proof. Direct-loader coverage is a
lower-boundary control, not sole production evidence. For each severity, the
declared duration must change the logical completion endpoint relative to an
omitted control with the same seed and setup. Completion is observed at the
first production interval endpoint satisfying the treatment threshold.

This proves the era construction boundary and live engine cadence. It does not
claim that battle casualties are automatically admitted to medical care;
that missing lifecycle remains a follow-up.

### Maintenance repair

A factory-built `RuntimeSession` may register real equipment through the
public maintenance API. Breakdown must be reached through
`RuntimeSession.step()`, repair must be started through the public API, and
subsequent session steps must produce different completion endpoints for
declared and omitted controls. Completion is observed at the first production
interval endpoint satisfying the repair threshold. Tests may not mutate
private records or invoke `MaintenanceEngine.update()` directly.

Maintenance advances exactly once per logical interval. The all-resolution
`SimulationEngine` cadence is authoritative; the duplicate strategic
`CampaignManager` update is removed. This is an intentional state/RNG semantic
correction; omission preserves parameter values, not the prior double update.
It does not claim that loadouts are
automatically registered or that spare-parts logistics starts repairs; those
missing lifecycle stages remain follow-up work.

## State and persistence

Checkpoint format 114 persists `era_runtime_contract` exactly once in the
simulation context. The source scenario configuration and selected
`EraConfig` remain persisted for input and gate identity; neither substitutes
for the effective contract.

Before any live mutation, restore must:

1. validate the strict format-114 topology;
2. parse the checkpoint contract through its typed schema;
3. require exact equality with the target runtime contract, including the
   selected registry identifier; and
4. require the saved clock duration to agree with the saved engine resolution
   under that contract.

Full checkpoint restoration is engine-owned because engine state owns the
resolution. Context preflight validates contract and consumer identity; the
engine additionally validates clock-to-resolution agreement before any owner
commits. Active non-default treatment and repair must survive fresh and
in-place restore with exact state, events, timestamps, RNG state, and
same-seed continuation versus an uninterrupted run.

Missing, extra, malformed, or different contract data is an atomic error.
Fresh-runtime and in-place restore must preserve exact state at the checkpoint
and exact same-seed continuation after it.

A versionless checkpoint may omit the new field only for a target whose era
override declarations are empty and whose existing config/era/clock checks
prove the baseline. Versionless restore into a runtime with any declared era
override is rejected rather than inferred. Versioned formats other than 114
remain unsupported.

## Configuration and failure semantics

- Unknown or invalid declarations fail at `EraConfig` construction or
  registration.
- Tick declarations and scenario cadence inputs that quantize below or between
  clock microseconds, overflow duration/calendar storage, or cannot execute
  through the declared scenario horizon fail before RNG construction.
- A uniform cadence plus era tick override fails before RNG/runtime creation.
- Unsupported legacy C2/nuclear keys fail explicitly; they are not ignored,
  aliased, or converted to unrelated proxies.
- Engine construction uses the typed contract directly and may not silently
  fall back if a value cannot be applied.
- The captured `EraConfig` and `EraRuntimeContract` are nonreplaceable context
  identities. Their exact scenario-side cadence inputs and execution horizon
  are stable identities too. Medical and maintenance configurations are
  complete and frozen before engine construction. Before every step and
  checkpoint, the runtime rejects any contract/config/clock divergence rather
  than persisting false behavior or provenance.
- A prepared production variant freezes and injects its isolated era inputs;
  later registry mutation cannot alter a repeated build.
- Maintenance observes one runtime-owned update per logical interval at every
  engine resolution.
- Checkpoint mismatch validation is preflight-only and atomic.

## Production trace

| Stage | Phase 114 contract |
| --- | --- |
| Declared | Strict frozen physics/tick declaration models and frozen effective runtime contract |
| Loaded | Selected registry entry resolved during authoritative factory preparation, or at `ScenarioLoader` for an explicit direct load, before RNG/runtime construction |
| Wired | Contract exclusively supplies clock, engine resolution, medical config, and maintenance config |
| Enabled | Sparse declarations overlay their exact baseline; omission is an exact control |
| Exercised | Natural strategic/operational/tactical steps and public medical/maintenance setup followed by production engine steps |
| Outcome-affecting | Logical-time advance and treatment/repair completion timing differ from same-seed omitted controls |
| Persisted/exposed | Format-114 context checkpoint stores and compares the exact effective contract; API/analysis fingerprints include the captured era inputs |

External REST/frontend exposure is N/A. REM-018 is a mandatory construction
and checkpoint contract selected by scenario era; the current API already
uses the authoritative runtime factory, and no user-facing override editor is
introduced in this phase. Existing API/analysis `config_fingerprint` exposure
does include the effective era inputs.

## Stochastic and military basis

Phase 114 adds no distribution or military parameter. Medical and maintenance
retain their existing engine models and RNG stream ownership. Synthetic test
overrides validate wiring only and are not historical calibration. Shipped
era presets omit the old unsourced physics numbers.

Tick changes alter how often existing stochastic and deterministic work is
executed. Same-seed fresh replay, checkpoint continuation, event ordering, and
RNG stream state therefore require determinism review.

## Verification plan

The initial red proof must show that the current arbitrary schema accepts
invalid/unknown metadata, persists dead values, and leaves production clock,
medical, and maintenance behavior at defaults.

Focused acceptance includes:

1. strict positive/finite/type and unknown-key rejection, exact microsecond
   representation, duration/calendar range, executable scenario-horizon
   preflight before RNG, and acceptance of the exact one-microsecond boundary;
2. registration isolation and mutation revalidation;
3. conflict rejection for `tick_duration_seconds` plus era ticks;
4. sparse overlay and exact omitted controls;
5. prepare-once/build-twice isolation from later registry replacement, a new
   preparation that reflects the replacement, and distinct exposed
   fingerprints for behaviorally distinct era contracts, plus rejection of a
   mutated authored tick source even when an era overlay shadows its effective
   value;
6. natural production strategic, operational, and tactical cadence effects,
   plus strategic-to-operational, operational-to-tactical, and de-escalation
   interval proofs covering manager path, subsystem `dt`, event
   timestamp/order, and checkpoint cadence agreement;
7. public-setup/production-step medical behavior for all three severities;
8. exactly-once public-setup/production-step maintenance repair behavior;
9. exact format-114 topology; missing/extra/malformed/mismatched contract and
   clock/resolution rejection before mutation; explicit format-113 rejection;
   versionless omitted/declaration cases; active treatment/repair fresh and
   in-place restoration; and exact same-seed state/event/RNG continuation;
10. unchanged built-in era loading with no invented historical values; and
11. authoritative factory/API construction using the same boundary.

Applicable closure routes are `$audit-determinism`, `$validate-data`,
`$evaluate-scenarios`, `$validate-conventions`, `$simplify`, `$update-docs`,
`$cross-doc-audit`, and `$postmortem`. A paired omitted-control performance
check is a regression guard; this O(1) construction merge is not itself a
performance capability.

## Non-goals and accepted limitations

- No historical treatment, repair, C2, nuclear, or tick value is introduced or
  calibrated.
- Automatic medical admission, facility topology, equipment maintenance
  registration, repair logistics, communications equipment assignment, and
  scheduled CBRN employment are not claimed by REM-018.
- REM-020 and REM-021 retain their existing logistics authority scope.
- Historical scenario validation remains REM-030.
- The validation-only campaign-data factory's era loss was recorded as
  REM-040/Phase 127 before Phase 114 closed; it was not silently absorbed into
  this contract.

## Open decisions

None. REM-035 through REM-040 record the production prerequisites surfaced
during Phase 114 documentation closure.

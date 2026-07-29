# ASAT Production Integration

**Status:** Implemented, verified, and accepted in Phase 110

**Owner:** REM-011

## Purpose and scope

Phase 110 replaces the logging-only ASAT hook with one typed, deterministic
production path:

`scenario YAML -> CampaignScenarioConfig -> ScenarioLoader space catalogs ->
SpaceEngine -> ASATEngine scheduled action -> satellite/asset state ->
EventBus/recorder/API/checkpoint`

The supported capability is a scenario-authored, direct-ascent kinetic ASAT
action against one exact catalog-backed enemy satellite. The action executes
when logical simulation time first reaches its declared time, consumes finite
state from one uniquely identified ASAT asset, changes the satellite state on
a hit, and exposes the attempt and constellation outcome.

This is a strategic-asset abstraction. An ASAT asset is owned by a scenario
side and has finite rounds and a weapon-catalog definition, but it is not
attached to a tactical map unit or its Class V magazine.

## Requirements

### Typed scenario contract

`CampaignScenarioConfig.space_config` is `SpaceConfig | None`, not an
untyped dictionary. A dependency-neutral `space.config` module owns
`SpaceConfig`, constellation definitions, ASAT weapon definitions, asset
declarations, action declarations, and their enums. `space.constellations`
and `space.asat` may re-export their historical public names but neither
defines nor imports configuration from the other. All models reject unknown
fields and non-finite values.

The scenario-facing ASAT fields are:

- `enable_space: bool`, default `false`;
- `constellation_ids: list[str]`, in declaration order;
- `enable_asat: bool`, default `false`;
- `asat_assets: list[ASATAssetConfig]`;
- `asat_orders: list[ASATOrderConfig]`.

An asset declares a unique, non-empty `asset_id`, an exact `weapon_id`, one
scenario `side`, and positive integer `rounds_available`. An order declares a
unique, non-empty `order_id`, an exact `asset_id`, an exact
`target_satellite_id`, and finite non-negative `execute_at_s`.

`enable_space: false` may not carry space catalogs, assets, or orders.
`enable_space: true` in a production scenario requires at least one explicit
constellation. Assets and orders are validated even when `enable_asat` is
false, so a disabled control can use the identical declared world and plan.
`enable_asat: true` requires at least one asset and one order. Every order
must execute no later than `duration_hours * 3600`; a plan that can never
become due is a load error, not a pending no-op.
`duration_hours` is a strict finite positive number; booleans, numeric
strings, NaN, and infinity are rejected before the order-horizon comparison.
`enable_asat` is the only ASAT execution sub-gate; the older
`calibration_overrides.enable_space_effects` remains scoped to its Phase 65
ISR/SIGINT effects and does not silently form a second ASAT gate.

The loader derives omitted space theater latitude/longitude from the scenario
latitude/longitude. Explicit values remain allowed and must be finite and
within geodetic bounds.

### Catalog and reference integrity

For every `enable_space: true` scenario, the production loader reads and
validates all files under `data/space/constellations/` and
`data/space/asat_weapons/` with the strict duplicate-key YAML loader and a
canonical sorted traversal, then materializes only explicitly selected
constellations and referenced weapon definitions. Space-disabled scenarios do
not read the optional catalogs. The repository data validator always checks
the complete catalogs. The boundary rejects:

- duplicate catalog IDs, selected constellation IDs, asset IDs, or order IDs;
- an unknown constellation, weapon, asset, side, or satellite reference;
- duplicate generated satellite IDs or an inconsistent constellation
  topology;
- invalid enum values, orbital elements, counts, ranges, reload values, or
  type-specific weapon fields;
- an asset whose side is absent from the scenario;
- a friendly target;
- a target whose possible orbital-altitude envelope does not intersect the
  weapon's declared altitude envelope; and
- a production asset using an unsupported ASAT type.

Identifiers must be non-empty, trimmed strings. Counts are strict integers,
not booleans: satellite, plane, satellites-per-plane, and available-round
counts are positive. `num_satellites` must equal
`plane_count * sats_per_plane`; implicit truncation is forbidden. The orbital
template requires finite semimajor axis, eccentricity, inclination, RAAN,
argument of perigee, and true anomaly. Eccentricity is in `[0, 1)`,
inclination is in `[0, 180]`, angular fields are in `[0, 360)`, semimajor axis
is positive and no greater than `1e9` metres, and computed perigee must remain
above Earth's surface. The upper bound is the declared numerical domain of
the Earth-orbit propagator, not a military performance claim.

Space latitude is in `[-90, 90]`, longitude in `[-180, 180]`, minimum
elevation in `[0, 90]`, intervals and positive uncertainty scales are finite
and positive, and probabilities/fractions are in `[0, 1]`. Non-negative
rates may be zero only where zero has a defined disabled meaning.

ASAT altitude bounds are finite, `0 <= min_altitude_km <
max_altitude_km`; reload and velocity metadata are finite and non-negative.
For direct-ascent kinetic definitions, lethal radius, guidance sigma, and
closing velocity are positive, while dazzle duration/range are zero. For a
laser-dazzle catalog definition, kinetic fields are zero and dazzle
duration/range are positive. Other enum-specific schemas remain strict even
though their production use is rejected.

Phase 110 supports `DIRECT_ASCENT_KKV`. `CO_ORBITAL`,
`GROUND_LASER_DAZZLE`, and `GROUND_LASER_DESTRUCT` fail explicitly at the
production asset boundary. In particular, the existing dazzle dictionary has
no GPS, ISR, early-warning, or SATCOM consumer and therefore cannot be
presented as outcome-affecting behavior.

Catalog weapon IDs identify immutable definitions. Scenario `asset_id` values
identify mutable weapon instances. Multiple assets may use the same definition
without overwriting ownership, inventory, or cooldown state.

`ASATEngine` receives the completely validated immutable definition/asset/order
set in its constructor and owns all mutable asset/order/debris state. The old
incremental `register_weapon()` and caller-supplied-side `engage()` APIs are
removed; they may not remain as ownership, inventory, or validation bypasses.
There is no direct production fire entry point outside the configured action
queue.

### Timing, ordering, and execution

`SpaceEngine.update()` is the one orchestration boundary. It passes the
scenario clock timestamp into its sub-engines and, at each simulation tick:

1. propagates the selected satellites to the tick's logical end time;
2. updates pre-existing ASAT debris/timers;
3. executes all newly due orders in canonical
   `(execute_at_s, declaration_index)` order; and
4. computes GPS, ISR, early-warning, and SATCOM effects from the resulting
   satellite state.

Thus a successful action affects downstream space consumers in the same
logical tick. Strategic, operational, and tactical resolution changes do not
alter this rule. An order executes at most once and is never retargeted.

Before a random draw, the runtime verifies that the asset exists, owns a
round, is out of cooldown, and that the exact enemy target exists, is active,
and is currently within range. A rejected action is completed once with an
explicit reason; it consumes no round and no RNG draw. An accepted launch
consumes one round even on a miss and starts that asset's cooldown.

Cooldown starts at the actual logical tick-end execution time, not the
scheduled time. Simultaneously due orders retain declaration order. For two
orders using the same asset, the first accepted launch commits before the
second is checked. The second is `asset_depleted` when no rounds remain,
otherwise `asset_reloading` while the cooldown is active. An order scheduled
at zero executes on the first engine tick, never during loading.

The kinetic hit probability is the Rayleigh radial-error CDF

`Pk = 1 - exp(-0.5 * (lethal_radius_m / guidance_sigma_m) ** 2)`.

`guidance_sigma_m` is the modeled one-axis standard deviation of independent,
zero-mean, isotropic intercept miss error at the target. The former arbitrary
closing-velocity multiplier is not part of the production equation.
`closing_velocity_mps` remains catalog metadata. Every stochastic draw uses
the injected `ModuleId.SPACE` generator; disabled or pre-launch rejected
orders consume no draw.

On a hit, `ConstellationManager`—not the ASAT engine by direct field
assignment—deactivates the exact satellite. A secondary debris collision also
selects the first eligible active satellite in canonical satellite-ID order
and routes the mutation through the same manager boundary. Both paths emit a
constellation degradation event. Kinetic debris remains the existing
configurable Poisson abstraction and is not claimed as a calibrated NASA
breakup model. Its authored Poisson mean is bounded at `1e18`; restored debris
counts are non-negative signed-64-bit integers so sampling, aggregation, and
collision-probability arithmetic remain inside a validated numerical domain.
The Rayleigh equation uses a stable `expm1` form and saturates at one when the
ratio is beyond a numerically meaningful tail.

### Observable results and failure behavior

Every due order emits one `ASATEngagementEvent`, including:

- order, asset, weapon, attacker side, target satellite, and target
  constellation IDs;
- scheduled and actual logical execution seconds;
- whether a launch occurred, hit probability, hit/miss/rejected outcome, and
  rejection reason;
- debris generated, remaining rounds, and constellation count before/after.

All event fields use JSON-safe `str`, `float`, `int`, and `bool` values.
`outcome` is exactly `hit`, `miss`, or `rejected`. `reason` is empty for a
launch and otherwise exactly `asset_depleted`, `asset_reloading`,
`target_inactive`, or `target_out_of_range`. A no-launch result has
`launched=false`, `hit=false`, and `pk=0.0`. Configuration-time missing,
ownership, friendly-target, unsupported-type, and impossible-envelope defects
never become runtime rejection events.

A hit emits `ConstellationDegradedEvent` before
`ASATEngagementEvent`; a miss or rejection emits only the engagement event.
The engagement field is named `attacker_side` so the existing API side filter
can select it. Events use the scenario clock, are recorded by
`SimulationRecorder`, and are available through the existing generic API event
endpoint. Observer failures occur after the committed transition and are
collected/logged rather than rolling back or duplicating the action.

Configuration and catalog errors fail scenario loading before a
`SimulationContext` is returned. Runtime order rejection is an observable
domain result, not a swallowed exception or debug-only log.

### State and persistence

Checkpoint state includes:

- a canonical fingerprint of selected constellation definitions, weapon
  definitions, assets, and orders;
- exact satellite IDs, active flags, and orbital state;
- per-asset definition/owner topology, initial and remaining rounds, and
  cooldown time;
- pending/completed order identity and completed results;
- debris/timer state; and
- the existing `ModuleId.SPACE` RNG state through `RNGManager`.

Restore validates configuration, catalog fingerprint, exact satellite/asset/
order topology, numeric ranges, logical clock alignment, pending/completed
partition, result/inventory/cooldown consistency, disabled-runtime pristine
state, debris conservation, and constellation-count chronology before
mutating live space state. GPS and SATCOM prior-value caches must match the
staged constellation snapshot; ISR overpass history may not refer to an
unknown satellite or a future logical time. `SimulationContext.set_state()`
stages this complete space validation before committing its clock, RNG, units,
morale, loadouts, or any other context-owned state; a corrupt space checkpoint
leaves the entire runtime unchanged. A fresh runtime restored at a checkpoint
must continue with the same event order, hits, debris, inventory, satellite
state, service history, and RNG state as uninterrupted execution. Phase 110
advances the engine checkpoint schema to version 110.

## Military and mathematical basis

- **Tier 1 / official doctrine:** U.S. Space Force,
  *Space Warfighting: A Framework for Planners* (March 2025), pp. 9 and
  17-18. The framework treats orbital strike as a planned kinetic or
  non-kinetic action, says target/weapon pairing and target development are
  deliberate activities, and calls for observable measures of performance
  and effectiveness. This supports explicit predeclared target/action records
  and state outcomes, not an automatic "first enemy satellite" selector:
  <https://www.spaceforce.mil/Portals/2/Documents/SAF%202025/Space_Warfighting_A_Framework%20_for_Planners%20_WTE3.pdf>.
- **Tier 1 / government statistical reference:** NIST, `RAYCDF`, gives
  `F(x)=1-exp(-0.5*((x-u)/sigma)^2)` for the Rayleigh CDF. Under the stated
  two-axis Gaussian miss assumption, the probability that radial miss is
  within the lethal radius is this CDF:
  <https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/raycdf.htm>.
- **Tier 1 / government technical evidence:** NASA Orbital Debris Program
  Office, Murray et al., *Observations of Small Debris from the Cosmos 1408
  Anti-Satellite Test using the HUSIR and Goldstone Radars* (2022), reports
  more than 1,500 trackable fragments and uses the NASA Standard Satellite
  Breakup Model. It establishes that destructive ASAT outcomes create
  persistent, orbit-dependent debris risk, but it does not validate this
  repository's simple Poisson count or collision coefficient:
  <https://ntrs.nasa.gov/citations/20220011989>.

The checked-in weapon performance values are nominal simulation inputs, not
verified intelligence estimates or historical calibration. Phase 110 proves
software integration and deterministic state behavior, not real-world ASAT
effectiveness.

## Acceptance criteria

1. The shipped ASAT scenario loads selected real constellation and weapon
   catalogs into a production `ScenarioLoader` runtime.
2. A due direct-ascent order traverses `SimulationEngine` exactly once,
   consumes finite asset state, and produces an ASAT event.
3. The fixed-seed enabled scenario changes the exact enemy LEO satellite and
   constellation count; an otherwise identical `enable_asat: false` control
   does not change either and consumes no ASAT RNG.
4. Ownership, friendly target, missing reference, duplicate ID, unsupported
   type, impossible altitude envelope, depleted/reloading, not-yet-due, and
   inactive-target controls fail or report exactly as specified.
5. A real space-service consumer observes the post-ASAT satellite state in the
   same tick, while a disabled control observes the intact state.
6. Same-seed fresh runs and hash-seed controls preserve order and outcomes.
7. Fresh checkpoint restore before/after an action proves no duplicate
   execution and exact continuation of satellite, asset, order, debris, event,
   and RNG state.
8. Corrupt catalog fingerprint, satellite/asset/order topology, and mutable
   ASAT state are rejected before any whole-runtime state mutation.
9. Recorder and API tests expose the action identifiers and satellite count
   transition.
10. The data validator checks all 9 constellation files and all 3 ASAT weapon
   files, plus scenario references, with zero errors or warnings.
11. The ASAT scenario evaluator and applicable surrounding scenario rows are
   recorded and semantically reviewed.
12. Focused and broader tests, repository-wide Ruff, strict documentation,
    applicable skill reviews, and the Phase 110 postmortem are green before
    REM-011 closes.

## Non-goals and accepted limits

- No autonomous commander target selection, dynamic retasking, or generic C2
  order integration.
- No tactical map-unit launcher, logistics Class V synchronization, or
  aggregation ownership. Those require a separate authority contract.
- No production claim for co-orbital, laser-dazzle, or laser-destruct ASAT.
- No claim that one satellite loss necessarily changes terrestrial combat
  results; the required Phase 110 outcome is the satellite/constellation state
  and its exposed event.
- No historical scenario, backtest, ASAT performance calibration, or
  high-fidelity debris breakup/collision model.

## Scenario migration decisions

- `space_asat_escalation` becomes a hypothetical direct-ascent validation
  scenario. It explicitly selects `keyhole_optical`, declares one
  red-owned `nudol_asat` asset with one round, and schedules one exact strike
  against `keyhole_optical_p0_s0` at 7,200 seconds. All tick resolutions are
  fixed at 3,600 seconds so the order is not made dependent on tactical battle
  proximity. It retains its existing geographic setting; omitted space
  theater coordinates derive from that setting.
- `taiwan_strait` and `korean_peninsula` remain ASAT-disabled. Each explicitly
  selects the blue-owned `gps_navstar`, `keyhole_optical`, `lacrosse_sar`,
  `sigint_leo`, `sbirs_ew`, `milstar_satcom`, and `wgs_satcom` catalogs.
  These are hypothetical allied availability assumptions, not historical
  order-of-battle claims. Their omitted space theater coordinates derive from
  the scenario coordinates.
- No Russian-owned `glonass` or `molniya_ew` constellation is assigned to the
  generic red side in either 2025 scenario. Production behavior changes caused
  by activating the selected space assets must be captured in identical-seed
  pre/post evaluation rows rather than hidden.

## Verification plan

The initial red proof must use the real `ScenarioLoader`,
`SimulationEngine`, recorder, and shipped ASAT scenario. It must show that the
phase-start revision creates no space engine for that scenario, that other
enabled scenarios create empty space registries, and that a tick produces no
ASAT event or satellite change. A dedicated red test then encodes the typed
production contract before implementation.

Focused verification covers strict schemas/catalogs, loader references,
enabled/disabled execution, order timing and ordering, ownership/inventory,
same-tick service consumption, deterministic cascade selection, event payload
and order, observer failure, deterministic replay, whole-runtime checkpoint
atomicity/continuation, and API exposure. Applicable legacy Phase
17/54/65/107 tests remain regression controls. Catalog-wide validation,
scenario evaluation (including the two activated surrounding scenarios), the
default backend suite, API and E2E suites, repository-wide Ruff, and strict
MkDocs form the broader gate. Exact commands, counts, warnings, exclusions,
and scenario rows belong in the Phase 110 devlog.

## Design review verdict

The dedicated typed space-domain action queue is **APPROVED WITH NOTES** as
the smallest coherent Phase 110 design. Generic C2 orders and
`scripted_events` lack the required typed payload, stable logical clock,
checkpointed action state, and explicit target semantics. The design verdict
does not establish implementation completeness or phase status.

## Open decisions

None for Phase 110. The accepted limits above require new, separately scoped
work before broader ASAT capability claims.

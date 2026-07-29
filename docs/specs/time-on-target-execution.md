# Time-on-Target Execution

**Status:** Verified - Phase 111 complete; REM-012 closed

**Owner:** REM-012

## Purpose and scope

Phase 111 replaces the disconnected, stateless time-on-target helpers with one
typed production path:

`scenario YAML -> CampaignScenarioConfig -> ScenarioLoader -> resolved live
batteries -> IndirectFireEngine scheduled fire/impact lifecycle -> unit and
loadout state -> EventBus/recorder/API/checkpoint`

The supported capability is a preplanned tube-artillery or mortar mission
against one fixed ENU target point and one exact enemy unit. Each participating
battery has an exact unit, live weapon attachment, ammunition type, round
count, and fire-control time of flight. Batteries fire once at their derived
times, their generated impacts remain in flight, and the mission resolves once
at the common scheduled impact time.

This is a fire-direction scheduling abstraction, not a new exterior-ballistics
or command-and-control model. The repository does not contain weapon,
projectile, charge, atmosphere, and firing-table data sufficient to compute
production artillery time of flight. Phase 111 therefore requires an explicit
fire-control time for each battery instead of preserving the unsupported
`2 * range / muzzle_velocity` proxy or inventing another silent fallback.

## Requirements

### Typed scenario contract

`CampaignScenarioConfig.indirect_fire` is an
`IndirectFireScenarioConfig`, with:

- `enable_time_on_target: bool`, default `false`; and
- `time_on_target_missions: list[TimeOnTargetMissionConfig]`, default empty.

Every nested model rejects unknown fields. Identifiers are non-empty, trimmed
strings. Numeric values reject booleans, strings, NaN, and infinity.

A mission declares:

- unique `mission_id`;
- exact `target_unit_id`;
- `target_position` as explicit finite `easting`, `northing`, and `altitude`
  in internal ENU metres;
- a strict positive whole-second `impact_time_s`, measured from scenario
  start;
- a strict positive integer `rounds_per_battery`; and
- one to six ordered `batteries`.

Each battery declares:

- exact `unit_id`;
- strict non-negative `source_equipment_index`, identifying the exact Phase 109
  attachment rather than assuming a catalog weapon ID is unique on a unit;
- exact `weapon_id`;
- exact `ammo_id`; and
- a strict positive whole-second `time_of_flight_s`, representing the
  fire-direction solution's predicted muzzle-to-impact hang time.

Mission IDs are unique across the scenario. Battery unit IDs are unique within
one mission. The six-battery limit is rejected at validation; no plan is
silently truncated. `impact_time_s` must not exceed
`duration_hours * 3600`, and every derived
`impact_time_s - time_of_flight_s` must be strictly positive.

Any declared mission, including a disabled populated control, requires a
strict positive whole-second `tick_duration_seconds`. The loader makes all
three engine resolutions use that one fixed cadence, and every derived fire
time and impact time must be an exact multiple of it. Subsecond,
microsecond-inexact, and off-cadence schedules fail loading. This implements
the cited whole-second fire-control abstraction without floating-point clock
fiction.

`enable_time_on_target: true` requires at least one mission. A disabled
configuration may retain a completely valid mission list so the same declared
world and plan can serve as an A/B negative control. Omitted or empty,
disabled configuration is inert. The root scenario validator rejects
feature-shaped unknown keys such as `indirect_fier`, `indrect_fire`,
`timeOnTargetMissions`, `enableTimeOnTarget`, `totPlan`, or a misplaced
`time_on_target_missions`; compact `enable_tot`/`totEnabled` forms also reject.
Separator/case normalization and a bounded
near-match check prevent a plausible typo from silently selecting the
disabled default. The repository's nine shipped unrelated historical
metadata keys remain outside this targeted Phase 111 strictness boundary.

### Production resolution and validation

One simulation-layer `TimeOnTargetMissionResolver` is the typed production
construction boundary. It consumes the validated configuration, initial force
roster, and exact Phase 109 `RuntimeLoadouts` product once, then emits
immutable combat-layer plan records into `IndirectFireEngine`. The combat
layer does not import `simulation.loadouts`, use `Any` as a type escape, build
a second loadout, or accept a definitions-only weapon map. Each plan retains
the attachment's source-equipment discriminator and runtime multiplier while
holding the exact lower-layer `Unit`, `WeaponInstance`, and `AmmoDefinition`
references required for execution.

Before returning a `SimulationContext`, construction resolves and validates:

- each target and battery ID against the exact initial production roster;
- all batteries in a mission belong to one side and the target belongs to a
  different scenario side;
- target and battery units are active;
- the configured target point lies within the loaded terrain bounds;
- `source_equipment_index` resolves one and only one `WeaponAttachment`, whose
  `WeaponInstance` and `AmmoDefinition` match the declared weapon and
  ammunition IDs;
- the weapon category is `HOWITZER`, `MORTAR`, or `ARTILLERY`;
- the weapon's effective target domains include the exact target unit's
  domain;
- ammunition is compatible with the weapon and the initial live magazine can
  satisfy the requested rounds;
- ammunition has a finite positive `blast_radius_m`; smoke, illumination, and
  any other non-damaging round are explicitly unsupported by the Phase 111
  target-effect boundary;
- the real initial horizontal battery-to-configured-target distance is at
  least the weapon's declared minimum range and no greater than its declared
  maximum range;
- weapon muzzle velocity or ammunition maximum speed supplies a finite
  positive physical speed bound; and
- `time_of_flight_s` is no shorter than the three-dimensional straight-line
  battery-to-configured-target distance divided by the greater valid
  projectile-speed bound.

`rounds_per_battery` means simultaneous initial rounds, one per represented
firing system. It may not exceed the exact attachment's
`runtime_system_multiplier`. A multiplier-one M109 therefore fires one round,
not several rounds at one instant. Phase 111 does not model multiple-round
simultaneous impact (MRSI); a future MRSI path would require per-shot fire
times, rate-of-fire spacing, and individual flight solutions.

An unknown or ambiguous attachment, friendly target, unsupported rocket or
other weapon category/domain, non-damaging or incompatible ammunition,
impossible range, insufficient initial ammunition, invalid timing, or
duplicate identity fails loading explicitly.
There is no 300 or 500 m/s fallback, missing-weapon skip, origin substitute, or
insertion-order truncation.

Across missions, the resolver sums requested rounds by exact attachment and
ammunition and rejects aggregate overbooking of the initial live magazine. It
also orders every fire assigned to one attachment and rejects authored gaps
shorter than the attachment's quantity-aware aggregate cooldown:
`WeaponInstance._cooldown_s * rounds_per_battery`. The runtime definition's
rate of fire already scales by `runtime_system_multiplier`; multiplying its
derived cooldown by the number of simultaneous rounds consumes exactly that
share of the aggregate firing rate instead of permitting squared throughput.
The due-fire check uses
`can_fire_timed(..., cooldown_multiplier=rounds_per_battery)` with the same
rule. Runtime depletion or cooldown caused through another authorized
consumer remains an explicit terminal rejection, not an implicit retry.

The immutable resolved plan records the declaration indices, attacker side,
target point and target unit, each exact attachment discriminator and runtime
multiplier, real planned firing position, scheduled fire time, predicted time
of flight, weapon/ammunition identity, and round count. Its canonical topology
fingerprint is part of checkpoint state.

### Timing, ordering, and exactly-once lifecycle

`SimulationEngine.step()` calls one public time-on-target update on every fixed
whole-second scenario tick after reinforcement, environment, logistics, and
scripted events, but before strategic movement, battle detection, or tactical
combat. Because declared fire and impact times are exact multiples of the
scenario's one cadence, no step crosses a milestone and no extra full engine
tick is inserted. Enabled and disabled populated controls therefore retain
identical clock, max-tick, environment, logistics, maintenance, recorder, and
other subsystem cadence. An event processed at the same boundary changes the
preconditions observed by time on target; a later event cannot be applied
before an earlier aligned fire. A planned mission is not dependent on an
active `BattleManager` battle.

One update processes every newly due milestone in canonical order:

`(scheduled_time_s, fire-before-impact, mission declaration index,
battery declaration index)`.

Equal-time milestones use their exact scheduled timestamp and process in the
declared canonical order. The terminal result also records the tick-end time,
which equals the scheduled milestone under the validated fixed cadence.

For each battery:

1. its lifecycle begins `pending`;
2. at the first update reaching its scheduled fire time, runtime preconditions
   are checked once;
3. a successful fire consumes the exact live ammunition, increments live
   maintenance-round state, records live cooldown at the scheduled fire time,
   generates impacts from the battery's current real position, and becomes
   `fired`; or
4. a failed precondition becomes one terminal `rejected` result with an exact
   reason and no ammunition or random draw.

The battery is never retried. Runtime rejection checks and reasons use this
fixed precedence:

- `battery_inactive`;
- `battery_moving`;
- `battery_displaced`;
- `weapon_inoperable`;
- `insufficient_ammunition`; or
- `weapon_cooldown`.

`battery_moving` applies when the exact weapon requires deployment and unit
speed exceeds the production battle threshold of 0.5 m/s. A lower-precedence
fault is not also reported.

`battery_displaced` means the current three-dimensional firing position no
longer exactly matches the immutable planned position. A changed position
invalidates the authored fire-control hang time; the runtime does not silently
reuse stale coordinates or recompute an unsourced solution.

At the update at `impact_time_s`, all stored fired-battery impacts
resolve together against the target unit's then-current position. The mission
becomes `completed` once, publishes one terminal result, and can never fire or
impact again. A target that moved out of the impact area can escape. A target
already inactive at impact remains unchanged, but the expended mission still
completes and exposes that outcome.

While any enabled mission using an attachment remains incomplete, the exact
`(unit_id, source_equipment_index, weapon_id)` attachment is reserved from
autonomous `BattleManager` selection. Other attachments on that unit remain
selectable. The reservation is released only after every declared mission
using the attachment completes; a rejected battery remains committed until
its common impact boundary closes the mission. A disabled plan reserves
nothing.

### Impact and unit outcome

The terminal effect reuses the existing production aggregate indirect-fire
abstraction, not a Phase 111 calibration. A public pure assessment accepts
impacts with their originating ammunition radii, prior cumulative near-impact
count, terrain modifier, casualty fraction, and destruction/disable
thresholds. The ordinary battle caller retains its current cumulative tracker
and terrain/skill modifier exactly. A scheduled mission supplies zero prior
hits and a neutral terrain modifier because it has no enclosing battle terrain
assessment:

- count each stored impact whose horizontal distance from the target unit is
  less than the positive blast radius of the ammunition that generated it;
- multiply near impacts by the existing `0.15` casualty fraction per impact,
  capped at one; and
- compare that fraction with the scenario's existing
  `destruction_threshold` and `disable_threshold`.

The inherited `0.15` scalar and threshold abstraction are not established by
the cited time-on-target doctrine and remain an explicit terminal-effect
fidelity debt. Phase 111 neither recalibrates them nor applies the legacy 50 m
fallback to scheduled ammunition. The scheduled path changes the exact
target's `UnitStatus` once and publishes the corresponding
`UnitDestroyedEvent` or `UnitDisabledEvent` after committing the transition.
It does not call or import the private
`BattleManager._apply_indirect_fire_result` helper.

Target-effect classification uses one fixed precedence. If the target status
before impact is not `ACTIVE`, the effect is `target_inactive`. Otherwise zero
near-target impacts means `missed`; a committed transition means `destroyed`
or `disabled`; and positive near-target impacts below both thresholds mean
`unchanged`. Terminal `target_status_before` and `target_status_after` values
are exact uppercase `UnitStatus.name` strings (`ACTIVE`, `DISABLED`,
`DESTROYED`, `SURRENDERED`, or `ROUTING`).

The target point may be an anticipated point distinct from the target unit's
initial position; exact co-location is not required. The target is the exact
configured unit only, and its position at impact controls the effect. Area
effects on other nearby units, collateral damage, suppression integration,
observer correction, counterbattery response, and target retasking are
non-goals.

### Observable results and failure behavior

A successful battery fire publishes:

- one existing `AmmoExpendedEvent` with unit, ammunition, and quantity after
  the exact live magazine commits; and
- one existing `ArtilleryFireEvent` with battery, target point, ammunition,
  and actual rounds.

Every due mission publishes exactly one `TimeOnTargetMissionEvent`, including:

- mission ID and attacker side;
- target unit and target ENU point;
- scheduled impact and tick-end processing times;
- ordered battery IDs, source-equipment indices, runtime multipliers,
  weapon/ammunition IDs, planned/actual firing positions, scheduled fire
  times, predicted times of flight, processing times, statuses, reasons,
  rounds fired, and generated impact counts;
- total generated and near-target impacts;
- mission outcome (`completed`, `partial`, or `rejected`); and
- target effect and target status before and after impact.

Battery `status` is exactly `fired` or `rejected` in a terminal event.
Successful batteries use an empty `reason`; rejected batteries use exactly one
precedence-defined reason, zero rounds, and zero impacts. Every position is a
three-number `[easting, northing, altitude]` JSON array, including the observed
position of a rejected battery. Times are finite seconds from scenario start.

A mission `outcome` is `completed` when every battery fired, `partial` when
some fired, and `rejected` when none fired. `target_effect` is exactly
`destroyed`, `disabled`, `unchanged`, `missed`, or `target_inactive`.
Target movement, an already inactive target, or zero near impacts does not
relabel a fully fired mission as rejected.

For each fired battery, event order is `AmmoExpendedEvent` then
`ArtilleryFireEvent`. At impact, any committed unit status event precedes the
one terminal mission event. Planned/actual firing positions and exact
attachment identity in the terminal event supply the evidence that the older
events cannot carry. A scheduled `UnitDestroyedEvent` or `UnitDisabledEvent`
uses `cause="time_on_target"`, the target's side, and `weapon_id=""`: a
heterogeneous simultaneous mission has no honest single-weapon attribution,
which remains complete in the ordered terminal battery results.
`attacker_side` intentionally matches the existing generic API side filter.
The recorder and `GET /api/runs/{run_id}/events` expose the complete result
without a bespoke endpoint when normal recorder and API storage retention are
enabled.

Observer exceptions occur after the resource, lifecycle, and target
transitions commit. Event dispatch collects and logs subscriber errors without
rolling back or making a mission retryable.

Configuration and reference errors fail scenario loading. Runtime
precondition failures are explicit terminal battery results; none are swallowed
as debug-only logs.

### State and checkpoint persistence

For configured time-on-target operation, `IndirectFireEngine` state contains:

- the immutable plan-topology fingerprint;
- enabled/disabled state;
- every mission lifecycle;
- every battery lifecycle, exact rejection reason, processed time, rounds
  fired, and generated impact positions;
- the latest observed live resource state for every planned attachment
  (ammunition by type, total and maintenance rounds, and last-fire time), plus
  the unit/equipment precondition snapshot stored with each transition;
- the terminal mission result needed to prevent duplicate effects; and
- a read-only mirror of the shared COMBAT generator state for direct-engine
  compatibility.

Lifecycle state has one authority in the engine. Live ammunition, cooldown,
maintenance, equipment condition, unit position, and unit status retain their
existing authorities in `WeaponInstance`, equipment, and `Unit`.

An indirect resource observation encodes `last_fire_time_s` as JSON `null` if
and only if the live `WeaponInstance` uses its canonical never-fired
`float("-inf")` sentinel. After any fire, the observation contains the exact
finite non-negative fire time. Positive infinity, negative infinity in an
observation, any other non-finite value, and a finite negative fire time
reject. Reconciliation maps staged live `-inf` to `null` before exact
comparison; `null` never means unknown or unchecked state.

Enabled mission and battery lifecycles begin `pending`. Disabled populated
plans use distinct pristine `dormant` mission and battery states, so a
disabled checkpoint remains valid after every authored time has passed.

`stage_state()` validates topology, exact IDs and ordering, finite values,
allowed transitions, rejection vocabulary and precedence, schedule chronology,
impact counts and ammunition IDs, pending/fired/rejected/completed
consistency, and dormant disabled-state pristineness without mutation. For an
enabled plan, every pending milestone must be strictly later than the
checkpoint clock: a milestone equal to elapsed time is already due and cannot
remain pending. A fired/rejected milestone may not be in its future, and a
completed mission's impact may not be in its future. Dormant plans are
explicitly exempt from enabled chronology and draw no random state.
Lifecycle `rounds_fired` is a non-boolean non-negative integer and a processed
time is the exact finite float emitted by the aligned schedule. Terminal
payload and COMBAT-mirror scalar equality is type-aware, so JSON booleans
cannot masquerade as integer counters.

Staging also reconciles context-owned checkpoint authorities:

- the indirect engine's COMBAT RNG mirror exactly equals the staged
  `RNGManager` COMBAT stream; only `RNGManager` commits it;
- every exact staged attachment's ammunition, total/maintenance rounds, and
  canonicalized last-fire state equal the engine's latest resource observation
  exactly, and each observation is internally consistent with its
  fired/rejected lifecycle history; the observation is initialized at load
  and refreshed after every scheduled precondition/result transition.
  Causally valid aggregate public live-fire transitions may bridge consecutive
  lifecycle observations or the last observation to the staged
  `WeaponInstance`, including before a pending scheduled fire. Every bridge
  must preserve ammunition topology, contain no ammunition increase, match
  ammunition depletion to total and maintenance round counters, carry one
  finite advancing last-fire time, satisfy quantity-aware cooldown from the
  preceding observation, occur no earlier than the latest preceding
  resource-bearing processed milestone, and occur no later than the staged
  checkpoint clock. Mission impact/release does not sample live weapon
  resources and therefore cannot retroactively become a resource-history
  lower bound;
- enabled plans reserve those attachments from other production fire until
  their last using mission completes. Reservation is enforced by the ordinary
  `BattleManager` selection boundary; it does not revoke the public
  `WeaponInstance` mutation authority. A valid pre-fire bridge therefore
  restores and the scheduled milestone deterministically observes the
  depletion/cooldown. Missing, future, nonadvancing, counter-inconsistent, or
  ammunition-increasing transitions and `fired+unspent` histories reject;
- the exact staged attachment topology, source-equipment identity, runtime
  multiplier, and unit identity still match the immutable plan;
  transition-time unit position/speed/status and equipment
  condition/operational snapshots must justify the recorded result, while a
  later legitimate movement, breakdown, or repair need not equal that
  historical snapshot; and
- a completed target transition is compatible with staged unit state:
  destroyed remains destroyed, disabled may remain disabled or later be
  destroyed, surrendered remains surrendered or is later destroyed, routing
  may rally or undergo a later transition, and an unchanged active target may
  undergo a later transition.

`WeaponInstance.reload()` has no production caller or typed Class V resupply
provenance. An ammunition increase on a planned attachment therefore remains
unsupported by this checkpoint boundary and rejects rather than being guessed
as a legitimate reload. Wiring live magazine replenishment and its persisted
authority remains part of REM-021; Phase 111 does not weaken corruption checks
to conceal that gap.

`SimulationContext.set_state()` stages indirect-fire state before mutating the
clock, RNG manager, units, morale, or live loadouts. It commits the staged
mission state only after the context's unit and weapon instances have restored.
A malformed indirect-fire checkpoint leaves the entire context unchanged.

A fresh runtime restored before firing, between firing and impact, or after
completion must continue with the same ordered events, impact points,
ammunition, cooldown, maintenance count, target state, engine state, and COMBAT
RNG as uninterrupted execution. Restore after completion cannot fire or apply
the mission again.

Phase 111 advances the exact engine checkpoint schema to version 111, so
version 110, future, boolean, null, and other malformed version values reject
before mutation. A versionless checkpoint cannot restore a runtime with
declared time-on-target missions, including a disabled populated plan whose
topology would otherwise be absent. Existing versionless compatibility remains
only for runtimes with no declared missions.

### Legacy component boundary

The stateless `TOTFirePlan`, `compute_tot_plan()`, and
`execute_tot_mission()` APIs are removed. Repository callers are tests only;
there is no compatibility reason to retain a second unsafe execution path.
Ordinary `fire_mission()` and non-time-on-target battle behavior remain public
and compatible. Existing artillery/ammunition event schemas do not pretend to
identify the source attachment; the terminal time-on-target event supplies
that identity. The complete aggregate assessment moves to the public pure
boundary without changing ordinary battle inputs or outcomes.

## Military and mathematical basis

- **Tier 1 / official doctrine:** U.S. Army,
  *TC 3-09.81, Field Artillery Manual Cannon Gunnery* (13 April 2016),
  paragraphs 5-40 through 5-41, p. 5-13, requires participating firing units
  to report READY and their individual time of flight, then derives each
  firing instant by subtracting that unit's time of flight from a common
  interval. Paragraphs 5-54 through 5-55, p. 5-17, report time of flight to
  the nearest whole second. Chapter 7 explains that real firing-table
  solutions depend on experimental trajectories plus weapon, ammunition,
  weather, material, elevation, and correction data:
  <https://rdl.train.army.mil/catalog-ws/view/100.ATSC/4BA86079-56B8-42E9-8F79-C340F08A9D39-1457034137314/tc3_09x81.pdf>.
- **Tier 1 / official joint service doctrine:** U.S. Army/U.S. Marine Corps,
  *ATP 3-21.90/MCTP 3-01D, Tactical Employment of Mortars* (9 October
  2019), Appendix A, paragraphs A-2 through A-6, pp. A-1 through A-2,
  defines time on target as the actual impact time, requires accurate firing
  unit and target locations plus weapon, ammunition, meteorological, and
  computational data, and describes automated transmission of firing
  solutions and hang times:
  <https://www.marines.mil/Portals/1/Publications/MCTP%203-01D.pdf>.
- **Tier 1 / official doctrine:** U.S. Army/U.S. Marine Corps,
  *ATTP 3-21.90/MCWP 3-15.2, Tactical Employment of Mortars* (4 April
  2011), paragraph 3-88, p. 3-18, says a schedule identifies the designated
  target, time on target, and rounds or duration, and requires unfired targets
  to be reported. This supports explicit schedules, finite ammunition, and
  observable non-fire results:
  <https://www.marines.mil/Portals/1/MCWP%203-15.2.pdf>.
- **Tier 1 / official doctrine:** U.S. Army,
  *FM 23-91, Mortar Gunnery* (1 March 2000), paragraphs 2-1 through 2-13,
  pp. 2-1 through 2-9, explains that firing data and time of flight depend on
  range, vertical interval, charge, elevation, weapon, ammunition lot,
  projectile properties, atmosphere, wind, and drag. It therefore contradicts
  treating range and one nominal muzzle velocity as a complete artillery
  solution:
  <https://www.marines.mil/portals/1/publications/fm%2023-91.pdf>.

No source found supports the old `2 * range / muzzle_velocity` formula or
independent Normal planning jitter with a two-second standard deviation.
Vacuum projectile equations reveal that the multiplier of two silently fixes
an elevation of 60 degrees while omitting drag and vertical interval; the
repository does not possess the firing-table inputs needed to make that a
general production model. `BallisticsEngine.compute_time_of_flight()` also
uses an unsourced linear drag multiplier and fabricated velocity fallbacks.

Phase 111 therefore models the doctrinal scheduling equation

`fire_time_i = common_impact_time - reported_time_of_flight_i`

and treats the reported time as explicit scenario fire-control data. It does
not claim to predict real M795, Excalibur, or mortar exterior ballistics.
Weapon/ammunition/charge-specific firing tables or a validated modified
point-mass inverse solver remain the honest route to future automatic
calculation.

## Non-goals and residual boundaries

- No automatic target selection, retargeting, observer call-for-fire workflow,
  or C2 latency.
- No firing-table catalog, charge selection, inverse trajectory solver,
  stochastic muzzle-velocity/time error, or calibration claim.
- No modeled shell entity between fire and impact; persisted impact points are
  the in-flight aggregate.
- No rocket-artillery time-on-target support.
- No effects on units other than the exact configured target.
- No repair of ordinary battle-route live Class V consumption; that adjacent
  authority gap must remain explicit rather than be silently absorbed into
  REM-012.
- No Phase 112 validation-suite, structural-test, analysis-tool, or scenario
  diagnostic work.

## Acceptance criteria

1. A strict real scenario configuration declares two exact batteries, one
   enemy unit and target point, exact source-equipment attachments,
   weapons/ammunition, individual times of flight, rounds, and a common impact
   time.
2. The simulation-layer resolver resolves declarations to the exact Phase 109
   `WeaponAttachment` objects and real initial firing positions, then injects
   lower-layer plan records; invalid or ambiguous attachment, identity, side,
   type/domain, ammunition, aggregate inventory, range, timing, count, and
   numeric data fail before a context returns.
3. The same production `SimulationEngine.step()` path fires the farther/longer
   hang-time battery first, consumes each live magazine exactly once, stores
   impacts, and resolves one common impact outcome without calling a private
   test helper. The fixed cadence lands on each whole-second milestone without
   extra engine ticks or evaluating historical fire times against later state.
4. Enabled-versus-disabled and populated-versus-empty same-seed controls prove
   no hidden second gate, no disabled ammunition/event/target effect, and no
   disabled or rejected COMBAT RNG consumption.
5. Extra ticks produce no additional fire, ammunition, maintenance, cooldown,
   impact, target transition, terminal event, or RNG movement attributable to
   the completed mission.
6. Runtime inactive, moving, displaced, inoperable, depleted, and cooldown
   controls produce the precedence-defined one-time rejection with no random
   draw or partial resource mutation.
7. A fixed-seed mission changes the exact target status while the otherwise
   identical disabled control does not.
8. A real battle selection proves the exact attachment is reserved, unrelated
   attachments remain eligible, and reservation releases only after every
   using mission completes.
9. Recorder and real HTTP API event retrieval expose the complete exact
   mission payload and side filter despite a deliberately throwing observer.
10. Same-seed fresh runs match across ordered events, impacts, unit/loadout
   state, indirect-fire state, and COMBAT RNG.
11. Same-time shared-attachment processing asserts the follow-on fire events
    occur before the earlier mission's impact/status/terminal events, with
    exact unit-status attribution.
12. Fresh checkpoint continuation before fire, after a causal pre-fire public
    resource mutation, between fire and impact, through a shared attachment,
    and after completion is exact; a disabled populated plan restores after
    its authored times. Corrupt topology/lifecycle/timing (including a pending
    milestone equal to elapsed time), null/non-finite sentinel boundaries,
    ambiguous attachment/ammunition topology, quantity-aware cooldown,
    terminal-target regression, and engine-versus-live-state/RNG
    contradictions reject atomically.
13. Existing ordinary indirect-fire behavior, including terrain modifiers and
    cumulative hit history, remains green; the legacy
    stateless time-on-target path is absent, relevant data validation reports
    zero errors/warnings, and the exact repository Python Ruff command is
    clean.

## Completion evidence matrix

| Stage | Required Phase 111 evidence |
|---|---|
| Declared | Strict nested scenario models and explicit supported/unsupported boundary |
| Loaded | Real YAML and API-inline configuration resolve exact target, batteries, source-equipment attachments, positions, ammunition, and schedule |
| Wired | `SimulationEngine.step()` invokes the engine at every resolution before autonomous combat |
| Enabled | Same declared plan enabled/disabled controls plus omitted/empty controls |
| Exercised | Real two-battery mission crosses distinct aligned fire times and one impact time through fixed-cadence production steps; exact-pair reservation and release are behavioral |
| Outcome-affecting | Exact live magazines/cooldowns/maintenance and exact target status diverge from the disabled control |
| Persisted/exposed | Atomic fresh checkpoint continuation plus recorder and real API event retrieval |

Design approval alone does not establish implementation completeness. The
verified matrix, fresh production evidence, and accepted postmortem establish
the Phase 111 complete status recorded above.

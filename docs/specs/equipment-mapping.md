# Equipment Mapping and Runtime Loadout Contract

## Purpose and scope

Phase 109 closes REM-010 by making equipment-name resolution a strict,
typed production contract. Unit-catalog `WEAPON` and `SENSOR` entries must
resolve through one runtime-owned boundary to a typed attachment, store, or
non-runtime outcome, or scenario loading must fail with an explicit reason. A
validation helper may consume that boundary, but it does not own production
mapping or construction.

This contract covers:

- the central weapon and sensor mapping registry;
- scenario-local `weapon_assignments` compatibility overlays;
- initial, reinforcement, and checkpoint-reconstruction loadout construction;
- semantic and catalog validation for every built-in unit;
- the two catalog units that currently have no sensor entry; and
- the Phase 109 portion of the repository Python-lint baseline.

## Requirements

### Typed mapping registry

1. Mapping declarations are an ordered sequence of immutable typed records,
   not a dictionary literal. The registry rejects a duplicate
   `(equipment category, exact equipment name)` before constructing any lookup
   index, even when both targets are equal.
2. Equipment names and target IDs are non-empty, trimmed, case-sensitive
   values. Lookup never guesses, normalizes, or silently falls back.
3. Records form a discriminated union with two separate axes. Every record has
   exactly one disposition: live attachment, carried store, accepted
   non-runtime equipment, or unsupported equipment that must fail if
   reachable. Attachment/store records also declare one reference kind:
   - an exact or variant reference names the represented catalog definition;
   - a functional analogue names its semantic constraints, explicit allowed
     target set, rationale, and source.
   Non-runtime and unsupported records carry a reason and no reference kind or
   catalog target. Disposition-specific fields cannot be mixed. Weapon
   dispositions distinguish a live launcher/weapon attachment from carried
   ammunition and from equipment outside the modeled runtime boundary.
4. A supported weapon target must exist in the effective weapon catalog,
   parse to the declared `WeaponCategory`, and resolve at least one compatible
   ammunition definition. Where the record constrains guidance, ammunition
   role, bore/caliber semantics, or target domain, the definition must satisfy
   those constraints. Every declared compatible ammunition reference must
   resolve; one valid entry never hides another missing or incompatible one.
5. A supported sensor target must exist in the effective sensor catalog,
   parse to the declared `SensorType`, and satisfy the record's detection
   domain constraints.
6. A functional analogue may simplify within the same modeled role; it is not
   an assertion that two systems have identical physical performance. A
   weapon, sensor, effector, structure, navigation device, protection item, or
   utility item may not be mapped across unrelated roles merely to produce a
   live attachment.
7. Equipment authored under the wrong category is corrected in the unit data.
   EW jammers, navigation sets, breaching tools, mine detectors without a
   modeled detection interface, flight-deck/bomb-bay structures, blades, and
   protective shields do not acquire synthetic direct-fire or surveillance
   capability.
8. A launcher and its separately listed munition/store do not each create a
   complete launcher with a fresh magazine. A live-attachment record creates
   exactly one `WeaponInstance`. A store record names an `ammo_id` rather than
   a `weapon_id`, names the compatible attachment target or targets, resolves
   that ammunition definition, and requires one of those attachments on the
   same unit; it creates no second launcher and does not independently credit
   another magazine. A non-runtime record is retained as equipment with an
   explicit modeled-boundary reason and creates no attachment.
9. Scenario-local `weapon_assignments` pass through the same catalog and
   semantic validation. A reachable assignment key must name declared weapon
   equipment, its target must be loadable, and it may not contradict the
   registry's identity/role contract. Stale, unknown, or semantically
   incompatible overrides fail preflight.
10. Duplicate keys in the central source and in a scenario's
    `weapon_assignments` must be rejected before last-write-wins behavior can
    occur.
11. Explicit source-system multiplicity is part of the mapping contract. A
    record declares source and target system counts, derives one positive
    integral runtime multiplier, and rejects contradictory declarations.
    Runtime construction scales cadence, magazine capacity, and barrel life
    exactly once. Specialized aggregate routes fire
    `burst_size * runtime_system_multiplier` rounds or missiles per synchronized
    salvo and multiply the already scaled cooldown by the same runtime
    multiplier; rate of fire is never reused as salvo quantity. The ordered
    resolution topology and checkpoint fingerprint expose all three counts.

### Runtime loadout ownership

1. `stochastic_warfare.simulation` owns a public, typed
   `RuntimeLoadoutBuilder` and typed result/attachment structures. The builder
   receives concrete `WeaponLoader`, `AmmoLoader`, `SensorLoader`, an immutable
   mapping of effective `UnitDefinition` objects, effective `EraConfig`, typed
   assignment overrides, the reachable initial/reinforcement unit types, and
   the immutable registry. Unit definitions are the authoritative policy and
   authored-topology lookup for a runtime unit's `unit_type`; callers cannot
   infer sensor policy from the already-flattened `EquipmentItem` list.
2. `ScenarioLoader` constructs one builder before force creation, preflights
   every reachable initial and reinforcement unit definition, and retains the
   exact object on `SimulationContext`. Initial forces, arriving
   reinforcements, and checkpoint-only reconstructed units use that same
   boundary.
3. The simplified validation runner and the static data validator are
   consumers of the production registry/builder. Production code does not
   import or invoke a private validation-runner mapping or assignment helper.
4. Every output contains an entry for every input unit ID, including an
   intentionally empty weapon or sensor list. Duplicate or empty unit IDs
   reject before output is committed.
5. A declared weapon or sensor that is unmapped, explicitly unsupported,
   absent from the effective catalog, incompatible with its semantic record,
   or missing usable ammunition raises a contextual error naming the unit,
   equipment, and failed reference. No such condition is skipped or logged as
   success.
6. Explicit store/non-runtime dispositions are not silent skips: they are
   validated typed mapping outcomes. Their equipment remains on the unit, but
   the result records that no live weapon attachment was constructed.
7. Each `WeaponInstance` and `SensorInstance` remains linked to the exact
   `EquipmentItem` on its owning unit. Separate units receive independent live
   instances and ammunition state.
   Typed `WeaponAttachment` and `RuntimeLoadouts` use immutable tuples, expose
   the source equipment explicitly, and include an ordered
   `EquipmentResolution` for every mapped weapon, sensor, store, and
   non-runtime item.
8. Weapon ordering is deterministic with the exact key
   `(-max_range_m, source_equipment_index, weapon_id)`. Sensor ordering follows
   source equipment order. Construction consumes no RNG and reads no wall
   clock.
9. Era capability gates remain part of the same atomic build. A gate or
   mapping failure leaves initial loading unsuccessful, a reinforcement wave
   pending and uncommitted, and checkpoint restore unmodified.
10. One public authoritative `SensorType -> SignatureDomain` function is
    consumed by `DetectionEngine.check_detection()`, `SensorSuite`, and the
    builder. Sensor-domain validation follows that production dispatch, not an
    unconsumed metadata field. Authored `detects_domain` metadata must agree
    with it; an unhandled sensor type or disagreement fails validation.
11. Global registry construction validates duplicate keys and record-shape
    invariants without demanding every historical target from one era's
    loader. A scenario builder validates only records reachable from its
    initial and reinforcement definitions against that effective catalog.
    Static data validation repeats the same construction for modern and every
    historical era so all 184 unit definitions are covered.

### Explicit no-sensor classification

1. Unit definitions declare a typed sensor policy. The normal policy requires
   at least one `SENSOR` equipment entry; an intentionally sensorless unit
   requires an explicit `intentionally_none` disposition and reason.
2. `civilian_noncombatant` is explicitly sensorless and receives no invented
   surveillance capability.
3. `insurgent_squad` is an armed human unit and receives an explicit visual
   observation sensor rather than retaining an unproven sensorless
   classification.
4. Contradictory policy/data combinations fail unit-catalog validation.

### Phase 115 targeting bindings

Phase 115 extends the same production builder without creating another mapping
owner. Every live weapon and sensor attachment now carries its exact canonical
source-equipment index, modeled role, allowed domains, and compatible source
indexes into tactical targeting. Initial, reinforcement, and checkpoint-only
construction must reproduce those bindings exactly; duplicate names, repeated
roles, and reordered source equipment cannot pass by list-position
coincidence. Weapon attachment order remains
`(-max_range_m, source_equipment_index, weapon_id)`, while sensor bindings
retain source order.

Role compatibility is a total upper-bound policy, not a proxy for the exact
catalog definition. The policy must admit the shooter role and target domain,
the selected mapped sensor must name the selected weapon source index, and the
attached weapon definition must independently admit the target domain. This
last gate is important for shared cross-era role profiles: the strict Salamis
production regression accepts ancient projectile/melee attachments against
their authored naval targets and rejects an aerial control without widening
the catalog definitions.

The current mapping can associate any same-unit weapon and director that pass
the exact role/domain policy because the catalog has no authored physical
mount/director association. That narrower topology deficit is REM-042 / Phase
129; Phase 115 does not infer it from equipment names or claim that compatible
roles prove a physical connection.

## Interfaces and dependencies

The runtime boundary lives in `simulation/` because it composes typed entity,
combat, detection, era, and calibration inputs. Moving it into `entities/`
would reverse the documented dependency direction. Domain engines continue to
consume the existing context weapon and sensor maps; Phase 109 changes their
construction and typing, not their combat or detection algorithms.

`EquipmentEntry.weapon_ref` is currently unused and no catalog entry declares
it. Phase 109 removes the dead field so it cannot become a second, silently
ignored ownership path.

## Production trace

`unit/scenario YAML -> typed UnitDefinition and CalibrationSchema -> effective
catalog loaders -> EquipmentMappingRegistry -> RuntimeLoadoutBuilder ->
RuntimeLoadouts -> SimulationContext -> battle/detection -> recorder/API and
checkpoint`

| Stage | Required Phase 109 evidence |
|---|---|
| Declared | A discriminated union of immutable attachment/store/non-runtime/unsupported records, typed sensor policy, builder inputs, result, resolution, and attachment types; invalid combinations are unrepresentable or reject |
| Loaded | `ScenarioLoader` validates the effective registry, catalogs, unit equipment, and scenario overrides |
| Wired | One injected builder serves initial units, reinforcements, and fresh checkpoint reconstruction; validation code only consumes it |
| Enabled | N/A for optional enablement because authored weapon/sensor loadouts are mandatory; era feature gates and unsupported records remain negative controls |
| Exercised | Production scenarios reach corrected weapons and sensors; unsupported/missing/semantic failures reject atomically |
| Outcome-affecting | Controlled production runs show corrected equipment changes detection, firing/ammunition, event, or battle state while removed fake capability cannot act |
| Persisted/exposed | Checkpoint state records the builder fingerprint and preserves exact corrected attachment identity, order, equipment links, mutable state, and deterministic continuation; the existing API ammunition percentage is repaired and exercised against the typed attachment shape |

## State and persistence

The registry and builder are immutable scenario/catalog topology and hold no
mutable simulation state. Live weapon, ammunition, sensor, and linked
equipment state continues to use the current checkpoint contract. The
checkpoint records a canonical builder fingerprint covering ordered registry
records reachable from the scenario, effective unit equipment and sensor
policies, referenced weapon/ammunition/sensor definitions, era gates, and
typed assignment overrides. It also records the transparent ordered
per-unit resolution topology, including store and non-runtime decisions. A
restored runtime rebuilds with the retained builder, never checkpoint-supplied
assignments, and compares the fingerprint and topology before mutating clock,
RNG, calibration, roster, or live instances. Checkpoint calibration must equal
the already validated effective scenario configuration; restore never adopts
different assignments. A changed mapping/catalog envelope or assignment
contract is an incompatible restore. The simulation checkpoint schema version
advances from 108 to 109 for these required fields; the existing explicit
legacy-without-version migration path remains separate.

The fingerprint is SHA-256 over canonical JSON with lexically ordered mapping
keys and stable source equipment order. Python `hash()` and unordered set/dict
iteration are forbidden.

## Configuration and failures

- Mapping, catalog, semantic, era-gate, and sensor-policy checks are strict and
  complete before initial context publication.
- Reinforcement and restore callers preserve their existing rollback/atomicity
  guarantees.
- Unsupported means an explicit exception at the production boundary, never
  an empty attachment presented as success.
- Built-in scenario data must finish Phase 109 without unsupported reachable
  weapon/sensor equipment, mapping errors, or unclassified sensor omissions.
- The validator reports exact counts and distinguishes catalog-validation
  findings from unrelated logger warnings.

## Stochastic and military basis

Loadout construction is deterministic and consumes no RNG stream. Phase 109
does not tune weapon or sensor performance and does not add a physical
parameter merely to clear validation. Exact definitions already present in the
catalog are preferred. A same-role analogue must be labeled as an abstraction,
constrained by typed semantics, and supported by the Phase 109 military-data
review; otherwise the equipment is corrected to its noncombat category or
fails as unsupported.

## Verification plan

1. Preserve the clean phase-start revision and capture formal red evidence for
   six duplicate mapping keys, 22 mapping-error occurrences, two no-sensor
   warnings, B-52H CSRL-to-Stinger overwrite, EA-18G jammer-to-Vulcan
   capability, and the SA-6 missing radar.
2. Add Phase 109 tests that fail on the current source for duplicate
   declarations, duplicate scenario assignment keys, missing targets/ammo,
   semantic mismatches, launcher/store duplication, unsupported records, and
   contradictory sensor policy.
3. Prove exact per-unit initial loadouts through `ScenarioLoader`; aggregate
   armed/sensored counts are diagnostic only.
4. Prove corrected detection and/or firing state through the production
   battle path, with a removed-fake-capability negative control. Production
   multi-tick controls must also prove that explicit launcher, gun, torpedo,
   and depth-charge multiplicity changes engine-call and ammunition totals
   without squaring or collapsing cadence.
5. Repeat reinforcement atomicity and live fire/ammunition tests through the
   injected builder.
6. Repeat fresh-runtime checkpoint reconstruction and deterministic
   continuation, including attachment ordering and equipment object links.
7. Run full unit/scenario data validation and require zero Phase 109 errors
   and zero unclassified sensor warnings.
8. Store pre-implementation semantic outcomes for affected representative
   scenarios, then run the same seeds after implementation and explain every
   difference.
9. Run focused loadout/data tests, API ammunition-exposure tests, the default
   backend suite, repository-wide Ruff including `scripts/`, strict
   documentation, and `git diff --check`.
10. Apply `$validate-conventions`, `$audit-determinism`, `$validate-data`,
    `$evaluate-scenarios`, and `$simplify`, followed by `$update-docs`,
    `$cross-doc-audit`, and `$postmortem`.

The frontend, terrain, slow, and benchmark suites are not automatically
applicable because this phase changes no frontend contract, terrain behavior,
stochastic model, or performance-sensitive simulation loop. Any discovered
API/frame change or measurable scenario/performance effect makes its
corresponding boundary applicable and must be recorded.

## Acceptance criteria

Phase 109 is acceptable only when:

1. no equipment mapping can be silently overwritten or skipped;
2. the tracked 22 occurrences resolve to correct typed targets or corrected
   non-weapon/sensor data, and both no-sensor cases have explicit policy;
3. known unrelated proxy capability is removed and same-role abstractions are
   explicit and semantically validated;
4. launcher-plus-store catalog entries create one intended launcher topology,
   not duplicate full magazines;
5. initial, dynamic, and reconstructed units use one runtime-owned typed
   builder with exact live-object and ordering behavior;
6. production behavior proves corrected detection/fire outcomes, the absence
   of former fake capability, and exact multi-tick ammunition/engine-call
   effects for explicitly counted weapon systems;
7. checkpoint continuation and deterministic construction remain exact;
8. the API exposes ammunition percentage from typed production attachments,
   and full relevant data validation and repository-wide Python Ruff are green;
9. REM-010's evidence matrix is complete with every N/A justified; and
10. the Phase 109 postmortem finds no papered-over or untracked blocker.

## Non-goals and accepted limitations

- No weapon/sensor performance calibration, force-composition tuning, or
  historical outcome fitting.
- No new EW, mine-detection, breaching, carrier-air-operations, navigation, or
  UAV-spotting mechanic.
- No Phase 109 claim that equipment-store counts are a complete live
  ammunition logistics model; REM-021 retains live-store authority and
  resupply synchronization.
- No repair of commander-profile validation, analysis-tool trust, morale
  ownership, era override execution, or logistics live-store synchronization.
- Same-role functional analogues remain bounded abstractions rather than
  claims of exact historical identity.
- Aggregation/disaggregation loadout reconstruction remains REM-016.

## Military-data decisions

The Phase 109 source review establishes these classifications:

- AN/ALQ-99, AN/ALQ-165, and AN/ALQ-167 are EW
  jamming/countermeasure effectors, not guns or general surveillance sensors;
  without a Phase 109 EW attachment contract they remain explicit non-runtime
  equipment
  ([NAVAIR ALQ-99](https://www.navair.navy.mil/product/ALQ-99-Tactical-Jamming-System),
  [NAVAIR IDECM](https://www.navair.navy.mil/product/Integrated-Defensive-Electronic-Countermeasures-IDECM)).
- AN/ALR-67 is a passive radar-warning receiver. An ESM target is permitted
  only as a labeled same-role abstraction; a laser-warning or active-radar
  identity is not
  ([NAVAIR ALR-67](https://www.navair.navy.mil/node/12551)).
- AN/AAQ-28 LITENING is a genuine EO/IR targeting sensor. A catalog EO/IR
  targeting pod may be used as a constrained same-role analogue without
  claiming unimplemented laser-designation behavior
  ([USAF LITENING fact sheet](https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104571/litening-advance-targeting/)).
- GPS/INS is navigation, not target detection
  ([NAVAIR EGI](https://www.navair.navy.mil/node/10896)).
- Mine detectors, Bangalore torpedoes, MICLIC, and D9 blades/rippers are
  specialized countermine or mobility tools/effectors, not battlefield search
  radar or rifles. They remain non-runtime under this phase
  ([ATP 3-21.8 Appendix H](https://www.benning.army.mil/Infantry/DoctrineSupplement/ATP3-21.8/appendix_h/ObstacleReduction/ReduceaMinefield/index.html),
  [Army demolition systems](https://www.cpeae.army.mil/Project-Offices/PM-CCS/Organizations/PdD-Demolitions-Countermeasures/Products/Demolition-Systems/)).
- A flight deck and bare bomb-bay structure are facilities, while the B-52
  CSRL is a live carriage/launcher attachment. The latter may use the generic
  bomb-rack abstraction but never an air-defense missile
  ([AFGSC CSRL](https://www.afgsc.af.mil/News/Article-Display/Article/629758/upgrade-gives-b-52-more-teeth/)).
- Javelin's reusable CLU and its missile round form one system attachment plus
  a store; they are not two launchers
  ([U.S. Army Javelin](https://history.redstone.army.mil/miss-javelin.html)).

Any remaining non-exact mapping must be labeled and constrained to the same
modeled role. If that cannot be defended without new physical data, the entry
is corrected to a noncombat category or marked unsupported; it is not silently
approximated.

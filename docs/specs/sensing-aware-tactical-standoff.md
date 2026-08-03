# Sensing-Aware Tactical Standoff

**Status:** Accepted and complete in Phase 115

**Owner:** Phase 115 / REM-028

> **Superseded checkpoint boundary:** This document records Phase 115's
> accepted format-115 behavior and its then-open REM-029 exclusion. The Phase
> 116 implementation advances the current engine to format 116 and restores
> exact roster-backed contacts and bounded current witnesses; Phase 116 passed
> postmortem and closed REM-029. The Phase 115 statements below remain
> historical evidence, not current-format limitations.

## Purpose and scope

At the Phase 115 baseline, tactical movement treated 80 percent of a live
weapon's catalog maximum range as sufficient reason to stop advancing toward
the nearest real enemy. That branch did not require an owner-side observation,
a current contact, a usable fire-control path, or the weapon's effective
engagement range. Phase 115 replaces that rule with one typed targeting
interval shared by movement and engagement. Environment, concealment, and
stochastic FOW update once per simulation tactical interval; RNG-free battle
pictures are then keyed by exact engine tick, battle, and shooter.

The observable capability is narrow and exact: an automatically advancing
unit may hold for weapon standoff only when the runtime has selected a real,
current hostile contact and a live weapon/fire-control combination that can
engage it at the current distance. The same decision must govern subsequent
engagement eligibility in that tick. Explicit scenario-authored, defensive,
emplaced, and unreleased-wave holds remain separate earlier decisions.

This contract applies to the authoritative
`SimulationRuntimeFactory -> PreparedScenario.build -> ScenarioLoader ->
SimulationEngine.step -> BattleManager.execute_tick` path, including initial
units and production reinforcements. A private helper call, source lookup, or
constructed sensor is not completion evidence.

## Military and data basis

The contract distinguishes three ranges instead of treating ballistic maximum
as tactically usable range:

- The U.S. Marine Corps' *MCTP 3-01C, Machine Guns and Machine Gun Gunnery*,
  page 1-6, distinguishes maximum range, maximum effective range, and maximum
  usable range. It defines usable direct-fire range as visible distance still
  bounded by maximum effective range and notes that observation or optics can
  change that bound. This is Tier 1 doctrine and supports the limiting
  relationship, not a universal numeric multiplier:
  <https://www.marines.mil/Portals/1/Publications/MCTP%203-01C.pdf?ver=5Cn2XHSyhe0BsKNItp6ssw%3D%3D>.
- *FM 3-21.8, The Infantry Rifle Platoon and Squad*, paragraph 2-63/page 2-12,
  defines target acquisition as detection, identification, and location in
  sufficient detail for effective weapon employment. This is Tier 1 doctrine
  and supports requiring an actual target contact before an automatic firing
  standoff:
  <https://www.marines.mil/Portals/1/Publications/FM%203-21.8%20%20The%20Infantry%20Rifle%20Platoon%20and%20Squad_2.pdf>.
- U.S. Navy *Landing Operations Doctrine, USN, FTP-167*, section 532(a),
  describes direct fire as requiring a visible target and obtains range from
  radar, a rangefinder, or a bounded plotting method. This Tier 1 historical
  doctrine supports a distinct director/rangefinding path for naval gunfire;
  it does not authorize a generic search contact as fire control:
  <https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/l/landing-operations-doctrine-usn-ftp-167.html>.
- The U.S. Navy describes AN/SPS-73 as a surface-search/navigation system that
  produces contact range and bearing, while AEGIS integrates search, track,
  missile guidance, and weapon control. These Tier 1 official system
  descriptions support retaining the catalog's search-versus-fire-control
  role distinction rather than inferring fire control from `SensorType.RADAR`:
  <https://www.navy.mil/Resources/Fact-Files/Display-FactFiles/Article/2167987/ansps-73v12-radar-set/>
  and
  <https://www.navy.mil/Resources/Fact-Files/Display-FactFiles/Article/2166739/aegis-weapon-system/>.

No new sensor, weapon, or visibility range may be calibrated in this phase.
Physical range comes from `WeaponDefinition.max_range_m`. An effective range is
authored only when `WeaponDefinition.effective_range_m > 0`; the existing
`get_effective_range()` fallback is not evidence. Across all 244 weapon YAMLs,
97 author a positive effective range and 147 omit it; in the 126-file base
catalog the corresponding counts are 51 and 75. The omissions are classified
as `LEGACY_DERIVED_80_PERCENT_OF_MAX`, never silently relabeled as authored.
The phase-start baseline may report that legacy value, but no format-115
runtime variant may use it to authorize automatic standoff.

An authored effective range is a predictive-hold ceiling, not a contact. A
weapon without one may still fire when the shared decision proves a current
target-acquisition/fire-control solution and every ordinary engagement gate;
it simply contributes `0.0 m` of predictive automatic standoff. Sensor limits
come from the exact live mapped instance after equipment-condition degradation
and current environmental effects. Scenario/weather visibility remains an
independent bound.

## Typed runtime contract

### Configuration

`CalibrationSchema` declares:

```text
enable_sensing_aware_standoff: bool = true
```

The field is strict, loader-owned, included in the flattened runtime
calibration and configuration fingerprint, and persisted through the existing
checkpoint calibration boundary.

- `true` enables automatic hold only when the targeting decision authorizes
  it.
- `false` sets the authorized automatic standoff range to `0.0 m`. It does not
  restore the defective catalog-maximum rule and does not disable correct
  targeting constraints for combat.
- The flag does not alter authored, defensive, emplaced, reserve, or wave
  holds. Those branches remain earlier and retain their existing exact
  movement reasons.

### Runtime loadout bindings

`RuntimeLoadoutBuilder` must publish immutable live bindings rather than make
the tactical loop recover roles from names or zip parallel collections:

```text
WeaponAttachment
  live WeaponInstance
  immutable ammunition definitions
  source EquipmentItem and source index
  WeaponModeledRole
  mapping/reference provenance already required by Phase 109

SensorAttachment
  live SensorInstance
  source EquipmentItem and source index
  SensorModeledRole
  mapping-authored compatible WeaponModeledRole tuple
  builder-resolved compatible weapon source-index tuple
  mapping/reference provenance already required by Phase 109
```

`RuntimeLoadouts` and `SimulationContext` retain both the typed sensor
attachments and the compatibility `unit_sensors` projection needed by existing
detection consumers. Their unit-ID sets, source-object identity, target IDs,
and order must agree exactly. Initial loading, reinforcement registration,
checkpoint reconstruction, and rollback publish them atomically.

Fire-control compatibility is attachment-to-attachment, not unit-wide.
`SensorAttachmentMapping` explicitly declares the weapon roles supported by
that exact equipment mapping; the builder resolves those roles to exact live
weapon source indexes on the same unit and publishes the immutable tuple.
Local fire control requires the selected weapon source index to occur in that
tuple. Contact/search-only mappings declare an empty tuple. No. 7 Dial Sight
and Panoramic Sight declare only `FIELD_ARTILLERY`; because that weapon role is
standoff-ineligible, neither can direct another organic weapon on a mixed
loadout. Barr & Stroud and Zeiss declare only `NAVAL_GUNFIRE`. Mapping/data
validation rejects missing, duplicate, unknown, source-inconsistent, or
semantically incompatible role/index bindings.

The WW1 mapping that currently collapses field binoculars, naval rangefinders,
and artillery sights into one observation role must be split. Field Binoculars
remain observation-only; Barr & Stroud and Zeiss rangefinders use the applicable
naval visual-director role; No. 7 Dial Sight and Panoramic Sight use the
applicable ground visual-sight role. Existing mapped ranges remain unchanged.

Those assignments are equipment-specific and source-bounded, not inferred from
their names. The 1916 Admiralty *Handbook for Barr & Stroud Naval Range-finders
and Mountings* includes gun-control-tower mountings, while the Dreadnought
Project's primary-manual transcription describes a Barr & Stroud FQ2 sending
range/bearing to the transmitting station; USNI independently documents the
family's placement in fire-control directors. These Tier 2/primary-document
routes support `NAVAL_VISUAL_DIRECTOR`, but not the functional analogue's
3,000 m cap as historical performance:
<https://dreadnoughtproject.org/docs/notes/ADM_186_205.php>,
<https://www.dreadnoughtproject.org/tech/essays/FireControl/ArgoAimCorrector/>,
and
<https://www.usni.org/magazines/naval-history-magazine/2024/february/barr-and-stroud-rangefinder>.
ZEISS's corporate history documents military stereoscopic rangefinders from
1895 and early naval optics, while NavWeaps' technical history documents Zeiss
shipboard ranges entering the analog fire-control solution; together they
support the same role classification without sourcing this catalog cap:
<https://www.zeiss.de/corporate/ueber-zeiss/vergangenheit/geschichte/technische-meilensteine/verteidigungssysteme.html>
and <https://www.navweaps.com/index_tech/tech-078.php>.

For ground sights, Collections WA identifies the British No. 7 on WW1
18-pounders and its direct/indirect laying function, and the Australian War
Memorial identifies the Rbl.F.16 panoramic sight as WW1 equipment for light
field guns/howitzers. These Tier 2 museum records support
`GROUND_VISUAL_SIGHT`; the indirect-fire weapon-role exclusion still prevents
either sight from authorizing tactical direct-fire standoff:
<https://collectionswa.net.au/items/95201dcb-848a-4355-99a9-1777437226de>
and <https://www.awm.gov.au/collection/C311429>.

The Hezbollah coastal battery now declares a distinct composite `Coastal
Missile Targeting Network` attachment, modeled as generic
`FIRE_CONTROL_RADAR` and compatible only with `ANTI_SHIP_MISSILE`; it does not
promote the former standalone `Coastal Surveillance Radar` search identity
into fire control. The U.S. Office of Naval Intelligence identifies the
C-802/Noor as a mobile coastal-defense missile system, while a contemporaneous
USNI analysis reports that the INS Hanit attack apparently used the Lebanese
coastal-surveillance system as a targeting network. NAVSEA's public radar
descriptions independently preserve the functional distinction between
surveillance and fire-control radars used with gun and missile systems:
<https://www.oni.navy.mil/Portals/12/Intel%20agencies/iran/Iran%20022217SP.pdf>,
<https://www.usni.org/magazines/proceedings/2006/october/world-naval-developments-network-centric-warfare-middle-east>,
and
<https://www.navsea.navy.mil/Home/Warfare-Centers/NSWC-Port-Hueneme/What-We-Do/In-Service-Engineering/Radars/>.
The mapping's 60,000 m reach and 360-degree field of view remain the catalog's
existing `ground_search_radar` functional analogue, not a sourced claim about
historical C-802 targeting performance.

The FOW fusion repair retains the existing generic position-error model rather
than treating a zero-range detection as perfect knowledge. Kalman's original
linear-filter formulation derives the estimate and covariance recursion from
the state/measurement covariance model, and NASA's discrete navigation-filter
formulation makes the required innovation inverse explicit as
`(H P H^T + R)^-1` and uses the Joseph covariance update for numerical
stability:
<https://asmedigitalcollection.asme.org/fluidsengineering/article/82/1/35/397706/A-New-Approach-to-Linear-Filtering-and>
and
<https://ntrs.nasa.gov/api/citations/20180002039/downloads/20180002039.pdf>.
A peer-reviewed treatment of noise-free measurements separately notes that the
ordinary Kalman formulation requires nonsingular measurement-noise covariance
and needs a different estimator when a measurement is genuinely exact:
<https://doi.org/10.1002/oca.690>.

Phase 115 therefore requires finite, strictly positive fusion uncertainty and
retains the subsystem's existing one-metre generic numerical minimum. That
minimum is not a claim about any catalog sensor's historical accuracy. The
missing sensor-specific range/bearing error covariance and provenance is a
separate fidelity deficit; Phase 115 does not tune the minimum to produce a
preferred detection, movement, or engagement outcome. REM-044 / Phase 131 owns
that sourced covariance plus detached predictive-update transaction.

Sensor roles are classified explicitly as observation/search only or capable
of supplying a local fire-control solution. Weapon roles are classified as
organic direct aim, compatible-director required, or unsupported for automatic
tactical standoff. Field artillery, mortar, and rocket-artillery attachments
remain owned by the indirect-fire action path and cannot create a direct-fire
automatic standoff. There is no permissive unknown-role fallback.

The following tables are the total policy, not examples. Production constants
must contain every current enum member exactly once and import-time/data tests
must fail on a missing, extra, or multiply classified role.

| Weapon standoff class | Exact `WeaponModeledRole` members |
|---|---|
| Organic direct aim | `GROUND_DIRECT_FIRE`, `ASSAULT_RIFLE`, `MUZZLE_LOADING_MUSKET`, `BOLT_ACTION_RIFLE`, `SEMI_AUTOMATIC_RIFLE`, `SNIPER_RIFLE`, `ANTI_MATERIEL_RIFLE`, `SUBMACHINE_GUN`, `LIGHT_MACHINE_GUN`, `GENERAL_PURPOSE_MACHINE_GUN`, `HEAVY_MACHINE_GUN`, `INDIVIDUAL_GRENADE_LAUNCHER`, `AUTOMATIC_GRENADE_LAUNCHER`, `ANCIENT_PROJECTILE`, `ANTI_ARMOR`, `INCENDIARY_PROJECTOR` |
| Compatible director required | `AIR_DEFENSE_GUN`, `NAVAL_GUNFIRE`, `NAVAL_AIR_DEFENSE_GUN`, `AIR_DEFENSE_MISSILE`, `AIR_TO_AIR_MISSILE`, `AIR_TO_GROUND_MISSILE`, `ANTI_SHIP_MISSILE`, `MULTI_ROLE_VLS`, `AIRCRAFT_GUN`, `CLOSE_IN_DEFENSE`, `DIRECTED_ENERGY` |
| Unsupported for automatic tactical standoff | `FIELD_ARTILLERY`, `MORTAR_FIRE`, `ROCKET_ARTILLERY`, `HAND_GRENADE`, `MELEE`, `BOMB_DELIVERY`, `TORPEDO`, `ANTI_SUBMARINE` |

`DIRECT_VISUAL` is a typed local fire-control source, not an invented catalog
sensor. In non-FOW mode it records the shooter itself, target, current ENU
geometry, scenario/weather/illumination/concealment/LOS bounds, and no sensor
ID. It can support only the organic-direct-aim class. It does not extend
visibility, create a FOW contact, or satisfy a director-required role.

| Sensor targeting class | Exact `SensorModeledRole` members |
|---|---|
| Local fire control | `THERMAL_TARGETING`, `AIRBORNE_FIRE_CONTROL_RADAR`, `AIRBORNE_GROUND_FIRE_CONTROL_RADAR`, `AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR`, `FIRE_CONTROL_RADAR`, `GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR`, `NAVAL_FIRE_CONTROL_RADAR`, `NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR`, `GROUND_VISUAL_SIGHT`, `GROUND_AIR_DEFENSE_OPTICAL_SIGHT`, `AIRBORNE_VISUAL_SIGHT`, `AIRBORNE_GROUND_VISUAL_TARGETING`, `AIRBORNE_GROUND_BOMBSIGHT`, `NAVAL_VISUAL_DIRECTOR`, `NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR`, `GROUND_NIGHT_SIGHT`, `GROUND_ACTIVE_IR_SIGHT`, `GROUND_THERMAL_TARGETING`, `AIRBORNE_GROUND_THERMAL_TARGETING` |
| Contact/search only | `VISUAL_OBSERVATION`, `NIGHT_VISION`, `AIRBORNE_MARITIME_SEARCH_RADAR`, `AIR_SEARCH_RADAR`, `SHIP_AIR_SURFACE_SEARCH_RADAR`, `SURFACE_SEARCH_RADAR`, `SHIP_SURFACE_SEARCH_RADAR`, `SUBMARINE_SURFACE_SEARCH_RADAR`, `GROUND_SURVEILLANCE_RADAR`, `COASTAL_SURVEILLANCE_RADAR`, `NAVAL_LOOKOUT`, `AIRBORNE_LOW_LIGHT_OBSERVATION`, `INDIVIDUAL_NIGHT_VISION`, `AIRBORNE_AIR_THERMAL_SEARCH`, `AIRBORNE_SURFACE_THERMAL_SEARCH`, `RADAR_WARNING_ESM`, `ELECTRONIC_SUPPORT`, `ACTIVE_SONAR`, `PASSIVE_SONAR` |

Allowed shooter domains are also a total role contract. They do not create a
capability: the exact mapped attachment, target-domain tuple, operational
state, contact, and compatibility gates remain necessary.

| Allowed shooter domains | Exact `SensorModeledRole` members |
|---|---|
| `GROUND`, `AERIAL`, `NAVAL`, `SUBMARINE`, `AMPHIBIOUS` | `VISUAL_OBSERVATION`, `NIGHT_VISION`, `THERMAL_TARGETING`, `FIRE_CONTROL_RADAR`, `RADAR_WARNING_ESM`, `ELECTRONIC_SUPPORT` |
| `AERIAL` | `AIRBORNE_FIRE_CONTROL_RADAR`, `AIRBORNE_GROUND_FIRE_CONTROL_RADAR`, `AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR`, `AIRBORNE_MARITIME_SEARCH_RADAR`, `AIRBORNE_VISUAL_SIGHT`, `AIRBORNE_GROUND_VISUAL_TARGETING`, `AIRBORNE_GROUND_BOMBSIGHT`, `AIRBORNE_LOW_LIGHT_OBSERVATION`, `AIRBORNE_GROUND_THERMAL_TARGETING`, `AIRBORNE_AIR_THERMAL_SEARCH`, `AIRBORNE_SURFACE_THERMAL_SEARCH` |
| `GROUND`, `AMPHIBIOUS` | `GROUND_SURVEILLANCE_RADAR`, `COASTAL_SURVEILLANCE_RADAR`, `GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR`, `GROUND_VISUAL_SIGHT`, `GROUND_AIR_DEFENSE_OPTICAL_SIGHT`, `GROUND_NIGHT_SIGHT`, `GROUND_ACTIVE_IR_SIGHT`, `INDIVIDUAL_NIGHT_VISION`, `GROUND_THERMAL_TARGETING` |
| `NAVAL` | `SHIP_AIR_SURFACE_SEARCH_RADAR`, `SHIP_SURFACE_SEARCH_RADAR`, `NAVAL_FIRE_CONTROL_RADAR`, `NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR`, `NAVAL_VISUAL_DIRECTOR`, `NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR`, `NAVAL_LOOKOUT` |
| `GROUND`, `AERIAL`, `NAVAL`, `AMPHIBIOUS` | `AIR_SEARCH_RADAR`, `SURFACE_SEARCH_RADAR` |
| `SUBMARINE` | `SUBMARINE_SURFACE_SEARCH_RADAR` |
| `NAVAL`, `SUBMARINE` | `ACTIVE_SONAR`, `PASSIVE_SONAR` |

The following compatibility matrix is a global upper bound; the exact sensor
mapping's compatible-role tuple and resolved source-index tuple must also admit
the selected weapon. Compatibility is total and role-owned. Every
organic-direct-aim role
accepts only `DIRECT_VISUAL`, `THERMAL_TARGETING`, `FIRE_CONTROL_RADAR`,
`GROUND_VISUAL_SIGHT`, `GROUND_NIGHT_SIGHT`, `GROUND_ACTIVE_IR_SIGHT`, or
`GROUND_THERMAL_TARGETING`. Naval gunfire accepts only
`NAVAL_VISUAL_DIRECTOR` or `NAVAL_FIRE_CONTROL_RADAR`; naval air defense and
close-in defense accept only `NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR`,
`NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR`, or `NAVAL_FIRE_CONTROL_RADAR`; ground
air-defense guns/missiles accept only `GROUND_AIR_DEFENSE_OPTICAL_SIGHT`,
`GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR`, or generic `FIRE_CONTROL_RADAR`;
air-to-air weapons and aircraft guns accept only `AIRBORNE_VISUAL_SIGHT`,
`AIRBORNE_FIRE_CONTROL_RADAR`, or
`AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR`; air-to-ground weapons accept only
`AIRBORNE_GROUND_VISUAL_TARGETING`,
`AIRBORNE_GROUND_THERMAL_TARGETING`,
`AIRBORNE_GROUND_FIRE_CONTROL_RADAR`, or
`AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR`. `AIRBORNE_GROUND_BOMBSIGHT` is
reserved for the separate `BOMB_DELIVERY` path and cannot authorize automatic
standoff. Anti-ship missiles accept
only `NAVAL_FIRE_CONTROL_RADAR`, `AIRBORNE_MULTI_DOMAIN_FIRE_CONTROL_RADAR`,
or a target-domain-compatible `FIRE_CONTROL_RADAR`; `MULTI_ROLE_VLS` accepts
only `FIRE_CONTROL_RADAR`, `GROUND_AIR_DEFENSE_FIRE_CONTROL_RADAR`,
`NAVAL_FIRE_CONTROL_RADAR`, or `NAVAL_AIR_DEFENSE_FIRE_CONTROL_RADAR`;
`DIRECTED_ENERGY` accepts those same four radar roles plus
`GROUND_AIR_DEFENSE_OPTICAL_SIGHT` and
`NAVAL_AIR_DEFENSE_OPTICAL_DIRECTOR`. In every case the sensor role's declared
target-domain tuple and the shooter platform domain must also match. A role
outside the named set, a shooter-platform/domain mismatch, or any unsupported
weapon class produces a typed non-authorizing result. Search/contact roles
never satisfy fire control. Tests must enumerate the Cartesian policy and
reject any missing/default branch.

### Decision scope and existing combat owners

The shared decision gates only the current unit-to-target direct-engagement
branch and automatic movement standoff. Its supported direct-fire roles are the
organic/director-required rows above. `HAND_GRENADE` and `MELEE` remain valid
close direct-engagement roles but always have `authorized_standoff_m == 0.0`;
their same target/contact decision may authorize engagement without authorizing
a hold. “Unsupported for automatic tactical standoff” is therefore not a
claim that a weapon is globally unsupported.

The following owners remain separate and cannot supply this movement hold:

- `FIELD_ARTILLERY`, `MORTAR_FIRE`, and `ROCKET_ARTILLERY` remain with the
  indirect-fire mission/reservation/action owner completed in Phase 111;
- `BOMB_DELIVERY` remains with the air strike/routing owner;
- `TORPEDO` and `ANTI_SUBMARINE` remain with the naval/subsurface routing owner.

Phase 115 neither inserts its direct-fire decision as a new prerequisite for
those routed actions nor lets their weapons leak back into ordinary direct-fire
selection. Focused controls for every excluded role prove that toggling
automatic standoff leaves its owning action path unchanged, while the excluded
attachment contributes zero tactical hold. No sensing-integrity claim for a
separate routed owner is inferred from those regression tests.

### Targeting decision

One simulation-owned `TacticalTargetingRuntime` creates immutable
`TacticalTargetingDecision` values. Each decision is keyed by
`(engine_tick, battle_id, shooter_id)` rather than overwriting a unit-global
slot, and contains at least:

- logical engine tick, battle ID, deterministic ordinal, shooter ID and side;
- exact hostile target ID/side/domain, or no target;
- pre-movement ENU distance;
- exact weapon target ID, source-equipment index, modeled role, ammunition ID,
  physical maximum range, predictive effective range (`0.0` when absent),
  effective-range basis (`AUTHORED` or
  `LEGACY_DERIVED_80_PERCENT_OF_MAX`), and the separately labeled legacy
  reference value for diagnostics;
- contact source, observing unit ID, sensor source-equipment index, and logical
  contact time;
- scenario/weather visibility bound, including for an explicit targetless
  decision, and the winning local sensing attachment, range, and modeled role
  when one exists;
- fire-control source, range, and role classification;
- typed disposition explaining every rejection;
- authorized automatic standoff range; and
- whether the current pre-movement distance authorizes a hold.

All IDs are exact loaded runtime IDs. Values are finite and non-negative.
`authorized_standoff_m` may be positive only when:

1. the target is active, hostile, and present in the current battle roster;
2. the contact is current under the mode-specific rules below;
3. the weapon attachment is operational, has fireable ammunition, is not
   reserved by the indirect-fire owner, and supports the target domain;
4. the weapon role supports automatic tactical standoff;
5. a compatible fire-control source exists; and
6. a positive predictive range has an `AUTHORED` effective-range basis; and
7. the authorized range is no greater than physical maximum, authored
   effective range, current sensing/contact reach, and fire-control reach.

The shared decision separately records `engagement_solution_valid`. A missing
authored effective range makes `authorized_standoff_m == 0.0` but does not by
itself make that field false. This distinction prevents the legacy multiplier
from authorizing movement while preserving an otherwise real, current firing
solution. For an `AUTHORED` weapon the current distance must also be within the
authored effective range. For a legacy-derived weapon, engagement retains the
existing physical-range ceiling and explicitly exposes `EFFECTIVE_RANGE_UNKNOWN`;
it never converts the diagnostic legacy reference into an eligibility gate.

The runtime selects among eligible current contacts using the configured
closest or threat-scored policy. All candidate construction and tie-breaking
are canonical by side, target ID, weapon source index, weapon ID, sensor source
index, and sensor ID after the existing score/distance key. A nearer
undetectable or domain-incompatible ground-truth unit cannot starve a farther
valid contact.

### Contact and sensing semantics

The interval observation state is resolved once after the fog-of-war update.
One complete RNG-free picture set is then resolved for every active battle from
that same post-observation, pre-movement snapshot and published before the
canonical battle loop begins. This prevents an earlier battle's movement,
ammunition expenditure, or damage from changing a later battle's same-interval
evidence when membership overlaps while REM-035 remains open. Each battle's
movement and engagement consumers use its immutable composite-keyed decisions;
neither performs a second detection roll or reconstructs a different answer
after movement.

- With fog of war disabled, the current non-FOW production acquisition
  calculation is refactored into one side-effect-free typed sensing-envelope
  resolver. It includes the visibility, weather, illumination/night,
  concealment, obscurant, sensor modality, radar/acoustic propagation, MOPP,
  altitude, target posture, domain, FOV/LOS, and equipment-condition gates that
  can currently change acquisition. Any mutable concealment update occurs once
  at a declared tick stage, not once per resolver call or attacker iteration.
  The resulting exact same-tick local observation is the contact; it consumes
  no RNG, preserving current non-FOW stochastic authority.
- With fog of war enabled, the existing canonical DETECTION draw/update remains
  the only stochastic contact authority. Each successful draw emits one
  immutable `ObserverDetectionWitness` containing side, observing unit ID,
  target ID, exact sensor attachment source index/ID/role, logical elapsed
  seconds, and the detection result. The update receives those identity fields
  plus current visibility, illumination, target concealment/posture, and other
  inputs that its detection call presently defaults. A qualifying contact must
  identify the exact hostile roster target, have at least `DETECTED`
  identification, not be `STALE` or `LOST`, and be backed by a witness for the
  same shooter, target, exact live attachment, and current update. A target-
  level `reporting_sensors` entry alone is insufficient. Contact acquisition
  and fire control may use the same attachment; if they differ, both must be
  shooter-local and the explicit compatibility table must accept the fire-
  control attachment. The targeting resolver performs no second draw.
- FOW time is scenario-logical elapsed seconds from
  `ctx.clock.elapsed.total_seconds()`, never wall/epoch time. World-view update,
  contact, witness, targeting decision, and checkpoint validation compare that
  representation exactly. A current witness has
  `witness.logical_time_s == world_view.last_update_time == current elapsed_s`;
  a coasting or previous-tick record is not current.
- Every position report submitted to intelligence fusion has finite, strictly
  positive measurement uncertainty. The production sensor adapter retains its
  existing five-percent-of-range model but applies the fusion subsystem's
  conservative one-metre minimum at zero or very short range. Direct callers
  that claim zero, negative, or non-finite uncertainty reject explicitly.
  Repeated co-located FOW observations update the already issued side-local
  track; they cannot fail on a singular innovation covariance or mint a
  replacement identity merely to avoid that update.
- Under FOW, `DIRECT_VISUAL` is never an independent detection path. It may
  supply fire control for an organic-direct-aim weapon only after the same
  shooter/target has a current canonical witness whose mapped role is
  `VISUAL_OBSERVATION`, `NIGHT_VISION`, `NAVAL_LOOKOUT`,
  `AIRBORNE_LOW_LIGHT_OBSERVATION`, or `INDIVIDUAL_NIGHT_VISION`. The runtime
  then derives an RNG-free visual/LOS/environment envelope from the already
  committed interval inputs; its reach is capped at the witnessed current
  distance and cannot extrapolate the successful stochastic observation. A
  radar, thermal, acoustic, or ESM witness cannot become `DIRECT_VISUAL`; it
  requires a separately compatible local fire-control attachment.
- Scenario/weather optical visibility bounds unaided visual, visual sight,
  director, lookout, and other direct-optical paths. It does not cap thermal,
  radar, acoustic, or ESM reach unless that modality's own production physics
  explicitly applies the environment term. Illumination, obscurant, LOS,
  propagation, and condition gates remain modality-specific.
- A side-wide contact does not imply an offboard fire-control path. Automatic
  standoff still requires a local organic/director-compatible source. Remote
  cueing is unsupported until the communications topology owned by REM-036 /
  Phase 123 can prove the link.
- Passive ESM, search-only, or observation-only equipment can support the
  typed contact stage where its real detection model permits, but cannot be
  silently promoted to fire control.

The movement destination used when no targeting contact exists remains the
existing battle-level force-closure vector. It is an approach reference, not a
claimed target contact, and no target ID or targeting capability may be
exposed from it. Replacing force-level approach planning with contact-track or
objective navigation is outside REM-028.

### Tick ordering and consumers

For each active tactical interval:

1. after the normal environment stage, `SimulationEngine` invokes the targeting
   interval coordinator exactly once before its active-battle loop, keyed by
   `ctx.clock.tick_count` and logical elapsed seconds;
2. that coordinator updates mutable concealment inputs once and performs at
   most one side-wide FOW update for the complete roster, retaining immutable
   per-observer witnesses; a second preparation for the same engine tick
   rejects;
3. before entering the battle loop, the coordinator filters the committed
   interval observations for every battle's current declared membership and
   atomically publishes the complete canonical RNG-free picture set keyed by
   `(engine_tick, battle_id, shooter_id)`; the engine then iterates that fixed
   set in canonical battle-ID order;
4. that battle executes authored/defensive/emplaced/wave movement holds first;
5. for an ordinarily advancing unit, hold with
   `ENGINE_WEAPON_STANDOFF` only when its published decision authorizes the
   current distance; otherwise continue movement and record the targeting
   rejection alongside the movement decision;
6. execute engagement from the same selected target, weapon, contact, sensing,
   and fire-control decision, revalidating only post-movement mutable facts
   such as target status, exact distance, weapon condition, reservation, and
   ammunition before commit; and
7. publish bounded diagnostic/exposure state atomically, then continue to the
   next battle without repeating the interval FOW update.

The current battle membership topology is consumed exactly as declared; Phase
115 does not claim it is globally correct. A unit present in multiple active
battles receives a distinct composite-keyed decision for each and cannot be
silently overwritten. REM-035 / Phase 122 retains correction of duplicate and
stale battle membership itself.

The ordinary unit-target direct-engagement branch always obeys the targeting
decision; the explicitly separated owners above retain their own contracts.
Disabling automatic standoff changes only step 5; it must not authorize direct
fire from an invalid contact or outside physical/fire-control reach, or outside
authored effective range when that range exists.

ROE, morale, posture, concealment engagement thresholds, cooldown, weapon arcs,
hit probability, damage, and event publication remain later necessary gates.
Consequently a valid targeting decision is necessary, not a guarantee that a
shot is committed. Those later gates cannot retroactively turn an absent
contact into a standoff authorization.

## State, persistence, and exposure

Checkpoint format 115 persists the targeting runtime's exact registered
unit/side topology, prepared interval tick/time, canonical battle ordering,
and bounded latest decisions by exact `(engine_tick, battle_id, shooter_id)`
key. It persists scalar/enum/ID evidence only, never live object
references. Restore validates:

- exact current roster side/target topology;
- exact weapon and sensor attachment source indexes, target IDs, modeled roles,
  and loaded object identity after reconstruction;
- finite ranges and the complete limiting-range inequalities;
- logical tick/time and canonical ordering;
- exact battle ID and declared membership for every composite decision key;
- contact/source/disposition invariants; and
- calibration enablement agreement.

Malformed, missing, extra, stale, cross-side, source-mismatched, or impossible
decisions reject before any context, manager, RNG, recorder, or entity state
mutates. Version 114 is explicitly rejected by the current-format loader;
versionless migration may omit targeting state only under the same bounded
pre-execution topology used by existing legacy migration.

Fresh-runtime continuation must be exact for the FOW-disabled targeting path,
including the next targeting picture, movement decision, positions,
ammunition, events, RNG state, diagnostics, and whole checkpoint. The runtime
also persists and exposes FOW-enabled targeting decisions, but a restored
decision is historical, explicitly `consumable=false`, and cannot authorize
movement or fire until a new same-tick picture replaces it. Exact fresh
continuation from nonempty ordinary `SideWorldView.contacts` remains the
explicit REM-029 / Phase 116 boundary because format 115 still deliberately discards
those contacts on restore. Phase 115 must not claim that continuation or hide
the limitation behind duplicated contact state or persisted witnesses.

Movement diagnostics retain the exact targeting decision associated with each
tactical observation. The evaluator consumes that recorded decision and must
not recompute legacy catalog standoff. Public evaluator/API/replay output
exposes at least target ID, disposition, contact source/time, weapon physical
and effective range, sensing and fire-control source/range, authorized
standoff, and enablement. No exposed target may be absent from the hostile
loaded roster.

That exact-ID record is privileged engine/evaluator evidence. A FOW-limited or
player-facing API receives the side's authorized contact identifier and public
track fields only when its current world view contains that contact; it never
receives the ground-truth roster entity ID, hidden attachment identity, or a
decision for another side. Track identifiers are deterministic per-side
ordinals allocated in canonical first-detection order and persisted by the
side's intelligence-fusion track state. They are not hashes of enumerable
observer, target, tick, or time inputs. Exposure schemas declare
`PRIVILEGED_ENGINE` versus `SIDE_FOW` scope, and API/replay consumers require
the parsed payload's exact `viewer_side` to match the requested side even when
that side has an empty roster. Paired tests prove both the evidence view and
the absence of cross-side/undetected or reversible-identifier leakage.

## Failure behavior and atomicity

- Unknown configuration fields and non-boolean enablement reject at scenario
  validation.
- Missing or inconsistent live role bindings reject during loadout preflight;
  runtime code never guesses from equipment names, sensor types, or collection
  order.
- Before an engine tick can advance, targeting registration walks the exact
  side buckets, rejects duplicate entity IDs and bucket/unit-side disagreement,
  and then requires exact agreement with the registered unit/side topology.
- Unsupported weapon-role/fire-control combinations yield an explicit typed
  non-authorizing decision. They do not use catalog maximum as fallback.
- The atomic targeting boundary begins after a successful FOW update. FOW owns
  its canonical draws/contact mutation and Phase 115 does not promise rollback
  to the pre-FOW state. FOW failure is surfaced and aborts the remaining tick;
  it is never swallowed and no targeting, movement, engagement, or diagnostic
  commit follows it.
- Targeting-picture construction stages the complete canonical immutable set
  for every active battle, builds one runtime snapshot containing the interval,
  published IDs, pictures, and revalidation ledger, and swaps that one
  reference. Failure publishes no prefix or partial picture and, from that
  post-FOW baseline, leaves positions, ammunition, events, and previous
  diagnostic state unchanged. It performs no RNG draw.
- Post-movement revalidation failure skips the shot and publishes its exact
  typed reason without fabricating a replacement target or weapon.
- Recorder or diagnostic publication follows the existing commit ordering;
  this phase makes no unsupported battle-wide rollback claim. Validated
  publication payloads are built before the associated movement/engagement
  commit, and focused fault tests cover every boundary this phase changes.

## Production trace and proof obligations

| Stage | Required evidence |
|---|---|
| Declared | Strict `CalibrationSchema` flag plus typed role bindings, decisions, sources, and dispositions. |
| Loaded | Factory-built scenarios retain exact flag and mapping roles; malformed/unknown data rejects. |
| Wired | `ScenarioLoader` injects one targeting owner; `BattleManager` movement and engagement consume its same decision. |
| Enabled | Default-on and explicit-off factory variants reach distinct automatic-hold branches; off never restores raw maximum holding. |
| Exercised | Catalog-backed Cambrai/Jutland and focused cross-domain/FOW controls produce real decisions through `RuntimeSession.step`. |
| Outcome-affecting | Positions, movement reasons, weapon fire/ammunition, engagement events, and at least one terminal or force-state metric differ under predeclared controls. |
| Persisted/exposed | Format-115 strict state, exact no-FOW fresh continuation, movement diagnostics, evaluator, replay/API fields, and explicit REM-029 FOW-continuation exclusion. |

## Verification plan

### Baseline and production red

1. Record the synchronized `f057923e3b13aabe2f0994e03063e6692ceef0ce`
   Phase 115 base and complete hosted Phase 114 evidence.
2. Run the current focused movement, sensor-domain, evaluator, checkpoint, and
   Jutland multiplicity tests unchanged.
3. Reproduce Cambrai seed 42 and Jutland seed 42 through the production factory
   and evaluator, retaining exact positions, ranges, sensor definitions,
   movement reasons, fire/ammunition, engagements, casualties, events, ticks,
   duration, and terminal result.
4. Add a factory/session production red that fails because Cambrai Mark IVs
   authorize 5,340 m without a contact or effective-range/fire-control
   solution; add Jutland, search-versus-director, disabled, same-decision,
   strict-state, and public-exposure reds. Tests must fail behaviorally, not
   merely because a class or field is absent.

### Focused behavioral acceptance

1. Prove all targeting dataclass, range, role, target-selection, ordering, and
   state invariants, including NaN/nonfinite and impossible inequalities.
2. Through factory-built catalog units and `RuntimeSession.step`, prove:
   sensor absent/offline/degraded, wrong-domain, observation/search-only,
   director/fire-control, direct visual, no-ammo, indirect reservation,
   unsupported-role, off-boresight/LOS, mixed-target, and mixed-loadout
   controls. The mixed loadout proves a No. 7/Panoramic artillery sight cannot
   direct an organic direct-fire weapon on the same unit.
3. Prove one interval publishes one FOW answer and that every composite-keyed
   battle picture's movement/direct-engagement consumers use it without
   another DETECTION draw, including multi-battle, parallel-detection,
   scan-scheduling, and LOD controls. When an identification engine is
   configured, its stochastic misclassification must consume the same
   caller-owned side-local stream rather than shared mutable RNG state.
4. Prove `enable_sensing_aware_standoff=true` holds only on authorization and
   `false` authorizes `0.0 m`, while authored/defensive/emplaced/wave holds are
   identical in both variants.
5. Run Cambrai and Jutland seeds 42-44. For each, retain exact old-versus-new
   movement, capital/tank weapon-fire topology, ammunition, engagement events,
   casualties, terminal outcome, and warnings. Do not describe either as
   historically validated: completed Phase 117 classifies zero claims as
   production-validated and closed REM-030 with a truthful failed study; these
   runs remain current-engine regression evidence only.
6. Prove FOW disabled direct-contact behavior and FOW enabled no-contact,
   current-contact, stale/coasting, ownership, and single-draw behavior. Do not
   claim fresh nonempty-contact continuation.
7. Prove format-115 exact in-place and fresh no-FOW continuation, whole-state
   equality, corrupt-state atomic rejection, and versionless bounds.
8. Prove evaluator, recorder/replay, and API exposure from real production
   decisions, including the absence of invented or cross-side targets.
9. For `FIELD_ARTILLERY`, `MORTAR_FIRE`, `ROCKET_ARTILLERY`, `BOMB_DELIVERY`,
   `TORPEDO`, and `ANTI_SUBMARINE`, prove the owning routed action is unchanged
   by the standoff flag and contributes zero hold. Prove `HAND_GRENADE` and
   `MELEE` can retain close direct engagement while contributing zero hold.

### Broader validation and reviews

- focused Phase 115 unit, integration, validation, API, and checkpoint tests;
- all directly affected Phase 109/112/114 tests;
- `$audit-determinism` with hash-seed, repeated-seed, FOW DETECTION-stream, and
  checkpoint controls;
- `$validate-data` for changed mapping declarations and every reachable
  loadout/scenario;
- `$evaluate-scenarios` for Cambrai/Jutland and the complete scenario catalog,
  with exact warnings and exclusions;
- `$validate-conventions` for typed state, public API, clock/RNG, and
  checkpoint changes;
- `$profile` because targeting runs in the production tactical hot loop;
- repository exact Python partitions, frontend checks if an exposed schema
  changes, Ruff, compileall, strict docs, and `git diff --check`;
- `$simplify`, then `$update-docs`, `$cross-doc-audit`, and `$postmortem`
  before the single Phase 115 commit.

## Implemented production boundary

The production implementation follows the accepted contract rather than
retaining the former movement-only calculation:

- `ScenarioLoader` constructs one `TacticalTargetingRuntime`, binds that exact
  object to `SimulationContext`, `SimulationEngine`, and every
  `BattleManager`, and rejects owner replacement or incomplete live bindings.
  `SimulationEngine` also rejects an ownerless empty context, keeping every
  format-115 checkpoint inside the same strict ownership contract.
- `RuntimeLoadoutBuilder` preserves canonical source-equipment order and
  resolves each modeled weapon and sensor role to exact source indexes. Initial
  units, reinforcements, and checkpoint reconstruction all use the same typed
  boundary. A compatible role is only an upper-bound policy: the exact weapon
  definition must still admit the target domain.
- the engine prepares environment, concealment, and FOW once per tactical
  interval, then the coordinator publishes the complete immutable picture set
  keyed by tick, battle, and shooter before the canonical battle loop starts.
  Movement and ordinary direct engagement consume those pictures;
  post-movement engagement revalidation records an explicit outcome instead
  of silently choosing a different weapon, sensor, or target;
- observation/search-only sensors cannot become fire control, direct visual
  requires a same-shooter current visual witness, and every sensor and weapon
  role has an exhaustive allowed-domain/compatibility disposition. Unsupported
  combinations authorize neither a shot nor a catalog-range hold;
- `enable_sensing_aware_standoff` is a strict, default-on calibration field.
  Explicit `false` makes automatic tactical standoff exactly zero; it does not
  revive the legacy maximum-range branch or alter separate authored,
  defensive, emplaced, wave-release, indirect-fire, bomb, torpedo, or ASW
  owners;
- checkpoint format 115 stores the runtime owner state, interval, exact battle
  memberships, pictures, decisions, revalidations, enablement, visibility
  bound, and source bindings. Restore stages and cross-validates them against
  the clock, roster, battle state, loadout topology, and movement diagnostics
  before committing; restored FOW-backed decisions are historical and
  non-consumable; and
- movement diagnostics, evaluator output, replay, stored frames, API schemas,
  and frontend types expose the same decision evidence. Stored frames contain
  paired `PRIVILEGED_ENGINE` and `SIDE_FOW` projections; the latter substitutes
  opaque owner-side track data and omits hidden entity and attachment identity.
  Every stored side decision/outcome must equal the complete projection derived
  from its privileged source and root-only target/track association. Its
  per-battle decision ordinal is recomputed within the viewer side, so an
  opposing shooter's hidden roster position is not observable.

Production validation found and repaired one additional cross-era semantic
case: Salamis uses ancient projectile/melee roles against naval targets. The
global compatibility policy now asks the complete validated role profile
whether the target domain is supported, while the exact attached weapon
definition remains the final domain gate. A strict production Salamis run
records real javelin engagement events and rejects an aerial control. This is
not permission to widen any weapon's authored domains.

The fresh Phase 115 suite, data inventory, deterministic scenario controls,
and profile are recorded with exact commands in the
[Phase 115 devlog](../devlog/phase-115.md). Cambrai's four Mark IVs now advance
instead of blind-holding beyond their 3,000 m usable optical envelope, and
Jutland's capital ships no longer stop at 21.7 km solely because a catalog gun
can reach that far. Those are current-engine integrity regressions, not claims
of historical calibration or validity.

Four deliberately separate follow-ups were surfaced during implementation.
REM-041 must add caller authentication/authorization and make player-facing API
defaults side-safe; an explicit scope query is not authorization. REM-042 must
author physical mount/director associations so a mixed unit cannot cross-bind
two otherwise compatible attachments merely because their roles match.
REM-043 must define availability-aware threat scoring rather than extending the
Phase 115 targeting contract by implication. They are assigned to Phases 128,
129, and 130 respectively. REM-044 / Phase 131 must replace the generic
isotropic uncertainty floor with sourced sensor covariance and stage elapsed-
time prediction plus measurement update as one atomic track transaction.

## Acceptance criteria

Phase 115 and REM-028 may close only when:

1. raw catalog maximum cannot independently authorize tactical standoff;
2. one typed, canonical interval observation and composite-keyed per-battle
   decision distinguish physical reach, effective range,
   sensing/visibility, contact, and fire control and are shared by movement
   and engagement without a repeated FOW update;
3. no second detection roll, implicit sensor extension, name-derived role,
   ground-truth target claim, or search-to-fire-control promotion remains;
4. enabled and disabled controls change real movement and combat outcomes,
   while disabled automatic standoff is exactly zero and explicit holds remain
   unchanged;
5. Cambrai and Jutland no longer exhibit the recorded blind capital/tank
   standoff, with exact production evidence and no historical-validity claim;
6. initial, reinforcement, checkpoint, diagnostics, evaluator, replay, and API
   paths retain exact typed role/decision evidence;
7. malformed state/data reject atomically, determinism and RNG authority pass,
   and benchmark-integrity policy is satisfied either by an ordinary paired
   performance pass for identical workloads or by Phase 115's exact non-timing
   transition qualification, which makes no performance claim;
8. format-115 no-FOW continuation is exact and the independent REM-029
   nonempty-FOW continuation deficit remains explicitly bounded for Phase 116;
   and
9. all applicable focused, data, scenario, convention, broader, documentation,
   cross-document, and postmortem gates pass before one coherent phase commit.

## Non-goals and accepted limitations

- Phase 115 does not restore ordinary `SideWorldView.contacts`; REM-029 /
  Phase 116 owns their complete typed continuation.
- It does not create offboard fire-control or communications links; REM-036 /
  Phase 123 owns that topology.
- It does not replace scheduled indirect fire, time-on-target, or ammunition
  reservation ownership completed in Phase 111.
- It does not recalibrate weapon, ammunition, sensor, visibility, hit
  probability, damage, morale, or historical outcome parameters.
- It does not claim Cambrai or Jutland historical validation; REM-030 /
  Phase 117 owns source-backed held-out outcome envelopes.
- It does not replace the existing no-contact force-closure movement vector
  with contact-track navigation or authored-objective planning.
- Aggregation loadout reconstruction remains REM-016; logistics authority
  remains REM-020/REM-021.

## Open decisions

No implementation-contract decision remains open. Formal design review
accepted authored effective-range provenance, per-observer FOW witnesses,
elapsed-seconds contact time, total role/compatibility policy,
non-consumable restored FOW decisions, and the post-FOW atomic boundary before
behavioral implementation began. The independent remediation items listed
above remain explicit rather than being treated as Phase 115 completion
evidence.

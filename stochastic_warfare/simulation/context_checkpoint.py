"""Strict staging and validation helpers for context checkpoints."""

from __future__ import annotations

import copy
import enum
import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from stochastic_warfare.core.types import Domain, Position
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.detection.estimation import TrackStatus
from stochastic_warfare.detection.sensors import SensorType
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.entities.equipment import EquipmentCategory
from stochastic_warfare.morale.state import MoraleState
from stochastic_warfare.simulation.loadouts import (
    RuntimeLoadouts,
    SensorAttachment,
    WeaponAttachment,
)
from stochastic_warfare.simulation.scenario_config import CampaignScenarioConfig
from stochastic_warfare.simulation.tactical_targeting import (
    ContactSource,
    EffectiveRangeBasis,
    FireControlSource,
    TacticalTargetingDecision,
    TacticalTargetingRestorePlan,
    sensor_environment_range_policy,
    sensor_environment_range_upper_bound_m,
    targeting_visibility_bound_m,
)

if TYPE_CHECKING:
    from stochastic_warfare.detection.fog_of_war import (
        FogOfWarRestorePlan,
        FogOfWarSensorBinding,
    )


@runtime_checkable
class AtomicCheckpointOwner(Protocol):
    """Typed owner that validates a restore plan before committing it."""

    def get_state(self) -> Any:
        """Capture the owner's canonical checkpoint state."""

    def stage_state(self, state: Any, *args: Any, **kwargs: Any) -> Any:
        """Validate state without mutating the live owner."""

    def commit_state(self, plan: Any, *args: Any, **kwargs: Any) -> Any:
        """Commit one owner-bound validated plan."""


@runtime_checkable
class LegacyCheckpointOwner(Protocol):
    """Explicit compatibility owner staged through an isolated clone."""

    def get_state(self) -> Any:
        """Capture the owner's canonical checkpoint state."""

    def set_state(self, state: Any) -> Any:
        """Restore canonical checkpoint state."""


class CheckpointOwnerDisposition(str, enum.Enum):
    """Atomicity contract assigned to a registered context owner."""

    TYPED_ATOMIC = "typed_atomic"
    LEGACY_CLONE = "legacy_clone"
    STATELESS = "stateless"


@dataclass(frozen=True, slots=True)
class ContextCheckpointOwnerBinding:
    """One explicitly classified owner in deterministic registry order."""

    name: str
    owner: object | None
    disposition: CheckpointOwnerDisposition


@dataclass(frozen=True, slots=True)
class CapturedCheckpointOwnerState:
    """One canonical owner state captured for a context preflight snapshot."""

    binding: ContextCheckpointOwnerBinding
    state: Any


@dataclass(frozen=True, slots=True)
class ContextCheckpointSnapshot:
    """Owner-bound snapshot graph shared by validation and JSON projection.

    The topology is immutable and transaction-private.  Canonical state
    payloads are the fresh values returned by their owners and are never
    exposed independently of the final checkpoint projection.
    """

    context_owner_id: int
    rng_owner_id: int
    rng_state: dict[str, Any]
    owners: tuple[CapturedCheckpointOwnerState, ...]
    targeting_owner_id: int | None
    targeting_plan: TacticalTargetingRestorePlan | None
    fog_owner_id: int | None
    fog_plan: FogOfWarRestorePlan | None

    def owner_state(self, name: str) -> Any:
        """Return one already-captured canonical owner payload."""
        for captured in self.owners:
            if captured.binding.name == name:
                return captured.state
        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class LegacyCheckpointRestorePlan:
    """Canonical state staged by the isolated legacy-owner adapter."""

    owner_id: int
    name: str
    canonical_state: Any


def _unit_class_from_state(state: dict[str, Any]) -> type[Unit]:
    """Resolve a serialized unit state through a fixed, safe class allowlist."""
    from stochastic_warfare.entities.unit_classes.aerial import AerialUnit
    from stochastic_warfare.entities.unit_classes.air_defense import AirDefenseUnit
    from stochastic_warfare.entities.unit_classes.ground import GroundUnit
    from stochastic_warfare.entities.unit_classes.naval import NavalUnit
    from stochastic_warfare.entities.unit_classes.support import SupportUnit

    classes: dict[str, type[Unit]] = {
        "Unit": Unit,
        "GroundUnit": GroundUnit,
        "AerialUnit": AerialUnit,
        "NavalUnit": NavalUnit,
        "AirDefenseUnit": AirDefenseUnit,
        "SupportUnit": SupportUnit,
    }
    discriminator = state.get("unit_class")
    if discriminator is not None:
        try:
            return classes[discriminator]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"Unknown checkpoint unit_class {discriminator!r}",
            ) from exc

    legacy_fields = (
        ("ground_type", GroundUnit),
        ("aerial_type", AerialUnit),
        ("naval_type", NavalUnit),
        ("ad_type", AirDefenseUnit),
        ("support_type", SupportUnit),
    )
    inferred_classes = [unit_class for field_name, unit_class in legacy_fields if field_name in state]
    if len(inferred_classes) > 1:
        markers = [field_name for field_name, _ in legacy_fields if field_name in state]
        raise ValueError(
            f"Ambiguous legacy checkpoint unit fields: {markers!r}",
        )
    if inferred_classes:
        return inferred_classes[0]
    return Unit


def _stage_checkpoint_unit(state: Any, side: str) -> Unit:
    """Validate and build one checkpoint unit without touching live state."""
    if not isinstance(state, dict):
        raise ValueError(
            f"Checkpoint unit for side {side!r} must be a mapping",
        )
    entity_id = state.get("entity_id")
    if not isinstance(entity_id, str) or not entity_id:
        raise ValueError(
            f"Checkpoint unit for side {side!r} has an invalid entity_id",
        )
    state_side = state.get("side")
    if state_side != side:
        raise ValueError(
            f"Checkpoint unit {entity_id!r} is stored under side {side!r} but declares side {state_side!r}",
        )

    unit_class = _unit_class_from_state(state)
    unit = unit_class(entity_id=entity_id, position=Position(0.0, 0.0, 0.0))
    try:
        unit.set_state(state)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid checkpoint state for unit {entity_id!r}: {exc}",
        ) from exc
    return unit


def _validate_checkpoint_ammunition_state(
    saved_state: dict[str, Any],
    runtime_entry: Any,
    instance: Any,
    *,
    entity_id: str,
    index: int,
) -> None:
    """Validate exact live ammunition topology before staging a weapon."""
    compatible_ammo = tuple(instance.definition.compatible_ammo)
    expected_ammo = compatible_ammo
    if isinstance(runtime_entry, WeaponAttachment):
        attachment_ammo = tuple(ammunition.ammo_id for ammunition in runtime_entry.ammunition)
        if attachment_ammo != compatible_ammo:
            raise ValueError(
                f"Runtime weapon ammunition topology for unit "
                f"{entity_id!r} at index {index} is inconsistent: "
                f"attachment={attachment_ammo!r}, "
                f"compatible_ammo={compatible_ammo!r}",
            )
        expected_ammo = attachment_ammo

    ammo_state = saved_state.get("ammo_state")
    if not isinstance(ammo_state, dict):
        raise ValueError(
            f"Checkpoint weapon state {entity_id!r}[{index}] ammo_state must be a mapping",
        )
    rounds_by_type = ammo_state.get("rounds_by_type")
    if not isinstance(rounds_by_type, dict):
        raise ValueError(
            f"Checkpoint weapon state {entity_id!r}[{index}] rounds_by_type must be a mapping",
        )
    expected_keys = set(expected_ammo)
    saved_keys = set(rounds_by_type)
    if saved_keys != expected_keys:
        raise ValueError(
            f"Incompatible weapon ammunition topology for unit "
            f"{entity_id!r} at index {index}: "
            f"missing={sorted(expected_keys - saved_keys, key=repr)!r}, "
            f"extra={sorted(saved_keys - expected_keys, key=repr)!r}",
        )
    for ammo_id, rounds in rounds_by_type.items():
        if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 0:
            raise ValueError(
                f"Checkpoint weapon state {entity_id!r}[{index}] "
                f"rounds_by_type[{ammo_id!r}] must be a non-negative "
                "integer",
            )
    total_rounds_fired = ammo_state.get("total_rounds_fired")
    if not isinstance(total_rounds_fired, int) or isinstance(total_rounds_fired, bool) or total_rounds_fired < 0:
        raise ValueError(
            f"Checkpoint weapon state {entity_id!r}[{index}] total_rounds_fired must be a non-negative integer",
        )


def _stage_runtime_instance_states(
    raw_states: Any,
    current_instances: dict[str, list[Any]],
    checkpoint_unit_ids: set[str],
    compatible_unit_ids: set[str],
    checkpoint_equipment: dict[str, dict[str, dict[str, Any]]] | None,
    *,
    kind: str,
    allow_legacy_weapon_timestamp_omission: bool = False,
) -> list[tuple[Any, dict[str, Any]]]:
    """Validate weapon or sensor instance state without mutating live objects."""
    if not isinstance(raw_states, dict):
        raise ValueError(f"Checkpoint {kind} states must be a mapping")

    expected_ids = set(current_instances) & compatible_unit_ids
    serialized_ids = set(raw_states)
    missing = sorted(expected_ids - serialized_ids)
    if missing:
        extra = sorted(serialized_ids - expected_ids)
        raise ValueError(
            f"Incompatible {kind} unit topology: missing={missing!r}, extra={extra!r}",
        )

    staged: list[tuple[Any, dict[str, Any]]] = []
    for entity_id, saved_instances in raw_states.items():
        if not isinstance(entity_id, str) or entity_id not in checkpoint_unit_ids:
            raise ValueError(
                f"Checkpoint {kind} state references unknown unit {entity_id!r}",
            )
        if not isinstance(saved_instances, list):
            raise ValueError(
                f"Checkpoint {kind} state for {entity_id!r} must be a list",
            )
        if saved_instances and entity_id not in compatible_unit_ids:
            raise ValueError(
                f"Cannot restore {kind} state for reconstructed unit {entity_id!r}; build a compatible runtime first",
            )
        runtime_entries = current_instances.get(entity_id, []) if entity_id in compatible_unit_ids else []
        if len(runtime_entries) != len(saved_instances):
            raise ValueError(
                f"Incompatible {kind} topology for unit {entity_id!r}: "
                f"checkpoint has {len(saved_instances)}, runtime has "
                f"{len(runtime_entries)}",
            )

        for index, saved_state in enumerate(saved_instances):
            if not isinstance(saved_state, dict):
                raise ValueError(
                    f"Checkpoint {kind} state {entity_id!r}[{index}] must be a mapping",
                )
            normalized_state = saved_state
            if kind == "weapon" and allow_legacy_weapon_timestamp_omission and "last_fire_time_s" not in saved_state:
                normalized_state = {
                    **saved_state,
                    "last_fire_time_s": None,
                }
            runtime_entry = runtime_entries[index]
            instance = runtime_entry[0] if kind == "weapon" else runtime_entry
            identity_field = "weapon_id" if kind == "weapon" else "sensor_id"
            runtime_id = getattr(instance, identity_field, None)
            if normalized_state.get(identity_field) != runtime_id:
                raise ValueError(
                    f"Incompatible {kind} identity for unit {entity_id!r} "
                    f"at index {index}: checkpoint has "
                    f"{normalized_state.get(identity_field)!r}, runtime has "
                    f"{runtime_id!r}",
                )
            if kind == "weapon":
                _validate_checkpoint_ammunition_state(
                    normalized_state,
                    runtime_entry,
                    instance,
                    entity_id=entity_id,
                    index=index,
                )
            equipment = getattr(instance, "equipment", None)
            if equipment is not None and checkpoint_equipment is not None:
                saved_equipment = checkpoint_equipment.get(
                    entity_id,
                    {},
                ).get(equipment.equipment_id)
                if saved_equipment is None:
                    raise ValueError(
                        f"Checkpoint {kind} {runtime_id!r} references missing equipment {equipment.equipment_id!r}",
                    )
                if normalized_state.get("equipment_condition") != saved_equipment.get(
                    "condition",
                ) or normalized_state.get("equipment_operational") != saved_equipment.get("operational"):
                    raise ValueError(
                        f"Conflicting checkpoint equipment state for {kind} {runtime_id!r} on unit {entity_id!r}",
                    )
            try:
                staged_instance = copy.deepcopy(instance)
                staged_instance.set_state(normalized_state)
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid {kind} state for unit {entity_id!r} at index {index}: {exc}",
                ) from exc
            staged.append((instance, normalized_state))

    return staged


def _json_compatible_value(value: Any) -> Any:
    """Convert model values to deterministic JSON-compatible structures."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: _json_compatible_value(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        converted = [_json_compatible_value(item) for item in value]
        return sorted(converted, key=repr)
    if isinstance(value, (list, tuple)):
        return [_json_compatible_value(item) for item in value]
    return value


def _model_dump_json_compatible(model: Any) -> dict[str, Any]:
    """Dump Pydantic models canonically while supporting legacy test doubles."""
    try:
        raw = model.model_dump(mode="python")
    except TypeError:
        raw = model.model_dump()
    return _json_compatible_value(raw)


def _json_values_equal(left: Any, right: Any) -> bool:
    """Compare JSON-compatible values without bool/number coercion."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_json_values_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_values_equal(left_item, right_item) for left_item, right_item in zip(left, right, strict=True)
        )
    return bool(left == right)


def _normalize_targeting_battle_memberships(
    memberships: Mapping[str, Collection[str]] | None,
) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
    """Return one immutable canonical active-battle topology."""
    if memberships is None:
        return None
    if not isinstance(memberships, Mapping):
        raise ValueError(
            "targeting_battle_memberships must be a mapping",
        )
    normalized: list[tuple[str, tuple[str, ...]]] = []
    for battle_id, raw_unit_ids in memberships.items():
        if not isinstance(battle_id, str) or not battle_id or battle_id != battle_id.strip():
            raise ValueError(
                "targeting battle IDs must be non-empty trimmed strings",
            )
        if isinstance(raw_unit_ids, (str, bytes)) or not isinstance(
            raw_unit_ids,
            Collection,
        ):
            raise ValueError(
                f"targeting battle {battle_id!r} members must be a collection",
            )
        unit_ids = tuple(sorted(raw_unit_ids))
        if any(not isinstance(unit_id, str) or not unit_id or unit_id != unit_id.strip() for unit_id in unit_ids):
            raise ValueError(
                "targeting battle members must be non-empty trimmed strings",
            )
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError(
                f"targeting battle {battle_id!r} contains duplicate members",
            )
        normalized.append((battle_id, unit_ids))
    return tuple(sorted(normalized))


def _validate_runtime_loadout_object_bindings(
    *,
    units: Mapping[str, Unit],
    loadouts: RuntimeLoadouts,
) -> None:
    """Require attachments to point at exact prospective unit equipment."""
    unit_ids = set(units)
    if (
        set(loadouts.unit_weapons) != unit_ids
        or set(loadouts.unit_sensor_attachments) != unit_ids
        or set(loadouts.equipment_resolutions) != unit_ids
    ):
        raise ValueError(
            "prospective loadout topology disagrees with checkpoint roster",
        )
    for unit_id in sorted(unit_ids):
        unit = units[unit_id]
        equipment = unit.equipment
        resolutions = loadouts.equipment_resolutions[unit_id]
        resolution_indexes = tuple(resolution.source_equipment_index for resolution in resolutions)
        expected_indexes = tuple(
            index
            for index, item in enumerate(equipment)
            if item.category
            in {
                EquipmentCategory.WEAPON,
                EquipmentCategory.SENSOR,
            }
        )
        if resolution_indexes != expected_indexes:
            raise ValueError(
                f"equipment resolutions for {unit_id!r} must exactly cover the live equipment source order",
            )
        for resolution in resolutions:
            if (
                resolution.unit_type != unit.unit_type
                or resolution.source_equipment is not equipment[resolution.source_equipment_index]
            ):
                raise ValueError(
                    f"equipment resolution for {unit_id!r} source index "
                    f"{resolution.source_equipment_index} is detached from "
                    "the exact unit type or equipment object",
                )
        for label, attachments in (
            ("weapon", loadouts.unit_weapons[unit_id]),
            ("sensor", loadouts.unit_sensor_attachments[unit_id]),
        ):
            for attachment in attachments:
                source_index = attachment.source_equipment_index
                if source_index >= len(equipment) or equipment[source_index] is not attachment.source_equipment:
                    raise ValueError(
                        f"{label} attachment for {unit_id!r} is detached from its exact source equipment object",
                    )


def _targeting_visibility_bound_m(
    *,
    calibration: Mapping[str, object],
    weather_engine: Any,
    default_visibility_m: float,
) -> float:
    """Return the exact configured/current visibility used by targeting."""
    weather_visibility_m: float | None = None
    if weather_engine is not None:
        weather_visibility_m = getattr(
            getattr(weather_engine, "current", None),
            "visibility",
            None,
        )
        if weather_visibility_m is None:
            raise ValueError(
                "targeting weather owner has no current visibility",
            )
    return targeting_visibility_bound_m(
        calibration=calibration,
        default_visibility_m=default_visibility_m,
        weather_visibility_m=weather_visibility_m,
    )


def _targeting_interval_is_current(
    *,
    plan: TacticalTargetingRestorePlan,
    clock_tick: int,
    logical_time_s: float,
) -> bool:
    """Return whether retained targeting evidence belongs to this clock."""
    interval = plan.prepared_interval
    if interval is None:
        return False
    if interval.engine_tick > clock_tick or interval.logical_time_s > logical_time_s:
        raise ValueError(
            "targeting checkpoint interval is later than the checkpoint clock",
        )
    tick_is_current = interval.engine_tick == clock_tick
    time_is_current = interval.logical_time_s == logical_time_s
    if tick_is_current != time_is_current:
        raise ValueError(
            "targeting checkpoint interval tick/time disagree with the checkpoint clock",
        )
    return tick_is_current


def _prospective_targeting_visibility_bound_m(
    *,
    calibration: Mapping[str, object],
    weather_engine: Any,
    checkpoint_state: Mapping[str, object],
    default_visibility_m: float,
) -> float:
    """Resolve visibility from an isolated checkpoint-staged weather owner."""
    if weather_engine is None:
        return _targeting_visibility_bound_m(
            calibration=calibration,
            weather_engine=None,
            default_visibility_m=default_visibility_m,
        )
    if "weather_engine" not in checkpoint_state:
        raise ValueError(
            "targeting checkpoint evidence requires weather_engine state",
        )
    staged_weather = copy.deepcopy(weather_engine)
    staged_weather.set_state(copy.deepcopy(checkpoint_state["weather_engine"]))
    return _targeting_visibility_bound_m(
        calibration=calibration,
        weather_engine=staged_weather,
        default_visibility_m=default_visibility_m,
    )


def _validate_targeting_decision_live_bindings(
    *,
    decision: TacticalTargetingDecision,
    units: Mapping[str, Unit],
    loadouts: RuntimeLoadouts,
    calibration: Mapping[str, object],
    live_visibility_m: float | None,
    require_current_consumability: bool,
) -> None:
    """Match one persisted decision to exact prospective runtime objects."""

    def sensor_attachment_for(
        *,
        shooter_id: str,
        source_index: int,
        sensor_id: str,
        modeled_role: Any,
        evidence_label: str,
    ) -> SensorAttachment:
        matches = tuple(
            attachment
            for attachment in loadouts.unit_sensor_attachments.get(
                shooter_id,
                (),
            )
            if (
                attachment.source_equipment_index == source_index
                and attachment.sensor_id == sensor_id
                and attachment.modeled_role is modeled_role
            )
        )
        if len(matches) != 1:
            raise ValueError(
                f"{evidence_label} sensor identity does not resolve to one exact live attachment",
            )
        return matches[0]

    shooter = units.get(decision.shooter_id)
    if shooter is None:
        raise ValueError(
            "targeting shooter identity is absent from the restored roster",
        )
    shooter_side = shooter.side if isinstance(shooter.side, str) else shooter.side.value
    if shooter_side != decision.shooter_side:
        raise ValueError(
            "targeting shooter side disagrees with the live unit",
        )
    if shooter.domain is not decision.shooter_domain:
        raise ValueError(
            "targeting shooter domain disagrees with the live unit",
        )
    if decision.target_id is not None:
        target = units.get(decision.target_id)
        if target is None:
            raise ValueError(
                "targeting target identity is absent from the restored roster",
            )
        target_side = target.side if isinstance(target.side, str) else target.side.value
        if target_side != decision.target_side:
            raise ValueError(
                "targeting target side disagrees with the live unit",
            )
        if target.domain is not decision.target_domain:
            raise ValueError(
                "targeting target domain disagrees with the live unit",
            )
    if live_visibility_m is not None and not math.isclose(
        decision.visibility_bound_m,
        live_visibility_m,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise ValueError(
            "targeting recorded visibility disagrees with the live environment",
        )

    range_policy = None
    if require_current_consumability:
        try:
            range_policy = sensor_environment_range_policy(
                calibration=calibration,
                observer_domain=shooter.domain,
                observer_altitude_m=float(shooter.position.altitude or 0.0),
                observer_acclimatized=getattr(
                    shooter,
                    "acclimatized",
                    False,
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "targeting observer environmental range policy is invalid",
            ) from exc

    weapon_attachment: WeaponAttachment | None = None
    if decision.weapon_id is not None:
        weapon_matches = tuple(
            attachment
            for attachment in loadouts.unit_weapons.get(
                decision.shooter_id,
                (),
            )
            if (
                attachment.source_equipment_index == decision.weapon_source_equipment_index
                and attachment.weapon.weapon_id == decision.weapon_id
                and attachment.modeled_role is decision.weapon_modeled_role
            )
        )
        if len(weapon_matches) != 1:
            raise ValueError(
                "targeting weapon identity does not resolve to one exact live attachment",
            )
        weapon_attachment = weapon_matches[0]
        definition = weapon_attachment.weapon.definition
        authored_effective = float(definition.effective_range_m)
        expected_basis = (
            EffectiveRangeBasis.AUTHORED
            if authored_effective > 0.0
            else EffectiveRangeBasis.LEGACY_DERIVED_80_PERCENT_OF_MAX
        )
        expected_predictive = authored_effective if authored_effective > 0.0 else 0.0
        expected_legacy = float(definition.max_range_m) * 0.8
        if (
            decision.effective_range_basis is not expected_basis
            or not math.isclose(
                decision.physical_max_range_m,
                float(definition.max_range_m),
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
            or not math.isclose(
                decision.predictive_effective_range_m,
                expected_predictive,
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
            or not math.isclose(
                decision.legacy_derived_reference_range_m,
                expected_legacy,
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(
                "targeting range evidence disagrees with the loaded weapon definition",
            )
        if decision.ammunition_id is not None and decision.ammunition_id not in {
            ammunition.ammo_id for ammunition in weapon_attachment.ammunition
        }:
            raise ValueError(
                "targeting ammunition identity is absent from the live weapon attachment",
            )

    sensor_evidence = (
        (
            "contact",
            decision.contact_sensor_source_equipment_index,
            decision.contact_sensor_id,
            decision.contact_sensor_modeled_role,
            decision.contact_range_m,
        ),
        (
            "sensing",
            decision.sensing_sensor_source_equipment_index,
            decision.sensing_sensor_id,
            decision.sensing_sensor_modeled_role,
            decision.sensing_range_m,
        ),
        (
            "fire-control",
            decision.fire_control_sensor_source_equipment_index,
            decision.fire_control_sensor_id,
            decision.fire_control_sensor_modeled_role,
            decision.fire_control_range_m,
        ),
    )
    fire_control_attachment: SensorAttachment | None = None
    for (
        label,
        source_index,
        sensor_id,
        modeled_role,
        live_range_m,
    ) in sensor_evidence:
        if source_index is None:
            continue
        assert sensor_id is not None
        attachment = sensor_attachment_for(
            shooter_id=decision.shooter_id,
            source_index=source_index,
            sensor_id=sensor_id,
            modeled_role=modeled_role,
            evidence_label=label,
        )
        if require_current_consumability:
            assert range_policy is not None
            strict_fow_witness = decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS and label in {
                "contact",
                "sensing",
            }
            try:
                live_sensor_range = float(attachment.sensor.effective_range)
                if not math.isfinite(live_sensor_range) or live_sensor_range < 0.0:
                    raise ValueError(
                        "live sensor range must be finite and non-negative",
                    )
                upper_bound_m = (
                    live_sensor_range
                    if strict_fow_witness
                    else sensor_environment_range_upper_bound_m(
                        policy=range_policy,
                        sensor_type=attachment.sensor.sensor_type,
                        condition_adjusted_range_m=live_sensor_range,
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"targeting {label} live sensor range evidence is invalid",
                ) from exc
            if live_range_m > upper_bound_m + 1e-9:
                if strict_fow_witness:
                    raise ValueError(
                        "targeting FOW witness range exceeds the live sensor range",
                    )
                raise ValueError(
                    f"targeting {label} range exceeds the live sensor environmental range bound",
                )
            optical_attachment = attachment.sensor.sensor_type in {
                SensorType.VISUAL,
                SensorType.NVG,
            }
            if optical_attachment and live_range_m > decision.visibility_bound_m + 1e-9:
                raise ValueError(
                    f"targeting {label} optical range exceeds the recorded visibility bound",
                )
        if label == "fire-control":
            fire_control_attachment = attachment

    if decision.fire_control_source is FireControlSource.SENSOR_ATTACHMENT and (
        fire_control_attachment is None
        or weapon_attachment is None
        or weapon_attachment.source_equipment_index not in fire_control_attachment.compatible_weapon_source_indexes
    ):
        raise ValueError(
            "targeting fire-control evidence disagrees with the mapping-resolved attachment compatibility",
        )

    if decision.contact_source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT:
        evidence = decision.observer_track_support
        assert evidence is not None
        assert decision.contact_sensor_source_equipment_index is not None
        assert decision.contact_sensor_id is not None
        assert decision.contact_sensor_modeled_role is not None
        support_attachment = sensor_attachment_for(
            shooter_id=decision.shooter_id,
            source_index=(decision.contact_sensor_source_equipment_index),
            sensor_id=decision.contact_sensor_id,
            modeled_role=decision.contact_sensor_modeled_role,
            evidence_label="observer track support",
        )
        if support_attachment.sensor.sensor_type is not evidence.sensor_type:
            raise ValueError(
                "targeting observer track support disagrees with its live sensor type",
            )
        if require_current_consumability:
            if not support_attachment.sensor.operational:
                raise ValueError(
                    "targeting observer track support sensor is not operational",
                )
            estimated_range_m = evidence.estimated_range_m(
                observer_easting_m=float(shooter.position.easting),
                observer_northing_m=float(shooter.position.northing),
            )
            if estimated_range_m + evidence.position_uncertainty_m > decision.contact_range_m + 1e-9:
                raise ValueError(
                    "targeting observer track support estimate exceeds its recorded live reach",
                )


def _validate_targeting_live_bindings(
    *,
    plan: TacticalTargetingRestorePlan,
    units: Mapping[str, Unit],
    loadouts: RuntimeLoadouts,
    calibration: Mapping[str, object],
    live_visibility_m: float | None,
) -> None:
    """Match persisted latest-picture identities to live attachments."""

    expected_fog_of_war_enabled = _configured_fog_of_war_enabled(
        calibration,
    )
    interval = plan.prepared_interval
    if interval is not None and interval.fog_of_war_enabled is not expected_fog_of_war_enabled:
        raise ValueError(
            "targeting fog-of-war enablement disagrees with calibration",
        )

    for picture in plan.latest_pictures:
        for decision in picture.decisions:
            _validate_targeting_decision_live_bindings(
                decision=decision,
                units=units,
                loadouts=loadouts,
                calibration=calibration,
                live_visibility_m=live_visibility_m,
                require_current_consumability=True,
            )


def _configured_fog_of_war_enabled(
    calibration: Mapping[str, object],
) -> bool:
    """Return the strict production fog-of-war configuration gate."""
    enabled = calibration.get("enable_fog_of_war", False)
    if type(enabled) is not bool:
        raise ValueError("enable_fog_of_war must be a boolean")
    return enabled


def _fog_sensor_bindings(
    *,
    unit_sides: Mapping[str, str],
    loadouts: RuntimeLoadouts,
) -> tuple[FogOfWarSensorBinding, ...]:
    """Project staged loadouts into the FOW checkpoint's typed boundary."""
    from stochastic_warfare.detection.fog_of_war import (
        FogOfWarSensorBinding,
    )

    bindings = [
        FogOfWarSensorBinding(
            unit_id=unit_id,
            side=unit_sides[unit_id],
            source_equipment_index=attachment.source_equipment_index,
            sensor_id=attachment.sensor_id,
            modeled_role=attachment.modeled_role.value,
            sensor_type=attachment.sensor.sensor_type.name,
        )
        for unit_id in sorted(loadouts.unit_sensor_attachments)
        for attachment in loadouts.unit_sensor_attachments[unit_id]
    ]
    return tuple(
        sorted(
            bindings,
            key=lambda binding: (
                binding.side,
                binding.unit_id,
                binding.source_equipment_index,
                binding.sensor_id,
                binding.modeled_role,
            ),
        ),
    )


def _fog_cadence_restore_bindings(
    *,
    observer_unit_ids: Collection[str],
    lod_tiers: Mapping[str, int],
    calibration: Mapping[str, object],
    unit_sides: Mapping[str, str],
    loadouts: RuntimeLoadouts,
) -> tuple[
    tuple[FogOfWarSensorBinding, ...],
    tuple[Any, ...],
    tuple[Any, ...],
]:
    """Project the exact last-observation roster into cadence sidecars."""
    from stochastic_warfare.detection.cadence import (
        TacticalAttachmentIdentity,
    )
    from stochastic_warfare.detection.fog_of_war import (
        FogOfWarCadenceBinding,
        FogOfWarNativePhaseBinding,
    )

    observer_ids = frozenset(observer_unit_ids)
    if any(type(unit_id) is not str or not unit_id or unit_id != unit_id.strip() for unit_id in observer_ids):
        raise ValueError(
            "FOW cadence observer IDs must be non-empty trimmed strings",
        )
    if not observer_ids <= set(loadouts.unit_sensor_attachments):
        raise ValueError(
            "FOW cadence observers are absent from the runtime loadout roster",
        )
    if not observer_ids <= set(unit_sides):
        raise ValueError(
            "FOW cadence observers are absent from the runtime side roster",
        )

    scan_enabled = calibration.get("enable_scan_scheduling", False)
    lod_enabled = calibration.get("enable_lod", False)
    if type(scan_enabled) is not bool or type(lod_enabled) is not bool:
        raise ValueError("FOW cadence flags must be strict booleans")
    nearby_period = calibration.get("lod_nearby_interval", 5)
    distant_period = calibration.get("lod_distant_interval", 20)
    for value, label in (
        (nearby_period, "lod_nearby_interval"),
        (distant_period, "lod_distant_interval"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive strict integer")

    full_sensor_bindings = _fog_sensor_bindings(
        unit_sides=unit_sides,
        loadouts=loadouts,
    )
    resolved_attachments: dict[TacticalAttachmentIdentity, SensorAttachment] = {}
    native_phase_bindings: list[FogOfWarNativePhaseBinding] = []
    for binding in full_sensor_bindings:
        identity = binding.cadence_identity
        attachments = loadouts.unit_sensor_attachments[binding.unit_id]
        matches = tuple(
            attachment
            for attachment in attachments
            if (
                attachment.source_equipment_index == binding.source_equipment_index
                and attachment.sensor_id == binding.sensor_id
                and attachment.modeled_role.value == binding.modeled_role
            )
        )
        if len(matches) != 1:
            raise ValueError(
                "FOW native phase binding does not resolve one typed runtime attachment",
            )
        attachment = matches[0]
        resolved_attachments[identity] = attachment
        native_phase_bindings.append(
            FogOfWarNativePhaseBinding(
                identity=identity,
                native_period=(attachment.sensor.definition.scan_interval_ticks if scan_enabled else 1),
            ),
        )
    cadence_sensor_bindings = tuple(binding for binding in full_sensor_bindings if binding.unit_id in observer_ids)
    cadence_bindings: list[FogOfWarCadenceBinding] = []
    for binding in cadence_sensor_bindings:
        identity = binding.cadence_identity
        attachment = resolved_attachments[identity]
        native_period = attachment.sensor.definition.scan_interval_ticks if scan_enabled else 1
        if lod_enabled:
            if binding.unit_id not in lod_tiers:
                raise ValueError(
                    "Battle LOD tiers do not cover a persisted FOW observer",
                )
            raw_tier = lod_tiers[binding.unit_id]
            lod_period_by_tier = {
                0: 1,
                1: nearby_period,
                2: distant_period,
            }
            if raw_tier not in lod_period_by_tier:
                raise ValueError("Battle checkpoint contains an invalid LOD tier")
            lod_period = lod_period_by_tier[raw_tier]
        else:
            lod_period = 1
        cadence_bindings.append(
            FogOfWarCadenceBinding(
                identity=identity,
                native_period=native_period,
                current_lod_period=lod_period,
            )
        )
    return (
        cadence_sensor_bindings,
        tuple(cadence_bindings),
        tuple(native_phase_bindings),
    )


def _validate_fow_targeting_bindings(
    *,
    targeting_plan: TacticalTargetingRestorePlan,
    fog_plan: FogOfWarRestorePlan,
    expected_fog_of_war_enabled: bool,
    units: Mapping[str, Unit],
    support_process_noise_std_mps2: float,
    support_max_position_uncertainty_m: float,
) -> None:
    """Bind every retained consumable FOW decision to staged evidence."""
    interval = targeting_plan.prepared_interval
    if type(expected_fog_of_war_enabled) is not bool:
        raise ValueError("expected_fog_of_war_enabled must be a boolean")
    if interval is not None and interval.fog_of_war_enabled is not expected_fog_of_war_enabled:
        raise ValueError(
            "targeting fog-of-war enablement disagrees with calibration",
        )

    witness_map = fog_plan.current_detection_witnesses
    retained_supports = fog_plan.observer_track_supports
    support_by_identity = {support.identity: support for support in retained_supports}
    if len(support_by_identity) != len(retained_supports):
        raise ValueError("FOW observer track support identities are not unique")
    if (
        isinstance(support_process_noise_std_mps2, bool)
        or not isinstance(support_process_noise_std_mps2, (int, float))
        or not math.isfinite(float(support_process_noise_std_mps2))
        or float(support_process_noise_std_mps2) < 0.0
    ):
        raise ValueError("FOW observer support process noise must be finite and non-negative")
    if (
        isinstance(support_max_position_uncertainty_m, bool)
        or not isinstance(support_max_position_uncertainty_m, (int, float))
        or not math.isfinite(float(support_max_position_uncertainty_m))
        or float(support_max_position_uncertainty_m) <= 0.0
    ):
        raise ValueError("FOW observer support maximum uncertainty must be finite and positive")
    world_views = fog_plan.world_views
    fusion = fog_plan.intel_fusion
    fow_track_ids = {
        track_id
        for side_tracks in fusion["tracks"].values()
        for track_id in side_tracks
        if track_id.startswith("fow-track-")
    }
    has_allocated_ordinary_state = bool(
        any(world_view.contacts for world_view in world_views.values())
        or witness_map
        or retained_supports
        or fow_track_ids
        or fusion["fow_track_counters"]
    )
    if not expected_fog_of_war_enabled:
        if has_allocated_ordinary_state:
            raise ValueError(
                "disabled production fog-of-war cannot restore ordinary state",
            )
        return
    if interval is None:
        # Dynamic topology changes deliberately invalidate the prepared
        # targeting interval without erasing durable FOW contacts or the
        # bounded latest witness cache. Their own owner validates that state;
        # there is no retained consumable targeting decision to bind here.
        return

    has_support_decision = any(
        decision.contact_source is ContactSource.FOW_OBSERVER_TRACK_SUPPORT
        for picture in targeting_plan.latest_pictures
        for decision in picture.decisions
    )
    expected_projection_ordinal: int | None = None
    if has_support_decision:
        cadence_state = fog_plan.cadence_state
        committed_ordinal = cadence_state["committed_ordinal"]
        if isinstance(committed_ordinal, bool) or not isinstance(committed_ordinal, int) or committed_ordinal <= 0:
            raise ValueError(
                "Retained consumable FOW targeting interval has no committed cadence ordinal",
            )
        expected_projection_ordinal = committed_ordinal - 1

    witnesses = {
        (
            witness.side,
            witness.observer_unit_id,
            witness.target_id,
            witness.source_equipment_index,
            witness.sensor_id,
            witness.modeled_role,
            witness.logical_time_s,
            witness.range_m,
        ): witness
        for side_witnesses in witness_map.values()
        for witness in side_witnesses
    }
    for picture in targeting_plan.latest_pictures:
        for decision in picture.decisions:
            if decision.contact_source not in {
                ContactSource.FOW_OBSERVER_WITNESS,
                ContactSource.FOW_OBSERVER_TRACK_SUPPORT,
            }:
                continue
            assert decision.target_id is not None
            assert decision.observing_unit_id is not None
            assert decision.contact_sensor_source_equipment_index is not None
            assert decision.contact_sensor_id is not None
            assert decision.contact_sensor_modeled_role is not None
            assert decision.contact_time_s is not None
            world_view = world_views.get(decision.shooter_side)
            contact = None if world_view is None else world_view.contacts.get(decision.target_id)
            if contact is None:
                raise ValueError(
                    "Retained consumable FOW targeting decision target is absent from the reporting-side world view",
                )
            if decision.contact_source is ContactSource.FOW_OBSERVER_WITNESS:
                identity = (
                    decision.shooter_side,
                    decision.observing_unit_id,
                    decision.target_id,
                    decision.contact_sensor_source_equipment_index,
                    decision.contact_sensor_id,
                    decision.contact_sensor_modeled_role.value,
                    decision.contact_time_s,
                    decision.contact_range_m,
                )
                if identity not in witnesses:
                    raise ValueError(
                        "Retained consumable FOW targeting decision has no exact detection witness",
                    )
                if (
                    world_view.last_update_time != decision.contact_time_s
                    or contact.last_sensor_contact_time != decision.contact_time_s
                    or decision.contact_sensor_id not in contact.reporting_sensors
                ):
                    raise ValueError(
                        "Retained consumable FOW targeting decision disagrees with its contact epoch or sensor provenance",
                    )
                continue

            evidence = decision.observer_track_support
            if evidence is None:
                raise ValueError(
                    "Retained FOW observer-support decision has no typed evidence",
                )
            if expected_projection_ordinal is None or evidence.projection_ordinal != expected_projection_ordinal:
                raise ValueError(
                    "Retained FOW observer-support decision projection ordinal disagrees with the staged cadence owner",
                )
            retained = support_by_identity.get(evidence.identity)
            if retained is None:
                raise ValueError(
                    "Retained FOW observer-support decision has no exact owner state",
                )
            try:
                projected = retained.project(
                    projection_ordinal=evidence.projection_ordinal,
                    projection_time_s=decision.contact_time_s,
                    process_noise_std_mps2=float(
                        support_process_noise_std_mps2,
                    ),
                )
            except ValueError as exc:
                raise ValueError(
                    "Retained FOW observer-support decision cannot be projected from owner state",
                ) from exc
            if projected != evidence:
                raise ValueError(
                    "Retained FOW observer-support decision disagrees with its exact owner projection",
                )
            shooter = units.get(decision.shooter_id)
            if shooter is None or not evidence.is_within_limits(
                observer_easting_m=float(shooter.position.easting),
                observer_northing_m=float(shooter.position.northing),
                reach_m=decision.contact_range_m,
                max_position_uncertainty_m=float(
                    support_max_position_uncertainty_m,
                ),
            ):
                raise ValueError(
                    "Retained FOW observer-support decision exceeds live reach or uncertainty",
                )
            if (
                world_view.last_update_time != decision.contact_time_s
                or contact.last_sensor_contact_time > decision.contact_time_s
                or contact.track.status in {TrackStatus.STALE, TrackStatus.LOST}
                or contact.track.track_id != evidence.fusion_track_id
                or evidence.fusion_track_id not in fusion["tracks"].get(decision.shooter_side, {})
                or decision.contact_sensor_id not in contact.reporting_sensors
            ):
                raise ValueError(
                    "Retained FOW observer-support decision disagrees with its live contact or fusion generation",
                )


def _validate_movement_targeting_restore_bindings(
    *,
    movement_plan: Any,
    targeting_plan: TacticalTargetingRestorePlan,
    units: Mapping[str, Unit],
    loadouts: RuntimeLoadouts,
    calibration: Mapping[str, object],
) -> None:
    """Validate every retained movement decision before checkpoint commit."""
    picture_by_identity = {
        (picture.engine_tick, picture.battle_id): picture for picture in targeting_plan.latest_pictures
    }
    prepared_interval = targeting_plan.prepared_interval
    for summary in movement_plan.units:
        for observation in summary.recent_observations:
            decision = observation.targeting_decision
            if decision is None:
                continue
            _validate_targeting_decision_live_bindings(
                decision=decision,
                units=units,
                loadouts=loadouts,
                calibration=calibration,
                live_visibility_m=None,
                require_current_consumability=False,
            )
            membership = observation.targeting_membership
            if membership is None:
                raise ValueError(
                    "movement targeting evidence is missing its exact battle membership snapshot",
                )
            members = membership.unit_ids
            if decision.shooter_id not in members or (
                decision.target_id is not None and decision.target_id not in members
            ):
                raise ValueError(
                    "movement targeting evidence disagrees with retained battle membership",
                )
            if (
                prepared_interval is not None
                and prepared_interval.engine_tick == decision.engine_tick
                and prepared_interval.battle_memberships.get(
                    decision.battle_id,
                )
                != members
            ):
                raise ValueError(
                    "movement targeting evidence disagrees with the exact same-tick targeting interval membership",
                )
            picture = picture_by_identity.get(
                (
                    decision.engine_tick,
                    decision.battle_id,
                )
            )
            if picture is None:
                continue
            restored = picture.decision_for(decision.shooter_id)
            if restored is None:
                raise ValueError(
                    "movement targeting evidence has no matching persisted picture decision",
                )
            if decision != restored:
                raise ValueError(
                    "movement targeting evidence disagrees with the exact persisted picture decision",
                )


@dataclass(frozen=True, slots=True)
class _CheckpointAggregateMoraleTopology:
    """Validated aggregate constituent IDs and captured unit statuses."""

    constituents: dict[str, tuple[str, ...]]
    statuses: dict[str, UnitStatus]
    proxy_expectations: dict[str, tuple[str, str, tuple[float, ...]]]
    original_indexes: dict[str, tuple[int, ...]]
    proxy_domains: dict[str, Domain]


def _checkpoint_aggregate_morale_topology(
    raw_aggregation: Any,
) -> _CheckpointAggregateMoraleTopology:
    """Parse aggregate morale topology and statuses in one strict pass."""
    if raw_aggregation is None:
        return _CheckpointAggregateMoraleTopology({}, {}, {}, {}, {})
    if not isinstance(raw_aggregation, dict):
        raise ValueError("Checkpoint aggregation_engine must be a mapping")
    raw_aggregates = raw_aggregation.get("aggregates", {})
    if not isinstance(raw_aggregates, dict):
        raise ValueError(
            "Checkpoint aggregation_engine.aggregates must be a mapping",
        )
    result: dict[str, tuple[str, ...]] = {}
    statuses: dict[str, UnitStatus] = {}
    proxy_expectations: dict[
        str,
        tuple[str, str, tuple[float, ...]],
    ] = {}
    original_indexes: dict[str, tuple[int, ...]] = {}
    proxy_domains: dict[str, Domain] = {}
    seen_constituents: set[str] = set()
    for aggregate_id in sorted(raw_aggregates):
        raw_aggregate = raw_aggregates[aggregate_id]
        if not isinstance(aggregate_id, str) or not aggregate_id:
            raise ValueError("Checkpoint aggregate IDs must be non-empty strings")
        if not isinstance(raw_aggregate, dict):
            raise ValueError("Checkpoint aggregate entries must be mappings")
        if raw_aggregate.get("aggregate_id") != aggregate_id:
            raise ValueError(
                f"Checkpoint aggregate identity mismatch for {aggregate_id!r}",
            )
        raw_side = raw_aggregate.get("side")
        raw_unit_type = raw_aggregate.get("unit_type")
        raw_position = raw_aggregate.get("position")
        if (
            not isinstance(raw_side, str)
            or not raw_side
            or not isinstance(raw_unit_type, str)
            or not raw_unit_type
            or not isinstance(raw_position, (list, tuple))
            or len(raw_position) not in {2, 3}
            or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value))
                for value in raw_position
            )
        ):
            raise ValueError(
                f"Checkpoint aggregate {aggregate_id!r} proxy is malformed",
            )
        proxy_expectations[aggregate_id] = (
            raw_side,
            raw_unit_type,
            tuple(Position(*raw_position)),
        )
        raw_snapshots = raw_aggregate.get("snapshots")
        if not isinstance(raw_snapshots, list) or not raw_snapshots:
            raise ValueError(
                f"Checkpoint aggregate {aggregate_id!r} requires snapshots",
            )
        constituent_ids: list[str] = []
        constituent_domains: set[Domain] = set()
        for raw_snapshot in raw_snapshots:
            if not isinstance(raw_snapshot, dict) or set(raw_snapshot) != {
                "unit_state",
                "weapon_states",
                "sensor_states",
                "supply_inventory",
                "original_side",
                "original_index",
                "order_records",
            }:
                raise ValueError("Checkpoint aggregate snapshots must be mappings")
            raw_unit = raw_snapshot.get("unit_state")
            if not isinstance(raw_unit, dict):
                raise ValueError(
                    "Checkpoint aggregate unit_state must be a mapping",
                )
            if (
                raw_unit.get("unit_class") != Unit.__name__
                or raw_unit.get("equipment") != []
                or not isinstance(raw_snapshot["original_side"], str)
                or not raw_snapshot["original_side"]
                or raw_snapshot["original_side"] != raw_snapshot["original_side"].strip()
                or raw_unit.get("side") != raw_snapshot["original_side"]
                or raw_snapshot["original_side"] != raw_side
                or raw_snapshot["weapon_states"] != []
                or raw_snapshot["sensor_states"] != []
                or raw_snapshot["supply_inventory"] is not None
                or raw_snapshot["order_records"] != []
            ):
                raise ValueError(
                    "REM-016: checkpoint aggregation supports only exact "
                    "base-Unit, equipmentless, no-supply/no-order snapshots",
                )
            unit_id = raw_unit.get("entity_id")
            raw_status = raw_unit.get("status")
            raw_domain = raw_unit.get("domain")
            raw_original_index = raw_snapshot["original_index"]
            if not isinstance(unit_id, str) or not unit_id:
                raise ValueError(
                    "Checkpoint aggregate constituent IDs must be non-empty strings",
                )
            if isinstance(raw_status, bool) or not isinstance(raw_status, int):
                raise ValueError(
                    "Checkpoint aggregate constituent status is malformed",
                )
            if isinstance(raw_domain, bool) or not isinstance(raw_domain, int):
                raise ValueError(
                    "Checkpoint aggregate constituent domain is malformed",
                )
            try:
                constituent_domains.add(Domain(raw_domain))
            except ValueError as exc:
                raise ValueError(
                    "Checkpoint aggregate constituent domain is unknown",
                ) from exc
            if (
                isinstance(raw_original_index, bool)
                or not isinstance(raw_original_index, int)
                or raw_original_index < 0
            ):
                raise ValueError(
                    "Checkpoint aggregate constituent original_index is malformed",
                )
            if raw_status != int(UnitStatus.ACTIVE):
                raise ValueError(
                    "Checkpoint suspended morale/status disagree: aggregate snapshots must capture ACTIVE constituents",
                )
            if unit_id in seen_constituents:
                raise ValueError(
                    f"Duplicate aggregate constituent ID {unit_id!r}",
                )
            seen_constituents.add(unit_id)
            constituent_ids.append(unit_id)
            try:
                statuses[unit_id] = UnitStatus(raw_status)
            except ValueError as exc:
                raise ValueError(
                    f"Unknown aggregate constituent status for {unit_id!r}",
                ) from exc
        aggregate_indexes = tuple(raw_snapshot["original_index"] for raw_snapshot in raw_snapshots)
        if len(aggregate_indexes) != len(set(aggregate_indexes)):
            raise ValueError(
                f"Checkpoint aggregate {aggregate_id!r} original indexes must be unique",
            )
        if len(constituent_domains) != 1:
            raise ValueError(
                "REM-016: aggregate constituents must share one exact domain",
            )
        result[aggregate_id] = tuple(sorted(constituent_ids))
        original_indexes[aggregate_id] = aggregate_indexes
        proxy_domains[aggregate_id] = next(iter(constituent_domains))
    return _CheckpointAggregateMoraleTopology(
        result,
        statuses,
        proxy_expectations,
        original_indexes,
        proxy_domains,
    )


def _checkpoint_declares_empty_runtime_loadout(
    state: Mapping[str, Any],
    *,
    unit_id: str,
) -> bool:
    """Return whether a checkpoint declares exact empty runtime bindings."""
    for key in (
        "unit_weapon_states",
        "unit_sensor_states",
        "loadout_topology",
    ):
        owner = state.get(key)
        if not isinstance(owner, dict) or unit_id not in owner or owner[unit_id] != []:
            return False
    return True


def _checkpoint_has_active_routes(raw_rout_state: Any) -> bool:
    """Return whether a validated-enough rout envelope is non-empty."""
    if raw_rout_state is None:
        return False
    if not isinstance(raw_rout_state, dict):
        raise ValueError("Checkpoint rout_engine state must be a mapping")
    raw_routes = raw_rout_state.get("active_routs", {})
    if not isinstance(raw_routes, dict):
        raise ValueError("Checkpoint active_routs must be a mapping")
    return bool(raw_routes)


def _legacy_morale_value(value: Any, *, owner: str, unit_id: str) -> Any:
    """Parse one strict legacy context or machine morale value."""
    try:
        if owner == "context" and isinstance(value, str):
            return MoraleState[value]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("must be an integer enum value")
        return MoraleState(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid legacy {owner} morale for {unit_id!r}: {value!r}",
        ) from exc


def _migrate_legacy_morale_runtime(
    *,
    context_morale: Any,
    machine_state: Any,
    units: Mapping[str, Unit],
    side_initial: Mapping[str, str],
    elapsed_time_s: float,
    continuous_time: bool,
    authoritative_rng_state: Any,
    rout_state: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Build one bounded format-113 morale envelope from versionless state."""
    if continuous_time and elapsed_time_s > 0.0:
        raise ValueError(
            "A started continuous-time runtime cannot reconstruct legacy morale check history",
        )
    if context_morale is None:
        raw_context: Mapping[str, Any] = {}
    elif isinstance(context_morale, dict):
        raw_context = context_morale
    else:
        raise ValueError("Legacy morale_states must be a mapping")

    raw_machine_units: Mapping[str, Any] = {}
    if machine_state is not None:
        if not isinstance(machine_state, dict):
            raise ValueError("Legacy morale_machine must be a mapping")
        if set(machine_state) != {"unit_states", "rng_state"}:
            raise ValueError(
                "Legacy morale_machine has invalid key topology",
            )
        raw_machine_units = machine_state["unit_states"]
        if not isinstance(raw_machine_units, dict):
            raise ValueError(
                "Legacy morale_machine.unit_states must be a mapping",
            )
        if not _json_values_equal(
            machine_state["rng_state"],
            authoritative_rng_state,
        ):
            raise ValueError(
                "Legacy morale_machine RNG disagrees with RNGManager",
            )

    normalized_rout_state: dict[str, Any] | None = None
    if rout_state is not None:
        if not isinstance(rout_state, dict):
            raise ValueError("Legacy rout_engine must be a mapping")
        if set(rout_state) != {"active_routs", "rng_state"}:
            raise ValueError(
                "Legacy rout_engine has invalid key topology",
            )
        if not _json_values_equal(
            rout_state["rng_state"],
            authoritative_rng_state,
        ):
            raise ValueError(
                "Legacy rout_engine RNG disagrees with RNGManager",
            )
        normalized_rout_state = {
            "active_routs": copy.deepcopy(rout_state["active_routs"]),
        }

    expected_ids = set(units)
    extra_context = set(raw_context) - expected_ids
    extra_machine = set(raw_machine_units) - expected_ids
    if extra_context:
        raise ValueError(
            f"Legacy morale_states contains units outside the force roster: {sorted(extra_context)!r}",
        )
    if extra_machine:
        raise ValueError(
            f"Legacy morale_machine contains units outside the force roster: {sorted(extra_machine)!r}",
        )

    active_records: dict[str, dict[str, Any]] = {}
    for unit_id in sorted(expected_ids):
        context_value = raw_context.get(unit_id)
        context_state = (
            _legacy_morale_value(
                context_value,
                owner="context",
                unit_id=unit_id,
            )
            if unit_id in raw_context
            else None
        )

        machine_morale = None
        transition_time: float | None = None
        generation = 0
        if unit_id in raw_machine_units:
            raw_record = raw_machine_units[unit_id]
            if not isinstance(raw_record, dict):
                raise ValueError(
                    f"Legacy morale record for {unit_id!r} must be a mapping",
                )
            if set(raw_record) != {
                "current_state",
                "transition_cooldown_s",
                "last_transition_time",
            }:
                raise ValueError(
                    f"Legacy morale record for {unit_id!r} has invalid keys",
                )
            machine_morale = _legacy_morale_value(
                raw_record["current_state"],
                owner="machine",
                unit_id=unit_id,
            )
            cooldown = raw_record["transition_cooldown_s"]
            if (
                isinstance(cooldown, bool)
                or not isinstance(cooldown, (int, float))
                or not math.isfinite(float(cooldown))
                or float(cooldown) != 0.0
            ):
                raise ValueError(
                    f"Legacy per-record transition_cooldown_s must be the canonical inert 0.0 for {unit_id!r}",
                )
            raw_time = raw_record["last_transition_time"]
            if (
                isinstance(raw_time, bool)
                or not isinstance(raw_time, (int, float))
                or not math.isfinite(float(raw_time))
            ):
                raise ValueError(
                    f"Legacy transition time for {unit_id!r} is invalid",
                )
            normalized_time = float(raw_time)
            if normalized_time == -1e9:
                transition_time = None
            elif 0.0 <= normalized_time <= elapsed_time_s:
                transition_time = normalized_time
                generation = 1
            else:
                raise ValueError(
                    f"Legacy transition time for {unit_id!r} is impossible",
                )

        if context_state is not None and machine_morale is not None and context_state is not machine_morale:
            raise ValueError(
                f"Legacy morale stores disagree for unit {unit_id!r}",
            )

        chosen_state = machine_morale if machine_morale is not None else context_state
        if chosen_state is None:
            side = units[unit_id].side
            side_name = side if isinstance(side, str) else side.value
            try:
                chosen_state = MoraleState[side_initial[side_name]]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Cannot backfill legacy morale for unit {unit_id!r}",
                ) from exc

        active_records[unit_id] = {
            "current_state": int(chosen_state),
            "last_transition_time_s": transition_time,
            "last_check_time_s": transition_time,
            "generation": generation,
        }

    return (
        {
            "active_records": active_records,
            "suspended_archives": {},
        },
        normalized_rout_state,
    )


def _initial_morale_for_units(
    config: CampaignScenarioConfig,
    units: list[Unit],
) -> dict[str, MoraleState]:
    """Derive typed side morale without mutating caller-owned units."""
    state_by_side = {side.side: MoraleState[side.morale_initial] for side in config.sides}
    result: dict[str, MoraleState] = {}
    for unit in units:
        side = unit.side if isinstance(unit.side, str) else unit.side.value
        try:
            morale = state_by_side[side]
        except KeyError as exc:
            raise ValueError(
                f"Unit {unit.entity_id!r} references unknown side {side!r}",
            ) from exc
        result[unit.entity_id] = morale
    return result


def _initial_status_for_morale(morale: MoraleState) -> UnitStatus:
    """Return the required initial unit-status projection for morale."""
    if morale is MoraleState.ROUTED:
        return UnitStatus.ROUTING
    if morale is MoraleState.SURRENDERED:
        return UnitStatus.SURRENDERED
    return UnitStatus.ACTIVE


_CONTEXT_STATE_ENGINE_NAMES = (
    "ooda_engine",
    "planning_engine",
    "order_execution",
    "logistics_runtime",
    "stockpile_manager",
    "fog_of_war",
    "aggregation_engine",
    "space_engine",
    "cbrn_engine",
    "school_registry",
    "trench_engine",
    "barrage_engine",
    "gas_warfare_engine",
    "volley_fire_engine",
    "melee_engine",
    "cavalry_engine",
    "formation_napoleonic_engine",
    "courier_engine",
    "foraging_engine",
    "archery_engine",
    "siege_engine",
    "formation_ancient_engine",
    "naval_oar_engine",
    "visual_signals_engine",
    "escalation_engine",
    "political_engine",
    "consequence_engine",
    "unconventional_engine",
    "insurgency_engine",
    "sof_engine",
    "war_termination_engine",
    "incendiary_engine",
    "uxo_engine",
    "commander_engine",
    "eccm_engine",
    "sigint_engine",
    "ew_decoy_engine",
    "dew_engine",
    "indirect_fire_engine",
    "naval_surface_engine",
    "naval_subsurface_engine",
    "naval_gunfire_support_engine",
    "mine_warfare_engine",
    "disruption_engine",
    "maintenance_engine",
    "medical_engine",
    "engineering_engine",
    "collateral_engine",
    "weather_engine",
    "sea_state_engine",
    "stratagem_engine",
    "iads_engine",
    "ato_engine",
    "underwater_acoustics_engine",
    "carrier_ops_engine",
    "comms_engine",
    "detection_engine",
    "movement_engine",
    "movement_diagnostics",
    "tactical_targeting",
    "conditions_engine",
    "engagement_engine",
    "suppression_engine",
    "air_combat_engine",
    "air_ground_engine",
    "air_defense_engine",
    "missile_engine",
    "missile_defense_engine",
    "naval_gunnery_engine",
    "convoy_engine",
    "strategic_bombing_engine",
    "time_of_day_engine",
    "seasons_engine",
    "obscurants_engine",
    "order_propagation",
    "assessor",
    "decision_engine",
    "adaptation_engine",
    "roe_engine",
    "rout_engine",
    "ew_engine",
    "consumption_engine",
    "supply_network_engine",
    "command_engine",
)

_TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES = frozenset(
    {
        "commander_engine",
        "fog_of_war",
        "indirect_fire_engine",
        "logistics_runtime",
        "movement_diagnostics",
        "obscurants_engine",
        "ooda_engine",
        "rout_engine",
        "school_registry",
        "space_engine",
        "tactical_targeting",
    },
)
_STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES = frozenset(
    {
        # MovementEngine owns immutable routing algorithms; per-unit movement
        # state lives on units and MovementDiagnostics.
        "movement_engine",
    },
)
_LEGACY_CONTEXT_CHECKPOINT_OWNER_NAMES = tuple(
    name
    for name in _CONTEXT_STATE_ENGINE_NAMES
    if name not in _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES
    and name not in _STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES
)

_CLASSIFIED_CONTEXT_CHECKPOINT_OWNER_NAMES = (
    _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES
    | _STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES
    | set(_LEGACY_CONTEXT_CHECKPOINT_OWNER_NAMES)
)
if not (
    _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES
    | _STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES
).issubset(_CONTEXT_STATE_ENGINE_NAMES):
    raise RuntimeError(
        "context checkpoint-owner classifications contain unknown names",
    )
if (
    set(_LEGACY_CONTEXT_CHECKPOINT_OWNER_NAMES)
    & _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES
    or set(_LEGACY_CONTEXT_CHECKPOINT_OWNER_NAMES)
    & _STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES
    or _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES
    & _STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES
):
    raise RuntimeError("context checkpoint-owner classifications overlap")
if _CLASSIFIED_CONTEXT_CHECKPOINT_OWNER_NAMES != set(
    _CONTEXT_STATE_ENGINE_NAMES,
):
    raise RuntimeError("context checkpoint-owner classifications are incomplete")


def _checkpoint_owner_disposition(
    name: str,
) -> CheckpointOwnerDisposition:
    """Return the static checkpoint contract for one registered owner name."""
    if name in _TYPED_CONTEXT_CHECKPOINT_OWNER_NAMES:
        return CheckpointOwnerDisposition.TYPED_ATOMIC
    if name in _STATELESS_CONTEXT_CHECKPOINT_OWNER_NAMES:
        return CheckpointOwnerDisposition.STATELESS
    if name in _LEGACY_CONTEXT_CHECKPOINT_OWNER_NAMES:
        return CheckpointOwnerDisposition.LEGACY_CLONE
    raise ValueError(f"Unknown context checkpoint owner {name!r}")


def _bind_context_checkpoint_owner(
    name: str,
    owner: object | None,
) -> ContextCheckpointOwnerBinding:
    """Bind one owner to its explicit checkpoint protocol."""
    binding = ContextCheckpointOwnerBinding(
        name=name,
        owner=owner,
        disposition=_checkpoint_owner_disposition(name),
    )
    if owner is None:
        return binding
    if binding.disposition is CheckpointOwnerDisposition.STATELESS:
        return binding
    if binding.disposition is CheckpointOwnerDisposition.TYPED_ATOMIC:
        if not isinstance(owner, AtomicCheckpointOwner):
            raise TypeError(
                f"Context checkpoint owner {name!r} is classified typed_atomic "
                "but lacks get_state/stage_state/commit_state",
            )
    elif not isinstance(owner, LegacyCheckpointOwner):
        raise TypeError(
            f"Context checkpoint owner {name!r} is classified legacy_clone "
            "but lacks get_state/set_state",
        )
    return binding


def _capture_context_checkpoint_owner(
    binding: ContextCheckpointOwnerBinding,
) -> Any:
    """Capture one already-classified non-null owner."""
    owner = binding.owner
    if owner is None:
        raise RuntimeError(
            f"Cannot capture absent context checkpoint owner {binding.name!r}",
        )
    if binding.disposition is CheckpointOwnerDisposition.TYPED_ATOMIC:
        if not isinstance(owner, AtomicCheckpointOwner):
            raise RuntimeError(
                f"Typed checkpoint owner {binding.name!r} changed protocol",
            )
        return owner.get_state()
    if not isinstance(owner, LegacyCheckpointOwner):
        raise RuntimeError(
            f"Legacy checkpoint owner {binding.name!r} changed protocol",
        )
    return owner.get_state()


def _stage_legacy_context_checkpoint_owner(
    binding: ContextCheckpointOwnerBinding,
    raw_state: Any,
    *,
    event_bus: EventBus,
    authoritative_detection_rng_state: Any,
) -> LegacyCheckpointRestorePlan:
    """Preflight one explicitly legacy owner on an isolated clone."""
    owner = binding.owner
    if (
        binding.disposition is not CheckpointOwnerDisposition.LEGACY_CLONE
        or owner is None
        or not isinstance(owner, LegacyCheckpointOwner)
    ):
        raise TypeError(
            f"Context checkpoint owner {binding.name!r} is not a bound legacy owner",
        )
    try:
        staged_owner = copy.deepcopy(
            owner,
            {id(event_bus): EventBus()},
        )
        staged_owner.set_state(copy.deepcopy(raw_state))
        canonical_state = staged_owner.get_state()
        if binding.name == "detection_engine" and not _json_values_equal(
            canonical_state.get("rng_state"),
            authoritative_detection_rng_state,
        ):
            raise ValueError(
                "DetectionEngine RNG mirror disagrees with RNGManager DETECTION state",
            )
        canonical_comparison = canonical_state
        if (
            binding.name == "planning_engine"
            and isinstance(raw_state, dict)
            and "checkpoint_schema" not in raw_state
        ):
            # PlanningProcessEngine upgrades its old markerless nested format
            # after strict staging.  Compare against the exact legacy
            # projection, then commit the canonical marked state.
            canonical_comparison = copy.deepcopy(canonical_state)
            canonical_comparison.pop("checkpoint_schema")
            for raw_planning_state in canonical_comparison["states"].values():
                raw_planning_state.pop("selected_result")
        if not _json_values_equal(
            _json_compatible_value(raw_state),
            _json_compatible_value(canonical_comparison),
        ):
            raise ValueError("state does not round-trip canonically")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid checkpoint {binding.name} state: {exc}",
        ) from exc
    return LegacyCheckpointRestorePlan(
        owner_id=id(owner),
        name=binding.name,
        canonical_state=canonical_state,
    )


def _commit_legacy_context_checkpoint_owner(
    binding: ContextCheckpointOwnerBinding,
    plan: LegacyCheckpointRestorePlan,
) -> None:
    """Commit a previously validated legacy-owner restore plan."""
    owner = binding.owner
    if (
        binding.disposition is not CheckpointOwnerDisposition.LEGACY_CLONE
        or owner is None
        or not isinstance(owner, LegacyCheckpointOwner)
    ):
        raise TypeError(
            f"Context checkpoint owner {binding.name!r} is not a bound legacy owner",
        )
    if plan.owner_id != id(owner) or plan.name != binding.name:
        raise ValueError(
            f"Legacy checkpoint plan does not belong to owner {binding.name!r}",
        )
    owner.set_state(plan.canonical_state)

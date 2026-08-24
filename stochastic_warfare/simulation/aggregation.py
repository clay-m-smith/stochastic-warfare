"""Force aggregation and disaggregation for large-scale campaigns.

Provides :class:`AggregationEngine` which captures, merges, and restores
per-unit state across all subsystems.  Units far from active battles are
aggregated into composite formations; they disaggregate when they
approach the battle area.

Phase 13a-7.
"""

from __future__ import annotations

import copy
import math
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.runtime_failure import RuntimeFailureHandler
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.runtime import MoraleRuntime
from stochastic_warfare.simulation.loadouts import RuntimeLoadouts
from stochastic_warfare.simulation.tactical_targeting import (
    TacticalTargetingRestorePlan,
    TacticalTargetingRuntime,
)

logger = get_logger(__name__)

_LOADOUT_OWNER_NAMES = (
    "unit_weapons",
    "unit_sensor_attachments",
    "unit_sensors",
    "equipment_resolutions",
)
UNSUPPORTED_AGGREGATION_OWNER_NAMES: tuple[str, ...] = (
    "stockpile_manager",
    "movement_diagnostics",
    "fog_of_war",
    "space_engine",
    "ooda_engine",
    "commander_engine",
    "school_registry",
    "logistics_runtime",
    "force_builder",
    "loadout_builder",
    "suppression_engine",
    "maintenance_engine",
    "medical_engine",
    "consumption_engine",
    "supply_network_engine",
    "command_engine",
    "comms_engine",
    "order_propagation",
    "order_execution",
    "ato_engine",
    "cbrn_engine",
    "planning_engine",
    "roe_engine",
)
_SUPPORTED_AGGREGATION_CONTEXT_OWNER_NAMES = frozenset({
    "aggregation_engine",
    "rout_engine",
    "tactical_targeting",
})

_AGGREGATION_STATE_KEYS = frozenset({"config", "next_id", "aggregates"})
_AGGREGATION_CONFIG_KEYS = frozenset({
    "enable_aggregation",
    "aggregation_distance_m",
    "min_units_to_aggregate",
    "disaggregate_distance_m",
})
_AGGREGATE_STATE_KEYS = frozenset({
    "aggregate_id",
    "side",
    "unit_type",
    "position",
    "aggregate_combat_power",
    "aggregate_personnel",
    "aggregate_supply_state",
    "snapshots",
})
_SNAPSHOT_STATE_KEYS = frozenset({
    "unit_state",
    "weapon_states",
    "sensor_states",
    "supply_inventory",
    "original_side",
    "original_index",
    "order_records",
})
_BASE_UNIT_STATE_KEYS = frozenset({
    "entity_id",
    "position",
    "unit_class",
    "name",
    "unit_type",
    "side",
    "domain",
    "status",
    "heading",
    "speed",
    "max_speed",
    "training_level",
    "weight_tons",
    "personnel",
    "equipment",
})
_PERSONNEL_STATE_KEYS = frozenset({
    "member_id",
    "role",
    "skill",
    "experience",
    "injury",
    "fatigue",
})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class AggregationConfig(BaseModel):
    """Tuning parameters for force aggregation."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    enable_aggregation: bool = False
    aggregation_distance_m: float = 50_000.0
    """Min distance from active battle to be eligible for aggregation."""

    min_units_to_aggregate: int = 4
    """Minimum group size to aggregate."""

    disaggregate_distance_m: float = 20_000.0
    """Disaggregate when this close to an active battle."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class UnitSnapshot:
    """Complete serialized state of a single unit across all subsystems."""

    unit_state: dict
    weapon_states: list[dict] = field(default_factory=list)
    sensor_states: list[dict] = field(default_factory=list)
    supply_inventory: dict | None = None
    original_side: str = ""
    original_index: int = 0
    order_records: list[dict] = field(default_factory=list)  # Phase 85


@dataclass
class AggregateUnit:
    """A formation-level composite replacing multiple individual units."""

    aggregate_id: str
    side: str
    unit_type: str
    position: Position
    constituent_snapshots: list[UnitSnapshot]
    aggregate_combat_power: float
    aggregate_personnel: int
    aggregate_supply_state: float
    parent_id: str | None = None


def _state_values_equal(left: Any, right: Any) -> bool:
    """Compare state strictly while accepting JSON list/tuple representation."""
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _state_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _state_values_equal(left[key], right[key])
            for key in left
        )
    return bool(left == right)


def _reject_nonfinite_state(value: Any, *, path: str) -> None:
    """Reject non-finite numbers anywhere in an aggregation checkpoint."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite numbers")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _reject_nonfinite_state(nested, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_nonfinite_state(nested, path=f"{path}[{index}]")


def _strict_non_negative_int(value: Any, *, label: str) -> int:
    """Return one strict non-negative integer or reject the checkpoint."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative strict integer")
    return value


def _strict_finite_number(
    value: Any,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Return one finite number satisfying the declared closed bounds."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} must be a finite number")
    parsed = float(value)
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{label} must be at least {minimum:g}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{label} must be at most {maximum:g}")
    return parsed


def _stage_aggregation_config(raw_config: Any) -> AggregationConfig:
    """Stage one exact, immutable aggregation configuration."""
    if (
        not isinstance(raw_config, dict)
        or set(raw_config) != _AGGREGATION_CONFIG_KEYS
    ):
        raise ValueError("Aggregation config has invalid key topology")
    try:
        return AggregationConfig.model_validate(raw_config, strict=True)
    except ValueError as exc:
        raise ValueError(f"Aggregation config is invalid: {exc}") from exc


def _aggregate_ordinal(aggregate_id: Any) -> int:
    """Parse the canonical engine-owned aggregate identifier namespace."""
    if not isinstance(aggregate_id, str) or not aggregate_id.startswith("agg_"):
        raise ValueError("Aggregation IDs must use the canonical agg_#### form")
    suffix = aggregate_id.removeprefix("agg_")
    if not suffix.isdigit() or len(suffix) < 4:
        raise ValueError("Aggregation IDs must use the canonical agg_#### form")
    ordinal = int(suffix)
    if suffix != f"{ordinal:04d}":
        raise ValueError("Aggregation IDs must use the canonical agg_#### form")
    return ordinal


def _stage_base_unit_state(raw_unit: Any, *, side: str) -> dict[str, Any]:
    """Strictly validate one reconstructable base-Unit checkpoint payload."""
    if not isinstance(raw_unit, dict) or set(raw_unit) != _BASE_UNIT_STATE_KEYS:
        raise ValueError(
            "Aggregate constituent unit_state has invalid key topology",
        )
    _reject_nonfinite_state(raw_unit, path="aggregation constituent")
    unit_id = raw_unit.get("entity_id")
    if not isinstance(unit_id, str) or not unit_id:
        raise ValueError("Aggregate constituent ID must be a non-empty string")
    if raw_unit.get("unit_class") != Unit.__name__:
        raise _rem016_unsupported(
            f"snapshot {unit_id!r} is not an exact base Unit",
        )
    if raw_unit.get("side") != side:
        raise _rem016_unsupported(
            f"snapshot {unit_id!r} side disagrees with its archive",
        )
    raw_position = raw_unit.get("position")
    if (
        not isinstance(raw_position, (list, tuple))
        or len(raw_position) != 3
    ):
        raise ValueError(
            f"Aggregate constituent {unit_id!r} position is malformed",
        )
    for index, coordinate in enumerate(raw_position):
        _strict_finite_number(
            coordinate,
            label=f"aggregate constituent {unit_id!r} position[{index}]",
        )
    for field_name in ("name", "unit_type", "side"):
        field_value = raw_unit.get(field_name)
        if (
            not isinstance(field_value, str)
            or (field_name in {"unit_type", "side"} and not field_value)
        ):
            raise ValueError(
                f"Aggregate constituent {unit_id!r} {field_name} must be a "
                "string",
            )
    for field_name in ("domain", "status"):
        value = raw_unit.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"Aggregate constituent {unit_id!r} {field_name} must be a "
                "strict integer",
            )
    for field_name in (
        "heading",
        "speed",
        "max_speed",
        "training_level",
        "weight_tons",
    ):
        lower = 0.0 if field_name != "heading" else None
        upper = 1.0 if field_name == "training_level" else None
        _strict_finite_number(
            raw_unit.get(field_name),
            label=f"aggregate constituent {unit_id!r} {field_name}",
            minimum=lower,
            maximum=upper,
        )
    if raw_unit.get("equipment") != []:
        raise _rem016_unsupported(
            f"snapshot {unit_id!r} carries equipment",
        )
    raw_personnel = raw_unit.get("personnel")
    if not isinstance(raw_personnel, list):
        raise ValueError(
            f"Aggregate constituent {unit_id!r} personnel must be a list",
        )
    for index, member in enumerate(raw_personnel):
        if not isinstance(member, dict) or set(member) != _PERSONNEL_STATE_KEYS:
            raise ValueError(
                f"Aggregate constituent {unit_id!r} personnel[{index}] has "
                "invalid key topology",
            )
        if not isinstance(member["member_id"], str) or not member["member_id"]:
            raise ValueError(
                f"Aggregate constituent {unit_id!r} personnel[{index}] has "
                "an invalid member_id",
            )
        for enum_field in ("role", "skill", "injury"):
            enum_value = member[enum_field]
            if isinstance(enum_value, bool) or not isinstance(enum_value, int):
                raise ValueError(
                    f"Aggregate constituent {unit_id!r} personnel[{index}] "
                    f"{enum_field} must be a strict integer",
                )
        for numeric_field in ("experience", "fatigue"):
            _strict_finite_number(
                member[numeric_field],
                label=(
                    f"aggregate constituent {unit_id!r} personnel[{index}] "
                    f"{numeric_field}"
                ),
                minimum=0.0,
                maximum=1.0,
            )
    try:
        staged = Unit(unit_id, Position(0.0, 0.0, 0.0))
        staged.set_state(copy.deepcopy(raw_unit))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid aggregate constituent {unit_id!r}: {exc}",
        ) from exc
    if not _state_values_equal(raw_unit, staged.get_state()):
        raise ValueError(
            f"Aggregate constituent {unit_id!r} does not round-trip canonically",
        )
    return copy.deepcopy(raw_unit)


def _stage_snapshot(raw_snapshot: Any, *, side: str) -> UnitSnapshot:
    """Strictly stage one narrow-boundary constituent snapshot."""
    if (
        not isinstance(raw_snapshot, dict)
        or set(raw_snapshot) != _SNAPSHOT_STATE_KEYS
    ):
        raise ValueError("Aggregate snapshot has invalid key topology")
    original_side = raw_snapshot["original_side"]
    if (
        not isinstance(original_side, str)
        or not original_side
        or original_side != original_side.strip()
        or original_side != side
    ):
        raise _rem016_unsupported(
            "snapshot original_side is not the exact aggregate side",
        )
    original_index = _strict_non_negative_int(
        raw_snapshot["original_index"],
        label="Aggregate snapshot original_index",
    )
    if (
        raw_snapshot["weapon_states"] != []
        or raw_snapshot["sensor_states"] != []
        or raw_snapshot["supply_inventory"] is not None
        or raw_snapshot["order_records"] != []
    ):
        raise _rem016_unsupported(
            "snapshot carries loadout, supply, or order state",
        )
    unit_state = _stage_base_unit_state(
        raw_snapshot["unit_state"],
        side=original_side,
    )
    if unit_state["status"] != int(UnitStatus.ACTIVE):
        raise _rem016_unsupported(
            f"snapshot {unit_state['entity_id']!r} is not ACTIVE",
        )
    return UnitSnapshot(
        unit_state=unit_state,
        weapon_states=[],
        sensor_states=[],
        supply_inventory=None,
        original_side=original_side,
        original_index=original_index,
        order_records=[],
    )


def _stage_aggregation_state(
    state: Any,
    *,
    expected_config: AggregationConfig,
) -> tuple[int, dict[str, AggregateUnit]]:
    """Validate the complete current aggregation envelope without mutation."""
    if not isinstance(state, dict) or set(state) != _AGGREGATION_STATE_KEYS:
        raise ValueError("Aggregation state has invalid key topology")
    staged_config = _stage_aggregation_config(state["config"])
    if staged_config != expected_config:
        raise ValueError(
            "Aggregation checkpoint config does not match the runtime config",
        )
    next_id = _strict_non_negative_int(
        state["next_id"],
        label="Aggregation next_id",
    )
    raw_aggregates = state["aggregates"]
    if not isinstance(raw_aggregates, dict):
        raise ValueError("Aggregation aggregates must be a mapping")
    if raw_aggregates and not staged_config.enable_aggregation:
        raise ValueError(
            "Active aggregates require aggregation config to be enabled",
        )

    staged_aggregates: dict[str, AggregateUnit] = {}
    seen_constituents: set[str] = set()
    seen_sides: set[str] = set()
    max_ordinal = -1
    for aggregate_id in sorted(raw_aggregates):
        ordinal = _aggregate_ordinal(aggregate_id)
        max_ordinal = max(max_ordinal, ordinal)
        raw_aggregate = raw_aggregates[aggregate_id]
        if (
            not isinstance(raw_aggregate, dict)
            or set(raw_aggregate) != _AGGREGATE_STATE_KEYS
        ):
            raise ValueError(
                f"Aggregate {aggregate_id!r} has invalid key topology",
            )
        if raw_aggregate["aggregate_id"] != aggregate_id:
            raise ValueError(
                f"Aggregate identity mismatch for {aggregate_id!r}",
            )
        side = raw_aggregate["side"]
        unit_type = raw_aggregate["unit_type"]
        if (
            not isinstance(side, str)
            or not side
            or side != side.strip()
            or not isinstance(unit_type, str)
            or not unit_type
        ):
            raise ValueError(f"Aggregate {aggregate_id!r} identity is malformed")
        if side in seen_sides:
            raise _rem016_unsupported(
                f"side {side!r} has more than one active aggregate",
            )
        seen_sides.add(side)

        raw_position = raw_aggregate["position"]
        if (
            not isinstance(raw_position, (list, tuple))
            or len(raw_position) != 3
        ):
            raise ValueError(f"Aggregate {aggregate_id!r} position is malformed")
        for index, coordinate in enumerate(raw_position):
            _strict_finite_number(
                coordinate,
                label=f"aggregate {aggregate_id!r} position[{index}]",
            )
        combat_power = _strict_finite_number(
            raw_aggregate["aggregate_combat_power"],
            label=f"aggregate {aggregate_id!r} combat power",
            minimum=0.0,
        )
        personnel = _strict_non_negative_int(
            raw_aggregate["aggregate_personnel"],
            label=f"aggregate {aggregate_id!r} personnel",
        )
        supply_state = _strict_finite_number(
            raw_aggregate["aggregate_supply_state"],
            label=f"aggregate {aggregate_id!r} supply state",
            minimum=0.0,
            maximum=1.0,
        )
        raw_snapshots = raw_aggregate["snapshots"]
        if not isinstance(raw_snapshots, list) or not raw_snapshots:
            raise ValueError(
                f"Aggregate {aggregate_id!r} requires snapshots",
            )
        snapshots = [
            _stage_snapshot(raw_snapshot, side=side)
            for raw_snapshot in raw_snapshots
        ]
        constituent_ids = tuple(
            snapshot.unit_state["entity_id"]
            for snapshot in snapshots
        )
        if constituent_ids != tuple(sorted(constituent_ids)):
            raise ValueError(
                f"Aggregate {aggregate_id!r} snapshots are not canonical",
            )
        if (
            len(constituent_ids) != len(set(constituent_ids))
            or set(constituent_ids) & seen_constituents
            or set(constituent_ids) & set(raw_aggregates)
        ):
            raise ValueError("Aggregate constituent identities are not disjoint")
        seen_constituents.update(constituent_ids)
        original_indexes = [snapshot.original_index for snapshot in snapshots]
        if len(original_indexes) != len(set(original_indexes)):
            raise ValueError(
                f"Aggregate {aggregate_id!r} original indexes are not unique",
            )

        expected_personnel = sum(
            len(snapshot.unit_state["personnel"])
            if snapshot.unit_state["personnel"]
            else 4
            for snapshot in snapshots
        )
        expected_power = float(expected_personnel + 2 * len(snapshots))
        unit_types = {
            snapshot.unit_state["unit_type"]
            for snapshot in snapshots
        }
        domains = {
            snapshot.unit_state["domain"]
            for snapshot in snapshots
        }
        if len(domains) != 1:
            raise _rem016_unsupported(
                "aggregate constituents must share one exact domain",
            )
        expected_type = (
            snapshots[0].unit_state["unit_type"]
            if len(unit_types) == 1
            else "mixed"
        )
        expected_position = Position(
            sum(snapshot.unit_state["position"][0] for snapshot in snapshots)
            / len(snapshots),
            sum(snapshot.unit_state["position"][1] for snapshot in snapshots)
            / len(snapshots),
        )
        if (
            unit_type != expected_type
            or not _state_values_equal(raw_position, expected_position)
            or combat_power != expected_power
            or personnel != expected_personnel
            or supply_state != 0.0
        ):
            raise ValueError(
                f"Aggregate {aggregate_id!r} summary disagrees with snapshots",
            )
        staged_aggregates[aggregate_id] = AggregateUnit(
            aggregate_id=aggregate_id,
            side=side,
            unit_type=unit_type,
            position=Position(*raw_position),
            constituent_snapshots=snapshots,
            aggregate_combat_power=combat_power,
            aggregate_personnel=personnel,
            aggregate_supply_state=supply_state,
        )
    if max_ordinal >= next_id:
        raise ValueError(
            "Aggregation next_id must be greater than every active aggregate ID",
        )
    return next_id, staged_aggregates


def _morale_runtime(ctx: Any) -> MoraleRuntime:
    """Return the mandatory morale owner for a roster mutation."""
    runtime = getattr(ctx, "morale_runtime", None)
    if runtime is None:
        raise RuntimeError(
            "Aggregation and disaggregation require MoraleRuntime",
        )
    return runtime


def _restore_mapping(target: Any, snapshot: dict[Any, Any]) -> None:
    """Restore a mutable mapping without replacing its identity."""
    target.clear()
    target.update(snapshot)


def _restore_roster(
    units_by_side: dict[str, list[Unit]],
    snapshot: dict[str, list[Unit]],
) -> None:
    """Restore side lists and their existing identities where possible."""
    for side in tuple(units_by_side):
        if side not in snapshot:
            del units_by_side[side]
    for side, units in snapshot.items():
        if side in units_by_side:
            units_by_side[side][:] = units
        else:
            units_by_side[side] = list(units)


def _roster_index(ctx: Any, *, operation: str) -> dict[str, Unit]:
    """Build an exact roster index without collapsing duplicate IDs."""
    units = [
        unit
        for side_units in ctx.units_by_side.values()
        for unit in side_units
    ]
    roster = {unit.entity_id: unit for unit in units}
    if len(roster) != len(units):
        raise ValueError(f"{operation} roster contains duplicate unit IDs")
    return roster


def _unit_side(unit: Unit) -> str:
    """Return one canonical side identifier for a runtime unit."""
    return unit.side if isinstance(unit.side, str) else unit.side.value


def _rem016_unsupported(detail: str) -> ValueError:
    """Build the explicit bounded-fidelity aggregation rejection."""
    return ValueError(
        "REM-016: aggregation supports only exact base-Unit, "
        "equipmentless, no-supply contexts with empty runtime loadouts; "
        f"{detail}",
    )


def unsupported_aggregation_owner_names(ctx: Any) -> tuple[str, ...]:
    """Return every live context-state owner outside the narrow transaction.

    A production ``SimulationContext`` supplies its authoritative checkpoint
    registry.  Explicit non-checkpoint roster/build owners and every visible
    ``*_engine`` attribute supplement that registry.  Small compatibility
    fixtures lack the registry, so the same conservative attribute scan owns
    their complete gate.  This makes a new engine fail closed without losing
    the exact name/object binding supplied by the production registry.
    """
    checkpoint_engines = getattr(ctx, "_checkpoint_engines", None)
    candidate_owners: dict[str, Any] = {}
    if callable(checkpoint_engines):
        owner_items = checkpoint_engines()
        if not isinstance(owner_items, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0]
            for item in owner_items
        ):
            raise _rem016_unsupported(
                "context state-owner registry is malformed",
            )
        registry_names = tuple(name for name, _owner in owner_items)
        if len(registry_names) != len(set(registry_names)):
            raise _rem016_unsupported(
                "context state-owner registry contains duplicate names",
            )
        for name, owner in owner_items:
            if not hasattr(ctx, name) or getattr(ctx, name) is not owner:
                raise _rem016_unsupported(
                    "context state-owner registry binding disagrees with "
                    f"attribute {name!r}",
                )
        candidate_owners.update(owner_items)

    try:
        context_names = vars(ctx)
    except TypeError as exc:
        if not callable(checkpoint_engines):
            raise _rem016_unsupported(
                "context does not expose a state-owner registry",
            ) from exc
        context_names = {}
    candidate_names = set(UNSUPPORTED_AGGREGATION_OWNER_NAMES)
    candidate_names.update(
        name
        for name in context_names
        if name.endswith("_engine")
    )
    for name in candidate_names:
        candidate_owners.setdefault(name, getattr(ctx, name, None))
    return tuple(
        name
        for name, owner in sorted(candidate_owners.items())
        if name not in _SUPPORTED_AGGREGATION_CONTEXT_OWNER_NAMES
        and owner is not None
    )


def _supported_owner_topology(
    ctx: Any,
    roster: dict[str, Unit],
) -> tuple[
    tuple[MutableMapping[str, Any], ...],
    TacticalTargetingRuntime,
    TacticalTargetingRestorePlan,
    dict[str, str],
]:
    """Validate the only aggregation topology supported before REM-016.

    This deliberately narrow boundary keeps the existing exact morale-only
    base-unit round trip.  It does not reconstruct subclasses, equipment,
    supply, or other roster-indexed owners whose aggregation semantics have
    not been defined.
    """
    for unit_id in sorted(roster):
        unit = roster[unit_id]
        if type(unit) is not Unit:
            raise _rem016_unsupported(
                f"unit {unit_id!r} has concrete class {type(unit).__name__!r}",
            )
        if unit.equipment:
            raise _rem016_unsupported(
                f"unit {unit_id!r} carries equipment",
            )

    unsupported_owners = unsupported_aggregation_owner_names(ctx)
    if unsupported_owners:
        raise _rem016_unsupported(
            "uncoordinated context state owners are present: "
            f"{unsupported_owners!r}",
        )

    roster_ids = set(roster)
    loadout_owners: list[MutableMapping[str, Any]] = []
    for name in _LOADOUT_OWNER_NAMES:
        owner = getattr(ctx, name, None)
        if not isinstance(owner, MutableMapping):
            raise _rem016_unsupported(
                f"{name} is not a mutable runtime mapping",
            )
        owner_ids = set(owner)
        if owner_ids != roster_ids:
            raise _rem016_unsupported(
                f"{name} topology disagrees with the roster: "
                f"missing={sorted(roster_ids - owner_ids)!r}, "
                f"extra={sorted(owner_ids - roster_ids)!r}",
            )
        nonempty = tuple(
            unit_id
            for unit_id in sorted(roster_ids)
            if owner[unit_id] != ()
        )
        if nonempty:
            raise _rem016_unsupported(
                f"{name} has nonempty bindings for {nonempty!r}",
            )
        loadout_owners.append(owner)

    try:
        validated_loadouts = RuntimeLoadouts(
            unit_weapons=loadout_owners[0],
            unit_sensor_attachments=loadout_owners[1],
            equipment_resolutions=loadout_owners[3],
        )
    except (TypeError, ValueError) as exc:
        raise _rem016_unsupported(
            f"runtime loadout projection is invalid: {exc}",
        ) from exc
    if dict(validated_loadouts.unit_sensors) != dict(loadout_owners[2]):
        raise _rem016_unsupported(
            "unit_sensors is detached from the typed sensor projection",
        )

    targeting = getattr(ctx, "tactical_targeting", None)
    if type(targeting) is not TacticalTargetingRuntime:
        raise _rem016_unsupported(
            "the exact TacticalTargetingRuntime owner is absent",
        )
    unit_sides = {
        unit_id: _unit_side(roster[unit_id])
        for unit_id in sorted(roster)
    }
    if dict(targeting.registered_unit_sides) != unit_sides:
        raise _rem016_unsupported(
            "tactical-targeting topology disagrees with the roster",
        )
    targeting_before = targeting.stage_state(targeting.get_state())
    return tuple(loadout_owners), targeting, targeting_before, unit_sides


def _validate_supported_snapshots(
    snapshots: list[UnitSnapshot],
    *,
    expected_side: str | None = None,
) -> None:
    """Reject a persisted aggregate outside the narrow REM-016 boundary."""
    original_indexes: set[int] = set()
    domains: set[Any] = set()
    for snapshot in snapshots:
        state = snapshot.unit_state
        unit_id = state.get("entity_id")
        if state.get("unit_class") != Unit.__name__:
            raise _rem016_unsupported(
                f"snapshot {unit_id!r} is not an exact base Unit",
            )
        if state.get("equipment") != []:
            raise _rem016_unsupported(
                f"snapshot {unit_id!r} carries equipment",
            )
        snapshot_side = snapshot.original_side
        if (
            not isinstance(snapshot_side, str)
            or not snapshot_side
            or snapshot_side != snapshot_side.strip()
            or state.get("side") != snapshot_side
            or (
                expected_side is not None
                and snapshot_side != expected_side
            )
            or state.get("status") != int(UnitStatus.ACTIVE)
        ):
            raise _rem016_unsupported(
                f"snapshot {unit_id!r} side/status is not the exact active "
                "aggregate baseline",
            )
        _stage_base_unit_state(state, side=snapshot_side)
        if (
            isinstance(snapshot.original_index, bool)
            or not isinstance(snapshot.original_index, int)
            or snapshot.original_index < 0
            or snapshot.original_index in original_indexes
        ):
            raise _rem016_unsupported(
                "snapshots require unique non-negative original roster indexes",
            )
        original_indexes.add(snapshot.original_index)
        domains.add(state.get("domain"))
        if (
            snapshot.weapon_states
            or snapshot.sensor_states
            or snapshot.supply_inventory is not None
            or snapshot.order_records
        ):
            raise _rem016_unsupported(
                f"snapshot {unit_id!r} carries loadout, supply, or order state",
            )
    if len(domains) != 1:
        raise _rem016_unsupported(
            "aggregate constituents must share one exact domain",
        )


def _validate_active_aggregate_topology(
    aggregates: dict[str, AggregateUnit],
    roster: dict[str, Unit],
    morale_runtime: MoraleRuntime,
    units_by_side: dict[str, list[Unit]],
) -> set[str]:
    """Cross-check active proxies and suspended constituents exactly."""
    morale_runtime.validate_bindings(roster)
    aggregate_ids = set(aggregates)
    raw_archives = morale_runtime.get_state().get("suspended_archives")
    if not isinstance(raw_archives, dict) or set(raw_archives) != aggregate_ids:
        raise ValueError(
            "Aggregation and morale archive IDs disagree",
        )

    archived_constituents: set[str] = set()
    aggregate_sides: set[str] = set()
    for aggregate_id in sorted(aggregate_ids):
        aggregate = aggregates[aggregate_id]
        if (
            not isinstance(aggregate_id, str)
            or not aggregate_id
            or aggregate.aggregate_id != aggregate_id
            or aggregate_id not in roster
        ):
            raise ValueError(
                "Active aggregate IDs must exactly identify one roster proxy",
            )
        proxy = roster[aggregate_id]
        if (
            type(proxy) is not Unit
            or _unit_side(proxy) != aggregate.side
            or proxy.unit_type != aggregate.unit_type
            or proxy.position != aggregate.position
        ):
            raise ValueError(
                "Active aggregate roster proxy disagrees with aggregate state",
            )
        if aggregate.side in aggregate_sides:
            raise _rem016_unsupported(
                f"side {aggregate.side!r} has more than one active aggregate",
            )
        aggregate_sides.add(aggregate.side)
        snapshots = aggregate.constituent_snapshots
        if not snapshots:
            raise ValueError("Active aggregates require constituent snapshots")
        _validate_supported_snapshots(
            snapshots,
            expected_side=aggregate.side,
        )
        archived_domain = snapshots[0].unit_state["domain"]
        side_units = units_by_side.get(aggregate.side, [])
        proxy_indexes = [
            index
            for index, unit in enumerate(side_units)
            if unit.entity_id == aggregate_id
        ]
        original_indexes = [
            snapshot.original_index
            for snapshot in snapshots
        ]
        reconstructed_size = len(side_units) - 1 + len(snapshots)
        if (
            int(proxy.domain) != archived_domain
            or proxy_indexes != [min(original_indexes)]
            or any(index >= reconstructed_size for index in original_indexes)
        ):
            raise ValueError(
                "Active aggregate proxy domain/order disagrees with snapshots",
            )
        snapshot_ids = tuple(
            snapshot.unit_state.get("entity_id")
            for snapshot in snapshots
        )
        if (
            any(not isinstance(unit_id, str) or not unit_id for unit_id in snapshot_ids)
            or len(snapshot_ids) != len(set(snapshot_ids))
        ):
            raise ValueError(
                "Active aggregate snapshots require unique constituent IDs",
            )
        snapshot_id_set = set(snapshot_ids)
        if (
            snapshot_id_set & set(roster)
            or snapshot_id_set & aggregate_ids
            or snapshot_id_set & archived_constituents
        ):
            raise ValueError(
                "Active aggregate constituents must be globally disjoint "
                "from the live roster and other archives",
            )
        raw_archive = raw_archives[aggregate_id]
        raw_records = (
            raw_archive.get("constituent_records")
            if isinstance(raw_archive, dict)
            else None
        )
        if not isinstance(raw_records, dict) or set(raw_records) != snapshot_id_set:
            raise ValueError(
                "Aggregation snapshots and morale constituents disagree",
            )
        archived_constituents.update(snapshot_id_set)
    return archived_constituents


# ---------------------------------------------------------------------------
# Aggregation engine
# ---------------------------------------------------------------------------


class AggregationEngine:
    """Manages force aggregation and disaggregation.

    Parameters
    ----------
    config:
        Aggregation tuning parameters.
    rng:
        PRNG generator (for deterministic ordering).
    event_bus:
        For publishing aggregation/disaggregation events.
    """

    def __init__(
        self,
        config: AggregationConfig | None = None,
        *,
        rng: np.random.Generator,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config if config is not None else AggregationConfig()
        self._rng = rng
        self._bus = event_bus
        self._aggregates: dict[str, AggregateUnit] = {}
        self._next_id = 0

    # -- Snapshot / restore -------------------------------------------------

    def snapshot_unit(
        self,
        unit: Unit,
        ctx: Any,
        *,
        original_index: int = 0,
        failure_handler: RuntimeFailureHandler | None = None,
    ) -> UnitSnapshot:
        """Capture complete per-unit state from all subsystems."""
        unit_state = unit.get_state()

        # Weapons
        weapon_states: list[dict] = []
        weapons = ctx.unit_weapons.get(unit.entity_id, [])
        for wpn_inst, ammo_defs in weapons:
            weapon_states.append(wpn_inst.get_state())

        # Sensors
        sensor_states: list[dict] = []
        sensors = ctx.unit_sensors.get(unit.entity_id, [])
        for sensor in sensors:
            sensor_states.append(sensor.get_state())

        # Supply
        supply_inv = None
        if ctx.stockpile_manager is not None:
            try:
                if ctx.stockpile_manager.has_unit_inventory(unit.entity_id):
                    inv = ctx.stockpile_manager.get_unit_inventory(
                        unit.entity_id,
                    )
                    supply_inv = inv.get_state()
            except Exception as exc:
                if failure_handler is None or not failure_handler(
                    "logistics.stockpile",
                    "snapshot_supply_inventory",
                    exc,
                ):
                    raise

        # Orders (Phase 85)
        order_records: list[dict] = []
        _order_exec = getattr(ctx, "order_execution", None)
        if _order_exec is not None:
            try:
                records = (
                    _order_exec.get_active_orders(unit.entity_id)
                    + _order_exec.get_pending_orders(unit.entity_id)
                )
            except Exception as exc:
                if failure_handler is None or not failure_handler(
                    "c2.order_execution",
                    "snapshot_orders",
                    exc,
                ):
                    raise
                records = ()
            for rec in records:
                try:
                    order_records.append(rec.get_state())
                except Exception as exc:
                    if failure_handler is None or not failure_handler(
                        "c2.order_execution",
                        "snapshot_order_record",
                        exc,
                    ):
                        raise

        return UnitSnapshot(
            unit_state=unit_state,
            weapon_states=weapon_states,
            sensor_states=sensor_states,
            supply_inventory=supply_inv,
            original_side=_unit_side(unit),
            original_index=original_index,
            order_records=order_records,
        )

    def aggregate(
        self,
        unit_ids: list[str],
        ctx: Any,
        *,
        failure_handler: RuntimeFailureHandler | None = None,
    ) -> AggregateUnit | None:
        """Aggregate units into a composite formation.

        Morale records move through ``MoraleRuntime`` as complete immutable
        records.  The aggregation engine owns only roster/unit snapshots and
        never serializes a second morale copy.
        """
        if len(unit_ids) < self._config.min_units_to_aggregate:
            return None

        unit_ids = sorted(unit_ids)
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("Aggregation unit IDs must be unique")

        roster_index = _roster_index(ctx, operation="Aggregation")
        units = [
            roster_index[unit_id]
            for unit_id in unit_ids
            if (
                unit_id in roster_index
                and roster_index[unit_id].status == UnitStatus.ACTIVE
            )
        ]
        if len(units) != len(unit_ids):
            return None

        sides = {_unit_side(unit) for unit in units}
        if len(sides) != 1:
            return None
        side = sides.pop()
        domains = {unit.domain for unit in units}
        if len(domains) != 1:
            raise _rem016_unsupported(
                "aggregate constituents must share one exact domain",
            )
        domain = domains.pop()

        morale_runtime = _morale_runtime(ctx)
        archived_constituents = _validate_active_aggregate_topology(
            self._aggregates,
            roster_index,
            morale_runtime,
            ctx.units_by_side,
        )
        if set(unit_ids) & (set(self._aggregates) | archived_constituents):
            raise ValueError(
                "Aggregation candidates cannot be active proxies or "
                "suspended constituents",
            )
        (
            loadout_owners,
            targeting,
            targeting_before,
            unit_sides_before,
        ) = _supported_owner_topology(ctx, roster_index)

        same_side_aggregates = tuple(
            aggregate_id
            for aggregate_id, aggregate in sorted(self._aggregates.items())
            if aggregate.side == side
        )
        if same_side_aggregates:
            raise _rem016_unsupported(
                f"side {side!r} already has active aggregate(s) "
                f"{same_side_aggregates!r}",
            )
        side_positions = {
            unit.entity_id: index
            for index, unit in enumerate(ctx.units_by_side[side])
        }
        snapshots = [
            self.snapshot_unit(
                unit,
                ctx,
                original_index=side_positions[unit.entity_id],
                failure_handler=failure_handler,
            )
            for unit in units
        ]
        _validate_supported_snapshots(snapshots, expected_side=side)

        total_power = 0.0
        total_personnel = 0
        total_supply = 0.0
        supply_count = 0
        positions_e: list[float] = []
        positions_n: list[float] = []
        unit_types: set[str] = set()

        for u in units:
            personnel = len(u.personnel) if u.personnel else 4
            equipment = len(u.equipment) if u.equipment else 1
            total_power += personnel + equipment * 2.0
            total_personnel += personnel
            unit_types.add(u.unit_type)
            positions_e.append(u.position.easting)
            positions_n.append(u.position.northing)

            if ctx.stockpile_manager is not None:
                try:
                    ss = ctx.stockpile_manager.get_supply_state(u.entity_id)
                    total_supply += ss
                    supply_count += 1
                except Exception as exc:
                    if failure_handler is None or not failure_handler(
                        "logistics.stockpile",
                        "get_supply_state",
                        exc,
                    ):
                        raise
                    total_supply += 1.0
                    supply_count += 1

        avg_supply = total_supply / max(supply_count, 1)
        centroid = Position(
            sum(positions_e) / len(positions_e),
            sum(positions_n) / len(positions_n),
        )
        agg_type = units[0].unit_type if len(unit_types) == 1 else "mixed"

        if (
            isinstance(self._next_id, bool)
            or not isinstance(self._next_id, int)
            or self._next_id < 0
        ):
            raise ValueError("Aggregation next_id must be a non-negative integer")
        agg_id = f"agg_{self._next_id:04d}"
        if (
            agg_id in roster_index
            or agg_id in self._aggregates
            or agg_id in archived_constituents
        ):
            raise ValueError(
                f"Aggregate ID {agg_id!r} collides with existing topology",
            )
        agg = AggregateUnit(
            aggregate_id=agg_id,
            side=side,
            unit_type=agg_type,
            position=centroid,
            constituent_snapshots=snapshots,
            aggregate_combat_power=total_power,
            aggregate_personnel=total_personnel,
            aggregate_supply_state=avg_supply,
        )
        proxy = Unit(
            entity_id=agg_id,
            position=centroid,
            name=f"Aggregate ({len(units)} units)",
            unit_type=agg_type,
            side=side,
            domain=domain,
            status=UnitStatus.ACTIVE,
            speed=min(u.speed for u in units) if units else 0.0,
            max_speed=min(u.max_speed for u in units) if units else 0.0,
        )

        morale_plan = morale_runtime.prepare_aggregation(
            agg_id,
            unit_ids,
            proxy,
        )
        unit_sides_after = {
            unit_id: registered_side
            for unit_id, registered_side in unit_sides_before.items()
            if unit_id not in set(unit_ids)
        }
        unit_sides_after[agg_id] = side
        unit_sides_after = dict(sorted(unit_sides_after.items()))
        roster_before = {
            roster_side: list(side_units)
            for roster_side, side_units in ctx.units_by_side.items()
        }
        weapons_before = dict(ctx.unit_weapons)
        sensor_attachments_before = dict(ctx.unit_sensor_attachments)
        sensors_before = dict(ctx.unit_sensors)
        resolutions_before = dict(ctx.equipment_resolutions)
        aggregates_before = dict(self._aggregates)
        next_id_before = self._next_id
        morale_committed = False

        try:
            morale_runtime.commit_aggregation(morale_plan)
            morale_committed = True

            constituent_ids = set(unit_ids)
            retained_units = [
                unit
                for unit in ctx.units_by_side[side]
                if unit.entity_id not in constituent_ids
            ]
            retained_units.insert(
                min(snapshot.original_index for snapshot in snapshots),
                proxy,
            )
            ctx.units_by_side[side][:] = retained_units
            for owner in loadout_owners:
                for unit_id in constituent_ids:
                    owner.pop(unit_id)
                owner[agg_id] = ()
            targeting.replace_registered_units(
                expected_current=unit_sides_before,
                replacement=unit_sides_after,
            )
            self._aggregates[agg_id] = agg
            self._next_id += 1
            committed_roster = _roster_index(
                ctx,
                operation="Aggregation",
            )
            _supported_owner_topology(ctx, committed_roster)
            _validate_active_aggregate_topology(
                self._aggregates,
                committed_roster,
                morale_runtime,
                ctx.units_by_side,
            )
        except Exception as exc:
            rollback_errors: list[Exception] = []
            try:
                _restore_roster(ctx.units_by_side, roster_before)
                _restore_mapping(ctx.unit_weapons, weapons_before)
                _restore_mapping(
                    ctx.unit_sensor_attachments,
                    sensor_attachments_before,
                )
                _restore_mapping(ctx.unit_sensors, sensors_before)
                _restore_mapping(
                    ctx.equipment_resolutions,
                    resolutions_before,
                )
                targeting.commit_state(targeting_before)
                _restore_mapping(self._aggregates, aggregates_before)
                self._next_id = next_id_before
            except Exception as rollback_exc:
                rollback_errors.append(rollback_exc)
            if morale_committed:
                try:
                    morale_runtime.rollback_aggregation(morale_plan)
                except Exception as rollback_exc:
                    rollback_errors.append(rollback_exc)
            if rollback_errors:
                raise ExceptionGroup(
                    "Aggregation failed and rollback was incomplete",
                    [exc, *rollback_errors],
                ) from exc
            raise

        logger.info(
            "Aggregated %d units into %s (side=%s, power=%.0f)",
            len(units), agg_id, side, total_power,
        )

        return agg

    def disaggregate(
        self,
        aggregate_id: str,
        ctx: Any,
        *,
        failure_handler: RuntimeFailureHandler | None = None,
    ) -> list[str]:
        """Restore individual units from an aggregate.

        The complete proxy morale record is checked against the runtime-owned
        baseline before any roster mutation.  A proxy that evolved—even away
        and back to the same enum state—cannot be lossily expanded.
        """
        agg = self._aggregates.get(aggregate_id)
        if agg is None:
            return []

        roster_index = _roster_index(ctx, operation="Disaggregation")
        morale_runtime = _morale_runtime(ctx)
        _validate_active_aggregate_topology(
            self._aggregates,
            roster_index,
            morale_runtime,
            ctx.units_by_side,
        )
        _validate_supported_snapshots(
            agg.constituent_snapshots,
            expected_side=agg.side,
        )
        (
            loadout_owners,
            targeting,
            targeting_before,
            unit_sides_before,
        ) = _supported_owner_topology(ctx, roster_index)

        restored_units: dict[str, Unit] = {}
        restored_sides: dict[str, str] = {}
        staged_orders: list[Any] = []
        order_execution = getattr(ctx, "order_execution", None)
        for snap in agg.constituent_snapshots:
            unit = Unit(
                entity_id=snap.unit_state["entity_id"],
                position=Position(*snap.unit_state["position"]),
            )
            unit.set_state(snap.unit_state)
            if unit.entity_id in restored_units:
                raise ValueError(
                    "Aggregate snapshots contain duplicate unit ID "
                    f"{unit.entity_id!r}",
                )
            restored_units[unit.entity_id] = unit
            restored_sides[unit.entity_id] = snap.original_side

            if order_execution is not None and snap.order_records:
                from stochastic_warfare.c2.orders.types import OrderExecutionRecord

                for rec_state in snap.order_records:
                    try:
                        rec = OrderExecutionRecord(
                            order_id=rec_state.get("order_id", ""),
                            recipient_id=rec_state.get("recipient_id", ""),
                        )
                        rec.set_state(rec_state)
                        staged_orders.append(rec)
                    except Exception as exc:
                        if failure_handler is None or not failure_handler(
                            "c2.order_execution",
                            "restore_order_record",
                            exc,
                        ):
                            raise

        current_ids = {
            unit.entity_id
            for side_units in ctx.units_by_side.values()
            for unit in side_units
            if unit.entity_id != aggregate_id
        }
        collisions = current_ids & set(restored_units)
        if collisions:
            raise ValueError(
                "Disaggregation would duplicate active unit IDs: "
                f"{sorted(collisions)!r}",
            )
        restorations_by_side: dict[str, list[tuple[int, Unit]]] = {}
        for snapshot in agg.constituent_snapshots:
            unit_id = snapshot.unit_state["entity_id"]
            restorations_by_side.setdefault(snapshot.original_side, []).append(
                (snapshot.original_index, restored_units[unit_id]),
            )
        for side, restorations in restorations_by_side.items():
            side_units = ctx.units_by_side.get(side, [])
            retained_count = sum(
                unit.entity_id != aggregate_id
                for unit in side_units
            )
            restored_count = len(restorations)
            indexes = [index for index, _unit in restorations]
            if (
                len(indexes) != len(set(indexes))
                or any(
                    index >= retained_count + restored_count
                    for index in indexes
                )
            ):
                raise ValueError(
                    "Aggregate original roster indexes cannot reconstruct "
                    f"side {side!r}",
                )

        morale_plan = morale_runtime.prepare_disaggregation(
            aggregate_id,
            restored_units,
        )
        unit_sides_after = {
            unit_id: registered_side
            for unit_id, registered_side in unit_sides_before.items()
            if unit_id != aggregate_id
        }
        unit_sides_after.update(restored_sides)
        unit_sides_after = dict(sorted(unit_sides_after.items()))
        roster_before = {
            roster_side: list(side_units)
            for roster_side, side_units in ctx.units_by_side.items()
        }
        weapons_before = dict(ctx.unit_weapons)
        sensor_attachments_before = dict(ctx.unit_sensor_attachments)
        sensors_before = dict(ctx.unit_sensors)
        resolutions_before = dict(ctx.equipment_resolutions)
        aggregates_before = dict(self._aggregates)
        order_records_before = None
        if order_execution is not None:
            try:
                order_records_before = (
                    order_execution.capture_record_snapshot()
                )
            except Exception as exc:
                if failure_handler is None or not failure_handler(
                    "c2.order_execution",
                    "capture_record_snapshot",
                    exc,
                ):
                    raise
                # Without an owner snapshot, no atomic disaggregation is
                # possible.  The degraded result is explicitly non-operative.
                return []
        morale_committed = False

        try:
            morale_runtime.commit_disaggregation(morale_plan)
            morale_committed = True

            for side_units in ctx.units_by_side.values():
                side_units[:] = [
                    unit
                    for unit in side_units
                    if unit.entity_id != aggregate_id
                ]
            for owner in loadout_owners:
                owner.pop(aggregate_id)
                owner.update({unit_id: () for unit_id in restored_units})
            for side, restorations in sorted(restorations_by_side.items()):
                side_units = ctx.units_by_side.setdefault(side, [])
                for original_index, unit in sorted(
                    restorations,
                    key=lambda item: item[0],
                ):
                    side_units.insert(original_index, unit)
            if order_execution is not None and staged_orders:
                try:
                    order_execution.install_records(staged_orders)
                except Exception as exc:
                    if failure_handler is None or not failure_handler(
                        "c2.order_execution",
                        "install_restored_records",
                        exc,
                    ):
                        raise
            targeting.replace_registered_units(
                expected_current=unit_sides_before,
                replacement=unit_sides_after,
            )
            self._aggregates.pop(aggregate_id)
            committed_roster = _roster_index(
                ctx,
                operation="Disaggregation",
            )
            _supported_owner_topology(ctx, committed_roster)
            _validate_active_aggregate_topology(
                self._aggregates,
                committed_roster,
                morale_runtime,
                ctx.units_by_side,
            )
        except Exception as exc:
            rollback_errors: list[Exception] = []
            try:
                _restore_roster(ctx.units_by_side, roster_before)
                _restore_mapping(ctx.unit_weapons, weapons_before)
                _restore_mapping(
                    ctx.unit_sensor_attachments,
                    sensor_attachments_before,
                )
                _restore_mapping(ctx.unit_sensors, sensors_before)
                _restore_mapping(
                    ctx.equipment_resolutions,
                    resolutions_before,
                )
                targeting.commit_state(targeting_before)
                _restore_mapping(self._aggregates, aggregates_before)
                if order_records_before is not None:
                    order_execution.restore_record_snapshot(
                        order_records_before,
                    )
            except Exception as rollback_exc:
                rollback_errors.append(rollback_exc)
            if morale_committed:
                try:
                    morale_runtime.rollback_disaggregation(morale_plan)
                except Exception as rollback_exc:
                    rollback_errors.append(rollback_exc)
            if rollback_errors:
                raise ExceptionGroup(
                    "Disaggregation failed and rollback was incomplete",
                    [exc, *rollback_errors],
                ) from exc
            raise

        restored_ids = list(restored_units)

        logger.info(
            "Disaggregated %s into %d units (side=%s)",
            aggregate_id, len(restored_ids), agg.side,
        )

        return restored_ids

    # -- Candidate detection ------------------------------------------------

    def check_aggregation_candidates(
        self,
        ctx: Any,
        battle_positions: list[Position] | None = None,
    ) -> list[list[str]]:
        """Find groups of units eligible for aggregation.

        Criteria: same side, not in active battle, distance from nearest
        battle > aggregation_distance_m, group size >= min_units.
        """
        if not self._config.enable_aggregation:
            return []

        battle_pos = battle_positions or []
        agg_dist = self._config.aggregation_distance_m
        min_units = self._config.min_units_to_aggregate

        candidates: list[list[str]] = []
        active_aggregate_sides = {
            aggregate.side
            for aggregate in self._aggregates.values()
        }

        for side in sorted(ctx.units_by_side):
            units = ctx.units_by_side[side]
            if side in active_aggregate_sides:
                continue
            eligible: list[Unit] = []
            for u in units:
                if u.status != UnitStatus.ACTIVE:
                    continue
                if u.entity_id in self._aggregates:
                    continue  # Already an aggregate proxy

                # Check distance from battles
                far_enough = True
                for bp in battle_pos:
                    dx = u.position.easting - bp.easting
                    dy = u.position.northing - bp.northing
                    if math.sqrt(dx * dx + dy * dy) < agg_dist:
                        far_enough = False
                        break
                if far_enough:
                    eligible.append(u)

            # Group by unit_type
            by_type: dict[str, list[str]] = {}
            for u in eligible:
                by_type.setdefault(u.unit_type, []).append(u.entity_id)

            eligible_groups = [
                sorted(by_type[unit_type])
                for unit_type in sorted(by_type)
                if len(by_type[unit_type]) >= min_units
            ]
            if eligible_groups:
                # REM-016 permits only one active aggregate per side.  Return
                # one canonical group so the engine never partially commits a
                # first group and then rejects a second group in the same tick.
                candidates.append(eligible_groups[0])

        return candidates

    def check_disaggregation_triggers(
        self,
        ctx: Any,
        battle_positions: list[Position] | None = None,
    ) -> list[str]:
        """Find aggregates that should be disaggregated.

        Trigger: distance from nearest active battle < disaggregate_distance_m.
        """
        if not self._config.enable_aggregation:
            return []

        battle_pos = battle_positions or []
        disagg_dist = self._config.disaggregate_distance_m
        to_disagg: list[str] = []

        for agg_id, agg in self._aggregates.items():
            for bp in battle_pos:
                dx = agg.position.easting - bp.easting
                dy = agg.position.northing - bp.northing
                if math.sqrt(dx * dx + dy * dy) < disagg_dist:
                    to_disagg.append(agg_id)
                    break

        return sorted(to_disagg)

    # -- State persistence --------------------------------------------------

    @property
    def config(self) -> AggregationConfig:
        """Immutable aggregation configuration owned by this runtime."""
        return self._config

    @property
    def active_aggregates(self) -> dict[str, AggregateUnit]:
        """Detached snapshots of the currently active aggregates."""
        return copy.deepcopy(self._aggregates)

    def get_state(self) -> dict[str, Any]:
        """Capture aggregation engine state."""
        state = {
            "config": self._config.model_dump(mode="json"),
            "next_id": self._next_id,
            "aggregates": {
                agg_id: {
                    "aggregate_id": agg.aggregate_id,
                    "side": agg.side,
                    "unit_type": agg.unit_type,
                    "position": tuple(agg.position),
                    "aggregate_combat_power": agg.aggregate_combat_power,
                    "aggregate_personnel": agg.aggregate_personnel,
                    "aggregate_supply_state": agg.aggregate_supply_state,
                    "snapshots": [
                        {
                            "unit_state": s.unit_state,
                            "weapon_states": s.weapon_states,
                            "sensor_states": s.sensor_states,
                            "supply_inventory": s.supply_inventory,
                            "original_side": s.original_side,
                            "original_index": s.original_index,
                            "order_records": s.order_records,
                        }
                        for s in agg.constituent_snapshots
                    ],
                }
                for agg_id, agg in sorted(self._aggregates.items())
            },
        }
        return copy.deepcopy(state)

    def set_state(self, state: dict[str, Any]) -> None:
        """Atomically restore one strict current aggregation envelope."""
        next_id, aggregates = _stage_aggregation_state(
            state,
            expected_config=self._config,
        )
        self._next_id = next_id
        self._aggregates.clear()
        self._aggregates.update(aggregates)

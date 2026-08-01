"""Force aggregation and disaggregation for large-scale campaigns.

Provides :class:`AggregationEngine` which captures, merges, and restores
per-unit state across all subsystems.  Units far from active battles are
aggregated into composite formations; they disaggregate when they
approach the battle area.

Phase 13a-7.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.runtime import MoraleRuntime

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class AggregationConfig(BaseModel):
    """Tuning parameters for force aggregation."""

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
        self._config = config or AggregationConfig()
        self._rng = rng
        self._bus = event_bus
        self._aggregates: dict[str, AggregateUnit] = {}
        self._next_id = 0

    # -- Snapshot / restore -------------------------------------------------

    def snapshot_unit(
        self,
        unit: Unit,
        ctx: Any,
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
                inv = ctx.stockpile_manager._unit_inventories.get(unit.entity_id)
                if inv is not None:
                    supply_inv = inv.get_state()
            except Exception:
                pass

        # Orders (Phase 85)
        order_records: list[dict] = []
        _order_exec = getattr(ctx, "order_execution", None)
        if _order_exec is not None:
            for rec in (
                _order_exec.get_active_orders(unit.entity_id)
                + _order_exec.get_pending_orders(unit.entity_id)
            ):
                try:
                    order_records.append(rec.get_state())
                except Exception:
                    pass

        return UnitSnapshot(
            unit_state=unit_state,
            weapon_states=weapon_states,
            sensor_states=sensor_states,
            supply_inventory=supply_inv,
            original_side=unit.side if isinstance(unit.side, str) else str(unit.side),
            order_records=order_records,
        )

    def aggregate(
        self,
        unit_ids: list[str],
        ctx: Any,
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

        roster_index = {
            unit.entity_id: unit
            for side_units in ctx.units_by_side.values()
            for unit in side_units
        }
        if len(roster_index) != sum(
            len(side_units) for side_units in ctx.units_by_side.values()
        ):
            raise ValueError("Aggregation roster contains duplicate unit IDs")
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

        sides = {u.side if isinstance(u.side, str) else str(u.side) for u in units}
        if len(sides) != 1:
            return None
        side = sides.pop()

        snapshots = [self.snapshot_unit(u, ctx) for u in units]

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
                except Exception:
                    total_supply += 1.0
                    supply_count += 1

        avg_supply = total_supply / max(supply_count, 1)
        centroid = Position(
            sum(positions_e) / len(positions_e),
            sum(positions_n) / len(positions_n),
        )
        agg_type = units[0].unit_type if len(unit_types) == 1 else "mixed"

        agg_id = f"agg_{self._next_id:04d}"
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
            domain=units[0].domain,
            status=UnitStatus.ACTIVE,
            speed=min(u.speed for u in units) if units else 0.0,
            max_speed=min(u.max_speed for u in units) if units else 0.0,
        )

        morale_runtime = _morale_runtime(ctx)
        morale_plan = morale_runtime.prepare_aggregation(
            agg_id,
            unit_ids,
            proxy,
        )
        roster_before = {
            roster_side: list(side_units)
            for roster_side, side_units in ctx.units_by_side.items()
        }
        weapons_before = dict(ctx.unit_weapons)
        sensors_before = dict(ctx.unit_sensors)
        resolutions = getattr(ctx, "equipment_resolutions", None)
        resolutions_before = (
            dict(resolutions) if resolutions is not None else None
        )
        aggregates_before = dict(self._aggregates)
        next_id_before = self._next_id
        morale_committed = False

        try:
            morale_runtime.commit_aggregation(morale_plan)
            morale_committed = True

            constituent_ids = set(unit_ids)
            ctx.units_by_side[side][:] = [
                unit
                for unit in ctx.units_by_side[side]
                if unit.entity_id not in constituent_ids
            ]
            ctx.units_by_side[side].append(proxy)
            for unit_id in unit_ids:
                ctx.unit_weapons.pop(unit_id, None)
                ctx.unit_sensors.pop(unit_id, None)
                if resolutions is not None:
                    resolutions.pop(unit_id, None)
            self._aggregates[agg_id] = agg
            self._next_id += 1
        except Exception as exc:
            rollback_errors: list[Exception] = []
            try:
                _restore_roster(ctx.units_by_side, roster_before)
                _restore_mapping(ctx.unit_weapons, weapons_before)
                _restore_mapping(ctx.unit_sensors, sensors_before)
                if resolutions_before is not None:
                    _restore_mapping(resolutions, resolutions_before)
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
    ) -> list[str]:
        """Restore individual units from an aggregate.

        The complete proxy morale record is checked against the runtime-owned
        baseline before any roster mutation.  A proxy that evolved—even away
        and back to the same enum state—cannot be lossily expanded.
        """
        agg = self._aggregates.get(aggregate_id)
        if agg is None:
            return []

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
            restored_sides[unit.entity_id] = snap.original_side or agg.side

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
                    except Exception:
                        pass

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

        morale_runtime = _morale_runtime(ctx)
        morale_plan = morale_runtime.prepare_disaggregation(
            aggregate_id,
            restored_units,
        )
        roster_before = {
            roster_side: list(side_units)
            for roster_side, side_units in ctx.units_by_side.items()
        }
        weapons_before = dict(ctx.unit_weapons)
        sensors_before = dict(ctx.unit_sensors)
        resolutions = getattr(ctx, "equipment_resolutions", None)
        resolutions_before = (
            dict(resolutions) if resolutions is not None else None
        )
        aggregates_before = dict(self._aggregates)
        order_records = (
            getattr(order_execution, "_records", None)
            if order_execution is not None
            else None
        )
        order_records_before = (
            dict(order_records) if order_records is not None else None
        )
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
            ctx.unit_weapons.pop(aggregate_id, None)
            ctx.unit_sensors.pop(aggregate_id, None)
            if resolutions is not None:
                resolutions.pop(aggregate_id, None)
            for unit_id, unit in restored_units.items():
                side = restored_sides[unit_id]
                ctx.units_by_side.setdefault(side, []).append(unit)
            if order_records is not None:
                for record in staged_orders:
                    order_records[record.order_id] = record
            self._aggregates.pop(aggregate_id)
        except Exception as exc:
            rollback_errors: list[Exception] = []
            try:
                _restore_roster(ctx.units_by_side, roster_before)
                _restore_mapping(ctx.unit_weapons, weapons_before)
                _restore_mapping(ctx.unit_sensors, sensors_before)
                if resolutions_before is not None:
                    _restore_mapping(resolutions, resolutions_before)
                _restore_mapping(self._aggregates, aggregates_before)
                if order_records_before is not None:
                    _restore_mapping(order_records, order_records_before)
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

        for side, units in ctx.units_by_side.items():
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

            for utype, ids in by_type.items():
                if len(ids) >= min_units:
                    candidates.append(sorted(ids))

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
    def active_aggregates(self) -> dict[str, AggregateUnit]:
        """Currently active aggregates."""
        return dict(self._aggregates)

    def get_state(self) -> dict[str, Any]:
        """Capture aggregation engine state."""
        return {
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
                            "order_records": s.order_records,
                        }
                        for s in agg.constituent_snapshots
                    ],
                }
                for agg_id, agg in sorted(self._aggregates.items())
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore aggregation engine state."""
        self._next_id = state.get("next_id", 0)
        self._aggregates.clear()
        for agg_id, adata in sorted(state.get("aggregates", {}).items()):
            snapshots = [
                UnitSnapshot(
                    unit_state=s["unit_state"],
                    weapon_states=s.get("weapon_states", []),
                    sensor_states=s.get("sensor_states", []),
                    supply_inventory=s.get("supply_inventory"),
                    original_side=s.get("original_side", ""),
                    order_records=s.get("order_records", []),
                )
                for s in sorted(
                    adata["snapshots"],
                    key=lambda item: item["unit_state"]["entity_id"],
                )
            ]
            self._aggregates[agg_id] = AggregateUnit(
                aggregate_id=adata["aggregate_id"],
                side=adata["side"],
                unit_type=adata["unit_type"],
                position=Position(*adata["position"]),
                constituent_snapshots=snapshots,
                aggregate_combat_power=adata["aggregate_combat_power"],
                aggregate_personnel=adata["aggregate_personnel"],
                aggregate_supply_state=adata["aggregate_supply_state"],
            )

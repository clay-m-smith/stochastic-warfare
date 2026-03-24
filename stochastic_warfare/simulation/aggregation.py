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
from stochastic_warfare.morale.state import MoraleState

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
    morale_state: int  # MoraleState enum value
    weapon_states: list[dict] = field(default_factory=list)
    sensor_states: list[dict] = field(default_factory=list)
    supply_inventory: dict | None = None
    original_side: str = ""


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
    morale_state: MoraleState
    parent_id: str | None = None


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

        # Morale
        morale_val = int(MoraleState.STEADY)
        if ctx.morale_states is not None:
            ms = ctx.morale_states.get(unit.entity_id)
            if ms is not None:
                morale_val = int(ms)

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

        return UnitSnapshot(
            unit_state=unit_state,
            morale_state=morale_val,
            weapon_states=weapon_states,
            sensor_states=sensor_states,
            supply_inventory=supply_inv,
            original_side=unit.side if isinstance(unit.side, str) else str(unit.side),
        )

    def aggregate(
        self,
        unit_ids: list[str],
        ctx: Any,
    ) -> AggregateUnit | None:
        """Aggregate units into a composite formation.

        1. Snapshot each unit
        2. Remove from ctx.units_by_side, unit_weapons, unit_sensors,
           morale_states
        3. Create AggregateUnit with merged state
        4. Register proxy Unit in units_by_side
        5. Return the aggregate
        """
        if len(unit_ids) < self._config.min_units_to_aggregate:
            return None

        # Sort for deterministic processing
        unit_ids = sorted(unit_ids)

        # Find units
        units: list[Unit] = []
        for uid in unit_ids:
            for side_units in ctx.units_by_side.values():
                for u in side_units:
                    if u.entity_id == uid and u.status == UnitStatus.ACTIVE:
                        units.append(u)
                        break

        if len(units) < self._config.min_units_to_aggregate:
            return None

        # All must be same side
        sides = {u.side if isinstance(u.side, str) else str(u.side) for u in units}
        if len(sides) != 1:
            return None
        side = sides.pop()

        # Snapshot all units
        snapshots = [self.snapshot_unit(u, ctx) for u in units]

        # Compute aggregate stats
        total_power = 0.0
        total_personnel = 0
        total_supply = 0.0
        supply_count = 0
        worst_morale = MoraleState.STEADY
        positions_e = []
        positions_n = []
        unit_types: set[str] = set()

        for u, snap in zip(units, snapshots):
            personnel = len(u.personnel) if u.personnel else 4
            equipment = len(u.equipment) if u.equipment else 1
            total_power += personnel + equipment * 2.0
            total_personnel += personnel
            unit_types.add(u.unit_type)
            positions_e.append(u.position.easting)
            positions_n.append(u.position.northing)

            morale = MoraleState(snap.morale_state)
            if morale.value > worst_morale.value:
                worst_morale = morale

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

        # Generate aggregate ID
        agg_id = f"agg_{self._next_id:04d}"
        self._next_id += 1

        agg = AggregateUnit(
            aggregate_id=agg_id,
            side=side,
            unit_type=agg_type,
            position=centroid,
            constituent_snapshots=snapshots,
            aggregate_combat_power=total_power,
            aggregate_personnel=total_personnel,
            aggregate_supply_state=avg_supply,
            morale_state=worst_morale,
        )

        # Remove individual units from context
        for u in units:
            side_key = u.side if isinstance(u.side, str) else str(u.side)
            if side_key in ctx.units_by_side:
                ctx.units_by_side[side_key] = [
                    x for x in ctx.units_by_side[side_key]
                    if x.entity_id != u.entity_id
                ]
            ctx.unit_weapons.pop(u.entity_id, None)
            ctx.unit_sensors.pop(u.entity_id, None)
            if ctx.morale_states is not None:
                ctx.morale_states.pop(u.entity_id, None)

        # Create proxy unit for the aggregate
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

        if side in ctx.units_by_side:
            ctx.units_by_side[side].append(proxy)
        else:
            ctx.units_by_side[side] = [proxy]

        # Set aggregate morale
        if ctx.morale_states is not None:
            ctx.morale_states[agg_id] = worst_morale

        self._aggregates[agg_id] = agg

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

        1. Remove proxy from ctx
        2. Recreate units from snapshots
        3. Re-register in all subsystems
        """
        agg = self._aggregates.pop(aggregate_id, None)
        if agg is None:
            return []

        # Remove proxy unit
        side = agg.side
        if side in ctx.units_by_side:
            ctx.units_by_side[side] = [
                u for u in ctx.units_by_side[side]
                if u.entity_id != aggregate_id
            ]
        ctx.unit_weapons.pop(aggregate_id, None)
        ctx.unit_sensors.pop(aggregate_id, None)
        if ctx.morale_states is not None:
            ctx.morale_states.pop(aggregate_id, None)

        # Restore individual units
        restored_ids: list[str] = []
        for snap in agg.constituent_snapshots:
            unit = Unit(
                entity_id=snap.unit_state["entity_id"],
                position=Position(*snap.unit_state["position"]),
            )
            unit.set_state(snap.unit_state)

            orig_side = snap.original_side or side
            if orig_side in ctx.units_by_side:
                ctx.units_by_side[orig_side].append(unit)
            else:
                ctx.units_by_side[orig_side] = [unit]

            # Restore morale
            if ctx.morale_states is not None:
                ctx.morale_states[unit.entity_id] = MoraleState(snap.morale_state)

            restored_ids.append(unit.entity_id)

        logger.info(
            "Disaggregated %s into %d units (side=%s)",
            aggregate_id, len(restored_ids), side,
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
                    "morale_state": int(agg.morale_state),
                    "snapshots": [
                        {
                            "unit_state": s.unit_state,
                            "morale_state": s.morale_state,
                            "weapon_states": s.weapon_states,
                            "sensor_states": s.sensor_states,
                            "supply_inventory": s.supply_inventory,
                            "original_side": s.original_side,
                        }
                        for s in agg.constituent_snapshots
                    ],
                }
                for agg_id, agg in self._aggregates.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore aggregation engine state."""
        self._next_id = state.get("next_id", 0)
        self._aggregates.clear()
        for agg_id, adata in state.get("aggregates", {}).items():
            snapshots = [
                UnitSnapshot(
                    unit_state=s["unit_state"],
                    morale_state=s["morale_state"],
                    weapon_states=s.get("weapon_states", []),
                    sensor_states=s.get("sensor_states", []),
                    supply_inventory=s.get("supply_inventory"),
                    original_side=s.get("original_side", ""),
                )
                for s in adata["snapshots"]
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
                morale_state=MoraleState(adata["morale_state"]),
            )

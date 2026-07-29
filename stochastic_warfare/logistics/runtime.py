"""Deterministic production wiring for scenario logistics."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.types import Position
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.logistics.config import (
    LogisticsConfig,
    RouteTemplateConfig,
    UnitLogisticsProfileConfig,
)
from stochastic_warfare.logistics.stockpile import (
    DepotType,
    StockpileConfig,
    StockpileManager,
)
from stochastic_warfare.logistics.supply_classes import (
    SupplyInventory,
    SupplyItemLoader,
)
from stochastic_warfare.logistics.supply_network import (
    SupplyNetworkEngine,
    SupplyNetworkConfig,
    SupplyNode,
    SupplyRoute,
    TransportMode,
)


_GROUND_STATE_CODES = {
    "DRY": 0,
    "WET": 1,
    "THAWING": 2,
    "SATURATED": 2,
    "SNOW_COVERED": 3,
    "FROZEN": 4,
}


def logistics_ground_state_code(ground_state: Any) -> int:
    """Translate environment ground state to logistics semantics."""
    if ground_state is None:
        return _GROUND_STATE_CODES["DRY"]
    name = getattr(ground_state, "name", None)
    if not isinstance(name, str) or name not in _GROUND_STATE_CODES:
        raise ValueError(f"Unsupported environment ground state {ground_state!r}")
    return _GROUND_STATE_CODES[name]


def _unit_side(unit: Unit) -> str:
    side = unit.side
    return side if isinstance(side, str) else side.value


def _position_tuple(position: Position) -> tuple[float, float, float]:
    return (
        float(position.easting),
        float(position.northing),
        float(position.altitude),
    )


def _position_from_values(values: Sequence[float]) -> Position:
    altitude = float(values[2]) if len(values) == 3 else 0.0
    return Position(float(values[0]), float(values[1]), altitude)


def _inventory(
    entries: Sequence[Any],
) -> SupplyInventory:
    inventory = SupplyInventory()
    for entry in entries:
        inventory.add(
            entry.supply_class_value,
            entry.item_id,
            entry.quantity,
        )
    return inventory


def _supply_map(entries: Sequence[Any]) -> dict[int, dict[str, float]]:
    result: dict[int, dict[str, float]] = {}
    for entry in entries:
        result.setdefault(entry.supply_class_value, {})[
            entry.item_id
        ] = entry.quantity
    return result


def _depot_node_id(depot_id: str) -> str:
    return f"depot:{depot_id}"


def _unit_node_id(unit_id: str) -> str:
    return f"unit:{unit_id}"


def _expanded_route_id(template_id: str, unit_id: str) -> str:
    return f"{template_id}:{unit_id}"


def _require_exact_keys(
    value: Any,
    expected: set[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{label} key topology differs: "
            f"missing={sorted(expected - actual, key=str)!r}, "
            f"extra={sorted(actual - expected, key=str)!r}",
        )
    return value


def _strict_json_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (
            set(actual) == set(expected)
            and all(
                _strict_json_equal(actual[key], expected[key])
                for key in expected
            )
        )
    if isinstance(expected, list):
        return (
            len(actual) == len(expected)
            and all(
                _strict_json_equal(left, right)
                for left, right in zip(actual, expected, strict=True)
            )
        )
    return bool(actual == expected)


def _inventory_item_pairs(
    state: Any,
    label: str,
) -> frozenset[tuple[int, str]]:
    inventory = _require_exact_keys(state, {"items"}, label)
    raw_items = inventory["items"]
    if not isinstance(raw_items, Mapping):
        raise ValueError(f"{label}.items must be a mapping")
    pairs: set[tuple[int, str]] = set()
    for raw_class, items in raw_items.items():
        if not isinstance(raw_class, str):
            raise ValueError(f"{label} supply-class keys must be strings")
        try:
            supply_class = int(raw_class)
        except ValueError as exc:
            raise ValueError(
                f"{label} has invalid supply class {raw_class!r}",
            ) from exc
        if str(supply_class) != raw_class or not isinstance(items, Mapping):
            raise ValueError(
                f"{label} has invalid supply-class bucket {raw_class!r}",
            )
        for item_id in items:
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{label} contains an invalid item ID")
            pairs.add((supply_class, item_id))
    return frozenset(pairs)


def _maximum_state(
    maximum: Mapping[int, Mapping[str, float]],
) -> dict[str, dict[str, float]]:
    return {
        str(supply_class): {
            item_id: float(items[item_id])
            for item_id in sorted(items)
        }
        for supply_class, items in sorted(maximum.items())
    }


@dataclass(frozen=True)
class _UnitRegistration:
    unit_id: str
    inventory: SupplyInventory
    maximum: dict[int, dict[str, float]]
    node: SupplyNode
    routes: tuple[SupplyRoute, ...]
    eligible_from_seconds: float
    boundary_position: tuple[float, float, float]


@dataclass(frozen=True)
class _DepotContract:
    side: str
    depot_type: int
    position: tuple[float, float, float]
    capacity_tons: float
    throughput_tons_per_hour: float
    inventory_items: frozenset[tuple[int, str]]


def _plan_fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _registration_fingerprint(
    registrations: tuple[_UnitRegistration, ...],
) -> str:
    return _plan_fingerprint([
        asdict(registration)
        for registration in registrations
    ])


@dataclass(frozen=True)
class _LogisticsRegistrationPlan:
    """Validated batch of logistics objects for dynamic unit admission."""

    registrations: tuple[_UnitRegistration, ...]
    owner_token: object
    fingerprint: str


@dataclass(frozen=True)
class _LogisticsRestorePlan:
    """Validated, non-mutating logistics checkpoint commit plan."""

    elapsed_accumulator_seconds: float
    last_boundary_elapsed_seconds: float
    unit_eligible_from_seconds: dict[str, float]
    unit_last_accounted_seconds: dict[str, float]
    unit_interval_disqualified: dict[str, bool]
    last_boundary_positions: dict[str, tuple[float, float, float]]
    stockpile_state: dict[str, Any]
    supply_network_state: dict[str, Any]
    owner_token: object
    fingerprint: str


def _restore_plan_payload(plan: _LogisticsRestorePlan) -> dict[str, Any]:
    return {
        "elapsed_accumulator_seconds": plan.elapsed_accumulator_seconds,
        "last_boundary_elapsed_seconds": plan.last_boundary_elapsed_seconds,
        "unit_eligible_from_seconds": plan.unit_eligible_from_seconds,
        "unit_last_accounted_seconds": plan.unit_last_accounted_seconds,
        "unit_interval_disqualified": plan.unit_interval_disqualified,
        "last_boundary_positions": plan.last_boundary_positions,
        "stockpile_state": plan.stockpile_state,
        "supply_network_state": plan.supply_network_state,
    }


class LogisticsRuntime:
    """Own fixed-cadence logistics state and deterministic allocation."""

    def __init__(
        self,
        *,
        config: LogisticsConfig,
        stockpile_manager: StockpileManager,
        supply_network_engine: SupplyNetworkEngine,
        supply_item_loader: SupplyItemLoader,
        disruption_engine: Any = None,
    ) -> None:
        self._config = config
        self._stockpile = stockpile_manager
        self._network = supply_network_engine
        self._item_loader = supply_item_loader
        self._disruption = disruption_engine
        self._plan_owner_token = object()
        self._elapsed_accumulator_seconds = 0.0
        self._last_boundary_elapsed_seconds = 0.0
        self._unit_eligible_from_seconds: dict[str, float] = {}
        self._unit_last_accounted_seconds: dict[str, float] = {}
        self._unit_interval_disqualified: dict[str, bool] = {}
        self._last_boundary_positions: dict[
            str,
            tuple[float, float, float],
        ] = {}
        self._profiles = {
            (profile.side, profile.unit_type): profile
            for profile in config.unit_profiles
        }
        self._templates = tuple(
            sorted(config.route_templates, key=lambda route: route.route_id)
        )
        self._configured_depots: dict[str, _DepotContract] = {}
        self._stockpile_config_state = copy.deepcopy(
            stockpile_manager.get_state()["config"],
        )
        self._network_config_state = copy.deepcopy(
            supply_network_engine.get_state()["config"],
        )

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def stockpile_manager(self) -> StockpileManager:
        return self._stockpile

    @property
    def supply_network_engine(self) -> SupplyNetworkEngine:
        return self._network

    @property
    def elapsed_accumulator_seconds(self) -> float:
        return self._elapsed_accumulator_seconds

    def initialize(
        self,
        depots_by_side: Mapping[str, Sequence[Any]],
        units: Sequence[Unit],
    ) -> None:
        """Atomically materialize configured depots and initial unit topology."""
        if not self.enabled:
            return
        if (
            self._stockpile.list_depots()
            or self._stockpile.registered_unit_ids()
            or self._network.node_count()
            or self._network.route_count()
        ):
            raise ValueError("Logistics runtime is already initialized")

        stockpile_before = self._stockpile.get_state()
        network_before = self._network.get_state()
        depot_contracts_before = dict(self._configured_depots)
        try:
            for side in sorted(depots_by_side):
                depots = sorted(
                    depots_by_side[side],
                    key=lambda depot: depot.depot_id,
                )
                for depot_config in depots:
                    if depot_config.depot_id in self._configured_depots:
                        raise ValueError(
                            f"Duplicate depot ID {depot_config.depot_id!r}",
                        )
                    position = _position_from_values(depot_config.position)
                    depot = self._stockpile.create_depot(
                        depot_config.depot_id,
                        position,
                        DepotType[depot_config.depot_type],
                        side,
                        initial_inventory=_inventory(
                            depot_config.initial_inventory,
                        ),
                        capacity_tons=depot_config.capacity_tons,
                        throughput_tons_per_hour=(
                            depot_config.throughput_tons_per_hour
                        ),
                        condition=depot_config.condition,
                    )
                    self._network.add_node(
                        SupplyNode(
                            node_id=_depot_node_id(depot.depot_id),
                            position=depot.position,
                            node_type="DEPOT",
                            linked_id=depot.depot_id,
                            echelon_level=3,
                            throughput_tons_per_hour=(
                                depot.throughput_tons_per_hour
                            ),
                            side=side,
                        ),
                    )
                    self._configured_depots[depot.depot_id] = _DepotContract(
                        side=side,
                        depot_type=int(depot.depot_type),
                        position=_position_tuple(depot.position),
                        capacity_tons=float(depot.capacity_tons),
                        throughput_tons_per_hour=float(
                            depot.throughput_tons_per_hour,
                        ),
                        inventory_items=_inventory_item_pairs(
                            depot.inventory.get_state(),
                            f"configured depot {depot.depot_id} inventory",
                        ),
                    )

            plan = self.prepare_unit_registration(
                units,
                eligible_from_seconds=0.0,
            )
            self.commit_unit_registration(plan)
        except Exception:
            self._stockpile.set_state(stockpile_before)
            self._network.set_state(network_before)
            self._configured_depots = depot_contracts_before
            self._unit_eligible_from_seconds.clear()
            self._unit_last_accounted_seconds.clear()
            self._unit_interval_disqualified.clear()
            self._last_boundary_positions.clear()
            raise

    def prepare_unit_registration(
        self,
        units: Sequence[Unit],
        *,
        eligible_from_seconds: float,
    ) -> _LogisticsRegistrationPlan:
        """Validate a unit batch without mutating live logistics state."""
        if not self.enabled or not units:
            registrations: tuple[_UnitRegistration, ...] = ()
            return _LogisticsRegistrationPlan(
                registrations=registrations,
                owner_token=self._plan_owner_token,
                fingerprint=_registration_fingerprint(registrations),
            )
        if (
            isinstance(eligible_from_seconds, bool)
            or not isinstance(eligible_from_seconds, (int, float))
            or not math.isfinite(float(eligible_from_seconds))
            or float(eligible_from_seconds) < 0.0
        ):
            raise ValueError(
                "eligible_from_seconds must be finite and non-negative",
            )

        existing_unit_ids = set(self._stockpile.registered_unit_ids())
        existing_node_ids = {
            node.node_id
            for node in self._network.list_nodes()
        }
        existing_route_ids = {
            route.route_id
            for route in self._network.list_routes()
        }
        incoming_ids: set[str] = set()
        registrations: list[_UnitRegistration] = []
        for unit in sorted(units, key=lambda candidate: candidate.entity_id):
            unit_id = unit.entity_id
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or unit_id in existing_unit_ids
                or unit_id in incoming_ids
            ):
                raise ValueError(
                    f"Duplicate or invalid logistics unit ID {unit_id!r}",
                )
            profile = self._profiles.get((_unit_side(unit), unit.unit_type))
            if profile is None:
                raise ValueError(
                    "No logistics profile for "
                    f"{_unit_side(unit)!r}/{unit.unit_type!r}",
                )
            incoming_ids.add(unit_id)
            node_id = _unit_node_id(unit_id)
            if node_id in existing_node_ids:
                raise ValueError(f"Duplicate supply node ID {node_id!r}")
            existing_node_ids.add(node_id)
            node = SupplyNode(
                node_id=node_id,
                position=unit.position,
                node_type="UNIT",
                linked_id=unit_id,
                side=_unit_side(unit),
            )

            routes: list[SupplyRoute] = []
            for template in self._matching_templates(profile):
                depot = self._stockpile.get_depot(template.depot_id)
                route_id = _expanded_route_id(template.route_id, unit_id)
                if route_id in existing_route_ids:
                    raise ValueError(f"Duplicate supply route ID {route_id!r}")
                existing_route_ids.add(route_id)
                distance_m = math.dist(unit.position, depot.position)
                routes.append(
                    SupplyRoute(
                        route_id=route_id,
                        from_node=_depot_node_id(template.depot_id),
                        to_node=node_id,
                        transport_mode=template.transport_mode_value,
                        distance_m=distance_m,
                        capacity_tons_per_hour=(
                            template.capacity_tons_per_hour
                        ),
                        base_transit_time_hours=(
                            distance_m
                            / (template.transport_speed_kph * 1000.0)
                        ),
                        condition=template.condition,
                        transport_speed_kph=template.transport_speed_kph,
                    ),
                )
            registrations.append(
                _UnitRegistration(
                    unit_id=unit_id,
                    inventory=self._profile_inventory(profile),
                    maximum=_supply_map(profile.maximum_inventory),
                    node=node,
                    routes=tuple(routes),
                    eligible_from_seconds=float(eligible_from_seconds),
                    boundary_position=_position_tuple(unit.position),
                ),
            )
        prepared = tuple(registrations)
        return _LogisticsRegistrationPlan(
            registrations=prepared,
            owner_token=self._plan_owner_token,
            fingerprint=_registration_fingerprint(prepared),
        )

    @staticmethod
    def _profile_inventory(
        profile: UnitLogisticsProfileConfig,
    ) -> SupplyInventory:
        """Materialize every configured maximum item, including zero stock."""
        inventory = _inventory(profile.initial_inventory)
        for supply_class, items in sorted(
            _supply_map(profile.maximum_inventory).items(),
        ):
            for item_id in sorted(items):
                if inventory.available(supply_class, item_id) == 0.0:
                    inventory.add(supply_class, item_id, 0.0)
        return inventory

    def commit_unit_registration(
        self,
        plan: _LogisticsRegistrationPlan,
    ) -> None:
        """Atomically commit a previously validated registration batch."""
        if not isinstance(plan, _LogisticsRegistrationPlan):
            raise TypeError("plan must be a logistics registration plan")
        if (
            plan.owner_token is not self._plan_owner_token
            or plan.fingerprint
            != _registration_fingerprint(plan.registrations)
        ):
            raise ValueError(
                "Logistics registration plan is foreign or was mutated",
            )
        if not plan.registrations:
            return
        stockpile_before = self._stockpile.get_state()
        network_before = self._network.get_state()
        eligible_before = dict(self._unit_eligible_from_seconds)
        accounted_before = dict(self._unit_last_accounted_seconds)
        disqualified_before = dict(self._unit_interval_disqualified)
        positions_before = dict(self._last_boundary_positions)
        try:
            for registration in plan.registrations:
                self._stockpile.register_unit_inventory(
                    registration.unit_id,
                    registration.inventory,
                    max_supplies=registration.maximum,
                )
                self._network.add_node(registration.node)
                for route in registration.routes:
                    self._network.add_route(route)
                self._unit_eligible_from_seconds[registration.unit_id] = (
                    registration.eligible_from_seconds
                )
                self._unit_last_accounted_seconds[registration.unit_id] = (
                    registration.eligible_from_seconds
                )
                self._unit_interval_disqualified[registration.unit_id] = False
                self._last_boundary_positions[registration.unit_id] = (
                    registration.boundary_position
                )
        except Exception:
            self._stockpile.set_state(stockpile_before)
            self._network.set_state(network_before)
            self._unit_eligible_from_seconds = eligible_before
            self._unit_last_accounted_seconds = accounted_before
            self._unit_interval_disqualified = disqualified_before
            self._last_boundary_positions = positions_before
            raise

    def _matching_templates(
        self,
        profile: UnitLogisticsProfileConfig,
    ) -> tuple[RouteTemplateConfig, ...]:
        return tuple(
            template
            for template in self._templates
            if (
                template.side == profile.side
                and profile.unit_type in template.unit_types
            )
        )

    def note_interval_activity(self, unit_ids: Sequence[str] | set[str]) -> None:
        """Disqualify registered units from idle debit in the open interval."""
        if not self.enabled:
            return
        for unit_id in sorted(set(unit_ids)):
            if unit_id in self._unit_interval_disqualified:
                self._unit_interval_disqualified[unit_id] = True

    def update(
        self,
        *,
        dt_seconds: float,
        interval_end: datetime,
        interval_end_elapsed_seconds: float,
        units: Sequence[Unit],
        active_battle_unit_ids: set[str] | frozenset[str] = frozenset(),
        ground_state: Any = None,
        enable_supply_network: bool = True,
    ) -> None:
        """Advance all complete fixed logistics quanta in logical time."""
        if not self.enabled:
            return
        if (
            isinstance(dt_seconds, bool)
            or not isinstance(dt_seconds, (int, float))
            or not math.isfinite(float(dt_seconds))
            or float(dt_seconds) < 0.0
        ):
            raise ValueError("dt_seconds must be finite and non-negative")
        if not isinstance(interval_end, datetime):
            raise TypeError("interval_end must be a datetime")
        if (
            isinstance(interval_end_elapsed_seconds, bool)
            or not isinstance(interval_end_elapsed_seconds, (int, float))
            or not math.isfinite(float(interval_end_elapsed_seconds))
            or float(interval_end_elapsed_seconds) < float(dt_seconds)
        ):
            raise ValueError(
                "interval_end_elapsed_seconds must be finite and not precede "
                "the tick start",
            )
        if not isinstance(enable_supply_network, bool):
            raise TypeError("enable_supply_network must be boolean")

        unit_map = {unit.entity_id: unit for unit in units}
        if len(unit_map) != len(units):
            raise ValueError("Live logistics units contain duplicate IDs")
        missing_units = sorted(
            set(self._unit_eligible_from_seconds) - set(unit_map),
        )
        if missing_units:
            raise ValueError(
                f"Logistics topology contains missing live units {missing_units!r}",
            )
        persistent_disqualified = {
            unit_id: (
                unit_map[unit_id].status is not UnitStatus.ACTIVE
                or unit_id in active_battle_unit_ids
            )
            for unit_id in sorted(self._unit_eligible_from_seconds)
        }
        sampled_disqualified = {
            unit_id: (
                persistent_disqualified[unit_id]
                or _position_tuple(unit_map[unit_id].position)
                != self._last_boundary_positions[unit_id]
            )
            for unit_id in sorted(self._unit_eligible_from_seconds)
        }

        interval = self._config.update_interval_seconds
        total = self._elapsed_accumulator_seconds + float(dt_seconds)
        epsilon = min(
            interval * 1e-9,
            max(math.ulp(total), math.ulp(interval)) * 4.0,
        )
        tracked_tick_start = (
            self._last_boundary_elapsed_seconds
            + self._elapsed_accumulator_seconds
        )
        supplied_tick_start = (
            float(interval_end_elapsed_seconds) - float(dt_seconds)
        )
        chronology_tolerance = max(
            interval * 1e-12,
            math.ulp(tracked_tick_start) * 8.0,
            math.ulp(supplied_tick_start) * 8.0,
        )
        if not math.isclose(
            tracked_tick_start,
            supplied_tick_start,
            rel_tol=0.0,
            abs_tol=chronology_tolerance,
        ):
            raise ValueError(
                "Logistics cadence does not match the supplied logical tick",
            )

        for unit_id, disqualified in sampled_disqualified.items():
            self._unit_interval_disqualified[unit_id] |= disqualified
        self._elapsed_accumulator_seconds = total
        complete_quanta = int(math.floor((total + epsilon) / interval))
        if complete_quanta == 0:
            return

        for quantum_index in range(complete_quanta):
            boundary_elapsed = (
                self._last_boundary_elapsed_seconds + interval
            )
            boundary_timestamp = interval_end - timedelta(
                seconds=(
                    float(interval_end_elapsed_seconds)
                    - boundary_elapsed
                ),
            )
            boundary_events: list[Event] = []
            self._run_quantum(
                boundary_elapsed_seconds=boundary_elapsed,
                boundary_timestamp=boundary_timestamp,
                units=unit_map,
                interval_disqualified=self._unit_interval_disqualified,
                ground_state=ground_state,
                enable_supply_network=enable_supply_network,
                event_sink=boundary_events,
            )
            self._last_boundary_elapsed_seconds = boundary_elapsed
            remaining = total - (quantum_index + 1) * interval
            self._elapsed_accumulator_seconds = (
                0.0 if abs(remaining) <= epsilon else remaining
            )
            self._unit_interval_disqualified = {
                unit_id: (
                    persistent_disqualified[unit_id]
                    if remaining > epsilon
                    else False
                )
                for unit_id in sorted(sampled_disqualified)
            }
            # Events are post-commit notifications for exactly one boundary.
            # All observers are attempted before subscriber errors propagate;
            # committed cadence is never rolled back or retried.
            self._stockpile.publish_events(boundary_events)

    def _run_quantum(
        self,
        *,
        boundary_elapsed_seconds: float,
        boundary_timestamp: datetime,
        units: Mapping[str, Unit],
        interval_disqualified: Mapping[str, bool],
        ground_state: Any,
        enable_supply_network: bool,
        event_sink: list[Event],
    ) -> None:
        interval_seconds = self._config.update_interval_seconds
        interval_hours = interval_seconds / 3600.0
        interval_start = boundary_elapsed_seconds - interval_seconds
        eligible_seconds = {
            unit_id: max(
                0.0,
                boundary_elapsed_seconds
                - max(
                    interval_start,
                    self._unit_last_accounted_seconds[unit_id],
                    eligible_from,
                ),
            )
            for unit_id, eligible_from in sorted(
                self._unit_eligible_from_seconds.items(),
            )
        }
        eligible_ids = {
            unit_id
            for unit_id, duration in eligible_seconds.items()
            if duration > 0.0
        }
        network_before = self._network.get_state()
        stockpile_before = self._stockpile.get_state()
        positions_before = dict(self._last_boundary_positions)
        accounted_before = dict(self._unit_last_accounted_seconds)
        try:
            for unit_id in sorted(self._unit_eligible_from_seconds):
                unit = units.get(unit_id)
                if unit is None:
                    continue
                self._network.update_node_position(
                    _unit_node_id(unit_id),
                    unit.position,
                )
            self._network.begin_flow_interval()
            if enable_supply_network:
                self._network.update(
                    interval_hours,
                    logistics_ground_state_code(ground_state),
                )
                self._apply_blockades()
                self._resupply(
                    units=units,
                    eligible_ids=eligible_ids,
                    interval_hours=interval_hours,
                    eligible_seconds=eligible_seconds,
                    timestamp=boundary_timestamp,
                    event_sink=event_sink,
                )
            self._consume_idle(
                units=units,
                eligible_ids=eligible_ids,
                interval_disqualified=interval_disqualified,
                eligible_seconds=eligible_seconds,
                timestamp=boundary_timestamp,
                event_sink=event_sink,
            )
            for unit_id in sorted(self._unit_eligible_from_seconds):
                unit = units.get(unit_id)
                if unit is not None:
                    self._last_boundary_positions[unit_id] = (
                        _position_tuple(unit.position)
                    )
                if (
                    self._unit_eligible_from_seconds[unit_id]
                    <= boundary_elapsed_seconds
                ):
                    self._unit_last_accounted_seconds[unit_id] = (
                        boundary_elapsed_seconds
                    )
        except Exception:
            self._stockpile.set_state(stockpile_before)
            self._network.set_state(network_before)
            self._last_boundary_positions = positions_before
            self._unit_last_accounted_seconds = accounted_before
            raise

    def _apply_blockades(self) -> None:
        if self._disruption is None:
            return
        blockades = sorted(
            self._disruption.active_blockades(),
            key=lambda blockade: blockade.blockade_id,
        )
        max_effectiveness = 0.0
        for blockade in blockades:
            for zone_id in sorted(blockade.sea_zone_ids):
                max_effectiveness = max(
                    max_effectiveness,
                    float(self._disruption.check_blockade(zone_id)),
                )
        if max_effectiveness <= 0.0:
            return
        penalty = max(0.01, 1.0 - max_effectiveness)
        for route in self._network.list_routes():
            if route.transport_mode is TransportMode.SEA:
                self._network.update_route_condition(
                    route.route_id,
                    route.condition * penalty,
                )

    def _resupply(
        self,
        *,
        units: Mapping[str, Unit],
        eligible_ids: set[str],
        interval_hours: float,
        eligible_seconds: Mapping[str, float],
        timestamp: datetime,
        event_sink: list[Event],
    ) -> None:
        depot_remaining_tons = {
            depot.depot_id: (
                depot.throughput_tons_per_hour
                * depot.condition
                * interval_hours
            )
            for depot in self._stockpile.list_depots()
        }
        recipient_depot_remaining_tons: dict[tuple[str, str], float] = {}
        recipient_route_remaining_tons: dict[
            tuple[str, tuple[str, ...]],
            float,
        ] = {}
        for side in sorted({_unit_side(unit) for unit in units.values()}):
            side_depot_nodes = self._network.list_nodes(
                side=side,
                node_type="DEPOT",
            )
            depot_node_ids = [node.node_id for node in side_depot_nodes]
            side_units = sorted(
                (
                    unit
                    for unit in units.values()
                    if (
                        _unit_side(unit) == side
                        and unit.entity_id in eligible_ids
                        and unit.status is UnitStatus.ACTIVE
                    )
                ),
                key=lambda unit: unit.entity_id,
            )
            for unit in side_units:
                deficits = self._stockpile.get_unit_deficits(unit.entity_id)
                if not deficits:
                    continue
                candidates = self._network.reachable_direct_depot_paths(
                    _unit_node_id(unit.entity_id),
                    depot_node_ids,
                )
                for supply_class in sorted(deficits):
                    for item_id in sorted(deficits[supply_class]):
                        remaining_quantity = deficits[supply_class][item_id]
                        for depot_node_id, route_path in candidates:
                            if remaining_quantity <= 0.0:
                                break
                            depot_node = self._network.get_node(depot_node_id)
                            depot_id = depot_node.linked_id
                            if depot_id is None:
                                raise ValueError(
                                    f"Depot node {depot_node_id!r} is unlinked",
                                )
                            depot = self._stockpile.get_depot(depot_id)
                            if (
                                depot.side != side
                                or depot.inventory.available(
                                    supply_class,
                                    item_id,
                                )
                                <= 0.0
                            ):
                                continue
                            eligible_hours = (
                                eligible_seconds[unit.entity_id] / 3600.0
                            )
                            recipient_depot_key = (
                                unit.entity_id,
                                depot_id,
                            )
                            if (
                                recipient_depot_key
                                not in recipient_depot_remaining_tons
                            ):
                                recipient_depot_remaining_tons[
                                    recipient_depot_key
                                ] = (
                                    depot.throughput_tons_per_hour
                                    * depot.condition
                                    * eligible_hours
                                )
                            route_key = (
                                unit.entity_id,
                                tuple(
                                    route.route_id
                                    for route in route_path
                                ),
                            )
                            if route_key not in recipient_route_remaining_tons:
                                recipient_route_remaining_tons[route_key] = min(
                                    self._network.remaining_route_capacity_tons(
                                        route_path,
                                        interval_hours,
                                    ),
                                    self._network.compute_route_capacity(
                                        route_path,
                                    ) * eligible_hours,
                                )
                            max_tons = min(
                                depot_remaining_tons[depot_id],
                                recipient_depot_remaining_tons[
                                    recipient_depot_key
                                ],
                                recipient_route_remaining_tons[route_key],
                            )
                            if max_tons <= 0.0:
                                continue
                            delivery = self._stockpile.deliver_to_unit(
                                depot_id,
                                unit.entity_id,
                                supply_class,
                                item_id,
                                remaining_quantity,
                                max_tons,
                                timestamp,
                                int(route_path[0].transport_mode),
                                route_id=route_path[0].route_id,
                                event_sink=event_sink,
                            )
                            if delivery.quantity <= 0.0:
                                continue
                            self._network.record_route_flow(
                                route_path,
                                delivery.quantity_tons,
                                interval_hours,
                            )
                            depot_remaining_tons[depot_id] -= (
                                delivery.quantity_tons
                            )
                            recipient_depot_remaining_tons[
                                recipient_depot_key
                            ] -= delivery.quantity_tons
                            recipient_route_remaining_tons[
                                route_key
                            ] -= delivery.quantity_tons
                            remaining_quantity -= delivery.quantity

    def _consume_idle(
        self,
        *,
        units: Mapping[str, Unit],
        eligible_ids: set[str],
        interval_disqualified: Mapping[str, bool],
        eligible_seconds: Mapping[str, float],
        timestamp: datetime,
        event_sink: list[Event],
    ) -> None:
        for unit_id in sorted(eligible_ids):
            unit = units[unit_id]
            if (
                unit.status is not UnitStatus.ACTIVE
                or interval_disqualified.get(unit_id, True)
            ):
                continue
            profile = self._profiles[(_unit_side(unit), unit.unit_type)]
            eligible_hours = eligible_seconds[unit_id] / 3600.0
            consumption = {
                supply_class: {
                    item_id: quantity * eligible_hours
                    for item_id, quantity in sorted(items.items())
                }
                for supply_class, items in sorted(
                    _supply_map(
                        profile.idle_consumption_per_hour,
                    ).items(),
                )
            }
            if consumption:
                self._stockpile.consume_unit_supplies(
                    unit_id,
                    consumption,
                    timestamp=timestamp,
                    event_sink=event_sink,
                )

    def get_state(self) -> dict[str, Any]:
        """Return complete, JSON-safe runtime state."""
        return {
            "elapsed_accumulator_seconds": (
                self._elapsed_accumulator_seconds
            ),
            "last_boundary_elapsed_seconds": (
                self._last_boundary_elapsed_seconds
            ),
            "unit_eligible_from_seconds": {
                unit_id: self._unit_eligible_from_seconds[unit_id]
                for unit_id in sorted(self._unit_eligible_from_seconds)
            },
            "unit_last_accounted_seconds": {
                unit_id: self._unit_last_accounted_seconds[unit_id]
                for unit_id in sorted(self._unit_last_accounted_seconds)
            },
            "unit_interval_disqualified": {
                unit_id: self._unit_interval_disqualified[unit_id]
                for unit_id in sorted(self._unit_interval_disqualified)
            },
            "last_boundary_positions": {
                unit_id: list(self._last_boundary_positions[unit_id])
                for unit_id in sorted(self._last_boundary_positions)
            },
            "stockpile": self._stockpile.get_state(),
            "supply_network": self._network.get_state(),
        }

    def _validate_checkpoint_envelopes(
        self,
        stockpile_state: Any,
        network_state: Any,
    ) -> None:
        stockpile = _require_exact_keys(
            stockpile_state,
            {
                "config",
                "depots",
                "unit_inventories",
                "unit_max_supplies",
                "spoilage_accumulator",
            },
            "checkpoint stockpile",
        )
        stockpile_config = _require_exact_keys(
            stockpile["config"],
            set(self._stockpile_config_state),
            "checkpoint stockpile config",
        )
        try:
            StockpileConfig.model_validate(
                dict(stockpile_config),
                strict=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Checkpoint stockpile config is invalid",
            ) from exc
        if not _strict_json_equal(
            dict(stockpile_config),
            self._stockpile_config_state,
        ):
            raise ValueError(
                "Checkpoint stockpile config differs from the scenario",
            )
        raw_depots = stockpile["depots"]
        raw_inventories = stockpile["unit_inventories"]
        raw_maxima = stockpile["unit_max_supplies"]
        if not isinstance(raw_depots, Mapping):
            raise ValueError("Checkpoint depots must be a mapping")
        if not isinstance(raw_inventories, Mapping):
            raise ValueError("Checkpoint unit inventories must be a mapping")
        if not isinstance(raw_maxima, Mapping):
            raise ValueError("Checkpoint unit maxima must be a mapping")
        for depot_id, depot in raw_depots.items():
            _require_exact_keys(
                depot,
                {
                    "depot_id",
                    "position",
                    "depot_type",
                    "side",
                    "inventory",
                    "capacity_tons",
                    "throughput_tons_per_hour",
                    "condition",
                },
                f"checkpoint depot {depot_id!r}",
            )
            _inventory_item_pairs(
                depot["inventory"],
                f"checkpoint depot {depot_id!r} inventory",
            )
        for unit_id, inventory in raw_inventories.items():
            _inventory_item_pairs(
                inventory,
                f"checkpoint unit {unit_id!r} inventory",
            )
        for unit_id, maximum in raw_maxima.items():
            _inventory_item_pairs(
                {"items": maximum},
                f"checkpoint unit {unit_id!r} maximum",
            )

        network = _require_exact_keys(
            network_state,
            {"config", "nodes", "routes"},
            "checkpoint supply network",
        )
        network_config = _require_exact_keys(
            network["config"],
            set(self._network_config_state),
            "checkpoint supply-network config",
        )
        try:
            SupplyNetworkConfig.model_validate(
                dict(network_config),
                strict=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Checkpoint supply-network config is invalid",
            ) from exc
        if not _strict_json_equal(
            dict(network_config),
            self._network_config_state,
        ):
            raise ValueError(
                "Checkpoint supply-network config differs from the scenario",
            )
        raw_nodes = network["nodes"]
        raw_routes = network["routes"]
        if not isinstance(raw_nodes, Mapping):
            raise ValueError("Checkpoint supply nodes must be a mapping")
        if not isinstance(raw_routes, Mapping):
            raise ValueError("Checkpoint supply routes must be a mapping")
        for node_id, node in raw_nodes.items():
            _require_exact_keys(
                node,
                {
                    "node_id",
                    "position",
                    "node_type",
                    "linked_id",
                    "echelon_level",
                    "infrastructure_id",
                    "throughput_tons_per_hour",
                    "side",
                },
                f"checkpoint supply node {node_id!r}",
            )
        for route_id, route in raw_routes.items():
            _require_exact_keys(
                route,
                {
                    "route_id",
                    "from_node",
                    "to_node",
                    "transport_mode",
                    "distance_m",
                    "capacity_tons_per_hour",
                    "base_transit_time_hours",
                    "condition",
                    "current_flow_tons_per_hour",
                    "infrastructure_ids",
                    "transport_speed_kph",
                },
                f"checkpoint supply route {route_id!r}",
            )

    def _validate_catalog_pairs(
        self,
        pairs: frozenset[tuple[int, str]],
        label: str,
    ) -> None:
        for supply_class, item_id in sorted(pairs):
            try:
                definition = self._item_loader.get_definition(item_id)
                catalog_class = int(definition.supply_class_enum)
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"{label} references unknown catalog item {item_id!r}",
                ) from exc
            if catalog_class != supply_class:
                raise ValueError(
                    f"{label} assigns item {item_id!r} to supply class "
                    f"{supply_class}, expected {catalog_class}",
                )

    def stage_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_units: Mapping[str, Unit] | Sequence[Unit] | None = None,
        expected_elapsed_seconds: float | None = None,
    ) -> _LogisticsRestorePlan:
        """Validate checkpoint state without mutating live runtime objects."""
        if not isinstance(state, Mapping):
            raise TypeError("Logistics runtime state must be a mapping")
        expected_keys = {
            "elapsed_accumulator_seconds",
            "last_boundary_elapsed_seconds",
            "unit_eligible_from_seconds",
            "unit_last_accounted_seconds",
            "unit_interval_disqualified",
            "last_boundary_positions",
            "stockpile",
            "supply_network",
        }
        if set(state) != expected_keys:
            raise ValueError(
                "Logistics runtime state key topology differs: "
                f"missing={sorted(expected_keys - set(state))!r}, "
                f"extra={sorted(set(state) - expected_keys)!r}",
            )
        accumulator = state["elapsed_accumulator_seconds"]
        if (
            isinstance(accumulator, bool)
            or not isinstance(accumulator, (int, float))
            or not math.isfinite(float(accumulator))
            or float(accumulator) < 0.0
        ):
            raise ValueError(
                "elapsed_accumulator_seconds must be finite and non-negative",
            )
        last_boundary = state["last_boundary_elapsed_seconds"]
        if (
            isinstance(last_boundary, bool)
            or not isinstance(last_boundary, (int, float))
            or not math.isfinite(float(last_boundary))
            or float(last_boundary) < 0.0
        ):
            raise ValueError(
                "last_boundary_elapsed_seconds must be finite and "
                "non-negative",
            )
        if not self.enabled and (
            float(accumulator) != 0.0
            or float(last_boundary) != 0.0
        ):
            raise ValueError(
                "Disabled logistics runtime cadence state must remain zero",
            )
        boundary_multiple = (
            float(last_boundary) / self._config.update_interval_seconds
        )
        if (
            not math.isfinite(boundary_multiple)
            or not math.isclose(
                boundary_multiple,
                round(boundary_multiple),
                rel_tol=0.0,
                abs_tol=max(
                    math.ulp(boundary_multiple) * 8.0,
                    1e-12,
                ),
            )
        ):
            raise ValueError(
                "last_boundary_elapsed_seconds is not on the configured "
                "cadence",
            )

        raw_eligible = state["unit_eligible_from_seconds"]
        raw_accounted = state["unit_last_accounted_seconds"]
        raw_disqualified = state["unit_interval_disqualified"]
        raw_positions = state["last_boundary_positions"]
        if not isinstance(raw_eligible, Mapping):
            raise ValueError("unit_eligible_from_seconds must be a mapping")
        if not isinstance(raw_accounted, Mapping):
            raise ValueError(
                "unit_last_accounted_seconds must be a mapping",
            )
        if not isinstance(raw_disqualified, Mapping):
            raise ValueError(
                "unit_interval_disqualified must be a mapping",
            )
        if not isinstance(raw_positions, Mapping):
            raise ValueError("last_boundary_positions must be a mapping")
        eligible: dict[str, float] = {}
        accounted: dict[str, float] = {}
        disqualified: dict[str, bool] = {}
        positions: dict[str, tuple[float, float, float]] = {}
        for unit_id, value in raw_eligible.items():
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"Invalid logistics eligibility for {unit_id!r}",
                )
            eligible[unit_id] = float(value)
        for unit_id, value in raw_accounted.items():
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"Invalid logistics accounting time for {unit_id!r}",
                )
            accounted[unit_id] = float(value)
        for unit_id, value in raw_disqualified.items():
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or not isinstance(value, bool)
            ):
                raise ValueError(
                    f"Invalid interval activity state for {unit_id!r}",
                )
            disqualified[unit_id] = value
        for unit_id, values in raw_positions.items():
            if (
                not isinstance(unit_id, str)
                or not isinstance(values, (list, tuple))
                or len(values) != 3
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    for value in values
                )
            ):
                raise ValueError(
                    f"Invalid last boundary position for {unit_id!r}",
                )
            positions[unit_id] = tuple(float(value) for value in values)
        if not (
            set(eligible)
            == set(accounted)
            == set(disqualified)
            == set(positions)
        ):
            raise ValueError(
                "Logistics eligibility, accounting, and boundary-position "
                "topology differ",
            )
        if expected_elapsed_seconds is not None:
            if (
                isinstance(expected_elapsed_seconds, bool)
                or not isinstance(expected_elapsed_seconds, (int, float))
                or not math.isfinite(float(expected_elapsed_seconds))
                or float(expected_elapsed_seconds) < 0.0
            ):
                raise ValueError(
                    "expected_elapsed_seconds must be finite and non-negative",
                )
            expected_elapsed = float(expected_elapsed_seconds)
            time_epsilon = max(
                math.ulp(expected_elapsed),
                math.ulp(self._config.update_interval_seconds),
            ) * 8.0
            for unit_id in eligible:
                if (
                    eligible[unit_id] > expected_elapsed + time_epsilon
                    or accounted[unit_id] > expected_elapsed + time_epsilon
                ):
                    raise ValueError(
                        f"Unit {unit_id!r} logistics time exceeds checkpoint "
                        "clock",
                    )
            if float(last_boundary) > expected_elapsed + time_epsilon:
                raise ValueError(
                    "Last logistics boundary exceeds checkpoint clock",
                )
            if self.enabled:
                expected_accumulator = expected_elapsed - float(last_boundary)
                if not math.isclose(
                    float(accumulator),
                    expected_accumulator,
                    rel_tol=0.0,
                    abs_tol=time_epsilon,
                ):
                    raise ValueError(
                        "Logistics cadence accumulator disagrees with "
                        "checkpoint clock",
                    )
        for unit_id in eligible:
            expected_accounted = max(
                float(last_boundary),
                eligible[unit_id],
            )
            accounting_tolerance = max(
                math.ulp(expected_accounted) * 8.0,
                math.ulp(accounted[unit_id]) * 8.0,
                math.ulp(self._config.update_interval_seconds) * 8.0,
            )
            if not math.isclose(
                accounted[unit_id],
                expected_accounted,
                rel_tol=0.0,
                abs_tol=accounting_tolerance,
            ):
                raise ValueError(
                    f"Unit {unit_id!r} accounting time disagrees with the "
                    "last committed boundary and eligibility",
                )

        self._validate_checkpoint_envelopes(
            state["stockpile"],
            state["supply_network"],
        )
        # Manager set_state() stages complete replacement containers before
        # assignment, so shallow shells isolate validation without recursively
        # copying the shared EventBus, subscribers, recorder, or RNG streams.
        staged_stockpile = copy.copy(self._stockpile)
        staged_network = copy.copy(self._network)
        staged_stockpile.set_state(copy.deepcopy(dict(state["stockpile"])))
        staged_network.set_state(
            copy.deepcopy(dict(state["supply_network"])),
        )

        if expected_units is None:
            unit_map = {
                unit_id: None
                for unit_id in self._stockpile.registered_unit_ids()
            }
        elif isinstance(expected_units, Mapping):
            unit_map = dict(expected_units)
        else:
            unit_map = {
                unit.entity_id: unit
                for unit in expected_units
            }
        expected_registered = {
            unit_id
            for unit_id, unit in unit_map.items()
            if (
                unit is None
                or (_unit_side(unit), unit.unit_type) in self._profiles
            )
        } if self.enabled else set()
        if set(eligible) != expected_registered:
            raise ValueError(
                "Checkpoint logistics unit topology disagrees with the "
                f"force roster: expected={sorted(expected_registered)!r}, "
                f"actual={sorted(eligible)!r}",
            )
        if set(staged_stockpile.registered_unit_ids()) != expected_registered:
            raise ValueError(
                "Checkpoint stockpile unit topology disagrees with the roster",
            )
        if {
            depot.depot_id
            for depot in staged_stockpile.list_depots()
        } != set(self._configured_depots):
            raise ValueError("Checkpoint depot topology differs from scenario")

        expected_node_ids = {
            _depot_node_id(depot_id)
            for depot_id in self._configured_depots
        } | {
            _unit_node_id(unit_id)
            for unit_id in expected_registered
        }
        if {
            node.node_id
            for node in staged_network.list_nodes()
        } != expected_node_ids:
            raise ValueError("Checkpoint supply-node topology differs")

        staged_stockpile_state = staged_stockpile.get_state()
        current_stockpile_state = self._stockpile.get_state()
        expected_route_signatures: dict[
            str,
            tuple[str, str, int, float, float],
        ] = {}
        for unit_id in sorted(expected_registered):
            unit = unit_map.get(unit_id)
            if unit is None:
                current_node = self._network.get_node(_unit_node_id(unit_id))
                side = current_node.side
                expected_maximum = current_stockpile_state[
                    "unit_max_supplies"
                ][unit_id]
                matching = [
                    route
                    for route in self._network.list_routes()
                    if route.to_node == _unit_node_id(unit_id)
                ]
                for route in matching:
                    if route.transport_speed_kph is None:
                        raise ValueError(
                            f"Live route {route.route_id!r} has no speed",
                        )
                    expected_route_signatures[route.route_id] = (
                        route.from_node,
                        route.to_node,
                        int(route.transport_mode),
                        float(route.capacity_tons_per_hour),
                        float(route.transport_speed_kph),
                    )
            else:
                profile = self._profiles[(_unit_side(unit), unit.unit_type)]
                side = profile.side
                expected_maximum = _maximum_state(
                    _supply_map(profile.maximum_inventory),
                )
                for template in self._matching_templates(profile):
                    route_id = _expanded_route_id(
                        template.route_id,
                        unit_id,
                    )
                    expected_route_signatures[route_id] = (
                        _depot_node_id(template.depot_id),
                        _unit_node_id(unit_id),
                        int(template.transport_mode_value),
                        float(template.capacity_tons_per_hour),
                        float(template.transport_speed_kph),
                    )

            staged_maximum = staged_stockpile_state[
                "unit_max_supplies"
            ][unit_id]
            if not _strict_json_equal(
                staged_maximum,
                expected_maximum,
            ):
                raise ValueError(
                    f"Checkpoint unit {unit_id!r} maxima differ from its "
                    "scenario profile",
                )
            maximum_pairs = _inventory_item_pairs(
                {"items": staged_maximum},
                f"checkpoint unit {unit_id!r} maximum",
            )
            inventory_pairs = _inventory_item_pairs(
                staged_stockpile_state["unit_inventories"][unit_id],
                f"checkpoint unit {unit_id!r} inventory",
            )
            self._validate_catalog_pairs(
                maximum_pairs,
                f"checkpoint unit {unit_id!r} maximum",
            )
            self._validate_catalog_pairs(
                inventory_pairs,
                f"checkpoint unit {unit_id!r} inventory",
            )
            if inventory_pairs != maximum_pairs:
                raise ValueError(
                    f"Checkpoint unit {unit_id!r} inventory item topology "
                    "differs from its profile",
                )

            node = staged_network.get_node(_unit_node_id(unit_id))
            if (
                node.node_type != "UNIT"
                or node.linked_id != unit_id
                or node.side != side
                or node.echelon_level != 0
                or node.infrastructure_id is not None
                or node.throughput_tons_per_hour != 100.0
                or _position_tuple(node.position) != positions[unit_id]
            ):
                raise ValueError(
                    f"Checkpoint unit node {unit_id!r} has invalid identity",
                )
            if (
                unit is not None
                and not disqualified[unit_id]
                and positions[unit_id] != _position_tuple(unit.position)
            ):
                raise ValueError(
                    f"Checkpoint unit {unit_id!r} boundary position disagrees "
                    "with its staged unit position while the activity latch "
                    "is clear",
                )
        if {
            route.route_id
            for route in staged_network.list_routes()
        } != set(expected_route_signatures):
            raise ValueError("Checkpoint supply-route topology differs")

        for depot_id, contract in sorted(self._configured_depots.items()):
            depot = staged_stockpile.get_depot(depot_id)
            node = staged_network.get_node(_depot_node_id(depot_id))
            if (
                depot.side != contract.side
                or int(depot.depot_type) != contract.depot_type
                or _position_tuple(depot.position) != contract.position
                or depot.capacity_tons != contract.capacity_tons
                or (
                    depot.throughput_tons_per_hour
                    != contract.throughput_tons_per_hour
                )
                or node.node_type != "DEPOT"
                or node.linked_id != depot_id
                or node.side != contract.side
                or node.echelon_level != 3
                or node.infrastructure_id is not None
                or (
                    node.throughput_tons_per_hour
                    != contract.throughput_tons_per_hour
                )
                or _position_tuple(node.position) != contract.position
            ):
                raise ValueError(
                    f"Checkpoint depot {depot_id!r} differs from its scenario "
                    "declaration",
                )
            depot_pairs = _inventory_item_pairs(
                staged_stockpile_state["depots"][depot_id]["inventory"],
                f"checkpoint depot {depot_id!r} inventory",
            )
            self._validate_catalog_pairs(
                depot_pairs,
                f"checkpoint depot {depot_id!r} inventory",
            )
            if depot_pairs != contract.inventory_items:
                raise ValueError(
                    f"Checkpoint depot {depot_id!r} item topology differs "
                    "from its scenario declaration",
                )
            if (
                depot.inventory.total_weight(self._item_loader)
                > depot.capacity_tons * 1000.0 + 1e-9
            ):
                raise ValueError(
                    f"Checkpoint depot {depot_id!r} exceeds capacity",
                )

        for route_id, signature in sorted(
            expected_route_signatures.items(),
        ):
            route = staged_network.get_route(route_id)
            from_node, to_node, mode, capacity, speed = signature
            if (
                route.from_node != from_node
                or route.to_node != to_node
                or int(route.transport_mode) != mode
                or route.capacity_tons_per_hour != capacity
                or route.transport_speed_kph != speed
                or route.infrastructure_ids
            ):
                raise ValueError(
                    f"Checkpoint route {route_id!r} differs from its scenario "
                    "template",
                )
            expected_distance = math.dist(
                staged_network.get_node(from_node).position,
                staged_network.get_node(to_node).position,
            )
            expected_transit = expected_distance / 1000.0 / speed
            geometry_tolerance = max(
                1e-12,
                math.ulp(expected_distance) * 8.0,
                math.ulp(expected_transit) * 8.0,
            )
            if (
                not math.isclose(
                    route.distance_m,
                    expected_distance,
                    rel_tol=0.0,
                    abs_tol=geometry_tolerance,
                )
                or not math.isclose(
                    route.base_transit_time_hours,
                    expected_transit,
                    rel_tol=0.0,
                    abs_tol=geometry_tolerance,
                )
            ):
                raise ValueError(
                    f"Checkpoint route {route_id!r} geometry is inconsistent",
                )

        plan = _LogisticsRestorePlan(
            elapsed_accumulator_seconds=float(accumulator),
            last_boundary_elapsed_seconds=float(last_boundary),
            unit_eligible_from_seconds=eligible,
            unit_last_accounted_seconds=accounted,
            unit_interval_disqualified=disqualified,
            last_boundary_positions=positions,
            stockpile_state=copy.deepcopy(dict(state["stockpile"])),
            supply_network_state=copy.deepcopy(
                dict(state["supply_network"]),
            ),
            owner_token=self._plan_owner_token,
            fingerprint="",
        )
        return replace(
            plan,
            fingerprint=_plan_fingerprint(_restore_plan_payload(plan)),
        )

    def commit_state(self, plan: _LogisticsRestorePlan) -> None:
        """Commit a prevalidated restore plan while retaining manager identity."""
        if not isinstance(plan, _LogisticsRestorePlan):
            raise TypeError("plan must be a logistics restore plan")
        if (
            plan.owner_token is not self._plan_owner_token
            or plan.fingerprint
            != _plan_fingerprint(_restore_plan_payload(plan))
        ):
            raise ValueError(
                "Logistics restore plan is foreign or was mutated",
            )
        stockpile_before = self._stockpile.get_state()
        network_before = self._network.get_state()
        try:
            self._stockpile.set_state(plan.stockpile_state)
            self._network.set_state(plan.supply_network_state)
        except Exception:
            self._stockpile.set_state(stockpile_before)
            self._network.set_state(network_before)
            raise
        self._elapsed_accumulator_seconds = (
            plan.elapsed_accumulator_seconds
        )
        self._last_boundary_elapsed_seconds = (
            plan.last_boundary_elapsed_seconds
        )
        self._unit_eligible_from_seconds = dict(
            plan.unit_eligible_from_seconds,
        )
        self._unit_last_accounted_seconds = dict(
            plan.unit_last_accounted_seconds,
        )
        self._unit_interval_disqualified = dict(
            plan.unit_interval_disqualified,
        )
        self._last_boundary_positions = dict(
            plan.last_boundary_positions,
        )

    def set_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_units: Mapping[str, Unit] | Sequence[Unit] | None = None,
        expected_elapsed_seconds: float | None = None,
    ) -> None:
        """Validate and atomically restore runtime state."""
        self.commit_state(
            self.stage_state(
                state,
                expected_units=expected_units,
                expected_elapsed_seconds=expected_elapsed_seconds,
            ),
        )


__all__ = [
    "LogisticsRuntime",
    "logistics_ground_state_code",
]

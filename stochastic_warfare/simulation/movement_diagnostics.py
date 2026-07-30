"""Typed, deterministic movement-decision diagnostics.

The diagnostics in this module are observational.  They do not select movement
targets, consume randomness, or commit entity positions.  Movement managers
submit their already-made production decisions in batches so this component can
assign a canonical order and update bounded cumulative state atomically.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from stochastic_warfare.core.types import Position

MOVEMENT_EPSILON_M = 1e-9
MOVEMENT_OBSERVATION_LIMIT = 64


class MovementStage(str, Enum):
    """Production movement boundary that considered a unit."""

    STRATEGIC = "STRATEGIC"
    OPERATIONAL = "OPERATIONAL"
    TACTICAL = "TACTICAL"


_STAGE_ORDER: dict[MovementStage, int] = {
    MovementStage.STRATEGIC: 0,
    MovementStage.OPERATIONAL: 1,
    MovementStage.TACTICAL: 2,
}


class MovementReason(str, Enum):
    """Exact disposition selected by a production movement manager."""

    MOVED = "MOVED"
    INACTIVE = "INACTIVE"
    DEFENSIVE_HOLD = "DEFENSIVE_HOLD"
    AUTHORED_HOLD = "AUTHORED_HOLD"
    EMPLACED_HOLD = "EMPLACED_HOLD"
    RESERVE_OR_UNRELEASED = "RESERVE_OR_UNRELEASED"
    ENGINE_WEAPON_STANDOFF = "ENGINE_WEAPON_STANDOFF"
    RESOURCE_BLOCKED = "RESOURCE_BLOCKED"
    NO_TARGET = "NO_TARGET"
    ZERO_PROGRESS = "ZERO_PROGRESS"


_REASONS: tuple[MovementReason, ...] = tuple(MovementReason)
_REASON_INDEX: dict[MovementReason, int] = {
    reason: index for index, reason in enumerate(_REASONS)
}


@dataclass(frozen=True, slots=True)
class MovementOrder:
    """Deterministic identity and within-tick order of one observation."""

    engine_tick: int
    stage: MovementStage
    battle_id: str
    side: str
    unit_id: str
    ordinal: int

    def sort_key(self) -> tuple[int, int, str, str, str, int]:
        """Return the canonical total-order key."""
        return (
            self.engine_tick,
            _STAGE_ORDER[self.stage],
            self.battle_id,
            self.side,
            self.unit_id,
            self.ordinal,
        )

    def prefix_key(self) -> tuple[int, int, str, str, str]:
        """Return the canonical key before ordinal assignment."""
        return self.sort_key()[:-1]


@dataclass(frozen=True, slots=True)
class MovementDecision:
    """One manager-owned decision awaiting canonical ordinal assignment."""

    unit_id: str
    side: str
    reason: MovementReason
    attempted_m: float
    pre_position: Position
    post_position: Position


@dataclass(frozen=True, slots=True)
class MovementObservation:
    """Immutable record of one production movement consideration."""

    engine_tick: int
    stage: MovementStage
    battle_id: str
    side: str
    unit_id: str
    ordinal: int
    reason: MovementReason
    attempted_m: float
    achieved_m: float
    pre_position: Position
    post_position: Position

    @property
    def order(self) -> MovementOrder:
        """Return the observation's typed ordering identity."""
        return MovementOrder(
            engine_tick=self.engine_tick,
            stage=self.stage,
            battle_id=self.battle_id,
            side=self.side,
            unit_id=self.unit_id,
            ordinal=self.ordinal,
        )


@dataclass(frozen=True, slots=True)
class MovementUnitDiagnostics:
    """Immutable cumulative diagnostic summary for one registered unit."""

    unit_id: str
    side: str
    _reason_counts: tuple[int, ...]
    decision_count: int
    total_attempted_m: float
    total_achieved_m: float
    expected_progress_count: int
    zero_progress_count: int
    positive_progress_count: int
    final_reason: MovementReason | None
    final_order: MovementOrder | None
    recent_observations: tuple[MovementObservation, ...]
    dropped_observation_count: int

    @property
    def reason_counts(self) -> Mapping[MovementReason, int]:
        """Return an immutable typed reason-count view."""
        return MappingProxyType({
            reason: self._reason_counts[index]
            for index, reason in enumerate(_REASONS)
        })

    def reason_count(self, reason: MovementReason) -> int:
        """Return the cumulative count for one exact reason."""
        return self._reason_counts[_REASON_INDEX[reason]]

    def reason_counts_by_name(self) -> dict[str, int]:
        """Return JSON-facing exact reason counters."""
        return {
            reason.value: self._reason_counts[index]
            for index, reason in enumerate(_REASONS)
        }


@dataclass(frozen=True, slots=True)
class MovementDiagnosticsRestorePlan:
    """Validated, non-mutating movement-diagnostics restore plan."""

    units: tuple[MovementUnitDiagnostics, ...]
    total_observation_count: int
    last_order: MovementOrder | None
    next_ordinal: int


@dataclass(slots=True)
class _MovementUnitAccumulator:
    """Mutable runtime storage behind immutable public diagnostic snapshots."""

    unit_id: str
    side: str
    reason_counts: list[int]
    decision_count: int
    total_attempted_m: float
    total_achieved_m: float
    expected_progress_count: int
    zero_progress_count: int
    positive_progress_count: int
    final_reason: MovementReason | None
    final_order: MovementOrder | None
    recent_observations: deque[MovementObservation]
    dropped_observation_count: int

    @classmethod
    def from_snapshot(
        cls,
        summary: MovementUnitDiagnostics,
    ) -> _MovementUnitAccumulator:
        return cls(
            unit_id=summary.unit_id,
            side=summary.side,
            reason_counts=list(summary._reason_counts),
            decision_count=summary.decision_count,
            total_attempted_m=summary.total_attempted_m,
            total_achieved_m=summary.total_achieved_m,
            expected_progress_count=summary.expected_progress_count,
            zero_progress_count=summary.zero_progress_count,
            positive_progress_count=summary.positive_progress_count,
            final_reason=summary.final_reason,
            final_order=summary.final_order,
            recent_observations=deque(
                summary.recent_observations,
                maxlen=MOVEMENT_OBSERVATION_LIMIT,
            ),
            dropped_observation_count=summary.dropped_observation_count,
        )

    def snapshot(self) -> MovementUnitDiagnostics:
        return MovementUnitDiagnostics(
            unit_id=self.unit_id,
            side=self.side,
            _reason_counts=tuple(self.reason_counts),
            decision_count=self.decision_count,
            total_attempted_m=self.total_attempted_m,
            total_achieved_m=self.total_achieved_m,
            expected_progress_count=self.expected_progress_count,
            zero_progress_count=self.zero_progress_count,
            positive_progress_count=self.positive_progress_count,
            final_reason=self.final_reason,
            final_order=self.final_order,
            recent_observations=tuple(self.recent_observations),
            dropped_observation_count=self.dropped_observation_count,
        )


def _empty_unit_accumulator(
    unit_id: str,
    side: str,
) -> _MovementUnitAccumulator:
    return _MovementUnitAccumulator(
        unit_id=unit_id,
        side=side,
        reason_counts=[0] * len(_REASONS),
        decision_count=0,
        total_attempted_m=0.0,
        total_achieved_m=0.0,
        expected_progress_count=0,
        zero_progress_count=0,
        positive_progress_count=0,
        final_reason=None,
        final_order=None,
        recent_observations=deque(maxlen=MOVEMENT_OBSERVATION_LIMIT),
        dropped_observation_count=0,
    )


def _validate_unit_id(value: object, *, label: str) -> str:
    if isinstance(value, Enum):
        value = value.value
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
    ):
        raise ValueError(
            f"{label} must be a non-empty string without surrounding whitespace",
        )
    return value


def _validate_non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _validate_non_negative_number(value: object, *, label: str) -> float:
    if type(value) is float and math.isfinite(value) and value >= 0.0:
        return value
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{label} must be a finite non-negative number")
    return float(value)


def _validate_position(value: object, *, label: str) -> Position:
    if type(value) is Position and all(
        type(coordinate) is float and math.isfinite(coordinate)
        for coordinate in value
    ):
        return value
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{label} must contain exactly three ENU coordinates")
    coordinates: list[float] = []
    for index, coordinate in enumerate(value):
        if (
            isinstance(coordinate, bool)
            or not isinstance(coordinate, (int, float))
            or not math.isfinite(float(coordinate))
        ):
            raise ValueError(
                f"{label}[{index}] must be a finite numeric coordinate",
            )
        coordinates.append(float(coordinate))
    return Position(*coordinates)


def _position_distance(pre: Position, post: Position) -> float:
    return math.sqrt(
        (post.easting - pre.easting) ** 2
        + (post.northing - pre.northing) ** 2
        + (post.altitude - pre.altitude) ** 2
    )


def _validate_reason_distances(
    *,
    reason: MovementReason,
    attempted_m: float,
    achieved_m: float,
    label: str,
) -> None:
    attempted = attempted_m > MOVEMENT_EPSILON_M
    achieved = achieved_m > MOVEMENT_EPSILON_M
    if reason is MovementReason.MOVED:
        if not attempted or not achieved:
            raise ValueError(
                f"{label} MOVED requires positive attempted and achieved distance",
            )
    elif reason is MovementReason.ZERO_PROGRESS:
        if not attempted or achieved:
            raise ValueError(
                f"{label} ZERO_PROGRESS requires a positive attempt and zero progress",
            )
    elif attempted or achieved:
        raise ValueError(
            f"{label} {reason.value} must be a no-attempt, zero-progress decision",
        )
    if achieved_m > attempted_m and not math.isclose(
        achieved_m,
        attempted_m,
        rel_tol=1e-12,
        abs_tol=MOVEMENT_EPSILON_M,
    ):
        raise ValueError(f"{label} achieved distance exceeds attempted distance")


def _order_to_state(order: MovementOrder | None) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "engine_tick": order.engine_tick,
        "stage": order.stage.value,
        "battle_id": order.battle_id,
        "side": order.side,
        "unit_id": order.unit_id,
        "ordinal": order.ordinal,
    }


_ORDER_KEYS = {
    "engine_tick",
    "stage",
    "battle_id",
    "side",
    "unit_id",
    "ordinal",
}


def _order_from_state(value: object, *, label: str) -> MovementOrder:
    if not isinstance(value, dict) or set(value) != _ORDER_KEYS:
        raise ValueError(f"{label} has invalid movement-order key topology")
    try:
        stage = MovementStage(value["stage"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}.stage is not a supported movement stage") from exc
    battle_id = value["battle_id"]
    side = value["side"]
    if not isinstance(battle_id, str):
        raise ValueError(f"{label}.battle_id must be a string")
    side = _validate_unit_id(side, label=f"{label}.side")
    unit_id = _validate_unit_id(value["unit_id"], label=f"{label}.unit_id")
    return MovementOrder(
        engine_tick=_validate_non_negative_int(
            value["engine_tick"],
            label=f"{label}.engine_tick",
        ),
        stage=stage,
        battle_id=battle_id,
        side=side,
        unit_id=unit_id,
        ordinal=_validate_non_negative_int(
            value["ordinal"],
            label=f"{label}.ordinal",
        ),
    )


_OBSERVATION_KEYS = _ORDER_KEYS | {
    "reason",
    "attempted_m",
    "achieved_m",
    "pre_position",
    "post_position",
}


def _observation_to_state(observation: MovementObservation) -> dict[str, Any]:
    return {
        **(_order_to_state(observation.order) or {}),
        "reason": observation.reason.value,
        "attempted_m": observation.attempted_m,
        "achieved_m": observation.achieved_m,
        "pre_position": list(observation.pre_position),
        "post_position": list(observation.post_position),
    }


def _observation_from_state(
    value: object,
    *,
    label: str,
) -> MovementObservation:
    if not isinstance(value, dict) or set(value) != _OBSERVATION_KEYS:
        raise ValueError(f"{label} has invalid movement-observation key topology")
    order = _order_from_state(
        {key: value[key] for key in _ORDER_KEYS},
        label=f"{label}.order",
    )
    try:
        reason = MovementReason(value["reason"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}.reason is not supported") from exc
    attempted_m = _validate_non_negative_number(
        value["attempted_m"],
        label=f"{label}.attempted_m",
    )
    achieved_m = _validate_non_negative_number(
        value["achieved_m"],
        label=f"{label}.achieved_m",
    )
    pre_position = _validate_position(
        value["pre_position"],
        label=f"{label}.pre_position",
    )
    post_position = _validate_position(
        value["post_position"],
        label=f"{label}.post_position",
    )
    computed_achieved = _position_distance(pre_position, post_position)
    if not math.isclose(
        achieved_m,
        computed_achieved,
        rel_tol=1e-12,
        abs_tol=MOVEMENT_EPSILON_M,
    ):
        raise ValueError(f"{label}.achieved_m disagrees with its ENU positions")
    _validate_reason_distances(
        reason=reason,
        attempted_m=attempted_m,
        achieved_m=achieved_m,
        label=label,
    )
    return MovementObservation(
        engine_tick=order.engine_tick,
        stage=order.stage,
        battle_id=order.battle_id,
        side=order.side,
        unit_id=order.unit_id,
        ordinal=order.ordinal,
        reason=reason,
        attempted_m=attempted_m,
        achieved_m=achieved_m,
        pre_position=pre_position,
        post_position=post_position,
    )


class MovementDiagnostics:
    """Simulation-owned cumulative movement diagnostics."""

    _STATE_KEYS = {
        "units",
        "total_observation_count",
        "last_order",
        "next_ordinal",
    }
    _UNIT_STATE_KEYS = {
        "side",
        "reason_counts",
        "decision_count",
        "total_attempted_m",
        "total_achieved_m",
        "expected_progress_count",
        "zero_progress_count",
        "positive_progress_count",
        "final_reason",
        "final_order",
        "recent_observations",
        "dropped_observation_count",
    }

    def __init__(
        self,
        unit_sides: Mapping[str, str] | None = None,
    ) -> None:
        self._units: dict[str, _MovementUnitAccumulator] = {}
        self._total_observation_count = 0
        self._last_order: MovementOrder | None = None
        self._next_ordinal = 0
        self.register_units(unit_sides or {})

    @property
    def total_observation_count(self) -> int:
        """Return the number of decisions recorded across all units."""
        return self._total_observation_count

    def register_units(self, unit_sides: Mapping[str, str]) -> None:
        """Transactionally register zeroed initial or dynamic unit topology.

        Registering an already known ID is an idempotent no-op.  All input is
        validated before any new unit is published.
        """
        if not isinstance(unit_sides, Mapping):
            raise ValueError(
                "movement diagnostic unit_sides must be a mapping",
            )
        staged_topology: dict[str, str] = {}
        for raw_unit_id, raw_side in unit_sides.items():
            unit_id = _validate_unit_id(
                raw_unit_id,
                label="movement diagnostic unit_id",
            )
            side = _validate_unit_id(
                raw_side,
                label=f"movement diagnostic side for {unit_id!r}",
            )
            staged_topology[unit_id] = side
        for unit_id, side in staged_topology.items():
            existing = self._units.get(unit_id)
            if existing is not None and existing.side != side:
                raise ValueError(
                    f"movement diagnostic unit {unit_id!r} is already "
                    f"registered to side {existing.side!r}",
                )
        additions = {
            unit_id: _empty_unit_accumulator(
                unit_id,
                staged_topology[unit_id],
            )
            for unit_id in sorted(staged_topology)
            if unit_id not in self._units
        }
        self._units.update(additions)

    def get_unit(self, unit_id: str) -> MovementUnitDiagnostics:
        """Return one immutable typed cumulative summary."""
        try:
            return self._units[unit_id].snapshot()
        except KeyError as exc:
            raise KeyError(
                f"Unknown movement diagnostic unit_id {unit_id!r}",
            ) from exc

    def summaries(self) -> tuple[MovementUnitDiagnostics, ...]:
        """Return all summaries in stable unit-ID order."""
        return tuple(
            self._units[unit_id].snapshot()
            for unit_id in sorted(self._units)
        )

    def record_batch(
        self,
        *,
        engine_tick: int,
        stage: MovementStage,
        battle_id: str,
        decisions: Iterable[MovementDecision],
    ) -> tuple[MovementObservation, ...]:
        """Atomically record one manager consideration batch."""
        tick = _validate_non_negative_int(engine_tick, label="engine_tick")
        if not isinstance(stage, MovementStage):
            raise ValueError("stage must be a MovementStage")
        if not isinstance(battle_id, str):
            raise ValueError("battle_id must be a string")
        if isinstance(decisions, (str, bytes)):
            raise ValueError("decisions must be an iterable")

        staged_decisions = tuple(decisions)
        seen_unit_ids: set[str] = set()
        normalized: list[tuple[MovementDecision, float]] = []
        for index, decision in enumerate(staged_decisions):
            label = f"decisions[{index}]"
            if not isinstance(decision, MovementDecision):
                raise ValueError(f"{label} must be a MovementDecision")
            unit_id = _validate_unit_id(decision.unit_id, label=f"{label}.unit_id")
            side = _validate_unit_id(decision.side, label=f"{label}.side")
            if unit_id not in self._units:
                raise ValueError(
                    f"{label} references unregistered unit_id {unit_id!r}",
                )
            if side != self._units[unit_id].side:
                raise ValueError(
                    f"{label}.side disagrees with registered unit topology",
                )
            if unit_id in seen_unit_ids:
                raise ValueError(
                    f"movement batch considers unit_id {unit_id!r} more than once",
                )
            seen_unit_ids.add(unit_id)
            if not isinstance(decision.reason, MovementReason):
                raise ValueError(f"{label}.reason must be a MovementReason")
            attempted_m = _validate_non_negative_number(
                decision.attempted_m,
                label=f"{label}.attempted_m",
            )
            pre_position = _validate_position(
                decision.pre_position,
                label=f"{label}.pre_position",
            )
            post_position = _validate_position(
                decision.post_position,
                label=f"{label}.post_position",
            )
            achieved_m = _position_distance(pre_position, post_position)
            _validate_reason_distances(
                reason=decision.reason,
                attempted_m=attempted_m,
                achieved_m=achieved_m,
                label=label,
            )
            normalized_decision = (
                decision
                if (
                    unit_id is decision.unit_id
                    and side is decision.side
                    and attempted_m is decision.attempted_m
                    and pre_position is decision.pre_position
                    and post_position is decision.post_position
                )
                else MovementDecision(
                    unit_id=unit_id,
                    side=side,
                    reason=decision.reason,
                    attempted_m=attempted_m,
                    pre_position=pre_position,
                    post_position=post_position,
                )
            )
            normalized.append((normalized_decision, achieved_m))

        if not normalized:
            return ()
        normalized.sort(key=lambda item: (item[0].side, item[0].unit_id))

        first_ordinal = (
            self._next_ordinal
            if self._last_order is not None
            and self._last_order.engine_tick == tick
            else 0
        )
        observations: list[tuple[MovementObservation, MovementOrder]] = []
        previous_order = self._last_order
        for offset, (decision, achieved_m) in enumerate(normalized):
            order = MovementOrder(
                engine_tick=tick,
                stage=stage,
                battle_id=battle_id,
                side=decision.side,
                unit_id=decision.unit_id,
                ordinal=first_ordinal + offset,
            )
            observation = MovementObservation(
                engine_tick=order.engine_tick,
                stage=order.stage,
                battle_id=order.battle_id,
                side=order.side,
                unit_id=order.unit_id,
                ordinal=order.ordinal,
                reason=decision.reason,
                attempted_m=decision.attempted_m,
                achieved_m=achieved_m,
                pre_position=decision.pre_position,
                post_position=decision.post_position,
            )
            if (
                previous_order is not None
                and order.prefix_key()
                < previous_order.prefix_key()
            ):
                raise ValueError(
                    "movement observation batch is earlier than the canonical "
                    "last order",
                )
            observations.append((observation, order))
            previous_order = order

        # Complete every potentially-raising numerical reduction before the
        # non-throwing accumulator commit so invalid input cannot partially
        # publish a batch.
        staged_totals: list[
            tuple[
                _MovementUnitAccumulator,
                MovementObservation,
                MovementOrder,
                float,
                float,
            ]
        ] = []
        for observation, order in observations:
            current = self._units[observation.unit_id]
            staged_totals.append((
                current,
                observation,
                order,
                math.fsum((
                    current.total_attempted_m,
                    observation.attempted_m,
                )),
                math.fsum((
                    current.total_achieved_m,
                    observation.achieved_m,
                )),
            ))

        for (
            current,
            observation,
            order,
            total_attempted_m,
            total_achieved_m,
        ) in staged_totals:
            expected = observation.attempted_m > MOVEMENT_EPSILON_M
            positive = observation.achieved_m > MOVEMENT_EPSILON_M
            current.reason_counts[_REASON_INDEX[observation.reason]] += 1
            current.decision_count += 1
            current.total_attempted_m = total_attempted_m
            current.total_achieved_m = total_achieved_m
            current.expected_progress_count += int(expected)
            current.zero_progress_count += int(expected and not positive)
            current.positive_progress_count += int(positive)
            current.final_reason = observation.reason
            current.final_order = order
            current.recent_observations.append(observation)
            current.dropped_observation_count = (
                current.decision_count - len(current.recent_observations)
            )

        self._total_observation_count += len(observations)
        self._last_order = observations[-1][1]
        self._next_ordinal = observations[-1][1].ordinal + 1
        return tuple(observation for observation, _order in observations)

    def get_state(self) -> dict[str, Any]:
        """Return exact schema-112 cumulative state."""
        return {
            "units": {
                summary.unit_id: {
                    "side": summary.side,
                    "reason_counts": summary.reason_counts_by_name(),
                    "decision_count": summary.decision_count,
                    "total_attempted_m": summary.total_attempted_m,
                    "total_achieved_m": summary.total_achieved_m,
                    "expected_progress_count": summary.expected_progress_count,
                    "zero_progress_count": summary.zero_progress_count,
                    "positive_progress_count": summary.positive_progress_count,
                    "final_reason": (
                        summary.final_reason.value
                        if summary.final_reason is not None
                        else None
                    ),
                    "final_order": _order_to_state(summary.final_order),
                    "recent_observations": [
                        _observation_to_state(observation)
                        for observation in summary.recent_observations
                    ],
                    "dropped_observation_count": (
                        summary.dropped_observation_count
                    ),
                }
                for summary in self.summaries()
            },
            "total_observation_count": self._total_observation_count,
            "last_order": _order_to_state(self._last_order),
            "next_ordinal": self._next_ordinal,
        }

    def stage_state(
        self,
        state: object,
        *,
        expected_unit_sides: Mapping[str, str],
    ) -> MovementDiagnosticsRestorePlan:
        """Validate checkpoint state without mutating live diagnostics."""
        if not isinstance(state, dict) or set(state) != self._STATE_KEYS:
            raise ValueError(
                "movement diagnostics state has invalid key topology",
            )
        if not isinstance(expected_unit_sides, Mapping):
            raise ValueError(
                "expected movement unit topology must be a mapping",
            )
        expected_topology = {
            _validate_unit_id(
                unit_id,
                label="expected movement unit_id",
            ): _validate_unit_id(
                side,
                label=f"expected movement side for {unit_id!r}",
            )
            for unit_id, side in expected_unit_sides.items()
        }
        expected_ids = set(expected_topology)
        raw_units = state["units"]
        if not isinstance(raw_units, dict):
            raise ValueError("movement diagnostics units must be a mapping")
        if not all(isinstance(unit_id, str) for unit_id in raw_units):
            raise ValueError("movement diagnostics unit keys must be strings")
        if set(raw_units) != expected_ids:
            raise ValueError(
                "movement diagnostics unit topology does not match the "
                "checkpoint force roster",
            )

        summaries = tuple(
            self._stage_unit_state(
                unit_id,
                expected_topology[unit_id],
                raw_units[unit_id],
            )
            for unit_id in sorted(expected_ids)
        )
        total_observation_count = _validate_non_negative_int(
            state["total_observation_count"],
            label="movement diagnostics total_observation_count",
        )
        if total_observation_count != sum(
            summary.decision_count for summary in summaries
        ):
            raise ValueError(
                "movement diagnostics total_observation_count disagrees with "
                "unit decision counts",
            )
        next_ordinal = _validate_non_negative_int(
            state["next_ordinal"],
            label="movement diagnostics next_ordinal",
        )
        raw_last_order = state["last_order"]
        last_order = (
            None
            if raw_last_order is None
            else _order_from_state(
                raw_last_order,
                label="movement diagnostics last_order",
            )
        )
        final_orders = tuple(
            summary.final_order
            for summary in summaries
            if summary.final_order is not None
        )
        if not final_orders:
            if (
                total_observation_count != 0
                or last_order is not None
                or next_ordinal != 0
            ):
                raise ValueError(
                    "empty movement diagnostics have non-empty global counters",
                )
        else:
            expected_last = max(final_orders, key=MovementOrder.sort_key)
            if last_order != expected_last:
                raise ValueError(
                    "movement diagnostics last_order disagrees with unit state",
                )
            if next_ordinal != expected_last.ordinal + 1:
                raise ValueError(
                    "movement diagnostics next_ordinal disagrees with last_order",
                )

        self._validate_cross_unit_order(summaries)
        return MovementDiagnosticsRestorePlan(
            units=summaries,
            total_observation_count=total_observation_count,
            last_order=last_order,
            next_ordinal=next_ordinal,
        )

    def _stage_unit_state(
        self,
        unit_id: str,
        expected_side: str,
        value: object,
    ) -> MovementUnitDiagnostics:
        label = f"movement diagnostics unit {unit_id!r}"
        if not isinstance(value, dict) or set(value) != self._UNIT_STATE_KEYS:
            raise ValueError(f"{label} has invalid key topology")
        side = _validate_unit_id(value["side"], label=f"{label}.side")
        if side != expected_side:
            raise ValueError(f"{label} side disagrees with runtime topology")
        raw_counts = value["reason_counts"]
        expected_reason_keys = {reason.value for reason in _REASONS}
        if (
            not isinstance(raw_counts, dict)
            or set(raw_counts) != expected_reason_keys
        ):
            raise ValueError(f"{label} has invalid reason-count topology")
        counts = tuple(
            _validate_non_negative_int(
                raw_counts[reason.value],
                label=f"{label}.reason_counts.{reason.value}",
            )
            for reason in _REASONS
        )
        decision_count = _validate_non_negative_int(
            value["decision_count"],
            label=f"{label}.decision_count",
        )
        if decision_count != sum(counts):
            raise ValueError(f"{label} decision count disagrees with reason sums")

        total_attempted_m = _validate_non_negative_number(
            value["total_attempted_m"],
            label=f"{label}.total_attempted_m",
        )
        total_achieved_m = _validate_non_negative_number(
            value["total_achieved_m"],
            label=f"{label}.total_achieved_m",
        )
        expected_progress_count = _validate_non_negative_int(
            value["expected_progress_count"],
            label=f"{label}.expected_progress_count",
        )
        zero_progress_count = _validate_non_negative_int(
            value["zero_progress_count"],
            label=f"{label}.zero_progress_count",
        )
        positive_progress_count = _validate_non_negative_int(
            value["positive_progress_count"],
            label=f"{label}.positive_progress_count",
        )
        moved_count = counts[_REASON_INDEX[MovementReason.MOVED]]
        zero_reason_count = counts[_REASON_INDEX[MovementReason.ZERO_PROGRESS]]
        if (
            positive_progress_count != moved_count
            or zero_progress_count != zero_reason_count
            or expected_progress_count
            != positive_progress_count + zero_progress_count
        ):
            raise ValueError(f"{label} progress counters are inconsistent")

        raw_recent = value["recent_observations"]
        if not isinstance(raw_recent, list):
            raise ValueError(f"{label}.recent_observations must be a list")
        if len(raw_recent) > MOVEMENT_OBSERVATION_LIMIT:
            raise ValueError(f"{label} exceeds the 64-observation ring bound")
        recent = tuple(
            _observation_from_state(
                raw_observation,
                label=f"{label}.recent_observations[{index}]",
            )
            for index, raw_observation in enumerate(raw_recent)
        )
        if any(observation.unit_id != unit_id for observation in recent):
            raise ValueError(f"{label} ring contains another unit identity")
        if any(
            later.order.sort_key() <= earlier.order.sort_key()
            for earlier, later in zip(recent, recent[1:])
        ):
            raise ValueError(f"{label} ring is not strictly ordered")
        if any(observation.side != side for observation in recent):
            raise ValueError(f"{label} ring changes immutable side identity")

        dropped = _validate_non_negative_int(
            value["dropped_observation_count"],
            label=f"{label}.dropped_observation_count",
        )
        if (
            len(recent) != min(decision_count, MOVEMENT_OBSERVATION_LIMIT)
            or dropped != decision_count - len(recent)
        ):
            raise ValueError(f"{label} ring and dropped counters disagree")
        ring_counts = {reason: 0 for reason in _REASONS}
        for observation in recent:
            ring_counts[observation.reason] += 1
        if any(
            ring_counts[reason] > counts[_REASON_INDEX[reason]]
            for reason in _REASONS
        ):
            raise ValueError(f"{label} ring reason counts exceed cumulative counts")
        ring_attempted = math.fsum(
            observation.attempted_m for observation in recent
        )
        ring_achieved = math.fsum(
            observation.achieved_m for observation in recent
        )
        if (
            total_attempted_m + MOVEMENT_EPSILON_M < ring_attempted
            or total_achieved_m + MOVEMENT_EPSILON_M < ring_achieved
        ):
            raise ValueError(f"{label} ring distances exceed cumulative totals")
        if total_achieved_m > total_attempted_m and not math.isclose(
            total_achieved_m,
            total_attempted_m,
            rel_tol=1e-12,
            abs_tol=MOVEMENT_EPSILON_M,
        ):
            raise ValueError(f"{label} achieved total exceeds attempted total")

        raw_final_reason = value["final_reason"]
        if raw_final_reason is None:
            final_reason = None
        else:
            try:
                final_reason = MovementReason(raw_final_reason)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label}.final_reason is not supported") from exc
        raw_final_order = value["final_order"]
        final_order = (
            None
            if raw_final_order is None
            else _order_from_state(
                raw_final_order,
                label=f"{label}.final_order",
            )
        )
        if decision_count == 0:
            if (
                recent
                or dropped != 0
                or final_reason is not None
                or final_order is not None
                or total_attempted_m != 0.0
                or total_achieved_m != 0.0
                or expected_progress_count != 0
                or zero_progress_count != 0
                or positive_progress_count != 0
            ):
                raise ValueError(f"{label} zero state has non-zero fields")
        elif (
            not recent
            or final_reason is not recent[-1].reason
            or final_order != recent[-1].order
        ):
            raise ValueError(f"{label} final disposition disagrees with its ring")

        return MovementUnitDiagnostics(
            unit_id=unit_id,
            side=side,
            _reason_counts=counts,
            decision_count=decision_count,
            total_attempted_m=total_attempted_m,
            total_achieved_m=total_achieved_m,
            expected_progress_count=expected_progress_count,
            zero_progress_count=zero_progress_count,
            positive_progress_count=positive_progress_count,
            final_reason=final_reason,
            final_order=final_order,
            recent_observations=recent,
            dropped_observation_count=dropped,
        )

    @staticmethod
    def _tick_history_is_complete(
        summaries: tuple[MovementUnitDiagnostics, ...],
        tick: int,
    ) -> bool:
        """Return whether every observation for *tick* remains in the rings.

        A summary with no drops retains its complete history.  When drops have
        occurred, a retained observation from an earlier tick proves that the
        dropped prefix cannot contain an observation from the later tick.
        An oldest retained observation on the tick itself is intentionally
        inconclusive because an earlier ordinal from that tick may have been
        dropped by the independently bounded per-unit ring.
        """
        return all(
            summary.dropped_observation_count == 0
            or (
                bool(summary.recent_observations)
                and summary.recent_observations[0].engine_tick < tick
            )
            for summary in summaries
        )

    @staticmethod
    def _validate_cross_unit_order(
        summaries: tuple[MovementUnitDiagnostics, ...],
    ) -> None:
        observations = [
            observation
            for summary in summaries
            for observation in summary.recent_observations
        ]
        by_tick: dict[int, list[MovementObservation]] = {}
        for observation in observations:
            by_tick.setdefault(observation.engine_tick, []).append(observation)
        for tick in sorted(by_tick):
            tick_observations = by_tick[tick]
            ordered = sorted(tick_observations, key=lambda obs: obs.ordinal)
            ordinals = [observation.ordinal for observation in ordered]
            if len(ordinals) != len(set(ordinals)):
                raise ValueError(
                    f"movement diagnostics tick {tick} has duplicate ordinals",
                )
            if (
                MovementDiagnostics._tick_history_is_complete(
                    summaries,
                    tick,
                )
                and ordinals != list(range(len(ordered)))
            ):
                raise ValueError(
                    f"movement diagnostics tick {tick} complete history must "
                    "use contiguous zero-based ordinals",
                )
            prefixes = [
                observation.order.prefix_key()
                for observation in ordered
            ]
            if any(
                later < earlier
                for earlier, later in zip(prefixes, prefixes[1:])
            ):
                raise ValueError(
                    f"movement diagnostics tick {tick} violates canonical order",
                )

    def commit_state(self, plan: MovementDiagnosticsRestorePlan) -> None:
        """Commit a previously staged movement-diagnostics plan."""
        if not isinstance(plan, MovementDiagnosticsRestorePlan):
            raise TypeError("plan must be a MovementDiagnosticsRestorePlan")
        self._units = {
            summary.unit_id: _MovementUnitAccumulator.from_snapshot(summary)
            for summary in plan.units
        }
        self._total_observation_count = plan.total_observation_count
        self._last_order = plan.last_order
        self._next_ordinal = plan.next_ordinal

    def set_state(
        self,
        state: object,
        *,
        expected_unit_sides: Mapping[str, str],
    ) -> None:
        """Validate and atomically restore movement-diagnostics state."""
        self.commit_state(
            self.stage_state(
                state,
                expected_unit_sides=expected_unit_sides,
            ),
        )


def resolve_movement_diagnostics_owner(
    context: Any,
    injected: MovementDiagnostics | None,
    *,
    boundary: str,
) -> tuple[MovementDiagnostics | None, int | None]:
    """Resolve one injected/context owner and its logical engine tick."""
    context_owner = getattr(context, "movement_diagnostics", None)
    owner = injected
    if owner is None and isinstance(context_owner, MovementDiagnostics):
        owner = context_owner
    elif (
        owner is not None
        and isinstance(context_owner, MovementDiagnostics)
        and owner is not context_owner
    ):
        raise RuntimeError(
            f"{boundary} and SimulationContext movement diagnostics must "
            "share one owner",
        )
    if owner is None:
        return None, None
    clock = getattr(context, "clock", None)
    if clock is None:
        raise RuntimeError(
            f"{boundary} movement diagnostics require the logical clock",
        )
    return (
        owner,
        _validate_non_negative_int(
            getattr(clock, "tick_count", None),
            label=f"{boundary} movement diagnostic engine tick",
        ),
    )

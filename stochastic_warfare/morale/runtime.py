"""Authoritative runtime ownership for unit morale semantics."""

from __future__ import annotations

import copy
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.entities.base import Unit, UnitStatus
from stochastic_warfare.morale.events import (
    MoraleStateChangeEvent,
    RallyEvent,
)
from stochastic_warfare.morale.rout import (
    RoutCascadeCandidate,
    RoutEngine,
)
from stochastic_warfare.morale.state import (
    MoraleConfig,
    MoraleState,
    MoraleStateMachine,
    MoraleTransitionCause,
)


@dataclass(frozen=True, slots=True)
class MoraleStateRecord:
    """Immutable complete semantic morale record for one active unit."""

    current_state: MoraleState
    last_transition_time_s: float | None = None
    last_check_time_s: float | None = None
    generation: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.current_state, MoraleState):
            raise TypeError("current_state must be a MoraleState")
        for field_name in (
            "last_transition_time_s",
            "last_check_time_s",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"{field_name} must be None or a finite non-negative number",
                )
            object.__setattr__(self, field_name, float(value))
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise ValueError("generation must be a non-negative strict integer")
        if self.generation == 0 and (
            self.last_transition_time_s is not None
            or self.last_check_time_s is not None
        ):
            raise ValueError("generation zero cannot have recorded morale times")
        if self.generation > 0 and self.last_check_time_s is None:
            raise ValueError("positive generation requires last_check_time_s")
        if (
            self.last_transition_time_s is not None
            and self.last_check_time_s is not None
            and self.last_transition_time_s > self.last_check_time_s
        ):
            raise ValueError(
                "last_transition_time_s cannot exceed last_check_time_s",
            )


@dataclass(frozen=True, slots=True)
class MoraleRegistration:
    """Immutable request to register one unit's initial morale state."""

    unit_id: str
    initial_state: MoraleState

    def __post_init__(self) -> None:
        if not isinstance(self.unit_id, str) or not self.unit_id:
            raise ValueError("Morale registration unit_id must be non-empty")
        if not isinstance(self.initial_state, MoraleState):
            raise TypeError("initial_state must be a MoraleState")


@dataclass(frozen=True, slots=True)
class MoraleAggregateArchive:
    """Complete suspended morale topology for one aggregate proxy."""

    aggregate_id: str
    constituent_records: tuple[tuple[str, MoraleStateRecord], ...]
    proxy_baseline: MoraleStateRecord


class MoraleStateStore:
    """Private mutable owner behind immutable runtime projections."""

    def __init__(self) -> None:
        self._active: dict[str, MoraleStateRecord] = {}
        self._suspended: dict[str, MoraleAggregateArchive] = {}


class _MoraleStateView(Mapping[str, MoraleState]):
    __slots__ = ("_store",)

    def __init__(self, store: MoraleStateStore) -> None:
        self._store = store

    def __getitem__(self, unit_id: str) -> MoraleState:
        return self._store._active[unit_id].current_state

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._store._active))

    def __len__(self) -> int:
        return len(self._store._active)


class _MoraleRecordView(Mapping[str, MoraleStateRecord]):
    __slots__ = ("_store",)

    def __init__(self, store: MoraleStateStore) -> None:
        self._store = store

    def __getitem__(self, unit_id: str) -> MoraleStateRecord:
        return self._store._active[unit_id]

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._store._active))

    def __len__(self) -> int:
        return len(self._store._active)


@dataclass(frozen=True, slots=True)
class MoraleAggregationPlan:
    """Owner-bound, reversible morale half of aggregation."""

    owner_token: object
    aggregate_id: str
    constituents: tuple[tuple[str, MoraleStateRecord, Unit], ...]
    proxy_unit: Unit
    proxy_record: MoraleStateRecord
    proxy_status_before: UnitStatus
    archive: MoraleAggregateArchive


@dataclass(frozen=True, slots=True)
class MoraleDisaggregationPlan:
    """Owner-bound, reversible morale half of disaggregation."""

    owner_token: object
    aggregate_id: str
    archive: MoraleAggregateArchive
    proxy_unit: Unit
    restored_units: tuple[tuple[str, Unit, UnitStatus], ...]


@dataclass(frozen=True, slots=True)
class MoraleRuntimeStatePlan:
    """Validated, owner-bound current-format morale restore plan."""

    owner_token: object
    active_records: tuple[tuple[str, MoraleStateRecord], ...]
    suspended_archives: tuple[tuple[str, MoraleAggregateArchive], ...]


def _required_status(state: MoraleState) -> UnitStatus:
    if state is MoraleState.ROUTED:
        return UnitStatus.ROUTING
    if state is MoraleState.SURRENDERED:
        return UnitStatus.SURRENDERED
    return UnitStatus.ACTIVE


def _status_is_compatible(unit: Unit, record: MoraleStateRecord) -> bool:
    return _status_value_is_compatible(unit.status, record)


def _status_value_is_compatible(
    status: UnitStatus,
    record: MoraleStateRecord,
) -> bool:
    if status in (UnitStatus.DISABLED, UnitStatus.DESTROYED):
        return True
    return status is _required_status(record.current_state)


def _validated_time(value: float, *, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{label} must be a finite non-negative number")
    return float(value)


def _record_state(record: MoraleStateRecord) -> dict[str, Any]:
    return {
        "current_state": int(record.current_state),
        "last_transition_time_s": record.last_transition_time_s,
        "last_check_time_s": record.last_check_time_s,
        "generation": record.generation,
    }


def _parse_record(raw: object, *, label: str) -> MoraleStateRecord:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a mapping")
    expected = {
        "current_state",
        "last_transition_time_s",
        "last_check_time_s",
        "generation",
    }
    if set(raw) != expected:
        raise ValueError(f"{label} has invalid key topology")
    raw_state = raw["current_state"]
    if isinstance(raw_state, bool) or not isinstance(raw_state, int):
        raise ValueError(f"{label}.current_state must be a strict integer")
    try:
        state = MoraleState(raw_state)
        return MoraleStateRecord(
            current_state=state,
            last_transition_time_s=raw["last_transition_time_s"],
            last_check_time_s=raw["last_check_time_s"],
            generation=raw["generation"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}: {exc}") from exc


class MoraleRuntime:
    """Single production coordinator for morale state and side effects."""

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: MoraleConfig | None = None,
        *,
        rout_engine: RoutEngine | None = None,
    ) -> None:
        if not isinstance(rng, np.random.Generator):
            raise TypeError("MoraleRuntime requires a numpy Generator")
        effective_config = config or MoraleConfig()
        self._event_bus = event_bus
        self._rng = rng
        self._config = effective_config
        self._machine = MoraleStateMachine(rng, effective_config)
        self._rout_engine = rout_engine or RoutEngine(event_bus, rng)
        if self._machine.rng is not rng or self._rout_engine.rng is not rng:
            raise ValueError(
                "Morale runtime, state machine, and rout engine must share RNG",
            )
        self._store = MoraleStateStore()
        self._units: dict[str, Unit] = {}
        self._states_view: Mapping[str, MoraleState] = _MoraleStateView(
            self._store,
        )
        self._records_view: Mapping[str, MoraleStateRecord] = (
            _MoraleRecordView(self._store)
        )
        self._owner_token = object()

    @property
    def rng(self) -> np.random.Generator:
        """Return the authoritative injected MORALE generator."""
        return self._rng

    @property
    def config(self) -> MoraleConfig:
        """Return the sole effective morale configuration."""
        return self._config

    @property
    def rout_engine(self) -> RoutEngine:
        """Return the coordinated rout owner."""
        return self._rout_engine

    @property
    def states(self) -> Mapping[str, MoraleState]:
        """Return the stable read-only current-state compatibility view."""
        return self._states_view

    @property
    def records(self) -> Mapping[str, MoraleStateRecord]:
        """Return the stable read-only immutable-record view."""
        return self._records_view

    def validate_bindings(self, expected_units: Mapping[str, Unit]) -> None:
        """Validate exact active-roster, object, status, RNG, and config ties."""
        if not isinstance(expected_units, Mapping):
            raise TypeError("expected_units must be a mapping")
        expected_ids = set(expected_units)
        if (
            set(self._store._active) != expected_ids
            or set(self._units) != expected_ids
        ):
            raise ValueError(
                "Morale runtime topology does not match the active roster",
            )
        if (
            self._machine.rng is not self._rng
            or self._rout_engine.rng is not self._rng
        ):
            raise ValueError(
                "Morale runtime owners no longer share one MORALE RNG",
            )
        if self._machine.config is not self._config:
            raise ValueError(
                "Morale runtime and state machine configuration disagree",
            )
        for unit_id in sorted(expected_ids):
            unit = expected_units[unit_id]
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or not isinstance(unit, Unit)
                or unit.entity_id != unit_id
                or self._units[unit_id] is not unit
            ):
                raise ValueError(
                    f"Morale runtime unit binding disagrees for {unit_id!r}",
                )
            if not _status_is_compatible(
                unit,
                self._store._active[unit_id],
            ):
                raise ValueError(
                    f"Morale/status disagree for unit {unit_id!r}",
                )

    def record_for(self, unit_id: str) -> MoraleStateRecord:
        """Return one immutable authoritative record."""
        return self._store._active[unit_id]

    def register_units(
        self,
        registrations: Sequence[MoraleRegistration],
        units: Mapping[str, Unit],
    ) -> None:
        """Atomically register one ordered batch without RNG or events."""
        registrations = tuple(registrations)
        staged: list[tuple[str, MoraleStateRecord, Unit]] = []
        seen: set[str] = set()
        suspended_ids = {
            unit_id
            for archive in self._store._suspended.values()
            for unit_id, _ in archive.constituent_records
        }
        for registration in registrations:
            if not isinstance(registration, MoraleRegistration):
                raise TypeError(
                    "registrations must contain MoraleRegistration values",
                )
            unit_id = registration.unit_id
            if unit_id in seen:
                raise ValueError(f"Duplicate morale registration {unit_id!r}")
            if unit_id in self._store._active or unit_id in self._units:
                raise ValueError(f"Morale unit {unit_id!r} is already active")
            if unit_id in suspended_ids:
                raise ValueError(f"Morale unit {unit_id!r} is suspended")
            unit = units.get(unit_id)
            if unit is None or unit.entity_id != unit_id:
                raise ValueError(f"Unknown morale registration unit {unit_id!r}")
            record = MoraleStateRecord(registration.initial_state)
            if not _status_is_compatible(unit, record):
                raise ValueError(
                    f"Initial morale/status disagree for unit {unit_id!r}",
                )
            seen.add(unit_id)
            staged.append((unit_id, record, unit))
        if set(units) != seen:
            raise ValueError(
                "Registration unit mapping must exactly match the request",
            )

        try:
            for unit_id, record, unit in staged:
                self._store._active[unit_id] = record
                self._units[unit_id] = unit
        except Exception:
            for unit_id, _record, _unit in staged:
                self._store._active.pop(unit_id, None)
                self._units.pop(unit_id, None)
            raise

    def check_transition(
        self,
        unit_id: str,
        casualty_rate: float,
        suppression_level: float,
        leadership_present: bool,
        cohesion: float,
        force_ratio: float,
        *,
        timestamp: datetime,
        current_time_s: float,
        cbrn_stress: float = 0.0,
    ) -> MoraleState:
        """Execute one cooldown-aware admitted stochastic morale check."""
        record, unit, logical_time = self._prevalidate_transition(
            unit_id,
            timestamp,
            current_time_s,
        )
        if record.current_state is MoraleState.SURRENDERED:
            return record.current_state
        if (
            record.last_transition_time_s is not None
            and logical_time - record.last_transition_time_s
            < self._config.transition_cooldown_s
        ):
            return record.current_state
        previous_check = record.last_check_time_s or 0.0
        dt = logical_time - previous_check
        if not math.isfinite(dt) or dt <= 0.0:
            raise ValueError("Admitted morale check dt must be finite and positive")

        rng_before = copy.deepcopy(self._rng.bit_generator.state)
        old_status = unit.status
        old_route = self._rout_engine._active_rout_snapshot(unit_id)
        try:
            new_state = self._machine.select_transition(
                record.current_state,
                casualty_rate,
                suppression_level,
                leadership_present,
                cohesion,
                force_ratio,
                dt=dt,
                cbrn_stress=cbrn_stress,
            )
            new_record = MoraleStateRecord(
                current_state=new_state,
                last_transition_time_s=(
                    logical_time
                    if new_state is not record.current_state
                    else record.last_transition_time_s
                ),
                last_check_time_s=logical_time,
                generation=record.generation + 1,
            )
            event = (
                self._transition_event(
                    unit_id,
                    record.current_state,
                    new_state,
                    MoraleTransitionCause.STOCHASTIC,
                    timestamp,
                    logical_time,
                )
                if new_state is not record.current_state
                else None
            )
            self._store._active[unit_id] = new_record
            unit.status = _required_status(new_state)
            if new_state is not MoraleState.ROUTED:
                self._rout_engine._remove_active_rout(unit_id)
        except Exception:
            self._store._active[unit_id] = record
            unit.status = old_status
            self._rout_engine._restore_active_rout(unit_id, old_route)
            self._rng.bit_generator.state = rng_before
            raise

        if event is not None:
            self._publish_events((event,), label="morale transition")
        return new_state

    def force_transition(
        self,
        unit_id: str,
        new_state: MoraleState,
        *,
        cause: MoraleTransitionCause,
        timestamp: datetime,
        current_time_s: float,
    ) -> MoraleState:
        """Apply a forced melee-rout transition without an RNG draw."""
        if cause is not MoraleTransitionCause.MELEE_ROUT:
            raise ValueError(
                "force_transition is reserved for MELEE_ROUT; use the "
                "dedicated rally or cascade transaction",
            )
        if new_state is not MoraleState.ROUTED:
            raise ValueError("MELEE_ROUT may only transition to ROUTED")
        record, unit, logical_time = self._prevalidate_transition(
            unit_id,
            timestamp,
            current_time_s,
        )
        if record.current_state in (
            MoraleState.ROUTED,
            MoraleState.SURRENDERED,
        ):
            return record.current_state
        if record.current_state not in (
            MoraleState.STEADY,
            MoraleState.SHAKEN,
            MoraleState.BROKEN,
        ):
            raise ValueError("Invalid MELEE_ROUT source state")
        new_record = self._forced_record(record, new_state, logical_time)
        event = self._transition_event(
            unit_id,
            record.current_state,
            new_state,
            cause,
            timestamp,
            logical_time,
        )
        old_status = unit.status
        try:
            self._store._active[unit_id] = new_record
            unit.status = UnitStatus.ROUTING
        except Exception:
            self._store._active[unit_id] = record
            unit.status = old_status
            raise
        self._publish_events((event,), label="forced morale transition")
        return new_state

    def check_rally(
        self,
        unit_id: str,
        nearby_friendly_count: int,
        leader_present: bool,
        *,
        timestamp: datetime,
        current_time_s: float,
    ) -> bool:
        """Evaluate and atomically commit one eligible rally attempt."""
        record, unit, logical_time = self._prevalidate_transition(
            unit_id,
            timestamp,
            current_time_s,
        )
        if record.current_state is not MoraleState.ROUTED:
            return False
        rng_before = copy.deepcopy(self._rng.bit_generator.state)
        old_status = unit.status
        old_route = self._rout_engine._active_rout_snapshot(unit_id)
        try:
            plan = self._rout_engine.plan_rally(
                unit_id,
                nearby_friendly_count,
                leader_present,
            )
            if not plan.rallied:
                return False
            new_record = self._forced_record(
                record,
                MoraleState.SHAKEN,
                logical_time,
            )
            state_event = self._transition_event(
                unit_id,
                MoraleState.ROUTED,
                MoraleState.SHAKEN,
                MoraleTransitionCause.RALLY,
                timestamp,
                logical_time,
            )
            rally_event = RallyEvent(
                timestamp=timestamp,
                source=ModuleId.MORALE,
                unit_id=unit_id,
                rallied_by=plan.rallied_by,
            )
            self._store._active[unit_id] = new_record
            unit.status = UnitStatus.ACTIVE
            self._rout_engine._remove_active_rout(unit_id)
        except Exception:
            self._store._active[unit_id] = record
            unit.status = old_status
            self._rout_engine._restore_active_rout(unit_id, old_route)
            self._rng.bit_generator.state = rng_before
            raise
        self._publish_events(
            (state_event, rally_event),
            label="rally transition",
        )
        return True

    def rout_cascade(
        self,
        routing_unit_id: str,
        candidate_distances_m: Mapping[str, float],
        *,
        timestamp: datetime,
        current_time_s: float,
    ) -> tuple[str, ...]:
        """Select and commit one routing source's atomic cascade batch."""
        source_record, _source_unit, logical_time = (
            self._prevalidate_transition(
                routing_unit_id,
                timestamp,
                current_time_s,
            )
        )
        if source_record.current_state is not MoraleState.ROUTED:
            return ()
        if not isinstance(candidate_distances_m, Mapping):
            raise TypeError("candidate_distances_m must be a mapping")

        candidates: list[RoutCascadeCandidate] = []
        for unit_id in sorted(candidate_distances_m):
            record, unit = self._record_and_unit(unit_id)
            self._validate_record_time(record, logical_time)
            if (
                unit.status in (UnitStatus.DISABLED, UnitStatus.DESTROYED)
                and record.current_state in (
                    MoraleState.SHAKEN,
                    MoraleState.BROKEN,
                )
            ):
                raise ValueError(
                    f"Terminal cascade candidate {unit_id!r} cannot be routed",
                )
            distance = _validated_time(
                candidate_distances_m[unit_id],
                label=f"cascade distance for {unit_id!r}",
            )
            candidates.append(
                RoutCascadeCandidate(
                    unit_id=unit_id,
                    morale_state=int(record.current_state),
                    distance_m=distance,
                ),
            )

        rng_before = copy.deepcopy(self._rng.bit_generator.state)
        try:
            plan = self._rout_engine.plan_cascade(
                routing_unit_id,
                tuple(candidates),
            )
        except Exception:
            self._rng.bit_generator.state = rng_before
            raise
        if not plan.selected_unit_ids:
            return ()

        old: list[tuple[str, MoraleStateRecord, Unit, UnitStatus]] = []
        try:
            for unit_id in plan.selected_unit_ids:
                record, unit = self._record_and_unit(unit_id)
                if record.current_state not in (
                    MoraleState.SHAKEN,
                    MoraleState.BROKEN,
                ):
                    raise RuntimeError(
                        "Cascade candidate changed after planning",
                    )
                old.append((unit_id, record, unit, unit.status))
            new_records = [
                (
                    unit_id,
                    self._forced_record(
                        record,
                        MoraleState.ROUTED,
                        logical_time,
                    ),
                )
                for unit_id, record, _unit, _status in old
            ]
            events = [
                self._transition_event(
                    unit_id,
                    record.current_state,
                    MoraleState.ROUTED,
                    MoraleTransitionCause.ROUT_CASCADE,
                    timestamp,
                    logical_time,
                )
                for unit_id, record, _unit, _status in old
            ]
            for unit_id, new_record in new_records:
                self._store._active[unit_id] = new_record
            for unit_id, _record, unit, _status in old:
                unit.status = UnitStatus.ROUTING
        except Exception:
            for unit_id, record, unit, status in old:
                self._store._active[unit_id] = record
                unit.status = status
            self._rng.bit_generator.state = rng_before
            raise
        self._publish_events(tuple(events), label="rout cascade")
        return plan.selected_unit_ids

    def prepare_aggregation(
        self,
        aggregate_id: str,
        constituent_ids: Sequence[str],
        proxy_unit: Unit,
    ) -> MoraleAggregationPlan:
        """Prepare the exact, reversible morale aggregation mutation."""
        if not isinstance(aggregate_id, str) or not aggregate_id:
            raise ValueError("aggregate_id must be a non-empty string")
        ids = tuple(sorted(constituent_ids))
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Aggregation constituents must be unique and non-empty")
        if aggregate_id in self._store._active or aggregate_id in self._store._suspended:
            raise ValueError(f"Aggregate morale ID {aggregate_id!r} already exists")
        if not isinstance(proxy_unit, Unit) or proxy_unit.entity_id != aggregate_id:
            raise ValueError("Aggregate proxy ID does not match aggregate_id")
        if proxy_unit.status is not UnitStatus.ACTIVE:
            raise ValueError("Morale aggregation requires an active aggregate proxy")
        constituents: list[tuple[str, MoraleStateRecord, Unit]] = []
        for unit_id in ids:
            record, unit = self._record_and_unit(unit_id)
            if unit.status is not UnitStatus.ACTIVE:
                raise ValueError(
                    f"Aggregation requires active constituent {unit_id!r}",
                )
            constituents.append((unit_id, record, unit))
        worst_state = max(
            record.current_state
            for _, record, _ in constituents
        )
        proxy_record = next(
            record
            for unit_id, record, _ in constituents
            if record.current_state is worst_state
        )
        archive = MoraleAggregateArchive(
            aggregate_id=aggregate_id,
            constituent_records=tuple(
                (unit_id, record)
                for unit_id, record, _ in constituents
            ),
            proxy_baseline=proxy_record,
        )
        return MoraleAggregationPlan(
            owner_token=self._owner_token,
            aggregate_id=aggregate_id,
            constituents=tuple(constituents),
            proxy_unit=proxy_unit,
            proxy_record=proxy_record,
            proxy_status_before=proxy_unit.status,
            archive=archive,
        )

    def commit_aggregation(self, plan: MoraleAggregationPlan) -> None:
        """Commit a prepared aggregate store mutation in place."""
        if not isinstance(plan, MoraleAggregationPlan):
            raise TypeError("plan must be a MoraleAggregationPlan")
        self._validate_plan_owner(plan.owner_token)
        if (
            not isinstance(plan.aggregate_id, str)
            or not plan.aggregate_id
            or not isinstance(plan.constituents, tuple)
            or not plan.constituents
            or any(
                not isinstance(entry, tuple) or len(entry) != 3
                for entry in plan.constituents
            )
            or any(
                not isinstance(unit_id, str)
                or not unit_id
                or not isinstance(record, MoraleStateRecord)
                or not isinstance(unit, Unit)
                for unit_id, record, unit in plan.constituents
            )
            or not isinstance(plan.proxy_record, MoraleStateRecord)
            or not isinstance(plan.archive, MoraleAggregateArchive)
            or not isinstance(plan.proxy_status_before, UnitStatus)
            or plan.proxy_status_before is not UnitStatus.ACTIVE
        ):
            raise ValueError("Morale aggregation plan is not self-consistent")
        constituent_ids = tuple(
            unit_id for unit_id, _record, _unit in plan.constituents
        )
        if constituent_ids != tuple(sorted(set(constituent_ids))):
            raise ValueError("Morale aggregation plan is not self-consistent")
        expected_archive_records = tuple(
            (unit_id, record)
            for unit_id, record, _unit in plan.constituents
        )
        if (
            plan.archive.aggregate_id != plan.aggregate_id
            or plan.archive.constituent_records != expected_archive_records
            or plan.archive.proxy_baseline != plan.proxy_record
        ):
            raise ValueError("Morale aggregation plan is not self-consistent")
        worst_state = max(
            record.current_state
            for _unit_id, record, _unit in plan.constituents
        )
        canonical_proxy = next(
            record
            for _unit_id, record, _unit in plan.constituents
            if record.current_state is worst_state
        )
        if plan.proxy_record != canonical_proxy:
            raise ValueError("Morale aggregation plan is not self-consistent")
        if (
            plan.aggregate_id in self._store._active
            or plan.aggregate_id in self._store._suspended
            or plan.aggregate_id in self._units
            or not isinstance(plan.proxy_unit, Unit)
            or plan.proxy_unit.entity_id != plan.aggregate_id
            or plan.proxy_unit.status is not plan.proxy_status_before
            or plan.proxy_unit.status is not UnitStatus.ACTIVE
        ):
            raise ValueError("Morale aggregation plan is stale")
        for unit_id, record, unit in plan.constituents:
            if (
                self._store._active.get(unit_id) != record
                or self._units.get(unit_id) is not unit
                or unit.entity_id != unit_id
                or unit.status is not UnitStatus.ACTIVE
                or not _status_is_compatible(unit, record)
            ):
                raise ValueError("Morale aggregation plan is stale")
        try:
            for unit_id, _record, _unit in plan.constituents:
                self._store._active.pop(unit_id)
                self._units.pop(unit_id)
            self._store._suspended[plan.aggregate_id] = plan.archive
            self._store._active[plan.aggregate_id] = plan.proxy_record
            self._units[plan.aggregate_id] = plan.proxy_unit
            plan.proxy_unit.status = _required_status(
                plan.proxy_record.current_state,
            )
        except Exception:
            self.rollback_aggregation(plan)
            raise

    def rollback_aggregation(self, plan: MoraleAggregationPlan) -> None:
        """Restore the pre-aggregation morale topology in place."""
        self._validate_plan_owner(plan.owner_token)
        self._store._active.pop(plan.aggregate_id, None)
        self._store._suspended.pop(plan.aggregate_id, None)
        self._units.pop(plan.aggregate_id, None)
        for unit_id, record, unit in plan.constituents:
            self._store._active[unit_id] = record
            self._units[unit_id] = unit
        plan.proxy_unit.status = plan.proxy_status_before

    def prepare_disaggregation(
        self,
        aggregate_id: str,
        restored_units: Mapping[str, Unit],
    ) -> MoraleDisaggregationPlan:
        """Validate unchanged proxy state and prepare exact restoration."""
        archive = self._store._suspended.get(aggregate_id)
        if archive is None:
            raise ValueError(f"Unknown morale aggregate {aggregate_id!r}")
        proxy_record = self._store._active.get(aggregate_id)
        if proxy_record != archive.proxy_baseline:
            raise ValueError(
                f"Aggregate morale proxy {aggregate_id!r} evolved",
            )
        proxy_unit = self._units.get(aggregate_id)
        if proxy_unit is None:
            raise ValueError("Aggregate morale proxy unit is missing")
        if proxy_unit.status is not _required_status(archive.proxy_baseline.current_state):
            raise ValueError("Aggregate morale proxy status is not restorable")
        constituent_ids = tuple(
            unit_id
            for unit_id, _ in archive.constituent_records
        )
        if set(restored_units) != set(constituent_ids):
            raise ValueError(
                "Restored unit IDs do not match archived morale constituents",
            )
        staged_units: list[tuple[str, Unit, UnitStatus]] = []
        for unit_id in constituent_ids:
            unit = restored_units[unit_id]
            if not isinstance(unit, Unit) or unit.entity_id != unit_id:
                raise ValueError("Restored unit key/entity_id mismatch")
            if unit.status is not UnitStatus.ACTIVE:
                raise ValueError(
                    "Morale disaggregation requires an active restored unit",
                )
            staged_units.append((unit_id, unit, unit.status))
        return MoraleDisaggregationPlan(
            owner_token=self._owner_token,
            aggregate_id=aggregate_id,
            archive=archive,
            proxy_unit=proxy_unit,
            restored_units=tuple(staged_units),
        )

    def commit_disaggregation(self, plan: MoraleDisaggregationPlan) -> None:
        """Commit an exact archived constituent restoration in place."""
        self._validate_plan_owner(plan.owner_token)
        if (
            self._store._suspended.get(plan.aggregate_id) != plan.archive
            or self._store._active.get(plan.aggregate_id)
            != plan.archive.proxy_baseline
            or self._units.get(plan.aggregate_id) is not plan.proxy_unit
            or plan.proxy_unit.entity_id != plan.aggregate_id
            or plan.proxy_unit.status
            is not _required_status(
                plan.archive.proxy_baseline.current_state,
            )
        ):
            raise ValueError("Morale disaggregation plan is stale")
        record_by_id = dict(plan.archive.constituent_records)
        restored_ids = tuple(unit_id for unit_id, _unit, _status in plan.restored_units)
        if restored_ids != tuple(record_by_id) or any(
            not isinstance(unit, Unit)
            or unit.entity_id != unit_id
            or unit.status is not old_status
            or old_status is not UnitStatus.ACTIVE
            or not _status_value_is_compatible(
                old_status,
                record_by_id[unit_id],
            )
            or unit_id in self._store._active
            or unit_id in self._units
            for unit_id, unit, old_status in plan.restored_units
        ):
            raise ValueError("Morale disaggregation plan is stale")
        try:
            self._store._active.pop(plan.aggregate_id)
            self._store._suspended.pop(plan.aggregate_id)
            self._units.pop(plan.aggregate_id)
            for unit_id, unit, _status in plan.restored_units:
                record = record_by_id[unit_id]
                self._store._active[unit_id] = record
                self._units[unit_id] = unit
                unit.status = _required_status(record.current_state)
        except Exception:
            self.rollback_disaggregation(plan)
            raise

    def rollback_disaggregation(self, plan: MoraleDisaggregationPlan) -> None:
        """Restore the aggregate proxy topology in place."""
        self._validate_plan_owner(plan.owner_token)
        for unit_id, unit, old_status in plan.restored_units:
            self._store._active.pop(unit_id, None)
            self._units.pop(unit_id, None)
            unit.status = old_status
        self._store._suspended[plan.aggregate_id] = plan.archive
        self._store._active[plan.aggregate_id] = plan.archive.proxy_baseline
        self._units[plan.aggregate_id] = plan.proxy_unit

    def get_state(self) -> dict[str, Any]:
        """Return canonical current-format state without any RNG mirror."""
        return {
            "active_records": {
                unit_id: _record_state(self._store._active[unit_id])
                for unit_id in sorted(self._store._active)
            },
            "suspended_archives": {
                aggregate_id: {
                    "proxy_baseline": _record_state(archive.proxy_baseline),
                    "constituent_records": {
                        unit_id: _record_state(record)
                        for unit_id, record in archive.constituent_records
                    },
                }
                for aggregate_id, archive in sorted(
                    self._store._suspended.items(),
                )
            },
        }

    def stage_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_units: Mapping[str, Unit],
        elapsed_time_s: float,
        aggregate_constituents: Mapping[str, Sequence[str]] | None = None,
        suspended_statuses: Mapping[str, UnitStatus] | None = None,
    ) -> MoraleRuntimeStatePlan:
        """Validate a complete current-format envelope without mutation."""
        elapsed = _validated_time(elapsed_time_s, label="elapsed_time_s")
        if not isinstance(state, Mapping) or set(state) != {
            "active_records",
            "suspended_archives",
        }:
            raise ValueError("Morale runtime state has invalid key topology")
        raw_active = state["active_records"]
        raw_archives = state["suspended_archives"]
        if not isinstance(raw_active, Mapping) or not isinstance(
            raw_archives,
            Mapping,
        ):
            raise ValueError("Morale records and archives must be mappings")
        active_records: list[tuple[str, MoraleStateRecord]] = []
        for unit_id in sorted(raw_active):
            if not isinstance(unit_id, str) or not unit_id:
                raise ValueError("Active morale IDs must be non-empty strings")
            record = _parse_record(
                raw_active[unit_id],
                label=f"active morale record {unit_id!r}",
            )
            self._validate_record_time(record, elapsed)
            active_records.append((unit_id, record))
        if set(dict(active_records)) != set(expected_units):
            raise ValueError("Active morale topology does not match active roster")
        for unit_id, record in active_records:
            unit = expected_units[unit_id]
            if unit.entity_id != unit_id or not _status_is_compatible(unit, record):
                raise ValueError(
                    f"Checkpoint morale/status disagree for unit {unit_id!r}",
                )

        expected_aggregates = aggregate_constituents or {}
        expected_suspended_statuses = suspended_statuses or {}
        if not isinstance(expected_suspended_statuses, Mapping):
            raise TypeError("suspended_statuses must be a mapping")
        archives: list[tuple[str, MoraleAggregateArchive]] = []
        all_suspended: set[str] = set()
        suspended_records: dict[str, MoraleStateRecord] = {}
        for aggregate_id in sorted(raw_archives):
            raw_archive = raw_archives[aggregate_id]
            if (
                not isinstance(aggregate_id, str)
                or not aggregate_id
                or not isinstance(raw_archive, Mapping)
                or set(raw_archive)
                != {"proxy_baseline", "constituent_records"}
            ):
                raise ValueError("Invalid suspended morale archive topology")
            raw_constituents = raw_archive["constituent_records"]
            if not isinstance(raw_constituents, Mapping) or not raw_constituents:
                raise ValueError("Morale archive constituents must be a mapping")
            constituent_records: list[tuple[str, MoraleStateRecord]] = []
            for unit_id in sorted(raw_constituents):
                if (
                    not isinstance(unit_id, str)
                    or not unit_id
                    or unit_id in all_suspended
                    or unit_id in raw_active
                ):
                    raise ValueError("Invalid or duplicate suspended morale unit")
                record = _parse_record(
                    raw_constituents[unit_id],
                    label=f"suspended morale record {unit_id!r}",
                )
                self._validate_record_time(record, elapsed)
                all_suspended.add(unit_id)
                suspended_records[unit_id] = record
                constituent_records.append((unit_id, record))
            baseline = _parse_record(
                raw_archive["proxy_baseline"],
                label=f"proxy baseline {aggregate_id!r}",
            )
            self._validate_record_time(baseline, elapsed)
            worst_state = max(
                record.current_state
                for _unit_id, record in constituent_records
            )
            expected_baseline = next(
                record
                for _unit_id, record in constituent_records
                if record.current_state is worst_state
            )
            if baseline != expected_baseline:
                raise ValueError(
                    "Morale archive proxy baseline is not the canonical "
                    "worst constituent record",
                )
            if aggregate_id not in raw_active:
                raise ValueError("Morale archive has no active aggregate proxy")
            if tuple(sorted(expected_aggregates.get(aggregate_id, ()))) != tuple(
                unit_id for unit_id, _ in constituent_records
            ):
                raise ValueError(
                    "Morale archive does not match aggregation topology",
                )
            archives.append(
                (
                    aggregate_id,
                    MoraleAggregateArchive(
                        aggregate_id=aggregate_id,
                        constituent_records=tuple(constituent_records),
                        proxy_baseline=baseline,
                    ),
                ),
            )
        if set(raw_archives) != set(expected_aggregates):
            raise ValueError("Morale/aggregation archive IDs disagree")
        if set(expected_suspended_statuses) != all_suspended:
            raise ValueError(
                "Suspended morale/status topology disagrees",
            )
        for unit_id in sorted(all_suspended):
            status = expected_suspended_statuses[unit_id]
            record = suspended_records[unit_id]
            if not isinstance(status, UnitStatus) or not (
                _status_value_is_compatible(status, record)
            ):
                raise ValueError(
                    "Checkpoint suspended morale/status disagree for unit "
                    f"{unit_id!r}",
                )
        return MoraleRuntimeStatePlan(
            owner_token=self._owner_token,
            active_records=tuple(active_records),
            suspended_archives=tuple(archives),
        )

    def commit_state(
        self,
        plan: MoraleRuntimeStatePlan,
        *,
        units: Mapping[str, Unit],
        elapsed_time_s: float,
        aggregate_constituents: Mapping[str, Sequence[str]],
        suspended_statuses: Mapping[str, UnitStatus],
    ) -> None:
        """Commit a validated envelope while preserving owner/view identity."""
        if not isinstance(plan, MoraleRuntimeStatePlan):
            raise TypeError("plan must be a MoraleRuntimeStatePlan")
        self._validate_plan_owner(plan.owner_token)
        if not isinstance(plan.active_records, tuple) or any(
            not isinstance(entry, tuple)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not entry[0]
            or not isinstance(entry[1], MoraleStateRecord)
            for entry in plan.active_records
        ):
            raise ValueError(
                "Morale state plan requires canonical unique active records",
            )
        active_ids = tuple(unit_id for unit_id, _record in plan.active_records)
        if active_ids != tuple(sorted(set(active_ids))):
            raise ValueError(
                "Morale state plan requires canonical unique active records",
            )
        if not isinstance(plan.suspended_archives, tuple) or any(
            not isinstance(entry, tuple)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not entry[0]
            or not isinstance(entry[1], MoraleAggregateArchive)
            or entry[1].aggregate_id != entry[0]
            or not isinstance(entry[1].proxy_baseline, MoraleStateRecord)
            for entry in plan.suspended_archives
        ):
            raise ValueError(
                "Morale state plan requires canonical unique archives",
            )
        archive_ids = tuple(
            aggregate_id
            for aggregate_id, _archive in plan.suspended_archives
        )
        if archive_ids != tuple(sorted(set(archive_ids))):
            raise ValueError(
                "Morale state plan requires canonical unique archives",
            )
        for _aggregate_id, archive in plan.suspended_archives:
            entries = archive.constituent_records
            if not isinstance(entries, tuple) or not entries or any(
                not isinstance(entry, tuple)
                or len(entry) != 2
                or not isinstance(entry[0], str)
                or not entry[0]
                or not isinstance(entry[1], MoraleStateRecord)
                for entry in entries
            ):
                raise ValueError(
                    "Morale state plan requires canonical unique constituents",
                )
            constituent_ids = tuple(unit_id for unit_id, _record in entries)
            if constituent_ids != tuple(sorted(set(constituent_ids))):
                raise ValueError(
                    "Morale state plan requires canonical unique constituents",
                )

        raw_state = {
            "active_records": {
                unit_id: _record_state(record)
                for unit_id, record in plan.active_records
            },
            "suspended_archives": {
                aggregate_id: {
                    "proxy_baseline": _record_state(archive.proxy_baseline),
                    "constituent_records": {
                        unit_id: _record_state(record)
                        for unit_id, record in archive.constituent_records
                    },
                }
                for aggregate_id, archive in plan.suspended_archives
            },
        }
        canonical = self.stage_state(
            raw_state,
            expected_units=units,
            elapsed_time_s=elapsed_time_s,
            aggregate_constituents=aggregate_constituents,
            suspended_statuses=suspended_statuses,
        )
        if (
            canonical.active_records != plan.active_records
            or canonical.suspended_archives != plan.suspended_archives
        ):
            raise ValueError("Morale state plan is not canonical")
        self._store._active.clear()
        self._store._active.update(canonical.active_records)
        self._store._suspended.clear()
        self._store._suspended.update(canonical.suspended_archives)
        self._units.clear()
        self._units.update(units)

    def set_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_units: Mapping[str, Unit],
        elapsed_time_s: float,
        aggregate_constituents: Mapping[str, Sequence[str]] | None = None,
        suspended_statuses: Mapping[str, UnitStatus] | None = None,
    ) -> None:
        """Validate and commit a complete current-format envelope."""
        plan = self.stage_state(
            state,
            expected_units=expected_units,
            elapsed_time_s=elapsed_time_s,
            aggregate_constituents=aggregate_constituents,
            suspended_statuses=suspended_statuses,
        )
        self.commit_state(
            plan,
            units=expected_units,
            elapsed_time_s=elapsed_time_s,
            aggregate_constituents=aggregate_constituents or {},
            suspended_statuses=suspended_statuses or {},
        )

    def _record_and_unit(
        self,
        unit_id: str,
    ) -> tuple[MoraleStateRecord, Unit]:
        if not isinstance(unit_id, str) or not unit_id:
            raise ValueError("Morale unit_id must be a non-empty string")
        record = self._store._active.get(unit_id)
        unit = self._units.get(unit_id)
        if record is None or unit is None:
            raise ValueError(f"Unknown active morale unit {unit_id!r}")
        if not _status_is_compatible(unit, record):
            raise ValueError(f"Morale/status disagree for unit {unit_id!r}")
        return record, unit

    def _prevalidate_transition(
        self,
        unit_id: str,
        timestamp: datetime,
        current_time_s: float,
    ) -> tuple[MoraleStateRecord, Unit, float]:
        if not isinstance(timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        logical_time = _validated_time(
            current_time_s,
            label="current_time_s",
        )
        record, unit = self._record_and_unit(unit_id)
        self._validate_record_time(record, logical_time)
        if unit.status in (UnitStatus.DISABLED, UnitStatus.DESTROYED):
            raise ValueError(
                f"Terminal unit {unit_id!r} cannot execute a morale operation",
            )
        return record, unit, logical_time

    @staticmethod
    def _validate_record_time(
        record: MoraleStateRecord,
        elapsed_time_s: float,
    ) -> None:
        for value in (
            record.last_transition_time_s,
            record.last_check_time_s,
        ):
            if value is not None and value > elapsed_time_s:
                raise ValueError("Morale record time exceeds logical time")

    @staticmethod
    def _forced_record(
        record: MoraleStateRecord,
        new_state: MoraleState,
        logical_time: float,
    ) -> MoraleStateRecord:
        return MoraleStateRecord(
            current_state=new_state,
            last_transition_time_s=logical_time,
            last_check_time_s=logical_time,
            generation=record.generation + 1,
        )

    @staticmethod
    def _transition_event(
        unit_id: str,
        old_state: MoraleState,
        new_state: MoraleState,
        cause: MoraleTransitionCause,
        timestamp: datetime,
        logical_time_s: float,
    ) -> MoraleStateChangeEvent:
        return MoraleStateChangeEvent(
            timestamp=timestamp,
            source=ModuleId.MORALE,
            unit_id=unit_id,
            old_state=int(old_state),
            new_state=int(new_state),
            cause=cause,
            logical_time_s=logical_time_s,
        )

    def _publish_events(
        self,
        events: Sequence[MoraleStateChangeEvent | RallyEvent],
        *,
        label: str,
    ) -> None:
        errors: list[Exception] = []
        for event in events:
            errors.extend(self._event_bus.publish_collecting(event))
        if errors:
            raise ExceptionGroup(f"{label} subscriber failures", errors)

    def _validate_plan_owner(self, owner_token: object) -> None:
        if owner_token is not self._owner_token:
            raise ValueError("Morale plan belongs to another runtime")


__all__ = [
    "MoraleAggregateArchive",
    "MoraleAggregationPlan",
    "MoraleDisaggregationPlan",
    "MoraleRegistration",
    "MoraleRuntime",
    "MoraleRuntimeStatePlan",
    "MoraleStateRecord",
    "MoraleTransitionCause",
]

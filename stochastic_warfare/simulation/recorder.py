"""Simulation event recorder — captures all events for replay and analysis.

Subscribes to the :class:`EventBus` base ``Event`` type (via MRO dispatch)
to capture every published event.  Periodically stores state snapshots for
debugging, replay, and post-simulation analysis.

Supports checkpoint/restore via the standard ``get_state``/``set_state``
protocol.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.runtime_failure import (
    RuntimeFailureHandler,
    RuntimeFailurePolicyBinding,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pydantic configuration
# ---------------------------------------------------------------------------


class RecorderConfig(BaseModel):
    """Configuration for the simulation event recorder."""

    model_config = ConfigDict(extra="forbid")

    max_events: StrictInt = Field(default=1_000_000, gt=0)
    snapshot_interval_ticks: StrictInt = Field(default=100, ge=0)
    enabled: StrictBool = True
    strict_overflow: StrictBool = False
    strict_extraction_errors: StrictBool = False


# ---------------------------------------------------------------------------
# Frozen data records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordedEvent:
    """Immutable record of a single captured event."""

    tick: int
    timestamp: datetime
    event_type: str
    source: str
    data: dict[str, Any]


@dataclass(frozen=True)
class StateSnapshot:
    """Immutable periodic snapshot of simulation state."""

    tick: int
    timestamp: datetime
    state: dict[str, Any]


@dataclass(frozen=True)
class RecorderStatePlan:
    """Validated, owner-bound recorder checkpoint commit plan."""

    owner_id: int
    current_tick: int
    events: tuple[RecordedEvent, ...]
    snapshots: tuple[StateSnapshot, ...]


# ---------------------------------------------------------------------------
# Main recorder
# ---------------------------------------------------------------------------


class SimulationRecorder:
    """Captures all events published to an EventBus for later analysis.

    Parameters
    ----------
    event_bus:
        The bus to subscribe to.
    config:
        Optional recorder configuration.  Defaults are used when *None*.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: RecorderConfig | None = None,
    ) -> None:
        self._bus = event_bus
        self._config = config or RecorderConfig()
        self._events: list[RecordedEvent] = []
        self._snapshots: list[StateSnapshot] = []
        self._current_tick: int = 0
        self._subscribed: bool = False
        self._runtime_failure_handler: RuntimeFailurePolicyBinding | None = None
        self._unreported_integrity_failure: Exception | None = None
        self._overflow_failure: RuntimeError | None = None
        self._overflow_fallback_active = False

    def _validate_runtime_config(self) -> None:
        """Validate recorder settings used by an authoritative runtime."""
        if not self._config.enabled:
            raise ValueError("A runtime-bound recorder must be enabled")
        if (
            isinstance(self._config.max_events, bool)
            or not isinstance(self._config.max_events, int)
            or self._config.max_events <= 0
        ):
            raise ValueError(
                "A runtime-bound recorder requires a positive max_events",
            )
        if (
            isinstance(self._config.snapshot_interval_ticks, bool)
            or not isinstance(self._config.snapshot_interval_ticks, int)
            or self._config.snapshot_interval_ticks < 0
        ):
            raise ValueError(
                "A runtime-bound recorder requires a non-negative "
                "snapshot_interval_ticks",
            )

    def bind_runtime_failure_handler(
        self,
        handler: RuntimeFailureHandler,
        *,
        event_bus: EventBus,
    ) -> None:
        """Bind and validate the production owner of recorder integrity."""
        binding = RuntimeFailurePolicyBinding(handler)
        if event_bus is not self._bus:
            raise ValueError(
                "Runtime recorder must use the SimulationContext event bus",
            )
        self._validate_runtime_config()
        if self._unreported_integrity_failure is not None:
            raise self._unreported_integrity_failure
        existing = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if existing is not None and existing != handler:
            raise RuntimeError(
                "SimulationRecorder already has a different runtime "
                "failure-policy owner",
            )
        self._runtime_failure_handler = binding

    def validate_runtime_integrity(
        self,
        handler: RuntimeFailureHandler,
        *,
        event_bus: EventBus,
    ) -> None:
        """Reject recorder owner/config drift or pre-binding evidence loss."""
        if event_bus is not self._bus:
            raise RuntimeError(
                "Runtime recorder event-bus binding changed",
            )
        self._validate_runtime_config()
        bound = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if bound != handler:
            raise RuntimeError(
                "Runtime recorder failure-policy binding changed",
            )
        if self._unreported_integrity_failure is not None:
            raise self._unreported_integrity_failure

    def _apply_runtime_integrity_policy(
        self,
        operation: str,
        exception: Exception,
    ) -> bool:
        """Report one integrity fault, or mark an unbound recorder unhealthy."""
        handler = (
            self._runtime_failure_handler.resolve()
            if self._runtime_failure_handler is not None
            else None
        )
        if handler is None:
            if self._unreported_integrity_failure is None:
                self._unreported_integrity_failure = exception
            return False
        if not handler("simulation.recorder", operation, exception):
            raise exception
        return True

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Subscribe to the base ``Event`` class to capture all events."""
        if not self._subscribed:
            self._bus.subscribe(Event, self._on_event)
            self._subscribed = True
            logger.debug("Recorder started — subscribed to EventBus")

    def stop(self) -> None:
        """Unsubscribe from the event bus."""
        if self._subscribed:
            self._bus.unsubscribe(Event, self._on_event)
            self._subscribed = False
            logger.debug("Recorder stopped — unsubscribed from EventBus")

    # ── Event handling ────────────────────────────────────────────────

    def _on_event(self, event: Event) -> None:
        """Handle an incoming event — convert to RecordedEvent and store."""
        if not self._config.enabled:
            return
        if len(self._events) >= self._config.max_events:
            if self._overflow_fallback_active:
                return
            if self._overflow_failure is not None:
                raise self._overflow_failure
            failure = RuntimeError(
                "Simulation recorder event limit exceeded before recording "
                "the complete event stream",
            )
            self._overflow_failure = failure
            if self._apply_runtime_integrity_policy(
                "record_event_overflow",
                failure,
            ):
                self._overflow_fallback_active = True
                return
            if self._config.strict_overflow:
                raise failure
            # Standalone recorders retain the legacy bounded-capacity mode;
            # the integrity latch prevents later authoritative binding.
            self._overflow_fallback_active = True
            return

        recorded = RecordedEvent(
            tick=self._current_tick,
            timestamp=event.timestamp,
            event_type=type(event).__name__,
            source=event.source.value if hasattr(event.source, "value") else str(event.source),
            data=self._extract_event_data(event),
        )
        self._events.append(recorded)

    def _extract_event_data(self, event: Event) -> dict[str, Any]:
        """Extract event fields into a serializable dict.

        Removes base ``Event`` fields (timestamp, source) that are already
        captured as top-level ``RecordedEvent`` attributes.  Enum values
        are converted to their ``.value`` for serialization.
        """
        try:
            d = asdict(event)
            # Remove base fields already captured at the RecordedEvent level
            d.pop("timestamp", None)
            d.pop("source", None)
            # Convert enum values to their .value for serialization
            return {
                k: (v.value if hasattr(v, "value") else v)
                for k, v in d.items()
            }
        except Exception as exc:
            if self._apply_runtime_integrity_policy(
                "extract_event_data",
                exc,
            ):
                return {
                    "recorder_integrity_error": {
                        "exception_type": (
                            f"{type(exc).__module__}."
                            f"{type(exc).__qualname__}"
                        ),
                        "message": str(exc),
                    },
                }
            if self._config.strict_extraction_errors:
                raise RuntimeError(
                    "Simulation recorder could not extract complete event "
                    "data",
                ) from exc
            # Standalone legacy mode only; the integrity latch prevents this
            # recorder from later entering an authoritative runtime.
            return {}

    # ── Tick tracking ─────────────────────────────────────────────────

    def record_tick(self, tick: int, timestamp: datetime) -> None:
        """Mark a tick boundary — events after this call are tagged with *tick*."""
        self._current_tick = tick

    # ── Snapshots ─────────────────────────────────────────────────────

    def take_snapshot(
        self,
        tick: int,
        timestamp: datetime,
        state_provider: Callable[[], dict[str, Any]],
    ) -> None:
        """Capture a periodic state snapshot.

        Parameters
        ----------
        tick:
            Current simulation tick.
        timestamp:
            Current simulation time.
        state_provider:
            Zero-argument callable that returns the state dict to snapshot.
        """
        state = state_provider()
        snap = StateSnapshot(tick=tick, timestamp=timestamp, state=state)
        self._snapshots.append(snap)

    # ── Query API ─────────────────────────────────────────────────────

    @property
    def events(self) -> list[RecordedEvent]:
        """Return a copy of all recorded events."""
        return list(self._events)

    @property
    def snapshots(self) -> list[StateSnapshot]:
        """Return a copy of all state snapshots."""
        return list(self._snapshots)

    def event_count(self) -> int:
        """Return the number of recorded events."""
        return len(self._events)

    def events_of_type(self, event_type_name: str) -> list[RecordedEvent]:
        """Filter recorded events by type name string."""
        return [e for e in self._events if e.event_type == event_type_name]

    def events_in_range(self, start_tick: int, end_tick: int) -> list[RecordedEvent]:
        """Return events within a tick range [start_tick, end_tick] inclusive."""
        return [
            e for e in self._events
            if start_tick <= e.tick <= end_tick
        ]

    # ── Checkpoint / restore ──────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Serialize recorder state for checkpointing."""
        return {
            "events": [
                {
                    "tick": e.tick,
                    "timestamp": e.timestamp.isoformat(),
                    "event_type": e.event_type,
                    "source": e.source,
                    "data": e.data,
                }
                for e in self._events
            ],
            "snapshots": [
                {
                    "tick": s.tick,
                    "timestamp": s.timestamp.isoformat(),
                    "state": copy.deepcopy(s.state),
                }
                for s in self._snapshots
            ],
            "current_tick": self._current_tick,
        }

    @staticmethod
    def _state_tick(value: Any, *, field_name: str) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise ValueError(
                f"Recorder {field_name} must be a non-negative strict integer",
            )
        return value

    @staticmethod
    def _state_timestamp(value: Any, *, field_name: str) -> datetime:
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"Recorder {field_name} must be a non-empty ISO timestamp",
            )
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"Recorder {field_name} is not a valid ISO timestamp",
            ) from exc

    def stage_state(
        self,
        state: dict[str, Any],
        *,
        allow_legacy: bool = False,
        expected_current_tick: int | None = None,
    ) -> RecorderStatePlan:
        """Validate all recorder state without mutating live evidence."""
        if (
            not isinstance(state, dict)
            or set(state) != {"current_tick", "events", "snapshots"}
        ):
            raise ValueError(
                "Recorder checkpoint state has invalid key topology",
            )
        current_tick = self._state_tick(
            state["current_tick"],
            field_name="current_tick",
        )
        if (
            expected_current_tick is not None
            and current_tick != expected_current_tick
        ):
            raise ValueError(
                "Recorder current_tick disagrees with the checkpoint clock",
            )
        raw_events = state["events"]
        if not isinstance(raw_events, list):
            raise ValueError("Recorder events must be a list")
        events: list[RecordedEvent] = []
        prior_tick = -1
        event_fields = {
            "tick",
            "timestamp",
            "event_type",
            "source",
            "data",
        }
        for index, raw in enumerate(raw_events):
            if not isinstance(raw, dict) or set(raw) != event_fields:
                raise ValueError(
                    f"Recorder event {index} has invalid key topology",
                )
            tick = self._state_tick(
                raw["tick"],
                field_name=f"events[{index}].tick",
            )
            if tick > current_tick or tick < prior_tick:
                raise ValueError(
                    "Recorder event ticks must be ordered and no later than "
                    "current_tick",
                )
            prior_tick = tick
            event_type = raw["event_type"]
            source = raw["source"]
            if (
                not isinstance(event_type, str)
                or not event_type
                or event_type != event_type.strip()
                or not isinstance(source, str)
                or not source
                or source != source.strip()
            ):
                raise ValueError(
                    "Recorder event_type and source must be non-empty trimmed "
                    "strings",
                )
            data = raw["data"]
            if not isinstance(data, dict):
                raise ValueError("Recorder event data must be a mapping")
            events.append(
                RecordedEvent(
                    tick=tick,
                    timestamp=self._state_timestamp(
                        raw["timestamp"],
                        field_name=f"events[{index}].timestamp",
                    ),
                    event_type=event_type,
                    source=source,
                    data=copy.deepcopy(data),
                ),
            )

        raw_snapshots = state["snapshots"]
        if not isinstance(raw_snapshots, list):
            raise ValueError("Recorder snapshots must be a list")
        snapshots: list[StateSnapshot] = []
        prior_tick = -1
        for index, raw in enumerate(raw_snapshots):
            if not isinstance(raw, dict):
                raise ValueError(
                    f"Recorder snapshot {index} must be a mapping",
                )
            if allow_legacy and set(raw) == {"tick", "timestamp"}:
                raise ValueError(
                    "Legacy recorder snapshots omitted their state and cannot "
                    "be restored faithfully",
                )
            if set(raw) != {"tick", "timestamp", "state"}:
                raise ValueError(
                    f"Recorder snapshot {index} has invalid key topology",
                )
            tick = self._state_tick(
                raw["tick"],
                field_name=f"snapshots[{index}].tick",
            )
            if tick > current_tick or tick < prior_tick:
                raise ValueError(
                    "Recorder snapshot ticks must be ordered and no later "
                    "than current_tick",
                )
            prior_tick = tick
            snapshot_state = raw["state"]
            if not isinstance(snapshot_state, dict):
                raise ValueError(
                    "Recorder snapshot state must be a mapping",
                )
            snapshots.append(
                StateSnapshot(
                    tick=tick,
                    timestamp=self._state_timestamp(
                        raw["timestamp"],
                        field_name=f"snapshots[{index}].timestamp",
                    ),
                    state=copy.deepcopy(snapshot_state),
                ),
            )
        return RecorderStatePlan(
            owner_id=id(self),
            current_tick=current_tick,
            events=tuple(events),
            snapshots=tuple(snapshots),
        )

    def commit_state(self, plan: RecorderStatePlan) -> None:
        """Commit a validated recorder checkpoint plan."""
        if plan.owner_id != id(self):
            raise ValueError(
                "Recorder checkpoint plan belongs to another recorder",
            )
        self._current_tick = plan.current_tick
        self._events = [
            RecordedEvent(
                tick=event.tick,
                timestamp=event.timestamp,
                event_type=event.event_type,
                source=event.source,
                data=copy.deepcopy(event.data),
            )
            for event in plan.events
        ]
        self._snapshots = [
            StateSnapshot(
                tick=snapshot.tick,
                timestamp=snapshot.timestamp,
                state=copy.deepcopy(snapshot.state),
            )
            for snapshot in plan.snapshots
        ]

    def set_state(self, state: dict[str, Any]) -> None:
        """Validate and atomically restore recorder evidence."""
        self.commit_state(self.stage_state(state))

"""Simulation event recorder — captures all events for replay and analysis.

Subscribes to the :class:`EventBus` base ``Event`` type (via MRO dispatch)
to capture every published event.  Periodically stores state snapshots for
debugging, replay, and post-simulation analysis.

Supports checkpoint/restore via the standard ``get_state``/``set_state``
protocol.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel

from stochastic_warfare.core.events import Event, EventBus
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic configuration
# ---------------------------------------------------------------------------


class RecorderConfig(BaseModel):
    """Configuration for the simulation event recorder."""

    max_events: int = 1_000_000
    snapshot_interval_ticks: int = 100
    enabled: bool = True


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
            return  # silently drop if at capacity

        recorded = RecordedEvent(
            tick=self._current_tick,
            timestamp=event.timestamp,
            event_type=type(event).__name__,
            source=event.source.value if hasattr(event.source, "value") else str(event.source),
            data=self._extract_event_data(event),
        )
        self._events.append(recorded)

    @staticmethod
    def _extract_event_data(event: Event) -> dict[str, Any]:
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
        except Exception:
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
                }
                for s in self._snapshots
            ],
            "current_tick": self._current_tick,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore recorder state from checkpoint.

        Snapshots are **not** restored — they contain full state dicts
        that may be very large.  Only snapshot metadata is preserved in
        ``get_state``.
        """
        self._current_tick = state.get("current_tick", 0)
        self._events = [
            RecordedEvent(
                tick=e["tick"],
                timestamp=datetime.fromisoformat(e["timestamp"]),
                event_type=e["event_type"],
                source=e["source"],
                data=e["data"],
            )
            for e in state.get("events", [])
        ]

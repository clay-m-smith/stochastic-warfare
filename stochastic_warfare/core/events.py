"""Typed publish-subscribe event bus for inter-module communication.

Events are dispatched synchronously in priority order (lower value = higher
priority).  Subscribing to a base ``Event`` type will receive *all* events.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from stochastic_warfare.core.types import ModuleId


@dataclass(frozen=True)
class Event:
    """Base event — all domain events inherit from this."""

    timestamp: datetime
    source: ModuleId


class EventBus:
    """Synchronous typed pub-sub dispatcher."""

    def __init__(self) -> None:
        # event_type → list of (priority, handler)
        self._subscribers: dict[type[Event], list[tuple[int, Callable[[Event], None]]]] = (
            defaultdict(list)
        )

    def subscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Event], None],
        priority: int = 0,
    ) -> None:
        """Register *handler* for *event_type* (and its subclasses).

        Lower *priority* values are dispatched first.  Handlers at the same
        priority are called in registration order (stable sort).
        """
        self._subscribers[event_type].append((priority, handler))
        # Re-sort to maintain ordering; Python sort is stable so equal
        # priorities preserve insertion order.
        self._subscribers[event_type].sort(key=lambda t: t[0])

    def unsubscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Event], None],
    ) -> None:
        """Remove *handler* from *event_type*."""
        subs = self._subscribers.get(event_type, [])
        self._subscribers[event_type] = [
            (p, h) for p, h in subs if h != handler
        ]

    def publish(self, event: Event) -> None:
        """Dispatch *event* to all matching subscribers.

        A subscriber registered for a base type receives events of that type
        *and all subclasses*.  Uses MRO walk for O(depth) dispatch instead of
        O(num_subscribed_types) isinstance checks.
        """
        for cls in type(event).__mro__:
            handlers = self._subscribers.get(cls)
            if handlers:
                for _priority, handler in handlers:
                    handler(event)

    def clear(self) -> None:
        """Remove all subscriptions."""
        self._subscribers.clear()

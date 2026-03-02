"""Organization-layer events published on the EventBus."""

from __future__ import annotations

from dataclasses import dataclass

from stochastic_warfare.core.events import Event


@dataclass(frozen=True)
class OrgAttachEvent(Event):
    """Published when a unit is task-organized to a new parent."""

    unit_id: str
    from_parent: str
    to_parent: str
    relationship: int


@dataclass(frozen=True)
class OrgDetachEvent(Event):
    """Published when a unit is returned to its organic parent."""

    unit_id: str
    restored_parent: str

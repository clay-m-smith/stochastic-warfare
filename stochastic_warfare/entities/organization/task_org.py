"""Task organization — dynamic command relationship overlays."""

from __future__ import annotations

import enum

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree

logger = get_logger(__name__)


class CommandRelationship(enum.IntEnum):
    """NATO-standard command relationships."""

    ORGANIC = 0
    OPCON = 1
    TACON = 2
    ADCON = 3
    DIRECT_SUPPORT = 4
    GENERAL_SUPPORT = 5
    REINFORCING = 6


class TaskOrgAssignment(BaseModel):
    """A temporary task-organization reassignment."""

    unit_id: str
    original_parent: str
    current_parent: str
    relationship: int  # CommandRelationship value


class TaskOrgManager:
    """Manage task-organization overlays on top of organic hierarchy.

    Queries for subordinates check the overlay first, then fall back to
    the organic tree.
    """

    def __init__(self, hierarchy: HierarchyTree) -> None:
        self._hierarchy = hierarchy
        self._assignments: dict[str, TaskOrgAssignment] = {}

    def attach(
        self,
        unit_id: str,
        to_parent: str,
        relationship: CommandRelationship,
    ) -> TaskOrgAssignment:
        """Attach *unit_id* to *to_parent* under *relationship*."""
        original = self._hierarchy.get_parent(unit_id)
        if original is None:
            raise ValueError(f"Cannot task-org a root unit {unit_id!r}")
        assignment = TaskOrgAssignment(
            unit_id=unit_id,
            original_parent=original,
            current_parent=to_parent,
            relationship=int(relationship),
        )
        self._assignments[unit_id] = assignment
        logger.info(
            "Task org: %s -> %s (%s)",
            unit_id, to_parent, relationship.name,
        )
        return assignment

    def detach(self, unit_id: str) -> None:
        """Restore *unit_id* to its organic parent."""
        if unit_id not in self._assignments:
            raise KeyError(f"Unit {unit_id!r} has no task-org assignment")
        del self._assignments[unit_id]

    def get_effective_parent(self, unit_id: str) -> str | None:
        """Return the effective parent — overlay if present, else organic."""
        if unit_id in self._assignments:
            return self._assignments[unit_id].current_parent
        return self._hierarchy.get_parent(unit_id)

    def get_effective_subordinates(self, parent_id: str) -> list[str]:
        """Return direct subordinates considering task-org overlays.

        Units task-org'd away from *parent_id* are excluded.
        Units task-org'd to *parent_id* are included.
        """
        organic = set(self._hierarchy.get_children(parent_id))
        # Remove units that have been task-org'd away
        for uid, a in self._assignments.items():
            if a.original_parent == parent_id and a.current_parent != parent_id:
                organic.discard(uid)
            if a.current_parent == parent_id and uid not in organic:
                organic.add(uid)
        return sorted(organic)

    def get_relationship(self, unit_id: str) -> CommandRelationship:
        """Return the command relationship for *unit_id*."""
        if unit_id in self._assignments:
            return CommandRelationship(self._assignments[unit_id].relationship)
        return CommandRelationship.ORGANIC

    def is_task_organized(self, unit_id: str) -> bool:
        """Return True if *unit_id* has a task-org overlay."""
        return unit_id in self._assignments

    def get_state(self) -> dict:
        return {
            "assignments": {
                uid: a.model_dump()
                for uid, a in self._assignments.items()
            }
        }

    def set_state(self, state: dict) -> None:
        self._assignments.clear()
        for uid, ad in state["assignments"].items():
            self._assignments[uid] = TaskOrgAssignment.model_validate(ad)

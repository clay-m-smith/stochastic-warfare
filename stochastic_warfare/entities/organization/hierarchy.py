"""Organizational hierarchy tree — adjacency-list representation."""

from __future__ import annotations

from dataclasses import dataclass, field

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.entities.organization.echelons import EchelonLevel

logger = get_logger(__name__)


@dataclass
class HierarchyNode:
    """One node in the organizational tree."""

    unit_id: str
    echelon: EchelonLevel
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    side: str = "blue"


class HierarchyTree:
    """Adjacency-list tree of unit organization.

    Provides queries for chain of command, subordinates, and echelon
    filtering. All operations are O(n) at worst — sufficient for
    tactical-scale hierarchies.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, HierarchyNode] = {}

    def add_unit(
        self,
        unit_id: str,
        echelon: EchelonLevel,
        parent_id: str | None = None,
        side: str = "blue",
    ) -> HierarchyNode:
        """Add *unit_id* to the tree under *parent_id*."""
        if unit_id in self._nodes:
            raise ValueError(f"Unit {unit_id!r} already in hierarchy")
        if parent_id is not None and parent_id not in self._nodes:
            raise KeyError(f"Parent {parent_id!r} not found")
        node = HierarchyNode(
            unit_id=unit_id, echelon=echelon, parent_id=parent_id, side=side,
        )
        self._nodes[unit_id] = node
        if parent_id is not None:
            self._nodes[parent_id].children_ids.append(unit_id)
        return node

    def remove_unit(self, unit_id: str) -> None:
        """Remove *unit_id* and reparent children to its parent."""
        node = self._nodes.pop(unit_id)
        if node.parent_id is not None and node.parent_id in self._nodes:
            parent = self._nodes[node.parent_id]
            parent.children_ids.remove(unit_id)
            # Reparent children
            for child_id in node.children_ids:
                self._nodes[child_id].parent_id = node.parent_id
                parent.children_ids.append(child_id)
        else:
            for child_id in node.children_ids:
                self._nodes[child_id].parent_id = None

    def get_node(self, unit_id: str) -> HierarchyNode:
        """Return the node for *unit_id*."""
        return self._nodes[unit_id]

    def get_parent(self, unit_id: str) -> str | None:
        """Return the parent unit_id, or None if root."""
        return self._nodes[unit_id].parent_id

    def get_children(self, unit_id: str) -> list[str]:
        """Return direct child unit_ids."""
        return list(self._nodes[unit_id].children_ids)

    def get_chain_of_command(self, unit_id: str) -> list[str]:
        """Return list from root to *unit_id* (inclusive)."""
        chain: list[str] = []
        current: str | None = unit_id
        while current is not None:
            chain.append(current)
            current = self._nodes[current].parent_id
        chain.reverse()
        return chain

    def get_all_subordinates(self, unit_id: str) -> list[str]:
        """Return all subordinates recursively (depth-first)."""
        result: list[str] = []
        stack = list(self._nodes[unit_id].children_ids)
        while stack:
            cid = stack.pop()
            result.append(cid)
            stack.extend(self._nodes[cid].children_ids)
        return result

    def get_siblings(self, unit_id: str) -> list[str]:
        """Return siblings (same parent, excluding self)."""
        pid = self._nodes[unit_id].parent_id
        if pid is None:
            return []
        return [c for c in self._nodes[pid].children_ids if c != unit_id]

    def get_units_at_echelon(self, echelon: EchelonLevel) -> list[str]:
        """Return all unit_ids at a given echelon level."""
        return [uid for uid, n in self._nodes.items() if n.echelon == echelon]

    def all_unit_ids(self) -> list[str]:
        """Return all unit_ids in the tree."""
        return list(self._nodes.keys())

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, unit_id: str) -> bool:
        return unit_id in self._nodes

    def get_state(self) -> dict:
        return {
            "nodes": {
                uid: {
                    "unit_id": n.unit_id,
                    "echelon": int(n.echelon),
                    "parent_id": n.parent_id,
                    "children_ids": list(n.children_ids),
                    "side": n.side,
                }
                for uid, n in self._nodes.items()
            }
        }

    def set_state(self, state: dict) -> None:
        self._nodes.clear()
        for uid, ns in state["nodes"].items():
            self._nodes[uid] = HierarchyNode(
                unit_id=ns["unit_id"],
                echelon=EchelonLevel(ns["echelon"]),
                parent_id=ns["parent_id"],
                children_ids=list(ns["children_ids"]),
                side=ns["side"],
            )

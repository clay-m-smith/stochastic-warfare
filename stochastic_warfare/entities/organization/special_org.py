"""Special organization types — SOF, irregular, coalition."""

from __future__ import annotations

import enum

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class OrgType(enum.IntEnum):
    """Organization archetype."""

    CONVENTIONAL = 0
    SOF = 1
    IRREGULAR = 2
    COALITION = 3
    INSURGENT = 4
    MILITIA = 5
    PMC = 6


class SpecialOrgTraits(BaseModel):
    """Traits modifying behavior for non-conventional organizations."""

    org_type: int  # OrgType value
    independent_ops: bool = False
    network_structure: bool = False
    interoperability: float = 1.0  # 0.0–1.0
    c2_flexibility: float = 0.5  # 0.0–1.0


class SpecialOrgManager:
    """Designate and query special organization traits for units."""

    def __init__(self) -> None:
        self._traits: dict[str, SpecialOrgTraits] = {}

    def designate_special(
        self, unit_id: str, traits: SpecialOrgTraits
    ) -> None:
        """Apply special organization traits to *unit_id*."""
        self._traits[unit_id] = traits

    def get_traits(self, unit_id: str) -> SpecialOrgTraits | None:
        """Return traits for *unit_id*, or None if conventional."""
        return self._traits.get(unit_id)

    def remove(self, unit_id: str) -> None:
        """Remove special designation from *unit_id*."""
        self._traits.pop(unit_id, None)

    def get_state(self) -> dict:
        return {
            "traits": {
                uid: t.model_dump() for uid, t in self._traits.items()
            }
        }

    def set_state(self, state: dict) -> None:
        self._traits.clear()
        for uid, td in state["traits"].items():
            self._traits[uid] = SpecialOrgTraits.model_validate(td)

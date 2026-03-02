"""Staff section modeling — S1 through S6 effectiveness."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class StaffFunction(enum.IntEnum):
    """Standard US Army staff functions."""

    S1 = 1  # Personnel / Admin
    S2 = 2  # Intelligence
    S3 = 3  # Operations
    S4 = 4  # Logistics
    S5 = 5  # Civil-military
    S6 = 6  # Signal / Comms


@dataclass
class StaffSection:
    """One staff section within a headquarters."""

    function: StaffFunction
    effectiveness: float  # 0.0–1.0
    personnel_count: int

    def get_state(self) -> dict:
        return {
            "function": int(self.function),
            "effectiveness": self.effectiveness,
            "personnel_count": self.personnel_count,
        }

    def set_state(self, state: dict) -> None:
        self.function = StaffFunction(state["function"])
        self.effectiveness = state["effectiveness"]
        self.personnel_count = state["personnel_count"]


class StaffCapabilities:
    """Aggregate staff capability for a headquarters unit."""

    def __init__(self, sections: list[StaffSection] | None = None) -> None:
        self._sections: dict[StaffFunction, StaffSection] = {}
        if sections:
            for s in sections:
                self._sections[s.function] = s

    def get_effectiveness(self, function: StaffFunction) -> float:
        """Return effectiveness (0.0–1.0) for *function*, or 0.0 if absent."""
        s = self._sections.get(function)
        return s.effectiveness if s is not None else 0.0

    def degrade(self, function: StaffFunction, amount: float) -> None:
        """Reduce effectiveness of *function* by *amount*."""
        s = self._sections.get(function)
        if s is not None:
            s.effectiveness = max(0.0, s.effectiveness - amount)

    def has_function(self, function: StaffFunction) -> bool:
        """Return True if this staff has the given function."""
        return function in self._sections

    @property
    def overall_effectiveness(self) -> float:
        """Mean effectiveness across all sections."""
        if not self._sections:
            return 0.0
        return sum(s.effectiveness for s in self._sections.values()) / len(
            self._sections
        )

    def get_state(self) -> dict:
        return {
            "sections": [s.get_state() for s in self._sections.values()]
        }

    def set_state(self, state: dict) -> None:
        self._sections.clear()
        for sd in state["sections"]:
            s = StaffSection(StaffFunction(sd["function"]), 0.0, 0)
            s.set_state(sd)
            self._sections[s.function] = s

"""Napoleonic battalion-level formations — LINE, COLUMN, SQUARE, SKIRMISH.

Separate from the modern :mod:`movement.formation` system (which is
squad/platoon-level).  Each formation modifies firepower fraction, speed,
cavalry vulnerability, and artillery vulnerability.  Transitions take
30–120 seconds; during transition the unit uses the **worst** vulnerability
of both formations.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NapoleonicFormationType(enum.IntEnum):
    """Napoleonic battalion-level formation."""

    LINE = 0
    COLUMN = 1
    SQUARE = 2
    SKIRMISH = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class NapoleonicFormationConfig(BaseModel):
    """Configuration for Napoleonic formation modifiers and transitions."""

    firepower_fractions: dict[int, float] = {
        NapoleonicFormationType.LINE: 1.0,
        NapoleonicFormationType.COLUMN: 0.3,
        NapoleonicFormationType.SQUARE: 0.25,
        NapoleonicFormationType.SKIRMISH: 0.15,
    }

    speed_multipliers: dict[int, float] = {
        NapoleonicFormationType.LINE: 0.6,
        NapoleonicFormationType.COLUMN: 0.9,
        NapoleonicFormationType.SQUARE: 0.3,
        NapoleonicFormationType.SKIRMISH: 0.8,
    }

    cavalry_vulnerability: dict[int, float] = {
        NapoleonicFormationType.LINE: 1.0,
        NapoleonicFormationType.COLUMN: 0.8,
        NapoleonicFormationType.SQUARE: 0.1,
        NapoleonicFormationType.SKIRMISH: 1.5,
    }

    artillery_vulnerability: dict[int, float] = {
        NapoleonicFormationType.LINE: 0.5,
        NapoleonicFormationType.COLUMN: 1.5,
        NapoleonicFormationType.SQUARE: 2.0,
        NapoleonicFormationType.SKIRMISH: 0.3,
    }

    transition_times_s: dict[str, float] = {
        "LINE_to_COLUMN": 45.0,
        "LINE_to_SQUARE": 45.0,
        "LINE_to_SKIRMISH": 30.0,
        "COLUMN_to_LINE": 60.0,
        "COLUMN_to_SQUARE": 60.0,
        "COLUMN_to_SKIRMISH": 45.0,
        "SQUARE_to_LINE": 90.0,
        "SQUARE_to_COLUMN": 90.0,
        "SQUARE_to_SKIRMISH": 120.0,
        "SKIRMISH_to_LINE": 60.0,
        "SKIRMISH_to_COLUMN": 45.0,
        "SKIRMISH_to_SQUARE": 45.0,
    }


# ---------------------------------------------------------------------------
# Per-unit state
# ---------------------------------------------------------------------------


@dataclass
class UnitFormationState:
    """Tracks a single unit's formation state and any pending transition."""

    unit_id: str
    current: NapoleonicFormationType = NapoleonicFormationType.LINE
    target: NapoleonicFormationType | None = None
    transition_remaining_s: float = 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class NapoleonicFormationEngine:
    """Manages Napoleonic battalion formations and transitions.

    Parameters
    ----------
    config:
        Formation configuration.
    """

    def __init__(self, config: NapoleonicFormationConfig | None = None) -> None:
        self._config = config or NapoleonicFormationConfig()
        self._states: dict[str, UnitFormationState] = {}

    def set_formation(
        self,
        unit_id: str,
        formation: NapoleonicFormationType,
    ) -> None:
        """Set a unit's formation immediately (no transition delay)."""
        self._states[unit_id] = UnitFormationState(
            unit_id=unit_id,
            current=formation,
        )

    def order_formation_change(
        self,
        unit_id: str,
        target: NapoleonicFormationType,
    ) -> float:
        """Order a formation change, returning the transition time in seconds.

        If the unit is already in *target* or already transitioning, returns 0.
        """
        state = self._states.get(unit_id)
        if state is None:
            state = UnitFormationState(unit_id=unit_id)
            self._states[unit_id] = state

        if state.current == target:
            return 0.0
        if state.target is not None:
            return 0.0  # already transitioning

        key = f"{NapoleonicFormationType(state.current).name}_to_{NapoleonicFormationType(target).name}"
        time_s = self._config.transition_times_s.get(key, 60.0)
        state.target = target
        state.transition_remaining_s = time_s
        logger.info(
            "Unit %s: %s → %s (%.0fs)",
            unit_id, NapoleonicFormationType(state.current).name,
            NapoleonicFormationType(target).name, time_s,
        )
        return time_s

    def update(self, dt_s: float) -> list[str]:
        """Advance all transitions by *dt_s* seconds.

        Returns list of unit_ids whose transitions completed this tick.
        """
        completed: list[str] = []
        for state in self._states.values():
            if state.target is None:
                continue
            state.transition_remaining_s -= dt_s
            if state.transition_remaining_s <= 0.0:
                state.current = state.target
                state.target = None
                state.transition_remaining_s = 0.0
                completed.append(state.unit_id)
        return completed

    def get_formation(self, unit_id: str) -> NapoleonicFormationType:
        """Return the current formation for a unit."""
        state = self._states.get(unit_id)
        if state is None:
            return NapoleonicFormationType.LINE
        return state.current

    def is_transitioning(self, unit_id: str) -> bool:
        """Check if a unit is currently changing formation."""
        state = self._states.get(unit_id)
        return state is not None and state.target is not None

    def _get_modifier(
        self,
        unit_id: str,
        table: dict[int, float],
        worst: bool = False,
    ) -> float:
        """Look up a modifier, using worst-of-both during transition.

        Parameters
        ----------
        worst:
            If True, return the *higher* (worse) value during transition.
            If False, return the *lower* (worse) value during transition.
        """
        state = self._states.get(unit_id)
        if state is None:
            return table.get(int(NapoleonicFormationType.LINE), 1.0)

        current_val = table.get(int(state.current), 1.0)
        if state.target is None:
            return current_val

        target_val = table.get(int(state.target), 1.0)
        if worst:
            return max(current_val, target_val)
        return min(current_val, target_val)

    def firepower_fraction(self, unit_id: str) -> float:
        """Return the firepower fraction (0–1) for a unit's formation."""
        return self._get_modifier(
            unit_id, self._config.firepower_fractions, worst=False,
        )

    def speed_multiplier(self, unit_id: str) -> float:
        """Return the speed multiplier for a unit's formation."""
        return self._get_modifier(
            unit_id, self._config.speed_multipliers, worst=False,
        )

    def cavalry_vulnerability(self, unit_id: str) -> float:
        """Return cavalry vulnerability (higher = more vulnerable)."""
        return self._get_modifier(
            unit_id, self._config.cavalry_vulnerability, worst=True,
        )

    def artillery_vulnerability(self, unit_id: str) -> float:
        """Return artillery vulnerability (higher = more vulnerable)."""
        return self._get_modifier(
            unit_id, self._config.artillery_vulnerability, worst=True,
        )

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "states": {
                uid: {
                    "unit_id": s.unit_id,
                    "current": int(s.current),
                    "target": int(s.target) if s.target is not None else None,
                    "transition_remaining_s": s.transition_remaining_s,
                }
                for uid, s in self._states.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._states.clear()
        for uid, sdata in state.get("states", {}).items():
            self._states[uid] = UnitFormationState(
                unit_id=sdata["unit_id"],
                current=NapoleonicFormationType(sdata["current"]),
                target=(
                    NapoleonicFormationType(sdata["target"])
                    if sdata["target"] is not None
                    else None
                ),
                transition_remaining_s=sdata["transition_remaining_s"],
            )

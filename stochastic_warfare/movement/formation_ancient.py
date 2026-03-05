"""Ancient/Medieval battalion-level formations.

Seven formation types: PHALANX, SHIELD_WALL, PIKE_BLOCK, WEDGE, SKIRMISH,
TESTUDO, COLUMN.  Mechanically distinct from Napoleonic formations.

Key mechanics:
* TESTUDO — near-immune to archery (0.1 vuln) but very slow and weak melee.
* PHALANX — strong front (cavalry vuln 0.3) but extremely vulnerable to flanking (2.0).
* WEDGE — high melee power (1.5) for breaking formations, poor defense.
* Worst-of-both during transitions (same pattern as Napoleonic).
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


class AncientFormationType(enum.IntEnum):
    """Ancient/Medieval battalion-level formation."""

    PHALANX = 0
    SHIELD_WALL = 1
    PIKE_BLOCK = 2
    WEDGE = 3
    SKIRMISH = 4
    TESTUDO = 5
    COLUMN = 6


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class AncientFormationConfig(BaseModel):
    """Configuration for ancient formation modifiers and transitions."""

    melee_power: dict[int, float] = {
        AncientFormationType.PHALANX: 1.2,
        AncientFormationType.SHIELD_WALL: 0.8,
        AncientFormationType.PIKE_BLOCK: 1.0,
        AncientFormationType.WEDGE: 1.5,
        AncientFormationType.SKIRMISH: 0.3,
        AncientFormationType.TESTUDO: 0.4,
        AncientFormationType.COLUMN: 0.5,
    }

    defense_modifier: dict[int, float] = {
        AncientFormationType.PHALANX: 1.0,
        AncientFormationType.SHIELD_WALL: 1.5,
        AncientFormationType.PIKE_BLOCK: 0.8,
        AncientFormationType.WEDGE: 0.6,
        AncientFormationType.SKIRMISH: 0.4,
        AncientFormationType.TESTUDO: 2.0,
        AncientFormationType.COLUMN: 0.3,
    }

    speed_multipliers: dict[int, float] = {
        AncientFormationType.PHALANX: 0.4,
        AncientFormationType.SHIELD_WALL: 0.3,
        AncientFormationType.PIKE_BLOCK: 0.5,
        AncientFormationType.WEDGE: 0.7,
        AncientFormationType.SKIRMISH: 1.0,
        AncientFormationType.TESTUDO: 0.2,
        AncientFormationType.COLUMN: 0.9,
    }

    archery_vulnerability: dict[int, float] = {
        AncientFormationType.PHALANX: 0.8,
        AncientFormationType.SHIELD_WALL: 0.5,
        AncientFormationType.PIKE_BLOCK: 1.0,
        AncientFormationType.WEDGE: 1.2,
        AncientFormationType.SKIRMISH: 0.6,
        AncientFormationType.TESTUDO: 0.1,
        AncientFormationType.COLUMN: 1.5,
    }

    cavalry_vulnerability: dict[int, float] = {
        AncientFormationType.PHALANX: 0.3,
        AncientFormationType.SHIELD_WALL: 0.4,
        AncientFormationType.PIKE_BLOCK: 0.2,
        AncientFormationType.WEDGE: 0.8,
        AncientFormationType.SKIRMISH: 2.0,
        AncientFormationType.TESTUDO: 0.3,
        AncientFormationType.COLUMN: 1.5,
    }

    flanking_vulnerability: dict[int, float] = {
        AncientFormationType.PHALANX: 2.0,
        AncientFormationType.SHIELD_WALL: 1.5,
        AncientFormationType.PIKE_BLOCK: 2.5,
        AncientFormationType.WEDGE: 0.5,
        AncientFormationType.SKIRMISH: 0.3,
        AncientFormationType.TESTUDO: 1.0,
        AncientFormationType.COLUMN: 2.0,
    }

    transition_times_s: dict[str, float] = {
        "PHALANX_to_SHIELD_WALL": 60.0,
        "PHALANX_to_PIKE_BLOCK": 45.0,
        "PHALANX_to_WEDGE": 90.0,
        "PHALANX_to_SKIRMISH": 60.0,
        "PHALANX_to_TESTUDO": 30.0,
        "PHALANX_to_COLUMN": 60.0,
        "SHIELD_WALL_to_PHALANX": 60.0,
        "SHIELD_WALL_to_PIKE_BLOCK": 60.0,
        "SHIELD_WALL_to_WEDGE": 90.0,
        "SHIELD_WALL_to_SKIRMISH": 45.0,
        "SHIELD_WALL_to_TESTUDO": 30.0,
        "SHIELD_WALL_to_COLUMN": 45.0,
        "PIKE_BLOCK_to_PHALANX": 45.0,
        "PIKE_BLOCK_to_SHIELD_WALL": 60.0,
        "PIKE_BLOCK_to_WEDGE": 90.0,
        "PIKE_BLOCK_to_SKIRMISH": 60.0,
        "PIKE_BLOCK_to_TESTUDO": 60.0,
        "PIKE_BLOCK_to_COLUMN": 45.0,
        "WEDGE_to_PHALANX": 90.0,
        "WEDGE_to_SHIELD_WALL": 90.0,
        "WEDGE_to_PIKE_BLOCK": 90.0,
        "WEDGE_to_SKIRMISH": 60.0,
        "WEDGE_to_TESTUDO": 120.0,
        "WEDGE_to_COLUMN": 60.0,
        "SKIRMISH_to_PHALANX": 60.0,
        "SKIRMISH_to_SHIELD_WALL": 45.0,
        "SKIRMISH_to_PIKE_BLOCK": 60.0,
        "SKIRMISH_to_WEDGE": 60.0,
        "SKIRMISH_to_TESTUDO": 45.0,
        "SKIRMISH_to_COLUMN": 30.0,
        "TESTUDO_to_PHALANX": 30.0,
        "TESTUDO_to_SHIELD_WALL": 30.0,
        "TESTUDO_to_PIKE_BLOCK": 60.0,
        "TESTUDO_to_WEDGE": 120.0,
        "TESTUDO_to_SKIRMISH": 45.0,
        "TESTUDO_to_COLUMN": 45.0,
        "COLUMN_to_PHALANX": 60.0,
        "COLUMN_to_SHIELD_WALL": 45.0,
        "COLUMN_to_PIKE_BLOCK": 45.0,
        "COLUMN_to_WEDGE": 60.0,
        "COLUMN_to_SKIRMISH": 30.0,
        "COLUMN_to_TESTUDO": 45.0,
    }


# ---------------------------------------------------------------------------
# Per-unit state
# ---------------------------------------------------------------------------


@dataclass
class UnitFormationState:
    """Tracks a single unit's ancient formation state."""

    unit_id: str
    current: AncientFormationType = AncientFormationType.PHALANX
    target: AncientFormationType | None = None
    transition_remaining_s: float = 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AncientFormationEngine:
    """Manages ancient/medieval battalion formations and transitions.

    Parameters
    ----------
    config:
        Formation configuration.
    """

    def __init__(self, config: AncientFormationConfig | None = None) -> None:
        self._config = config or AncientFormationConfig()
        self._states: dict[str, UnitFormationState] = {}

    def set_formation(
        self,
        unit_id: str,
        formation: AncientFormationType,
    ) -> None:
        """Set a unit's formation immediately (no transition delay)."""
        self._states[unit_id] = UnitFormationState(
            unit_id=unit_id,
            current=formation,
        )

    def order_formation_change(
        self,
        unit_id: str,
        target: AncientFormationType,
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

        key = f"{AncientFormationType(state.current).name}_to_{AncientFormationType(target).name}"
        time_s = self._config.transition_times_s.get(key, 60.0)
        state.target = target
        state.transition_remaining_s = time_s
        logger.info(
            "Unit %s: %s -> %s (%.0fs)",
            unit_id, AncientFormationType(state.current).name,
            AncientFormationType(target).name, time_s,
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

    def get_formation(self, unit_id: str) -> AncientFormationType:
        """Return the current formation for a unit."""
        state = self._states.get(unit_id)
        if state is None:
            return AncientFormationType.PHALANX
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
            return table.get(int(AncientFormationType.PHALANX), 1.0)

        current_val = table.get(int(state.current), 1.0)
        if state.target is None:
            return current_val

        target_val = table.get(int(state.target), 1.0)
        if worst:
            return max(current_val, target_val)
        return min(current_val, target_val)

    def melee_power(self, unit_id: str) -> float:
        """Return melee power multiplier for a unit's formation."""
        return self._get_modifier(
            unit_id, self._config.melee_power, worst=False,
        )

    def defense_mod(self, unit_id: str) -> float:
        """Return defense modifier for a unit's formation."""
        return self._get_modifier(
            unit_id, self._config.defense_modifier, worst=False,
        )

    def speed_multiplier(self, unit_id: str) -> float:
        """Return the speed multiplier for a unit's formation."""
        return self._get_modifier(
            unit_id, self._config.speed_multipliers, worst=False,
        )

    def archery_vulnerability(self, unit_id: str) -> float:
        """Return archery vulnerability (higher = more vulnerable)."""
        return self._get_modifier(
            unit_id, self._config.archery_vulnerability, worst=True,
        )

    def cavalry_vulnerability(self, unit_id: str) -> float:
        """Return cavalry vulnerability (higher = more vulnerable)."""
        return self._get_modifier(
            unit_id, self._config.cavalry_vulnerability, worst=True,
        )

    def flanking_vulnerability(self, unit_id: str) -> float:
        """Return flanking vulnerability (higher = more vulnerable)."""
        return self._get_modifier(
            unit_id, self._config.flanking_vulnerability, worst=True,
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
                current=AncientFormationType(sdata["current"]),
                target=(
                    AncientFormationType(sdata["target"])
                    if sdata["target"] is not None
                    else None
                ),
                transition_remaining_s=sdata["transition_remaining_s"],
            )

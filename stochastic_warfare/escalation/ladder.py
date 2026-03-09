"""Escalation ladder state machine (0--10 scale).

Phase 24a-1.  Models the desperation-driven escalation process from
conventional operations through ROE relaxation, prohibited methods,
chemical/biological, and nuclear employment.  Transition thresholds
are modulated by commander personality (violation tolerance and
escalation awareness).

Desperation index is a weighted composite of five factors:
casualty ratio, supply deprivation, morale collapse, stalemate
duration, and domestic political pressure.
"""

from __future__ import annotations

import enum
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

from stochastic_warfare.escalation.events import EscalationLevelChangeEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EscalationLevel(enum.IntEnum):
    """Ten-rung escalation ladder from conventional to general nuclear."""

    CONVENTIONAL = 0
    ROE_RELAXATION = 1
    COLLATERAL_ACCEPTANCE = 2
    ROE_VIOLATIONS = 3
    PROHIBITED_METHODS = 4
    CHEMICAL = 5
    BIOLOGICAL = 6
    TACTICAL_NUCLEAR = 7
    THEATER_NUCLEAR = 8
    STRATEGIC_NUCLEAR_LIMITED = 9
    STRATEGIC_NUCLEAR_GENERAL = 10


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class DesperationWeights(BaseModel):
    """Weights for the five desperation factors (must sum to ~1.0).

    Source: Kahn, "On Escalation" (1965), Ch. 2 — casualties and supply
    deprivation are the primary drivers; political pressure and stalemate
    are secondary but accumulate over time.  Schelling, "Arms and
    Influence" (1966), Ch. 3 — stalemate duration as escalation catalyst.
    """

    casualty: float = 0.30
    supply: float = 0.20
    morale: float = 0.20
    stalemate: float = 0.15
    political: float = 0.15
    stalemate_normalize_s: float = 259200.0  # 72 hours


class EscalationLadderConfig(BaseModel):
    """Configuration for the escalation ladder.

    Source: Kahn, "On Escalation" (1965) — 44-rung ladder compressed to
    11 levels.  Entry thresholds spaced to model increasing reluctance at
    higher levels.  Hysteresis 0.7 prevents oscillation (Schelling:
    commitment mechanisms make de-escalation harder than escalation).
    """

    entry_thresholds: list[float] = [
        0.0, 0.15, 0.25, 0.35, 0.50,
        0.60, 0.70, 0.80, 0.85, 0.90, 0.95,
    ]
    """Desperation threshold to enter each escalation level."""

    hysteresis_factor: float = 0.7
    """Exit threshold = entry threshold * hysteresis_factor."""

    desperation_weights: DesperationWeights = DesperationWeights()
    """Weights for desperation index computation."""

    cooldown_s: float = 3600.0
    """Minimum seconds between escalation transitions."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class EscalationLadder:
    """Escalation state machine tracking per-side escalation level.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``EscalationLevelChangeEvent`` on transitions.
    rng : np.random.Generator
        PRNG stream (reserved for future stochastic extensions).
    config : EscalationLadderConfig | None
        Configuration.  Defaults to standard thresholds.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: EscalationLadderConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or EscalationLadderConfig()
        self._levels: dict[str, EscalationLevel] = {}
        self._last_transition_time: dict[str, datetime | None] = {}

    # -- Public API ---------------------------------------------------------

    def compute_desperation(
        self,
        side: str,
        casualties_sustained: float,
        initial_strength: float,
        supply_state: float,
        avg_morale: float,
        stalemate_duration_s: float,
        domestic_pressure: float,
    ) -> float:
        """Compute composite desperation index in [0, 1].

        Parameters
        ----------
        side : str
            Side identifier (unused in calculation, included for logging).
        casualties_sustained : float
            Total casualties suffered.
        initial_strength : float
            Starting force strength.
        supply_state : float
            Current supply state in [0, 1] (1.0 = fully supplied).
        avg_morale : float
            Average morale in [0, 1] (1.0 = perfect morale).
        stalemate_duration_s : float
            Duration of stalemate in seconds.
        domestic_pressure : float
            Domestic political pressure in [0, 1].

        Returns
        -------
        float
            Composite desperation index clamped to [0, 1].
        """
        w = self._config.desperation_weights

        casualty_factor = min(1.0, max(0.0,
            casualties_sustained / max(initial_strength, 1)
        ))
        supply_factor = min(1.0, max(0.0, 1.0 - supply_state))
        morale_factor = min(1.0, max(0.0, 1.0 - avg_morale))
        stalemate_factor = min(1.0, max(0.0,
            stalemate_duration_s / w.stalemate_normalize_s
        ))
        political_factor = min(1.0, max(0.0, domestic_pressure))

        desperation = (
            w.casualty * casualty_factor
            + w.supply * supply_factor
            + w.morale * morale_factor
            + w.stalemate * stalemate_factor
            + w.political * political_factor
        )
        result = min(1.0, max(0.0, desperation))

        logger.debug(
            "Desperation[%s]: cas=%.3f sup=%.3f mor=%.3f stl=%.3f pol=%.3f => %.3f",
            side, casualty_factor, supply_factor, morale_factor,
            stalemate_factor, political_factor, result,
        )
        return result

    def evaluate_transition(
        self,
        side: str,
        desperation: float,
        commander_violation_tolerance: float,
        commander_escalation_awareness: float,
        timestamp: datetime,
    ) -> EscalationLevel | None:
        """Evaluate whether the escalation level should change.

        Parameters
        ----------
        side : str
            Side identifier.
        desperation : float
            Current desperation index [0, 1].
        commander_violation_tolerance : float
            Commander's willingness to violate norms [0, 1].
            Higher values lower entry thresholds.
        commander_escalation_awareness : float
            Commander's awareness of escalation consequences [0, 1].
            Higher values inhibit escalation.
        timestamp : datetime
            Current simulation time.

        Returns
        -------
        EscalationLevel | None
            New level if transition occurred, None otherwise.
        """
        current = self.get_level(side)
        last_time = self._last_transition_time.get(side)

        # Enforce cooldown
        if last_time is not None:
            elapsed = (timestamp - last_time).total_seconds()
            if elapsed < self._config.cooldown_s:
                return None

        # --- Check escalation (scan from highest down) ---
        for level_val in range(len(EscalationLevel) - 1, current.value, -1):
            level = EscalationLevel(level_val)
            entry_threshold = (
                self._config.entry_thresholds[level.value]
                / (1.0 + commander_violation_tolerance)
            )
            consequence_cost = level.value * 0.1 * commander_escalation_awareness
            if desperation - consequence_cost > entry_threshold:
                self._set_level_internal(side, level, desperation, timestamp)
                return level

        # --- Check de-escalation ---
        if current.value > 0:
            exit_threshold = (
                self._config.entry_thresholds[current.value]
                * self._config.hysteresis_factor
            )
            if desperation < exit_threshold:
                new_level = EscalationLevel(current.value - 1)
                self._set_level_internal(side, new_level, desperation, timestamp)
                return new_level

        return None

    def get_level(self, side: str) -> EscalationLevel:
        """Return current escalation level for *side* (default CONVENTIONAL)."""
        return self._levels.get(side, EscalationLevel.CONVENTIONAL)

    def set_level(self, side: str, level: EscalationLevel) -> None:
        """Directly override escalation level for *side*."""
        self._levels[side] = level

    def is_authorized(self, level: EscalationLevel, side: str) -> bool:
        """Return True if *side*'s current level >= *level*."""
        return self.get_level(side) >= level

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        return {
            "levels": {s: lv.value for s, lv in self._levels.items()},
            "last_transition_time": {
                s: t.isoformat() if t else None
                for s, t in self._last_transition_time.items()
            },
        }

    def set_state(self, state: dict) -> None:
        self._levels = {
            s: EscalationLevel(v) for s, v in state.get("levels", {}).items()
        }
        self._last_transition_time = {}
        for s, t in state.get("last_transition_time", {}).items():
            if t is not None:
                self._last_transition_time[s] = datetime.fromisoformat(t)
            else:
                self._last_transition_time[s] = None

    # -- Internal -----------------------------------------------------------

    def _set_level_internal(
        self,
        side: str,
        new_level: EscalationLevel,
        desperation: float,
        timestamp: datetime,
    ) -> None:
        """Set level and publish event."""
        old_level = self.get_level(side)
        self._levels[side] = new_level
        self._last_transition_time[side] = timestamp

        self._event_bus.publish(EscalationLevelChangeEvent(
            timestamp=timestamp,
            source=ModuleId.ESCALATION,
            side=side,
            old_level=old_level.value,
            new_level=new_level.value,
            desperation_index=desperation,
        ))
        logger.info(
            "Escalation[%s]: %s -> %s (desperation=%.3f)",
            side, old_level.name, new_level.name, desperation,
        )

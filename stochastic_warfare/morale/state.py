"""Markov-chain morale state machine.

Models unit morale as a 5-state Markov chain with transition probabilities
driven by casualty rate, suppression, leadership, cohesion, and force ratio.
SURRENDERED is an absorbing state.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.morale.events import MoraleStateChangeEvent

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Morale state enum
# ---------------------------------------------------------------------------


class MoraleState(enum.IntEnum):
    """Discrete morale levels from best to worst."""

    STEADY = 0
    SHAKEN = 1
    BROKEN = 2
    ROUTED = 3
    SURRENDERED = 4


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class MoraleConfig(BaseModel):
    """Configurable parameters for morale state transitions."""

    base_degrade_rate: float = 0.05
    """Base probability of degrading one step per check."""

    base_recover_rate: float = 0.10
    """Base probability of recovering one step per check."""

    casualty_weight: float = 2.0
    """Multiplier on casualty_rate contribution to degradation."""

    suppression_weight: float = 1.5
    """Multiplier on suppression_level contribution to degradation."""

    leadership_weight: float = 0.3
    """Recovery bonus when leadership is present."""

    cohesion_weight: float = 0.4
    """Recovery bonus from unit cohesion."""

    force_ratio_weight: float = 0.5
    """Degrade bonus when outnumbered (force_ratio < 1)."""

    transition_cooldown_s: float = 30.0
    """Minimum seconds between morale state transitions."""

    use_continuous_time: bool = False
    """When True, interpret rates as continuous-time Markov chain rates
    and scale by dt, making transitions tick-rate-independent."""


# ---------------------------------------------------------------------------
# Per-unit morale tracking
# ---------------------------------------------------------------------------


@dataclass
class UnitMoraleState:
    """Tracks the morale state of a single unit."""

    current_state: MoraleState = MoraleState.STEADY
    transition_cooldown_s: float = 0.0
    last_transition_time: float = -1e9

    def get_state(self) -> dict[str, Any]:
        return {
            "current_state": int(self.current_state),
            "transition_cooldown_s": self.transition_cooldown_s,
            "last_transition_time": self.last_transition_time,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.current_state = MoraleState(state["current_state"])
        self.transition_cooldown_s = state["transition_cooldown_s"]
        self.last_transition_time = state["last_transition_time"]


# ---------------------------------------------------------------------------
# Morale state machine
# ---------------------------------------------------------------------------

# Effects multipliers per morale state: accuracy, speed, initiative
_MORALE_EFFECTS: dict[MoraleState, dict[str, float]] = {
    MoraleState.STEADY: {"accuracy_mult": 1.0, "speed_mult": 1.0, "initiative_mult": 1.0},
    MoraleState.SHAKEN: {"accuracy_mult": 0.7, "speed_mult": 0.7, "initiative_mult": 0.6},
    MoraleState.BROKEN: {"accuracy_mult": 0.3, "speed_mult": 0.3, "initiative_mult": 0.2},
    MoraleState.ROUTED: {"accuracy_mult": 0.1, "speed_mult": 0.1, "initiative_mult": 0.0},
    MoraleState.SURRENDERED: {"accuracy_mult": 0.0, "speed_mult": 0.0, "initiative_mult": 0.0},
}


class MoraleStateMachine:
    """Markov-chain morale state transitions.

    Parameters
    ----------
    event_bus:
        EventBus for publishing morale state changes.
    rng:
        A ``numpy.random.Generator``.
    config:
        Morale configuration parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: MoraleConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or MoraleConfig()
        self._unit_states: dict[str, UnitMoraleState] = {}
        # Last-result cache for compute_transition_matrix (same-side units
        # share identical parameters within a tick)
        self._cached_matrix_key: tuple[float, ...] | None = None
        self._cached_matrix: np.ndarray | None = None

    def _get_unit_state(self, unit_id: str) -> UnitMoraleState:
        """Get or create morale state for a unit."""
        if unit_id not in self._unit_states:
            self._unit_states[unit_id] = UnitMoraleState()
        return self._unit_states[unit_id]

    def compute_transition_matrix(
        self,
        casualty_rate: float,
        suppression_level: float,
        leadership_present: bool,
        cohesion: float,
        force_ratio: float,
        cbrn_stress: float = 0.0,
    ) -> np.ndarray:
        """Build a 5x5 morale transition matrix.

        Parameters
        ----------
        casualty_rate:
            Fraction of casualties (0.0–1.0).
        suppression_level:
            Level of suppression (0.0–1.0).
        leadership_present:
            Whether a leader is present with the unit.
        cohesion:
            Unit cohesion factor (0.0–1.0).
        force_ratio:
            Friendly-to-enemy force ratio (>1 = advantage).
        cbrn_stress:
            Additional degradation pressure from CBRN environment (0.0–1.0).

        Returns
        -------
        np.ndarray
            5x5 row-stochastic transition matrix.
        """
        cfg = self._config
        key = (casualty_rate, suppression_level, float(leadership_present), cohesion, force_ratio, cbrn_stress)
        if self._cached_matrix_key == key and self._cached_matrix is not None:
            return self._cached_matrix
        n = len(MoraleState)
        matrix = np.zeros((n, n), dtype=np.float64)

        # Degradation pressure
        degrade = cfg.base_degrade_rate
        degrade += cfg.casualty_weight * casualty_rate
        degrade += cfg.suppression_weight * suppression_level
        if force_ratio < 1.0:
            degrade += cfg.force_ratio_weight * (1.0 - force_ratio)
        degrade += cbrn_stress  # CBRN environmental stress
        degrade = np.clip(degrade, 0.0, 0.8)

        # Recovery pressure
        recover = cfg.base_recover_rate
        if leadership_present:
            recover += cfg.leadership_weight
        recover += cfg.cohesion_weight * cohesion
        if force_ratio > 1.0:
            recover += cfg.force_ratio_weight * min(force_ratio - 1.0, 1.0) * 0.5
        recover = np.clip(recover, 0.0, 0.8)

        for i in range(n):
            state = MoraleState(i)

            if state == MoraleState.SURRENDERED:
                # Absorbing state — never leaves
                matrix[i, i] = 1.0
                continue

            # Probability of degrading one step
            p_down = degrade * (1.0 + 0.2 * i)  # Worse states degrade faster
            p_down = min(p_down, 0.9)

            # Probability of recovering one step
            p_up = recover * max(0.1, 1.0 - 0.3 * i)  # Worse states recover harder
            if i == 0:
                p_up = 0.0  # Can't improve from STEADY

            # Clamp total transition probability
            total_trans = p_down + p_up
            if total_trans > 0.95:
                scale = 0.95 / total_trans
                p_down *= scale
                p_up *= scale

            # Fill row
            if i < n - 1:
                matrix[i, i + 1] = p_down
            if i > 0:
                matrix[i, i - 1] = p_up
            matrix[i, i] = 1.0 - p_down - p_up

        self._cached_matrix_key = key
        self._cached_matrix = matrix
        return matrix

    def compute_continuous_transition_probs(
        self,
        casualty_rate: float,
        suppression_level: float,
        leadership_present: bool,
        cohesion: float,
        force_ratio: float,
        dt: float,
    ) -> np.ndarray:
        """Build a 5x5 transition matrix using continuous-time rates.

        Uses ``P(transition) = 1 - exp(-λ·dt)`` so that transitions are
        tick-rate-independent.  With ``dt=1.0`` and moderate rates, this
        closely approximates the discrete matrix but scales properly for
        any tick duration.

        Parameters
        ----------
        casualty_rate, suppression_level, leadership_present, cohesion, force_ratio:
            Same semantics as :meth:`compute_transition_matrix`.
        dt:
            Time step duration in seconds.

        Returns
        -------
        np.ndarray
            5x5 row-stochastic transition matrix.
        """
        cfg = self._config

        # Degradation rate (per second)
        degrade_rate = cfg.base_degrade_rate
        degrade_rate += cfg.casualty_weight * casualty_rate
        degrade_rate += cfg.suppression_weight * suppression_level
        if force_ratio < 1.0:
            degrade_rate += cfg.force_ratio_weight * (1.0 - force_ratio)
        degrade_rate = min(degrade_rate, 2.0)

        # Recovery rate (per second)
        recover_rate = cfg.base_recover_rate
        if leadership_present:
            recover_rate += cfg.leadership_weight
        recover_rate += cfg.cohesion_weight * cohesion
        if force_ratio > 1.0:
            recover_rate += cfg.force_ratio_weight * min(force_ratio - 1.0, 1.0) * 0.5
        recover_rate = min(recover_rate, 2.0)

        n = len(MoraleState)
        matrix = np.zeros((n, n), dtype=np.float64)

        for i in range(n):
            state = MoraleState(i)

            if state == MoraleState.SURRENDERED:
                matrix[i, i] = 1.0
                continue

            # State-dependent rate scaling (same shape as discrete version)
            lambda_down = degrade_rate * (1.0 + 0.2 * i)
            lambda_up = recover_rate * max(0.1, 1.0 - 0.3 * i) if i > 0 else 0.0

            # Convert rate to probability over dt
            p_down = 1.0 - np.exp(-lambda_down * dt)
            p_up = 1.0 - np.exp(-lambda_up * dt)

            # Clamp total transition probability
            total_trans = p_down + p_up
            if total_trans > 0.95:
                scale = 0.95 / total_trans
                p_down *= scale
                p_up *= scale

            if i < n - 1:
                matrix[i, i + 1] = p_down
            if i > 0:
                matrix[i, i - 1] = p_up
            matrix[i, i] = 1.0 - p_down - p_up

        return matrix

    def check_transition(
        self,
        unit_id: str,
        casualty_rate: float,
        suppression_level: float,
        leadership_present: bool,
        cohesion: float,
        force_ratio: float,
        timestamp: datetime | None = None,
        dt: float = 1.0,
        current_time_s: float = 0.0,
        cbrn_stress: float = 0.0,
    ) -> MoraleState:
        """Check for a morale state transition.

        Parameters
        ----------
        timestamp:
            Simulation clock time for the event.  Falls back to
            ``datetime.now(UTC)`` if not provided (legacy callers).
        dt:
            Tick duration in seconds.  Only used when
            ``config.use_continuous_time`` is True.
        current_time_s:
            Current simulation time in seconds, for cooldown enforcement.
        cbrn_stress:
            Additional degradation pressure from CBRN environment (0.0–1.0).

        Returns the (possibly new) morale state.
        """
        ums = self._get_unit_state(unit_id)
        old_state = ums.current_state

        if old_state == MoraleState.SURRENDERED:
            return old_state

        # Enforce transition cooldown
        elapsed_since_last = current_time_s - ums.last_transition_time
        if elapsed_since_last < self._config.transition_cooldown_s:
            return old_state

        if self._config.use_continuous_time:
            matrix = self.compute_continuous_transition_probs(
                casualty_rate, suppression_level, leadership_present,
                cohesion, force_ratio, dt,
            )
        else:
            matrix = self.compute_transition_matrix(
                casualty_rate, suppression_level, leadership_present, cohesion, force_ratio,
                cbrn_stress=cbrn_stress,
            )

        row = matrix[int(old_state)]
        roll = self._rng.random()

        cumulative = 0.0
        new_state = old_state
        for j in range(len(MoraleState)):
            cumulative += row[j]
            if roll < cumulative:
                new_state = MoraleState(j)
                break

        if new_state != old_state:
            ums.current_state = new_state
            ums.last_transition_time = current_time_s
            logger.debug(
                "Unit %s morale: %s -> %s", unit_id, old_state.name, new_state.name,
            )
            ts = timestamp if timestamp is not None else datetime.now(tz=timezone.utc)
            self._event_bus.publish(MoraleStateChangeEvent(
                timestamp=ts,
                source=ModuleId.MORALE,
                unit_id=unit_id,
                old_state=int(old_state),
                new_state=int(new_state),
            ))

        return new_state

    @staticmethod
    def apply_morale_effects(state: MoraleState) -> dict[str, float]:
        """Return effectiveness multipliers for the given morale state."""
        return _MORALE_EFFECTS[state]

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "unit_states": {
                uid: ums.get_state()
                for uid, ums in sorted(self._unit_states.items())
            },
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._unit_states.clear()
        for uid, ums_state in state["unit_states"].items():
            ums = UnitMoraleState()
            ums.set_state(ums_state)
            self._unit_states[uid] = ums

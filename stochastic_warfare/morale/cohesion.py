"""Unit cohesion modeling.

Cohesion represents the internal binding force of a unit — its willingness to
fight as a coherent whole.  Driven by personnel strength, training, leadership,
proximity to friendly forces, and combat history.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class CohesionConfig(BaseModel):
    """Configurable parameters for cohesion computation."""

    base_cohesion: float = 0.5
    """Baseline cohesion when all other factors are neutral."""

    personnel_weight: float = 0.25
    """Weight of personnel strength (0.0–1.0) in cohesion."""

    training_weight: float = 0.15
    """Weight of training level (0.0–1.0) in cohesion."""

    friendly_bonus_per_unit: float = 0.03
    """Cohesion bonus per nearby friendly unit (up to 5)."""

    leadership_bonus: float = 0.10
    """Cohesion bonus when a leader is present."""

    isolation_penalty: float = 0.20
    """Cohesion penalty when the unit is isolated."""

    leader_loss_cohesion_drop: float = 0.15
    """Base cohesion drop when a leader is lost."""

    leader_loss_subordinate_factor: float = 0.02
    """Additional drop per subordinate when a leader is lost."""

    combat_hours_bonus_rate: float = 0.005
    """Cohesion bonus per hour of combat experience (diminishing)."""

    prior_rout_penalty: float = 0.05
    """Cohesion penalty per prior rout."""


# ---------------------------------------------------------------------------
# Cohesion engine
# ---------------------------------------------------------------------------


class CohesionEngine:
    """Computes unit cohesion from multiple factors.

    Parameters
    ----------
    rng:
        A ``numpy.random.Generator`` for stochastic noise.
    config:
        Cohesion configuration parameters.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        config: CohesionConfig | None = None,
    ) -> None:
        self._rng = rng
        self._config = config or CohesionConfig()

    def compute_cohesion(
        self,
        personnel_strength: float,
        training_level: float,
        nearby_friendly_count: int,
        leader_present: bool,
        isolated: bool,
    ) -> float:
        """Compute unit cohesion from situational factors.

        Parameters
        ----------
        personnel_strength:
            Fraction of full-strength personnel remaining (0.0–1.0).
        training_level:
            Training quality (0.0–1.0).
        nearby_friendly_count:
            Number of friendly units within mutual support range.
        leader_present:
            Whether the unit's leader is present and effective.
        isolated:
            Whether the unit is cut off from higher echelons.

        Returns
        -------
        float
            Cohesion value clamped to [0.0, 1.0].
        """
        cfg = self._config
        cohesion = cfg.base_cohesion

        # Personnel strength contribution
        cohesion += cfg.personnel_weight * personnel_strength

        # Training contribution
        cohesion += cfg.training_weight * training_level

        # Nearby friendlies (capped at 5 for diminishing returns)
        friendly_cap = min(nearby_friendly_count, 5)
        cohesion += cfg.friendly_bonus_per_unit * friendly_cap

        # Leadership
        if leader_present:
            cohesion += cfg.leadership_bonus

        # Isolation
        if isolated:
            cohesion -= cfg.isolation_penalty

        # Small stochastic noise
        noise = self._rng.normal(0.0, 0.02)
        cohesion += noise

        return float(np.clip(cohesion, 0.0, 1.0))

    def leadership_cascade(
        self,
        unit_id: str,
        leader_lost: bool,
        subordinate_count: int,
    ) -> float:
        """Compute cohesion drop when a leader is lost.

        Parameters
        ----------
        unit_id:
            Identifier for the affected unit (for logging).
        leader_lost:
            Whether the leader was actually lost (killed/captured/incapacitated).
        subordinate_count:
            Number of subordinates affected.

        Returns
        -------
        float
            Magnitude of cohesion drop (positive = bad), or 0.0 if no leader lost.
        """
        if not leader_lost:
            return 0.0

        cfg = self._config
        drop = cfg.leader_loss_cohesion_drop
        drop += cfg.leader_loss_subordinate_factor * subordinate_count

        # Stochastic variation
        noise = self._rng.normal(0.0, 0.02)
        drop += noise
        drop = max(drop, 0.0)

        logger.debug(
            "Leader lost for unit %s — cohesion drop %.3f (subordinates=%d)",
            unit_id, drop, subordinate_count,
        )
        return float(drop)

    def unit_history_modifier(
        self,
        combat_hours: float,
        prior_routs: int,
    ) -> float:
        """Compute a cohesion modifier from unit combat history.

        Parameters
        ----------
        combat_hours:
            Total hours of combat experience.
        prior_routs:
            Number of times this unit has previously routed.

        Returns
        -------
        float
            Modifier to add to cohesion (can be negative).
        """
        cfg = self._config

        # Combat experience bonus with diminishing returns
        experience_bonus = cfg.combat_hours_bonus_rate * combat_hours
        experience_bonus = experience_bonus / (1.0 + experience_bonus)  # saturates at 1.0

        # Prior rout penalty
        rout_penalty = cfg.prior_rout_penalty * prior_routs

        return float(experience_bonus - rout_penalty)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]

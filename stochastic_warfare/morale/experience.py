"""Experience progression and combat effectiveness.

Models how units gain experience through combat and how experience translates
into combat effectiveness modifiers.  Uses a learning curve with diminishing
returns.
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


class ExperienceConfig(BaseModel):
    """Configurable parameters for experience progression."""

    learning_rate: float = 0.02
    """Base experience gained per combat hour."""

    diminishing_returns_factor: float = 0.5
    """Controls how quickly experience gains diminish (higher = faster saturation)."""

    max_combat_modifier: float = 1.5
    """Maximum combat effectiveness modifier from experience."""

    min_combat_modifier: float = 0.5
    """Minimum combat effectiveness modifier (green troops)."""

    training_synergy: float = 0.3
    """How much training level amplifies experience benefits."""

    noise_sigma: float = 0.005
    """Stochastic noise in experience gain."""


# ---------------------------------------------------------------------------
# Experience engine
# ---------------------------------------------------------------------------


class ExperienceEngine:
    """Models experience gain and its effect on combat performance.

    Parameters
    ----------
    rng:
        A ``numpy.random.Generator`` for stochastic noise.
    config:
        Experience configuration parameters.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        config: ExperienceConfig | None = None,
    ) -> None:
        self._rng = rng
        self._config = config or ExperienceConfig()

    def update_experience(
        self,
        current_experience: float,
        combat_hours: float,
        rng: np.random.Generator | None = None,
    ) -> float:
        """Update experience based on combat exposure.

        Uses a learning curve with diminishing returns:
        ``gain = learning_rate * combat_hours / (1 + diminishing_returns * current_experience)``

        Parameters
        ----------
        current_experience:
            Current cumulative experience value (>= 0).
        combat_hours:
            Hours of combat exposure in the current period.
        rng:
            Optional override RNG (if None, uses engine's RNG).

        Returns
        -------
        float
            Updated experience value (always >= 0).
        """
        cfg = self._config
        active_rng = rng or self._rng

        # Learning curve: diminishing returns as experience grows
        gain = cfg.learning_rate * combat_hours / (1.0 + cfg.diminishing_returns_factor * current_experience)

        # Stochastic noise in learning
        noise = active_rng.normal(0.0, cfg.noise_sigma * combat_hours)

        new_experience = current_experience + gain + noise
        return float(max(new_experience, 0.0))

    def compute_combat_modifier(
        self,
        experience: float,
        training_level: float,
    ) -> float:
        """Compute combat effectiveness multiplier from experience and training.

        Parameters
        ----------
        experience:
            Cumulative experience value (>= 0).
        training_level:
            Training quality (0.0–1.0).

        Returns
        -------
        float
            Effectiveness multiplier clamped to [min_combat_modifier, max_combat_modifier].
        """
        cfg = self._config

        # Base modifier: starts at min, asymptotically approaches max
        range_ = cfg.max_combat_modifier - cfg.min_combat_modifier
        # Saturating curve: modifier = min + range * (1 - exp(-k * experience))
        k = 0.1  # Saturation rate
        base_mod = cfg.min_combat_modifier + range_ * (1.0 - np.exp(-k * experience))

        # Training synergy: good training amplifies experience benefits
        synergy = 1.0 + cfg.training_synergy * training_level
        modifier = cfg.min_combat_modifier + (base_mod - cfg.min_combat_modifier) * synergy

        return float(np.clip(modifier, cfg.min_combat_modifier, cfg.max_combat_modifier))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]

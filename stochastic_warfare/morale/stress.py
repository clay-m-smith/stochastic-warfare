"""Combat stress with random walk and sleep deprivation.

Stress accumulates as a biased random walk driven by combat intensity and
environmental conditions.  Sleep deprivation adds exponential performance
degradation beyond a configurable threshold.
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


class StressConfig(BaseModel):
    """Configurable parameters for stress accumulation."""

    combat_stress_rate: float = 0.01
    """Stress accumulation per second at full combat intensity."""

    rest_recovery_rate: float = 0.005
    """Stress recovery per second when not in combat."""

    sleep_dep_threshold_hours: float = 24.0
    """Hours awake before sleep deprivation effects begin."""

    sleep_dep_decay_rate: float = 0.05
    """Exponential decay rate per hour beyond threshold."""

    noise_sigma: float = 0.002
    """Standard deviation of the random walk noise per second."""

    environmental_stress_weight: float = 0.3
    """Weight of environmental stress contribution."""

    max_stress: float = 1.0
    """Maximum stress level."""

    min_stress: float = 0.0
    """Minimum stress level."""


# ---------------------------------------------------------------------------
# Stress engine
# ---------------------------------------------------------------------------


class StressEngine:
    """Models combat stress as a biased random walk.

    Parameters
    ----------
    rng:
        A ``numpy.random.Generator`` for stochastic noise.
    config:
        Stress configuration parameters.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        config: StressConfig | None = None,
    ) -> None:
        self._rng = rng
        self._config = config or StressConfig()

    def update_stress(
        self,
        current_stress: float,
        dt: float,
        combat_intensity: float,
        sleep_hours: float,
        environmental_stress: float = 0.0,
    ) -> float:
        """Update stress level via biased random walk.

        Parameters
        ----------
        current_stress:
            Current stress level (0.0–1.0).
        dt:
            Time step in seconds.
        combat_intensity:
            Current combat intensity (0.0–1.0).
        sleep_hours:
            Hours of sleep in the last 24 hours.
        environmental_stress:
            Environmental stress factor (0.0–1.0), e.g. extreme weather.

        Returns
        -------
        float
            Updated stress level clamped to [0.0, 1.0].
        """
        cfg = self._config

        # Drift term: positive when in combat, negative when resting
        if combat_intensity > 0.0:
            drift = cfg.combat_stress_rate * combat_intensity
        else:
            drift = -cfg.rest_recovery_rate

        # Environmental contribution
        drift += cfg.environmental_stress_weight * environmental_stress * cfg.combat_stress_rate

        # Sleep deprivation contribution
        hours_awake = max(0.0, 24.0 - sleep_hours)
        if hours_awake > cfg.sleep_dep_threshold_hours:
            excess = hours_awake - cfg.sleep_dep_threshold_hours
            sleep_stress = cfg.combat_stress_rate * 0.5 * (1.0 - np.exp(-cfg.sleep_dep_decay_rate * excess))
            drift += sleep_stress

        # Random walk noise (scaled by sqrt(dt) for proper diffusion)
        noise = self._rng.normal(0.0, cfg.noise_sigma * np.sqrt(dt))

        # Apply update
        new_stress = current_stress + drift * dt + noise

        return float(np.clip(new_stress, cfg.min_stress, cfg.max_stress))

    def sleep_deprivation_effect(self, hours_awake: float) -> float:
        """Compute performance degradation from sleep deprivation.

        Parameters
        ----------
        hours_awake:
            Hours continuously awake.

        Returns
        -------
        float
            Effectiveness multiplier in [0.0, 1.0] where 1.0 = no effect.
        """
        cfg = self._config

        if hours_awake <= cfg.sleep_dep_threshold_hours:
            return 1.0

        excess = hours_awake - cfg.sleep_dep_threshold_hours
        effect = np.exp(-cfg.sleep_dep_decay_rate * excess)

        return float(np.clip(effect, 0.0, 1.0))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]

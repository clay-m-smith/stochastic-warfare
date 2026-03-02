"""Psychological operations and surrender inducement.

Models PSYOP effects on enemy morale, surrender probability computation,
and civilian population reaction to military operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class PsychologyConfig(BaseModel):
    """Configurable parameters for psychological operations."""

    psyop_base_effect: float = 0.10
    """Base morale degradation from a PSYOP event."""

    psyop_visibility_weight: float = 0.5
    """How much visibility (0–1) amplifies PSYOP effects."""

    surrender_force_ratio_threshold: float = 3.0
    """Force ratio above which surrender becomes likely."""

    surrender_base_probability: float = 0.05
    """Base surrender probability for a BROKEN unit."""

    surrender_isolation_weight: float = 0.3
    """How much isolation increases surrender probability."""

    civilian_hostility_threshold: float = 0.7
    """Military intensity above which civilians become hostile."""

    civilian_cooperation_threshold: float = 0.3
    """Military intensity below which civilians may cooperate."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PsyopResult:
    """Outcome of a PSYOP application."""

    morale_degradation: float
    """Amount of morale degradation caused (0.0–1.0)."""

    effective: bool
    """Whether the PSYOP had meaningful effect."""

    description: str
    """Human-readable summary of the outcome."""

    def get_state(self) -> dict[str, Any]:
        return {
            "morale_degradation": self.morale_degradation,
            "effective": self.effective,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Psychology engine
# ---------------------------------------------------------------------------


class PsychologyEngine:
    """Models psychological warfare and surrender mechanics.

    Parameters
    ----------
    event_bus:
        EventBus for publishing psychology-related events.
    rng:
        A ``numpy.random.Generator``.
    config:
        Psychology configuration parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: PsychologyConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or PsychologyConfig()

    def apply_psyop(
        self,
        target_morale_state: int,
        psyop_intensity: float,
        visibility: float,
    ) -> PsyopResult:
        """Apply a psychological operation against a target.

        Parameters
        ----------
        target_morale_state:
            Current morale state of the target (0=STEADY .. 4=SURRENDERED).
        psyop_intensity:
            Intensity of the PSYOP campaign (0.0–1.0).
        visibility:
            How visible the PSYOP is to the target (0.0–1.0).

        Returns
        -------
        PsyopResult
            Outcome including morale degradation amount.
        """
        cfg = self._config

        # Already surrendered — no further effect
        if target_morale_state >= 4:
            return PsyopResult(
                morale_degradation=0.0,
                effective=False,
                description="Target already surrendered",
            )

        # Base effect scaled by intensity
        effect = cfg.psyop_base_effect * psyop_intensity

        # Visibility amplification
        effect *= (1.0 + cfg.psyop_visibility_weight * visibility)

        # Targets in worse morale states are more susceptible
        susceptibility = 1.0 + 0.3 * target_morale_state
        effect *= susceptibility

        # Stochastic variation
        noise = self._rng.normal(0.0, 0.02)
        effect += noise
        effect = float(np.clip(effect, 0.0, 1.0))

        effective = effect > 0.02
        if effective:
            logger.debug(
                "PSYOP applied: degradation=%.3f, morale_state=%d, intensity=%.2f",
                effect, target_morale_state, psyop_intensity,
            )

        return PsyopResult(
            morale_degradation=effect,
            effective=effective,
            description=f"PSYOP degradation {effect:.3f} (intensity={psyop_intensity:.2f})",
        )

    def surrender_inducement(
        self,
        morale_state_int: int,
        force_ratio: float,
        isolation_factor: float,
    ) -> float:
        """Compute probability that a unit surrenders.

        Parameters
        ----------
        morale_state_int:
            Current morale state (0=STEADY .. 4=SURRENDERED).
        force_ratio:
            Enemy-to-friendly force ratio (higher = more enemies).
        isolation_factor:
            Degree of isolation (0.0 = connected, 1.0 = fully isolated).

        Returns
        -------
        float
            Surrender probability in [0.0, 1.0].
        """
        cfg = self._config

        # Only BROKEN (2) or ROUTED (3) units consider surrender
        if morale_state_int < 2:
            return 0.0

        # Already surrendered
        if morale_state_int >= 4:
            return 1.0

        # Base probability depends on morale state
        prob = cfg.surrender_base_probability
        if morale_state_int == 3:  # ROUTED
            prob *= 3.0

        # Force ratio effect: high enemy ratio increases surrender chance
        if force_ratio > cfg.surrender_force_ratio_threshold:
            excess = force_ratio - cfg.surrender_force_ratio_threshold
            prob += 0.1 * excess

        # Isolation effect
        prob += cfg.surrender_isolation_weight * isolation_factor

        return float(np.clip(prob, 0.0, 1.0))

    def compute_civilian_reaction(
        self,
        population_disposition: float,
        military_intensity: float,
    ) -> str:
        """Determine civilian population reaction to military operations.

        Parameters
        ----------
        population_disposition:
            How favorably the population views the operating force
            (0.0 = hostile, 0.5 = neutral, 1.0 = supportive).
        military_intensity:
            Level of military activity in the area (0.0–1.0).

        Returns
        -------
        str
            One of "cooperative", "neutral", "hostile".
        """
        cfg = self._config

        # High intensity tends to make population hostile regardless of disposition
        effective_disposition = population_disposition - 0.5 * military_intensity

        # Stochastic variation
        noise = self._rng.normal(0.0, 0.05)
        effective_disposition += noise

        if military_intensity > cfg.civilian_hostility_threshold:
            effective_disposition -= 0.2

        if military_intensity < cfg.civilian_cooperation_threshold:
            effective_disposition += 0.1

        if effective_disposition > 0.6:
            return "cooperative"
        elif effective_disposition < 0.3:
            return "hostile"
        else:
            return "neutral"

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]

"""MOPP levels and protection engine.

Maps MOPP (Mission Oriented Protective Posture) levels to speed, detection,
and fatigue multipliers.  Computes protection factor against each agent
category as a function of MOPP level, with degradation over time and heat
stress coupling.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.cbrn.agents import AgentCategory
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# MOPP levels
# ---------------------------------------------------------------------------


class MOPPLevel(enum.IntEnum):
    """Mission Oriented Protective Posture levels."""

    MOPP_0 = 0
    MOPP_1 = 1
    MOPP_2 = 2
    MOPP_3 = 3
    MOPP_4 = 4


# ---------------------------------------------------------------------------
# Module-level constant tables
# ---------------------------------------------------------------------------

_MOPP_SPEED_FACTOR: dict[int, float] = {
    0: 1.00,
    1: 0.95,
    2: 0.90,
    3: 0.80,
    4: 0.70,
}

_MOPP_DETECTION_FACTOR: dict[int, float] = {
    0: 1.00,
    1: 1.00,
    2: 0.90,
    3: 0.80,
    4: 0.70,
}

_MOPP_FATIGUE_MULT: dict[int, float] = {
    0: 1.0,
    1: 1.1,
    2: 1.2,
    3: 1.4,
    4: 1.6,
}

# Minimum MOPP level for full protection per agent category
_PROTECTION_THRESHOLD: dict[AgentCategory, int] = {
    AgentCategory.NERVE: 4,
    AgentCategory.BLISTER: 4,
    AgentCategory.CHOKING: 3,
    AgentCategory.BLOOD: 3,
    AgentCategory.BIOLOGICAL: 3,
    AgentCategory.RADIOLOGICAL: 4,
    AgentCategory.NUCLEAR_FALLOUT: 4,
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ProtectionConfig(BaseModel):
    """Configuration for the protection engine."""

    heat_stress_threshold_c: float = 30.0
    heat_stress_fatigue_bonus: float = 0.3
    protection_degradation_per_hour: float = 0.01


# ---------------------------------------------------------------------------
# Protection engine
# ---------------------------------------------------------------------------


class ProtectionEngine:
    """Computes MOPP-level effects on unit performance and CBRN protection."""

    def __init__(self, config: ProtectionConfig | None = None) -> None:
        self._config = config or ProtectionConfig()

    @staticmethod
    def get_mopp_speed_factor(mopp_level: int) -> float:
        """Return speed multiplier for a MOPP level (0-4)."""
        return _MOPP_SPEED_FACTOR.get(mopp_level, 1.0)

    @staticmethod
    def get_mopp_detection_factor(mopp_level: int) -> float:
        """Return detection effectiveness multiplier for a MOPP level."""
        return _MOPP_DETECTION_FACTOR.get(mopp_level, 1.0)

    def get_mopp_fatigue_multiplier(
        self, mopp_level: int, temperature_c: float = 20.0
    ) -> float:
        """Return fatigue multiplier for a MOPP level, including heat stress.

        Above the heat stress threshold, MOPP gear causes additional fatigue
        proportional to the temperature excess.
        """
        base = _MOPP_FATIGUE_MULT.get(mopp_level, 1.0)
        if mopp_level > 0 and temperature_c > self._config.heat_stress_threshold_c:
            excess = temperature_c - self._config.heat_stress_threshold_c
            base += self._config.heat_stress_fatigue_bonus * (excess / 10.0)
        return base

    def compute_protection_factor(
        self,
        mopp_level: int,
        agent_category: int,
        equipment_age_hours: float = 0.0,
    ) -> float:
        """Compute protection factor (0-1) against an agent category.

        Returns 0.0 if MOPP level provides no protection, scaling linearly
        up to 1.0 at the threshold level.  Degrades with equipment age.

        Parameters
        ----------
        mopp_level:
            Current MOPP level (0-4).
        agent_category:
            AgentCategory int value.
        equipment_age_hours:
            Hours since last equipment change.
        """
        try:
            cat = AgentCategory(agent_category)
        except ValueError:
            return 0.0

        threshold = _PROTECTION_THRESHOLD.get(cat, 4)

        if mopp_level <= 0:
            return 0.0

        # Linear scaling: full protection at threshold level
        factor = min(1.0, mopp_level / threshold)

        # Degradation over time
        degradation = self._config.protection_degradation_per_hour * equipment_age_hours
        factor *= max(0.0, 1.0 - degradation)

        return factor

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {"config": self._config.model_dump()}

    def set_state(self, state: dict[str, Any]) -> None:
        if "config" in state:
            self._config = ProtectionConfig(**state["config"])

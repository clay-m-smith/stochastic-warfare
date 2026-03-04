"""CBRN agent definitions and registry.

Each agent (chemical, biological, radiological) is defined by a
:class:`AgentDefinition` loaded from YAML.  The :class:`AgentRegistry`
stores and retrieves definitions by ``agent_id``.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentCategory(enum.IntEnum):
    """Classification of CBRN agents."""

    NERVE = 0
    BLISTER = 1
    CHOKING = 2
    BLOOD = 3
    BIOLOGICAL = 4
    RADIOLOGICAL = 5
    NUCLEAR_FALLOUT = 6


# ---------------------------------------------------------------------------
# Agent definition (YAML-loaded, pydantic-validated)
# ---------------------------------------------------------------------------


class AgentDefinition(BaseModel):
    """Data-driven CBRN agent specification loaded from YAML."""

    agent_id: str
    display_name: str = ""
    category: int = 0  # AgentCategory value
    lct50_mg_min_m3: float = 0.0  # Lethal Ct50 (chemical)
    ict50_mg_min_m3: float = 0.0  # Incapacitating Ct50
    ld50_mg: float = 0.0  # Lethal dose (biological)
    detection_threshold_mg_m3: float = 0.0
    persistence_hours: float = 1.0
    evaporation_rate_per_c: float = 0.01  # Temp-dependent evaporation
    decon_difficulty: float = 0.5  # 0-1
    density_kg_m3: float = 1.2
    vapor_pressure_kpa: float = 0.01
    probit_a: float = -14.0  # Probit intercept
    probit_b: float = 1.0  # Probit slope
    rain_washout_rate: float = 0.1  # Fraction removed per mm/hr
    soil_absorption: dict[str, float] = {}  # SoilType -> absorption multiplier


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------


class AgentRegistry:
    """Registry of CBRN agent definitions, keyed by agent_id."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, defn: AgentDefinition) -> None:
        """Register an agent definition."""
        self._agents[defn.agent_id] = defn
        logger.debug("Registered CBRN agent: %s", defn.agent_id)

    def get(self, agent_id: str) -> AgentDefinition | None:
        """Look up an agent by ID.  Returns ``None`` if not found."""
        return self._agents.get(agent_id)

    def all_agents(self) -> list[AgentDefinition]:
        """Return all registered agent definitions."""
        return list(self._agents.values())

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {"agents": {aid: a.model_dump() for aid, a in self._agents.items()}}

    def set_state(self, state: dict[str, Any]) -> None:
        self._agents.clear()
        for aid, data in state.get("agents", {}).items():
            self._agents[aid] = AgentDefinition(**data)

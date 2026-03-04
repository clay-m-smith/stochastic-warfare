"""Decontamination operations.

Models hasty, deliberate, and thorough decontamination with type-specific
duration and effectiveness.  Agent difficulty scales the duration.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.cbrn.events import (
    DecontaminationCompletedEvent,
    DecontaminationStartedEvent,
)
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Decon types
# ---------------------------------------------------------------------------


class DeconType(enum.IntEnum):
    """Decontamination operation types."""

    HASTY = 0
    DELIBERATE = 1
    THOROUGH = 2


# Base duration (s) and effectiveness (0-1) per type
_DECON_PARAMS: dict[DeconType, tuple[float, float]] = {
    DeconType.HASTY: (300.0, 0.60),
    DeconType.DELIBERATE: (1800.0, 0.95),
    DeconType.THOROUGH: (7200.0, 0.99),
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class DecontaminationConfig(BaseModel):
    """Configuration for the decontamination engine."""

    difficulty_duration_scale: float = 1.0  # How much decon_difficulty scales duration


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------


@dataclass
class DeconOperation:
    """Active decontamination operation."""

    unit_id: str
    decon_type: DeconType
    agent_id: str
    start_time_s: float
    duration_s: float
    effectiveness: float


# ---------------------------------------------------------------------------
# Decontamination engine
# ---------------------------------------------------------------------------


class DecontaminationEngine:
    """Manages decontamination operations for units."""

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: DecontaminationConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or DecontaminationConfig()
        self._active_ops: list[DeconOperation] = []

    def start_decon(
        self,
        unit_id: str,
        decon_type: int,
        agent_id: str,
        decon_difficulty: float,
        sim_time_s: float,
        timestamp: Any = None,
    ) -> DeconOperation:
        """Start a decontamination operation for a unit.

        Parameters
        ----------
        decon_difficulty:
            Agent-specific difficulty (0-1).  Scales duration.
        """
        dt = DeconType(decon_type)
        base_duration, base_effectiveness = _DECON_PARAMS[dt]

        # Difficulty scales duration: harder agents take longer
        duration = base_duration * (1.0 + decon_difficulty * self._config.difficulty_duration_scale)
        effectiveness = base_effectiveness

        op = DeconOperation(
            unit_id=unit_id,
            decon_type=dt,
            agent_id=agent_id,
            start_time_s=sim_time_s,
            duration_s=duration,
            effectiveness=effectiveness,
        )
        self._active_ops.append(op)

        if timestamp is not None:
            self._event_bus.publish(DecontaminationStartedEvent(
                timestamp=timestamp,
                source=ModuleId.CBRN,
                unit_id=unit_id,
                decon_type=int(dt),
                estimated_duration_s=duration,
            ))

        logger.debug("Decon started: %s type=%s duration=%.0fs", unit_id, dt.name, duration)
        return op

    def update(self, sim_time_s: float, timestamp: Any = None) -> list[str]:
        """Check for completed operations.  Returns list of completed unit IDs."""
        completed: list[str] = []
        still_active: list[DeconOperation] = []

        for op in self._active_ops:
            elapsed = sim_time_s - op.start_time_s
            if elapsed >= op.duration_s:
                completed.append(op.unit_id)
                if timestamp is not None:
                    self._event_bus.publish(DecontaminationCompletedEvent(
                        timestamp=timestamp,
                        source=ModuleId.CBRN,
                        unit_id=op.unit_id,
                        decon_type=int(op.decon_type),
                        effectiveness=op.effectiveness,
                    ))
                logger.debug("Decon completed: %s effectiveness=%.2f",
                             op.unit_id, op.effectiveness)
            else:
                still_active.append(op)

        self._active_ops = still_active
        return completed

    @staticmethod
    def get_supply_requirements(decon_type: int) -> dict[str, float]:
        """Return supply requirements for a decon operation type.

        Returns dict of supply class -> quantity needed.
        """
        dt = DeconType(decon_type)
        if dt == DeconType.HASTY:
            return {"class_iv": 10.0, "water_gallons": 50.0}
        elif dt == DeconType.DELIBERATE:
            return {"class_iv": 50.0, "water_gallons": 200.0, "decon_solution_liters": 100.0}
        else:  # THOROUGH
            return {"class_iv": 200.0, "water_gallons": 1000.0, "decon_solution_liters": 500.0}

    @property
    def active_operations(self) -> list[DeconOperation]:
        """Active decon operations."""
        return list(self._active_ops)

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {
            "active_ops": [
                {
                    "unit_id": op.unit_id,
                    "decon_type": int(op.decon_type),
                    "agent_id": op.agent_id,
                    "start_time_s": op.start_time_s,
                    "duration_s": op.duration_s,
                    "effectiveness": op.effectiveness,
                }
                for op in self._active_ops
            ],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._active_ops = [
            DeconOperation(
                unit_id=data["unit_id"],
                decon_type=DeconType(data["decon_type"]),
                agent_id=data["agent_id"],
                start_time_s=data["start_time_s"],
                duration_s=data["duration_s"],
                effectiveness=data["effectiveness"],
            )
            for data in state.get("active_ops", [])
        ]

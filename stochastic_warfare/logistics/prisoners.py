"""Prisoner of war handling — capture, processing, guarding, evacuation.

Prisoners consume Class I supplies and require guards (unavailable for
other duties).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.logistics.events import (
    PrisonerCapturedEvent,
    PrisonerTransferredEvent,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TreatmentLevel(enum.IntEnum):
    """Prisoner treatment levels."""

    STANDARD = 0
    MISTREATED = 1
    TORTURED = 2


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PrisonerGroup:
    """A group of prisoners held together."""

    group_id: str
    count: int
    capturing_unit_id: str
    position: Position
    side_captured: str
    status: str = "UNPROCESSED"  # UNPROCESSED, PROCESSING, HELD, EVACUATED
    processing_elapsed: float = 0.0
    treatment_level: int = 0  # TreatmentLevel value
    interrogation_stress: float = 0.0
    intelligence_yielded: bool = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class PrisonerConfig(BaseModel):
    """Tuning parameters for POW handling."""

    processing_time_hours: float = 2.0
    guard_ratio: int = 10  # 1 guard per N prisoners
    food_per_prisoner_per_hour: float = 0.104  # same as troops
    water_per_prisoner_per_hour: float = 0.167
    interrogation_base_delay_hours: float = 8.0
    stress_yield_multiplier: float = 2.0
    stress_reliability_penalty: float = 0.4


# ---------------------------------------------------------------------------
# Interrogation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InterrogationResult:
    """Result of a prisoner interrogation."""

    intelligence_type: str
    reliability: float
    delay_hours: float
    value: float


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PrisonerEngine:
    """Manage prisoner groups from capture through evacuation.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``PrisonerCapturedEvent``, ``PrisonerTransferredEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : PrisonerConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: PrisonerConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or PrisonerConfig()
        self._groups: dict[str, PrisonerGroup] = {}
        self._next_id: int = 0

    def capture(
        self,
        capturing_unit_id: str,
        count: int,
        position: Position,
        side_captured: str,
        timestamp: datetime | None = None,
    ) -> PrisonerGroup:
        """Record the capture of enemy personnel."""
        self._next_id += 1
        group_id = f"pow_{self._next_id}"
        group = PrisonerGroup(
            group_id=group_id,
            count=count,
            capturing_unit_id=capturing_unit_id,
            position=position,
            side_captured=side_captured,
        )
        self._groups[group_id] = group

        if timestamp is not None:
            self._event_bus.publish(PrisonerCapturedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                capturing_unit_id=capturing_unit_id,
                prisoner_count=count,
                side_captured=side_captured,
            ))

        logger.info("Captured %d %s prisoners (%s)", count, side_captured, group_id)
        return group

    def update(self, dt_hours: float) -> None:
        """Advance processing timers."""
        for group in self._groups.values():
            if group.status == "UNPROCESSED":
                group.status = "PROCESSING"
            if group.status == "PROCESSING":
                group.processing_elapsed += dt_hours
                if group.processing_elapsed >= self._config.processing_time_hours:
                    group.status = "HELD"

    def evacuate(
        self,
        group_id: str,
        destination_id: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Evacuate a prisoner group to a rear facility."""
        group = self._groups[group_id]
        group.status = "EVACUATED"

        if timestamp is not None:
            self._event_bus.publish(PrisonerTransferredEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                group_id=group_id,
                destination_id=destination_id,
            ))

        logger.info("Evacuated POW group %s to %s", group_id, destination_id)

    def set_treatment(
        self,
        group_id: str,
        level: int,
        timestamp: datetime | None = None,
    ) -> None:
        """Set treatment level for a prisoner group."""
        group = self._groups[group_id]
        group.treatment_level = level

    def interrogate(
        self,
        group_id: str,
        stress_level: float,
        timestamp: datetime | None = None,
    ) -> InterrogationResult | None:
        """Interrogate a prisoner group.

        Higher stress produces faster results but lower reliability.
        Returns ``None`` if no intelligence obtained.
        """
        group = self._groups[group_id]
        if group.intelligence_yielded:
            return None

        cfg = self._config
        # Stress speeds up but reduces reliability
        delay = cfg.interrogation_base_delay_hours / (
            1.0 + stress_level * cfg.stress_yield_multiplier
        )
        reliability = max(
            0.1, 1.0 - stress_level * cfg.stress_reliability_penalty
        )

        # Chance of yielding intel
        yield_prob = 0.3 + stress_level * 0.4  # 0.3 base, up to 0.7
        if self._rng.random() < yield_prob:
            group.intelligence_yielded = True
            group.interrogation_stress = stress_level
            return InterrogationResult(
                intelligence_type="tactical",
                reliability=reliability,
                delay_hours=delay,
                value=self._rng.uniform(0.3, 1.0),
            )
        return None

    def get_group(self, group_id: str) -> PrisonerGroup:
        """Return a prisoner group; raises ``KeyError`` if not found."""
        return self._groups[group_id]

    def total_prisoners(self) -> int:
        """Return total number of prisoners not yet evacuated."""
        return sum(
            g.count for g in self._groups.values()
            if g.status != "EVACUATED"
        )

    def guards_required(self) -> int:
        """Return number of guards needed for all held prisoners."""
        total = self.total_prisoners()
        ratio = max(self._config.guard_ratio, 1)
        return (total + ratio - 1) // ratio  # ceiling division

    def supply_consumption_per_hour(self) -> dict[str, float]:
        """Return food/water consumption by prisoners per hour."""
        count = self.total_prisoners()
        return {
            "food_kg": count * self._config.food_per_prisoner_per_hour,
            "water_liters": count * self._config.water_per_prisoner_per_hour,
        }

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "next_id": self._next_id,
            "groups": {
                gid: {
                    "group_id": g.group_id,
                    "count": g.count,
                    "capturing_unit_id": g.capturing_unit_id,
                    "position": list(g.position),
                    "side_captured": g.side_captured,
                    "status": g.status,
                    "processing_elapsed": g.processing_elapsed,
                    "treatment_level": g.treatment_level,
                    "interrogation_stress": g.interrogation_stress,
                    "intelligence_yielded": g.intelligence_yielded,
                }
                for gid, g in self._groups.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._next_id = state.get("next_id", 0)
        self._groups.clear()
        for gid, gd in state["groups"].items():
            self._groups[gid] = PrisonerGroup(
                group_id=gd["group_id"],
                count=gd["count"],
                capturing_unit_id=gd["capturing_unit_id"],
                position=Position(*gd["position"]),
                side_captured=gd["side_captured"],
                status=gd["status"],
                processing_elapsed=gd.get("processing_elapsed", 0.0),
                treatment_level=gd.get("treatment_level", 0),
                interrogation_stress=gd.get("interrogation_stress", 0.0),
                intelligence_yielded=gd.get("intelligence_yielded", False),
            )

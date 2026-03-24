"""Collateral damage tracking.

Phase 12e-3. Tracks civilian casualties per cell/side from military
actions. Cumulative tracking for ROE escalation threshold.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.population.events import CollateralDamageEvent

logger = get_logger(__name__)


class CollateralConfig(BaseModel):
    """Collateral damage tracking configuration."""

    escalation_threshold: int = 50
    """Cumulative civilian casualties before ROE escalation triggers."""


class CollateralEngine:
    """Track civilian casualties from military actions.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``CollateralDamageEvent``.
    config : CollateralConfig | None
        Configuration.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: CollateralConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config or CollateralConfig()
        self._cumulative_by_side: dict[str, int] = {}
        self._records: list[dict] = []

    def record_damage(
        self,
        position: Position,
        casualties: int,
        cause: str,
        responsible_side: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Record a collateral damage incident.

        Parameters
        ----------
        position:
            Location of the incident.
        casualties:
            Number of civilian casualties.
        cause:
            Cause of damage (e.g., "indirect_fire", "air_strike").
        responsible_side:
            Side responsible for the damage.
        timestamp:
            Simulation timestamp.
        """
        ts = timestamp or datetime.now(tz=timezone.utc)
        self._cumulative_by_side[responsible_side] = (
            self._cumulative_by_side.get(responsible_side, 0) + casualties
        )
        self._records.append({
            "position": position,
            "casualties": casualties,
            "cause": cause,
            "side": responsible_side,
            "timestamp": ts,
        })
        self._event_bus.publish(CollateralDamageEvent(
            timestamp=ts,
            source=ModuleId.POPULATION,
            position=position,
            casualties=casualties,
            cause=cause,
            responsible_side=responsible_side,
        ))
        logger.debug(
            "Collateral: %d casualties at (%.0f,%.0f) from %s by %s",
            casualties, position.easting, position.northing, cause, responsible_side,
        )

    def get_cumulative(self, side: str) -> int:
        """Return cumulative civilian casualties caused by a side."""
        return self._cumulative_by_side.get(side, 0)

    def exceeds_threshold(self, side: str) -> bool:
        """Check if a side has exceeded the escalation threshold."""
        return self.get_cumulative(side) >= self._config.escalation_threshold

    def get_records(self) -> list[dict]:
        """Return all collateral damage records."""
        return list(self._records)

    # -- State protocol --

    def get_state(self) -> dict:
        return {
            "cumulative_by_side": dict(self._cumulative_by_side),
            "record_count": len(self._records),
        }

    def set_state(self, state: dict) -> None:
        self._cumulative_by_side = dict(state.get("cumulative_by_side", {}))

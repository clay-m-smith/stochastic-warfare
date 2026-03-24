"""Supply regeneration at depots — production facilities.

Models supply production at fixed facilities (factories, depots). Production
rate scales with infrastructure condition. Damaged facilities produce less;
destroyed facilities produce nothing.

Phase 12b-2.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ProductionFacilityConfig(BaseModel):
    """Configuration for a single production facility."""

    facility_id: str
    facility_type: str  # "factory", "depot", "port", "arsenal"
    production_rates: dict[str, float] = {}
    """Supply class → tons per hour production rate."""
    infrastructure_id: str | None = None
    """Linked infrastructure feature for damage coupling."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ProductionEngine:
    """Manages supply production at depot facilities.

    Parameters
    ----------
    event_bus:
        EventBus for publishing ``SupplyDeliveredEvent`` on production.
    rng:
        A ``numpy.random.Generator``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._facilities: dict[str, ProductionFacilityConfig] = {}
        self._facility_conditions: dict[str, float] = {}

    def register_facility(self, config: ProductionFacilityConfig) -> None:
        """Register a production facility."""
        self._facilities[config.facility_id] = config
        self._facility_conditions[config.facility_id] = 1.0

    def set_facility_condition(self, facility_id: str, condition: float) -> None:
        """Set facility condition (0.0 = destroyed, 1.0 = fully operational)."""
        self._facility_conditions[facility_id] = max(0.0, min(1.0, condition))

    def get_facility_condition(self, facility_id: str) -> float:
        """Return current facility condition."""
        return self._facility_conditions.get(facility_id, 0.0)

    def update(
        self,
        dt_hours: float,
        stockpile_manager: Any | None = None,
        infrastructure_manager: Any | None = None,
        timestamp: datetime | None = None,
    ) -> dict[str, dict[str, float]]:
        """Produce supplies at all registered facilities.

        Parameters
        ----------
        dt_hours:
            Time step in hours.
        stockpile_manager:
            If provided, produced supplies are added to linked depot inventories.
        infrastructure_manager:
            If provided, syncs facility condition from infrastructure state.

        Returns dict of facility_id → {supply_class: tons_produced}.
        """
        ts = timestamp or datetime.now(tz=timezone.utc)
        production_results: dict[str, dict[str, float]] = {}

        for fid, config in self._facilities.items():
            # Sync condition from infrastructure
            if infrastructure_manager is not None and config.infrastructure_id:
                if hasattr(infrastructure_manager, "get_feature_condition"):
                    cond = infrastructure_manager.get_feature_condition(
                        config.infrastructure_id,
                    )
                    self._facility_conditions[fid] = cond

            condition = self._facility_conditions.get(fid, 1.0)
            if condition <= 0.0:
                continue

            produced: dict[str, float] = {}
            for supply_class, rate in config.production_rates.items():
                amount = rate * condition * dt_hours
                if amount > 0:
                    produced[supply_class] = amount

                    # Add to stockpile if manager available
                    if stockpile_manager is not None and hasattr(
                        stockpile_manager, "add_supply",
                    ):
                        stockpile_manager.add_supply(fid, supply_class, amount)

            if produced:
                production_results[fid] = produced
                logger.debug(
                    "Facility %s produced: %s (condition=%.2f)",
                    fid, produced, condition,
                )

        return production_results

    # -- State protocol --

    def get_state(self) -> dict[str, Any]:
        return {
            "facilities": {
                fid: cfg.model_dump()
                for fid, cfg in self._facilities.items()
            },
            "conditions": dict(self._facility_conditions),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._facilities.clear()
        self._facility_conditions.clear()
        for fid, cfg_data in state["facilities"].items():
            self._facilities[fid] = ProductionFacilityConfig.model_validate(cfg_data)
        self._facility_conditions = dict(state["conditions"])

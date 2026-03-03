"""Campaign-level metric extraction for validation.

Extracts summary metrics from :class:`CampaignRunResult` for comparison
against historical documented outcomes.  Produces a flat ``dict[str, float]``
compatible with :class:`MonteCarloResult.compare_to_historical`.

Distinct from :mod:`validation.metrics` which operates on engagement-level
:class:`SimulationResult`.
"""

from __future__ import annotations

import math
from typing import Any

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.entities.base import UnitStatus

logger = get_logger(__name__)


class CampaignValidationMetrics:
    """Static methods extracting named metrics from CampaignRunResult."""

    @staticmethod
    def units_destroyed_count(result: Any, side: str) -> int:
        """Count of units with DESTROYED or SURRENDERED status on *side*."""
        units = result.final_units_by_side.get(side, [])
        return sum(
            1 for u in units
            if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
        )

    @staticmethod
    def units_surviving_count(result: Any, side: str) -> int:
        """Count of units still ACTIVE on *side*."""
        units = result.final_units_by_side.get(side, [])
        return sum(1 for u in units if u.status == UnitStatus.ACTIVE)

    @staticmethod
    def total_units_count(result: Any, side: str) -> int:
        """Total units (all statuses) on *side*."""
        return len(result.final_units_by_side.get(side, []))

    @staticmethod
    def exchange_ratio(result: Any, blue_side: str, red_side: str) -> float:
        """Ratio of red losses to blue losses (higher = better for blue).

        Returns ``inf`` if blue has zero losses but red has some.
        Returns 0.0 if neither side has losses.
        """
        blue_lost = CampaignValidationMetrics.units_destroyed_count(result, blue_side)
        red_lost = CampaignValidationMetrics.units_destroyed_count(result, red_side)
        if blue_lost == 0:
            return float("inf") if red_lost > 0 else 0.0
        return red_lost / blue_lost

    @staticmethod
    def campaign_duration_s(result: Any) -> float:
        """Duration of the campaign run in seconds."""
        return result.duration_simulated_s

    @staticmethod
    def winning_side(result: Any) -> str:
        """Name of the winning side, or '' if no victory."""
        return result.victory_result.winning_side

    @staticmethod
    def victory_condition_met(result: Any) -> str:
        """Type of victory condition that ended the campaign."""
        return result.victory_result.condition_type

    @staticmethod
    def territory_control_fraction(result: Any, side: str) -> float:
        """Fraction of final units on *side* that are active (proxy for control)."""
        total = CampaignValidationMetrics.total_units_count(result, side)
        if total == 0:
            return 0.0
        active = CampaignValidationMetrics.units_surviving_count(result, side)
        return active / total

    @staticmethod
    def engagement_count(result: Any) -> int:
        """Count of engagement events recorded during the campaign."""
        if result.recorder is None:
            return 0
        return len(result.recorder.events_of_type("EngagementEvent"))

    @staticmethod
    def force_ratio_final(result: Any, blue_side: str, red_side: str) -> float:
        """Final force ratio (blue active / red active)."""
        blue_active = CampaignValidationMetrics.units_surviving_count(result, blue_side)
        red_active = CampaignValidationMetrics.units_surviving_count(result, red_side)
        if red_active == 0:
            return float("inf") if blue_active > 0 else 0.0
        return blue_active / red_active

    @staticmethod
    def ships_sunk(result: Any, side: str) -> int:
        """Count of naval units destroyed on *side*."""
        _NAVAL_TYPES = frozenset({
            "type42_destroyer", "type22_frigate",
            "ddg51", "ssn688", "lhd1",
        })
        units = result.final_units_by_side.get(side, [])
        return sum(
            1 for u in units
            if u.status in (UnitStatus.DESTROYED, UnitStatus.SURRENDERED)
            and getattr(u, "unit_type", "") in _NAVAL_TYPES
        )

    @staticmethod
    def extract_all(
        result: Any,
        blue_side: str = "blue",
        red_side: str = "red",
    ) -> dict[str, float]:
        """Extract all standard campaign metrics as a flat dict.

        Keys match :class:`HistoricalMetric` names for direct comparison.
        """
        m = CampaignValidationMetrics
        metrics: dict[str, float] = {}

        metrics["blue_units_destroyed"] = float(m.units_destroyed_count(result, blue_side))
        metrics["red_units_destroyed"] = float(m.units_destroyed_count(result, red_side))
        metrics["blue_units_surviving"] = float(m.units_surviving_count(result, blue_side))
        metrics["red_units_surviving"] = float(m.units_surviving_count(result, red_side))
        metrics["exchange_ratio"] = m.exchange_ratio(result, blue_side, red_side)
        metrics["campaign_duration_s"] = m.campaign_duration_s(result)
        metrics["engagement_count"] = float(m.engagement_count(result))
        metrics["force_ratio_final"] = m.force_ratio_final(result, blue_side, red_side)
        metrics["blue_territory_control"] = m.territory_control_fraction(result, blue_side)
        metrics["red_territory_control"] = m.territory_control_fraction(result, red_side)
        metrics["blue_ships_sunk"] = float(m.ships_sunk(result, blue_side))
        metrics["red_ships_sunk"] = float(m.ships_sunk(result, red_side))

        return metrics

"""Campaign-level metrics extraction and summary.

Provides :class:`CampaignMetrics` with static methods that read from
a :class:`SimulationRecorder` to produce time-series data and campaign
summaries.  No simulation logic -- pure data extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeSeriesPoint:
    """Single point in a time-series measurement."""

    tick: int
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class SideSummary:
    """Summary statistics for one side of a campaign."""

    side: str
    initial_units: int
    final_active_units: int
    units_destroyed: int
    units_routing: int
    units_surrendered: int
    total_engagements: int = 0
    avg_supply_level: float = 1.0


@dataclass(frozen=True)
class CampaignSummary:
    """Complete summary of a campaign run."""

    name: str
    duration_simulated_s: float
    ticks_executed: int
    game_over: bool
    winning_side: str
    victory_condition: str
    sides: dict[str, SideSummary]
    total_events: int
    total_engagements: int = 0
    objectives_controlled: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Metrics engine
# ---------------------------------------------------------------------------


class CampaignMetrics:
    """Static methods for extracting campaign metrics from a recorder.

    All methods are stateless -- they read from a recorder instance
    (or from raw data) and return structured results.
    """

    @staticmethod
    def force_strength_over_time(
        snapshots: list[Any],
        side: str,
    ) -> list[TimeSeriesPoint]:
        """Extract force strength time-series from state snapshots.

        Each snapshot should have a ``state`` dict with a
        ``units_by_side`` key mapping side names to unit state lists.
        Active units are counted.
        """
        points: list[TimeSeriesPoint] = []
        for snap in snapshots:
            state = snap.state if hasattr(snap, "state") else snap
            units_data = state.get("units_by_side", {}).get(side, [])
            active = sum(
                1 for u in units_data
                if (u.get("status", "ACTIVE") if isinstance(u, dict) else "ACTIVE") == "ACTIVE"
            )
            points.append(TimeSeriesPoint(
                tick=snap.tick,
                timestamp=snap.timestamp,
                value=float(active),
            ))
        return points

    @staticmethod
    def supply_level_over_time(
        snapshots: list[Any],
        side: str,
    ) -> list[TimeSeriesPoint]:
        """Extract average supply level time-series from state snapshots.

        Each snapshot should contain a ``supply_states`` dict mapping
        unit_id → supply level (0.0–1.0).  The result is the mean
        across all units on the given side.
        """
        points: list[TimeSeriesPoint] = []
        for snap in snapshots:
            state = snap.state if hasattr(snap, "state") else snap
            supply_states = state.get("supply_states", {})
            units_data = state.get("units_by_side", {}).get(side, [])
            unit_ids = [
                u.get("entity_id", "") if isinstance(u, dict) else ""
                for u in units_data
            ]
            levels = [
                supply_states.get(uid, 1.0)
                for uid in unit_ids
                if uid
            ]
            avg = sum(levels) / len(levels) if levels else 1.0
            points.append(TimeSeriesPoint(
                tick=snap.tick,
                timestamp=snap.timestamp,
                value=avg,
            ))
        return points

    @staticmethod
    def objective_control_timeline(
        snapshots: list[Any],
        objective_id: str,
    ) -> list[TimeSeriesPoint]:
        """Extract objective control timeline from state snapshots.

        Returns a time-series where value encodes the controlling side:
        0.0 = uncontrolled, 1.0 = side A, 2.0 = side B, -1.0 = contested.
        Side mapping is stored as string in the snapshot under
        ``objectives.<objective_id>.controlling_side``.
        """
        points: list[TimeSeriesPoint] = []
        side_map: dict[str, float] = {}
        next_val = 1.0

        for snap in snapshots:
            state = snap.state if hasattr(snap, "state") else snap
            objectives = state.get("objectives", {})
            obj_state = objectives.get(objective_id, {})
            controlling = obj_state.get("controlling_side", "")
            contested = obj_state.get("contested", False)

            if contested:
                val = -1.0
            elif not controlling:
                val = 0.0
            else:
                if controlling not in side_map:
                    side_map[controlling] = next_val
                    next_val += 1.0
                val = side_map[controlling]

            points.append(TimeSeriesPoint(
                tick=snap.tick,
                timestamp=snap.timestamp,
                value=val,
            ))
        return points

    @staticmethod
    def engagement_outcomes(
        events: list[Any],
    ) -> dict[str, int]:
        """Count engagement outcomes from recorded events.

        Looks for events with type name containing 'Engagement' and
        aggregates hit/miss/aborted counts from the event data.
        """
        outcomes: dict[str, int] = {
            "total": 0,
            "hits": 0,
            "misses": 0,
            "aborted": 0,
        }
        for ev in events:
            etype = ev.event_type if hasattr(ev, "event_type") else ""
            if "Engagement" not in etype:
                continue
            outcomes["total"] += 1
            data = ev.data if hasattr(ev, "data") else {}
            if data.get("aborted_reason"):
                outcomes["aborted"] += 1
            elif data.get("hit", False):
                outcomes["hits"] += 1
            else:
                outcomes["misses"] += 1
        return outcomes

    @staticmethod
    def extract_campaign_summary(
        recorder: Any,
        victory: Any,
        units_by_side: dict[str, list[Any]],
        objectives: dict[str, Any] | None = None,
        campaign_name: str = "",
        ticks_executed: int = 0,
        duration_s: float = 0.0,
    ) -> CampaignSummary:
        """Extract a complete campaign summary.

        Parameters
        ----------
        recorder:
            SimulationRecorder with captured events.
        victory:
            VictoryResult from the evaluator.
        units_by_side:
            Final state of units per side.
        objectives:
            Optional objective state dict.
        campaign_name:
            Campaign name for the summary.
        ticks_executed:
            Total ticks simulated.
        duration_s:
            Total simulated time in seconds.
        """
        from stochastic_warfare.entities.base import UnitStatus

        sides: dict[str, SideSummary] = {}
        total_engagements = 0

        # Count engagement events
        events = recorder.events if hasattr(recorder, "events") else []
        eng_outcomes = CampaignMetrics.engagement_outcomes(events)
        total_engagements = eng_outcomes["total"]

        for side_name, units in units_by_side.items():
            initial = len(units)
            active = sum(1 for u in units if u.status == UnitStatus.ACTIVE)
            destroyed = sum(1 for u in units if u.status == UnitStatus.DESTROYED)
            routing = sum(1 for u in units if u.status == UnitStatus.ROUTING)
            surrendered = sum(1 for u in units if u.status == UnitStatus.SURRENDERED)

            sides[side_name] = SideSummary(
                side=side_name,
                initial_units=initial,
                final_active_units=active,
                units_destroyed=destroyed,
                units_routing=routing,
                units_surrendered=surrendered,
                total_engagements=total_engagements,
            )

        # Objective control
        obj_control: dict[str, str] = {}
        if objectives:
            for oid, obj in objectives.items():
                cs = obj.controlling_side if hasattr(obj, "controlling_side") else obj.get("controlling_side", "")
                obj_control[oid] = cs

        return CampaignSummary(
            name=campaign_name,
            duration_simulated_s=duration_s,
            ticks_executed=ticks_executed,
            game_over=victory.game_over if hasattr(victory, "game_over") else False,
            winning_side=victory.winning_side if hasattr(victory, "winning_side") else "",
            victory_condition=victory.condition_type if hasattr(victory, "condition_type") else "",
            sides=sides,
            total_events=len(events),
            total_engagements=total_engagements,
            objectives_controlled=obj_control,
        )

"""Extract engagement-level metrics from simulation results.

Provides functions to compute casualty exchange ratios, equipment losses,
morale distributions, and other summary statistics from raw simulation
output.  The extracted metrics are keyed by name for comparison against
:class:`HistoricalMetric` values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stochastic_warfare.core.events import Event
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Simulation result container
# ---------------------------------------------------------------------------


@dataclass
class UnitFinalState:
    """Snapshot of a unit at the end of a simulation run."""

    entity_id: str
    side: str
    unit_type: str
    status: str  # UnitStatus name: ACTIVE, DISABLED, DESTROYED, etc.
    personnel_remaining: int = 0
    personnel_initial: int = 0
    equipment_destroyed: int = 0
    equipment_total: int = 0
    morale_state: str = "STEADY"
    ammo_expended: dict[str, int] = field(default_factory=dict)


@dataclass
class SimulationResult:
    """Output of one simulation run, ready for metric extraction."""

    seed: int
    ticks_executed: int
    duration_simulated_s: float
    units_final: list[UnitFinalState]
    event_log: list[Event]
    terminated_by: str  # "time_limit", "force_destroyed", etc.


# ---------------------------------------------------------------------------
# Metric extraction functions
# ---------------------------------------------------------------------------


class EngagementMetrics:
    """Static methods extracting named metrics from SimulationResult."""

    @staticmethod
    def _units_for_side(
        result: SimulationResult, side: str
    ) -> list[UnitFinalState]:
        return [u for u in result.units_final if u.side == side]

    @staticmethod
    def equipment_loss_count(result: SimulationResult, side: str) -> int:
        """Count of equipment items destroyed on *side*."""
        return sum(
            u.equipment_destroyed
            for u in EngagementMetrics._units_for_side(result, side)
        )

    @staticmethod
    def units_destroyed_count(result: SimulationResult, side: str) -> int:
        """Count of units with DESTROYED status on *side*."""
        return sum(
            1
            for u in EngagementMetrics._units_for_side(result, side)
            if u.status == "DESTROYED"
        )

    @staticmethod
    def casualty_exchange_ratio(
        result: SimulationResult, blue_side: str, red_side: str
    ) -> float:
        """Ratio of red losses to blue losses (higher = better for blue).

        Uses destroyed unit count.  Returns ``inf`` if blue has zero losses.
        """
        blue_lost = EngagementMetrics.units_destroyed_count(result, blue_side)
        red_lost = EngagementMetrics.units_destroyed_count(result, red_side)
        if blue_lost == 0:
            return float("inf") if red_lost > 0 else 0.0
        return red_lost / blue_lost

    @staticmethod
    def personnel_casualties(
        result: SimulationResult, side: str
    ) -> dict[str, int]:
        """Compute personnel losses on *side*.

        Returns dict with keys ``initial``, ``remaining``, ``casualties``.
        """
        units = EngagementMetrics._units_for_side(result, side)
        initial = sum(u.personnel_initial for u in units)
        remaining = sum(u.personnel_remaining for u in units)
        return {
            "initial": initial,
            "remaining": remaining,
            "casualties": initial - remaining,
        }

    @staticmethod
    def equipment_losses(
        result: SimulationResult, side: str
    ) -> dict[str, int]:
        """Equipment loss summary for *side*.

        Returns ``{destroyed: int, total: int}``.
        """
        units = EngagementMetrics._units_for_side(result, side)
        destroyed = sum(u.equipment_destroyed for u in units)
        total = sum(u.equipment_total for u in units)
        return {"destroyed": destroyed, "total": total}

    @staticmethod
    def engagement_duration_s(result: SimulationResult) -> float:
        """Duration of the engagement in seconds."""
        return result.duration_simulated_s

    @staticmethod
    def ammunition_expended(result: SimulationResult) -> dict[str, float]:
        """Total ammunition expended by type across all units."""
        totals: dict[str, float] = {}
        for unit in result.units_final:
            for ammo_type, count in unit.ammo_expended.items():
                totals[ammo_type] = totals.get(ammo_type, 0.0) + count
        return totals

    @staticmethod
    def morale_distribution(
        result: SimulationResult, side: str
    ) -> dict[str, int]:
        """Count of units in each morale state on *side*."""
        dist: dict[str, int] = {}
        for u in EngagementMetrics._units_for_side(result, side):
            dist[u.morale_state] = dist.get(u.morale_state, 0) + 1
        return dist

    @staticmethod
    def ships_sunk(result: SimulationResult, side: str) -> int:
        """Count of naval units destroyed on *side*."""
        return sum(
            1
            for u in EngagementMetrics._units_for_side(result, side)
            if u.status == "DESTROYED"
            and u.unit_type
            in (
                "type42_destroyer",
                "type22_frigate",
                "ddg51",
                "ssn688",
                "lhd1",
            )
        )

    # Weapon IDs that are classified as missile systems for metric tracking.
    _MISSILE_WEAPON_IDS = frozenset({
        "am39_exocet", "sea_dart", "sea_wolf",
        "tow2_atgm", "at3_sagger",
        "aim9x_sidewinder",
    })

    @staticmethod
    def missiles_hit_ratio(result: SimulationResult) -> float:
        """Fraction of missile engagements that resulted in hits.

        Scans the event log for ``EngagementEvent`` entries whose
        ``weapon_id`` matches a known missile system.  Returns 0.0 if no
        missile engagements occurred.
        """
        launches = 0
        hits = 0
        for event in result.event_log:
            cls_name = type(event).__name__
            if cls_name == "EngagementEvent":
                weapon_id = getattr(event, "weapon_id", "")
                if weapon_id in EngagementMetrics._MISSILE_WEAPON_IDS:
                    launches += 1
                    if getattr(event, "result", "") == "hit":
                        hits += 1
        if launches == 0:
            return 0.0
        return hits / launches

    @staticmethod
    def extract_all(
        result: SimulationResult,
        blue_side: str = "blue",
        red_side: str = "red",
    ) -> dict[str, float]:
        """Extract all standard metrics as a flat dict for comparison."""
        m = EngagementMetrics
        metrics: dict[str, float] = {}

        metrics["exchange_ratio"] = m.casualty_exchange_ratio(
            result, blue_side, red_side
        )
        metrics["duration_s"] = m.engagement_duration_s(result)

        blue_pers = m.personnel_casualties(result, blue_side)
        red_pers = m.personnel_casualties(result, red_side)
        metrics["blue_personnel_casualties"] = float(blue_pers["casualties"])
        metrics["red_personnel_casualties"] = float(red_pers["casualties"])

        metrics["blue_equipment_destroyed"] = float(
            m.equipment_loss_count(result, blue_side)
        )
        metrics["red_equipment_destroyed"] = float(
            m.equipment_loss_count(result, red_side)
        )
        metrics["blue_units_destroyed"] = float(
            m.units_destroyed_count(result, blue_side)
        )
        metrics["red_units_destroyed"] = float(
            m.units_destroyed_count(result, red_side)
        )
        metrics["blue_ships_sunk"] = float(m.ships_sunk(result, blue_side))
        metrics["red_ships_sunk"] = float(m.ships_sunk(result, red_side))
        metrics["missiles_hit_ratio"] = m.missiles_hit_ratio(result)

        return metrics

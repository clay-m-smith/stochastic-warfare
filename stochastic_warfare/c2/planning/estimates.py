"""Running estimates -- staff-maintained operational status tracking.

Models the five standard staff estimates (Personnel, Intelligence, Operations,
Logistics, Communications) that staff officers maintain continuously. Each
estimate computes a supportability score (0.0--1.0) indicating how well the
current situation supports continued operations. Estimates update at
configurable intervals (default 300s), not every tick.

Significant changes (>10% supportability shift) trigger events.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from stochastic_warfare.c2.events import EstimateUpdatedEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EstimateType(enum.IntEnum):
    """Standard staff estimate categories."""

    PERSONNEL = 0
    INTELLIGENCE = 1
    OPERATIONS = 2
    LOGISTICS = 3
    COMMUNICATIONS = 4


# ---------------------------------------------------------------------------
# Estimate dataclasses (frozen -- immutable snapshots)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonnelEstimate:
    """S1/G1/J1 personnel status estimate."""

    strength_ratio: float  # current/authorized (0--1)
    casualty_rate: float  # casualties per hour
    replacement_available: bool
    supportability: float  # 0.0--1.0


@dataclass(frozen=True)
class IntelEstimate:
    """S2/G2/J2 intelligence estimate."""

    confirmed_contacts: int
    estimated_enemy_strength: float
    intel_coverage: float  # fraction of AO covered (0--1)
    collection_assets_available: int
    supportability: float  # 0.0--1.0


@dataclass(frozen=True)
class OperationsEstimate:
    """S3/G3/J3 operations estimate."""

    combat_power_ratio: float  # friendly/enemy
    tempo: float  # operations per hour (0=halted, high=rapid)
    objectives_progress: float  # 0--1 toward mission completion
    terrain_favorability: float  # -1 to 1
    supportability: float  # 0.0--1.0


@dataclass(frozen=True)
class LogisticsEstimate:
    """S4/G4/J4 logistics estimate."""

    supply_level: float  # average across classes (0--1)
    ammo_level: float  # Class V (0--1)
    fuel_level: float  # Class III (0--1)
    transport_available: float  # fraction of needed transport (0--1)
    msr_status: float  # main supply route open fraction (0--1)
    supportability: float  # 0.0--1.0


@dataclass(frozen=True)
class CommsEstimate:
    """S6/G6 communications estimate."""

    network_connectivity: float  # fraction of subordinates reachable (0--1)
    primary_comms_up: bool
    alternate_comms_available: bool
    jamming_threat: float  # 0--1
    supportability: float  # 0.0--1.0


@dataclass(frozen=True)
class RunningEstimates:
    """Composite snapshot of all five staff estimates for a unit."""

    unit_id: str
    timestamp: datetime
    personnel: PersonnelEstimate
    intelligence: IntelEstimate
    operations: OperationsEstimate
    logistics: LogisticsEstimate
    communications: CommsEstimate

    @property
    def overall_supportability(self) -> float:
        """Overall supportability -- bottlenecked by the worst estimate."""
        return min(
            self.personnel.supportability,
            self.intelligence.supportability,
            self.operations.supportability,
            self.logistics.supportability,
            self.communications.supportability,
        )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class EstimatesConfig(BaseModel):
    """Tuning parameters for the running estimates engine."""

    update_interval_s: float = 300.0  # how often estimates refresh
    significant_change_threshold: float = 0.10  # 10% change triggers event
    personnel_critical: float = 0.5  # below this, personnel unsupportable
    supply_critical: float = 0.2
    comms_critical: float = 0.3


# ---------------------------------------------------------------------------
# Supportability computation helpers
# ---------------------------------------------------------------------------


def _clamp01(value: float) -> float:
    """Clamp a value to [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


def _compute_personnel_supportability(
    strength_ratio: float,
    casualty_rate: float,
    replacement_available: bool,
) -> float:
    """Compute personnel supportability score.

    ``strength_ratio * (1 - min(1, casualty_rate/10))`` with a +0.1 boost
    if replacements are available.
    """
    raw = strength_ratio * (1.0 - min(1.0, casualty_rate / 10.0))
    if replacement_available:
        raw += 0.1
    return _clamp01(raw)


def _compute_intel_supportability(
    intel_coverage: float,
    collection_assets: int,
    confirmed_contacts: int,
) -> float:
    """Compute intelligence supportability score.

    Weighted sum: coverage (40%), collection capability (30%), contact
    confirmation (30%).
    """
    raw = (
        intel_coverage * 0.4
        + min(1.0, collection_assets / 3.0) * 0.3
        + (0.3 if confirmed_contacts > 0 else 0.0)
    )
    return _clamp01(raw)


def _compute_operations_supportability(
    combat_power_ratio: float,
    terrain_favorability: float,
    objectives_progress: float,
) -> float:
    """Compute operations supportability score.

    Weighted sum: combat power (50%), terrain (30%), objective progress (20%).
    """
    raw = (
        min(1.0, combat_power_ratio / 3.0) * 0.5
        + (terrain_favorability + 1.0) / 2.0 * 0.3
        + objectives_progress * 0.2
    )
    return _clamp01(raw)


def _compute_logistics_supportability(
    supply_level: float,
    ammo_level: float,
    fuel_level: float,
    transport_available: float,
    msr_status: float,
) -> float:
    """Compute logistics supportability score.

    Bottlenecked by the worst supply class, then weighted with transport and
    MSR status.
    """
    raw = (
        min(supply_level, ammo_level, fuel_level) * 0.5
        + transport_available * 0.25
        + msr_status * 0.25
    )
    return _clamp01(raw)


def _compute_comms_supportability(
    network_connectivity: float,
    primary_comms_up: bool,
    alternate_comms_available: bool,
    jamming_threat: float,
) -> float:
    """Compute communications supportability score.

    Weighted sum: connectivity (50%), primary up (25%), alternate available
    (15%), jamming resistance (10%).
    """
    raw = (
        network_connectivity * 0.5
        + (0.25 if primary_comms_up else 0.0)
        + (0.15 if alternate_comms_available else 0.0)
        + (1.0 - jamming_threat) * 0.1
    )
    return _clamp01(raw)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class EstimatesEngine:
    """Maintains running estimates for all tracked units.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``EstimateUpdatedEvent`` on significant changes.
    config : EstimatesConfig | None
        Tuning parameters.  Uses defaults if ``None``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: EstimatesConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config or EstimatesConfig()
        self._estimates: dict[str, RunningEstimates] = {}
        self._last_update_time: dict[str, float] = {}
        self._previous_supportability: dict[str, dict[str, float]] = {}

    # -- Main update --------------------------------------------------------

    def update_all(  # noqa: PLR0913
        self,
        unit_id: str,
        strength_ratio: float,
        casualty_rate: float,
        replacement_available: bool,
        confirmed_contacts: int,
        estimated_enemy_strength: float,
        intel_coverage: float,
        collection_assets: int,
        combat_power_ratio: float,
        tempo: float,
        objectives_progress: float,
        terrain_favorability: float,
        supply_level: float,
        ammo_level: float,
        fuel_level: float,
        transport_available: float,
        msr_status: float,
        network_connectivity: float,
        primary_comms_up: bool,
        alternate_comms_available: bool,
        jamming_threat: float,
        ts: datetime | None = None,
    ) -> RunningEstimates:
        """Build all five estimates and return a composite ``RunningEstimates``.

        Computes supportability for each estimate category.  If previous
        estimates exist, publishes ``EstimateUpdatedEvent`` for each estimate
        type whose supportability changed by more than the configured
        threshold.

        Parameters
        ----------
        unit_id : str
            Unit these estimates apply to.
        strength_ratio, casualty_rate, replacement_available :
            Personnel inputs.
        confirmed_contacts, estimated_enemy_strength, intel_coverage,
        collection_assets :
            Intelligence inputs.
        combat_power_ratio, tempo, objectives_progress, terrain_favorability :
            Operations inputs.
        supply_level, ammo_level, fuel_level, transport_available, msr_status :
            Logistics inputs.
        network_connectivity, primary_comms_up, alternate_comms_available,
        jamming_threat :
            Communications inputs.
        ts : datetime | None
            Simulation timestamp.  Uses ``datetime.now()`` if ``None``.

        Returns
        -------
        RunningEstimates
            Composite snapshot of all estimates.
        """
        timestamp = ts or datetime.now()

        # --- Compute supportability for each area --------------------------
        personnel_sup = _compute_personnel_supportability(
            strength_ratio, casualty_rate, replacement_available,
        )
        intel_sup = _compute_intel_supportability(
            intel_coverage, collection_assets, confirmed_contacts,
        )
        ops_sup = _compute_operations_supportability(
            combat_power_ratio, terrain_favorability, objectives_progress,
        )
        log_sup = _compute_logistics_supportability(
            supply_level, ammo_level, fuel_level, transport_available, msr_status,
        )
        comms_sup = _compute_comms_supportability(
            network_connectivity, primary_comms_up, alternate_comms_available,
            jamming_threat,
        )

        # --- Build frozen estimate objects ---------------------------------
        personnel = PersonnelEstimate(
            strength_ratio=strength_ratio,
            casualty_rate=casualty_rate,
            replacement_available=replacement_available,
            supportability=personnel_sup,
        )
        intelligence = IntelEstimate(
            confirmed_contacts=confirmed_contacts,
            estimated_enemy_strength=estimated_enemy_strength,
            intel_coverage=intel_coverage,
            collection_assets_available=collection_assets,
            supportability=intel_sup,
        )
        operations = OperationsEstimate(
            combat_power_ratio=combat_power_ratio,
            tempo=tempo,
            objectives_progress=objectives_progress,
            terrain_favorability=terrain_favorability,
            supportability=ops_sup,
        )
        logistics = LogisticsEstimate(
            supply_level=supply_level,
            ammo_level=ammo_level,
            fuel_level=fuel_level,
            transport_available=transport_available,
            msr_status=msr_status,
            supportability=log_sup,
        )
        communications = CommsEstimate(
            network_connectivity=network_connectivity,
            primary_comms_up=primary_comms_up,
            alternate_comms_available=alternate_comms_available,
            jamming_threat=jamming_threat,
            supportability=comms_sup,
        )

        estimates = RunningEstimates(
            unit_id=unit_id,
            timestamp=timestamp,
            personnel=personnel,
            intelligence=intelligence,
            operations=operations,
            logistics=logistics,
            communications=communications,
        )

        # --- Detect significant changes and publish events -----------------
        new_sups = {
            EstimateType.PERSONNEL.name: personnel_sup,
            EstimateType.INTELLIGENCE.name: intel_sup,
            EstimateType.OPERATIONS.name: ops_sup,
            EstimateType.LOGISTICS.name: log_sup,
            EstimateType.COMMUNICATIONS.name: comms_sup,
        }

        prev_sups = self._previous_supportability.get(unit_id, {})
        threshold = self._config.significant_change_threshold

        for est_name, new_val in new_sups.items():
            old_val = prev_sups.get(est_name)
            if old_val is not None and abs(new_val - old_val) > threshold:
                self._event_bus.publish(EstimateUpdatedEvent(
                    timestamp=timestamp,
                    source=ModuleId.C2,
                    unit_id=unit_id,
                    estimate_type=est_name,
                    supportability=new_val,
                ))
                logger.info(
                    "Estimate %s for %s changed: %.2f -> %.2f",
                    est_name, unit_id, old_val, new_val,
                )

        # --- Store results -------------------------------------------------
        self._estimates[unit_id] = estimates
        self._previous_supportability[unit_id] = new_sups

        logger.debug(
            "Updated estimates for %s: overall=%.2f",
            unit_id, estimates.overall_supportability,
        )

        return estimates

    # -- Queries ------------------------------------------------------------

    def get_estimates(self, unit_id: str) -> RunningEstimates | None:
        """Return the latest estimates for *unit_id*, or ``None`` if unknown."""
        return self._estimates.get(unit_id)

    def check_supportability(
        self,
        unit_id: str,
        activity: str = "continue",
    ) -> float:
        """Return overall supportability for *unit_id*.

        Returns 1.0 (fully supportable) if no estimates exist yet --
        assumes supportable until proven otherwise.

        Parameters
        ----------
        unit_id : str
            Unit to check.
        activity : str
            Reserved for future per-activity supportability checks.

        Returns
        -------
        float
            Overall supportability (0.0--1.0).
        """
        est = self._estimates.get(unit_id)
        if est is None:
            return 1.0
        return est.overall_supportability

    # -- Update timing ------------------------------------------------------

    def should_update(self, unit_id: str, elapsed_s: float) -> bool:
        """Return ``True`` if enough time has elapsed since the last update.

        Parameters
        ----------
        unit_id : str
            Unit to check.
        elapsed_s : float
            Seconds elapsed since the last update for this unit.

        Returns
        -------
        bool
            ``True`` if *elapsed_s* >= the configured update interval.
        """
        last = self._last_update_time.get(unit_id, 0.0)
        return (last + elapsed_s) >= self._config.update_interval_s

    def mark_updated(self, unit_id: str) -> None:
        """Reset the update timer for *unit_id*."""
        self._last_update_time[unit_id] = 0.0

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize engine state for checkpoint/restore."""
        estimates_ser: dict[str, dict] = {}
        for uid, est in self._estimates.items():
            estimates_ser[uid] = {
                "unit_id": est.unit_id,
                "timestamp": est.timestamp.isoformat(),
                "personnel": {
                    "strength_ratio": est.personnel.strength_ratio,
                    "casualty_rate": est.personnel.casualty_rate,
                    "replacement_available": est.personnel.replacement_available,
                    "supportability": est.personnel.supportability,
                },
                "intelligence": {
                    "confirmed_contacts": est.intelligence.confirmed_contacts,
                    "estimated_enemy_strength": est.intelligence.estimated_enemy_strength,
                    "intel_coverage": est.intelligence.intel_coverage,
                    "collection_assets_available": est.intelligence.collection_assets_available,
                    "supportability": est.intelligence.supportability,
                },
                "operations": {
                    "combat_power_ratio": est.operations.combat_power_ratio,
                    "tempo": est.operations.tempo,
                    "objectives_progress": est.operations.objectives_progress,
                    "terrain_favorability": est.operations.terrain_favorability,
                    "supportability": est.operations.supportability,
                },
                "logistics": {
                    "supply_level": est.logistics.supply_level,
                    "ammo_level": est.logistics.ammo_level,
                    "fuel_level": est.logistics.fuel_level,
                    "transport_available": est.logistics.transport_available,
                    "msr_status": est.logistics.msr_status,
                    "supportability": est.logistics.supportability,
                },
                "communications": {
                    "network_connectivity": est.communications.network_connectivity,
                    "primary_comms_up": est.communications.primary_comms_up,
                    "alternate_comms_available": est.communications.alternate_comms_available,
                    "jamming_threat": est.communications.jamming_threat,
                    "supportability": est.communications.supportability,
                },
            }

        return {
            "estimates": estimates_ser,
            "last_update_time": dict(self._last_update_time),
            "previous_supportability": {
                uid: dict(sups)
                for uid, sups in self._previous_supportability.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore engine state from checkpoint."""
        self._estimates.clear()
        self._last_update_time.clear()
        self._previous_supportability.clear()

        for uid, sd in state["estimates"].items():
            ts = datetime.fromisoformat(sd["timestamp"])
            p = sd["personnel"]
            i = sd["intelligence"]
            o = sd["operations"]
            l = sd["logistics"]  # noqa: E741
            c = sd["communications"]

            self._estimates[uid] = RunningEstimates(
                unit_id=sd["unit_id"],
                timestamp=ts,
                personnel=PersonnelEstimate(
                    strength_ratio=p["strength_ratio"],
                    casualty_rate=p["casualty_rate"],
                    replacement_available=p["replacement_available"],
                    supportability=p["supportability"],
                ),
                intelligence=IntelEstimate(
                    confirmed_contacts=i["confirmed_contacts"],
                    estimated_enemy_strength=i["estimated_enemy_strength"],
                    intel_coverage=i["intel_coverage"],
                    collection_assets_available=i["collection_assets_available"],
                    supportability=i["supportability"],
                ),
                operations=OperationsEstimate(
                    combat_power_ratio=o["combat_power_ratio"],
                    tempo=o["tempo"],
                    objectives_progress=o["objectives_progress"],
                    terrain_favorability=o["terrain_favorability"],
                    supportability=o["supportability"],
                ),
                logistics=LogisticsEstimate(
                    supply_level=l["supply_level"],
                    ammo_level=l["ammo_level"],
                    fuel_level=l["fuel_level"],
                    transport_available=l["transport_available"],
                    msr_status=l["msr_status"],
                    supportability=l["supportability"],
                ),
                communications=CommsEstimate(
                    network_connectivity=c["network_connectivity"],
                    primary_comms_up=c["primary_comms_up"],
                    alternate_comms_available=c["alternate_comms_available"],
                    jamming_threat=c["jamming_threat"],
                    supportability=c["supportability"],
                ),
            )

        self._last_update_time = dict(state.get("last_update_time", {}))
        self._previous_supportability = {
            uid: dict(sups)
            for uid, sups in state.get("previous_supportability", {}).items()
        }

"""Special Operations Forces mission planning and execution.

Models SOF missions through a lifecycle (PLANNING -> INFIL -> EXECUTING ->
EXFIL -> COMPLETE/FAILED) with stochastic success rolls for HVT targeting,
sabotage, direct action, unconventional warfare, and infiltration operations.
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

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class SOFConfig(BaseModel):
    """Tuning parameters for SOF operations."""

    infiltration_detection_multiplier: float = 0.1
    hvt_success_base_probability: float = 0.3
    sabotage_infrastructure_damage: float = 0.5
    training_force_multiplier: float = 5.0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SOFOperationType(enum.IntEnum):
    """Type of SOF operation."""

    INFILTRATION = 0
    HVT_TARGETING = 1
    DIRECT_ACTION = 2
    UNCONVENTIONAL_WARFARE = 3
    SABOTAGE = 4


class SOFMissionStatus(str, enum.Enum):
    """Lifecycle state of a SOF mission."""

    PLANNING = "planning"
    INFIL = "infil"
    EXECUTING = "executing"
    EXFIL = "exfil"
    COMPLETE = "complete"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Mission data
# ---------------------------------------------------------------------------

# Default durations per operation type (seconds)
_DEFAULT_DURATION: dict[SOFOperationType, float] = {
    SOFOperationType.INFILTRATION: 7200.0,       # 2 hours
    SOFOperationType.HVT_TARGETING: 14400.0,     # 4 hours
    SOFOperationType.DIRECT_ACTION: 3600.0,      # 1 hour
    SOFOperationType.UNCONVENTIONAL_WARFARE: 28800.0,  # 8 hours
    SOFOperationType.SABOTAGE: 10800.0,          # 3 hours
}


@dataclass
class SOFMission:
    """A single SOF mission."""

    mission_id: str
    operation_type: SOFOperationType
    unit_id: str
    target_id: str
    position: Position
    start_time_s: float
    duration_s: float
    status: SOFMissionStatus = SOFMissionStatus.PLANNING
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class SOFMissionResult:
    """Result of a completed (or failed) SOF mission."""

    mission_id: str
    success: bool
    effects: dict[str, float]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SOFOpsEngine:
    """Plan, execute, and resolve SOF missions.

    Parameters
    ----------
    event_bus : EventBus
        For publishing mission events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : SOFConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: SOFConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or SOFConfig()
        self._missions: dict[str, SOFMission] = {}
        self._next_id: int = 0

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def plan_mission(
        self,
        operation_type: SOFOperationType,
        unit_id: str,
        target_id: str,
        position: Position,
        timestamp: datetime | None = None,
    ) -> SOFMission:
        """Create a new SOF mission in PLANNING status.

        Parameters
        ----------
        operation_type : SOFOperationType
            Kind of operation.
        unit_id : str
            ID of the SOF unit executing the mission.
        target_id : str
            ID of the target (HVT, infrastructure, etc.).
        position : Position
            Mission location.
        timestamp : datetime | None
            Optional reference timestamp.

        Returns
        -------
        SOFMission
            The newly-created mission.
        """
        self._next_id += 1
        mission_id = f"sof_{self._next_id}"
        duration = _DEFAULT_DURATION.get(operation_type, 7200.0)
        mission = SOFMission(
            mission_id=mission_id,
            operation_type=operation_type,
            unit_id=unit_id,
            target_id=target_id,
            position=position,
            start_time_s=0.0,
            duration_s=duration,
            status=SOFMissionStatus.PLANNING,
        )
        self._missions[mission_id] = mission
        logger.info(
            "SOF mission planned: %s type=%s unit=%s target=%s",
            mission_id,
            operation_type.name,
            unit_id,
            target_id,
        )
        return mission

    # ------------------------------------------------------------------
    # Update / lifecycle
    # ------------------------------------------------------------------

    def update(
        self,
        dt: float,
        timestamp: datetime | None = None,
    ) -> list[SOFMissionResult]:
        """Advance all active missions by *dt* seconds.

        Lifecycle phases consume fractions of total duration:
          - PLANNING -> INFIL   (instant transition at first update)
          - INFIL     25% of duration_s
          - EXECUTING  50% of duration_s
          - EXFIL     25% of duration_s
          - COMPLETE

        Returns
        -------
        list[SOFMissionResult]
            Results for any missions that completed this tick.
        """
        results: list[SOFMissionResult] = []
        for mission in list(self._missions.values()):
            if mission.status in (
                SOFMissionStatus.COMPLETE,
                SOFMissionStatus.FAILED,
            ):
                continue

            # Advance
            if mission.status == SOFMissionStatus.PLANNING:
                mission.status = SOFMissionStatus.INFIL
                mission.elapsed_s = 0.0

            mission.elapsed_s += dt

            infil_end = mission.duration_s * 0.25
            exec_end = mission.duration_s * 0.75
            exfil_end = mission.duration_s

            if mission.status == SOFMissionStatus.INFIL:
                if mission.elapsed_s >= infil_end:
                    mission.status = SOFMissionStatus.EXECUTING
                    logger.debug(
                        "Mission %s transitioned to EXECUTING", mission.mission_id
                    )

            if mission.status == SOFMissionStatus.EXECUTING:
                if mission.elapsed_s >= exec_end:
                    # Execute the mission
                    result = self._execute(mission)
                    results.append(result)
                    if result.success:
                        mission.status = SOFMissionStatus.EXFIL
                    else:
                        mission.status = SOFMissionStatus.FAILED

            if mission.status == SOFMissionStatus.EXFIL:
                if mission.elapsed_s >= exfil_end:
                    mission.status = SOFMissionStatus.COMPLETE
                    logger.info(
                        "Mission %s COMPLETE", mission.mission_id
                    )

        return results

    def _execute(self, mission: SOFMission) -> SOFMissionResult:
        """Roll for mission success (internal)."""
        if mission.operation_type == SOFOperationType.HVT_TARGETING:
            return self.execute_hvt(mission, 0.5)
        elif mission.operation_type == SOFOperationType.SABOTAGE:
            return self.execute_sabotage(mission, 0.3)
        else:
            # Generic success roll for other types
            prob = self._config.hvt_success_base_probability
            success = self._rng.random() < prob
            effects = {"generic_effect": 1.0} if success else {}
            return SOFMissionResult(
                mission_id=mission.mission_id,
                success=success,
                effects=effects,
            )

    # ------------------------------------------------------------------
    # Specific execution methods
    # ------------------------------------------------------------------

    def execute_hvt(
        self,
        mission: SOFMission,
        target_protection_level: float,
    ) -> SOFMissionResult:
        """Execute an HVT targeting mission.

        Parameters
        ----------
        mission : SOFMission
            The mission to execute.
        target_protection_level : float
            Target protection level 0--1 (higher = harder to reach).

        Returns
        -------
        SOFMissionResult
        """
        prob = self._config.hvt_success_base_probability * (
            1.0 - target_protection_level
        )
        success = self._rng.random() < prob
        effects = {"command_disruption": 0.5} if success else {}
        logger.info(
            "HVT mission %s: P=%.3f success=%s",
            mission.mission_id,
            prob,
            success,
        )
        return SOFMissionResult(
            mission_id=mission.mission_id,
            success=success,
            effects=effects,
        )

    def execute_sabotage(
        self,
        mission: SOFMission,
        infrastructure_defense: float,
    ) -> SOFMissionResult:
        """Execute a sabotage mission.

        Parameters
        ----------
        mission : SOFMission
            The mission to execute.
        infrastructure_defense : float
            Defense level 0--1 (higher = harder to sabotage).

        Returns
        -------
        SOFMissionResult
        """
        prob = self._config.hvt_success_base_probability * (
            1.0 - infrastructure_defense
        )
        success = self._rng.random() < prob
        effects = (
            {"infrastructure_damage": self._config.sabotage_infrastructure_damage}
            if success
            else {}
        )
        logger.info(
            "Sabotage mission %s: P=%.3f success=%s",
            mission.mission_id,
            prob,
            success,
        )
        return SOFMissionResult(
            mission_id=mission.mission_id,
            success=success,
            effects=effects,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_missions(self) -> list[SOFMission]:
        """Return all missions not yet completed or failed."""
        return [
            m
            for m in self._missions.values()
            if m.status
            not in (SOFMissionStatus.COMPLETE, SOFMissionStatus.FAILED)
        ]

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "next_id": self._next_id,
            "missions": {
                mid: {
                    "mission_id": m.mission_id,
                    "operation_type": int(m.operation_type),
                    "unit_id": m.unit_id,
                    "target_id": m.target_id,
                    "position": list(m.position),
                    "start_time_s": m.start_time_s,
                    "duration_s": m.duration_s,
                    "status": m.status.value,
                    "elapsed_s": m.elapsed_s,
                }
                for mid, m in self._missions.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._next_id = state.get("next_id", 0)
        self._missions.clear()
        for mid, md in state["missions"].items():
            self._missions[mid] = SOFMission(
                mission_id=md["mission_id"],
                operation_type=SOFOperationType(md["operation_type"]),
                unit_id=md["unit_id"],
                target_id=md["target_id"],
                position=Position(*md["position"]),
                start_time_s=md["start_time_s"],
                duration_s=md["duration_s"],
                status=SOFMissionStatus(md["status"]),
                elapsed_s=md.get("elapsed_s", 0.0),
            )

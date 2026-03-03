"""Combat engineering — build, repair, emplace, and clear obstacles.

Engineering units execute projects that modify terrain (bridges, roads,
fortifications, minefields).  Progress is time-based; completion publishes
events consumed by terrain and C2.
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
    ConstructionCompletedEvent,
    ConstructionStartedEvent,
    InfrastructureRepairedEvent,
    ObstacleClearedEvent,
    ObstacleEmplacedEvent,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class EngineeringTask(enum.IntEnum):
    """Types of engineering projects."""

    BUILD_BRIDGE = 0
    REPAIR_ROAD = 1
    REPAIR_BRIDGE = 2
    BUILD_FORTIFICATION = 3
    EMPLACE_OBSTACLE = 4
    CLEAR_OBSTACLE = 5
    BUILD_AIRFIELD = 6


@dataclass
class EngineeringProject:
    """A single engineering project in progress."""

    project_id: str
    task_type: EngineeringTask
    position: Position
    progress: float  # 0-1
    estimated_hours: float
    assigned_unit_id: str
    target_feature_id: str | None = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class EngineeringConfig(BaseModel):
    """Tuning parameters for engineering tasks."""

    bridge_build_hours: float = 8.0
    bridge_repair_hours: float = 4.0
    road_repair_rate_per_hour: float = 0.05
    fortification_build_hours: float = 4.0
    minefield_emplace_hours: float = 2.0
    minefield_clear_hours_per_density: float = 6.0
    airfield_build_hours: float = 48.0
    construction_material_per_hour_tons: float = 0.5
    duration_sigma: float = 0.0  # log-normal sigma for stochastic variation (0=deterministic MVP)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class EngineeringEngine:
    """Manage engineering projects and advance them over time.

    Parameters
    ----------
    event_bus : EventBus
        Publishes construction, infrastructure, and obstacle events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : EngineeringConfig | None
        Tuning parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: EngineeringConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or EngineeringConfig()
        self._projects: dict[str, EngineeringProject] = {}
        self._next_id: int = 0

    def start_project(
        self,
        task_type: EngineeringTask,
        position: Position,
        assigned_unit_id: str,
        target_feature_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> EngineeringProject:
        """Start a new engineering project."""
        self._next_id += 1
        project_id = f"eng_{self._next_id}"
        estimated = self.assess_task(task_type)
        project = EngineeringProject(
            project_id=project_id,
            task_type=task_type,
            position=position,
            progress=0.0,
            estimated_hours=estimated,
            assigned_unit_id=assigned_unit_id,
            target_feature_id=target_feature_id,
        )
        self._projects[project_id] = project

        if timestamp is not None:
            self._event_bus.publish(ConstructionStartedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                project_id=project_id,
                task_type=int(task_type),
                position=position,
                assigned_unit_id=assigned_unit_id,
            ))

        logger.info(
            "Started %s at %s (est. %.1f hrs)",
            task_type.name, position, estimated,
        )
        return project

    def update(
        self,
        dt_hours: float,
        timestamp: datetime | None = None,
    ) -> list[EngineeringProject]:
        """Advance all active projects.  Return newly completed ones."""
        completed: list[EngineeringProject] = []
        for project in list(self._projects.values()):
            if project.progress >= 1.0:
                continue
            if project.estimated_hours > 0:
                project.progress += dt_hours / project.estimated_hours
                project.progress = min(project.progress, 1.0)

            if project.progress >= 1.0:
                completed.append(project)
                self._publish_completion(project, timestamp)

        return completed

    def assess_task(self, task_type: EngineeringTask) -> float:
        """Return estimated hours for a task type.

        When ``duration_sigma > 0``, applies log-normal variation to the
        base duration. When ``duration_sigma == 0``, returns the
        deterministic base duration (MVP behavior).
        """
        cfg = self._config
        base = {
            EngineeringTask.BUILD_BRIDGE: cfg.bridge_build_hours,
            EngineeringTask.REPAIR_ROAD: 1.0 / max(cfg.road_repair_rate_per_hour, 0.001),
            EngineeringTask.REPAIR_BRIDGE: cfg.bridge_repair_hours,
            EngineeringTask.BUILD_FORTIFICATION: cfg.fortification_build_hours,
            EngineeringTask.EMPLACE_OBSTACLE: cfg.minefield_emplace_hours,
            EngineeringTask.CLEAR_OBSTACLE: cfg.minefield_clear_hours_per_density,
            EngineeringTask.BUILD_AIRFIELD: cfg.airfield_build_hours,
        }[task_type]
        if cfg.duration_sigma > 0:
            base *= float(self._rng.lognormal(0, cfg.duration_sigma))
        return base

    def get_project(self, project_id: str) -> EngineeringProject:
        """Return a project; raises ``KeyError`` if not found."""
        return self._projects[project_id]

    def active_projects(self) -> list[EngineeringProject]:
        """Return all incomplete projects."""
        return [p for p in self._projects.values() if p.progress < 1.0]

    def _publish_completion(
        self, project: EngineeringProject, timestamp: datetime | None,
    ) -> None:
        """Publish the appropriate completion event."""
        if timestamp is None:
            return
        task = project.task_type

        if task in (EngineeringTask.BUILD_BRIDGE, EngineeringTask.BUILD_FORTIFICATION,
                    EngineeringTask.BUILD_AIRFIELD):
            self._event_bus.publish(ConstructionCompletedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                project_id=project.project_id,
                task_type=int(task),
                target_feature_id=project.target_feature_id or "",
            ))
        elif task in (EngineeringTask.REPAIR_ROAD, EngineeringTask.REPAIR_BRIDGE):
            self._event_bus.publish(InfrastructureRepairedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                feature_id=project.target_feature_id or "",
                condition_restored=0.8,
            ))
        elif task == EngineeringTask.EMPLACE_OBSTACLE:
            self._event_bus.publish(ObstacleEmplacedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                obstacle_id=project.target_feature_id or project.project_id,
                obstacle_type="minefield",
                position=project.position,
            ))
        elif task == EngineeringTask.CLEAR_OBSTACLE:
            self._event_bus.publish(ObstacleClearedEvent(
                timestamp=timestamp,
                source=ModuleId.LOGISTICS,
                obstacle_id=project.target_feature_id or project.project_id,
            ))

    # -- State protocol --

    def get_state(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "next_id": self._next_id,
            "projects": {
                pid: {
                    "project_id": p.project_id,
                    "task_type": int(p.task_type),
                    "position": list(p.position),
                    "progress": p.progress,
                    "estimated_hours": p.estimated_hours,
                    "assigned_unit_id": p.assigned_unit_id,
                    "target_feature_id": p.target_feature_id,
                }
                for pid, p in self._projects.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._next_id = state.get("next_id", 0)
        self._projects.clear()
        for pid, pd in state["projects"].items():
            self._projects[pid] = EngineeringProject(
                project_id=pd["project_id"],
                task_type=EngineeringTask(pd["task_type"]),
                position=Position(*pd["position"]),
                progress=pd["progress"],
                estimated_hours=pd["estimated_hours"],
                assigned_unit_id=pd["assigned_unit_id"],
                target_feature_id=pd.get("target_feature_id"),
            )

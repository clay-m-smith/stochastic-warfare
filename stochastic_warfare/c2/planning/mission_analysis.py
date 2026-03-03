"""Mission analysis -- the first step of the Military Decision Making Process.

Extracts specified tasks from the received order, identifies implied tasks
based on mission type, assesses risks, and determines key terrain and
intelligence requirements.  Staff quality affects the probability of
discovering implied tasks and the thoroughness of risk assessment.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from stochastic_warfare.c2.events import MissionAnalysisCompleteEvent
from stochastic_warfare.c2.orders.types import MissionType, Order
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskType(enum.IntEnum):
    """Classification of tasks extracted during mission analysis."""

    SPECIFIED = 0
    IMPLIED = 1
    ESSENTIAL = 2


class IntelRequirementType(enum.IntEnum):
    """Intelligence requirement categories."""

    PIR = 0   # Priority Intelligence Requirement
    FFIR = 1  # Friendly Force Information Requirement
    EEFI = 2  # Essential Elements of Friendly Information


class RiskLevel(enum.IntEnum):
    """Risk severity levels."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    EXTREME = 3


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """A task extracted or identified during mission analysis."""

    task_id: str
    task_type: TaskType
    description: str
    priority: int  # lower = higher priority


@dataclass(frozen=True)
class IntelRequirement:
    """An intelligence requirement identified during mission analysis."""

    requirement_id: str
    req_type: IntelRequirementType
    description: str
    priority: int


@dataclass(frozen=True)
class RiskAssessment:
    """A risk identified and assessed during mission analysis."""

    risk_id: str
    description: str
    level: RiskLevel
    probability: float  # 0--1
    impact: float  # 0--1
    mitigation: str


@dataclass(frozen=True)
class MissionAnalysisResult:
    """Complete output of the mission analysis step."""

    unit_id: str
    order_id: str
    timestamp: datetime
    specified_tasks: tuple[Task, ...]
    implied_tasks: tuple[Task, ...]
    essential_tasks: tuple[Task, ...]
    intel_requirements: tuple[IntelRequirement, ...]
    risks: tuple[RiskAssessment, ...]
    constraints: tuple[str, ...]
    key_terrain_positions: tuple[Position, ...]
    restated_mission: str


# ---------------------------------------------------------------------------
# Implied task table
# ---------------------------------------------------------------------------

# For each MissionType, list of (description, discovery_probability).
# Staff quality is multiplied by discovery_probability to determine if
# the task is discovered.
_IMPLIED_TASK_TABLE: dict[int, list[tuple[str, float]]] = {
    MissionType.ATTACK: [
        ("Suppress enemy overwatch positions", 0.8),
        ("Secure flanks during advance", 0.7),
        ("Establish support-by-fire positions", 0.9),
        ("Plan casualty evacuation", 0.6),
        ("Coordinate indirect fire support", 0.85),
        ("Establish communications with adjacent units", 0.75),
    ],
    MissionType.DEFEND: [
        ("Prepare alternate and supplementary positions", 0.85),
        ("Plan counterattack routes", 0.7),
        ("Establish observation posts", 0.9),
        ("Prepare obstacles and barriers", 0.8),
        ("Coordinate fire support plan", 0.85),
        ("Plan withdrawal routes", 0.6),
    ],
    MissionType.DELAY: [
        ("Identify subsequent delay positions", 0.9),
        ("Plan disengagement criteria", 0.8),
        ("Prepare demolition targets", 0.6),
        ("Coordinate passage of lines", 0.7),
    ],
    MissionType.MOVEMENT_TO_CONTACT: [
        ("Establish advance guard", 0.9),
        ("Plan hasty attack options", 0.75),
        ("Coordinate reconnaissance", 0.85),
        ("Plan for meeting engagement", 0.7),
    ],
    MissionType.WITHDRAW: [
        ("Establish covering force", 0.85),
        ("Plan passage of lines", 0.8),
        ("Coordinate deception operations", 0.5),
        ("Plan for pursuit avoidance", 0.7),
    ],
    MissionType.RECON: [
        ("Establish communication checkpoints", 0.9),
        ("Plan alternate routes", 0.8),
        ("Prepare disengagement plan", 0.75),
    ],
    MissionType.BREACH: [
        ("Suppress enemy direct fire positions", 0.95),
        ("Obscure breach point", 0.85),
        ("Secure far side of obstacle", 0.9),
        ("Plan casualty evacuation from breach", 0.7),
    ],
    MissionType.SEIZE: [
        ("Isolate the objective", 0.85),
        ("Establish support-by-fire positions", 0.9),
        ("Plan consolidation on objective", 0.8),
    ],
    MissionType.AMBUSH: [
        ("Establish security positions", 0.9),
        ("Plan withdrawal after ambush", 0.85),
        ("Coordinate signal for initiation", 0.95),
    ],
}


# ---------------------------------------------------------------------------
# Mission purpose mapping (for restated mission)
# ---------------------------------------------------------------------------

_MISSION_PURPOSE: dict[int, str] = {
    MissionType.ATTACK: "destroy enemy forces in the objective area",
    MissionType.DEFEND: "defeat enemy attack and retain the position",
    MissionType.DELAY: "slow enemy advance and preserve combat power",
    MissionType.WITHDRAW: "disengage and move to a new position",
    MissionType.SCREEN: "provide early warning and security",
    MissionType.GUARD: "protect the main body from attack",
    MissionType.COVER: "protect the force by fighting if necessary",
    MissionType.MOVEMENT_TO_CONTACT: "develop the situation and establish contact",
    MissionType.RECON: "confirm or deny enemy presence and terrain conditions",
    MissionType.PASSAGE_OF_LINES: "execute orderly passage and maintain continuity",
    MissionType.RELIEF_IN_PLACE: "assume responsibility for the sector",
    MissionType.SUPPORT_BY_FIRE: "suppress the enemy to enable maneuver",
    MissionType.SUPPRESS: "degrade enemy capability through fires",
    MissionType.BREACH: "create a gap in enemy obstacles for passage",
    MissionType.SEIZE: "take possession of the designated terrain",
    MissionType.SECURE: "prevent enemy interference with the specified area",
    MissionType.PATROL: "gather information or provide security",
    MissionType.AMBUSH: "surprise and destroy enemy forces",
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MissionAnalysisEngine:
    """Performs mission analysis on received orders.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``MissionAnalysisCompleteEvent`` upon completion.
    rng : np.random.Generator
        Deterministic RNG for implied-task discovery rolls.
    """

    def __init__(self, event_bus: EventBus, rng: np.random.Generator) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._analysis_count: int = 0

    # -- Main analysis ------------------------------------------------------

    def analyze(  # noqa: PLR0913
        self,
        unit_id: str,
        order: Order,
        friendly_units: int,
        contacts: int,
        supply_level: float,
        terrain_positions: list[Position],
        combat_power_ratio: float,
        staff_quality: float,
        ts: datetime | None = None,
    ) -> MissionAnalysisResult:
        """Perform mission analysis on *order* for *unit_id*.

        Parameters
        ----------
        unit_id : str
            The unit performing the analysis.
        order : Order
            The received order to analyze.
        friendly_units : int
            Number of friendly units in the area.
        contacts : int
            Number of detected enemy contacts.
        supply_level : float
            Current supply level (0.0--1.0).
        terrain_positions : list[Position]
            Significant terrain positions identified by the caller.
        combat_power_ratio : float
            Friendly-to-enemy combat power ratio.
        staff_quality : float
            Staff proficiency (0.0--1.0).  Multiplies implied-task
            discovery probability.
        ts : datetime | None
            Simulation timestamp.  Uses ``datetime.now()`` if ``None``.

        Returns
        -------
        MissionAnalysisResult
            Complete mission analysis output.
        """
        timestamp = ts or datetime.now()

        # 1. Specified tasks
        specified_tasks = self._extract_specified_tasks(order)

        # 2. Implied tasks
        implied_tasks = self._discover_implied_tasks(order, staff_quality)

        # 3. Essential tasks
        essential_tasks = self._identify_essential_tasks(
            specified_tasks, implied_tasks,
        )

        # 4. Intel requirements
        intel_requirements = self._generate_intel_requirements(
            order, contacts,
        )

        # 5. Risks
        risks = self._assess_risks(
            order, friendly_units, contacts, supply_level,
            combat_power_ratio,
        )

        # 6. Constraints
        constraints = self._build_constraints(order)

        # 7. Key terrain
        key_terrain = self._determine_key_terrain(
            order, terrain_positions,
        )

        # 8. Restated mission
        restated_mission = self._build_restated_mission(
            unit_id, order,
        )

        self._analysis_count += 1

        result = MissionAnalysisResult(
            unit_id=unit_id,
            order_id=order.order_id,
            timestamp=timestamp,
            specified_tasks=tuple(specified_tasks),
            implied_tasks=tuple(implied_tasks),
            essential_tasks=tuple(essential_tasks),
            intel_requirements=tuple(intel_requirements),
            risks=tuple(risks),
            constraints=tuple(constraints),
            key_terrain_positions=tuple(key_terrain),
            restated_mission=restated_mission,
        )

        # Publish event
        self._event_bus.publish(MissionAnalysisCompleteEvent(
            timestamp=timestamp,
            source=ModuleId.C2,
            unit_id=unit_id,
            num_specified_tasks=len(specified_tasks),
            num_implied_tasks=len(implied_tasks),
            num_constraints=len(constraints),
        ))

        logger.info(
            "Mission analysis complete for %s: %d specified, %d implied, "
            "%d essential tasks, %d risks",
            unit_id,
            len(specified_tasks),
            len(implied_tasks),
            len(essential_tasks),
            len(risks),
        )

        return result

    # -- Sub-steps ----------------------------------------------------------

    def _extract_specified_tasks(self, order: Order) -> list[Task]:
        """Extract specified tasks directly from the order."""
        tasks: list[Task] = []

        # Primary mission task -- always present
        try:
            mission_name = MissionType(order.mission_type).name
        except ValueError:
            mission_name = f"MISSION_{order.mission_type}"

        obj_str = str(order.objective_position) if order.objective_position else "designated area"
        tasks.append(Task(
            task_id=f"{order.order_id}_spec_0",
            task_type=TaskType.SPECIFIED,
            description=f"{mission_name} at {obj_str}",
            priority=0,
        ))

        # Phase line task
        if order.phase_line:
            tasks.append(Task(
                task_id=f"{order.order_id}_spec_1",
                task_type=TaskType.SPECIFIED,
                description=f"Secure phase line {order.phase_line}",
                priority=1,
            ))

        return tasks

    def _discover_implied_tasks(
        self,
        order: Order,
        staff_quality: float,
    ) -> list[Task]:
        """Discover implied tasks based on mission type and staff quality."""
        implied_entries = _IMPLIED_TASK_TABLE.get(order.mission_type, [])
        tasks: list[Task] = []

        for i, (description, discovery_prob) in enumerate(implied_entries):
            roll = self._rng.random()
            if roll < discovery_prob * staff_quality:
                tasks.append(Task(
                    task_id=f"{order.order_id}_impl_{i}",
                    task_type=TaskType.IMPLIED,
                    description=description,
                    priority=i,
                ))

        return tasks

    def _identify_essential_tasks(
        self,
        specified_tasks: list[Task],
        implied_tasks: list[Task],
    ) -> list[Task]:
        """Identify essential tasks from specified and implied tasks."""
        essential: list[Task] = []

        # The first specified task is always essential
        if specified_tasks:
            first_spec = specified_tasks[0]
            essential.append(Task(
                task_id=first_spec.task_id,
                task_type=TaskType.ESSENTIAL,
                description=first_spec.description,
                priority=first_spec.priority,
            ))

        # The first discovered implied task is also essential
        if implied_tasks:
            first_impl = implied_tasks[0]
            essential.append(Task(
                task_id=first_impl.task_id,
                task_type=TaskType.ESSENTIAL,
                description=first_impl.description,
                priority=first_impl.priority,
            ))

        return essential

    def _generate_intel_requirements(
        self,
        order: Order,
        contacts: int,
    ) -> list[IntelRequirement]:
        """Generate standard intelligence requirements."""
        reqs: list[IntelRequirement] = [
            IntelRequirement(
                requirement_id=f"{order.order_id}_pir_0",
                req_type=IntelRequirementType.PIR,
                description="Enemy strength and disposition",
                priority=0,
            ),
            IntelRequirement(
                requirement_id=f"{order.order_id}_pir_1",
                req_type=IntelRequirementType.PIR,
                description="Enemy likely course of action",
                priority=1,
            ),
            IntelRequirement(
                requirement_id=f"{order.order_id}_ffir_0",
                req_type=IntelRequirementType.FFIR,
                description="Status of adjacent friendly units",
                priority=0,
            ),
            IntelRequirement(
                requirement_id=f"{order.order_id}_eefi_0",
                req_type=IntelRequirementType.EEFI,
                description="Friendly unit locations and strength",
                priority=0,
            ),
        ]

        if contacts > 3:
            reqs.append(IntelRequirement(
                requirement_id=f"{order.order_id}_pir_2",
                req_type=IntelRequirementType.PIR,
                description="Enemy reserve location",
                priority=1,
            ))

        return reqs

    def _assess_risks(  # noqa: PLR0913
        self,
        order: Order,
        friendly_units: int,
        contacts: int,
        supply_level: float,
        combat_power_ratio: float,
    ) -> list[RiskAssessment]:
        """Assess risks based on situational inputs."""
        risks: list[RiskAssessment] = []
        risk_idx = 0

        # Unfavorable force ratio
        if combat_power_ratio < 1.0:
            risks.append(RiskAssessment(
                risk_id=f"{order.order_id}_risk_{risk_idx}",
                description="Unfavorable force ratio",
                level=RiskLevel.HIGH,
                probability=0.7,
                impact=0.8,
                mitigation="Request reinforcements or adjust scheme of maneuver",
            ))
            risk_idx += 1

        # Supply shortage
        if supply_level < 0.3:
            level = RiskLevel.HIGH if supply_level < 0.15 else RiskLevel.MODERATE
            risks.append(RiskAssessment(
                risk_id=f"{order.order_id}_risk_{risk_idx}",
                description="Supply shortage",
                level=level,
                probability=0.6,
                impact=0.6,
                mitigation="Prioritize resupply and reduce consumption rate",
            ))
            risk_idx += 1

        # Outnumbered by contacts
        if contacts > friendly_units:
            risks.append(RiskAssessment(
                risk_id=f"{order.order_id}_risk_{risk_idx}",
                description="Outnumbered by detected contacts",
                level=RiskLevel.MODERATE,
                probability=0.5,
                impact=0.5,
                mitigation="Concentrate forces and seek terrain advantage",
            ))
            risk_idx += 1

        # Fratricide risk -- always present
        risks.append(RiskAssessment(
            risk_id=f"{order.order_id}_risk_{risk_idx}",
            description="Fratricide",
            level=RiskLevel.LOW,
            probability=0.1,
            impact=0.3,
            mitigation="Enforce fire control measures and identification procedures",
        ))

        return risks

    def _build_constraints(self, order: Order) -> list[str]:
        """Build constraints from order context."""
        constraints: list[str] = []

        if order.phase_line:
            constraints.append(
                f"Do not cross {order.phase_line} before H-hour"
            )

        # Always-present constraints
        constraints.append("Minimize collateral damage")
        constraints.append("Maintain communications with higher HQ")

        return constraints

    def _determine_key_terrain(
        self,
        order: Order,
        terrain_positions: list[Position],
    ) -> list[Position]:
        """Determine key terrain positions."""
        key_terrain: list[Position] = []

        if order.objective_position is not None:
            key_terrain.append(order.objective_position)

        key_terrain.extend(terrain_positions)

        return key_terrain

    def _build_restated_mission(
        self,
        unit_id: str,
        order: Order,
    ) -> str:
        """Auto-generate the restated mission string."""
        try:
            mission_name = MissionType(order.mission_type).name.lower().replace("_", " ")
        except ValueError:
            mission_name = f"execute mission {order.mission_type}"

        purpose = _MISSION_PURPOSE.get(
            order.mission_type,
            "accomplish the assigned mission",
        )

        nlt = str(order.execution_time) if order.execution_time else "on order"

        return (
            f"Unit {unit_id} {mission_name}s to {purpose} "
            f"NLT {nlt}"
        )

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize engine state for checkpoint/restore."""
        return {
            "analysis_count": self._analysis_count,
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict) -> None:
        """Restore engine state from checkpoint."""
        self._analysis_count = state["analysis_count"]
        self._rng.bit_generator.state = state["rng_state"]

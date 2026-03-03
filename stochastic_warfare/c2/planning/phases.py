"""Operational phasing -- plan structure with condition-based transitions.

Creates multi-phase operational plans from selected COAs. Phase transitions
are condition-based (enemy reserve committed, objective secured, casualties
exceed threshold), not scheduled. Time acts as a fallback condition. Planning
horizon scales with echelon level.

Supports branches (contingency plans triggered by enemy actions) and
sequels (follow-on operations after current plan completes).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

from stochastic_warfare.c2.events import PhaseTransitionEvent
from stochastic_warfare.c2.orders.types import MissionType
from stochastic_warfare.c2.planning.coa import COA
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OperationalPhaseType(enum.IntEnum):
    """Standard operational phases for phased operations."""

    SHAPING = 0
    DECISIVE = 1
    EXPLOITATION = 2
    TRANSITION = 3
    PREPARATION = 4
    DEFENSE = 5
    COUNTERATTACK = 6
    CONSOLIDATION = 7


class ConditionType(enum.IntEnum):
    """Types of conditions that can trigger phase transitions."""

    TIME_ELAPSED = 0
    CASUALTIES_EXCEED = 1
    OBJECTIVE_SECURED = 2
    FORCE_RATIO_BELOW = 3
    FORCE_RATIO_ABOVE = 4
    SUPPLY_BELOW = 5
    MORALE_BELOW = 6
    ENEMY_RESERVE_COMMITTED = 7


# ---------------------------------------------------------------------------
# Dataclasses (mutable -- plans evolve during execution)
# ---------------------------------------------------------------------------


@dataclass
class TransitionCondition:
    """A single condition that can trigger a phase transition."""

    condition_type: ConditionType
    threshold: float  # e.g., 0.3 for 30% casualties, 3600.0 for time
    description: str


@dataclass
class OperationalPhase:
    """A phase within an operational plan."""

    phase_type: OperationalPhaseType
    name: str
    duration_estimate_s: float
    tasks: tuple[str, ...]  # task descriptions for this phase
    transition_conditions: list[TransitionCondition]  # any one triggers transition
    is_active: bool = False
    is_complete: bool = False


@dataclass
class BranchPlan:
    """A contingency plan triggered by enemy actions or changed conditions."""

    branch_id: str
    trigger_description: str
    trigger_condition: TransitionCondition
    phases: list[OperationalPhase]


@dataclass
class SequelPlan:
    """A follow-on operation after current plan completes."""

    sequel_id: str
    description: str
    mission_type: int  # MissionType value for the follow-on
    conditions_for_initiation: list[TransitionCondition]


@dataclass
class OperationalPlan:
    """A complete multi-phase operational plan derived from a selected COA."""

    plan_id: str
    unit_id: str
    coa_id: str
    timestamp: datetime
    phases: list[OperationalPhase]
    current_phase_index: int = 0
    branches: list[BranchPlan] = field(default_factory=list)
    sequels: list[SequelPlan] = field(default_factory=list)
    planning_horizon_s: float = 28800.0  # default 8h (battalion)
    is_complete: bool = False

    @property
    def current_phase(self) -> OperationalPhase | None:
        """Return the currently active phase, or None if plan is complete."""
        if self.is_complete or self.current_phase_index >= len(self.phases):
            return None
        return self.phases[self.current_phase_index]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class PhasingConfig(BaseModel):
    """Tuning parameters for operational phasing."""

    planning_horizons_s: dict[str, float] = {
        "PLATOON": 1800.0,
        "COMPANY": 7200.0,
        "BATTALION": 28800.0,
        "BRIGADE": 86400.0,
        "DIVISION": 172800.0,
        "CORPS": 345600.0,
    }
    default_casualty_threshold: float = 0.3
    default_supply_threshold: float = 0.15
    default_morale_threshold: float = 0.25


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Maps echelon integer values to planning horizon keys.
_ECHELON_TO_KEY: dict[int, str] = {
    0: "PLATOON",
    1: "PLATOON",
    2: "PLATOON",
    3: "PLATOON",
    4: "PLATOON",
    5: "COMPANY",
    6: "BATTALION",
    7: "BATTALION",
    8: "BRIGADE",
    9: "DIVISION",
    10: "CORPS",
    11: "CORPS",
    12: "CORPS",
    13: "CORPS",
}

# Mission types that produce offensive phase sequences.
_OFFENSIVE_MISSIONS: frozenset[int] = frozenset({
    MissionType.ATTACK,
    MissionType.SEIZE,
    MissionType.MOVEMENT_TO_CONTACT,
})

# Mission types that produce defensive phase sequences.
_DEFENSIVE_MISSIONS: frozenset[int] = frozenset({
    MissionType.DEFEND,
})

# Mission types that produce delay/withdrawal phase sequences.
_DELAY_MISSIONS: frozenset[int] = frozenset({
    MissionType.DELAY,
    MissionType.WITHDRAW,
})

# Phase duration distribution for offensive operations.
_OFFENSIVE_PHASE_FRACTIONS: tuple[tuple[OperationalPhaseType, float], ...] = (
    (OperationalPhaseType.SHAPING, 0.20),
    (OperationalPhaseType.DECISIVE, 0.50),
    (OperationalPhaseType.EXPLOITATION, 0.20),
    (OperationalPhaseType.TRANSITION, 0.10),
)

# Phase duration distribution for defensive operations.
_DEFENSIVE_PHASE_FRACTIONS: tuple[tuple[OperationalPhaseType, float], ...] = (
    (OperationalPhaseType.PREPARATION, 0.20),
    (OperationalPhaseType.DEFENSE, 0.50),
    (OperationalPhaseType.COUNTERATTACK, 0.20),
    (OperationalPhaseType.CONSOLIDATION, 0.10),
)

# Phase duration distribution for delay/withdrawal operations.
_DELAY_PHASE_FRACTIONS: tuple[tuple[OperationalPhaseType, float], ...] = (
    (OperationalPhaseType.SHAPING, 0.25),
    (OperationalPhaseType.DEFENSE, 0.50),
    (OperationalPhaseType.TRANSITION, 0.25),
)

# Default (fallback) phase distribution.
_DEFAULT_PHASE_FRACTIONS: tuple[tuple[OperationalPhaseType, float], ...] = (
    (OperationalPhaseType.SHAPING, 0.30),
    (OperationalPhaseType.DECISIVE, 0.50),
    (OperationalPhaseType.TRANSITION, 0.20),
)

# Phase type display names.
_PHASE_NAMES: dict[OperationalPhaseType, str] = {
    OperationalPhaseType.SHAPING: "Shaping",
    OperationalPhaseType.DECISIVE: "Decisive Action",
    OperationalPhaseType.EXPLOITATION: "Exploitation",
    OperationalPhaseType.TRANSITION: "Transition",
    OperationalPhaseType.PREPARATION: "Preparation",
    OperationalPhaseType.DEFENSE: "Defense",
    OperationalPhaseType.COUNTERATTACK: "Counterattack",
    OperationalPhaseType.CONSOLIDATION: "Consolidation",
}


# ---------------------------------------------------------------------------
# Condition checking
# ---------------------------------------------------------------------------


def _check_condition(
    condition: TransitionCondition,
    force_ratio: float,
    casualties_fraction: float,
    objectives_progress: float,
    supply_level: float,
    morale_level: float,
    elapsed_s: float,
) -> bool:
    """Evaluate a single transition condition against current state."""
    ct = condition.condition_type
    threshold = condition.threshold

    if ct == ConditionType.TIME_ELAPSED:
        return elapsed_s >= threshold
    if ct == ConditionType.CASUALTIES_EXCEED:
        return casualties_fraction >= threshold
    if ct == ConditionType.OBJECTIVE_SECURED:
        return objectives_progress >= threshold
    if ct == ConditionType.FORCE_RATIO_BELOW:
        return force_ratio <= threshold
    if ct == ConditionType.FORCE_RATIO_ABOVE:
        return force_ratio >= threshold
    if ct == ConditionType.SUPPLY_BELOW:
        return supply_level <= threshold
    if ct == ConditionType.MORALE_BELOW:
        return morale_level <= threshold
    if ct == ConditionType.ENEMY_RESERVE_COMMITTED:
        # Triggered by external event, not checked here.
        return False

    return False  # pragma: no cover


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PhasingEngine:
    """Creates and manages operational plans with condition-based phase transitions.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``PhaseTransitionEvent`` on phase changes.
    config : PhasingConfig | None
        Tuning parameters.  Uses defaults if ``None``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: PhasingConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config or PhasingConfig()
        self._plan_count: int = 0

    # -- Plan creation -------------------------------------------------------

    def create_plan(  # noqa: PLR0913
        self,
        unit_id: str,
        coa: COA,
        echelon: int,
        mission_type: int,
        ts: datetime | None = None,
    ) -> OperationalPlan:
        """Create an operational plan from a selected COA.

        Parameters
        ----------
        unit_id : str
            The planning unit.
        coa : COA
            The selected Course of Action.
        echelon : int
            Echelon level of the planning unit (drives planning horizon).
        mission_type : int
            MissionType value determining the phase sequence.
        ts : datetime | None
            Simulation timestamp.  Falls back to ``datetime.now()`` if ``None``.

        Returns
        -------
        OperationalPlan
            A multi-phase plan with branches and sequels.
        """
        timestamp = ts or datetime.now()

        # 1. Determine planning horizon from echelon
        echelon_key = _ECHELON_TO_KEY.get(echelon, "BATTALION")
        planning_horizon_s = self._config.planning_horizons_s.get(
            echelon_key, 28800.0,
        )

        # 2. Select phase sequence based on mission type
        if mission_type in _OFFENSIVE_MISSIONS:
            phase_fractions = _OFFENSIVE_PHASE_FRACTIONS
        elif mission_type in _DEFENSIVE_MISSIONS:
            phase_fractions = _DEFENSIVE_PHASE_FRACTIONS
        elif mission_type in _DELAY_MISSIONS:
            phase_fractions = _DELAY_PHASE_FRACTIONS
        else:
            phase_fractions = _DEFAULT_PHASE_FRACTIONS

        # 3. Build phases with duration estimates
        phases = self._build_phases(
            phase_fractions, planning_horizon_s, coa, mission_type,
        )

        # 4. Set first phase as active
        if phases:
            phases[0].is_active = True

        # 5. Build plan_id
        plan_id = f"{unit_id}_plan_{int(timestamp.timestamp()) if ts else 0}"

        # 6. Build standard branch plans
        branches = self._build_standard_branches(plan_id, planning_horizon_s)

        # 7. Build standard sequel plans
        sequels = self._build_standard_sequels(plan_id, mission_type)

        self._plan_count += 1

        plan = OperationalPlan(
            plan_id=plan_id,
            unit_id=unit_id,
            coa_id=coa.coa_id,
            timestamp=timestamp,
            phases=phases,
            current_phase_index=0,
            branches=branches,
            sequels=sequels,
            planning_horizon_s=planning_horizon_s,
            is_complete=False,
        )

        logger.info(
            "Created plan %s for %s: %d phases, horizon=%.0fs, mission=%s",
            plan_id, unit_id, len(phases), planning_horizon_s,
            MissionType(mission_type).name if mission_type in iter(MissionType) else str(mission_type),
        )

        return plan

    # -- Phase transition checking -------------------------------------------

    def check_transition(  # noqa: PLR0913
        self,
        plan: OperationalPlan,
        force_ratio: float,
        casualties_fraction: float,
        objectives_progress: float,
        supply_level: float,
        morale_level: float,
        elapsed_s: float,
        ts: datetime | None = None,
    ) -> bool:
        """Check if the current phase should transition to the next.

        Evaluates all transition conditions on the current phase. If ANY
        condition is met, the plan advances to the next phase.

        Parameters
        ----------
        plan : OperationalPlan
            The operational plan to check.
        force_ratio : float
            Current friendly-to-enemy force ratio.
        casualties_fraction : float
            Friendly casualties as fraction of initial strength (0--1).
        objectives_progress : float
            Objective completion progress (0--1).
        supply_level : float
            Current supply level (0--1).
        morale_level : float
            Current morale level (0--1).
        elapsed_s : float
            Time elapsed in the current phase (seconds).
        ts : datetime | None
            Simulation timestamp for events.

        Returns
        -------
        bool
            True if a transition occurred.
        """
        if plan.is_complete:
            return False

        current = plan.current_phase
        if current is None:
            return False

        # Check if ANY transition condition is met
        triggered_condition: TransitionCondition | None = None
        for condition in current.transition_conditions:
            if _check_condition(
                condition,
                force_ratio,
                casualties_fraction,
                objectives_progress,
                supply_level,
                morale_level,
                elapsed_s,
            ):
                triggered_condition = condition
                break

        if triggered_condition is None:
            return False

        # Transition: mark current phase complete
        old_phase_type = current.phase_type
        current.is_complete = True
        current.is_active = False

        # Advance phase index
        plan.current_phase_index += 1

        # Check if past last phase
        if plan.current_phase_index >= len(plan.phases):
            plan.is_complete = True

            logger.info(
                "Plan %s complete (last phase %s finished, trigger: %s)",
                plan.plan_id,
                OperationalPhaseType(old_phase_type).name,
                triggered_condition.description,
            )

            # Publish transition event with empty new_phase
            timestamp = ts or datetime.now()
            self._event_bus.publish(PhaseTransitionEvent(
                timestamp=timestamp,
                source=ModuleId.C2,
                unit_id=plan.unit_id,
                plan_id=plan.plan_id,
                old_phase=OperationalPhaseType(old_phase_type).name,
                new_phase="COMPLETE",
                trigger=triggered_condition.description,
            ))

            return True

        # Activate next phase
        new_phase = plan.phases[plan.current_phase_index]
        new_phase.is_active = True

        timestamp = ts or datetime.now()
        self._event_bus.publish(PhaseTransitionEvent(
            timestamp=timestamp,
            source=ModuleId.C2,
            unit_id=plan.unit_id,
            plan_id=plan.plan_id,
            old_phase=OperationalPhaseType(old_phase_type).name,
            new_phase=OperationalPhaseType(new_phase.phase_type).name,
            trigger=triggered_condition.description,
        ))

        logger.info(
            "Plan %s: %s -> %s (trigger: %s)",
            plan.plan_id,
            OperationalPhaseType(old_phase_type).name,
            OperationalPhaseType(new_phase.phase_type).name,
            triggered_condition.description,
        )

        return True

    # -- Branch activation ---------------------------------------------------

    def check_branch_activation(  # noqa: PLR0913
        self,
        plan: OperationalPlan,
        force_ratio: float,
        casualties_fraction: float,
        objectives_progress: float,
        supply_level: float,
        morale_level: float,
        elapsed_s: float,
    ) -> BranchPlan | None:
        """Check if any branch plan should be activated.

        Parameters
        ----------
        plan : OperationalPlan
            The operational plan to check branches for.
        force_ratio : float
            Current friendly-to-enemy force ratio.
        casualties_fraction : float
            Friendly casualties as fraction of initial strength (0--1).
        objectives_progress : float
            Objective completion progress (0--1).
        supply_level : float
            Current supply level (0--1).
        morale_level : float
            Current morale level (0--1).
        elapsed_s : float
            Time elapsed in the current phase (seconds).

        Returns
        -------
        BranchPlan | None
            The first branch plan whose trigger condition is met, or None.
        """
        for branch in plan.branches:
            if _check_condition(
                branch.trigger_condition,
                force_ratio,
                casualties_fraction,
                objectives_progress,
                supply_level,
                morale_level,
                elapsed_s,
            ):
                logger.info(
                    "Branch activated for plan %s: %s",
                    plan.plan_id, branch.trigger_description,
                )
                return branch

        return None

    # -- State protocol ------------------------------------------------------

    def get_state(self) -> dict:
        """Serialize engine state for checkpoint/restore."""
        return {
            "plan_count": self._plan_count,
        }

    def set_state(self, state: dict) -> None:
        """Restore engine state from checkpoint."""
        self._plan_count = state["plan_count"]

    # -- Private helpers -----------------------------------------------------

    def _build_phases(
        self,
        phase_fractions: tuple[tuple[OperationalPhaseType, float], ...],
        planning_horizon_s: float,
        coa: COA,
        mission_type: int,
    ) -> list[OperationalPhase]:
        """Build phase objects with duration estimates and transition conditions."""
        phases: list[OperationalPhase] = []

        # Build a lookup of COA timeline tasks by index
        coa_timeline_tasks: dict[int, tuple[str, ...]] = {}
        for idx, tl in enumerate(coa.timeline):
            coa_timeline_tasks[idx] = tl.actions

        for idx, (phase_type, fraction) in enumerate(phase_fractions):
            duration_estimate_s = planning_horizon_s * fraction

            # Tasks: use COA timeline if available, else generate defaults
            tasks = coa_timeline_tasks.get(idx, self._default_tasks(phase_type))

            # Transition conditions based on phase type
            conditions = self._build_transition_conditions(
                phase_type, duration_estimate_s, mission_type,
            )

            phase = OperationalPhase(
                phase_type=phase_type,
                name=_PHASE_NAMES.get(phase_type, phase_type.name),
                duration_estimate_s=duration_estimate_s,
                tasks=tasks,
                transition_conditions=conditions,
            )
            phases.append(phase)

        return phases

    def _build_transition_conditions(
        self,
        phase_type: OperationalPhaseType,
        duration_estimate_s: float,
        mission_type: int,
    ) -> list[TransitionCondition]:
        """Build transition conditions for a given phase type."""
        conditions: list[TransitionCondition] = []
        cfg = self._config

        if phase_type == OperationalPhaseType.SHAPING:
            conditions.append(TransitionCondition(
                condition_type=ConditionType.TIME_ELAPSED,
                threshold=duration_estimate_s,
                description="Shaping phase time elapsed",
            ))
            conditions.append(TransitionCondition(
                condition_type=ConditionType.OBJECTIVE_SECURED,
                threshold=0.3,
                description="Initial objectives 30% secured",
            ))

        elif phase_type == OperationalPhaseType.DECISIVE:
            conditions.append(TransitionCondition(
                condition_type=ConditionType.CASUALTIES_EXCEED,
                threshold=cfg.default_casualty_threshold,
                description=f"Enemy casualties exceed {cfg.default_casualty_threshold:.0%}",
            ))
            conditions.append(TransitionCondition(
                condition_type=ConditionType.OBJECTIVE_SECURED,
                threshold=0.7,
                description="Objectives 70% secured",
            ))

        elif phase_type == OperationalPhaseType.EXPLOITATION:
            conditions.append(TransitionCondition(
                condition_type=ConditionType.OBJECTIVE_SECURED,
                threshold=1.0,
                description="All objectives secured",
            ))
            conditions.append(TransitionCondition(
                condition_type=ConditionType.TIME_ELAPSED,
                threshold=duration_estimate_s,
                description="Exploitation phase time elapsed",
            ))
            conditions.append(TransitionCondition(
                condition_type=ConditionType.FORCE_RATIO_BELOW,
                threshold=0.5,
                description="Force ratio dropped below 0.5",
            ))

        elif phase_type == OperationalPhaseType.TRANSITION:
            # Transition is the final phase -- time-based only
            conditions.append(TransitionCondition(
                condition_type=ConditionType.TIME_ELAPSED,
                threshold=duration_estimate_s,
                description="Transition phase time elapsed",
            ))

        elif phase_type == OperationalPhaseType.PREPARATION:
            conditions.append(TransitionCondition(
                condition_type=ConditionType.TIME_ELAPSED,
                threshold=duration_estimate_s,
                description="Preparation phase time elapsed",
            ))
            conditions.append(TransitionCondition(
                condition_type=ConditionType.ENEMY_RESERVE_COMMITTED,
                threshold=1.0,
                description="Enemy attack begins (reserve committed)",
            ))

        elif phase_type == OperationalPhaseType.DEFENSE:
            conditions.append(TransitionCondition(
                condition_type=ConditionType.FORCE_RATIO_ABOVE,
                threshold=1.5,
                description="Local superiority achieved (force ratio >= 1.5)",
            ))
            conditions.append(TransitionCondition(
                condition_type=ConditionType.CASUALTIES_EXCEED,
                threshold=cfg.default_casualty_threshold,
                description=f"Enemy casualties exceed {cfg.default_casualty_threshold:.0%}",
            ))

        elif phase_type == OperationalPhaseType.COUNTERATTACK:
            conditions.append(TransitionCondition(
                condition_type=ConditionType.OBJECTIVE_SECURED,
                threshold=0.8,
                description="Battle positions restored (80%)",
            ))
            conditions.append(TransitionCondition(
                condition_type=ConditionType.TIME_ELAPSED,
                threshold=duration_estimate_s,
                description="Counterattack phase time elapsed",
            ))

        elif phase_type == OperationalPhaseType.CONSOLIDATION:
            conditions.append(TransitionCondition(
                condition_type=ConditionType.TIME_ELAPSED,
                threshold=duration_estimate_s,
                description="Consolidation phase time elapsed",
            ))

        return conditions

    def _default_tasks(self, phase_type: OperationalPhaseType) -> tuple[str, ...]:
        """Generate default task descriptions for a phase type."""
        defaults: dict[OperationalPhaseType, tuple[str, ...]] = {
            OperationalPhaseType.SHAPING: (
                "Establish surveillance",
                "Shape engagement area",
                "Suppress enemy positions",
            ),
            OperationalPhaseType.DECISIVE: (
                "Execute main effort",
                "Destroy enemy on objective",
            ),
            OperationalPhaseType.EXPLOITATION: (
                "Pursue defeated enemy",
                "Consolidate on objective",
            ),
            OperationalPhaseType.TRANSITION: (
                "Transition to follow-on mission",
                "Consolidate and reorganize",
            ),
            OperationalPhaseType.PREPARATION: (
                "Prepare defensive positions",
                "Emplace obstacles",
                "Register fire support",
            ),
            OperationalPhaseType.DEFENSE: (
                "Engage enemy in engagement area",
                "Execute fires plan",
            ),
            OperationalPhaseType.COUNTERATTACK: (
                "Commit reserve",
                "Restore battle position",
            ),
            OperationalPhaseType.CONSOLIDATION: (
                "Consolidate on positions",
                "Prepare for subsequent operations",
            ),
        }
        return defaults.get(phase_type, ("Execute phase tasks",))

    def _build_standard_branches(
        self,
        plan_id: str,
        planning_horizon_s: float,
    ) -> list[BranchPlan]:
        """Build standard branch plans included in every plan."""
        branches: list[BranchPlan] = []

        # Branch: Enemy counterattack -- triggered by force ratio dropping
        counterattack_branch = BranchPlan(
            branch_id=f"{plan_id}_branch_counterattack",
            trigger_description="Enemy counterattack",
            trigger_condition=TransitionCondition(
                condition_type=ConditionType.FORCE_RATIO_BELOW,
                threshold=0.5,
                description="Force ratio dropped below 0.5 (enemy counterattack)",
            ),
            phases=[
                OperationalPhase(
                    phase_type=OperationalPhaseType.DEFENSE,
                    name="Emergency Defense",
                    duration_estimate_s=planning_horizon_s * 0.3,
                    tasks=("Assume hasty defense", "Repel counterattack"),
                    transition_conditions=[
                        TransitionCondition(
                            condition_type=ConditionType.FORCE_RATIO_ABOVE,
                            threshold=1.0,
                            description="Force ratio restored",
                        ),
                    ],
                ),
                OperationalPhase(
                    phase_type=OperationalPhaseType.COUNTERATTACK,
                    name="Resume Offensive",
                    duration_estimate_s=planning_horizon_s * 0.4,
                    tasks=("Resume offensive operations",),
                    transition_conditions=[
                        TransitionCondition(
                            condition_type=ConditionType.TIME_ELAPSED,
                            threshold=planning_horizon_s * 0.4,
                            description="Counterattack time elapsed",
                        ),
                    ],
                ),
            ],
        )
        branches.append(counterattack_branch)

        return branches

    def _build_standard_sequels(
        self,
        plan_id: str,
        mission_type: int,
    ) -> list[SequelPlan]:
        """Build standard sequel plans based on mission type."""
        sequels: list[SequelPlan] = []

        if mission_type in _OFFENSIVE_MISSIONS:
            # Sequel: exploitation after successful attack
            sequels.append(SequelPlan(
                sequel_id=f"{plan_id}_sequel_exploit",
                description="Exploitation and pursuit",
                mission_type=int(MissionType.MOVEMENT_TO_CONTACT),
                conditions_for_initiation=[
                    TransitionCondition(
                        condition_type=ConditionType.OBJECTIVE_SECURED,
                        threshold=1.0,
                        description="All objectives secured",
                    ),
                ],
            ))
        elif mission_type in _DEFENSIVE_MISSIONS:
            # Sequel: counterattack after successful defense
            sequels.append(SequelPlan(
                sequel_id=f"{plan_id}_sequel_counterattack",
                description="Counterattack to restore positions",
                mission_type=int(MissionType.ATTACK),
                conditions_for_initiation=[
                    TransitionCondition(
                        condition_type=ConditionType.FORCE_RATIO_ABOVE,
                        threshold=1.5,
                        description="Achieve local superiority for counterattack",
                    ),
                ],
            ))
        elif mission_type in _DELAY_MISSIONS:
            # Sequel: withdraw to subsequent positions
            sequels.append(SequelPlan(
                sequel_id=f"{plan_id}_sequel_withdraw",
                description="Withdraw to subsequent position",
                mission_type=int(MissionType.WITHDRAW),
                conditions_for_initiation=[
                    TransitionCondition(
                        condition_type=ConditionType.CASUALTIES_EXCEED,
                        threshold=self._config.default_casualty_threshold,
                        description="Casualties exceed threshold",
                    ),
                ],
            ))
        else:
            # Generic sequel: transition to defense
            sequels.append(SequelPlan(
                sequel_id=f"{plan_id}_sequel_transition",
                description="Transition to hasty defense",
                mission_type=int(MissionType.DEFEND),
                conditions_for_initiation=[
                    TransitionCondition(
                        condition_type=ConditionType.TIME_ELAPSED,
                        threshold=3600.0,
                        description="Transition after 1 hour",
                    ),
                ],
            ))

        return sequels

"""Planning process orchestrator -- MDMP state machine.

Sequences the Military Decision Making Process (MDMP) and its faster
variants.  The orchestrator is a state machine that tracks which planning
phase each unit is in and manages timers.  It does NOT call sub-modules
directly -- the orchestration layer reads the current phase and calls the
appropriate module (mission_analysis, coa, phases), then injects results
via setter methods.

Planning methods by echelon (DD-6):
- Individual through Platoon: INTUITIVE (no formal planning)
- Company through Battalion: RAPID or MDMP depending on time available
- Brigade+: Full MDMP with COA development and wargaming

The 1/3-2/3 rule: commander takes 1/3 of available time for planning,
leaving 2/3 for subordinate preparation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.c2.events import (
    PlanningCompletedEvent,
    PlanningStartedEvent,
)
from stochastic_warfare.c2.orders.types import Order
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PlanningMethod(enum.IntEnum):
    """Planning methodology, ordered by formality."""

    INTUITIVE = 0
    DIRECTIVE = 1
    RAPID = 2
    MDMP = 3


class PlanningPhase(enum.IntEnum):
    """Phases of the planning process state machine."""

    IDLE = 0
    RECEIVING_MISSION = 1
    ANALYZING = 2
    DEVELOPING_COA = 3
    COMPARING = 4
    APPROVING = 5
    ISSUING_ORDERS = 6
    COMPLETE = 7


# Full MDMP phase sequence (excluding IDLE and COMPLETE, which are
# terminal / sentinel states managed outside the sequence).
_FULL_PHASE_SEQUENCE: list[PlanningPhase] = [
    PlanningPhase.RECEIVING_MISSION,
    PlanningPhase.ANALYZING,
    PlanningPhase.DEVELOPING_COA,
    PlanningPhase.COMPARING,
    PlanningPhase.APPROVING,
    PlanningPhase.ISSUING_ORDERS,
]

# Phases skipped by INTUITIVE: skip COA development, comparing, approving
_INTUITIVE_SKIP: frozenset[PlanningPhase] = frozenset({
    PlanningPhase.DEVELOPING_COA,
    PlanningPhase.COMPARING,
    PlanningPhase.APPROVING,
})

# Phases skipped by RAPID: skip formal comparison
_RAPID_SKIP: frozenset[PlanningPhase] = frozenset({
    PlanningPhase.COMPARING,
})

# Echelon thresholds
_ECHELON_PLATOON = 4
_ECHELON_COMPANY = 5
_ECHELON_BATTALION = 6
_ECHELON_BRIGADE = 8


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class PlanningProcessConfig(BaseModel):
    """Tuning parameters for the planning process state machine."""

    method_speed_multipliers: dict[str, float] = {
        "INTUITIVE": 10.0,
        "DIRECTIVE": 5.0,
        "RAPID": 3.0,
        "MDMP": 1.0,
    }
    base_phase_durations_s: dict[str, float] = {
        "RECEIVING_MISSION": 300.0,
        "ANALYZING": 1800.0,
        "DEVELOPING_COA": 3600.0,
        "COMPARING": 1200.0,
        "APPROVING": 600.0,
        "ISSUING_ORDERS": 900.0,
    }
    time_rule_fraction: float = 1.0 / 3.0  # 1/3-2/3 rule


# ---------------------------------------------------------------------------
# Internal per-unit state
# ---------------------------------------------------------------------------


@dataclass
class _PlanningState:
    """Mutable per-unit planning state (internal to the engine)."""

    unit_id: str
    method: PlanningMethod
    phase: PlanningPhase
    phase_timer: float  # remaining seconds in current phase
    total_elapsed_s: float  # total time spent planning
    available_time_s: float  # total time budget (1/3 of available)
    echelon_level: int
    order_id: str  # the order being planned for
    # Results injected by orchestration layer:
    analysis_result: Any = None  # MissionAnalysisResult
    coas: list = field(default_factory=list)  # list[COA]
    selected_coa: Any = None  # COA
    plan: Any = None  # OperationalPlan


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PlanningProcessEngine:
    """MDMP state machine for military planning processes.

    Manages per-unit planning states, timers, and phase transitions.
    The orchestration layer is responsible for calling the appropriate
    sub-module when a phase completes, then injecting results via setter
    methods before calling :meth:`advance_phase`.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``PlanningStartedEvent`` and ``PlanningCompletedEvent``.
    rng : np.random.Generator
        Deterministic RNG (reserved for future stochastic interrupts).
    config : PlanningProcessConfig | None
        Tuning parameters.  Uses defaults if ``None``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: PlanningProcessConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or PlanningProcessConfig()
        self._states: dict[str, _PlanningState] = {}

    # -- Method selection ---------------------------------------------------

    def select_method(
        self,
        echelon: int,
        available_time_s: float,
        doctrine_style: str = "HYBRID",
    ) -> PlanningMethod:
        """Select a planning method based on echelon, time, and doctrine.

        Parameters
        ----------
        echelon : int
            Echelon level (``EchelonLevel`` value).
        available_time_s : float
            Time available for all planning (before 1/3-2/3 split).
        doctrine_style : str
            ``"HYBRID"`` (default), ``"BEFEHLSTAKTIK"`` (centralized),
            or ``"AUFTRAGSTAKTIK"`` (mission command).

        Returns
        -------
        PlanningMethod
            The selected planning methodology.
        """
        # Auftragstaktik doubles the time thresholds (more willing to decide
        # quickly and delegate), so lower echelons choose less formal methods.
        time_mult = 2.0 if doctrine_style == "AUFTRAGSTAKTIK" else 1.0

        if echelon <= _ECHELON_PLATOON:
            return PlanningMethod.INTUITIVE

        if echelon <= _ECHELON_BATTALION:
            if available_time_s < 1800 * time_mult:
                method = PlanningMethod.INTUITIVE
            elif available_time_s < 7200 * time_mult:
                method = PlanningMethod.RAPID
            else:
                method = PlanningMethod.MDMP
        else:
            # Brigade and above
            if available_time_s < 3600 * time_mult:
                method = PlanningMethod.RAPID
            else:
                method = PlanningMethod.MDMP

        # Befehlstaktik: prefer DIRECTIVE over INTUITIVE for company+
        if (
            doctrine_style == "BEFEHLSTAKTIK"
            and method == PlanningMethod.INTUITIVE
            and echelon >= _ECHELON_COMPANY
        ):
            method = PlanningMethod.DIRECTIVE

        return method

    # -- Planning lifecycle -------------------------------------------------

    def initiate_planning(
        self,
        unit_id: str,
        order: Order,
        available_time_s: float,
        ts: datetime | None = None,
        doctrine_style: str = "HYBRID",
    ) -> PlanningMethod:
        """Begin a planning process for *unit_id* in response to *order*.

        Applies the 1/3-2/3 rule: the planning budget is
        ``available_time_s * config.time_rule_fraction``.

        Parameters
        ----------
        unit_id : str
            The unit initiating planning.
        order : Order
            The received order that triggers planning.
        available_time_s : float
            Total time available (before 1/3-2/3 split).
        ts : datetime | None
            Simulation timestamp for the event.
        doctrine_style : str
            Doctrine style (see :meth:`select_method`).

        Returns
        -------
        PlanningMethod
            The selected planning methodology.
        """
        method = self.select_method(
            order.echelon_level, available_time_s, doctrine_style,
        )
        planning_budget = available_time_s * self._config.time_rule_fraction

        first_phase = PlanningPhase.RECEIVING_MISSION
        phase_duration = self._compute_phase_duration(first_phase, method)
        # Cap at budget so we never exceed available time
        phase_duration = min(phase_duration, planning_budget)

        state = _PlanningState(
            unit_id=unit_id,
            method=method,
            phase=first_phase,
            phase_timer=phase_duration,
            total_elapsed_s=0.0,
            available_time_s=planning_budget,
            echelon_level=order.echelon_level,
            order_id=order.order_id,
        )
        self._states[unit_id] = state

        # Estimate total duration (sum of phases that will be executed)
        estimated_duration = self._estimate_total_duration(method)
        estimated_duration = min(estimated_duration, planning_budget)

        self._event_bus.publish(PlanningStartedEvent(
            timestamp=ts or datetime.utcnow(),
            source=ModuleId.C2,
            unit_id=unit_id,
            planning_method=method.name,
            echelon_level=order.echelon_level,
            estimated_duration_s=estimated_duration,
        ))

        logger.info(
            "Unit %s initiated %s planning for order %s (budget=%.0fs)",
            unit_id, method.name, order.order_id, planning_budget,
        )

        return method

    def update(
        self,
        dt_seconds: float,
        ts: datetime | None = None,
    ) -> list[tuple[str, PlanningPhase]]:
        """Advance all active planning timers by *dt_seconds*.

        Returns a list of ``(unit_id, completed_phase)`` pairs for units
        whose current phase timer has expired.  The orchestrator should
        inject results and call :meth:`advance_phase` for each.

        Does NOT auto-advance phases -- the orchestrator is responsible
        for that after injecting sub-module results.

        Parameters
        ----------
        dt_seconds : float
            Simulation time step.
        ts : datetime | None
            Current simulation timestamp (unused, reserved).

        Returns
        -------
        list[tuple[str, PlanningPhase]]
            Units whose current phase just completed.
        """
        completed: list[tuple[str, PlanningPhase]] = []

        for state in self._states.values():
            if state.phase in (PlanningPhase.IDLE, PlanningPhase.COMPLETE):
                continue

            state.phase_timer -= dt_seconds
            state.total_elapsed_s += dt_seconds

            if state.phase_timer <= 0.0:
                completed.append((state.unit_id, state.phase))

        return completed

    def advance_phase(self, unit_id: str) -> PlanningPhase:
        """Move *unit_id* to the next planning phase.

        Skips phases according to the selected planning method:
        - INTUITIVE: skip DEVELOPING_COA, COMPARING, APPROVING
        - RAPID: skip COMPARING
        - DIRECTIVE: same sequence as RAPID
        - MDMP: all phases

        Returns
        -------
        PlanningPhase
            The new phase (may be ISSUING_ORDERS if phases were skipped).

        Raises
        ------
        KeyError
            If *unit_id* is not currently planning.
        """
        state = self._states[unit_id]

        # Determine which phases to skip
        if state.method == PlanningMethod.INTUITIVE:
            skip = _INTUITIVE_SKIP
        elif state.method == PlanningMethod.RAPID:
            skip = _RAPID_SKIP
        else:
            skip = frozenset()

        # Find next phase in sequence
        current_idx = _FULL_PHASE_SEQUENCE.index(state.phase)
        new_phase: PlanningPhase | None = None

        for candidate in _FULL_PHASE_SEQUENCE[current_idx + 1:]:
            if candidate not in skip:
                new_phase = candidate
                break

        if new_phase is None:
            # Past the last phase in sequence -- should not happen normally,
            # as complete_planning handles the terminal transition.
            state.phase = PlanningPhase.COMPLETE
            return PlanningPhase.COMPLETE

        state.phase = new_phase
        phase_duration = self._compute_phase_duration(new_phase, state.method)
        remaining_budget = state.available_time_s - state.total_elapsed_s
        state.phase_timer = min(phase_duration, max(remaining_budget, 0.0))

        logger.debug(
            "Unit %s advanced to %s (timer=%.0fs)",
            unit_id, new_phase.name, state.phase_timer,
        )

        return new_phase

    # -- Status queries -----------------------------------------------------

    def get_planning_status(self, unit_id: str) -> PlanningPhase:
        """Return the current planning phase for *unit_id*.

        Returns ``PlanningPhase.IDLE`` if the unit is not planning.
        """
        state = self._states.get(unit_id)
        if state is None:
            return PlanningPhase.IDLE
        return state.phase

    def get_method(self, unit_id: str) -> PlanningMethod | None:
        """Return the planning method for *unit_id*, or ``None``."""
        state = self._states.get(unit_id)
        if state is None:
            return None
        return state.method

    # -- Result injection (called by orchestration layer) -------------------

    def set_analysis_result(self, unit_id: str, result: Any) -> None:
        """Inject mission analysis result for *unit_id*."""
        self._states[unit_id].analysis_result = result

    def set_coas(self, unit_id: str, coas: list) -> None:
        """Inject developed COAs for *unit_id*."""
        self._states[unit_id].coas = coas

    def set_selected_coa(self, unit_id: str, coa: Any) -> None:
        """Inject the selected COA for *unit_id*."""
        self._states[unit_id].selected_coa = coa

    def set_plan(self, unit_id: str, plan: Any) -> None:
        """Inject the operational plan for *unit_id*."""
        self._states[unit_id].plan = plan

    # -- Terminal transitions -----------------------------------------------

    def complete_planning(
        self,
        unit_id: str,
        ts: datetime | None = None,
    ) -> None:
        """Mark planning as complete and publish ``PlanningCompletedEvent``.

        Parameters
        ----------
        unit_id : str
            The unit whose planning is complete.
        ts : datetime | None
            Simulation timestamp for the event.
        """
        state = self._states[unit_id]
        state.phase = PlanningPhase.COMPLETE

        # Extract COA info for the event
        selected_coa_id = ""
        if state.selected_coa is not None:
            selected_coa_id = getattr(state.selected_coa, "coa_id", str(state.selected_coa))
        num_coas = len(state.coas)

        self._event_bus.publish(PlanningCompletedEvent(
            timestamp=ts or datetime.utcnow(),
            source=ModuleId.C2,
            unit_id=unit_id,
            planning_method=state.method.name,
            selected_coa_id=selected_coa_id,
            duration_s=state.total_elapsed_s,
            num_coas_evaluated=num_coas,
        ))

        logger.info(
            "Unit %s completed %s planning in %.0fs (%d COAs evaluated)",
            unit_id, state.method.name, state.total_elapsed_s, num_coas,
        )

    def cancel_planning(self, unit_id: str) -> None:
        """Cancel planning for *unit_id* (e.g., superseded order).

        Resets the unit's state to IDLE and removes it from active tracking.
        """
        if unit_id in self._states:
            logger.info("Unit %s planning cancelled", unit_id)
            del self._states[unit_id]

    # -- Checkpoint / restore -----------------------------------------------

    def get_state(self) -> dict:
        """Serialize engine state for checkpoint/restore."""
        states = {}
        for uid, s in self._states.items():
            states[uid] = {
                "unit_id": s.unit_id,
                "method": int(s.method),
                "phase": int(s.phase),
                "phase_timer": s.phase_timer,
                "total_elapsed_s": s.total_elapsed_s,
                "available_time_s": s.available_time_s,
                "echelon_level": s.echelon_level,
                "order_id": s.order_id,
                # analysis_result, coas, selected_coa, plan are transient --
                # they would need domain-specific serializers if we wanted
                # full checkpoint support.  For now we store None markers.
                "has_analysis": s.analysis_result is not None,
                "num_coas": len(s.coas),
                "has_selected_coa": s.selected_coa is not None,
                "has_plan": s.plan is not None,
            }
        return {
            "config": self._config.model_dump(),
            "states": states,
        }

    def set_state(self, state: dict) -> None:
        """Restore engine state from checkpoint."""
        self._config = PlanningProcessConfig(**state["config"])
        self._states.clear()
        for uid, s in state["states"].items():
            ps = _PlanningState(
                unit_id=s["unit_id"],
                method=PlanningMethod(s["method"]),
                phase=PlanningPhase(s["phase"]),
                phase_timer=s["phase_timer"],
                total_elapsed_s=s["total_elapsed_s"],
                available_time_s=s["available_time_s"],
                echelon_level=s["echelon_level"],
                order_id=s["order_id"],
            )
            self._states[uid] = ps

    # -- Internal helpers ---------------------------------------------------

    def _compute_phase_duration(
        self,
        phase: PlanningPhase,
        method: PlanningMethod,
    ) -> float:
        """Compute duration for a planning phase given the method speed."""
        base = self._config.base_phase_durations_s.get(phase.name, 600.0)
        speed_mult = self._config.method_speed_multipliers.get(method.name, 1.0)
        return base / speed_mult

    def _estimate_total_duration(self, method: PlanningMethod) -> float:
        """Estimate total planning duration for the given method."""
        if method == PlanningMethod.INTUITIVE:
            skip = _INTUITIVE_SKIP
        elif method == PlanningMethod.RAPID:
            skip = _RAPID_SKIP
        else:
            skip = frozenset()

        total = 0.0
        for phase in _FULL_PHASE_SEQUENCE:
            if phase not in skip:
                total += self._compute_phase_duration(phase, method)
        return total

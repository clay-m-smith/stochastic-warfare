"""Command authority engine — status tracking, succession, and effectiveness.

Models the 4-state command authority machine:
``FULLY_OPERATIONAL → DEGRADED → DISRUPTED → DESTROYED``.

When a commander is lost, succession follows a priority list
(XO → S3 → senior subordinate) with a log-normal delay during which
the unit operates at reduced effectiveness. Communications loss degrades
authority; restoration can recover it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.events import (
    CommandStatusChangeEvent,
    SuccessionEvent,
)
from stochastic_warfare.entities.organization.hierarchy import HierarchyTree
from stochastic_warfare.entities.organization.task_org import (
    CommandRelationship,
    TaskOrgManager,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & config
# ---------------------------------------------------------------------------


class CommandStatus(enum.IntEnum):
    """Command authority state machine."""

    FULLY_OPERATIONAL = 0
    DEGRADED = 1
    DISRUPTED = 2
    DESTROYED = 3


class CommandConfig(BaseModel):
    """Tuning parameters for the command authority engine."""

    succession_delay_mean_s: float = 300.0  # 5 min mean
    succession_delay_sigma: float = 0.5  # log-normal σ
    degraded_effectiveness_mult: float = 0.6
    disrupted_effectiveness_mult: float = 0.2
    destroyed_effectiveness_mult: float = 0.0
    recovery_time_s: float = 600.0  # Time for DISRUPTED → DEGRADED


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


@dataclass
class _UnitCommandState:
    """Tracks command status for a single unit."""

    unit_id: str
    commander_id: str
    status: CommandStatus = CommandStatus.FULLY_OPERATIONAL
    succession_timer: float = 0.0  # Remaining time for succession
    succession_target_id: str = ""  # Who is taking over
    comms_lost: bool = False
    recovery_timer: float = 0.0  # For DISRUPTED → DEGRADED recovery


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CommandEngine:
    """Manages command authority, succession, and C2 effectiveness.

    Parameters
    ----------
    hierarchy : HierarchyTree
        Organic chain of command.
    task_org : TaskOrgManager
        Task-organization overlay for authority checks.
    staff_capabilities : dict[str, object]
        Maps unit_id → StaffCapabilities. Used for planning time modifiers.
    event_bus : EventBus
        Publishes ``CommandStatusChangeEvent``, ``SuccessionEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream (from ``RNGManager.get_stream(ModuleId.C2)``).
    config : CommandConfig | None
        Tuning parameters. Uses defaults if ``None``.
    """

    def __init__(
        self,
        hierarchy: HierarchyTree,
        task_org: TaskOrgManager,
        staff_capabilities: dict[str, object],
        event_bus: EventBus,
        rng: np.random.Generator,
        config: CommandConfig | None = None,
    ) -> None:
        self._hierarchy = hierarchy
        self._task_org = task_org
        self._staff = staff_capabilities
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or CommandConfig()
        self._units: dict[str, _UnitCommandState] = {}
        self._sim_time: float = 0.0

    # -- Registration -------------------------------------------------------

    def register_unit(self, unit_id: str, commander_id: str) -> None:
        """Register a unit with its initial commander."""
        self._units[unit_id] = _UnitCommandState(
            unit_id=unit_id, commander_id=commander_id,
        )

    # -- Queries ------------------------------------------------------------

    def get_status(self, unit_id: str) -> CommandStatus:
        """Return current command status for *unit_id*."""
        return self._units[unit_id].status

    def get_effectiveness(self, unit_id: str) -> float:
        """Return command effectiveness multiplier (0.0–1.0)."""
        s = self._units[unit_id]
        if s.succession_timer > 0:
            # During succession, use disrupted effectiveness
            return self._config.disrupted_effectiveness_mult
        mult_map = {
            CommandStatus.FULLY_OPERATIONAL: 1.0,
            CommandStatus.DEGRADED: self._config.degraded_effectiveness_mult,
            CommandStatus.DISRUPTED: self._config.disrupted_effectiveness_mult,
            CommandStatus.DESTROYED: self._config.destroyed_effectiveness_mult,
        }
        return mult_map[s.status]

    def get_commander(self, unit_id: str) -> str:
        """Return the current commander_id for *unit_id*."""
        return self._units[unit_id].commander_id

    # -- Event handlers -----------------------------------------------------

    def handle_commander_loss(
        self,
        unit_id: str,
        timestamp: datetime,
    ) -> None:
        """Handle the loss of a unit's commander (KIA/WIA/captured).

        Triggers succession: XO → S3 → senior subordinate.
        Publishes ``SuccessionEvent`` and ``CommandStatusChangeEvent``.
        """
        s = self._units[unit_id]
        old_status = s.status
        old_commander = s.commander_id

        # Find successor
        successor = self._find_successor(unit_id)
        if successor is None:
            # No viable successor — unit is destroyed as C2 entity
            self._transition(s, CommandStatus.DESTROYED, "commander_kia", timestamp)
            return

        # Calculate succession delay (log-normal)
        delay = float(self._rng.lognormal(
            np.log(self._config.succession_delay_mean_s),
            self._config.succession_delay_sigma,
        ))

        s.succession_timer = delay
        s.succession_target_id = successor

        # Immediately degrade to DISRUPTED during succession
        if old_status < CommandStatus.DISRUPTED:
            self._transition(s, CommandStatus.DISRUPTED, "commander_kia", timestamp)

        self._event_bus.publish(SuccessionEvent(
            timestamp=timestamp, source=ModuleId.C2,
            unit_id=unit_id,
            old_commander_id=old_commander,
            new_commander_id=successor,
            succession_delay_s=delay,
        ))
        logger.info(
            "Succession triggered for %s: %s → %s (delay %.0fs)",
            unit_id, old_commander, successor, delay,
        )

    def handle_hq_destroyed(
        self,
        unit_id: str,
        timestamp: datetime,
    ) -> None:
        """Handle destruction of a unit's headquarters element."""
        s = self._units[unit_id]
        self._transition(s, CommandStatus.DESTROYED, "hq_destroyed", timestamp)

    def handle_comms_loss(
        self,
        unit_id: str,
        timestamp: datetime,
    ) -> None:
        """Handle loss of communications (degrades command status)."""
        s = self._units[unit_id]
        s.comms_lost = True
        if s.status == CommandStatus.FULLY_OPERATIONAL:
            self._transition(s, CommandStatus.DEGRADED, "comms_loss", timestamp)
        elif s.status == CommandStatus.DEGRADED:
            self._transition(s, CommandStatus.DISRUPTED, "comms_loss", timestamp)

    def handle_comms_restored(
        self,
        unit_id: str,
        timestamp: datetime,
    ) -> None:
        """Handle restoration of communications."""
        s = self._units[unit_id]
        s.comms_lost = False
        if s.status == CommandStatus.DISRUPTED and s.succession_timer <= 0:
            self._transition(s, CommandStatus.DEGRADED, "recovery", timestamp)
            s.recovery_timer = self._config.recovery_time_s

    # -- Update loop --------------------------------------------------------

    def update(self, dt_seconds: float, timestamp: datetime) -> None:
        """Advance succession timers and recovery timers."""
        self._sim_time += dt_seconds
        for s in self._units.values():
            remaining = dt_seconds

            # Succession timer countdown
            if s.succession_timer > 0:
                old_timer = s.succession_timer
                s.succession_timer -= dt_seconds
                if s.succession_timer <= 0:
                    remaining = -s.succession_timer  # Time left after succession
                    s.succession_timer = 0
                    s.commander_id = s.succession_target_id
                    s.succession_target_id = ""
                    # Recover to DEGRADED (not fully operational yet)
                    if s.status == CommandStatus.DISRUPTED:
                        self._transition(
                            s, CommandStatus.DEGRADED, "recovery", timestamp,
                        )
                        s.recovery_timer = self._config.recovery_time_s
                else:
                    remaining = 0  # All time consumed by succession wait

            # Recovery timer (DEGRADED → FULLY_OPERATIONAL)
            if s.recovery_timer > 0 and s.status == CommandStatus.DEGRADED:
                s.recovery_timer -= remaining
                if s.recovery_timer <= 0 and not s.comms_lost:
                    s.recovery_timer = 0
                    self._transition(
                        s, CommandStatus.FULLY_OPERATIONAL, "recovery", timestamp,
                    )

    # -- Authority checks ---------------------------------------------------

    def can_issue_order(self, issuer_id: str, recipient_id: str) -> bool:
        """Check if *issuer_id* has authority to issue orders to *recipient_id*.

        OPCON and ORGANIC grant order authority. TACON grants tactical-only.
        ADCON does not grant operational authority.
        """
        if issuer_id not in self._units:
            return False
        if self._units[issuer_id].status == CommandStatus.DESTROYED:
            return False

        # Check chain of command: issuer must be in recipient's CoC,
        # or have OPCON/TACON via task org
        relationship = self._task_org.get_relationship(recipient_id)
        effective_parent = self._task_org.get_effective_parent(recipient_id)

        if effective_parent == issuer_id:
            return relationship in (
                CommandRelationship.ORGANIC,
                CommandRelationship.OPCON,
                CommandRelationship.TACON,
            )

        # Check if issuer is higher in CoC
        coc = self._hierarchy.get_chain_of_command(recipient_id)
        return issuer_id in coc

    # -- Internal -----------------------------------------------------------

    def _find_successor(self, unit_id: str) -> str | None:
        """Find succession candidate: XO → S3 → senior subordinate."""
        # In this model, we use a simple priority-based succession:
        # 1. First registered subordinate (proxy for XO)
        # 2. Second registered subordinate (proxy for S3)
        # If unit has children in hierarchy, use the first child
        children = self._hierarchy.get_children(unit_id)
        if children:
            return children[0]

        # Check siblings (peer units under same parent)
        siblings = self._hierarchy.get_siblings(unit_id)
        if siblings:
            return siblings[0]

        return None

    def _transition(
        self,
        state: _UnitCommandState,
        new_status: CommandStatus,
        cause: str,
        timestamp: datetime,
    ) -> None:
        """Transition a unit's command status and publish event."""
        old_status = state.status
        if old_status == new_status:
            return
        state.status = new_status
        self._event_bus.publish(CommandStatusChangeEvent(
            timestamp=timestamp, source=ModuleId.C2,
            unit_id=state.unit_id,
            old_status=int(old_status),
            new_status=int(new_status),
            cause=cause,
        ))
        logger.info(
            "C2 status %s: %s → %s (cause: %s)",
            state.unit_id, old_status.name, new_status.name, cause,
        )

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        """Serialize for checkpoint/restore."""
        return {
            "sim_time": self._sim_time,
            "units": {
                uid: {
                    "unit_id": s.unit_id,
                    "commander_id": s.commander_id,
                    "status": int(s.status),
                    "succession_timer": s.succession_timer,
                    "succession_target_id": s.succession_target_id,
                    "comms_lost": s.comms_lost,
                    "recovery_timer": s.recovery_timer,
                }
                for uid, s in self._units.items()
            },
        }

    def set_state(self, state: dict) -> None:
        """Restore from checkpoint."""
        self._sim_time = state["sim_time"]
        self._units.clear()
        for uid, sd in state["units"].items():
            self._units[uid] = _UnitCommandState(
                unit_id=sd["unit_id"],
                commander_id=sd["commander_id"],
                status=CommandStatus(sd["status"]),
                succession_timer=sd["succession_timer"],
                succession_target_id=sd["succession_target_id"],
                comms_lost=sd["comms_lost"],
                recovery_timer=sd["recovery_timer"],
            )

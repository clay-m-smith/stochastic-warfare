"""Mount / dismount state machine for mechanized units."""

from __future__ import annotations

import enum
from typing import NamedTuple

from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import Seconds

logger = get_logger(__name__)


class MountState(enum.IntEnum):
    """Possible mount/dismount states."""

    MOUNTED = 0
    DISMOUNTING = 1
    DISMOUNTED = 2
    MOUNTING = 3


class MountTransitionResult(NamedTuple):
    """Result of a mount/dismount update tick."""

    new_state: MountState
    time_elapsed: Seconds
    complete: bool


# Transition times in seconds
_DISMOUNT_TIME: float = 30.0  # 30 seconds
_MOUNT_TIME: float = 45.0  # 45 seconds


class MountDismountManager:
    """Manage mount/dismount transitions for mechanized units."""

    def __init__(self) -> None:
        self._progress: dict[str, float] = {}  # unit_id -> seconds elapsed

    def transition_time(self, unit, action: str) -> Seconds:
        """Return seconds needed to mount or dismount *unit*.

        Parameters
        ----------
        action:
            "mount" or "dismount".
        """
        if action == "dismount":
            return _DISMOUNT_TIME
        return _MOUNT_TIME

    def begin_dismount(self, unit) -> MountTransitionResult:
        """Start dismounting *unit*."""
        uid = unit.entity_id
        self._progress[uid] = 0.0
        return MountTransitionResult(MountState.DISMOUNTING, 0.0, False)

    def begin_mount(self, unit) -> MountTransitionResult:
        """Start mounting *unit*."""
        uid = unit.entity_id
        self._progress[uid] = 0.0
        return MountTransitionResult(MountState.MOUNTING, 0.0, False)

    def update(self, unit, dt: Seconds) -> MountTransitionResult:
        """Advance mount/dismount transition by *dt* seconds."""
        uid = unit.entity_id
        if uid not in self._progress:
            # No transition in progress
            state = MountState.MOUNTED if getattr(unit, "mounted", True) else MountState.DISMOUNTED
            return MountTransitionResult(state, 0.0, True)

        self._progress[uid] += dt
        elapsed = self._progress[uid]

        # Determine which transition we're in
        if getattr(unit, "mounted", True):
            # Currently mounted → dismounting
            if elapsed >= _DISMOUNT_TIME:
                del self._progress[uid]
                return MountTransitionResult(MountState.DISMOUNTED, elapsed, True)
            return MountTransitionResult(MountState.DISMOUNTING, elapsed, False)
        else:
            # Currently dismounted → mounting
            if elapsed >= _MOUNT_TIME:
                del self._progress[uid]
                return MountTransitionResult(MountState.MOUNTED, elapsed, True)
            return MountTransitionResult(MountState.MOUNTING, elapsed, False)

    def get_state(self) -> dict:
        return {"progress": dict(self._progress)}

    def set_state(self, state: dict) -> None:
        self._progress = dict(state["progress"])

"""OODA loop engine -- Boyd's Observe-Orient-Decide-Act cycle.

Tracks per-commander OODA state as a pure timer/state machine. Phase
durations scale with echelon level (platoon faster than division) and are
modulated by staff quality, C2 effectiveness, and personality. Log-normal
timing variation (sigma=0.3) models Clausewitzian friction.

The OODA engine does NOT call assessment, planning, or decision modules
directly. The orchestration layer reads OODA state and calls the
appropriate module. This keeps each module independently testable.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.c2.events import OODALoopResetEvent, OODAPhaseChangeEvent
from stochastic_warfare.entities.organization.echelons import EchelonLevel

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OODAPhase(enum.IntEnum):
    """Boyd's OODA loop phases."""

    OBSERVE = 0
    ORIENT = 1
    DECIDE = 2
    ACT = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class OODAConfig(BaseModel):
    """Tuning parameters for the OODA loop engine."""

    base_durations_s: dict[str, dict[str, float]] = {
        "PLATOON": {"OBSERVE": 30, "ORIENT": 60, "DECIDE": 30, "ACT": 30},
        "COMPANY": {"OBSERVE": 60, "ORIENT": 180, "DECIDE": 120, "ACT": 60},
        "BATTALION": {"OBSERVE": 300, "ORIENT": 900, "DECIDE": 600, "ACT": 300},
        "BRIGADE": {"OBSERVE": 600, "ORIENT": 1800, "DECIDE": 1200, "ACT": 600},
        "DIVISION": {"OBSERVE": 1800, "ORIENT": 3600, "DECIDE": 3600, "ACT": 1800},
        "CORPS": {"OBSERVE": 3600, "ORIENT": 7200, "DECIDE": 7200, "ACT": 3600},
    }
    timing_sigma: float = 0.3  # log-normal sigma for friction
    degraded_mult: float = 1.5  # C2 degraded multiplier
    disrupted_mult: float = 3.0  # C2 disrupted multiplier
    tactical_acceleration: float = 0.5  # multiplier for tactical OODA (<1 = faster)


# ---------------------------------------------------------------------------
# Echelon-to-config mapping
# ---------------------------------------------------------------------------

# Maps EchelonLevel int values to the config key they should use.
_ECHELON_CONFIG_KEY: dict[int, str] = {
    EchelonLevel.INDIVIDUAL: "PLATOON",
    EchelonLevel.FIRE_TEAM: "PLATOON",
    EchelonLevel.SQUAD: "PLATOON",
    EchelonLevel.SECTION: "PLATOON",
    EchelonLevel.PLATOON: "PLATOON",
    EchelonLevel.COMPANY: "COMPANY",
    EchelonLevel.BATTALION: "BATTALION",
    EchelonLevel.REGIMENT: "BATTALION",
    EchelonLevel.BRIGADE: "BRIGADE",
    EchelonLevel.DIVISION: "DIVISION",
    EchelonLevel.CORPS: "CORPS",
    EchelonLevel.ARMY: "CORPS",
    EchelonLevel.ARMY_GROUP: "CORPS",
    EchelonLevel.THEATER: "CORPS",
}


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


@dataclass
class _OODAState:
    """Per-commander OODA loop state."""

    phase: OODAPhase
    phase_timer: float  # time remaining in current phase (-1 = not started)
    phase_duration: float  # total duration of current phase
    cycle_count: int
    echelon_level: int


@dataclass(frozen=True)
class OODAStatePlan:
    """Validated immutable checkpoint payload for OODA commander state."""

    commanders: tuple[
        tuple[str, OODAPhase, float, float, int, int],
        ...,
    ]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class OODALoopEngine:
    """Manages per-commander OODA loop state as a pure timer/state machine.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``OODAPhaseChangeEvent`` and ``OODALoopResetEvent``.
    rng : numpy.random.Generator
        Deterministic PRNG stream (from ``RNGManager.get_stream(ModuleId.C2)``).
    config : OODAConfig | None
        Tuning parameters. Uses defaults if ``None``.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: OODAConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or OODAConfig()
        self._commanders: dict[str, _OODAState] = {}

    # -- Registration -------------------------------------------------------

    def register_commander(self, unit_id: str, echelon_level: int) -> None:
        """Register a commander, starting at OBSERVE with timer=-1 (not started).

        Parameters
        ----------
        unit_id : str
            Unique identifier for the commanding unit.
        echelon_level : int
            ``EchelonLevel`` integer value (e.g. ``EchelonLevel.BATTALION``).
        """
        if (
            not isinstance(unit_id, str)
            or not unit_id
            or unit_id != unit_id.strip()
        ):
            raise ValueError(
                "OODA commander unit IDs must be non-empty trimmed strings",
            )
        if unit_id in self._commanders:
            raise ValueError(
                f"OODA commander {unit_id!r} is already registered",
            )
        if (
            isinstance(echelon_level, bool)
            or not isinstance(echelon_level, int)
        ):
            raise ValueError("OODA echelon_level must be a strict integer")
        try:
            echelon = EchelonLevel(echelon_level)
        except ValueError as exc:
            raise ValueError(
                f"Unknown OODA echelon_level {echelon_level!r}",
            ) from exc
        self._commanders[unit_id] = _OODAState(
            phase=OODAPhase.OBSERVE,
            phase_timer=-1.0,
            phase_duration=0.0,
            cycle_count=0,
            echelon_level=int(echelon),
        )
        logger.debug("Registered OODA commander %s (echelon=%d)", unit_id, echelon_level)

    # -- Duration computation -----------------------------------------------

    def compute_phase_duration(
        self,
        echelon: int,
        phase: OODAPhase,
        staff_quality: float = 1.0,
        c2_multiplier: float = 1.0,
        personality_mult: float = 1.0,
        tactical_mult: float = 1.0,
    ) -> float:
        """Compute the duration (seconds) for a given OODA phase.

        Parameters
        ----------
        echelon : int
            ``EchelonLevel`` integer value.
        phase : OODAPhase
            Which OODA phase to compute for.
        staff_quality : float
            Higher = faster (divisor). 1.0 = baseline.
        c2_multiplier : float
            >1 = slower (degraded/disrupted C2). 1.0 = baseline.
        personality_mult : float
            Commander personality modifier. 1.0 = baseline.
        tactical_mult : float
            <1 = faster (tactical acceleration during battles). 1.0 = baseline.

        Returns
        -------
        float
            Phase duration in seconds with log-normal variation applied.
        """
        config_key = _ECHELON_CONFIG_KEY.get(echelon, "CORPS")
        phase_name = phase.name
        base = self._config.base_durations_s[config_key][phase_name]

        # Apply modifiers: c2, personality, tactical increase/decrease duration; staff decreases
        duration = base * c2_multiplier * personality_mult * tactical_mult / staff_quality

        # Apply log-normal variation for Clausewitzian friction
        duration = duration * float(self._rng.lognormal(0, self._config.timing_sigma))

        return duration

    # -- Phase control ------------------------------------------------------

    def start_phase(
        self,
        unit_id: str,
        phase: OODAPhase,
        staff_quality: float = 1.0,
        c2_multiplier: float = 1.0,
        personality_mult: float = 1.0,
        tactical_mult: float = 1.0,
        ts: datetime | None = None,
        *,
        publish_event: bool = True,
    ) -> None:
        """Start a specific OODA phase for a commander.

        Computes the duration with variation and publishes an
        ``OODAPhaseChangeEvent``.

        Parameters
        ----------
        unit_id : str
            Commander unit ID (must be registered).
        phase : OODAPhase
            Phase to start.
        staff_quality : float
            Higher = faster (divisor).
        c2_multiplier : float
            >1 = slower.
        personality_mult : float
            Commander personality modifier.
        tactical_mult : float
            <1 = faster (tactical acceleration during battles). 1.0 = baseline.
        ts : datetime | None
            Simulation timestamp for the event. Uses ``datetime.now()`` if None.
        """
        state = self._commanders[unit_id]
        old_phase = state.phase

        duration = self.compute_phase_duration(
            state.echelon_level,
            phase,
            staff_quality=staff_quality,
            c2_multiplier=c2_multiplier,
            personality_mult=personality_mult,
            tactical_mult=tactical_mult,
        )

        state.phase = phase
        state.phase_timer = duration
        state.phase_duration = duration

        if publish_event:
            timestamp = ts or datetime.now()
            self._event_bus.publish(OODAPhaseChangeEvent(
                timestamp=timestamp,
                source=ModuleId.C2,
                unit_id=unit_id,
                old_phase=int(old_phase),
                new_phase=int(phase),
                cycle_number=state.cycle_count,
            ))

        logger.debug(
            "OODA %s: started %s (%.1fs, cycle %d)",
            unit_id, phase.name, duration, state.cycle_count,
        )

    # -- Update loop --------------------------------------------------------

    def update(
        self,
        dt_seconds: float,
        ts: datetime | None = None,
    ) -> list[tuple[str, OODAPhase]]:
        """Advance all active OODA timers by *dt_seconds*.

        Parameters
        ----------
        dt_seconds : float
            Time step in seconds.
        ts : datetime | None
            Simulation timestamp (unused here, reserved for future use).

        Returns
        -------
        list[tuple[str, OODAPhase]]
            List of ``(unit_id, completed_phase)`` for commanders whose
            current phase timer has expired. The engine does **not**
            auto-advance to the next phase -- the orchestrator handles that.
        """
        completed: list[tuple[str, OODAPhase]] = []

        for unit_id, state in self._commanders.items():
            if state.phase_timer <= 0:
                # Timer not started or already expired -- skip
                continue
            state.phase_timer -= dt_seconds
            if state.phase_timer <= 0:
                # Phase completed
                completed.append((unit_id, state.phase))
                logger.debug(
                    "OODA %s: completed %s (cycle %d)",
                    unit_id, state.phase.name, state.cycle_count,
                )

        return completed

    def expired_phases(self) -> tuple[tuple[str, OODAPhase], ...]:
        """Return started phases that remain expired and unacknowledged.

        The orchestrator normally acknowledges a completion immediately by
        advancing the commander to its next phase.  A DECIDE phase may instead
        be deferred while planning or order propagation completes.  Such a
        phase deliberately keeps its expired timer so it can be polled on a
        later logical interval without recomputing a duration or consuming an
        additional RNG draw.

        Registration/reset sentinels have ``phase_duration == 0`` and are not
        completions.  Sorting by commander identity makes the retry order
        independent of insertion history and checkpoint reconstruction.
        """
        return tuple(
            (unit_id, state.phase)
            for unit_id, state in sorted(self._commanders.items())
            if state.phase_duration > 0.0 and state.phase_timer <= 0.0
        )

    # -- Properties ---------------------------------------------------------

    @property
    def tactical_acceleration(self) -> float:
        """Tactical OODA acceleration multiplier (< 1.0 = faster)."""
        return self._config.tactical_acceleration

    @property
    def commander_ids(self) -> tuple[str, ...]:
        """Return registered commander identities in update order."""
        return tuple(self._commanders)

    # -- Queries ------------------------------------------------------------

    def get_phase(self, unit_id: str) -> OODAPhase:
        """Return current OODA phase for *unit_id*."""
        return self._commanders[unit_id].phase

    def get_cycle_count(self, unit_id: str) -> int:
        """Return number of completed OODA cycles for *unit_id*."""
        return self._commanders[unit_id].cycle_count

    # -- Loop control -------------------------------------------------------

    def reset_loop(
        self,
        unit_id: str,
        cause: str,
        ts: datetime | None = None,
    ) -> None:
        """Reset a commander's OODA loop back to OBSERVE.

        Increments the cycle count and publishes ``OODALoopResetEvent``.

        Parameters
        ----------
        unit_id : str
            Commander to reset.
        cause : str
            Reason for the reset (e.g. ``"surprise_contact"``,
            ``"c2_disruption"``, ``"frago_received"``).
        ts : datetime | None
            Simulation timestamp for the event.
        """
        state = self._commanders[unit_id]
        state.phase = OODAPhase.OBSERVE
        state.phase_timer = -1.0
        state.phase_duration = 0.0
        state.cycle_count += 1

        timestamp = ts or datetime.now()
        self._event_bus.publish(OODALoopResetEvent(
            timestamp=timestamp,
            source=ModuleId.C2,
            unit_id=unit_id,
            cause=cause,
            cycle_number=state.cycle_count,
        ))

        logger.info(
            "OODA %s: loop reset (cause=%s, cycle=%d)",
            unit_id, cause, state.cycle_count,
        )

    def advance_phase(self, unit_id: str) -> OODAPhase:
        """Advance a commander to the next OODA phase.

        OBSERVE -> ORIENT -> DECIDE -> ACT -> OBSERVE (wraps).
        Increments cycle_count when wrapping from ACT to OBSERVE.

        Parameters
        ----------
        unit_id : str
            Commander to advance.

        Returns
        -------
        OODAPhase
            The new phase after advancement.
        """
        state = self._commanders[unit_id]
        old_phase = state.phase

        if old_phase == OODAPhase.ACT:
            state.phase = OODAPhase.OBSERVE
            state.cycle_count += 1
        else:
            state.phase = OODAPhase(int(old_phase) + 1)

        # Reset timer so start_phase can be called by orchestrator
        state.phase_timer = -1.0
        state.phase_duration = 0.0

        return state.phase

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        """Serialize engine state for checkpoint/restore."""
        return {
            "commanders": {
                uid: {
                    "phase": int(s.phase),
                    "phase_timer": s.phase_timer,
                    "phase_duration": s.phase_duration,
                    "cycle_count": s.cycle_count,
                    "echelon_level": s.echelon_level,
                }
                for uid, s in sorted(self._commanders.items())
            },
        }

    def stage_state(
        self,
        state: Mapping[str, Any],
        *,
        expected_unit_ids: set[str] | None = None,
    ) -> OODAStatePlan:
        """Validate checkpoint state without mutating live commanders."""
        if set(state) != {"commanders"}:
            raise ValueError(
                "OODA checkpoint state must contain only commanders",
            )
        raw_commanders = state["commanders"]
        if not isinstance(raw_commanders, Mapping):
            raise ValueError("OODA checkpoint commanders must be a mapping")
        commander_ids = set(raw_commanders)
        if (
            expected_unit_ids is not None
            and commander_ids != expected_unit_ids
        ):
            raise ValueError(
                "OODA commander topology must match the exact runtime "
                f"roster: missing={sorted(expected_unit_ids - commander_ids)!r}, "
                f"extra={sorted(commander_ids - expected_unit_ids)!r}",
            )
        staged: list[
            tuple[str, OODAPhase, float, float, int, int]
        ] = []
        expected_fields = {
            "phase",
            "phase_timer",
            "phase_duration",
            "cycle_count",
            "echelon_level",
        }
        for unit_id, raw in sorted(raw_commanders.items()):
            if (
                not isinstance(unit_id, str)
                or not unit_id
                or unit_id != unit_id.strip()
            ):
                raise ValueError(
                    "OODA commander unit IDs must be non-empty trimmed "
                    "strings",
                )
            if not isinstance(raw, Mapping) or set(raw) != expected_fields:
                raise ValueError(
                    f"OODA commander {unit_id!r} has invalid state fields",
                )
            phase_value = raw["phase"]
            if isinstance(phase_value, bool) or not isinstance(
                phase_value,
                int,
            ):
                raise ValueError("OODA phase must be a strict integer")
            try:
                phase = OODAPhase(phase_value)
            except ValueError as exc:
                raise ValueError(
                    f"OODA commander {unit_id!r} has invalid phase",
                ) from exc
            phase_timer = self._finite_state_float(
                raw["phase_timer"],
                field_name="phase_timer",
            )
            phase_duration = self._finite_state_float(
                raw["phase_duration"],
                field_name="phase_duration",
            )
            if phase_duration < 0.0:
                raise ValueError("OODA phase_duration must be non-negative")
            if phase_timer > phase_duration:
                raise ValueError(
                    "OODA phase_timer may not exceed phase_duration",
                )
            if phase_duration == 0.0 and phase_timer != -1.0:
                raise ValueError(
                    "OODA zero-duration state requires phase_timer=-1",
                )
            cycle_count = raw["cycle_count"]
            if (
                isinstance(cycle_count, bool)
                or not isinstance(cycle_count, int)
                or cycle_count < 0
            ):
                raise ValueError(
                    "OODA cycle_count must be a non-negative strict integer",
                )
            echelon_value = raw["echelon_level"]
            if isinstance(echelon_value, bool) or not isinstance(
                echelon_value,
                int,
            ):
                raise ValueError(
                    "OODA echelon_level must be a strict integer",
                )
            try:
                echelon = EchelonLevel(echelon_value)
            except ValueError as exc:
                raise ValueError(
                    f"OODA commander {unit_id!r} has invalid echelon_level",
                ) from exc
            staged.append((
                unit_id,
                phase,
                phase_timer,
                phase_duration,
                cycle_count,
                int(echelon),
            ))
        return OODAStatePlan(tuple(staged))

    @staticmethod
    def _finite_state_float(value: Any, *, field_name: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError(
                f"OODA {field_name} must be a finite number",
            )
        return float(value)

    def commit_state(self, plan: OODAStatePlan) -> None:
        """Replace live commander state with a validated checkpoint plan."""
        self._commanders = {
            unit_id: _OODAState(
                phase=phase,
                phase_timer=phase_timer,
                phase_duration=phase_duration,
                cycle_count=cycle_count,
                echelon_level=echelon_level,
            )
            for (
                unit_id,
                phase,
                phase_timer,
                phase_duration,
                cycle_count,
                echelon_level,
            ) in plan.commanders
        }

    def set_state(self, state: Mapping[str, Any]) -> None:
        """Restore independently validated commander state."""
        self.commit_state(self.stage_state(state))

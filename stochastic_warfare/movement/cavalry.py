"""Napoleonic cavalry charge — multi-phase state machine.

A cavalry charge proceeds through phases: WALK → TROT → GALLOP → CHARGE →
IMPACT → PURSUIT → RALLY.  Phase transitions are distance-driven (gallop
at 150 m, charge at 50 m).  Fatigue accumulates at gallop+ rates.  Rally
takes 120 s (cavalry is disordered after a charge).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ChargePhase(enum.IntEnum):
    """Phase of a cavalry charge."""

    WALK = 0
    TROT = 1
    GALLOP = 2
    CHARGE = 3
    IMPACT = 4
    PURSUIT = 5
    RALLY = 6


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class CavalryConfig(BaseModel):
    """Configuration for cavalry charge mechanics."""

    phase_speeds: dict[int, float] = {
        ChargePhase.WALK: 2.0,
        ChargePhase.TROT: 4.0,
        ChargePhase.GALLOP: 8.0,
        ChargePhase.CHARGE: 10.0,
        ChargePhase.PURSUIT: 8.0,
        ChargePhase.RALLY: 0.5,
    }

    gallop_start_distance_m: float = 150.0
    charge_start_distance_m: float = 50.0
    max_gallop_duration_s: float = 60.0
    rally_duration_s: float = 120.0
    fatigue_per_second_gallop: float = 0.02
    fatigue_per_second_charge: float = 0.03
    screening_detection_bonus: float = 1.5
    exhaustion_threshold: float = 1.0


# ---------------------------------------------------------------------------
# Per-charge state
# ---------------------------------------------------------------------------


@dataclass
class ChargeState:
    """Tracks a single cavalry charge."""

    charge_id: str
    unit_id: str
    target_id: str
    phase: ChargePhase = ChargePhase.WALK
    distance_to_target_m: float = 500.0
    fatigue: float = 0.0
    phase_time_s: float = 0.0
    gallop_time_s: float = 0.0
    completed: bool = False


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CavalryEngine:
    """Manages cavalry charge state machines.

    Parameters
    ----------
    config:
        Cavalry configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: CavalryConfig | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._config = config or CavalryConfig()
        self._rng = rng or np.random.default_rng(42)
        self._charges: dict[str, ChargeState] = {}

    def initiate_charge(
        self,
        charge_id: str,
        unit_id: str,
        target_id: str,
        distance_m: float,
    ) -> ChargeState:
        """Begin a new cavalry charge."""
        cfg = self._config
        # Determine starting phase from distance
        if distance_m <= cfg.charge_start_distance_m:
            phase = ChargePhase.CHARGE
        elif distance_m <= cfg.gallop_start_distance_m:
            phase = ChargePhase.GALLOP
        else:
            phase = ChargePhase.WALK

        state = ChargeState(
            charge_id=charge_id,
            unit_id=unit_id,
            target_id=target_id,
            phase=phase,
            distance_to_target_m=distance_m,
        )
        self._charges[charge_id] = state
        logger.info(
            "Charge %s: %s → %s at %.0fm (%s)",
            charge_id, unit_id, target_id, distance_m,
            ChargePhase(phase).name,
        )
        return state

    def update_charge(self, charge_id: str, dt_s: float) -> ChargePhase:
        """Advance a charge by *dt_s* seconds.

        Returns the current phase after update.
        """
        state = self._charges.get(charge_id)
        if state is None or state.completed:
            return ChargePhase.RALLY

        cfg = self._config
        state.phase_time_s += dt_s

        # Rally phase: just count down
        if state.phase == ChargePhase.RALLY:
            if state.phase_time_s >= cfg.rally_duration_s:
                state.completed = True
            return state.phase

        # Pursuit phase: stays until explicitly transitioned
        if state.phase == ChargePhase.PURSUIT:
            return state.phase

        # Impact phase: instantaneous, move to pursuit
        if state.phase == ChargePhase.IMPACT:
            state.phase = ChargePhase.PURSUIT
            state.phase_time_s = 0.0
            return state.phase

        # Movement phases: advance towards target
        speed = cfg.phase_speeds.get(int(state.phase), 2.0)
        advance = speed * dt_s
        state.distance_to_target_m = max(0.0, state.distance_to_target_m - advance)

        # Fatigue accumulation at gallop+
        if state.phase in (ChargePhase.GALLOP, ChargePhase.CHARGE):
            rate = (
                cfg.fatigue_per_second_charge
                if state.phase == ChargePhase.CHARGE
                else cfg.fatigue_per_second_gallop
            )
            state.fatigue += rate * dt_s
            state.gallop_time_s += dt_s

        # Phase transitions by distance
        if (
            state.phase == ChargePhase.WALK
            and state.distance_to_target_m <= cfg.gallop_start_distance_m
        ):
            state.phase = ChargePhase.TROT
            state.phase_time_s = 0.0

        if (
            state.phase == ChargePhase.TROT
            and state.distance_to_target_m <= cfg.gallop_start_distance_m
        ):
            state.phase = ChargePhase.GALLOP
            state.phase_time_s = 0.0

        if (
            state.phase == ChargePhase.GALLOP
            and state.distance_to_target_m <= cfg.charge_start_distance_m
        ):
            state.phase = ChargePhase.CHARGE
            state.phase_time_s = 0.0

        # Exhaustion check
        if state.gallop_time_s >= cfg.max_gallop_duration_s:
            state.fatigue = max(state.fatigue, cfg.exhaustion_threshold)

        # Impact at contact
        if state.distance_to_target_m <= 0.0 and state.phase == ChargePhase.CHARGE:
            state.phase = ChargePhase.IMPACT
            state.phase_time_s = 0.0

        return state.phase

    def get_charge_speed(self, charge_id: str) -> float:
        """Return current movement speed for a charge."""
        state = self._charges.get(charge_id)
        if state is None or state.completed:
            return 0.0
        return self._config.phase_speeds.get(int(state.phase), 0.0)

    def begin_pursuit(self, charge_id: str) -> None:
        """Transition a charge to pursuit phase."""
        state = self._charges.get(charge_id)
        if state is not None:
            state.phase = ChargePhase.PURSUIT
            state.phase_time_s = 0.0

    def begin_rally(self, charge_id: str) -> None:
        """Transition a charge to rally phase."""
        state = self._charges.get(charge_id)
        if state is not None:
            state.phase = ChargePhase.RALLY
            state.phase_time_s = 0.0

    def is_exhausted(self, charge_id: str) -> bool:
        """Check if charge unit is exhausted."""
        state = self._charges.get(charge_id)
        if state is None:
            return False
        return state.fatigue >= self._config.exhaustion_threshold

    def screening_modifier(self, unit_type: str) -> float:
        """Return detection bonus for cavalry screening duties.

        Light cavalry (hussars) provide screening bonus.
        """
        if "hussar" in unit_type.lower() or "light" in unit_type.lower():
            return self._config.screening_detection_bonus
        return 1.0

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "charges": {
                cid: {
                    "charge_id": s.charge_id,
                    "unit_id": s.unit_id,
                    "target_id": s.target_id,
                    "phase": int(s.phase),
                    "distance_to_target_m": s.distance_to_target_m,
                    "fatigue": s.fatigue,
                    "phase_time_s": s.phase_time_s,
                    "gallop_time_s": s.gallop_time_s,
                    "completed": s.completed,
                }
                for cid, s in self._charges.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._charges.clear()
        for cid, cdata in state.get("charges", {}).items():
            self._charges[cid] = ChargeState(
                charge_id=cdata["charge_id"],
                unit_id=cdata["unit_id"],
                target_id=cdata["target_id"],
                phase=ChargePhase(cdata["phase"]),
                distance_to_target_m=cdata["distance_to_target_m"],
                fatigue=cdata["fatigue"],
                phase_time_s=cdata["phase_time_s"],
                gallop_time_s=cdata["gallop_time_s"],
                completed=cdata["completed"],
            )

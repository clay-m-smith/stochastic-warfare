"""Oar-powered galley propulsion with fatigue model.

Fundamentally different from modern propulsion (cubic fuel law doesn't
apply).  Fatigue-based rowing model: crew endurance depletes at rowing
speed, recovers at rest.  Ramming as primary weapon (approach speed x
mass -> damage).  Boarding transitions to melee combat on deck.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RowingSpeed(enum.IntEnum):
    """Galley rowing speed setting."""

    REST = 0
    CRUISE = 1
    BATTLE = 2
    RAMMING = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class GalleyConfig(BaseModel):
    """Configuration for oar-powered galley propulsion."""

    cruise_speed_mps: float = 2.5
    battle_speed_mps: float = 4.0
    ramming_speed_mps: float = 6.0
    fatigue_rate_cruise: float = 0.005
    fatigue_rate_battle: float = 0.02
    fatigue_rate_ramming: float = 0.05
    recovery_rate_rest: float = 0.01
    max_fatigue: float = 1.0
    exhaustion_threshold: float = 0.8
    ram_damage_base: float = 100.0
    ram_damage_speed_factor: float = 20.0
    boarding_transition_time_s: float = 30.0


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class GalleyState:
    """Tracks state of a single galley."""

    vessel_id: str
    rowing_speed: RowingSpeed = RowingSpeed.REST
    fatigue: float = 0.0
    heading_rad: float = 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class NavalOarEngine:
    """Manages oar-powered galley propulsion and combat.

    Parameters
    ----------
    config:
        Galley configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: GalleyConfig | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._config = config or GalleyConfig()
        self._rng = rng or np.random.default_rng(42)
        self._galleys: dict[str, GalleyState] = {}
        self._boarding: dict[str, tuple[str, float]] = {}  # vessel_id -> (target_id, remaining_s)

    def register_vessel(self, vessel_id: str) -> None:
        """Register a galley for tracking."""
        if vessel_id not in self._galleys:
            self._galleys[vessel_id] = GalleyState(vessel_id=vessel_id)

    def set_speed(self, vessel_id: str, speed: RowingSpeed) -> None:
        """Set the rowing speed for a vessel."""
        self.register_vessel(vessel_id)
        self._galleys[vessel_id].rowing_speed = speed

    def get_speed(self, vessel_id: str) -> float:
        """Return current speed in m/s accounting for fatigue."""
        state = self._galleys.get(vessel_id)
        if state is None:
            return 0.0

        cfg = self._config
        base_speeds = {
            RowingSpeed.REST: 0.0,
            RowingSpeed.CRUISE: cfg.cruise_speed_mps,
            RowingSpeed.BATTLE: cfg.battle_speed_mps,
            RowingSpeed.RAMMING: cfg.ramming_speed_mps,
        }
        speed = base_speeds.get(state.rowing_speed, 0.0)

        # Exhaustion penalty
        if state.fatigue >= cfg.exhaustion_threshold:
            speed *= 0.5

        return speed

    def update(self, dt_s: float) -> None:
        """Advance fatigue model by *dt_s* seconds."""
        cfg = self._config

        for state in self._galleys.values():
            fatigue_rates = {
                RowingSpeed.REST: -cfg.recovery_rate_rest,
                RowingSpeed.CRUISE: cfg.fatigue_rate_cruise,
                RowingSpeed.BATTLE: cfg.fatigue_rate_battle,
                RowingSpeed.RAMMING: cfg.fatigue_rate_ramming,
            }
            rate = fatigue_rates.get(state.rowing_speed, 0.0)
            state.fatigue = max(0.0, min(cfg.max_fatigue, state.fatigue + rate * dt_s))

        # Advance boarding timers
        completed: list[str] = []
        for vid, (target_id, remaining) in self._boarding.items():
            remaining -= dt_s
            if remaining <= 0:
                completed.append(vid)
            else:
                self._boarding[vid] = (target_id, remaining)
        for vid in completed:
            del self._boarding[vid]

    def compute_ram_damage(
        self,
        vessel_id: str,
        approach_speed: float | None = None,
    ) -> float:
        """Compute ramming damage.

        Parameters
        ----------
        approach_speed:
            Override approach speed (m/s). If None, uses current vessel speed.
        """
        cfg = self._config
        if approach_speed is None:
            approach_speed = self.get_speed(vessel_id)
        return cfg.ram_damage_base + cfg.ram_damage_speed_factor * approach_speed

    def initiate_boarding(self, vessel_id: str, target_id: str) -> float:
        """Initiate boarding action, returning transition time in seconds."""
        cfg = self._config
        self._boarding[vessel_id] = (target_id, cfg.boarding_transition_time_s)
        self.set_speed(vessel_id, RowingSpeed.REST)
        logger.info("Vessel %s boarding %s (%.0fs)", vessel_id, target_id,
                     cfg.boarding_transition_time_s)
        return cfg.boarding_transition_time_s

    def is_boarding(self, vessel_id: str) -> bool:
        """Check if a vessel is in boarding transition."""
        return vessel_id in self._boarding

    def get_fatigue(self, vessel_id: str) -> float:
        """Return current fatigue level for a vessel."""
        state = self._galleys.get(vessel_id)
        return state.fatigue if state else 0.0

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "galleys": {
                vid: {
                    "vessel_id": g.vessel_id,
                    "rowing_speed": int(g.rowing_speed),
                    "fatigue": g.fatigue,
                    "heading_rad": g.heading_rad,
                }
                for vid, g in self._galleys.items()
            },
            "boarding": {
                vid: {"target_id": t, "remaining_s": r}
                for vid, (t, r) in self._boarding.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._galleys.clear()
        for vid, gdata in state.get("galleys", {}).items():
            self._galleys[vid] = GalleyState(
                vessel_id=gdata["vessel_id"],
                rowing_speed=RowingSpeed(gdata["rowing_speed"]),
                fatigue=gdata["fatigue"],
                heading_rad=gdata["heading_rad"],
            )
        self._boarding.clear()
        for vid, bdata in state.get("boarding", {}).items():
            self._boarding[vid] = (bdata["target_id"], bdata["remaining_s"])

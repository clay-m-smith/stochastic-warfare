"""Fatigue accumulation and recovery modeling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


class FatigueState(NamedTuple):
    """Snapshot of a unit's fatigue condition."""

    physical: float  # 0.0–1.0
    mental: float  # 0.0–1.0
    sleep_debt_hours: float
    hours_since_rest: float


class FatigueConfig(BaseModel):
    """Configuration for fatigue accumulation rates."""

    max_march_hours: float = 12.0
    rest_recovery_rate: float = 0.15  # per hour of rest
    march_fatigue_rate: float = 0.08  # per hour of marching
    combat_fatigue_rate: float = 0.12  # per hour of combat
    altitude_fatigue_multiplier: float = 1.5
    altitude_threshold: float = 2500.0  # meters — above this, altitude penalty
    load_fatigue_multiplier: float = 1.3
    max_physical: float = 1.0
    max_mental: float = 1.0


class FatigueManager:
    """Track and update fatigue state per unit.

    Parameters
    ----------
    config:
        Fatigue rate parameters.
    """

    def __init__(self, config: FatigueConfig | None = None) -> None:
        self._config = config or FatigueConfig()
        self._states: dict[str, FatigueState] = {}

    def _ensure(self, unit_id: str) -> FatigueState:
        if unit_id not in self._states:
            self._states[unit_id] = FatigueState(0.0, 0.0, 0.0, 0.0)
        return self._states[unit_id]

    def accumulate(
        self,
        unit_id: str,
        hours: float,
        activity: str = "march",
        altitude: float = 0.0,
        *,
        temperature_stress: float = 0.0,
    ) -> FatigueState:
        """Accumulate fatigue for *hours* of *activity*.

        Parameters
        ----------
        activity:
            One of "march", "combat", "idle".
        altitude:
            Meters above sea level — penalty above threshold.
        temperature_stress:
            Heat/cold stress multiplier (0.0 = neutral, positive = faster fatigue).
        """
        s = self._ensure(unit_id)
        cfg = self._config

        if activity == "combat":
            rate = cfg.combat_fatigue_rate
        elif activity == "march":
            rate = cfg.march_fatigue_rate
        else:
            rate = cfg.march_fatigue_rate * 0.2  # idle: minimal

        # Altitude penalty
        if altitude > cfg.altitude_threshold:
            rate *= cfg.altitude_fatigue_multiplier

        # Phase 78c: temperature stress penalty (heat or cold)
        if temperature_stress > 0:
            rate *= (1.0 + temperature_stress)

        physical = min(cfg.max_physical, s.physical + rate * hours)
        mental = min(cfg.max_mental, s.mental + rate * 0.5 * hours)
        sleep_debt = s.sleep_debt_hours + hours * 0.3
        hours_since = s.hours_since_rest + hours

        new_state = FatigueState(physical, mental, sleep_debt, hours_since)
        self._states[unit_id] = new_state
        return new_state

    def rest(self, unit_id: str, hours: float) -> FatigueState:
        """Recover fatigue by resting for *hours*."""
        s = self._ensure(unit_id)
        cfg = self._config

        physical = max(0.0, s.physical - cfg.rest_recovery_rate * hours)
        mental = max(0.0, s.mental - cfg.rest_recovery_rate * 0.8 * hours)
        sleep_debt = max(0.0, s.sleep_debt_hours - hours * 0.8)
        hours_since = 0.0  # reset counter on rest

        new_state = FatigueState(physical, mental, sleep_debt, hours_since)
        self._states[unit_id] = new_state
        return new_state

    def get_fatigue(self, unit_id: str) -> FatigueState:
        """Return current fatigue state."""
        return self._ensure(unit_id)

    def speed_modifier(self, unit_id: str) -> float:
        """Return 0.0–1.0 speed multiplier from fatigue."""
        s = self._ensure(unit_id)
        # Linear degradation: 100% at 0 fatigue, 50% at max fatigue
        return 1.0 - 0.5 * s.physical

    def accuracy_modifier(self, unit_id: str) -> float:
        """Return 0.0–1.0 accuracy multiplier from fatigue."""
        s = self._ensure(unit_id)
        return 1.0 - 0.4 * s.mental

    def get_state(self) -> dict:
        return {
            "states": {
                uid: list(fs) for uid, fs in self._states.items()
            }
        }

    def set_state(self, state: dict) -> None:
        self._states.clear()
        for uid, fs in state["states"].items():
            self._states[uid] = FatigueState(*fs)

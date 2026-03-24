"""Air campaign management — sortie rates, pilot fatigue, weather days.

Phase 12f-2. Manages air campaign phases, sortie capacity, attrition,
and pilot fatigue dynamics.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class CampaignPhase(enum.IntEnum):
    """Air campaign doctrinal phase sequence."""

    AIR_SUPERIORITY = 0
    SEAD = 1
    INTERDICTION = 2
    CAS = 3


@dataclass
class PilotState:
    """Track individual pilot fatigue."""

    pilot_id: str
    missions_today: int = 0
    cumulative_missions: int = 0
    fatigue: float = 0.0  # 0.0 = fresh, 1.0 = exhausted
    performance_modifier: float = 1.0


class AirCampaignConfig(BaseModel):
    """Air campaign configuration."""

    max_sorties_per_day: int = 100
    maintenance_unavailable_fraction: float = 0.15
    """Fraction of aircraft down for maintenance at any time."""
    max_missions_per_pilot_per_day: int = 3
    fatigue_per_mission: float = 0.15
    fatigue_recovery_per_day: float = 0.4
    fatigue_performance_threshold: float = 0.5
    """Fatigue level above which performance degrades."""
    weather_cancellation_threshold: float = 0.3
    """Weather quality below which sorties are cancelled."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AirCampaignEngine:
    """Manage air campaign operations.

    Parameters
    ----------
    event_bus : EventBus
        For publishing events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : AirCampaignConfig | None
        Configuration.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: AirCampaignConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or AirCampaignConfig()
        self._pilots: dict[str, PilotState] = {}
        self._current_phase = CampaignPhase.AIR_SUPERIORITY
        self._fleet_size: int = 0
        self._losses: int = 0

    def set_fleet_size(self, size: int) -> None:
        """Set initial fleet size."""
        self._fleet_size = size

    def set_phase(self, phase: CampaignPhase) -> None:
        """Set current campaign phase."""
        self._current_phase = phase

    @property
    def current_phase(self) -> CampaignPhase:
        return self._current_phase

    def register_pilot(self, pilot_id: str) -> None:
        """Register a pilot for fatigue tracking."""
        self._pilots[pilot_id] = PilotState(pilot_id=pilot_id)

    def compute_daily_sortie_capacity(
        self,
        available_aircraft: int,
        mission_capable_rate: float = 0.85,
    ) -> int:
        """Compute maximum daily sortie capacity.

        Parameters
        ----------
        available_aircraft:
            Number of aircraft in the fleet.
        mission_capable_rate:
            Fraction of aircraft that are mission-capable (0-1).
        """
        cfg = self._config
        mc_aircraft = int(
            available_aircraft
            * mission_capable_rate
            * (1.0 - cfg.maintenance_unavailable_fraction)
        )
        # Each MC aircraft can fly ~2 sorties/day on average
        daily_cap = mc_aircraft * 2
        return min(daily_cap, cfg.max_sorties_per_day)

    def update_pilot_fatigue(self, pilot_id: str, missions_today: int) -> float:
        """Update pilot fatigue after flying missions.

        Returns the pilot's performance modifier (0-1).
        """
        cfg = self._config
        if pilot_id not in self._pilots:
            self._pilots[pilot_id] = PilotState(pilot_id=pilot_id)
        pilot = self._pilots[pilot_id]
        pilot.missions_today = missions_today
        pilot.cumulative_missions += missions_today
        pilot.fatigue = min(1.0, pilot.fatigue + cfg.fatigue_per_mission * missions_today)

        # Performance degrades above threshold
        if pilot.fatigue > cfg.fatigue_performance_threshold:
            excess = pilot.fatigue - cfg.fatigue_performance_threshold
            pilot.performance_modifier = max(0.3, 1.0 - excess * 2.0)
        else:
            pilot.performance_modifier = 1.0

        return pilot.performance_modifier

    def recover_fatigue(self) -> None:
        """Apply daily fatigue recovery to all pilots."""
        cfg = self._config
        for pilot in self._pilots.values():
            pilot.fatigue = max(0.0, pilot.fatigue - cfg.fatigue_recovery_per_day)
            pilot.missions_today = 0
            # Recalculate performance
            if pilot.fatigue > cfg.fatigue_performance_threshold:
                excess = pilot.fatigue - cfg.fatigue_performance_threshold
                pilot.performance_modifier = max(0.3, 1.0 - excess * 2.0)
            else:
                pilot.performance_modifier = 1.0

    def check_weather_day(self, weather_quality: float) -> float:
        """Compute sortie cancellation fraction from weather.

        Parameters
        ----------
        weather_quality:
            Weather quality 0.0-1.0 (1.0 = clear, 0.0 = zero visibility).

        Returns
        -------
        float
            Fraction of sorties that can fly (0.0-1.0).
        """
        cfg = self._config
        if weather_quality < cfg.weather_cancellation_threshold:
            return 0.0
        # Linear ramp from threshold to 1.0
        return min(1.0, (weather_quality - cfg.weather_cancellation_threshold) /
                   (1.0 - cfg.weather_cancellation_threshold))

    def update_attrition(
        self,
        losses: int,
        depot_repairs: int = 0,
        production: int = 0,
    ) -> int:
        """Update fleet size from attrition and regeneration.

        Returns current fleet size.
        """
        self._losses += losses
        self._fleet_size = max(0, self._fleet_size - losses + depot_repairs + production)
        return self._fleet_size

    def get_pilot(self, pilot_id: str) -> PilotState:
        """Return pilot state; raises ``KeyError`` if not found."""
        return self._pilots[pilot_id]

    # -- State protocol --

    def get_state(self) -> dict:
        return {
            "fleet_size": self._fleet_size,
            "losses": self._losses,
            "current_phase": int(self._current_phase),
            "pilots": {
                pid: {
                    "pilot_id": p.pilot_id,
                    "missions_today": p.missions_today,
                    "cumulative_missions": p.cumulative_missions,
                    "fatigue": p.fatigue,
                    "performance_modifier": p.performance_modifier,
                }
                for pid, p in self._pilots.items()
            },
        }

    def set_state(self, state: dict) -> None:
        self._fleet_size = state["fleet_size"]
        self._losses = state["losses"]
        self._current_phase = CampaignPhase(state["current_phase"])
        self._pilots.clear()
        for pid, pd in state.get("pilots", {}).items():
            self._pilots[pid] = PilotState(
                pilot_id=pd["pilot_id"],
                missions_today=pd["missions_today"],
                cumulative_missions=pd["cumulative_missions"],
                fatigue=pd["fatigue"],
                performance_modifier=pd["performance_modifier"],
            )

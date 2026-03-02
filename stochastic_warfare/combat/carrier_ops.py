"""Carrier flight operations — sortie rate, launch, recovery, CAP.

Models carrier deck state transitions, sortie rate computation based
on available aircraft and crew quality, launch and recovery (with
bolter probability from sea state), and aircraft turnaround.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.events import CarrierSortieEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


class DeckState(enum.IntEnum):
    """Carrier deck operational state."""

    IDLE = 0
    LAUNCH_CYCLE = 1
    RECOVERY_CYCLE = 2
    MAINTENANCE = 3
    DAMAGED = 4


class CarrierOpsConfig(BaseModel):
    """Tunable parameters for carrier operations."""

    max_sortie_rate_per_hour: float = 12.0  # theoretical max
    base_launch_success: float = 0.98
    base_recovery_success: float = 0.95
    bolter_probability_base: float = 0.05
    sea_state_bolter_factor: float = 0.03  # additional bolter prob per sea state unit
    damaged_deck_sortie_factor: float = 0.3
    maintenance_sortie_factor: float = 0.0
    turnaround_base_s: float = 1800.0  # 30 minutes base turnaround
    turnaround_rearm_factor: float = 1.5  # rearm takes longer
    turnaround_hot_refuel_factor: float = 0.7  # hot refuel is faster
    cap_station_endurance_s: float = 14400.0  # 4 hours on station


@dataclass
class LaunchResult:
    """Outcome of an aircraft launch."""

    aircraft_id: str
    success: bool
    mission_type: str
    deck_state: DeckState


@dataclass
class RecoveryResult:
    """Outcome of an aircraft recovery."""

    aircraft_id: str
    success: bool
    bolter: bool = False
    wave_off: bool = False


@dataclass
class CAPStatus:
    """Current combat air patrol status."""

    aircraft_on_station: int
    time_on_station_s: float
    endurance_remaining_s: float
    coverage_factor: float  # 0.0–1.0 effectiveness


class CarrierOpsEngine:
    """Carrier flight operations management.

    Parameters
    ----------
    event_bus:
        For publishing carrier sortie events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: CarrierOpsConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or CarrierOpsConfig()
        self._sorties_launched: int = 0
        self._aircraft_turnaround: dict[str, float] = {}  # aircraft_id -> ready_time_s

    def compute_sortie_rate(
        self,
        aircraft_available: int,
        deck_crew_quality: float,
        weather_factor: float,
        deck_state: DeckState,
    ) -> float:
        """Compute achievable sortie rate in sorties per hour.

        Parameters
        ----------
        aircraft_available:
            Number of mission-ready aircraft.
        deck_crew_quality:
            Crew quality factor 0.0–1.0.
        weather_factor:
            Weather impact factor 0.0–1.0 (1.0 = perfect conditions).
        deck_state:
            Current state of the flight deck.
        """
        cfg = self._config

        if aircraft_available <= 0:
            return 0.0

        # Deck state factors
        state_factors = {
            DeckState.IDLE: 1.0,
            DeckState.LAUNCH_CYCLE: 1.0,
            DeckState.RECOVERY_CYCLE: 0.5,  # Can do some launches during recovery
            DeckState.MAINTENANCE: cfg.maintenance_sortie_factor,
            DeckState.DAMAGED: cfg.damaged_deck_sortie_factor,
        }
        state_factor = state_factors.get(deck_state, 0.5)

        # Sortie rate = max_rate * crew_quality * weather * deck_state
        # Diminishing returns on aircraft: sqrt(available/max)
        aircraft_factor = min(1.0, (aircraft_available / 20.0) ** 0.5)

        rate = cfg.max_sortie_rate_per_hour * aircraft_factor * deck_crew_quality * weather_factor * state_factor

        return max(0.0, rate)

    def launch_aircraft(
        self,
        carrier_id: str,
        aircraft_id: str,
        mission_type: str,
        deck_state: DeckState,
        timestamp: Any = None,
    ) -> LaunchResult:
        """Launch an aircraft from the carrier.

        Parameters
        ----------
        carrier_id:
            Entity ID of the carrier.
        aircraft_id:
            Entity ID of the aircraft.
        mission_type:
            Mission type ("CAP", "STRIKE", "ASW", "AEW", etc.).
        deck_state:
            Current deck state.
        timestamp:
            Simulation timestamp.
        """
        cfg = self._config

        # Cannot launch from maintenance or damaged deck (with some chance)
        if deck_state == DeckState.MAINTENANCE:
            return LaunchResult(
                aircraft_id=aircraft_id, success=False,
                mission_type=mission_type, deck_state=deck_state,
            )

        launch_pk = cfg.base_launch_success
        if deck_state == DeckState.DAMAGED:
            launch_pk *= cfg.damaged_deck_sortie_factor

        success = self._rng.random() < launch_pk

        if success:
            self._sorties_launched += 1
            if timestamp is not None:
                self._event_bus.publish(CarrierSortieEvent(
                    timestamp=timestamp, source=ModuleId.COMBAT,
                    carrier_id=carrier_id, aircraft_id=aircraft_id,
                    mission_type=mission_type,
                ))

        logger.debug(
            "Launch %s from %s for %s: %s (deck=%s)",
            aircraft_id, carrier_id, mission_type,
            "success" if success else "failed", deck_state.name,
        )

        return LaunchResult(
            aircraft_id=aircraft_id, success=success,
            mission_type=mission_type, deck_state=deck_state,
        )

    def recover_aircraft(
        self,
        carrier_id: str,
        aircraft_id: str,
        sea_state: float,
        pilot_skill: float,
    ) -> RecoveryResult:
        """Recover an aircraft to the carrier.

        Bolter probability increases with sea state and decreases with
        pilot skill.

        Parameters
        ----------
        carrier_id:
            Entity ID of the carrier.
        aircraft_id:
            Entity ID of the aircraft.
        sea_state:
            Current sea state (0–9 Beaufort-derived).
        pilot_skill:
            Pilot skill 0.0–1.0.
        """
        cfg = self._config

        # Bolter probability
        bolter_prob = cfg.bolter_probability_base + cfg.sea_state_bolter_factor * sea_state
        # Better pilots reduce bolter risk
        bolter_prob *= (1.5 - pilot_skill)
        bolter_prob = max(0.0, min(0.9, bolter_prob))

        bolter = self._rng.random() < bolter_prob

        if bolter:
            logger.debug("Recovery %s on %s: BOLTER", aircraft_id, carrier_id)
            return RecoveryResult(
                aircraft_id=aircraft_id, success=False, bolter=True,
            )

        # Base recovery success (trap attempt)
        recovery_pk = cfg.base_recovery_success * (0.5 + 0.5 * pilot_skill)
        success = self._rng.random() < recovery_pk

        if not success:
            # Wave-off
            logger.debug("Recovery %s on %s: WAVE-OFF", aircraft_id, carrier_id)
            return RecoveryResult(
                aircraft_id=aircraft_id, success=False, wave_off=True,
            )

        logger.debug("Recovery %s on %s: success", aircraft_id, carrier_id)
        return RecoveryResult(aircraft_id=aircraft_id, success=True)

    def turnaround_aircraft(
        self,
        aircraft_id: str,
        rearm_type: str,
    ) -> float:
        """Compute turnaround time for an aircraft.

        Parameters
        ----------
        aircraft_id:
            Entity ID of the aircraft.
        rearm_type:
            Type of rearming: "full", "hot_refuel", "rearm", "reconfigure".

        Returns
        -------
        float:
            Turnaround time in seconds.
        """
        cfg = self._config
        base = cfg.turnaround_base_s

        type_factors = {
            "full": cfg.turnaround_rearm_factor,
            "hot_refuel": cfg.turnaround_hot_refuel_factor,
            "rearm": cfg.turnaround_rearm_factor,
            "reconfigure": cfg.turnaround_rearm_factor * 1.3,
        }
        factor = type_factors.get(rearm_type, 1.0)

        # Add variation (10% stochastic)
        variation = 1.0 + self._rng.normal(0.0, 0.1)
        variation = max(0.5, variation)

        turnaround_s = base * factor * variation
        self._aircraft_turnaround[aircraft_id] = turnaround_s

        logger.debug(
            "Turnaround %s (%s): %.0f seconds",
            aircraft_id, rearm_type, turnaround_s,
        )
        return turnaround_s

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "sorties_launched": self._sorties_launched,
            "aircraft_turnaround": dict(self._aircraft_turnaround),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._sorties_launched = state["sorties_launched"]
        self._aircraft_turnaround = dict(state["aircraft_turnaround"])

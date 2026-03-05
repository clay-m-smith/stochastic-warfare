"""War crimes consequence engine.

Phase 24a-3.  Computes cascading consequences of war crimes, prohibited
weapon employment, and prisoner mistreatment: own-side morale penalties,
enemy hardening, civilian hostility, international/domestic political
pressure, and escalation-spiral risk (Bernoulli retaliation trigger).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

from stochastic_warfare.escalation.events import (
    ProhibitedWeaponEmployedEvent,
    PrisonerMistreatmentEvent,
    WarCrimeRecordedEvent,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConsequenceConfig(BaseModel):
    """Configuration for consequence calculations."""

    own_morale_penalty_per_crime: float = 0.05
    enemy_hardening_per_crime: float = 0.03
    civilian_hostility_per_crime: float = 0.10
    political_pressure_per_crime: float = 0.05
    spiral_retaliation_probability: float = 0.3


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsequenceResult:
    """Immutable result of processing a war crime or violation."""

    own_morale_delta: float
    enemy_morale_delta: float
    civilian_hostility_delta: float
    international_pressure_delta: float
    domestic_pressure_delta: float
    escalation_spiral_triggered: bool


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ConsequenceEngine:
    """Compute cascading consequences of war crimes and violations.

    Parameters
    ----------
    event_bus : EventBus
        Publishes violation events.
    rng : np.random.Generator
        PRNG stream for Bernoulli spiral rolls.
    config : ConsequenceConfig | None
        Configuration.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: ConsequenceConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or ConsequenceConfig()
        self._crime_counts: dict[str, int] = {}

    # -- Public API ---------------------------------------------------------

    def process_war_crime(
        self,
        crime_type: str,
        responsible_side: str,
        severity: float,
        position: Position,
        timestamp: datetime,
    ) -> ConsequenceResult:
        """Process a war crime and compute consequences.

        Parameters
        ----------
        crime_type : str
            Type of war crime.
        responsible_side : str
            Side that committed the crime.
        severity : float
            Severity in [0, 1].
        position : Position
            Location of the crime.
        timestamp : datetime
            Simulation time.

        Returns
        -------
        ConsequenceResult
            Computed consequence deltas.
        """
        cfg = self._config
        self._crime_counts[responsible_side] = (
            self._crime_counts.get(responsible_side, 0) + 1
        )

        own_morale_delta = -(cfg.own_morale_penalty_per_crime * severity)
        enemy_morale_delta = cfg.enemy_hardening_per_crime * severity
        civilian_hostility_delta = cfg.civilian_hostility_per_crime * severity
        international_pressure_delta = cfg.political_pressure_per_crime * severity
        domestic_pressure_delta = cfg.political_pressure_per_crime * severity

        spiral = bool(
            self._rng.random() < cfg.spiral_retaliation_probability * severity
        )

        self._event_bus.publish(WarCrimeRecordedEvent(
            timestamp=timestamp,
            source=ModuleId.ESCALATION,
            responsible_side=responsible_side,
            crime_type=crime_type,
            severity=severity,
            position=position,
        ))

        logger.info(
            "WarCrime[%s]: type=%s severity=%.2f spiral=%s",
            responsible_side, crime_type, severity, spiral,
        )

        return ConsequenceResult(
            own_morale_delta=own_morale_delta,
            enemy_morale_delta=enemy_morale_delta,
            civilian_hostility_delta=civilian_hostility_delta,
            international_pressure_delta=international_pressure_delta,
            domestic_pressure_delta=domestic_pressure_delta,
            escalation_spiral_triggered=spiral,
        )

    def process_prohibited_weapon(
        self,
        weapon_id: str,
        ammo_id: str,
        responsible_side: str,
        civilian_casualties: int,
        position: Position,
        timestamp: datetime,
    ) -> ConsequenceResult:
        """Process prohibited weapon employment.

        Parameters
        ----------
        weapon_id : str
            Weapon identifier.
        ammo_id : str
            Ammunition identifier.
        responsible_side : str
            Side that employed the weapon.
        civilian_casualties : int
            Number of civilian casualties caused.
        position : Position
            Employment location.
        timestamp : datetime
            Simulation time.

        Returns
        -------
        ConsequenceResult
            Computed consequence deltas.
        """
        cfg = self._config
        severity = min(1.0, civilian_casualties / 100.0)

        self._crime_counts[responsible_side] = (
            self._crime_counts.get(responsible_side, 0) + 1
        )

        own_morale_delta = -(cfg.own_morale_penalty_per_crime * severity)
        enemy_morale_delta = cfg.enemy_hardening_per_crime * severity
        civilian_hostility_delta = cfg.civilian_hostility_per_crime * severity
        international_pressure_delta = cfg.political_pressure_per_crime * severity
        domestic_pressure_delta = cfg.political_pressure_per_crime * severity

        spiral = bool(
            self._rng.random() < cfg.spiral_retaliation_probability * severity
        )

        self._event_bus.publish(ProhibitedWeaponEmployedEvent(
            timestamp=timestamp,
            source=ModuleId.ESCALATION,
            responsible_side=responsible_side,
            weapon_id=weapon_id,
            ammo_id=ammo_id,
            position=position,
        ))

        logger.info(
            "ProhibitedWeapon[%s]: %s/%s civ_cas=%d severity=%.2f spiral=%s",
            responsible_side, weapon_id, ammo_id, civilian_casualties,
            severity, spiral,
        )

        return ConsequenceResult(
            own_morale_delta=own_morale_delta,
            enemy_morale_delta=enemy_morale_delta,
            civilian_hostility_delta=civilian_hostility_delta,
            international_pressure_delta=international_pressure_delta,
            domestic_pressure_delta=domestic_pressure_delta,
            escalation_spiral_triggered=spiral,
        )

    def process_prisoner_mistreatment(
        self,
        responsible_side: str,
        treatment_level: int,
        documented: bool,
        timestamp: datetime,
    ) -> ConsequenceResult:
        """Process prisoner mistreatment.

        Parameters
        ----------
        responsible_side : str
            Side that mistreated prisoners.
        treatment_level : int
            0 = minor, 1 = moderate, 2 = severe.
        documented : bool
            Whether the mistreatment was documented/witnessed.
        timestamp : datetime
            Simulation time.

        Returns
        -------
        ConsequenceResult
            Computed consequence deltas.
        """
        cfg = self._config

        # Severity from treatment level
        severity_map = {0: 0.0, 1: 0.5, 2: 1.0}
        severity = severity_map.get(treatment_level, 1.0)

        self._crime_counts[responsible_side] = (
            self._crime_counts.get(responsible_side, 0) + 1
        )

        own_morale_delta = -(cfg.own_morale_penalty_per_crime * severity)
        enemy_morale_delta = cfg.enemy_hardening_per_crime * severity
        civilian_hostility_delta = cfg.civilian_hostility_per_crime * severity

        international_pressure_delta = cfg.political_pressure_per_crime * severity
        if documented:
            international_pressure_delta *= 2.0

        domestic_pressure_delta = cfg.political_pressure_per_crime * severity

        spiral = bool(
            self._rng.random() < cfg.spiral_retaliation_probability * severity
        )

        self._event_bus.publish(PrisonerMistreatmentEvent(
            timestamp=timestamp,
            source=ModuleId.ESCALATION,
            responsible_side=responsible_side,
            treatment_level=treatment_level,
            prisoner_count=0,  # count not tracked in this path
        ))

        logger.info(
            "PrisonerMistreatment[%s]: level=%d documented=%s severity=%.2f spiral=%s",
            responsible_side, treatment_level, documented, severity, spiral,
        )

        return ConsequenceResult(
            own_morale_delta=own_morale_delta,
            enemy_morale_delta=enemy_morale_delta,
            civilian_hostility_delta=civilian_hostility_delta,
            international_pressure_delta=international_pressure_delta,
            domestic_pressure_delta=domestic_pressure_delta,
            escalation_spiral_triggered=spiral,
        )

    def get_crime_count(self, side: str) -> int:
        """Return cumulative crime count for *side*."""
        return self._crime_counts.get(side, 0)

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        return {
            "crime_counts": dict(self._crime_counts),
        }

    def set_state(self, state: dict) -> None:
        self._crime_counts = dict(state.get("crime_counts", {}))

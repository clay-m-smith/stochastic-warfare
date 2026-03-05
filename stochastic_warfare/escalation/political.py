"""Political pressure model — international and domestic.

Phase 24a-2.  Tracks accumulating international and domestic political
pressure driven by war crimes, collateral damage, prohibited weapons,
media visibility, own-side casualties, stalemate, propaganda, and
perceived existential threat.

Pressure levels trigger concrete effects: supply constraints, coalition
fracture risk, forced ROE tightening, and war termination pressure
(international), or ROE loosening and escalation authorization (domestic).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

from stochastic_warfare.escalation.events import PoliticalPressureChangeEvent

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums / data
# ---------------------------------------------------------------------------


class PoliticalEffect(enum.IntEnum):
    """Effects triggered by political pressure thresholds."""

    NONE = 0
    SUPPLY_CONSTRAINT = 1
    COALITION_FRACTURE_RISK = 2
    FORCED_ROE_TIGHTENING = 3
    WAR_TERMINATION_PRESSURE = 4
    ROE_LOOSENING_AUTHORIZED = 5
    ESCALATION_AUTHORIZED = 6
    CONSCRIPTION = 7
    LEADERSHIP_CHANGE_RISK = 8


@dataclass(frozen=True)
class PoliticalPressureState:
    """Immutable snapshot of a side's political pressure."""

    international: float
    domestic: float
    effects: tuple[PoliticalEffect, ...]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class PoliticalPressureConfig(BaseModel):
    """Configuration for political pressure accumulation."""

    # International pressure rate coefficients
    k_crime: float = 0.05
    k_collateral: float = 0.002
    k_prohibited: float = 0.10
    k_media: float = 0.03
    k_int_decay: float = 0.01

    # Domestic pressure rate coefficients
    k_own_cas: float = 0.003
    k_stalemate: float = 0.02
    k_propaganda: float = 0.01
    k_existential_threat: float = 0.05
    k_dom_decay: float = 0.005

    # International thresholds
    supply_constraint: float = 0.3
    coalition_fracture: float = 0.5
    forced_roe: float = 0.7
    war_termination: float = 0.9

    # Domestic thresholds
    roe_loosening: float = 0.3
    escalation_auth: float = 0.5


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PoliticalPressureEngine:
    """Track and evaluate political pressure for each side.

    Parameters
    ----------
    event_bus : EventBus
        Publishes ``PoliticalPressureChangeEvent`` on updates.
    config : PoliticalPressureConfig | None
        Configuration.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: PoliticalPressureConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config or PoliticalPressureConfig()
        self._international: dict[str, float] = {}
        self._domestic: dict[str, float] = {}

    # -- Public API ---------------------------------------------------------

    def update(
        self,
        side: str,
        dt_hours: float,
        war_crime_count: int,
        civilian_casualties: int,
        prohibited_weapon_events: int,
        media_visibility: float,
        own_casualties: int,
        stalemate_indicator: float,
        enemy_psyop_effectiveness: float,
        perceived_existential_threat: float,
        timestamp: datetime,
    ) -> PoliticalPressureState:
        """Advance political pressure by *dt_hours* for *side*.

        Parameters
        ----------
        side : str
            Side identifier.
        dt_hours : float
            Time step in hours.
        war_crime_count : int
            New war crimes committed this tick.
        civilian_casualties : int
            Civilian casualties this tick.
        prohibited_weapon_events : int
            Prohibited weapon employment events this tick.
        media_visibility : float
            Media coverage intensity [0, 1].
        own_casualties : int
            Own-side casualties this tick.
        stalemate_indicator : float
            Degree of stalemate [0, 1].
        enemy_psyop_effectiveness : float
            Enemy propaganda effectiveness [0, 1].
        perceived_existential_threat : float
            How existential the threat is perceived domestically [0, 1].
        timestamp : datetime
            Current simulation time.

        Returns
        -------
        PoliticalPressureState
            Updated pressure snapshot.
        """
        cfg = self._config
        old_int = self.get_international(side)
        old_dom = self.get_domestic(side)

        # International pressure growth
        int_growth = dt_hours * (
            cfg.k_crime * war_crime_count
            + cfg.k_collateral * civilian_casualties / 100.0
            + cfg.k_prohibited * prohibited_weapon_events
            + cfg.k_media * media_visibility
        )
        int_decay = cfg.k_int_decay * dt_hours
        new_int = min(1.0, max(0.0, old_int + int_growth - int_decay))

        # Domestic pressure growth
        dom_growth = dt_hours * (
            cfg.k_own_cas * own_casualties
            + cfg.k_stalemate * stalemate_indicator
            + cfg.k_propaganda * enemy_psyop_effectiveness
        )
        # Existential threat suppresses domestic pressure growth
        dom_growth -= cfg.k_existential_threat * perceived_existential_threat * dt_hours
        dom_decay = cfg.k_dom_decay * dt_hours
        new_dom = min(1.0, max(0.0, old_dom + dom_growth - dom_decay))

        self._international[side] = new_int
        self._domestic[side] = new_dom

        # Publish event if anything changed
        if new_int != old_int or new_dom != old_dom:
            self._event_bus.publish(PoliticalPressureChangeEvent(
                timestamp=timestamp,
                source=ModuleId.ESCALATION,
                side=side,
                old_international=old_int,
                new_international=new_int,
                old_domestic=old_dom,
                new_domestic=new_dom,
            ))

        effects = self.evaluate_effects(side)

        logger.debug(
            "Political[%s]: int=%.3f->%.3f dom=%.3f->%.3f effects=%s",
            side, old_int, new_int, old_dom, new_dom,
            [e.name for e in effects],
        )

        return PoliticalPressureState(
            international=new_int,
            domestic=new_dom,
            effects=tuple(effects),
        )

    def get_international(self, side: str) -> float:
        """Return current international pressure for *side* (default 0.0)."""
        return self._international.get(side, 0.0)

    def get_domestic(self, side: str) -> float:
        """Return current domestic pressure for *side* (default 0.0)."""
        return self._domestic.get(side, 0.0)

    def evaluate_effects(self, side: str) -> list[PoliticalEffect]:
        """Evaluate threshold effects for *side*.

        Returns
        -------
        list[PoliticalEffect]
            Active effects based on current pressure levels.
        """
        cfg = self._config
        p_int = self.get_international(side)
        p_dom = self.get_domestic(side)
        effects: list[PoliticalEffect] = []

        # International thresholds
        if p_int >= cfg.supply_constraint:
            effects.append(PoliticalEffect.SUPPLY_CONSTRAINT)
        if p_int >= cfg.coalition_fracture:
            effects.append(PoliticalEffect.COALITION_FRACTURE_RISK)
        if p_int >= cfg.forced_roe:
            effects.append(PoliticalEffect.FORCED_ROE_TIGHTENING)
        if p_int >= cfg.war_termination:
            effects.append(PoliticalEffect.WAR_TERMINATION_PRESSURE)

        # Domestic thresholds
        if p_dom >= cfg.roe_loosening:
            effects.append(PoliticalEffect.ROE_LOOSENING_AUTHORIZED)
        if p_dom >= cfg.escalation_auth:
            effects.append(PoliticalEffect.ESCALATION_AUTHORIZED)

        return effects

    # -- State protocol -----------------------------------------------------

    def get_state(self) -> dict:
        return {
            "international": dict(self._international),
            "domestic": dict(self._domestic),
        }

    def set_state(self, state: dict) -> None:
        self._international = dict(state.get("international", {}))
        self._domestic = dict(state.get("domestic", {}))

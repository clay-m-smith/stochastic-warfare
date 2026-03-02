"""Rout, rally, surrender, and cascade mechanics.

Handles units breaking and fleeing, rally attempts, formal surrender
processing, and the contagion of routing to nearby fragile units.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId
from stochastic_warfare.morale.events import RallyEvent, RoutEvent, SurrenderEvent

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class RoutConfig(BaseModel):
    """Configurable parameters for rout and rally mechanics."""

    rally_base_chance: float = 0.15
    """Base probability of a routing unit rallying per check."""

    rally_friendly_bonus: float = 0.05
    """Rally probability bonus per nearby friendly unit (up to 5)."""

    rally_leader_bonus: float = 0.20
    """Rally probability bonus when a leader is present."""

    cascade_radius_m: float = 500.0
    """Maximum distance (meters) at which a routing unit can trigger cascade."""

    cascade_base_chance: float = 0.10
    """Base probability that a nearby unit is affected by cascade."""

    cascade_shaken_susceptibility: float = 1.5
    """Multiplier on cascade chance for SHAKEN units."""

    cascade_broken_susceptibility: float = 2.5
    """Multiplier on cascade chance for BROKEN units."""

    surrender_threshold: float = 0.6
    """Surrender probability above which surrender is automatic."""

    rout_speed_factor: float = 1.5
    """Speed multiplier for routing units (flee at max speed)."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class RoutState:
    """Tracking data for a routing unit."""

    unit_id: str
    direction_rad: float
    """Direction of flight in radians (opposite to threat)."""

    speed_factor: float
    """Speed multiplier during rout."""

    def get_state(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "direction_rad": self.direction_rad,
            "speed_factor": self.speed_factor,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.unit_id = state["unit_id"]
        self.direction_rad = state["direction_rad"]
        self.speed_factor = state["speed_factor"]


@dataclass
class SurrenderResult:
    """Result of a surrender event."""

    unit_id: str
    pow_count: int
    """Number of personnel taken as prisoners of war."""

    def get_state(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "pow_count": self.pow_count,
        }


# ---------------------------------------------------------------------------
# Rout engine
# ---------------------------------------------------------------------------


class RoutEngine:
    """Handles rout initiation, rally attempts, surrender, and cascade.

    Parameters
    ----------
    event_bus:
        EventBus for publishing rout/rally/surrender events.
    rng:
        A ``numpy.random.Generator``.
    config:
        Rout configuration parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: RoutConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or RoutConfig()
        self._active_routs: dict[str, RoutState] = {}

    def initiate_rout(
        self,
        unit_id: str,
        threat_direction_rad: float,
    ) -> RoutState:
        """Begin a rout — the unit flees opposite the threat direction.

        Parameters
        ----------
        unit_id:
            Identifier of the routing unit.
        threat_direction_rad:
            Direction from which the threat comes (radians).

        Returns
        -------
        RoutState
            The rout tracking data.
        """
        cfg = self._config

        # Flee opposite to threat with some random scatter
        scatter = self._rng.normal(0.0, 0.2)  # ~11 degrees scatter
        flee_direction = threat_direction_rad + math.pi + scatter
        # Normalize to [0, 2*pi)
        flee_direction = flee_direction % (2.0 * math.pi)

        rout_state = RoutState(
            unit_id=unit_id,
            direction_rad=flee_direction,
            speed_factor=cfg.rout_speed_factor,
        )
        self._active_routs[unit_id] = rout_state

        logger.info(
            "Unit %s routing — flee direction %.2f rad, speed factor %.1f",
            unit_id, flee_direction, cfg.rout_speed_factor,
        )

        self._event_bus.publish(RoutEvent(
            timestamp=datetime.now(tz=timezone.utc),
            source=ModuleId.MORALE,
            unit_id=unit_id,
            direction=flee_direction,
        ))

        return rout_state

    def check_rally(
        self,
        unit_id: str,
        nearby_friendly_count: int,
        leader_present: bool,
    ) -> bool:
        """Check if a routing unit can rally.

        Parameters
        ----------
        unit_id:
            Identifier of the routing unit.
        nearby_friendly_count:
            Number of friendly units nearby.
        leader_present:
            Whether a leader is present to rally the unit.

        Returns
        -------
        bool
            True if the unit rallies.
        """
        cfg = self._config

        rally_chance = cfg.rally_base_chance
        rally_chance += cfg.rally_friendly_bonus * min(nearby_friendly_count, 5)
        if leader_present:
            rally_chance += cfg.rally_leader_bonus
        rally_chance = min(rally_chance, 0.95)

        roll = self._rng.random()
        rallied = roll < rally_chance

        if rallied:
            self._active_routs.pop(unit_id, None)
            rallied_by = "leader" if leader_present else ""
            logger.info("Unit %s rallied (chance=%.2f)", unit_id, rally_chance)

            self._event_bus.publish(RallyEvent(
                timestamp=datetime.now(tz=timezone.utc),
                source=ModuleId.MORALE,
                unit_id=unit_id,
                rallied_by=rallied_by,
            ))

        return rallied

    def process_surrender(
        self,
        unit_id: str,
        personnel_count: int,
        capturing_side: str,
    ) -> SurrenderResult:
        """Process a unit surrender.

        Parameters
        ----------
        unit_id:
            Identifier of the surrendering unit.
        personnel_count:
            Number of personnel in the surrendering unit.
        capturing_side:
            Side that captures the surrendering unit.

        Returns
        -------
        SurrenderResult
            Result with POW count.
        """
        # Some personnel may escape during surrender
        escape_fraction = self._rng.uniform(0.0, 0.1)
        pow_count = max(1, int(personnel_count * (1.0 - escape_fraction)))

        self._active_routs.pop(unit_id, None)

        logger.info(
            "Unit %s surrendered — %d POW captured by %s",
            unit_id, pow_count, capturing_side,
        )

        self._event_bus.publish(SurrenderEvent(
            timestamp=datetime.now(tz=timezone.utc),
            source=ModuleId.MORALE,
            unit_id=unit_id,
            capturing_side=capturing_side,
        ))

        return SurrenderResult(unit_id=unit_id, pow_count=pow_count)

    def rout_cascade(
        self,
        routing_unit_id: str,
        adjacent_unit_morale_states: dict[str, int],
        distances_m: dict[str, float],
    ) -> list[str]:
        """Check if a routing unit causes nearby units to cascade into rout.

        Parameters
        ----------
        routing_unit_id:
            The unit that is routing (source of cascade).
        adjacent_unit_morale_states:
            Mapping of nearby unit_id -> morale state (int).
        distances_m:
            Mapping of nearby unit_id -> distance in meters.

        Returns
        -------
        list[str]
            Unit IDs of units that have been triggered to rout by cascade.
        """
        cfg = self._config
        cascaded: list[str] = []

        for uid, morale_state in sorted(adjacent_unit_morale_states.items()):
            if uid == routing_unit_id:
                continue

            distance = distances_m.get(uid, float("inf"))
            if distance > cfg.cascade_radius_m:
                continue

            # Only SHAKEN (1) and BROKEN (2) units are susceptible
            if morale_state == 1:
                susceptibility = cfg.cascade_shaken_susceptibility
            elif morale_state == 2:
                susceptibility = cfg.cascade_broken_susceptibility
            else:
                continue

            # Distance attenuation
            distance_factor = 1.0 - (distance / cfg.cascade_radius_m)
            cascade_prob = cfg.cascade_base_chance * susceptibility * distance_factor

            roll = self._rng.random()
            if roll < cascade_prob:
                cascaded.append(uid)
                logger.debug(
                    "Cascade: unit %s triggered rout in unit %s (prob=%.3f)",
                    routing_unit_id, uid, cascade_prob,
                )

        return cascaded

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        return {
            "active_routs": {
                uid: rs.get_state()
                for uid, rs in sorted(self._active_routs.items())
            },
            "rng_state": self._rng.bit_generator.state,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._active_routs.clear()
        for uid, rs_state in state["active_routs"].items():
            rs = RoutState(unit_id="", direction_rad=0.0, speed_factor=0.0)
            rs.set_state(rs_state)
            self._active_routs[uid] = rs

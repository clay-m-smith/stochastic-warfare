"""Fratricide risk assessment driven by detection confidence.

Risk is primarily a function of target identification confidence from
Phase 3 detection.  Additional modifiers for visibility, terrain,
intermixed forces, and stress.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.events import FratricideEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class FratricideConfig(BaseModel):
    """Tunable parameters for fratricide risk."""

    identified_base_risk: float = 0.01
    classified_base_risk: float = 0.07
    detected_only_base_risk: float = 0.22
    unknown_base_risk: float = 0.40
    visibility_risk_multiplier: float = 1.5
    urban_risk_multiplier: float = 1.3
    stress_risk_multiplier: float = 0.3
    danger_close_radius_m: float = 600.0


@dataclass
class FratricideRisk:
    """Result of a fratricide risk assessment."""

    risk: float  # 0.0–1.0
    is_friendly: bool
    modifiers: dict[str, float]


class FratricideEngine:
    """Assesses and resolves fratricide risk.

    Parameters
    ----------
    event_bus:
        For publishing fratricide events.
    rng:
        PRNG generator for stochastic resolution.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: FratricideConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or FratricideConfig()
        self._level_risks = {
            "IDENTIFIED": self._config.identified_base_risk,
            "CLASSIFIED": self._config.classified_base_risk,
            "DETECTED": self._config.detected_only_base_risk,
            "UNKNOWN": self._config.unknown_base_risk,
        }

    def check_fratricide_risk(
        self,
        identification_level: str,
        confidence: float,
        target_is_friendly: bool = False,
        visibility: float = 1.0,
        urban_terrain: bool = False,
        stress_level: float = 0.0,
    ) -> FratricideRisk:
        """Assess fratricide risk for a potential engagement.

        Parameters
        ----------
        identification_level:
            Contact identification level: "IDENTIFIED", "CLASSIFIED",
            "DETECTED", "UNKNOWN".
        confidence:
            Identification confidence 0.0–1.0.
        target_is_friendly:
            Ground truth: is the target actually friendly?
        visibility:
            Visibility factor 0.0–1.0.
        urban_terrain:
            Whether engagement is in urban terrain.
        stress_level:
            Shooter stress 0.0–1.0.
        """
        cfg = self._config
        modifiers: dict[str, float] = {}

        # Base risk from identification level
        base_risk = self._level_risks.get(identification_level, cfg.unknown_base_risk)
        modifiers["base"] = base_risk

        # Confidence reduces risk
        confidence_factor = max(0.1, 1.0 - confidence * 0.8)
        risk = base_risk * confidence_factor
        modifiers["confidence"] = confidence_factor

        # Poor visibility increases risk
        if visibility < 1.0:
            vis_factor = 1.0 + (1.0 - visibility) * cfg.visibility_risk_multiplier
            risk *= vis_factor
            modifiers["visibility"] = vis_factor

        # Urban terrain increases risk
        if urban_terrain:
            risk *= cfg.urban_risk_multiplier
            modifiers["urban"] = cfg.urban_risk_multiplier

        # Stress increases risk
        if stress_level > 0:
            stress_factor = 1.0 + stress_level * cfg.stress_risk_multiplier
            risk *= stress_factor
            modifiers["stress"] = stress_factor

        risk = min(0.99, risk)

        return FratricideRisk(
            risk=risk,
            is_friendly=target_is_friendly,
            modifiers=modifiers,
        )

    def resolve_fratricide(
        self,
        risk: FratricideRisk,
        shooter_id: str,
        target_id: str,
        weapon_id: str = "",
        timestamp: Any = None,
    ) -> bool:
        """Stochastically determine if fratricide occurs.

        Returns True if the engagement should be blocked (fratricide would
        occur and is prevented), False if clear to fire.
        """
        if not risk.is_friendly:
            return False  # Not actually friendly — no fratricide

        # Roll for fratricide
        if float(self._rng.random()) < risk.risk:
            if timestamp is not None:
                self._event_bus.publish(FratricideEvent(
                    timestamp=timestamp, source=ModuleId.COMBAT,
                    shooter_id=shooter_id, victim_id=target_id,
                    weapon_id=weapon_id, cause="misidentification",
                ))
            return True  # Fratricide occurred
        return False

    def deconflict(
        self,
        shooter_pos: Position,
        fire_direction_rad: float,
        fire_range_m: float,
        friendlies: list[tuple[str, Position]],
    ) -> list[str]:
        """Identify friendlies in the danger zone of a fire mission.

        Parameters
        ----------
        shooter_pos:
            Position of the firing unit.
        fire_direction_rad:
            Direction of fire in radians from north.
        fire_range_m:
            Range of the engagement.
        friendlies:
            List of (entity_id, position) for all friendly units.

        Returns
        -------
        list:
            Entity IDs of friendlies in the danger zone.
        """
        danger_radius = self._config.danger_close_radius_m
        at_risk: list[str] = []

        for eid, pos in friendlies:
            dx = pos.easting - shooter_pos.easting
            dy = pos.northing - shooter_pos.northing
            dist = math.sqrt(dx * dx + dy * dy)

            if dist > fire_range_m + danger_radius:
                continue

            # Check if friendly is near the line of fire
            bearing = math.atan2(dx, dy)
            angle_diff = abs(bearing - fire_direction_rad) % (2 * math.pi)
            if angle_diff > math.pi:
                angle_diff = 2 * math.pi - angle_diff

            # Danger zone: within cone and range
            cone_half_angle = math.atan2(danger_radius, max(dist, 1.0))
            if angle_diff < cone_half_angle and dist < fire_range_m + danger_radius:
                at_risk.append(eid)

        return at_risk

    def get_state(self) -> dict[str, Any]:
        return {"rng_state": self._rng.bit_generator.state}

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]

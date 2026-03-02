"""Air-to-ground combat — CAS, SEAD, DEAD, interdiction.

Models close air support with danger-close proximity checks,
suppression of enemy air defense (SEAD) via anti-radiation missiles
homing on emitting radars, and weapon delivery accuracy degradation
from altitude, speed, guidance type, and environmental conditions.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.events import AirEngagementEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class AirGroundMission(enum.IntEnum):
    """Air-to-ground mission classification."""

    CAS = 0
    SEAD = 1
    DEAD = 2
    AIR_INTERDICTION = 3
    BAI = 4


class AirGroundConfig(BaseModel):
    """Tunable parameters for air-to-ground engagements."""

    danger_close_radius_m: float = 600.0
    danger_close_abort_threshold: float = 0.3
    arm_baseline_pk: float = 0.6
    arm_emcon_penalty: float = 0.85
    altitude_accuracy_penalty_per_km: float = 0.02
    speed_accuracy_penalty_per_100mps: float = 0.03
    guided_base_accuracy: float = 0.85
    unguided_base_accuracy: float = 0.35
    weather_accuracy_penalty: float = 0.15
    night_accuracy_penalty: float = 0.10


@dataclass
class CASResult:
    """Outcome of a close air support engagement."""

    aircraft_id: str
    target_id: str
    weapon_pk: float = 0.0
    effective_pk: float = 0.0
    hit: bool = False
    danger_close: bool = False
    friendly_distance_m: float = 0.0
    aborted: bool = False
    abort_reason: str = ""


@dataclass
class SEADResult:
    """Outcome of a SEAD/DEAD engagement."""

    aircraft_id: str
    target_ad_id: str
    arm_pk: float = 0.0
    effective_pk: float = 0.0
    hit: bool = False
    target_emitting: bool = False
    emcon_defeated: bool = False


class AirGroundEngine:
    """Resolves air-to-ground engagements (CAS, SEAD, interdiction).

    Parameters
    ----------
    event_bus:
        For publishing engagement events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: AirGroundConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or AirGroundConfig()
        self._missions_executed: int = 0

    def execute_cas(
        self,
        aircraft_id: str,
        target_id: str,
        aircraft_pos: Position,
        target_pos: Position,
        weapon_pk: float,
        friendly_pos: Position | None = None,
        guidance_type: str = "gps",
        conditions: dict[str, float] | None = None,
        timestamp: Any = None,
    ) -> CASResult:
        """Execute a close air support engagement.

        Parameters
        ----------
        aircraft_id:
            Attacking aircraft entity ID.
        target_id:
            Ground target entity ID.
        aircraft_pos:
            Aircraft position (ENU).
        target_pos:
            Ground target position (ENU).
        weapon_pk:
            Base weapon probability of kill.
        friendly_pos:
            Nearest friendly position for danger-close check.
        guidance_type:
            "gps", "laser", "unguided", etc.
        conditions:
            Environmental conditions dict (visibility, weather_penalty, night).
        timestamp:
            Simulation timestamp for events.
        """
        cfg = self._config
        conditions = conditions or {}

        result = CASResult(
            aircraft_id=aircraft_id,
            target_id=target_id,
            weapon_pk=weapon_pk,
        )

        # Danger-close check
        if friendly_pos is not None:
            dx = target_pos.easting - friendly_pos.easting
            dy = target_pos.northing - friendly_pos.northing
            friendly_dist = math.sqrt(dx * dx + dy * dy)
            result.friendly_distance_m = friendly_dist
            result.danger_close = friendly_dist < cfg.danger_close_radius_m

            if result.danger_close:
                # Risk of fratricide — may abort
                risk_factor = 1.0 - (friendly_dist / cfg.danger_close_radius_m)
                if risk_factor > cfg.danger_close_abort_threshold:
                    result.aborted = True
                    result.abort_reason = "danger_close"
                    return result

        # Weapon delivery accuracy
        altitude_m = max(0.0, aircraft_pos.altitude)
        speed_mps = conditions.get("speed_mps", 200.0)
        accuracy = self.compute_weapon_delivery_accuracy(
            altitude_m, speed_mps, guidance_type, conditions,
        )

        effective_pk = weapon_pk * accuracy
        effective_pk = max(0.01, min(0.99, effective_pk))
        result.effective_pk = effective_pk

        hit = float(self._rng.random()) < effective_pk
        result.hit = hit

        self._missions_executed += 1

        if timestamp is not None:
            self._event_bus.publish(AirEngagementEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                attacker_id=aircraft_id, target_id=target_id,
                engagement_type="CAS",
            ))

        return result

    def execute_sead(
        self,
        aircraft_id: str,
        target_ad_id: str,
        aircraft_pos: Position,
        target_pos: Position,
        arm_pk: float = 0.6,
        target_emitting: bool = True,
        timestamp: Any = None,
    ) -> SEADResult:
        """Execute a SEAD engagement with anti-radiation missile.

        Parameters
        ----------
        aircraft_id:
            Attacking aircraft entity ID.
        target_ad_id:
            Target air defense system entity ID.
        aircraft_pos:
            Aircraft position (ENU).
        target_pos:
            Target AD system position (ENU).
        arm_pk:
            Base Pk of the anti-radiation missile.
        target_emitting:
            Whether the target radar is actively emitting.
        timestamp:
            Simulation timestamp for events.
        """
        cfg = self._config

        result = SEADResult(
            aircraft_id=aircraft_id,
            target_ad_id=target_ad_id,
            arm_pk=arm_pk,
            target_emitting=target_emitting,
        )

        if not target_emitting:
            # EMCON — radar not emitting, ARM cannot home
            effective_pk = arm_pk * (1.0 - cfg.arm_emcon_penalty)
            result.emcon_defeated = True
        else:
            effective_pk = arm_pk

        # Range factor
        dx = target_pos.easting - aircraft_pos.easting
        dy = target_pos.northing - aircraft_pos.northing
        dz = target_pos.altitude - aircraft_pos.altitude
        range_m = math.sqrt(dx * dx + dy * dy + dz * dz)
        range_factor = max(0.3, 1.0 - 0.3 * (range_m / 100_000.0))
        effective_pk *= range_factor

        effective_pk = max(0.01, min(0.99, effective_pk))
        result.effective_pk = effective_pk

        hit = float(self._rng.random()) < effective_pk
        result.hit = hit

        self._missions_executed += 1

        if timestamp is not None:
            self._event_bus.publish(AirEngagementEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                attacker_id=aircraft_id, target_id=target_ad_id,
                engagement_type="SEAD",
            ))

        return result

    def compute_weapon_delivery_accuracy(
        self,
        altitude_m: float,
        speed_mps: float,
        guidance_type: str,
        conditions: dict[str, float] | None = None,
    ) -> float:
        """Compute weapon delivery accuracy factor.

        Parameters
        ----------
        altitude_m:
            Release altitude in meters.
        speed_mps:
            Aircraft speed at release in m/s.
        guidance_type:
            "gps", "laser", "unguided", etc.
        conditions:
            Environmental conditions (weather_penalty: 0-1, night: 0 or 1).

        Returns
        -------
        float
            Accuracy factor 0.0--1.0 applied to weapon Pk.
        """
        cfg = self._config
        conditions = conditions or {}

        # Base accuracy from guidance type
        if guidance_type in ("gps", "laser", "combined"):
            accuracy = cfg.guided_base_accuracy
        else:
            accuracy = cfg.unguided_base_accuracy

        # Altitude penalty (higher release = less accurate for unguided)
        alt_km = altitude_m / 1000.0
        altitude_penalty = cfg.altitude_accuracy_penalty_per_km * alt_km
        accuracy -= altitude_penalty

        # Speed penalty
        speed_penalty = cfg.speed_accuracy_penalty_per_100mps * (speed_mps / 100.0)
        accuracy -= speed_penalty

        # Weather penalty
        weather = conditions.get("weather_penalty", 0.0)
        accuracy -= cfg.weather_accuracy_penalty * weather

        # Night penalty
        night = conditions.get("night", 0.0)
        accuracy -= cfg.night_accuracy_penalty * night

        return max(0.05, min(1.0, accuracy))

    def get_state(self) -> dict[str, Any]:
        """Return serialisable engine state."""
        return {
            "rng_state": self._rng.bit_generator.state,
            "missions_executed": self._missions_executed,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a previous snapshot."""
        self._rng.bit_generator.state = state["rng_state"]
        self._missions_executed = state["missions_executed"]

"""Air defense — SAM engagement envelopes, shoot-look-shoot, threat evaluation.

Models surface-to-air missile systems with 3-D engagement envelopes
(min/max altitude and range), threat prioritisation (missiles > fighters >
transports), and shoot-look-shoot doctrine to conserve interceptors.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.events import AirEngagementEvent, MissileInterceptEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position

logger = get_logger(__name__)


class EngagementDoctrine(enum.IntEnum):
    """Fire control doctrine for engaging aerial targets."""

    SHOOT_SHOOT = 0
    SHOOT_LOOK_SHOOT = 1
    HOLD_FIRE = 2


class AirDefenseConfig(BaseModel):
    """Tunable parameters for air defense engagements."""

    default_min_altitude_m: float = 30.0
    default_max_altitude_m: float = 24_000.0
    default_max_range_m: float = 80_000.0
    rcs_reference_m2: float = 3.0
    rcs_pk_exponent: float = 0.25
    shoot_look_assess_time_s: float = 8.0
    max_sls_shots: int = 3
    threat_weight_speed: float = 0.3
    threat_weight_altitude: float = 0.2
    threat_weight_type: float = 0.5


@dataclass
class ThreatAssessment:
    """Prioritised threat evaluation of an aerial target."""

    target_type: str
    threat_score: float
    priority: int  # lower = more urgent
    is_attacking: bool = False
    speed_factor: float = 0.0
    altitude_factor: float = 0.0
    type_factor: float = 0.0


@dataclass
class InterceptResult:
    """Outcome of a single interceptor engagement."""

    ad_id: str
    target_id: str
    interceptor_pk: float = 0.0
    effective_pk: float = 0.0
    hit: bool = False
    range_m: float = 0.0
    shot_number: int = 1


class AirDefenseEngine:
    """Resolves surface-to-air engagements with threat prioritisation.

    Parameters
    ----------
    event_bus:
        For publishing intercept events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: AirDefenseConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or AirDefenseConfig()
        self._interceptors_fired: int = 0

    def evaluate_threat(
        self,
        target_type: str,
        target_speed_mps: float = 250.0,
        target_altitude_m: float = 5000.0,
        is_attacking: bool = False,
    ) -> ThreatAssessment:
        """Evaluate threat level of an aerial target.

        Priority ordering: missiles > fighters > helicopters > transports.

        Parameters
        ----------
        target_type:
            "missile", "fighter", "helicopter", "transport", "uav".
        target_speed_mps:
            Target speed in m/s.
        target_altitude_m:
            Target altitude in meters.
        is_attacking:
            Whether the target is in an attack profile.
        """
        cfg = self._config

        # Type factor: missiles most threatening, transports least
        type_scores = {
            "missile": 1.0,
            "fighter": 0.8,
            "helicopter": 0.6,
            "uav": 0.5,
            "transport": 0.3,
        }
        type_factor = type_scores.get(target_type, 0.5)

        # Speed factor: faster = more threatening (normalised to Mach ~1)
        speed_factor = min(1.0, target_speed_mps / 340.0)

        # Altitude factor: lower altitude = more threatening (harder to engage)
        altitude_factor = max(0.0, 1.0 - target_altitude_m / 20_000.0)

        threat_score = (
            cfg.threat_weight_type * type_factor
            + cfg.threat_weight_speed * speed_factor
            + cfg.threat_weight_altitude * altitude_factor
        )

        # Attacking bonus
        if is_attacking:
            threat_score = min(1.0, threat_score + 0.2)

        # Convert to priority (1 = highest)
        if threat_score > 0.8:
            priority = 1
        elif threat_score > 0.6:
            priority = 2
        elif threat_score > 0.4:
            priority = 3
        else:
            priority = 4

        return ThreatAssessment(
            target_type=target_type,
            threat_score=threat_score,
            priority=priority,
            is_attacking=is_attacking,
            speed_factor=speed_factor,
            altitude_factor=altitude_factor,
            type_factor=type_factor,
        )

    def can_engage_target(
        self,
        ad_pos: Position,
        target_pos: Position,
        target_altitude_m: float | None = None,
        min_alt_m: float | None = None,
        max_alt_m: float | None = None,
        max_range_m: float | None = None,
    ) -> bool:
        """Check if a target falls within the 3-D engagement envelope.

        Parameters
        ----------
        ad_pos:
            Air defense system position.
        target_pos:
            Target position.
        target_altitude_m:
            Target altitude (uses target_pos.altitude if ``None``).
        min_alt_m:
            Minimum engagement altitude (uses config default if ``None``).
        max_alt_m:
            Maximum engagement altitude (uses config default if ``None``).
        max_range_m:
            Maximum engagement range (uses config default if ``None``).
        """
        cfg = self._config
        min_alt = min_alt_m if min_alt_m is not None else cfg.default_min_altitude_m
        max_alt = max_alt_m if max_alt_m is not None else cfg.default_max_altitude_m
        max_range = max_range_m if max_range_m is not None else cfg.default_max_range_m

        alt = target_altitude_m if target_altitude_m is not None else target_pos.altitude

        # Altitude check
        if alt < min_alt or alt > max_alt:
            return False

        # Slant range check
        dx = target_pos.easting - ad_pos.easting
        dy = target_pos.northing - ad_pos.northing
        dz = alt - ad_pos.altitude
        slant_range = math.sqrt(dx * dx + dy * dy + dz * dz)

        return slant_range <= max_range

    def fire_interceptor(
        self,
        ad_id: str,
        target_id: str,
        interceptor_pk: float,
        range_m: float,
        target_rcs_m2: float = 3.0,
        countermeasures: str = "none",
        shot_number: int = 1,
        timestamp: Any = None,
        weather_modifier: float = 1.0,
    ) -> InterceptResult:
        """Fire a single interceptor at an aerial target.

        Parameters
        ----------
        ad_id:
            Air defense system entity ID.
        target_id:
            Target entity ID.
        interceptor_pk:
            Base single-shot Pk of the interceptor.
        range_m:
            Slant range to target in meters.
        target_rcs_m2:
            Target radar cross section in m^2.
        countermeasures:
            "chaff", "ecm", or "none".
        shot_number:
            Which shot in a sequence (for logging).
        timestamp:
            Simulation timestamp for events.
        weather_modifier:
            Weather quality 0.0--1.0 (heavy rain/clutter degrades tracking).
        """
        cfg = self._config

        # RCS factor: larger RCS = easier to track
        rcs_factor = (target_rcs_m2 / cfg.rcs_reference_m2) ** cfg.rcs_pk_exponent
        rcs_factor = min(1.5, max(0.3, rcs_factor))

        # Range factor: Pk degrades at longer ranges
        max_range = cfg.default_max_range_m
        range_factor = max(0.3, 1.0 - 0.5 * (range_m / max_range))

        effective_pk = interceptor_pk * rcs_factor * range_factor

        # Countermeasure reduction
        if countermeasures == "chaff":
            effective_pk *= 0.7
        elif countermeasures == "ecm":
            effective_pk *= 0.6

        effective_pk = max(0.01, min(0.99, effective_pk))

        # Weather degradation (heavy rain/clutter affects radar tracking)
        effective_pk *= weather_modifier
        effective_pk = max(0.01, min(0.99, effective_pk))

        hit = float(self._rng.random()) < effective_pk
        self._interceptors_fired += 1

        if timestamp is not None:
            self._event_bus.publish(MissileInterceptEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                defender_id=ad_id, missile_id=target_id,
                interceptor_type="SAM", success=hit,
            ))

        return InterceptResult(
            ad_id=ad_id,
            target_id=target_id,
            interceptor_pk=interceptor_pk,
            effective_pk=effective_pk,
            hit=hit,
            range_m=range_m,
            shot_number=shot_number,
        )

    def shoot_look_shoot(
        self,
        ad_id: str,
        target_id: str,
        interceptor_pk: float,
        max_shots: int = 2,
        range_m: float = 30_000.0,
        target_rcs_m2: float = 3.0,
        countermeasures: str = "none",
        timestamp: Any = None,
        weather_modifier: float = 1.0,
    ) -> list[InterceptResult]:
        """Execute shoot-look-shoot doctrine.

        Fire an interceptor, assess the result, and fire again if missed.

        Parameters
        ----------
        ad_id:
            Air defense system entity ID.
        target_id:
            Target entity ID.
        interceptor_pk:
            Base Pk per interceptor.
        max_shots:
            Maximum number of interceptors to fire.
        range_m:
            Slant range to target.
        target_rcs_m2:
            Target RCS.
        countermeasures:
            Countermeasure type.
        timestamp:
            Simulation timestamp for events.
        weather_modifier:
            Weather quality 0.0--1.0 (passed through to fire_interceptor).
        """
        cfg = self._config
        max_shots = min(max_shots, cfg.max_sls_shots)
        results: list[InterceptResult] = []

        for shot_num in range(1, max_shots + 1):
            result = self.fire_interceptor(
                ad_id=ad_id,
                target_id=target_id,
                interceptor_pk=interceptor_pk,
                range_m=range_m,
                target_rcs_m2=target_rcs_m2,
                countermeasures=countermeasures,
                shot_number=shot_num,
                timestamp=timestamp,
                weather_modifier=weather_modifier,
            )
            results.append(result)

            if result.hit:
                logger.debug(
                    "SLS: %s killed %s on shot %d", ad_id, target_id, shot_num,
                )
                break

        return results

    def get_state(self) -> dict[str, Any]:
        """Return serialisable engine state."""
        return {
            "rng_state": self._rng.bit_generator.state,
            "interceptors_fired": self._interceptors_fired,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a previous snapshot."""
        self._rng.bit_generator.state = state["rng_state"]
        self._interceptors_fired = state["interceptors_fired"]

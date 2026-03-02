"""Air-to-air combat — BVR (AMRAAM-type), WVR (Sidewinder-type), guns.

Models three regimes of air combat: beyond-visual-range active radar homing,
within-visual-range IR homing with aspect angle dependency, and guns
engagements with deflection shooting.  Countermeasures (chaff vs radar,
flares vs IR) degrade missile Pk.
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


class AirCombatMode(enum.IntEnum):
    """Air-to-air engagement regime."""

    BVR = 0
    WVR = 1
    GUNS_ONLY = 2


class AirCombatConfig(BaseModel):
    """Tunable parameters for air-to-air combat."""

    bvr_max_range_m: float = 80_000.0
    bvr_min_range_m: float = 10_000.0
    wvr_max_range_m: float = 10_000.0
    wvr_min_range_m: float = 500.0
    guns_max_range_m: float = 1_000.0
    guns_min_range_m: float = 100.0
    chaff_effectiveness: float = 0.3
    flare_effectiveness: float = 0.4
    rear_hemisphere_bonus: float = 0.25
    pilot_skill_weight: float = 0.4
    deflection_penalty_per_deg: float = 0.005
    guns_base_pk: float = 0.15


@dataclass
class AirCombatResult:
    """Outcome of an air-to-air engagement."""

    mode: AirCombatMode
    attacker_id: str
    target_id: str
    missile_pk: float = 0.0
    effective_pk: float = 0.0
    hit: bool = False
    range_m: float = 0.0
    countermeasure_reduction: float = 0.0


class AirCombatEngine:
    """Resolves air-to-air engagements across BVR, WVR, and guns regimes.

    Parameters
    ----------
    event_bus:
        For publishing air engagement events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: AirCombatConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or AirCombatConfig()
        self._engagements_resolved: int = 0

    def resolve_air_engagement(
        self,
        attacker_id: str,
        defender_id: str,
        attacker_pos: Position,
        defender_pos: Position,
        missile_pk: float = 0.7,
        mode: AirCombatMode | None = None,
        aspect_angle_deg: float = 0.0,
        pilot_skill: float = 0.5,
        countermeasure_type: str = "none",
        timestamp: Any = None,
    ) -> AirCombatResult:
        """Resolve an air-to-air engagement, auto-selecting mode if not given.

        Parameters
        ----------
        attacker_id:
            Attacking aircraft entity ID.
        defender_id:
            Target aircraft entity ID.
        attacker_pos:
            Attacker position (ENU).
        defender_pos:
            Defender position (ENU).
        missile_pk:
            Base single-shot probability of kill for missile.
        mode:
            Engagement mode (auto-selected from range if ``None``).
        aspect_angle_deg:
            Angle off tail for WVR (0 = tail-on, 180 = head-on).
        pilot_skill:
            Pilot skill factor 0.0--1.0.
        countermeasure_type:
            "chaff", "flare", or "none".
        timestamp:
            Simulation timestamp for events.
        """
        dx = defender_pos.easting - attacker_pos.easting
        dy = defender_pos.northing - attacker_pos.northing
        dz = defender_pos.altitude - attacker_pos.altitude
        range_m = math.sqrt(dx * dx + dy * dy + dz * dz)

        cfg = self._config

        # Auto-select mode based on range
        if mode is None:
            if range_m >= cfg.bvr_min_range_m and range_m <= cfg.bvr_max_range_m:
                mode = AirCombatMode.BVR
            elif range_m <= cfg.wvr_max_range_m and range_m >= cfg.wvr_min_range_m:
                mode = AirCombatMode.WVR
            else:
                mode = AirCombatMode.GUNS_ONLY

        if mode == AirCombatMode.BVR:
            result = self.bvr_engagement(
                attacker_id, defender_id, range_m, missile_pk, countermeasure_type,
            )
        elif mode == AirCombatMode.WVR:
            result = self.wvr_engagement(
                attacker_id, defender_id, range_m, missile_pk, aspect_angle_deg,
                countermeasure_type,
            )
        else:
            result = self.guns_engagement(
                attacker_id, defender_id, range_m, pilot_skill, aspect_angle_deg,
            )

        self._engagements_resolved += 1

        if timestamp is not None:
            self._event_bus.publish(AirEngagementEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                attacker_id=attacker_id, target_id=defender_id,
                engagement_type=mode.name,
            ))

        return result

    def bvr_engagement(
        self,
        attacker_id: str,
        defender_id: str,
        range_m: float,
        missile_pk: float,
        countermeasures: str = "none",
    ) -> AirCombatResult:
        """Resolve a BVR engagement with active radar homing missile.

        Parameters
        ----------
        attacker_id:
            Attacker entity ID.
        defender_id:
            Target entity ID.
        range_m:
            Engagement range in meters.
        missile_pk:
            Base single-shot Pk of the missile.
        countermeasures:
            "chaff", "flare", or "none".
        """
        cfg = self._config

        # Range degradation: Pk drops at long range (linear falloff)
        max_range = cfg.bvr_max_range_m
        range_factor = max(0.3, 1.0 - 0.7 * (range_m / max_range))
        effective_pk = missile_pk * range_factor

        # Apply countermeasures
        cm_reduction = self.apply_countermeasures("radar", countermeasures)
        effective_pk *= (1.0 - cm_reduction)
        effective_pk = max(0.01, min(0.99, effective_pk))

        hit = float(self._rng.random()) < effective_pk

        return AirCombatResult(
            mode=AirCombatMode.BVR,
            attacker_id=attacker_id,
            target_id=defender_id,
            missile_pk=missile_pk,
            effective_pk=effective_pk,
            hit=hit,
            range_m=range_m,
            countermeasure_reduction=cm_reduction,
        )

    def wvr_engagement(
        self,
        attacker_id: str,
        defender_id: str,
        range_m: float,
        missile_pk: float,
        aspect_angle_deg: float = 0.0,
        countermeasures: str = "none",
    ) -> AirCombatResult:
        """Resolve a WVR engagement with IR-homing missile.

        Parameters
        ----------
        attacker_id:
            Attacker entity ID.
        defender_id:
            Target entity ID.
        range_m:
            Engagement range in meters.
        missile_pk:
            Base Pk of the IR missile.
        aspect_angle_deg:
            Angle off tail (0 = tail-on / rear hemisphere = best for IR).
        countermeasures:
            "chaff", "flare", or "none".
        """
        cfg = self._config

        # IR seekers prefer rear hemisphere (hot exhaust)
        # aspect_angle_deg: 0 = tail-on (best), 180 = head-on (worst)
        aspect_factor = 1.0 + cfg.rear_hemisphere_bonus * math.cos(
            math.radians(aspect_angle_deg)
        )
        effective_pk = missile_pk * aspect_factor

        # Range factor (closer = better)
        range_factor = max(0.5, 1.0 - 0.5 * (range_m / cfg.wvr_max_range_m))
        effective_pk *= range_factor

        # Apply countermeasures (flares effective against IR)
        cm_reduction = self.apply_countermeasures("ir", countermeasures)
        effective_pk *= (1.0 - cm_reduction)
        effective_pk = max(0.01, min(0.99, effective_pk))

        hit = float(self._rng.random()) < effective_pk

        return AirCombatResult(
            mode=AirCombatMode.WVR,
            attacker_id=attacker_id,
            target_id=defender_id,
            missile_pk=missile_pk,
            effective_pk=effective_pk,
            hit=hit,
            range_m=range_m,
            countermeasure_reduction=cm_reduction,
        )

    def guns_engagement(
        self,
        attacker_id: str,
        defender_id: str,
        range_m: float,
        pilot_skill: float = 0.5,
        deflection_angle_deg: float = 0.0,
    ) -> AirCombatResult:
        """Resolve a guns engagement with deflection shooting.

        Parameters
        ----------
        attacker_id:
            Attacker entity ID.
        defender_id:
            Target entity ID.
        range_m:
            Engagement range in meters.
        pilot_skill:
            Pilot gunnery skill 0.0--1.0.
        deflection_angle_deg:
            Deflection angle (0 = no deflection, 90 = max crossing).
        """
        cfg = self._config

        # Base Pk modified by skill
        skill_factor = 0.5 + cfg.pilot_skill_weight * pilot_skill
        pk = cfg.guns_base_pk * skill_factor

        # Range penalty (closer is easier)
        range_factor = max(0.2, 1.0 - 0.8 * (range_m / cfg.guns_max_range_m))
        pk *= range_factor

        # Deflection penalty
        defl_penalty = 1.0 - cfg.deflection_penalty_per_deg * abs(deflection_angle_deg)
        defl_penalty = max(0.1, defl_penalty)
        pk *= defl_penalty

        pk = max(0.01, min(0.99, pk))
        hit = float(self._rng.random()) < pk

        return AirCombatResult(
            mode=AirCombatMode.GUNS_ONLY,
            attacker_id=attacker_id,
            target_id=defender_id,
            missile_pk=0.0,
            effective_pk=pk,
            hit=hit,
            range_m=range_m,
            countermeasure_reduction=0.0,
        )

    def apply_countermeasures(
        self,
        guidance_type: str,
        countermeasure_type: str,
    ) -> float:
        """Compute countermeasure effectiveness reduction.

        Parameters
        ----------
        guidance_type:
            "radar" or "ir" for the incoming missile seeker.
        countermeasure_type:
            "chaff", "flare", or "none".

        Returns
        -------
        float
            Fraction of Pk reduction (0.0 = no effect, 1.0 = total defeat).
        """
        cfg = self._config

        if countermeasure_type == "none":
            return 0.0

        if guidance_type == "radar" and countermeasure_type == "chaff":
            return cfg.chaff_effectiveness
        if guidance_type == "ir" and countermeasure_type == "flare":
            return cfg.flare_effectiveness
        # Mismatched CM type (chaff vs IR, flares vs radar) — minimal effect
        return 0.05

    def get_state(self) -> dict[str, Any]:
        """Return serialisable engine state."""
        return {
            "rng_state": self._rng.bit_generator.state,
            "engagements_resolved": self._engagements_resolved,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a previous snapshot."""
        self._rng.bit_generator.state = state["rng_state"]
        self._engagements_resolved = state["engagements_resolved"]

"""Missile defense — BMD layers, C-RAM, discrimination.

Models layered ballistic missile defense with cumulative kill probability
(1 - product of miss probabilities), cruise missile defense with
sea-skimming penalty, C-RAM for short-range rocket/artillery/mortar
defense, and warhead discrimination against decoys.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.events import MissileInterceptEvent
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


class DefenseLayer(enum.IntEnum):
    """Missile defense engagement layer."""

    UPPER_TIER = 0
    LOWER_TIER = 1
    POINT_DEFENSE = 2
    CRAM = 3


class MissileDefenseConfig(BaseModel):
    """Tunable parameters for missile defense."""

    upper_tier_speed_threshold_mps: float = 3000.0
    lower_tier_speed_threshold_mps: float = 1500.0
    sea_skimming_penalty: float = 0.4
    cram_max_range_m: float = 2000.0
    cram_base_pk: float = 0.7
    cram_caliber_factor: float = 0.002
    discrimination_base: float = 0.8
    discrimination_sensor_weight: float = 0.5
    discrimination_decoy_penalty: float = 0.05


@dataclass
class BMDResult:
    """Outcome of a layered ballistic missile defense engagement."""

    layers_engaged: int = 0
    per_layer_pk: list[float] = field(default_factory=list)
    per_layer_hit: list[bool] = field(default_factory=list)
    cumulative_pk: float = 0.0
    intercepted: bool = False
    missile_speed_mps: float = 0.0


@dataclass
class CruiseMissileDefenseResult:
    """Outcome of a cruise missile defense engagement."""

    interceptor_pk: float = 0.0
    effective_pk: float = 0.0
    hit: bool = False
    sea_skimming: bool = False
    missile_speed_mps: float = 0.0


@dataclass
class CRAMResult:
    """Outcome of a C-RAM engagement against incoming rocket/mortar."""

    defender_id: str
    intercepted: bool = False
    effective_pk: float = 0.0
    incoming_caliber_mm: float = 0.0
    range_m: float = 0.0


class MissileDefenseEngine:
    """Resolves layered missile defense, cruise missile defense, and C-RAM.

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
        config: MissileDefenseConfig | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or MissileDefenseConfig()
        self._intercepts_attempted: int = 0

    def engage_ballistic_missile(
        self,
        defender_pks: list[float],
        missile_speed_mps: float = 3000.0,
        defender_id: str = "bmd",
        missile_id: str = "bm",
        timestamp: Any = None,
        early_warning_time_s: float = 0.0,
    ) -> BMDResult:
        """Engage a ballistic missile with layered interceptors.

        Cumulative Pk = 1 - product(1 - Pk_i) for independent layers.

        Parameters
        ----------
        defender_pks:
            Pk for each defense layer (ordered from outer to inner).
        missile_speed_mps:
            Incoming missile speed in m/s.
        defender_id:
            BMD system entity ID.
        missile_id:
            Incoming missile entity ID.
        timestamp:
            Simulation timestamp for events.
        """
        cfg = self._config

        result = BMDResult(missile_speed_mps=missile_speed_mps)

        # Speed penalty: faster missiles are harder to intercept
        if missile_speed_mps > cfg.upper_tier_speed_threshold_mps:
            speed_penalty = 0.8
        elif missile_speed_mps > cfg.lower_tier_speed_threshold_mps:
            speed_penalty = 0.9
        else:
            speed_penalty = 1.0

        # Early warning bonus: more time = better first-layer engagement
        ew_bonus = min(0.15, early_warning_time_s / 600.0) if early_warning_time_s > 60.0 else 0.0

        miss_product = 1.0

        for idx, pk in enumerate(defender_pks):
            effective_pk = pk * speed_penalty
            # Apply early warning bonus to first layer only
            if idx == 0 and ew_bonus > 0:
                effective_pk = min(0.99, effective_pk + ew_bonus)
            effective_pk = max(0.01, min(0.99, effective_pk))
            result.per_layer_pk.append(effective_pk)

            hit = float(self._rng.random()) < effective_pk
            result.per_layer_hit.append(hit)
            result.layers_engaged += 1
            self._intercepts_attempted += 1

            miss_product *= (1.0 - effective_pk)

            if hit:
                result.intercepted = True
                if timestamp is not None:
                    self._event_bus.publish(MissileInterceptEvent(
                        timestamp=timestamp, source=ModuleId.COMBAT,
                        defender_id=defender_id, missile_id=missile_id,
                        interceptor_type="BMD", success=True,
                    ))
                break

        result.cumulative_pk = 1.0 - miss_product

        if not result.intercepted and timestamp is not None:
            self._event_bus.publish(MissileInterceptEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                defender_id=defender_id, missile_id=missile_id,
                interceptor_type="BMD", success=False,
            ))

        return result

    def engage_cruise_missile(
        self,
        defender_pk: float,
        missile_speed_mps: float = 250.0,
        sea_skimming: bool = False,
        defender_id: str = "ad",
        missile_id: str = "cm",
        timestamp: Any = None,
    ) -> CruiseMissileDefenseResult:
        """Engage a cruise missile.

        Parameters
        ----------
        defender_pk:
            Base Pk of the defending system.
        missile_speed_mps:
            Incoming cruise missile speed.
        sea_skimming:
            Whether the missile is sea-skimming (reduces Pk significantly).
        defender_id:
            Defender entity ID.
        missile_id:
            Cruise missile entity ID.
        timestamp:
            Simulation timestamp for events.
        """
        cfg = self._config

        effective_pk = defender_pk

        # Sea-skimming penalty (radar clutter, late detection)
        if sea_skimming:
            effective_pk *= (1.0 - cfg.sea_skimming_penalty)

        # Supersonic penalty
        if missile_speed_mps > 340.0:
            mach = missile_speed_mps / 340.0
            speed_penalty = max(0.5, 1.0 - 0.1 * (mach - 1.0))
            effective_pk *= speed_penalty

        effective_pk = max(0.01, min(0.99, effective_pk))

        hit = float(self._rng.random()) < effective_pk
        self._intercepts_attempted += 1

        if timestamp is not None:
            self._event_bus.publish(MissileInterceptEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                defender_id=defender_id, missile_id=missile_id,
                interceptor_type="CRUISE_DEFENSE", success=hit,
            ))

        return CruiseMissileDefenseResult(
            interceptor_pk=defender_pk,
            effective_pk=effective_pk,
            hit=hit,
            sea_skimming=sea_skimming,
            missile_speed_mps=missile_speed_mps,
        )

    def engage_cram(
        self,
        defender_id: str,
        incoming_caliber_mm: float = 107.0,
        range_m: float = 1000.0,
        timestamp: Any = None,
    ) -> CRAMResult:
        """Engage an incoming rocket, artillery, or mortar round with C-RAM.

        Parameters
        ----------
        defender_id:
            C-RAM system entity ID.
        incoming_caliber_mm:
            Caliber of the incoming projectile in mm.
        range_m:
            Engagement range in meters.
        timestamp:
            Simulation timestamp for events.
        """
        cfg = self._config

        if range_m > cfg.cram_max_range_m:
            return CRAMResult(
                defender_id=defender_id,
                intercepted=False,
                effective_pk=0.0,
                incoming_caliber_mm=incoming_caliber_mm,
                range_m=range_m,
            )

        # Base Pk
        pk = cfg.cram_base_pk

        # Range factor (closer = better)
        range_factor = max(0.3, 1.0 - 0.5 * (range_m / cfg.cram_max_range_m))
        pk *= range_factor

        # Larger caliber = slightly easier to track but more robust
        caliber_factor = 1.0 - cfg.cram_caliber_factor * max(0.0, incoming_caliber_mm - 80.0)
        caliber_factor = max(0.5, caliber_factor)
        pk *= caliber_factor

        pk = max(0.01, min(0.99, pk))

        hit = float(self._rng.random()) < pk
        self._intercepts_attempted += 1

        if timestamp is not None:
            self._event_bus.publish(MissileInterceptEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                defender_id=defender_id, missile_id="incoming",
                interceptor_type="CRAM", success=hit,
            ))

        return CRAMResult(
            defender_id=defender_id,
            intercepted=hit,
            effective_pk=pk,
            incoming_caliber_mm=incoming_caliber_mm,
            range_m=range_m,
        )

    def compute_discrimination(
        self,
        sensor_quality: float = 0.5,
        decoy_count: int = 0,
    ) -> float:
        """Compute probability of correctly discriminating warhead from decoys.

        Parameters
        ----------
        sensor_quality:
            Quality of discrimination sensors 0.0--1.0.
        decoy_count:
            Number of decoys accompanying the warhead.

        Returns
        -------
        float
            Probability of correct discrimination 0.0--1.0.
        """
        cfg = self._config

        # Base discrimination from sensor quality
        base = cfg.discrimination_base * (
            1.0 - cfg.discrimination_sensor_weight
            + cfg.discrimination_sensor_weight * sensor_quality
        )

        # Decoys degrade discrimination
        decoy_penalty = cfg.discrimination_decoy_penalty * decoy_count
        discrimination = base - decoy_penalty

        return max(0.05, min(1.0, discrimination))

    def get_state(self) -> dict[str, Any]:
        """Return serialisable engine state."""
        return {
            "rng_state": self._rng.bit_generator.state,
            "intercepts_attempted": self._intercepts_attempted,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a previous snapshot."""
        self._rng.bit_generator.state = state["rng_state"]
        self._intercepts_attempted = state["intercepts_attempted"]

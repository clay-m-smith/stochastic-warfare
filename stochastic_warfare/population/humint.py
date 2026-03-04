"""Civilian HUMINT generation.

Phase 12e-4. Friendly civilian population generates detection tips;
hostile population warns the enemy.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId, Position
from stochastic_warfare.population.civilians import (
    CivilianDisposition,
    CivilianManager,
    CivilianRegion,
)
from stochastic_warfare.population.events import HumintTipEvent

logger = get_logger(__name__)


class HumintConfig(BaseModel):
    """HUMINT generation configuration."""

    base_tip_rate: float = 0.1
    """Tips per hour per region at maximum conditions."""
    position_noise_m: float = 500.0
    """Standard deviation of reported position noise (meters)."""
    tip_delay_hours: float = 1.0
    """Base delay before tip reaches intelligence fusion."""
    density_scale: float = 10000.0
    """Population density normalization (tips scale with pop/density_scale)."""


class CivilianHumintEngine:
    """Generate HUMINT tips from civilian population.

    Friendly populations report enemy movements. Hostile populations
    warn the enemy about friendly movements.

    Parameters
    ----------
    civilian_manager : CivilianManager
        Source of region data.
    event_bus : EventBus
        For publishing HUMINT tip events.
    rng : numpy.random.Generator
        Deterministic PRNG stream.
    config : HumintConfig | None
        Configuration.
    """

    def __init__(
        self,
        civilian_manager: CivilianManager,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: HumintConfig | None = None,
    ) -> None:
        self._civilians = civilian_manager
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or HumintConfig()

    def generate_tips(
        self,
        enemy_units: list[tuple[str, Position, str]],
        dt_hours: float,
        timestamp: datetime | None = None,
    ) -> list[dict]:
        """Generate HUMINT tips for the current time step.

        Parameters
        ----------
        enemy_units:
            List of (unit_id, position, side) for all units. Tips are
            generated about units that are in regions with opposing
            disposition.
        dt_hours:
            Time step in hours.
        timestamp:
            Simulation timestamp.

        Returns
        -------
        list[dict]
            Generated tips with keys: region_id, target_unit_id,
            reported_position, reliability, delay_hours, tip_side.
        """
        ts = timestamp or datetime.now(tz=timezone.utc)
        cfg = self._config
        tips: list[dict] = []

        for region in self._civilians.all_regions():
            if region.disposition == CivilianDisposition.NEUTRAL:
                continue

            # Find units within this region
            for unit_id, unit_pos, unit_side in enemy_units:
                dx = unit_pos.easting - region.center.easting
                dy = unit_pos.northing - region.center.northing
                if math.hypot(dx, dy) > region.radius_m:
                    continue

                # Determine if this generates a tip
                # FRIENDLY pop reports enemies, HOSTILE pop reports friendlies
                if region.disposition == CivilianDisposition.FRIENDLY:
                    # Reports about enemy units (unit_side != region's friendly side)
                    tip_side = "blue"  # friendly reports go to blue
                elif region.disposition == CivilianDisposition.HOSTILE:
                    tip_side = "red"  # hostile pop warns the enemy
                elif region.disposition == CivilianDisposition.MIXED:
                    # 50/50 chance of either side
                    tip_side = "blue" if self._rng.random() < 0.5 else "red"
                else:
                    continue

                # Poisson tip generation
                pop_factor = min(1.0, region.population / cfg.density_scale)
                rate = cfg.base_tip_rate * pop_factor * dt_hours
                n_tips = int(self._rng.poisson(rate))

                for _ in range(n_tips):
                    # Add position noise
                    noise_e = self._rng.normal(0.0, cfg.position_noise_m)
                    noise_n = self._rng.normal(0.0, cfg.position_noise_m)
                    reported_pos = Position(
                        unit_pos.easting + noise_e,
                        unit_pos.northing + noise_n,
                        unit_pos.altitude,
                    )
                    # Reliability based on disposition strength
                    reliability = 0.3 + 0.4 * self._rng.random()
                    delay = cfg.tip_delay_hours * (0.5 + self._rng.random())

                    tip = {
                        "region_id": region.region_id,
                        "target_unit_id": unit_id,
                        "reported_position": reported_pos,
                        "reliability": reliability,
                        "delay_hours": delay,
                        "tip_side": tip_side,
                    }
                    tips.append(tip)
                    self._event_bus.publish(HumintTipEvent(
                        timestamp=ts,
                        source=ModuleId.POPULATION,
                        region_id=region.region_id,
                        target_unit_id=unit_id,
                        reported_position=reported_pos,
                        reliability=reliability,
                        delay_hours=delay,
                        tip_side=tip_side,
                    ))

        return tips

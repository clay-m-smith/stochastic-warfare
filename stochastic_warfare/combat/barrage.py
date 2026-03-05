"""WW1 artillery barrage — aggregate fire density model.

Models standing, creeping, box, and counter-battery barrages as aggregate
fire density (rounds/hectare) rather than individual shell trajectories.
A WW1 barrage involves thousands of shells over hours — aggregate
modelling is both physically sound and computationally tractable.

Physics
-------
* Fire density (rounds/hectare) → suppression probability and casualty
  probability per tick.
* Creeping advance: barrage center moves forward at a configured rate
  (historical: ~50 m/min).
* Drift: 2-D Gaussian with sigma growing over time (barrel wear, FO
  communication lag).
* Friendly fire risk: infantry within a safety zone of the barrage
  center.
* Dugout protection: reduces casualty probability but not suppression.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BarrageType(enum.IntEnum):
    """Classification of artillery barrage."""

    STANDING = 0
    CREEPING = 1
    BOX = 2
    COUNTER_BATTERY = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class BarrageConfig(BaseModel):
    """Configuration for WW1 barrage model."""

    suppression_rate_per_round_hectare: float = 0.003
    """Suppression probability per round-per-hectare of fire density."""

    casualty_rate_per_round_hectare: float = 0.0005
    """Casualty probability per round-per-hectare of fire density."""

    dugout_protection_factor: float = 0.85
    """Fraction of casualty probability negated by dugout shelter."""

    creeping_advance_rate_mps: float = 0.833
    """Creeping barrage advance rate in m/s (default 50 m/min)."""

    drift_sigma_m_per_min: float = 5.0
    """1-sigma drift per minute of barrage duration."""

    friendly_fire_zone_m: float = 100.0
    """Distance from barrage center within which friendly fire is possible."""

    friendly_fire_probability: float = 0.1
    """Base probability of friendly fire if in the danger zone."""

    default_duration_s: float = 3600.0
    """Default barrage duration in seconds."""

    trench_condition_loss_per_density: float = 0.0001
    """Trench condition loss per round/hectare of fire density."""


# ---------------------------------------------------------------------------
# Barrage zone state
# ---------------------------------------------------------------------------


@dataclass
class BarrageZone:
    """Tracks the state of a single barrage."""

    barrage_id: str
    barrage_type: BarrageType
    side: str
    center_easting: float
    center_northing: float
    width_m: float = 500.0
    depth_m: float = 200.0
    heading_deg: float = 0.0
    """Heading of the barrage advance (0 = north)."""
    advance_rate_mps: float = 0.0
    """Advance rate (0 for standing)."""
    fire_density_rounds_per_hectare: float = 100.0
    elapsed_s: float = 0.0
    duration_s: float = 3600.0
    drift_easting_m: float = 0.0
    drift_northing_m: float = 0.0
    active: bool = True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BarrageEngine:
    """WW1 artillery barrage engine.

    Parameters
    ----------
    config:
        Barrage configuration.
    rng:
        Numpy random generator for drift and effects.
    """

    def __init__(
        self,
        config: BarrageConfig | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._config = config or BarrageConfig()
        self._rng = rng
        self._barrages: dict[str, BarrageZone] = {}

    def create_barrage(
        self,
        barrage_id: str,
        barrage_type: BarrageType,
        side: str,
        center_easting: float,
        center_northing: float,
        width_m: float = 500.0,
        depth_m: float = 200.0,
        heading_deg: float = 0.0,
        fire_density: float = 100.0,
        duration_s: float | None = None,
    ) -> BarrageZone:
        """Create a new barrage zone."""
        dur = duration_s or self._config.default_duration_s
        advance = (
            self._config.creeping_advance_rate_mps
            if barrage_type == BarrageType.CREEPING
            else 0.0
        )
        zone = BarrageZone(
            barrage_id=barrage_id,
            barrage_type=barrage_type,
            side=side,
            center_easting=center_easting,
            center_northing=center_northing,
            width_m=width_m,
            depth_m=depth_m,
            heading_deg=heading_deg,
            advance_rate_mps=advance,
            fire_density_rounds_per_hectare=fire_density,
            duration_s=dur,
        )
        self._barrages[barrage_id] = zone
        logger.info(
            "Created %s barrage %s at (%.0f, %.0f), density=%.0f rpH",
            BarrageType(barrage_type).name, barrage_id,
            center_easting, center_northing, fire_density,
        )
        return zone

    def update(
        self,
        dt_s: float,
        trench_engine: Any = None,
    ) -> None:
        """Advance all active barrages by *dt_s* seconds.

        Parameters
        ----------
        dt_s:
            Time step in seconds.
        trench_engine:
            Optional :class:`TrenchSystemEngine` for trench degradation.
        """
        cfg = self._config

        for zone in self._barrages.values():
            if not zone.active:
                continue

            zone.elapsed_s += dt_s

            # Expire
            if zone.elapsed_s >= zone.duration_s:
                zone.active = False
                continue

            # Creeping advance
            if zone.advance_rate_mps > 0:
                advance_m = zone.advance_rate_mps * dt_s
                rad = math.radians(zone.heading_deg)
                zone.center_easting += advance_m * math.sin(rad)
                zone.center_northing += advance_m * math.cos(rad)

            # Drift accumulation
            dt_min = dt_s / 60.0
            sigma = cfg.drift_sigma_m_per_min * math.sqrt(dt_min)
            if sigma > 0:
                zone.drift_easting_m += self._rng.normal(0, sigma)
                zone.drift_northing_m += self._rng.normal(0, sigma)

            # Trench degradation
            if trench_engine is not None:
                radius = max(zone.width_m, zone.depth_m) / 2
                intensity = zone.fire_density_rounds_per_hectare * cfg.trench_condition_loss_per_density
                trench_engine.apply_bombardment(
                    zone.center_easting + zone.drift_easting_m,
                    zone.center_northing + zone.drift_northing_m,
                    radius,
                    intensity,
                )

    def get_barrage_zone_at(
        self,
        easting: float,
        northing: float,
    ) -> BarrageZone | None:
        """Return the active barrage affecting a position, or None."""
        for zone in self._barrages.values():
            if not zone.active:
                continue
            ce = zone.center_easting + zone.drift_easting_m
            cn = zone.center_northing + zone.drift_northing_m
            de = abs(easting - ce)
            dn = abs(northing - cn)
            if de <= zone.width_m / 2 and dn <= zone.depth_m / 2:
                return zone
        return None

    def compute_effects(
        self,
        easting: float,
        northing: float,
        in_dugout: bool = False,
    ) -> dict[str, float]:
        """Compute suppression and casualty probabilities at a position.

        Returns
        -------
        dict with keys ``suppression_p`` and ``casualty_p``.
        """
        zone = self.get_barrage_zone_at(easting, northing)
        if zone is None:
            return {"suppression_p": 0.0, "casualty_p": 0.0}

        cfg = self._config
        density = zone.fire_density_rounds_per_hectare
        sup_p = min(1.0, density * cfg.suppression_rate_per_round_hectare)
        cas_p = density * cfg.casualty_rate_per_round_hectare
        if in_dugout:
            cas_p *= (1.0 - cfg.dugout_protection_factor)
        cas_p = min(1.0, cas_p)

        return {"suppression_p": sup_p, "casualty_p": cas_p}

    def check_friendly_fire(
        self,
        unit_easting: float,
        unit_northing: float,
        unit_side: str,
    ) -> float:
        """Check friendly fire risk for a unit.

        Returns the probability of friendly fire (0 if no risk).
        """
        cfg = self._config
        for zone in self._barrages.values():
            if not zone.active or zone.side != unit_side:
                continue
            ce = zone.center_easting + zone.drift_easting_m
            cn = zone.center_northing + zone.drift_northing_m
            dist = math.sqrt((unit_easting - ce) ** 2 + (unit_northing - cn) ** 2)
            if dist <= cfg.friendly_fire_zone_m:
                return cfg.friendly_fire_probability
        return 0.0

    def is_safe_to_advance(
        self,
        easting: float,
        northing: float,
        barrage_id: str,
        safety_margin_m: float = 100.0,
    ) -> bool:
        """Check if it's safe for infantry to advance past a barrage.

        Returns True if the barrage center is at least *safety_margin_m*
        ahead of the given position.
        """
        zone = self._barrages.get(barrage_id)
        if zone is None or not zone.active:
            return True

        ce = zone.center_easting + zone.drift_easting_m
        cn = zone.center_northing + zone.drift_northing_m
        # Distance along heading direction
        rad = math.radians(zone.heading_deg)
        dx = ce - easting
        dy = cn - northing
        forward_dist = dx * math.sin(rad) + dy * math.cos(rad)
        return forward_dist >= safety_margin_m

    @property
    def active_barrages(self) -> list[BarrageZone]:
        """Return list of active barrages."""
        return [z for z in self._barrages.values() if z.active]

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "barrages": {
                bid: {
                    "barrage_id": z.barrage_id,
                    "barrage_type": int(z.barrage_type),
                    "side": z.side,
                    "center_easting": z.center_easting,
                    "center_northing": z.center_northing,
                    "width_m": z.width_m,
                    "depth_m": z.depth_m,
                    "heading_deg": z.heading_deg,
                    "advance_rate_mps": z.advance_rate_mps,
                    "fire_density_rounds_per_hectare": z.fire_density_rounds_per_hectare,
                    "elapsed_s": z.elapsed_s,
                    "duration_s": z.duration_s,
                    "drift_easting_m": z.drift_easting_m,
                    "drift_northing_m": z.drift_northing_m,
                    "active": z.active,
                }
                for bid, z in self._barrages.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._barrages.clear()
        for bid, zdata in state.get("barrages", {}).items():
            zdata["barrage_type"] = BarrageType(zdata["barrage_type"])
            self._barrages[bid] = BarrageZone(**zdata)

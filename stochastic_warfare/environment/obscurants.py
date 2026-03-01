"""Obscurants model: smoke, dust, and fog.

Each obscurant cloud is tracked as a centre + radius + density that drifts
with wind, expands over time, and decays exponentially.  Different obscurant
types block different spectral bands.
"""

from __future__ import annotations

import enum
import math
import uuid
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.types import Meters, Position
from stochastic_warfare.environment.weather import WeatherEngine
from stochastic_warfare.environment.time_of_day import TimeOfDayEngine


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ObscurantType(enum.IntEnum):
    """Obscurant categories."""

    SMOKE = 0
    SMOKE_MULTISPECTRAL = 1
    DUST = 2
    FOG_RADIATION = 3
    FOG_ADVECTION = 4
    FOG_SEA = 5


class SpectralBlocking(NamedTuple):
    """Opacity across spectral bands (0–1 each)."""

    visual: float
    thermal: float
    radar: float


# Spectral blocking by type at full density
_SPECTRAL_TABLE: dict[ObscurantType, SpectralBlocking] = {
    ObscurantType.SMOKE: SpectralBlocking(0.9, 0.1, 0.0),
    ObscurantType.SMOKE_MULTISPECTRAL: SpectralBlocking(0.9, 0.8, 0.3),
    ObscurantType.DUST: SpectralBlocking(0.7, 0.5, 0.3),
    ObscurantType.FOG_RADIATION: SpectralBlocking(0.9, 0.6, 0.0),
    ObscurantType.FOG_ADVECTION: SpectralBlocking(0.9, 0.6, 0.0),
    ObscurantType.FOG_SEA: SpectralBlocking(0.9, 0.6, 0.0),
}


# ---------------------------------------------------------------------------
# Internal cloud representation
# ---------------------------------------------------------------------------


class _Cloud:
    """Internal representation of a single obscurant cloud."""

    def __init__(
        self,
        cloud_id: str,
        cloud_type: ObscurantType,
        center_e: float,
        center_n: float,
        radius: float,
        density: float,
    ) -> None:
        self.cloud_id = cloud_id
        self.cloud_type = cloud_type
        self.center_e = center_e
        self.center_n = center_n
        self.radius = radius
        self.density = density
        self.age_seconds = 0.0


# ---------------------------------------------------------------------------
# ObscurantsEngine
# ---------------------------------------------------------------------------


class ObscurantsEngine:
    """Manages obscurant clouds with drift, dispersion, and dissipation.

    Parameters
    ----------
    weather:
        Weather engine (wind for drift, humidity for fog).
    time_of_day:
        Time-of-day engine (illumination for fog formation).
    clock:
        Simulation clock.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        weather: WeatherEngine,
        time_of_day: TimeOfDayEngine,
        clock: SimulationClock,
        rng: np.random.Generator,
    ) -> None:
        self._weather = weather
        self._time_of_day = time_of_day
        self._clock = clock
        self._rng = rng
        self._clouds: dict[str, _Cloud] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deploy_smoke(
        self, center: Position, radius: Meters, multispectral: bool = False
    ) -> str:
        """Deploy a smoke cloud.  Returns the cloud ID."""
        ctype = (
            ObscurantType.SMOKE_MULTISPECTRAL if multispectral
            else ObscurantType.SMOKE
        )
        cid = f"smoke_{uuid.uuid4().hex[:8]}"
        self._clouds[cid] = _Cloud(
            cid, ctype, center.easting, center.northing, radius, 1.0
        )
        return cid

    def add_dust(self, center: Position, radius: Meters) -> str:
        """Add a dust cloud.  Returns the cloud ID."""
        cid = f"dust_{uuid.uuid4().hex[:8]}"
        self._clouds[cid] = _Cloud(
            cid, ObscurantType.DUST, center.easting, center.northing, radius, 1.0
        )
        return cid

    def update(self, dt_seconds: float) -> None:
        """Advance all clouds: drift, expand, decay.  Handle fog."""
        wind = self._weather.current.wind
        wx = self._weather.current

        to_remove: list[str] = []
        for cid, cloud in self._clouds.items():
            cloud.age_seconds += dt_seconds

            # Drift with wind
            dt_hours = dt_seconds / 3600.0
            cloud.center_e += wind.speed * math.sin(wind.direction) * dt_seconds
            cloud.center_n += wind.speed * math.cos(wind.direction) * dt_seconds

            # Expand: r(t) = r0 + k * sqrt(t)
            k = 2.0  # dispersion coefficient
            cloud.radius += k * math.sqrt(dt_seconds) * 0.1

            # Decay density exponentially
            half_life = 1800.0  # 30 minutes for smoke/dust
            if cloud.cloud_type in (ObscurantType.FOG_RADIATION,
                                     ObscurantType.FOG_ADVECTION,
                                     ObscurantType.FOG_SEA):
                half_life = 7200.0  # fog persists longer

            decay = 0.5 ** (dt_seconds / half_life)
            cloud.density *= decay

            if cloud.density < 0.01:
                to_remove.append(cid)

        for cid in to_remove:
            del self._clouds[cid]

        # Natural fog formation
        if wx.state.name == "FOG" and not any(
            c.cloud_type in (ObscurantType.FOG_RADIATION,
                              ObscurantType.FOG_ADVECTION,
                              ObscurantType.FOG_SEA)
            for c in self._clouds.values()
        ):
            # Create a large fog patch
            cid = f"fog_{uuid.uuid4().hex[:8]}"
            self._clouds[cid] = _Cloud(
                cid, ObscurantType.FOG_RADIATION, 0.0, 0.0, 50000.0, 0.8
            )

    def opacity_at(self, pos: Position) -> SpectralBlocking:
        """Composite spectral opacity at *pos*."""
        visual = 0.0
        thermal = 0.0
        radar = 0.0

        for cloud in self._clouds.values():
            dist = math.sqrt(
                (pos.easting - cloud.center_e) ** 2
                + (pos.northing - cloud.center_n) ** 2
            )
            if dist > cloud.radius:
                continue

            # Linear falloff from center to edge
            fraction = max(0, 1.0 - dist / cloud.radius) if cloud.radius > 0 else 1.0
            effective_density = cloud.density * fraction

            spec = _SPECTRAL_TABLE[cloud.cloud_type]
            visual = min(1.0, visual + spec.visual * effective_density)
            thermal = min(1.0, thermal + spec.thermal * effective_density)
            radar = min(1.0, radar + spec.radar * effective_density)

        return SpectralBlocking(visual, thermal, radar)

    def visibility_at(self, pos: Position) -> Meters:
        """Effective visibility at *pos* (metres)."""
        base_vis = self._weather.current.visibility
        opacity = self.opacity_at(pos)
        if opacity.visual >= 1.0:
            return 10.0  # minimum
        return base_vis * (1.0 - opacity.visual)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "clouds": [
                {
                    "cloud_id": c.cloud_id,
                    "cloud_type": int(c.cloud_type),
                    "center_e": c.center_e,
                    "center_n": c.center_n,
                    "radius": c.radius,
                    "density": c.density,
                    "age_seconds": c.age_seconds,
                }
                for c in self._clouds.values()
            ]
        }

    def set_state(self, state: dict) -> None:
        self._clouds.clear()
        for cd in state["clouds"]:
            cloud = _Cloud(
                cd["cloud_id"],
                ObscurantType(cd["cloud_type"]),
                cd["center_e"],
                cd["center_n"],
                cd["radius"],
                cd["density"],
            )
            cloud.age_seconds = cd["age_seconds"]
            self._clouds[cloud.cloud_id] = cloud

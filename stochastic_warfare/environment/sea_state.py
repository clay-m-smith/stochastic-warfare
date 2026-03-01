"""Sea state model: waves, tides, SST, Beaufort scale.

Waves follow the Pierson-Moskowitz spectrum.  Tides are computed from
harmonic constituents (M2, S2, K1, O1) modulated by astronomical forcing.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.types import Meters
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.weather import WeatherEngine


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TidalConstituent(BaseModel):
    """A single tidal harmonic constituent."""

    name: str
    amplitude: float  # metres
    phase: float  # degrees
    speed: float  # degrees per hour


class SeaStateConfig(BaseModel):
    """Sea state engine parameters."""

    tidal_constituents: list[TidalConstituent] | None = None
    mean_sst: float = 15.0  # °C
    fetch_km: float = 100.0  # km


# Default M2, S2, K1, O1 constituents
_DEFAULT_CONSTITUENTS = [
    TidalConstituent(name="M2", amplitude=0.5, phase=0.0, speed=28.9841),
    TidalConstituent(name="S2", amplitude=0.2, phase=30.0, speed=30.0),
    TidalConstituent(name="K1", amplitude=0.15, phase=90.0, speed=15.0411),
    TidalConstituent(name="O1", amplitude=0.1, phase=270.0, speed=13.9430),
]

# Beaufort scale breakpoints (significant wave height in metres)
_BEAUFORT_BREAKS = [0.0, 0.1, 0.3, 0.6, 1.0, 2.0, 3.0, 4.0, 5.5, 7.0, 9.0, 11.5, 14.0]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class SeaConditions(NamedTuple):
    """Composite sea state snapshot."""

    significant_wave_height: Meters
    wave_period: float  # seconds
    tide_height: Meters
    tidal_current_speed: float  # m/s
    tidal_current_direction: float  # radians
    sst: float  # °C
    beaufort_scale: int


# ---------------------------------------------------------------------------
# SeaStateEngine
# ---------------------------------------------------------------------------


class SeaStateEngine:
    """Sea state simulation combining wind-waves and tidal harmonics.

    Parameters
    ----------
    config:
        Sea state parameters.
    clock:
        Simulation clock.
    astronomy:
        Astronomy engine (tidal forcing).
    weather:
        Weather engine (wind for waves).
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: SeaStateConfig,
        clock: SimulationClock,
        astronomy: AstronomyEngine,
        weather: WeatherEngine,
        rng: np.random.Generator,
    ) -> None:
        self._config = config
        self._clock = clock
        self._astronomy = astronomy
        self._weather = weather
        self._rng = rng

        self._constituents = (
            config.tidal_constituents
            if config.tidal_constituents
            else _DEFAULT_CONSTITUENTS
        )
        self._hours_elapsed = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current(self) -> SeaConditions:
        """Current sea state."""
        wind_speed = self._weather.current.wind.speed
        Hs = self._wave_height(wind_speed)
        Tp = self._wave_period(wind_speed)
        tide = self._tide_height()
        current_speed, current_dir = self._tidal_current()
        sst = self._sst()
        beaufort = self._beaufort(Hs)

        return SeaConditions(
            significant_wave_height=Hs,
            wave_period=Tp,
            tide_height=tide,
            tidal_current_speed=current_speed,
            tidal_current_direction=current_dir,
            sst=sst,
            beaufort_scale=beaufort,
        )

    def update(self, dt_seconds: float) -> None:
        """Advance time tracking."""
        self._hours_elapsed += dt_seconds / 3600.0

    def tide_at(self, hours_from_now: float = 0.0) -> float:
        """Tide height at a future time offset."""
        t = self._hours_elapsed + hours_from_now
        forcing = self._astronomy.tidal_forcing()
        return sum(
            c.amplitude * forcing * math.cos(
                math.radians(c.speed * t + c.phase)
            )
            for c in self._constituents
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {"hours_elapsed": self._hours_elapsed}

    def set_state(self, state: dict) -> None:
        self._hours_elapsed = state["hours_elapsed"]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _wave_height(self, wind_speed: float) -> Meters:
        """Pierson-Moskowitz significant wave height."""
        g = 9.81
        if wind_speed < 0.5:
            return 0.0
        return 0.22 * wind_speed ** 2 / g

    def _wave_period(self, wind_speed: float) -> float:
        """Peak wave period (seconds)."""
        g = 9.81
        if wind_speed < 0.5:
            return 0.0
        return 0.877 * 2 * math.pi * wind_speed / g

    def _tide_height(self) -> float:
        return self.tide_at(0.0)

    def _tidal_current(self) -> tuple[float, float]:
        """Tidal current proportional to dh/dt (strongest at mid-tide)."""
        h0 = self.tide_at(0.0)
        h1 = self.tide_at(0.1)
        dhdt = (h1 - h0) / 0.1  # metres/hour
        speed = abs(dhdt) * 0.5  # rough scaling
        direction = 0.0 if dhdt >= 0 else math.pi  # flood vs ebb
        return (speed, direction)

    def _sst(self) -> float:
        """Sea surface temperature with seasonal and diurnal variation."""
        month = self._clock.month
        # Seasonal sinusoidal variation (peak August, trough February)
        seasonal = self._config.mean_sst + 3.0 * math.sin(
            2 * math.pi * (month - 2) / 12.0
        )
        return seasonal

    def _beaufort(self, Hs: float) -> int:
        """Beaufort scale from significant wave height."""
        for i in range(len(_BEAUFORT_BREAKS) - 1, -1, -1):
            if Hs >= _BEAUFORT_BREAKS[i]:
                return i
        return 0

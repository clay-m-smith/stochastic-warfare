"""Seasonal ground-state accumulation model.

Tracks freezing/thawing degree-days, snow depth, vegetation density, and
ground trafficability as functions of accumulated weather.  Depends on
weather (temperature, precipitation) and astronomy (day length) but never
imports terrain modules — soil type is passed via config.
"""

from __future__ import annotations

import enum
import math
from typing import NamedTuple

from pydantic import BaseModel

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.environment.astronomy import AstronomyEngine
from stochastic_warfare.environment.weather import WeatherEngine, WeatherState


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class GroundState(enum.IntEnum):
    """Ground surface condition."""

    FROZEN = 0
    THAWING = 1
    DRY = 2
    WET = 3
    SATURATED = 4
    SNOW_COVERED = 5


class SeasonalConditions(NamedTuple):
    """Composite seasonal snapshot."""

    ground_state: GroundState
    snow_depth: float  # metres
    mud_depth: float  # metres
    vegetation_density: float  # 0–1
    vegetation_moisture: float  # 0–1
    sea_ice_thickness: float  # metres
    wildfire_risk: float  # 0–1
    ground_trafficability: float  # 0–1
    daylight_hours: float


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class SeasonsConfig(BaseModel):
    """Seasons engine parameters."""

    latitude: float
    soil_type_default: int = 2  # SoilType.LOAM


# Trafficability by ground state and general soil category
_TRAFFICABILITY: dict[GroundState, float] = {
    GroundState.FROZEN: 0.9,
    GroundState.THAWING: 0.3,
    GroundState.DRY: 1.0,
    GroundState.WET: 0.6,
    GroundState.SATURATED: 0.2,
    GroundState.SNOW_COVERED: 0.5,
}


# ---------------------------------------------------------------------------
# SeasonsEngine
# ---------------------------------------------------------------------------


class SeasonsEngine:
    """Accumulation-based seasonal model.

    Parameters
    ----------
    config:
        Latitude and soil parameters.
    clock:
        Simulation clock.
    weather:
        Weather engine (read current temperature, precipitation).
    astronomy:
        Astronomy engine (read day length).
    """

    def __init__(
        self,
        config: SeasonsConfig,
        clock: SimulationClock,
        weather: WeatherEngine,
        astronomy: AstronomyEngine,
    ) -> None:
        self._config = config
        self._clock = clock
        self._weather = weather
        self._astronomy = astronomy

        # Accumulators
        self._freezing_dd = 0.0  # freezing degree-days (< 0°C)
        self._thawing_dd = 0.0  # thawing degree-days (> 0°C)
        self._growing_dd = 0.0  # growing degree-days (base 5°C)
        self._snow_depth = 0.0  # metres
        self._mud_depth = 0.0
        self._sea_ice = 0.0
        self._ground_state = GroundState.DRY

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current(self) -> SeasonalConditions:
        """Current seasonal conditions."""
        wx = self._weather.current
        daylight = self._astronomy.day_length_hours(self._config.latitude, 0.0)
        veg = self._vegetation_density()
        veg_moist = self._vegetation_moisture(wx.humidity)
        wf_risk = self._wildfire_risk(wx.temperature, wx.humidity, wx.wind.speed, veg_moist)
        trafficability = _TRAFFICABILITY.get(self._ground_state, 0.5)

        return SeasonalConditions(
            ground_state=self._ground_state,
            snow_depth=self._snow_depth,
            mud_depth=self._mud_depth,
            vegetation_density=veg,
            vegetation_moisture=veg_moist,
            sea_ice_thickness=self._sea_ice,
            wildfire_risk=wf_risk,
            ground_trafficability=trafficability,
            daylight_hours=daylight,
        )

    def update(self, dt_seconds: float) -> None:
        """Advance seasonal accumulators by *dt_seconds*."""
        dt_hours = dt_seconds / 3600.0
        dt_days = dt_hours / 24.0
        temp = self._weather.current.temperature
        precip = self._weather.current.precipitation_rate  # mm/hr
        wx_state = self._weather.current.state

        # Degree-day accumulators
        if temp < 0:
            self._freezing_dd += abs(temp) * dt_days
            self._thawing_dd = max(0, self._thawing_dd - abs(temp) * dt_days)
        else:
            self._thawing_dd += temp * dt_days
            self._freezing_dd = max(0, self._freezing_dd - temp * dt_days)

        if temp > 5.0:
            self._growing_dd += (temp - 5.0) * dt_days

        # Snow accumulation / melt
        if wx_state == WeatherState.SNOW:
            # ~1mm rain ≈ 10mm snow, precip in mm/hr
            self._snow_depth += precip * 0.01 * dt_hours  # convert to metres
        if temp > 0 and self._snow_depth > 0:
            melt_rate = temp * 0.002 * dt_hours  # metres per degree-hour
            self._snow_depth = max(0, self._snow_depth - melt_rate)

        # Ground state transitions
        self._update_ground_state(temp)

        # Mud
        if self._ground_state in (GroundState.THAWING, GroundState.WET, GroundState.SATURATED):
            if precip > 0:
                self._mud_depth = min(0.5, self._mud_depth + precip * 0.0001 * dt_hours)
        if self._ground_state == GroundState.DRY:
            self._mud_depth = max(0, self._mud_depth - 0.01 * dt_days)

        # Sea ice (simplified)
        if abs(self._config.latitude) > 50:
            if temp < -5:
                self._sea_ice = min(3.0, self._sea_ice + 0.005 * dt_days)
            elif temp > 0:
                self._sea_ice = max(0, self._sea_ice - 0.01 * dt_days)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "freezing_dd": self._freezing_dd,
            "thawing_dd": self._thawing_dd,
            "growing_dd": self._growing_dd,
            "snow_depth": self._snow_depth,
            "mud_depth": self._mud_depth,
            "sea_ice": self._sea_ice,
            "ground_state": int(self._ground_state),
        }

    def set_state(self, state: dict) -> None:
        self._freezing_dd = state["freezing_dd"]
        self._thawing_dd = state["thawing_dd"]
        self._growing_dd = state["growing_dd"]
        self._snow_depth = state["snow_depth"]
        self._mud_depth = state["mud_depth"]
        self._sea_ice = state["sea_ice"]
        self._ground_state = GroundState(state["ground_state"])

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _update_ground_state(self, temp: float) -> None:
        if self._snow_depth > 0.02:
            self._ground_state = GroundState.SNOW_COVERED
        elif self._freezing_dd > 10 and temp < 0:
            self._ground_state = GroundState.FROZEN
        elif self._ground_state == GroundState.FROZEN and temp > 0:
            self._ground_state = GroundState.THAWING
        elif self._ground_state == GroundState.THAWING and self._thawing_dd > 5:
            self._ground_state = GroundState.WET
        elif self._ground_state == GroundState.WET and self._mud_depth < 0.01:
            self._ground_state = GroundState.DRY
        elif self._weather.current.precipitation_rate > 10:
            self._ground_state = GroundState.SATURATED
        elif self._weather.current.precipitation_rate > 2:
            if self._ground_state == GroundState.DRY:
                self._ground_state = GroundState.WET

    def _vegetation_density(self) -> float:
        """Sigmoid of growing degree-days.  Tropical = always high."""
        if abs(self._config.latitude) < 23.5:
            return 0.9  # tropical — always dense
        # Sigmoid: 0 in winter, 1 in summer
        return 1.0 / (1.0 + math.exp(-0.01 * (self._growing_dd - 200)))

    def _vegetation_moisture(self, humidity: float) -> float:
        """Vegetation moisture from humidity and recent precipitation."""
        return min(1.0, humidity * 0.8 + 0.2)

    def _wildfire_risk(
        self, temp: float, humidity: float, wind_speed: float, veg_moisture: float
    ) -> float:
        """Wildfire risk index (0–1)."""
        if temp < 10:
            return 0.0
        dryness = max(0, 1.0 - veg_moisture)
        heat = min(1.0, max(0, (temp - 20) / 30.0))
        wind_factor = min(1.0, wind_speed / 20.0)
        low_humidity = max(0, 1.0 - humidity)
        return min(1.0, dryness * heat * wind_factor * low_humidity)

"""Electromagnetic propagation model.

Models free-space path loss, atmospheric attenuation, radar horizon,
HF propagation quality (day/night), and GPS accuracy.
"""

from __future__ import annotations

import enum
import math
from typing import NamedTuple

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.types import Meters
from stochastic_warfare.environment.weather import WeatherEngine
from stochastic_warfare.environment.sea_state import SeaStateEngine


# ---------------------------------------------------------------------------
# Enums & types
# ---------------------------------------------------------------------------


class FrequencyBand(enum.IntEnum):
    """Radio frequency bands."""

    HF = 0  # 3–30 MHz
    VHF = 1  # 30–300 MHz
    UHF = 2  # 300–3000 MHz
    SHF = 3  # 3–30 GHz
    EHF = 4  # 30–300 GHz


class PropagationConditions(NamedTuple):
    """RF propagation snapshot for a band/range."""

    free_space_loss: float  # dB
    atmospheric_attenuation: float  # dB
    refraction_factor: float
    ducting_possible: bool
    duct_height: float | None  # metres


# ---------------------------------------------------------------------------
# EMEnvironment
# ---------------------------------------------------------------------------


class EMEnvironment:
    """Electromagnetic propagation model.

    Parameters
    ----------
    weather:
        Weather engine (humidity, temperature for ducting).
    sea_state:
        Sea state engine (optional — for evaporation duct).
    clock:
        Simulation clock.
    """

    def __init__(
        self,
        weather: WeatherEngine,
        sea_state: SeaStateEngine | None,
        clock: SimulationClock,
    ) -> None:
        self._weather = weather
        self._sea_state = sea_state
        self._clock = clock
        self._gps_jam_degradation_m: float = 0.0
        self._gps_spoof_offset: tuple[float, float] = (0.0, 0.0)
        self._constellation_accuracy_m: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def propagation(
        self, band: FrequencyBand, range_km: float
    ) -> PropagationConditions:
        """Propagation conditions for a frequency band and range."""
        # Representative frequencies by band (MHz)
        freq_mhz = {
            FrequencyBand.HF: 10.0,
            FrequencyBand.VHF: 150.0,
            FrequencyBand.UHF: 1000.0,
            FrequencyBand.SHF: 10000.0,
            FrequencyBand.EHF: 60000.0,
        }[band]

        fspl = self.free_space_path_loss(freq_mhz, range_km)
        attn = self.atmospheric_attenuation(freq_mhz) * range_km
        k = self.effective_earth_radius_factor()
        ducting, duct_h = self._check_ducting()

        return PropagationConditions(
            free_space_loss=fspl,
            atmospheric_attenuation=attn,
            refraction_factor=k,
            ducting_possible=ducting,
            duct_height=duct_h,
        )

    def free_space_path_loss(self, frequency_mhz: float, range_km: float) -> float:
        """Free-space path loss in dB."""
        if range_km <= 0 or frequency_mhz <= 0:
            return 0.0
        return 20 * math.log10(range_km) + 20 * math.log10(frequency_mhz) + 32.45

    def atmospheric_attenuation(self, frequency_mhz: float) -> float:
        """Atmospheric attenuation in dB/km (simplified).

        Significant only at SHF/EHF.  Water vapour absorption peaks at
        22 GHz and 60 GHz (O2).
        """
        if frequency_mhz < 1000:
            return 0.0
        humidity = self._weather.current.humidity
        freq_ghz = frequency_mhz / 1000.0

        # Simplified model
        if freq_ghz < 10:
            return 0.01 * humidity
        elif freq_ghz < 30:
            return 0.05 * humidity + 0.01 * (freq_ghz - 10)
        elif freq_ghz < 70:
            # O2 absorption peak near 60 GHz
            o2_peak = 15.0 * math.exp(-0.5 * ((freq_ghz - 60) / 5) ** 2)
            return 0.1 + o2_peak
        else:
            return 0.5

    def radar_horizon(self, antenna_height: Meters) -> Meters:
        """Radar horizon distance in metres."""
        k = self.effective_earth_radius_factor()
        R = 6_371_000.0  # earth radius
        return math.sqrt(2 * k * R * max(0, antenna_height))

    def effective_earth_radius_factor(self) -> float:
        """Effective earth radius factor (k).

        Standard atmosphere: k ≈ 4/3.  Varies with temperature gradient.
        """
        temp = self._weather.current.temperature
        humidity = self._weather.current.humidity
        # Slight variation with conditions
        k = 4.0 / 3.0
        # Super-refraction in warm humid conditions
        if temp > 30 and humidity > 0.8:
            k = 1.5
        return k

    def set_constellation_accuracy(self, accuracy_m: float) -> None:
        """Set GPS accuracy from space constellation (metres).

        When > 0, replaces the default 5.0m baseline in :meth:`gps_accuracy`.
        """
        self._constellation_accuracy_m = max(0.0, accuracy_m)

    def set_gps_jam_degradation(self, degradation_m: float) -> None:
        """Set GPS accuracy degradation from EW jamming (metres)."""
        self._gps_jam_degradation_m = max(0.0, degradation_m)

    def set_gps_spoof_offset(self, east_m: float, north_m: float) -> None:
        """Set GPS position offset from EW spoofing (metres)."""
        self._gps_spoof_offset = (east_m, north_m)

    @property
    def gps_spoof_offset(self) -> tuple[float, float]:
        """Current GPS spoofing offset (east_m, north_m)."""
        return self._gps_spoof_offset

    def gps_accuracy(self) -> Meters:
        """GPS position accuracy (metres)."""
        base = self._constellation_accuracy_m if self._constellation_accuracy_m > 0 else 5.0
        # Ionospheric delay worse at night (but dual-freq corrects)
        hour = self._clock.hour_utc
        # Storm interference
        if self._weather.current.state.name == "STORM":
            base += 3.0
        # EW jamming degradation
        base += self._gps_jam_degradation_m
        return base

    def hf_propagation_quality(self) -> float:
        """HF skywave propagation quality (0–1).

        HF bounces off the ionosphere.  D-layer absorption during daytime
        degrades HF; F-layer reflection at night improves it.
        """
        hour = self._clock.hour_utc
        # Simple day/night model
        if 6 <= hour <= 18:
            # Daytime: D-layer absorbs → poor HF
            quality = 0.3
        else:
            # Nighttime: F-layer reflects → good HF
            quality = 0.8

        # Storm degrades
        if self._weather.current.state.name == "STORM":
            quality *= 0.5

        return min(1.0, quality)

    def update(self, dt_seconds: float) -> None:
        """No internal state to advance."""
        pass

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "gps_jam_degradation_m": self._gps_jam_degradation_m,
            "gps_spoof_offset": list(self._gps_spoof_offset),
            "constellation_accuracy_m": self._constellation_accuracy_m,
        }

    def set_state(self, state: dict) -> None:
        self._gps_jam_degradation_m = state.get("gps_jam_degradation_m", 0.0)
        offset = state.get("gps_spoof_offset", [0.0, 0.0])
        self._gps_spoof_offset = (offset[0], offset[1])
        self._constellation_accuracy_m = state.get("constellation_accuracy_m", 0.0)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_ducting(self) -> tuple[bool, float | None]:
        """Check if atmospheric ducting conditions exist."""
        temp = self._weather.current.temperature
        humidity = self._weather.current.humidity

        # Evaporation duct over warm water
        if self._sea_state is not None:
            sst = self._sea_state.current.sst
            if sst > temp + 2 and humidity > 0.7:
                duct_height = 10.0 + 20.0 * (sst - temp) / 10.0
                return (True, duct_height)

        # Temperature inversion ducting
        # (simplified — would need vertical temp profile in reality)
        if humidity > 0.9 and temp > 20:
            return (True, 200.0)

        return (False, None)

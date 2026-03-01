"""Underwater acoustics: sound velocity profile, transmission loss, ambient noise.

Sound velocity uses the Mackenzie equation.  SVP structure models a mixed
layer, thermocline, and deep isothermal layer.  Transmission loss uses a
simple spreading + absorption model.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np

from stochastic_warfare.core.clock import SimulationClock
from stochastic_warfare.core.types import Meters
from stochastic_warfare.environment.sea_state import SeaStateEngine


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class SoundVelocityProfile(NamedTuple):
    """Depth vs sound velocity."""

    depths: np.ndarray  # metres
    velocities: np.ndarray  # m/s


class AcousticConditions(NamedTuple):
    """Composite underwater acoustic snapshot."""

    svp: SoundVelocityProfile
    surface_duct_depth: float | None
    thermocline_depth: float | None
    deep_channel_depth: float
    ambient_noise_level: float  # dB re 1 μPa


# ---------------------------------------------------------------------------
# UnderwaterAcousticsEngine
# ---------------------------------------------------------------------------


class UnderwaterAcousticsEngine:
    """Underwater acoustic propagation model.

    Parameters
    ----------
    sea_state:
        Sea state engine (SST, Beaufort for ambient noise).
    clock:
        Simulation clock.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        sea_state: SeaStateEngine,
        clock: SimulationClock,
        rng: np.random.Generator,
    ) -> None:
        self._sea_state = sea_state
        self._clock = clock
        self._rng = rng
        self._salinity = 35.0  # PSU, default ocean

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def svp_at(
        self, depth_max: Meters, sst: float | None = None
    ) -> SoundVelocityProfile:
        """Sound velocity profile from surface to *depth_max*."""
        if sst is None:
            sst = self._sea_state.current.sst

        depths = np.linspace(0, depth_max, num=max(10, int(depth_max / 10)))
        velocities = np.array([
            self.sound_velocity(
                self._temperature_at_depth(d, sst),
                self._salinity,
                d,
            )
            for d in depths
        ])
        return SoundVelocityProfile(depths, velocities)

    def sound_velocity(
        self, temperature: float, salinity: float, depth: float
    ) -> float:
        """Mackenzie equation for sound velocity (m/s).

        Valid for T: 2–30°C, S: 25–40 PSU, D: 0–8000m.
        """
        T = temperature
        S = salinity
        D = depth
        c = (
            1448.96
            + 4.591 * T
            - 0.05304 * T**2
            + 2.374e-4 * T**3
            + 1.340 * (S - 35)
            + 1.630e-2 * D
            + 1.675e-7 * D**2
            - 1.025e-2 * T * (S - 35)
            - 7.139e-13 * T * D**3
        )
        return c

    def transmission_loss(
        self, range_m: Meters, source_depth: Meters, receiver_depth: Meters
    ) -> float:
        """Transmission loss in dB.

        Uses cylindrical + spherical spreading with frequency-dependent
        absorption.
        """
        if range_m <= 0:
            return 0.0

        # Transition range from spherical to cylindrical spreading
        transition_range = 1000.0  # metres
        alpha = 0.001  # dB/m absorption at ~1kHz

        if range_m <= transition_range:
            # Spherical spreading
            tl = 20.0 * math.log10(max(1.0, range_m))
        else:
            # Cylindrical beyond transition
            tl = (
                20.0 * math.log10(transition_range)
                + 10.0 * math.log10(range_m / transition_range)
            )

        tl += alpha * range_m
        return tl

    def convergence_zone_ranges(self, source_depth: Meters) -> list[Meters]:
        """Approximate convergence zone ranges (deep water)."""
        # CZ at ~55km intervals (simplified)
        cz_interval = 55_000.0  # metres
        # Up to 5 CZs
        return [cz_interval * (i + 1) for i in range(5)]

    def ambient_noise(self, sea_state_beaufort: int) -> float:
        """Ambient noise level in dB re 1 μPa from sea state.

        Based on Wenz curves (simplified).
        """
        # Rough linear model: 40 dB at Beaufort 0, +6 dB per Beaufort number
        return 40.0 + 6.0 * sea_state_beaufort

    @property
    def conditions(self) -> AcousticConditions:
        """Current acoustic conditions."""
        sst = self._sea_state.current.sst
        svp = self.svp_at(1000.0, sst)

        # Find thermocline (where velocity starts decreasing)
        thermocline = self._find_thermocline(svp)

        # Surface duct: layer above thermocline where sound is trapped
        surface_duct = thermocline if thermocline and thermocline < 200 else None

        beaufort = self._sea_state.current.beaufort_scale
        noise = self.ambient_noise(beaufort)

        return AcousticConditions(
            svp=svp,
            surface_duct_depth=surface_duct,
            thermocline_depth=thermocline,
            deep_channel_depth=800.0,  # SOFAR channel ~800m
            ambient_noise_level=noise,
        )

    def update(self, dt_seconds: float) -> None:
        """Update (currently no internal state to advance)."""
        pass

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {"salinity": self._salinity}

    def set_state(self, state: dict) -> None:
        self._salinity = state["salinity"]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _temperature_at_depth(self, depth: float, sst: float) -> float:
        """Temperature profile: mixed layer → thermocline → deep isothermal."""
        month = self._clock.month
        # Thermocline depth: shallower in summer, deeper in winter
        thermo_depth = 50.0 + 100.0 * abs(math.sin(math.pi * (month - 3) / 6.0))
        deep_temp = 4.0  # deep ocean ~4°C

        if depth <= thermo_depth:
            return sst  # mixed layer
        elif depth <= thermo_depth + 500:
            # Linear decrease through thermocline
            frac = (depth - thermo_depth) / 500.0
            return sst + (deep_temp - sst) * frac
        else:
            return deep_temp

    def _find_thermocline(self, svp: SoundVelocityProfile) -> float | None:
        """Find depth where sound velocity starts decreasing."""
        for i in range(1, len(svp.velocities)):
            if svp.velocities[i] < svp.velocities[i - 1]:
                return float(svp.depths[i])
        return None

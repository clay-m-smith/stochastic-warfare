"""Pasquill-Gifford atmospheric dispersal model.

Models Gaussian puff dispersion with wind advection, stability-class-dependent
dispersion coefficients (Turner 1970), ground reflection, and optional terrain
channeling (valley concentration / ridge deflection).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stability classification
# ---------------------------------------------------------------------------


class StabilityClass(enum.IntEnum):
    """Pasquill-Gifford atmospheric stability classes."""

    A = 0  # Very unstable
    B = 1  # Moderately unstable
    C = 2  # Slightly unstable
    D = 3  # Neutral
    E = 4  # Slightly stable
    F = 5  # Stable


# Turner 1970 workbook coefficients for sigma_y = a * x^b
# and sigma_z = c * x^d (x in meters)
_SIGMA_Y_COEFFS: dict[StabilityClass, tuple[float, float]] = {
    StabilityClass.A: (0.22, 0.894),
    StabilityClass.B: (0.16, 0.894),
    StabilityClass.C: (0.11, 0.894),
    StabilityClass.D: (0.08, 0.894),
    StabilityClass.E: (0.06, 0.894),
    StabilityClass.F: (0.04, 0.894),
}

_SIGMA_Z_COEFFS: dict[StabilityClass, tuple[float, float]] = {
    StabilityClass.A: (0.20, 0.894),
    StabilityClass.B: (0.12, 0.894),
    StabilityClass.C: (0.08, 0.894),
    StabilityClass.D: (0.06, 0.894),
    StabilityClass.E: (0.03, 0.894),
    StabilityClass.F: (0.016, 0.894),
}


# ---------------------------------------------------------------------------
# Config & puff state
# ---------------------------------------------------------------------------


class DispersalConfig(BaseModel):
    """Configuration for the dispersal engine."""

    enable_terrain_channeling: bool = True
    valley_concentration_factor: float = 1.5
    ridge_deflection_factor: float = 0.5
    min_wind_speed_m_s: float = 0.5
    height_release_m: float = 2.0
    terrain_channel_offset_m: float = 50.0
    terrain_channel_height_m: float = 5.0
    max_puff_age_s: float = 3600.0


@dataclass
class PuffState:
    """Mutable runtime state of a dispersing chemical/biological puff."""

    puff_id: str
    agent_id: str
    center_e: float
    center_n: float
    mass_kg: float
    release_time_s: float
    age_s: float = 0.0


# ---------------------------------------------------------------------------
# Dispersal engine
# ---------------------------------------------------------------------------


class DispersalEngine:
    """Gaussian puff atmospheric dispersal with Pasquill-Gifford coefficients."""

    def __init__(self, config: DispersalConfig | None = None) -> None:
        self._config = config or DispersalConfig()
        self._puffs: list[PuffState] = []
        self._next_puff_id: int = 0

    @staticmethod
    def classify_stability(
        wind_speed_m_s: float,
        cloud_cover: float,
        is_daytime: bool,
    ) -> StabilityClass:
        """Classify Pasquill-Gifford stability from meteorological conditions.

        Parameters
        ----------
        wind_speed_m_s:
            Surface wind speed.
        cloud_cover:
            Fraction 0-1 (0=clear, 1=overcast).
        is_daytime:
            True during daytime, False at night.
        """
        if is_daytime:
            if wind_speed_m_s < 2.0:
                return StabilityClass.A if cloud_cover < 0.5 else StabilityClass.B
            elif wind_speed_m_s < 3.0:
                return StabilityClass.B if cloud_cover < 0.5 else StabilityClass.C
            elif wind_speed_m_s < 5.0:
                return StabilityClass.C if cloud_cover < 0.5 else StabilityClass.D
            else:
                return StabilityClass.D
        else:
            if wind_speed_m_s < 2.0:
                return StabilityClass.F if cloud_cover < 0.5 else StabilityClass.E
            elif wind_speed_m_s < 3.0:
                return StabilityClass.E if cloud_cover < 0.5 else StabilityClass.D
            else:
                return StabilityClass.D

    @staticmethod
    def sigma_y(x_m: float, stability: StabilityClass) -> float:
        """Lateral dispersion coefficient (meters) at downwind distance *x_m*."""
        a, b = _SIGMA_Y_COEFFS[stability]
        return a * max(x_m, 0.1) ** b

    @staticmethod
    def sigma_z(x_m: float, stability: StabilityClass) -> float:
        """Vertical dispersion coefficient (meters) at downwind distance *x_m*."""
        c, d = _SIGMA_Z_COEFFS[stability]
        return c * max(x_m, 0.1) ** d

    def create_puff(
        self,
        agent_id: str,
        position_e: float,
        position_n: float,
        mass_kg: float,
        sim_time_s: float,
    ) -> PuffState:
        """Create a new dispersing puff."""
        puff = PuffState(
            puff_id=f"puff_{self._next_puff_id}",
            agent_id=agent_id,
            center_e=position_e,
            center_n=position_n,
            mass_kg=mass_kg,
            release_time_s=sim_time_s,
            age_s=0.0,
        )
        self._next_puff_id += 1
        self._puffs.append(puff)
        return puff

    def compute_concentration(
        self,
        puff: PuffState,
        query_e: float,
        query_n: float,
        wind_speed_m_s: float,
        wind_direction_rad: float,
        stability: StabilityClass,
    ) -> float:
        """Compute ground-level concentration (mg/m³) at a query point.

        Uses the Gaussian puff model with ground reflection:
        ``C = Q/(π·σy·σz·u) · exp(-y²/2σy²) · [exp(-H²/2σz²) + exp(-H²/2σz²)]``

        Wind direction is the direction the wind blows TO (radians from north CW).
        """
        u = max(wind_speed_m_s, self._config.min_wind_speed_m_s)
        H = self._config.height_release_m

        # Compute distance along/across wind axis
        de = query_e - puff.center_e
        dn = query_n - puff.center_n

        # Wind direction: direction wind blows TO
        # Downwind axis (x) is along wind direction, crosswind (y) perpendicular
        sin_w = math.sin(wind_direction_rad)
        cos_w = math.cos(wind_direction_rad)
        x = de * sin_w + dn * cos_w  # downwind distance
        y = de * cos_w - dn * sin_w  # crosswind distance

        if x <= 0:
            return 0.0  # Upwind of source

        sy = self.sigma_y(x, stability)
        sz = self.sigma_z(x, stability)

        if sy < 1e-10 or sz < 1e-10:
            return 0.0

        # Q in mg (mass_kg * 1e6 to mg)
        Q = puff.mass_kg * 1e6

        # Gaussian plume with ground reflection (z=0 evaluation)
        exp_y = math.exp(-0.5 * (y / sy) ** 2)
        exp_z = math.exp(-0.5 * (H / sz) ** 2)

        conc = (Q / (math.pi * sy * sz * u)) * exp_y * 2.0 * exp_z
        return max(conc, 0.0)

    def advect_puff(
        self,
        puff: PuffState,
        dt_s: float,
        wind_speed_m_s: float,
        wind_direction_rad: float,
    ) -> None:
        """Move puff center with the wind for *dt_s* seconds."""
        u = max(wind_speed_m_s, self._config.min_wind_speed_m_s)
        drift = u * dt_s
        puff.center_e += drift * math.sin(wind_direction_rad)
        puff.center_n += drift * math.cos(wind_direction_rad)
        puff.age_s += dt_s

    def apply_terrain_channeling(
        self,
        concentration: float,
        position_e: float,
        position_n: float,
        heightmap: Any,
    ) -> float:
        """Modify concentration based on local terrain features.

        Valleys (local minima) concentrate agents; ridges (local maxima) deflect.
        """
        if not self._config.enable_terrain_channeling or heightmap is None:
            return concentration

        try:
            elev = heightmap.elevation_at(position_e, position_n)
        except (AttributeError, IndexError):
            return concentration

        # Sample cardinal neighbors
        offset = self._config.terrain_channel_offset_m
        neighbors = []
        for de, dn in [(offset, 0), (-offset, 0), (0, offset), (0, -offset)]:
            try:
                neighbors.append(
                    heightmap.elevation_at(position_e + de, position_n + dn)
                )
            except (AttributeError, IndexError):
                neighbors.append(elev)

        avg_neighbor = sum(neighbors) / len(neighbors) if neighbors else elev

        threshold = self._config.terrain_channel_height_m
        if elev < avg_neighbor - threshold:
            # Valley — concentrate
            return concentration * self._config.valley_concentration_factor
        elif elev > avg_neighbor + threshold:
            # Ridge — deflect
            return concentration * self._config.ridge_deflection_factor
        return concentration

    @property
    def puffs(self) -> list[PuffState]:
        """Active puffs."""
        return list(self._puffs)

    def remove_puff(self, puff_id: str) -> None:
        """Remove a puff by ID."""
        self._puffs = [p for p in self._puffs if p.puff_id != puff_id]

    def cleanup_aged_puffs(self) -> int:
        """Remove puffs older than ``max_puff_age_s``. Returns count removed."""
        max_age = self._config.max_puff_age_s
        before = len(self._puffs)
        self._puffs = [p for p in self._puffs if p.age_s < max_age]
        return before - len(self._puffs)

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        return {
            "next_puff_id": self._next_puff_id,
            "puffs": [
                {
                    "puff_id": p.puff_id,
                    "agent_id": p.agent_id,
                    "center_e": p.center_e,
                    "center_n": p.center_n,
                    "mass_kg": p.mass_kg,
                    "release_time_s": p.release_time_s,
                    "age_s": p.age_s,
                }
                for p in self._puffs
            ],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._next_puff_id = state.get("next_puff_id", 0)
        self._puffs = [
            PuffState(**data) for data in state.get("puffs", [])
        ]

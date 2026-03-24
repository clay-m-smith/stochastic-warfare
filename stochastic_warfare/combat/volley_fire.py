"""Napoleonic massed musket volley fire — aggregate fire model.

Models battalion-scale volley fire as an aggregate probability model
rather than individual engagements.  A battalion of 500 muskets at 100 m
expects ~25 hits.  Fire density × range modifier × smoke modifier ×
formation modifier → Binomial casualties.

Physics
-------
* Phit interpolated from smoothbore range table (50–200 m).
* Rifle accuracy multiplier for Baker rifle etc.
* Smoke accumulates per volley, decays with wind.
* Canister: short-range anti-personnel from artillery.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VolleyType(enum.IntEnum):
    """Type of volley fire."""

    VOLLEY_BY_RANK = 0
    ROLLING_FIRE = 1
    INDEPENDENT_FIRE = 2
    CANISTER = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Smoothbore hit probability by range (metres → probability per musket)
_DEFAULT_PHIT_TABLE: dict[int, float] = {
    50: 0.15,
    100: 0.05,
    150: 0.02,
    200: 0.01,
}


class VolleyFireConfig(BaseModel):
    """Configuration for Napoleonic volley fire model."""

    smoothbore_phit_by_range: dict[int, float] = _DEFAULT_PHIT_TABLE
    rifle_accuracy_multiplier: float = 3.0
    smoke_per_volley: float = 0.1
    smoke_decay_rate: float = 0.02
    smoke_accuracy_penalty: float = 0.5
    canister_range_m: float = 400.0
    canister_base_casualties: float = 0.10
    independent_fire_accuracy_modifier: float = 0.7
    rolling_fire_accuracy_modifier: float = 0.9


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class VolleyResult:
    """Result of a volley fire computation."""

    casualties: int
    suppression_value: float
    smoke_generated: float
    ammo_consumed: int


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class VolleyFireEngine:
    """Napoleonic massed musket fire aggregate model.

    Parameters
    ----------
    config:
        Volley fire configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: VolleyFireConfig | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._config = config or VolleyFireConfig()
        self._rng = rng
        self._current_smoke: float = 0.0

    def _interpolate_phit(self, range_m: float) -> float:
        """Interpolate hit probability from the smoothbore range table."""
        table = self._config.smoothbore_phit_by_range
        ranges = sorted(table.keys())
        if range_m <= ranges[0]:
            return table[ranges[0]]
        if range_m >= ranges[-1]:
            return table[ranges[-1]]

        for i in range(len(ranges) - 1):
            r0, r1 = ranges[i], ranges[i + 1]
            if r0 <= range_m <= r1:
                t = (range_m - r0) / (r1 - r0)
                return table[r0] * (1.0 - t) + table[r1] * t
        return table[ranges[-1]]  # pragma: no cover

    def fire_volley(
        self,
        n_muskets: int,
        range_m: float,
        is_rifle: bool = False,
        formation_firepower_fraction: float = 1.0,
        current_smoke: float | None = None,
        volley_type: VolleyType = VolleyType.VOLLEY_BY_RANK,
    ) -> VolleyResult:
        """Compute aggregate casualties from a massed volley.

        Parameters
        ----------
        n_muskets:
            Number of muskets firing.
        range_m:
            Range to target in metres.
        is_rifle:
            True for rifled weapons (Baker rifle).
        formation_firepower_fraction:
            Fraction of muskets that can fire (LINE=1.0, COLUMN=0.3 etc).
        current_smoke:
            Override battlefield smoke level (0–1). If None, uses engine
            internal tracking.
        volley_type:
            Type of volley.
        """
        cfg = self._config
        smoke = current_smoke if current_smoke is not None else self._current_smoke

        # Base Phit from range table
        phit = self._interpolate_phit(range_m)

        # Rifle accuracy bonus
        if is_rifle:
            phit *= cfg.rifle_accuracy_multiplier

        # Smoke penalty
        if smoke > 0:
            phit *= max(0.0, 1.0 - smoke * cfg.smoke_accuracy_penalty)

        # Volley type modifier
        if volley_type == VolleyType.INDEPENDENT_FIRE:
            phit *= cfg.independent_fire_accuracy_modifier
        elif volley_type == VolleyType.ROLLING_FIRE:
            phit *= cfg.rolling_fire_accuracy_modifier

        # Clamp
        phit = max(0.0, min(1.0, phit))

        # Effective muskets
        n_effective = int(n_muskets * formation_firepower_fraction)
        if n_effective <= 0:
            return VolleyResult(
                casualties=0,
                suppression_value=0.0,
                smoke_generated=0.0,
                ammo_consumed=0,
            )

        # Binomial casualties
        casualties = int(self._rng.binomial(n_effective, phit))

        # Suppression proportional to fire volume
        suppression = min(1.0, n_effective * phit * 2.0)

        # Smoke generation
        smoke_gen = cfg.smoke_per_volley
        self._current_smoke = min(1.0, self._current_smoke + smoke_gen)

        return VolleyResult(
            casualties=casualties,
            suppression_value=suppression,
            smoke_generated=smoke_gen,
            ammo_consumed=n_effective,
        )

    def fire_canister(
        self,
        range_m: float,
        n_guns: int,
        target_formation_artillery_vuln: float = 1.0,
    ) -> VolleyResult:
        """Fire canister shot (short-range anti-personnel).

        Parameters
        ----------
        range_m:
            Range to target.
        n_guns:
            Number of cannon firing canister.
        target_formation_artillery_vuln:
            Target formation artillery vulnerability modifier.
        """
        cfg = self._config
        if range_m > cfg.canister_range_m:
            return VolleyResult(
                casualties=0,
                suppression_value=0.0,
                smoke_generated=0.0,
                ammo_consumed=n_guns,
            )

        # Range effectiveness: linear falloff from canister_range
        range_eff = max(0.0, 1.0 - range_m / cfg.canister_range_m)
        base_cas = cfg.canister_base_casualties * range_eff * target_formation_artillery_vuln
        casualties = int(self._rng.binomial(n_guns * 50, min(1.0, base_cas)))
        suppression = min(1.0, base_cas * n_guns * 2.0)

        smoke_gen = cfg.smoke_per_volley * n_guns
        self._current_smoke = min(1.0, self._current_smoke + smoke_gen)

        return VolleyResult(
            casualties=casualties,
            suppression_value=suppression,
            smoke_generated=smoke_gen,
            ammo_consumed=n_guns,
        )

    def update_smoke(
        self,
        dt_s: float,
        wind_speed_mps: float = 0.0,
    ) -> float:
        """Dissipate battlefield smoke.

        Returns the new smoke level.
        """
        decay = self._config.smoke_decay_rate * dt_s
        # Wind accelerates dissipation
        if wind_speed_mps > 0:
            decay *= 1.0 + wind_speed_mps * 0.2
        self._current_smoke = max(0.0, self._current_smoke - decay)
        return self._current_smoke

    @property
    def current_smoke(self) -> float:
        """Current battlefield smoke level (0–1)."""
        return self._current_smoke

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {"current_smoke": self._current_smoke}

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._current_smoke = state.get("current_smoke", 0.0)

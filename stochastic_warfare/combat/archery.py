"""Massed archery and thrown weapon aggregate fire model.

Primary ranged combat for the Ancient/Medieval era.  Models massed
volleys (longbow, crossbow, composite bow) as aggregate Binomial
casualties — same pattern as :mod:`combat.volley_fire` but without
smoke mechanics.

Physics
-------
* Phit interpolated from per-missile-type range tables.
* Modified by armor reduction and formation vulnerability.
* Casualties = Binomial(n_archers, Phit × armor_mod × formation_mod).
* Ammo tracked per unit — when arrows run out, archers must switch to melee.
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


class MissileType(enum.IntEnum):
    """Type of ranged missile weapon."""

    LONGBOW = 0
    CROSSBOW = 1
    COMPOSITE_BOW = 2
    JAVELIN = 3
    SLING = 4


class ArmorType(enum.IntEnum):
    """Target armor classification."""

    NONE = 0
    LIGHT = 1
    MAIL = 2
    PLATE = 3


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_PHIT_LONGBOW: dict[int, float] = {
    50: 0.20,
    100: 0.12,
    150: 0.06,
    200: 0.03,
    250: 0.01,
}

_PHIT_CROSSBOW: dict[int, float] = {
    50: 0.30,
    100: 0.18,
    150: 0.10,
    200: 0.05,
    300: 0.02,
}

_PHIT_COMPOSITE: dict[int, float] = {
    50: 0.15,
    100: 0.08,
    150: 0.04,
    200: 0.02,
}

_PHIT_JAVELIN: dict[int, float] = {
    5: 0.40,
    15: 0.25,
    30: 0.10,
}

_PHIT_SLING: dict[int, float] = {
    30: 0.10,
    60: 0.05,
    100: 0.02,
}

_ARMOR_REDUCTION: dict[int, float] = {
    ArmorType.NONE: 1.0,
    ArmorType.LIGHT: 0.7,
    ArmorType.MAIL: 0.4,
    ArmorType.PLATE: 0.15,
}


class ArcheryConfig(BaseModel):
    """Configuration for massed archery fire model."""

    phit_by_range_longbow: dict[int, float] = _PHIT_LONGBOW
    phit_by_range_crossbow: dict[int, float] = _PHIT_CROSSBOW
    phit_by_range_composite: dict[int, float] = _PHIT_COMPOSITE
    phit_by_range_javelin: dict[int, float] = _PHIT_JAVELIN
    phit_by_range_sling: dict[int, float] = _PHIT_SLING
    armor_reduction: dict[int, float] = _ARMOR_REDUCTION
    arrows_per_archer: int = 24
    volley_ammo_cost: int = 1


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ArcheryResult:
    """Result of a massed archery volley."""

    casualties: int
    arrows_expended: int
    suppression_value: float
    armor_type_hit: ArmorType


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ArcheryEngine:
    """Massed archery aggregate fire model.

    Parameters
    ----------
    config:
        Archery configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: ArcheryConfig | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._config = config or ArcheryConfig()
        self._rng = rng or np.random.default_rng(42)
        self._ammo: dict[str, int] = {}

    def _get_phit_table(self, missile_type: MissileType) -> dict[int, float]:
        """Return the Phit range table for a missile type."""
        cfg = self._config
        if missile_type == MissileType.LONGBOW:
            return cfg.phit_by_range_longbow
        elif missile_type == MissileType.CROSSBOW:
            return cfg.phit_by_range_crossbow
        elif missile_type == MissileType.COMPOSITE_BOW:
            return cfg.phit_by_range_composite
        elif missile_type == MissileType.JAVELIN:
            return cfg.phit_by_range_javelin
        elif missile_type == MissileType.SLING:
            return cfg.phit_by_range_sling
        return cfg.phit_by_range_longbow  # pragma: no cover

    def _interpolate_phit(
        self, range_m: float, table: dict[int, float],
    ) -> float:
        """Interpolate hit probability from a range table."""
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

    def _init_ammo(self, unit_id: str) -> None:
        """Initialize ammo for a unit if not already tracked."""
        if unit_id not in self._ammo:
            self._ammo[unit_id] = self._config.arrows_per_archer

    def remaining_ammo(self, unit_id: str) -> int:
        """Return remaining arrows/bolts for a unit."""
        return self._ammo.get(unit_id, self._config.arrows_per_archer)

    def fire_volley(
        self,
        unit_id: str,
        n_archers: int,
        range_m: float,
        missile_type: MissileType,
        target_armor: ArmorType = ArmorType.NONE,
        target_formation_archery_vuln: float = 1.0,
    ) -> ArcheryResult:
        """Compute aggregate casualties from a massed volley.

        Parameters
        ----------
        unit_id:
            Firing unit identifier (for ammo tracking).
        n_archers:
            Number of archers/shooters firing.
        range_m:
            Range to target in metres.
        missile_type:
            Type of missile weapon.
        target_armor:
            Target armor classification.
        target_formation_archery_vuln:
            Target formation's archery vulnerability modifier.
        """
        self._init_ammo(unit_id)
        cfg = self._config

        # Check ammo — tracks arrows remaining per archer
        arrows_remaining = self._ammo[unit_id]
        if arrows_remaining < cfg.volley_ammo_cost:
            return ArcheryResult(
                casualties=0,
                arrows_expended=0,
                suppression_value=0.0,
                armor_type_hit=target_armor,
            )

        # All archers fire if ammo available
        n_effective = n_archers
        if n_effective <= 0:
            return ArcheryResult(
                casualties=0,
                arrows_expended=0,
                suppression_value=0.0,
                armor_type_hit=target_armor,
            )

        # Base Phit from range table
        table = self._get_phit_table(missile_type)
        phit = self._interpolate_phit(range_m, table)

        # Armor reduction
        armor_mod = cfg.armor_reduction.get(int(target_armor), 1.0)

        # Formation vulnerability modifier
        phit_final = max(0.0, min(1.0, phit * armor_mod * target_formation_archery_vuln))

        # Binomial casualties
        casualties = int(self._rng.binomial(n_effective, phit_final))

        # Consume ammo — one arrow per archer per volley
        ammo_used = n_effective * cfg.volley_ammo_cost
        self._ammo[unit_id] = max(0, arrows_remaining - cfg.volley_ammo_cost)

        # Suppression proportional to fire volume
        suppression = min(1.0, n_effective * phit_final * 2.0)

        logger.debug(
            "Archery volley: %d %s at %.0fm → %d casualties (Phit=%.4f, ammo_left=%d)",
            n_effective, MissileType(missile_type).name, range_m,
            casualties, phit_final, self._ammo[unit_id],
        )

        return ArcheryResult(
            casualties=casualties,
            arrows_expended=ammo_used,
            suppression_value=suppression,
            armor_type_hit=target_armor,
        )

    def fire_aimed(
        self,
        unit_id: str,
        n_shooters: int,
        range_m: float,
        missile_type: MissileType,
        target_armor: ArmorType = ArmorType.NONE,
    ) -> ArcheryResult:
        """Fire aimed shots (skirmisher/sniper mode, no formation modifier)."""
        return self.fire_volley(
            unit_id=unit_id,
            n_archers=n_shooters,
            range_m=range_m,
            missile_type=missile_type,
            target_armor=target_armor,
            target_formation_archery_vuln=1.0,
        )

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {"ammo": dict(self._ammo)}

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._ammo = dict(state.get("ammo", {}))

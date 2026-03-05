"""Convoy formation and escort mechanics for WW2-era naval operations.

Models convoy groupings, speed limitations, straggler mechanics,
wolf pack attacks, and depth charge counterattacks.  Designed for
Battle of the Atlantic-style scenarios.

Physics
-------
* Convoy speed = slowest ship.
* Straggler probability per tick based on speed differential.
* Wolf pack: submerged approach → surface/submerged attack → depth charge.
* Depth charge: diamond/cross pattern, lethal radius ~10 m, probability
  from range estimation error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ConvoyConfig(BaseModel):
    """Configuration for convoy operations."""

    max_convoy_speed_kts: float = 10.0
    """Maximum convoy speed in knots (limited by slowest ship)."""

    straggler_probability_per_hour: float = 0.02
    """Probability per hour that a merchant falls behind."""

    escort_detection_range_m: float = 3000.0
    """Range at which escorts can detect a submarine."""

    depth_charge_lethal_radius_m: float = 10.0
    """Lethal radius of a depth charge."""

    depth_charge_pattern_spread_m: float = 50.0
    """Spread of a depth charge pattern (diamond/cross)."""

    depth_charge_charges_per_pattern: int = 10
    """Number of depth charges in one attack pattern."""

    torpedo_hit_probability_base: float = 0.3
    """Base probability a torpedo hits a convoy ship."""

    wolf_pack_coordination_bonus: float = 0.15
    """Hit probability bonus when multiple subs attack."""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class ConvoyState:
    """Tracks the state of a single convoy."""

    convoy_id: str
    ship_ids: list[str] = field(default_factory=list)
    escort_ids: list[str] = field(default_factory=list)
    speed_kts: float = 8.0
    heading_deg: float = 0.0
    straggler_ids: list[str] = field(default_factory=list)
    ships_sunk: list[str] = field(default_factory=list)
    formation: str = "column"  # column | box | diamond


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ConvoyEngine:
    """WW2 convoy operations engine.

    Parameters
    ----------
    config:
        Convoy configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: ConvoyConfig | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._config = config or ConvoyConfig()
        self._rng = rng
        self._convoys: dict[str, ConvoyState] = {}

    def form_convoy(
        self,
        convoy_id: str,
        ship_ids: list[str],
        escort_ids: list[str],
        ship_speeds_kts: dict[str, float] | None = None,
        formation: str = "column",
    ) -> ConvoyState:
        """Create a new convoy.

        Parameters
        ----------
        convoy_id:
            Unique convoy identifier.
        ship_ids:
            Merchant ship unit IDs.
        escort_ids:
            Escort vessel unit IDs.
        ship_speeds_kts:
            Per-ship max speeds.  Convoy speed = min(all speeds, max_config).
        formation:
            Formation type: column, box, diamond.

        Returns
        -------
        The new convoy state.
        """
        if ship_speeds_kts:
            min_speed = min(ship_speeds_kts.values())
            speed = min(min_speed, self._config.max_convoy_speed_kts)
        else:
            speed = self._config.max_convoy_speed_kts

        convoy = ConvoyState(
            convoy_id=convoy_id,
            ship_ids=list(ship_ids),
            escort_ids=list(escort_ids),
            speed_kts=speed,
            formation=formation,
        )
        self._convoys[convoy_id] = convoy
        logger.info(
            "Convoy %s formed: %d ships, %d escorts, %.1f kts",
            convoy_id, len(ship_ids), len(escort_ids), speed,
        )
        return convoy

    def get_convoy(self, convoy_id: str) -> ConvoyState | None:
        """Get convoy state by ID."""
        return self._convoys.get(convoy_id)

    def update_convoy(self, convoy_id: str, dt_s: float) -> ConvoyState:
        """Update convoy for one tick — check for stragglers.

        Parameters
        ----------
        convoy_id:
            Convoy to update.
        dt_s:
            Time step in seconds.

        Returns
        -------
        Updated convoy state.
        """
        convoy = self._convoys[convoy_id]
        dt_hours = dt_s / 3600.0

        # Straggler check per ship
        p_straggle = 1.0 - (1.0 - self._config.straggler_probability_per_hour) ** dt_hours
        for ship_id in list(convoy.ship_ids):
            if ship_id in convoy.straggler_ids:
                continue
            if self._rng.random() < p_straggle:
                convoy.straggler_ids.append(ship_id)
                logger.info("Ship %s fell behind convoy %s", ship_id, convoy_id)

        return convoy

    def wolf_pack_attack(
        self,
        convoy_id: str,
        submarine_ids: list[str],
        torpedoes_per_sub: int = 2,
    ) -> dict[str, Any]:
        """Execute a wolf pack attack on a convoy.

        Parameters
        ----------
        convoy_id:
            Target convoy.
        submarine_ids:
            Attacking submarine unit IDs.
        torpedoes_per_sub:
            Torpedoes fired per submarine.

        Returns
        -------
        dict with keys: ``hits``, ``ships_hit``, ``torpedoes_fired``.
        """
        convoy = self._convoys[convoy_id]
        available_targets = [
            s for s in convoy.ship_ids
            if s not in convoy.ships_sunk
        ]
        if not available_targets:
            return {"hits": 0, "ships_hit": [], "torpedoes_fired": 0}

        # Coordination bonus for multiple subs
        num_subs = len(submarine_ids)
        coordination = (
            self._config.wolf_pack_coordination_bonus
            if num_subs > 1
            else 0.0
        )

        total_torpedoes = num_subs * torpedoes_per_sub
        p_hit = self._config.torpedo_hit_probability_base + coordination

        # Escort defense reduces hit probability
        escort_factor = max(0.3, 1.0 - 0.1 * len(convoy.escort_ids))
        p_hit *= escort_factor

        # Stragglers are easier targets
        hits = 0
        ships_hit: list[str] = []

        for _ in range(total_torpedoes):
            if not available_targets:
                break
            # Pick target (stragglers first)
            straggler_targets = [
                s for s in available_targets if s in convoy.straggler_ids
            ]
            if straggler_targets:
                target = self._rng.choice(straggler_targets)
                p_this = min(1.0, p_hit * 1.3)  # stragglers easier to hit
            else:
                target = self._rng.choice(available_targets)
                p_this = p_hit

            if self._rng.random() < p_this:
                hits += 1
                if target not in ships_hit:
                    ships_hit.append(target)
                    convoy.ships_sunk.append(target)
                    available_targets.remove(target)

        logger.info(
            "Wolf pack attack on convoy %s: %d torpedoes, %d hits, %d ships hit",
            convoy_id, total_torpedoes, hits, len(ships_hit),
        )
        return {
            "hits": hits,
            "ships_hit": ships_hit,
            "torpedoes_fired": total_torpedoes,
        }

    def depth_charge_attack(
        self,
        target_depth_m: float,
        estimated_range_error_m: float = 50.0,
    ) -> dict[str, Any]:
        """Execute a depth charge attack pattern.

        Parameters
        ----------
        target_depth_m:
            Estimated depth of the submarine target.
        estimated_range_error_m:
            1-sigma range estimation error in meters.

        Returns
        -------
        dict with keys: ``kill``, ``damage``, ``closest_charge_m``,
        ``charges_dropped``.
        """
        charges = self._config.depth_charge_charges_per_pattern
        lethal_r = self._config.depth_charge_lethal_radius_m
        spread = self._config.depth_charge_pattern_spread_m

        closest = float("inf")
        for _ in range(charges):
            # Each charge has a random offset from estimated position
            offset_x = self._rng.normal(0, spread / 2)
            offset_y = self._rng.normal(0, spread / 2)
            offset_z = self._rng.normal(0, estimated_range_error_m / 2)
            dist = math.sqrt(offset_x**2 + offset_y**2 + offset_z**2)
            closest = min(closest, dist)

        kill = closest <= lethal_r
        damage = closest <= lethal_r * 3  # damage zone is 3x lethal

        return {
            "kill": kill,
            "damage": damage or kill,
            "closest_charge_m": closest,
            "charges_dropped": charges,
        }

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "convoys": {
                cid: {
                    "convoy_id": c.convoy_id,
                    "ship_ids": list(c.ship_ids),
                    "escort_ids": list(c.escort_ids),
                    "speed_kts": c.speed_kts,
                    "heading_deg": c.heading_deg,
                    "straggler_ids": list(c.straggler_ids),
                    "ships_sunk": list(c.ships_sunk),
                    "formation": c.formation,
                }
                for cid, c in self._convoys.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._convoys.clear()
        for cid, cdata in state.get("convoys", {}).items():
            self._convoys[cid] = ConvoyState(**cdata)

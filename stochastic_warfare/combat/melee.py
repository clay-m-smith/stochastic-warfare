"""Napoleonic melee combat — bayonet charges, cavalry charges, saber duels.

The existing engagement system is entirely ranged.  Melee bypasses it.
Pre-contact morale check is critical: most Napoleonic charges were decided
*before* contact — the defender broke and ran.

Physics
-------
* Pre-contact morale threshold — defender breaks if morale < threshold.
* Cavalry shock multiplier lowers defender threshold further.
* Contact: casualties = force_ratio × base_rate × formation_modifier.
* Cavalry vs square: modifier 0.1 (square is ~immune).
* Cavalry vs line: modifier 1.5 (devastating).
* Shock bonus decays per round of sustained melee.
* Pursuit: fleeing troops suffer heavy casualties.
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


class MeleeType(enum.IntEnum):
    """Type of melee engagement."""

    BAYONET_CHARGE = 0
    CAVALRY_CHARGE = 1
    CAVALRY_VS_CAVALRY = 2
    MIXED_MELEE = 3
    # Ancient/Medieval types (Phase 23)
    PIKE_PUSH = 4
    SHIELD_WALL = 5
    MOUNTED_CHARGE = 6


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class MeleeConfig(BaseModel):
    """Configuration for melee combat resolution."""

    pre_contact_morale_threshold: float = 0.4
    cavalry_shock_multiplier: float = 2.0
    cavalry_vs_square_modifier: float = 0.1
    cavalry_vs_line_modifier: float = 1.5
    cavalry_vs_column_modifier: float = 1.0
    cavalry_vs_skirmish_modifier: float = 1.8
    bayonet_casualty_rate: float = 0.02
    cavalry_casualty_rate: float = 0.03
    pursuit_casualty_rate: float = 0.10
    shock_decay_per_round: float = 0.3
    defender_morale_penalty: float = 0.15
    attacker_morale_boost: float = 0.05
    # Ancient/Medieval additions (Phase 23)
    reach_advantage_modifier: float = 1.3
    flanking_casualty_multiplier: float = 2.5
    pike_push_attrition_rate: float = 0.01
    shield_wall_defense_bonus: float = 0.5
    mounted_charge_casualty_rate: float = 0.04


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class MeleeResult:
    """Result of a melee combat round."""

    attacker_casualties: int
    defender_casualties: int
    attacker_morale_change: float
    defender_morale_change: float
    defender_routed: bool
    attacker_routed: bool


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MeleeEngine:
    """Napoleonic melee combat resolution.

    Parameters
    ----------
    config:
        Melee configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: MeleeConfig | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._config = config or MeleeConfig()
        self._rng = rng

    def check_pre_contact_morale(
        self,
        attacker_morale: float,
        defender_morale: float,
        melee_type: MeleeType,
        defender_formation_cavalry_vuln: float = 1.0,
    ) -> tuple[bool, bool]:
        """Check if either side breaks before contact.

        Returns (defender_breaks, attacker_breaks).
        """
        cfg = self._config
        threshold = cfg.pre_contact_morale_threshold

        # Cavalry shock lowers defender threshold
        if melee_type in (MeleeType.CAVALRY_CHARGE, MeleeType.MIXED_MELEE):
            effective_threshold = threshold * (
                1.0 + cfg.cavalry_shock_multiplier * defender_formation_cavalry_vuln
            )
        else:
            effective_threshold = threshold

        defender_breaks = defender_morale < effective_threshold
        # Attacker breaks only at very low morale
        attacker_breaks = attacker_morale < threshold * 0.5

        return defender_breaks, attacker_breaks

    def compute_reach_advantage(
        self,
        attacker_reach_m: float,
        defender_reach_m: float,
        round_number: int = 1,
    ) -> float:
        """Compute reach advantage modifier.

        Longer weapon gets a bonus on round 1 only (first contact).
        After first round, close quarters negates reach.

        Returns modifier applied to attacker casualty-inflicting rate.
        """
        if round_number > 1:
            return 1.0
        if attacker_reach_m > defender_reach_m:
            return self._config.reach_advantage_modifier
        return 1.0

    def compute_flanking_bonus(self, is_flanked: bool) -> float:
        """Return flanking casualty multiplier.

        Returns ``flanking_casualty_multiplier`` if flanked, else 1.0.
        """
        if is_flanked:
            return self._config.flanking_casualty_multiplier
        return 1.0

    def resolve_melee_round(
        self,
        attacker_strength: int,
        defender_strength: int,
        melee_type: MeleeType,
        defender_formation_cavalry_vuln: float = 1.0,
        round_number: int = 1,
        attacker_reach_m: float = 1.0,
        defender_reach_m: float = 1.0,
        is_flanked: bool = False,
    ) -> MeleeResult:
        """Resolve one round of melee combat.

        Parameters
        ----------
        attacker_strength:
            Number of attacking combatants.
        defender_strength:
            Number of defending combatants.
        melee_type:
            Type of melee.
        defender_formation_cavalry_vuln:
            Defender's cavalry vulnerability from formation.
        round_number:
            Round number (1-based); shock decays with each round.
        attacker_reach_m:
            Attacker weapon reach in metres (for reach advantage).
        defender_reach_m:
            Defender weapon reach in metres (for reach advantage).
        is_flanked:
            Whether the defender is flanked.
        """
        cfg = self._config

        if attacker_strength <= 0 or defender_strength <= 0:
            return MeleeResult(
                attacker_casualties=0,
                defender_casualties=0,
                attacker_morale_change=0.0,
                defender_morale_change=0.0,
                defender_routed=False,
                attacker_routed=False,
            )

        # Force ratio
        force_ratio = attacker_strength / defender_strength

        # Base casualty rate depends on melee type
        if melee_type in (MeleeType.CAVALRY_CHARGE, MeleeType.CAVALRY_VS_CAVALRY):
            base_rate = cfg.cavalry_casualty_rate
        elif melee_type == MeleeType.PIKE_PUSH:
            base_rate = cfg.pike_push_attrition_rate
        elif melee_type == MeleeType.MOUNTED_CHARGE:
            base_rate = cfg.mounted_charge_casualty_rate
        elif melee_type == MeleeType.SHIELD_WALL:
            base_rate = cfg.bayonet_casualty_rate
        else:
            base_rate = cfg.bayonet_casualty_rate

        # Formation modifier (only applies to cavalry vs formation)
        formation_mod = 1.0
        if melee_type == MeleeType.CAVALRY_CHARGE:
            # Use the cavalry vulnerability directly as formation modifier
            if defender_formation_cavalry_vuln <= 0.15:
                formation_mod = cfg.cavalry_vs_square_modifier
            elif defender_formation_cavalry_vuln >= 1.4:
                formation_mod = cfg.cavalry_vs_skirmish_modifier
            elif defender_formation_cavalry_vuln >= 1.2:
                formation_mod = cfg.cavalry_vs_line_modifier
            else:
                formation_mod = cfg.cavalry_vs_column_modifier

        # Shield wall defense bonus — halves incoming casualties
        defense_mod = 1.0
        if melee_type == MeleeType.SHIELD_WALL:
            defense_mod = cfg.shield_wall_defense_bonus

        # Reach advantage (round 1 only)
        reach_mod = self.compute_reach_advantage(
            attacker_reach_m, defender_reach_m, round_number,
        )

        # Flanking multiplier
        flank_mod = self.compute_flanking_bonus(is_flanked)

        # Shock decay over rounds
        shock_bonus = max(0.0, 1.0 - cfg.shock_decay_per_round * (round_number - 1))

        # Defender casualties
        def_cas_rate = min(
            0.5,
            base_rate * force_ratio * formation_mod * (1.0 + shock_bonus)
            * reach_mod * flank_mod,
        )
        defender_cas = int(self._rng.binomial(defender_strength, def_cas_rate))

        # Attacker casualties (defenders fight back)
        att_cas_rate = min(
            0.5,
            base_rate / max(0.5, force_ratio) * (1.0 / max(0.1, formation_mod))
            * defense_mod,
        )
        attacker_cas = int(self._rng.binomial(attacker_strength, att_cas_rate))

        # Morale effects
        def_morale = -cfg.defender_morale_penalty * force_ratio * formation_mod
        att_morale = cfg.attacker_morale_boost * force_ratio

        # Check for rout
        defender_routed = defender_cas >= defender_strength * 0.3
        attacker_routed = attacker_cas >= attacker_strength * 0.3

        return MeleeResult(
            attacker_casualties=attacker_cas,
            defender_casualties=defender_cas,
            attacker_morale_change=att_morale,
            defender_morale_change=def_morale,
            defender_routed=defender_routed,
            attacker_routed=attacker_routed,
        )

    def compute_pursuit_casualties(
        self,
        routed_strength: int,
        pursuer_speed: float,
        routed_speed: float,
        dt_s: float,
    ) -> int:
        """Compute casualties inflicted on routed troops during pursuit.

        Pursuit only occurs if pursuer is faster than routed troops.
        """
        if pursuer_speed <= routed_speed or routed_strength <= 0:
            return 0

        cfg = self._config
        speed_ratio = pursuer_speed / max(0.1, routed_speed)
        rate = cfg.pursuit_casualty_rate * min(3.0, speed_ratio) * (dt_s / 60.0)
        rate = min(0.5, rate)
        return int(self._rng.binomial(routed_strength, rate))

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {}

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""

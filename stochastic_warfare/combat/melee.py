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
    # Cavalry terrain effects (Phase 27 — deficit 2.11)
    cavalry_slope_penalty_per_deg: float = 0.02
    cavalry_soft_ground_penalty: float = 0.3
    cavalry_obstacle_abort_threshold: float = 0.5
    cavalry_uphill_casualty_bonus: float = 0.1
    # Frontage constraint (Phase 27 — deficit 2.10)
    max_frontage_m: float = 0.0  # 0 = disabled
    combatant_spacing_m: float = 1.5
    second_rank_effectiveness: float = 0.3


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

    def compute_cavalry_terrain_modifier(
        self,
        slope_deg: float = 0.0,
        soft_ground: bool = False,
        obstacle_density: float = 0.0,
    ) -> tuple[float, bool]:
        """Compute terrain effects on cavalry charge.

        Returns (speed_modifier, should_abort). speed_modifier is 0.0–1.0
        factor applied to cavalry shock/speed. should_abort is True when
        obstacle density exceeds the abort threshold.
        """
        cfg = self._config
        modifier = 1.0

        # Uphill slope degrades charge speed
        if slope_deg > 0:
            modifier -= cfg.cavalry_slope_penalty_per_deg * slope_deg

        # Soft ground (mud, bog, sand) further reduces effectiveness
        if soft_ground:
            modifier -= cfg.cavalry_soft_ground_penalty

        modifier = max(0.0, modifier)

        # Dense obstacles abort the charge entirely
        should_abort = obstacle_density >= cfg.cavalry_obstacle_abort_threshold

        return modifier, should_abort

    def compute_frontage_constraint(
        self,
        attacker_strength: int,
        defender_strength: int,
        frontage_m: float = 0.0,
    ) -> tuple[int, int, int]:
        """Limit engaged combatants based on available frontage.

        Parameters
        ----------
        attacker_strength:
            Total attacker combatants.
        defender_strength:
            Total defender combatants.
        frontage_m:
            Available frontage in metres (0 = disabled).

        Returns
        -------
        (engaged_attackers, engaged_defenders, reserve_attackers)
        """
        if frontage_m <= 0 or self._config.combatant_spacing_m <= 0:
            return attacker_strength, defender_strength, 0

        max_in_line = max(1, int(frontage_m / self._config.combatant_spacing_m))
        engaged_att = min(attacker_strength, max_in_line)
        engaged_def = min(defender_strength, max_in_line)
        reserve_att = attacker_strength - engaged_att
        return engaged_att, engaged_def, reserve_att

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
        slope_deg: float = 0.0,
        soft_ground: bool = False,
        obstacle_density: float = 0.0,
        frontage_m: float = 0.0,
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

        # Cavalry terrain effects (deficit 2.11)
        terrain_mod = 1.0
        is_cavalry = melee_type in (
            MeleeType.CAVALRY_CHARGE, MeleeType.CAVALRY_VS_CAVALRY,
            MeleeType.MOUNTED_CHARGE,
        )
        if is_cavalry and (slope_deg > 0 or soft_ground or obstacle_density > 0):
            terrain_mod, should_abort = self.compute_cavalry_terrain_modifier(
                slope_deg, soft_ground, obstacle_density,
            )
            if should_abort:
                return MeleeResult(
                    attacker_casualties=0,
                    defender_casualties=0,
                    attacker_morale_change=0.0,
                    defender_morale_change=0.0,
                    defender_routed=False,
                    attacker_routed=False,
                )

        # Frontage constraint (deficit 2.10)
        engaged_att, engaged_def, reserve_att = self.compute_frontage_constraint(
            attacker_strength, defender_strength, frontage_m,
        )

        # Force ratio
        force_ratio = engaged_att / engaged_def

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

        # Shock decay over rounds — terrain_mod reduces cavalry shock
        shock_bonus = max(0.0, 1.0 - cfg.shock_decay_per_round * (round_number - 1))
        shock_bonus *= terrain_mod

        # Defender casualties (use engaged strengths for frontage)
        def_cas_rate = min(
            0.5,
            base_rate * force_ratio * formation_mod * (1.0 + shock_bonus)
            * reach_mod * flank_mod,
        )
        defender_cas = int(self._rng.binomial(engaged_def, def_cas_rate))
        # Reserves contribute at reduced effectiveness
        if reserve_att > 0:
            reserve_rate = def_cas_rate * cfg.second_rank_effectiveness
            defender_cas += int(self._rng.binomial(
                min(reserve_att, engaged_def), min(0.5, reserve_rate),
            ))

        # Attacker casualties (defenders fight back)
        att_cas_rate = min(
            0.5,
            base_rate / max(0.5, force_ratio) * (1.0 / max(0.1, formation_mod))
            * defense_mod,
        )
        # Uphill cavalry casualty bonus (attacker takes more casualties charging uphill)
        if is_cavalry and slope_deg > 0:
            att_cas_rate = min(0.5, att_cas_rate + cfg.cavalry_uphill_casualty_bonus)
        attacker_cas = int(self._rng.binomial(engaged_att, att_cas_rate))

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

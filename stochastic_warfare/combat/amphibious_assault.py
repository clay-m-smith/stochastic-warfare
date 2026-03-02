"""Amphibious assault mechanics — beach assault wave resolution.

Models the phases of an amphibious assault: approach under fire,
initial wave landing, buildup, and establishment of a beachhead.
Integrates naval surface fire support and accounts for beach
defensive strength, sea conditions, and terrain advantage.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.combat.damage import DamageEngine
from stochastic_warfare.combat.events import AmphibiousAssaultEvent
from stochastic_warfare.combat.naval_gunfire_support import NavalGunfireSupportEngine
from stochastic_warfare.combat.naval_surface import NavalSurfaceEngine
from stochastic_warfare.core.events import EventBus
from stochastic_warfare.core.logging import get_logger
from stochastic_warfare.core.types import ModuleId

logger = get_logger(__name__)


class AssaultPhase(enum.IntEnum):
    """Phases of an amphibious assault."""

    APPROACH = 0
    INITIAL_WAVE = 1
    BUILDUP = 2
    ESTABLISHED = 3


class AmphibiousAssaultConfig(BaseModel):
    """Tunable parameters for amphibious assault."""

    approach_attrition_factor: float = 0.05  # base casualty rate during approach
    wave_landing_factor: float = 0.8  # fraction that successfully land
    naval_support_effectiveness: float = 0.3  # suppression from NGFS
    sea_state_penalty_threshold: float = 3.0  # above this, landing is harder
    terrain_defense_multiplier: float = 1.5  # defender terrain advantage
    buildup_efficiency: float = 0.9  # fraction of subsequent waves that land
    min_force_ratio_for_establishment: float = 1.5  # attacker:defender ratio


@dataclass
class WaveResult:
    """Outcome of an amphibious assault wave."""

    wave_size: int
    landed: int
    casualties: int
    vehicles_lost: int = 0
    naval_support_suppression: float = 0.0
    phase: AssaultPhase = AssaultPhase.INITIAL_WAVE


@dataclass
class BeachCombatResult:
    """Outcome of beach combat after landing."""

    attacker_strength_remaining: float
    defender_strength_remaining: float
    attacker_casualties_fraction: float
    defender_casualties_fraction: float
    beachhead_established: bool = False


class AmphibiousAssaultEngine:
    """Manages amphibious assault wave execution and beach combat.

    Parameters
    ----------
    naval_surface_engine:
        For modeling fire support from naval vessels.
    naval_gunfire_engine:
        For shore bombardment support.
    damage_engine:
        For resolving damage.
    event_bus:
        For publishing assault events.
    rng:
        PRNG generator.
    config:
        Tunable parameters.
    """

    def __init__(
        self,
        naval_surface_engine: NavalSurfaceEngine,
        naval_gunfire_engine: NavalGunfireSupportEngine,
        damage_engine: DamageEngine,
        event_bus: EventBus,
        rng: np.random.Generator,
        config: AmphibiousAssaultConfig | None = None,
    ) -> None:
        self._naval_surface = naval_surface_engine
        self._naval_gunfire = naval_gunfire_engine
        self._damage = damage_engine
        self._event_bus = event_bus
        self._rng = rng
        self._config = config or AmphibiousAssaultConfig()
        self._wave_count: int = 0

    def execute_wave(
        self,
        wave_size: int,
        beach_defense_strength: float,
        naval_support_factor: float = 0.0,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
    ) -> WaveResult:
        """Execute an amphibious assault wave.

        Parameters
        ----------
        wave_size:
            Number of troops in the wave.
        beach_defense_strength:
            Relative defensive strength 0.0–1.0.
        naval_support_factor:
            Level of naval fire support 0.0–1.0.
        conditions:
            Environmental conditions (sea_state, visibility).
        timestamp:
            Simulation timestamp.
        """
        self._wave_count += 1
        cfg = self._config

        # Naval support suppresses defenders
        suppression = naval_support_factor * cfg.naval_support_effectiveness
        effective_defense = beach_defense_strength * (1.0 - suppression)

        # Sea state penalty
        sea_state = 0.0
        if conditions:
            sea_state = conditions.get("sea_state", 0.0)
        sea_penalty = 0.0
        if sea_state > cfg.sea_state_penalty_threshold:
            sea_penalty = (sea_state - cfg.sea_state_penalty_threshold) * 0.1

        # Landing factor (how many make it to shore)
        landing_factor = cfg.wave_landing_factor - sea_penalty
        landing_factor = max(0.1, min(1.0, landing_factor))

        # Approach attrition from beach defenses
        approach_attrition = cfg.approach_attrition_factor * effective_defense
        approach_attrition += approach_attrition * self._rng.normal(0.0, 0.3)
        approach_attrition = max(0.0, min(0.8, approach_attrition))

        # Compute outcomes
        approach_casualties = int(wave_size * approach_attrition)
        survivors = wave_size - approach_casualties

        # Landing success (stochastic)
        landed = int(self._rng.binomial(survivors, min(landing_factor, 1.0)))
        landing_casualties = survivors - landed

        total_casualties = approach_casualties + landing_casualties

        # Determine phase
        if self._wave_count == 1:
            phase = AssaultPhase.INITIAL_WAVE
        else:
            phase = AssaultPhase.BUILDUP

        result = WaveResult(
            wave_size=wave_size,
            landed=landed,
            casualties=total_casualties,
            naval_support_suppression=suppression,
            phase=phase,
        )

        if timestamp is not None:
            self._event_bus.publish(AmphibiousAssaultEvent(
                timestamp=timestamp, source=ModuleId.COMBAT,
                wave_id=f"wave_{self._wave_count}",
                wave_size=wave_size,
                landed=landed,
                casualties=total_casualties,
                phase=phase.name,
            ))

        logger.debug(
            "Wave %d: %d troops, %d landed, %d casualties",
            self._wave_count, wave_size, landed, total_casualties,
        )

        return result

    def resolve_beach_combat(
        self,
        assaulter_strength: float,
        defender_strength: float,
        terrain_advantage: float = 1.0,
    ) -> BeachCombatResult:
        """Resolve combat on the beach after landing.

        Uses a Lanchester-inspired attrition model with terrain advantage
        for the defender.

        Parameters
        ----------
        assaulter_strength:
            Relative attacking force strength.
        defender_strength:
            Relative defending force strength.
        terrain_advantage:
            Terrain advantage multiplier for the defender (>1.0 favors defense).
        """
        cfg = self._config

        # Effective defender strength with terrain advantage
        effective_defender = defender_strength * terrain_advantage * cfg.terrain_defense_multiplier

        # Force ratio
        if effective_defender > 0:
            ratio = assaulter_strength / effective_defender
        else:
            ratio = float("inf")

        # Attrition computation (Lanchester linear law variant)
        # Attacker casualties proportional to defender strength
        attacker_attrition_base = min(1.0, effective_defender / max(assaulter_strength, 0.01)) * 0.3
        # Defender casualties proportional to attacker strength
        defender_attrition_base = min(1.0, assaulter_strength / max(effective_defender, 0.01)) * 0.3

        # Add stochastic variation
        attacker_attrition = attacker_attrition_base * (0.5 + self._rng.random())
        defender_attrition = defender_attrition_base * (0.5 + self._rng.random())

        attacker_attrition = min(1.0, max(0.0, attacker_attrition))
        defender_attrition = min(1.0, max(0.0, defender_attrition))

        attacker_remaining = assaulter_strength * (1.0 - attacker_attrition)
        defender_remaining = defender_strength * (1.0 - defender_attrition)

        # Beachhead established if remaining force ratio exceeds threshold
        if defender_remaining > 0:
            remaining_ratio = attacker_remaining / defender_remaining
        else:
            remaining_ratio = float("inf")

        established = remaining_ratio >= cfg.min_force_ratio_for_establishment

        return BeachCombatResult(
            attacker_strength_remaining=attacker_remaining,
            defender_strength_remaining=defender_remaining,
            attacker_casualties_fraction=attacker_attrition,
            defender_casualties_fraction=defender_attrition,
            beachhead_established=established,
        )

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "wave_count": self._wave_count,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._wave_count = state["wave_count"]

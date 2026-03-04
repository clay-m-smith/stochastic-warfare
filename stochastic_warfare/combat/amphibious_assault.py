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
    enable_landing_craft_model: bool = False  # enable craft-limited throughput


@dataclass
class LandingCraft:
    """A single landing craft used for ship-to-shore movement."""

    craft_id: str
    capacity_troops: int = 200
    turnaround_time_s: float = 3600.0
    min_beach_depth_m: float = 1.5
    speed_kts: float = 10.0


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

    def compute_throughput(
        self,
        craft: list[LandingCraft],
        beach_gradient: float,
        obstacle_factor: float,
        fire_factor: float,
    ) -> float:
        """Compute troop throughput (troops per second) for a set of craft.

        Parameters
        ----------
        craft:
            Available landing craft.
        beach_gradient:
            Beach slope factor 0.0–1.0.  Steeper or rougher beaches reduce
            throughput (1.0 = ideal, 0.0 = impassable).
        obstacle_factor:
            Obstacle multiplier 0.0–1.0 (1.0 = clear beach).
        fire_factor:
            Defensive fire multiplier 0.0–1.0 (1.0 = no opposing fire).

        Returns
        -------
        float
            Effective troops per second that can be delivered to shore.
        """
        if not craft:
            return 0.0

        raw_throughput = sum(
            c.capacity_troops / max(c.turnaround_time_s, 1.0) for c in craft
        )
        return raw_throughput * beach_gradient * obstacle_factor * fire_factor

    @staticmethod
    def check_tidal_window(
        tide_height_m: float,
        craft_min_depth: float,
    ) -> bool:
        """Check whether the tide permits landing craft to beach.

        Parameters
        ----------
        tide_height_m:
            Current tide height in meters above chart datum.
        craft_min_depth:
            Minimum water depth the craft requires to reach the beach.

        Returns
        -------
        bool
            ``True`` if the tide is high enough for the craft to beach.
        """
        return tide_height_m >= craft_min_depth

    def execute_wave_with_craft(
        self,
        wave_size: int,
        craft: list[LandingCraft],
        tide_height: float,
        beach_gradient: float,
        defense_strength: float,
        conditions: dict[str, Any] | None = None,
        timestamp: Any = None,
    ) -> WaveResult:
        """Execute an amphibious wave constrained by landing craft and tides.

        The number of troops that can land in a single wave is limited by
        total craft capacity.  If the tidal window is closed for any craft
        its capacity is excluded.

        Parameters
        ----------
        wave_size:
            Number of troops assigned to the wave.
        craft:
            Available landing craft.
        tide_height:
            Current tide height in meters above chart datum.
        beach_gradient:
            Beach slope factor 0.0–1.0 (affects throughput).
        defense_strength:
            Beach defensive strength 0.0–1.0.
        conditions:
            Environmental conditions (``sea_state``, ``visibility``).
        timestamp:
            Simulation timestamp.
        """
        # Filter craft by tidal window
        usable_craft = [
            c for c in craft
            if self.check_tidal_window(tide_height, c.min_beach_depth_m)
        ]

        if not usable_craft:
            logger.debug("No craft can beach at tide height %.1f m", tide_height)
            return WaveResult(
                wave_size=wave_size,
                landed=0,
                casualties=0,
                phase=AssaultPhase.APPROACH,
            )

        # Craft capacity limits how many troops can go in one lift
        total_capacity = sum(c.capacity_troops for c in usable_craft)
        effective_wave = min(wave_size, total_capacity)

        # Compute throughput modifier (affects landing success)
        fire_factor = max(0.0, 1.0 - defense_strength)
        obstacle_factor = 1.0  # can be extended later
        throughput = self.compute_throughput(
            usable_craft, beach_gradient, obstacle_factor, fire_factor,
        )

        # Naval support — not separately specified here, use 0.0 default
        naval_support_factor = 0.0

        # Delegate to the standard wave execution with the capacity-limited size
        result = self.execute_wave(
            wave_size=effective_wave,
            beach_defense_strength=defense_strength,
            naval_support_factor=naval_support_factor,
            conditions=conditions,
            timestamp=timestamp,
        )

        # If wave_size exceeded capacity, the remainder did not embark
        # Report the original wave_size for bookkeeping
        result.wave_size = wave_size

        return result

    def get_state(self) -> dict[str, Any]:
        return {
            "rng_state": self._rng.bit_generator.state,
            "wave_count": self._wave_count,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._rng.bit_generator.state = state["rng_state"]
        self._wave_count = state["wave_count"]

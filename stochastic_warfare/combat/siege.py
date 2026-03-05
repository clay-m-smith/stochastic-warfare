"""Siege warfare — campaign-scale state machine with daily resolution.

Models the progression of a siege from encirclement through bombardment,
breach, and assault.  Starvation timeline from garrison size vs food stores.
Siege engines (trebuchet, ram, catapult) have breach rates.

States: ENCIRCLEMENT -> BOMBARDMENT -> BREACH -> ASSAULT -> FALLEN / RELIEF / ABANDONED
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


class SiegePhase(enum.IntEnum):
    """Current phase of a siege."""

    ENCIRCLEMENT = 0
    BOMBARDMENT = 1
    BREACH = 2
    ASSAULT = 3
    FALLEN = 4
    RELIEF = 5
    ABANDONED = 6


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class SiegeConfig(BaseModel):
    """Configuration for siege warfare model."""

    wall_hp: float = 1000.0
    trebuchet_damage_per_day: float = 50.0
    ram_damage_per_day: float = 30.0
    catapult_damage_per_day: float = 20.0
    mine_damage_per_day: float = 40.0
    breach_threshold: float = 0.3
    assault_casualty_rate_attacker: float = 0.15
    assault_casualty_rate_defender: float = 0.08
    starvation_days: int = 60
    starvation_attrition_rate: float = 0.02
    sally_probability: float = 0.05
    sally_casualty_rate: float = 0.03
    relief_force_ratio: float = 0.5


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class SiegeState:
    """Tracks state of a single siege."""

    siege_id: str
    phase: SiegePhase = SiegePhase.ENCIRCLEMENT
    wall_hp_remaining: float = 1000.0
    days_elapsed: int = 0
    garrison_size: int = 0
    garrison_food_days: int = 60
    attacker_size: int = 0
    engines_count: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.engines_count is None:
            self.engines_count = {}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SiegeEngine:
    """Manages siege state machines.

    Parameters
    ----------
    config:
        Siege configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: SiegeConfig | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._config = config or SiegeConfig()
        self._rng = rng or np.random.default_rng(42)
        self._sieges: dict[str, SiegeState] = {}

    def begin_siege(
        self,
        siege_id: str,
        garrison_size: int,
        food_days: int,
        attacker_size: int,
        wall_hp: float | None = None,
    ) -> SiegeState:
        """Begin a new siege.

        Parameters
        ----------
        siege_id:
            Unique siege identifier.
        garrison_size:
            Number of defenders.
        food_days:
            Days of food stores.
        attacker_size:
            Number of attackers.
        wall_hp:
            Wall hit points (defaults to config).
        """
        hp = wall_hp if wall_hp is not None else self._config.wall_hp
        state = SiegeState(
            siege_id=siege_id,
            phase=SiegePhase.ENCIRCLEMENT,
            wall_hp_remaining=hp,
            garrison_size=garrison_size,
            garrison_food_days=food_days,
            attacker_size=attacker_size,
        )
        self._sieges[siege_id] = state
        logger.info(
            "Siege %s begun: %d defenders, %d attackers, %.0f wall HP",
            siege_id, garrison_size, attacker_size, hp,
        )
        return state

    def advance_day(
        self,
        siege_id: str,
        n_trebuchets: int = 0,
        n_rams: int = 0,
        n_catapults: int = 0,
        n_mines: int = 0,
    ) -> SiegeState:
        """Advance one day of siege operations.

        Returns updated siege state.
        """
        state = self._sieges[siege_id]
        if state.phase in (SiegePhase.FALLEN, SiegePhase.RELIEF, SiegePhase.ABANDONED):
            return state

        state.days_elapsed += 1
        cfg = self._config

        # Move to bombardment if we have siege engines
        if state.phase == SiegePhase.ENCIRCLEMENT:
            if n_trebuchets + n_rams + n_catapults + n_mines > 0:
                state.phase = SiegePhase.BOMBARDMENT

        # Apply wall damage during bombardment
        if state.phase == SiegePhase.BOMBARDMENT:
            damage = (
                n_trebuchets * cfg.trebuchet_damage_per_day
                + n_rams * cfg.ram_damage_per_day
                + n_catapults * cfg.catapult_damage_per_day
                + n_mines * cfg.mine_damage_per_day
            )
            state.wall_hp_remaining = max(0.0, state.wall_hp_remaining - damage)

            # Check for breach
            if state.wall_hp_remaining <= cfg.breach_threshold * cfg.wall_hp:
                state.phase = SiegePhase.BREACH
                logger.info("Siege %s: BREACH at day %d", siege_id, state.days_elapsed)

        # Consume food
        state.garrison_food_days -= 1

        # Store engine counts
        state.engines_count = {
            "trebuchets": n_trebuchets,
            "rams": n_rams,
            "catapults": n_catapults,
            "mines": n_mines,
        }

        return state

    def attempt_assault(self, siege_id: str) -> tuple[bool, int, int]:
        """Attempt an assault on the fortification.

        Returns (success, attacker_casualties, defender_casualties).
        """
        state = self._sieges[siege_id]
        cfg = self._config

        if state.phase not in (SiegePhase.BREACH, SiegePhase.BOMBARDMENT):
            return False, 0, 0

        att_cas = int(self._rng.binomial(
            state.attacker_size, cfg.assault_casualty_rate_attacker,
        ))
        def_cas = int(self._rng.binomial(
            state.garrison_size, cfg.assault_casualty_rate_defender,
        ))

        state.attacker_size = max(0, state.attacker_size - att_cas)
        state.garrison_size = max(0, state.garrison_size - def_cas)

        # Assault succeeds if breach and garrison heavily reduced
        if state.phase == SiegePhase.BREACH and state.garrison_size <= 0:
            state.phase = SiegePhase.FALLEN
            success = True
        elif state.phase == SiegePhase.BREACH and def_cas > state.garrison_size * 0.5:
            state.phase = SiegePhase.FALLEN
            success = True
        else:
            success = False

        logger.info(
            "Siege %s assault: %s (att_cas=%d, def_cas=%d)",
            siege_id, "SUCCESS" if success else "REPULSED", att_cas, def_cas,
        )
        return success, att_cas, def_cas

    def check_starvation(self, siege_id: str) -> int:
        """Check for starvation attrition.

        Returns number of garrison casualties from starvation.
        """
        state = self._sieges[siege_id]
        cfg = self._config

        if state.garrison_food_days > 0:
            return 0

        # Garrison is starving
        casualties = int(self._rng.binomial(
            state.garrison_size, cfg.starvation_attrition_rate,
        ))
        state.garrison_size = max(0, state.garrison_size - casualties)

        if state.garrison_size <= 0:
            state.phase = SiegePhase.FALLEN

        return casualties

    def sally_sortie(self, siege_id: str) -> tuple[bool, int]:
        """Check if garrison attempts a sally sortie.

        Returns (attempted, attacker_casualties).
        """
        state = self._sieges[siege_id]
        cfg = self._config

        if state.phase in (SiegePhase.FALLEN, SiegePhase.RELIEF, SiegePhase.ABANDONED):
            return False, 0

        if self._rng.random() >= cfg.sally_probability:
            return False, 0

        # Sally attempted
        att_cas = int(self._rng.binomial(
            state.attacker_size, cfg.sally_casualty_rate,
        ))
        state.attacker_size = max(0, state.attacker_size - att_cas)

        logger.info(
            "Siege %s: sally sortie! Attacker casualties: %d",
            siege_id, att_cas,
        )
        return True, att_cas

    def relieve_siege(
        self,
        siege_id: str,
        relief_force_size: int,
    ) -> bool:
        """Attempt to relieve the siege with an external force.

        Returns True if siege is lifted.
        """
        state = self._sieges[siege_id]
        cfg = self._config

        if relief_force_size > state.attacker_size * cfg.relief_force_ratio:
            state.phase = SiegePhase.RELIEF
            logger.info(
                "Siege %s: RELIEVED by force of %d",
                siege_id, relief_force_size,
            )
            return True
        return False

    def get_phase(self, siege_id: str) -> SiegePhase:
        """Return current phase of a siege."""
        return self._sieges[siege_id].phase

    def get_siege_state(self, siege_id: str) -> SiegeState:
        """Return the full state of a siege."""
        return self._sieges[siege_id]

    # ── State persistence ─────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "sieges": {
                sid: {
                    "siege_id": s.siege_id,
                    "phase": int(s.phase),
                    "wall_hp_remaining": s.wall_hp_remaining,
                    "days_elapsed": s.days_elapsed,
                    "garrison_size": s.garrison_size,
                    "garrison_food_days": s.garrison_food_days,
                    "attacker_size": s.attacker_size,
                    "engines_count": dict(s.engines_count) if s.engines_count else {},
                }
                for sid, s in self._sieges.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._sieges.clear()
        for sid, sdata in state.get("sieges", {}).items():
            self._sieges[sid] = SiegeState(
                siege_id=sdata["siege_id"],
                phase=SiegePhase(sdata["phase"]),
                wall_hp_remaining=sdata["wall_hp_remaining"],
                days_elapsed=sdata["days_elapsed"],
                garrison_size=sdata["garrison_size"],
                garrison_food_days=sdata["garrison_food_days"],
                attacker_size=sdata["attacker_size"],
                engines_count=sdata.get("engines_count", {}),
            )

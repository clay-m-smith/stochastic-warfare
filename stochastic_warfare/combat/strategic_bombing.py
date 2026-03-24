"""WW2 strategic bombing — area bombing model for strategic campaigns.

Models USAAF daylight and RAF night bombing, including CEP-based area
damage, Norden bombsight altitude-dependent accuracy, flak as Poisson
process, fighter escort, bomber stream mutual defensive fire, and
cumulative target damage across raids.

Physics
-------
* CEP-based circular-normal distribution around aim point.
* Norden bombsight CEP scales with altitude: ``cep = base_cep * (alt / 6000)``.
* Flak: Poisson ``Pk`` per aircraft per pass, modulated by altitude.
* Fighter escort: reduces fighter interception effectiveness.
* Target damage accumulates across raids with partial regeneration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from stochastic_warfare.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class StrategicBombingConfig(BaseModel):
    """Configuration for WW2-era strategic bombing."""

    formation_cep_m: float = 500.0
    """Base CEP in meters for formation bombing (300-1000m)."""

    norden_reference_altitude_m: float = 6000.0
    """Reference altitude for base CEP (altitude scaling denominator)."""

    flak_pk_per_pass: float = 0.02
    """Probability of loss per aircraft per flak pass at reference alt."""

    flak_reference_altitude_m: float = 6000.0
    """Reference altitude for flak Pk (higher = less effective)."""

    fighter_escort_effectiveness: float = 0.5
    """Fraction of interceptors neutralized by escort (0-1)."""

    bomber_defensive_fire_pk: float = 0.05
    """Probability an interceptor is downed by bomber defensive fire per pass."""

    target_regeneration_rate: float = 0.05
    """Fraction of damage repaired per day."""

    bomb_load_kg: float = 2000.0
    """Average bomb load per bomber in kg."""

    damage_per_kg_in_cep: float = 0.001
    """Damage fraction per kg of bombs landing within CEP of target center."""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class BomberStreamState:
    """Tracks the state of a bomber stream for one mission."""

    mission_id: str
    bomber_count: int
    escort_count: int = 0
    target_id: str = ""
    altitude_m: float = 6000.0
    approach_heading_deg: float = 0.0
    bombers_lost: int = 0
    escorts_lost: int = 0
    bombs_dropped: bool = False


@dataclass
class TargetDamageState:
    """Tracks cumulative damage to a strategic target."""

    target_id: str
    damage_fraction: float = 0.0  # 0.0 = undamaged, 1.0 = destroyed
    raids_received: int = 0
    last_raid_time_s: float = 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class StrategicBombingEngine:
    """WW2 strategic bombing operations engine.

    Parameters
    ----------
    config:
        Bombing configuration.
    rng:
        Numpy random generator.
    """

    def __init__(
        self,
        config: StrategicBombingConfig | None = None,
        *,
        rng: np.random.Generator,
    ) -> None:
        self._config = config or StrategicBombingConfig()
        self._rng = rng
        self._targets: dict[str, TargetDamageState] = {}

    def get_target_damage(self, target_id: str) -> TargetDamageState:
        """Get or create damage state for a target."""
        if target_id not in self._targets:
            self._targets[target_id] = TargetDamageState(target_id=target_id)
        return self._targets[target_id]

    def plan_mission(
        self,
        mission_id: str,
        bomber_count: int,
        escort_count: int = 0,
        target_id: str = "",
        altitude_m: float = 6000.0,
    ) -> BomberStreamState:
        """Plan a bombing mission.

        Returns
        -------
        BomberStreamState for the planned mission.
        """
        return BomberStreamState(
            mission_id=mission_id,
            bomber_count=bomber_count,
            escort_count=escort_count,
            target_id=target_id,
            altitude_m=altitude_m,
        )

    def execute_flak_defense(
        self,
        stream: BomberStreamState,
        num_passes: int = 1,
    ) -> int:
        """Apply flak defense — returns number of bombers lost.

        Pk scales inversely with altitude above reference.
        """
        cfg = self._config
        alt_factor = (cfg.flak_reference_altitude_m / max(stream.altitude_m, 1000.0)) ** 2
        pk = cfg.flak_pk_per_pass * alt_factor

        losses = 0
        remaining = stream.bomber_count - stream.bombers_lost
        for _ in range(num_passes):
            for _ in range(remaining):
                if self._rng.random() < pk:
                    losses += 1
                    remaining -= 1
                    if remaining <= 0:
                        break
            if remaining <= 0:
                break

        stream.bombers_lost += losses
        return losses

    def execute_fighter_intercept(
        self,
        stream: BomberStreamState,
        interceptor_count: int,
    ) -> dict[str, int]:
        """Apply fighter interception — returns bombers and interceptors lost.

        Escort fighters screen interceptors; remaining engage bombers.
        Bomber defensive fire shoots back at interceptors.
        """
        cfg = self._config

        # Escorts neutralize some interceptors
        effective_interceptors = int(
            interceptor_count * (1.0 - cfg.fighter_escort_effectiveness * min(
                stream.escort_count / max(interceptor_count, 1), 1.0
            ))
        )

        # Escort losses (simplified)
        escort_losses = 0
        if stream.escort_count > 0 and interceptor_count > 0:
            engagement_ratio = min(interceptor_count / stream.escort_count, 2.0)
            p_escort_loss = 0.1 * engagement_ratio
            for _ in range(min(stream.escort_count, interceptor_count)):
                if self._rng.random() < p_escort_loss:
                    escort_losses += 1
        stream.escorts_lost += escort_losses

        # Remaining interceptors attack bombers
        bomber_losses = 0
        remaining_bombers = stream.bomber_count - stream.bombers_lost
        for _ in range(effective_interceptors):
            if remaining_bombers <= 0:
                break
            # Each interceptor has ~20% chance per pass to down a bomber
            if self._rng.random() < 0.2:
                bomber_losses += 1
                remaining_bombers -= 1
        stream.bombers_lost += bomber_losses

        # Bomber defensive fire shoots back
        interceptor_losses = 0
        for _ in range(effective_interceptors):
            # Each bomber in formation can shoot
            p_down = cfg.bomber_defensive_fire_pk * min(remaining_bombers, 10) / 10
            if self._rng.random() < p_down:
                interceptor_losses += 1

        return {
            "bombers_lost": bomber_losses,
            "escorts_lost": escort_losses,
            "interceptors_lost": interceptor_losses,
        }

    def execute_bombing_run(
        self,
        stream: BomberStreamState,
    ) -> dict[str, Any]:
        """Execute the bombing run and compute target damage.

        CEP scales with altitude.  Damage is proportional to bomb weight
        landing within CEP of target center.

        Returns
        -------
        dict with keys: ``damage_inflicted``, ``total_damage``,
        ``bombs_on_target_fraction``, ``bombers_surviving``.
        """
        cfg = self._config
        surviving = stream.bomber_count - stream.bombers_lost
        if surviving <= 0:
            return {
                "damage_inflicted": 0.0,
                "total_damage": self.get_target_damage(stream.target_id).damage_fraction,
                "bombs_on_target_fraction": 0.0,
                "bombers_surviving": 0,
            }

        # CEP scales with altitude
        cep = cfg.formation_cep_m * (stream.altitude_m / cfg.norden_reference_altitude_m)

        # Each bomber drops bombs — fraction landing within CEP of target
        # Using circular normal: P(within CEP) = 1 - exp(-0.5 * (R/sigma)^2)
        # where sigma = CEP / 1.1774 (CEP is 50th percentile radius)
        sigma = cep / 1.1774
        total_bomb_kg = surviving * cfg.bomb_load_kg

        # Compute fraction of bombs on target (within 1 CEP)
        # For area bombing, use expected value = 0.5 (by definition of CEP)
        # But add randomness
        on_target_fraction = 0.5 * self._rng.uniform(0.7, 1.3)
        on_target_fraction = min(1.0, max(0.0, on_target_fraction))

        effective_kg = total_bomb_kg * on_target_fraction
        damage = effective_kg * cfg.damage_per_kg_in_cep
        damage = min(damage, 1.0)  # cap at 100%

        target_state = self.get_target_damage(stream.target_id)
        target_state.damage_fraction = min(1.0, target_state.damage_fraction + damage)
        target_state.raids_received += 1
        stream.bombs_dropped = True

        logger.info(
            "Bombing run on %s: %d bombers, CEP=%.0fm, damage=%.1f%%, total=%.1f%%",
            stream.target_id, surviving, cep, damage * 100,
            target_state.damage_fraction * 100,
        )

        return {
            "damage_inflicted": damage,
            "total_damage": target_state.damage_fraction,
            "bombs_on_target_fraction": on_target_fraction,
            "bombers_surviving": surviving,
        }

    def apply_target_regeneration(self, dt_s: float) -> None:
        """Regenerate target damage over time.

        Parameters
        ----------
        dt_s:
            Time step in seconds.
        """
        dt_days = dt_s / 86400.0
        regen = self._config.target_regeneration_rate * dt_days
        for target in self._targets.values():
            target.damage_fraction = max(0.0, target.damage_fraction - regen)

    def compute_target_damage(
        self,
        target_id: str,
        total_bomb_kg: float,
        cep_m: float,
    ) -> float:
        """Compute damage from a known bomb load and CEP.

        Utility function for direct computation without a stream.
        """
        sigma = cep_m / 1.1774
        on_target_fraction = 0.5  # expected value at CEP
        effective_kg = total_bomb_kg * on_target_fraction
        return min(1.0, effective_kg * self._config.damage_per_kg_in_cep)

    def get_state(self) -> dict[str, Any]:
        """Capture state for checkpointing."""
        return {
            "targets": {
                tid: {
                    "target_id": t.target_id,
                    "damage_fraction": t.damage_fraction,
                    "raids_received": t.raids_received,
                    "last_raid_time_s": t.last_raid_time_s,
                }
                for tid, t in self._targets.items()
            },
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore state from checkpoint."""
        self._targets.clear()
        for tid, tdata in state.get("targets", {}).items():
            self._targets[tid] = TargetDamageState(**tdata)
